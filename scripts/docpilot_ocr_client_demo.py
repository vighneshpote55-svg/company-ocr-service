"""
DocPilot AI Offline OCR Client Demonstration Script
Demonstrates connecting to company-ocr-service using an API Key to perform offline OCR.
"""

import os
import sys

# Ensure repository root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import requests
import api_key_manager

BASE_URL = "http://localhost:8000"


def main():
    print("=" * 70)
    print("DOCPILOT AI <-> OFFLINE OCR SERVICE INTEGRATION")
    print("=" * 70)

    # 1. Obtain or generate an active API key
    record, api_key = api_key_manager.create_api_key(
        name="DocPilot AI Runner",
        user_id="00000000-0000-0000-0000-000000000001",
        user_email="admin@docpilot.ai",
    )
    print(f"Generated API Key : {api_key}")
    print(f"Service Endpoint  : {BASE_URL}")

    # 2. Ping & Check Engine Status
    print("\n[1/3] Checking Service Status (GET /api/v1/ping)...")
    try:
        ping_res = requests.get(
            f"{BASE_URL}/api/v1/ping",
            headers={"X-API-Key": api_key},
            timeout=10,
        )
        ping_res.raise_for_status()
        ping_data = ping_res.json()
        print(f"  • Status         : {ping_data.get('status')}")
        print(f"  • OCR Engine     : {ping_data.get('ocr_engine')} ({ping_data.get('ocr_engine_status')})")
        print(f"  • Execution Mode : {ping_data.get('mode')}")
        print(f"  • Supported Docs : {ping_data.get('supported_documents_count')} types")
    except Exception as e:
        print(f"Ping failed: {e}")
        sys.exit(1)

    # 3. Test Offline OCR on Sample Document
    test_doc = "/home/incraax-ai/Documents/Vighnesh/DocPilot/frontend/e2e/assets/dummy_pan.png"
    print(f"\n[2/3] Executing Offline OCR Pipeline on Document (POST /api/v1/ocr)...")
    print(f"  • Target File    : {test_doc}")

    with open(test_doc, "rb") as f:
        ocr_res = requests.post(
            f"{BASE_URL}/api/v1/ocr",
            headers={"X-API-Key": api_key},
            files={"file": ("dummy_pan.png", f, "image/png")},
            data={"doc_type": "auto"},
            timeout=30,
        )

    if ocr_res.status_code != 200:
        print(f"OCR request failed: HTTP {ocr_res.status_code} - {ocr_res.text}")
        sys.exit(1)

    data = ocr_res.json()
    print("\n" + "=" * 70)
    print("EXTRACTED DOCUMENT INTELLIGENCE (100% OFFLINE RAPIDOCR)")
    print("=" * 70)
    print(f"Document ID         : {data.get('document_id')}")
    print(f"OCR Engine          : {data.get('ocr_engine')}")
    print(f"Detected Type       : {data.get('doc_type')} ({data.get('document_type')})")
    print(f"Verification Status : {data.get('verification_status')}")
    print(f"Review Required     : {data.get('review_required')}")
    print(f"Risk Score          : {data.get('risk_score')}")
    print(f"Processing Time     : {data.get('processing_time_ms')} ms")

    print("\nExtracted Key-Value Fields:")
    for key, val in data.get("extracted_fields", {}).items():
        if not key.startswith("detected_") and not key.startswith("language_") and not key.startswith("partial_"):
            print(f"  • {key:20s}: {val}")

    print("\nExtracted Text (First Lines):")
    lines = (data.get("extracted_text") or "").splitlines()
    for l in lines[:7]:
        print(f"  | {l}")

    # 4. Also verify native DocPilot endpoint: POST /ocr/pan?sync=true
    print("\n[3/3] Verifying Native DocPilot Backend Endpoint (POST /ocr/pan?sync=true)...")
    with open(test_doc, "rb") as f:
        native_res = requests.post(
            f"{BASE_URL}/ocr/pan?sync=true",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": ("dummy_pan.png", f, "image/png")},
            timeout=30,
        )
    if native_res.status_code == 200:
        n_data = native_res.json()
        print(f"  • Status : {n_data.get('status')}")
        print(f"  • Fields : {n_data.get('extracted_fields')}")
        print("\nAll integration endpoints verified successfully!")
    else:
        print(f"Native endpoint returned HTTP {native_res.status_code}: {native_res.text}")


if __name__ == "__main__":
    main()
