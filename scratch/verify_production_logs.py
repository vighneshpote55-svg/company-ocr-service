"""
scratch/verify_production_logs.py
Live verification script demonstrating production JSON structured logging,
request ID tracing, performance timing, and automated PII redaction.
"""

import io
import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import logging_utils

# Enable capture to inspect exact formatted JSON output
logging_utils.enable_log_capture()
from main import app


def create_sample_pan_card_image():
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "INCOME TAX DEPARTMENT", fill=(0, 0, 0))
    draw.text((20, 60), "GOVT. OF INDIA", fill=(0, 0, 0))
    draw.text((20, 100), "Permanent Account Number", fill=(0, 0, 0))
    draw.text((20, 140), "ABCDE1234F", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def main():
    print("================================================================================")
    print("LIVE PRODUCTION LOGGING & PII REDACTION VERIFICATION")
    print("================================================================================")

    client = TestClient(app)

    # 1. Check startup logs
    captured = logging_utils.get_captured_logs()
    print(f"\n[1] Startup & Lifecycle Logs Captured: {len(captured)} records")
    for r in captured:
        print(f"  -> Event: {r.get('event')} | Log: {json.dumps(r)}")

    # 2. Issue a Health Check Request with Request ID Tracing
    print("\n[2] Testing Health Endpoint with Trace Header:")
    logging_utils.clear_log_capture()
    trace_id = "trace-verify-prod-001"
    res_health = client.get("/health", headers={"X-Request-ID": trace_id})
    print(f"  Status: {res_health.status_code}")
    print(f"  Response X-Request-ID: {res_health.headers.get('X-Request-ID')}")
    assert res_health.headers.get("X-Request-ID") == trace_id

    health_logs = [r for r in logging_utils.get_captured_logs() if r.get("logger") != "httpx"]
    for r in health_logs:
        print(f"  Log Record: {json.dumps(r)}")
        assert r.get("request_id") == trace_id

    # 3. Process a document in Offline Mode
    print("\n[3] Testing Offline Mode Document Upload & Performance Logging:")
    logging_utils.clear_log_capture()
    pan_bytes = create_sample_pan_card_image()
    res_upload = client.post(
        "/api/mode/offline",
        files={"file": ("Vighnesh_PAN.png", pan_bytes, "image/png")},
    )
    print(f"  Upload Status: {res_upload.status_code}")
    returned_req_id = res_upload.headers.get("X-Request-ID")
    print(f"  Auto-generated Request ID: {returned_req_id}")

    upload_logs = [r for r in logging_utils.get_captured_logs() if r.get("logger") != "httpx"]
    print(f"\n  Captured {len(upload_logs)} log events for this upload:")
    events_found = []
    for r in upload_logs:
        ev = r.get("event")
        events_found.append(ev)
        print(f"  [{ev}] -> {json.dumps(r)}")
        # Check request ID alignment
        assert r.get("request_id") == returned_req_id

    assert "ocr_started" in events_found
    assert "ocr_completed" in events_found
    assert "document_processed" in events_found

    # 4. Verify PII Redaction across all logs
    print("\n[4] Verifying PII Redaction (PAN 'ABCDE1234F' must NEVER appear in logs):")
    full_log_str = json.dumps(upload_logs)
    if "ABCDE1234F" in full_log_str:
        print("  [FAIL] Raw PAN ABCDE1234F leaked into logs!")
        sys.exit(1)
    else:
        print("  [PASS] Zero raw PAN numbers found in logs. Automatic redaction active!")

    # 5. Direct Unit Verification of PII Redaction Patterns
    print("\n[5] Testing PII Pattern Redactor directly:")
    samples = {
        "PAN": ("User PAN is ABCDE1234F verified", "[REDACTED_PAN]"),
        "Aadhaar": ("Aadhaar number 1234 5678 9012 valid", "[REDACTED_AADHAAR]"),
        "IFSC": ("Branch code SBIN0001234 confirmed", "[REDACTED_IFSC]"),
        "Account": ("Acc 98765432109876 credited", "[REDACTED_ACCOUNT]"),
        "GSTIN": ("Tax GSTIN 27AAPFU0939F1ZV active", "[REDACTED_GSTIN]"),
    }
    for label, (text, expected_token) in samples.items():
        redacted = logging_utils.redact_sensitive_text(text)
        assert expected_token in redacted
        print(f"  {label:8}: '{text}' -> '{redacted}'")

    print("\n================================================================================")
    print("ALL PRODUCTION LOGGING & REDACTION VERIFICATIONS PASSED SUCCESSFULLY!")
    print("================================================================================")


if __name__ == "__main__":
    main()
