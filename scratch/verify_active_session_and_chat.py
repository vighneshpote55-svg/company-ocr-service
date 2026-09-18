import os
import sys
import io
from PIL import Image, ImageDraw

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
import document_store

client = TestClient(app)

def create_image(lines: list[str]) -> bytes:
    img = Image.new("RGB", (1000, 450), color="white")
    draw = ImageDraw.Draw(img)
    y = 30
    for l in lines:
        draw.text((40, y), l, fill="black")
        y += 40
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def verify_session_flow():
    print("=== Testing Active Session, Field Lookup & Cross-Document Isolation ===")

    # Step 1: Upload PAN Card
    print("\n--- 1. Upload PAN Card ---")
    pan_bytes = create_image([
        "INCOME TAX DEPARTMENT GOVT. OF INDIA",
        "Permanent Account Number Card",
        "ABCDE1234F",
        "Name: VIGHNESH POTE",
        "Father's Name: SANDIP POTE",
        "Date of Birth: 22/06/2007"
    ])
    res_pan = client.post(
        "/api/mode/offline",
        files={"file": ("Vighnesh_PAN.png", pan_bytes, "image/png")},
        data={"doc_type": "auto"}
    )
    assert res_pan.status_code == 200, f"PAN upload failed: {res_pan.text}"
    pan_id = res_pan.json()["id"]
    print(f"PAN uploaded: id={pan_id}, active_id={document_store.get_active_document_id()}")
    assert document_store.get_active_document_id() == pan_id

    # Question: What is the PAN number?
    q_pan = client.post("/api/mode/ai/chat", json={"document_id": pan_id, "message": "What is the PAN number?"})
    assert q_pan.status_code == 200
    ans_pan = q_pan.json()["response"]
    print("Q: What is the PAN number? ->", ans_pan)
    assert "ABCDE1234F" in ans_pan

    # Step 2: Upload Bank Statement
    print("\n--- 2. Upload Bank Statement ---")
    bs_bytes = create_image([
        "AXIS BANK LIMITED",
        "STATEMENT OF ACCOUNT",
        "Account Holder: SNEHA GUPTA",
        "Account Number: 918010023456789",
        "IFSC Code: UTIB0001435",
        "Branch: PIMPRI PUNE",
        "Opening Balance: 10000.00",
        "Closing Balance: 25000.00",
        "Statement Period: 01/04/2025 to 31/03/2026"
    ])
    res_bs = client.post(
        "/api/mode/offline",
        files={"file": ("Sneha_Bank_Statement.png", bs_bytes, "image/png")},
        data={"doc_type": "auto"}
    )
    assert res_bs.status_code == 200, f"Bank Statement upload failed: {res_bs.text}"
    bs_id = res_bs.json()["id"]
    print(f"Bank statement uploaded: id={bs_id}, active_id={document_store.get_active_document_id()}")
    assert document_store.get_active_document_id() == bs_id
    assert document_store.get_active_document_id() != pan_id

    # Question: What is the account holder?
    q_holder = client.post("/api/mode/ai/chat", json={"document_id": bs_id, "message": "What is the account holder?"})
    assert q_holder.status_code == 200
    ans_holder = q_holder.json()["response"]
    print("Q: What is the account holder? ->", ans_holder)
    assert "SNEHA" in ans_holder

    # Question: Customer No? (Missing)
    q_cust = client.post("/api/mode/ai/chat", json={"document_id": bs_id, "message": "Customer No?"})
    assert q_cust.status_code == 200
    ans_cust = q_cust.json()["response"]
    print("Q: Customer No? ->", ans_cust)
    assert "could not find a customer number" in ans_cust.lower()

    # Question: Why?
    history = [
        {"role": "user", "content": "Customer No?"},
        {"role": "assistant", "content": ans_cust},
    ]
    q_why = client.post("/api/mode/ai/chat", json={"document_id": bs_id, "message": "Why?", "history": history})
    assert q_why.status_code == 200
    ans_why = q_why.json()["response"]
    print("Q: Why? ->", ans_why)
    assert "customer number" in ans_why.lower()
    assert "employee" not in ans_why.lower()
    assert "searched the extracted fields" in ans_why.lower()

    # Step 3: Upload GST Certificate
    print("\n--- 3. Upload GST Certificate ---")
    gst_bytes = create_image([
        "GOVERNMENT OF INDIA - FORM GST REG-06",
        "REGISTRATION CERTIFICATE",
        "Registration Number: 27AABCT3518Q1ZS",
        "Legal Name: ACME ENTERPRISES PRIVATE LIMITED",
        "Trade Name: ACME ENTERPRISES",
        "Date of Liability: 01/07/2017"
    ])
    res_gst = client.post(
        "/api/mode/offline",
        files={"file": ("ACME_GST_RC.png", gst_bytes, "image/png")},
        data={"doc_type": "auto"}
    )
    assert res_gst.status_code == 200, f"GST Certificate upload failed: {res_gst.text}"
    gst_id = res_gst.json()["id"]
    print(f"GST uploaded: id={gst_id}, active_id={document_store.get_active_document_id()}")
    assert document_store.get_active_document_id() == gst_id

    # Question: What is the GSTIN?
    q_gst = client.post("/api/mode/ai/chat", json={"document_id": gst_id, "message": "What is the GSTIN?"})
    assert q_gst.status_code == 200
    ans_gst = q_gst.json()["response"]
    print("Q: What is the GSTIN? ->", ans_gst)
    assert "27AABCT3518Q1ZS" in ans_gst

    # Step 4: Upload PAN Card after GST Certificate (Cross-Document Leakage check)
    print("\n--- 4. Upload PAN Card after GST Certificate ---")
    pan2_bytes = create_image([
        "INCOME TAX DEPARTMENT GOVT. OF INDIA",
        "Permanent Account Number Card",
        "XYZAB9876C",
        "Name: PRIYA SHARMA",
        "Father's Name: RAJESH SHARMA",
        "Date of Birth: 10/11/1995"
    ])
    res_pan2 = client.post(
        "/api/mode/offline",
        files={"file": ("Priya_PAN.png", pan2_bytes, "image/png")},
        data={"doc_type": "auto"}
    )
    assert res_pan2.status_code == 200, f"Second PAN upload failed: {res_pan2.text}"
    pan2_id = res_pan2.json()["id"]
    print(f"Second PAN uploaded: id={pan2_id}, active_id={document_store.get_active_document_id()}")
    assert document_store.get_active_document_id() == pan2_id

    # Question: What is the GSTIN? (Must NOT leak GST from previous upload!)
    q_gst_on_pan = client.post("/api/mode/ai/chat", json={"document_id": pan2_id, "message": "What is the GSTIN?"})
    assert q_gst_on_pan.status_code == 200
    ans_gst_on_pan = q_gst_on_pan.json()["response"]
    print("Q: What is the GSTIN on PAN? ->", ans_gst_on_pan)
    assert "27AABCT3518Q1ZS" not in ans_gst_on_pan
    assert "could not find a gstin" in ans_gst_on_pan.lower()

    # Question: What is the PAN number? (Must return new PAN)
    q_pan2 = client.post("/api/mode/ai/chat", json={"document_id": pan2_id, "message": "What is the PAN number?"})
    assert q_pan2.status_code == 200
    ans_pan2 = q_pan2.json()["response"]
    print("Q: What is the PAN number? ->", ans_pan2)
    assert "XYZAB9876C" in ans_pan2
    assert "ABCDE1234F" not in ans_pan2

    print("\nALL RUNTIME SESSION & GROUNDING CHECKS PASSED!")

    # Clean up test documents
    for did in [pan_id, bs_id, gst_id, pan2_id]:
        document_store.delete_document(did)

if __name__ == "__main__":
    verify_session_flow()
