"""
ai_providers.py
Modular, extensible AI model provider architecture for AI Mode in company-ocr-service.

Supports:
1. LocalOllamaProvider:
   - Uses local Ollama server (isolated in internal Docker network).
   - Default model: qwen2.5vl:3b.
   - Multimodal document analysis (renders first page of PDF / image + RapidOCR text).
   - Serves as the mandatory automatic fallback when no external provider/API key is configured.

2. OpenAICompatibleProvider:
   - Supports configurable provider name, base URL, API key, and model.
   - Works with OpenAI, OpenRouter, Google Gemini (via OpenAI-compatible endpoint),
     vLLM, or custom local/cloud endpoints.
   - Multimodal image/document payloads when supported, OCR text otherwise.
   - No API keys or secrets are ever exposed or logged.

3. AIProviderManager:
   - Deterministic provider selection:
     IF valid external provider configured AND API key is present -> External provider
     ELSE (no external provider or missing API key) -> LocalOllamaProvider (qwen2.5vl:3b).
   - External errors do NOT silently fall back to Qwen unless explicit fallback_on_error is enabled.
   - Provider response normalization produces the exact canonical AI analysis object.
"""

import asyncio
from abc import ABC, abstractmethod
import base64
import json
import logging
import mimetypes
import os
import re
import time
from typing import Any, Dict, List, Optional

import httpx

import logging_utils
import ollama_ai

logger = logging_utils.get_logger("company_server_ocr.ai_providers")

# Standard defaults
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LOCAL_MODEL = "qwen2.5vl:3b"
DEFAULT_EXTERNAL_MODEL = "google/gemini-2.5-flash"


def clean_json_response(raw_text: str) -> str:
    """Extract JSON block from model output handling markdown code blocks or surrounding text."""
    text = (raw_text or "").strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()
    return text


def normalize_openrouter_endpoint_and_model(
    provider: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
) -> tuple[str, str, str]:
    """
    Validates and normalizes OpenRouter and external provider configuration:
    - If provider is openrouter (or base_url is from openrouter.ai):
      * Normalizes base_url to https://openrouter.ai/api/v1
      * Strips fragments such as #providers
      * Does not interpret model webpage URL as API endpoint
      * Normalizes model ID (e.g. 'nvidia/nemotron-3-ultra-550b-a55b:free')
    - If base_url ends with /chat/completions, strips it.
    """
    prov = (provider or "").lower().strip()
    clean_model = (model or "").strip()
    clean_url = (base_url or "").strip()

    # Strip fragments like #providers
    if "#" in clean_url:
        clean_url = clean_url.split("#")[0].strip()
    if "#" in clean_model:
        clean_model = clean_model.split("#")[0].strip()

    is_openrouter = prov in ("openrouter", "open_router") or "openrouter.ai" in clean_url.lower()

    if is_openrouter:
        # Check if clean_url contains a model slug or webpage path
        if "openrouter.ai" in clean_url.lower():
            # e.g. https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free
            m_match = re.search(r"openrouter\.ai/(?!api/v1)([^/?#]+/[^/?#]+)", clean_url, re.IGNORECASE)
            if m_match and (not clean_model or clean_model == DEFAULT_EXTERNAL_MODEL or "nemotron" in m_match.group(1).lower()):
                clean_model = m_match.group(1).strip()

            clean_url = DEFAULT_OPENROUTER_BASE_URL
        elif not clean_url:
            clean_url = DEFAULT_OPENROUTER_BASE_URL

        # Check if user entered URL as model
        if "openrouter.ai/" in clean_model.lower():
            m_slug = re.search(r"openrouter\.ai/(?:models/)?([^/?#]+/[^/?#]+)", clean_model, re.IGNORECASE)
            if m_slug:
                clean_model = m_slug.group(1).strip()

        # Handle display names such as "NVIDIA: Nemotron 3 Ultra (free)"
        display_lower = clean_model.lower()
        if "nemotron" in display_lower and ("ultra" in display_lower or "nvidia" in display_lower):
            clean_model = "nvidia/nemotron-3-ultra-550b-a55b:free"
        elif not clean_model:
            clean_model = "nvidia/nemotron-3-ultra-550b-a55b:free"

    else:
        clean_url = clean_url.rstrip("/")
        if clean_url.endswith("/chat/completions"):
            clean_url = clean_url[:-len("/chat/completions")].rstrip("/")

    return prov, clean_model, clean_url


