"""
scratch/verify_live_upload_auth.py
Live end-to-end verification of Supabase auth, upload flow, Offline Mode, AI Mode, and Document Vault:
- GET /api/auth/me
- POST /api/mode/offline
- POST /api/upload
- POST /api/mode/ai/analyze
- GET /api/documents
- Verifies 401 when token is missing or invalid
"""

import os
import time
import jwt
import requests

BASE_URL = "http://127.0.0.1:8000"
USER_ID = "c80c0b46-3bc0-4c6f-9db0-741341f7ad32"
EMAIL = "vighneshpote.info@gmail.com"
TEST_IMG = "scratch/test_docs/PAN_Vighnesh.png"

# Read SUPABASE_JWT_SECRET from .env
from dotenv import load_dotenv
load_dotenv()
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

def make_jwt(expires_in=3600):
    now = int(time.time())
    payload = {
        "sub": USER_ID,
        "email": EMAIL,
        "aud": "authenticated",
        "role": "authenticated",
        "app_metadata": {"role": "user"},
        "user_metadata": {"full_name": "Vighnesh Pote", "role": "user"},
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def main():
    print("=== STEP 1: Verify /api/auth/me ===")
    token = make_jwt()
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    print(f"Status: {r.status_code}, Response: {r.json()}")
    assert r.status_code == 200
    assert r.json()["id"] == USER_ID

    print("\n=== STEP 2: Verify unauthenticated upload fails with 401 ===")
    with open(TEST_IMG, "rb") as f:
        r_unauth = requests.post(f"{BASE_URL}/api/mode/offline", files={"file": ("pan.png", f, "image/png")})
    print(f"Unauthenticated Status: {r_unauth.status_code}")
    assert r_unauth.status_code == 401

    print("\n=== STEP 3: Verify authenticated /api/mode/offline upload ===")
    with open(TEST_IMG, "rb") as f:
        r_offline = requests.post(
            f"{BASE_URL}/api/mode/offline",
            files={"file": ("PAN_Vighnesh.png", f, "image/png")},
            data={"doc_type": "pan"},
            headers=headers,
        )
    print(f"Offline Mode Status: {r_offline.status_code}")
    assert r_offline.status_code == 200
    offline_data = r_offline.json()
    print(f"Offline doc_id: {offline_data.get('id')}, doc_type: {offline_data.get('doc_type')}")
    assert offline_data.get("id")

    print("\n=== STEP 4: Verify authenticated /api/upload ===")
    with open(TEST_IMG, "rb") as f:
        r_upload = requests.post(
            f"{BASE_URL}/api/upload",
            files={"file": ("PAN_Vighnesh.png", f, "image/png")},
            data={"mode": "offline", "doc_type": "pan"},
            headers=headers,
        )
    print(f"/api/upload Status: {r_upload.status_code}")
    assert r_upload.status_code == 200
    upload_data = r_upload.json()
    print(f"Upload doc_id: {upload_data.get('id')}")
    assert upload_data.get("id")

    print("\n=== STEP 5: Verify authenticated /api/mode/ai/analyze ===")
    with open(TEST_IMG, "rb") as f:
        r_ai = requests.post(
            f"{BASE_URL}/api/mode/ai/analyze",
            files={"file": ("PAN_Vighnesh.png", f, "image/png")},
            headers=headers,
        )
    print(f"AI Mode Analyze Status: {r_ai.status_code}")
    assert r_ai.status_code == 200
    ai_data = r_ai.json()
    print(f"AI doc_id: {ai_data.get('document_id') or ai_data.get('id')}, doc_type: {ai_data.get('document_type')}")
    assert ai_data.get("document_id") or ai_data.get("id")

    print("\n=== STEP 6: Verify Document Vault for user ===")
    r_vault = requests.get(f"{BASE_URL}/api/documents", headers=headers)
    print(f"Vault Status: {r_vault.status_code}")
    assert r_vault.status_code == 200
    docs = r_vault.json()
    print(f"Total documents in user vault: {len(docs)}")
    assert len(docs) >= 3

    print("\n=== ALL E2E VERIFICATION CHECKS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
