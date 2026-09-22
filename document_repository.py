"""
document_repository.py
Multi-user Document Repository for Company-Server OCR service:
- Database source of truth: Supabase PostgreSQL (profiles, documents, document_files, ocr_results, extracted_fields, ai_analyses)
- Storage source of truth: Supabase Private Storage (company-documents bucket)
- Local fallback: local encrypted filesystem when Supabase is not configured
- AES-256-GCM encryption for all stored files
- Strict user-level isolation: User A can never view, download, modify, or delete User B's documents
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import encryption
from encryption import is_encrypted_payload
import logging_utils
from supabase_client import (
    get_supabase_client,
    is_supabase_configured,
    upload_encrypted_file,
    download_encrypted_file,
    delete_encrypted_file,
    SUPABASE_STORAGE_BUCKET,
)
import document_store

logger = logging_utils.get_logger("company_server_ocr.document_repository")


def _calculate_sha256(data: bytes) -> str:
    """Calculate SHA256 hex digest of file data."""
    return hashlib.sha256(data).hexdigest()


# ==============================================================================
# Document Creation / Ingestion
# ==============================================================================

def create_document(
    user_id: str,
    original_filename: str,
    file_bytes: bytes,
    file_type: str,
    doc_type: Optional[str] = None,
    mode: str = "offline",
    status: str = "processed",
    ocr_result: Optional[Dict[str, Any]] = None,
    extracted_fields: Optional[Dict[str, Any]] = None,
    ai_analysis: Optional[Dict[str, Any]] = None,
    verification_status: Optional[str] = None,
    review_required: bool = False,
    risk_score: float = 0.0,
    suspicious_signals: Optional[List[Any]] = None,
    human_review_reason: Optional[str] = None,
    verified_by_ai: bool = False,
) -> Dict[str, Any]:
    """
    Persist an uploaded document, its encrypted file, OCR data, extracted fields, AI analysis, and authenticity assessment.
    Enforces that user_id is saved as the document owner.
    """
    doc_id = str(uuid.uuid4())
    checksum = _calculate_sha256(file_bytes)
    checksum_sha256 = checksum
    file_size = len(file_bytes)
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Encrypt the file data
    encrypted_bytes = encryption.encrypt_data(file_bytes)

    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                # Storage path: documents/<user_id>/<doc_id>/<doc_id>.enc
                storage_filename = f"{doc_id}.enc"
                storage_path = f"documents/{user_id}/{doc_id}/{storage_filename}"

                # Upload encrypted bytes to Supabase private storage
                upload_encrypted_file(storage_path, encrypted_bytes)

                # Insert into documents table
                doc_row = {
                    "id": doc_id,
                    "user_id": user_id,
                    "original_filename": original_filename,
                    "file_type": file_type,
                    "storage_path": storage_path,
                    "doc_type": doc_type,
                    "mode": mode,
                    "status": status,
                    "file_size": file_size,
                    "checksum_sha256": checksum_sha256,
                    "verification_status": verification_status,
                    "review_required": review_required,
                    "risk_score": risk_score,
                    "suspicious_signals": suspicious_signals,
                    "human_review_reason": human_review_reason,
                    "verified_by_ai": verified_by_ai,
                    "verification_timestamp": now_iso,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }

                try:
                    # 1. Insert into documents table (with fallback if schema migration not yet applied in Supabase)
                    try:
                        client.table("documents").insert(doc_row).execute()
                    except Exception as insert_err:
                        err_msg = str(insert_err)
                        if "schema cache" in err_msg or "PGRST204" in err_msg or "column" in err_msg:
                            logger.warning(
                                f"Documents table missing new authenticity columns in Supabase schema cache; falling back to base columns: {insert_err}"
                            )
                            base_doc_row = {
                                "id": doc_id,
                                "user_id": user_id,
                                "original_filename": original_filename,
                                "file_type": file_type,
                                "storage_path": storage_path,
                                "doc_type": doc_type,
                                "mode": mode,
                                "status": status,
                                "file_size": file_size,
                                "checksum_sha256": checksum_sha256,
                                "created_at": now_iso,
                                "updated_at": now_iso,
                            }
                            client.table("documents").insert(base_doc_row).execute()
                        else:
                            raise

                    # 2. Insert into document_files (storage metadata)
                    file_row = {
                        "document_id": doc_id,
                        "user_id": user_id,
                        "bucket_name": SUPABASE_STORAGE_BUCKET,
                        "storage_path": storage_path,
                        "encryption_algorithm": "AES-256-GCM",
                        "file_size": file_size,
                        "created_at": now_iso,
                    }
                    client.table("document_files").insert(file_row).execute()

                    # 3. Phase 9.7: Insert into authenticity_checks table
                    try:
                        auth_check_row = {
                            "document_id": doc_id,
                            "user_id": user_id,
                            "risk_score": risk_score,
                            "verification_status": verification_status,
                            "suspicious_signals": suspicious_signals,
                            "created_at": now_iso,
                        }
                        client.table("authenticity_checks").insert(auth_check_row).execute()
                    except Exception as ex_auth:
                        logger.warning(f"Could not insert into authenticity_checks table: {ex_auth}")

                    # 4. Insert into ocr_results if present
                    if ocr_result:
                        ocr_row = {
                            "document_id": doc_id,
                            "user_id": user_id,
                            "raw_text": ocr_result.get("text", ""),
                            "detected_type": doc_type,
                            "confidence": ocr_result.get("confidence") or 0.0,
                            "page_count": ocr_result.get("pages_processed") or ocr_result.get("page_count", 1),
                            "raw_results": ocr_result,
                            "created_at": now_iso,
                        }
                        client.table("ocr_results").insert(ocr_row).execute()

                    # 5. Insert into extracted_fields if present
                    if extracted_fields:
                        fields_row = {
                            "document_id": doc_id,
                            "user_id": user_id,
                            "fields": extracted_fields,
                            "verification_status": verification_status or status,
                            "created_at": now_iso,
                        }
                        client.table("extracted_fields").insert(fields_row).execute()

                    # 6. Insert into ai_analyses if present
                    if ai_analysis:
                        ai_row = {
                            "document_id": doc_id,
                            "user_id": user_id,
                            "provider": ai_analysis.get("provider", "unknown"),
                            "model": ai_analysis.get("model", "unknown"),
                            "summary": ai_analysis.get("summary", ""),
                            "classification": ai_analysis.get("classification") or doc_type,
                            "raw_analysis": ai_analysis,
                            "created_at": now_iso,
                        }
                        client.table("ai_analyses").insert(ai_row).execute()

                    # Also save to local document_store for caching and backward compatibility
                    try:
                        document_store.save_document(
                            doc_id=doc_id,
                            original_filename=original_filename,
                            file_data=file_bytes,
                            file_type=file_type,
                            doc_type=doc_type,
                            mode=mode,
                            status=status,
                            ocr_result=ocr_result,
                            extracted_fields=extracted_fields,
                            ai_analysis=ai_analysis,
                            user_id=user_id,
                            verification_status=verification_status,
                            review_required=review_required,
                            risk_score=risk_score,
                            suspicious_signals=suspicious_signals,
                            human_review_reason=human_review_reason,
                            verified_by_ai=verified_by_ai,
                        )
                    except Exception as ex:
                        logger.debug(f"Local document store cache write skipped: {ex}")

                    saved = get_user_document(user_id, doc_id)
                    if saved:
                        return saved
                    return doc_row
                except Exception as ex:
                    logger.error(f"Failed to persist document to Supabase: {type(ex).__name__} - {str(ex)}")
                    raise

            except Exception as ex:
                err_msg = str(ex)
                if "23503" in err_msg or "foreign key" in err_msg.lower():
                    logger.warning(f"User ID {user_id} not present in Supabase auth.users; falling back to local document store: {ex}")
                    return document_store.save_document(
                        doc_id=doc_id,
                        original_filename=original_filename,
                        file_data=file_bytes,
                        file_type=file_type,
                        doc_type=doc_type,
                        mode=mode,
                        status=status,
                        ocr_result=ocr_result,
                        extracted_fields=extracted_fields,
                        ai_analysis=ai_analysis,
                        user_id=user_id,
                        verification_status=verification_status,
                        review_required=review_required,
                        risk_score=risk_score,
                        suspicious_signals=suspicious_signals,
                        human_review_reason=human_review_reason,
                        verified_by_ai=verified_by_ai,
                    )
                logger.error(f"Failed to persist document to Supabase: {type(ex).__name__} - {str(ex)}")
                raise

    # Fallback: Local storage with user_id attached
    return document_store.save_document(
        doc_id=doc_id,
        original_filename=original_filename,
        file_data=file_bytes,
        file_type=file_type,
        doc_type=doc_type,
        mode=mode,
        status=status,
        ocr_result=ocr_result,
        extracted_fields=extracted_fields,
        ai_analysis=ai_analysis,
        user_id=user_id,
    )


# ==============================================================================
# Document Retrieval & Listing (User-Scoped)
# ==============================================================================

def get_user_documents(
    user_id: str,
    page: int = 1,
    limit: int = 20,
    mode: Optional[str] = None,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List documents owned exclusively by user_id with pagination and filtering.
    """
    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                full_columns = (
                    "id, user_id, original_filename, file_type, doc_type, mode, status, file_size, checksum_sha256, "
                    "verification_status, review_required, risk_score, suspicious_signals, human_review_reason, verified_by_ai, verification_timestamp, "
                    "created_at, updated_at, "
                    "ocr_results(raw_text, detected_type, confidence, page_count), "
                    "extracted_fields(fields, verification_status), "
                    "ai_analyses(provider, model, summary, classification)"
                )
                base_columns = (
                    "id, user_id, original_filename, file_type, doc_type, mode, status, file_size, checksum_sha256, "
                    "created_at, updated_at, "
                    "ocr_results(raw_text, detected_type, confidence, page_count), "
                    "extracted_fields(fields, verification_status), "
                    "ai_analyses(provider, model, summary, classification)"
                )

                def build_query(cols):
                    q = client.table("documents").select(cols, count="exact").eq("user_id", user_id)
                    if mode:
                        q = q.eq("mode", mode)
                    if doc_type:
                        q = q.eq("doc_type", doc_type)
                    if status:
                        q = q.eq("status", status)
                    if search:
                        q = q.ilike("original_filename", f"%{search}%")
                    offset = (page - 1) * limit
                    return q.order("created_at", desc=True).range(offset, offset + limit - 1)

                try:
                    res = build_query(full_columns).execute()
                except Exception as ex_full:
                    err_str = str(ex_full)
                    if "schema cache" in err_str or "PGRST204" in err_str or "column" in err_str:
                        logger.warning("Supabase documents table missing authenticity columns in schema cache; querying base columns.")
                        res = build_query(base_columns).execute()
                    else:
                        raise

                items = []
                for row in res.data or []:
                    item = {
                        "id": row.get("id"),
                        "document_id": row.get("id"),
                        "user_id": row.get("user_id"),
                        "filename": row.get("original_filename"),
                        "original_filename": row.get("original_filename"),
                        "file_type": row.get("file_type"),
                        "doc_type": row.get("doc_type"),
                        "mode": row.get("mode"),
                        "status": row.get("status"),
                        "file_size": row.get("file_size"),
                        "checksum": row.get("checksum_sha256"),
                        "verification_status": row.get("verification_status") or "verified",
                        "review_required": bool(row.get("review_required", False)),
                        "risk_score": float(row.get("risk_score") or 0),
                        "suspicious_signals": row.get("suspicious_signals") or [],
                        "human_review_reason": row.get("human_review_reason"),
                        "verified_by_ai": bool(row.get("verified_by_ai", False)),
                        "verification_timestamp": row.get("verification_timestamp"),
                        "created_at": row.get("created_at"),
                        "updated_at": row.get("updated_at"),
                    }
                    if row.get("ocr_results"):
                        ocr = row["ocr_results"]
                        item["ocr_result"] = ocr[0] if isinstance(ocr, list) and len(ocr) > 0 else ocr
                    if row.get("extracted_fields"):
                        ef = row["extracted_fields"]
                        item["extracted_fields"] = ef[0].get("fields", {}) if isinstance(ef, list) and len(ef) > 0 else ef.get("fields", {})
                    if row.get("ai_analyses"):
                        ai = row["ai_analyses"]
                        item["ai_analysis"] = ai[0] if isinstance(ai, list) and len(ai) > 0 else ai
                    items.append(item)

                total = res.count if res.count is not None else len(items)
                return {
                    "documents": items,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "total_pages": (total + limit - 1) // limit if limit > 0 else 1,
                }
            except Exception as ex:
                logger.error(f"Failed to fetch documents from Supabase: {type(ex).__name__}")
                # Fall through to local fallback

    # Local storage fallback
    return document_store.get_documents(
        page=page,
        limit=limit,
        mode=mode,
        doc_type=doc_type,
        status=status,
        search=search,
        user_id=user_id,
    )


