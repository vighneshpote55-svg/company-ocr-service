"""
encryption.py
Authenticated local document encryption (AES-256-GCM) for company-ocr-service.
Features:
- AES-256-GCM authenticated encryption with 12-byte unique nonces per file
- Authentication tag verification preventing tampering
- Header format: b"ENC1" (4 bytes) + nonce (12 bytes) + ciphertext_with_tag
- Secure server-side key management via DOCUMENT_ENCRYPTION_KEY
- Zero plaintext retention on disk
"""

import base64
import logging
import os
import secrets
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("company_server_ocr.encryption")

MAGIC_HEADER = b"ENC1"
NONCE_LENGTH = 12
MIN_ENCRYPTED_LENGTH = len(MAGIC_HEADER) + NONCE_LENGTH + 16  # 32 bytes minimum


class DocumentEncryptionError(Exception):
    """Base exception for document encryption failures."""
    pass


class DocumentEncryptionKeyMissingError(DocumentEncryptionError):
    """Raised when DOCUMENT_ENCRYPTION_KEY is not configured or is invalid."""
    pass


class DocumentDecryptionError(DocumentEncryptionError):
    """Raised when decryption fails due to tag mismatch, corrupted data, or incorrect key."""
    pass


def generate_key() -> str:
    """Generate a random 32-byte key formatted as a 64-character hex string."""
    return secrets.token_hex(32)


def get_encryption_key() -> bytes:
    """
    Retrieve and validate the 32-byte encryption key from the environment.
    Supports 64-character hex strings, base64 strings, or raw 32-byte strings.
    """
    key_env = os.getenv("DOCUMENT_ENCRYPTION_KEY")
    if not key_env or not key_env.strip():
        raise DocumentEncryptionKeyMissingError(
            "DOCUMENT_ENCRYPTION_KEY environment variable is missing. Encryption cannot proceed."
        )

    raw_val = key_env.strip()

    # Case 1: 64-character hex string
    if len(raw_val) == 64:
        try:
            return bytes.fromhex(raw_val)
        except ValueError:
            pass

    # Case 2: Base64-encoded string
    try:
        decoded = base64.b64decode(raw_val)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    # Case 3: Raw 32 bytes string
    raw_bytes = raw_val.encode("utf-8")
    if len(raw_bytes) == 32:
        return raw_bytes

    raise DocumentEncryptionKeyMissingError(
        f"Invalid DOCUMENT_ENCRYPTION_KEY: expected 32 bytes (or 64 hex characters), got {len(raw_val)} chars."
    )


def is_encrypted_payload(data: bytes) -> bool:
    """Check if the provided byte sequence starts with the ENC1 magic header and has valid length."""
    return (
        isinstance(data, (bytes, bytearray))
        and len(data) >= MIN_ENCRYPTED_LENGTH
        and bytes(data[:4]) == MAGIC_HEADER
    )


def encrypt_bytes(data: bytes, key: Optional[bytes] = None) -> bytes:
    """
    Encrypt data using AES-256-GCM with a unique 12-byte random nonce.
    Returns: b"ENC1" + nonce (12 bytes) + ciphertext_with_tag
    """
    if key is None:
        key = get_encryption_key()

    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("Data to encrypt must be bytes or bytearray.")

    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, bytes(data), associated_data=None)

    return MAGIC_HEADER + nonce + ciphertext


def decrypt_bytes(encrypted_data: bytes, key: Optional[bytes] = None) -> bytes:
    """
    Decrypt data using AES-256-GCM and verify authentication tag.
    Raises DocumentDecryptionError on tag mismatch, corrupt data, or invalid payload.
    """
    if not is_encrypted_payload(encrypted_data):
        raise DocumentDecryptionError(
            "Invalid encrypted payload: missing ENC1 magic header or payload too short."
        )

    if key is None:
        key = get_encryption_key()

    nonce = encrypted_data[len(MAGIC_HEADER) : len(MAGIC_HEADER) + NONCE_LENGTH]
    ciphertext = encrypted_data[len(MAGIC_HEADER) + NONCE_LENGTH :]

    try:
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    except InvalidTag as it_ex:
        raise DocumentDecryptionError(
            "Decryption failed: authentication tag mismatch or corrupted data."
        ) from it_ex
    except Exception as ex:
        raise DocumentDecryptionError(f"Decryption failed: {str(ex)}") from ex
