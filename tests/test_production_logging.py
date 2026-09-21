"""
tests/test_production_logging.py
Comprehensive test suite verifying Production-Grade JSON Structured Logging with PII Redaction:
- Task 1: JSON Structured Logging (UTC timestamp, standard format, safe serialization)
- Task 2: Request ID Tracing (propagation through lifecycle and response headers)
- Task 3: OCR Performance Logs (ocr_started, ocr_completed, duration_ms, NO raw OCR text)
- Task 4: AI Performance Logs (ai_started, ai_completed, model, duration_ms, NO raw prompts/responses)
- Task 5: Structured Error Logs (upload_failed, error_code, request_id, friendly frontend response preserved)
- Task 6: Automated PII Redaction (PAN, Aadhaar, Account numbers, IFSC, GSTIN, encryption keys, large payloads)
- Task 7: Startup & Health Logs (server_started, health_check events)
"""

import io
import json
import logging
import re
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
import logging_utils
import ollama_ai
import document_store


@pytest.fixture(autouse=True)
def capture_logs():
    """Enable log capture before each test and clear after."""
    logging_utils.enable_log_capture()
    logging_utils.clear_log_capture()
    yield
    logging_utils.clear_log_capture()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _make_dummy_image(text="TEST DOCUMENT"):
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


# ==============================================================================
# Task 1: JSON Structured Logging & Formatting
# ==============================================================================

def test_task1_json_structured_log_format():
    """Test that all emitted log entries are valid JSON with required standard fields."""
    test_logger = logging_utils.get_logger("test.task1")
    logging_utils.set_request_id("test-req-12345")

    logging_utils.log_event(
        test_logger,
        logging.INFO,
        event="document_processed",
        document_type="PAN Card",
        ocr_engine="RapidOCR",
        ai_model="none",
        processing_time_ms=120,
        status="success",
    )

    records = logging_utils.get_captured_logs()
    assert len(records) >= 1
    rec = records[-1]

    assert rec["request_id"] == "test-req-12345"
    assert rec["event"] == "document_processed"
    assert rec["document_type"] == "PAN Card"
    assert rec["ocr_engine"] == "RapidOCR"
    assert rec["ai_model"] == "none"
    assert rec["processing_time_ms"] == 120
    assert rec["status"] == "success"
    assert rec["level"] == "INFO"
    assert rec["logger"] == "test.task1"

    # Verify UTC ISO-8601 timestamp ending in 'Z'
    ts = rec["timestamp"]
    assert ts.endswith("Z")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts)


# ==============================================================================
# Task 2: Request ID Tracing Across Lifecycle
# ==============================================================================

def test_task2_request_id_tracing_generated_and_propagated(client):
    """Verify request ID is generated when missing and returned in response headers."""
    png_bytes = _make_dummy_image("HELLO WORLD")
    res = client.post(
        "/api/mode/offline",
        files={"file": ("test.png", png_bytes, "image/png")},
    )
    assert res.status_code == 200
    res_req_id = res.headers.get("X-Request-ID")
    assert res_req_id is not None
    assert len(res_req_id) >= 16

    # Verify captured logs for this request share the exact same request_id
    records = logging_utils.get_captured_logs()
    matching_records = [r for r in records if r.get("request_id") == res_req_id]
    assert len(matching_records) >= 2  # at least ocr_started, ocr_completed, document_processed
    assert any(r.get("event") == "ocr_started" for r in matching_records)
    assert any(r.get("event") == "ocr_completed" for r in matching_records)
    assert any(r.get("event") == "document_processed" for r in matching_records)


def test_task2_request_id_tracing_incoming_header_preserved(client):
    """Verify incoming X-Request-ID header is preserved and attached to all logs."""
    custom_id = "custom-trace-uuid-9999"
    png_bytes = _make_dummy_image("INCOMING ID TEST")
    res = client.post(
        "/api/mode/offline",
        files={"file": ("test.png", png_bytes, "image/png")},
        headers={"X-Request-ID": custom_id},
    )
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == custom_id

    records = logging_utils.get_captured_logs()
    matching_records = [r for r in records if r.get("request_id") == custom_id]
    assert len(matching_records) >= 2
    for r in matching_records:
        assert r["request_id"] == custom_id


# ==============================================================================
# Task 3: OCR Performance Logs & No Raw Text Leak
# ==============================================================================

