import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from app.core.config import settings
from typing import List

# Parameter sekarang menerima list of dictionary (yang berisi public_url & local_path)
def send_ticket_email(to_email: str, buyer_name: str, ticket_data_list: List[dict]):
    msg = MIMEMultipart()
    msg['From'] = settings.SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = "Your TEDxUII 2026 E-Tickets are Here!"

    body = f"""
    Hello {buyer_name},

    Thank you for your payment! Your ticket(s) for TEDxUII are ready.
    Please find your E-Ticket(s) attached to this email as images.

    Please show the attached QR Code(s) at the registration desk.
    See you at the future!
    """
    msg.attach(MIMEText(body, 'plain'))

    # PERBAIKAN: Sisipkan gambar lokal ke dalam email
    for data in ticket_data_list:
        local_path = data.get("local_path")
        if local_path and os.path.exists(local_path):
            with open(local_path, "rb") as f:
                img_data = f.read()
            # Attach gambar ke email
            image = MIMEImage(img_data, name=os.path.basename(local_path))
            msg.attach(image)

    try:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)
        server.quit()
        
        # SANGAT PENTING: Hapus sampah gambar di server Vercel SETELAH email terkirim
        for data in ticket_data_list:
            local_path = data.get("local_path")
            if local_path and os.path.exists(local_path):
                os.remove(local_path)
                
        return True
    except Exception as e:
        print(f"Mail Error: {e}")
        return False