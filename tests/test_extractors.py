"""
tests/test_extractors.py
Comprehensive tests for all 13 document extractors.
"""

import os
import pytest
from ocr_engine import OCREngine, OCRDocumentResult, OCRLine, OCRPageResult
from extractors import (
    extract_document_fields,
    extract_document_fields_raw,
    mask_account_number,
    mask_aadhaar,
    EXTRACTOR_REGISTRY,
)

DEMO_DIR = "/home/vighnesh/Downloads/More_Demo_OCR_Test_Documents"


def create_mock_doc(text: str, conf: float = 0.98) -> OCRDocumentResult:
    lines = [OCRLine(text=l.strip(), confidence=conf) for l in text.split("\n") if l.strip()]
    page = OCRPageResult(page_num=1, full_text=text, lines=lines, average_confidence=conf)
    return OCRDocumentResult(pages=[page], full_text=text, average_confidence=conf)


def test_registry_contains_all_21_types():
    expected_types = {
        "pan", "aadhaar", "cancelled_cheque", "udyam", "fssai",
        "shop_establishment", "bank_statement", "salary_slip",
        "utility_bill", "passport", "voter_id", "driving_licence", "itr",
        "gst_certificate", "certificate_of_incorporation", "partnership_deed",
        "rent_agreement", "form_16", "bank_passbook", "property_tax_receipt", "iec_certificate",
    }
    assert set(EXTRACTOR_REGISTRY.keys()) == expected_types


def test_pan_extractor():
    text = """
    INCOME TAX DEPARTMENT
    GOVT. OF INDIA
    Permanent Account Number Card
    ABCDE1234F
    Name: JOHN DOE
    Father's Name: RICHARD ROE
    Date of Birth: 15/08/1990
    """
    fields, conf = extract_document_fields("pan", create_mock_doc(text))
    assert fields["pan_number"] == "ABCDE1234F"
    assert fields["name"] == "JOHN DOE"
    assert fields["father_name"] == "RICHARD ROE"
    assert fields["dob"] == "15/08/1990"
    assert conf["pan_number"] > 0.9


def test_aadhaar_extractor_with_masking():
    text = """
    UNIQUE IDENTIFICATION AUTHORITY OF INDIA
    Name: JANE DOE
    DOB: 01/01/1995
    Gender: Female
    Address: 123 Sample St, Pune, Maharashtra 411001
    Aadhaar Number: 5432 1098 7654
    """
    fields, _ = extract_document_fields("aadhaar", create_mock_doc(text))
    # Must be masked
    assert fields["aadhaar_number"] == "XXXXXXXX7654"
    assert fields["name"] == "JANE DOE"
    assert fields["dob"] == "01/01/1995"
    assert fields["gender"] == "Female"
    # Address must not be returned
    assert "address" not in fields
    assert "raw_aadhaar" not in fields


def test_cancelled_cheque_extractor():
    text = """
    STATE BANK OF INDIA
    Branch: PUNE MAIN BRANCH
    IFS Code: SBIN0001234
    A/C No. 123456789012
    Cheque Number: 000123
    Account Holder: DEMO CUSTOMER
    CANCELLED
    """
    fields, _ = extract_document_fields("cancelled_cheque", create_mock_doc(text))
    assert fields["marking"] == "CANCELLED"
    assert fields["account_number_masked"] == "XXXXXXXX9012"
    assert fields["ifsc"] == "SBIN0001234"
    assert fields["cheque_number"] == "000123"
    assert fields["account_holder"] == "DEMO CUSTOMER"


def test_udyam_extractor():
    text = """
    UDYAM REGISTRATION CERTIFICATE
    Enterprise Name: TECH VENTURES PRIVATE LIMITED
    Udyam Registration Number: UDYAM-MH-01-0012345
    Type of Enterprise: Micro
    Major Activity: Services
    """
    fields, _ = extract_document_fields("udyam", create_mock_doc(text))
    assert fields["udyam_registration_number"] == "UDYAM-MH-01-0012345"
    assert fields["enterprise_name"] == "TECH VENTURES PRIVATE LIMITED"
    assert fields["enterprise_type"] == "Micro"
    assert fields["major_activity"] == "Services"


def test_fssai_extractor():
    text = """
    FOOD SAFETY AND STANDARDS AUTHORITY OF INDIA
    Business Name: FRESH BAKES & FOODS
    FSSAI Licence Number: 10022022000123
    Kind of Business: Food Services
    Valid Till: 31/12/2028
    """
    fields, _ = extract_document_fields("fssai", create_mock_doc(text))
    assert fields["fssai_licence_number"] == "10022022000123"
    assert fields["business_name"] == "FRESH BAKES & FOODS"
    assert fields["valid_till"] == "31/12/2028"


def test_shop_establishment_extractor():
    text = """
    SHOP & ESTABLISHMENT REGISTRATION CERTIFICATE
    Establishment: METRO RETAILERS
    Registration Number: SHOP-MH-2026-999
    Employer: ALICE SMITH
    Nature of Business: Retail Trade
    """
    fields, _ = extract_document_fields("shop_establishment", create_mock_doc(text))
    assert fields["registration_number"] == "SHOP-MH-2026-999"
    assert fields["establishment_name"] == "METRO RETAILERS"


def test_passport_extractor():
    text = """
    REPUBLIC OF INDIA - PASSPORT
    Surname: SHARMA
    Given Name: ROHIT
    Nationality: INDIAN
    Passport Number: Z1234567
    Date of Birth: 24/04/1987
    Date of Expiry: 23/04/2037
    """
    fields, _ = extract_document_fields("passport", create_mock_doc(text))
    assert fields["passport_number"] == "Z1234567"
    assert fields["surname"] == "SHARMA"
    assert fields["given_name"] == "ROHIT"
    assert fields["dob"] == "24/04/1987"
    assert fields["expiry_date"] == "23/04/2037"


def test_voter_id_extractor():
    text = """
    ELECTION COMMISSION OF INDIA
    ELECTOR PHOTO IDENTITY CARD
    EPIC No: WXY1234567
    Name: VIKRAM PATIL
    Father's Name: SURESH PATIL
    Date of Birth: 12/06/1992
    """
    fields, _ = extract_document_fields("voter_id", create_mock_doc(text))
    assert fields["epic_number"] == "WXY1234567"
    assert fields["name"] == "VIKRAM PATIL"
    assert fields["relative_name"] == "SURESH PATIL"


