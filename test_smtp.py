# test_smtp.py
import os
import smtplib
from dotenv import load_dotenv

# Load .env file
load_dotenv()

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

print("Testing SMTP with:")
print("Server:", SMTP_SERVER)
print("Port:", SMTP_PORT)
print("Email:", SMTP_EMAIL)

try:
    if SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=10)
    else:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.starttls()

    server.login(SMTP_EMAIL, SMTP_PASSWORD)
    print("✅ SMTP CONNECTED SUCCESSFULLY")
    server.quit()

except Exception as e:
    print("❌ SMTP FAILED:", e)
