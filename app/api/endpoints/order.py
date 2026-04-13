from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from app.core.supabase import supabase
from app.services.ticket_gen import generate_ticket
from app.services.mailer import send_ticket_email
import uuid
import os

router = APIRouter()

# ==========================================
# FUNGSI PROSES TIKET & EMAIL (Dibuat Async)
# ==========================================
async def process_ticket_generation_and_email(order_id: str, qty: int, cat_id: str, full_name: str, email: str, ticket_type: str):
    """
    Fungsi ini ditunggu (await) agar Vercel tidak membunuh proses di tengah jalan.
    Hanya dijalankan ketika ADMIN menekan tombol APPROVE.
    """
    try:
        # 1. Update Jumlah Terjual di Tabel Kategori (Kuota baru berkurang saat di-approve)
        try:
            supabase.rpc('increment_sold', {'row_id': cat_id, 'amount': qty}).execute()
        except Exception as e:
            print(f"Log: Gagal update kuota terjual: {e}")

        # 2. Looping untuk membuat tiket
        generated_tickets = []
        for i in range(qty):
            short_id = str(order_id).split("-")[0].upper() 
            ticket_code = f"TEDX-{short_id}-{i+1}"
            
            # Generate gambar tiket fisik
            ticket_data = generate_ticket(
                ticket_code=ticket_code, 
                buyer_name=full_name, 
                ticket_type=ticket_type 
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
        
        # 3. Kirim email beserta GAMBARNYA
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
    
    # Mencegah user checkout jika kuota beneran habis
    if category['sold'] + quantity > category['quota']:
        raise HTTPException(status_code=400, detail="Maaf, sisa kuota tiket tidak mencukupi!")

    total_price = category['price'] * quantity
    order_id = str(uuid.uuid4())

    try:
        # 2. Upload Bukti Transfer ke Supabase Storage (Bucket: payment_proofs)
        file_ext = os.path.splitext(payment_proof.filename)[1] # Ambil ekstensi asli (misal: .jpg, .png)
        file_path = f"{order_id}{file_ext}" # Rename file dengan UUID pesanan biar rapi
        
        file_content = await payment_proof.read()
        
        supabase.storage.from_("payment_proofs").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": payment_proof.content_type}
        )
        
        # 3. Dapatkan URL Public Gambar
        proof_url = supabase.storage.from_("payment_proofs").get_public_url(file_path)

        # 4. Simpan Data ke Tabel Orders
        order_payload = {
            "id": order_id,
            "full_name": full_name,
            "email": email,
            "whatsapp_no": whatsapp_no,
            "category_id": category_id,
            "quantity": quantity,
            "total_price": total_price,
            "status": "pending",
            "payment_proof_url": proof_url # Simpan link foto
        }
        
        insert_res = supabase.table("orders").insert(order_payload).execute()
        if not insert_res.data:
            raise HTTPException(status_code=500, detail="Gagal menyimpan data pesanan ke database")

        return {
            "status": "success", 
            "message": "Pesanan berhasil dibuat. Bukti transfer sedang menunggu verifikasi panitia.",
            "order_id": order_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal memproses pesanan: {str(e)}")


# ==========================================
# ENDPOINT ADMIN: VERIFIKASI PEMBAYARAN
# ==========================================
@router.post("/approve/{order_id}")
async def admin_approve_order(order_id: str):
    # 1. Cari Pesanan
    order_res = supabase.table("orders").select("*, ticket_categories(name)").eq("id", order_id).execute()
    
    if not order_res.data:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")
        
    order_info = order_res.data[0]
    
    # 2. Cegah Double Approve
    if order_info['status'] == 'success':
        return {"status": "already_processed", "message": "Pesanan ini sudah sukses sebelumnya."}

    # 3. Ubah Status Jadi Success
    supabase.table("orders").update({"status": "success"}).eq("id", order_id).execute()
    
    # 4. Tembak Generator Tiket & Email (AWAIT)
    qty = order_info.get('quantity', 1) 
    cat_id = order_info['category_id']
    ticket_type_name = order_info['ticket_categories']['name']
    
    await process_ticket_generation_and_email(
        order_id=order_id,
        qty=qty,
        cat_id=cat_id,
        full_name=order_info['full_name'],
        email=order_info['email'],
        ticket_type=ticket_type_name
    )
    
    return {
        "status": "success", 
        "message": f"Verifikasi berhasil! Tiket sedang di-generate dan dikirim ke email peserta."
    }