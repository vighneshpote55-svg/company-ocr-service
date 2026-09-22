"""
migrate_json_to_supabase.py
Migration tool to migrate legacy documents from documents.json to Supabase:
- Requires explicit MIGRATION_DEFAULT_USER_ID to assign document ownership
- Idempotent: checks if document ID already exists in Supabase
- Migrates files to private Supabase Storage at documents/<user_id>/<doc_id>/...
- Migrates metadata, OCR results, extracted fields, and AI analyses
- Preserves local files safely without automatic deletion
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
import encryption
from encryption import is_encrypted_payload
from supabase_client import (
    get_supabase_client,
    is_supabase_configured,
    upload_encrypted_file,
    SUPABASE_STORAGE_BUCKET,
)
import document_store


def run_migration(default_user_id: str):
    print("================================================================")
    print("Starting Legacy documents.json -> Supabase Migration")
    print("================================================================")

    if not default_user_id or not default_user_id.strip():
        print("ERROR: MIGRATION_DEFAULT_USER_ID is required.", file=sys.stderr)
        print("Per security rules, ownership cannot be invented automatically.", file=sys.stderr)
        sys.exit(1)

    default_user_id = default_user_id.strip()
    print(f"Target Migration User UUID: {default_user_id}")

    if not is_supabase_configured():
        print("ERROR: Supabase is not configured. SUPABASE_URL and SUPABASE_SECRET_KEY required.", file=sys.stderr)
        sys.exit(1)

    client = get_supabase_client()
    if not client:
        print("ERROR: Failed to initialize Supabase client.", file=sys.stderr)
        sys.exit(1)

    # 1. Verify user exists in public.profiles or auth.users
    try:
        prof_res = client.table("profiles").select("id, email").eq("id", default_user_id).execute()
        if not prof_res.data:
            print(f"WARNING: User UUID {default_user_id} not found in public.profiles table.")
            print("Please ensure the user has signed up or exists in auth.users.")
        else:
            print(f"Verified target user: {prof_res.data[0].get('email')} ({default_user_id})")
    except Exception as ex:
        print(f"Profile check warning: {ex}")

    # 2. Read legacy documents.json
    index_file = document_store.INDEX_FILE
    if not os.path.exists(index_file):
        print(f"No legacy index file found at {index_file}. Nothing to migrate.")
        return

    try:
        with open(index_file, "r", encoding="utf-8") as f:
            legacy_docs = json.load(f)
    except Exception as ex:
        print(f"ERROR: Failed to read {index_file}: {ex}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(legacy_docs, list):
        print(f"ERROR: Expected list of documents in {index_file}.", file=sys.stderr)
        sys.exit(1)

    total_legacy = len(legacy_docs)
    print(f"Found {total_legacy} legacy document records in documents.json")

    migrated_count = 0
    skipped_count = 0
    error_count = 0

    for doc in legacy_docs:
        doc_id = doc.get("id") or doc.get("document_id")
        if not doc_id:
            continue

        # Check idempotency
        try:
            exists = client.table("documents").select("id").eq("id", doc_id).execute()
            if exists.data and len(exists.data) > 0:
                print(f"[-] Document {doc_id} already exists in Supabase. Skipping.")
                skipped_count += 1
                continue
        except Exception as ex:
            print(f"[!] Check failed for {doc_id}: {ex}")

        # Locate document file
        local_path = document_store.get_document_file_path(doc_id)
        file_bytes = b""
        if local_path and os.path.exists(local_path):
            with open(local_path, "rb") as f:
                raw_bytes = f.read()
            if is_encrypted_payload(raw_bytes):
                file_bytes = encryption.decrypt_data(raw_bytes)
            else:
                file_bytes = raw_bytes

        # Encrypt file for Supabase storage
        storage_path = f"documents/{default_user_id}/{doc_id}/{doc_id}.enc"
        if file_bytes:
            enc_bytes = encryption.encrypt_data(file_bytes)
            try:
                upload_encrypted_file(storage_path, enc_bytes)
            except Exception as ex:
                print(f"[!] Storage upload failed for {doc_id}: {ex}")

        # Insert metadata
        now_iso = datetime.now(timezone.utc).isoformat()
        orig_filename = doc.get("original_filename") or doc.get("filename") or f"{doc_id}.bin"
        file_type = doc.get("file_type") or "application/octet-stream"

        try:
            client.table("documents").insert({
                "id": doc_id,
                "user_id": default_user_id,
                "original_filename": orig_filename,
                "file_type": file_type,
                "storage_path": storage_path,
                "doc_type": doc.get("doc_type", "unknown"),
                "mode": doc.get("mode", "offline"),
                "status": doc.get("status", "processed"),
                "file_size": doc.get("file_size", len(file_bytes)),
                "checksum_sha256": doc.get("checksum"),
                "created_at": doc.get("created_at", now_iso),
                "updated_at": doc.get("updated_at", now_iso),
            }).execute()

            if file_bytes:
                client.table("document_files").insert({
                    "document_id": doc_id,
                    "user_id": default_user_id,
                    "bucket_name": SUPABASE_STORAGE_BUCKET,
                    "storage_path": storage_path,
                    "encryption_algorithm": "AES-256-GCM",
                    "file_size": len(enc_bytes),
                    "created_at": now_iso,
                }).execute()

            if doc.get("ocr_result"):
                ocr = doc["ocr_result"]
                client.table("ocr_results").insert({
                    "document_id": doc_id,
                    "user_id": default_user_id,
                    "raw_text": ocr.get("text") or ocr.get("raw_text", ""),
                    "detected_type": ocr.get("detected_type") or doc.get("doc_type"),
                    "confidence": ocr.get("confidence", 0.0),
                    "page_count": ocr.get("pages_processed", 1),
                    "raw_results": ocr,
                    "created_at": now_iso,
                }).execute()

            if doc.get("extracted_fields"):
                client.table("extracted_fields").insert({
                    "document_id": doc_id,
                    "user_id": default_user_id,
                    "fields": doc["extracted_fields"],
                    "verification_status": doc.get("status", "processed"),
                    "created_at": now_iso,
                }).execute()

            if doc.get("ai_analysis"):
                ai = doc["ai_analysis"]
                client.table("ai_analyses").insert({
                    "document_id": doc_id,
                    "user_id": default_user_id,
                    "provider": ai.get("provider", "unknown"),
                    "model": ai.get("model", "unknown"),
                    "summary": ai.get("summary", ""),
                    "classification": ai.get("classification") or doc.get("doc_type"),
                    "raw_analysis": ai,
                    "created_at": now_iso,
                }).execute()

            print(f"[+] Migrated {doc_id} ({orig_filename}) successfully.")
            migrated_count += 1
        except Exception as ex:
            print(f"[x] Error migrating {doc_id}: {ex}")
            error_count += 1

    print("================================================================")
    print(f"Migration Summary: Total: {total_legacy}, Migrated: {migrated_count}, Skipped: {skipped_count}, Errors: {error_count}")
    print("Legacy files in Docker volume preserved without deletion.")
    print("================================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate legacy documents.json to Supabase")
    parser.add_argument("--user-id", help="Default user UUID to assign legacy document ownership", default=os.getenv("MIGRATION_DEFAULT_USER_ID"))
    args = parser.parse_args()

    run_migration(args.user_id)
