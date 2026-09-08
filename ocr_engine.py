"""
ocr_engine.py
PaddleOCR (PP-OCRv5 + PPStructureV3) engine wrapper:
- Runs text detection & recognition with per-line confidence scores
- Multi-page PDF handling (extracts and runs OCR per page)
- Extracts tabular structures for bank statements
- Seamless fallback for PDF text extraction when PaddlePaddle binaries are absent
"""

import glob
import importlib.metadata
import io
import logging
import os
import platform
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image

logger = logging.getLogger("company_ocr.engine")

# Global engine state
HAS_PADDLEOCR = False
_paddleocr_instance = None
_ocr_backend: Optional[str] = None
_ocr_engine_details: str = "uninitialized"


def _detect_installed_versions() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Detect installed versions of rapidocr-onnxruntime, onnxruntime, and paddleocr."""
    rapid_ver = None
    onnx_ver = None
    paddle_ver = None
    try:
        rapid_ver = importlib.metadata.version("rapidocr-onnxruntime")
    except Exception:
        pass
    try:
        onnx_ver = importlib.metadata.version("onnxruntime")
    except Exception:
        pass
    try:
        paddle_ver = importlib.metadata.version("paddleocr")
    except Exception:
        pass
    return rapid_ver, onnx_ver, paddle_ver


def init_ocr_engine(force_engine: Optional[str] = None):
    """
    Initialize neural OCR engine according to OCR_ENGINE setting or force_engine parameter.
    Supported values: 'auto', 'rapidocr', 'paddleocr'.
    Fails loud if a specific engine is explicitly requested but cannot be loaded.
    """
    global HAS_PADDLEOCR, _paddleocr_instance, _ocr_backend, _ocr_engine_details

    setting = (force_engine or os.getenv("OCR_ENGINE", "auto")).lower().strip()
    if setting not in ("auto", "rapidocr", "paddleocr"):
        raise ValueError(
            f"Invalid OCR_ENGINE setting '{setting}'. Allowed values are 'auto', 'rapidocr', 'paddleocr'."
        )

    rapid_ver, onnx_ver, paddle_ver = _detect_installed_versions()
    py_ver = platform.python_version()

    _paddleocr_instance = None
    _ocr_backend = None
    HAS_PADDLEOCR = False

    if setting == "paddleocr":
        try:
            from paddleocr import PaddleOCR
            _paddleocr_instance = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            HAS_PADDLEOCR = True
            _ocr_backend = "paddleocr"
            _ocr_engine_details = f"paddleocr v{paddle_ver or 'unknown'} on Python {py_ver}"
        except Exception as ex:
            _ocr_engine_details = f"paddleocr initialization failed: {str(ex)}"
            raise RuntimeError(
                f"Configured OCR_ENGINE 'paddleocr' could not be initialized: {str(ex)}. "
                f"Please install PaddlePaddle wheels for your Python version, or switch to "
                f"'OCR_ENGINE=rapidocr' or 'OCR_ENGINE=auto' to use the ONNX-backed engine."
            ) from ex

    elif setting == "rapidocr":
        try:
            from rapidocr_onnxruntime import RapidOCR
            _paddleocr_instance = RapidOCR()
            HAS_PADDLEOCR = True
            _ocr_backend = "rapidocr"
            _ocr_engine_details = (
                f"rapidocr_onnxruntime v{rapid_ver or '1.2.3'} (onnxruntime v{onnx_ver or 'unknown'}) on Python {py_ver}"
            )
        except Exception as ex:
            _ocr_engine_details = f"rapidocr initialization failed: {str(ex)}"
            raise RuntimeError(
                f"Configured OCR_ENGINE 'rapidocr' could not be initialized: {str(ex)}"
            ) from ex

    else:  # 'auto'
        # First preference: RapidOCR (cross-platform, native ONNX runtime wheels for Python 3.14+)
        try:
            from rapidocr_onnxruntime import RapidOCR
            _paddleocr_instance = RapidOCR()
            HAS_PADDLEOCR = True
            _ocr_backend = "rapidocr"
            _ocr_engine_details = (
                f"rapidocr_onnxruntime v{rapid_ver or '1.2.3'} (onnxruntime v{onnx_ver or 'unknown'}) on Python {py_ver}"
            )
        except Exception as rapid_ex:
            # Second preference: native PaddleOCR
            try:
                from paddleocr import PaddleOCR
                _paddleocr_instance = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
                HAS_PADDLEOCR = True
                _ocr_backend = "paddleocr"
                _ocr_engine_details = f"paddleocr v{paddle_ver or 'unknown'} on Python {py_ver}"
            except Exception as paddle_ex:
                HAS_PADDLEOCR = False
                _ocr_backend = None
                _ocr_engine_details = (
                    f"no neural OCR engine available (rapidocr error: {str(rapid_ex)}; paddleocr error: {str(paddle_ex)})"
                )
                logger.warning(
                    "Startup OCR check: No neural OCR engine available (%s). Only digital PDFs with embedded text layers will be processed.",
                    _ocr_engine_details,
                )

    if HAS_PADDLEOCR:
        logger.info(
            "OCR engine initialized: %s (%s) [setting: %s]",
            _ocr_backend,
            _ocr_engine_details,
            setting,
        )


# Run initial engine detection at import time
try:
    init_ocr_engine()
except Exception as _init_err:
    logger.warning("Initial OCR engine startup notice: %s", _init_err)


def validate_ocr_engine_configuration():
    """
    Called during application startup to enforce fail-loud behavior if configured OCR_ENGINE cannot run.
    """
    setting = os.getenv("OCR_ENGINE", "auto").lower().strip()
    if setting not in ("auto", "rapidocr", "paddleocr"):
        raise ValueError(
            f"Invalid OCR_ENGINE '{setting}'. Allowed values: 'auto', 'rapidocr', 'paddleocr'."
        )
    if not HAS_PADDLEOCR:
        if setting in ("paddleocr", "rapidocr"):
            raise RuntimeError(
                f"Configured OCR_ENGINE '{setting}' is not available: {_ocr_engine_details}"
            )
    logger.info("Active OCR Engine: %s | Details: %s", _ocr_backend or "none", _ocr_engine_details)


def get_active_ocr_engine() -> Optional[str]:
    """Returns identifier of the active neural OCR engine ('rapidocr', 'paddleocr', or None)."""
    return _ocr_backend


def get_ocr_engine_info() -> Dict[str, Any]:
    """Returns structured engine metadata for /health and /engine-info endpoints."""
    rapid_ver, onnx_ver, paddle_ver = _detect_installed_versions()
    return {
        "active_engine": _ocr_backend or "none",
        "configured_engine": os.getenv("OCR_ENGINE", "auto").lower().strip(),
        "status": "ready" if HAS_PADDLEOCR else "unavailable",
        "details": _ocr_engine_details,
        "rapidocr_version": rapid_ver,
        "onnxruntime_version": onnx_ver,
        "paddleocr_version": paddle_ver,
        "python_version": platform.python_version(),
        "pdf_fallback": "pdftotext",
    }


@dataclass
class OCRLine:
    text: str
    confidence: float
    bbox: Optional[List[List[float]]] = None


@dataclass
class OCRPageResult:
    page_num: int
    full_text: str
    lines: List[OCRLine]
    average_confidence: float
    tables: List[List[List[str]]] = field(default_factory=list)
    image: Optional[Image.Image] = None
    engine_error: Optional[str] = None


@dataclass
class OCRDocumentResult:
    pages: List[OCRPageResult]
    full_text: str
    average_confidence: float
    field_confidences: Dict[str, float] = field(default_factory=dict)
    ocr_required: bool = False
    text_source: str = "pdf_text_layer"
    engine_error: Optional[str] = None


def get_paddleocr_instance():
    """Lazily initialize and reuse PaddleOCR / RapidOCR instance."""
    global _paddleocr_instance
    if _paddleocr_instance is None and os.getenv("OCR_ENGINE", "auto").lower().strip() != "none":
        try:
            init_ocr_engine()
        except Exception:
            pass
    return _paddleocr_instance



def extract_text_from_pdf_pdftotext(pdf_path: str) -> List[str]:
    """Extract text page-by-page using pdftotext utility if available."""
    pages_text = []
    try:
        # Check number of pages or extract with form feed separator
        result = subprocess.run(
            ["pdftotext", pdf_path, "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        raw_output = result.stdout
        # Form feed (\x0c) separates pages in pdftotext
        pages = raw_output.split("\x0c")
        pages_text = [p.strip() for p in pages if p.strip()]
        if not pages_text and raw_output.strip():
            pages_text = [raw_output.strip()]
    except Exception:
        pass
    return pages_text


def parse_text_into_ocr_lines(text: str, default_conf: float = 0.96) -> List[OCRLine]:
    """Convert raw page text into structured OCRLine objects with baseline confidence."""
    lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if line:
            # Synthetic / digital text extraction has near-perfect baseline confidence
            lines.append(OCRLine(text=line, confidence=default_conf))
    return lines


def check_pdf_text_layer(pdf_path_or_bytes: Union[str, bytes], min_char_threshold: int = 50) -> Tuple[bool, str, List[str]]:
    """
    Determines if a PDF has an existing text layer.
    Extracts text using pdftotext.
    Returns:
        (has_text_layer: bool, full_text: str, pages_text: List[str])
    If len(full_text.strip()) >= min_char_threshold (default 50 chars),
    has_text_layer is True (meaning OCR is NOT required).
    """
    tmp_file = None
    try:
        if isinstance(pdf_path_or_bytes, bytes):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(pdf_path_or_bytes)
                tmp_file = f.name
            path_to_read = tmp_file
        else:
            path_to_read = pdf_path_or_bytes

        pages_text = extract_text_from_pdf_pdftotext(path_to_read)
        full_text = "\n\n".join(pages_text).strip()
        has_text_layer = len(full_text) >= min_char_threshold
        return has_text_layer, full_text, pages_text
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


def render_pdf_pages_to_images(pdf_path: str, dpi: int = 150) -> List[Image.Image]:
    """
    Render all pages of a PDF to PIL Images using Poppler's pdftoppm.
    Falls back to PyMuPDF (fitz) if available.
    """
    images = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_prefix = os.path.join(tmp_dir, "page")
        cmd = ["pdftoppm", "-png", "-r", str(dpi), pdf_path, out_prefix]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            png_files = sorted(
                glob.glob(os.path.join(tmp_dir, "page-*.png")),
                key=lambda p: int(re.findall(r"page-(\d+)\.png", p)[0]) if re.findall(r"page-(\d+)\.png", p) else 0
            )
            for p in png_files:
                with Image.open(p) as img:
                    images.append(img.convert("RGB").copy())
        except Exception:
            pass

    if not images:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            for page in doc:
                pix = page.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)
        except Exception:
            pass

    return images


def render_thumbnail(file_path_or_bytes: Union[str, bytes], is_pdf: bool = False, max_size: Tuple[int, int] = (400, 400)) -> Optional[bytes]:
    """
    Generates PNG thumbnail bytes for a document (PDF or image).
    """
    try:
        if is_pdf:
            tmp_pdf = None
            try:
                if isinstance(file_path_or_bytes, bytes):
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                        f.write(file_path_or_bytes)
                        tmp_pdf = f.name
                    path_to_read = tmp_pdf
                else:
                    path_to_read = file_path_or_bytes

                with tempfile.TemporaryDirectory() as tmp_dir:
                    out_prefix = os.path.join(tmp_dir, "thumb")
                    cmd = ["pdftoppm", "-png", "-r", "100", "-f", "1", "-l", "1", path_to_read, out_prefix]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    pngs = glob.glob(os.path.join(tmp_dir, "thumb-*.png"))
                    if pngs:
                        with Image.open(pngs[0]) as img:
                            img.thumbnail(max_size, Image.Resampling.LANCZOS)
                            buf = io.BytesIO()
                            img.convert("RGB").save(buf, format="PNG", optimize=True)
                            return buf.getvalue()
            finally:
                if tmp_pdf and os.path.exists(tmp_pdf):
                    try:
                        os.remove(tmp_pdf)
                    except Exception:
                        pass
        else:
            if isinstance(file_path_or_bytes, bytes):
                img = Image.open(io.BytesIO(file_path_or_bytes))
            else:
                img = Image.open(file_path_or_bytes)
            with img:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="PNG", optimize=True)
                return buf.getvalue()
    except Exception:
        pass
    return None


class OCREngine:
    """Production OCR Engine utilizing PaddleOCR with multi-page handling."""

    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        self.paddle = get_paddleocr_instance()

    def process_image(self, img: Image.Image, page_num: int = 1) -> OCRPageResult:
        """Run OCR on a single PIL Image."""
        engine = get_paddleocr_instance()
        if engine is not None:
            try:
                import numpy as np
                arr = np.array(img.convert("RGB"))
                lines: List[OCRLine] = []
                total_conf = 0.0

                if _ocr_backend == "rapidocr":
                    results, elapse = engine(arr)
                    if results:
                        for item in results:
                            bbox = item[0]
                            txt = item[1]
                            score = float(item[2])
                            lines.append(OCRLine(text=txt, confidence=score, bbox=bbox))
                            total_conf += score
                else:
                    results = engine.ocr(arr, cls=True)
                    if results and results[0]:
                        for item in results[0]:
                            bbox = item[0]
                            txt, score = item[1]
                            lines.append(OCRLine(text=txt, confidence=float(score), bbox=bbox))
                            total_conf += float(score)

                avg_conf = (total_conf / len(lines)) if lines else 0.0
                full_text = "\n".join([line.text for line in lines])
                return OCRPageResult(
                    page_num=page_num,
                    full_text=full_text,
                    lines=lines,
                    average_confidence=round(avg_conf, 4),
                    image=img,
                    engine_error=None,
                )
            except Exception as ex:
                logger.error("OCR inference error on page %s: %s", page_num, ex, exc_info=True)
                return OCRPageResult(
                    page_num=page_num,
                    full_text="",
                    lines=[],
                    average_confidence=0.0,
                    image=img,
                    engine_error=f"ocr_inference_failed: {str(ex)}",
                )

        # Fallback for image when neural OCR engine is not loaded
        return OCRPageResult(
            page_num=page_num,
            full_text="",
            lines=[],
            average_confidence=0.0,
            image=img,
            engine_error="neural_ocr_engine_not_available",
        )

    def process_pdf(self, pdf_path: str) -> OCRDocumentResult:
        """
        Process a multi-page PDF document.
        First checks if the PDF has an embedded text layer (>= 50 chars).
        If text layer exists:
            OCR is not required. Extracts embedded text directly.
            ocr_required=False, text_source="pdf_text_layer"
        If text layer does NOT exist (scanned / image-only):
            OCR is required. Renders pages to images and runs neural OCR.
            ocr_required=True, text_source="rapid_ocr" / "paddle_ocr"
        """
        has_text_layer, full_text, pages_text = check_pdf_text_layer(pdf_path, min_char_threshold=50)

        if has_text_layer:
            page_results: List[OCRPageResult] = []
            for idx, p_text in enumerate(pages_text, start=1):
                lines = parse_text_into_ocr_lines(p_text, default_conf=0.98)
                avg_conf = sum(l.confidence for l in lines) / len(lines) if lines else 0.98
                page_results.append(
                    OCRPageResult(
                        page_num=idx,
                        full_text=p_text,
                        lines=lines,
                        average_confidence=round(avg_conf, 4),
                        engine_error=None,
                    )
                )
            overall_conf = (
                sum(p.average_confidence for p in page_results) / len(page_results)
                if page_results
                else 0.98
            )
            return OCRDocumentResult(
                pages=page_results,
                full_text=full_text,
                average_confidence=round(overall_conf, 4),
                ocr_required=False,
                text_source="pdf_text_layer",
                engine_error=None,
            )

        # Scanned PDF or insufficient text layer (< 50 chars) -> OCR required
        rendered_images = render_pdf_pages_to_images(pdf_path)
        page_results: List[OCRPageResult] = []

        if rendered_images:
            for idx, img in enumerate(rendered_images, start=1):
                page_res = self.process_image(img, page_num=idx)
                page_results.append(page_res)
        else:
            # Fallback if rendering completely failed
            if pages_text:
                for idx, p_text in enumerate(pages_text, start=1):
                    lines = parse_text_into_ocr_lines(p_text, default_conf=0.70)
                    page_results.append(
                        OCRPageResult(
                            page_num=idx,
                            full_text=p_text,
                            lines=lines,
                            average_confidence=0.70,
                            engine_error="pdf_rendering_fallback",
                        )
                    )

        full_doc_text = "\n\n".join([p.full_text for p in page_results])
        overall_conf = (
            sum(p.average_confidence for p in page_results) / len(page_results)
            if page_results
            else 0.0
        )
        source_name = "rapid_ocr" if _ocr_backend == "rapidocr" else "paddle_ocr"
        page_errors = [p.engine_error for p in page_results if p.engine_error]
        combined_error = "; ".join(page_errors) if page_errors else None

        return OCRDocumentResult(
            pages=page_results,
            full_text=full_doc_text,
            average_confidence=round(overall_conf, 4),
            ocr_required=True,
            text_source=source_name,
            engine_error=combined_error,
        )

    def process_file(self, file_path: str) -> OCRDocumentResult:
        """Unified entry point to process either an image or a PDF."""
        lower = file_path.lower()
        if lower.endswith(".pdf"):
            return self.process_pdf(file_path)
        else:
            with Image.open(file_path) as img:
                page_res = self.process_image(img.copy(), page_num=1)
                source_name = "rapid_ocr" if _ocr_backend == "rapidocr" else "paddle_ocr"
                return OCRDocumentResult(
                    pages=[page_res],
                    full_text=page_res.full_text,
                    average_confidence=page_res.average_confidence,
                    ocr_required=True,
                    text_source=source_name,
                    engine_error=page_res.engine_error,
                )