def normalize_ai_response(
    raw_response: Dict[str, Any],
    ocr_text: str = "",
    filename: str = "document",
    model_name: str = "",
    is_local: bool = True,
    duration: float = 0.0,
) -> Dict[str, Any]:
    """
    Canonical response normalizer:
    Ensures all providers return the exact canonical AI analysis object expected by:
    - AIAnalysisCard
    - AISummaryCard
    - AIKeyFindingsCard
    - AIQuickActions
    - AIChatPanel
    - ExtractedFields
    - Document Vault
    """
    import ai_service
    import verifier

    combined_text = ((ocr_text or "") + "\n" + str(raw_response.get("summary", ""))).strip()
    canonical_cls = verifier.classify_document_content(combined_text)

    if canonical_cls.get("doc_type") != "unknown":
        normalized_type = canonical_cls["document_type"]
        confidence = canonical_cls.get("confidence", "high")
        evidence = list(canonical_cls.get("evidence", []))
    else:
        raw_doc_type = raw_response.get("document_type") or "Unknown Document"
        normalized_type = ollama_ai.normalize_document_type(raw_doc_type, text_content=ocr_text)
        conf_raw = str(raw_response.get("confidence", "low")).lower().strip()
        confidence = conf_raw if conf_raw in ("high", "medium", "low") else ("high" if normalized_type != "Unknown Document" else "low")
        evidence = raw_response.get("evidence") or raw_response.get("reasoning") or []
        if isinstance(evidence, str):
            evidence = [evidence]

    if not evidence:
        if normalized_type != "Unknown Document":
            evidence = [
                f"Document structure matches {normalized_type}",
                f"Contains verified text tokens and layout features",
            ]
        else:
            evidence = [
                "No standard institutional headings or classification markers recognized",
                "Visible text lacks defining structural fields of supported document classes",
            ]

    # Summarize
    summary = raw_response.get("summary")
    if not summary or len(summary.strip()) < 10:
        if normalized_type != "Unknown Document":
            summary = f"This document was analyzed and identified as a {normalized_type}."
        else:
            summary = "This document could not be reliably classified into a recognized document type based on its visible content."

    # Extract & Merge verified canonical fields
    canonical_info = ai_service.classify_document_content(ocr_text, filename=filename)
    canonical_fields = canonical_info.get("extracted_fields") or {}
    merged_fields = dict(canonical_fields)

    raw_extracted = raw_response.get("extracted_fields") or {}
    if isinstance(raw_extracted, dict):
        cleaned_raw = ollama_ai._normalize_extracted_fields(raw_extracted)
        for k, v in cleaned_raw.items():
            if v and str(v).strip() and str(v).strip().lower() != "none" and (k not in merged_fields or not merged_fields[k]):
                merged_fields[k] = v

    return {
        "document_type": normalized_type,
        "confidence": confidence,
        "summary": summary,
        "evidence": evidence,
        "reasoning": evidence,
        "extracted_fields": merged_fields,
        "processing_time_seconds": round(duration, 2),
        "model_used": model_name or raw_response.get("model_used") or "ai_model",
        "is_local_ai": is_local,
    }


# ==============================================================================
# Common Provider Interface
# ==============================================================================

class BaseAIProvider(ABC):
    """Abstract Base Class defining standard AI provider interface."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g. 'ollama', 'openrouter', 'openai', 'gemini')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Active model identifier."""
        pass

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Whether this provider runs completely locally without external cloud calls."""
        pass

    @abstractmethod
    async def analyze_document(
        self,
        document_text: str,
        file_path: Optional[str] = None,
        filename: str = "document",
    ) -> Dict[str, Any]:
        """Perform document classification, reasoning, and structured field extraction."""
        pass

    @abstractmethod
    async def chat(
        self,
        document_text: str,
        filename: str,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        stored_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Perform contextual conversational QA grounded in the current document."""
        pass

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """Verify endpoint connectivity and model availability without exposing secrets."""
        pass


