"""
logging_utils.py
Production-grade JSON structured logging and automatic PII redaction utility
for company-ocr-service.
- Emits single-line JSON log entries with UTC ISO-8601 timestamps.
- Context-variable propagation for request_id across async and sync call chains.
- Automatic redaction of PAN, Aadhaar, Account numbers, GSTIN, IFSC, Customer numbers,
  and Encryption keys prior to serialization.
- Timing and metrics helpers for OCR, AI, and document processing.
- Safe serialization that handles arbitrary objects, exceptions, and sets without errors.
"""

import contextvars
from datetime import datetime, timezone
import json
import logging
import os
import re
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Union

# ContextVar for tracing request_id across execution contexts
current_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_request_id", default=None
)

# In-memory buffer for automated testing and test assertions
_log_capture_buffer: List[Dict[str, Any]] = []
_capture_enabled: bool = False

# ==============================================================================
# Regex Patterns for Automatic Redaction
# ==============================================================================

# 1. PAN Number: 5 uppercase letters, 4 digits, 1 uppercase letter
PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# 2. Aadhaar Number: 12 digits, optionally grouped in 4s by space or hyphen
AADHAAR_PATTERN = re.compile(r"\b\d{4}[ -]\d{4}[ -]\d{4}\b|\b\d{12}\b")

# 3. GSTIN: 2 digits, 5 letters, 4 digits, 1 letter, 1 alphanumeric, 'Z', 1 alphanumeric
GSTIN_PATTERN = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")

# 4. IFSC: 4 letters, '0', 6 alphanumeric characters
IFSC_PATTERN = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")

# 5. Bank Account Numbers: 9 to 18 consecutive digits
ACCOUNT_NUMBER_PATTERN = re.compile(r"\b\d{9,18}\b")

# 6. Encryption key patterns: 64-hex string or loaded DOCUMENT_ENCRYPTION_KEY
HEX_KEY_PATTERN = re.compile(r"\b[0-9a-fA-F]{64}\b")


def get_request_id() -> Optional[str]:
    """Retrieve current request ID from contextvar."""
    return current_request_id.get()


def set_request_id(req_id: Optional[str]) -> None:
    """Set current request ID in contextvar."""
    current_request_id.set(req_id)


def generate_request_id() -> str:
    """Generate a unique random request ID."""
    return uuid.uuid4().hex[:16]


def redact_sensitive_text(text: str) -> str:
    """
    Apply all redaction rules to a string before logging.
    Strictly replaces sensitive identifiers with [REDACTED_*] tokens.
    """
    if not isinstance(text, str) or not text:
        return text

    # Redact known server encryption key if set in environment
    env_key = os.getenv("DOCUMENT_ENCRYPTION_KEY", "").strip()
    if env_key and len(env_key) >= 16 and env_key in text:
        text = text.replace(env_key, "[REDACTED_KEY]")

    # Redact 64-char hex keys
    text = HEX_KEY_PATTERN.sub("[REDACTED_KEY]", text)

    # Redact GSTIN (15 chars, do before PAN to prevent partial match on PAN segment)
    text = GSTIN_PATTERN.sub("[REDACTED_GSTIN]", text)

    # Redact PAN
    text = PAN_PATTERN.sub("[REDACTED_PAN]", text)

    # Redact Aadhaar (12 digits with spaces or contiguous)
    text = AADHAAR_PATTERN.sub("[REDACTED_AADHAAR]", text)

    # Redact IFSC
    text = IFSC_PATTERN.sub("[REDACTED_IFSC]", text)

    # Redact Account Numbers (9 to 18 digits)
    # Note: ensure we don't accidentally match timestamps like 20260921 or phone numbers with +
    text = ACCOUNT_NUMBER_PATTERN.sub("[REDACTED_ACCOUNT]", text)

    return text


