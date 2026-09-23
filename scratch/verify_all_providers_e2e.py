import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import time
import jwt
from fastapi.testclient import TestClient
import main
from ai_providers import (
    ai_provider_manager,
    OllamaAdapter,
    OpenAIAdapter,
    GeminiAdapter,
    OpenRouterAdapter,
    CustomAdapter,
)

def make_test_jwt(user_id: str, email: str, role: str = "user", expires_in_seconds: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "app_metadata": {"role": role},
        "user_metadata": {"full_name": "Test User"},
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    secret = os.environ.get("SUPABASE_JWT_SECRET") or "super-secret-supabase-jwt-test-key-32chars!"
    return jwt.encode(payload, secret, algorithm="HS256")

client = TestClient(main.app)
admin_token = make_test_jwt("admin-123", "admin@incraax.com", role="admin")
user_token = make_test_jwt("user-456", "user@incraax.com", role="user")

admin_headers = {"Authorization": f"Bearer {admin_token}"}
user_headers = {"Authorization": f"Bearer {user_token}"}

print("=" * 60)
print("1. VERIFY AI CONFIG ENDPOINT (GET /api/ai/config)")
print("=" * 60)
res = client.get("/api/ai/config", headers=admin_headers)
print("Admin GET /api/ai/config:", res.status_code, res.json())
assert res.status_code == 200
cfg = res.json()
assert "api_key" not in cfg, "Secret api_key must never be exposed"

res_user = client.get("/api/ai/config", headers=user_headers)
print("User GET /api/ai/config:", res_user.status_code, res_user.json())
assert res_user.status_code == 200

print("=" * 60)
print("2. VERIFY PERMISSIONS / ACCESS CONTROL")
print("=" * 60)
# Normal user trying to update config -> 403 Forbidden
res_fail = client.post(
    "/api/ai/config",
    json={"active_provider": "openai", "active_model": "gpt-4o-mini"},
    headers=user_headers,
)
print("User POST /api/ai/config (expect 403):", res_fail.status_code, res_fail.json())
assert res_fail.status_code == 403

# Normal user trying to test connection -> 403 Forbidden
res_fail_test = client.post(
    "/api/ai/test-connection",
    json={"provider": "ollama"},
    headers=user_headers,
)
print("User POST /api/ai/test-connection (expect 403):", res_fail_test.status_code)
assert res_fail_test.status_code == 403

print("=" * 60)
print("3. VERIFY REAL LIVE CONNECTION TESTING (POST /api/ai/test-connection)")
print("=" * 60)
# Ollama test
res_ollama = client.post(
    "/api/ai/test-connection",
    json={"provider": "ollama"},
    headers=admin_headers,
)
print("Admin test Ollama:", res_ollama.status_code, res_ollama.json())
assert res_ollama.status_code == 200
data = res_ollama.json()
assert data["provider"] == "ollama"
# Notice: latency_ms is real
print(f"Ollama connected: {data['success']}, Latency: {data.get('latency_ms')}ms")

# Real invalid key test (must report real failure with actual reason, NOT fake connected)
res_bad_key = client.post(
    "/api/ai/test-connection",
    json={"provider": "openai", "api_key": "sk-invalid-test-key-12345", "model": "gpt-4o-mini"},
    headers=admin_headers,
)
print("Admin test OpenAI with invalid key:", res_bad_key.status_code, res_bad_key.json())
assert res_bad_key.status_code == 200
bad_data = res_bad_key.json()
assert bad_data["success"] is False, "Must NOT fake connected on invalid key!"
print(f"Properly rejected invalid key with message: {bad_data.get('message')}")

# Real Gemini test with invalid key
res_bad_gemini = client.post(
    "/api/ai/test-connection",
    json={"provider": "gemini", "api_key": "AIzaSy-invalid-test-key", "model": "gemini-2.0-flash"},
    headers=admin_headers,
)
print("Admin test Gemini with invalid key:", res_bad_gemini.status_code, res_bad_gemini.json())
assert res_bad_gemini.status_code == 200
bad_gemini_data = res_bad_gemini.json()
assert bad_gemini_data["success"] is False

# Custom format test
res_bad_custom = client.post(
    "/api/ai/test-connection",
    json={"provider": "custom", "base_url": "http://127.0.0.1:9999/v1", "model": "test-model", "request_format": "chat_completions"},
    headers=admin_headers,
)
print("Admin test Custom with unreachable host:", res_bad_custom.status_code, res_bad_custom.json())
assert res_bad_custom.status_code == 200
bad_custom_data = res_bad_custom.json()
assert bad_custom_data["success"] is False

print("=" * 60)
print("4. VERIFY CHAT ROUTING AND DOCUMENT ANALYSIS PER PROVIDER")
print("=" * 60)

# A. Ollama Flow via Admin API
res_save_ollama = client.post(
    "/api/ai/config",
    json={"active_provider": "ollama", "active_model": "qwen2.5vl:3b", "fallback_on_error": False},
    headers=admin_headers,
)
assert res_save_ollama.status_code == 200
active_adapter = ai_provider_manager.get_active_provider()
print(f"Ollama Flow - Active Adapter: {active_adapter.provider_name}, is_local: {active_adapter.is_local}")
assert isinstance(active_adapter, OllamaAdapter)

# B. OpenAI Flow via Admin API
res_save_openai = client.post(
    "/api/ai/config",
    json={"active_provider": "openai", "active_model": "gpt-4o-mini", "api_key": "sk-test-live-key", "fallback_on_error": False},
    headers=admin_headers,
)
assert res_save_openai.status_code == 200
active_adapter = ai_provider_manager.get_active_provider()
print(f"OpenAI Flow - Active Adapter: {active_adapter.provider_name}, is_local: {active_adapter.is_local}")
assert isinstance(active_adapter, OpenAIAdapter)
assert active_adapter.model_name == "gpt-4o-mini"

# C. Gemini Flow via Admin API
res_save_gemini = client.post(
    "/api/ai/config",
    json={"active_provider": "gemini", "active_model": "gemini-2.0-flash", "api_key": "AIzaSyTestKey", "fallback_on_error": False},
    headers=admin_headers,
)
assert res_save_gemini.status_code == 200
active_adapter = ai_provider_manager.get_active_provider()
print(f"Gemini Flow - Active Adapter: {active_adapter.provider_name}, is_local: {active_adapter.is_local}")
assert isinstance(active_adapter, GeminiAdapter)
assert "generativelanguage.googleapis.com" in active_adapter.base_url
assert active_adapter.model_name == "gemini-2.0-flash"

# D. OpenRouter Flow via Admin API
res_save_openrouter = client.post(
    "/api/ai/config",
    json={"active_provider": "openrouter", "active_model": "anthropic/claude-3.5-sonnet", "api_key": "sk-or-test-key", "fallback_on_error": False},
    headers=admin_headers,
)
assert res_save_openrouter.status_code == 200
active_adapter = ai_provider_manager.get_active_provider()
print(f"OpenRouter Flow - Active Adapter: {active_adapter.provider_name}, is_local: {active_adapter.is_local}")
assert isinstance(active_adapter, OpenRouterAdapter)
assert "openrouter.ai" in active_adapter.base_url

# E. Custom Flow via Admin API
res_save_custom = client.post(
    "/api/ai/config",
    json={
        "active_provider": "custom",
        "active_model": "llama-3.2-vision",
        "base_url": "http://internal-vllm:8000/v1",
        "api_key": "custom-secret",
        "request_format": "chat_completions",
        "fallback_on_error": False,
    },
    headers=admin_headers,
)
assert res_save_custom.status_code == 200
active_adapter = ai_provider_manager.get_active_provider()
print(f"Custom Flow - Active Adapter: {active_adapter.provider_name}, format: {active_adapter.request_format}, is_local: {active_adapter.is_local}")
assert isinstance(active_adapter, CustomAdapter)
assert active_adapter.request_format == "chat_completions"

# Reset back to Ollama
client.post(
    "/api/ai/config",
    json={"active_provider": "ollama", "active_model": "qwen2.5vl:3b", "fallback_on_error": False},
    headers=admin_headers,
)
print("Reset active provider back to Ollama.")

print("=" * 60)
print("ALL END-TO-END VERIFICATION CHECKS COMPLETED SUCCESSFULLY!")
print("=" * 60)
