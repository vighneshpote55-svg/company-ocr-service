"""
tests/test_ai_providers.py
Unit and integration tests for AI Model Provider Architecture:
1. No API key selects LocalOllamaProvider.
2. AI_PROVIDER=local selects Qwen.
3. External provider + API key selects external provider.
4. Missing API key falls back to local Qwen.
5. External API failure does NOT silently switch to Qwen unless explicit fallback is enabled.
6. GET /api/ai/config never returns the API key.
7. POST /api/ai/test-connection does not expose secrets.
8. AI_API_KEY is redacted from logs.
9. Provider output normalizes to canonical analysis.
10. AI chat uses selected provider.
11. Local provider works.
12. External provider adapter works with a mocked API.
13. Offline Mode regression tests pass unchanged.
14. Document Vault works regardless of provider.
15. Unknown Document response does not crash.
"""

import io
import json
import logging
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from main import app
import ai_providers
from ai_providers import (
    AIProviderManager,
    LocalOllamaProvider,
    OpenAICompatibleProvider,
    normalize_ai_response,
)
import ai_service
import document_store
import logging_utils


@pytest.fixture(autouse=True)
def reset_provider_env(monkeypatch):
    """Ensure clean provider environment for each test."""
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_FALLBACK_ON_ERROR", raising=False)
    ai_providers.ai_provider_manager.reload_from_env()
    yield
    ai_providers.ai_provider_manager.reload_from_env()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _create_sample_image(text_lines):
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


# 1. No API key selects LocalOllamaProvider
def test_no_api_key_selects_local_ollama_provider():
    mgr = AIProviderManager()
    mgr.update_config(provider="openrouter", api_key="", model="test-model")
    prov = mgr.get_active_provider()
    assert isinstance(prov, LocalOllamaProvider)
    assert prov.provider_name == "ollama"
    assert prov.is_local is True


# 2. AI_PROVIDER=local selects Qwen
def test_ai_provider_local_selects_qwen():
    mgr = AIProviderManager()
    mgr.update_config(provider="local", api_key="secret-key-ignored-when-local", model="qwen2.5vl:3b")
    prov = mgr.get_active_provider()
    assert isinstance(prov, LocalOllamaProvider)
    assert prov.is_local is True
    assert "qwen" in prov.model_name.lower()


# 3. External provider + API key selects external provider
def test_external_provider_with_api_key_selects_external_provider():
    mgr = AIProviderManager()
    mgr.update_config(
        provider="openrouter",
        api_key="sk-or-v1-abcdef1234567890abcdef",
        model="google/gemini-2.5-flash",
        base_url="https://openrouter.ai/api/v1",
    )
    prov = mgr.get_active_provider()
    assert isinstance(prov, OpenAICompatibleProvider)
    assert prov.provider_name == "openrouter"
    assert prov.model_name == "google/gemini-2.5-flash"
    assert prov.is_local is False


# 4. Missing API key falls back to local Qwen
def test_missing_api_key_falls_back_to_local_qwen():
    mgr = AIProviderManager()
    mgr.update_config(provider="openai", api_key=None)
    prov = mgr.get_active_provider()
    assert isinstance(prov, LocalOllamaProvider)
    assert prov.is_local is True


# 5. External API failure does NOT silently switch to Qwen unless explicit fallback is enabled
@pytest.mark.asyncio
async def test_external_api_failure_does_not_silently_fallback():
    mgr = AIProviderManager()
    mgr.update_config(
        provider="openrouter",
        api_key="sk-or-test-key",
        model="test-model",
        fallback_on_error=False,
    )

    with patch.object(
        OpenAICompatibleProvider,
        "analyze_document",
        side_effect=RuntimeError("HTTP 401: Unauthorized API key"),
    ):
        with pytest.raises(RuntimeError) as exc_info:
            await mgr.analyze_document(document_text="Test text", filename="doc.pdf")
        assert "Unauthorized" in str(exc_info.value) or "External provider" in str(exc_info.value)

    # When fallback_on_error is True, it falls back
    mgr.update_config(fallback_on_error=True)
    with patch.object(
        OpenAICompatibleProvider,
        "analyze_document",
        side_effect=RuntimeError("HTTP 500: Outage"),
    ), patch.object(
        LocalOllamaProvider,
        "analyze_document",
        return_value={
            "document_type": "PAN Card",
            "confidence": "high",
            "summary": "Local fallback summary",
            "evidence": ["e1"],
            "reasoning": ["e1"],
            "extracted_fields": {},
            "is_local_ai": True,
            "model_used": "qwen2.5vl:3b",
        },
    ):
        res = await mgr.analyze_document(document_text="Test text", filename="doc.pdf")
        assert res["is_local_ai"] is True


