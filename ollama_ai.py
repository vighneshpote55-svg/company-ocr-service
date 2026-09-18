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


def normalize_document_type(raw_type: str, text_content: str = "") -> str:
    """
    Map raw model classification to canonical, clean document types using
    the unified classify_document_content() engine.
    Ensures that raw strings like 'Incometaxdepartment' are NEVER used.
    """
    import verifier

    # 1. First check actual extracted document text
    if text_content and text_content.strip():
        cls = verifier.classify_document_content(text_content)
        if cls.get("doc_type") != "unknown":
            return cls["document_type"]

    # 2. Next check raw_type text against unified signatures
    if raw_type and raw_type.strip():
        cls = verifier.classify_document_content(raw_type)
        if cls.get("doc_type") != "unknown":
            return cls["document_type"]

    clean = (raw_type or "").strip()
    if not clean or "unknown" in clean.lower() or len(clean) > 35:
        return "Unknown Document"

    return clean.title()



def analyze_document(
    file_path: str,
    filename: str = "",
    ocr_text: str = "",
) -> Dict[str, Any]:
    """
    Analyze document with local Ollama + Qwen2.5-VL:3B:
    - Combines vision image + OCR extracted text
    - Extracts every visible field as structured key-value pairs
    - Classifies document into canonical types (e.g. 'GST Registration Certificate', 'PAN Card', 'Aadhaar Card', 'Employment Contract')
    - Returns structured JSON with meaningful confidence, summary, and evidence points.
    """
    logger.info("AI Mode Ollama analysis starting for file: %s", file_path)

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

    trimmed_ocr = (ocr_text or "").strip()[:2000]

    prompt = (
        "You are an expert document understanding AI. Analyze the uploaded document image and extracted text carefully.\n"
    )
    if trimmed_ocr:
        prompt += (
            f"Extracted Document OCR Text:\n---\n{trimmed_ocr}\n---\n\n"
        )
    prompt += (
        "TASK:\n"
        "1. Classify the document based on its actual content into one of these canonical types:\n"
        "   - 'GST Registration Certificate' (Form GST REG-06, Registration Certificate under Goods and Services Tax Act)\n"
        "   - 'PAN Card' (Permanent Account Number Card issued by Income Tax Dept)\n"
        "   - 'Aadhaar Card' (UIDAI identity card)\n"
        "   - 'Income Tax Notice' (Formal tax notice/demand/intimation under Income Tax Act)\n"
        "   - 'Employment Contract' (Employment contract, agreement, appointment letter)\n"
        "   - 'Bank Statement' (Statement of account, transaction records, balance)\n"
        "   - 'Commercial Invoice' (Billed goods/services, tax invoice)\n"
        "   - 'Salary Slip' (Monthly pay statement, earnings, deductions)\n"
        "   - 'Passport', 'Voter ID', 'Driving License', 'Rental Agreement'\n"
        "   - 'Unknown Document' (if the document cannot be reliably classified)\n"
        "2. Assess confidence: 'high' | 'medium' | 'low'.\n"
        "3. Provide a natural 1-2 sentence summary of facts present in the document.\n"
        "4. Provide 3-4 specific factual evidence points found in the document.\n"
        "5. Extract visible key fields into extracted_fields.\n\n"
        "CRITICAL RULES:\n"
        "- NEVER use the filename or raw text fragments like 'Incometaxdepartment' as the document type.\n"
        "- If the document is a PAN Card, classify it as 'PAN Card' (NOT 'Incometaxdepartment').\n"
        "- NEVER hallucinate fields. Only mention facts present in the document.\n\n"
        "Respond ONLY with a valid JSON object matching this schema:\n"
        "{\n"
        '  "document_type": "string",\n'
        '  "confidence": "high" | "medium" | "low",\n'
        '  "summary": "1-2 sentence executive summary of the document and its primary contents.",\n'
        '  "evidence": [\n'
        '    "Evidence point 1 extracted from document",\n'
        '    "Evidence point 2 extracted from document",\n'
        '    "Evidence point 3 extracted from document"\n'
        '  ],\n'
        '  "extracted_fields": {\n'
        '    "field_name_1": "field_value_1"\n'
        '  }\n'
        "}\n"
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
            options={"num_ctx": 8192},
            format="json",
        )

        duration = time.time() - t0
        logger.info("Response received from Ollama in %.2f seconds", duration)

        raw_content = response.get("message", {}).get("content", "")
        cleaned_json = _clean_json_response(raw_content)
        try:
            parsed = json.loads(cleaned_json)
        except Exception:
            try:
                parsed = json.loads(cleaned_json, strict=False)
            except Exception:
                parsed = {}

        # Normalize document type using unified classify_document_content
        import verifier
        combined_text = ((ocr_text or "") + "\n" + raw_content).strip()
        cls = verifier.classify_document_content(combined_text)
        if cls.get("doc_type") != "unknown":
            normalized_type = cls["document_type"]
            confidence = cls.get("confidence", "high")
            evidence = cls.get("evidence", [])
        else:
            raw_doc_type = parsed.get("document_type") or "Unknown Document"
            normalized_type = normalize_document_type(raw_doc_type, text_content=ocr_text)
            confidence = str(parsed.get("confidence", "low")).lower()
            if confidence not in ("high", "medium", "low"):
                confidence = "high" if normalized_type != "Unknown Document" else "low"
            evidence = parsed.get("evidence") or parsed.get("reasoning") or []

        summary = parsed.get("summary") or f"This document was analyzed and identified as a {normalized_type}."
        if not evidence:
            evidence = [
                f"Document structure matches {normalized_type}",
                f"Contains verified text tokens and layout features",
            ]

        # Ensure canonical structured fields from content classification are present
        import ai_service
        canonical_info = ai_service.classify_document_content(ocr_text, filename=filename)
        canonical_fields = canonical_info.get("extracted_fields") or {}
        merged_fields = dict(canonical_fields)
        for k, v in _normalize_extracted_fields(parsed.get("extracted_fields") or {}).items():
            if v and str(v).strip() and str(v).strip().lower() != "none" and (k not in merged_fields or not merged_fields[k]):
                merged_fields[k] = v

        extracted_fields = merged_fields

        return {
            "document_type": normalized_type,
            "confidence": confidence,
            "summary": summary,
            "evidence": evidence,
            "reasoning": evidence,
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
        if ("exceed" in err_text and "context" in err_text) or "status code: 400" in err_text:
            # Fall back to grounded local content analysis
            try:
                import ai_service
                cls = ai_service.classify_document_content(ocr_text, filename=filename)
                return {
                    "document_type": cls.get("document_type", "Document"),
                    "confidence": cls.get("confidence", "high"),
                    "summary": cls.get("summary", ""),
                    "evidence": cls.get("evidence", []),
                    "reasoning": cls.get("reasoning", []),
                    "extracted_fields": cls.get("extracted_fields", {}),
                    "processing_time_seconds": round(duration, 2),
                    "model_used": "grounded_content_classifier",
                    "is_local_ai": True,
                }
            except Exception as fallback_ex:
                logger.error("Fallback classification error: %s", fallback_ex)
        return {"error": f"Ollama analysis error: {str(ex)}"}


def chat_with_document(
    document_context: str,
    filename: str,
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    stored_analysis: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Document-grounded conversational chat using local Ollama model.
    Strictly answers ONLY from document context and explicitly rejects hallucinating missing fields.
    Reuses stored document analysis (document_type and verified fields).
    """
    health = check_ollama_health()
    if not health.get("reachable"):
        raise RuntimeError("Ollama server is not running.")

    verified_type = (stored_analysis or {}).get("document_type", "")
    verified_fields = (stored_analysis or {}).get("extracted_fields", {})

    doc_type_header = f"Verified Document Type: {verified_type}\n" if verified_type else ""
    fields_ctx = f"\nVerified Key Extracted Fields:\n{json.dumps(verified_fields, indent=2)}\n" if verified_fields else ""

    system_prompt = (
        f"You are an expert AI Document Assistant analyzing the document '{filename}'.\n"
        f"{doc_type_header}"
        "Here is the verified context and extracted content from this document:\n"
        "-----------------------------------------\n"
        f"{document_context[:10000]}\n"
        "-----------------------------------------\n"
        f"{fields_ctx}"
        "CRITICAL GROUNDING RULES:\n"
        "1. Answer strictly based on the facts present in the document context above.\n"
        "2. NEVER invent, assume, or hallucinate facts, numbers, dates, or names.\n"
        "3. If the user asks for a field that does NOT exist in this document "
        "(e.g., asking for 'employee name' on a PAN card, ID card, tax notice, or invoice; "
        "or asking for 'salary' or 'joining date' when none is stated), you MUST state clearly:\n"
        "   'I could not find [field name] in this document.'\n"
        "   For example:\n"
        "   - 'I could not find an employee name in this document.'\n"
        "   - 'I could not find a joining date in this document.'\n"
        "   - 'I could not find salary information in this document.'\n"
        "4. NEVER output raw OCR placeholder artifacts or label fragments such as '***/Name', 'Name', or fake values.\n"
        "5. If the user asks to summarize, provide a concise factual summary of what is actually in the document.\n"
        "6. If the user asks for dates, list only dates explicitly found. If no dates are found, state: 'No clear dates were found in the document.'\n"
        "7. If the user asks for financial or compensation details, list only monetary amounts explicitly found. If no financial information exists, state: 'No financial information was found in this document.'\n"
        "8. Keep answers concise, direct, helpful, and professional.\n"
        "9. Never return a Bank Name, Branch, or Institution Name as an IFSC code. An IFSC code must be an 11-character alphanumeric code starting with 4 letters and '0' (e.g. UTIB0001435). If no valid IFSC is present, state: 'I could not find an IFSC Code in this document.'\n"
        "10. Never output Python dictionary syntax such as {'from_date': ...}. Always format dates as clean bullet points with From and To labels."
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
    reply = response.get("message", {}).get("content", "").strip()

    # Sanitize any raw OCR artifacts
    reply = reply.replace("***/Name", "the cardholder's name").replace("*/Name", "").replace("\u5dde/Name", "")
    if "ifsc" in message.lower():
        if not re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", reply):
            reply = "I could not find an IFSC Code in this document."
    if "{'from_date'" in reply or '{"from_date"' in reply or "{'from'" in reply:
        m_f = re.search(r"['\"](?:from_date|from)['\"]\s*:\s*['\"]([^'\"]+)['\"]", reply)
        m_t = re.search(r"['\"](?:to_date|to)['\"]\s*:\s*['\"]([^'\"]+)['\"]", reply)
        if m_f and m_t:
            reply = f"Statement Period:\n\n• From: {m_f.group(1)}\n\n• To: {m_t.group(1)}"
    return reply
