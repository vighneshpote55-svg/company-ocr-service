"""
tests/test_multi_user_isolation.py
Comprehensive multi-tenant isolation tests between User A and User B:
- User A uploads document
- User B cannot see User A's document in /api/documents
- User B cannot GET /api/documents/{doc_id}
- User B cannot GET /api/documents/{doc_id}/file
- User B cannot GET /api/documents/{doc_id}/preview
- User B cannot chat with User A's document
- User B cannot delete User A's document
- User B calling /api/documents/clear does not affect User A
- /api/stats is completely isolated per user
"""

import os
import time
import io
import jwt
import pytest
from fastapi.testclient import TestClient

from main import app
import document_store

client = TestClient(app)

TEST_JWT_SECRET = "super-secret-supabase-jwt-test-key-32chars!"

@pytest.fixture(scope="module", autouse=True)
def setup_isolation_env():
    old_env = dict(os.environ)
    os.environ["SUPABASE_JWT_SECRET"] = TEST_JWT_SECRET
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["AUTH_MODE"] = "jwt"
    os.environ["DOCUMENT_ENCRYPTION_KEY"] = "f4949e05975053d959987df0e8b210e0007662e69073599d21935540d5e91ea9"
    yield
    os.environ.clear()
    os.environ.update(old_env)

USER_A_ID = "11111111-aaaa-aaaa-aaaa-111111111111"
USER_B_ID = "22222222-bbbb-bbbb-bbbb-222222222222"


def make_user_token(user_id: str, email: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "app_metadata": {"role": "user"},
        "user_metadata": {"role": "user"},
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


token_a = make_user_token(USER_A_ID, "usera@test.com")
token_b = make_user_token(USER_B_ID, "userb@test.com")
headers_a = {"Authorization": f"Bearer {token_a}"}
headers_b = {"Authorization": f"Bearer {token_b}"}


@pytest.fixture(autouse=True)
def cleanup_vault():
    """Ensure clean vault before and after tests."""
    document_store.clear_all_documents(user_id=USER_A_ID)
    document_store.clear_all_documents(user_id=USER_B_ID)
    yield
    document_store.clear_all_documents(user_id=USER_A_ID)
    document_store.clear_all_documents(user_id=USER_B_ID)


def test_multi_user_document_isolation():
    # 1. User A creates a document
    doc_a_record = document_store.save_document(
        file_bytes=b"Sample PDF Content for User A",
        filename="user_a_contract.pdf",
        result_data={
            "doc_type": "contract",
            "document_type": "Contract",
            "status": "completed",
            "confidence": 0.98,
            "extracted_text": "Agreement between Party A and Party B",
            "fields": {"party_a": "Alice", "amount": "$5,000"},
        },
        user_id=USER_A_ID,
    )
    doc_a_id = doc_a_record["id"]

    # 2. User A queries /api/documents -> Sees own document
    res_a = client.get("/api/documents", headers=headers_a)
    assert res_a.status_code == 200
    docs_a = res_a.json()["items"]
    assert any(d["id"] == doc_a_id for d in docs_a)

    # 3. User B queries /api/documents -> User A's document is NOT in the list!
    res_b = client.get("/api/documents", headers=headers_b)
    assert res_b.status_code == 200
    docs_b = res_b.json()["items"]
    assert not any(d["id"] == doc_a_id for d in docs_b)
    assert len(docs_b) == 0

    # 4. User B attempts GET /api/documents/{doc_a_id} -> 404 (no leak)
    res_get_b = client.get(f"/api/documents/{doc_a_id}", headers=headers_b)
    assert res_get_b.status_code == 404

    # 5. User B attempts GET /api/documents/{doc_a_id}/file -> 404
    res_file_b = client.get(f"/api/documents/{doc_a_id}/file", headers=headers_b)
    assert res_file_b.status_code == 404

    # 6. User B attempts GET /api/documents/{doc_a_id}/preview -> 404
    res_prev_b = client.get(f"/api/documents/{doc_a_id}/preview", headers=headers_b)
    assert res_prev_b.status_code == 404

    # 7. User B attempts AI chat with User A's document -> 404
    res_chat_b = client.post(
        "/api/mode/ai/chat",
        json={"document_id": doc_a_id, "message": "What is the contract amount?"},
        headers=headers_b,
    )
    assert res_chat_b.status_code == 404

    # 8. User B attempts to DELETE User A's document -> 404
    res_del_b = client.delete(f"/api/documents/{doc_a_id}", headers=headers_b)
    assert res_del_b.status_code == 404

    # 9. User B calls DELETE /api/documents/clear -> Clears ONLY User B's documents
    res_clear_b = client.delete("/api/documents/clear", headers=headers_b)
    assert res_clear_b.status_code == 200
    assert res_clear_b.json()["deleted_count"] == 0

    # Verify User A's document is still safe and accessible by User A
    res_a_after = client.get(f"/api/documents/{doc_a_id}", headers=headers_a)
    assert res_a_after.status_code == 200
    assert res_a_after.json()["id"] == doc_a_id

    # 10. User B uploads a document
    doc_b_record = document_store.save_document(
        file_bytes=b"Sample Invoice for User B",
        filename="user_b_invoice.pdf",
        result_data={
            "doc_type": "invoice",
            "document_type": "Invoice",
            "status": "completed",
            "confidence": 0.95,
            "extracted_text": "Invoice #9876 Total $120.00",
            "fields": {"invoice_no": "9876", "total": "120.00"},
        },
        user_id=USER_B_ID,
    )
    doc_b_id = doc_b_record["id"]

    # 11. Verify User A stats vs User B stats
    stats_a = client.get("/api/stats", headers=headers_a).json()
    stats_b = client.get("/api/stats", headers=headers_b).json()

    assert stats_a["total"] == 1
    assert stats_b["total"] == 1

    # User A cannot delete User B's document
    res_del_a = client.delete(f"/api/documents/{doc_b_id}", headers=headers_a)
    assert res_del_a.status_code == 404
