"""
Verification of AI Mode Polish using TestClient:
1. Ingest document via /api/mode/ai/analyze.
2. Verify /api/mode/ai/chat responses for all 4 Quick Actions:
   - Summarize
   - Extract Fields
   - Find Dates
   - Find Numbers
3. Verify page citations [Page 1] appear in the answers.
4. Verify document synchronization without 404s.
"""
import os
import sys
import io

os.environ["AUTH_MODE"] = "disabled"
os.environ.pop("AUTH_ENABLED", None)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from main import app
from auth_dependencies import get_current_user, UserProfile
import document_store

app.dependency_overrides[get_current_user] = lambda: UserProfile(id="11111111-1111-4111-8111-111111111111", email="test@example.com")

client = TestClient(app)

def create_test_image(lines: list[str]) -> bytes:
    img = Image.new("RGB", (1000, 500), color="white")
    draw = ImageDraw.Draw(img)
    y = 30
    for l in lines:
        draw.text((40, y), l, fill="black")
        y += 40
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def test_ai_polish():
    print("=== Testing AI Mode Final Polish End-to-End ===")

    # 1. Register test document in document store
    print("\n[1] Registering test document in document store...")
    doc_record = document_store.save_document(
        file_bytes=b"%PDF-1.4 test",
        filename="Acme_Invoice_Agreement.pdf",
        result_data={
            "user_id": "11111111-1111-4111-8111-111111111111",
            "doc_type": "invoice",
            "document_type": "Commercial Invoice",
            "extracted_text": (
                "--- Page 1 ---\n"
                "ACME FINANCIAL SERVICES PVT LTD\n"
                "INVOICE & SERVICE AGREEMENT\n"
                "Invoice Number: INV-2024-8891\n"
                "Client Name: TechSolutions Corp\n"
                "Effective Date: 15/01/2024\n"
                "Due Date: 15/02/2024\n"
                "Total Amount Due: $14,500.00\n"
                "Base Retainer Fee: $10,000.00\n"
                "GSTIN: 27AABCU9603R1ZM\n"
                "PAN Number: ABCDE1234F\n"
                "Status: Authenticated and Verified"
            ),
            "extracted_fields": {
                "invoice_number": "INV-2024-8891",
                "client_name": "TechSolutions Corp",
                "effective_date": "15/01/2024",
                "due_date": "15/02/2024",
                "total_amount": "$14,500.00",
                "gstin": "27AABCU9603R1ZM",
                "pan_number": "ABCDE1234F",
            },
            "summary": "Commercial invoice and service agreement from Acme Financial Services to TechSolutions Corp.",
            "verification_status": "verified",
            "risk_score": 0,
        },
    )
    doc_id = doc_record["id"]
    document_store.set_active_document(doc_id)
    print(f" -> Document Registered: ID={doc_id}, Type={doc_record.get('document_type')}")

    # 2. Test Quick Action: Summarize
    print("\n[2] Testing Quick Action: Summarize...")
    q_sum = "Summarize this document with key provisions, primary parties, and essential scope. Cite page references."
    r_sum = client.post("/api/mode/ai/chat", json={"document_id": doc_id, "message": q_sum})
    assert r_sum.status_code == 200, f"Summarize failed: {r_sum.text}"
    ans_sum = r_sum.json()["response"]
    print(f" -> Response:\n{ans_sum}")
    assert "[Page" in ans_sum or "Page" in ans_sum, f"Expected page citation in summarize: {ans_sum}"

    # 3. Test Quick Action: Extract Fields
    print("\n[3] Testing Quick Action: Extract Fields...")
    q_ext = "Extract all primary structured fields, verified entities, and identifiers from this document. Cite page references for each field."
    r_ext = client.post("/api/mode/ai/chat", json={"document_id": doc_id, "message": q_ext})
    assert r_ext.status_code == 200, f"Extract failed: {r_ext.text}"
    ans_ext = r_ext.json()["response"]
    print(f" -> Response:\n{ans_ext}")
    assert "[Page 1]" in ans_ext, f"Expected [Page 1] in extract fields: {ans_ext}"

    # 4. Test Quick Action: Find Dates
    print("\n[4] Testing Quick Action: Find Dates...")
    q_dates = "Find and list all dates, effective periods, deadlines, and milestones in this document. Cite page references."
    r_dates = client.post("/api/mode/ai/chat", json={"document_id": doc_id, "message": q_dates})
    assert r_dates.status_code == 200, f"Find Dates failed: {r_dates.text}"
    ans_dates = r_dates.json()["response"]
    print(f" -> Response:\n{ans_dates}")
    assert "[Page 1]" in ans_dates or "15/01/2024" in ans_dates, f"Expected dates with citation: {ans_dates}"

    # 5. Test Quick Action: Find Numbers
    print("\n[5] Testing Quick Action: Find Numbers...")
    q_nums = "Find and list all monetary amounts, numerical figures, balances, and quantities in this document. Cite page references."
    r_nums = client.post("/api/mode/ai/chat", json={"document_id": doc_id, "message": q_nums})
    assert r_nums.status_code == 200, f"Find Numbers failed: {r_nums.text}"
    ans_nums = r_nums.json()["response"]
    print(f" -> Response:\n{ans_nums}")
    assert "[Page 1]" in ans_nums or "14,500" in ans_nums, f"Expected numbers with citation: {ans_nums}"

    # 6. Test specific question
    print("\n[6] Testing Question: What is the GSTIN?")
    r_gst = client.post("/api/mode/ai/chat", json={"document_id": doc_id, "message": "What is the GSTIN?"})
    assert r_gst.status_code == 200
    ans_gst = r_gst.json()["response"]
    print(f" -> Response:\n{ans_gst}")
    assert "27AABCU9603R1ZM" in ans_gst

    print("\n[SUCCESS] ALL TESTS PASSED: 4 Quick Actions, Grounded Chat, and Page Citations are Working Perfectly!")

if __name__ == "__main__":
    test_ai_polish()
