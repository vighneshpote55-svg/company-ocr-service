import sys
import os
sys.path.insert(0, os.path.abspath("."))
import io
import fitz  # PyMuPDF
from fastapi.testclient import TestClient
from main import app
from ocr_engine import OCRDocumentResult, OCRPageResult, OCRLine
from verifier import classify_document_content, normalize_ocr_text
from extractors import extract_document_fields_raw

def make_mock_doc(text: str) -> OCRDocumentResult:
    lines = [OCRLine(text=line, confidence=0.98) for line in text.splitlines() if line.strip()]
    page = OCRPageResult(page_num=1, full_text=text, lines=lines, average_confidence=0.98)
    return OCRDocumentResult(pages=[page], full_text=text, average_confidence=0.98)

def test_offline_pipeline_e2e():
    print("=== 1. Testing PAN WhatsApp image text ===")
    pan_text = """
    INCOMETAXDEPARTMENT
    GOVT.OFINDIA
    RAHUL KUMAR SHARMA
    SURESH SHARMA
    15/08/1990
    ABCDE1234F
    Permanent Account Number
    """
    classified = classify_document_content(pan_text)
    print("PAN Classification:", classified)
    assert classified["doc_type"] == "pan"
    assert classified["document_type"] == "PAN Card"
    assert "Income Tax Department" in classified["issuer"]
    
    pan_fields, pan_confs = extract_document_fields_raw("pan", make_mock_doc(pan_text))
    print("PAN Extracted Fields:", pan_fields)
    assert pan_fields.get("pan_number") == "ABCDE1234F"
    assert "RAHUL" in pan_fields.get("name", "").upper()
    assert "SURESH" in pan_fields.get("father_name", "").upper()
    assert pan_fields.get("dob") == "15/08/1990"

    print("\n=== 2. Testing Bank Statement PDF with embedded text layer ===")
    doc = fitz.open()
    page = doc.new_page()
    bank_pdf_text = """
    STATE BANK OF INDIA
    Account Statement
    Account Name: VIKRAM ADITYA SINGH
    Account Number: 123456789012
    CIF No: 890123456
    IFS Code: SBIN0001234
    Branch: Connaught Place, New Delhi
    Statement Period: 01/01/2024 to 31/01/2024
    Opening Balance: 10,000.00
    Closing Balance: 25,000.00

    Txn Date | Value Date | Description | Ref No | Debit | Credit | Balance
    05/01/2024 | 05/01/2024 | SALARY CREDIT | 102938 | 0.00 | 20000.00 | 30000.00
    10/01/2024 | 10/01/2024 | ATM WDL | 992811 | 5000.00 | 0.00 | 25000.00
    """
    page.insert_text((50, 50), bank_pdf_text)
    pdf_bytes = doc.write()
    doc.close()

    classified_bank = classify_document_content(bank_pdf_text)
    print("Bank Classification:", classified_bank)
    assert classified_bank["doc_type"] == "bank_statement"
    assert classified_bank["document_type"] == "Bank Statement"
    
    bank_fields, bank_confs = extract_document_fields_raw("bank_statement", make_mock_doc(bank_pdf_text))
    print("Bank Extracted Fields:", bank_fields)
    assert "VIKRAM" in bank_fields.get("account_holder", "").upper()
    assert bank_fields.get("account_number", "").endswith("9012")
    assert bank_fields.get("ifsc") == "SBIN0001234"
    assert "STATE BANK OF INDIA" in bank_fields.get("bank_name", "").upper()
    assert bank_fields.get("statement_period") is not None

    print("\n=== 3. Testing Unknown Document handling ===")
    unknown_text = "The quick brown fox jumps over the lazy dog repeatedly in a field of wild flowers."
    classified_unknown = classify_document_content(unknown_text)
    print("Unknown Classification:", classified_unknown)
    assert classified_unknown["doc_type"] == "unknown"
    assert classified_unknown["document_type"] == "Unknown Document"
    assert classified_unknown["confidence"] == "low"

    print("\n=== 4. Testing End-to-End API upload in Offline Mode ===")
    client = TestClient(app)

    # 4a. Upload Bank Statement PDF
    resp = client.post(
        "/api/upload",
        files={"file": ("statement.pdf", pdf_bytes, "application/pdf")},
        data={"doc_type": "auto"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    print("API Bank Upload Result:", {
        "document_type": data.get("document_type"),
        "issuer": data.get("issuer"),
        "ocr_decision": data.get("ocr_decision"),
        "fields": data.get("extracted_fields")
    })
    assert data["document_type"] == "Bank Statement"
    assert "STATE BANK OF INDIA" in data["issuer"].upper()
    assert "VIKRAM" in data["extracted_fields"].get("account_holder", "").upper()
    assert data["extracted_fields"].get("account_number", "").endswith("9012")
    assert data["extracted_fields"].get("ifsc") == "SBIN0001234"

    # 4b. Upload Unknown Document text as PDF
    unknown_doc = fitz.open()
    unknown_page = unknown_doc.new_page()
    unknown_page.insert_text((50, 50), unknown_text)
    unknown_pdf_bytes = unknown_doc.write()
    unknown_doc.close()

    resp_unk = client.post(
        "/api/upload",
        files={"file": ("notes.pdf", unknown_pdf_bytes, "application/pdf")},
        data={"doc_type": "auto"}
    )
    assert resp_unk.status_code == 200, resp_unk.text
    data_unk = resp_unk.json()
    print("API Unknown Upload Result:", {
        "document_type": data_unk.get("document_type"),
        "issuer": data_unk.get("issuer"),
        "status": data_unk.get("status")
    })
    assert data_unk["document_type"] == "Unknown Document"
    print("Unknown extracted_fields:", data_unk.get("extracted_fields"))
    assert data_unk.get("extracted_fields") == {"document_type": "Unknown Document"}

    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_offline_pipeline_e2e()
