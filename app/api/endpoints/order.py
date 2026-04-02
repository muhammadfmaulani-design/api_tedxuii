# app/api/endpoints/order.py
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
    """
    Endpoint untuk membuat pesanan baru dari Frontend
    """
    # 1. Cek Kategori & Kuota di Supabase
    res = supabase.table("ticket_categories").select("*").eq("id", str(order_data.category_id)).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Kategori tiket tidak ditemukan")
    
    category = res.data[0]
    if category['sold'] >= category['quota']:
        raise HTTPException(status_code=400, detail="Maaf, kuota tiket sudah habis!")

    # 2. Buat ID Pesanan & Simpan ke DB
    order_id = str(uuid.uuid4())
    order_payload = {
        "id": order_id,
        "full_name": order_data.full_name,
        "email": order_data.email,
        "whatsapp_no": order_data.whatsapp_no,
        "category_id": str(order_data.category_id),
        "total_price": category['price'],
        "status": "pending"
    }
    
    insert_res = supabase.table("orders").insert(order_payload).execute()
    if not insert_res.data:
        raise HTTPException(status_code=500, detail="Gagal menyimpan data pesanan")

    # 3. Dapatkan Snap Token dari Midtrans
    snap_token = create_midtrans_transaction(order_id, category['price'], order_data)
    
    if not snap_token:
        raise HTTPException(status_code=500, detail="Gagal terhubung ke layanan pembayaran")

    return OrderResponse(
        id=order_id,
        status="pending",
        total_price=category['price'],
        message=snap_token # Token ini akan dibuka oleh Midtrans Snap di Frontend
    )

@router.post("/webhook")
async def midtrans_webhook(request: Request):
    """
    Endpoint otomatis yang dipanggil Midtrans saat user selesai bayar
    """
    data = await request.json()
    
    order_id = data.get('order_id')
    transaction_status = data.get('transaction_status')
    fraud_status = data.get('fraud_status')

    # Logika: Jika pembayaran sukses
    if transaction_status == 'capture' or transaction_status == 'settlement':
        if fraud_status == 'challenge':
            # Pembayaran dicurigai fraud (jarang terjadi di dev mode)
            return {"status": "challenged"}
        
        # 1. UPDATE STATUS ORDER JADI SUCCESS
        supabase.table("orders").update({"status": "success"}).eq("id", order_id).execute()
        
        # 2. AMBIL DATA PEMBELI
        order_res = supabase.table("orders").select("*, ticket_categories(name)").eq("id", order_id).execute()
        if not order_res.data:
            return {"status": "error", "message": "Order not found"}
        
        order_info = order_res.data[0]
        
        # 3. UPDATE JUMLAH TERJUAL DI KATEGORI
        cat_id = order_info['category_id']
        supabase.rpc('increment_sold', {'row_id': cat_id}).execute() 
        # Catatan: Kamu perlu buat function 'increment_sold' di SQL Supabase (opsional)

        # 4. GENERATE TIKET & BARCODE
        ticket_code = f"TEDXUII-{order_id[:8].upper()}"
        public_pdf_url = generate_qr_ticket(ticket_code, order_info['full_name'])
        
        # 5. SIMPAN KE TABEL TICKETS
        supabase.table("tickets").insert({
            "order_id": order_id,
            "ticket_code": ticket_code,
            "ticket_pdf_url": public_pdf_url
        }).execute()
        
        # 6. KIRIM EMAIL KE PESERTA
        send_ticket_email(order_info['email'], order_info['full_name'], public_pdf_url)
        
        return {"status": "success", "message": "Ticket generated and sent"}

    return {"status": "pending/other"}