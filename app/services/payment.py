import midtransclient
from app.core.config import settings

# Initialize Midtrans Client
snap = midtransclient.Snap(
    is_production=settings.MIDTRANS_IS_PRODUCTION,
    server_key=settings.MIDTRANS_SERVER_KEY,
    client_key=settings.MIDTRANS_CLIENT_KEY
)

def create_midtrans_transaction(order_id: str, amount: int, user_data):
    param = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": amount
        },
        "item_details": [{
            "id": "TICKET-001",
            "price": amount,
            "quantity": 1,
            "name": "TEDxUII Event Ticket"
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