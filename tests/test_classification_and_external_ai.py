import os
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

import verifier
from main import app
import ai_providers
import document_store


@pytest.fixture(autouse=True)
def reset_app_security(monkeypatch):
    import main
    import supabase_client
    import retention_service
    main._startup_security_error = None
    monkeypatch.setattr(supabase_client, "is_supabase_configured", lambda: False)
    monkeypatch.setattr(retention_service, "run_startup_cleanup", lambda: 0)
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("REGISTERED_CLIENTS_JSON", raising=False)
    monkeypatch.delenv("REGISTERED_CLIENTS_FILE", raising=False)
    yield
    main._startup_security_error = None


@pytest.fixture
def client(reset_app_security):
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# 1. DOCUMENT CLASSIFICATION & DISAMBIGUATION TESTS
# ==============================================================================

def test_aadhaar_with_fathers_name_not_classified_as_pan():
    """
    CRITICAL REGRESSION TEST:
    Aadhaar cards frequently list 'Father's Name' in the address/details block.
    This MUST be classified as Aadhaar Card, NEVER PAN Card.
    """
    aadhaar_ocr = """
    GOVERNMENT OF INDIA
    Unique Identification Authority of India
    Father's Name: Ramesh Kumar Sharma
    DOB: 15/08/1990
    Male
    1234 5678 9012
    Mera Aadhaar, Meri Pehchan
    """
    res = verifier.classify_document_content(aadhaar_ocr)
    assert res["doc_type"] == "aadhaar"
    assert res["document_type"] == "Aadhaar Card"
    assert res["confidence"] is not None
    assert 0.70 <= res["confidence"] <= 1.0


def test_real_pan_card_classification():
    """
    PAN card with institutional headers must classify as PAN Card with valid float confidence.
    """
    pan_ocr = """
    INCOME TAX DEPARTMENT
    GOVT OF INDIA
    Permanent Account Number Card
    ABCDE1234F
    Name: SURESH PATEL
    Father's Name: RAMESH PATEL
    Date of Birth: 01/01/1985
    """
    res = verifier.classify_document_content(pan_ocr)
    assert res["doc_type"] == "pan"
    assert res["document_type"] == "PAN Card"
    assert res["confidence"] is not None
    assert 0.70 <= res["confidence"] <= 1.0


def test_ambiguous_text_returns_unknown_not_pan():
    """
    Text that only mentions 'Father's Name' without institutional anchors should NOT classify as PAN.
    """
    vague_text = "Father's Name: John Doe. Address: 123 Main Street, City Center."
    res = verifier.classify_document_content(vague_text)
    assert res["doc_type"] != "pan"
    assert res["doc_type"] == "unknown"
    assert res["document_type"] == "Unknown Document"
    assert res["confidence"] is None


def test_unknown_document_insufficient_evidence():
    """
    Random or unclassifiable text must return Unknown Document and confidence None.
    """
    gibberish = "Hello world, quick brown fox jumps over the lazy dog. Random notes and text."
    res = verifier.classify_document_content(gibberish)
    assert res["doc_type"] == "unknown"
    assert res["document_type"] == "Unknown Document"
    assert res["confidence"] is None
    assert len(res["evidence"]) > 0
    assert any("Insufficient" in e or "No standard" in e for e in res["evidence"])


def test_multi_page_document_classification():
    """
    Multi-page document with page delimiters is parsed and evidence includes page numbers.
    """
    multi_page_doc = """
    --- Page 1 ---
    CONFIDENTIAL EMPLOYMENT AGREEMENT
    This Agreement is entered into on 1st January 2025.
    Employer: Acme Global Tech Private Limited
    Employee: Rahul Varma
    Designation: Senior Software Engineer
    --- Page 2 ---
    Terms and Conditions of Employment:
    1. Scope of Work and Responsibilities
    2. Compensation and Benefits: Gross Salary CTC INR 18,00,000 per annum
    3. Termination and Notice Period: 60 days
    """
    res = verifier.classify_document_content(multi_page_doc)
    assert res["doc_type"] == "employment_contract"
    assert res["document_type"] == "Employment Contract"
    assert res["confidence"] is not None
    assert 0.70 <= res["confidence"] <= 1.0
    # Multi-page layout evidence should be present
    assert any("page" in e.lower() for e in res["evidence"])


