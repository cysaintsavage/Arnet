import smtplib
from email.message import EmailMessage

from .config import env


def configured() -> bool:
    e = env()
    return bool(e.smtp_host and e.smtp_from)


def send(to: str, subject: str, body: str) -> None:
    e = env()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = e.smtp_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(e.smtp_host, e.smtp_port, timeout=20) as s:
        s.starttls()
        if e.smtp_user:
            s.login(e.smtp_user, e.smtp_password)
        s.send_message(msg)
