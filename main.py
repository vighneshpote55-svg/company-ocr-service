"""
main.py
Company-Server OCR FastAPI Microservice:
- Endpoints:
  - POST /ocr/{doc_type} (Async job queue with optional ?sync=true)
  - GET /ocr/jobs/{job_id} (Polling endpoint)
  - POST /auth/token (Mint short-lived JWTs)
  - GET /health (Health check)
- End-to-end document verification, PII minimisation, QR/MICR decoding,
  image quality pre-checks, temp file lifecycle management, and audit logging.
"""

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import io
import uuid
import fitz
from pypdf import PdfReader

from dotenv import load_dotenv

load_dotenv()

import ai_service
import ollama_ai
import ai_providers
from pydantic import BaseModel, Field
import logging_utils
import retention_service
from rate_limiter import rate_limit_upload, rate_limit_ai_chat, rate_limit_cleanup

logging_utils.setup_logging()
logger = logging_utils.get_logger("company_server_ocr")


from fastapi import (

    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from audit_logger import log_audit_event
import document_store
import document_repository
import chat_repository
import supabase_client
import encryption
from encryption import DocumentDecryptionError, DocumentEncryptionKeyMissingError
from extractors import (
    EXTRACTOR_REGISTRY,
    PII_ALLOWLIST,
    extract_document_fields,
    extract_document_fields_raw,
    sanitize_extracted_fields,
)
from image_quality import evaluate_image_quality
from micr_reader import extract_micr_from_cheque
from ocr_engine import (
    OCREngine,
    OCRDocumentResult,
    check_pdf_text_layer,
    get_languages_for_doc_type,
    get_ocr_engine_info,
    render_pdf_pages_to_images,
    render_thumbnail,
    validate_ocr_engine_configuration,
)
from qr_decoder import decode_qr_from_image, parse_qr_payload, reconcile_ocr_and_qr
from queue_manager import JobRecord, job_queue
from security import (
    authenticate_request,
    create_access_token,
    get_auth_mode,
    is_auth_enabled,
    validate_security_configuration,
    verify_client_credentials,
)
from auth_dependencies import get_current_user, UserProfile
from verifier import (
    check_doc_type_mismatch,
    classify_document_content,
    detect_document_type,
    determine_document_status,
    load_valid_bank_codes,
    normalize_ocr_text,
    perform_cross_check,
    validate_document_checksums,
    DOC_TYPE_METADATA,
)
from authenticity_checker import authenticity_manager

# Configuration & Constants
TEMP_DIR = os.getenv("OCR_TEMP_DIR", os.path.join(tempfile.gettempdir(), "company_ocr_temp"))
TEMP_FILE_TTL_MINUTES = int(os.getenv("TEMP_FILE_TTL_MINUTES", "15"))

os.makedirs(TEMP_DIR, exist_ok=True)
ocr_engine = OCREngine()


# ==============================================================================
# Orphaned Temp File Sweeper
# ==============================================================================

def sweep_orphaned_temp_files(max_age_minutes: int = TEMP_FILE_TTL_MINUTES):
    """Clean up any leftover temporary files older than max_age_minutes."""
    now = time.time()
    cutoff = now - (max_age_minutes * 60)
    try:
        for entry in os.scandir(TEMP_DIR):
            if entry.is_file():
                try:
                    stat = entry.stat()
                    if stat.st_mtime < cutoff:
                        os.remove(entry.path)
                except Exception:
                    pass
    except Exception:
        pass


async def periodic_temp_cleaner():
    """Periodic background task to ensure temp files are cleaned even on crashes."""
    while True:
        try:
            await asyncio.sleep(300)  # Sweep every 5 minutes
            sweep_orphaned_temp_files()
        except asyncio.CancelledError:
            break
        except Exception:
            pass


_startup_security_error: Optional[str] = None


def _map_error_code(status_code: int, detail: Any) -> str:
    """Map HTTP status and detail text to standardized error code for logging."""
    det = str(detail or "").upper()
    if "CORRUPT" in det:
        return "CORRUPTED_FILE"
    if "PASSWORD" in det or "ENCRYPTED" in det:
        return "ENCRYPTED_PDF"
    if "UNSUPPORTED" in det or "FILE TYPE" in det:
        return "UNSUPPORTED_EXTENSION"
    if "TRAVERSAL" in det or "INVALID FILENAME" in det:
        return "PATH_TRAVERSAL_DETECTED"
    if "SIZE" in det or "LARGE" in det or status_code == 413:
        return "FILE_SIZE_EXCEEDED"
    if "EMPTY" in det:
        return "EMPTY_FILE"
    if "INVALID PDF" in det:
        return "INVALID_PDF"
    if "OCR" in det:
        return "OCR_FAILED"
    if "AI" in det:
        return "AI_FAILED"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 401:
        return "UNAUTHORIZED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 422:
        return "UNPROCESSABLE_ENTITY"
    return f"HTTP_{status_code}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_security_error
    try:
        # Startup: fail fast if security configuration is invalid
        validate_security_configuration()
        # Startup: fail fast if bank codes configuration is invalid
        load_valid_bank_codes()
        # Startup: fail fast if configured OCR engine is invalid or unavailable
        validate_ocr_engine_configuration()
        _startup_security_error = None
    except Exception as ex:
        _startup_security_error = str(ex)
        raise

    # Component health discovery for startup event (Task 7)
    ocr_info = get_ocr_engine_info()
    rapidocr_status = "ready" if ocr_info.get("status") in ("ready", "mock_ready", "active") else "error"
    ollama_health = ollama_ai.check_ollama_health()
    ollama_status = "ready" if ollama_health.get("model_installed") else ("running" if ollama_health.get("reachable") else "offline")
    storage_health = document_store.check_storage_health()
    storage_status = "healthy" if storage_health.get("healthy") else "degraded"
    enc_status = "enabled" if encryption.is_encryption_available() else "disabled"

    logging_utils.log_event(
        logger,
        logging.INFO,
        event="server_started",
        rapidocr=rapidocr_status,
        ollama=ollama_status,
        storage=storage_status,
        encryption=enc_status,
    )
    logging_utils.log_event(logger, logging.INFO, event="ocr_health_check", rapidocr=rapidocr_status)
    logging_utils.log_event(logger, logging.INFO, event="ollama_health_check", ollama=ollama_status)
    logging_utils.log_event(logger, logging.INFO, event="storage_health_check", storage=storage_status)

    # Phase 6: Run startup verification and storage cleanup
    retention_service.run_startup_cleanup()

    # Sweep leftover temp files, start job queue and background sweep task
    sweep_orphaned_temp_files()
    await job_queue.start()
    cleaner_task = asyncio.create_task(periodic_temp_cleaner())
    retention_task = asyncio.create_task(retention_service.periodic_retention_worker())
    yield
    # Shutdown: stop workers and cleaners
    retention_task.cancel()
    cleaner_task.cancel()
    await job_queue.stop()



def get_cors_origins() -> List[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if origins:
            return origins
    env = os.getenv("ENVIRONMENT", "development").strip().lower()
    if env == "production":
        return ["http://localhost", "http://localhost:80", "https://localhost"]
    return [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://localhost:80",
        "http://localhost",
    ]


_cors_origins = get_cors_origins()
_allow_creds = "*" not in _cors_origins

app = FastAPI(
    title="Company-Server OCR",
    description="FastAPI OCR verification and PII minimisation service built on PaddleOCR",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_tracing_middleware(request: Request, call_next):
    """Task 2: Injects and propagates request_id across request lifecycle."""
    req_id = request.headers.get("X-Request-ID") or logging_utils.generate_request_id()
    logging_utils.set_request_id(req_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


@app.middleware("http")
async def enforce_startup_security_check(request: Request, call_next):
    if _startup_security_error is not None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": f"Service unavailable: startup security check failed: {_startup_security_error}"
            },
        )
    return await call_next(request)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Task 5: Structured error logs while preserving friendly frontend errors."""
    detail = exc.detail
    content = {"detail": detail}
    if isinstance(detail, str):
        content["error"] = detail
    elif isinstance(detail, dict):
        content.update(detail)

    error_code = _map_error_code(exc.status_code, detail)
    is_upload = any(p in request.url.path for p in ("/offline", "/analyze", "/ocr", "/upload"))
    logging_utils.log_event(
        logger,
        logging.WARNING if exc.status_code < 500 else logging.ERROR,
        event="upload_failed" if is_upload else "request_failed",
        error_code=error_code,
        status_code=exc.status_code,
        path=request.url.path,
        status="failed",
    )
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


@app.exception_handler(DocumentEncryptionKeyMissingError)
async def encryption_key_missing_handler(request: Request, exc: DocumentEncryptionKeyMissingError):
    msg = "Encryption service unavailable: server encryption key is not configured."
    logging_utils.log_event(
        logger,
        logging.ERROR,
        event="upload_failed",
        error_code="ENCRYPTION_KEY_MISSING",
        status_code=500,
        status="error",
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": msg, "error": msg})


@app.exception_handler(DocumentDecryptionError)
async def decryption_error_handler(request: Request, exc: DocumentDecryptionError):
    msg = "Document decryption failed."
    logging_utils.log_event(
        logger,
        logging.ERROR,
        event="decryption_failed",
        error_code="DECRYPTION_ERROR",
        status_code=500,
        status="error",
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": msg, "error": msg})


def get_max_image_size_bytes() -> int:
    try:
        mb = float(os.getenv("MAX_IMAGE_SIZE_MB", "20"))
        return int(mb * 1024 * 1024)
    except Exception:
        return 20 * 1024 * 1024


def get_max_pdf_size_bytes() -> int:
    try:
        mb = float(os.getenv("MAX_PDF_SIZE_MB", "50"))
        return int(mb * 1024 * 1024)
    except Exception:
        return 50 * 1024 * 1024


MAX_IMAGE_SIZE = get_max_image_size_bytes()
MAX_PDF_SIZE = get_max_pdf_size_bytes()
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def validate_upload_security(file: UploadFile, file_bytes: bytes) -> tuple[str, str]:
    """
    Validate uploaded file security:
    1. Reject path traversal attempts in filename (Task 2)
    2. Validate file extension and MIME type against allowed list (Task 3)
    3. Enforce maximum file size limits (Task 4)
    4. Validate magic bytes to prevent masqueraded files (Task 3)
    5. Detect password-protected encrypted PDFs (Task 6)
    6. Detect corrupted or unreadable images/PDFs before OCR (Task 5)
    Returns (clean_filename, extension).
    """
    raw_filename = file.filename or "document.bin"

    # 1. Path Traversal Check (Task 2)
    if ".." in raw_filename or "/" in raw_filename or "\\" in raw_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: path traversal characters detected.",
        )

    clean_filename = document_store.sanitize_filename(raw_filename)
    ext = os.path.splitext(clean_filename)[1].lower()

    # 2. File Extension Validation (Task 3)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type.",
        )

    content_type = (file.content_type or "").lower().strip()

    # 3. File Size Limits (Task 4)
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    env_max_img = get_max_image_size_bytes()
    cur_max_img = MAX_IMAGE_SIZE if MAX_IMAGE_SIZE != 20 * 1024 * 1024 else env_max_img
    env_max_pdf = get_max_pdf_size_bytes()
    cur_max_pdf = MAX_PDF_SIZE if MAX_PDF_SIZE != 50 * 1024 * 1024 else env_max_pdf

    if ext in (".png", ".jpg", ".jpeg", ".webp") and len(file_bytes) > cur_max_img:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="This file exceeds the maximum upload size.",
        )

    if ext == ".pdf" and len(file_bytes) > cur_max_pdf:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="This file exceeds the maximum upload size.",
        )

    # 4. Magic Bytes & MIME Type Check (Task 3)
    if ext == ".pdf":
        if b"%PDF-" not in file_bytes[:1024]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )
        if content_type and content_type not in (
            "application/pdf",
            "application/x-pdf",
            "application/octet-stream",
            "binary/octet-stream",
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )
    elif ext == ".png":
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )
        if content_type and content_type not in (
            "image/png",
            "application/octet-stream",
            "binary/octet-stream",
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )
    elif ext in (".jpg", ".jpeg"):
        if not file_bytes.startswith(b"\xff\xd8\xff"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )
        if content_type and content_type not in (
            "image/jpeg",
            "image/jpg",
            "image/pjpeg",
            "application/octet-stream",
            "binary/octet-stream",
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )
    elif ext == ".webp":
        if not (file_bytes.startswith(b"RIFF") and len(file_bytes) >= 12 and file_bytes[8:12] == b"WEBP"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )
        if content_type and content_type not in (
            "image/webp",
            "application/octet-stream",
            "binary/octet-stream",
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type.",
            )

    # 5. Encrypted PDF Detection (Task 6)
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            if reader.is_encrypted:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="This PDF is encrypted. Please upload an unlocked copy.",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    # 6. Corrupted File Detection (Task 5)
    if ext in (".png", ".jpg", ".jpeg", ".webp"):
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.load()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This file appears to be corrupted.",
            )
    elif ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            if len(reader.pages) == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="This file appears to be corrupted.",
                )
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            if doc.page_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="This file appears to be corrupted.",
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This file appears to be corrupted.",
            )

    return clean_filename, ext


# ==============================================================================
# Core OCR Processing Logic
# ==============================================================================

def execute_ocr_pipeline(
    file_path: str,
    doc_type: str,
    expected_data: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the end-to-end OCR pipeline synchronously:
    1. Image quality pre-check
    2. OCR Engine pass (PaddleOCR)
    3. Document type mismatch check
    4. QR code decoding & reconciliation
    5. MICR reading (if cancelled cheque)
    6. Field extraction & PII minimisation
    7. Checksums & cross-check verification
    8. Structured audit log entry (strictly no PII)
    """
    start_time = time.time()
    doc_type = doc_type.lower().strip()

    # 1. Quality Pre-check (evaluate first page or image)
    quality_issues: List[str] = []
    first_page_img: Optional[Image.Image] = None

    try:
        if file_path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
            with Image.open(file_path) as img:
                first_page_img = img.copy()
        elif file_path.lower().endswith(".pdf"):
            # Render first page for quality check if poppler/PyMuPDF available
            try:
                import fitz
                doc = fitz.open(file_path)
                if len(doc) > 0:
                    page = doc[0]
                    pix = page.get_pixmap()
                    first_page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            except Exception:
                pass
    except Exception:
        pass

    if first_page_img:
        q_result = evaluate_image_quality(first_page_img)
        if not q_result.is_acceptable:
            duration_ms = (time.time() - start_time) * 1000
            log_audit_event(
                doc_type=doc_type,
                status="low_confidence",
                confidence=0.0,
                job_id=job_id,
                customer_id=customer_id,
                reason="image_quality",
                duration_ms=duration_ms,
                extra_meta={"quality_issues": q_result.issues},
            )
            return {
                "status": "low_confidence",
                "reason": "image_quality",
                "doc_type": doc_type,
                "confidence": 0.0,
                "field_confidences": {},
                "quality_details": {
                    "issues": q_result.issues,
                    "blur_score": q_result.blur_score,
                },
                "extracted_fields": {},
            }

    # 2. OCR Extraction
    languages = get_languages_for_doc_type(doc_type)
    logging_utils.log_event(logger, logging.INFO, event="ocr_started", doc_type=doc_type)
    ocr_start_time = time.time()
    try:
        doc_res: OCRDocumentResult = ocr_engine.process_file(file_path, languages=languages)
        ocr_dur_ms = int((time.time() - ocr_start_time) * 1000)
        logging_utils.log_event(
            logger,
            logging.INFO,
            event="ocr_completed",
            duration_ms=ocr_dur_ms,
            pages=len(doc_res.pages) if doc_res.pages else 1,
            status="success",
        )
    except Exception as ex:
        ocr_dur_ms = int((time.time() - ocr_start_time) * 1000)
        logging_utils.log_event(
            logger,
            logging.ERROR,
            event="ocr_completed",
            duration_ms=ocr_dur_ms,
            status="failed",
        )
        duration_ms = (time.time() - start_time) * 1000
        logger.error("OCR engine crashed for job %s: %s", job_id, ex, exc_info=True)
        log_audit_event(
            doc_type=doc_type,
            status="error",
            confidence=0.0,
            job_id=job_id,
            customer_id=customer_id,
            reason="ocr_engine_returned_no_text",
            duration_ms=duration_ms,
            extra_meta={"engine_error": str(ex)},
        )
        return {
            "status": "error",
            "reason": "ocr_engine_returned_no_text",
            "doc_type": doc_type,
            "confidence": 0.0,
            "field_confidences": {},
            "extracted_fields": {},
            "message": f"OCR engine execution failed: {str(ex)}",
        }

    # Hard check: empty/whitespace text, zero confidence, zero lines, or explicit engine_error
    has_text = bool(doc_res.full_text and doc_res.full_text.strip())
    has_lines = any(bool(p.lines) for p in doc_res.pages) if doc_res.pages else False
    has_engine_error = bool(getattr(doc_res, "engine_error", None))

    if has_engine_error or not has_text or doc_res.average_confidence == 0.0 or not has_lines:
        duration_ms = (time.time() - start_time) * 1000
        failure_reason = getattr(doc_res, "engine_error", None) or "OCR engine returned no text or zero confidence"
        log_audit_event(
            doc_type=doc_type,
            status="error",
            confidence=0.0,
            job_id=job_id,
            customer_id=customer_id,
            reason="ocr_engine_returned_no_text",
            duration_ms=duration_ms,
            extra_meta={"engine_error": failure_reason},
        )
        return {
            "status": "error",
            "reason": "ocr_engine_returned_no_text",
            "doc_type": doc_type,
            "confidence": 0.0,
            "field_confidences": {},
            "extracted_fields": {},
            "message": failure_reason,
        }

    # 3. Document-Type Mismatch Detection
    is_mismatch, detected_type = check_doc_type_mismatch(doc_type, doc_res.full_text)
    if is_mismatch:
        duration_ms = (time.time() - start_time) * 1000
        log_audit_event(
            doc_type=doc_type,
            status="error",
            confidence=0.0,
            job_id=job_id,
            customer_id=customer_id,
            reason="doc_type_mismatch",
            duration_ms=duration_ms,
        )
        return {
            "status": "error",
            "reason": "doc_type_mismatch",
            "doc_type": doc_type,
            "detected_type": detected_type,
            "confidence": 0.0,
            "field_confidences": {},
            "extracted_fields": {},
            "message": f"Uploaded document appears to be '{detected_type}' rather than requested '{doc_type}'",
        }

    # 4. Raw Field Extraction (with unmasked & raw fields available for verification)
    raw_fields, field_confidences = extract_document_fields_raw(doc_type, doc_res)

    # 5. QR Code Decoding & Reconciliation (Aadhaar, Udyam, FSSAI)
    qr_disagreements: List[Dict[str, Any]] = []
    if doc_type in ("aadhaar", "udyam", "fssai"):
        qr_texts: List[str] = []
        if first_page_img:
            qr_texts = decode_qr_from_image(first_page_img)

        for qr_text in qr_texts:
            qr_data = parse_qr_payload(doc_type, qr_text)
            reconciled_fields, disagreements = reconcile_ocr_and_qr(raw_fields, qr_data)
            raw_fields = reconciled_fields
            qr_disagreements.extend(disagreements)

    # 6. MICR Line Reading (Cancelled Cheque)
    if doc_type == "cancelled_cheque":
        ocr_func = None
        if first_page_img:
            ocr_func = lambda img: (ocr_engine.process_image(img).full_text, None)
        micr_data = extract_micr_from_cheque(
            cheque_img=first_page_img or Image.new("RGB", (100, 100)),
            ocr_func=ocr_func,
            ocr_full_text=doc_res.full_text,
            full_page_fields=raw_fields,
        )
        raw_fields["micr_line"] = micr_data.get("micr_line")
        raw_fields["micr_confidence"] = micr_data.get("micr_confidence", "low")
        if micr_data.get("micr_code"):
            raw_fields["micr_code"] = micr_data["micr_code"]
        if micr_data.get("account_number_masked"):
            raw_fields["micr_account_number_masked"] = micr_data["account_number_masked"]
        if micr_data.get("tran_code"):
            raw_fields["tran_code"] = micr_data["tran_code"]
        if micr_data.get("cheque_number") and not raw_fields.get("cheque_number"):
            raw_fields["cheque_number"] = micr_data["cheque_number"]
        if "micr_match" in micr_data:
            raw_fields["micr_match"] = micr_data["micr_match"]
        if micr_data.get("micr_disagreements"):
            raw_fields["micr_disagreements"] = micr_data["micr_disagreements"]

    # 7. Checksums & Format Validation on RAW fields (raw_aadhaar is present for Verhoeff validation)
    is_valid_format, invalid_reason = validate_document_checksums(doc_type, raw_fields)
    overall_status = "success"
    status_reason = None

    if not is_valid_format:
        overall_status = "low_confidence"
        status_reason = invalid_reason

    # 8. Cross-check against expected fields on RAW fields (unmasked employee_name is present)
    cross_check_results = None
    if expected_data:
        cross_check_results = perform_cross_check(raw_fields, expected_data)

    # 9. PII Minimisation: Sanitize fields strictly AFTER verification and cross-checking
    sanitized_fields, sanitized_confidences = sanitize_extracted_fields(doc_type, raw_fields, field_confidences)

    # Overall confidence calculation
    if sanitized_confidences:
        calculated_conf = sum(sanitized_confidences.values()) / len(sanitized_confidences)
    elif field_confidences:
        calculated_conf = sum(field_confidences.values()) / len(field_confidences)
    else:
        calculated_conf = doc_res.average_confidence

    duration_ms = (time.time() - start_time) * 1000

    # 10. Structured Audit Logging (STRICTLY NO PII)
    log_audit_event(
        doc_type=doc_type,
        status=overall_status,
        confidence=calculated_conf,
        job_id=job_id,
        customer_id=customer_id,
        reason=status_reason,
        duration_ms=duration_ms,
        extra_meta={
            "pages_count": len(doc_res.pages),
            "qr_detected": bool(qr_disagreements or (doc_type in ("aadhaar", "udyam", "fssai"))),
            "micr_detected": doc_type == "cancelled_cheque",
        },
    )

    response_payload = {
        "status": overall_status,
        "doc_type": doc_type,
        "confidence": round(calculated_conf, 4),
        "field_confidences": sanitized_confidences,
        "extracted_fields": sanitized_fields,
    }

    if status_reason:
        response_payload["reason"] = status_reason
    if qr_disagreements:
        response_payload["qr_disagreements"] = qr_disagreements
    if cross_check_results:
        response_payload["cross_check"] = cross_check_results

    logging_utils.log_event(
        logger,
        logging.INFO,
        event="document_processed",
        document_type=doc_type,
        ocr_engine="RapidOCR",
        ai_model="none",
        processing_time_ms=int(duration_ms),
        status="success" if overall_status in ("verified", "completed", "low_confidence") else "failed",
    )

    return response_payload



# ==============================================================================
# Endpoints
# ==============================================================================

@app.post("/ocr/{doc_type}")
async def process_ocr_endpoint(
    doc_type: str,
    file: UploadFile = File(...),
    expected: Optional[str] = Form(None),
    webhook_url: Optional[str] = Form(None),
    customer_id: Optional[str] = Form(None),
    sync: bool = Query(False, description="Set True for immediate synchronous execution"),
    auth: dict = Depends(authenticate_request),
    _rate_limit: None = Depends(rate_limit_upload),
):
    """
    POST /ocr/{doc_type}
    Enqueues OCR job and returns a job_id (async queue pattern).
    Set ?sync=true for immediate synchronous execution.
    """
    # Parse optional expected JSON data
    expected_data = None
    if expected:
        try:
            expected_data = json.loads(expected)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Expected data must be a valid JSON string",
            )

    # Validate upload security (Path traversal, allowed MIME/types, file size, corruption, encryption)
    file_bytes = await file.read()
    clean_filename, ext = validate_upload_security(file, file_bytes)

    # Save uploaded file to temp directory using randomized UUID filename
    temp_path = os.path.join(TEMP_DIR, f"ocr_{uuid.uuid4()}{ext}")
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    # If synchronous mode requested
    if sync:
        try:
            result = execute_ocr_pipeline(
                file_path=temp_path,
                doc_type=doc_type,
                expected_data=expected_data,
                customer_id=customer_id,
            )
            return JSONResponse(content=result)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Async Job-Queue pattern
    job = job_queue.create_job(
        doc_type=doc_type,
        webhook_url=webhook_url,
        customer_id=customer_id,
    )

    async def run_job():
        try:
            return execute_ocr_pipeline(
                file_path=temp_path,
                doc_type=doc_type,
                expected_data=expected_data,
                job_id=job.job_id,
                customer_id=customer_id,
            )
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    await job_queue.enqueue(job.job_id, run_job)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job.job_id,
            "status": "pending",
            "doc_type": doc_type,
            "created_at": job.created_at,
            "poll_url": f"/ocr/jobs/{job.job_id}",
        },
    )


