"""
api_key_manager.py
API Key Management and Verification for DocPilot AI & External Service Integrations:
- Cryptographically secure API key generation (prefixed with 'dp_live_')
- One-way SHA-256 hashing at rest (raw keys are never persisted)
- Thread-safe storage in uploads/api_keys.json with optional Supabase replication
- Fast in-memory verification and last_used_at telemetry
- Scoped permissions for offline OCR processing
"""

import hashlib
import json
import logging
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("company_server_ocr.api_keys")

STORAGE_ROOT = os.getenv("DOCUMENT_STORAGE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
API_KEYS_FILE = os.path.join(STORAGE_ROOT, "api_keys.json")
_lock = threading.Lock()


def _ensure_storage():
    """Ensure storage directory and index file exist."""
    os.makedirs(STORAGE_ROOT, exist_ok=True)
    if not os.path.exists(API_KEYS_FILE):
        with open(API_KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def _load_keys() -> List[Dict[str, Any]]:
    """Load keys from disk within thread lock."""
    _ensure_storage()
    try:
        with open(API_KEYS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as ex:
        logger.error("Failed to load api_keys.json: %s", ex)
        return []


def _save_keys(keys: List[Dict[str, Any]]) -> bool:
    """Save keys to disk atomically within thread lock."""
    _ensure_storage()
    tmp_file = f"{API_KEYS_FILE}.tmp_{uuid.uuid4().hex[:8]}"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2)
        os.replace(tmp_file, API_KEYS_FILE)
        return True
    except Exception as ex:
        logger.error("Failed to save api_keys.json: %s", ex)
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                pass
        return False


def create_api_key(
    name: str,
    user_id: str,
    user_email: str = "",
    scopes: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Generate a new API key for DocPilot AI or an external client.
    Returns:
        (safe_record, raw_secret_key)
    Note: The raw_secret_key is only returned ONCE upon creation!
    """
    clean_name = (name or "").strip() or "DocPilot AI Integration"
    token_entropy = secrets.token_hex(20)
    raw_key = f"dp_live_{token_entropy}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_prefix = f"{raw_key[:12]}...{raw_key[-4:]}"

    now_iso = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "name": clean_name,
        "key_prefix": key_prefix,
        "key_hash": key_hash,
        "user_id": user_id,
        "user_email": user_email or "client@docpilot.ai",
        "created_at": now_iso,
        "last_used_at": None,
        "is_active": True,
        "scopes": scopes or ["ocr:offline", "ocr:read", "ocr:write"],
    }

    with _lock:
        keys = _load_keys()
        keys.append(record)
        _save_keys(keys)

    logger.info("Created new API key '%s' for user %s (prefix: %s)", clean_name, user_id, key_prefix)

    # Return safe record without key_hash, alongside raw_key for one-time display
    safe_record = {k: v for k, v in record.items() if k != "key_hash"}
    return safe_record, raw_key


def verify_api_key(raw_key: str) -> Optional[Dict[str, Any]]:
    """
    Verify raw API key:
    1. Checks static environment API_KEY fallback.
    2. Checks dynamic hashed keys in api_keys.json.
    Updates last_used_at on successful verification.
    """
    if not raw_key or not isinstance(raw_key, str):
        return None
    raw_key = raw_key.strip()
    if not raw_key:
        return None

    # 1. Static environment variable API_KEY check
    configured_static_key = os.getenv("API_KEY")
    if configured_static_key and secrets.compare_digest(raw_key, configured_static_key.strip()):
        dev_uid = os.getenv("DEFAULT_DEV_USER_ID", "00000000-0000-0000-0000-000000000001")
        return {
            "id": "static-env-key",
            "name": "Static Environment Key",
            "user_id": dev_uid,
            "user_email": "admin@docpilot.ai",
            "scopes": ["ocr:offline", "ocr:read", "ocr:write", "admin"],
            "is_active": True,
        }

    # 2. Hashed dynamic key lookup
    target_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    matched_record = None

    with _lock:
        keys = _load_keys()
        for k in keys:
            if k.get("is_active") and secrets.compare_digest(k.get("key_hash", ""), target_hash):
                k["last_used_at"] = datetime.now(timezone.utc).isoformat()
                matched_record = dict(k)
                _save_keys(keys)
                break

    if matched_record:
        matched_record.pop("key_hash", None)
        return matched_record

    return None


def list_api_keys(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """List API keys, optionally filtered by user_id. Key hashes are stripped."""
    with _lock:
        keys = _load_keys()

    out = []
    for k in keys:
        if user_id and k.get("user_id") != user_id:
            continue
        safe = {field: k[field] for field in (
            "id", "name", "key_prefix", "user_id", "user_email",
            "created_at", "last_used_at", "is_active", "scopes"
        ) if field in k}
        out.append(safe)

    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return out


def revoke_api_key(key_id: str, user_id: Optional[str] = None) -> bool:
    """Revoke or delete an API key by ID."""
    with _lock:
        keys = _load_keys()
        found = False
        new_keys = []
        for k in keys:
            if k.get("id") == key_id:
                if user_id and k.get("user_id") != user_id:
                    # User does not own this key
                    return False
                found = True
                continue  # Delete from active list
            new_keys.append(k)

        if found:
            _save_keys(new_keys)
            logger.info("Revoked API key ID: %s", key_id)
            return True

    return False
