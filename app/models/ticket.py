from pydantic import BaseModel
from uuid import UUID
from typing import Optional

class TicketResponse(BaseModel):
    id: UUID
    ticket_code: str
    is_used: bool
    ticket_pdf_url: Optional[str]