def test_driving_licence_extractor():
    text = """
    UNION OF INDIA DRIVING LICENCE
    Licence Number: MH12 20260000001
    Name: AMIT VERMA
    Date of Birth: 05/11/1993
    Valid Till: 04/11/2043
    Vehicle Class: LMV
    """
    fields, _ = extract_document_fields("driving_licence", create_mock_doc(text))
    assert fields["licence_number"] == "MH12 20260000001"
    assert fields["name"] == "AMIT VERMA"
    assert fields["dob"] == "05/11/1993"
    assert fields["vehicle_class"] == "LMV"


def test_itr_extractor():
    text = """
    INDIAN INCOME TAX RETURN ACKNOWLEDGEMENT
    ITR-V
    Assessment Year: 2025-26
    PAN: ABCDE1234F
    Name: PRIYA NAIR
    Acknowledgement Number: 123456789012345
    Total Income: Rs. 12,50,000
    Taxes Paid: Rs. 1,45,000
    """
    fields, _ = extract_document_fields("itr", create_mock_doc(text))
    assert fields["acknowledgement_number"] == "123456789012345"
    assert fields["assessment_year"] == "2025-26"
    assert fields["pan_number"] == "ABCDE1234F"
    assert fields["name"] == "PRIYA NAIR"
    assert fields["total_income"] == "1250000"


def test_multi_page_bank_statement_merge():
    p1 = OCRPageResult(
        page_num=1,
        full_text="""
        HDFC BANK
        Account No. 987654321012
        Statement Period: 01/01/2026 to 31/01/2026
        01/01/2026 SALARY CREDIT 50000 CR 50000
        05/01/2026 ATM WITHDRAWAL 2000 DR 48000
        """,
        lines=[
            OCRLine("Account No. 987654321012", 0.98),
            OCRLine("01/01/2026 SALARY CREDIT 50000 CR 50000", 0.95),
            OCRLine("05/01/2026 ATM WITHDRAWAL 2000 DR 48000", 0.95),
        ],
        average_confidence=0.96,
    )
    p2 = OCRPageResult(
        page_num=2,
        full_text="""
        10/01/2026 UTILITY BILL 1500 DR 46500
        Closing Balance: Rs. 46,500
        """,
        lines=[
            OCRLine("10/01/2026 UTILITY BILL 1500 DR 46500", 0.95),
            OCRLine("Closing Balance: Rs. 46,500", 0.99),
        ],
        average_confidence=0.97,
    )
    doc_res = OCRDocumentResult(
        pages=[p1, p2],
        full_text=p1.full_text + "\n" + p2.full_text,
        average_confidence=0.965,
    )
    fields, _ = extract_document_fields("bank_statement", doc_res)

    assert fields["account_number_masked"] == "XXXXXXXX1012"
    assert fields["closing_balance"] == "46500"
    txns = fields["transactions"]
    # Verify rows from both page 1 and page 2 are merged chronologically
    assert len(txns) == 3
    assert txns[0]["amount"] == "50000"
    assert txns[1]["amount"] == "2000"
    assert txns[2]["amount"] == "1500"


@pytest.mark.skipif(not os.path.exists(DEMO_DIR), reason="Demo directory not found")
def test_extractors_against_real_demo_pdfs():
    engine = OCREngine()

    # Demo Aadhaar
    res = engine.process_file(os.path.join(DEMO_DIR, "Demo_Aadhaar_Card.pdf"))
    fields, _ = extract_document_fields("aadhaar", res)
    assert fields.get("aadhaar_number") == "XXXX XXXX 4321" or "4321" in fields.get("aadhaar_number", "")
    assert fields.get("name") == "DEMO CUSTOMER"

    # Demo Cheque
    res = engine.process_file(os.path.join(DEMO_DIR, "Demo_Cancelled_Cheque.pdf"))
    fields, _ = extract_document_fields("cancelled_cheque", res)
    assert fields.get("cheque_number") == "000123"
    assert "4321" in fields.get("account_number_masked", "")
    assert fields.get("ifsc") == "DEMO0001234"

    # Demo DL
    res = engine.process_file(os.path.join(DEMO_DIR, "Demo_Driving_Licence.pdf"))
    fields, _ = extract_document_fields("driving_licence", res)
    assert fields.get("licence_number") == "MH12 20260000001"
    assert fields.get("vehicle_class") == "LMV"


