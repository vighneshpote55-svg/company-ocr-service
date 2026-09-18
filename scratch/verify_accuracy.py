import requests
import json
import os

BASE_URL = "http://127.0.0.1:8000"

def test_live_accuracy():
    print("=== LIVE ACCURACY TEST FOR AI MODE ===")

    # 1. Test PAN Document
    print("\n--- 1. Testing PAN Document ---")
    pan_path = os.path.join("scratch", "test_docs", "PAN_Vighnesh.png")
    with open(pan_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/api/mode/offline", files={"file": ("PAN_Vighnesh.png", f, "image/png")})
    assert r.status_code == 200, f"PAN upload failed: {r.text}"
    pan_data = r.json()
    print("Uploaded PAN doc:", pan_data.get("document_id"), "| Type:", pan_data.get("doc_type"))

    # Query PAN Number
    r_pan = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the PAN number?"}).json()
    print("[Q] What is the PAN number? -> [A]", r_pan["response"])
    assert "ABCDE1234F" in r_pan["response"]

    # Query Date of Birth (Formatted)
    r_dob = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the date of birth?"}).json()
    print("[Q] What is the date of birth? -> [A]", r_dob["response"])
    assert "22 June 2007" in r_dob["response"]

    # Query GSTIN on PAN (must be not found, never hallucinated or substituted)
    r_gst = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the GSTIN?"}).json()
    print("[Q] What is the GSTIN? -> [A]", r_gst["response"])
    assert "could not find a gstin" in r_gst["response"].lower()

    # Follow-up Why?
    history = [
        {"role": "user", "content": "What is the GSTIN?"},
        {"role": "assistant", "content": r_gst["response"]}
    ]
    r_why = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "Why?", "history": history}).json()
    print("[Q] Why? -> [A]", r_why["response"])
    assert "gstin" in r_why["response"].lower()
    assert "could not find" in r_why["response"].lower()

    # 2. Test Bank Statement Document
    print("\n--- 2. Testing Bank Statement Document ---")
    bs_path = os.path.join("scratch", "test_docs", "Bank_Statement_Sneha.png")
    with open(bs_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/api/mode/offline", files={"file": ("Bank_Statement_Sneha.png", f, "image/png")})
    assert r.status_code == 200, f"Bank statement upload failed: {r.text}"
    bs_data = r.json()
    print("Uploaded Bank Statement:", bs_data.get("document_id"), "| Type:", bs_data.get("doc_type"))
    print("Extracted fields:", json.dumps(bs_data.get("extracted_fields", {}), indent=2))

    # Query Bank Name
    r_bank = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the bank name?"}).json()
    print("[Q] What is the bank name? -> [A]", r_bank["response"])
    assert "AXIS BANK" in r_bank["response"]

    # Query IFSC Code (must be exact IFSC, never Bank Name)
    r_ifsc = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the IFSC Code?"}).json()
    print("[Q] What is the IFSC Code? -> [A]", r_ifsc["response"])
    assert "UTIB0001435" in r_ifsc["response"]
    assert "AXIS BANK" not in r_ifsc["response"]

    # Query Customer Number (absent from this statement -> must be not found, never Account Number!)
    r_cust = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the Customer No?"}).json()
    print("[Q] What is the Customer No? -> [A]", r_cust["response"])
    assert "could not find a customer number" in r_cust["response"].lower()
    assert "XXXXXXXXXXX6789" not in r_cust["response"]

    # Follow-up Why? for Customer Number (must explain not found Customer Number)
    bs_history = [
        {"role": "user", "content": "What is the Customer No?"},
        {"role": "assistant", "content": r_cust["response"]}
    ]
    r_cust_why = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "Why?", "history": bs_history}).json()
    print("[Q] Why? -> [A]", r_cust_why["response"])
    assert "customer number" in r_cust_why["response"].lower()
    assert "could not find" in r_cust_why["response"].lower()

    # Query Statement Period (Human-formatted: 01 April 2025 – 31 March 2026, NEVER python dict)
    r_sp = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the statement period?"}).json()
    print("[Q] What is the statement period? -> [A]", r_sp["response"])
    assert "01 April 2025 – 31 March 2026" in r_sp["response"]
    assert "{'from_date'" not in r_sp["response"]
    assert "{" not in r_sp["response"]

    # Query Branch
    r_br = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the branch?"}).json()
    print("[Q] What is the branch? -> [A]", r_br["response"])
    assert "PIMPRI PUNE" in r_br["response"]

    # Query Account Number (masked)
    r_acc = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the account number?"}).json()
    print("[Q] What is the account number? -> [A]", r_acc["response"])
    assert "6789" in r_acc["response"]

    # 3. Test GST Certificate Document
    print("\n--- 3. Testing GST Certificate Document ---")
    gst_path = os.path.join("scratch", "test_docs", "GST_Certificate.png")
    with open(gst_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/api/mode/offline", files={"file": ("GST_Certificate.png", f, "image/png")})
    assert r.status_code == 200, f"GST upload failed: {r.text}"
    gst_data = r.json()
    print("Uploaded GST:", gst_data.get("document_id"), "| Type:", gst_data.get("doc_type"))

    # Query GSTIN
    r_gstin = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the GSTIN?"}).json()
    print("[Q] What is the GSTIN? -> [A]", r_gstin["response"])
    assert "27AABCT3518Q1ZS" in r_gstin["response"]

    # Query Legal Name
    r_legal = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the legal business name?"}).json()
    print("[Q] What is the legal business name? -> [A]", r_legal["response"])
    assert "ENTERPRISES" in r_legal["response"]

    # Query PAN on GST (should not substitute GSTIN for PAN)
    r_pan_on_gst = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={"message": "What is the PAN number?"}).json()
    print("[Q] What is the PAN number? (on GST) -> [A]", r_pan_on_gst["response"])
    assert "27AABCT3518Q1ZS" not in r_pan_on_gst["response"]

    print("\nALL LIVE ACCURACY VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_live_accuracy()
