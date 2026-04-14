from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import order 
from app.api.endpoints import ticket_scanner
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "https://www.tedxuii.com",
        "https://tedxuii.com",
        "https://operasional-tedxuii.vercel.app"
    ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(order.router, prefix="/api/v1/orders", tags=["Orders"])
app.include_router(ticket_scanner.router, prefix="/api/v1/ticket-scanner", tags=["Ticket Scanner"]) # 2. TAMBAHKAN ROUTER INI

@app.get("/")
def read_root():
    return {"status": "Active", "message": "Welcome to TEDxUII Ticketing API"}