# app/services/ticket_gen.py
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
from app.core.supabase import supabase

def get_scalable_font(size):
    # Fungsi ini akan mencari font bawaan sistem agar ukurannya BISA dibesarkan
    # Tanpa perlu mengandalkan file font eksternal.
    system_fonts = [
        "arial.ttf", "DejaVuSans-Bold.ttf", "FreeSansBold.ttf", 
        "LiberationSans-Bold.ttf", "tahoma.ttf", "Helvetica"
    ]
    for font in system_fonts:
        try:
            return ImageFont.truetype(font, size)
        except IOError:
            continue
            
    # Jika sistem Vercel benar-benar kosong (sangat jarang terjadi), 
    # ini adalah fallback terakhir.
    return ImageFont.load_default()

def generate_qr_ticket(ticket_code: str, buyer_name: str, seat: str = "TBA", ticket_type: str = "FULL"):
    # 1. Tentukan Template
    if "FULL" in ticket_type.upper():
        template_path = "app/static/templates/template_full.png"
    else:
        template_path = "app/static/templates/template_one.png"
        
    output_path = f"/tmp/temp_{ticket_code}.jpg"
    
    if not os.path.exists(template_path):
        print(f"Error: Template tidak ditemukan di {template_path}")
        return None

    img = Image.open(template_path).convert('RGB')
    width, height = img.size

    # 2. Generate & Tempel QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=1) 
    qr.add_data(ticket_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    qr_size = int(height * 0.48) 
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    qr_x = int(width * 0.485) 
    qr_y = int(height * 0.33) 
    img.paste(qr_img, (qr_x, qr_y)) 

    # 3. SETUP FONT (Dinamis berdasarkan resolusi gambar)
    draw = ImageDraw.Draw(img)
    
    # Kita tidak pakai angka pasti seperti 96, tapi pakai PERSENTASE dari tinggi gambar.
    # Dijamin pasti besar berapapun resolusi gambarnya.
    size_name = int(height * 0.12)  # Font Nama: 12% dari tinggi tiket
    size_seat = int(height * 0.10)  # Font Seat: 10% dari tinggi tiket
    size_order = int(height * 0.08) # Font Order: 8% dari tinggi tiket

    font_name = get_scalable_font(size_name)
    font_seat = get_scalable_font(size_seat)
    font_order = get_scalable_font(size_order)

    # 4. KOORDINAT TEKS
    name_x = int(width * 0.09)
    name_y = int(height * 0.48)
    
    seat_x = int(width * 0.31)
    seat_y = int(height * 0.48)
    
    order_x = int(width * 0.755)
    order_y = int(height * 0.54)

    # 5. CETAK TEKS KE TIKET
    draw.text((name_x, name_y), buyer_name.upper()[:15], fill="#FFFFFF", font=font_name)
    draw.text((seat_x, seat_y), seat.upper(), fill="#FFFFFF", font=font_seat)
    draw.text((order_x, order_y), ticket_code, fill="#000000", font=font_order)
    
    # 6. Simpan & Upload
    img.save(output_path, "JPEG", quality=100) 
    
    file_name = f"public/{ticket_code}.jpg"
    try:
        with open(output_path, "rb") as f:
            supabase.storage.from_("tickets").upload(
                file_name, f, {"content-type": "image/jpeg", "upsert": "true"}
            )
        public_url = supabase.storage.from_("tickets").get_public_url(file_name)
        
        return {
            "public_url": public_url,
            "local_path": output_path
        }
    except Exception as e:
        print(f"Gagal upload tiket: {e}")
        return None