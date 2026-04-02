from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional

class OrderCreate(BaseModel):
    full_name: str
    email: EmailStr
    whatsapp_no: str
    category_id: UUID

class OrderResponse(BaseModel):
    id: UUID
    status: str
    total_price: int
    message: str  # Ini akan diisi Snap Token Midtrans