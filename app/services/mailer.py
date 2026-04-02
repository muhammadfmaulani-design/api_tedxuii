import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

def send_ticket_email(to_email: str, buyer_name: str, ticket_url: str):
    msg = MIMEMultipart()
    msg['From'] = settings.SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = "Your TEDxUII E-Ticket is Here!"

    body = f"""
    Hello {buyer_name},

    Thank you for your payment! Your ticket for TEDxUII is ready.
    You can download your ticket with the QR Code here:
    {ticket_url}

    Please show this ticket at the registration desk.
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