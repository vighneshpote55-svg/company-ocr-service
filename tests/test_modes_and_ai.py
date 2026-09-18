"""
tests/test_modes_and_ai.py
Unit and integration tests for Offline Mode and AI Mode endpoints:
- /api/mode/offline (supported document -> supported=True)
- /api/mode/offline (unsupported document -> supported=False with specific rejection message)
- /api/mode/ai/status (runtime AI configuration discovery)
- /api/mode/ai/analyze (analyzes document, returns structured document_type, confidence, summary, reasoning)
- /api/mode/ai/chat (answers questions grounded in document text)
- Context isolation between multiple documents in AI mode
- Error handling for missing AI API key and corrupt files
"""

import io
import json
import os
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
import document_store
import ai_service


@pytest.fixture(autouse=True)
def reset_app_security(monkeypatch):
    import main
    main._startup_security_error = None
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    yield
    main._startup_security_error = None


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _create_test_image(text_lines):
    """Helper to generate an in-memory image with readable text lines."""
    img = Image.new("RGB", (500, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 20
    for line in text_lines:
        draw.text((20, y), line, fill=(0, 0, 0))
        y += 35
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_ai_mode_status_endpoint(client, monkeypatch):
    """Test GET /api/mode/ai/status reports provider and key configuration."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    res = client.get("/api/mode/ai/status")
    assert res.status_code == 200
    data = res.json()
    assert "configured" in data
    assert data["configured"] is False
    assert "AI_API_KEY is not set" in data["message"]

    monkeypatch.setenv("AI_API_KEY", "test-mock-key-12345")
    res2 = client.get("/api/mode/ai/status")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["configured"] is True


def test_offline_mode_supported_document_succeeds(client):
    """Test Offline Mode with a supported Indian document type (PAN Card)."""
    buf = _create_test_image([
        "INCOME TAX DEPARTMENT",
        "PERMANENT ACCOUNT NUMBER",
        "ABCDE1234F",
        "FATHER'S NAME: RAMESH SHARMA",
    ])

    res = client.post(
        "/api/mode/offline",
        files={"file": ("pan_sample.png", buf, "image/png")},
        data={"doc_type": "pan"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["supported"] is True
    assert data["doc_type"] == "pan"
    assert data["status"] in ("completed", "success", "low_confidence", "warning")
    assert "extracted_fields" in data


def test_offline_mode_unsupported_document_ocr_and_unknown(client):
    """
    Test Offline Mode with an unsupported document (e.g., Employment Agreement or general notice).
    Must NOT reject the upload. Must perform OCR, classify as Unknown Document,
    store in vault, preserve extracted_text, set ocr_completed=True, and recommend AI Mode.
    """
    buf = _create_test_image([
        "ACME CORPORATION EMPLOYMENT AGREEMENT",
        "EMPLOYEE NAME: JOHN SMITH",
        "DESIGNATION: SENIOR SOFTWARE ENGINEER",
        "JOINING DATE: 15 OCTOBER 2026",
        "ANNUAL SALARY: USD 120000",
    ])

    res = client.post(
        "/api/mode/offline",
        files={"file": ("employment_contract.png", buf, "image/png")},
        data={"doc_type": "auto"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("supported") is True
    assert data["doc_type"] == "unknown"
    assert data["document_type"] == "Unknown Document"
    assert data["ocr_completed"] is True
    assert "EMPLOYMENT" in data["extracted_text"]
    assert "id" in data
    assert "Offline OCR completed successfully" in data["message"]


@pytest.mark.asyncio
async def test_ai_analyze_endpoint_success(client, monkeypatch):
    """Test AI Mode analyze endpoint with mock AI response."""
    mock_ai_analysis = {
        "document_type": "Employment Contract",
        "confidence": "high",
        "summary": "This document appears to be an employment contract because it contains employer/employee information, joining terms, salary information and employment conditions.",
        "reasoning": [
            "Contains employer and employee information",
            "Contains joining terms and position",
            "Contains compensation and salary information",
        ],
    }

    with patch("ai_service.analyze_document", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_ai_analysis

        buf = _create_test_image([
            "ACME CORP - EMPLOYMENT AGREEMENT",
            "EMPLOYEE NAME: JANE DOE",
            "JOINING DATE: 15 OCTOBER 2026",
            "ANNUAL COMPENSATION: $120,000",
            "TERMS AND CONDITIONS OF EMPLOYMENT",
        ])

        res = client.post(
            "/api/mode/ai/analyze",
            files={"file": ("Employment_Contract.png", buf, "image/png")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["document_type"] == "Employment Contract"
        assert data["confidence"] == "high"
        assert "employment contract" in data["summary"].lower()
        assert len(data["reasoning"]) >= 2
        assert "document_id" in data
        assert data["filename"] == "Employment_Contract.png"


@pytest.mark.asyncio
async def test_ai_chat_endpoint_answers_with_document_context(client):
    """Test AI Mode chat endpoint grounded in document context."""
    # First persist a mock document in document store
    doc_record = document_store.save_document(
        file_bytes=b"dummy content",
        filename="Employment_Contract.pdf",
        result_data={
            "doc_type": "ai_analyzed",
            "document_type": "Employment Contract",
            "extracted_text": (
                "ACME CORPORATION EMPLOYMENT AGREEMENT\n"
                "Employee Name: Alex Johnson\n"
                "Designation: Lead Architect\n"
                "Joining Date: 15 October 2026\n"
                "Annual Base Salary: USD 150,000\n"
                "Employer: ACME Global Technologies Inc.\n"
                "Notice Period: 60 Days\n"
                "Agreement Expiry Date: None (Permanent Position)"
            ),
        },
    )
    doc_id = doc_record["id"]

    with patch("ai_service.chat_with_document", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "The joining date mentioned in the document is 15 October 2026."

        res = client.post(
            "/api/mode/ai/chat",
            json={
                "document_id": doc_id,
                "message": "What is the joining date?",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "15 October 2026" in data["response"]

        mock_chat.assert_called_once()
        kwargs = mock_chat.call_args.kwargs
        assert "Alex Johnson" in kwargs.get("document_text", "")
        assert "What is the joining date?" in kwargs.get("message", "")


@pytest.mark.asyncio
async def test_ai_chat_document_context_isolation(client):
    """
    Test context isolation:
    Ensure Document A and Document B maintain strictly separate contexts.
    """
    doc_a = document_store.save_document(
        file_bytes=b"doc a",
        filename="Contract_A.pdf",
        result_data={
            "doc_type": "ai_analyzed",
            "document_type": "Contract A",
            "extracted_text": "Company Alpha agreed to pay 50,000 USD to Contractor Alice.",
        },
    )
    doc_b = document_store.save_document(
        file_bytes=b"doc b",
        filename="Contract_B.pdf",
        result_data={
            "doc_type": "ai_analyzed",
            "document_type": "Contract B",
            "extracted_text": "Company Beta agreed to pay 90,000 EUR to Contractor Bob.",
        },
    )

    with patch("ai_service.chat_with_document", new_callable=AsyncMock) as mock_chat:
        mock_chat.side_effect = lambda document_text, filename, message, history=None: f"Answer from {filename}: {document_text}"

        res_a = client.post(
            "/api/mode/ai/chat",
            json={"document_id": doc_a["id"], "message": "Who is the contractor?"},
        )
        assert res_a.status_code == 200
        assert "Alice" in res_a.json()["response"]
        assert "Bob" not in res_a.json()["response"]

        res_b = client.post(
            "/api/mode/ai/chat",
            json={"document_id": doc_b["id"], "message": "Who is the contractor?"},
        )
        assert res_b.status_code == 200
        assert "Bob" in res_b.json()["response"]
        assert "Alice" not in res_b.json()["response"]


def test_ai_chat_invalid_document_id_returns_404(client):
    """Test non-existent document_id in chat returns 404."""
    res = client.post(
        "/api/mode/ai/chat",
        json={"document_id": "non-existent-uuid-12345", "message": "Hello"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ai_mode_pan_card_classification_and_chat_grounding():
    """
    Test real PAN card text:
    - Must classify as 'PAN Card' (NOT 'Incometaxdepartment')
    - Confidence must be 'high'
    - Asking 'What is the employee name?' MUST return 'I could not find an employee name in this document.'
    - Asking 'What is the PAN number?' returns 'IVQPP1031M'
    - Must never return '***/Name'
    """
    pan_text = (
        "INCOMETAXDEPARTMENT\n"
        "GOVT.OFINDIA\n"
        "Permanent Account Number Card\n"
        "IVQPP1031M\n"
        "नाम/Name\n"
        "VIGHNESHSANDIPPOTE\n"
        "Father'sName\n"
        "POTESANDIP\n"
        "Date of Birth\n"
        "22/06/2007"
    )

    analysis = await ai_service.analyze_document(pan_text, filename="WhatsApp Image 2026-09-10 at 16.53.24.jpeg")
    assert analysis["document_type"] == "PAN Card"
    assert analysis["confidence"] == "high"
    assert "Incometaxdepartment" not in analysis["document_type"]
    assert "Permanent Account Number" in analysis["summary"] or "PAN" in analysis["summary"]
    assert len(analysis["evidence"]) >= 2

    # Chat Grounding Tests:
    # 1. Employee name MUST NOT hallucinate
    reply_emp = await ai_service.chat_with_document(
        pan_text,
        filename="WhatsApp Image 2026-09-10 at 16.53.24.jpeg",
        message="What is the employee name?",
    )
    assert "could not find an employee name" in reply_emp.lower()
    assert "***/Name" not in reply_emp
    assert "*/Name" not in reply_emp

    # 2. Joining date MUST NOT hallucinate
    reply_join = await ai_service.chat_with_document(
        pan_text,
        filename="WhatsApp Image 2026-09-10 at 16.53.24.jpeg",
        message="What is the joining date?",
    )
    assert "could not find a joining date" in reply_join.lower()

    # 3. Salary MUST NOT hallucinate
    reply_sal = await ai_service.chat_with_document(
        pan_text,
        filename="WhatsApp Image 2026-09-10 at 16.53.24.jpeg",
        message="What is the salary?",
    )
    assert "could not find salary information" in reply_sal.lower()

    # 4. PAN Number should be accurately answered
    reply_pan = await ai_service.chat_with_document(
        pan_text,
        filename="WhatsApp Image 2026-09-10 at 16.53.24.jpeg",
        message="What is the PAN number?",
    )
    assert "IVQPP1031M" in reply_pan

    # 5. Cardholder name query
    reply_name = await ai_service.chat_with_document(
        pan_text,
        filename="WhatsApp Image 2026-09-10 at 16.53.24.jpeg",
        message="What is the name of the individual?",
    )
    assert "VIGHNESHSANDIPPOTE" in reply_name
    assert "***/Name" not in reply_name


@pytest.mark.asyncio
async def test_ai_mode_document_classifications():
    """Verify Aadhaar, Income Tax Notice, Bank Statement, Contract, and Unknown."""
    # Aadhaar Card
    aadhaar_text = "UNIQUE IDENTIFICATION AUTHORITY OF INDIA\nGOVERNMENT OF INDIA\nName: Rahul Sharma\nDOB: 01/01/1990\nMale\n1234 5678 9012"
    res_aadhaar = await ai_service.analyze_document(aadhaar_text)
    assert res_aadhaar["document_type"] == "Aadhaar Card"
    assert res_aadhaar["confidence"] == "high"

    # Income Tax Notice (not a PAN card)
    it_notice_text = (
        "INCOME TAX DEPARTMENT\n"
        "GOVERNMENT OF INDIA\n"
        "Notice under section 143(2) of the Income-tax Act, 1961\n"
        "Assessment Year: 2026-27\n"
        "DIN: ITBA/AST/S/143(2)/2026-27/1054238910(1)\n"
        "To: ABC Enterprises Ltd"
    )
    res_notice = await ai_service.analyze_document(it_notice_text)
    assert res_notice["document_type"] == "Income Tax Notice"
    assert res_notice["confidence"] == "high"

    # Bank Statement
    bank_text = (
        "STATE BANK OF INDIA\n"
        "Statement of Account for Period 01/08/2026 to 31/08/2026\n"
        "Account Number: 123456789012\n"
        "IFSC: SBIN0001234\n"
        "Opening Balance: 45,000.00\n"
        "Closing Balance: 52,000.00"
    )
    res_bank = await ai_service.analyze_document(bank_text)
    assert res_bank["document_type"] == "Bank Statement"
    assert res_bank["confidence"] == "high"

    # Employment Contract
    contract_text = (
        "ACME CORP - EMPLOYMENT AGREEMENT\n"
        "Between Acme Corp and John Doe\n"
        "Position: Lead Architect\n"
        "Joining Date: 15 October 2026\n"
        "Salary: $150,000 per annum"
    )
    res_contract = await ai_service.analyze_document(contract_text)
    assert res_contract["document_type"] == "Employment Contract"
    assert res_contract["confidence"] == "high"

    # Unknown Document
    unknown_text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer nec odio. Praesent libero."
    res_unknown = await ai_service.analyze_document(unknown_text)
    assert res_unknown["document_type"] == "Unknown Document"
    assert res_unknown["confidence"] == "low"

    # OCR failure / low text
    res_low = await ai_service.analyze_document("Abc")
    assert res_low["document_type"] == "Unknown Document"
    assert res_low["confidence"] == "low"
    assert "upload a clearer image" in res_low["summary"].lower()


@pytest.mark.asyncio
async def test_ai_mode_bank_statement_chat_grounding():
    """Verify bank statement field intents, formatting, and follow-up handling."""
    bank_text = (
        "Account Statement Report\n"
        "Statement of Axis Bank Account No : 925020052380170 for the period ( From : 30/07/2025 To : 30/07/2026 )\n"
        "Customer No : 978738241     IFSC Code : UTIB0001435\n"
        "Branch Name(SOL) : AJMERA COMPLEX,PIMPRI,PUNE\n"
        "Account Holder Name: SNEHA\n"
        "Opening Balance: INR 0.00\n"
        "1 21/11/2025 5,00,000.00 CR 5,00,000.00 AJMERA COMPLEX,PIMPRI,PUNE\n"
    )
    stored_analysis = {
        "document_type": "Bank Statement",
        "extracted_fields": {
            "bank_name": "Axis Bank",
            "account_holder": "SNEHA",
            "account_number": "XXXXXXXXXXX0170",
            "customer_number": "978738241",
            "ifsc": "UTIB0001435",
            "branch": "AJMERA COMPLEX,PIMPRI,PUNE",
            "statement_period": {"from_date": "30/07/2025", "to_date": "30/07/2026"},
            "transactions": [
                {"date": "21/11/2025", "amount": "500000.00", "type": "CR", "balance": "500000.00"}
            ]
        }
    }

    # 1. Bank name
    r_bank = await ai_service.chat_with_document(bank_text, "statement.pdf", "What is the bank name?", stored_analysis=stored_analysis)
    assert "Axis Bank" in r_bank

    # 2. Account number
    r_acc = await ai_service.chat_with_document(bank_text, "statement.pdf", "What is the account number?", stored_analysis=stored_analysis)
    assert "0170" in r_acc

    # 3. Account holder
    r_holder = await ai_service.chat_with_document(bank_text, "statement.pdf", "What is the account holder?", stored_analysis=stored_analysis)
    assert "SNEHA" in r_holder
    assert "individual's name" not in r_holder

    # 4. Statement period (NEVER raw dict)
    r_period = await ai_service.chat_with_document(bank_text, "statement.pdf", "What is the statement period?", stored_analysis=stored_analysis)
    assert "{'from_date'" not in r_period
    assert "30 July 2025" in r_period and "30 July 2026" in r_period

    # 5. Customer Number
    r_cust = await ai_service.chat_with_document(bank_text, "statement.pdf", "What is the Customer No?", stored_analysis=stored_analysis)
    assert "978738241" in r_cust

    # 6. Follow-up Why?
    history = [
        {"role": "user", "content": "What is the Customer No?"},
        {"role": "assistant", "content": r_cust}
    ]
    r_why = await ai_service.chat_with_document(bank_text, "statement.pdf", "Why?", history=history, stored_analysis=stored_analysis)
    assert "customer number" in r_why.lower()
    assert "employee" not in r_why.lower()

    # 7. Branch
    r_branch = await ai_service.chat_with_document(bank_text, "statement.pdf", "What is the branch?", stored_analysis=stored_analysis)
    assert "AJMERA COMPLEX" in r_branch

    # 8. IFSC
    r_ifsc = await ai_service.chat_with_document(bank_text, "statement.pdf", "What is the IFSC Code?", stored_analysis=stored_analysis)
    assert "UTIB0001435" in r_ifsc
    assert "State Bank of India" not in r_ifsc

    # 9. Total transactions
    r_txns = await ai_service.chat_with_document(bank_text, "statement.pdf", "What is the total transactions amount?", stored_analysis=stored_analysis)
    assert "₹" in r_txns and "Credits" in r_txns


def test_active_document_session_and_cross_document_isolation(client):
    """
    Tasks 1, 2, 3, 4, 5, 6:
    - Verifies single active document per session.
    - Verifies cross-document isolation (PAN number does not leak to Bank Statement).
    - Verifies direct field-aware lookup.
    - Verifies follow-up 'Why?' references Customer Number without mentioning employee name.
    """
    # 1. Upload Document A (PAN Card)
    pan_doc = document_store.save_document(
        file_bytes=b"%PDF-1.4 PAN Mock",
        filename="Sneha_PAN.pdf",
        result_data={
            "doc_type": "pan",
            "document_type": "PAN Card",
            "extracted_text": "INCOME TAX DEPARTMENT GOVT OF INDIA Permanent Account Number ABCDE1234F Name SNEHA GUPTA DOB 15/08/1992",
            "extracted_fields": {
                "pan_number": "ABCDE1234F",
                "name": "SNEHA GUPTA",
                "date_of_birth": "15/08/1992",
            },
        },
    )
    pan_id = pan_doc["id"]
    assert document_store.get_active_document_id() == pan_id

    # Query active document for PAN
    res_pan = client.post(
        "/api/mode/ai/chat",
        json={"document_id": pan_id, "message": "What is the PAN number?"},
    )
    assert res_pan.status_code == 200
    assert "ABCDE1234F" in res_pan.json()["response"]

    # Query active document for GSTIN (does not exist on PAN)
    res_gst_on_pan = client.post(
        "/api/mode/ai/chat",
        json={"document_id": pan_id, "message": "What is the GSTIN?"},
    )
    assert res_gst_on_pan.status_code == 200
    assert "could not find a gstin" in res_gst_on_pan.json()["response"].lower()

    # 2. Upload Document B (Bank Statement)
    bs_doc = document_store.save_document(
        file_bytes=b"%PDF-1.4 Bank Mock",
        filename="Axis_Statement.pdf",
        result_data={
            "doc_type": "bank_statement",
            "document_type": "Bank Statement",
            "extracted_text": "AXIS BANK LIMITED Account Statement Account Holder: SNEHA GUPTA Account Number: 918010023456789 IFSC Code: UTIB0001435 Branch: PIMPRI PUNE",
            "extracted_fields": {
                "bank_name": "Axis Bank",
                "account_holder": "SNEHA GUPTA",
                "account_number": "XXXXXXXXXXX6789",
                "ifsc": "UTIB0001435",
                "branch": "PIMPRI PUNE",
            },
        },
    )
    bs_id = bs_doc["id"]
    # Session now points to Bank Statement
    assert document_store.get_active_document_id() == bs_id

    # 3. Cross-Document Leakage Check:
    # Asking for PAN number on Bank Statement MUST NOT leak the PAN from Document A!
    res_pan_on_bs = client.post(
        "/api/mode/ai/chat",
        json={"document_id": bs_id, "message": "What is the PAN number?"},
    )
    assert res_pan_on_bs.status_code == 200
    pan_reply = res_pan_on_bs.json()["response"]
    assert "ABCDE1234F" not in pan_reply
    assert "could not find a pan number" in pan_reply.lower()

    # 4. Field-Aware Lookup: Account Holder
    res_holder = client.post(
        "/api/mode/ai/chat",
        json={"document_id": bs_id, "message": "What is the account holder?"},
    )
    assert res_holder.status_code == 200
    assert "SNEHA GUPTA" in res_holder.json()["response"]

    # 5. Field-Aware Lookup: Missing Customer Number
    res_cust = client.post(
        "/api/mode/ai/chat",
        json={"document_id": bs_id, "message": "Customer No?"},
    )
    assert res_cust.status_code == 200
    cust_reply = res_cust.json()["response"]
    assert "could not find a customer number" in cust_reply.lower()

    # 6. Follow-up: Why?
    history = [
        {"role": "user", "content": "Customer No?"},
        {"role": "assistant", "content": cust_reply},
    ]
    res_why = client.post(
        "/api/mode/ai/chat",
        json={"document_id": bs_id, "message": "Why?", "history": history},
    )
    assert res_why.status_code == 200
    why_reply = res_why.json()["response"]
    assert "customer number" in why_reply.lower()
    assert "employee" not in why_reply.lower()
    assert "searched the extracted fields" in why_reply.lower()

    # 7. Active session endpoint
    active_res = client.get("/api/mode/ai/active")
    assert active_res.status_code == 200
    assert active_res.json()["active"] is True
    assert active_res.json()["document_id"] == bs_id

    # 8. Clear active session endpoint
    clear_res = client.post("/api/mode/ai/active/clear")
    assert clear_res.status_code == 200
    assert clear_res.json()["success"] is True
    assert document_store.get_active_document_id() is None

    # Clean up
    document_store.delete_document(pan_id)
    document_store.delete_document(bs_id)


def test_exact_acceptance_criteria_flow(client):
    """
    Test exact flow from acceptance criteria:
    1. PAN: What is the PAN number? -> Correct PAN
    2. PAN: What is the GSTIN? -> Not found
    3. Bank Statement: What is the account holder? -> Correct holder
    4. Bank Statement: Why? -> References previous question
    5. GST: What is the GSTIN? -> Correct GSTIN
    6. Upload PAN after GST: What is the GSTIN? -> Not found
    """
    # Step 1: PAN Card
    pan_doc = document_store.save_document(
        file_bytes=b"%PDF-1.4 PAN1",
        filename="PAN_Vighnesh.pdf",
        result_data={
            "doc_type": "pan",
            "document_type": "PAN Card",
            "extracted_text": "INCOME TAX DEPARTMENT GOVT OF INDIA ABCDE1234F VIGHNESH POTE",
            "extracted_fields": {
                "pan_number": "ABCDE1234F",
                "name": "VIGHNESH POTE",
            },
        },
    )
    pan_id = pan_doc["id"]
    assert document_store.get_active_document_id() == pan_id

    # 1. What is the PAN number?
    r1 = client.post("/api/mode/ai/chat", json={"message": "What is the PAN number?"})
    assert r1.status_code == 200
    assert "ABCDE1234F" in r1.json()["response"]

    # 2. What is the GSTIN? (On PAN)
    r2 = client.post("/api/mode/ai/chat", json={"message": "What is the GSTIN?"})
    assert r2.status_code == 200
    assert "could not find a gstin in this document" in r2.json()["response"].lower()

    # Step 2: Bank Statement
    bs_doc = document_store.save_document(
        file_bytes=b"%PDF-1.4 BS",
        filename="Sneha_Bank.pdf",
        result_data={
            "doc_type": "bank_statement",
            "document_type": "Bank Statement",
            "extracted_text": "AXIS BANK LIMITED Account Holder: SNEHA GUPTA Statement Period: 01/04/2025 to 31/03/2026",
            "extracted_fields": {
                "bank_name": "Axis Bank",
                "account_holder": "SNEHA GUPTA",
            },
        },
    )
    bs_id = bs_doc["id"]
    assert document_store.get_active_document_id() == bs_id

    # 3. What is the account holder?
    r3 = client.post("/api/mode/ai/chat", json={"message": "What is the account holder?"})
    assert r3.status_code == 200
    assert "SNEHA GUPTA" in r3.json()["response"]

    # Ask for missing Customer Number then Why?
    r_cust = client.post("/api/mode/ai/chat", json={"message": "Customer Number?"})
    assert r_cust.status_code == 200
    assert "could not find a customer number" in r_cust.json()["response"].lower()

    # 4. Why?
    r4 = client.post(
        "/api/mode/ai/chat",
        json={
            "message": "Why?",
            "history": [
                {"role": "user", "content": "Customer Number?"},
                {"role": "assistant", "content": r_cust.json()["response"]},
            ],
        },
    )
    assert r4.status_code == 200
    assert "customer number" in r4.json()["response"].lower()
    assert "searched the extracted fields, ocr text, and visible document content" in r4.json()["response"].lower()
    assert "employee" not in r4.json()["response"].lower()

    # Step 3: GST Certificate
    gst_doc = document_store.save_document(
        file_bytes=b"%PDF-1.4 GST",
        filename="Acme_GST.pdf",
        result_data={
            "doc_type": "gst_certificate",
            "document_type": "GST Registration Certificate",
            "extracted_text": "FORM GST REG-06 27AABCT3518Q1ZS ACME ENTERPRISES",
            "extracted_fields": {
                "gstin": "27AABCT3518Q1ZS",
                "legal_name": "ACME ENTERPRISES",
            },
        },
    )
    gst_id = gst_doc["id"]
    assert document_store.get_active_document_id() == gst_id

    # 5. What is the GSTIN?
    r5 = client.post("/api/mode/ai/chat", json={"message": "What is the GSTIN?"})
    assert r5.status_code == 200
    assert "27AABCT3518Q1ZS" in r5.json()["response"]

    # Step 4: Upload PAN after GST
    pan2_doc = document_store.save_document(
        file_bytes=b"%PDF-1.4 PAN2",
        filename="PAN_Priya.pdf",
        result_data={
            "doc_type": "pan",
            "document_type": "PAN Card",
            "extracted_text": "INCOME TAX DEPARTMENT GOVT OF INDIA XYZAB9876C PRIYA SHARMA",
            "extracted_fields": {
                "pan_number": "XYZAB9876C",
                "name": "PRIYA SHARMA",
            },
        },
    )
    pan2_id = pan2_doc["id"]
    assert document_store.get_active_document_id() == pan2_id

    # 6. What is the GSTIN? (Must be NOT found, no leakage from previous GST document)
    r6 = client.post("/api/mode/ai/chat", json={"message": "What is the GSTIN?"})
    assert r6.status_code == 200
    assert "27AABCT3518Q1ZS" not in r6.json()["response"]
    assert "could not find a gstin in this document" in r6.json()["response"].lower()

    # Cleanup
    for did in [pan_id, bs_id, gst_id, pan2_id]:
        document_store.delete_document(did)


# ==============================================================================
# Field Registry & Accuracy Unit Tests
# ==============================================================================

def test_field_registry_intent_detection():
    """Task 1 & Task 2: Test intent detection for field variations."""
    import field_registry

    # Customer number variations
    for q in ["What is the Customer No?", "Customer Number", "cif number", "cust id", "What is the CIF?"]:
        fdef = field_registry.detect_field_intent(q, doc_type="Bank Statement")
        assert fdef is not None, f"Failed on query: {q}"
        assert fdef.canonical_key == "customer_number"

    # IFSC variations
    for q in ["IFSC Code", "what is the ifsc", "rtgs/neft", "IFS code"]:
        fdef = field_registry.detect_field_intent(q, doc_type="Bank Statement")
        assert fdef is not None, f"Failed on query: {q}"
        assert fdef.canonical_key == "ifsc"

    # Statement period variations
    for q in ["What is the statement period?", "statement duration", "period of the statement"]:
        fdef = field_registry.detect_field_intent(q, doc_type="Bank Statement")
        assert fdef is not None, f"Failed on query: {q}"
        assert fdef.canonical_key == "statement_period"

    # PAN variations
    for q in ["What is the PAN number?", "PAN", "pan no"]:
        fdef = field_registry.detect_field_intent(q, doc_type="PAN Card")
        assert fdef is not None, f"Failed on query: {q}"
        assert fdef.canonical_key == "pan_number"

    # GSTIN variations
    for q in ["What is the GSTIN?", "GST number", "gstin"]:
        fdef = field_registry.detect_field_intent(q, doc_type="GST Registration Certificate")
        assert fdef is not None, f"Failed on query: {q}"
        assert fdef.canonical_key == "gstin"


def test_field_registry_formatting():
    """Task 4: Test human-friendly date and statement period formatting."""
    import field_registry

    # Dates
    assert field_registry.format_date_human("22/06/2007") == "22 June 2007"
    assert field_registry.format_date_human("01-04-2025") == "01 April 2025"
    assert field_registry.format_date_human("2026-12-31") == "31 December 2026"

    # Statement periods
    raw_dict = {"from_date": "30/07/2025", "to_date": "30/07/2026"}
    assert field_registry.format_statement_period_human(raw_dict) == "30 July 2025 – 30 July 2026"

    stringified_dict = "{'from_date': '30/07/2025', 'to_date': '30/07/2026'}"
    assert field_registry.format_statement_period_human(stringified_dict) == "30 July 2025 – 30 July 2026"

    text_range = "From : 01/01/2024 To : 31/12/2024"
    assert field_registry.format_statement_period_human(text_range) == "01 January 2024 – 31 December 2024"


def test_field_registry_anti_substitution():
    """Task 10: Anti-substitution guards."""
    import field_registry

    ifsc_def = field_registry.FIELD_REGISTRY["ifsc"]
    cust_def = field_registry.FIELD_REGISTRY["customer_number"]
    pan_def = field_registry.FIELD_REGISTRY["pan_number"]

    # IFSC must not be bank name
    val, source = field_registry.lookup_field_value(
        ifsc_def,
        extracted_fields={"ifsc": "STATE BANK OF INDIA"},
        ocr_text="STATE BANK OF INDIA",
    )
    assert source == "prohibited"
    assert val is None

    # Customer Number must not be Account Number
    val, source = field_registry.lookup_field_value(
        cust_def,
        extracted_fields={"customer_number": "1234567890", "account_number": "1234567890"},
        ocr_text="A/C: 1234567890",
    )
    assert source == "prohibited"
    assert val is None

    # PAN must not be GSTIN (15 chars)
    val, source = field_registry.lookup_field_value(
        pan_def,
        extracted_fields={"pan_number": "27AABCT3518Q1ZS"},
        ocr_text="GSTIN: 27AABCT3518Q1ZS",
    )
    assert source == "prohibited"
    assert val is None


@pytest.mark.asyncio
async def test_pan_and_gst_absent_field_lookups():
    """Task 6 & Task 7: Asking for GSTIN on PAN or absent fields returns explicit not found."""
    pan_analysis = {
        "document_type": "PAN Card",
        "confidence": "high",
        "summary": "Permanent Account Number card for Priya Sharma.",
        "evidence": ["INCOME TAX DEPARTMENT", "ABCDE1234F"],
        "extracted_fields": {
            "pan_number": "ABCDE1234F",
            "name": "PRIYA SHARMA",
            "date_of_birth": "22/06/2007",
        },
    }
    pan_text = "INCOME TAX DEPARTMENT GOVT OF INDIA ABCDE1234F PRIYA SHARMA 22/06/2007"

    # 1. PAN Number
    r_pan = await ai_service.chat_with_document(pan_text, "pan.jpg", "What is the PAN number?", stored_analysis=pan_analysis)
    assert "ABCDE1234F" in r_pan

    # 2. DOB formatted
    r_dob = await ai_service.chat_with_document(pan_text, "pan.jpg", "What is the date of birth?", stored_analysis=pan_analysis)
    assert "22 June 2007" in r_dob

    # 3. GSTIN on PAN must be not found
    r_gst = await ai_service.chat_with_document(pan_text, "pan.jpg", "What is the GSTIN?", stored_analysis=pan_analysis)
    assert "could not find a gstin in this document" in r_gst.lower()

    # 4. Follow-up Why?
    history = [
        {"role": "user", "content": "What is the GSTIN?"},
        {"role": "assistant", "content": r_gst}
    ]
    r_why = await ai_service.chat_with_document(pan_text, "pan.jpg", "Why?", history=history, stored_analysis=pan_analysis)
    assert "gstin" in r_why.lower()
    assert "could not find" in r_why.lower()


@pytest.mark.asyncio
async def test_unknown_document_no_hallucinations():
    """Task 8: Unknown document never fabricates structured fields."""
    unknown_analysis = {
        "document_type": "Unknown Document",
        "confidence": "low",
        "summary": "Unrecognized miscellaneous document.",
        "evidence": [],
        "extracted_fields": {},
    }
    unknown_text = "Sample random text without any structured financial or identity credentials."

    r_pan = await ai_service.chat_with_document(unknown_text, "doc.pdf", "What is the PAN number?", stored_analysis=unknown_analysis)
    assert "could not find a pan number" in r_pan.lower()

    r_ifsc = await ai_service.chat_with_document(unknown_text, "doc.pdf", "What is the IFSC Code?", stored_analysis=unknown_analysis)
    assert "could not find an ifsc code" in r_ifsc.lower()





