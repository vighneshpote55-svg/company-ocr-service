"""
supabase_client.py
Backend Supabase client abstraction for Company-Server OCR service:
- Initializes authenticated Supabase client using service_role key
- Manages private storage operations (company-documents bucket)
- Provides resilient health and readiness diagnostics
- Safe error handling: never exposes secrets, tokens, or sensitive URLs
"""

import os
from typing import Any, Dict, Optional
import logging_utils

from dotenv import load_dotenv
load_dotenv()

logger = logging_utils.get_logger("company_server_ocr.supabase")


def get_supabase_url() -> str:
    return os.getenv("SUPABASE_URL", "").strip()


def get_supabase_key() -> str:
    return os.getenv("SUPABASE_SECRET_KEY", os.getenv("SUPABASE_KEY", "")).strip()


def get_supabase_bucket() -> str:
    return os.getenv("SUPABASE_STORAGE_BUCKET", "company-documents").strip()


def get_supabase_jwt_secret() -> str:
    """Dynamically get the JWT secret from environment."""
    return os.getenv("SUPABASE_JWT_SECRET", "").strip() or os.getenv("JWT_SECRET", "").strip()


SUPABASE_URL = get_supabase_url()
SUPABASE_SECRET_KEY = get_supabase_key()
SUPABASE_STORAGE_BUCKET = get_supabase_bucket()
SUPABASE_JWT_SECRET = get_supabase_jwt_secret()

_supabase_client = None


def is_supabase_configured() -> bool:
    """Return True if Supabase URL and Secret Key are both present."""
    return bool(get_supabase_url() and get_supabase_key())


def get_supabase_client():
    """
    Retrieve or initialize the singleton Supabase client using the backend service_role key.
    Returns None if unconfigured.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    if not is_supabase_configured():
        return None

    try:
        from supabase import create_client, ClientOptions

        # Set reasonable timeouts
        options = ClientOptions(
            postgrest_client_timeout=15,
            storage_client_timeout=30,
        )
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY, options=options)
        logger.info("Supabase backend client initialized successfully.")
        return _supabase_client
    except Exception as ex:
        logger.error(f"Failed to initialize Supabase client: {type(ex).__name__}")
        return None


# ==============================================================================
# Storage Operations (Private bucket)
# ==============================================================================

def upload_encrypted_file(
    storage_path: str,
    file_bytes: bytes,
    content_type: str = "application/octet-stream"
) -> bool:
    """
    Upload an encrypted file blob to the private Supabase Storage bucket.
    Path format: documents/<user_id>/<document_id>/<filename>.enc
    """
    client = get_supabase_client()
    if not client:
        logger.warning("Supabase client unconfigured; cannot upload to Supabase Storage.")
        return False

    try:
        bucket = client.storage.from_(SUPABASE_STORAGE_BUCKET)
        # Upload with upsert=True
        bucket.upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"}
        )
        return True
    except Exception as ex:
        logger.error(f"Failed to upload encrypted file to Supabase Storage: {type(ex).__name__} - {str(ex)}")
        raise


def download_encrypted_file(storage_path: str) -> bytes:
    """
    Download an encrypted file blob from the private Supabase Storage bucket.
    """
    client = get_supabase_client()
    if not client:
        raise RuntimeError("Supabase client unconfigured; cannot download from storage.")

    try:
        bucket = client.storage.from_(SUPABASE_STORAGE_BUCKET)
        data = bucket.download(storage_path)
        if isinstance(data, bytes):
            return data
        return bytes(data)
    except Exception as ex:
        logger.error(f"Failed to download encrypted file from Supabase Storage: {type(ex).__name__}")
        raise


def delete_encrypted_file(storage_path: str) -> bool:
    """
    Delete an encrypted file blob from Supabase Storage.
    """
    client = get_supabase_client()
    if not client:
        return False

    try:
        bucket = client.storage.from_(SUPABASE_STORAGE_BUCKET)
        bucket.remove([storage_path])
        return True
    except Exception as ex:
        logger.error(f"Failed to delete file from Supabase Storage: {type(ex).__name__}")
        return False


# ==============================================================================
# Health and Diagnostics
# ==============================================================================

def check_supabase_health() -> Dict[str, Any]:
    """
    Check if Supabase client is configured and can reach the database.
    """
    if not is_supabase_configured():
        return {
            "status": "unconfigured",
            "connected": False,
            "details": "SUPABASE_URL or SUPABASE_SECRET_KEY is not set."
        }

    client = get_supabase_client()
    if not client:
        return {
            "status": "degraded",
            "connected": False,
            "details": "Client initialization failed."
        }

    try:
        # Ping table with a lightweight query
        res = client.table("profiles").select("id").limit(1).execute()
        return {
            "status": "healthy",
            "connected": True,
            "details": "Successfully connected to Supabase PostgreSQL."
        }
    except Exception as ex:
        logger.warning(f"Supabase health check probe failed: {type(ex).__name__}")
        return {
            "status": "degraded",
            "connected": False,
            "details": f"Database check returned {type(ex).__name__}"
        }


def check_storage_health() -> Dict[str, Any]:
    """
    Check if the private storage bucket is accessible.
    """
    if not is_supabase_configured():
        return {
            "status": "unconfigured",
            "connected": False,
            "bucket": SUPABASE_STORAGE_BUCKET
        }

    client = get_supabase_client()
    if not client:
        return {
            "status": "degraded",
            "connected": False,
            "bucket": SUPABASE_STORAGE_BUCKET
        }

    try:
        # Check bucket listing or info
        buckets = client.storage.list_buckets()
        bucket_names = [b.name for b in buckets] if buckets else []
        bucket_exists = SUPABASE_STORAGE_BUCKET in bucket_names
        return {
            "status": "healthy" if bucket_exists else "warning",
            "connected": True,
            "bucket": SUPABASE_STORAGE_BUCKET,
            "bucket_exists": bucket_exists
        }
    except Exception as ex:
        return {
            "status": "degraded",
            "connected": False,
            "bucket": SUPABASE_STORAGE_BUCKET,
            "error": type(ex).__name__
        }
