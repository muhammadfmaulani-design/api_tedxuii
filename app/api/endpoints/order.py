from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from app.core.supabase import supabase
from app.services.ticket_gen import generate_ticket
from app.services.mailer import send_ticket_email, send_order_rejection_email
import uuid
import os

router = APIRouter()
ORDERS_REJECT_METADATA_SUPPORTED = True


class RejectOrderRequest(BaseModel):
    reason: str


def parse_assigned_seats(assigned_seats_str: str) -> list[str]:
    if not assigned_seats_str:
        return []
    return [seat.strip() for seat in assigned_seats_str.split(",") if seat.strip()]


def serialize_public_order(order_row: dict, ticket_rows: list[dict]) -> dict:
    category_info = order_row.get("ticket_categories") or {}

    return {
        "id": order_row.get("id"),
        "full_name": order_row.get("full_name"),
        "email": order_row.get("email"),
        "whatsapp_no": order_row.get("whatsapp_no"),
        "status": order_row.get("status"),
        "quantity": order_row.get("quantity", 0),
        "total_price": order_row.get("total_price", 0),
        "assigned_seats": parse_assigned_seats(order_row.get("assigned_seats", "")),
        "payment_proof_url": order_row.get("payment_proof_url"),
        "created_at": order_row.get("created_at"),
        "ticket_category": category_info.get("name"),
        "tickets": [
            {
                "id": ticket.get("id"),
                "ticket_code": ticket.get("ticket_code"),
                "is_used": ticket.get("is_used", False),
                "ticket_pdf_url": ticket.get("ticket_pdf_url")
            }
            for ticket in ticket_rows
        ]
    }


def update_order_rejected_status(order_id: str, reason: str):
    global ORDERS_REJECT_METADATA_SUPPORTED

    if not ORDERS_REJECT_METADATA_SUPPORTED:
        return supabase.table("orders").update({"status": "rejected"}).eq("id", order_id).execute()

    payload_with_reason = {
        "status": "rejected",
        "rejected_reason": reason,
        "rejected_at": "now()"
    }

    try:
        return supabase.table("orders").update(payload_with_reason).eq("id", order_id).execute()
    except Exception as first_error:
        error_text = str(first_error)
        if "rejected_reason" in error_text or "rejected_at" in error_text:
            ORDERS_REJECT_METADATA_SUPPORTED = False
            return supabase.table("orders").update({"status": "rejected"}).eq("id", order_id).execute()
        raise first_error


# ==========================================
# LOGIKA PEMILIHAN KURSI OTOMATIS (Prioritas & VIP)
# ==========================================
def get_auto_assigned_seats(supabase_client, quantity: int):
    response = supabase_client.table("seats").select("id").eq("is_booked", False).execute()
    free_seats = response.data

    if not free_seats or len(free_seats) < quantity:
        return None

    def seat_priority(seat_id):
        section = seat_id[0]
        num = int(seat_id[1:])

        if section == 'A' and 1 <= num <= 16: return 1
        if section == 'B' and 9 <= num <= 30: return 2
        if section == 'C' and 1 <= num <= 16: return 3

        if section == 'A': return 4
        if section == 'B' and num > 30: return 5
        if section == 'C': return 6

        if section == 'B' and 1 <= num <= 8: return 7

        return 8

    sorted_free_seats = sorted(
        free_seats,
        key=lambda x: (seat_priority(x['id']), x['id'][0], int(x['id'][1:]))
    )

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

        seat_list = parse_assigned_seats(assigned_seats_str)

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


@router.get("/public")
async def get_public_orders():
    try:
        orders_res = supabase.table("orders").select("*, ticket_categories(name)").execute()
        orders = orders_res.data or []

        if not orders:
            return {"status": "success", "count": 0, "orders": []}

        order_ids = [order["id"] for order in orders if order.get("id")]
        tickets_by_order_id = {order_id: [] for order_id in order_ids}

        if order_ids:
            tickets_res = (
                supabase.table("tickets")
                .select("id, order_id, ticket_code, is_used, ticket_pdf_url")
                .in_("order_id", order_ids)
                .execute()
            )

            for ticket in tickets_res.data or []:
                order_id = ticket.get("order_id")
                if order_id in tickets_by_order_id:
                    tickets_by_order_id[order_id].append(ticket)

        sorted_orders = sorted(
            orders,
            key=lambda order: (
                order.get("created_at") is None,
                order.get("created_at") or "",
                order.get("full_name") or ""
            ),
            reverse=True
        )

        return {
            "status": "success",
            "count": len(sorted_orders),
            "orders": [
                serialize_public_order(order, tickets_by_order_id.get(order["id"], []))
                for order in sorted_orders
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil daftar order: {str(e)}")


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
    res = supabase.table("ticket_categories").select("*").eq("id", category_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Kategori tiket tidak ditemukan")

    category = res.data[0]

    if category['sold'] + quantity > category['quota']:
        raise HTTPException(status_code=400, detail="Maaf, sisa kuota tiket tidak mencukupi!")

    assigned_seats = get_auto_assigned_seats(supabase, quantity)
    if not assigned_seats:
        raise HTTPException(status_code=400, detail="Maaf, tidak ada kursi yang cukup untuk jumlah pesanan ini.")

    seats_string = ", ".join(assigned_seats)
    total_price = category['price'] * quantity
    order_id = str(uuid.uuid4())

    try:
        file_ext = os.path.splitext(payment_proof.filename)[1]
        file_path = f"{order_id}{file_ext}"

        file_content = await payment_proof.read()

        supabase.storage.from_("payment_proofs").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": payment_proof.content_type}
        )

        proof_url = supabase.storage.from_("payment_proofs").get_public_url(file_path)

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


# ==========================================
# ENDPOINT ADMIN: TOLAK PEMBAYARAN
# ==========================================
@router.post("/reject/{order_id}")
async def admin_reject_order(order_id: str, payload: RejectOrderRequest):
    order_res = supabase.table("orders").select("*").eq("id", order_id).execute()

    if not order_res.data:
        raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan")

    order_info = order_res.data[0]
    current_status = order_info.get("status")
    reason = payload.reason.strip()

    if not reason:
        raise HTTPException(status_code=400, detail="Alasan reject wajib diisi.")

    if current_status == "success":
        raise HTTPException(status_code=400, detail="Pesanan yang sudah disetujui tidak bisa ditolak.")

    if current_status == "rejected":
        return {"status": "already_rejected", "message": "Pesanan ini sudah ditolak sebelumnya."}

    assigned_seats = parse_assigned_seats(order_info.get("assigned_seats", ""))

    update_order_rejected_status(order_id, reason)

    if assigned_seats:
        supabase.table("seats").update({
            "is_booked": False,
            "order_id": None
        }).in_("id", assigned_seats).execute()

    send_order_rejection_email(order_info.get("email", ""), order_info.get("full_name", "Peserta"), reason)

    return {
        "status": "success",
        "message": f"Pesanan berhasil ditolak. Kursi {order_info.get('assigned_seats', '-')} telah dilepas kembali dan email notifikasi telah dikirim.",
        "reason": reason
    }