def test_field_boundary_bleed_regression_all_13_extractors():
    """
    Regression test for all 13 document extractors:
    Assert that source text where a field value is directly followed by
    another field's label with no newline or loose separator does NOT bleed
    the subsequent label into the extracted value.
    """
    # 1. PAN
    pan_text = "Permanent Account Number Card\nABCDE1234F Name: JOHN DOE Father's Name: RICHARD ROE Purpose: Testing Date of Birth: 01/01/1990"
    pan_fields, _ = extract_document_fields("pan", create_mock_doc(pan_text))
    assert pan_fields.get("name") == "JOHN DOE"
    assert pan_fields.get("father_name") == "RICHARD ROE"
    assert "Father" not in pan_fields.get("name", "")
    assert "Purpose" not in pan_fields.get("father_name", "")

    # 2. Aadhaar
    aadhaar_text = "Aadhaar Card 1234 5678 9012 Name: JANE DOE DOB: 01/01/1995 Gender: Female"
    aadhaar_fields, _ = extract_document_fields("aadhaar", create_mock_doc(aadhaar_text))
    assert aadhaar_fields.get("name") == "JANE DOE"
    assert "DOB" not in aadhaar_fields.get("name", "")
    assert "Gender" not in aadhaar_fields.get("name", "")

    # 3. Cancelled Cheque
    cheque_text = "STATE BANK OF INDIA Branch: PUNE CAMP IFS Code: SBIN0001234 Account Holder: DEMO CUSTOMER CANCELLED A/C No. 123456789012"
    cheque_fields, _ = extract_document_fields("cancelled_cheque", create_mock_doc(cheque_text))
    assert cheque_fields.get("branch") == "PUNE CAMP"
    assert cheque_fields.get("account_holder") == "DEMO CUSTOMER"
    assert "IFS" not in cheque_fields.get("branch", "")
    assert "CANCELLED" not in cheque_fields.get("account_holder", "")

    # 4. Udyam
    udyam_text = "UDYAM-MH-26-0804117 Enterprise Name: TECH VENTURES PRIVATE LIMITED SNo. 1 Classification Year: 2026-27 Type of Enterprise: Micro"
    udyam_fields, _ = extract_document_fields("udyam", create_mock_doc(udyam_text))
    assert udyam_fields.get("enterprise_name") == "TECH VENTURES PRIVATE LIMITED"
    assert "SNo" not in udyam_fields.get("enterprise_name", "")
    assert "Classification" not in udyam_fields.get("enterprise_name", "")

    # 5. FSSAI
    fssai_text = "FSSAI 10022022000123 Business Name: FRESH BAKES & FOODS Kind of Business: Food Services Valid Till: 31/12/2028"
    fssai_fields, _ = extract_document_fields("fssai", create_mock_doc(fssai_text))
    assert fssai_fields.get("business_name") == "FRESH BAKES & FOODS"
    assert "Kind of Business" not in fssai_fields.get("business_name", "")

    # 6. Shop & Establishment
    shop_text = "Registration Number: SHOP-MH-999 Establishment: METRO RETAILERS Employer: ALICE SMITH Nature of Business: Retail Trade"
    shop_fields, _ = extract_document_fields("shop_establishment", create_mock_doc(shop_text))
    assert shop_fields.get("establishment_name") == "METRO RETAILERS"
    assert shop_fields.get("employer_name") == "ALICE SMITH"
    assert "Employer" not in shop_fields.get("establishment_name", "")
    assert "Nature" not in shop_fields.get("employer_name", "")

    # 7. Bank Statement
    bank_text = "Bank Name: HDFC BANK Statement Period: 01/01/2026 to 31/01/2026 Account No. 987654321012 Closing Balance: Rs. 50,000"
    bank_fields, _ = extract_document_fields("bank_statement", create_mock_doc(bank_text))
    assert bank_fields.get("bank_name") == "HDFC BANK"
    assert "Statement" not in bank_fields.get("bank_name", "")

    # 8. Salary Slip
    salary_text = "Company: GLOBAL LOGISTICS PRIVATE LIMITED Employee Name: BOB MARLEY Net Salary: Rs. 85,000 Pay Period: January 2026"
    salary_fields, _ = extract_document_fields("salary_slip", create_mock_doc(salary_text))
    assert salary_fields.get("employer_name") == "GLOBAL LOGISTICS PRIVATE LIMITED"
    assert salary_fields.get("employee_name_masked") == "BOB M*****"
    assert "Employee" not in salary_fields.get("employer_name", "")

    # 9. Utility Bill
    bill_text = "Provider: TATA POWER COMPANY Consumer No: 123456789012 Bill Date: 15/01/2026 Due Date: 30/01/2026 Bill Amount: Rs. 2,450"
    bill_fields, _ = extract_document_fields("utility_bill", create_mock_doc(bill_text))
    assert bill_fields.get("utility_provider") == "TATA POWER COMPANY"
    assert "Consumer" not in bill_fields.get("utility_provider", "")

    # 10. Passport
    pass_text = "Passport Z1234567 Surname: SHARMA Given Name: ROHIT Nationality: INDIAN Date of Birth: 24/04/1987"
    pass_fields, _ = extract_document_fields("passport", create_mock_doc(pass_text))
    assert pass_fields.get("surname") == "SHARMA"
    assert pass_fields.get("given_name") == "ROHIT"
    assert "Given" not in pass_fields.get("surname", "")
    assert "Nationality" not in pass_fields.get("given_name", "")

    # 11. Voter ID
    voter_text = "EPIC No: WXY1234567 Name: VIKRAM PATIL Father's Name: SURESH PATIL Date of Birth: 12/06/1992"
    voter_fields, _ = extract_document_fields("voter_id", create_mock_doc(voter_text))
    assert voter_fields.get("name") == "VIKRAM PATIL"
    assert voter_fields.get("relative_name") == "SURESH PATIL"
    assert "Father" not in voter_fields.get("name", "")
    assert "Date" not in voter_fields.get("relative_name", "")

    # 12. Driving Licence
    dl_text = "Licence Number: MH12 20260000001 Name: AMIT VERMA Date of Birth: 05/11/1993 Vehicle Class: LMV"
    dl_fields, _ = extract_document_fields("driving_licence", create_mock_doc(dl_text))
    assert dl_fields.get("name") == "AMIT VERMA"
    assert "Date" not in dl_fields.get("name", "")

    # 13. ITR
    itr_text = "ITR-V Acknowledgement Number: 123456789012345 Name: PRIYA NAIR PAN: ABCDE1234F Total Income: Rs. 15,00,000 Taxes Paid: Rs. 2,50,000"
    itr_fields, _ = extract_document_fields("itr", create_mock_doc(itr_text))
    assert itr_fields.get("name") == "PRIYA NAIR"
    assert "PAN" not in itr_fields.get("name", "")


def test_itr_indian_currency_amounts_and_table_row_numbers():
    """
    Test ITR extractor with representative Indian comma-grouped currency figures
    and table row numbers (like row 1A for Total Income and row 7 for Taxes Paid).
    Assert full amounts are captured and not truncated to single digits.
    """
    # Sample matching genuine Indian ITR tabular layout
    tabular_itr_text = """
    Assessment Year: 2025-26
    PAN: CTDPC5789G
    Name: RUSHIKESH SHIVAJI CHIKHALE
    Acknowledgement Number: 980950140280526
    Current Year business loss, if any
    1
    0
    Total Income
    1A
    8,03,280
    Total tax, interest and Fee payable
    6
    0
    Taxes Paid
    7
    0
    """
    fields, _ = extract_document_fields("itr", create_mock_doc(tabular_itr_text))
    assert fields.get("name") == "RUSHIKESH SHIVAJI CHIKHALE"
    assert fields.get("total_income") == "803280"
    assert fields.get("taxes_paid") == "0"

    # High currency figures with Indian grouping (Lakhs and Crores)
    high_figure_text = """
    ITR-4 SUGAM Acknowledgement
    PAN: ABCDE1234F
    Name: ANANYA SHARMA
    Acknowledgement Number: 112233445566778
    Total Income: Rs. 15,50,000
    Taxes Paid: Rs. 3,25,000
    """
    fields_high, _ = extract_document_fields("itr", create_mock_doc(high_figure_text))
    assert fields_high.get("total_income") == "1550000"
    assert fields_high.get("taxes_paid") == "325000"

    # 7-digit crore figure
    crore_figure_text = """
    Total Income: 1,25,00,000
    Taxes Paid: 42,50,000
    """
    fields_crore, _ = extract_document_fields("itr", create_mock_doc(crore_figure_text))
    assert fields_crore.get("total_income") == "12500000"
    assert fields_crore.get("taxes_paid") == "4250000"


