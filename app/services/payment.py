import midtransclient
from app.core.config import settings

snap = midtransclient.Snap(
    is_production=settings.MIDTRANS_IS_PRODUCTION,
    server_key=settings.MIDTRANS_SERVER_KEY,
    client_key=settings.MIDTRANS_CLIENT_KEY
)

def create_midtrans_transaction(order_id: str, price_per_ticket: int, quantity: int, user_data):
    # Hitung total harga
    gross_amount = price_per_ticket * quantity

    param = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": gross_amount
        },
        "item_details": [{
            "id": str(user_data.category_id)[:10], # ID barang (opsional)
            "price": price_per_ticket,
            "quantity": quantity,
            "name": "TEDxUII 2026 Ticket"
        }],
        "customer_details": {
            "first_name": user_data.full_name,
            "email": user_data.email,
            "phone": user_data.whatsapp_no
        }
    }
    
    try:
        transaction = snap.create_transaction(param)
        return transaction['token']
    except Exception as e:
        print(f"Midtrans Error: {e}")
        return None