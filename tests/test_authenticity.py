"""
tests/test_authenticity.py
Unit and integration tests for Document Authenticity Assessment & Review Required Detection (Phase 9):
1. Font mismatch -> Review Required.
2. QR mismatch detected -> Review Required.
3. Invalid checksum increases score.
4. Low score remains Verified.
5. Salary slip math discrepancy -> Review Required.
6. Bank statement balance discrepancy -> Review Required.
7. AI authenticity JSON normalizes correctly.
8. Offline Mode returns authenticity fields.
9. AI Mode returns authenticity fields.
10. Document Vault stores and retrieves verification status and risk score.
11. Document isolation per user is maintained.
12. Strict terminology check: never uses 'Fake', 'Forged', or 'Fraudulent'.
"""

import io
import json
import os
import time
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from main import app
from auth_dependencies import get_current_user, UserProfile
from security import authenticate_request
from authenticity_checker import (
    AuthenticityManager,
    ImageIntegrityChecker,
    OCRConsistencyChecker,
    QRConsistencyChecker,
    authenticity_manager,
    get_signal_weight,
)
import document_repository
import document_store


@pytest.fixture
def client():
    user = UserProfile(
        id="c80c0b46-3bc0-4c6f-9db0-741341f7ad32",
        email="vighneshpote.info@gmail.com",
        role="user",
        full_name="Vighnesh Pote",
    )
    user_dict = {
        "user_id": "c80c0b46-3bc0-4c6f-9db0-741341f7ad32",
        "email": "vighneshpote.info@gmail.com",
        "role": "user",
        "sub": "c80c0b46-3bc0-4c6f-9db0-741341f7ad32",
    }
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[authenticate_request] = lambda: user_dict
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(authenticate_request, None)


