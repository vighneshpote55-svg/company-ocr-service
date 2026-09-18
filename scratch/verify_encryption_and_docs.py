import os
import sys
import io
from PIL import Image, ImageDraw
import pypdf

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
import document_store
import encryption

client = TestClient(app)

def create_card_image(title: str, lines: list[str]) -> bytes:
    img = Image.new("RGB", (600, 250), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((25, 25), title, fill="black")
    y = 65
    for l in lines:
        draw.text((25, y), l, fill="black")
        y += 35
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def create_pdf(text: str) -> bytes:
    # Use pypdf to generate a valid PDF
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=400, height=300)
    # We can write simple pdf bytes
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()

def run_verification():
    print("=== 1. Testing Document Uploads with Encryption ===")

    # Test 1: PAN Card
    pan_bytes = create_card_image(
        "INCOME TAX DEPARTMENT GOVT. OF INDIA",
        ["Permanent Account Number", "ABCDE1234F", "Name: SNEHA GUPTA", "DOB: 15/08/1992"]
    )
    res_pan = client.post(
        "/api/mode/offline",
        files={"file": ("PAN_Sneha.png", pan_bytes, "image/png")},
        data={"doc_type": "auto"}
    )
    assert res_pan.status_code == 200, f"PAN upload failed: {res_pan.text}"
    pan_doc = res_pan.json()
    print(f"PAN Card OCR: status={pan_doc.get('status')}, doc_type={pan_doc.get('doc_type')}, stored={pan_doc.get('stored_filename')}")
    assert pan_doc.get("doc_type") == "pan"
    assert pan_doc.get("stored_filename").endswith(".enc")

    # Test 2: Bank Statement
    bs_bytes = create_card_image(
        "STATE BANK OF INDIA - ACCOUNT STATEMENT",
        ["Account Number: 12345678901", "IFSC Code: SBIN0001234", "Account Holder: SNEHA GUPTA", "Balance: INR 50,000"]
    )
    res_bs = client.post(
        "/api/mode/offline",
        files={"file": ("SBI_Statement.png", bs_bytes, "image/png")},
        data={"doc_type": "bank_statement"}
    )
    assert res_bs.status_code == 200, f"Bank statement upload failed: {res_bs.text}"
    bs_doc = res_bs.json()
    print(f"Bank Statement OCR: status={bs_doc.get('status')}, doc_type={bs_doc.get('doc_type')}, stored={bs_doc.get('stored_filename')}")
    assert bs_doc.get("stored_filename").endswith(".enc")

    # Test 3: GST Certificate
    gst_bytes = create_card_image(
        "GOVERNMENT OF INDIA - REGISTRATION CERTIFICATE",
        ["GSTIN: 27AABCT3518Q1ZS", "Legal Name: ACME ENTERPRISES", "Registration Date: 01/07/2017"]
    )
    res_gst = client.post(
        "/api/mode/offline",
        files={"file": ("GST_Certificate.png", gst_bytes, "image/png")},
        data={"doc_type": "gst_certificate"}
    )
    assert res_gst.status_code == 200, f"GST Certificate upload failed: {res_gst.text}"
    gst_doc = res_gst.json()
    print(f"GST Certificate OCR: status={gst_doc.get('status')}, doc_type={gst_doc.get('doc_type')}, stored={gst_doc.get('stored_filename')}")
    assert gst_doc.get("stored_filename").endswith(".enc")

    # Test 4: Unknown Document
    unk_bytes = create_card_image(
        "CUSTOM INVENTORY LOG SHEET 2026",
        ["Item: Widget A, Quantity: 500", "Warehouse: Unit 4B", "Inspector: John Doe"]
    )
    res_unk = client.post(
        "/api/mode/offline",
        files={"file": ("Inventory_Log.png", unk_bytes, "image/png")},
        data={"doc_type": "auto"}
    )
    assert res_unk.status_code == 200, f"Unknown document upload failed: {res_unk.text}"
    unk_doc = res_unk.json()
    print(f"Unknown Document OCR: status={unk_doc.get('status')}, doc_type={unk_doc.get('doc_type')}, stored={unk_doc.get('stored_filename')}")
    assert unk_doc.get("doc_type") == "unknown"
    assert unk_doc.get("stored_filename").endswith(".enc")

    # Test 5: Existing old document opens and serves decrypted file
    print("\n=== 2. Testing Existing Old Document Retrieval & File Serving ===")
    docs = document_store.list_documents(limit=5)
    assert len(docs) > 0
    test_target = docs[0]
    doc_id = test_target["id"]
    print(f"Opening existing document: {doc_id} ({test_target.get('filename')})")
    
    get_res = client.get(f"/api/documents/{doc_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == doc_id
    
    file_res = client.get(f"/api/documents/{doc_id}/file")
    assert file_res.status_code == 200
    assert len(file_res.content) > 0
    # Decrypted content must NOT start with ENC1
    assert not file_res.content.startswith(b"ENC1")
    print(f"File serving returned decrypted bytes (length={len(file_res.content)}, content-type={file_res.headers.get('content-type')})")

    # Test 6: Verify uploads/original/ contains ONLY .enc files
    print("\n=== 3. Verifying uploads/original/ contains ONLY .enc files ===")
    original_files = os.listdir(document_store.ORIGINAL_DIR)
    print(f"Files in uploads/original/ ({len(original_files)} files):")
    for f in original_files:
        assert f.endswith(".enc"), f"File {f} in uploads/original/ does not end in .enc!"
        fpath = os.path.join(document_store.ORIGINAL_DIR, f)
        with open(fpath, "rb") as fp:
            header = fp.read(4)
        assert header == b"ENC1", f"File {f} does not start with ENC1!"
    print("All files in uploads/original/ are authenticated .enc files starting with ENC1!")

    # Test 7: Verify uploads/results/ contains encrypted result files
    print("\n=== 4. Verifying uploads/results/ contains encrypted result files ===")
    results_files = os.listdir(document_store.RESULTS_DIR)
    print(f"Files in uploads/results/ ({len(results_files)} files):")
    for f in results_files:
        assert f.endswith(".json.enc"), f"File {f} in uploads/results/ does not end in .json.enc!"
        fpath = os.path.join(document_store.RESULTS_DIR, f)
        with open(fpath, "rb") as fp:
            header = fp.read(4)
        assert header == b"ENC1", f"File {f} does not start with ENC1!"
    print("All files in uploads/results/ are authenticated .json.enc files starting with ENC1!")

    # Test 8: Verify no decrypted plaintext files remain in temp/
    print("\n=== 5. Verifying no plaintext copies remain in temp/ ===")
    if os.path.exists(document_store.TEMP_DIR):
        temp_files = os.listdir(document_store.TEMP_DIR)
        print(f"Files in temp/: {temp_files}")
        for tf in temp_files:
            assert not tf.startswith("temp_dec_"), f"Lingering decrypted file found: {tf}"
    print("No plaintext copies remain after processing!")

    print("\nALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_verification()