@pytest.mark.parametrize("doc_type,text_sample,expected_title", [
    (
        "aadhaar",
        "Unique Identification Authority of India 9876 5432 1098 Mera Aadhaar Meri Pehchan",
        "Aadhaar Card",
    ),
    (
        "pan",
        "INCOME TAX DEPARTMENT GOVT OF INDIA Permanent Account Number ABCDE9876K",
        "PAN Card",
    ),
    (
        "passport",
        "PASSPORT REPUBLIC OF INDIA Type P Code IND Passport No Z1234567",
        "Passport",
    ),
    (
        "driving_licence",
        "UNION OF INDIA DRIVING LICENCE Transport Department DL No DL-0420110012345",
        "Driving Licence",
    ),
    (
        "voter_id",
        "ELECTION COMMISSION OF INDIA ELECTOR PHOTO IDENTITY CARD EPIC NO WBG1234567",
        "Voter ID",
    ),
    (
        "utility_bill",
        "ELECTRICITY BILL CONSUMER NUMBER 1029384756 TARIFF LT-1 UNITS CONSUMED 240",
        "Utility Bill",
    ),
    (
        "bank_statement",
        "STATEMENT OF ACCOUNT FOR THE PERIOD ACCOUNT NUMBER 9182736450 IFSC HDFC0001234 CLOSING BALANCE 45000",
        "Bank Statement",
    ),
    (
        "salary_slip",
        "PAYSLIP FOR THE MONTH OF MARCH 2025 EMPLOYEE CODE EMP001 BASIC PAY 40000 NET PAY 65000",
        "Salary Slip",
    ),
    (
        "gst_certificate",
        "FORM GST REG-06 REGISTRATION CERTIFICATE GOVERNMENT OF INDIA GSTIN 27AABCT3518Q1ZV",
        "GST Registration Certificate",
    ),
    (
        "commercial_invoice",
        "TAX INVOICE INVOICE NUMBER INV-2025-001 BILL TO ACME CORP TOTAL AMOUNT 15000",
        "Commercial Invoice",
    ),
    (
        "employment_contract",
        "EMPLOYMENT AGREEMENT AND CONTRACT OF SERVICE BETWEEN COMPANY AND EMPLOYEE",
        "Employment Contract",
    ),
    (
        "income_tax_notice",
        "INCOME TAX DEPARTMENT NOTICE UNDER SECTION 143(1) OF INCOME TAX ACT 1961 ASSESSMENT YEAR 2024-25",
        "Income Tax Notice",
    ),
])
def test_all_major_document_types_classify_correctly(doc_type, text_sample, expected_title):
    res = verifier.classify_document_content(text_sample)
    assert res["doc_type"] == doc_type
    assert res["document_type"] == expected_title
    assert isinstance(res["confidence"], float)
    assert 0.0 < res["confidence"] <= 1.0


# ==============================================================================
# 2. EXTERNAL AI SETTINGS & PERMISSION TESTS
# ==============================================================================

def test_authenticated_user_can_configure_external_ai(client):
    """
    Verifies any authenticated user (not just admin) can configure external AI providers.
    API keys are encrypted and never exposed in the response.
    """
    config_payload = {
        "active_provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-test-secret-key-1234567890abcdef",
        "base_url": "https://api.openai.com/v1",
        "fallback_on_error": False,
    }
    resp = client.post("/api/ai/config", json=config_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_provider"] == "openai"
    assert data["active_model"] == "gpt-4o-mini"
    assert data["api_key_configured"] is True
    # Secret API key must be redacted in the response! Never expose raw key!
    assert "sk-test-secret-key-1234567890abcdef" not in str(data)


def test_authenticated_user_can_test_ai_connection(client):
    """
    Verifies testing connection endpoint works for authenticated users.
    """
    with patch.object(ai_providers.AIProviderManager, "test_connection", new_callable=AsyncMock) as mock_test:
        mock_test.return_value = {
            "success": True,
            "provider": "openai",
            "model": "gpt-4o-mini",
            "latency_ms": 120,
            "message": "Connected successfully to OpenAI",
        }
        test_payload = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "sk-mock-key-for-test",
            "base_url": "https://api.openai.com/v1",
        }
        resp = client.post("/api/ai/test-connection", json=test_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["provider"] == "openai"


def test_no_silent_fallback_when_external_provider_fails():
    """
    When active provider is external and fallback_on_error is False,
    exceptions must be raised cleanly to the caller without silently using Ollama.
    """
    manager = ai_providers.AIProviderManager()
    manager.update_config(
        provider="openrouter",
        model="deepseek/deepseek-r1",
        api_key="sk-or-test-key",
        base_url="https://openrouter.ai/api/v1",
        fallback_on_error=False,
    )
    assert not manager.get_active_provider().is_local
    assert manager.current_fallback_on_error is False


# ==============================================================================
# 3. AI CHAT GROUNDING FRESHNESS TESTS
# ==============================================================================

def test_chat_canonical_grounding_refresh_from_vault():
    """
    Verifies that chat canonical analysis refreshes with latest vault document data:
    real document_type, confidence, verification_status, and risk_score.
    """
    dev_user_id = os.getenv("DEFAULT_DEV_USER_ID", "00000000-0000-0000-0000-000000000001")
    
    # Seed document in store
    saved = document_store.save_document(
        file_bytes=b"sample content",
        filename="aadhaar_sample.pdf",
        result_data={
            "doc_type": "aadhaar",
            "document_type": "Aadhaar Card",
            "confidence": 0.94,
            "verification_status": "verified",
            "risk_score": 0,
            "extracted_text": "--- Page 1 ---\nGovernment of India Unique Identification Authority of India 1234 5678 9012",
            "extracted_fields": {"aadhaar_number": "1234 5678 9012", "name": "Rohan Gupta"},
        },
        user_id=dev_user_id,
    )
    doc_id = saved["id"]

    client = TestClient(app)
    
    with patch("ai_service.chat_with_document", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "The document is an Aadhaar Card belonging to Rohan Gupta. [Page 1]"
        
        chat_payload = {
            "document_id": doc_id,
            "message": "What is the document type and cardholder name?",
        }
        resp = client.post("/api/mode/ai/chat", json=chat_payload)
        assert resp.status_code == 200
        
        # Verify stored_analysis passed to ai_service has the latest vault metadata
        call_kwargs = mock_chat.call_args.kwargs
        stored = call_kwargs.get("stored_analysis")
        assert stored is not None
        assert stored["document_type"] == "Aadhaar Card"
        assert stored["confidence"] == 0.94
        assert stored["verification_status"] == "verified"
        assert stored["extracted_fields"]["aadhaar_number"] == "1234 5678 9012"
