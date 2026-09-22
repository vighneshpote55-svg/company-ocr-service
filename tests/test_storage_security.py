"""
tests/test_storage_security.py
Comprehensive test suite verifying Phase 1 Secure Local Storage hardening:
- Task 1: Randomized UUID filenames on disk, original filename retained in metadata
- Task 2: Path traversal rejection (../../secret.pdf, ..\\..\\windows.txt, /etc/passwd)
- Task 3: File type & MIME validation (reject malware.exe, fake images)
- Task 4: File size protection (Images >20MB, PDFs >50MB)
- Task 5: Corrupted file detection (corrupted PNG/JPEG, damaged PDF)
- Task 6: Encrypted PDF detection (password protected PDF)
- Task 7: Secure metadata fields in documents.json (document_id, original_filename, stored_filename, uploaded_at)
"""

import io
import os
import re
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from pypdf import PdfWriter

from main import app
import document_store


@pytest.fixture(autouse=True)
def setup_storage_env(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _make_valid_png():
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "INCOME TAX DEPARTMENT", fill=(0, 0, 0))
    draw.text((10, 50), "ABCDE1234F", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def _make_valid_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_task1_and_task7_randomized_stored_filename_and_secure_metadata(client):
    """
    Task 1: Generate UUID v4 for every uploaded file; never use original filename on disk.
    Task 7: Original filename saved in documents.json alongside stored_filename, document_id, uploaded_at.
    """
    png_bytes = _make_valid_png()
    original_name = "Vighnesh_PAN_Card.png"

    res = client.post(
        "/api/mode/offline",
        files={"file": (original_name, png_bytes, "image/png")},
        data={"doc_type": "pan"},
    )
    assert res.status_code == 200
    doc = res.json()
    doc_id = doc["id"]

    # Check on disk: file must exist in uploads/original/{doc_id}.png, NOT with original_name
    stored_name = doc.get("stored_filename")
    assert stored_name is not None
    assert stored_name.startswith(doc_id)
    assert original_name not in stored_name
    assert stored_name.endswith((".png", ".png.enc"))

    file_path = doc.get("file_path")
    assert os.path.exists(file_path)
    assert os.path.basename(file_path) == stored_name
    assert "Vighnesh" not in os.path.basename(file_path)

    # Check documents.json metadata (Task 7)
    record = document_store.get_document(doc_id)
    assert record is not None
    assert record.get("document_id") == doc_id
    assert record.get("original_filename") == original_name
    assert record.get("filename") == original_name
    assert record.get("stored_filename") == stored_name
    assert record.get("uploaded_at") is not None

    # Cleanup
    client.delete(f"/api/documents/{doc_id}")


@pytest.mark.parametrize("dangerous_filename", [
    "../../secret.pdf",
    r"..\..\windows.txt",
    "/etc/passwd",
    "../../etc/shadow",
    r"subdir\..\file.png",
])
def test_task2_path_traversal_rejected(client, dangerous_filename):
    """
    Task 2: Reject dangerous filenames with path traversal attempts.
    """
    png_bytes = _make_valid_png()
    res = client.post(
        "/api/mode/offline",
        files={"file": (dangerous_filename, png_bytes, "image/png")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 400
    err_msg = res.json().get("detail") or res.json().get("error")
    assert "path traversal" in err_msg.lower() or "invalid filename" in err_msg.lower()


def test_task3_unsupported_file_extension_rejected(client):
    """
    Task 3: Reject unsupported extensions like .exe, .sh, .txt.
    """
    res = client.post(
        "/api/mode/offline",
        files={"file": ("malware.exe", b"MZexecutable_binary_content", "application/x-msdownload")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 400
    assert "unsupported file type" in (res.json().get("error") or res.json().get("detail")).lower()


def test_task3_masqueraded_fake_file_rejected_by_magic_bytes(client):
    """
    Task 3: Reject files with valid extension but invalid magic bytes (e.g. exe renamed to .png).
    """
    res = client.post(
        "/api/mode/offline",
        files={"file": ("malware.png", b"MZexecutable_binary_content_fake_png", "image/png")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 400
    assert "unsupported file type" in (res.json().get("error") or res.json().get("detail")).lower()


def test_task4_image_file_size_limit(client, monkeypatch):
    """
    Task 4: Enforce upload size limit on images (20MB).
    """
    # Temporarily lower limit to test without allocating 20MB in test
    monkeypatch.setattr("main.MAX_IMAGE_SIZE", 500)
    png_bytes = _make_valid_png()
    assert len(png_bytes) > 500

    res = client.post(
        "/api/mode/offline",
        files={"file": ("large_image.png", png_bytes, "image/png")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 413
    assert "exceeds the maximum upload size" in (res.json().get("error") or res.json().get("detail")).lower()


def test_task4_pdf_file_size_limit(client, monkeypatch):
    """
    Task 4: Enforce upload size limit on PDFs (50MB).
    """
    monkeypatch.setattr("main.MAX_PDF_SIZE", 200)
    pdf_bytes = _make_valid_pdf()
    assert len(pdf_bytes) > 200

    res = client.post(
        "/api/mode/offline",
        files={"file": ("large_document.pdf", pdf_bytes, "application/pdf")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 413
    assert "exceeds the maximum upload size" in (res.json().get("error") or res.json().get("detail")).lower()


def test_task5_corrupted_png_rejected(client):
    """
    Task 5: Detect and reject corrupted PNG images before OCR.
    """
    # Starts with PNG header but corrupted image body
    corrupted_bytes = b"\x89PNG\r\n\x1a\ncorrupted_random_garbage_data"
    res = client.post(
        "/api/mode/offline",
        files={"file": ("corrupted.png", corrupted_bytes, "image/png")},
        data={"doc_type": "auto"},
    )
    assert res.status_code in (400, 422)
    assert "corrupted" in (res.json().get("error") or res.json().get("detail")).lower()


def test_task5_corrupted_pdf_rejected(client):
    """
    Task 5: Detect and reject damaged PDF files before OCR.
    """
    # Starts with %PDF- header but damaged xref/structure
    corrupted_pdf = b"%PDF-1.4\nDamaged and truncated stream without xref or trailer\n%%EOF"
    res = client.post(
        "/api/mode/offline",
        files={"file": ("damaged.pdf", corrupted_pdf, "application/pdf")},
        data={"doc_type": "auto"},
    )
    assert res.status_code in (400, 422)
    assert "corrupted" in (res.json().get("error") or res.json().get("detail")).lower()


def test_task6_encrypted_pdf_rejected(client):
    """
    Task 6: Detect password-protected encrypted PDFs and reject without OCR.
    """
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("mypassword123")
    buf = io.BytesIO()
    writer.write(buf)
    encrypted_bytes = buf.getvalue()

    res = client.post(
        "/api/mode/offline",
        files={"file": ("encrypted_statement.pdf", encrypted_bytes, "application/pdf")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 422
    assert "encrypted" in (res.json().get("error") or res.json().get("detail")).lower()
