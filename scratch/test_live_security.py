import io
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image, ImageDraw
import pypdf
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_live_security():
    print("Testing security endpoints with TestClient")
    
    # 1. Path traversal
    res = client.post("/api/mode/offline", files={"file": ("../../secret.pdf", b"abc", "application/pdf")})
    print(f"Path traversal 1: status={res.status_code}, body={res.json()}")
    assert res.status_code == 400

    res = client.post("/api/upload", files={"file": ("..\\..\\windows.txt", b"abc", "text/plain")})
    print(f"Path traversal 2: status={res.status_code}, body={res.json()}")
    assert res.status_code == 400

    # 2. Unsupported file extension
    res = client.post("/api/mode/offline", files={"file": ("malware.exe", b"MZtest", "application/x-msdownload")})
    print(f"Unsupported extension: status={res.status_code}, body={res.json()}")
    assert res.status_code == 400
    assert "unsupported file type" in res.json().get("error", "").lower()

    # 3. Masqueraded file (fake PNG with executable or text contents)
    res = client.post("/api/mode/offline", files={"file": ("malware.png", b"MZexecutable_code_here", "image/png")})
    print(f"Masqueraded file: status={res.status_code}, body={res.json()}")
    assert res.status_code == 400
    assert "unsupported file type" in res.json().get("error", "").lower()

    # 4. Corrupted PNG
    res = client.post("/api/mode/offline", files={"file": ("corrupt.png", b"\x89PNG\r\n\x1a\ncorrupted_data", "image/png")})
    print(f"Corrupted PNG: status={res.status_code}, body={res.json()}")
    assert res.status_code == 422
    assert "corrupted" in res.json().get("error", "").lower()

    # 5. Encrypted PDF
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret_password")
    buf = io.BytesIO()
    writer.write(buf)
    encrypted_pdf_bytes = buf.getvalue()
    res = client.post("/api/mode/offline", files={"file": ("locked.pdf", encrypted_pdf_bytes, "application/pdf")})
    print(f"Encrypted PDF: status={res.status_code}, body={res.json()}")
    assert res.status_code == 422
    assert "encrypted" in res.json().get("error", "").lower()

    # 6. Valid upload with personal name in original filename
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "INCOME TAX DEPARTMENT", fill="black")
    draw.text((20, 50), "PERMANENT ACCOUNT NUMBER", fill="black")
    draw.text((20, 80), "ABCDE1234F", fill="black")
    draw.text((20, 110), "NAME: TEST USER", fill="black")
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG")
    jpeg_bytes = img_buf.getvalue()

    res = client.post("/api/upload", files={"file": ("Vighnesh_PAN_Card.jpg", jpeg_bytes, "image/jpeg")})
    print(f"Valid upload with personal name: status={res.status_code}")
    assert res.status_code == 200
    data = res.json()
    print(f"Doc record: id={data.get('id')}, filename={data.get('filename')}, file_path={data.get('file_path')}")
    
    # Check that disk filename doesn't contain "Vighnesh"
    file_path = data.get("file_path")
    assert "Vighnesh" not in file_path
    assert file_path.endswith(".jpg")
    print("All live security checks passed successfully!")

if __name__ == "__main__":
    test_live_security()