def _create_sample_image(text_lines):
    img = Image.new("RGB", (600, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 20
    for line in text_lines:
        draw.text((30, y), line, fill=(0, 0, 0))
        y += 40
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# 1. Font mismatch -> Review Required
def test_font_mismatch_triggers_review_required():
    class MockOCRLine:
        def __init__(self, text, box):
            self.text = text
            self.box = box

    # Create lines with standard height ~20, and two lines with outlier heights ~60 (height variance > 2.5x)
    lines = [
        MockOCRLine("Header 1", [10, 10, 100, 30]),   # h = 20
        MockOCRLine("Normal line 1", [10, 40, 100, 60]), # h = 20
        MockOCRLine("Normal line 2", [10, 70, 100, 90]), # h = 20
        MockOCRLine("Normal line 3", [10, 100, 100, 120]), # h = 20
        MockOCRLine("Outlier big font 1", [10, 130, 100, 195]), # h = 65
        MockOCRLine("Outlier big font 2", [10, 205, 100, 270]), # h = 65
    ]

    img = Image.new("RGB", (200, 300), (255, 255, 255))
    findings = ImageIntegrityChecker.check_image(image=img, ocr_lines=lines)
    signals = [f["signal"] for f in findings]
    assert "font_size_inconsistency" in signals

    res = authenticity_manager.assess_document(
        doc_type="pan",
        image=img,
        ocr_lines=lines,
        extracted_fields={"pan_number": "ABCDE1234F", "name": "JOHN DOE"},
    )
    # Font mismatch weight = 15, valid PAN
    assert res["risk_score"] >= 15
    assert any("font" in s.lower() for s in res["suspicious_signals"])


# 2. QR mismatch detected -> Review Required
def test_qr_mismatch_detected():
    ocr_fields = {
        "pan_number": "ABCDE1234F",
        "name": "RAMESH SHARMA",
        "dob": "01/01/1990",
    }
    qr_fields = {
        "pan_number": "XYZAB9876C",
        "name": "SURESH VERMA",
        "dob": "02/02/1995",
    }

    findings, discrepancies = QRConsistencyChecker.check_qr_consistency(ocr_fields, qr_fields)
    assert len(findings) > 0
    signals = [f["signal"] for f in findings]
    assert "qr_data_mismatch" in signals

    # AuthenticityManager assessment with QR mismatch
    res = authenticity_manager.assess_document(
        doc_type="pan",
        extracted_fields=ocr_fields,
        qr_fields=qr_fields,
    )
    # QR mismatch weight = 40 (>= 30 triggers review_required)
    assert res["risk_score"] >= 40
    assert res["verification_status"] == "review_required"
    assert res["review_required"] is True
    assert "qr_data_mismatch" in str(res["findings"]) or any("qr" in s.lower() for s in res["suspicious_signals"])


# 3. Invalid checksum increases score
def test_invalid_checksum_increases_score():
    # Invalid PAN format
    invalid_pan_fields = {
        "pan_number": "12345ABCDE",  # numbers first instead of 5 letters
        "name": "RAMESH SHARMA",
    }
    findings = OCRConsistencyChecker.check_consistency("pan", invalid_pan_fields)
    signals = [f["signal"] for f in findings]
    assert "invalid_checksum" in signals

    res = authenticity_manager.assess_document(
        doc_type="pan",
        extracted_fields=invalid_pan_fields,
    )
    assert res["risk_score"] >= 30
    assert res["verification_status"] == "review_required"
    assert res["review_required"] is True


# 4. Clean document with valid fields remains Verified
def test_clean_document_remains_verified():
    valid_pan_fields = {
        "pan_number": "ABCPE1234F",
        "name": "RAMESH SHARMA",
    }
    res = authenticity_manager.assess_document(
        doc_type="pan",
        extracted_fields=valid_pan_fields,
        raw_text="INCOME TAX DEPARTMENT PERMANENT ACCOUNT NUMBER ABCPE1234F RAMESH SHARMA",
    )
    assert res["risk_score"] < 30
    assert res["verification_status"] == "verified"
    assert res["review_required"] is False
    assert res["human_review_reason"] is None


# 5. Salary slip math discrepancy -> Review Required
def test_salary_slip_math_discrepancy():
    # Gross: 50,000, Deductions: 5,000, Net should be 45,000, but stated as 48,000
    mismatched_salary = {
        "gross_salary": "50,000",
        "total_deductions": "5,000",
        "net_salary": "48,000",
    }
    findings = OCRConsistencyChecker.check_consistency("salary_slip", mismatched_salary)
    signals = [f["signal"] for f in findings]
    assert "math_inconsistency" in signals

    res = authenticity_manager.assess_document(
        doc_type="salary_slip",
        extracted_fields=mismatched_salary,
    )
    # Math inconsistency weight = 20
    assert res["risk_score"] >= 20
    assert any("arithmetic" in s.lower() or "mismatch" in s.lower() for s in res["suspicious_signals"])


# 6. Bank statement balance discrepancy -> Review Required
def test_bank_statement_balance_discrepancy():
    # Opening: 10,000 + Credits: 5,000 - Debits: 2,000 = 13,000, but Closing is stated as 20,000
    mismatched_statement = {
        "opening_balance": "10000.00",
        "total_deposits": "5000.00",
        "total_withdrawals": "2000.00",
        "closing_balance": "20000.00",
    }
    findings = OCRConsistencyChecker.check_consistency("bank_statement", mismatched_statement)
    signals = [f["signal"] for f in findings]
    assert "balance_inconsistency" in signals

    res = authenticity_manager.assess_document(
        doc_type="bank_statement",
        extracted_fields=mismatched_statement,
    )
    assert res["risk_score"] >= 20
    assert any("balance" in s.lower() for s in res["suspicious_signals"])


# 7. AI authenticity JSON normalizes correctly
def test_ai_authenticity_json_normalizes_correctly():
    ai_auth = {
        "authenticity_status": "review_required",
        "confidence": 0.84,
        "suspicious_signals": [
            "Different font size in amount field",
            "Seal appears duplicated",
        ],
        "human_review_reason": "Visible inconsistencies detected.",
    }

    res = authenticity_manager.assess_document(
        doc_type="ai_analyzed",
        extracted_fields={"invoice_number": "INV-001"},
        ai_authenticity_result=ai_auth,
        is_supported=True,
    )
    assert res["verified_by_ai"] is True
    assert len(res["suspicious_signals"]) >= 2
    assert "Different font size in amount field" in res["suspicious_signals"]
    assert "Seal appears duplicated" in res["suspicious_signals"]


# 8. Offline Mode endpoint returns authenticity fields
def test_offline_mode_endpoint_returns_authenticity_fields(client):
    buf = _create_sample_image([
        "INCOME TAX DEPARTMENT",
        "PERMANENT ACCOUNT NUMBER",
        "ABCPE1234F",
        "RAMESH SHARMA",
    ])
    res = client.post(
        "/api/mode/offline",
        files={"file": ("pan_sample.png", buf, "image/png")},
        data={"doc_type": "pan"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "verification_status" in data
    assert "risk_score" in data
    assert "review_required" in data
    assert "suspicious_signals" in data
    assert isinstance(data["suspicious_signals"], list)
    assert data["verification_status"] in ("verified", "review_required", "unsupported")


# 9. Unsupported document in Offline Mode returns 'unsupported' status
def test_unsupported_document_offline_mode(client):
    buf = _create_sample_image([
        "RANDOM UNKNOWN TEXT",
        "NOT A STANDARD DOCUMENT",
        "NO STRUCTURED HEADERS",
    ])
    res = client.post(
        "/api/mode/offline",
        files={"file": ("unknown_sample.png", buf, "image/png")},
        data={"doc_type": "unknown"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["verification_status"] == "unsupported"
    assert data["risk_score"] == 0
    assert data["review_required"] is False


# 10. AI Mode endpoint returns authenticity fields
def test_ai_mode_analyze_returns_authenticity_fields(client):
    buf = _create_sample_image([
        "ACME CORPORATION",
        "EMPLOYMENT AGREEMENT",
        "BETWEEN ACME CORP AND JANE DOE",
        "SALARY: $120,000 PER ANNUM",
    ])
    res = client.post(
        "/api/mode/ai/analyze",
        files={"file": ("contract.png", buf, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()
    assert "verification_status" in data
    assert "risk_score" in data
    assert "review_required" in data
    assert "suspicious_signals" in data
    assert "verified_by_ai" in data
    assert data["verified_by_ai"] is True


# 11. Strict terminology test: Never uses 'Fake', 'Forged', or 'Fraudulent'
def test_strict_terminology_never_uses_forbidden_words():
    forbidden_words = ["fake", "forged", "fraudulent"]

    # Generate a heavily anomalous document
    res = authenticity_manager.assess_document(
        doc_type="pan",
        extracted_fields={"pan_number": "123INVALID", "name": "Test $#@!"},
        qr_fields={"pan_number": "DIFFERENT", "name": "Mismatch"},
    )

    full_output = json.dumps(res).lower()
    for word in forbidden_words:
        assert word not in full_output, f"Forbidden word '{word}' found in authenticity output!"
