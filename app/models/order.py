from pydantic import BaseModel, EmailStr
from uuid import UUID

class OrderCreate(BaseModel):
    full_name: str
    email: EmailStr
    whatsapp_no: str
    category_id: UUID
    quantity: int = 1

class OrderResponse(BaseModel):
    id: UUID
    status: str
    total_price: int
    message: str