def test_task3_ocr_performance_logging_and_no_text_leak(client):
    """
    Verify:
    1. ocr_started is logged with doc_type and filename
    2. ocr_completed is logged with duration_ms and status
    3. full OCR text is NEVER logged
    """
    secret_text = "SECRET-TOP-CONFIDENTIAL-PHRASE-XYZ"
    png_bytes = _make_dummy_image(secret_text)

    res = client.post(
        "/api/mode/offline",
        files={"file": ("secret_doc.png", png_bytes, "image/png")},
    )
    assert res.status_code == 200

    records = logging_utils.get_captured_logs()

    ocr_started = [r for r in records if r.get("event") == "ocr_started"]
    assert len(ocr_started) >= 1
    assert "doc_type" in ocr_started[0]

    ocr_completed = [r for r in records if r.get("event") == "ocr_completed"]
    assert len(ocr_completed) >= 1
    assert "duration_ms" in ocr_completed[0]
    assert isinstance(ocr_completed[0]["duration_ms"], int)
    assert ocr_completed[0]["status"] == "success"

    # CRITICAL: Verify the secret raw OCR text does not appear in any log record
    for r in records:
        log_json_str = json.dumps(r)
        assert secret_text not in log_json_str
        assert "SECRET-TOP-CONFIDENTIAL" not in log_json_str


# ==============================================================================
# Task 4: AI Performance Logs & No Prompt/Response Leak
# ==============================================================================

def test_task4_ai_performance_logs_and_no_prompt_leak(monkeypatch):
    """
    Verify:
    1. ai_started is logged with model
    2. ai_completed is logged with model, duration_ms, and status
    3. Prompts and raw AI completions are strictly excluded from logs
    """
    secret_prompt = "Tell me the secret nuclear codes"
    secret_response = "The secret code is 998877665544"

    class MockOllamaClient:
        def chat(self, *args, **kwargs):
            return {
                "message": {
                    "role": "assistant",
                    "content": f'{{"document_type": "Passport", "confidence": "high", "extracted_fields": {{"secret": "{secret_response}"}}, "summary": "Sample summary"}}',
                }
            }

    monkeypatch.setattr(ollama_ai, "get_client", lambda: MockOllamaClient())
    monkeypatch.setattr(ollama_ai, "check_ollama_health", lambda: {"reachable": True, "model_installed": True})
    monkeypatch.setattr(ollama_ai, "_ensure_image_format", lambda p: "fake_image.png")

    res = ollama_ai.analyze_document(
        file_path="fake_path.png",
        filename="fake.png",
        ocr_text=secret_prompt,
    )

    records = logging_utils.get_captured_logs()
    ai_started = [r for r in records if r.get("event") == "ai_started"]
    assert len(ai_started) >= 1
    assert "model" in ai_started[0]

    ai_completed = [r for r in records if r.get("event") == "ai_completed"]
    assert len(ai_completed) >= 1
    assert "duration_ms" in ai_completed[0]
    assert ai_completed[0]["model"] == "qwen2.5vl:3b"
    assert ai_completed[0]["status"] == "success"

    # CRITICAL: Prompt and completion must NEVER appear in logs
    for r in records:
        log_str = json.dumps(r)
        assert secret_prompt not in log_str
        assert secret_response not in log_str
        assert "nuclear codes" not in log_str


# ==============================================================================
# Task 5: Structured Error Logs with Standardized Codes
# ==============================================================================

def test_task5_structured_error_logs_unsupported_extension(client):
    """Verify upload_failed event with UNSUPPORTED_EXTENSION on invalid file type."""
    res = client.post(
        "/api/mode/offline",
        files={"file": ("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/x-dosexec")},
    )
    assert res.status_code == 400
    # Friendly response preserved
    assert res.json().get("detail") == "Unsupported file type."

    records = logging_utils.get_captured_logs()
    err_logs = [r for r in records if r.get("event") == "upload_failed"]
    assert len(err_logs) >= 1
    assert err_logs[0]["error_code"] == "UNSUPPORTED_EXTENSION"
    assert err_logs[0]["status_code"] == 400
    assert err_logs[0]["status"] == "failed"


