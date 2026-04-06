# app/services/ticket_gen.py
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
import urllib.request
from app.core.supabase import supabase

def get_robust_font(size):
    """
    Mencari font sistem atau mendownload font standar jika tidak ada.
    Dijamin bisa di-resize, bukan font default PIL yang kaku.
    """
    # 1. Daftar lokasi font umum di Linux (Vercel)
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    
    # 2. Cek apakah ada font sistem yang tersedia
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
            
    # 3. JIKA TIDAK ADA: Download font standar ke /tmp (Solusi Pamungkas)
    # Ini hanya berjalan sekali, selanjutnya akan mengambil dari /tmp
    tmp_font = "/tmp/font_temp.ttf"
    if not os.path.exists(tmp_font):
        try:
            url = "https://github.com/google/fonts/raw/main/apache/robotocondensed/RobotoCondensed-Bold.ttf"
            urllib.request.urlretrieve(url, tmp_font)
        except Exception:
            return ImageFont.load_default() # Fallback terakhir jika internet mati

    return ImageFont.truetype(tmp_font, size)

def generate_qr_ticket(ticket_code: str, buyer_name: str, seat: str = "TBA", ticket_type: str = "FULL"):
    # 1. Tentukan Template (Gunakan PNG sesuai file terbaru kamu)
    if "FULL" in ticket_type.upper():
        template_path = "app/static/templates/template_full.png"
    else:
        template_path = "app/static/templates/template_one.png"
        
    output_path = f"/tmp/out_{ticket_code}.jpg"
    
    if not os.path.exists(template_path):
        print(f"Error: Template tidak ditemukan di {template_path}")
        return None

    # Gunakan .convert('RGB') agar bisa disave ke JPG dengan aman
    img = Image.open(template_path).convert('RGB')
    width, height = img.size

    # 2. Generate QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=1) 
    qr.add_data(ticket_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # Ukuran QR: 48% dari tinggi tiket
    qr_size = int(height * 0.48) 
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    
    # Koordinat QR (Pusat kotak putus-putus)
    qr_x = int(width * 0.485) 
    qr_y = int(height * 0.33) 
    img.paste(qr_img, (qr_x, qr_y)) 

    # 3. SETUP FONT BESAR (Berdasarkan persentase tinggi gambar)
    draw = ImageDraw.Draw(img)
    
    # Ukuran font diperbesar agar mantap sesuai desain Figma
    font_name = get_robust_font(int(height * 0.13))  # 13% Tinggi
    font_seat = get_robust_font(int(height * 0.11))  # 11% Tinggi
    font_order = get_robust_font(int(height * 0.09)) # 9% Tinggi

    # 4. KOORDINAT TEKS
    name_x = int(width * 0.09)
    name_y = int(height * 0.46) # Sedikit lebih naik agar pas di tengah area hitam
    
    seat_x = int(width * 0.31)
    seat_y = int(height * 0.46)
    
    order_x = int(width * 0.755)
    order_y = int(height * 0.54)

    # 5. CETAK TEKS
    # Nama dan Seat di area gelap (Putih)
    draw.text((name_x, name_y), buyer_name.upper()[:15], fill="#FFFFFF", font=font_name)
    draw.text((seat_x, seat_y), seat.upper(), fill="#FFFFFF", font=font_seat)
    
    # Order Number di area putih (Hitam)
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
        
        # Kembalikan path lokal untuk attachment email
        return {
            "public_url": public_url,
            "local_path": output_path
        }
    except Exception as e:
        print(f"Gagal upload tiket: {e}")
        return None