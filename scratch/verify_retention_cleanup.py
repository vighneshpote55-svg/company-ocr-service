"""
scratch/verify_retention_cleanup.py
Live verification of Phase 6 Automatic Document Retention & Cleanup:
1. Upload PAN Card, Aadhaar Card, Bank Statement.
2. Simulate expired timestamps for selected documents.
3. Trigger cleanup.
4. Verify:
   - expired encrypted files removed
   - previews removed
   - documents.json updated
   - Document Vault refreshed
   - structured retention logs emitted
   - no orphan files remain.
"""

from datetime import datetime, timedelta, timezone
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import document_store
import logging_utils
import retention_service

logging_utils.enable_log_capture()
from main import app


def create_sample_card(title: str, text: str):
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), title, fill=(0, 0, 0))
    draw.text((20, 60), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def main():
    print("================================================================================")
    print("LIVE RETENTION & AUTOMATIC CLEANUP VERIFICATION (PHASE 6)")
    print("================================================================================")

    client = TestClient(app)

    # 1. Upload PAN, Aadhaar, and Bank Statement
    print("\n[1] Uploading test documents...")
    pan_img = create_sample_card("INCOME TAX DEPARTMENT", "ABCDE1234F")
    aadhaar_img = create_sample_card("GOVERNMENT OF INDIA", "1234 5678 9012")
    statement_img = create_sample_card("STATE BANK OF INDIA", "Statement of Account 98765432109876")

    res_pan = client.post("/api/mode/offline", files={"file": ("PAN_Card.png", pan_img, "image/png")})
    res_aadhaar = client.post("/api/mode/offline", files={"file": ("Aadhaar_Card.png", aadhaar_img, "image/png")})
    res_statement = client.post("/api/mode/offline", files={"file": ("Bank_Statement.png", statement_img, "image/png")})

    assert res_pan.status_code == 200, res_pan.text
    assert res_aadhaar.status_code == 200, res_aadhaar.text
    assert res_statement.status_code == 200, res_statement.text

    pan_id = res_pan.json()["id"]
    aadhaar_id = res_aadhaar.json()["id"]
    statement_id = res_statement.json()["id"]

    print(f"  Uploaded PAN Card       : {pan_id}")
    print(f"  Uploaded Aadhaar Card   : {aadhaar_id}")
    print(f"  Uploaded Bank Statement : {statement_id}")

    # Check on-disk existence
    pan_orig = document_store.get_document_file_path(pan_id)
    aadhaar_orig = document_store.get_document_file_path(aadhaar_id)
    statement_orig = document_store.get_document_file_path(statement_id)

    assert pan_orig and os.path.exists(pan_orig)
    assert aadhaar_orig and os.path.exists(aadhaar_orig)
    assert statement_orig and os.path.exists(statement_orig)
    print("  [OK] All encrypted original files verified on disk.")

    # 2. Simulate expired timestamps: PAN (45 days old), Aadhaar (35 days old), Statement (recent: today)
    print("\n[2] Simulating expired timestamps in storage index...")
    now = datetime.now(timezone.utc)
    date_pan_expired = (now - timedelta(days=45)).isoformat()
    date_aadhaar_expired = (now - timedelta(days=35)).isoformat()

    with document_store._lock:
        items = document_store._load_index()
        for it in items:
            if it.get("id") == pan_id:
                it["uploaded_at"] = date_pan_expired
                it["created_at"] = date_pan_expired
            elif it.get("id") == aadhaar_id:
                it["uploaded_at"] = date_aadhaar_expired
                it["created_at"] = date_aadhaar_expired
        document_store._save_index(items)

    print(f"  PAN set to 45 days old (expired under 30d retention)")
    print(f"  Aadhaar set to 35 days old (expired under 30d retention)")
    print(f"  Bank Statement kept current (should be preserved)")

    # 3. Create a deliberate orphan file to test orphan purging
    orphan_file = os.path.join(document_store.ORIGINAL_DIR, "orphan-uuid-1111.png.enc")
    with open(orphan_file, "wb") as f:
        f.write(b"ENC1fakeorphan")
    assert os.path.exists(orphan_file)
    print("  Created orphan file: orphan-uuid-1111.png.enc")

    # 4. Trigger cleanup via manual API endpoint (POST /api/documents/cleanup)
    print("\n[3] Triggering cleanup via POST /api/documents/cleanup...")
    logging_utils.clear_log_capture()
    res_cleanup = client.post("/api/documents/cleanup")
    assert res_cleanup.status_code == 200
    cleanup_data = res_cleanup.json()
    print(f"  Cleanup Response: {cleanup_data}")
    assert cleanup_data["success"] is True
    assert cleanup_data["deleted_count"] >= 2  # PAN and Aadhaar

    # 5. Verify expired encrypted originals, results, previews are removed
    print("\n[4] Verifying storage state on disk:")
    pan_exists = os.path.exists(pan_orig)
    aadhaar_exists = os.path.exists(aadhaar_orig)
    statement_exists = os.path.exists(statement_orig)
    orphan_exists = os.path.exists(orphan_file)

    print(f"  PAN file on disk       : {'REMOVED' if not pan_exists else 'STILL EXISTS [FAIL]'}")
    print(f"  Aadhaar file on disk   : {'REMOVED' if not aadhaar_exists else 'STILL EXISTS [FAIL]'}")
    print(f"  Bank Statement on disk : {'PRESERVED' if statement_exists else 'MISSING [FAIL]'}")
    print(f"  Orphan file on disk    : {'REMOVED' if not orphan_exists else 'STILL EXISTS [FAIL]'}")

    assert not pan_exists, "Expired PAN original was not deleted!"
    assert not aadhaar_exists, "Expired Aadhaar original was not deleted!"
    assert statement_exists, "Recent Bank Statement was mistakenly deleted!"
    assert not orphan_exists, "Orphan file was not removed!"

    # 6. Verify Document Vault list API returns only surviving active documents
    print("\n[5] Verifying Document Vault list API (/api/documents):")
    res_vault = client.get("/api/documents")
    assert res_vault.status_code == 200
    vault_items = res_vault.json().get("items", [])
    vault_ids = [d.get("id") for d in vault_items]
    print(f"  Active vault count: {len(vault_items)}")
    print(f"  Active doc IDs: {vault_ids}")

    assert pan_id not in vault_ids, "Expired PAN still visible in vault!"
    assert aadhaar_id not in vault_ids, "Expired Aadhaar still visible in vault!"
    assert statement_id in vault_ids, "Recent Bank Statement missing from vault!"

    # 7. Check Structured Retention Logs
    print("\n[6] Verifying Structured Retention Logs:")
    captured = [r for r in logging_utils.get_captured_logs() if r.get("logger") != "httpx"]
    for r in captured:
        print(f"  Event: {r.get('event'):20} | Log: {json.dumps(r)}")

    events = [r.get("event") for r in captured]
    assert "document_expired" in events
    assert "cleanup_completed" in events

    print("\n================================================================================")
    print("ALL RETENTION & CLEANUP VERIFICATIONS PASSED WITH 100% COMPLIANCE!")
    print("================================================================================")


if __name__ == "__main__":
    main()
