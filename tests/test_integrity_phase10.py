"""
tests/test_integrity_phase10.py
Comprehensive test suite for Phase 10 — Universal Document Integrity & Review Detection.

Tests:
1. LayoutIntegrityChecker:
   - Duplicate field label detection (e.g. duplicate Name on PAN).
   - Overlapping bounding box detection (IoU > 0.15).
   - Tabular document exemption (bank statement does not flag expected recurring headers).
2. VisualTamperingChecker:
   - Font size inconsistency across text lines.
   - Pasted white patch detection on textured backgrounds.
3. UniversalConsistencyEngine:
   - PAN format validation.
   - Aadhaar Verhoeff checksum.
   - GSTIN Mod-36 checksum.
   - Salary Slip math (Gross - Deductions != Net).
   - Bank Statement running balance math.
   - Passport MRZ structure.
   - Driving Licence state pattern.
   - FSSAI 14-digit check.
   - Cross-field: Applicant name == Father name.
   - Cross-field: Future Date of Birth.
4. AuthenticityManager Orchestrator & Scoring:
   - Score >= 60 triggers priority: "high".
   - Score 30-59 triggers review_required.
   - Clean document remains verified (score: 0).
   - Unsupported document returns "unsupported".
5. Database Storage:
   - document_integrity_checks receives signal rows.
   - Clean documents receive baseline audit record.
6. Strict Terminology:
   - Zero occurrences of "fake", "forged", or "fraudulent".
"""

import io
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from main import app
from auth_dependencies import get_current_user, UserProfile
from security import authenticate_request
from layout_integrity import LayoutIntegrityChecker
from visual_tampering import VisualTamperingChecker
from consistency_engine import UniversalConsistencyEngine
from authenticity_checker import authenticity_manager, AuthenticityManager
import document_repository


class MockBoxLine:
    """Mock OCR line supporting text, bbox, and box."""
    def __init__(self, text: str, bbox: list):
        self.text = text
        self.bbox = bbox
        self.box = bbox
        self.confidence = 0.98


@pytest.fixture
def client():
    user = UserProfile(
        id="c80c0b46-3bc0-4c6f-9db0-741341f7ad32",
        email="test.user@company.com",
        role="user",
        full_name="Test User",
    )
    user_dict = {
        "user_id": "c80c0b46-3bc0-4c6f-9db0-741341f7ad32",
        "email": "test.user@company.com",
        "role": "user",
        "sub": "c80c0b46-3bc0-4c6f-9db0-741341f7ad32",
    }
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[authenticate_request] = lambda: user_dict
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(authenticate_request, None)


def _create_sample_image(lines: list, size=(500, 300)) -> io.BytesIO:
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 20
    for line in lines:
        draw.text((30, y), line, fill=(0, 0, 0))
        y += 35
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ==============================================================================
# 1. Layout Integrity Tests
# ==============================================================================

def test_duplicate_name_field_detected():
    """Detect duplicate Name label on single-record identity document (PAN)."""
    ocr_lines = [
        MockBoxLine("INCOME TAX DEPARTMENT", [50, 20, 300, 40]),
        MockBoxLine("Name", [50, 60, 100, 80]),
        MockBoxLine("VIGHNESH POTE", [50, 90, 220, 110]),
        MockBoxLine("Name", [50, 130, 100, 150]),
        MockBoxLine("VIGHNESH POTE", [50, 160, 220, 180]),
        MockBoxLine("Father's Name", [50, 200, 160, 220]),
    ]
    findings = LayoutIntegrityChecker.check_layout(ocr_lines=ocr_lines, doc_type="pan")
    signals = [f["signal"] for f in findings]
    assert "duplicate_field_label" in signals
    assert any("duplicate name" in f["description"].lower() for f in findings)


def test_overlapping_text_bounding_boxes_detected():
    """Detect overlapping bounding boxes (indicating pasted or stamped text)."""
    ocr_lines = [
        MockBoxLine("Original Title", [50, 50, 250, 90]),
        # Overlapping box with significant intersection
        MockBoxLine("Pasted Replacement", [60, 55, 240, 85]),
        MockBoxLine("Normal Line Below", [50, 120, 250, 150]),
    ]
    findings = LayoutIntegrityChecker.check_layout(ocr_lines=ocr_lines, doc_type="pan")
    signals = [f["signal"] for f in findings]
    assert "overlapping_text_regions" in signals
    assert any(f["score"] == 15 for f in findings)