@app.get("/ocr/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    auth: dict = Depends(authenticate_request),
):
    """Poll the status and result of an async OCR job."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    return {
        "job_id": job.job_id,
        "doc_type": job.doc_type,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "result": job.result,
        "error": job.error,
    }


@app.post("/auth/token")
async def issue_token(
    client_id: str = Form(...),
    client_secret: str = Form(...),
):
    """
    Mint short-lived JWT Bearer token for registered clients.
    Rejects with 401 Unauthorized if client_id or client_secret is invalid.
    """
    if not verify_client_credentials(client_id, client_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=client_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": 30,
    }



@app.get("/health")
@app.get("/api/health")
async def health():
    """Health check endpoint reporting operational status, active OCR engine, storage, and auth state."""
    engine_info = get_ocr_engine_info()
    storage_health = document_store.check_storage_health()
    ollama_health = ollama_ai.check_ollama_health()
    enc_avail = encryption.is_encryption_available()
    supa_health = supabase_client.check_supabase_health()

    logging_utils.log_event(
        logger,
        logging.INFO,
        event="health_check",
        status="healthy",
        storage="healthy" if storage_health.get("healthy") else "degraded",
        encryption="enabled" if enc_avail else "disabled",
        supabase=supa_health.get("status", "unconfigured"),
    )

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "ocr_engine": engine_info["active_engine"],
        "ocr_backend": engine_info["active_engine"],
        "ocr_engine_status": engine_info["status"],
        "auth_enabled": is_auth_enabled(),
        "auth_mode": get_auth_mode(),
        "storage": "healthy" if storage_health.get("healthy") else "degraded",
        "encryption": "enabled" if enc_avail else "disabled",
        "ollama": "ready" if ollama_health.get("model_installed") else ("running" if ollama_health.get("reachable") else "offline"),
        "supabase": supa_health.get("status", "unconfigured"),
    }


@app.get("/ready")
@app.get("/api/ready")
async def readiness_probe():
    """
    Production readiness probe evaluating all critical system components:
    - RapidOCR engine
    - Storage writeability
    - Document encryption key
    - Local Ollama service & model
    - Supabase connectivity (if configured)
    Returns HTTP 200 if core services are ready.
    """
    ocr_info = get_ocr_engine_info()
    rapidocr_ok = ocr_info.get("status") in ("ready", "mock_ready", "active")

    storage_health = document_store.check_storage_health()
    storage_ok = bool(storage_health.get("healthy"))

    enc_ok = encryption.is_encryption_available()

    ollama_health = ollama_ai.check_ollama_health()
    ollama_ok = bool(ollama_health.get("reachable"))
    ollama_model_ok = bool(ollama_health.get("model_installed"))

    supa_health = supabase_client.check_supabase_health()
    supa_storage = supabase_client.check_storage_health()

    core_ok = rapidocr_ok and storage_ok and enc_ok
    all_ok = core_ok and ollama_ok and ollama_model_ok

    status_str = "ok" if all_ok else ("degraded" if core_ok else "error")

    response_data = {
        "status": status_str,
        "ready": core_ok,
        "checks": {
            "rapidocr": rapidocr_ok,
            "storage": storage_ok,
            "encryption_key": enc_ok,
            "ollama": ollama_ok,
            "ollama_model": ollama_model_ok,
            "supabase": supa_health.get("status", "unconfigured"),
            "supabase_storage": supa_storage.get("status", "unconfigured"),
        },
        "details": {
            "ocr_engine": ocr_info.get("active_engine", "RapidOCR"),
            "ollama_host": ollama_ai.get_ollama_host(),
            "ollama_model": ollama_ai.get_ollama_model(),
        },
    }

    if not core_ok:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response_data)
    return JSONResponse(status_code=status.HTTP_200_OK, content=response_data)


@app.get("/auth-status")
@app.get("/api/auth-status")
async def auth_status_endpoint():
    """
    Public unauthenticated endpoint returning current authentication configuration.
    Enables frontend client to dynamically adjust its authentication gating at runtime.
    """
    return {
        "auth_enabled": is_auth_enabled(),
        "auth_mode": get_auth_mode(),
    }


@app.get("/engine-info")
@app.get("/api/engine-info")
async def engine_info_endpoint():
    """Returns detailed information about active and configured OCR engine."""
    return get_ocr_engine_info()



# ==============================================================================
# Web Application & Dashboard REST APIs
# ==============================================================================

SUPPORTED_DOC_TYPES = [
    {"id": "auto", "name": "Auto Detect", "category": "General"},
    {"id": "pan", "name": "PAN Card", "category": "Identity"},
    {"id": "aadhaar", "name": "Aadhaar Card", "category": "Identity"},
    {"id": "cancelled_cheque", "name": "Cancelled Cheque", "category": "Financial"},
    {"id": "bank_statement", "name": "Bank Statement", "category": "Financial"},
    {"id": "salary_slip", "name": "Salary Slip", "category": "Financial"},
    {"id": "utility_bill", "name": "Utility Bill", "category": "Utility"},
    {"id": "udyam", "name": "Udyam Certificate", "category": "Business"},
    {"id": "fssai", "name": "FSSAI License", "category": "Business"},
    {"id": "shop_establishment", "name": "Shop & Establishment", "category": "Business"},
    {"id": "passport", "name": "Passport", "category": "Identity"},
    {"id": "voter_id", "name": "Voter ID", "category": "Identity"},
    {"id": "driving_licence", "name": "Driving Licence", "category": "Identity"},
    {"id": "itr", "name": "ITR Ack", "category": "Tax"},
    {"id": "gst_certificate", "name": "GST Certificate", "category": "Business"},
    {"id": "certificate_of_incorporation", "name": "Certificate of Incorporation", "category": "Business"},
    {"id": "partnership_deed", "name": "Partnership Deed", "category": "Legal"},
    {"id": "rent_agreement", "name": "Rent Agreement", "category": "Legal"},
    {"id": "form_16", "name": "Form 16", "category": "Tax"},
    {"id": "bank_passbook", "name": "Bank Passbook", "category": "Financial"},
    {"id": "property_tax_receipt", "name": "Property Tax Receipt", "category": "Tax"},
    {"id": "iec_certificate", "name": "IEC Certificate", "category": "Business"},
    {"id": "income_certificate", "name": "Income Certificate", "category": "Certificate"},
]

SUPPORTED_DOC_TYPE_IDS = {t["id"] for t in SUPPORTED_DOC_TYPES if t["id"] != "auto"}


@app.get("/api/supported-types")
async def get_supported_types():
    """Returns list of supported document types for UI dropdowns and badges."""
    return SUPPORTED_DOC_TYPES


@app.get("/api/auth/me")
async def get_auth_me_endpoint(
    auth: UserProfile = Depends(get_current_user),
):
    """
    Returns current authenticated user identity and role from Supabase Auth & profiles.
    Never exposes passwords, tokens, or system secrets.
    """
    return {
        "id": auth.get("user_id") or auth.get("sub"),
        "email": auth.get("email"),
        "full_name": auth.get("full_name"),
        "role": auth.get("role", "user"),
    }


@app.get("/api/stats")
async def get_dashboard_stats(
    auth: dict = Depends(authenticate_request),
):
    """Retrieve aggregate document statistics scoped to the authenticated user."""
    user_id = auth.get("user_id") or auth.get("sub")
    if supabase_client.is_supabase_configured() and user_id:
        return document_repository.get_user_statistics(user_id)
    return document_store.get_stats(user_id=user_id)


@app.get("/api/documents")
async def list_documents_endpoint(
    search: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    ocr_required: Optional[bool] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    auth: dict = Depends(authenticate_request),
):
    """Retrieve paginated list of documents owned exclusively by the authenticated user."""
    user_id = auth.get("user_id") or auth.get("sub")

    if supabase_client.is_supabase_configured() and user_id:
        page = (offset // limit) + 1
        supa_res = document_repository.get_user_documents(
            user_id=user_id,
            page=page,
            limit=limit,
            doc_type=doc_type,
            status=status,
            search=search,
        )
        return {
            "items": supa_res.get("documents", []),
            "total": supa_res.get("total", 0),
            "limit": limit,
            "offset": offset,
        }

    items = document_store.list_documents(
        status_filter=status,
        ocr_required_filter=ocr_required,
        doc_type_filter=doc_type,
        search=search,
        limit=limit,
        offset=offset,
        user_id=user_id,
    )
    all_filtered = document_store.list_documents(
        status_filter=status,
        ocr_required_filter=ocr_required,
        doc_type_filter=doc_type,
        search=search,
        limit=10000,
        offset=0,
        user_id=user_id,
    )
    return {
        "items": items,
        "total": len(all_filtered),
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/documents/{doc_id}")
async def get_document_endpoint(
    doc_id: str,
    auth: dict = Depends(authenticate_request),
):
    """Retrieve details of a document, strictly verifying owner authorization."""
    user_id = auth.get("user_id") or auth.get("sub")

    if supabase_client.is_supabase_configured() and user_id:
        doc = document_repository.get_user_document(user_id, doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{doc_id}' not found",
            )
        return doc

    doc = document_store.get_document(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found",
        )
    # Check ownership: User A cannot access User B's document
    doc_user = doc.get("user_id")
    if doc_user and user_id and doc_user != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found",
        )
    return doc


@app.get("/api/documents/{doc_id}/file")
async def get_document_file_endpoint(
    doc_id: str,
    download: bool = Query(False),
    auth: dict = Depends(authenticate_request),
):
    """Serve decrypted document bytes for owner inline preview or download."""
    user_id = auth.get("user_id") or auth.get("sub")

    if supabase_client.is_supabase_configured() and user_id:
        payload = document_repository.get_document_file_payload(user_id, doc_id)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{doc_id}' not found",
            )
        decrypted_bytes, filename, media_type = payload
        disposition = "attachment" if download else "inline"
        return Response(
            content=decrypted_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'{disposition}; filename="{filename}"'
            },
        )

    doc = document_store.get_document(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found",
        )
    doc_user = doc.get("user_id")
    if doc_user and user_id and doc_user != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found",
        )

    try:
        decrypted_bytes = document_store.get_document_bytes(doc_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File for document '{doc_id}' not found",
        )
    except DocumentEncryptionKeyMissingError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption service unavailable: server encryption key is not configured.",
        )
    except DocumentDecryptionError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document decryption failed.",
        )

    filename = doc.get("filename") or doc.get("original_filename") or "document.bin"
    ext = os.path.splitext(filename)[1].lower() or doc.get("file_type", "").lower()
    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    disposition = "attachment" if download else "inline"
    return Response(
        content=decrypted_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"'
        },
    )


@app.get("/api/documents/{doc_id}/preview")
async def get_document_preview_endpoint(
    doc_id: str,
    auth: dict = Depends(authenticate_request),
):
    """Serve the thumbnail image preview for owner only."""
    user_id = auth.get("user_id") or auth.get("sub")

    # Verify document ownership first
    if supabase_client.is_supabase_configured() and user_id:
        doc = document_repository.get_user_document(user_id, doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preview for document '{doc_id}' not found",
            )
    else:
        doc = document_store.get_document(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preview for document '{doc_id}' not found",
            )
        doc_user = doc.get("user_id")
        if doc_user and user_id and doc_user != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preview for document '{doc_id}' not found",
            )

    preview_path = document_store.get_document_preview_path(doc_id)
    if not preview_path or not os.path.exists(preview_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preview for document '{doc_id}' not found",
        )
    return FileResponse(preview_path, media_type="image/png")


@app.delete("/api/documents/clear")
async def clear_all_documents_endpoint(
    auth: dict = Depends(authenticate_request),
):
    """Permanently delete all documents belonging exclusively to the authenticated user."""
    user_id = auth.get("user_id") or auth.get("sub")
    if supabase_client.is_supabase_configured() and user_id:
        deleted_count = document_repository.clear_user_documents(user_id)
    else:
        deleted_count = document_store.clear_all_documents(user_id=user_id)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": "All documents have been deleted.",
    }


@app.post("/api/documents/cleanup")
async def manual_cleanup_endpoint(
    auth: dict = Depends(authenticate_request),
    _rate_limit: None = Depends(rate_limit_cleanup),
):
    """Run document retention and storage cleanup immediately."""
    result = retention_service.run_cleanup()
    return {
        "success": True,
        "deleted_count": result.get("deleted_count", 0),
    }


@app.delete("/api/documents/{doc_id}")
async def delete_document_endpoint(
    doc_id: str,
    auth: dict = Depends(authenticate_request),
):
    """Permanently delete a document owned by the authenticated user."""
    user_id = auth.get("user_id") or auth.get("sub")
    if supabase_client.is_supabase_configured() and user_id:
        deleted = document_repository.delete_user_document(user_id, doc_id)
    else:
        doc = document_store.get_document(doc_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{doc_id}' not found",
            )
        doc_user = doc.get("user_id")
        if doc_user and user_id and doc_user != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{doc_id}' not found",
            )
        deleted = document_store.delete_document(doc_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found",
        )
    return {"success": True, "id": doc_id, "message": "Document deleted successfully"}


def persist_document(
    file_bytes: bytes,
    filename: str,
    result_data: Dict[str, Any],
    thumbnail_bytes: Optional[bytes] = None,
    user_id: Optional[str] = None,
    mode: str = "offline",
) -> Dict[str, Any]:
    """
    Persist document record:
    - If Supabase is configured and user_id is present: writes to Supabase PostgreSQL & Private Storage via document_repository.
    - If Supabase write fails: raises HTTPException 503 (Fail-Fast as per user decision).
    - Otherwise: writes to local encrypted document_store.
    """
    user_id = user_id or os.getenv("DEFAULT_DEV_USER_ID", "00000000-0000-0000-0000-000000000001")
    ext = os.path.splitext(filename)[1].lower() or ".bin"

    if supabase_client.is_supabase_configured() and user_id:
        try:
            return document_repository.create_document(
                user_id=user_id,
                original_filename=filename,
                file_bytes=file_bytes,
                file_type=ext,
                doc_type=result_data.get("doc_type") or result_data.get("document_type"),
                mode=mode,
                status=result_data.get("status", "completed"),
                ocr_result={
                    "raw_text": result_data.get("extracted_text", ""),
                    "detected_type": result_data.get("doc_type"),
                    "confidence": result_data.get("confidence", 1.0),
                    "page_count": result_data.get("pages", 1),
                },
                extracted_fields=result_data.get("extracted_fields") or result_data.get("fields", {}),
                ai_analysis=result_data.get("ai_analysis"),
                verification_status=result_data.get("verification_status") or result_data.get("status"),
                review_required=result_data.get("review_required", False),
                risk_score=result_data.get("risk_score", 0.0),
                suspicious_signals=result_data.get("suspicious_signals", []),
                human_review_reason=result_data.get("human_review_reason"),
                verified_by_ai=result_data.get("verified_by_ai", False),
            )
        except Exception as ex:
            logger.error(f"Failed to persist document to Supabase: {ex}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database or storage service unavailable. Please try again.",
            )

    return document_store.save_document(
        file_bytes=file_bytes,
        filename=filename,
        result_data=result_data,
        thumbnail_bytes=thumbnail_bytes,
        user_id=user_id,
    )


@app.post("/api/upload")
async def upload_document_endpoint(
    file: UploadFile = File(...),
    mode: Optional[str] = Form("offline"),
    doc_type: Optional[str] = Form(None),
    expected_data: Optional[str] = Form(None),
    auth: UserProfile = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit_upload),
):
    """
    Direct browser upload endpoint:
    - If mode == "ai": passes document to local Ollama (qwen2.5vl:3b) for visual reasoning and structured field extraction.
    - If mode == "offline": executes the existing RapidOCR / text layer pipeline for predefined document types.
    """
    req_start = time.time()
    file_bytes = await file.read()
    clean_filename, ext = validate_upload_security(file, file_bytes)
    filename = clean_filename

    temp_path = os.path.join(TEMP_DIR, f"web_upload_{uuid.uuid4()}{ext}")
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    try:
        # ====================================================================
        # AI Mode Branch: Local Ollama + Qwen2.5-VL:3B Document Understanding
        # ====================================================================
        if (mode or "").strip().lower() == "ai":
            health = ollama_ai.check_ollama_health()
            if not health.get("reachable"):
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"error": "Ollama server is not running."},
                )
            if not health.get("model_installed"):
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"error": health.get("error", "Model 'qwen2.5vl:3b' is missing. Please run: ollama pull qwen2.5vl:3b")},
                )

            # Extract text first: check PDF text layer first, fallback to OCR
            logging_utils.log_event(logger, logging.INFO, event="ocr_started", doc_type="ai_analyzed", filename=filename)
            ocr_t0 = time.time()
            if ext == ".pdf":
                doc_res = ocr_engine.process_pdf(temp_path)
            else:
                doc_res = ocr_engine.process_file(temp_path)
            ocr_dur_ms = int((time.time() - ocr_t0) * 1000)
            logging_utils.log_event(
                logger,
                logging.INFO,
                event="ocr_completed",
                duration_ms=ocr_dur_ms,
                pages=len(doc_res.pages) if doc_res.pages else 1,
                status="success",
            )

            extracted_text = doc_res.full_text or ""

            ai_res = ollama_ai.analyze_document(temp_path, filename=filename, ocr_text=extracted_text)
            if "error" in ai_res:
                err_code = (
                    status.HTTP_503_SERVICE_UNAVAILABLE
                    if "not running" in ai_res["error"] or "missing" in ai_res["error"]
                    else status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                return JSONResponse(status_code=err_code, content=ai_res)

            thumb_bytes = render_thumbnail(temp_path, is_pdf=(ext == ".pdf"))
            evidence_list = ai_res.get("evidence") or ai_res.get("reasoning", [])

            # Guarantee canonical structured fields from shared classifier are retained
            canonical_info = ai_service.classify_document_content(extracted_text, filename=filename)
            canonical_fields = canonical_info.get("extracted_fields") or {}
            merged_fields = dict(canonical_fields)
            for k, v in ai_res.get("extracted_fields", {}).items():
                if v and str(v).strip() and str(v).strip().lower() != "none" and (k not in merged_fields or not merged_fields[k]):
                    merged_fields[k] = v
            ai_res["extracted_fields"] = merged_fields

            # Authenticity Assessment (AI Mode)
            ai_auth = ai_res.get("authenticity") or ai_res.get("authenticity_assessment")
            authenticity = authenticity_manager.assess_document(
                doc_type="ai_analyzed",
                ocr_lines=doc_res.pages[0].lines if doc_res.pages else [],
                extracted_fields=merged_fields,
                raw_text=extracted_text,
                ai_authenticity_result=ai_auth,
                is_supported=True,
            )

            result_payload = {
                "doc_type": "ai_analyzed",
                "document_type": ai_res.get("document_type", "Unknown Document"),
                "ocr_required": getattr(doc_res, "ocr_required", False),
                "text_source": "ollama_qwen2.5vl",
                "status": "completed",
                "confidence": 0.95 if ai_res.get("confidence") == "high" else (0.80 if ai_res.get("confidence") == "medium" else 0.50),
                "pages": len(doc_res.pages) if doc_res.pages else 1,
                "reason": None,
                "extracted_fields": ai_res.get("extracted_fields", {}),
                "field_confidences": {},
                "extracted_text": extracted_text,
                "ai_analysis": ai_res,
                "verification_status": authenticity["verification_status"],
                "risk_score": authenticity["risk_score"],
                "review_required": authenticity["review_required"],
                "suspicious_signals": authenticity["suspicious_signals"],
                "human_review_reason": authenticity["human_review_reason"],
                "verified_by_ai": True,
            }

            saved_record = persist_document(
                file_bytes=file_bytes,
                filename=filename,
                result_data=result_payload,
                thumbnail_bytes=thumb_bytes,
                user_id=auth.get("user_id") or auth.get("sub"),
                mode="ai",
            )

            logging_utils.log_event(
                logger,
                logging.INFO,
                event="document_processed",
                document_type=ai_res.get("document_type", "Unknown Document"),
                ocr_engine="RapidOCR",
                ai_model="qwen2.5vl:3b",
                processing_time_ms=int((time.time() - req_start) * 1000),
                verification_status=authenticity["verification_status"],
                risk_score=authenticity["risk_score"],
                status="success",
            )

            return {
                "document_id": saved_record["id"],
                "filename": saved_record["filename"],
                "document_type": ai_res.get("document_type", "Unknown Document"),
                "confidence": ai_res.get("confidence", "high"),
                "summary": ai_res.get("summary", ""),
                "evidence": evidence_list,
                "reasoning": evidence_list,
                "extracted_fields": ai_res.get("extracted_fields", {}),
                "file_url": saved_record["file_url"],
                "preview_url": saved_record.get("preview_url"),
                "file_size": saved_record["file_size"],
                "pages": saved_record["pages"],
                "text_source": "ollama_qwen2.5vl",
                "extracted_text": extracted_text,
                "processing_time_seconds": ai_res.get("processing_time_seconds"),
                "model_used": ai_res.get("model_used", "qwen2.5vl:3b"),
                "is_local_ai": True,
                "verification_status": authenticity["verification_status"],
                "risk_score": authenticity["risk_score"],
                "review_required": authenticity["review_required"],
                "suspicious_signals": authenticity["suspicious_signals"],
                "human_review_reason": authenticity["human_review_reason"],
                "verified_by_ai": True,
            }

        # ====================================================================
        # Offline Mode Branch (RapidOCR + ONNX) - 100% Unchanged
        # ====================================================================
        requested_type = (doc_type or "").strip().lower()
        init_langs = get_languages_for_doc_type(requested_type) if requested_type and requested_type != "auto" else None
        logging_utils.log_event(logger, logging.INFO, event="ocr_started", doc_type=requested_type or "auto", filename=filename)
        ocr_t0 = time.time()
        try:
            if ext == ".pdf":
                doc_res = ocr_engine.process_pdf(temp_path, languages=init_langs)
            else:
                doc_res = ocr_engine.process_file(temp_path, languages=init_langs)
            ocr_dur_ms = int((time.time() - ocr_t0) * 1000)
            logging_utils.log_event(
                logger,
                logging.INFO,
                event="ocr_completed",
                duration_ms=ocr_dur_ms,
                pages=len(doc_res.pages) if doc_res.pages else 1,
                status="success",
            )
        except Exception as ex:
            ocr_dur_ms = int((time.time() - ocr_t0) * 1000)
            logging_utils.log_event(
                logger,
                logging.ERROR,
                event="ocr_completed",
                duration_ms=ocr_dur_ms,
                status="failed",
            )
            logger.error("OCR extraction exception in /api/ingest: %s", ex, exc_info=True)
            doc_res = OCRDocumentResult(
                pages=[],
                full_text="",
                average_confidence=0.0,
                ocr_required=True,
                text_source="none",
                engine_error=f"ocr_extraction_failed: {str(ex)}",
            )

        ocr_required = getattr(doc_res, "ocr_required", True)
        text_source = getattr(doc_res, "text_source", "none")

        has_text = bool(doc_res.full_text and doc_res.full_text.strip())
        has_lines = any(bool(p.lines) for p in doc_res.pages) if doc_res.pages else False
        has_engine_error = bool(getattr(doc_res, "engine_error", None))

        raw_fields: Dict[str, Any] = {}
        sanitized_fields: Dict[str, Any] = {}
        field_confs: Dict[str, float] = {}
        checksum_valid = True
        checksum_reason: Optional[str] = None
        cross_check_results = None

        if has_engine_error or not has_text or doc_res.average_confidence == 0.0 or not has_lines:
            failure_detail = getattr(doc_res, "engine_error", None) or "OCR engine returned no text or zero confidence: I couldn't extract enough text to identify this document."
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=failure_detail,
            )

        # 2. Text Normalization & Shared Content Classification
        doc_res.full_text = normalize_ocr_text(doc_res.full_text)
        classification = classify_document_content(doc_res.full_text)

        if not requested_type or requested_type == "auto":
            resolved_type = classification.get("doc_type", "unknown")
            # If resolved_type uses Devanagari passes and the initial pass was English-only,
            # and OCR was actually required, execute the bilingual pass now
            auto_langs = get_languages_for_doc_type(resolved_type)
            if auto_langs and len(auto_langs) > 1:
                dev_chars_now = len(re.findall(r"[\u0900-\u097F]", doc_res.full_text))
                if doc_res.ocr_required or dev_chars_now < 10:
                    try:
                        if ext == ".pdf":
                            doc_res = ocr_engine.process_pdf(temp_path, languages=auto_langs)
                        else:
                            doc_res = ocr_engine.process_file(temp_path, languages=auto_langs)
                        doc_res.full_text = normalize_ocr_text(doc_res.full_text)
                        classification = classify_document_content(doc_res.full_text)
                        resolved_type = classification.get("doc_type", resolved_type)
                    except Exception as ex:
                        logger.warning("Secondary Devanagari pass in /api/upload failed: %s", ex)
            elif resolved_type == "unknown" and doc_res.ocr_required:
                try:
                    fallback_langs = ["en", "hi", "mr"]
                    if ext == ".pdf":
                        retry_res = ocr_engine.process_pdf(temp_path, languages=fallback_langs)
                    else:
                        retry_res = ocr_engine.process_file(temp_path, languages=fallback_langs)
                    retry_res.full_text = normalize_ocr_text(retry_res.full_text)
                    retry_classification = classify_document_content(retry_res.full_text)
                    if retry_classification["doc_type"] != "unknown":
                        doc_res = retry_res
                        classification = retry_classification
                        resolved_type = retry_classification["doc_type"]
                    elif len(re.findall(r"[\u0900-\u097F]", retry_res.full_text)) > len(re.findall(r"[\u0900-\u097F]", doc_res.full_text)):
                        doc_res = retry_res
                except Exception as ex:
                    logger.warning("Regional fallback pass in /api/upload failed: %s", ex)
        else:
            resolved_type = requested_type

        meta = DOC_TYPE_METADATA.get(resolved_type, {})
        detected_doc_title = classification.get("document_type") or meta.get("name") or (
            resolved_type.replace("_", " ").title() if resolved_type != "unknown" else "Unknown Document"
        )
        detected_issuer = classification.get("issuer") or meta.get("issuer")

        first_page_img: Optional[Image.Image] = None
        if doc_res.pages and doc_res.pages[0].image:
            first_page_img = doc_res.pages[0].image
        elif ext == ".pdf":
            pdf_imgs = render_pdf_pages_to_images(temp_path)
            if pdf_imgs:
                first_page_img = pdf_imgs[0]
        else:
            try:
                with Image.open(temp_path) as img:
                    first_page_img = img.convert("RGB").copy()
            except Exception:
                pass

        # 3. Field Extraction & Verification
        if resolved_type != "unknown":
            try:
                raw_fields, field_confs = extract_document_fields_raw(resolved_type, doc_res)
                if resolved_type == "cancelled_cheque":
                    ocr_func = None
                    if first_page_img:
                        ocr_func = lambda img: (ocr_engine.process_image(img).full_text, None)
                    micr_data = extract_micr_from_cheque(
                        cheque_img=first_page_img or Image.new("RGB", (100, 100)),
                        ocr_func=ocr_func,
                        ocr_full_text=doc_res.full_text,
                        full_page_fields=raw_fields,
                    )
                    raw_fields["micr_line"] = micr_data.get("micr_line")
                    raw_fields["micr_confidence"] = micr_data.get("micr_confidence", "low")
                    if micr_data.get("micr_code"):
                        raw_fields["micr_code"] = micr_data["micr_code"]
                    if micr_data.get("account_number_masked"):
                        raw_fields["micr_account_number_masked"] = micr_data["account_number_masked"]
                    if micr_data.get("tran_code"):
                        raw_fields["tran_code"] = micr_data["tran_code"]
                    if micr_data.get("cheque_number") and not raw_fields.get("cheque_number"):
                        raw_fields["cheque_number"] = micr_data["cheque_number"]
                    if "micr_match" in micr_data:
                        raw_fields["micr_match"] = micr_data["micr_match"]
                    if micr_data.get("micr_disagreements"):
                        raw_fields["micr_disagreements"] = micr_data["micr_disagreements"]

                checksum_valid, checksum_reason = validate_document_checksums(resolved_type, raw_fields)
                # 4. Optional Cross-check on raw unmasked fields
                if expected_data:
                    try:
                        expected_dict = json.loads(expected_data)
                        if isinstance(expected_dict, dict):
                            cross_check_results = perform_cross_check(raw_fields, expected_dict)
                    except Exception:
                        pass
                sanitized_fields, field_confs = sanitize_extracted_fields(resolved_type, raw_fields, field_confs)

                # Context-specific issuer detection
                if resolved_type == "bank_statement" and sanitized_fields.get("bank_name"):
                    detected_issuer = sanitized_fields["bank_name"]
                elif resolved_type == "salary_slip" and sanitized_fields.get("employer_name"):
                    detected_issuer = sanitized_fields["employer_name"]
                elif resolved_type == "utility_bill" and sanitized_fields.get("utility_provider"):
                    detected_issuer = sanitized_fields["utility_provider"]
                elif resolved_type == "income_certificate" and sanitized_fields.get("issuing_authority"):
                    detected_issuer = sanitized_fields["issuing_authority"]
            except Exception as ex:
                checksum_valid = False
                checksum_reason = f"Extraction error: {str(ex)}"
        else:
            sanitized_fields = {"document_type": "Unknown Document"}

        # 5. Authenticity Assessment (Offline Mode)
        qr_fields = {}
        if first_page_img:
            try:
                qrs = decode_qr_from_image(first_page_img)
                for q in qrs:
                    qr_fields.update(parse_qr_payload(resolved_type, q))
            except Exception:
                pass

        authenticity = authenticity_manager.assess_document(
            doc_type=resolved_type,
            image=first_page_img,
            ocr_lines=doc_res.pages[0].lines if doc_res.pages else [],
            extracted_fields=raw_fields,
            raw_text=doc_res.full_text,
            qr_fields=qr_fields,
            is_supported=(resolved_type != "unknown"),
        )

        doc_status = determine_document_status(
            checksum_valid=checksum_valid,
            average_confidence=doc_res.average_confidence,
            vault_mode=True,
        )

        # 6. Generate Thumbnail Preview
        thumb_bytes = render_thumbnail(temp_path, is_pdf=(ext == ".pdf"))

        # 7. Package Result Data (Strictly sanitized fields, no raw PII)
        result_payload = {
            "doc_type": resolved_type,
            "document_type": detected_doc_title,
            "issuer": detected_issuer,
            "classification": classification,
            "evidence": classification.get("evidence", []),
            "ocr_required": ocr_required,
            "text_source": text_source,
            "status": doc_status,
            "confidence": doc_res.average_confidence,
            "pages": len(doc_res.pages),
            "reason": checksum_reason,
            "extracted_fields": sanitized_fields,
            "field_confidences": field_confs,
            "extracted_text": doc_res.full_text,
            "checksum_valid": checksum_valid,
            "checksum_reason": checksum_reason,
            "cross_check": cross_check_results,
            "verification_status": authenticity["verification_status"],
            "risk_score": authenticity["risk_score"],
            "review_required": authenticity["review_required"],
            "suspicious_signals": authenticity["suspicious_signals"],
            "human_review_reason": authenticity["human_review_reason"],
            "verified_by_ai": False,
        }

        # 8. Persist to Document Store
        saved_record = persist_document(
            file_bytes=file_bytes,
            filename=filename,
            result_data=result_payload,
            thumbnail_bytes=thumb_bytes,
            user_id=auth.get("user_id") or auth.get("sub"),
            mode="offline",
        )

        logging_utils.log_event(
            logger,
            logging.INFO,
            event="document_processed",
            document_type=detected_doc_title,
            ocr_engine="RapidOCR",
            ai_model="none",
            processing_time_ms=int((time.time() - req_start) * 1000),
            verification_status=authenticity["verification_status"],
            risk_score=authenticity["risk_score"],
            status="success",
        )

        return saved_record
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass



# ==============================================================================
# Dedicated Operational Modes: Offline Mode & AI Mode Endpoints
# ==============================================================================

class AiChatPayload(BaseModel):
    document_id: Optional[str] = None
    message: str
    history: Optional[List[Dict[str, str]]] = None


@app.get("/api/mode/ai/active")
async def get_active_document_endpoint(
    auth: dict = Depends(authenticate_request),
):
    """Returns metadata for the currently active document in the session."""
    active_doc = document_store.get_active_document()
    if not active_doc:
        return {"active": False, "document": None}
    return {
        "active": True,
        "document_id": active_doc["id"],
        "filename": active_doc.get("filename"),
        "document_type": active_doc.get("document_type"),
        "summary": active_doc.get("summary") or (active_doc.get("ai_analysis") or {}).get("summary"),
        "confidence": active_doc.get("confidence"),
    }


@app.post("/api/mode/ai/active/clear")
async def clear_active_document_endpoint(
    auth: dict = Depends(authenticate_request),
):
    """Explicitly clears the active document session."""
    document_store.clear_active_document()
    return {"success": True, "message": "Active document session cleared."}


@app.get("/api/ollama/status")
async def get_ollama_status():
    """Returns local Ollama server and Qwen2.5-VL model health status."""
    return ollama_ai.check_ollama_health()


@app.get("/api/mode/ai/status")
async def get_ai_mode_status(
    auth: dict = Depends(authenticate_request),
):
    """Returns runtime AI provider configuration status and model metadata."""
    res = ai_service.check_ai_status()
    try:
        res["ollama"] = ollama_ai.check_ollama_health()
    except Exception:
        pass
    return res


class AiConfigUpdatePayload(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    fallback_on_error: Optional[bool] = None


class AiTestConnectionPayload(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@app.get("/api/ai/config")
async def get_ai_config_endpoint(
    auth: dict = Depends(authenticate_request),
):
    """
    Returns public safe AI provider configuration status.
    CRITICAL: Never returns API keys, authorization headers, or secret tokens.
    """
    return ai_providers.ai_provider_manager.get_safe_config()


@app.post("/api/ai/config")
async def update_ai_config_endpoint(
    payload: AiConfigUpdatePayload,
    auth: dict = Depends(authenticate_request),
):
    """
    Updates runtime AI provider configuration securely on backend.
    Enforces admin role: normal users receive HTTP 403 Forbidden.
    Never stores keys on frontend, never returns secret keys in response.
    """
    if auth.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify global AI provider configuration.",
        )

    ai_providers.ai_provider_manager.update_config(
        provider=payload.provider,
        api_key=payload.api_key,
        model=payload.model,
        base_url=payload.base_url,
        fallback_on_error=payload.fallback_on_error,
    )
    return ai_providers.ai_provider_manager.get_safe_config()


@app.post("/api/ai/test-connection")
async def test_ai_connection_endpoint(
    payload: Optional[AiTestConnectionPayload] = None,
    auth: dict = Depends(authenticate_request),
):
    """
    Tests connectivity to candidate or currently configured AI provider.
    Enforces admin role for testing candidate configurations.
    Returns safe test result (success, provider, model, message, latency_ms).
    Never exposes secrets in response.
    """
    if auth.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to test AI provider connections.",
        )

    candidate = payload.model_dump() if payload else None
    return await ai_providers.ai_provider_manager.test_connection(candidate)


@app.post("/api/mode/offline")
async def process_offline_mode_endpoint(
    file: UploadFile = File(...),
    doc_type: Optional[str] = Form(None),
    expected_data: Optional[str] = Form(None),
    auth: UserProfile = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit_upload),
):
    """
    Offline Mode Document Processing Endpoint:
    - Strictly for the 22 predefined document types supported by the application.
    - Uses local PaddleOCR / text-layer extraction pipeline (zero external AI API requirement).
    - If uploaded document does not match a supported document type, returns a clear rejection:
      "This document type is not supported in Offline Mode. Please use AI Mode for unknown documents."
    - If supported: extracts fields, validates checksums, sanitizes PII, and stores in vault.
    """
    req_start = time.time()
    file_bytes = await file.read()
    clean_filename, ext = validate_upload_security(file, file_bytes)
    filename = clean_filename

    temp_path = os.path.join(TEMP_DIR, f"offline_upload_{uuid.uuid4()}{ext}")
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    try:
        # 1. Text Layer Detection & OCR
        requested_type = (doc_type or "").strip().lower()
        init_langs = get_languages_for_doc_type(requested_type) if requested_type and requested_type != "auto" else None
        logging_utils.log_event(logger, logging.INFO, event="ocr_started", doc_type=requested_type or "auto", filename=filename)
        ocr_t0 = time.time()
        try:
            if ext == ".pdf":
                doc_res = ocr_engine.process_pdf(temp_path, languages=init_langs)
            else:
                doc_res = ocr_engine.process_file(temp_path, languages=init_langs)
            ocr_dur_ms = int((time.time() - ocr_t0) * 1000)
            logging_utils.log_event(
                logger,
                logging.INFO,
                event="ocr_completed",
                duration_ms=ocr_dur_ms,
                pages=len(doc_res.pages) if doc_res.pages else 1,
                status="success",
            )
        except Exception as ex:
            ocr_dur_ms = int((time.time() - ocr_t0) * 1000)
            logging_utils.log_event(
                logger,
                logging.ERROR,
                event="ocr_completed",
                duration_ms=ocr_dur_ms,
                status="failed",
            )
            logger.error("OCR extraction exception in /api/mode/offline: %s", ex, exc_info=True)
            doc_res = OCRDocumentResult(
                pages=[],
                full_text="",
                average_confidence=0.0,
                ocr_required=True,
                text_source="none",
                engine_error=f"ocr_extraction_failed: {str(ex)}",
            )

        ocr_required = getattr(doc_res, "ocr_required", True)
        text_source = getattr(doc_res, "text_source", "none")

        has_text = bool(doc_res.full_text and doc_res.full_text.strip())
        has_lines = any(bool(p.lines) for p in doc_res.pages) if doc_res.pages else False
        has_engine_error = bool(getattr(doc_res, "engine_error", None))

        if has_engine_error or not has_text or doc_res.average_confidence == 0.0 or not has_lines:
            failure_detail = getattr(doc_res, "engine_error", None) or "OCR engine returned no text or zero confidence: I couldn't extract enough text to identify this document."
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=failure_detail,
            )

        # 2. Text Normalization & Shared Content Classification
        doc_res.full_text = normalize_ocr_text(doc_res.full_text)
        classification = classify_document_content(doc_res.full_text)

        if not requested_type or requested_type == "auto":
            resolved_type = classification.get("doc_type", "unknown")
            if resolved_type == "unknown" and doc_res.ocr_required:
                try:
                    fallback_langs = ["en", "hi", "mr"]
                    if ext == ".pdf":
                        retry_res = ocr_engine.process_pdf(temp_path, languages=fallback_langs)
                    else:
                        retry_res = ocr_engine.process_file(temp_path, languages=fallback_langs)
                    retry_res.full_text = normalize_ocr_text(retry_res.full_text)
                    retry_classification = classify_document_content(retry_res.full_text)
                    if retry_classification["doc_type"] != "unknown":
                        doc_res = retry_res
                        classification = retry_classification
                        resolved_type = retry_classification["doc_type"]
                    elif len(re.findall(r"[\u0900-\u097F]", retry_res.full_text)) > len(re.findall(r"[\u0900-\u097F]", doc_res.full_text)):
                        doc_res = retry_res
                except Exception as ex:
                    logger.warning("Regional fallback pass in /api/mode/offline failed: %s", ex)
        else:
            resolved_type = requested_type

        # 3. Check against supported document types & EXTRACTOR_REGISTRY
        if resolved_type not in SUPPORTED_DOC_TYPE_IDS or resolved_type == "unknown" or resolved_type not in EXTRACTOR_REGISTRY:
            # Unsupported / Unknown document in Offline Mode:
            # 100% OCR is performed, text preserved, thumbnail generated, and stored in Document Vault
            thumb_bytes = render_thumbnail(temp_path, is_pdf=(ext == ".pdf"))
            doc_status = "low_confidence" if doc_res.average_confidence < 0.6 else "completed"
            authenticity = authenticity_manager.assess_document(
                doc_type="unknown",
                is_supported=False,
            )
            result_payload = {
                "doc_type": "unknown",
                "document_type": "Unknown Document",
                "issuer": None,
                "classification": classification,
                "evidence": classification.get("evidence", []),
                "ocr_required": ocr_required,
                "text_source": text_source,
                "status": doc_status,
                "confidence": doc_res.average_confidence,
                "pages": len(doc_res.pages) if doc_res.pages else 1,
                "reason": "Offline OCR completed successfully. Document is not one of the 22 supported structured types.",
                "extracted_fields": {},
                "fields": {},
                "field_confidences": {},
                "extracted_text": doc_res.full_text,
                "checksum_valid": None,
                "checksum_reason": None,
                "cross_check": None,
                "ocr_completed": True,
                "message": "Offline OCR completed successfully. Use AI Mode for detailed document understanding.",
                "verification_status": "unsupported",
                "risk_score": 0,
                "review_required": False,
                "suspicious_signals": [],
                "human_review_reason": "Unsupported document type.",
                "verified_by_ai": False,
            }
            saved_record = persist_document(
                file_bytes=file_bytes,
                filename=filename,
                result_data=result_payload,
                thumbnail_bytes=thumb_bytes,
                user_id=auth.get("user_id") or auth.get("sub"),
                mode="offline",
            )
            saved_record["supported"] = True
            saved_record["ocr_completed"] = True
            saved_record["message"] = "Offline OCR completed successfully. Use AI Mode for detailed document understanding."
            saved_record["verification_status"] = "unsupported"
            saved_record["risk_score"] = 0
            saved_record["review_required"] = False
            saved_record["suspicious_signals"] = []
            saved_record["human_review_reason"] = "Unsupported document type."
            logging_utils.log_event(
                logger,
                logging.INFO,
                event="document_processed",
                document_type="Unknown Document",
                ocr_engine="RapidOCR",
                ai_model="none",
                processing_time_ms=int((time.time() - req_start) * 1000),
                verification_status="unsupported",
                risk_score=0,
                status="success",
            )
            return saved_record

        meta = DOC_TYPE_METADATA.get(resolved_type, {})
        detected_doc_title = classification.get("document_type") or meta.get("name") or (
            resolved_type.replace("_", " ").title() if resolved_type != "unknown" else "Unknown Document"
        )
        detected_issuer = classification.get("issuer") or meta.get("issuer")

        # 4. Processing for supported document
        first_page_img: Optional[Image.Image] = None
        if doc_res.pages and doc_res.pages[0].image:
            first_page_img = doc_res.pages[0].image
        elif ext == ".pdf":
            pdf_imgs = render_pdf_pages_to_images(temp_path)
            if pdf_imgs:
                first_page_img = pdf_imgs[0]
        else:
            try:
                with Image.open(temp_path) as img:
                    first_page_img = img.convert("RGB").copy()
            except Exception:
                pass

        raw_fields: Dict[str, Any] = {}
        sanitized_fields: Dict[str, Any] = {}
        field_confs: Dict[str, float] = {}
        checksum_valid = True
        checksum_reason: Optional[str] = None
        cross_check_results = None

        try:
            raw_fields, field_confs = extract_document_fields_raw(resolved_type, doc_res)
            if resolved_type == "cancelled_cheque":
                ocr_func = None
                if first_page_img:
                    ocr_func = lambda img: (ocr_engine.process_image(img).full_text, None)
                micr_data = extract_micr_from_cheque(
                    cheque_img=first_page_img or Image.new("RGB", (100, 100)),
                    ocr_func=ocr_func,
                    ocr_full_text=doc_res.full_text,
                    full_page_fields=raw_fields,
                )
                raw_fields["micr_line"] = micr_data.get("micr_line")
                raw_fields["micr_confidence"] = micr_data.get("micr_confidence", "low")
                if micr_data.get("micr_code"):
                    raw_fields["micr_code"] = micr_data["micr_code"]
                if micr_data.get("account_number_masked"):
                    raw_fields["micr_account_number_masked"] = micr_data["account_number_masked"]
                if micr_data.get("tran_code"):
                    raw_fields["tran_code"] = micr_data["tran_code"]
                if micr_data.get("cheque_number") and not raw_fields.get("cheque_number"):
                    raw_fields["cheque_number"] = micr_data["cheque_number"]
                if "micr_match" in micr_data:
                    raw_fields["micr_match"] = micr_data["micr_match"]
                if micr_data.get("micr_disagreements"):
                    raw_fields["micr_disagreements"] = micr_data["micr_disagreements"]

            checksum_valid, checksum_reason = validate_document_checksums(resolved_type, raw_fields)
            if expected_data:
                try:
                    expected_dict = json.loads(expected_data)
                    if isinstance(expected_dict, dict):
                        cross_check_results = perform_cross_check(raw_fields, expected_dict)
                except Exception:
                    pass
            sanitized_fields, field_confs = sanitize_extracted_fields(resolved_type, raw_fields, field_confs)

            # Context-specific issuer detection
            if resolved_type == "bank_statement" and sanitized_fields.get("bank_name"):
                detected_issuer = sanitized_fields["bank_name"]
            elif resolved_type == "salary_slip" and sanitized_fields.get("employer_name"):
                detected_issuer = sanitized_fields["employer_name"]
            elif resolved_type == "utility_bill" and sanitized_fields.get("utility_provider"):
                detected_issuer = sanitized_fields["utility_provider"]
            elif resolved_type == "income_certificate" and sanitized_fields.get("issuing_authority"):
                detected_issuer = sanitized_fields["issuing_authority"]
        except Exception as ex:
            checksum_valid = False
            checksum_reason = f"Extraction error: {str(ex)}"

        # 5. Authenticity Assessment
        qr_fields = {}
        if first_page_img:
            try:
                qrs = decode_qr_from_image(first_page_img)
                for q in qrs:
                    qr_fields.update(parse_qr_payload(resolved_type, q))
            except Exception:
                pass

        authenticity = authenticity_manager.assess_document(
            doc_type=resolved_type,
            image=first_page_img,
            ocr_lines=doc_res.pages[0].lines if doc_res.pages else [],
            extracted_fields=raw_fields,
            raw_text=doc_res.full_text,
            qr_fields=qr_fields,
            is_supported=True,
        )

        doc_status = determine_document_status(
            checksum_valid=checksum_valid,
            average_confidence=doc_res.average_confidence,
            vault_mode=True,
        )

        thumb_bytes = render_thumbnail(temp_path, is_pdf=(ext == ".pdf"))

        result_payload = {
            "doc_type": resolved_type,
            "document_type": detected_doc_title,
            "issuer": detected_issuer,
            "classification": classification,
            "evidence": classification.get("evidence", []),
            "ocr_required": ocr_required,
            "text_source": text_source,
            "status": doc_status,
            "confidence": doc_res.average_confidence,
            "pages": len(doc_res.pages),
            "reason": checksum_reason,
            "extracted_fields": sanitized_fields,
            "field_confidences": field_confs,
            "extracted_text": doc_res.full_text,
            "checksum_valid": checksum_valid,
            "checksum_reason": checksum_reason,
            "cross_check": cross_check_results,
            "verification_status": authenticity["verification_status"],
            "risk_score": authenticity["risk_score"],
            "review_required": authenticity["review_required"],
            "suspicious_signals": authenticity["suspicious_signals"],
            "human_review_reason": authenticity["human_review_reason"],
            "verified_by_ai": False,
        }

        saved_record = persist_document(
            file_bytes=file_bytes,
            filename=filename,
            result_data=result_payload,
            thumbnail_bytes=thumb_bytes,
            user_id=auth.get("user_id") or auth.get("sub"),
            mode="offline",
        )
        saved_record["supported"] = True
        saved_record["ocr_completed"] = True
        saved_record["verification_status"] = authenticity["verification_status"]
        saved_record["risk_score"] = authenticity["risk_score"]
        saved_record["review_required"] = authenticity["review_required"]
        saved_record["suspicious_signals"] = authenticity["suspicious_signals"]
        saved_record["human_review_reason"] = authenticity["human_review_reason"]
        saved_record["verified_by_ai"] = False
        logging_utils.log_event(
            logger,
            logging.INFO,
            event="document_processed",
            document_type=detected_doc_title,
            ocr_engine="RapidOCR",
            ai_model="none",
            processing_time_ms=int((time.time() - req_start) * 1000),
            verification_status=authenticity["verification_status"],
            risk_score=authenticity["risk_score"],
            status="success",
        )
        return saved_record

    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@app.post("/api/mode/ai/analyze")
async def process_ai_analyze_endpoint(
    file: UploadFile = File(...),
    auth: UserProfile = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit_upload),
):
    """
    AI Mode Document Analyze Endpoint:
    - Allows uploading documents NOT included in the predefined Offline Mode list.
    - Extracts text via embedded PDF layer (digital) or neural OCR (scanned/images).
    - AI analyzes document structure to determine document type, confidence, and reasoning.
    - Persists document in vault and returns structured AI classification result.
    """
    req_start = time.time()
    file_bytes = await file.read()
    clean_filename, ext = validate_upload_security(file, file_bytes)
    filename = clean_filename

    temp_path = os.path.join(TEMP_DIR, f"ai_upload_{uuid.uuid4()}{ext}")
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    try:
        # Extract text: check PDF text layer first, fallback to OCR
        logging_utils.log_event(logger, logging.INFO, event="ocr_started", doc_type="ai_analyzed", filename=filename)
        ocr_t0 = time.time()
        if ext == ".pdf":
            doc_res = ocr_engine.process_pdf(temp_path)
        else:
            doc_res = ocr_engine.process_file(temp_path)
        ocr_dur_ms = int((time.time() - ocr_t0) * 1000)
        logging_utils.log_event(
            logger,
            logging.INFO,
            event="ocr_completed",
            duration_ms=ocr_dur_ms,
            pages=len(doc_res.pages) if doc_res.pages else 1,
            status="success",
        )

        ocr_required = getattr(doc_res, "ocr_required", True)
        text_source = getattr(doc_res, "text_source", "none")

        extracted_text = doc_res.full_text or ""

        # Call AI analysis service with both OCR text and image path
        try:
            ai_res = await ai_service.analyze_document(
                document_text=extracted_text,
                file_path=temp_path,
                filename=filename,
            )
        except RuntimeError as ai_err:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(ai_err),
            )
        except Exception as ex:
            logger.error("AI document analysis failed: %s", ex, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI analysis failed: {str(ex)}",
            )

        thumb_bytes = render_thumbnail(temp_path, is_pdf=(ext == ".pdf"))
        evidence_list = ai_res.get("evidence") or ai_res.get("reasoning", [])

        # Authenticity Assessment (AI Mode Analyze)
        first_page_img: Optional[Image.Image] = None
        if doc_res.pages and doc_res.pages[0].image:
            first_page_img = doc_res.pages[0].image
        elif ext == ".pdf":
            pdf_imgs = render_pdf_pages_to_images(temp_path)
            if pdf_imgs:
                first_page_img = pdf_imgs[0]
        else:
            try:
                with Image.open(temp_path) as img:
                    first_page_img = img.convert("RGB").copy()
            except Exception:
                pass

        qr_fields = {}
        if first_page_img:
            try:
                qrs = decode_qr_from_image(first_page_img)
                for q in qrs:
                    qr_fields.update(parse_qr_payload("auto", q))
            except Exception:
                pass

        ai_auth = ai_res.get("authenticity") or ai_res.get("authenticity_assessment")
        authenticity = authenticity_manager.assess_document(
            doc_type="ai_analyzed",
            image=first_page_img,
            ocr_lines=doc_res.pages[0].lines if doc_res.pages else [],
            extracted_fields=ai_res.get("extracted_fields", {}),
            raw_text=extracted_text,
            qr_fields=qr_fields,
            ai_authenticity_result=ai_auth,
            is_supported=True,
        )

        result_payload = {
            "doc_type": "ai_analyzed",
            "document_type": ai_res.get("document_type", "Unknown Document"),
            "ocr_required": ocr_required,
            "text_source": text_source,
            "status": "completed",
            "confidence": 0.95 if ai_res.get("confidence") == "high" else (0.80 if ai_res.get("confidence") == "medium" else 0.50),
            "pages": len(doc_res.pages) if doc_res.pages else 1,
            "reason": None,
            "extracted_fields": ai_res.get("extracted_fields", {}),
            "field_confidences": {},
            "extracted_text": extracted_text,
            "summary": ai_res.get("summary", ""),
            "evidence": evidence_list,
            "is_local_ai": ai_res.get("is_local_ai", True),
            "model_used": ai_res.get("model_used", "qwen2.5vl:3b"),
            "verification_status": authenticity["verification_status"],
            "risk_score": authenticity["risk_score"],
            "review_required": authenticity["review_required"],
            "suspicious_signals": authenticity["suspicious_signals"],
            "human_review_reason": authenticity["human_review_reason"],
            "verified_by_ai": True,
            "ai_analysis": {
                "document_type": ai_res.get("document_type", "Unknown Document"),
                "confidence": ai_res.get("confidence", "high"),
                "summary": ai_res.get("summary", ""),
                "evidence": evidence_list,
                "extracted_fields": ai_res.get("extracted_fields", {}),
                "is_local_ai": ai_res.get("is_local_ai", True),
                "model_used": ai_res.get("model_used", "qwen2.5vl:3b"),
                "verification_status": authenticity["verification_status"],
                "risk_score": authenticity["risk_score"],
                "review_required": authenticity["review_required"],
                "suspicious_signals": authenticity["suspicious_signals"],
                "human_review_reason": authenticity["human_review_reason"],
            },
        }

        saved_record = persist_document(
            file_bytes=file_bytes,
            filename=filename,
            result_data=result_payload,
            thumbnail_bytes=thumb_bytes,
            user_id=auth.get("user_id") or auth.get("sub"),
            mode="ai",
        )
        if saved_record.get("ai_analysis"):
            saved_record["ai_analysis"]["document_id"] = saved_record["id"]

        is_local = ai_res.get("is_local_ai", True)
        used_model = ai_res.get("model_used", "qwen2.5vl:3b")

        logging_utils.log_event(
            logger,
            logging.INFO,
            event="document_processed",
            document_type=ai_res.get("document_type", "Unknown Document"),
            ocr_engine="RapidOCR",
            ai_provider="ollama" if is_local else "external",
            ai_model=used_model,
            processing_time_ms=int((time.time() - req_start) * 1000),
            verification_status=authenticity["verification_status"],
            risk_score=authenticity["risk_score"],
            status="success",
        )

        return {
            "document_id": saved_record["id"],
            "filename": saved_record["filename"],
            "document_type": ai_res.get("document_type", "Unknown Document"),
            "confidence": ai_res.get("confidence", "high"),
            "summary": ai_res.get("summary", ""),
            "evidence": evidence_list,
            "reasoning": evidence_list,
            "extracted_fields": ai_res.get("extracted_fields", {}),
            "file_url": saved_record["file_url"],
            "preview_url": saved_record.get("preview_url"),
            "file_size": saved_record["file_size"],
            "pages": saved_record["pages"],
            "text_source": text_source,
            "extracted_text": extracted_text,
            "is_local_ai": is_local,
            "model_used": used_model,
            "verification_status": authenticity["verification_status"],
            "risk_score": authenticity["risk_score"],
            "review_required": authenticity["review_required"],
            "suspicious_signals": authenticity["suspicious_signals"],
            "human_review_reason": authenticity["human_review_reason"],
            "verified_by_ai": True,
        }

    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@app.post("/api/mode/ai/chat")
async def process_ai_chat_endpoint(
    payload: AiChatPayload,
    auth: UserProfile = Depends(get_current_user),
    _rate_limit: None = Depends(rate_limit_ai_chat),
):
    """
    AI Mode Interactive Chat Endpoint:
    - Receives user query and document_id.
    - Answers using the uploaded document's canonical analysis object and extracted text.
    - Maintains conversational continuity while keeping documents isolated and grounded.
    """
    target_id = payload.document_id or document_store.get_active_document_id()
    if not target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_id is required",
        )
    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message cannot be empty",
        )

    # Set as active session document
    document_store.set_active_document(target_id)
    doc = document_store.get_document(target_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{target_id}' not found in vault",
        )

    user_id = auth.get("user_id") or auth.get("sub")
    doc_user = doc.get("user_id")
    if doc_user and user_id and doc_user != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{target_id}' not found in vault",
        )

    doc_text = doc.get("extracted_text") or ""
    if not doc_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Document text is not available for this document. Please re-upload.",
        )

    filename = doc.get("filename", "document")
    # Load canonical analysis object (single source of truth for AI chat)
    canonical_analysis = document_store.get_canonical_analysis(target_id)
    doc_text = (canonical_analysis.get("ocr_text") if canonical_analysis else None) or doc_text

    try:
        try:
            reply = await ai_service.chat_with_document(
                document_text=doc_text,
                filename=filename,
                message=payload.message,
                history=payload.history,
                stored_analysis=canonical_analysis,
            )
        except TypeError as te:
            if "stored_analysis" in str(te):
                reply = await ai_service.chat_with_document(
                    document_text=doc_text,
                    filename=filename,
                    message=payload.message,
                    history=payload.history,
                )
            else:
                raise

        # Save conversation to chat repository
        if user_id:
            chat_repository.add_chat_message(
                user_id=user_id,
                document_id=target_id,
                role="user",
                content=payload.message,
            )
            chat_repository.add_chat_message(
                user_id=user_id,
                document_id=target_id,
                role="assistant",
                content=reply,
            )

        return {"response": reply}
    except RuntimeError as ai_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(ai_err),
        )
    except Exception as ex:
        logger.error("AI chat failed for document %s: %s", payload.document_id, ex, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI chat error: {str(ex)}",
        )


@app.get("/api/mode/ai/chat/{doc_id}")
async def get_ai_chat_history_endpoint(
    doc_id: str,
    auth: dict = Depends(authenticate_request),
):
    """Retrieve isolated multi-turn chat history for a document owned by the user."""
    user_id = auth.get("user_id") or auth.get("sub")
    doc = document_store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    doc_user = doc.get("user_id")
    if doc_user and user_id and doc_user != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"history": chat_repository.get_chat_history(user_id or "default", doc_id)}


# Mount frontend single page application if built
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")


