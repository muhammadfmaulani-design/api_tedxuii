# app/services/ticket_gen.py
import qrcode
from PIL import Image, ImageDraw, ImageFont
import os
from app.core.supabase import supabase

def generate_qr_ticket(ticket_code: str, buyer_name: str):
    # 1. Tentukan path template desain kamu
    template_path = "app/static/templates/desain_tiket.png" 
    output_path = f"/tmp/temp_{ticket_code}.jpg" # Sudah benar pakai /tmp/ untuk Vercel
    
    if not os.path.exists(template_path):
        print(f"Error: Template tidak ditemukan di {template_path}")
        return None

    # 2. Buka Desain Tiket & Konversi ke RGB (Syarat wajib sebelum save ke JPG)
    img = Image.open(template_path).convert('RGB')
    width, height = img.size

    # 3. Generate QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=2) # Border dikecilkan agar lebih elegan
    qr.add_data(ticket_code)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # 4. MATEMATIKA POSISI: Hitung Ukuran & Titik Koordinat Dinamis
    # Kita asumsikan kotak krem di kiri lebarnya sama dengan tinggi tiket (persegi)
    qr_size = int(height * 0.55) # Ukuran QR adalah 55% dari tinggi tiket
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)

    # Pusatkan posisi X dan Y di area kotak sebelah kiri
    pos_x = int((height - qr_size) / 2)
    pos_y = int((height - qr_size) / 2) - int(height * 0.05) # Naikkan sedikit untuk ruang teks di bawahnya

    # Tempel QR Code ke kanvas tiket
    img.paste(qr_img, (pos_x, pos_y)) 

    # 5. CETAK NAMA PEMBELI & KODE TIKET
    draw = ImageDraw.Draw(img)
    
    # Setup Font (Gunakan try-except agar Vercel tidak crash jika font lupa diupload)
    try:
        # Pastikan Anda punya file font ini di folder static
        font_path = "app/static/fonts/Roboto-Bold.ttf"
        font_name = ImageFont.truetype(font_path, int(height * 0.035))
        font_code = ImageFont.truetype(font_path, int(height * 0.025))
    except IOError:
        # Jika font tidak ditemukan, pakai font default bawaan sistem
        font_name = ImageFont.load_default()
        font_code = ImageFont.load_default()

    # Tentukan posisi teks (sejajar dengan sisi kiri QR code, letaknya di bawah QR)
    text_y_start = pos_y + qr_size + int(height * 0.03) # Jarak antara QR dan teks
    
    # Tulis Nama dan Kode dengan warna gelap (karena backgroundnya krem)
    draw.text((pos_x, text_y_start), f"NAMA : {buyer_name.upper()[:20]}", fill="#1f2937", font=font_name)
    draw.text((pos_x, text_y_start + int(height * 0.04)), f"KODE : {ticket_code}", fill="#4b5563", font=font_code)
    
    # 6. Simpan gambar sementara di Vercel
    # Gunakan quality=95 agar gambar tajam dan teks tidak buram
    img.save(output_path, "JPEG", quality=95)
    
    # 7. Upload ke Supabase Storage
    file_name = f"public/{ticket_code}.jpg"
    try:
        with open(output_path, "rb") as f:
            # Tambahkan upsert=true agar tidak error jika nama file sudah ada
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