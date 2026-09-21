"""
tests/test_retention_cleanup.py
Comprehensive test suite verifying Phase 6 Automatic Document Retention & Cleanup:
- Task 1: Configurable retention policy (default 30 days, 0 disables, invalid failsafe)
- Task 2: Background retention worker configuration & interval parsing
- Task 3: Safe deletion of expired encrypted originals, results, previews, and metadata
- Task 4: Startup cleanup & directory verification
- Task 5: Manual cleanup API (POST /api/documents/cleanup)
- Task 6: Document Vault synchronization (no broken references or ghost records)
- Task 7: Structured retention audit logging (document_expired, cleanup_completed, startup_cleanup)
"""

from datetime import datetime, timedelta, timezone
import io
import json
import logging
import os
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
import document_store
import logging_utils
import retention_service


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


def _make_dummy_image(text="TEST RETENTION"):
    img = Image.new("RGB", (300, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 20), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


# ==============================================================================
# Task 1: Configurable Retention Policy
# ==============================================================================

def test_task1_retention_policy_defaults_and_failsafe(monkeypatch):
    """Verify default 30 days, custom values, 0 disables, and invalid values fail-safe."""
    # 1. Default when unset
    monkeypatch.delenv("DOCUMENT_RETENTION_DAYS", raising=False)
    assert retention_service.get_retention_days() == 30
    assert retention_service.is_retention_enabled() is True

    # 2. Custom valid days
    monkeypatch.setenv("DOCUMENT_RETENTION_DAYS", "15")
    assert retention_service.get_retention_days() == 15
    assert retention_service.is_retention_enabled() is True

    # 3. 0 disables automatic deletion
    monkeypatch.setenv("DOCUMENT_RETENTION_DAYS", "0")
    assert retention_service.get_retention_days() == 0
    assert retention_service.is_retention_enabled() is False

    # 4. Invalid value fails safely to 30
    monkeypatch.setenv("DOCUMENT_RETENTION_DAYS", "invalid_number")
    assert retention_service.get_retention_days() == 30

    # 5. Negative number fails safely to 30
    monkeypatch.setenv("DOCUMENT_RETENTION_DAYS", "-10")
    assert retention_service.get_retention_days() == 30


def test_task1_cleanup_interval_parsing(monkeypatch):
    """Verify CLEANUP_INTERVAL_HOURS parsing and failsafe defaults."""
    monkeypatch.delenv("CLEANUP_INTERVAL_HOURS", raising=False)
    assert retention_service.get_cleanup_interval_hours() == 24.0

    monkeypatch.setenv("CLEANUP_INTERVAL_HOURS", "12.5")
    assert retention_service.get_cleanup_interval_hours() == 12.5

    monkeypatch.setenv("CLEANUP_INTERVAL_HOURS", "bad_float")
    assert retention_service.get_cleanup_interval_hours() == 24.0


# ==============================================================================
# Task 2 & 3: Safe Deletion of Expired Encrypted Files
# ==============================================================================

def test_task3_expired_document_files_deleted_and_recent_kept(client):
    """
    Verify:
    1. A document older than retention_days has its encrypted original,
       result JSON, preview thumbnail, and documents.json record deleted.
    2. A recent document is fully preserved.
    """
    png_bytes = _make_dummy_image("PAN CARD")

    # Upload two documents
    res1 = client.post("/api/mode/offline", files={"file": ("recent.png", png_bytes, "image/png")})
    assert res1.status_code == 200
    doc_recent_id = res1.json()["id"]

    res2 = client.post("/api/mode/offline", files={"file": ("expired.png", png_bytes, "image/png")})
    assert res2.status_code == 200
    doc_expired_id = res2.json()["id"]

    # Verify both exist on disk
    orig_recent = document_store.get_document_file_path(doc_recent_id)
    orig_expired = document_store.get_document_file_path(doc_expired_id)
    assert orig_recent and os.path.exists(orig_recent)
    assert orig_expired and os.path.exists(orig_expired)

    # Simulate doc2 being 35 days old by modifying its uploaded_at timestamp in documents.json
    past_date = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
    with document_store._lock:
        items = document_store._load_index()
        for it in items:
            if it.get("id") == doc_expired_id:
                it["uploaded_at"] = past_date
                it["created_at"] = past_date
        document_store._save_index(items)

    # Run cleanup with 30-day retention
    result = retention_service.run_cleanup(retention_days=30)
    assert result["success"] is True
    assert result["deleted_count"] >= 1
    assert doc_expired_id in [r.get("document_id") for r in logging_utils.get_captured_logs() if r.get("event") == "document_expired"]

    # Verify expired document is GONE from disk and documents.json
    assert not os.path.exists(orig_expired)
    assert document_store.get_document(doc_expired_id) is None
    assert document_store.get_document_file_path(doc_expired_id) is None

    # Verify preview thumbnail is also gone
    preview_expired = os.path.join(document_store.PROCESSED_DIR, f"{doc_expired_id}_thumb.png")
    assert not os.path.exists(preview_expired)

    # Verify recent document is STILL ACCESSIBLE
    assert os.path.exists(orig_recent)
    assert document_store.get_document(doc_recent_id) is not None


def test_task3_retention_disabled_does_not_delete(client, monkeypatch):
    """Verify that when retention is 0, expired documents are NOT removed."""
    monkeypatch.setenv("DOCUMENT_RETENTION_DAYS", "0")
    png_bytes = _make_dummy_image("DISABLED TEST")

    res = client.post("/api/mode/offline", files={"file": ("old_doc.png", png_bytes, "image/png")})
    assert res.status_code == 200
    doc_id = res.json()["id"]

    # Backdate to 100 days ago
    past_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    with document_store._lock:
        items = document_store._load_index()
        for it in items:
            if it.get("id") == doc_id:
                it["uploaded_at"] = past_date
        document_store._save_index(items)

    result = retention_service.run_cleanup()
    assert result["deleted_count"] == 0
    # Document still exists
    assert document_store.get_document(doc_id) is not None


# ==============================================================================
# Task 3: Orphan & Broken Reference Cleanup
# ==============================================================================

def test_task3_orphan_file_cleanup():
    """Verify unreferenced files on disk in original, results, and processed are removed."""
    fake_orphan_id = "orphan-dead-beef-9999"
    orphan_orig = os.path.join(document_store.ORIGINAL_DIR, f"{fake_orphan_id}.pdf.enc")
    orphan_res = os.path.join(document_store.RESULTS_DIR, f"{fake_orphan_id}.json.enc")
    orphan_thumb = os.path.join(document_store.PROCESSED_DIR, f"{fake_orphan_id}_thumb.png")

    with open(orphan_orig, "wb") as f:
        f.write(b"ENC1fakepayload")
    with open(orphan_res, "wb") as f:
        f.write(b"ENC1fakeresult")
    with open(orphan_thumb, "wb") as f:
        f.write(b"\x89PNGfake")

    assert os.path.exists(orphan_orig)
    assert os.path.exists(orphan_res)
    assert os.path.exists(orphan_thumb)

    result = retention_service.run_cleanup(purge_orphans=True)
    assert result["orphans_cleaned"] >= 3
    assert not os.path.exists(orphan_orig)
    assert not os.path.exists(orphan_res)
    assert not os.path.exists(orphan_thumb)


def test_task3_broken_reference_cleanup():
    """Verify metadata entries pointing to non-existent files are safely pruned."""
    broken_id = "ghost-doc-uuid-0000"
    broken_entry = {
        "id": broken_id,
        "document_id": broken_id,
        "filename": "missing.pdf",
        "file_path": os.path.join(document_store.ORIGINAL_DIR, f"{broken_id}.pdf.enc"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    with document_store._lock:
        items = document_store._load_index()
        items.insert(0, broken_entry)
        document_store._save_index(items)

    # Confirm ghost entry is present
    assert any(it.get("id") == broken_id for it in document_store._load_index())

    result = retention_service.run_cleanup(purge_broken_refs=True)
    assert result["broken_refs_count"] >= 1
    # Ghost entry removed
    assert not any(it.get("id") == broken_id for it in document_store._load_index())


# ==============================================================================
# Task 4: Startup Cleanup
# ==============================================================================

def test_task4_startup_cleanup_creates_dirs_and_logs():
    """Verify run_startup_cleanup logs startup_cleanup event and ensures directories exist."""
    deleted_count = retention_service.run_startup_cleanup()
    assert isinstance(deleted_count, int)

    # Check directories exist
    assert os.path.exists(document_store.ORIGINAL_DIR)
    assert os.path.exists(document_store.PROCESSED_DIR)
    assert os.path.exists(document_store.RESULTS_DIR)

    # Verify startup_cleanup log event
    captured = logging_utils.get_captured_logs()
    startup_logs = [r for r in captured if r.get("event") == "startup_cleanup"]
    assert len(startup_logs) >= 1
    assert "deleted" in startup_logs[0]


# ==============================================================================
# Task 5: Manual Cleanup API Endpoint
# ==============================================================================

def test_task5_manual_cleanup_api_endpoint(client):
    """Verify POST /api/documents/cleanup triggers cleanup and returns deleted_count."""
    png_bytes = _make_dummy_image("CLEANUP API")
    res = client.post("/api/mode/offline", files={"file": ("to_clean.png", png_bytes, "image/png")})
    assert res.status_code == 200
    doc_id = res.json()["id"]

    # Backdate to 40 days
    past_date = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    with document_store._lock:
        items = document_store._load_index()
        for it in items:
            if it.get("id") == doc_id:
                it["uploaded_at"] = past_date
        document_store._save_index(items)

    # Call POST /api/documents/cleanup
    res_cleanup = client.post("/api/documents/cleanup")
    assert res_cleanup.status_code == 200
    data = res_cleanup.json()
    assert data["success"] is True
    assert "deleted_count" in data
    assert data["deleted_count"] >= 1

    # Verify document no longer exists
    assert document_store.get_document(doc_id) is None


# ==============================================================================
# Task 6: Document Vault Synchronization
# ==============================================================================

def test_task6_vault_synchronization_no_broken_cards(client):
    """Verify GET /api/documents does not return expired or missing documents."""
    png_bytes = _make_dummy_image("VAULT SYNC")
    res = client.post("/api/mode/offline", files={"file": ("vault_doc.png", png_bytes, "image/png")})
    doc_id = res.json()["id"]

    # Expire and run cleanup
    past_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    with document_store._lock:
        items = document_store._load_index()
        for it in items:
            if it.get("id") == doc_id:
                it["uploaded_at"] = past_date
        document_store._save_index(items)

    client.post("/api/documents/cleanup")

    # Fetch document vault list
    list_res = client.get("/api/documents")
    assert list_res.status_code == 200
    vault_items = list_res.json().get("items", [])
    assert not any(d.get("id") == doc_id for d in vault_items)


# ==============================================================================
# Task 7: Retention Logs & No Document Content Leak
# ==============================================================================

def test_task7_retention_logs_no_document_content_leak(client):
    """Verify document_expired and cleanup_completed events are emitted without document text."""
    secret_text = "CONFIDENTIAL-PAYSLIP-SECRET-9988"
    png_bytes = _make_dummy_image(secret_text)
    res = client.post("/api/mode/offline", files={"file": ("secret.png", png_bytes, "image/png")})
    doc_id = res.json()["id"]

    # Expire it
    past_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    with document_store._lock:
        items = document_store._load_index()
        for it in items:
            if it.get("id") == doc_id:
                it["uploaded_at"] = past_date
        document_store._save_index(items)

    logging_utils.clear_log_capture()
    client.post("/api/documents/cleanup")

    records = logging_utils.get_captured_logs()
    expired_logs = [r for r in records if r.get("event") == "document_expired"]
    assert len(expired_logs) >= 1
    assert expired_logs[0]["document_id"] == doc_id
    assert "age_days" in expired_logs[0]
    assert expired_logs[0]["age_days"] >= 40

    cleanup_logs = [r for r in records if r.get("event") == "cleanup_completed"]
    assert len(cleanup_logs) >= 1
    assert cleanup_logs[0]["deleted_count"] >= 1

    # CRITICAL: Verify secret text NEVER appears in any retention log entry
    for r in records:
        log_str = json.dumps(r)
        assert secret_text not in log_str
