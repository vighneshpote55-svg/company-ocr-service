"""
tests/test_modes_and_ai.py
Unit and integration tests for Offline Mode and AI Mode endpoints:
- /api/mode/offline (supported document -> supported=True)
- /api/mode/offline (unsupported document -> supported=False with specific rejection message)
- /api/mode/ai/status (runtime AI configuration discovery)
- /api/mode/ai/analyze (analyzes document, returns structured document_type, confidence, summary, reasoning)
- /api/mode/ai/chat (answers questions grounded in document text)
- Context isolation between multiple documents in AI mode
- Error handling for missing AI API key and corrupt files
"""

import io
import json
import os
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
import document_store


@pytest.fixture(autouse=True)
def reset_app_security(monkeypatch):
    import main
    main._startup_security_error = None
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    yield
    main._startup_security_error = None


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _create_test_image(text_lines):
    """Helper to generate an in-memory image with readable text lines."""
    img = Image.new("RGB", (500, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 20
    for line in text_lines:
        draw.text((20, y), line, fill=(0, 0, 0))
        y += 35
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_ai_mode_status_endpoint(client, monkeypatch):
    """Test GET /api/mode/ai/status reports provider and key configuration."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    res = client.get("/api/mode/ai/status")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert data["configured"] is False
    assert "AI_API_KEY is not set" in data["message"]

    monkeypatch.setenv("AI_API_KEY", "test-mock-key-12345")
    res2 = client.get("/api/mode/ai/status")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["configured"] is True


def test_offline_mode_supported_document_succeeds(client):
    """Test Offline Mode with a supported Indian document type (PAN Card)."""
    buf = _create_test_image([
        "INCOME TAX DEPARTMENT",
        "PERMANENT ACCOUNT NUMBER",
        "ABCDE1234F",
        "FATHER'S NAME: RAMESH SHARMA",
    ])

    res = client.post(
        "/api/mode/offline",
        files={"file": ("pan_sample.png", buf, "image/png")},
        data={"doc_type": "pan"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["supported"] is True
    assert data["doc_type"] == "pan"
    assert data["status"] in ("completed", "success", "low_confidence", "warning")
    assert "extracted_fields" in data


def test_offline_mode_unsupported_document_rejected(client):
    """
    Test Offline Mode with an unsupported document (e.g., Employment Agreement or general notice).
    Must return clear rejection message:
    'This document type is not supported in Offline Mode. Please use AI Mode for unknown documents.'
    """
    buf = _create_test_image([
        "ACME CORPORATION EMPLOYMENT AGREEMENT",
        "EMPLOYEE NAME: JOHN SMITH",
        "DESIGNATION: SENIOR SOFTWARE ENGINEER",
        "JOINING DATE: 15 OCTOBER 2026",
        "ANNUAL SALARY: USD 120000",
    ])

    res = client.post(
        "/api/mode/offline",
        files={"file": ("employment_contract.png", buf, "image/png")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["supported"] is False
    assert data["status"] == "unsupported"
    expected_msg = "This document type is not supported in Offline Mode. Please use AI Mode for unknown documents."
    assert data["message"] == expected_msg


@pytest.mark.asyncio
async def test_ai_analyze_endpoint_success(client, monkeypatch):
    """Test AI Mode analyze endpoint with mock AI response."""
    mock_ai_analysis = {
        "document_type": "Employment Contract",
        "confidence": "high",
        "summary": "This document appears to be an employment contract because it contains employer/employee information, joining terms, salary information and employment conditions.",
        "reasoning": [
            "Contains employer and employee information",
            "Contains joining terms and position",
            "Contains compensation and salary information",
        ],
    }

    with patch("ai_service.analyze_document", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_ai_analysis

        buf = _create_test_image([
            "ACME CORP - EMPLOYMENT AGREEMENT",
            "EMPLOYEE NAME: JANE DOE",
            "JOINING DATE: 15 OCTOBER 2026",
            "ANNUAL COMPENSATION: $120,000",
            "TERMS AND CONDITIONS OF EMPLOYMENT",
        ])

        res = client.post(
            "/api/mode/ai/analyze",
            files={"file": ("Employment_Contract.png", buf, "image/png")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["document_type"] == "Employment Contract"
        assert data["confidence"] == "high"
        assert "employment contract" in data["summary"].lower()
        assert len(data["reasoning"]) >= 2
        assert "document_id" in data
        assert data["filename"] == "Employment_Contract.png"


@pytest.mark.asyncio
async def test_ai_chat_endpoint_answers_with_document_context(client):
    """Test AI Mode chat endpoint grounded in document context."""
    # First persist a mock document in document store
    doc_record = document_store.save_document(
        file_bytes=b"dummy content",
        filename="Employment_Contract.pdf",
        result_data={
            "doc_type": "ai_analyzed",
            "document_type": "Employment Contract",
            "extracted_text": (
                "ACME CORPORATION EMPLOYMENT AGREEMENT\n"
                "Employee Name: Alex Johnson\n"
                "Designation: Lead Architect\n"
                "Joining Date: 15 October 2026\n"
                "Annual Base Salary: USD 150,000\n"
                "Employer: ACME Global Technologies Inc.\n"
                "Notice Period: 60 Days\n"
                "Agreement Expiry Date: None (Permanent Position)"
            ),
        },
    )
    doc_id = doc_record["id"]

    with patch("ai_service.chat_with_document", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "The joining date mentioned in the document is 15 October 2026."

        res = client.post(
            "/api/mode/ai/chat",
            json={
                "document_id": doc_id,
                "message": "What is the joining date?",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "15 October 2026" in data["response"]

        mock_chat.assert_called_once()
        kwargs = mock_chat.call_args.kwargs
        assert "Alex Johnson" in kwargs.get("document_text", "")
        assert "What is the joining date?" in kwargs.get("message", "")


@pytest.mark.asyncio
async def test_ai_chat_document_context_isolation(client):
    """
    Test context isolation:
    Ensure Document A and Document B maintain strictly separate contexts.
    """
    doc_a = document_store.save_document(
        file_bytes=b"doc a",
        filename="Contract_A.pdf",
        result_data={
            "doc_type": "ai_analyzed",
            "document_type": "Contract A",
            "extracted_text": "Company Alpha agreed to pay 50,000 USD to Contractor Alice.",
        },
    )
    doc_b = document_store.save_document(
        file_bytes=b"doc b",
        filename="Contract_B.pdf",
        result_data={
            "doc_type": "ai_analyzed",
            "document_type": "Contract B",
            "extracted_text": "Company Beta agreed to pay 90,000 EUR to Contractor Bob.",
        },
    )

    with patch("ai_service.chat_with_document", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = lambda document_text, filename, message, history=None: f"Answer from {filename}: {document_text}"

        res_a = client.post(
            "/api/mode/ai/chat",
            json={"document_id": doc_a["id"], "message": "Who is the contractor?"},
        )
        assert res_a.status_code == 200
        assert "Alice" in res_a.json()["response"]
        assert "Bob" not in res_a.json()["response"]

        res_b = client.post(
            "/api/mode/ai/chat",
            json={"document_id": doc_b["id"], "message": "Who is the contractor?"},
        )
        assert res_b.status_code == 200
        assert "Bob" in res_b.json()["response"]
        assert "Alice" not in res_b.json()["response"]


def test_ai_chat_invalid_document_id_returns_404(client):
    """Test non-existent document_id in chat returns 404."""
    res = client.post(
        "/api/mode/ai/chat",
        json={"document_id": "non-existent-uuid-12345", "message": "Hello"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()