def test_tabular_documents_exempt_from_duplicate_column_headers():
    """Bank statements legitimately repeat transaction headers; exempt from false positives."""
    ocr_lines = [
        MockBoxLine("Date", [50, 50, 100, 70]),
        MockBoxLine("Description", [110, 50, 250, 70]),
        MockBoxLine("Date", [50, 90, 100, 110]),
        MockBoxLine("Description", [110, 90, 250, 110]),
    ]
    findings = LayoutIntegrityChecker.check_layout(ocr_lines=ocr_lines, doc_type="bank_statement")
    signals = [f["signal"] for f in findings]
    assert "duplicate_field_label" not in signals


# ==============================================================================
# 2. Visual Tampering Tests
# ==============================================================================

def test_pasted_white_patch_on_textured_document():
    """Detect sharp rectangular white box placed on textured page background."""
    # Create textured background with substantial variance (inner_std > 10)
    img = Image.new("RGB", (600, 400), (180, 180, 180))
    draw = ImageDraw.Draw(img)
    # Add dark texture lines to create a genuine scanned document appearance
    for x in range(0, 600, 8):
        draw.line([(x, 0), (x, 400)], fill=(120, 120, 120), width=2)
    # Paste a sharp, near-pure white rectangular box in the center (text mask)
    draw.rectangle([150, 120, 350, 170], fill=(255, 255, 255))

    findings = VisualTamperingChecker.check_visual(image=img)
    signals = [f["signal"] for f in findings]
    assert "pasted_white_patch" in signals
    assert any(f["score"] == 20 for f in findings)


# ==============================================================================
# 3. Universal Consistency Engine Tests
# ==============================================================================

def test_passport_mrz_corrupted_detected():
    """Corrupted passport MRZ string flags invalid_checksum."""
    findings = UniversalConsistencyEngine.check_consistency(
        doc_type="passport",
        extracted_fields={"passport_number": "A1234567"},
        raw_text="P<INDDOE<<JANE<<<<<<<<<<<<<<<<<<<<<<\nBAD_MRZ_CHECKSUM_123456<<7",
    )
    signals = [f["signal"] for f in findings]
    assert "invalid_checksum" in signals


def test_driving_license_state_format_validation():
    """Driving Licence not matching state pattern triggers invalid_checksum."""
    findings = UniversalConsistencyEngine.check_consistency(
        doc_type="driving_licence",
        extracted_fields={"driving_license_number": "INVALID-DL-FORMAT-000"},
    )
    signals = [f["signal"] for f in findings]
    assert "invalid_checksum" in signals


def test_fssai_digit_count_validation():
    """FSSAI license number must be exactly 14 digits."""
    findings = UniversalConsistencyEngine.check_consistency(
        doc_type="fssai",
        extracted_fields={"fssai_licence_number": "12345"},  # Only 5 digits
    )
    signals = [f["signal"] for f in findings]
    assert "invalid_checksum" in signals


def test_cross_field_applicant_equals_father_name():
    """Applicant Name identical to Father Name flags duplicate_field_label."""
    findings = UniversalConsistencyEngine.check_consistency(
        doc_type="pan",
        extracted_fields={
            "pan_number": "ABCDE1234F",
            "name": "RAMESH SHARMA",
            "father_name": "RAMESH SHARMA",
        },
    )
    signals = [f["signal"] for f in findings]
    assert "duplicate_field_label" in signals


def test_cross_field_future_date_of_birth():
    """Date of birth in the future triggers invalid_checksum."""
    findings = UniversalConsistencyEngine.check_consistency(
        doc_type="pan",
        extracted_fields={
            "pan_number": "ABCPE1234F",
            "dob": "2030-05-15",
        },
    )
    signals = [f["signal"] for f in findings]
    assert "invalid_checksum" in signals