def test_real_vault_documents_bleed_regression():
    """
    Regression test using the actual extracted text from genuine documents
    stored in the vault, verifying that the corrupted fields are resolved cleanly.
    """
    # 1. Demo_PAN_Card.pdf
    pan_raw_text = """INCOME TAX DEPARTMENT - PAN CARD
TEST / REDACTED SAMPLE
Field\n\nDemo Value\n\nName\n\nDEMO CUSTOMER\n\nPermanent Account Number\n\nABCDE1234F\n\nDate of Birth\n\n01/01/1995\n\nFather's Name\n\nDEMO FATHER\n\nPurpose\n\nOCR workflow testing only\n\nDEMO DOCUMENT - NOT VALID FOR ANY OFFICIAL USE"""
    pan_fields, _ = extract_document_fields("pan", create_mock_doc(pan_raw_text))
    assert pan_fields["father_name"] == "DEMO FATHER"
    assert "Purpose" not in pan_fields["father_name"]

    # 2. ROYAL CAKE HOUSE.pdf
    udyam_raw_text = """UDYAM REGISTRATION CERTIFICATE\nUDYAM REGISTRATION NUMBER\n\nUDYAM-MH-26-0804117\n\nNAME OF ENTERPRISE\n\nROYAL CAKE HOUSE\nSNo.\n\nClassification Year\n\nEnterprise Type\n\n1\n\n2026-27\n\nMicro"""
    udyam_fields, _ = extract_document_fields("udyam", create_mock_doc(udyam_raw_text))
    assert udyam_fields["enterprise_name"] == "ROYAL CAKE HOUSE"
    assert "SNo" not in udyam_fields["enterprise_name"]
    assert "Classification" not in udyam_fields["enterprise_name"]

    # 3. ITR SET FY 2025-26.pdf
    itr_raw_text = """Acknowledgement Number:980950140280526\n\n2026-27\n\nCTDPC5789G\n\nName\n\nRUSHIKESH SHIVAJI CHIKHALE\n\nAddress\n\nHouse No 481\n\nTotal Income\n\n1A\n\n8,03,280\n\nTaxes Paid\n\n7\n\n0"""
    itr_fields, _ = extract_document_fields("itr", create_mock_doc(itr_raw_text))
    assert itr_fields["name"] == "RUSHIKESH SHIVAJI CHIKHALE"
    assert "Address" not in itr_fields["name"]
    assert itr_fields["total_income"] == "803280"
    assert itr_fields["taxes_paid"] == "0"


# ==============================================================================
# Part A1: MICR Line Reading & Cross-Checking Tests
# ==============================================================================

def test_micr_clean_line_extraction():
    """A1: Assert clean MICR line extracts cheque number, MICR code, account number, tran code with high confidence."""
    from micr_reader import parse_micr_string

    # Standard Indian Cheque MICR format with E-13B symbols
    clean_line = "⑆000123⑆ 400002001⑈ 123456789012⑇ 10"
    data, conf = parse_micr_string(clean_line)

    assert data["cheque_number"] == "000123"
    assert data["micr_code"] == "400002001"
    assert data["account_number"] == "123456789012"
    assert data["account_number_masked"] == "XXXXXXXX9012"
    assert data["tran_code"] == "10"
    assert conf == "high"
    assert data["micr_confidence"] == "high"
    assert data["micr_confidence_score"] >= 0.90


def test_micr_degraded_line_flagged_low_confidence():
    """A1: Assert degraded/corrupt MICR line produces micr_confidence: 'low' without fabricating digits."""
    from micr_reader import parse_micr_string

    # Degraded line with wrong digit counts (5 digits for cheque, 8 for MICR, missing delimiters)
    degraded_line = "⑆00123⑆ 40000201⑈ ??"
    data, conf = parse_micr_string(degraded_line)

    assert conf == "low"
    assert data["micr_confidence"] == "low"
    assert data["micr_confidence_score"] <= 0.50
    # Digits must NOT be silently fabricated to reach 6 or 9 digits
    assert data.get("cheque_number") != "000123"
    assert data.get("micr_code") != "400002001"


def test_micr_cross_check_agreement_and_disagreement():
    """A1: Assert agreement when MICR matches full-page fields, and disagreement surfaced when differing."""
    from micr_reader import parse_micr_string, cross_check_micr_with_cheque_fields

    micr_line = "⑆000123⑆ 400002001⑈ 123456789012⑇ 10"
    data, _ = parse_micr_string(micr_line)

    # 1. Full match
    matching_fields = {"cheque_number": "000123", "account_number_masked": "XXXXXX9012"}
    match, disagreements = cross_check_micr_with_cheque_fields(data, matching_fields)
    assert match is True
    assert len(disagreements) == 0

    # 2. Disagreement on cheque number and account number
    mismatch_fields = {"cheque_number": "999999", "account_number_masked": "XXXXXX4321"}
    match, disagreements = cross_check_micr_with_cheque_fields(data, mismatch_fields)
    assert match is False
    assert len(disagreements) == 2
    assert any("Cheque number mismatch" in d for d in disagreements)
    assert any("Account number mismatch" in d for d in disagreements)


def test_micr_crop_and_extract_from_cheque_image():
    """A1: Test cropping bottom 20% band and extracting MICR via dedicated OCR func."""
    from PIL import Image
    from micr_reader import extract_micr_from_cheque, crop_cheque_bottom_band

    img = Image.new("RGB", (600, 300), color="white")
    cropped = crop_cheque_bottom_band(img, band_ratio=0.20)
    assert cropped.size == (600, 60)

    # Mock OCR function specifically reading the bottom band
    mock_band_ocr = lambda cropped_img: ("⑆000123⑆ 400002001⑈ 123456789012⑇ 10", 0.95)
    result = extract_micr_from_cheque(
        cheque_img=img,
        ocr_func=mock_band_ocr,
        full_page_fields={"cheque_number": "000123", "account_number_masked": "XXXXXX9012"},
    )
    assert result["cheque_number"] == "000123"
    assert result["micr_code"] == "400002001"
    assert result["micr_confidence"] == "high"
    assert result["micr_match"] is True


