"""
document_store.py
Document storage abstraction for Document OCR Web Application:
- Local storage directories: uploads/original/, uploads/processed/, uploads/results/
- Thread-safe metadata index in uploads/documents.json
- AES-256-GCM encrypted document storage and result storage
- Transparent decryption and secure temporary file management
- Querying, filtering, statistics, and retrieval
- Designed for easy future transition to S3 / Supabase / GCS
"""

import json
import logging
import os
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

import encryption
from encryption import (
    DocumentDecryptionError,
    DocumentEncryptionError,
    DocumentEncryptionKeyMissingError,
    is_encrypted_payload,
)
import logging_utils

logger = logging_utils.get_logger("company_server_ocr.document_store")

STORAGE_ROOT = os.getenv("DOCUMENT_STORAGE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
ORIGINAL_DIR = os.path.join(STORAGE_ROOT, "original")
PROCESSED_DIR = os.path.join(STORAGE_ROOT, "processed")
RESULTS_DIR = os.path.join(STORAGE_ROOT, "results")
INDEX_FILE = os.path.join(STORAGE_ROOT, "documents.json")
TEMP_DIR = os.getenv("DOCUMENT_TEMP_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp"))


def check_storage_health() -> Dict[str, Any]:
    """Verify writeability and existence of all document storage directories."""
    dirs_to_check = [STORAGE_ROOT, ORIGINAL_DIR, PROCESSED_DIR, RESULTS_DIR]
    healthy = True
    details = {}
    for d in dirs_to_check:
        try:
            os.makedirs(d, exist_ok=True)
            test_file = os.path.join(d, f".health_check_{uuid.uuid4().hex[:8]}")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            details[os.path.basename(d) or "root"] = "writable"
        except Exception as ex:
            healthy = False
            details[os.path.basename(d) or "root"] = f"error: {str(ex)}"
    return {
        "status": "healthy" if healthy else "degraded",
        "healthy": healthy,
        "details": details,
        "storage_root": STORAGE_ROOT,
    }


_lock = threading.Lock()
_active_document_id: Optional[str] = None


def set_active_document(doc_id: str):
    """Set the active document for the current session."""
    global _active_document_id
    with _lock:
        _active_document_id = doc_id


def get_active_document_id() -> Optional[str]:
    """Retrieve the active document ID for the current session."""
    with _lock:
        return _active_document_id


def get_active_document() -> Optional[Dict[str, Any]]:
    """Retrieve full details of the currently active document."""
    with _lock:
        doc_id = _active_document_id
    if doc_id:
        return get_document(doc_id)
    return None


def clear_active_document():
    """Clear the active document from the current session."""
    global _active_document_id
    with _lock:
        _active_document_id = None


