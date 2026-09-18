import sys
import os
sys.path.insert(0, os.path.abspath("."))
import json
import re
import urllib.request
import fitz  # PyMuPDF
from fastapi.testclient import TestClient
from main import app
import ai_service
import ollama_ai
import document_store
from verifier import classify_document_content
from extractors import extract_document_fields_raw

client = TestClient(app)

def run_step_1():
    print("\n--- STEP 1: Backend Health Check ---")
    resp1 = urllib.request.urlopen('http://127.0.0.1:8000/health')
    assert resp1.status == 200
    data1 = json.loads(resp1.read().decode())
    print("GET /health ->", data1["status"], "OCR Engine:", data1.get("ocr_engine"))

    resp2 = urllib.request.urlopen('http://127.0.0.1:8000/api/health')
    assert resp2.status == 200
    data2 = json.loads(resp2.read().decode())
    print("GET /api/health ->", data2["status"])
    assert data1["status"] == "healthy"
    assert data2["status"] == "healthy"
    print("STEP 1: PASS")

def run_step_2():
    print("\n--- STEP 2: Frontend Serving Check ---")
    resp = urllib.request.urlopen('http://127.0.0.1:8000/')
    assert resp.status == 200
    html = resp.read().decode()
    assert '<div id="root">' in html
    js_match = re.search(r'src="(/assets/[^"]+\.js)"', html)
    css_match = re.search(r'href="(/assets/[^"]+\.css)"', html)
    assert js_match, "JS bundle not found in index.html"
    assert css_match, "CSS bundle not found in index.html"

    js_url = 'http://127.0.0.1:8000' + js_match.group(1)
    css_url = 'http://127.0.0.1:8000' + css_match.group(1)
    js_resp = urllib.request.urlopen(js_url)
    css_resp = urllib.request.urlopen(css_url)
    assert js_resp.status == 200
    assert css_resp.status == 200
    print(f"Index HTML: 200 OK, JS: {js_resp.status} OK ({len(js_resp.read())} bytes), CSS: {css_resp.status} OK ({len(css_resp.read())} bytes)")
    print("STEP 2: PASS")

