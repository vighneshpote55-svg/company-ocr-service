import sys
sys.stdout.reconfigure(encoding="utf-8")
import requests

BASE_URL = "http://127.0.0.1:8000"

def test_api_chat_flow():
    # 1. Health check
    h = requests.get(f"{BASE_URL}/health")
    print("Health check:", h.status_code, h.json())
    assert h.status_code == 200

    # 2. Upload real Axis Bank PDF in AI Mode
    pdf_path = "C:/Users/sachi/Downloads/Account_Statement_Report_30-07-2026_1246hrs.PDF"
    with open(pdf_path, "rb") as f:
        files = {"file": ("Account_Statement_Report_30-07-2026_1246hrs.PDF", f, "application/pdf")}
        data = {"mode": "ai"}
        up_res = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
    
    print("Upload status:", up_res.status_code)
    assert up_res.status_code == 200, f"Upload failed: {up_res.text}"
    doc_data = up_res.json()
    doc_id = doc_data["document_id"]
    print("Document ID:", doc_id)
    print("Document Type:", doc_data.get("document_type"))
    print("Stored Extracted Fields:", list(doc_data.get("extracted_fields", {}).keys()))

    # 3. Test the exact 8 questions from the prompt in conversation
    questions = [
        ("What is the bank name?", ["Axis Bank"]),
        ("What is the account number?", ["0170"]),
        ("What is the account holder?", ["SNEHA"]),
        ("What is the statement period?", ["From: 30/07/2025", "To: 30/07/2026"]),
        ("What is the Customer No?", ["978738241"]),
        ("Why?", ["Customer Number", "label"]),
        ("What is the branch?", ["AJMERA COMPLEX", "PIMPRI", "PUNE"]),
        ("What is the IFSC Code?", ["UTIB0001435"]),
    ]

    history = []

    for q, expected_tokens in questions:
        payload = {
            "document_id": doc_id,
            "message": q,
            "history": history,
        }
        chat_res = requests.post(f"{BASE_URL}/api/mode/ai/chat", json=payload)
        assert chat_res.status_code == 200, f"Chat failed for '{q}': {chat_res.text}"
        reply = chat_res.json()["response"]
        print(f"\nUser: {q}")
        print(f"Assistant: {reply}")

        for tok in expected_tokens:
            assert tok.lower() in reply.lower(), f"Expected token '{tok}' not found in reply: '{reply}'"

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": reply})

    print("\n" + "=" * 60)
    print("ALL 8 API ENDPOINT CHAT QUESTIONS VERIFIED SUCCESSFULLY AGAINST LIVE SERVER!")
    print("=" * 60)

if __name__ == "__main__":
    test_api_chat_flow()
