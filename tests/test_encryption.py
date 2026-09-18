"""
tests/test_encryption.py
Comprehensive tests for AES-256-GCM local document and result encryption in company-ocr-service.
Covers:
- Task 1: AES-256-GCM authenticated encryption, unique nonces, authentication tag verification
- Task 2: Secure key management via DOCUMENT_ENCRYPTION_KEY, safe failure when missing
- Task 3: Transparent decryption for OCR/AI/file serving
- Task 4: Encrypted results in uploads/results/{document_id}.json.enc
- Task 5: Secure temporary file cleanup with temporary_decrypted_document context manager
- Task 6: Preserve Document Vault (documents.json compatibility)
- Task 7: Backward compatibility and automatic migration for older unencrypted documents
"""

import io
import json
import os
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import document_store
import encryption
from encryption import (
    DocumentDecryptionError,
    DocumentEncryptionKeyMissingError,
    decrypt_bytes,
    encrypt_bytes,
    generate_key,
    get_encryption_key,
    is_encrypted_payload,
)
from main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_task1_aes_256_gcm_unique_nonce_and_tamper_proofing():
    """
    Task 1: Verify AES-256-GCM encryption:
    - Generates unique nonces for identical plaintext (different ciphertexts)
    - Verifies authentication tag: tampering with ciphertext raises DocumentDecryptionError
    """
    secret_text = b"Confidential financial statement containing PAN and Bank details"
    enc1 = encrypt_bytes(secret_text)
    enc2 = encrypt_bytes(secret_text)

    # 1. Verification of encryption and magic header
    assert is_encrypted_payload(enc1)
    assert is_encrypted_payload(enc2)
    assert enc1.startswith(b"ENC1")

    # 2. Unique nonces: two encryptions of same data must differ
    assert enc1 != enc2
    # Nonces at bytes [4:16] must be different
    assert enc1[4:16] != enc2[4:16]

    # 3. Successful decryption
    assert decrypt_bytes(enc1) == secret_text
    assert decrypt_bytes(enc2) == secret_text

    # 4. Tamper proofing: flipping a single bit in ciphertext must cause authentication failure
    tampered = bytearray(enc1)
    tampered[-1] ^= 0x01  # Flip one bit in authentication tag
    with pytest.raises(DocumentDecryptionError) as exc_info:
        decrypt_bytes(bytes(tampered))
    assert "authentication tag mismatch" in str(exc_info.value).lower() or "decryption failed" in str(exc_info.value).lower()


def test_task2_key_management_formats_and_missing_key_behavior(monkeypatch):
    """
    Task 2: Key Management:
    - Supports 64-hex strings, base64 strings, and 32 raw bytes
    - If missing or invalid length, fails safely with DocumentEncryptionKeyMissingError
    - Never leaks key in error messages
    """
    # 1. 64-character hex key
    hex_key = generate_key()
    monkeypatch.setenv("DOCUMENT_ENCRYPTION_KEY", hex_key)
    parsed_key = get_encryption_key()
    assert len(parsed_key) == 32
    assert parsed_key == bytes.fromhex(hex_key)

    # 2. Missing key raises DocumentEncryptionKeyMissingError
    monkeypatch.delenv("DOCUMENT_ENCRYPTION_KEY", raising=False)
    with pytest.raises(DocumentEncryptionKeyMissingError):
        get_encryption_key()

    # 3. Invalid length key raises DocumentEncryptionKeyMissingError
    monkeypatch.setenv("DOCUMENT_ENCRYPTION_KEY", "too_short_key")
    with pytest.raises(DocumentEncryptionKeyMissingError) as exc_info:
        get_encryption_key()
    assert "invalid document_encryption_key" in str(exc_info.value).lower()


def test_task2_wrong_key_causes_safe_decryption_failure():
    """
    Task 2: Verify wrong encryption key causes safe authentication failure without crashing.
    """
    key_a = bytes.fromhex(generate_key())
    key_b = bytes.fromhex(generate_key())

    data = b"Secret payload"
    enc = encrypt_bytes(data, key=key_a)

    with pytest.raises(DocumentDecryptionError):
        decrypt_bytes(enc, key=key_b)