# ==============================================================================
# 1. Local Ollama Provider (Qwen2.5-VL 3B)
# ==============================================================================

class LocalOllamaProvider(BaseAIProvider):
    """
    Provider adapter for private local Ollama instance (Qwen2.5-VL:3B).
    Guarantees zero external network access and preserves existing multimodal behavior.
    """

    def __init__(self, model_name: Optional[str] = None):
        self._model = model_name or ollama_ai.get_ollama_model() or DEFAULT_LOCAL_MODEL

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_local(self) -> bool:
        return True

    async def analyze_document(
        self,
        document_text: str,
        file_path: Optional[str] = None,
        filename: str = "document",
    ) -> Dict[str, Any]:
        t0 = time.time()
        # ollama_ai.analyze_document is synchronous, run in executor to avoid blocking event loop
        loop = asyncio.get_running_loop()
        raw_res = await loop.run_in_executor(
            None,
            lambda: ollama_ai.analyze_document(
                file_path=file_path or "",
                filename=filename,
                ocr_text=document_text,
            ),
        )

        if "error" in raw_res and not raw_res.get("document_type"):
            err_msg = raw_res.get("error", "Local Ollama server is unavailable.")
            raise RuntimeError(f"Local AI Provider (Ollama) error: {err_msg}")

        duration = time.time() - t0
        return normalize_ai_response(
            raw_response=raw_res,
            ocr_text=document_text,
            filename=filename,
            model_name=self.model_name,
            is_local=True,
            duration=duration,
        )

    async def chat(
        self,
        document_text: str,
        filename: str,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        stored_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(
            None,
            lambda: ollama_ai.chat_with_document(
                document_context=document_text,
                filename=filename,
                message=message,
                history=history,
                stored_analysis=stored_analysis,
            ),
        )
        return reply

    async def test_connection(self) -> Dict[str, Any]:
        t0 = time.time()
        health = ollama_ai.check_ollama_health()
        latency_ms = round((time.time() - t0) * 1000)

        reachable = health.get("reachable", False)
        installed = health.get("model_installed", False)
        success = reachable and installed

        if success:
            msg = f"Local Ollama server connected • Model '{self.model_name}' is ready ({latency_ms}ms latency)."
        elif reachable:
            msg = health.get("error") or f"Ollama is reachable, but model '{self.model_name}' is not installed."
        else:
            msg = health.get("error") or "Local Ollama server is not running."

        return {
            "success": success,
            "provider": "ollama",
            "model": self.model_name,
            "message": msg,
            "latency_ms": latency_ms,
        }


# ==============================================================================
# 2. OpenAI Compatible Provider (OpenAI, OpenRouter, Gemini, Custom vLLM)
# ==============================================================================

class OpenAICompatibleProvider(BaseAIProvider):
    """
    Provider adapter for external OpenAI-compatible chat completion APIs.
    Supports OpenRouter, OpenAI, Google Gemini, and custom local/cloud endpoints.
    Never logs or leaks API keys.
    """

    def __init__(
        self,
        provider_name: str,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout: float = 60.0,
    ):
        norm_prov, norm_model, norm_url = normalize_openrouter_endpoint_and_model(
            provider_name, model_name, base_url
        )
        self._provider = norm_prov or "external"
        self._base_url = norm_url or (
            DEFAULT_OPENAI_BASE_URL if self._provider == "openai" else DEFAULT_OPENROUTER_BASE_URL
        )
        self._api_key = (api_key or "").strip()
        self._model = norm_model or (
            "gpt-4o-mini" if self._provider == "openai" else DEFAULT_EXTERNAL_MODEL
        )
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return self._provider

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_local(self) -> bool:
        return False

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter.ai" in self._base_url:
            headers["HTTP-Referer"] = "https://company-ocr.internal"
            headers["X-Title"] = "Company OCR Service"
        return headers

    def _prepare_image_payload(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Encode image or first page of PDF as base64 data URL for vision models."""
        try:
            if not file_path or not os.path.exists(file_path):
                return None
            img_path = ollama_ai._ensure_image_format(file_path)
            if not os.path.exists(img_path):
                return None

            mime, _ = mimetypes.guess_type(img_path)
            mime = mime or "image/png"

            with open(img_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")

            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64_data}",
                },
            }
        except Exception as ex:
            logger.warning("Could not encode image for external vision provider: %s", ex)
            return None

    async def analyze_document(
        self,
        document_text: str,
        file_path: Optional[str] = None,
        filename: str = "document",
    ) -> Dict[str, Any]:
        t0 = time.time()
        logging_utils.log_event(
            logger,
            logging.INFO,
            event="ai_started",
            provider=self.provider_name,
            model=self.model_name,
            operation="analyze_document",
        )

        system_prompt = (
            "You are an expert document understanding AI. Analyze the uploaded document's extracted text and image.\n"
            "Classify it into its true canonical document type (e.g. 'GST Registration Certificate', 'PAN Card', 'Aadhaar Card', "
            "'Income Tax Notice', 'Employment Contract', 'Bank Statement', 'Commercial Invoice', 'Salary Slip', or 'Unknown Document').\n"
            "CRITICAL RULES:\n"
            "- NEVER use the filename or raw text fragments like 'Incometaxdepartment' as the document type.\n"
            "- If the document is a GST Registration Certificate, classify it as 'GST Registration Certificate'.\n"
            "- If the document is a PAN Card, classify it as 'PAN Card'.\n"
            "- If the document is an Aadhaar Card, classify it as 'Aadhaar Card'.\n"
            "- If the document is an Income Tax Department notice, classify it as 'Income Tax Notice'.\n"
            "- NEVER hallucinate fields. Only extract factual values present in the document.\n"
            "- Respond ONLY with a valid JSON object matching:\n"
            "{\n"
            '  "document_type": "string",\n'
            '  "confidence": "high" | "medium" | "low",\n'
            '  "summary": "1-2 sentence factual executive summary of the document and its actual contents.",\n'
            '  "evidence": [\n'
            '    "Factual evidence point 1 from document",\n'
            '    "Factual evidence point 2 from document",\n'
            '    "Factual evidence point 3 from document"\n'
            '  ],\n'
            '  "extracted_fields": {\n'
            '    "field_name": "field_value"\n'
            '  }\n'
            "}\n"
        )

        user_text = f"Document Filename: {filename}\n\nExtracted Text:\n---\n{(document_text or '')[:12000]}\n---"
        user_content: Any = user_text

        # Multimodal image support
        if file_path:
            img_payload = self._prepare_image_payload(file_path)
            if img_payload:
                user_content = [
                    {"type": "text", "text": user_text},
                    img_payload,
                ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        endpoint = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1500,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.post(endpoint, headers=self._get_headers(), json=payload)
                if res.status_code != 200:
                    safe_err = res.text[:200].replace(self._api_key, "[REDACTED_API_KEY]")
                    raise RuntimeError(f"HTTP {res.status_code}: {safe_err}")

                data = res.json()
                raw_reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                cleaned = clean_json_response(raw_reply)
                parsed = json.loads(cleaned)

                duration = time.time() - t0
                logging_utils.log_event(
                    logger,
                    logging.INFO,
                    event="ai_completed",
                    provider=self.provider_name,
                    model=self.model_name,
                    duration_ms=round(duration * 1000, 2),
                    status="success",
                    operation="analyze_document",
                )

                return normalize_ai_response(
                    raw_response=parsed,
                    ocr_text=document_text,
                    filename=filename,
                    model_name=self.model_name,
                    is_local=False,
                    duration=duration,
                )
        except Exception as ex:
            duration = time.time() - t0
            logging_utils.log_event(
                logger,
                logging.ERROR,
                event="ai_failed",
                provider=self.provider_name,
                model=self.model_name,
                duration_ms=round(duration * 1000, 2),
                error_code="EXTERNAL_PROVIDER_ERROR",
                status="error",
                operation="analyze_document",
            )
            safe_ex_str = str(ex).replace(self._api_key, "[REDACTED_API_KEY]")
            raise RuntimeError(f"External provider '{self.provider_name}' error during analyze_document: {safe_ex_str}")

    async def chat(
        self,
        document_text: str,
        filename: str,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        stored_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        doc_type = (stored_analysis or {}).get("document_type") or "Document"
        extracted = (stored_analysis or {}).get("extracted_fields") or {}

        system_prompt = (
            f"You are an AI Document Assistant analyzing the document '{filename}'.\n"
            f"Document Type: {doc_type}\n"
            f"Extracted Document Text:\n---\n{(document_text or '')[:12000]}\n---\n\n"
            f"Verified Stored Fields:\n{json.dumps(extracted, indent=2)}\n\n"
            "CRITICAL GROUNDING RULES:\n"
            "1. Answer only from the provided document text and verified fields above.\n"
            "2. Use OCR text and extracted fields as primary evidence.\n"
            "3. Do not invent values, assume, or hallucinate facts, numbers, dates, or names.\n"
            "4. If information is absent, explicitly say it was not found (e.g. 'I could not find [field name] in this document.').\n"
            "5. Never use previous conversation unless it refers to the current document.\n"
            "6. Do not expose chain-of-thought, internal reasoning, or thinking tags.\n"
            "7. Return concise grounded answers.\n"
            "8. NEVER output raw OCR placeholder artifacts or label fragments such as '***/Name', 'Name', or fake values.\n"
            "9. Never substitute Bank Name or Branch when asked for IFSC.\n"
            "10. Never substitute Account Number when asked for Customer Number, or GSTIN when asked for PAN.\n"
            "11. Never output Python dictionary syntax for dates or statement periods.\n"
            "12. Maintain a concise, direct, helpful, and professional tone."
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            for turn in history[-6:]:
                r = turn.get("role")
                c = turn.get("content")
                if r in ("user", "assistant") and c:
                    messages.append({"role": r, "content": str(c)})
        messages.append({"role": "user", "content": message.strip()})

        endpoint = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1000,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.post(endpoint, headers=self._get_headers(), json=payload)
                if res.status_code != 200:
                    safe_err = res.text[:200].replace(self._api_key, "[REDACTED_API_KEY]")
                    raise RuntimeError(f"HTTP {res.status_code}: {safe_err}")

                data = res.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                reply = reply.replace("***/Name", "the cardholder's name").replace("*/Name", "")
                return reply
        except Exception as ex:
            safe_ex_str = str(ex).replace(self._api_key, "[REDACTED_API_KEY]")
            raise RuntimeError(f"External provider '{self.provider_name}' error during chat: {safe_ex_str}")

    async def test_connection(self) -> Dict[str, Any]:
        t0 = time.time()
        # Test endpoint by sending a minimal 5-token ping
        endpoint = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(endpoint, headers=self._get_headers(), json=payload)
                latency_ms = round((time.time() - t0) * 1000)

                if res.status_code == 200:
                    return {
                        "success": True,
                        "provider": self.provider_name,
                        "model": self.model_name,
                        "message": f"Connected successfully to {self.provider_name} • Model '{self.model_name}' ({latency_ms}ms latency).",
                        "latency_ms": latency_ms,
                    }
                else:
                    safe_err = res.text[:150].replace(self._api_key, "[REDACTED_API_KEY]")
                    return {
                        "success": False,
                        "provider": self.provider_name,
                        "model": self.model_name,
                        "message": f"Connection failed (HTTP {res.status_code}): {safe_err}",
                        "latency_ms": latency_ms,
                    }
        except Exception as ex:
            latency_ms = round((time.time() - t0) * 1000)
            safe_err = str(ex).replace(self._api_key, "[REDACTED_API_KEY]")
            return {
                "success": False,
                "provider": self.provider_name,
                "model": self.model_name,
                "message": f"Connection error: {safe_err}",
                "latency_ms": latency_ms,
            }


# ==============================================================================
# 3. Deterministic AI Provider Manager
# ==============================================================================

class AIProviderManager:
    """
    Manager singleton responsible for:
    - Loading provider configuration from environment and runtime settings.
    - Deterministic provider selection:
      * Valid external provider + valid API key -> OpenAICompatibleProvider
      * Unconfigured external provider / missing API key -> LocalOllamaProvider (qwen2.5vl:3b)
    - Protecting API key secrets.
    - Preventing silent fallback on external runtime errors unless explicitly configured.
    """

    def __init__(self):
        self._provider: Optional[str] = None
        self._api_key: Optional[str] = None
        self._model: Optional[str] = None
        self._base_url: Optional[str] = None
        self._fallback_on_error: Optional[bool] = None

    @property
    def current_provider(self) -> str:
        if self._provider is not None:
            return self._provider
        return os.getenv("AI_PROVIDER", "local").lower().strip()

    @property
    def current_api_key(self) -> str:
        if self._api_key is not None:
            return self._api_key
        return (
            os.getenv("AI_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or ""
        ).strip()

    @property
    def current_model(self) -> str:
        raw = self._model if self._model is not None else os.getenv("AI_MODEL", "").strip()
        p = self.current_provider
        u = self._base_url if self._base_url is not None else os.getenv("AI_BASE_URL", "").strip()
        _, norm_model, _ = normalize_openrouter_endpoint_and_model(p, raw, u)
        return norm_model

    @property
    def current_base_url(self) -> str:
        raw = self._base_url if self._base_url is not None else os.getenv("AI_BASE_URL", "").strip()
        p = self.current_provider
        m = self._model if self._model is not None else os.getenv("AI_MODEL", "").strip()
        _, _, norm_url = normalize_openrouter_endpoint_and_model(p, m, raw)
        return norm_url

    @property
    def current_fallback_on_error(self) -> bool:
        if self._fallback_on_error is not None:
            return self._fallback_on_error
        return os.getenv("AI_FALLBACK_ON_ERROR", "false").lower() in ("true", "1", "yes")

    def reload_from_env(self) -> None:
        """Reload configuration from environment variables."""
        self._provider = None
        self._api_key = None
        self._model = None
        self._base_url = None
        self._fallback_on_error = None

    def update_config(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        fallback_on_error: Optional[bool] = None,
    ) -> None:
        """Update runtime provider configuration securely."""
        if provider is not None:
            self._provider = provider.lower().strip()
        if api_key is not None:
            self._api_key = api_key.strip()

        target_p = self._provider or os.getenv("AI_PROVIDER", "local")
        target_m = model if model is not None else (self._model or os.getenv("AI_MODEL", ""))
        target_u = base_url if base_url is not None else (self._base_url or os.getenv("AI_BASE_URL", ""))

        norm_p, norm_m, norm_u = normalize_openrouter_endpoint_and_model(target_p, target_m, target_u)

        if model is not None or norm_m != target_m:
            self._model = norm_m
        if base_url is not None or norm_u != target_u:
            self._base_url = norm_u
        if fallback_on_error is not None:
            self._fallback_on_error = bool(fallback_on_error)

    def get_effective_base_url(self, provider_name: str) -> str:
        base_url = self.current_base_url
        if base_url:
            return base_url
        if provider_name == "openai":
            return DEFAULT_OPENAI_BASE_URL
        return DEFAULT_OPENROUTER_BASE_URL

    def get_effective_model(self, provider_name: str) -> str:
        model = self.current_model
        if model:
            return model
        if provider_name == "local" or provider_name == "ollama":
            return DEFAULT_LOCAL_MODEL
        elif provider_name == "openai":
            return "gpt-4o-mini"
        elif provider_name in ("openrouter", "open_router"):
            return "nvidia/nemotron-3-ultra-550b-a55b:free"
        return DEFAULT_EXTERNAL_MODEL

    def get_active_provider(self) -> BaseAIProvider:
        """
        Deterministic provider selection:
        IF:
          - A valid external provider is configured
          - AND API key is present
        THEN:
          - Use configured OpenAICompatibleProvider
        ELSE IF:
          - No external provider OR API key is missing OR provider == 'local'
        THEN:
          - Mandatory fallback to LocalOllamaProvider (qwen2.5vl:3b)
        """
        p = self.current_provider
        api_key = self.current_api_key
        has_key = bool(api_key)

        if p and p != "local" and has_key:
            return OpenAICompatibleProvider(
                provider_name=p,
                base_url=self.get_effective_base_url(p),
                api_key=api_key,
                model_name=self.get_effective_model(p),
            )
        else:
            return LocalOllamaProvider(model_name=self.get_effective_model("local"))

    def get_safe_config(self) -> Dict[str, Any]:
        """
        Return public safe configuration without exposing any API keys or secrets.
        """
        provider = self.get_active_provider()
        ollama_health = ollama_ai.check_ollama_health()
        is_external = not provider.is_local

        return {
            "active_provider": provider.provider_name,
            "active_model": provider.model_name,
            "mode": "external" if is_external else "local",
            "api_key_configured": bool(self.current_api_key),
            "base_url": provider.base_url if is_external else "",
            "ollama_available": ollama_health.get("reachable", False) and ollama_health.get("model_installed", False),
            "local_fallback_available": True,
            "fallback_on_error": self.current_fallback_on_error,
        }

    async def test_connection(self, candidate_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Test candidate or currently active provider connection without exposing secrets."""
        if candidate_config:
            p = (candidate_config.get("provider") or "local").lower().strip()
            raw_key = candidate_config.get("api_key")
            key = (raw_key if raw_key is not None else (self._api_key if p == self._provider else "")).strip()
            raw_model = (candidate_config.get("model") or self.get_effective_model(p)).strip()
            raw_url = (candidate_config.get("base_url") or self.get_effective_base_url(p)).strip()

            norm_p, norm_m, norm_u = normalize_openrouter_endpoint_and_model(p, raw_model, raw_url)

            if norm_p != "local" and key:
                test_prov = OpenAICompatibleProvider(
                    provider_name=norm_p,
                    base_url=norm_u,
                    api_key=key,
                    model_name=norm_m,
                )
                return await test_prov.test_connection()
            else:
                test_prov = LocalOllamaProvider(model_name=norm_m if norm_p == "local" else DEFAULT_LOCAL_MODEL)
                return await test_prov.test_connection()

        provider = self.get_active_provider()
        return await provider.test_connection()

    async def analyze_document(
        self,
        document_text: str,
        file_path: Optional[str] = None,
        filename: str = "document",
    ) -> Dict[str, Any]:
        """Route document analysis to the deterministically selected provider."""
        provider = self.get_active_provider()
        try:
            return await provider.analyze_document(
                document_text=document_text,
                file_path=file_path,
                filename=filename,
            )
        except Exception as ex:
            if not provider.is_local and self._fallback_on_error:
                logger.warning(
                    "External provider '%s' failed: %s; explicit fallback to local Ollama enabled",
                    provider.provider_name,
                    ex,
                )
                local_fallback = LocalOllamaProvider(model_name=DEFAULT_LOCAL_MODEL)
                return await local_fallback.analyze_document(
                    document_text=document_text,
                    file_path=file_path,
                    filename=filename,
                )
            raise

    async def chat(
        self,
        document_text: str,
        filename: str,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        stored_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Route document chat to the deterministically selected provider."""
        provider = self.get_active_provider()
        try:
            return await provider.chat(
                document_text=document_text,
                filename=filename,
                message=message,
                history=history,
                stored_analysis=stored_analysis,
            )
        except Exception as ex:
            if not provider.is_local and self._fallback_on_error:
                logger.warning(
                    "External provider '%s' failed during chat: %s; explicit fallback to local Ollama enabled",
                    provider.provider_name,
                    ex,
                )
                local_fallback = LocalOllamaProvider(model_name=DEFAULT_LOCAL_MODEL)
                return await local_fallback.chat(
                    document_text=document_text,
                    filename=filename,
                    message=message,
                    history=history,
                    stored_analysis=stored_analysis,
                )
            raise


# Global singleton instance
ai_provider_manager = AIProviderManager()