def test_micr_pipeline_end_to_end_on_real_demo_cheque_file():
    """
    Task 1 Integration Test:
    Runs the real end-to-end pipeline (PDF render -> bottom 20% crop -> OCR -> parse)
    against the actual Demo_Cancelled_Cheque.pdf document.
    Asserts the pipeline correctly characterizes its own confidence as 'low' rather than
    hallucinating or fabricating digits when E-13B MICR line is missing/unreadable.
    """
    from ocr_engine import OCREngine, render_pdf_pages_to_images
    from micr_reader import crop_cheque_bottom_band, parse_micr_string, extract_micr_from_cheque

    cheque_pdf = os.path.join(DEMO_DIR, "Demo_Cancelled_Cheque.pdf")
    imgs = render_pdf_pages_to_images(cheque_pdf)
    assert len(imgs) >= 1
    page_img = imgs[0]

    # 1. Crop bottom 20% band
    band_img = crop_cheque_bottom_band(page_img, band_ratio=0.20)
    expected_height = page_img.size[1] - int(page_img.size[1] * (1.0 - 0.20))
    assert band_img.size == (page_img.size[0], expected_height)

    # 2. Run OCR directly on cropped band
    engine = OCREngine()
    page_res = engine.process_image(band_img)
    raw_band_text = page_res.full_text

    # 3. Parse with parse_micr_string
    parsed_data, conf = parse_micr_string(raw_band_text)
    assert conf == "low"
    assert parsed_data["micr_confidence"] == "low"
    # Ensure no fabricated digits
    assert parsed_data.get("micr_code") is None

    # 4. Full extract_micr_from_cheque call with ocr_func
    ocr_func = lambda cropped: (engine.process_image(cropped).full_text, None)
    full_result = extract_micr_from_cheque(
        cheque_img=page_img,
        ocr_func=ocr_func,
        ocr_full_text=engine.process_pdf(cheque_pdf).full_text,
        full_page_fields={"cheque_number": "000123", "account_number_masked": "XXXXXX4321"},
    )
    assert full_result["micr_confidence"] == "low"
    assert full_result["micr_confidence_score"] <= 0.50
    assert full_result["cheque_number"] == "000123"


# ==============================================================================
# Part A2: State-Specific Shop & Establishment Parsing Tests
# ==============================================================================

def test_shop_establishment_state_registry_mh_match():
    """A2: Test Maharashtra Shop & Establishment template match with validated state fields and template_verified=True."""
    from extractors import extract_shop_establishment

    mh_text = """
    GOVERNMENT OF MAHARASHTRA
    LABOUR DEPARTMENT - PUNE MUNICIPAL CORPORATION
    FORM G - CERTIFICATE OF REGISTRATION UNDER MAHARASHTRA SHOPS & ESTABLISHMENTS ACT
    Registration Number: MH/PUN/2026/009876
    Establishment: METRO SWEETS & BAKERY
    Employer: RAJESH KULKARNI
    Nature of Business: Bakery & Food Products
    Address: PUNE, MAHARASHTRA
    """
    fields, confs = extract_shop_establishment(create_mock_doc(mh_text))

    assert fields["state"] == "MH"
    assert fields["state_name"] == "Maharashtra"
    assert fields["issuing_authority"] == "Government of Maharashtra"
    assert fields["template_matched"] is True
    assert fields["template_verified"] is True
    assert fields["registration_number"] == "MH/PUN/2026/009876"
    assert fields["establishment_name"] == "METRO SWEETS & BAKERY"
    assert fields["employer_name"] == "RAJESH KULKARNI"
    assert fields["nature_of_business"] == "Bakery & Food Products"


def test_shop_establishment_dl_template_synthetic_reference_unverified():
    """
    A2: Test Delhi template parsing against a clearly-labeled synthetic reference statutory layout
    (Delhi Form C under Delhi Shops and Establishments Act, 1954).
    Asserts template matches but is honestly flagged as template_verified: False (unverified against real scan).
    """
    from extractors import extract_shop_establishment

    dl_synthetic_reference_text = """
    GOVERNMENT OF NCT OF DELHI
    DEPARTMENT OF LABOUR - DISTRICT SOUTH
    FORM C - REGISTRATION CERTIFICATE OF ESTABLISHMENT
    DELHI SHOPS & ESTABLISHMENTS ACT 1954
    Registration Number: DL/2026/SE/004512
    Name of Establishment: CAPITAL CONSULTING PRIVATE LIMITED
    Employer: VIKAS KHANNA
    Nature of Business: Commercial & Consulting Services
    Address: CONNAUGHT PLACE, NEW DELHI
    """
    fields, _ = extract_shop_establishment(create_mock_doc(dl_synthetic_reference_text))

    assert fields["state"] == "DL"
    assert fields["state_name"] == "Delhi"
    assert fields["issuing_authority"] == "Government of NCT of Delhi"
    assert fields["template_matched"] is True
    # Explicitly flagged as unverified because no real scan sample has been validated
    assert fields["template_verified"] is False
    assert fields["registration_number"] == "DL/2026/SE/004512"
    assert fields["establishment_name"] == "CAPITAL CONSULTING PRIVATE LIMITED"
    assert fields["employer_name"] == "VIKAS KHANNA"


def test_shop_establishment_ka_template_synthetic_reference_unverified():
    """
    A2: Test Karnataka template parsing against a clearly-labeled synthetic reference statutory layout
    (Karnataka Form C under Karnataka Shops and Commercial Establishments Act, 1961 / e-Karmika).
    Asserts template matches but is honestly flagged as template_verified: False (unverified against real scan).
    """
    from extractors import extract_shop_establishment

    ka_synthetic_reference_text = """
    GOVERNMENT OF KARNATAKA
    DEPARTMENT OF LABOUR - e-Karmika PORTAL
    FORM C - REGISTRATION CERTIFICATE OF ESTABLISHMENT
    KARNATAKA SHOPS AND COMMERCIAL ESTABLISHMENTS ACT 1961
    Registration Number: KA/BLR/2026/982134
    Name of Establishment: BENGALURU DIGITAL INNOVATIONS
    Employer: SURESH RAO
    Nature of Business: Information Technology
    Address: KORAMANGALA, BANGALORE, KARNATAKA
    """
    fields, _ = extract_shop_establishment(create_mock_doc(ka_synthetic_reference_text))

    assert fields["state"] == "KA"
    assert fields["state_name"] == "Karnataka"
    assert fields["issuing_authority"] == "Government of Karnataka"
    assert fields["template_matched"] is True
    # Explicitly flagged as unverified because no real scan sample has been validated
    assert fields["template_verified"] is False
    assert fields["registration_number"] == "KA/BLR/2026/982134"
    assert fields["establishment_name"] == "BENGALURU DIGITAL INNOVATIONS"
    assert fields["employer_name"] == "SURESH RAO"


