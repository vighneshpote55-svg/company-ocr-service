import os
import requests
import json

BASE_URL = "http://localhost"

def test_flow():
    print("=== 1. Initial State / Safe Config ===")
    r = requests.get(f"{BASE_URL}/api/ai/config")
    assert r.status_code == 200, f"Failed config: {r.status_code}"
    cfg = r.json()
    print("AI Config:", json.dumps(cfg, indent=2))
    assert cfg["mode"] == "local"
    assert cfg["active_provider"] == "ollama"
    assert cfg["active_model"] == "qwen2.5vl:3b"
    assert cfg["api_key_configured"] is False
    assert "api_key" not in cfg  # Must never leak

    print("\n=== 2. Test Local Ollama Connection ===")
    r = requests.post(f"{BASE_URL}/api/ai/test-connection", json={"provider": "ollama", "model": "qwen2.5vl:3b"})
    assert r.status_code == 200
    res = r.json()
    print("Test connection result:", json.dumps(res, indent=2))
    assert res["success"] is True

    print("\n=== 3. Upload Document in AI Mode (Local Ollama) ===")
    pan_path = os.path.join(os.getcwd(), "test_docs", "sample_pan.png")
    with open(pan_path, "rb") as f:
        files = {"file": ("sample_pan.png", f, "image/png")}
        data = {"prompt": "Analyze this identity card"}
        r = requests.post(f"{BASE_URL}/api/mode/ai/analyze", files=files, data=data)
    assert r.status_code == 200, f"AI upload failed: {r.status_code} {r.text}"
    ai_result = r.json()
    doc_id = ai_result.get("document_id")
    print(f"AI Mode Upload Result: doc_id={doc_id}, doc_type={ai_result.get('document_type')}, summary={ai_result.get('summary')[:80]}...")
    assert doc_id is not None

    print("\n=== 4. AI Chat Question ===")
    r = requests.post(f"{BASE_URL}/api/mode/ai/chat", json={
        "document_id": doc_id,
        "message": "What is the document title or type of this card?"
    })
    assert r.status_code == 200, f"Chat failed: {r.status_code} {r.text}"
    chat_res = r.json()
    print("AI Chat Response:", chat_res.get("response"))
    assert len(chat_res.get("response", "")) > 0

    print("\n=== 5. Configure External Provider in Backend ===")
    # Configure mock external provider or test credentials
    r = requests.post(f"{BASE_URL}/api/ai/config", json={
        "provider": "openrouter",
        "api_key": "sk-or-v1-dummy-key-for-test-1234567890abcdef",
        "model": "google/gemini-flash-1.5",
        "base_url": "https://openrouter.ai/api/v1"
    })
    assert r.status_code == 200
    ext_cfg = r.json()
    print("External Config:", json.dumps(ext_cfg, indent=2))
    assert ext_cfg["mode"] == "external"
    assert ext_cfg["active_provider"] == "openrouter"
    assert ext_cfg["active_model"] == "google/gemini-flash-1.5"
    assert ext_cfg["api_key_configured"] is True
    assert "sk-or-v1" not in json.dumps(ext_cfg)  # Never leak key

    print("\n=== 6. Reset / Clear API Key -> Fallback to Local Ollama ===")
    r = requests.post(f"{BASE_URL}/api/ai/config", json={
        "provider": "ollama",
        "api_key": "",
        "model": "qwen2.5vl:3b"
    })
    assert r.status_code == 200
    fallback_cfg = r.json()
    print("Fallback Config:", json.dumps(fallback_cfg, indent=2))
    assert fallback_cfg["mode"] == "local"
    assert fallback_cfg["active_provider"] == "ollama"
    assert fallback_cfg["active_model"] == "qwen2.5vl:3b"
    assert fallback_cfg["api_key_configured"] is False

    print("\n=== 7. Offline Mode Upload (PAN Card) ===")
    with open(pan_path, "rb") as f:
        files = {"file": ("sample_pan.png", f, "image/png")}
        data = {"document_type": "PAN Card"}
        r = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
    assert r.status_code == 200, f"Offline upload failed: {r.status_code} {r.text}"
    offline_result = r.json()
    print(f"Offline Mode Upload Result: status={offline_result.get('status')}, doc_type={offline_result.get('document_type')}, verified={offline_result.get('verification_result', {}).get('status')}")

    print("\n=== 8. Document Vault Check ===")
    r = requests.get(f"{BASE_URL}/api/documents?limit=50")
    assert r.status_code == 200
    vault_data = r.json()
    items = vault_data.get("items", [])
    print(f"Document Vault total items: {len(items)}")
    for item in items[:5]:
        print(f"  - [{item.get('mode', 'offline')}] {item.get('document_type')} ({item.get('filename')}) ID: {item.get('document_id')}")

    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_flow()