def run_step_3():
    print("\n--- STEP 3: Offline Mode Verification ---")
    # 3a. Real Supported Document: PAN Card text
    pan_text = """
    INCOMETAXDEPARTMENT
    GOVT.OFINDIA
    RAJESH KUMAR VERMA
    SURESH VERMA
    12/04/1988
    BNZPV1234K
    Permanent Account Number Card
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), pan_text)
    pdf_bytes = doc.write()
    doc.close()

    # Upload with filename that does NOT hint PAN, to test purely content-based routing
    upload_resp = client.post(
        "/api/upload",
        files={"file": ("scanned_document_001.pdf", pdf_bytes, "application/pdf")},
        data={"doc_type": "auto"}
    )
    assert upload_resp.status_code == 200, upload_resp.text
    res = upload_resp.json()
    print("PAN Upload Result:", {
        "document_type": res.get("document_type"),
        "issuer": res.get("issuer"),
        "status": res.get("status"),
        "pan_number": res.get("extracted_fields", {}).get("pan_number"),
        "name": res.get("extracted_fields", {}).get("name"),
        "dob": res.get("extracted_fields", {}).get("dob"),
    })
    assert res.get("document_type") == "PAN Card"
    assert "Income Tax Department" in res.get("issuer", "")
    assert res.get("extracted_fields", {}).get("pan_number") == "BNZPV1234K"
    assert "RAJESH" in res.get("extracted_fields", {}).get("name", "").upper()
    assert res.get("extracted_fields", {}).get("dob") == "12/04/1988"

    # 3b. Unsupported / Unknown Document named with misleading filename
    # Must NOT classify based on filename!
    unknown_text = "The committee held a preliminary assembly regarding the proposed regional forestry guidelines."
    doc_unk = fitz.open()
    p_unk = doc_unk.new_page()
    p_unk.insert_text((50, 50), unknown_text)
    unk_pdf_bytes = doc_unk.write()
    doc_unk.close()

    unk_resp = client.post(
        "/api/upload",
        files={"file": ("salary_slip_and_pan_card.pdf", unk_pdf_bytes, "application/pdf")},
        data={"doc_type": "auto"}
    )
    assert unk_resp.status_code == 200, unk_resp.text
    unk_res = unk_resp.json()
    print("Misleading Filename Result:", {
        "filename": unk_res.get("filename"),
        "document_type": unk_res.get("document_type"),
        "issuer": unk_res.get("issuer"),
        "status": unk_res.get("status"),
        "fields": unk_res.get("extracted_fields")
    })
    assert unk_res.get("document_type") == "Unknown Document", f"Expected Unknown Document but got {unk_res.get('document_type')}"
    assert unk_res.get("extracted_fields") == {"document_type": "Unknown Document"}
    print("STEP 3: PASS")

def run_step_4_to_6():
    print("\n--- STEPS 4, 5 & 6: AI Mode & Chat Grounding Verification ---")
    # Real document NOT in the 22 predefined offline types: Employment Contract
    contract_text = """
    EMPLOYMENT AGREEMENT
    This Employment Agreement (the "Agreement") is entered into on 15th January 2024,
    BETWEEN:
    Acme Innovations Private Limited, a company incorporated under the Companies Act, 2013 (the "Employer")
    AND
    Ananya Deshmukh, residing at 402 Palm Heights, Powai, Mumbai 400076 (the "Employee").

    1. Position and Joining Date:
    The Employee shall be employed as Senior Software Engineer with effect from 1st February 2024.

    2. Compensation:
    The Employer shall pay the Employee a fixed base salary of INR 18,50,000 per annum,
    payable in monthly instalments subject to statutory deductions.

    3. Governing Law:
    This Agreement shall be governed by and construed in accordance with the laws of India.
    """
    doc_contract = fitz.open()
    p_c = doc_contract.new_page()
    p_c.insert_text((50, 50), contract_text)
    contract_bytes = doc_contract.write()
    doc_contract.close()

    # Upload to AI Mode analyze endpoint (/api/mode/ai/analyze)
    ai_resp = client.post(
        "/api/mode/ai/analyze",
        files={"file": ("doc_attachment_8832.pdf", contract_bytes, "application/pdf")},
    )
    assert ai_resp.status_code == 200, ai_resp.text
    ai_data = ai_resp.json()
    doc_id = ai_data["document_id"]
    print("AI Analysis Result:", {
        "document_id": doc_id,
        "document_type": ai_data.get("document_type"),
        "confidence": ai_data.get("confidence"),
        "summary": ai_data.get("summary"),
        "evidence": ai_data.get("evidence"),
        "extracted_fields": ai_data.get("extracted_fields")
    })

    # STEP 5: Verification of classification & evidence
    assert ai_data.get("document_type") == "Employment Contract"
    assert ai_data.get("confidence") in ["high", "medium"]
    assert len(ai_data.get("evidence", [])) >= 1
    assert "employment" in ai_data.get("summary", "").lower() or "contract" in ai_data.get("summary", "").lower()
    print("STEP 4 & 5: PASS")

    # STEP 6: Interactive Chat Grounding
    print("\nTesting Grounded Chat:")
    
    # 6a. Asking for Employee Name (exists in document)
    chat1 = client.post(
        "/api/mode/ai/chat",
        json={"document_id": doc_id, "message": "What is the employee name?"}
    )
    assert chat1.status_code == 200, chat1.text
    ans1 = chat1.json()["response"]
    print("Q: What is the employee name? ->", ans1)
    assert "Ananya" in ans1 or "Deshmukh" in ans1

    # 6b. Asking for Salary (exists in document)
    chat2 = client.post(
        "/api/mode/ai/chat",
        json={"document_id": doc_id, "message": "What is the salary?"}
    )
    assert chat2.status_code == 200, chat2.text
    ans2 = chat2.json()["response"]
    print("Q: What is the salary? ->", ans2)
    assert "18,50,000" in ans2 or "1850000" in ans2

    # 6c. Asking for Non-Existent Field (e.g. PAN number or Vehicle number on an employment contract)
    chat3 = client.post(
        "/api/mode/ai/chat",
        json={"document_id": doc_id, "message": "What is the PAN number?"}
    )
    assert chat3.status_code == 200, chat3.text
    ans3 = chat3.json()["response"]
    print("Q: What is the PAN number? ->", ans3)
    assert "could not find" in ans3.lower() or "not found" in ans3.lower() or "no pan" in ans3.lower()

    # 6d. Verify it NEVER produces placeholder tokens
    for bad_token in ["***/Name", "Demo Customer", "Demo Value", "*/Name"]:
        assert bad_token not in ans1, f"Found placeholder {bad_token} in response"
        assert bad_token not in ans2, f"Found placeholder {bad_token} in response"
        assert bad_token not in ans3, f"Found placeholder {bad_token} in response"

    print("STEP 6: PASS")

def run_step_7():
    print("\n--- STEP 7: Investigate Previous Bug ---")
    # Verify the previous buggy file text:
    # "WhatsApp Image 2026-09-10 at 16.53.24.jpeg"
    whatsapp_pan_text = """
    INCOMETAXDEPARTMENT
    GOVT.OFINDIA
    VIKAS JOSHI
    RAMESH JOSHI
    19/07/1992
    ABCDE1234F
    Permanent Account Number
    """
    classified = classify_document_content(whatsapp_pan_text)
    print("WhatsApp Image Content Classification:", classified)
    assert classified["document_type"] == "PAN Card"
    assert classified["document_type"] != "Incometaxdepartment"
    assert "Incometaxdepartment" not in classified["document_type"]

    # Verify AI normalization
    norm = ollama_ai.normalize_document_type("incometaxdepartment", text_content=whatsapp_pan_text)
    print("AI Normalization of 'incometaxdepartment':", norm)
    assert norm == "PAN Card"
    assert norm != "Incometaxdepartment"
    print("STEP 7: PASS")

def run_step_8():
    print("\n--- STEP 8: AI Provider Status ---")
    resp = client.get("/api/mode/ai/status")
    assert resp.status_code == 200, resp.text
    status_data = resp.json()
    print("GET /api/mode/ai/status ->", status_data)
    # Validate structure
    assert "configured" in status_data
    assert "provider" in status_data
    assert "model" in status_data
    assert "message" in status_data
    assert "ollama" in status_data
    print("Configured Provider:", status_data["provider"], "| Configured API Key:", status_data["configured"])
    print("STEP 8: PASS")

def run_step_9():
    print("\n--- STEP 9: Security & Context Isolation ---")
    # 9a. Verify document isolation
    doc1 = document_store.save_document(
        file_bytes=b"doc1 content",
        filename="doc1.txt",
        result_data={"extracted_text": "Secret Information for User A: Account 9999", "doc_type": "text"}
    )
    doc2 = document_store.save_document(
        file_bytes=b"doc2 content",
        filename="doc2.txt",
        result_data={"extracted_text": "Public Information for User B: Account 1111", "doc_type": "text"}
    )

    # Asking doc2 about doc1 secret
    chat_resp = client.post(
        "/api/mode/ai/chat",
        json={"document_id": doc2["id"], "message": "What is the secret for User A?"}
    )
    assert chat_resp.status_code == 200
    reply = chat_resp.json()["response"]
    print("Isolated doc query reply:", reply)
    assert "9999" not in reply, "Leaked information from doc1 into doc2!"

    # 9b. Verify non-existent doc_id gives 404
    bad_resp = client.post(
        "/api/mode/ai/chat",
        json={"document_id": "non_existent_uuid_12345", "message": "Hello"}
    )
    assert bad_resp.status_code == 404

    # 9c. Verify API key is NOT in frontend assets
    frontend_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
    if os.path.exists(frontend_dist):
        for root, dirs, files in os.walk(frontend_dist):
            for file in files:
                if file.endswith(".js"):
                    with open(os.path.join(root, file), "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        assert "AI_API_KEY" not in content
                        assert "OPENROUTER_API_KEY" not in content
                        assert "OPENAI_API_KEY" not in content

    print("STEP 9: PASS")

if __name__ == "__main__":
    run_step_1()
    run_step_2()
    run_step_3()
    run_step_4_to_6()
    run_step_7()
    run_step_8()
    run_step_9()
    print("\n=======================================================")
    print("ALL RUNTIME VERIFICATION STEPS (1 through 9) PASSED!")
    print("=======================================================")