def test_shop_establishment_fallback_unrecognized_state():
    """A2: Fall back gracefully to generic extraction with template_matched: False and template_verified: False when state is unrecognized."""
    from extractors import extract_shop_establishment

    generic_text = """
    DEPARTMENT OF LABOUR
    SHOP & ESTABLISHMENT REGISTRATION CERTIFICATE
    Registration Number: SE-UNKNOWN-2026-11
    Establishment: GLOBAL TRADING HUB
    Employer: JOHN DOE
    Nature of Business: Import Export
    """
    fields, _ = extract_shop_establishment(create_mock_doc(generic_text))

    assert fields["template_matched"] is False
    assert fields["template_verified"] is False
    assert fields["state"] is None
    assert fields["registration_number"] == "SE-UNKNOWN-2026-11"
    assert fields["establishment_name"] == "GLOBAL TRADING HUB"
    assert fields["employer_name"] == "JOHN DOE"


# ==============================================================================
# Part B1: Clean Field Value Logging Tests
# ==============================================================================

def test_clean_field_value_logs_trim_without_pii(caplog):
    """B1: Assert log entry is emitted at INFO level without PII when field cleaning trims content."""
    import logging
    from extractors import clean_field_value

    with caplog.at_level(logging.INFO, logger="extractors"):
        val_with_bleed = "ROYAL CAKE HOUSE\nSNo.\n\nClassification Year\n\nEnterprise Type"
        res = clean_field_value(val_with_bleed, field_name="enterprise_name", doc_type="udyam")

    assert res == "ROYAL CAKE HOUSE"
    # Confirm log was emitted
    trim_records = [r for r in caplog.records if "trimmed residual bleed" in r.message]
    assert len(trim_records) >= 1
    log_msg = trim_records[0].message
    assert "field=enterprise_name" in log_msg
    assert "doc_type=udyam" in log_msg
    # Ensure NO PII or trimmed text leaked into log message
    assert "ROYAL CAKE HOUSE" not in log_msg
    assert "Classification" not in log_msg


def test_clean_field_value_warns_on_suspicious_output(caplog):
    """B1: Assert warning log is emitted if cleaned field value remains unusually long (>80 chars)."""
    import logging
    from extractors import clean_field_value

    with caplog.at_level(logging.WARNING, logger="extractors"):
        suspicious_long_val = "A" * 90
        clean_field_value(suspicious_long_val, field_name="father_name", doc_type="pan")

    warn_records = [r for r in caplog.records if "suspicious" in r.message and r.levelno == logging.WARNING]
    assert len(warn_records) >= 1
    assert "father_name" in warn_records[0].message
    assert "pan" in warn_records[0].message


# ==============================================================================
# Part B2: Shared Status Determination Tests
# ==============================================================================

def test_determine_document_status_unification():
    """B2: Confirm determine_document_status produces identical status for vault and API pipeline."""
    from verifier import determine_document_status

    # Checksum failure -> warning in vault, low_confidence in pipeline
    assert determine_document_status(checksum_valid=False, average_confidence=0.95, vault_mode=True) == "warning"
    assert determine_document_status(checksum_valid=False, average_confidence=0.95, vault_mode=False) == "low_confidence"

    # Checksum valid + high confidence -> completed (vault) / success (pipeline)
    assert determine_document_status(checksum_valid=True, average_confidence=0.98, vault_mode=True) == "completed"
    assert determine_document_status(checksum_valid=True, average_confidence=0.98, vault_mode=False) == "success"

    # Checksum valid + low confidence (< 0.70) -> low_confidence
    assert determine_document_status(checksum_valid=True, average_confidence=0.65, vault_mode=True) == "low_confidence"
    assert determine_document_status(checksum_valid=True, average_confidence=0.65, vault_mode=False) == "low_confidence"


# ==============================================================================
# Part B3: Real/Demo Salary Slip Extraction Tests
# ==============================================================================

def test_salary_slip_real_demo_documents_employer_name():
    """B3: Test salary slip employer extraction against actual Demo_Salary_Slip documents."""
    from extractors import extract_salary_slip, sanitize_extracted_fields

    # Digital text layout from Demo_Salary_Slip.pdf
    pdf_text = """
    DEMO COMPANY PRIVATE LIMITED - SALARY SLIP
    SYNTHETIC DEMO DOCUMENT — NOT VALID FOR OFFICIAL USE
    Field\n\nDemo / Redacted Value\n\nEmployee\n\nDEMO CUSTOMER\n\nEmployee ID\n\nDEMO-E1024
    Month\n\nAugust 2026\n\nBasic Salary\n\nRs. 35,000\n\nHRA\n\nRs. 12,000\n\nNet Salary\n\nRs. 49,500
    """
    fields_pdf, confs_pdf = extract_salary_slip(create_mock_doc(pdf_text))
    san_pdf, _ = sanitize_extracted_fields("salary_slip", fields_pdf, confs_pdf)
    assert san_pdf["employer_name"] == "DEMO COMPANY PRIVATE LIMITED"
    assert san_pdf["employee_name_masked"] == "DEMO C*******"
    assert san_pdf["net_pay"] == "49500"
    assert san_pdf["pay_period"] == "August 2026"

    # Scanned OCR layout from Demo_Salary_Slip_Image.png
    ocr_img_text = """
    DEMO COMPANY PVT LTD
    SALARY SLIP - AUGUST 2026
    Employee
    DEMO CUSTOMER
    Employee ID
    DEMO-E1024
    Basic
    Rs. 35,000
    HRA
    Rs. 12,000
    NET SALARY
    Rs. 49,500
    """
    fields_img, confs_img = extract_salary_slip(create_mock_doc(ocr_img_text))
    san_img, _ = sanitize_extracted_fields("salary_slip", fields_img, confs_img)
    assert san_img["employer_name"] == "DEMO COMPANY PVT LTD"
    assert san_img["employee_name_masked"] == "DEMO C*******"
    assert san_img["net_pay"] == "49500"


