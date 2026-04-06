# app/services/ticket_gen.py
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
from app.core.supabase import supabase

def generate_qr_ticket(ticket_code: str, buyer_name: str, seat: str = "TBA", ticket_type: str = "FULL"):
    # 1. Tentukan path template berdasarkan tipe tiket
    if ticket_type.upper() == "FULL":
        template_path = "app/static/templates/TICKET_FULL.png"
    else:
        template_path = "app/static/templates/TICKET_ONE.png"
        
    output_path = f"/tmp/temp_{ticket_code}.jpg"
    
    if not os.path.exists(template_path):
        print(f"Error: Template tidak ditemukan di {template_path}")
        return None

    # 2. Buka Desain Tiket & Konversi ke RGB
    img = Image.open(template_path).convert('RGB')
    width, height = img.size

    # 3. Generate QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=1) # Border ditipiskan agar pas di dalam garis putus-putus
    qr.add_data(ticket_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # 4. MATEMATIKA POSISI: Berdasarkan Persentase Desain Baru
    # Mengambil ~42% dari tinggi tiket agar pas masuk ke dalam kotak putus-putus
    qr_size = int(height * 0.42)
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)

    # Koordinat QR Code (Di area tengah-kanan)
    qr_x = int(width * 0.505) # Berada di sekitar 50.5% dari kiri
    qr_y = int(height * 0.38) # Berada di sekitar 38% dari atas

    # Tempel QR Code ke kanvas tiket
    img.paste(qr_img, (qr_x, qr_y)) 

    # 5. CETAK TEKS (NAMA, SEAT, ORDER NUMBER)
    draw = ImageDraw.Draw(img)
    
    # Setup Font Dinamis
    try:
        font_path = "app/static/fonts/Roboto-Bold.ttf"
        font_name = ImageFont.truetype(font_path, int(height * 0.08)) # Font besar untuk Nama/Order
        font_seat = ImageFont.truetype(font_path, int(height * 0.08)) # Font untuk Seat
    except IOError:
        font_name = ImageFont.load_default()
        font_seat = ImageFont.load_default()

    # Koordinat X dan Y Teks (Berdasarkan estimasi visual dari desain baru)
    name_x = int(width * 0.09)
    name_y = int(height * 0.46)
    
    seat_x = int(width * 0.31)
    seat_y = int(height * 0.46)
    
    order_x = int(width * 0.755)
    order_y = int(height * 0.54)

    # Tulis Teks ke Gambar
    # Nama dan Seat di area hitam (Gunakan teks Putih)
    draw.text((name_x, name_y), buyer_name.upper()[:15], fill="#ffffff", font=font_name)
    draw.text((seat_x, seat_y), seat.upper(), fill="#ffffff", font=font_seat)
    
    # Order Number di area sobekan putih (Gunakan teks Hitam)
    draw.text((order_x, order_y), ticket_code, fill="#000000", font=font_name)
    
    # 6. Simpan gambar sementara di Vercel
    img.save(output_path, "JPEG", quality=95)
    
    # 7. Upload ke Supabase Storage
    file_name = f"public/{ticket_code}.jpg"
    try:
        with open(output_path, "rb") as f:
            supabase.storage.from_("tickets").upload(
                file_name, 
                f, 
                {"content-type": "image/jpeg", "upsert": "true"}
            )
        
        # 8. Ambil Public URL
        public_url = supabase.storage.from_("tickets").get_public_url(file_name)
        
        # Bersihkan sampah file di Vercel
        if os.path.exists(output_path):
            os.remove(output_path)
            
        return public_url
        
    except Exception as e:
        print(f"Gagal upload tiket: {e}")
        return None