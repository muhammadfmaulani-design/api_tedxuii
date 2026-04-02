from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import order # Pastikan file di endpoints namanya order.py
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(order.router, prefix="/api/v1/orders", tags=["Orders"])

@app.get("/")
def read_root():
    return {"status": "Active", "message": "Welcome to TEDxUII Ticketing API"}