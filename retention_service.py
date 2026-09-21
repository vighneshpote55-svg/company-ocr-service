"""
retention_service.py
Automated Document Retention & Lifecycle Cleanup Service:
- Configurable retention period (DOCUMENT_RETENTION_DAYS, default: 30 days; 0 = disabled)
- Configurable background cleanup interval (CLEANUP_INTERVAL_HOURS, default: 24 hours)
- Purges expired encrypted originals, results, previews, and metadata
- Cleans orphaned files on disk (unreferenced by documents.json)
- Cleans broken references in documents.json (referenced files missing on disk)
- Startup verification & cleanup on microservice launch
- Structured logging: document_expired, cleanup_completed, startup_cleanup (NO document content)
"""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import os
import shutil
from typing import Any, Dict, List, Optional, Set

import document_store
import logging_utils

logger = logging_utils.get_logger("company_server_ocr.retention")

DEFAULT_RETENTION_DAYS = 30
DEFAULT_CLEANUP_INTERVAL_HOURS = 24.0


def get_retention_days() -> int:
    """
    Retrieve configured document retention period in days.
    Returns:
        int: Number of days to retain documents. 0 means retention is disabled.
    Fail-safe: defaults to 30 on invalid or missing values.
    """
    val = os.getenv("DOCUMENT_RETENTION_DAYS")
    if val is None or not str(val).strip():
        return DEFAULT_RETENTION_DAYS
    try:
        days = int(str(val).strip())
        if days < 0:
            return DEFAULT_RETENTION_DAYS
        return days
    except (ValueError, TypeError) as ex:
        logger.warning(
            "Invalid DOCUMENT_RETENTION_DAYS '%s' configured: %s. Failing safely to default %d days.",
            val,
            ex,
            DEFAULT_RETENTION_DAYS,
        )
        return DEFAULT_RETENTION_DAYS


def is_retention_enabled() -> bool:
    """Check if automatic retention deletion is enabled (> 0 days)."""
    return get_retention_days() > 0


def get_cleanup_interval_hours() -> float:
    """
    Retrieve background cleanup worker interval in hours.
    Fail-safe: defaults to 24.0 on invalid or missing values.
    """
    val = os.getenv("CLEANUP_INTERVAL_HOURS")
    if val is None or not str(val).strip():
        return DEFAULT_CLEANUP_INTERVAL_HOURS
    try:
        hours = float(str(val).strip())
        if hours <= 0:
            return DEFAULT_CLEANUP_INTERVAL_HOURS
        return hours
    except (ValueError, TypeError):
        return DEFAULT_CLEANUP_INTERVAL_HOURS


def parse_document_timestamp(doc: Dict[str, Any]) -> Optional[datetime]:
    """Parse document upload or creation timestamp to timezone-aware UTC datetime."""
    raw = doc.get("uploaded_at") or doc.get("created_at")
    if raw and isinstance(raw, str):
        try:
            # Handle ISO string (e.g. 2026-09-20T10:32:15Z or +00:00)
            cleaned = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

    # Fallback to file creation timestamp on disk if file exists
    file_path = doc.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            stat = os.stat(file_path)
            return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        except Exception:
            pass

    return None


