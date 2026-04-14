from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.core.supabase import supabase
from app.services.ticket_gen import generate_ticket
from app.services.mailer import send_ticket_email
import uuid
import os

router = APIRouter()

# ==========================================
# LOGIKA PEMILIHAN KURSI OTOMATIS (Berdasarkan Sesi)
# ==========================================
def get_auto_assigned_seats(supabase_client, quantity: int, ticket_type: str):
    t_type = ticket_type.upper()
    
    # 1. Tentukan query berdasarkan sesi tiket
    query = supabase_client.table("seats").select("id")
    
    if "MORNING" in t_type:
        query = query.eq("is_booked_morning", False)
    elif "AFTERNOON" in t_type:
        query = query.eq("is_booked_afternoon", False)
    else: # Tiket FULL DAY
        query = query.eq("is_booked_morning", False).eq("is_booked_afternoon", False)
        
    response = query.execute()
    free_seats = response.data
    
    if not free_seats or len(free_seats) < quantity:
        return None

    def seat_priority(seat_id):
        section = seat_id[0] # A, B, atau C
        num = int(seat_id[1:]) # Nomor kursi
        
        # --- LEVEL 1: PRIORITAS UTAMA ---
        if section == 'A' and 1 <= num <= 16: return 1
        if section == 'B' and 9 <= num <= 30: return 2 # Lompat B1-B8 untuk VIP
        if section == 'C' and 1 <= num <= 16: return 3
            
        # --- LEVEL 2: SISA KURSI ---
        if section == 'A': return 4
        if section == 'B' and num > 30: return 5
        if section == 'C': return 6

        # Level Terakhir: B1 - B8
        if section == 'B' and 1 <= num <= 8: return 7
            
        return 8

    # Sortir semua kursi kosong
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
    try:
        try:
            supabase.rpc('increment_sold', {'row_id': cat_id, 'amount': qty}).execute()
        except Exception as e:
            print(f"Log: Gagal update kuota terjual: {e}")

        seat_list = [s.strip() for s in assigned_seats_str.split(",")] if assigned_seats_str else []

        generated_tickets = []
        for i in range(qty):
            short_id = str(order_id).split("-")[0].upper() 
            ticket_code = f"TEDX-{short_id}-{i+1}"
            
            current_seat = seat_list[i] if i < len(seat_list) else "TBD"
            
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
                
                generated_tickets.append(ticket_data)
        
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
    # 1. Cek Kategori & Kuota
    res = supabase.table("ticket_categories").select("*").eq("id", category_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Kategori tiket tidak ditemukan")
    
    category = res.data[0]
    t_type = category['name'].upper()
    
    if category['sold'] + quantity > category['quota']:
        raise HTTPException(status_code=400, detail="Maaf, sisa kuota tiket tidak mencukupi!")

    # 1.5 ALOKASIKAN KURSI SESUAI SESI
    assigned_seats = get_auto_assigned_seats(supabase, quantity, t_type)
    if not assigned_seats:
        raise HTTPException(status_code=400, detail="Maaf, kursi untuk sesi ini sudah penuh!")
        
    seats_string = ", ".join(assigned_seats)
    total_price = category['price'] * quantity
    order_id = str(uuid.uuid4())

    try:
        # 2. Upload Bukti Transfer
        file_ext = os.path.splitext(payment_proof.filename)[1]
        file_path = f"{order_id}{file_ext}" 
        
        file_content = await payment_proof.read()
        supabase.storage.from_("payment_proofs").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": payment_proof.content_type}
        )
        proof_url = supabase.storage.from_("payment_proofs").get_public_url(file_path)

        # 3. Simpan Data Pesanan
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
            raise HTTPException(status_code=500, detail="Gagal menyimpan pesanan")

        # 4. KUNCI KURSI BERDASARKAN SESI
        update_data = {}
        if "MORNING" in t_type:
            update_data = {"is_booked_morning": True, "order_id_morning": order_id}
        elif "AFTERNOON" in t_type:
            update_data = {"is_booked_afternoon": True, "order_id_afternoon": order_id}
        else: # FULL
            update_data = {
                "is_booked_morning": True, 
                "is_booked_afternoon": True, 
                "order_id_morning": order_id, 
                "order_id_afternoon": order_id
            }

        supabase.table("seats").update(update_data).in_("id", assigned_seats).execute()

        return {
            "status": "success", 
            "message": "Pesanan berhasil. Menunggu verifikasi.",
            "order_id": order_id,
            "seats": seats_string
        }

    except Exception as e:
        # FAIL-SAFE: Lepaskan kursi sesuai sesi jika terjadi error saat upload/insert
        rollback_data = {}
        if "MORNING" in t_type:
            rollback_data = {"is_booked_morning": False, "order_id_morning": None}
        elif "AFTERNOON" in t_type:
            rollback_data = {"is_booked_afternoon": False, "order_id_afternoon": None}
        else:
            rollback_data = {
                "is_booked_morning": False, "is_booked_afternoon": False, 
                "order_id_morning": None, "order_id_afternoon": None
            }
        supabase.table("seats").update(rollback_data).in_("id", assigned_seats).execute()
        raise HTTPException(status_code=500, detail=f"Gagal memproses: {str(e)}")


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
        return {"status": "already_processed", "message": "Sudah sukses sebelumnya."}

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
        "message": f"Verifikasi berhasil! Tiket (Kursi: {order_info.get('assigned_seats', '-')}) sedang dikirim."
    }

# ==========================================
# ENDPOINT ADMIN: TOLAK PEMBAYARAN (REJECT)
# ==========================================
@router.post("/reject/{order_id}")
async def admin_reject_order(order_id: str):
    # 1. Cari data pesanan dan kategori tiketnya
    order_res = supabase.table("orders").select("*, ticket_categories(name)").eq("id", order_id).execute()
    
    if not order_res.data:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        
    order_info = order_res.data[0]
    t_type = order_info['ticket_categories']['name'].upper()
    assigned_seats_str = order_info.get('assigned_seats', '')
    
    # 2. Ubah status pesanan menjadi 'rejected'
    supabase.table("orders").update({"status": "rejected"}).eq("id", order_id).execute()
    
    # 3. LEPASKAN KURSI SESUAI SESI
    if assigned_seats_str:
        seat_list = [s.strip() for s in assigned_seats_str.split(",")]
        
        rollback_data = {}
        if "MORNING" in t_type:
            rollback_data = {"is_booked_morning": False, "order_id_morning": None}
        elif "AFTERNOON" in t_type:
            rollback_data = {"is_booked_afternoon": False, "order_id_afternoon": None}
        else:
            rollback_data = {
                "is_booked_morning": False, "is_booked_afternoon": False, 
                "order_id_morning": None, "order_id_afternoon": None
            }
            
        supabase.table("seats").update(rollback_data).in_("id", seat_list).execute()
    
    return {
        "status": "success", 
        "message": f"Pesanan ditolak. Kursi {assigned_seats_str} telah tersedia kembali."
    }