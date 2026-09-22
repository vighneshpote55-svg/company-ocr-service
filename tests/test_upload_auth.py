"""
tests/test_upload_auth.py
Verification tests for Supabase Authentication during OCR Uploads:
- GET /api/auth/me with Bearer token returns 200
- POST /api/upload without token returns 401
- POST /api/upload with valid token returns 200
- POST /api/mode/offline without token returns 401
- POST /api/mode/offline with valid token returns 200
- POST /api/mode/ai/analyze without token returns 401
- POST /api/mode/ai/chat without token returns 401
- Depends(get_current_user) correctly extracts UserProfile and logs structured auth
"""

import io
import os
import time
import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
from auth_dependencies import get_current_user, UserProfile

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


def _make_valid_png():
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), "INCOME TAX DEPARTMENT", fill=(0, 0, 0))
    draw.text((10, 50), "ABCDE1234F", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def test_auth_me_authenticated():
    token = make_test_jwt("c80c0b46-3bc0-4c6f-9db0-741341f7ad32", "vighneshpote.info@gmail.com", role="user")
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "c80c0b46-3bc0-4c6f-9db0-741341f7ad32"
    assert data["email"] == "vighneshpote.info@gmail.com"


def test_upload_offline_requires_auth():
    png_bytes = _make_valid_png()
    res = client.post(
        "/api/mode/offline",
        files={"file": ("pan.png", png_bytes, "image/png")},
        data={"doc_type": "pan"},
    )
    assert res.status_code == 401


def test_upload_offline_with_auth_succeeds():
    token = make_test_jwt("c80c0b46-3bc0-4c6f-9db0-741341f7ad32", "vighneshpote.info@gmail.com", role="user")
    png_bytes = _make_valid_png()
    res = client.post(
        "/api/mode/offline",
        files={"file": ("pan.png", png_bytes, "image/png")},
        data={"doc_type": "pan"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "id" in data


def test_api_upload_requires_auth():
    png_bytes = _make_valid_png()
    res = client.post(
        "/api/upload",
        files={"file": ("pan.png", png_bytes, "image/png")},
        data={"mode": "offline", "doc_type": "pan"},
    )
    assert res.status_code == 401


def test_api_upload_with_auth_succeeds():
    token = make_test_jwt("c80c0b46-3bc0-4c6f-9db0-741341f7ad32", "vighneshpote.info@gmail.com", role="user")
    png_bytes = _make_valid_png()
    res = client.post(
        "/api/upload",
        files={"file": ("pan.png", png_bytes, "image/png")},
        data={"mode": "offline", "doc_type": "pan"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "id" in data


def test_ai_analyze_requires_auth():
    png_bytes = _make_valid_png()
    res = client.post(
        "/api/mode/ai/analyze",
        files={"file": ("test.png", png_bytes, "image/png")},
    )
    assert res.status_code == 401


def test_ai_chat_requires_auth():
    res = client.post(
        "/api/mode/ai/chat",
        json={"document_id": "test-doc-id", "message": "hello"},
    )
    assert res.status_code == 401


def test_document_file_unauthenticated_returns_401():
    res = client.get("/api/documents/some-doc-id/file")
    assert res.status_code == 401
    assert "Bearer JWT required" in res.json().get("detail", "")


def test_document_file_authenticated_and_bytes_match():
    user_id = "c80c0b46-3bc0-4c6f-9db0-741341f7ad32"
    token = make_test_jwt(user_id, "vighneshpote.info@gmail.com", role="user")
    png_bytes = _make_valid_png()

    # Upload document
    upload_res = client.post(
        "/api/upload",
        files={"file": ("pan.png", png_bytes, "image/png")},
        data={"mode": "offline", "doc_type": "pan"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # 1. Fetch file with valid auth
    file_res = client.get(
        f"/api/documents/{doc_id}/file",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert file_res.status_code == 200
    assert file_res.headers["content-type"] == "image/png"
    assert "inline" in file_res.headers.get("content-disposition", "")
    assert file_res.content == png_bytes

    # 2. Download endpoint with ?download=true
    download_res = client.get(
        f"/api/documents/{doc_id}/file?download=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert download_res.status_code == 200
    assert "attachment" in download_res.headers.get("content-disposition", "")
    assert download_res.content == png_bytes

    # 3. Thumbnail / Preview endpoint
    thumb_res = client.get(
        f"/api/documents/{doc_id}/thumbnail",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert thumb_res.status_code == 200
    assert thumb_res.headers["content-type"] == "image/png"


def test_document_file_wrong_user_returns_404():
    user_a = "c80c0b46-3bc0-4c6f-9db0-741341f7ad32"
    user_b = "11111111-2222-3333-4444-555555555555"
    token_a = make_test_jwt(user_a, "user_a@company.com", role="user")
    token_b = make_test_jwt(user_b, "user_b@company.com", role="user")
    png_bytes = _make_valid_png()

    # User A uploads
    upload_res = client.post(
        "/api/upload",
        files={"file": ("pan.png", png_bytes, "image/png")},
        data={"mode": "offline", "doc_type": "pan"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # User B attempts to access User A's file -> 404
    file_res = client.get(
        f"/api/documents/{doc_id}/file",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert file_res.status_code == 404

    # User B attempts to access User A's thumbnail -> 404
    thumb_res = client.get(
        f"/api/documents/{doc_id}/thumbnail",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert thumb_res.status_code == 404

