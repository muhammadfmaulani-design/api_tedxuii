# app/services/ticket_gen.py
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
from app.core.supabase import supabase

# FUNGSI CUSTOM: Menggambar teks dengan letter spacing karena PIL tidak memiliki fitur bawaan ini
def draw_text_with_spacing(draw, text, position, font, fill, spacing_px):
    x, y = position
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        # Dapatkan lebar karakter saat ini, lalu tambahkan nilai spacing (yang bernilai minus)
        char_width = font.getlength(char)
        x += char_width + spacing_px

def generate_qr_ticket(ticket_code: str, buyer_name: str, seat: str = "TBA", ticket_type: str = "FULL"):
    # 1. Tentukan Template
    if "FULL" in ticket_type.upper():
        template_path = "app/static/templates/template_full.jpg"
    else:
        template_path = "app/static/templates/template_one.jpg"
        
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

    # 3. CETAK TEKS SESUAI SPESIFIKASI FIGMA
    draw = ImageDraw.Draw(img)
    
    try:
        # PASTIKAN: Kamu harus mendownload font Satoshi-Bold.ttf dan menaruhnya di folder ini
        font_path = "app/static/fonts/Satoshi-Bold.ttf"
        
        # Terapkan ukuran absolut dari Figma (Size: 96)
        font_name = ImageFont.truetype(font_path, 96) 
        
        # Asumsi untuk Seat dan Order Number. Sesuaikan lagi dengan inspektor Figma kamu jika berbeda
        font_seat = ImageFont.truetype(font_path, 72) 
        font_order = ImageFont.truetype(font_path, 54) 
    except IOError:
        print("Peringatan: Font Satoshi tidak ditemukan, pastikan path benar!")
        font_name = ImageFont.load_default()
        font_seat = ImageFont.load_default()
        font_order = ImageFont.load_default()

    # Hitung Letter Spacing: -6% dari font size 96 = -5.76 pixel
    spacing_name_px = 96 * (-0.06)

    # KOORDINAT (Gunakan koordinat X dan Y persis dari menu Inspect/Code di Figma jika mau akurasi 100%)
    name_x = int(width * 0.09)
    name_y = int(height * 0.48)
    
    seat_x = int(width * 0.31)
    seat_y = int(height * 0.48)
    
    order_x = int(width * 0.755)
    order_y = int(height * 0.54)

    # 4. CETAK NAMA DENGAN FUNGSI SPACING KHUSUS
    draw_text_with_spacing(
        draw=draw, 
        text=buyer_name.upper()[:15], 
        position=(name_x, name_y), 
        font=font_name, 
        fill="#FFFFFF", 
        spacing_px=spacing_name_px
    )
    
    # Cetak teks lainnya (Seat & Order)
    draw.text((seat_x, seat_y), seat.upper(), fill="#FFFFFF", font=font_seat)
    draw.text((order_x, order_y), ticket_code, fill="#000000", font=font_order)
    
    # 5. Simpan & Upload
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