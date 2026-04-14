import qrcode
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont

def wrap_and_truncate_text(text: str, font, max_width: int, max_lines: int = 2) -> str:
    """
    Memecah teks menjadi beberapa baris. 
    Jika jumlah baris melebihi max_lines, teks akan dipotong dan ditambahkan '...' di akhirnya.
    """
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        if font.getlength(test_line) <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
                
    if current_line:
        lines.append(" ".join(current_line))
        
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last_line = lines[-1]
        while True:
            test_last_line = last_line + "_"
            if font.getlength(test_last_line) <= max_width or len(last_line.split()) <= 1:
                lines[-1] = test_last_line
                break
            else:
                last_words = last_line.split()
                last_line = " ".join(last_words[:-1])
                
    return "\n".join(lines)


def generate_ticket(ticket_code: str, buyer_name: str, ticket_type: str = "FULL", seat_number: str = "TBD") -> dict:
    """
    Menghasilkan tiket fisik (JPG) TEDxUII dengan resolusi tinggi.
    File disimpan secara aman di temporary directory agar kompatibel dengan Vercel Serverless.
    """
    
    # ==========================================
    # 1. RESOLVE PATH TEMPLATE & FONT
    # ==========================================
    t_type = ticket_type.upper()
    if "MORNING" in t_type:
        file_name = "template_morning.png"
    elif "AFTERNOON" in t_type:
        file_name = "template_afternoon.png"
    else:
        file_name = "template_full.png"

    current_file_path = os.path.dirname(os.path.abspath(__file__)) 
    app_dir = os.path.dirname(current_file_path) 
    
    template_path = os.path.join(app_dir, "static", "templates", file_name)
    font_path = os.path.join(app_dir, "static", "fonts", "Satoshi-Variable.ttf")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"[TicketGen] Template hilang di: {template_path}")

    # ==========================================
    # 2. PROSES GAMBAR & RENDER TEKS
    # ==========================================
    img = Image.open(template_path).convert('RGB')
    draw = ImageDraw.Draw(img)

    try:
        font_obj = ImageFont.truetype(font_path, 72) 
    except Exception as e:
        print(f"⚠️ [TicketGen] Font gagal diload: {e}")
        font_obj = ImageFont.load_default()

    color_white = (255, 255, 255)
    MAX_NAME_WIDTH = 680
    
    wrapped_name = wrap_and_truncate_text(buyer_name.upper(), font_obj, MAX_NAME_WIDTH, max_lines=2)
    
    # Cetak Nama
    draw.multiline_text((322, 562), wrapped_name, font=font_obj, fill=color_white, spacing=15)
    
    # Cetak Nomor Kursi
    draw.text((1066, 522), seat_number, font=font_obj, fill=color_white)

    # ==========================================
    # 3. GENERATE & RENDER QR CODE
    # ==========================================
    qr = qrcode.QRCode(
        version=1, 
        error_correction=qrcode.constants.ERROR_CORRECT_H, 
        box_size=10, 
        border=1 
    )
    qr.add_data(ticket_code)
    qr.make(fit=True)
    
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    qr_img = qr_img.resize((558, 558), Image.Resampling.LANCZOS)
    
    img.paste(qr_img, (1738, 445)) 

    # ==========================================
    # 4. SIMPAN KE TEMPORARY DIRECTORY
    # ==========================================
    temp_dir = tempfile.gettempdir()
    output_name = f"ticket_{ticket_code}.jpg"
    output_path = os.path.join(temp_dir, output_name)
    
    img.save(output_path, "JPEG", quality=90, optimize=True)
    
    return {
        "local_path": output_path, 
        "seat": seat_number
    }