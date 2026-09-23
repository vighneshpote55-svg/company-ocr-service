import sys, os, requests, json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from verify_phase10_live import get_auth_token, create_overlapping_image

t = get_auth_token()
dup_pan_bytes = create_overlapping_image([
    ("INCOME TAX DEPARTMENT", (40, 20)),
    ("GOVT. OF INDIA", (40, 50)),
    ("ABCPE1234F", (40, 80)),
    ("Name", (40, 110)),
    ("VIGHNESH POTE", (40, 135)),
    ("Name", (40, 160)),
    ("VIGHNESH POTE", (40, 185)),
    ("Father's Name: ANIL POTE", (40, 215)),
])
r = requests.post(
    "http://127.0.0.1:8000/api/mode/offline",
    files={"file": ("dup_pan.png", dup_pan_bytes, "image/png")},
    data={"doc_type": "pan"},
    headers={"Authorization": f"Bearer {t}"}
)
res = r.json()
print("OCR TEXT:")
print(res.get("extracted_text"))
print("\nSIGNALS:")
print(res.get("suspicious_signals"))
print("\nSTATUS:", res.get("verification_status"))
print("RISK SCORE:", res.get("risk_score"))
