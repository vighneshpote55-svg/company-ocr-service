import pytest
from fastapi.testclient import TestClient
from main import app
from document_store import save_document, list_documents, get_documents, _load_index, _save_index, _lock
import os

@pytest.fixture(autouse=True)
def reset_app_security(monkeypatch):
    import main
    import supabase_client
    import retention_service
    main._startup_security_error = None
    monkeypatch.setattr(supabase_client, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(retention_service, "run_startup_cleanup", lambda: 0)
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("REGISTERED_CLIENTS_JSON", raising=False)
    monkeypatch.delenv("REGISTERED_CLIENTS_FILE", raising=False)
    yield
    main._startup_security_error = None

@pytest.fixture
def client(reset_app_security):
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture(autouse=True)
def setup_test_documents():
    """Seed test documents with diverse modes, doc_types, statuses, and confidence values."""
    dev_user_id = os.getenv("DEFAULT_DEV_USER_ID", "00000000-0000-0000-0000-000000000001")
    
    # Save original items
    with _lock:
        original_items = _load_index()
    
    test_docs = [
        # 1. Offline PAN card - verified - confidence 0.94
        {
            "id": "doc-test-1",
            "document_id": "doc-test-1",
            "user_id": dev_user_id,
            "filename": "pan_card_sample.pdf",
            "original_filename": "pan_card_sample.pdf",
            "doc_type": "pan",
            "document_type": "PAN Card",
            "mode": "offline",
            "status": "completed",
            "verification_status": "verified",
            "review_required": False,
            "risk_score": 5,
            "confidence": 0.9425,
            "extracted_text": "INCOME TAX DEPARTMENT GOVT OF INDIA ABCDE1234F",
            "ocr_required": True,
            "pages": 1,
        },
        # 2. Offline GST certificate - review required - confidence 0.81
        {
            "id": "doc-test-2",
            "document_id": "doc-test-2",
            "user_id": dev_user_id,
            "filename": "gst_registration_doc.pdf",
            "original_filename": "gst_registration_doc.pdf",
            "doc_type": "gst_certificate",
            "document_type": "GST Registration Certificate",
            "mode": "offline",
            "status": "warning",
            "verification_status": "review_required",
            "review_required": True,
            "risk_score": 45,
            "confidence": 0.812,
            "extracted_text": "GOODS AND SERVICES TAX REGISTRATION CERTIFICATE",
            "ocr_required": True,
            "pages": 2,
        },
        # 3. AI Mode invoice - verified - confidence 0.98
        {
            "id": "doc-test-3",
            "document_id": "doc-test-3",
            "user_id": dev_user_id,
            "filename": "commercial_invoice.pdf",
            "original_filename": "commercial_invoice.pdf",
            "doc_type": "ai_analyzed",
            "document_type": "Tax Invoice",
            "mode": "ai",
            "status": "completed",
            "verification_status": "verified",
            "review_required": False,
            "risk_score": 10,
            "confidence": 0.98,
            "extracted_text": "COMMERCIAL TAX INVOICE TOTAL AMOUNT 15000",
            "ai_analysis": {"model": "qwen2.5vl:3b", "summary": "Invoice"},
            "ocr_required": False,
            "pages": 1,
        },
        # 4. Unknown document - unsupported - confidence None
        {
            "id": "doc-test-4",
            "document_id": "doc-test-4",
            "user_id": dev_user_id,
            "filename": "random_receipt.png",
            "original_filename": "random_receipt.png",
            "doc_type": "unknown",
            "document_type": "Unknown Document",
            "mode": "offline",
            "status": "low_confidence",
            "verification_status": "unsupported",
            "review_required": False,
            "risk_score": 0,
            "confidence": None,
            "extracted_text": "some unclassified receipt content",
            "ocr_required": True,
            "pages": 1,
        },
        # 5. Failed document - failed - confidence 0.0
        {
            "id": "doc-test-5",
            "document_id": "doc-test-5",
            "user_id": dev_user_id,
            "filename": "corrupt_scan.pdf",
            "original_filename": "corrupt_scan.pdf",
            "doc_type": "unknown",
            "document_type": "Unknown Document",
            "mode": "offline",
            "status": "failed",
            "verification_status": "failed",
            "review_required": False,
            "risk_score": 100,
            "confidence": 0.0,
            "extracted_text": "",
            "ocr_required": True,
            "pages": 1,
        },
    ]

    with _lock:
        _save_index(test_docs)

    yield

    with _lock:
        _save_index(original_items)


def test_list_documents_returns_all_unfiltered(client):
    res = client.get("/api/documents")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5


def test_list_documents_filter_by_mode(client):
    # 1. Filter mode=offline (should return 4 docs: docs 1, 2, 4, 5)
    res_offline = client.get("/api/documents?mode=offline")
    assert res_offline.status_code == 200
    items_offline = res_offline.json()["items"]
    assert len(items_offline) == 4
    for doc in items_offline:
        assert doc["mode"] == "offline"

    # 2. Filter mode=ai (should return 1 doc: doc 3)
    res_ai = client.get("/api/documents?mode=ai")
    assert res_ai.status_code == 200
    items_ai = res_ai.json()["items"]
    assert len(items_ai) == 1
    assert items_ai[0]["id"] == "doc-test-3"


def test_list_documents_filter_by_doc_type(client):
    # Filter doc_type=pan
    res = client.get("/api/documents?doc_type=pan")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == "doc-test-1"

    # Filter doc_type=gst_certificate
    res_gst = client.get("/api/documents?doc_type=gst_certificate")
    assert res_gst.status_code == 200
    assert res_gst.json()["total"] == 1
    assert res_gst.json()["items"][0]["id"] == "doc-test-2"


def test_list_documents_filter_by_status(client):
    # 1. Verified (docs 1 and 3)
    res_verif = client.get("/api/documents?status=verified")
    assert res_verif.status_code == 200
    data_verif = res_verif.json()
    assert data_verif["total"] == 2
    ids_verif = {d["id"] for d in data_verif["items"]}
    assert ids_verif == {"doc-test-1", "doc-test-3"}

    # 2. Review Required (doc 2)
    res_rev = client.get("/api/documents?status=review_required")
    assert res_rev.status_code == 200
    data_rev = res_rev.json()
    assert data_rev["total"] == 1
    assert data_rev["items"][0]["id"] == "doc-test-2"

    # 3. Unsupported (doc 4)
    res_unsup = client.get("/api/documents?status=unsupported")
    assert res_unsup.status_code == 200
    data_unsup = res_unsup.json()
    assert data_unsup["total"] == 1
    assert data_unsup["items"][0]["id"] == "doc-test-4"

    # 4. Failed (doc 5)
    res_fail = client.get("/api/documents?status=failed")
    assert res_fail.status_code == 200
    data_fail = res_fail.json()
    assert data_fail["total"] == 1
    assert data_fail["items"][0]["id"] == "doc-test-5"


def test_list_documents_search_query(client):
    # Search by filename
    res_name = client.get("/api/documents?search=pan_card")
    assert res_name.status_code == 200
    assert res_name.json()["total"] == 1
    assert res_name.json()["items"][0]["id"] == "doc-test-1"

    # Search by extracted content text
    res_content = client.get("/api/documents?search=ABCDE1234F")
    assert res_content.status_code == 200
    assert res_content.json()["total"] == 1
    assert res_content.json()["items"][0]["id"] == "doc-test-1"

    # Search by document type title
    res_type = client.get("/api/documents?search=Registration")
    assert res_type.status_code == 200
    assert res_type.json()["total"] == 1
    assert res_type.json()["items"][0]["id"] == "doc-test-2"


def test_multi_filter_combination_working_together(client):
    # Combine mode=offline + status=verified
    res = client.get("/api/documents?mode=offline&status=verified")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == "doc-test-1"

    # Combine mode=offline + status=review_required + search=gst
    res2 = client.get("/api/documents?mode=offline&status=review_required&search=gst")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["total"] == 1
    assert data2["items"][0]["id"] == "doc-test-2"

    # Combine mode=ai + status=verified
    res3 = client.get("/api/documents?mode=ai&status=verified")
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["total"] == 1
    assert data3["items"][0]["id"] == "doc-test-3"

    # Non-matching combination
    res_empty = client.get("/api/documents?mode=ai&doc_type=pan")
    assert res_empty.status_code == 200
    assert res_empty.json()["total"] == 0
    assert len(res_empty.json()["items"]) == 0


def test_real_confidence_preserved_without_hardcoded_100(client):
    res = client.get("/api/documents")
    assert res.status_code == 200
    items = {d["id"]: d for d in res.json()["items"]}

    # Doc 1 has real float 0.9425
    assert items["doc-test-1"]["confidence"] == pytest.approx(0.9425)

    # Doc 2 has real float 0.812
    assert items["doc-test-2"]["confidence"] == pytest.approx(0.812)

    # Doc 3 has real float 0.98
    assert items["doc-test-3"]["confidence"] == pytest.approx(0.98)

    # Doc 4 has None (not 1.0!)
    assert items["doc-test-4"]["confidence"] is None

    # Doc 5 has 0.0 (failed)
    assert items["doc-test-5"]["confidence"] == 0.0


def test_pagination_and_counts(client):
    # Page 1, limit 2
    res_p1 = client.get("/api/documents?limit=2&offset=0")
    assert res_p1.status_code == 200
    d_p1 = res_p1.json()
    assert d_p1["total"] == 5
    assert len(d_p1["items"]) == 2

    # Page 2, limit 2
    res_p2 = client.get("/api/documents?limit=2&offset=2")
    assert res_p2.status_code == 200
    d_p2 = res_p2.json()
    assert d_p2["total"] == 5
    assert len(d_p2["items"]) == 2
    assert d_p2["items"][0]["id"] != d_p1["items"][0]["id"]
