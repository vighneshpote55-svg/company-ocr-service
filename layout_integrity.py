"""
layout_integrity.py
Universal Document Layout Integrity Checker for Company OCR Service.

Analyzes RapidOCR bounding boxes and geometric document structure to detect:
- Overlapping OCR text bounding boxes (indicating pasted or overwritten text).
- Duplicate primary field labels (e.g., duplicate "Name" or "DOB" headers).
- Abnormal field alignment and unexpected text placement.

Objective Terminology Invariant:
Never use the words "Fake", "Forged", or "Fraudulent".
Use objective phrasing: "Review Required", "Visible inconsistencies detected".
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("company_ocr.layout_integrity")

PRIMARY_IDENTITY_LABELS = [
    # Primary cardholder/person name (exclusions prevent false match on Father's, Mother's, Company name)
    (r"\bname\b", "Name", ["father", "mother", "husband", "spouse", "company", "employer", "trade", "firm"]),
    (r"\bfather'?s?\s*name\b", "Father's Name", []),
    (r"\bdate\s*of\s*birth\b|\bdob\b", "Date of Birth", []),
    (r"\bpan\s*(?:no|number)?\b", "PAN", []),
    (r"\baadhaar\s*(?:no|number)?\b", "Aadhaar", []),
    (r"\bgross\s*(?:pay|salary|wages)\b", "Gross Pay", []),
    (r"\bnet\s*(?:pay|salary|amount)\b", "Net Pay", []),
    (r"\btax\s*invoice\b", "Tax Invoice", []),
]

# Document types that legitimately contain recurring tabular row headers
TABULAR_DOC_TYPES = {
    "bank_statement",
    "commercial_invoice",
    "invoice",
    "statement",
}


def _bbox_to_xyxy(bbox: Any) -> Optional[Tuple[float, float, float, float]]:
    """Convert any bbox format (4-point polygon [[x1,y1], [x2,y1], [x3,y2], [x4,y2]] or [x1,y1,x2,y2]) to (xmin, ymin, xmax, ymax)."""
    if not bbox:
        return None
    try:
        # Case: 4-point polygon [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and isinstance(bbox[0], (list, tuple)):
            xs = [float(pt[0]) for pt in bbox]
            ys = [float(pt[1]) for pt in bbox]
            return min(xs), min(ys), max(xs), max(ys)
        # Case: [xmin, ymin, xmax, ymax]
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
            return float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    except Exception:
        pass
    return None


def _calculate_iou_and_containment(
    b1: Tuple[float, float, float, float],
    b2: Tuple[float, float, float, float]
) -> Tuple[float, float]:
    """Calculate Intersection-over-Union (IoU) and maximum vertical/area containment between two bounding boxes."""
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0, 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])

    if area1 <= 0 or area2 <= 0:
        return 0.0, 0.0

    union = area1 + area2 - intersection
    iou = intersection / union if union > 0 else 0.0
    containment = max(intersection / area1, intersection / area2)

    return iou, containment


class LayoutIntegrityChecker:
    """Document-agnostic layout integrity analyzer operating on RapidOCR bounding boxes."""

    @classmethod
    def check_layout(
        cls,
        ocr_lines: Optional[List[Any]],
        doc_type: str = "unknown",
        raw_text: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Executes all layout integrity checks.
        Returns a list of structured signal dictionaries:
        [{"signal": str, "category": "layout", "score": int, "description": str}]
        """
        findings: List[Dict[str, Any]] = []
        if not ocr_lines and not raw_text:
            return findings

        try:
            # 1. Check for overlapping OCR bounding boxes
            if ocr_lines:
                cls._check_overlapping_boxes(ocr_lines, findings)

            # 2. Check for duplicate field labels
            cls._check_duplicate_labels(ocr_lines, doc_type, raw_text, findings)

            # 3. Check for abnormal alignment and unexpected field placement
            if ocr_lines:
                cls._check_abnormal_alignment(ocr_lines, findings)
        except Exception as ex:
            logger.warning("Layout integrity check encountered non-fatal error: %s", ex)

        return findings

    @classmethod
    def _check_overlapping_boxes(
        cls,
        ocr_lines: List[Any],
        findings: List[Dict[str, Any]],
        iou_threshold: float = 0.15,
        containment_threshold: float = 0.45,
    ) -> None:
        """
        Detects distinct OCR lines whose bounding boxes overlap significantly.
        Overlapping text is an objective indicator of physical/digital text paste-overs.
        """
        boxes = []
        for idx, line in enumerate(ocr_lines):
            bbox = getattr(line, "bbox", None) if hasattr(line, "bbox") else (line.get("bbox") if isinstance(line, dict) else None)
            text = (getattr(line, "text", "") if hasattr(line, "text") else (line.get("text", "") if isinstance(line, dict) else str(line))).strip()
            xyxy = _bbox_to_xyxy(bbox)
            if xyxy and len(text) > 1:
                boxes.append((idx, text, xyxy))

        overlap_detected = False
        overlapping_pairs = []

        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                idx1, text1, b1 = boxes[i]
                idx2, text2, b2 = boxes[j]

                # Skip identical texts at essentially the same index
                if text1.lower() == text2.lower() and idx1 == idx2:
                    continue

                iou, containment = _calculate_iou_and_containment(b1, b2)
                # Overlap triggered if IoU > 0.15 or one box is substantially contained within another
                if iou >= iou_threshold or containment >= containment_threshold:
                    overlap_detected = True
                    overlapping_pairs.append(f"'{text1[:20]}' / '{text2[:20]}'")
                    if len(overlapping_pairs) >= 3:
                        break
            if len(overlapping_pairs) >= 3:
                break

        if overlap_detected:
            findings.append({
                "signal": "overlapping_text_regions",
                "category": "layout",
                "score": 15,
                "description": "Overlapping text regions detected.",
            })

    @classmethod
    def _check_duplicate_labels(
        cls,
        ocr_lines: Optional[List[Any]],
        doc_type: str,
        raw_text: str,
        findings: List[Dict[str, Any]],
    ) -> None:
        """
        Detects duplicate primary field labels (such as two 'Name' labels) on non-tabular documents.
        """
        # Exclude expected tabular documents
        clean_doc_type = (doc_type or "").lower().strip()
        if clean_doc_type in TABULAR_DOC_TYPES or "statement" in clean_doc_type or "invoice" in clean_doc_type:
            return

        # Extract all line texts
        line_texts: List[str] = []
        if ocr_lines:
            for line in ocr_lines:
                txt = getattr(line, "text", None) if hasattr(line, "text") else (line.get("text") if isinstance(line, dict) else str(line))
                if txt:
                    line_texts.append(txt.strip())
        elif raw_text:
            line_texts = [l.strip() for l in raw_text.split("\n") if l.strip()]

        if not line_texts:
            return

        # Check each primary label pattern
        detected_duplicate_labels = set()
        for pattern, label_display, exclusions in PRIMARY_IDENTITY_LABELS:
            regex = re.compile(pattern, re.IGNORECASE)
            matches = []
            for t in line_texts:
                if regex.search(t):
                    t_lower = t.lower()
                    if not any(excl in t_lower for excl in exclusions):
                        matches.append(t)

            # If the label appears more than once as a standalone header or field prefix
            if len(matches) >= 2:
                if label_display not in detected_duplicate_labels:
                    detected_duplicate_labels.add(label_display)
                    findings.append({
                        "signal": "duplicate_field_label",
                        "category": "layout",
                        "score": 20,
                        "description": f"Duplicate {label_display} field detected.",
                    })
                    findings.append({
                        "signal": "abnormal_alignment",
                        "category": "layout",
                        "score": 10,
                        "description": f"Unexpected field position detected for {label_display}.",
                    })

    @classmethod
    def _check_abnormal_alignment(
        cls,
        ocr_lines: List[Any],
        findings: List[Dict[str, Any]],
    ) -> None:
        """
        Analyzes horizontal baseline and indentation consistency across vertical text blocks.
        """
        if len(ocr_lines) < 6:
            return

        left_positions = []
        for line in ocr_lines:
            bbox = getattr(line, "bbox", None) if hasattr(line, "bbox") else (line.get("bbox") if isinstance(line, dict) else None)
            xyxy = _bbox_to_xyxy(bbox)
            if xyxy:
                left_positions.append(xyxy[0])

        if len(left_positions) >= 6:
            # Check for sudden micro-offsets where a single line is displaced by a small unexpected margin
            # (e.g., standard left margin is ~50px, but one field is at 68px with identical vertical column)
            sorted_x = sorted(left_positions)
            median_x = sorted_x[len(sorted_x) // 2]
            anomalous_shifts = [x for x in left_positions if 5.0 < abs(x - median_x) < 25.0]

            if len(anomalous_shifts) >= 3:
                findings.append({
                    "signal": "abnormal_alignment",
                    "category": "layout",
                    "score": 10,
                    "description": "Unexpected field placement or abnormal text alignment detected.",
                })
