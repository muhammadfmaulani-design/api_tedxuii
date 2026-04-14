from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.core.supabase import supabase
from app.services.ticket_gen import generate_ticket
from app.services.mailer import send_ticket_email
import uuid
import os

router = APIRouter()

# ==========================================
# LOGIKA PEMILIHAN KURSI OTOMATIS (Prioritas & VIP)
# ==========================================
def get_auto_assigned_seats(supabase_client, quantity: int):
    # 1. Ambil semua kursi yang masih tersedia
    response = supabase_client.table("seats").select("id").eq("is_booked", False).execute()
    free_seats = response.data
    
    if not free_seats or len(free_seats) < quantity:
        return None

    def seat_priority(seat_id):
        section = seat_id[0] # A, B, atau C
        num = int(seat_id[1:]) # Nomor kursi
        
        # --- LEVEL 1: PRIORITAS UTAMA (Putaran Pertama) ---
        if section == 'A' and 1 <= num <= 16: return 1
        if section == 'B' and 9 <= num <= 30: return 2 # Lompat B1-B8 untuk VIP
        if section == 'C' and 1 <= num <= 16: return 3
            
        # --- LEVEL 2: SISA KURSI (Putaran Kedua) ---
        if section == 'A': return 4
        if section == 'B' and num > 30: return 5
        if section == 'C': return 6

        # Level Terakhir: B1 - B8 (Hanya diisi jika benar-benar penuh/opsional)
        if section == 'B' and 1 <= num <= 8: return 7
            
        return 8

    # Sortir semua kursi kosong berdasarkan bobot prioritas di atas
    sorted_free_seats = sorted(
        free_seats, 
        key=lambda x: (seat_priority(x['id']), x['id'][0], int(x['id'][1:]))
    )
    
    # Ambil kursi sebanyak jumlah pesanan
    assigned_ids = [s['id'] for s in sorted_free_seats[:quantity]]
    return assigned_ids

# ==========================================
# FUNGSI PROSES TIKET & EMAIL (Dibuat Async)
# ==========================================
async def process_ticket_generation_and_email(order_id: str, qty: int, cat_id: str, full_name: str, email: str, ticket_type: str, assigned_seats_str: str):
    """
    Fungsi ini ditunggu (await) agar Vercel tidak membunuh proses di tengah jalan.
    Hanya dijalankan ketika ADMIN menekan tombol APPROVE.
    """
    try:
        # 1. Update Jumlah Terjual di Tabel Kategori
        try:
            supabase.rpc('increment_sold', {'row_id': cat_id, 'amount': qty}).execute()
        except Exception as e:
            print(f"Log: Gagal update kuota terjual: {e}")

        # 2. Pecah string kursi (misal: "A1, A2" jadi list ['A1', 'A2'])
        seat_list = [s.strip() for s in assigned_seats_str.split(",")] if assigned_seats_str else []

        # 3. Looping untuk membuat tiket fisik
        generated_tickets = []
        for i in range(qty):
            short_id = str(order_id).split("-")[0].upper() 
            ticket_code = f"TEDX-{short_id}-{i+1}"
            
            # Ambil kursi spesifik untuk tiket ini (kalau tidak ada, fallback ke TBD)
            current_seat = seat_list[i] if i < len(seat_list) else "TBD"
            
            # Generate gambar tiket fisik dengan membawa data kursi
            ticket_data = generate_ticket(
                ticket_code=ticket_code, 
                buyer_name=full_name, 
                ticket_type=ticket_type,
                seat_number=current_seat
            )
            
            if ticket_data:
                db_url = ticket_data.get("public_url", "") 
                
                supabase.table("tickets").insert({
                    "order_id": order_id,
                    "ticket_code": ticket_code,
                    "ticket_pdf_url": db_url
                }).execute()
                
                # Simpan seluruh dict (local_path & seat) untuk dilampirkan ke email
                generated_tickets.append(ticket_data)
        
        # 4. Kirim email beserta GAMBARNYA
        if generated_tickets:
            send_ticket_email(email, full_name, generated_tickets)
            print(f"Log: Sukses mengirim {len(generated_tickets)} tiket ke {email}")
            
    except Exception as e:
        print(f"Critical Error on Process Task: {str(e)}")