def test_task1_and_task4_upload_encrypts_original_and_results(client):
    """
    Tasks 1, 4, 6: Verify uploaded document is encrypted on disk:
    - uploads/original/<uuid>.<ext>.enc contains encrypted bytes (never plaintext)
    - uploads/results/<uuid>.json.enc contains encrypted JSON
    - documents.json index preserves metadata and tracks stored_filename as .enc
    """
    # Create test image with clear text
    img = Image.new("RGB", (400, 150), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "INCOME TAX DEPARTMENT", fill="black")
    draw.text((20, 60), "PAN: ABCDE1234F", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    res = client.post(
        "/api/upload",
        files={"file": ("Personal_PAN.png", png_bytes, "image/png")},
        data={"doc_type": "pan"},
    )
    assert res.status_code == 200
    doc = res.json()
    doc_id = doc["id"]

    # 1. Verify original file on disk is encrypted
    stored_path = document_store.get_document_file_path(doc_id)
    assert stored_path is not None
    assert stored_path.endswith(".enc")
    assert os.path.exists(stored_path)

    with open(stored_path, "rb") as f:
        disk_bytes = f.read()

    # Must be encrypted: starts with ENC1, not PNG header
    assert is_encrypted_payload(disk_bytes)
    assert not disk_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # 2. Verify results file in uploads/results/ is encrypted
    result_enc_path = os.path.join(document_store.RESULTS_DIR, f"{doc_id}.json.enc")
    assert os.path.exists(result_enc_path)
    with open(result_enc_path, "rb") as f:
        res_bytes = f.read()
    assert is_encrypted_payload(res_bytes)
    # Plaintext JSON file must NOT exist
    assert not os.path.exists(os.path.join(document_store.RESULTS_DIR, f"{doc_id}.json"))

    # 3. Transparent document details retrieval
    retrieved_doc = document_store.get_document(doc_id)
    assert retrieved_doc is not None
    assert retrieved_doc["id"] == doc_id
    assert retrieved_doc["filename"] == "Personal_PAN.png"
    assert retrieved_doc["is_encrypted"] is True

    # Clean up
    client.delete(f"/api/documents/{doc_id}")


def test_task3_transparent_file_serving_endpoint(client):
    """
    Task 3: Transparent Decryption for file viewing and download:
    - GET /api/documents/{doc_id}/file returns decrypted plaintext bytes
    - Correct content-type header
    - Correct content-disposition header (inline vs attachment)
    """
    img = Image.new("RGB", (300, 100), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "DRIVING LICENCE", fill="black")
    draw.text((20, 50), "DL NO: DL-0420110012345", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    original_bytes = buf.getvalue()

    res = client.post(
        "/api/upload",
        files={"file": ("DL_Card.png", original_bytes, "image/png")},
        data={"doc_type": "driving_licence"},
    )
    assert res.status_code == 200
    doc_id = res.json()["id"]

    # 1. Inline viewing
    file_res = client.get(f"/api/documents/{doc_id}/file")
    assert file_res.status_code == 200
    assert file_res.headers["content-type"] == "image/png"
    assert "inline" in file_res.headers["content-disposition"]
    # Returned content matches original decrypted bytes!
    assert file_res.content == original_bytes

    # 2. Attachment download
    down_res = client.get(f"/api/documents/{doc_id}/file?download=true")
    assert down_res.status_code == 200
    assert "attachment" in down_res.headers["content-disposition"]
    assert "DL_Card.png" in down_res.headers["content-disposition"]
    assert down_res.content == original_bytes

    # Clean up
    client.delete(f"/api/documents/{doc_id}")


def test_task5_temporary_decrypted_document_cleanup():
    """
    Task 5: Verify temporary_decrypted_document context manager:
    - Creates plaintext temp file during processing
    - Cleans up plaintext file on normal exit
    - Cleans up plaintext file even if an unhandled exception occurs
    """
    plain_content = b"%PDF-1.4 Mock PDF for test"
    record = document_store.save_document(
        file_bytes=plain_content,
        filename="test_statement.pdf",
        result_data={"doc_type": "bank_statement", "document_type": "Bank Statement"},
    )
    doc_id = record["id"]

    temp_path_captured = None
    # 1. Normal context manager flow
    with document_store.temporary_decrypted_document(doc_id) as temp_path:
        temp_path_captured = temp_path
        assert os.path.exists(temp_path)
        with open(temp_path, "rb") as f:
            assert f.read() == plain_content

    # Guaranteed deleted after exiting with block
    assert not os.path.exists(temp_path_captured)

    # 2. Exception flow: guaranteed deleted even when exception raised inside with block
    temp_path_err = None
    with pytest.raises(RuntimeError):
        with document_store.temporary_decrypted_document(doc_id) as temp_path:
            temp_path_err = temp_path
            assert os.path.exists(temp_path)
            raise RuntimeError("Simulated processing failure")

    assert temp_path_err is not None
    assert not os.path.exists(temp_path_err)

    # Clean up
    document_store.delete_document(doc_id)


def test_task7_backward_compatibility_unencrypted_older_document():
    """
    Task 7: Backward compatibility:
    - Older unencrypted files in uploads/original/ can be read transparently
    - migrate_unencrypted_documents() encrypts them to .enc and deletes plaintext copies
    """
    doc_id = "legacy-test-doc-1234"
    plain_data = b"Legacy plaintext passport document content"

    # Write legacy unencrypted original file and legacy unencrypted JSON result
    legacy_file = os.path.join(document_store.ORIGINAL_DIR, f"{doc_id}.pdf")
    with open(legacy_file, "wb") as f:
        f.write(plain_data)

    legacy_result = os.path.join(document_store.RESULTS_DIR, f"{doc_id}.json")
    with open(legacy_result, "w", encoding="utf-8") as f:
        json.dump({"id": doc_id, "document_type": "Passport", "filename": "old_passport.pdf"}, f)

    try:
        # 1. Transparent read before migration
        assert document_store.get_document_bytes(doc_id) == plain_data

        # 2. Execute migration
        migrated = document_store.migrate_unencrypted_documents()
        assert migrated >= 1

        # 3. Plaintext original file was removed
        assert not os.path.exists(legacy_file)
        # Encrypted file was created
        enc_file = legacy_file + ".enc"
        assert os.path.exists(enc_file)

        # 4. Result file was migrated to .json.enc
        assert not os.path.exists(legacy_result)
        assert os.path.exists(os.path.join(document_store.RESULTS_DIR, f"{doc_id}.json.enc"))

        # 5. Transparent read after migration still returns exact plaintext
        assert document_store.get_document_bytes(doc_id) == plain_data
    finally:
        # Clean up
        document_store.delete_document(doc_id)