def get_canonical_analysis(doc_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve one canonical analysis object for the given document_id (or active session document):
    {
      "document_id": "...",
      "document_type": "...",
      "confidence": "...",
      "ocr_text": "...",
      "summary": "...",
      "evidence": [],
      "extracted_fields": {}
    }
    This serves as the single source of truth for AI grounding and chat.
    """
    target_id = doc_id or get_active_document_id()
    if not target_id:
        return None
    doc = get_document(target_id)
    if not doc:
        return None
    if isinstance(doc.get("canonical_analysis"), dict):
        return doc["canonical_analysis"]

    canonical_fields = {}
    if isinstance(doc.get("fields"), dict):
        canonical_fields.update(doc["fields"])
    if isinstance(doc.get("extracted_fields"), dict):
        canonical_fields.update(doc["extracted_fields"])
    if isinstance((doc.get("ai_analysis") or {}).get("extracted_fields"), dict):
        canonical_fields.update(doc["ai_analysis"]["extracted_fields"])

    conf = doc.get("confidence", "high")
    if isinstance(conf, (int, float)):
        conf = "high" if conf >= 0.85 else ("medium" if conf >= 0.60 else "low")

    return {
        "document_id": doc.get("id") or target_id,
        "document_type": doc.get("document_type") or doc.get("doc_type", "Unknown Document"),
        "confidence": conf,
        "ocr_text": doc.get("extracted_text") or "",
        "summary": doc.get("summary") or (doc.get("ai_analysis") or {}).get("summary") or "",
        "evidence": doc.get("evidence") or (doc.get("ai_analysis") or {}).get("evidence") or [],
        "extracted_fields": canonical_fields,
    }


def init_storage():
    """Ensure all required storage directories and index file exist."""
    os.makedirs(ORIGINAL_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    if not os.path.exists(INDEX_FILE):
        with _lock:
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
    # Migrate any existing unencrypted files if encryption key is configured
    try:
        migrate_unencrypted_documents()
    except Exception as ex:
        logger.warning("Automatic document migration skipped: %s", ex)


def _load_index() -> List[Dict[str, Any]]:
    """Load metadata list from documents.json."""
    if not os.path.exists(INDEX_FILE):
        return []
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_index(items: List[Dict[str, Any]]):
    """Save metadata list to documents.json."""
    tmp_path = INDEX_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp_path, INDEX_FILE)


def sanitize_filename(filename: str) -> str:
    """Strip dangerous path characters and path traversal sequences from filename."""
    base = os.path.basename(filename.replace("\\", "/"))
    base = base.lstrip(".")
    return "".join(c for c in base if c.isalnum() or c in "._- ") or "document.bin"


def save_document(
    file_bytes: bytes,
    filename: str,
    result_data: Dict[str, Any],
    thumbnail_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    Persist an uploaded document:
    - Encrypt original file with AES-256-GCM immediately and save as uploads/original/<doc_id>.<ext>.enc
    - Save thumbnail unencrypted in uploads/processed/
    - Encrypt result JSON and save as uploads/results/<doc_id>.json.enc
    - Update documents.json index
    """
    doc_id = str(uuid.uuid4())
    clean_name = sanitize_filename(filename)
    ext = os.path.splitext(clean_name)[1].lower() or ".bin"
    # Never use original filename on disk: randomize with UUID v4 and .enc extension
    stored_filename = f"{doc_id}{ext}.enc"
    original_file_path = os.path.join(ORIGINAL_DIR, stored_filename)

    # 1. Encrypt and write original file immediately
    encrypted_file_bytes = encryption.encrypt_bytes(file_bytes)
    with open(original_file_path, "wb") as f:
        f.write(encrypted_file_bytes)

    # 2. Write thumbnail if provided (unencrypted preview)
    preview_filename = None
    if thumbnail_bytes:
        preview_filename = f"{doc_id}_thumb.png"
        preview_file_path = os.path.join(PROCESSED_DIR, preview_filename)
        with open(preview_file_path, "wb") as f:
            f.write(thumbnail_bytes)

    # 3. Format full document record
    doc_type = result_data.get("doc_type") or result_data.get("document_type") or "unknown"
    doc_type_clean = doc_type.lower().strip()
    status = result_data.get("status", "completed")
    if status in ("error", "failed"):
        human_doc_type = "OCR Error" if status == "error" else "Processing Failed"
    elif result_data.get("document_type"):
        human_doc_type = result_data["document_type"]
    else:
        human_doc_type = doc_type_clean.replace("_", " ").title() if doc_type_clean != "unknown" else "Unknown Document"

    now_iso = datetime.now(timezone.utc).isoformat()

    doc_record = {
        "id": doc_id,
        "document_id": doc_id,
        "filename": clean_name,
        "original_filename": clean_name,
        "stored_filename": stored_filename,
        "file_path": original_file_path,
        "file_size": len(file_bytes),
        "file_type": ext,
        "is_encrypted": True,
        "uploaded_at": now_iso,
        "doc_type": doc_type_clean,
        "document_type": human_doc_type,
        "issuer": result_data.get("issuer"),
        "ocr_required": result_data.get("ocr_required", True),
        "text_source": result_data.get("text_source", "paddle_ocr"),
        "status": result_data.get("status", "completed"),
        "confidence": result_data.get("confidence", 1.0),
        "pages": result_data.get("pages", 1),
        "reason": result_data.get("reason"),
        "checksum_valid": result_data.get("checksum_valid", False if result_data.get("status") == "warning" else True),
        "checksum_reason": result_data.get("checksum_reason", result_data.get("reason")),
        "cross_check": result_data.get("cross_check"),
        "extracted_fields": result_data.get("extracted_fields", {}),
        "fields": result_data.get("extracted_fields", result_data.get("fields", {})),
        "field_confidences": result_data.get("field_confidences", {}),
        "extracted_text": result_data.get("extracted_text", ""),
        "has_preview": preview_filename is not None,
        "preview_url": f"/api/documents/{doc_id}/preview" if preview_filename else None,
        "file_url": f"/api/documents/{doc_id}/file",
        "created_at": now_iso,
        "ai_analysis": {
            **(result_data.get("ai_analysis") or {}),
            "document_id": doc_id,
        } if result_data.get("ai_analysis") else None,
        "summary": result_data.get("summary") or (result_data.get("ai_analysis") or {}).get("summary"),
        "evidence": result_data.get("evidence") or (result_data.get("ai_analysis") or {}).get("evidence"),
        "canonical_analysis": {
            "document_id": doc_id,
            "document_type": result_data.get("document_type") or result_data.get("doc_type", "Unknown Document"),
            "confidence": "high" if (result_data.get("confidence") in ("high", 1.0) or (isinstance(result_data.get("confidence"), (int, float)) and result_data.get("confidence") >= 0.85)) else ("medium" if (result_data.get("confidence") == "medium" or (isinstance(result_data.get("confidence"), (int, float)) and result_data.get("confidence") >= 0.60)) else "low"),
            "ocr_text": result_data.get("extracted_text") or "",
            "summary": result_data.get("summary") or (result_data.get("ai_analysis") or {}).get("summary") or "",
            "evidence": result_data.get("evidence") or (result_data.get("ai_analysis") or {}).get("evidence") or [],
            "extracted_fields": {
                **(result_data.get("fields") if isinstance(result_data.get("fields"), dict) else {}),
                **(result_data.get("extracted_fields") if isinstance(result_data.get("extracted_fields"), dict) else {}),
                **((result_data.get("ai_analysis") or {}).get("extracted_fields") if isinstance((result_data.get("ai_analysis") or {}).get("extracted_fields"), dict) else {}),
            },
        },
    }

    # 4. Save encrypted result JSON
    result_enc_path = os.path.join(RESULTS_DIR, f"{doc_id}.json.enc")
    json_bytes = json.dumps(doc_record, indent=2).encode("utf-8")
    enc_json_bytes = encryption.encrypt_bytes(json_bytes)
    with open(result_enc_path, "wb") as f:
        f.write(enc_json_bytes)

    # If an old unencrypted JSON exists, remove it
    legacy_result_path = os.path.join(RESULTS_DIR, f"{doc_id}.json")
    if os.path.exists(legacy_result_path):
        try:
            os.remove(legacy_result_path)
        except Exception:
            pass

    # 5. Update index
    with _lock:
        items = _load_index()
        # Keep recent items at front
        items.insert(0, doc_record)
        _save_index(items)

    # 6. Mark as active document for current session
    set_active_document(doc_id)

    logging_utils.log_event(
        logger,
        logging.INFO,
        event="document_persisted",
        message=f"Document {doc_id} persisted securely",
        document_id=doc_id,
        file_size=len(file_bytes),
        encrypted=True,
        status="success",
    )

    return doc_record


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full document details by ID from encrypted results or legacy fallback."""
    # 1. Check encrypted result file
    result_enc_path = os.path.join(RESULTS_DIR, f"{doc_id}.json.enc")
    if os.path.exists(result_enc_path):
        try:
            with open(result_enc_path, "rb") as f:
                enc_data = f.read()
            dec_bytes = encryption.decrypt_bytes(enc_data)
            return json.loads(dec_bytes.decode("utf-8"))
        except Exception as ex:
            logger.error("Failed to decrypt result file %s: %s", result_enc_path, ex)

    # 2. Check legacy unencrypted result file
    result_path = os.path.join(RESULTS_DIR, f"{doc_id}.json")
    if os.path.exists(result_path):
        try:
            with open(result_path, "rb") as f:
                raw_data = f.read()
            if is_encrypted_payload(raw_data):
                dec_bytes = encryption.decrypt_bytes(raw_data)
                return json.loads(dec_bytes.decode("utf-8"))
            return json.loads(raw_data.decode("utf-8"))
        except Exception as ex:
            logger.warning("Failed to parse legacy result file %s: %s", result_path, ex)

    # 3. Fallback to index
    items = _load_index()
    for item in items:
        if item.get("id") == doc_id or item.get("document_id") == doc_id:
            return item

    return None


def get_document_file_path(doc_id: str) -> Optional[str]:
    """Return local path to the stored document file on disk (encrypted or legacy)."""
    doc = get_document(doc_id)
    if doc and doc.get("file_path") and os.path.exists(doc["file_path"]):
        return doc["file_path"]

    # Search in ORIGINAL_DIR for files starting with doc_id
    if os.path.isdir(ORIGINAL_DIR):
        for fname in os.listdir(ORIGINAL_DIR):
            if fname.startswith(doc_id):
                cand = os.path.join(ORIGINAL_DIR, fname)
                if os.path.isfile(cand):
                    return cand

    return None


def get_document_bytes(doc_id: str) -> bytes:
    """
    Read and return transparently decrypted document bytes.
    Handles both encrypted (.enc) and legacy unencrypted files.
    """
    file_path = get_document_file_path(doc_id)
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError(f"Document file for '{doc_id}' not found.")

    with open(file_path, "rb") as f:
        data = f.read()

    if file_path.endswith(".enc") or is_encrypted_payload(data):
        return encryption.decrypt_bytes(data)

    return data


@contextmanager
def temporary_decrypted_document(doc_id: str) -> Generator[str, None, None]:
    """
    Safely decrypts an encrypted document to a temporary file in TEMP_DIR for OCR/AI processing.
    Guarantees cleanup in a finally block so no plaintext remains on disk.
    """
    doc = get_document(doc_id)
    ext = (doc.get("file_type") if doc else None) or ".bin"
    temp_plaintext_path = os.path.join(TEMP_DIR, f"temp_dec_{uuid.uuid4()}{ext}")
    decrypted_bytes = get_document_bytes(doc_id)

    try:
        with open(temp_plaintext_path, "wb") as f:
            f.write(decrypted_bytes)
        yield temp_plaintext_path
    finally:
        if os.path.exists(temp_plaintext_path):
            try:
                os.remove(temp_plaintext_path)
            except Exception as ex:
                logger.warning("Failed to remove temporary plaintext file %s: %s", temp_plaintext_path, ex)


def is_document_encrypted(doc_id: str) -> bool:
    """Check if the document stored on disk is encrypted."""
    file_path = get_document_file_path(doc_id)
    if not file_path or not os.path.exists(file_path):
        return False
    if file_path.endswith(".enc"):
        return True
    try:
        with open(file_path, "rb") as f:
            header = f.read(32)
        return is_encrypted_payload(header)
    except Exception:
        return False


def list_documents(
    status_filter: Optional[str] = None,
    ocr_required_filter: Optional[bool] = None,
    doc_type_filter: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Query stored documents with filters."""
    items = _load_index()

    filtered = []
    for item in items:
        if status_filter and status_filter.lower() != "all":
            if item.get("status", "").lower() != status_filter.lower():
                continue
        if ocr_required_filter is not None:
            if item.get("ocr_required") != ocr_required_filter:
                continue
        if doc_type_filter and doc_type_filter.lower() != "all":
            if item.get("doc_type", "").lower() != doc_type_filter.lower():
                continue
        if search:
            query = search.lower()
            name_match = query in item.get("filename", "").lower()
            type_match = query in item.get("document_type", "").lower()
            text_match = query in item.get("extracted_text", "").lower()
            if not (name_match or type_match or text_match):
                continue
        filtered.append(item)

    return filtered[offset : offset + limit]


def delete_document(doc_id: str) -> bool:
    """Delete a document, its encrypted files, thumbnails, results, and index entry."""
    with _lock:
        items = _load_index()
        target = next((item for item in items if item.get("id") == doc_id or item.get("document_id") == doc_id), None)

        # 1. Remove original files matching doc_id
        if os.path.isdir(ORIGINAL_DIR):
            for fname in os.listdir(ORIGINAL_DIR):
                if fname.startswith(doc_id):
                    try:
                        os.remove(os.path.join(ORIGINAL_DIR, fname))
                    except Exception:
                        pass

        # 2. Remove preview thumbnail
        preview_file = os.path.join(PROCESSED_DIR, f"{doc_id}_thumb.png")
        if os.path.exists(preview_file):
            try:
                os.remove(preview_file)
            except Exception:
                pass

        # 3. Remove result files (.json and .json.enc)
        for res_name in (f"{doc_id}.json.enc", f"{doc_id}.json"):
            res_path = os.path.join(RESULTS_DIR, res_name)
            if os.path.exists(res_path):
                try:
                    os.remove(res_path)
                except Exception:
                    pass

        if not target:
            return False

        # Update index
        updated = [item for item in items if item.get("id") != doc_id and item.get("document_id") != doc_id]
        _save_index(updated)
        return True


def clear_all_documents() -> int:
    """
    Permanently delete all document records and their associated files:
    - original uploads in ORIGINAL_DIR
    - thumbnails and previews in PROCESSED_DIR
    - result files in RESULTS_DIR
    - resets documents.json to an empty list
    Returns the count of deleted documents.
    """
    with _lock:
        items = _load_index()
        count = len(items)

        # 1. Clean files in upload directories
        for folder in (ORIGINAL_DIR, PROCESSED_DIR, RESULTS_DIR):
            if os.path.isdir(folder):
                for fname in os.listdir(folder):
                    fpath = os.path.join(folder, fname)
                    if os.path.isfile(fpath):
                        try:
                            os.remove(fpath)
                        except Exception:
                            pass

        # 2. Reset document index
        _save_index([])
        return count


def get_document_preview_path(doc_id: str) -> Optional[str]:
    """Return local path to the rendered thumbnail."""
    preview_path = os.path.join(PROCESSED_DIR, f"{doc_id}_thumb.png")
    if os.path.exists(preview_path):
        return preview_path
    return None


def get_stats() -> Dict[str, int]:
    """Compute dashboard statistics."""
    items = _load_index()
    total = len(items)
    ocr_processed = sum(1 for d in items if d.get("ocr_required") is True)
    ocr_not_required = sum(1 for d in items if d.get("ocr_required") is False)
    failed = sum(1 for d in items if d.get("status") in ("error", "failed"))
    completed = sum(1 for d in items if d.get("status") in ("success", "completed", "low_confidence", "warning"))

    return {
        "total": total,
        "ocr_processed": ocr_processed,
        "ocr_not_required": ocr_not_required,
        "completed": completed,
        "failed": failed,
    }


def migrate_unencrypted_documents() -> int:
    """
    Scan uploads/original and uploads/results to migrate any legacy unencrypted documents:
    - Encrypts unencrypted originals to .enc and deletes plaintext originals
    - Encrypts unencrypted JSON results to .json.enc and deletes plaintext JSON
    - Updates documents.json entries
    Returns number of migrated original documents.
    """
    migrated_count = 0
    with _lock:
        # 1. Migrate original files
        if os.path.isdir(ORIGINAL_DIR):
            for fname in os.listdir(ORIGINAL_DIR):
                if not fname.endswith(".enc"):
                    plain_path = os.path.join(ORIGINAL_DIR, fname)
                    if os.path.isfile(plain_path):
                        try:
                            with open(plain_path, "rb") as f:
                                data = f.read()
                            if not is_encrypted_payload(data):
                                enc_data = encryption.encrypt_bytes(data)
                                enc_path = plain_path + ".enc"
                                with open(enc_path, "wb") as f:
                                    f.write(enc_data)
                                os.remove(plain_path)
                                migrated_count += 1
                                logger.info("Migrated unencrypted file: %s -> %s", fname, fname + ".enc")
                        except Exception as ex:
                            logger.error("Failed to migrate original file %s: %s", fname, ex)

        # 2. Migrate result files
        if os.path.isdir(RESULTS_DIR):
            for fname in os.listdir(RESULTS_DIR):
                if fname.endswith(".json") and not fname.endswith(".json.enc"):
                    plain_path = os.path.join(RESULTS_DIR, fname)
                    if os.path.isfile(plain_path):
                        try:
                            with open(plain_path, "rb") as f:
                                data = f.read()
                            if not is_encrypted_payload(data):
                                enc_data = encryption.encrypt_bytes(data)
                                enc_path = os.path.join(RESULTS_DIR, f"{os.path.splitext(fname)[0]}.json.enc")
                                with open(enc_path, "wb") as f:
                                    f.write(enc_data)
                                os.remove(plain_path)
                                logger.info("Migrated unencrypted result: %s", fname)
                        except Exception as ex:
                            logger.error("Failed to migrate result file %s: %s", fname, ex)

        # 3. Update documents.json records
        items = _load_index()
        updated = False
        for item in items:
            stored_name = item.get("stored_filename", "")
            if stored_name and not stored_name.endswith(".enc"):
                item["stored_filename"] = stored_name + ".enc"
                old_path = item.get("file_path", "")
                if old_path and not old_path.endswith(".enc"):
                    item["file_path"] = old_path + ".enc"
                item["is_encrypted"] = True
                updated = True
        if updated:
            _save_index(items)

    return migrated_count


# Initialize storage on import
init_storage()