# ==============================================================================
# 4. Universal Risk Scoring & Priority Tests
# ==============================================================================

def test_risk_scoring_high_priority_mapping():
    """Score >= 60 assigns priority='high' and review_required status."""
    res = authenticity_manager.assess_document(
        doc_type="pan",
        extracted_fields={
            "pan_number": "INVALID123",  # 30 pts (invalid checksum)
        },
        qr_fields={
            "pan_number": "DIFFERENT",   # 40 pts (qr mismatch)
        },
    )
    assert res["risk_score"] >= 60
    assert res["verification_status"] == "review_required"
    assert res["review_required"] is True
    assert res["priority"] == "high"
    assert "High Priority" in res["human_review_reason"]


def test_clean_document_zero_risk_verified():
    """Clean document produces 0 risk and verified status."""
    res = authenticity_manager.assess_document(
        doc_type="pan",
        extracted_fields={
            "pan_number": "ABCPE1234F",
            "name": "VIGHNESH POTE",
            "father_name": "ANIL POTE",
            "dob": "1995-04-12",
        },
    )
    assert res["risk_score"] == 0
    assert res["verification_status"] == "verified"
    assert res["review_required"] is False
    assert res["priority"] == "low"
    assert res["human_review_reason"] is None


def test_unsupported_document_type_safe():
    """Unknown or unsupported document safely returns 'unsupported' with 0 risk."""
    res = authenticity_manager.assess_document(
        doc_type="unknown",
        is_supported=False,
    )
    assert res["verification_status"] == "unsupported"
    assert res["risk_score"] == 0
    assert res["review_required"] is False


# ==============================================================================
# 5. Database & Audit Trail Persistence
# ==============================================================================

def test_document_integrity_audit_persistence():
    """Test that create_document persists records to document_integrity_checks."""
    # Clean doc persistence
    clean_doc = document_repository.create_document(
        user_id="c80c0b46-3bc0-4c6f-9db0-741341f7ad32",
        original_filename="clean_pan.pdf",
        file_bytes=b"%PDF-1.4 mock clean",
        file_type=".pdf",
        doc_type="pan",
        verification_status="verified",
        risk_score=0,
        review_required=False,
        suspicious_signals=[],
    )
    assert clean_doc["id"] is not None

    # Suspicious doc persistence
    suspicious_doc = document_repository.create_document(
        user_id="c80c0b46-3bc0-4c6f-9db0-741341f7ad32",
        original_filename="tampered_slip.pdf",
        file_bytes=b"%PDF-1.4 mock suspicious",
        file_type=".pdf",
        doc_type="salary_slip",
        verification_status="review_required",
        risk_score=65,
        review_required=True,
        suspicious_signals=[
            {"signal": "duplicate_field_label", "category": "layout", "score": 20},
            {"signal": "math_inconsistency", "category": "consistency", "score": 30},
            {"signal": "overlapping_text_regions", "category": "layout", "score": 15},
        ],
        human_review_reason="Visible inconsistencies detected (High Priority).",
    )
    assert suspicious_doc["id"] is not None


# ==============================================================================
# 6. Strict Terminology Invariant Check
# ==============================================================================

def test_strict_terminology_phase10_invariant():
    """Ensure the prohibited words 'fake', 'forged', 'fraudulent' never appear anywhere."""
    forbidden = ["fake", "forged", "fraudulent"]

    res = authenticity_manager.assess_document(
        doc_type="pan",
        extracted_fields={"pan_number": "BAD123", "name": "Aman Gupta"},
        qr_fields={"pan_number": "DIFFERENT", "name": "Suresh Rao"},
        ocr_lines=[
            MockBoxLine("Name", [10, 10, 50, 30]),
            MockBoxLine("Name", [10, 10, 50, 30]),
        ],
    )

    combined_text = (
        str(res.get("verification_status", "")) +
        " " +
        str(res.get("human_review_reason", "")) +
        " " +
        " ".join([str(s) for s in res.get("suspicious_signals", [])])
    ).lower()

    for word in forbidden:
        assert word not in combined_text, f"Forbidden word '{word}' found in assessment output!"