def run_cleanup(
    retention_days: Optional[int] = None,
    purge_orphans: bool = True,
    purge_broken_refs: bool = True,
) -> Dict[str, Any]:
    """
    Execute complete retention and cleanup pass:
    1. Delete expired documents older than retention_days (if retention enabled).
    2. Purge broken references in documents.json where files no longer exist.
    3. Purge orphaned files on disk not associated with any active document.
    4. Synchronize documents.json metadata atomically.
    5. Emit structured retention logs.
    """
    if retention_days is None:
        retention_days = get_retention_days()

    now = datetime.now(timezone.utc)
    expired_doc_ids: Set[str] = set()
    broken_ref_ids: Set[str] = set()
    orphans_cleaned: int = 0

    with document_store._lock:
        items = document_store._load_index()

        # Step 1: Detect expired documents
        if retention_days > 0:
            cutoff = now - timedelta(days=retention_days)
            for item in items:
                doc_id = item.get("id") or item.get("document_id")
                if not doc_id:
                    continue

                ts = parse_document_timestamp(item)
                if ts and ts < cutoff:
                    age_days = (now - ts).total_seconds() / 86400.0
                    logging_utils.log_event(
                        logger,
                        logging.INFO,
                        event="document_expired",
                        document_id=doc_id,
                        age_days=round(age_days, 1),
                    )
                    expired_doc_ids.add(doc_id)

        # Step 2: Detect broken references (file missing on disk)
        if purge_broken_refs:
            for item in items:
                doc_id = item.get("id") or item.get("document_id")
                if not doc_id or doc_id in expired_doc_ids:
                    continue
                file_path = document_store.get_document_file_path(doc_id)
                if not file_path or not os.path.exists(file_path):
                    broken_ref_ids.add(doc_id)

        # Step 3: Physically remove files for expired & broken docs
        all_to_remove = expired_doc_ids | broken_ref_ids
        for doc_id in all_to_remove:
            # 1. Remove original uploads
            if os.path.isdir(document_store.ORIGINAL_DIR):
                for fname in os.listdir(document_store.ORIGINAL_DIR):
                    if fname.startswith(doc_id):
                        try:
                            os.remove(os.path.join(document_store.ORIGINAL_DIR, fname))
                        except Exception as ex:
                            logger.warning("Failed to remove original file %s: %s", fname, ex)

            # 2. Remove preview thumbnail
            preview_file = os.path.join(document_store.PROCESSED_DIR, f"{doc_id}_thumb.png")
            if os.path.exists(preview_file):
                try:
                    os.remove(preview_file)
                except Exception as ex:
                    logger.warning("Failed to remove preview %s: %s", preview_file, ex)

            # 3. Remove result files (.json and .json.enc)
            for res_name in (f"{doc_id}.json.enc", f"{doc_id}.json"):
                res_path = os.path.join(document_store.RESULTS_DIR, res_name)
                if os.path.exists(res_path):
                    try:
                        os.remove(res_path)
                    except Exception as ex:
                        logger.warning("Failed to remove result %s: %s", res_path, ex)

        # Step 4: Synchronize documents.json index
        remaining_items = [
            item for item in items
            if (item.get("id") or item.get("document_id")) not in all_to_remove
        ]
        document_store._save_index(remaining_items)

        # Step 5: Clean orphaned files on disk
        if purge_orphans:
            valid_doc_ids = {
                item.get("id") or item.get("document_id")
                for item in remaining_items
                if (item.get("id") or item.get("document_id"))
            }

            # Check ORIGINAL_DIR
            if os.path.isdir(document_store.ORIGINAL_DIR):
                for fname in os.listdir(document_store.ORIGINAL_DIR):
                    fpath = os.path.join(document_store.ORIGINAL_DIR, fname)
                    if os.path.isfile(fpath):
                        # Extract UUID prefix from filename e.g. 9f3c2b6a-...
                        base_prefix = fname.split(".")[0]
                        if base_prefix not in valid_doc_ids:
                            try:
                                os.remove(fpath)
                                orphans_cleaned += 1
                            except Exception:
                                pass

            # Check RESULTS_DIR
            if os.path.isdir(document_store.RESULTS_DIR):
                for fname in os.listdir(document_store.RESULTS_DIR):
                    fpath = os.path.join(document_store.RESULTS_DIR, fname)
                    if os.path.isfile(fpath):
                        base_prefix = fname.split(".")[0]
                        if base_prefix not in valid_doc_ids:
                            try:
                                os.remove(fpath)
                                orphans_cleaned += 1
                            except Exception:
                                pass

            # Check PROCESSED_DIR
            if os.path.isdir(document_store.PROCESSED_DIR):
                for fname in os.listdir(document_store.PROCESSED_DIR):
                    fpath = os.path.join(document_store.PROCESSED_DIR, fname)
                    if os.path.isfile(fpath):
                        doc_part = fname.replace("_thumb.png", "").split(".")[0]
                        if doc_part not in valid_doc_ids:
                            try:
                                os.remove(fpath)
                                orphans_cleaned += 1
                            except Exception:
                                pass

    deleted_count = len(all_to_remove)

    logging_utils.log_event(
        logger,
        logging.INFO,
        event="cleanup_completed",
        deleted_count=deleted_count,
        orphans_cleaned=orphans_cleaned,
    )

    return {
        "success": True,
        "deleted_count": deleted_count,
        "expired_count": len(expired_doc_ids),
        "broken_refs_count": len(broken_ref_ids),
        "orphans_cleaned": orphans_cleaned,
    }


def run_startup_cleanup() -> int:
    """
    On microservice startup:
    1. Verify storage directory structure.
    2. Verify metadata consistency and remove broken references.
    3. Purge orphaned files.
    4. Delete any expired documents.
    5. Log startup_cleanup event with total deleted count.
    """
    os.makedirs(document_store.ORIGINAL_DIR, exist_ok=True)
    os.makedirs(document_store.PROCESSED_DIR, exist_ok=True)
    os.makedirs(document_store.RESULTS_DIR, exist_ok=True)

    result = run_cleanup()
    total_deleted = result.get("deleted_count", 0) + result.get("orphans_cleaned", 0)

    logging_utils.log_event(
        logger,
        logging.INFO,
        event="startup_cleanup",
        deleted=total_deleted,
    )

    return total_deleted


async def periodic_retention_worker() -> None:
    """
    Background worker that runs retention cleanup periodically every CLEANUP_INTERVAL_HOURS.
    Runs non-blockingly as an asynchronous task within FastAPI lifespan.
    """
    interval_hours = get_cleanup_interval_hours()
    interval_seconds = max(60.0, interval_hours * 3600.0)

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            run_cleanup()
        except asyncio.CancelledError:
            break
        except Exception as ex:
            logger.error("Periodic document retention cleanup failed: %s", ex, exc_info=True)