# 6. GET /api/ai/config never returns the API key
def test_get_ai_config_never_returns_api_key(client, monkeypatch):
    secret_key = "sk-super-secret-production-key-999"
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("AI_API_KEY", secret_key)
    monkeypatch.setenv("AI_MODEL", "google/gemini-2.5-flash")
    ai_providers.ai_provider_manager.reload_from_env()

    res = client.get("/api/ai/config")
    assert res.status_code == 200
    data = res.json()

    assert secret_key not in json.dumps(data)
    assert data["api_key_configured"] is True
    assert data["mode"] == "external"
    assert data["active_provider"] == "openrouter"
    assert "api_key" not in data


# 7. POST /api/ai/test-connection does not expose secrets
def test_post_ai_test_connection_does_not_expose_secrets(client):
    secret_key = "sk-test-secret-never-expose"
    res = client.post(
        "/api/ai/test-connection",
        json={
            "provider": "openai",
            "api_key": secret_key,
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert secret_key not in json.dumps(data)
    assert "provider" in data
    assert "model" in data
    assert "success" in data


# 8. AI_API_KEY is redacted from logs
def test_ai_api_key_redacted_from_logs(monkeypatch):
    secret_key = "sk-live-secret-to-be-redacted-888"
    monkeypatch.setenv("AI_API_KEY", secret_key)

    redacted_text = logging_utils.redact_sensitive_text(f"Calling provider with key {secret_key} now")
    assert secret_key not in redacted_text
    assert "[REDACTED_API_KEY]" in redacted_text

    data_payload = {
        "provider": "openrouter",
        "api_key": secret_key,
        "ai_api_key": secret_key,
        "authorization": f"Bearer {secret_key}",
    }
    redacted_dict = logging_utils.redact_data(data_payload)
    assert secret_key not in json.dumps(redacted_dict)


# 9. Provider output normalizes to canonical analysis
def test_provider_output_normalizes_to_canonical_analysis():
    raw_provider_output = {
        "document_type": "incometaxdepartment",
        "confidence": "HIGH",
        "summary": "This is a PAN card.",
        "evidence": ["Contains Income Tax header"],
        "extracted_fields": {
            "pan_number": "ABCDE1234F",
            "name": "Jane Doe",
        },
    }
    pan_text = "INCOME TAX DEPARTMENT PERMANENT ACCOUNT NUMBER ABCDE1234F JANE DOE"
    canonical = normalize_ai_response(
        raw_response=raw_provider_output,
        ocr_text=pan_text,
        filename="pan.png",
        model_name="test-model",
        is_local=False,
    )

    assert canonical["document_type"] == "PAN Card"
    assert canonical["confidence"] == "high"
    assert "pan" in canonical["summary"].lower()
    assert canonical["extracted_fields"]["pan_number"] == "ABCDE1234F"
    assert canonical["is_local_ai"] is False
    assert canonical["model_used"] == "test-model"


# 10. AI chat uses selected provider
@pytest.mark.asyncio
async def test_ai_chat_uses_selected_provider():
    ai_providers.ai_provider_manager.update_config(
        provider="openrouter",
        api_key="sk-valid-key",
        model="gpt-4o-mini",
    )

    with patch.object(
        OpenAICompatibleProvider,
        "chat",
        new_callable=AsyncMock,
        return_value="Answer from OpenAICompatibleProvider",
    ) as mock_ext_chat:
        reply = await ai_service.chat_with_document(
            document_text="Sample text content for query verification.",
            filename="sample.pdf",
            message="What is the general context of this document?",
        )
        assert reply == "Answer from OpenAICompatibleProvider"
        assert mock_ext_chat.called


# 11. Local provider works
@pytest.mark.asyncio
async def test_local_provider_analyze_and_chat():
    prov = LocalOllamaProvider(model_name="qwen2.5vl:3b")
    assert prov.provider_name == "ollama"
    assert prov.is_local is True

    with patch(
        "ollama_ai.analyze_document",
        return_value={
            "document_type": "PAN Card",
            "confidence": "high",
            "summary": "Local analysis summary",
            "evidence": ["ev1"],
            "reasoning": ["ev1"],
            "extracted_fields": {"pan_number": "ABCDE1234F"},
        },
    ):
        res = await prov.analyze_document(document_text="INCOME TAX DEPARTMENT ABCDE1234F")
        assert res["document_type"] == "PAN Card"
        assert res["is_local_ai"] is True

    with patch(
        "ollama_ai.chat_with_document",
        return_value="Local Ollama reply",
    ):
        reply = await prov.chat(
            document_text="Context text",
            filename="pan.png",
            message="Test question",
        )
        assert reply == "Local Ollama reply"


# 12. External provider adapter works with a mocked API
@pytest.mark.asyncio
async def test_external_provider_adapter_mocked_api():
    prov = OpenAICompatibleProvider(
        provider_name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="sk-test-key",
        model_name="google/gemini-2.5-flash",
    )

    fake_response = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "document_type": "GST Registration Certificate",
                        "confidence": "high",
                        "summary": "Mocked external analysis summary",
                        "evidence": ["GST REG-06 token"],
                        "extracted_fields": {"gstin": "27AAAAA0000A1Z5"},
                    })
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await prov.analyze_document(
            document_text="GOVERNMENT OF INDIA FORM GST REG-06 27AAAAA0000A1Z5",
            filename="gst.pdf",
        )
        assert res["document_type"] == "GST Registration Certificate"
        assert res["extracted_fields"]["gstin"] == "27AAAAA0000A1Z5"
        assert res["is_local_ai"] is False


