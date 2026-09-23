import sys, os, requests, json
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from verify_phase10_live import get_auth_token, create_image

t = get_auth_token()
b = create_image([
    "INCOME TAX DEPARTMENT",
    "GOVT. OF INDIA",
    "Permanent Account Number Card",
    "ABCPE1234F",
    "Name: VIGHNESH POTE",
    "Father's Name: ANIL POTE",
    "Date of Birth: 12/04/1995"
])
r = requests.post(
    "http://127.0.0.1:8000/api/mode/offline",
    files={"file": ("clean_pan.png", b, "image/png")},
    data={"doc_type": "pan"},
    headers={"Authorization": f"Bearer {t}"}
)
print("=== CASE A ===")
print(json.dumps(r.json(), indent=2))

salary_bytes = create_image([
    "TECH ENTERPRISES PVT LTD",
    "SALARY SLIP FOR AUGUST 2026",
    "Employee Name: Rohan Sharma",
    "Gross Salary: 80,000",
    "Total Deductions: 10,000",
    "Net Pay: 95,000",
])
r_c = requests.post(
    "http://127.0.0.1:8000/api/mode/offline",
    files={"file": ("salary.png", salary_bytes, "image/png")},
    data={"doc_type": "salary_slip"},
    headers={"Authorization": f"Bearer {t}"}
)
print("=== CASE C ===")
print(json.dumps(r_c.json(), indent=2))
