"""
tests/test_production_hardening.py

Comprehensive tests for Phase 7 Production Hardening:
- Dynamic configuration & CORS
- File size limit enforcement
- In-memory rate limiting with HTTP 429 & Retry-After header
- Readiness probe /ready and /api/ready
- Architecture verification (Ollama network isolation in docker-compose)
"""

import os
import io
import yaml
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from main import app, get_cors_origins, get_max_image_size_bytes, get_max_pdf_size_bytes
from rate_limiter import (
    SlidingWindowRateLimiter,
    get_client_ip,
    reset_rate_limits,
    is_rate_limit_enabled,
)


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Ensure clean rate limiting state before and after each test."""
    reset_rate_limits()
    yield
    reset_rate_limits()


def test_cors_origins_resolution():
    """Test CORS resolution based on ENVIRONMENT and CORS_ALLOWED_ORIGINS."""
    # 1. Default dev origins
    with patch.dict(os.environ, {"ENVIRONMENT": "development", "CORS_ALLOWED_ORIGINS": ""}):
        dev_origins = get_cors_origins()
        assert "http://localhost:5173" in dev_origins
        assert "http://127.0.0.1:5173" in dev_origins

    # 2. Production with fallback
    with patch.dict(os.environ, {"ENVIRONMENT": "production", "CORS_ALLOWED_ORIGINS": ""}):
        prod_origins = get_cors_origins()
        assert "http://localhost:80" in prod_origins or "http://localhost" in prod_origins
        assert "http://localhost:5173" not in prod_origins

    # 3. Explicit custom origins
    with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "https://ocr.mycompany.internal,https://app.mycompany.internal"}):
        custom_origins = get_cors_origins()
        assert "https://ocr.mycompany.internal" in custom_origins
        assert "https://app.mycompany.internal" in custom_origins
        assert len(custom_origins) == 2


def test_dynamic_file_size_limits():
    """Test dynamic max file size calculations from environment variables."""
    with patch.dict(os.environ, {"MAX_IMAGE_SIZE_MB": "15", "MAX_PDF_SIZE_MB": "45"}):
        assert get_max_image_size_bytes() == 15 * 1024 * 1024
        assert get_max_pdf_size_bytes() == 45 * 1024 * 1024

    with patch.dict(os.environ, {"MAX_IMAGE_SIZE_MB": "invalid", "MAX_PDF_SIZE_MB": "invalid"}):
        assert get_max_image_size_bytes() == 20 * 1024 * 1024
        assert get_max_pdf_size_bytes() == 50 * 1024 * 1024


def test_readiness_probe_healthy():
    """Test /ready returns HTTP 200 and structured checks when core components are functional."""
    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert "status" in data
    assert data["checks"]["rapidocr"] is True
    assert data["checks"]["storage"] is True
    assert data["checks"]["encryption_key"] is True
    assert "ollama" in data["checks"]
    assert "details" in data


def test_readiness_probe_alias():
    """Test /api/ready alias returns identical structured response."""
    client = TestClient(app)
    response = client.get("/api/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert "checks" in data


def test_readiness_probe_degraded_when_ollama_down():
    """Test readiness is still 200 (degraded) when Ollama is unreachable because Offline Mode works."""
    client = TestClient(app)
    with patch("ollama_ai.check_ollama_health", return_value={"reachable": False, "model_installed": False, "models": []}):
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["status"] == "degraded"
        assert data["checks"]["ollama"] is False


def test_readiness_probe_fails_when_storage_or_encryption_unhealthy():
    """Test readiness returns 503 when core components (storage or encryption) fail."""
    client = TestClient(app)
    with patch("encryption.is_encryption_available", return_value=False):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["status"] == "error"
        assert data["checks"]["encryption_key"] is False


def test_rate_limiter_sliding_window_logic():
    """Test SlidingWindowRateLimiter sliding window tracking and retry-after calculation."""
    limiter = SlidingWindowRateLimiter(window_seconds=60)
    key = "192.168.1.100:test_action"

    # Allow up to 3 requests
    assert limiter.is_allowed(key, max_requests=3) is True
    assert limiter.is_allowed(key, max_requests=3) is True
    assert limiter.is_allowed(key, max_requests=3) is True

    # 4th request must be rejected
    assert limiter.is_allowed(key, max_requests=3) is False
    retry_after = limiter.get_retry_after(key, max_requests=3)
    assert retry_after > 0
    assert retry_after <= 60


def test_rate_limiting_http_429_on_chat():
    """Test /api/mode/ai/chat returns HTTP 429 when rate limit is exceeded."""
    client = TestClient(app)

    with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "true", "RATE_LIMIT_AI_CHAT_PER_MINUTE": "2"}):
        # 1st and 2nd chat requests
        res1 = client.post("/api/mode/ai/chat", json={"message": "", "document_id": "none"})
        # (This will fail with 400 for empty message or 401 if auth enabled, but rate limiter evaluates before or during)
        res2 = client.post("/api/mode/ai/chat", json={"message": "hello", "document_id": "test"})
        # 3rd request from same client exceeds limit of 2
        res3 = client.post(
            "/api/mode/ai/chat",
            json={"message": "hello again", "document_id": "test"},
            headers={"X-Forwarded-For": "203.0.113.195"},
        )

        # Test specifically with consistent forwarded IP
        client_ip = "198.51.100.42"
        r1 = client.post("/api/mode/ai/chat", json={"message": "q1", "document_id": "d1"}, headers={"X-Forwarded-For": client_ip})
        r2 = client.post("/api/mode/ai/chat", json={"message": "q2", "document_id": "d1"}, headers={"X-Forwarded-For": client_ip})
        r3 = client.post("/api/mode/ai/chat", json={"message": "q3", "document_id": "d1"}, headers={"X-Forwarded-For": client_ip})

        assert r3.status_code == 429
        assert "Too Many Requests" in r3.json()["detail"] or "rate limit" in r3.json()["detail"].lower()
        assert "Retry-After" in r3.headers


def test_rate_limit_disabled_flag():
    """Test that setting RATE_LIMIT_ENABLED=false bypasses rate limiting."""
    client = TestClient(app)
    with patch.dict(os.environ, {"RATE_LIMIT_ENABLED": "false", "RATE_LIMIT_AI_CHAT_PER_MINUTE": "1"}):
        client_ip = "198.51.100.50"
        for _ in range(5):
            r = client.post("/api/mode/ai/chat", json={"message": "q", "document_id": "d"}, headers={"X-Forwarded-For": client_ip})
            assert r.status_code != 429


def test_docker_compose_ollama_network_isolation():
    """Verify that docker-compose.yml does NOT expose Ollama's port to host."""
    compose_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-compose.yml")
    assert os.path.exists(compose_path)

    with open(compose_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    ollama_cfg = config["services"]["ollama"]
    # Ollama must not have 'ports' mapped to host
    assert "ports" not in ollama_cfg, "Ollama must not expose ports publicly!"
    # Ollama must be on internal_net
    assert "internal_net" in ollama_cfg["networks"]
    # internal_net must have internal: true
    assert config["networks"]["internal_net"]["internal"] is True