# 13. Offline Mode regression tests pass unchanged
def test_offline_mode_regression_remains_unchanged(client):
    buf = _create_sample_image([
        "INCOME TAX DEPARTMENT",
        "PERMANENT ACCOUNT NUMBER",
        "ABCDE1234F",
        "RAMESH SHARMA",
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


# 14. Document Vault works regardless of provider
def test_document_vault_works_regardless_of_provider(client):
    res = client.get("/api/documents")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# 15. Unknown Document response does not crash
@pytest.mark.asyncio
async def test_unknown_document_does_not_crash():
    res = await ai_service.analyze_document("This is completely arbitrary text with no markers.")
    assert "document_type" in res
    assert "confidence" in res
    assert "summary" in res
    assert "extracted_fields" in res


def test_openrouter_url_and_model_normalization(client, monkeypatch):
    """
    OpenRouter configuration must:
    - Normalize base_url to https://openrouter.ai/api/v1
    - Strip fragments such as #providers
    - Not interpret model webpage URL as API endpoint
    - Normalize model ID to nvidia/nemotron-3-ultra-550b-a55b:free
    """
    ai_providers.ai_provider_manager.update_config(
        provider="openrouter",
        api_key="sk-or-v1-test-key",
        model="NVIDIA: Nemotron 3 Ultra (free)",
        base_url="https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free#providers",
    )

    cfg = ai_providers.ai_provider_manager.get_safe_config()
    assert cfg["mode"] == "external"
    assert cfg["active_provider"] == "openrouter"
    assert cfg["active_model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert cfg["base_url"] == "https://openrouter.ai/api/v1"
    assert "#providers" not in cfg["base_url"]

    # Also test via POST /api/ai/config endpoint
    res = client.post("/api/ai/config", json={
        "provider": "openrouter",
        "api_key": "sk-or-v1-test-key-2",
        "model": "https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free#providers",
        "base_url": "https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free#providers",
    })
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["mode"] == "external"
    assert res_data["active_provider"] == "openrouter"
    assert res_data["active_model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert res_data["base_url"] == "https://openrouter.ai/api/v1"