def get_user_document(user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve single document metadata and results.
    Verifies that the document belongs to user_id. Returns None if not found or unauthorized.
    """
    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                full_cols = (
                    "id, user_id, original_filename, file_type, doc_type, mode, status, file_size, checksum_sha256, storage_path, "
                    "verification_status, review_required, risk_score, suspicious_signals, human_review_reason, verified_by_ai, verification_timestamp, "
                    "created_at, updated_at, "
                    "ocr_results(raw_text, detected_type, confidence, page_count, raw_results), "
                    "extracted_fields(fields, verification_status), "
                    "ai_analyses(provider, model, summary, classification, raw_analysis)"
                )
                base_cols = (
                    "id, user_id, original_filename, file_type, doc_type, mode, status, file_size, checksum_sha256, storage_path, "
                    "created_at, updated_at, "
                    "ocr_results(raw_text, detected_type, confidence, page_count, raw_results), "
                    "extracted_fields(fields, verification_status), "
                    "ai_analyses(provider, model, summary, classification, raw_analysis)"
                )
                try:
                    res = client.table("documents").select(full_cols).eq("id", document_id).eq("user_id", user_id).limit(1).execute()
                except Exception as ex_full:
                    err_str = str(ex_full)
                    if "schema cache" in err_str or "PGRST204" in err_str or "column" in err_str:
                        logger.warning("Supabase documents table missing authenticity columns in schema cache; querying base columns.")
                        res = client.table("documents").select(base_cols).eq("id", document_id).eq("user_id", user_id).limit(1).execute()
                    else:
                        raise

                if res.data and len(res.data) > 0:
                    row = res.data[0]
                    item = {
                        "id": row.get("id"),
                        "document_id": row.get("id"),
                        "user_id": row.get("user_id"),
                        "filename": row.get("original_filename"),
                        "original_filename": row.get("original_filename"),
                        "file_type": row.get("file_type"),
                        "doc_type": row.get("doc_type"),
                        "mode": row.get("mode"),
                        "status": row.get("status"),
                        "file_size": row.get("file_size"),
                        "checksum": row.get("checksum_sha256"),
                        "storage_path": row.get("storage_path"),
                        "verification_status": row.get("verification_status") or "verified",
                        "review_required": bool(row.get("review_required", False)),
                        "risk_score": float(row.get("risk_score") or 0),
                        "suspicious_signals": row.get("suspicious_signals") or [],
                        "human_review_reason": row.get("human_review_reason"),
                        "verified_by_ai": bool(row.get("verified_by_ai", False)),
                        "verification_timestamp": row.get("verification_timestamp"),
                        "created_at": row.get("created_at"),
                        "updated_at": row.get("updated_at"),
                    }
                    item["file_url"] = f"/api/documents/{row.get('id')}/file"
                    item["preview_url"] = f"/api/documents/{row.get('id')}/preview"
                    item["pages"] = 1
                    if row.get("ocr_results"):
                        ocr = row["ocr_results"]
                        item["ocr_result"] = ocr[0] if isinstance(ocr, list) and len(ocr) > 0 else ocr
                        if isinstance(item["ocr_result"], dict):
                            item["pages"] = item["ocr_result"].get("page_count", 1)
                    if row.get("extracted_fields"):
                        ef = row["extracted_fields"]
                        item["extracted_fields"] = ef[0].get("fields", {}) if isinstance(ef, list) and len(ef) > 0 else ef.get("fields", {})
                    if row.get("ai_analyses"):
                        ai = row["ai_analyses"]
                        item["ai_analysis"] = ai[0] if isinstance(ai, list) and len(ai) > 0 else ai
                    return item
                return None
            except Exception as ex:
                logger.error(f"Failed to fetch document {document_id} from Supabase: {type(ex).__name__}")

    # Local fallback
    doc = document_store.get_document_metadata(document_id)
    if doc:
        # Check user ownership if user_id is present
        doc_owner = doc.get("user_id")
        if doc_owner and doc_owner != user_id:
            return None
        return doc
    return None


# ==============================================================================
# Document File Download & Preview (Decryption in Memory)
# ==============================================================================

def get_document_file_payload(
    user_id: str,
    document_id: str
) -> Optional[Tuple[bytes, str, str]]:
    """
    Retrieve and decrypt document file for the verified owner.
    Returns: (decrypted_bytes, filename, content_type) or None if unauthorized/not found.
    """
    doc = get_user_document(user_id, document_id)
    if not doc:
        return None

    filename = doc.get("original_filename") or doc.get("filename") or f"{document_id}.bin"
    file_type = (doc.get("file_type") or "").lower()

    if "pdf" in file_type or filename.lower().endswith(".pdf"):
        content_type = "application/pdf"
    elif "png" in file_type or filename.lower().endswith(".png"):
        content_type = "image/png"
    elif "jpg" in file_type or "jpeg" in file_type or filename.lower().endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    elif "tiff" in file_type or filename.lower().endswith((".tif", ".tiff")):
        content_type = "image/tiff"
    else:
        content_type = "application/octet-stream"

    # Try downloading from Supabase Storage
    if is_supabase_configured():
        storage_path = doc.get("storage_path") or f"documents/{user_id}/{document_id}/{document_id}.enc"
        try:
            encrypted_bytes = download_encrypted_file(storage_path)
            decrypted_bytes = encryption.decrypt_data(encrypted_bytes)
            return decrypted_bytes, filename, content_type
        except Exception as ex:
            logger.warning(f"Failed to download/decrypt from Supabase Storage: {type(ex).__name__}")

    # Local filesystem fallback
    local_path = document_store.get_document_file_path(document_id)
    if local_path and os.path.exists(local_path):
        with open(local_path, "rb") as f:
            raw = f.read()
        if is_encrypted_payload(raw):
            decrypted = encryption.decrypt_data(raw)
            return decrypted, filename, content_type
        return raw, filename, content_type

    return None


# ==============================================================================
# Document Deletion (User-Scoped)
# ==============================================================================

def delete_user_document(user_id: str, document_id: str) -> bool:
    """
    Delete a document owned by user_id from database and storage.
    """
    doc = get_user_document(user_id, document_id)
    if not doc:
        return False

    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                storage_path = doc.get("storage_path") or f"documents/{user_id}/{document_id}/{document_id}.enc"
                try:
                    delete_encrypted_file(storage_path)
                except Exception as ex:
                    logger.warning(f"Could not delete storage object {storage_path}: {ex}")

                client.table("documents").delete().eq("id", document_id).eq("user_id", user_id).execute()
                # Clean up local cache if present
                try:
                    document_store.delete_document(document_id)
                except Exception:
                    pass
                return True
            except Exception as ex:
                logger.error(f"Failed to delete document {document_id} in Supabase: {type(ex).__name__}")
                return False

    # Local fallback
    return document_store.delete_document(document_id)


def clear_user_documents(user_id: str) -> int:
    """
    Delete all documents owned exclusively by user_id.
    """
    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                # Fetch all document IDs and paths for this user
                res = client.table("documents").select("id, storage_path").eq("user_id", user_id).execute()
                docs = res.data or []
                count = len(docs)
                for d in docs:
                    sp = d.get("storage_path")
                    if sp:
                        try:
                            delete_encrypted_file(sp)
                        except Exception:
                            pass
                    try:
                        document_store.delete_document(d.get("id"))
                    except Exception:
                        pass

                # Delete all user documents from DB
                client.table("documents").delete().eq("user_id", user_id).execute()
                return count
            except Exception as ex:
                logger.error(f"Failed to clear documents for user {user_id}: {type(ex).__name__}")
                return 0

    # Local fallback
    return document_store.clear_all_documents(user_id=user_id)


# ==============================================================================
# User Statistics (User-Scoped)
# ==============================================================================

def get_user_statistics(user_id: str) -> Dict[str, Any]:
    """
    Calculate statistics exclusively for documents owned by user_id.
    """
    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                res = client.table("documents").select("mode, status, doc_type, file_size").eq("user_id", user_id).execute()
                rows = res.data or []

                total = len(rows)
                offline_count = sum(1 for r in rows if r.get("mode") == "offline")
                ai_count = sum(1 for r in rows if r.get("mode") == "ai")
                processed_count = sum(1 for r in rows if r.get("status") in ("processed", "completed", "valid", "verified"))
                failed_count = sum(1 for r in rows if r.get("status") in ("failed", "error", "invalid"))
                total_bytes = sum(int(r.get("file_size") or 0) for r in rows)

                by_doc_type = {}
                for r in rows:
                    dt = r.get("doc_type") or "unknown"
                    by_doc_type[dt] = by_doc_type.get(dt, 0) + 1

                return {
                    "total_documents": total,
                    "offline_documents": offline_count,
                    "ai_documents": ai_count,
                    "processed_documents": processed_count,
                    "failed_documents": failed_count,
                    "total_storage_bytes": total_bytes,
                    "total_storage_mb": round(total_bytes / (1024 * 1024), 2),
                    "documents_by_type": by_doc_type,
                    "success_rate": round((processed_count / total) * 100, 1) if total > 0 else 100.0,
                }
            except Exception as ex:
                logger.error(f"Failed to calculate stats in Supabase: {type(ex).__name__}")

    # Local fallback
    return document_store.get_document_statistics(user_id=user_id)
