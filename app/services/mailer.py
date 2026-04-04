import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
from typing import List

def send_ticket_email(to_email: str, buyer_name: str, ticket_urls: List[str]):
    msg = MIMEMultipart()
    msg['From'] = settings.SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = "Your TEDxUII E-Tickets are Here!"

    # Gabungkan semua link tiket menjadi satu string
    links_text = "\n".join([f"- Tiket {i+1}: {url}" for i, url in enumerate(ticket_urls)])

    body = f"""
    Hello {buyer_name},

    Thank you for your payment! Your ticket(s) for TEDxUII are ready.
    You can download your E-Ticket with the QR Code(s) here:
    
{links_text}

    Please show the QR Code(s) at the registration desk.
    See you at the future!
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Mail Error: {e}")
        return False