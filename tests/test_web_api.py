"""
tests/test_web_api.py
Unit and integration tests for the Document OCR Web Application REST APIs.
Tests:
- /api/supported-types
- /api/stats
- /api/upload (text-based PDF -> ocr_required=False, image -> ocr_required=True)
- /api/documents (listing, filtering, search)
- /api/documents/{id} (retrieval)
- /api/documents/{id}/file (file serving)
- /api/documents/{id}/preview (thumbnail serving)
- DELETE /api/documents/{id}
- Authentication regression: 401 on unauthenticated access to /api/upload and dashboard endpoints
- Query parameter authentication for browser media loading (?token=...)
"""

import io
import json
import os
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
import document_store
from security import create_access_token


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "dual")
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-at-least-32-chars-long-123456")
    monkeypatch.setenv("API_KEY", "test-static-api-key-2026")
    return TestClient(app)


@pytest.fixture
def auth_headers():
    token = create_access_token(subject="test-client")
    return {"Authorization": f"Bearer {token}"}


def test_public_endpoints_remain_open(client):
    """Liveness probe, engine metadata, and supported document catalog remain public."""
    assert client.get("/health").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/engine-info").status_code == 200
    assert client.get("/api/engine-info").status_code == 200

    resp = client.get("/api/supported-types")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 14
    ids = [item["id"] for item in data]
    assert "auto" in ids
    assert "pan" in ids
    assert "aadhaar" in ids
    assert "bank_statement" in ids


