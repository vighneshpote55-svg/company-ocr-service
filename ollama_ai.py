"""
ollama_ai.py
Local Ollama AI Mode integration using Qwen2.5-VL:3B for document understanding
and structured field extraction.
- Completely local and air-gapped; no external cloud API or keys required.
- Connects to the local Ollama server (default: http://127.0.0.1:11434).
- Model: qwen2.5vl:3b
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from PIL import Image

try:
    import ollama
except ImportError:
    ollama = None

logger = logging.getLogger("company_server_ocr.ollama_ai")

DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b")


def get_client() -> Any:
    """Return an Ollama client pointing to the configured host."""
    if ollama is None:
        raise RuntimeError("The 'ollama' Python package is not installed.")
    return ollama.Client(host=DEFAULT_OLLAMA_HOST)


def check_ollama_health() -> Dict[str, Any]:
    """
    Verify if the Ollama server is reachable and if qwen2.5vl:3b is installed.
    Returns status dictionary for health checks and debugging.
    """
    if ollama is None:
        return {
            "reachable": False,
            "model_installed": False,
            "model": DEFAULT_MODEL,
            "error": "The 'ollama' Python package is not installed.",
        }

    try:
        client = get_client()
        models_response = client.list()
        installed_models = []
        raw_list = models_response.get("models", []) if isinstance(models_response, dict) else getattr(models_response, "models", [])
        for m in raw_list:
            name = m.get("model", "") if isinstance(m, dict) else getattr(m, "model", "")
            if not name:
                name = m.get("name", "") if isinstance(m, dict) else getattr(m, "name", "")
            installed_models.append(name.lower())

        target_model = DEFAULT_MODEL.lower()
        # Accept exact match or prefix match (e.g. qwen2.5vl:3b or qwen2.5vl:latest)
        model_found = any(
            target_model in m or m.startswith(target_model.split(":")[0])
            for m in installed_models
        )

        if not model_found:
            return {
                "reachable": True,
                "model_installed": False,
                "model": DEFAULT_MODEL,
                "installed_models": installed_models,
                "error": f"Model '{DEFAULT_MODEL}' is missing. Please run: ollama pull {DEFAULT_MODEL}",
            }

        return {
            "reachable": True,
            "model_installed": True,
            "model": DEFAULT_MODEL,
            "installed_models": installed_models,
            "message": f"Ollama server is running and {DEFAULT_MODEL} is ready.",
        }
    except Exception as ex:
        err_msg = str(ex).lower()
        if "connection refused" in err_msg or "failed to connect" in err_msg or "connecterror" in err_msg:
            return {
                "reachable": False,
                "model_installed": False,
                "model": DEFAULT_MODEL,
                "error": "Ollama server is not running.",
            }
        return {
            "reachable": False,
            "model_installed": False,
            "model": DEFAULT_MODEL,
            "error": f"Ollama health check error: {str(ex)}",
        }


def _ensure_image_format(image_path: str) -> str:
    """
    If the file is a PDF, render its first page to an image.
    If it's already an image, return its path.
    """
    ext = os.path.splitext(image_path)[1].lower()
    if ext != ".pdf":
        return image_path

    # Convert first page of PDF to image
    rendered_image_path = f"{image_path}_page1.png"
    if os.path.exists(rendered_image_path):
        return rendered_image_path

    try:
        from ocr_engine import render_pdf_pages_to_images
        imgs = render_pdf_pages_to_images(image_path, max_pages=1, dpi=150)
        if imgs and len(imgs) > 0:
            imgs[0].save(rendered_image_path, "PNG")
            return rendered_image_path
    except Exception as ex:
        logger.warning("Could not render PDF page via render_pdf_pages_to_images: %s", ex)

    # Fallback to PyMuPDF if available
    try:
        import fitz
        doc = fitz.open(image_path)
        if len(doc) > 0:
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            pix.save(rendered_image_path)
            doc.close()
            return rendered_image_path
    except Exception as ex:
        logger.warning("Could not render PDF with PyMuPDF: %s", ex)

    raise ValueError(f"Unable to render PDF document '{image_path}' to image for vision processing.")


def _clean_json_response(raw_text: str) -> str:
    """Clean markdown code fences or surrounding text to isolate JSON object."""
    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]
    return text


def _normalize_extracted_fields(raw_fields: Any) -> Dict[str, Any]:
    """Normalize extracted fields into clean key-value dictionary."""
    if not isinstance(raw_fields, dict):
        return {"raw_content": str(raw_fields)}

    # Check for paired pattern: {"field_name_1": "PAN", "field_value_1": "123", ...}
    has_paired_keys = any(k.startswith("field_name_") for k in raw_fields)
    if has_paired_keys:
        normalized: Dict[str, Any] = {}
        idx = 1
        while True:
            name_key = f"field_name_{idx}"
            val_key = f"field_value_{idx}"
            if name_key in raw_fields:
                field_name = str(raw_fields[name_key]).strip()
                field_val = raw_fields.get(val_key, "")
                if field_name:
                    normalized[field_name] = field_val
                idx += 1
            else:
                break
        if normalized:
            return normalized

    # Clean standard dict
    clean_dict = {}
    for k, v in raw_fields.items():
        if isinstance(v, (str, int, float, bool, list, dict)):
            clean_dict[str(k).strip()] = v
        else:
            clean_dict[str(k).strip()] = str(v)
    return clean_dict


def analyze_document(file_path: str, filename: str = "") -> Dict[str, Any]:
    """
    Analyze document with local Ollama + Qwen2.5-VL:3B:
    - Extracts every visible field as structured key-value pairs
    - Classifies document type
    - Assesses confidence
    - Produces an executive summary and reasoning points
    - Returns structured JSON
    """
    logger.info("AI Mode selected")

    # 1. Health check & verification
    health = check_ollama_health()
    if not health.get("reachable"):
        return {"error": "Ollama server is not running."}
    if not health.get("model_installed"):
        return {"error": health.get("error", f"Model '{DEFAULT_MODEL}' is missing. Please run: ollama pull {DEFAULT_MODEL}")}

    # 2. Convert to vision-supported image if PDF
    image_to_send = _ensure_image_format(file_path)

    logger.info("Sending image to Ollama: %s", image_to_send)
    t0 = time.time()

    prompt = (
        "You are an expert document understanding AI. Analyze the uploaded document image carefully.\n"
        "Extract every single visible field, identifier, name, date, amount, organization, and attribute into structured data.\n"
        "Respond ONLY with a valid JSON object matching this exact schema:\n"
        "{\n"
        '  "document_type": "string (e.g. Employment Contract, PAN Card, Invoice, Aadhaar, Agreement)",\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "summary": "1-2 sentence executive summary of the document and its primary contents.",\n'
        '  "reasoning": [\n'
        '    "Evidence point 1 extracted from document",\n'
        '    "Evidence point 2 extracted from document",\n'
        '    "Evidence point 3 extracted from document"\n'
        "  ],\n"
        '  "extracted_fields": {\n'
        '    "field_name_1": "field_value_1",\n'
        '    "field_name_2": "field_value_2"\n'
        "  }\n"
        "}\n"
        "IMPORTANT RULES:\n"
        "- Do NOT include any markdown fences or conversational preamble.\n"
        "- Extract ALL visible text and key-value pairs into extracted_fields.\n"
        "- Be factual, exact, and complete."
    )

    try:
        client = get_client()
        response = client.chat(
            model=DEFAULT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_to_send],
                }
            ],
            format="json",
        )

        duration = time.time() - t0
        logger.info("Response received from Ollama in %.2f seconds", duration)

        raw_content = response.get("message", {}).get("content", "")
        cleaned_json = _clean_json_response(raw_content)
        parsed = json.loads(cleaned_json)

        # Normalize output fields
        doc_type = parsed.get("document_type") or "Analyzed Document"
        confidence = str(parsed.get("confidence", "high")).lower()
        if confidence not in ("high", "medium", "low"):
            confidence = "high"

        summary = parsed.get("summary") or f"Document classified as {doc_type} using local Qwen2.5-VL vision model."
        reasoning = parsed.get("reasoning") or []
        if isinstance(reasoning, str):
            reasoning = [reasoning]

        extracted_fields = _normalize_extracted_fields(parsed.get("extracted_fields") or {})

        return {
            "document_type": doc_type,
            "confidence": confidence,
            "summary": summary,
            "reasoning": reasoning,
            "extracted_fields": extracted_fields,
            "processing_time_seconds": round(duration, 2),
            "model_used": DEFAULT_MODEL,
            "is_local_ai": True,
        }

    except Exception as ex:
        duration = time.time() - t0
        logger.error("Error communicating with Ollama: %s", ex, exc_info=True)
        err_text = str(ex).lower()
        if "connection refused" in err_text or "connecterror" in err_text:
            return {"error": "Ollama server is not running."}
        return {"error": f"Ollama analysis error: {str(ex)}"}


def chat_with_document(
    document_context: str,
    filename: str,
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Document-grounded conversational chat using local Ollama model.
    """
    health = check_ollama_health()
    if not health.get("reachable"):
        raise RuntimeError("Ollama server is not running.")

    system_prompt = (
        f"You are an AI Document Assistant analyzing the document '{filename}'.\n"
        "Here is the verified context and extracted content from this document:\n"
        "-----------------------------------------\n"
        f"{document_context[:10000]}\n"
        "-----------------------------------------\n"
        "Instructions:\n"
        "1. Answer questions accurately based strictly on the document context above.\n"
        "2. If an answer cannot be found in the context, clearly state that it is not present in the document.\n"
        "3. Keep answers concise, helpful, and professional."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for item in history[-6:]:
            role = item.get("role", "user")
            content = item.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    client = get_client()
    response = client.chat(model=DEFAULT_MODEL, messages=messages)
    return response.get("message", {}).get("content", "").strip()
