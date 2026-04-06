# app/services/ticket_gen.py
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
from app.core.supabase import supabase

def generate_qr_ticket(ticket_code: str, buyer_name: str, seat: str = "TBA", ticket_type: str = "FULL"):
    # 1. Pastikan logika pemilihan template BENAR
    # Gunakan .upper() dan cek substring untuk menghindari error typo
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

    # 2. Generate QR Code (Tanpa border berlebih)
    qr = qrcode.QRCode(version=1, box_size=10, border=1) 
    qr.add_data(ticket_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # 3. Besarkan ukuran QR dan taruh di tengah kotak putus-putus
    qr_size = int(height * 0.48) # Dibesarkan jadi 48% tinggi tiket
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)

    # Koordinat QR Code (Disesuaikan agar lebih pas di tengah kotak)
    qr_x = int(width * 0.485) # Geser kiri-kanan
    qr_y = int(height * 0.33) # Geser atas-bawah

    img.paste(qr_img, (qr_x, qr_y)) 

    # 4. CETAK TEKS (DENGAN UKURAN FONT JAUH LEBIH BESAR)
    draw = ImageDraw.Draw(img)
    
    try:
        font_path = "app/static/fonts/Roboto-Bold.ttf"
        # Skala font dinaikkan drastis!
        font_name = ImageFont.truetype(font_path, int(height * 0.15)) # Untuk Nama
        font_seat = ImageFont.truetype(font_path, int(height * 0.15)) # Untuk Seat
        font_order = ImageFont.truetype(font_path, int(height * 0.12)) # Untuk Order Number
    except IOError:
        font_name = ImageFont.load_default()
        font_seat = ImageFont.load_default()
        font_order = ImageFont.load_default()

    # Penyesuaian Koordinat Teks
    name_x = int(width * 0.09)
    name_y = int(height * 0.48) # Turun sedikit
    
    seat_x = int(width * 0.31)
    seat_y = int(height * 0.48)
    
    order_x = int(width * 0.755)
    order_y = int(height * 0.54)

    # Cetak Teks
    draw.text((name_x, name_y), buyer_name.upper()[:15], fill="#ffffff", font=font_name)
    draw.text((seat_x, seat_y), seat.upper(), fill="#ffffff", font=font_seat)
    draw.text((order_x, order_y), ticket_code, fill="#000000", font=font_order)
    
    # Simpan gambar
    img.save(output_path, "JPEG", quality=100) # Quality maksimal
    
    file_name = f"public/{ticket_code}.jpg"
    try:
        with open(output_path, "rb") as f:
            supabase.storage.from_("tickets").upload(
                file_name, f, {"content-type": "image/jpeg", "upsert": "true"}
            )
        public_url = supabase.storage.from_("tickets").get_public_url(file_name)
        
        # PERUBAHAN PENTING: Kembalikan file path juga agar bisa dilampirkan ke email!
        # JANGAN di-remove dulu di sini.
        return {
            "public_url": public_url,
            "local_path": output_path
        }
        
    except Exception as e:
        print(f"Gagal upload tiket: {e}")
        return None