# ==============================================================================
# 8 New Document Types: Extraction & Bleed Tests
# ==============================================================================

def test_gst_certificate_extractor_and_bleed():
    text = """
    Government of India
    Form GST REG-06
    Registration Certificate
    Registration Number: 27AABCU9603R1ZN
    Legal Name: ACME ENTERPRISES PRIVATE LIMITED
    Trade Name, if any: ACME DIGITAL SOLUTIONS
    Constitution of Business: Private Limited Company
    Date of Registration: 01/07/2025
    GOODS AND SERVICES TAX
    """
    fields, conf = extract_document_fields("gst_certificate", create_mock_doc(text))
    assert fields["gstin"] == "27AABCU9603R1ZN"
    assert fields["legal_name"] == "ACME ENTERPRISES PRIVATE LIMITED"
    assert fields["trade_name"] == "ACME DIGITAL SOLUTIONS"
    assert fields["constitution_of_business"] == "Private Limited Company"
    assert fields["registration_date"] == "01/07/2025"

    # Field-boundary bleed regression: next field header immediately follows without empty line
    bleed_text = """
    Legal Name: ROYAL CATERERS PRIVATE LIMITED
    Trade Name: ROYAL SWEETS
    Constitution of Business: Partnership Firm
    Date of Registration: 15/08/2024
    """
    b_fields, _ = extract_document_fields("gst_certificate", create_mock_doc(bleed_text))
    assert b_fields["legal_name"] == "ROYAL CATERERS PRIVATE LIMITED"
    assert b_fields["trade_name"] == "ROYAL SWEETS"
    assert "Trade Name" not in b_fields["legal_name"]


def test_certificate_of_incorporation_extractor_and_bleed():
    text = """
    GOVERNMENT OF INDIA
    MINISTRY OF CORPORATE AFFAIRS
    CERTIFICATE OF INCORPORATION
    I hereby certifies that NEXUS ROBOTICS PRIVATE LIMITED is incorporated on this Twelfth day of August 2025
    Corporate Identity Number: U72900MH2025PTC412345
    Registrar of Companies, ROC Mumbai
    """
    fields, conf = extract_document_fields("certificate_of_incorporation", create_mock_doc(text))
    assert fields["cin"] == "U72900MH2025PTC412345"
    assert fields["company_name"] == "NEXUS ROBOTICS PRIVATE LIMITED"
    assert "August 2025" in fields["date_of_incorporation"]
    assert "ROC Mumbai" in fields["registrar_office"]

    # Field-boundary bleed regression
    bleed_text = """
    Name of the Company: APEX MOTORS LIMITED
    Corporate Identity Number: U29100DL2024PLC123456
    Date of Incorporation: 05/01/2024
    """
    b_fields, _ = extract_document_fields("certificate_of_incorporation", create_mock_doc(bleed_text))
    assert b_fields["company_name"] == "APEX MOTORS LIMITED"
    assert "Corporate" not in b_fields["company_name"]


def test_partnership_deed_extractor_and_bleed():
    text = """
    DEED OF PARTNERSHIP
    Between:
    Party of the First Part: MR. VIKRAM MALHOTRA
    Party of the Second Part: MR. ROHAN DESHMUKH
    Firm Name: MALHOTRA & DESHMUKH TRADERS
    Date of Deed: 01/04/2025
    Profit Sharing Ratio: 50:50
    """
    fields, conf = extract_document_fields("partnership_deed", create_mock_doc(text))
    assert fields["firm_name"] == "MALHOTRA & DESHMUKH TRADERS"
    assert "partner_names" not in fields
    assert "raw_partner_names" not in fields
    assert isinstance(fields["partner_names_masked"], list)
    assert "MR. M*******" in fields["partner_names_masked"]
    assert "MR. D*******" in fields["partner_names_masked"]
    assert fields["profit_sharing_ratio"] == "50:50"
    assert fields["date_of_deed"] == "01/04/2025"

    # Verify raw extractor retains unmasked names for verification/cross-check
    raw_fields, _ = extract_document_fields_raw("partnership_deed", create_mock_doc(text))
    assert "MR. VIKRAM MALHOTRA" in raw_fields["partner_names"]
    assert "MR. ROHAN DESHMUKH" in raw_fields["partner_names"]

    # Field-boundary bleed regression
    bleed_text = """
    Firm Name: SUNRISE TEXTILES
    Date of Execution: 12/03/2024
    Profit Sharing Ratio: 60:40
    """
    b_fields, _ = extract_document_fields("partnership_deed", create_mock_doc(bleed_text))
    assert b_fields["firm_name"] == "SUNRISE TEXTILES"
    assert "Date" not in b_fields["firm_name"]


def test_rent_agreement_extractor_and_bleed():
    text = """
    RENT AGREEMENT
    LESSOR: MR. SURESH MENON
    LESSEE: MR. ARJUN NAIR
    Premises situated at: Flat 302, Green Meadows, Bengaluru 560034
    Monthly Rent: Rs. 35,000
    Lease period from: 01/06/2025
    Expiring on: 30/04/2026
    """
    fields, conf = extract_document_fields("rent_agreement", create_mock_doc(text))
    # PII allowlist checks:
    assert "lessor_name_masked" in fields
    assert fields["lessor_name_masked"] == "MR. M****"
    assert "lessee_name_masked" in fields
    assert fields["lessee_name_masked"] == "MR. N***"
    assert fields["monthly_rent"] == "35000"
    assert fields["agreement_start_date"] == "01/06/2025"
    assert fields["agreement_end_date"] == "30/04/2026"
    assert "XXXX" in fields["property_address_masked"]
    # Raw personal details must NOT appear
    assert "raw_lessor_name" not in fields
    assert "raw_property_address" not in fields

    # Field-boundary bleed regression
    bleed_text = """
    LESSOR: PRIYA SHARMA
    LESSEE: ROHIT VERMA
    Monthly Rent: 20000
    """
    b_fields, _ = extract_document_fields("rent_agreement", create_mock_doc(bleed_text))
    assert b_fields["lessor_name_masked"] == "PRIYA S*****"
    assert b_fields["lessee_name_masked"] == "ROHIT V****"


