# app/services/ticket_gen.py
import qrcode
from PIL import Image
import os
from app.core.supabase import supabase

def generate_qr_ticket(ticket_code: str, buyer_name: str):
    # 1. Tentukan path template desain kamu
    template_path = "app/static/templates/desain_tiket.png" 
    output_path = f"/tmp/temp_{ticket_code}.jpg"
    
    if not os.path.exists(template_path):
        return None

    # 2. Generate QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(ticket_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # Resize QR Code jika diperlukan (misal 300x300 pixel)
    qr_img = qr_img.resize((300, 300))

    # 3. Buka Desain Tiket
    img = Image.open(template_path)
    
    # 4. Tempel QR Code ke koordinat tertentu (Ganti x, y sesuai desainmu)
    # Misal: ditaruh di pojok kanan bawah
    img.paste(qr_img, (1500, 2000)) 
    
    # 5. Simpan sementara
    img.save(output_path, quality=95)
    
    # 6. Upload ke Supabase Storage (Folder public sesuai policy tadi)
    file_name = f"public/{ticket_code}.jpg"
    with open(output_path, "rb") as f:
        supabase.storage.from_("tickets").upload(file_name, f, {"content-type": "image/jpeg"})
    
    # 7. Ambil Public URL
    public_url = supabase.storage.from_("tickets").get_public_url(file_name)
    
    # Hapus file sementara di server
    os.remove(output_path)
    
    return public_url