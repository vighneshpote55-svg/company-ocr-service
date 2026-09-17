"""
tests/test_ollama_ai.py
Unit and integration tests for local Ollama AI Mode (Qwen2.5-VL:3B):
- check_ollama_health helper
- error handling when Ollama is unreachable or model is missing
- /api/upload with mode="offline" vs mode="ai"
- /api/ollama/status endpoint
"""

import io
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
import ollama_ai


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


def test_check_ollama_health_success():
    """Test check_ollama_health when server and model are available."""
    mock_client = MagicMock()
    mock_client.list.return_value = {
        "models": [{"model": "qwen2.5vl:3b"}, {"model": "gemma3:1b"}]
    }
    with patch("ollama_ai.get_client", return_value=mock_client):
        health = ollama_ai.check_ollama_health()
        assert health["reachable"] is True
        assert health["model_installed"] is True
        assert health["model"] == "qwen2.5vl:3b"


def test_check_ollama_health_missing_model():
    """Test check_ollama_health when target model is not installed."""
    mock_client = MagicMock()
    mock_client.list.return_value = {
        "models": [{"model": "llama3:8b"}]
    }
    with patch("ollama_ai.get_client", return_value=mock_client):
        health = ollama_ai.check_ollama_health()
        assert health["reachable"] is True
        assert health["model_installed"] is False
        assert "ollama pull qwen2.5vl:3b" in health["error"]


def test_check_ollama_health_server_down():
    """Test check_ollama_health when Ollama server connection is refused."""
    with patch("ollama_ai.get_client", side_effect=Exception("Failed to connect to 127.0.0.1:11434: Connection refused")):
        health = ollama_ai.check_ollama_health()
        assert health["reachable"] is False
        assert health["model_installed"] is False
        assert health["error"] == "Ollama server is not running."


def test_ollama_status_endpoint(client):
    """Test GET /api/ollama/status endpoint."""
    res = client.get("/api/ollama/status")
    assert res.status_code == 200
    data = res.json()
    assert "reachable" in data
    assert "model_installed" in data
    assert data["model"] == "qwen2.5vl:3b"


def test_upload_endpoint_offline_mode(client):
    """Test POST /api/upload with mode='offline' runs standard RapidOCR."""
    buf = _create_test_image([
        "INCOME TAX DEPARTMENT",
        "PERMANENT ACCOUNT NUMBER",
        "ABCDE1234F",
    ])
    res = client.post(
        "/api/upload",
        files={"file": ("test_pan.png", buf, "image/png")},
        data={"mode": "offline", "doc_type": "pan"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["doc_type"] == "pan"
    assert "extracted_fields" in data


def test_upload_endpoint_ai_mode_success(client):
    """Test POST /api/upload with mode='ai' calls ollama_ai and returns structured AI result."""
    mock_ai_result = {
        "document_type": "Permanent Account Number Card",
        "confidence": "high",
        "summary": "Verified PAN Card with tax identification details.",
        "reasoning": ["Document explicitly states Permanent Account Number Card."],
        "extracted_fields": {
            "PAN Number": "ABCDE1234F",
            "Name": "VIKRAM SHARMA",
        },
        "processing_time_seconds": 1.45,
        "model_used": "qwen2.5vl:3b",
        "is_local_ai": True,
    }

    mock_health = {"reachable": True, "model_installed": True, "model": "qwen2.5vl:3b"}

    with patch("ollama_ai.check_ollama_health", return_value=mock_health), \
         patch("ollama_ai.analyze_document", return_value=mock_ai_result):

        buf = _create_test_image(["PAN CARD", "ABCDE1234F"])
        res = client.post(
            "/api/upload",
            files={"file": ("sample.png", buf, "image/png")},
            data={"mode": "ai"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["document_type"] == "Permanent Account Number Card"
        assert data["confidence"] == "high"
        assert data["is_local_ai"] is True
        assert data["extracted_fields"]["PAN Number"] == "ABCDE1234F"
        assert "document_id" in data


def test_upload_endpoint_ai_mode_server_down(client):
    """Test POST /api/upload with mode='ai' returns 503 when Ollama server is down."""
    mock_health = {"reachable": False, "model_installed": False, "error": "Ollama server is not running."}

    with patch("ollama_ai.check_ollama_health", return_value=mock_health):
        buf = _create_test_image(["SOME TEXT"])
        res = client.post(
            "/api/upload",
            files={"file": ("sample.png", buf, "image/png")},
            data={"mode": "ai"},
        )
        assert res.status_code == 503
        data = res.json()
        assert data["error"] == "Ollama server is not running."


def test_upload_endpoint_ai_mode_model_missing(client):
    """Test POST /api/upload with mode='ai' returns 503 with pull instruction when model is missing."""
    mock_health = {
        "reachable": True,
        "model_installed": False,
        "error": "Model 'qwen2.5vl:3b' is missing. Please run: ollama pull qwen2.5vl:3b",
    }

    with patch("ollama_ai.check_ollama_health", return_value=mock_health):
        buf = _create_test_image(["SOME TEXT"])
        res = client.post(
            "/api/upload",
            files={"file": ("sample.png", buf, "image/png")},
            data={"mode": "ai"},
        )
        assert res.status_code == 503
        data = res.json()
        assert "ollama pull qwen2.5vl:3b" in data["error"]