def test_form_16_extractor_and_bleed():
    text = """
    FORM NO. 16
    Certificate under section 203 of the Income-tax Act
    Name of the Employer: INFOTECH SOLUTIONS INDIA PRIVATE LIMITED
    Name of the Employee: MR. KAVIN SHARMA
    Employee PAN: ABCPS1234E
    Deductor TAN: HYDI12345F
    Assessment Year: 2025-26
    Gross Salary: Rs. 14,50,000.00
    Total Tax Deducted: Rs. 1,25,000.00
    """
    fields, conf = extract_document_fields("form_16", create_mock_doc(text))
    assert fields["employer_name"] == "INFOTECH SOLUTIONS INDIA PRIVATE LIMITED"
    assert fields["employee_name_masked"] == "MR. S*****"
    assert fields["pan_number"] == "ABCPS1234E"
    assert fields["tan_number"] == "HYDI12345F"
    assert fields["assessment_year"] == "2025-26"
    assert fields["gross_salary"] == "1450000.00"
    assert fields["tax_deducted"] == "125000.00"
    assert "raw_employee_name" not in fields

    # Field-boundary bleed regression
    bleed_text = """
    Name of the Employer: TECHNO CORP
    Name of the Employee: AMIT PATEL
    Employee PAN: AAACP1234K
    """
    b_fields, _ = extract_document_fields("form_16", create_mock_doc(bleed_text))
    assert b_fields["employer_name"] == "TECHNO CORP"
    assert "Name of the Employee" not in b_fields["employer_name"]


def test_bank_passbook_extractor_and_bleed():
    text = """
    STATE BANK OF INDIA
    SAVINGS BANK PASS BOOK
    Branch Name: KORAMANGALA
    IFSC: SBIN0004567
    Account Number: 20123456789
    Name of Account Holder: PRIYA SHARMA
    """
    fields, conf = extract_document_fields("bank_passbook", create_mock_doc(text))
    assert fields["bank_name"] == "STATE BANK OF INDIA"
    assert fields["branch"] == "KORAMANGALA"
    assert fields["ifsc"] == "SBIN0004567"
    assert fields["account_number_masked"] == "XXXXXXX6789"
    assert fields["account_holder_name_masked"] == "PRIYA S*****"
    assert "raw_account_number" not in fields

    # Field-boundary bleed regression
    bleed_text = """
    Name of Account Holder: RAHUL GUPTA
    Account Number: 987654321012
    IFSC: HDFC0000123
    """
    b_fields, _ = extract_document_fields("bank_passbook", create_mock_doc(bleed_text))
    assert b_fields["account_holder_name_masked"] == "RAHUL G****"
    assert "Account Number" not in b_fields["account_holder_name_masked"]


def test_property_tax_receipt_extractor_and_bleed():
    text = """
    MUNICIPAL CORPORATION PROPERTY TAX RECEIPT
    Property ID: PID-88992211
    Owner Name: MR. RAMESH KUMAR
    Assessment Year: 2025-26
    Payment Date: 20/05/2025
    Tax Amount Paid: Rs. 8,450.00
    """
    fields, conf = extract_document_fields("property_tax_receipt", create_mock_doc(text))
    assert fields["property_id"] == "PID-88992211"
    assert fields["owner_name_masked"] == "MR. K****"
    assert fields["assessment_year"] == "2025-26"
    assert fields["payment_date"] == "20/05/2025"
    assert fields["tax_amount_paid"] == "8450.00"
    assert "raw_owner_name" not in fields

    # Field-boundary bleed regression
    bleed_text = """
    Owner Name: SUNITA DESHMUKH
    Property ID: PID-112233
    Assessment Year: 2024-25
    """
    b_fields, _ = extract_document_fields("property_tax_receipt", create_mock_doc(bleed_text))
    assert b_fields["owner_name_masked"] == "SUNITA D*******"
    assert "Property ID" not in b_fields["owner_name_masked"]


def test_iec_certificate_extractor_and_bleed():
    text = """
    IMPORTER EXPORTER CODE (IEC) CERTIFICATE
    IEC Number: 0312345678
    Entity Name: GLOBAL OVERSEAS LOGISTICS LLP
    PAN: AABCG1234M
    Issue Date: 10/01/2024
    """
    fields, conf = extract_document_fields("iec_certificate", create_mock_doc(text))
    assert fields["iec_number"] == "0312345678"
    assert fields["entity_name"] == "GLOBAL OVERSEAS LOGISTICS LLP"
    assert fields["pan_number"] == "AABCG1234M"
    assert fields["issue_date"] == "10/01/2024"

    # Field-boundary bleed regression
    bleed_text = """
    Entity Name: ORIENT EXPORTS PRIVATE LIMITED
    IEC Number: 0522334455
    PAN: AAACZ1234R
    """
    b_fields, _ = extract_document_fields("iec_certificate", create_mock_doc(bleed_text))
    assert b_fields["entity_name"] == "ORIENT EXPORTS PRIVATE LIMITED"
    assert "IEC Number" not in b_fields["entity_name"]


def test_mask_address_quality_and_preservation():
    from extractors import mask_address

    # Case 1: Street number with locality, city, state, PIN
    res1 = mask_address("123 MG Road, Andheri West, Mumbai, Maharashtra 400058")
    assert res1 == "XXXX, Andheri West, Mumbai, Maharashtra 400058"
    assert "123" not in res1
    assert "Andheri West" in res1
    assert "Mumbai" in res1
    assert "400058" in res1

    # Case 2: Multi-part premise (Flat + Building) with society, city, PIN
    res2 = mask_address("Flat 402, Building C, Sunshine Heights, Pune 411038")
    assert res2 == "XXXX, Sunshine Heights, Pune 411038"
    assert "402" not in res2
    assert "Building C" not in res2
    assert "Sunshine Heights" in res2
    assert "Pune 411038" in res2

    # Case 3: Flat + society + city + PIN
    res3 = mask_address("Flat 302, Green Meadows, Bengaluru 560034")
    assert res3 == "XXXX, Green Meadows, Bengaluru 560034"
    assert "302" not in res3
    assert "Green Meadows" in res3
    assert "Bengaluru 560034" in res3

    # Case 4: Non-comma separated address
    res4 = mask_address("Flat 302 Green Meadows Bengaluru 560034")
    assert "XXXX" in res4
    assert "302" not in res4
    assert "Green Meadows Bengaluru 560034" in res4

    # Case 5: Empty / None
    assert mask_address(None) is None
    assert mask_address("") is None