# ==========================================
# ENDPOINT CREATE ORDER (Upload Bukti Bayar)
# ==========================================
@router.post("/")
async def create_new_order(
    full_name: str = Form(...),
    email: str = Form(...),
    whatsapp_no: str = Form(...),
    category_id: str = Form(...),
    quantity: int = Form(...),
    payment_proof: UploadFile = File(...)
):
    # 1. Cek Kategori & Kuota Sementara
    res = supabase.table("ticket_categories").select("*").eq("id", category_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Kategori tiket tidak ditemukan")
    
    category = res.data[0]
    
    if category['sold'] + quantity > category['quota']:
        raise HTTPException(status_code=400, detail="Maaf, sisa kuota tiket tidak mencukupi!")

    # 1.5 ALOKASIKAN KURSI SECARA OTOMATIS
    assigned_seats = get_auto_assigned_seats(supabase, quantity)
    if not assigned_seats:
        raise HTTPException(status_code=400, detail="Maaf, tidak ada kursi yang cukup untuk jumlah pesanan ini.")
        
    seats_string = ", ".join(assigned_seats)
    total_price = category['price'] * quantity
    order_id = str(uuid.uuid4())

    try:
        # 2. Upload Bukti Transfer ke Supabase Storage (Bucket: payment_proofs)
        file_ext = os.path.splitext(payment_proof.filename)[1]
        file_path = f"{order_id}{file_ext}" 
        
        file_content = await payment_proof.read()
        
        supabase.storage.from_("payment_proofs").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": payment_proof.content_type}
        )
        
        proof_url = supabase.storage.from_("payment_proofs").get_public_url(file_path)

        # 3. Simpan Data ke Tabel Orders
        order_payload = {
            "id": order_id,
            "full_name": full_name,
            "email": email,
            "whatsapp_no": whatsapp_no,
            "category_id": category_id,
            "quantity": quantity,
            "total_price": total_price,
            "status": "pending",
            "payment_proof_url": proof_url,
            "assigned_seats": seats_string
        }
        
        insert_res = supabase.table("orders").insert(order_payload).execute()
        if not insert_res.data:
            raise HTTPException(status_code=500, detail="Gagal menyimpan data pesanan ke database")

        # 4. KUNCI KURSI DI TABEL SEATS AGAR TIDAK DIAMBIL ORANG LAIN
        supabase.table("seats").update({
            "is_booked": True,
            "order_id": order_id
        }).in_("id", assigned_seats).execute()

        return {
            "status": "success", 
            "message": "Pesanan berhasil dibuat. Bukti transfer sedang menunggu verifikasi panitia.",
            "order_id": order_id,
            "seats": seats_string
        }

    except Exception as e:
        # Lepaskan kursi jika pesanan gagal diproses
        supabase.table("seats").update({"is_booked": False, "order_id": None}).in_("id", assigned_seats).execute()
        raise HTTPException(status_code=500, detail=f"Gagal memproses pesanan: {str(e)}")


# ==========================================
# ENDPOINT ADMIN: VERIFIKASI PEMBAYARAN
# ==========================================
@router.post("/approve/{order_id}")
async def admin_approve_order(order_id: str):
    order_res = supabase.table("orders").select("*, ticket_categories(name)").eq("id", order_id).execute()
    
    if not order_res.data:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        
    order_info = order_res.data[0]
    
    if order_info['status'] == 'success':
        return {"status": "already_processed", "message": "Pesanan ini sudah sukses sebelumnya."}

    supabase.table("orders").update({"status": "success"}).eq("id", order_id).execute()
    
    qty = order_info.get('quantity', 1) 
    cat_id = order_info['category_id']
    ticket_type_name = order_info['ticket_categories']['name']
    
    await process_ticket_generation_and_email(
        order_id=order_id,
        qty=qty,
        cat_id=cat_id,
        full_name=order_info['full_name'],
        email=order_info['email'],
        ticket_type=ticket_type_name,
        assigned_seats_str=order_info.get('assigned_seats', '')
    )
    
    return {
        "status": "success", 
        "message": f"Verifikasi berhasil! Tiket (Kursi: {order_info.get('assigned_seats', '-')}) sedang di-generate dan dikirim ke email peserta."
    }