# app/services/ticket_gen.py
import qrcode
from PIL import Image
import os
from app.core.supabase import supabase

def generate_qr_ticket(ticket_code: str, buyer_name: str = "", seat: str = "", ticket_type: str = "FULL"):
    """
    Generator Tiket TEDxUII 3.0 (Versi Minimalis).
    Hanya men-generate QR Code dan menempelkannya ke template.
    """
    
    # 1. Tentukan Template berdasarkan Tipe Tiket (Sekarang ada 3)
    ticket_type_upper = ticket_type.upper()
    
    if "MORNING" in ticket_type_upper:
        template_path = "app/static/templates/template_morning.png"
    elif "AFTERNOON" in ticket_type_upper:
        template_path = "app/static/templates/template_afternoon.png"
    else:
        # Default fallback ke Full Session (jika tidak ada kata morning/afternoon)
        template_path = "app/static/templates/template_full.png"
        
    output_path = f"/tmp/out_{ticket_code}.jpg"
    
    if not os.path.exists(template_path):
        print(f"ERROR CRITICAL: Template tidak ditemukan di {template_path}")
        return None

    # Buka Template dan Konversi ke RGB (wajib untuk save ke JPG)
    img = Image.open(template_path).convert('RGB')
    width, height = img.size

    # 2. GENERATE & TEMPEL QR CODE
    # Gunakan border=1 agar ukuran QR maksimal mengisi area
    qr = qrcode.QRCode(version=1, box_size=10, border=1) 
    qr.add_data(ticket_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # Matematika Posisi QR (52% dari tinggi tiket)
    qr_size = int(height * 0.52) 
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    
    # Koordinat X dan Y untuk QR Code (Pusat kotak putus-putus)
    qr_x = int(width * 0.485) 
    qr_y = int(height * 0.31) 
    
    # Tempel QR ke gambar template
    img.paste(qr_img, (qr_x, qr_y)) 

    # 3. SIMPAN & UPLOAD KE SUPABASE
    # Gunakan quality=100 agar gambar QR tajam maksimal dan mudah di-scan
    img.save(output_path, "JPEG", quality=100) 
    
    file_name = f"public/{ticket_code}.jpg"
    try:
        with open(output_path, "rb") as f:
            supabase.storage.from_("tickets").upload(
                file_name, f, {"content-type": "image/jpeg", "upsert": "true"}
            )
        # Ambil Public URL
        public_url = supabase.storage.from_("tickets").get_public_url(file_name)
        
        # Kembalikan dictionary data untuk attachment email
        return {
            "public_url": public_url,
            "local_path": output_path
        }
        
    except Exception as e:
        print(f"Gagal upload tiket ke Supabase: {e}")
        return None