def test_upload_unauthenticated_rejected_401(client):
    """Unauthenticated requests to POST /api/upload must be rejected with HTTP 401."""
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    # 1. No auth headers at all
    res = client.post(
        "/api/upload",
        files={"file": ("test.png", buf, "image/png")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 401
    assert "Missing or invalid authentication credentials" in res.json().get("detail", "")

    # 2. Invalid bearer token
    buf.seek(0)
    res_bad = client.post(
        "/api/upload",
        files={"file": ("test.png", buf, "image/png")},
        data={"doc_type": "auto"},
        headers={"Authorization": "Bearer invalid-garbage-token"},
    )
    assert res_bad.status_code == 401


def test_dashboard_endpoints_unauthenticated_rejected_401(client):
    """Vault data and stats endpoints must be strictly protected against unauthenticated requests."""
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents/non-existent-doc-id").status_code == 401
    assert client.get("/api/documents/non-existent-doc-id/file").status_code == 401
    assert client.get("/api/documents/non-existent-doc-id/preview").status_code == 401
    assert client.delete("/api/documents/non-existent-doc-id").status_code == 401


def test_get_stats(client, auth_headers):
    response = client.get("/api/stats", headers=auth_headers)
    assert response.status_code == 200
    stats = response.json()
    assert "total" in stats
    assert "ocr_processed" in stats
    assert "ocr_not_required" in stats


def test_upload_image_document(client, auth_headers, tmp_path):
    # Create an image with readable text in memory
    img = Image.new("RGB", (400, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), "INCOME TAX DEPARTMENT", fill=(0, 0, 0))
    draw.text((20, 60), "PERMANENT ACCOUNT NUMBER", fill=(0, 0, 0))
    draw.text((20, 90), "ABCDE1234F", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    response = client.post(
        "/api/upload",
        files={"file": ("test_pan_card.png", buf, "image/png")},
        data={"doc_type": "auto"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc = response.json()
    assert doc["id"] is not None
    assert doc["filename"] == "test_pan_card.png"
    assert doc["ocr_required"] is True
    assert doc["text_source"] in ("rapid_ocr", "paddle_ocr")
    assert doc["file_type"] == ".png"
    doc_id = doc["id"]

    # Verify listing includes it
    list_res = client.get("/api/documents", headers=auth_headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert any(i["id"] == doc_id for i in items)

    # Verify fetching by ID
    get_res = client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == doc_id

    # Verify file endpoint via Header
    file_res = client.get(f"/api/documents/{doc_id}/file", headers=auth_headers)
    assert file_res.status_code == 200
    assert file_res.headers["content-type"] == "image/png"

    # Verify file endpoint via query param (?token=) for browser img/iframe tags
    token = create_access_token(subject="browser-user")
    file_query_res = client.get(f"/api/documents/{doc_id}/file?token={token}")
    assert file_query_res.status_code == 200
    assert file_query_res.headers["content-type"] == "image/png"

    # Verify preview endpoint via query param (?token=)
    preview_query_res = client.get(f"/api/documents/{doc_id}/preview?token={token}")
    assert preview_query_res.status_code == 200
    assert preview_query_res.headers["content-type"] == "image/png"

    # Verify deletion
    del_res = client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # After deletion, 404
    get_after = client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    assert get_after.status_code == 404


def test_upload_blank_image_rejected(client, auth_headers):
    # Blank/unreadable images must be rejected with HTTP 422 and not saved
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    response = client.post(
        "/api/upload",
        files={"file": ("blank_card.png", buf, "image/png")},
        data={"doc_type": "auto"},
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "no text or zero confidence" in response.json()["detail"]

    # Verify blank document was NOT persisted to repository
    list_res = client.get("/api/documents", headers=auth_headers)
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert not any(i.get("filename") == "blank_card.png" for i in items)


def test_upload_real_pdf_demo(client, auth_headers):
    demo_pdf_path = "/home/vighnesh/Downloads/Demo_PAN_Card.pdf"
    if not os.path.exists(demo_pdf_path):
        pytest.skip("Demo_PAN_Card.pdf not available in Downloads")

    with open(demo_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    response = client.post(
        "/api/upload",
        files={"file": ("Demo_PAN_Card.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"doc_type": "auto"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc = response.json()
    assert doc["id"] is not None
    # Embedded text layer was detected, so OCR was not required!
    assert doc["ocr_required"] is False
    assert doc["text_source"] in ("pdf_text_layer", "embedded_pdf_text")
    assert doc["doc_type"] == "pan"
    assert "ABCDE1234F" in str(doc.get("extracted_fields", {}))

    # Clean up
    client.delete(f"/api/documents/{doc['id']}", headers=auth_headers)


def test_upload_cross_check_ordering_with_masked_fields(client, auth_headers):
    """
    Regression test for cross-check execution order bug:
    Ensures that /api/upload runs perform_cross_check against raw_fields BEFORE
    sanitize_extracted_fields. If it ran against sanitized fields, cross-checking
    an applicant's raw name against 'employee_name_masked' (e.g. 'RAHUL S*****')
    would fail, but running against raw fields must succeed with matched: True.
    """
    # Create a synthetic salary slip image with clear unmasked employee name
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), "PAYSLIP / SALARY SLIP", fill=(0, 0, 0))
    draw.text((20, 70), "Employer: ACME GLOBAL SOLUTIONS PVT LTD", fill=(0, 0, 0))
    draw.text((20, 110), "Employee Name: RAHUL SHARMA", fill=(0, 0, 0))
    draw.text((20, 150), "Pay Period: July 2026", fill=(0, 0, 0))
    draw.text((20, 190), "Net Pay: Rs. 85,000", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    # Submit with expected_data containing the raw unmasked name
    expected_payload = json.dumps({"name": "RAHUL SHARMA"})
    response = client.post(
        "/api/upload",
        files={"file": ("test_salary_slip.png", buf, "image/png")},
        data={"doc_type": "salary_slip", "expected_data": expected_payload},
        headers=auth_headers,
    )
    assert response.status_code == 200
    doc = response.json()
    doc_id = doc["id"]

    try:
        # Cross-check MUST succeed against raw unmasked name
        cross_check = doc.get("cross_check")
        assert cross_check is not None, "cross_check result missing from response"
        assert "name" in cross_check, f"cross_check missing 'name' field: {cross_check}"
        assert cross_check["name"]["matched"] is True, f"Cross-check failed: {cross_check['name']}"
        assert cross_check["name"]["score"] >= 0.95

        # PII minimisation: the response extracted_fields must ONLY contain masked fields
        ext_fields = doc.get("extracted_fields", {})
        assert "employee_name_masked" in ext_fields
        assert ext_fields["employee_name_masked"] == "RAHUL S*****"
        assert "employee_name" not in ext_fields
        assert "raw_employee_name" not in ext_fields
        assert not any(k.startswith("raw_") for k in ext_fields.keys())
        assert "RAHUL SHARMA" not in str(ext_fields)
    finally:
        # Clean up
        client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