def test_task5_structured_error_logs_empty_file(client):
    """Verify upload_failed event with EMPTY_FILE on 0-byte file."""
    res = client.post(
        "/api/mode/offline",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert res.status_code == 400
    assert "empty" in res.json().get("detail", "").lower()

    records = logging_utils.get_captured_logs()
    err_logs = [r for r in records if r.get("event") == "upload_failed"]
    assert len(err_logs) >= 1
    assert err_logs[0]["error_code"] == "EMPTY_FILE"


def test_task5_structured_error_logs_path_traversal(client):
    """Verify upload_failed event with PATH_TRAVERSAL_DETECTED."""
    res = client.post(
        "/api/mode/offline",
        files={"file": ("../../etc/passwd.png", b"dummy content", "image/png")},
    )
    assert res.status_code == 400

    records = logging_utils.get_captured_logs()
    err_logs = [r for r in records if r.get("event") == "upload_failed"]
    assert len(err_logs) >= 1
    assert err_logs[0]["error_code"] == "PATH_TRAVERSAL_DETECTED"


# ==============================================================================
# Task 6: Automated PII Redaction
# ==============================================================================

def test_task6_pii_redaction_unit():
    """Verify automatic redaction of PAN, Aadhaar, Account numbers, IFSC, GSTIN, and keys."""
    # 1. PAN
    text_pan = "User with PAN ABCDE1234F submitted form"
    redacted = logging_utils.redact_sensitive_text(text_pan)
    assert "ABCDE1234F" not in redacted
    assert "[REDACTED_PAN]" in redacted

    # 2. Aadhaar (spaced and continuous)
    text_aadhaar1 = "Aadhaar number is 9876 5432 1098 here"
    text_aadhaar2 = "Aadhaar number is 987654321098 here"
    assert "[REDACTED_AADHAAR]" in logging_utils.redact_sensitive_text(text_aadhaar1)
    assert "9876 5432 1098" not in logging_utils.redact_sensitive_text(text_aadhaar1)
    assert "[REDACTED_AADHAAR]" in logging_utils.redact_sensitive_text(text_aadhaar2)
    assert "987654321098" not in logging_utils.redact_sensitive_text(text_aadhaar2)

    # 3. Bank Account Number (12 to 16 digits)
    text_acc = "Salary deposited to account 12345678901234 on 1st"
    assert "[REDACTED_ACCOUNT]" in logging_utils.redact_sensitive_text(text_acc)
    assert "12345678901234" not in logging_utils.redact_sensitive_text(text_acc)

    # 4. IFSC Code
    text_ifsc = "Branch IFSC is SBIN0001234 for transfer"
    assert "[REDACTED_IFSC]" in logging_utils.redact_sensitive_text(text_ifsc)
    assert "SBIN0001234" not in logging_utils.redact_sensitive_text(text_ifsc)

    # 5. GSTIN
    text_gst = "Taxpayer GSTIN: 27AAPFU0939F1ZV recorded"
    assert "[REDACTED_GSTIN]" in logging_utils.redact_sensitive_text(text_gst)
    assert "27AAPFU0939F1ZV" not in logging_utils.redact_sensitive_text(text_gst)

    # 6. Encryption Key (64 hex characters)
    fake_key = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
    text_key = f"Key loaded: {fake_key}"
    assert "[REDACTED_KEY]" in logging_utils.redact_sensitive_text(text_key)
    assert fake_key not in logging_utils.redact_sensitive_text(text_key)


def test_task6_redact_data_dictionary():
    """Verify recursive dict redaction for sensitive keys and large payloads."""
    test_dict = {
        "user_pan": "ABCDE1234F",
        "nested": {
            "account": "98765432109876",
            "ifsc": "HDFC0001234",
        },
        "ocr_text": "This is a full page of extracted OCR text that should never be logged",
        "prompt": "You are an AI model...",
        "encryption_key": "secretkey",
    }
    cleaned = logging_utils.redact_data(test_dict)

    assert cleaned["user_pan"] == "[REDACTED_PAN]"
    assert cleaned["nested"]["account"] == "[REDACTED_ACCOUNT]"
    assert cleaned["nested"]["ifsc"] == "[REDACTED_IFSC]"
    assert cleaned["ocr_text"] == "[REDACTED_LARGE_PAYLOAD]"
    assert cleaned["prompt"] == "[REDACTED_LARGE_PAYLOAD]"
    assert cleaned["encryption_key"] == "[REDACTED_SECRET]"


# ==============================================================================
# Task 7: Startup and Health Logs
# ==============================================================================

def test_task7_health_endpoint_logs(client):
    """Verify /health endpoint logs health_check structured event."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "storage" in data
    assert "encryption" in data

    records = logging_utils.get_captured_logs()
    health_logs = [r for r in records if r.get("event") == "health_check"]
    assert len(health_logs) >= 1
    assert health_logs[0]["status"] == "healthy"
    assert "storage" in health_logs[0]