def redact_data(obj: Any) -> Any:
    """
    Recursively redact sensitive strings within dictionaries, lists, and primitives.
    """
    if isinstance(obj, str):
        return redact_sensitive_text(obj)
    elif isinstance(obj, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in obj.items():
            # Never log sensitive field keys or their values
            key_str = str(k).lower()
            if key_str in ("ocr_text", "full_text", "prompt", "ai_prompt", "response_text", "raw_content", "ai_response"):
                cleaned[k] = "[REDACTED_LARGE_PAYLOAD]"
            elif any(s in key_str for s in ("encryption_key", "jwt_secret", "secret_key", "password", "api_key")):
                cleaned[k] = "[REDACTED_SECRET]"
            else:
                cleaned[k] = redact_data(v)
        return cleaned
    elif isinstance(obj, (list, tuple, set)):
        return [redact_data(item) for item in obj]
    elif isinstance(obj, Exception):
        return redact_sensitive_text(str(obj))
    return obj


# ==============================================================================
# JSON Structured Formatter
# ==============================================================================

class JsonFormatter(logging.Formatter):
    """
    Formats standard Python logging records into production JSON log lines.
    Automatically injects UTC ISO-8601 timestamp, current request_id, event name,
    and structured extras while redacting all sensitive PII.
    """

    def __init__(self, service_name: str = "company-ocr-service"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        extra_fields = getattr(record, "_extra_fields", {}) or {}

        # Determine request_id: _extra_fields or record attribute or contextvar
        req_id = extra_fields.get("request_id") or getattr(record, "request_id", None) or get_request_id()

        # Determine event name
        event_name = extra_fields.get("event") or getattr(record, "event", None) or getattr(record, "event_name", None) or "log_message"

        # Base structured entry
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": req_id,
            "event": event_name,
        }

        # Include custom message if different from event
        raw_msg = extra_fields.get("message") or record.getMessage()
        if raw_msg and raw_msg != event_name:
            log_entry["message"] = raw_msg

        # Merge custom structured fields passed via _extra_fields
        for k, v in extra_fields.items():
            if k not in ("timestamp", "level", "logger", "request_id", "event", "message"):
                log_entry[k] = v

        # Merge any other non-standard attributes passed directly
        standard_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "event", "event_name", "request_id",
            "_extra_fields"
        }
        for k, v in record.__dict__.items():
            if k not in standard_attrs and not k.startswith("_") and k not in log_entry:
                log_entry[k] = v

        # Add exception info if present
        if record.exc_info and not record.exc_text:
            log_entry["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            log_entry["exception"] = record.exc_text

        # Automatic PII Redaction across all log entry fields
        sanitized_entry = redact_data(log_entry)

        # Store in test capture buffer if enabled
        if _capture_enabled:
            _log_capture_buffer.append(dict(sanitized_entry))

        # Serialize safely to single-line JSON string
        try:
            return json.dumps(sanitized_entry, default=str)
        except Exception:
            # Fallback safe serialization
            return json.dumps(
                {
                    "timestamp": sanitized_entry.get("timestamp"),
                    "level": sanitized_entry.get("level"),
                    "request_id": sanitized_entry.get("request_id"),
                    "event": sanitized_entry.get("event"),
                    "message": str(sanitized_entry.get("message")),
                },
                default=str,
            )


# ==============================================================================
# Logger Setup & Helpers
# ==============================================================================

def setup_logging(
    level: int = logging.INFO,
    service_name: str = "company-ocr-service",
) -> logging.Logger:
    """
    Configure root logger with the JsonFormatter stream handler.
    """
    formatter = JsonFormatter(service_name=service_name)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers
    has_json_handler = any(isinstance(getattr(h, "formatter", None), JsonFormatter) for h in root_logger.handlers)
    if not has_json_handler:
        # Clear existing stream handlers to prevent duplicate plain-text logs
        root_logger.handlers = [h for h in root_logger.handlers if not isinstance(h, logging.StreamHandler)]
        root_logger.addHandler(handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Return a standard Python logger that outputs JSON via root configuration."""
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Convenience helper to emit a structured log event with extra fields.
    """
    extra_payload = dict(kwargs)
    extra_payload["event"] = event
    req_id = kwargs.get("request_id") or get_request_id()
    if req_id:
        extra_payload["request_id"] = req_id

    log_msg = message or event
    logger.log(level, log_msg, extra={"_extra_fields": extra_payload})


# ==============================================================================
# Testing Utilities for Assertions
# ==============================================================================

def enable_log_capture() -> None:
    """Enable in-memory capturing of sanitized JSON log records for testing."""
    global _capture_enabled
    _capture_enabled = True


def disable_log_capture() -> None:
    """Disable in-memory capturing."""
    global _capture_enabled
    _capture_enabled = False


def clear_log_capture() -> None:
    """Clear captured log records."""
    global _log_capture_buffer
    _log_capture_buffer.clear()


def get_captured_logs() -> List[Dict[str, Any]]:
    """Return a copy of captured log records."""
    return list(_log_capture_buffer)
