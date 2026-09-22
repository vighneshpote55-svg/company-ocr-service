"""
tests/test_auth.py
Unit tests for Supabase Authentication, JWT validation, and RBAC:
- Valid Supabase JWT authenticates successfully
- Expired / invalid JWT rejected with HTTP 401
- Missing credentials rejected with HTTP 401
- GET /api/auth/me returns expected user profile & role
- RBAC: Normal user blocked from POST /api/ai/config with HTTP 403 Forbidden
"""

import os
import time
import jwt
import pytest
from fastapi.testclient import TestClient

from main import app
from auth_dependencies import verify_supabase_jwt, get_current_user

client = TestClient(app)

TEST_JWT_SECRET = "super-secret-supabase-jwt-test-key-32chars!"

@pytest.fixture(scope="module", autouse=True)
def setup_auth_env():
    old_env = dict(os.environ)
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["AUTH_MODE"] = "jwt"
    os.environ["DOCUMENT_ENCRYPTION_KEY"] = "f4949e05975053d959987df0e8b210e0007662e69073599d21935540d5e91ea9"
    yield
    os.environ.clear()
    os.environ.update(old_env)


def make_test_jwt(user_id: str, email: str, role: str = "user", expires_in_seconds: int = 3600) -> str:
    """Helper to create a signed HS256 Supabase-like JWT."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "app_metadata": {"role": role},
        "user_metadata": {"full_name": f"User {user_id[:6]}", "role": role},
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


def test_missing_token_returns_401():
    """Request to protected endpoint without Authorization header must return HTTP 401."""
    res = client.get("/api/auth/me")
    assert res.status_code == 401
    assert "credentials were not provided" in res.json().get("detail", "").lower() or "authentication" in res.json().get("detail", "").lower()


def test_invalid_signature_returns_401():
    """Token signed with wrong key must return HTTP 401."""
    bad_token = jwt.encode({"sub": "user-123"}, "wrong-secret-key-1234567890!", algorithm="HS256")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert res.status_code == 401


def test_expired_token_returns_401():
    """Token with expired timestamp must return HTTP 401 with session expired message."""
    expired_token = make_test_jwt("user-123", "expired@test.com", expires_in_seconds=-60)
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert "expired" in res.json().get("detail", "").lower()


def test_valid_user_jwt_returns_profile():
    """Valid JWT should return user profile with role 'user'."""
    user_token = make_test_jwt("user-uuid-1111", "alice@example.com", role="user")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "user-uuid-1111"
    assert data["email"] == "alice@example.com"
    assert data["role"] == "user"


def test_valid_admin_jwt_returns_admin_profile():
    """Valid JWT with admin role should return profile with role 'admin'."""
    admin_token = make_test_jwt("admin-uuid-9999", "admin@example.com", role="admin")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "admin-uuid-9999"
    assert data["role"] == "admin"


def test_normal_user_cannot_update_ai_config():
    """Normal user (role='user') attempting POST /api/ai/config must be rejected with HTTP 403 Forbidden."""
    user_token = make_test_jwt("user-uuid-1111", "alice@example.com", role="user")
    payload = {
        "provider": "openrouter",
        "api_key": "sk-test-key-attempt",
        "model": "test-model",
    }
    res = client.post("/api/ai/config", json=payload, headers={"Authorization": f"Bearer {user_token}"})
    assert res.status_code == 403
    assert "permission" in res.json().get("detail", "").lower()


def test_normal_user_cannot_test_ai_connection():
    """Normal user (role='user') attempting POST /api/ai/test-connection must be rejected with HTTP 403 Forbidden."""
    user_token = make_test_jwt("user-uuid-1111", "alice@example.com", role="user")
    res = client.post("/api/ai/test-connection", json={"provider": "local"}, headers={"Authorization": f"Bearer {user_token}"})
    assert res.status_code == 403


def test_admin_can_view_and_update_ai_config():
    """Admin user (role='admin') can update AI config."""
    admin_token = make_test_jwt("admin-uuid-9999", "admin@example.com", role="admin")
    payload = {
        "provider": "local",
        "model": "qwen2.5vl:3b",
        "fallback_on_error": False,
    }
    res = client.post("/api/ai/config", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data.get("active_provider") in ("local", "ollama")
