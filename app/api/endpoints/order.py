from fastapi import APIRouter, HTTPException, Request, status
from app.models.order import OrderCreate, OrderResponse
from app.core.supabase import supabase
from app.services.payment import create_midtrans_transaction
from app.services.ticket_gen import generate_qr_ticket
from app.services.mailer import send_ticket_email
import uuid

router = APIRouter()

@router.post("/", response_model=OrderResponse)
async def create_new_order(order_data: OrderCreate):
    # 1. Cek Kategori & Kuota
    res = supabase.table("ticket_categories").select("*").eq("id", str(order_data.category_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Kategori tiket tidak ditemukan")
    
    category = res.data[0]
    
    # PERBAIKAN: Pastikan kuota cukup untuk jumlah yang dibeli
    if category['sold'] + order_data.quantity > category['quota']:
        raise HTTPException(status_code=400, detail="Maaf, sisa kuota tiket tidak mencukupi untuk pesanan Anda!")

    total_price = category['price'] * order_data.quantity

    # 2. Buat ID Pesanan & Simpan ke DB
    order_id = str(uuid.uuid4())
    order_payload = {
        "id": order_id,
        "full_name": order_data.full_name,
        "email": order_data.email,
        "whatsapp_no": order_data.whatsapp_no,
        "category_id": str(order_data.category_id),
        "quantity": order_data.quantity,  # PASTIKAN KOLOM INI ADA DI TABEL 'orders'
        "total_price": total_price,
        "status": "pending"
    }
    
    insert_res = supabase.table("orders").insert(order_payload).execute()
    if not insert_res.data:
        raise HTTPException(status_code=500, detail="Gagal menyimpan data pesanan")

    # 3. Request Token Midtrans (Lempar harga satuan & quantity)
    snap_token = create_midtrans_transaction(order_id, category['price'], order_data.quantity, order_data)
    
    if not snap_token:
        raise HTTPException(status_code=500, detail="Gagal terhubung ke layanan pembayaran")

    return OrderResponse(
        id=order_id,
        status="pending",
        total_price=total_price,
        message=snap_token
    )

@router.post("/webhook")
async def midtrans_webhook(request: Request):
    # Mengambil data JSON yang dikirim oleh Midtrans
    data = await request.json()
    
    order_id = data.get('order_id')
    transaction_status = data.get('transaction_status')
    fraud_status = data.get('fraud_status')

    # --- REVISI 1: PENYARING TESTING MIDTRANS ---
    # Jika Midtrans cuma ngetes URL (saat klik Update di Dashboard), 
    # kita langsung kembalikan sukses tanpa menyentuh Database agar tidak Error UUID.
    if not order_id or order_id.startswith("payment_notif_test"):
        return {"status": "success", "message": "Test notification received"}

    # Kita hanya proses jika statusnya 'capture' (kartu kredit) atau 'settlement' (VA/Gopay/dll)
    if transaction_status in ['capture', 'settlement']:
        if fraud_status == 'challenge':
            return {"status": "challenged"}
        
        # --- REVISI 2: CEK APAKAH SUDAH SUCCESS SEBELUMNYA ---
        # Mencegah tiket ter-generate dua kali jika Midtrans mengirim notifikasi ulang.
        check_order = supabase.table("orders").select("status").eq("id", order_id).execute()
        if check_order.data and check_order.data[0]['status'] == 'success':
            return {"status": "already_processed", "message": "Order already marked as success"}

        # 1. Update status orders di Supabase menjadi success
        supabase.table("orders").update({"status": "success"}).eq("id", order_id).execute()
        
        # 2. Ambil data order lengkap untuk proses pembuatan tiket
        order_res = supabase.table("orders").select("*, ticket_categories(name)").eq("id", order_id).execute()
        if not order_res.data:
            return {"status": "error", "message": "Order not found in database"}
        
        order_info = order_res.data[0]
        qty = order_info.get('quantity', 1) # Default 1 jika kolom quantity kosong
        cat_id = order_info['category_id']
        
        # 3. Update Jumlah Terjual di Tabel Kategori menggunakan RPC
        try:
            supabase.rpc('increment_sold', {'row_id': cat_id, 'amount': qty}).execute()
        except Exception as e:
            print(f"Log: Gagal update kuota terjual: {e}")

        # 4 & 5. Looping untuk membuat tiket sebanyak jumlah yang dibeli (Quantity)
        generated_ticket_urls = []
        for i in range(qty):
            # Membuat kode tiket unik (Contoh: TEDX-8ZQDX-1)
            # order_id[:8] mengambil 8 karakter pertama dari UUID agar tidak terlalu panjang
            short_id = str(order_id).split("-")[0].upper() 
            ticket_code = f"TEDX-{short_id}-{i+1}"
            
            # Memanggil fungsi generate QR dan PDF (Pastikan fungsi ini sudah kamu buat)
            public_pdf_url = generate_qr_ticket(ticket_code, order_info['full_name'])
            
            if public_pdf_url:
                # Simpan data tiket per lembar ke tabel 'tickets'
                supabase.table("tickets").insert({
                    "order_id": order_id,
                    "ticket_code": ticket_code,
                    "ticket_pdf_url": public_pdf_url
                }).execute()
                
                generated_ticket_urls.append(public_pdf_url)
        
        # 6. Kirim semua link tiket yang sudah digenerate ke email pembeli
        if generated_ticket_urls:
            send_ticket_email(
                order_info['email'], 
                order_info['full_name'], 
                generated_ticket_urls
            )
        
        return {
            "status": "success", 
            "message": f"{len(generated_ticket_urls)} Ticket(s) generated and sent to {order_info['email']}"
        }

    # Jika statusnya 'pending', 'expire', atau 'cancel', kita kembalikan status apa adanya
    return {"status": "info", "message": f"Transaction status is {transaction_status}"}