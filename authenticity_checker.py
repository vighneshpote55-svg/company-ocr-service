"""
authenticity_checker.py
Universal Document Integrity Assessment and Review Required Detection engine for Company OCR Service.

Orchestrates Phase 10 Document Integrity Layer:
- LayoutIntegrityChecker (layout_integrity.py): Bounding box overlaps, duplicate field labels, abnormal alignment.
- VisualTamperingChecker (visual_tampering.py): Pasted white patches, cloned stamps, compression artifacts, blur anomalies.
- UniversalConsistencyEngine (consistency_engine.py): PAN/Aadhaar/GST/DL/Passport/FSSAI checksums, salary math, bank balance math.
- QRConsistencyChecker: Reconciles OCR-extracted fields against decoded QR data.
- AuthenticityManager: Aggregates signals, applies weighted risk scoring, coordinates optional
  AI authenticity analysis, and produces the canonical authenticity assessment.

Status values:
- 'verified': No significant inconsistencies detected (Score 0-29).
- 'review_required': Visible inconsistencies detected (Score 30-59, or Score 60+ with high priority).
- 'unsupported': Unsupported document type.

Strict Terminology Invariant:
Never use the words "Fake", "Forged", or "Fraudulent".
Uses objective, professional terminology: "Review Required", "Visible inconsistencies detected",
"Verification could not be completed automatically".
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image

from layout_integrity import LayoutIntegrityChecker
from visual_tampering import VisualTamperingChecker
from consistency_engine import UniversalConsistencyEngine

logger = logging.getLogger("company_ocr.authenticity")

# ==============================================================================
# Signal Weight Registry (Phase 10 & Universal Risk Scoring)
# ==============================================================================

SIGNAL_WEIGHTS: Dict[str, int] = {
    "qr_mismatch": 40,
    "qr_data_mismatch": 40,
    "invalid_checksum": 30,
    "pan_format_invalid": 30,
    "aadhaar_checksum_invalid": 30,
    "gstin_checksum_invalid": 30,
    "math_inconsistency": 30,
    "balance_inconsistency": 30,
    "duplicate_field": 20,
    "duplicate_field_label": 20,
    "pasted_white_patch": 20,
    "white_patch": 20,
    "cloned_stamp": 25,
    "duplicated_stamp": 25,
    "cloned_signature": 25,
    "overwritten_text": 20,
    "overlap": 15,
    "overlapping_text_regions": 15,
    "font_mismatch": 15,
    "font_size_inconsistency": 15,
    "inconsistent_font_weight": 15,
    "alignment_issue": 10,
    "abnormal_alignment": 10,
    "uneven_text_baseline": 10,
    "shifted_numbers": 10,
    "misaligned_fields": 10,
    "compression_issue": 10,
    "compression_artifact": 10,
    "blurred_edited_region": 10,
    "cut_and_paste_edges": 10,
    "background_texture_anomaly": 10,
    "cropped_borders": 10,
}


def get_signal_weight(signal_name: str) -> int:
    """Return the assigned weight for a given authenticity signal."""
    clean_name = signal_name.lower().strip()
    if clean_name in SIGNAL_WEIGHTS:
        return SIGNAL_WEIGHTS[clean_name]
    for key, weight in SIGNAL_WEIGHTS.items():
        if key in clean_name or clean_name in key:
            return weight
    return 10


# Backward compatibility wrappers for Phase 9 tests
class ImageIntegrityChecker:
    """Delegates to VisualTamperingChecker for image-level analysis."""
    @classmethod
    def check_image(
        cls,
        image: Optional[Image.Image],
        ocr_lines: Optional[List[Any]] = None,
        extracted_fields: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        return VisualTamperingChecker.check_visual(image=image, ocr_lines=ocr_lines)


class OCRConsistencyChecker:
    """Delegates to UniversalConsistencyEngine for field consistency analysis."""
    @classmethod
    def check_consistency(
        cls,
        doc_type: str,
        extracted_fields: Dict[str, Any],
        raw_text: str = "",
    ) -> List[Dict[str, Any]]:
        return UniversalConsistencyEngine.check_consistency(
            doc_type=doc_type,
            extracted_fields=extracted_fields,
            raw_text=raw_text,
        )


class QRConsistencyChecker:
    """
    Cross-checks decoded QR code payload against OCR-extracted fields:
    - Name
    - Date of Birth
    - Document Number (PAN, Aadhaar, Udyam URN, FSSAI License, etc.)
    If mismatch exists: adds 'qr_data_mismatch' signal (40 pts).
    Never overwrites OCR values; preserves both.
    """

    @classmethod
    def check_qr_consistency(
        cls,
        ocr_fields: Dict[str, Any],
        qr_fields: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        discrepancies: Dict[str, Any] = {}

        if not qr_fields:
            return findings, discrepancies

        comparisons = [
            ("name", ["name", "cardholder_name", "applicant_name", "employee_name"]),
            ("dob", ["dob", "date_of_birth"]),
            ("doc_number", ["pan_number", "aadhaar_number", "raw_aadhaar", "udyam_registration_number", "fssai_licence_number"]),
        ]

        for qr_key, ocr_aliases in comparisons:
            qr_val = qr_fields.get(qr_key)
            if qr_val is None:
                for alias in ocr_aliases:
                    if alias in qr_fields:
                        qr_val = qr_fields[alias]
                        break

            if qr_val is None:
                continue

            ocr_val = None
            for alias in ocr_aliases:
                if alias in ocr_fields and ocr_fields[alias] is not None:
                    ocr_val = ocr_fields[alias]
                    break

            if ocr_val is None:
                continue

            str_qr = str(qr_val).strip().upper()
            str_ocr = str(ocr_val).strip().upper()

            norm_qr = re.sub(r"[\s\-_/]", "", str_qr)
            norm_ocr = re.sub(r"[\s\-_/]", "", str_ocr)

            if norm_qr != norm_ocr:
                discrepancies[qr_key] = {
                    "ocr_value": ocr_val,
                    "qr_value": qr_val,
                }
                findings.append({
                    "signal": "qr_data_mismatch",
                    "category": "security_feature",
                    "score": 40,
                    "severity": "high",
                    "description": (
                        f"QR code payload mismatch for {qr_key}: "
                        f"OCR read '{ocr_val}', while digital QR decoded '{qr_val}'."
                    ),
                })

        return findings, discrepancies


# ==============================================================================
# AuthenticityManager (Orchestrator for Universal Document Integrity Layer)
# ==============================================================================

class AuthenticityManager:
    """
    Universal Document Integrity Pipeline Orchestrator:
    RapidOCR
         ↓
    Layout Integrity (layout_integrity.py)
         ↓
    Visual Tampering (visual_tampering.py)
         ↓
    Consistency Engine (consistency_engine.py)
         ↓
    QR / Barcode Validation (QRConsistencyChecker)
         ↓
    Risk Score & Status Determination
    """

    def assess_document(
        self,
        doc_type: str,
        image: Optional[Image.Image] = None,
        ocr_lines: Optional[List[Any]] = None,
        extracted_fields: Optional[Dict[str, Any]] = None,
        raw_text: str = "",
        qr_fields: Optional[Dict[str, Any]] = None,
        ai_authenticity_result: Optional[Dict[str, Any]] = None,
        is_supported: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes all generic integrity checks and compiles the canonical assessment.
        """
        extracted_fields = extracted_fields or {}
        findings: List[Dict[str, Any]] = []

        # 0. Unsupported / Unknown documents
        if not is_supported or doc_type == "unknown":
            return {
                "verification_status": "unsupported",
                "risk_score": 0,
                "review_required": False,
                "priority": "low",
                "suspicious_signals": [],
                "human_review_reason": "Unsupported document type.",
                "verified_by_ai": False,
                "findings": [],
                "qr_discrepancies": {},
            }

        # 1. Layout Integrity (RapidOCR bounding boxes)
        layout_findings = LayoutIntegrityChecker.check_layout(
            ocr_lines=ocr_lines,
            doc_type=doc_type,
            raw_text=raw_text,
        )
        findings.extend(layout_findings)

        # 2. Visual Tampering (Image-level OpenCV checks)
        if image is not None:
            visual_findings = VisualTamperingChecker.check_visual(
                image=image,
                ocr_lines=ocr_lines,
            )
            findings.extend(visual_findings)

        # 3. Universal Consistency Engine (Checksums, formats, math, cross-field)
        consistency_findings = UniversalConsistencyEngine.check_consistency(
            doc_type=doc_type,
            extracted_fields=extracted_fields,
            raw_text=raw_text,
        )
        findings.extend(consistency_findings)

        # 4. QR / Barcode Validation
        qr_discrepancies = {}
        if qr_fields:
            qr_findings, qr_discrepancies = QRConsistencyChecker.check_qr_consistency(
                ocr_fields=extracted_fields,
                qr_fields=qr_fields,
            )
            findings.extend(qr_findings)

        # 5. Merge AI Authenticity Assessment (if present in AI mode)
        verified_by_ai = False
        if ai_authenticity_result:
            verified_by_ai = True
            ai_signals = ai_authenticity_result.get("suspicious_signals") or []
            for sig in ai_signals:
                sig_text = sig if isinstance(sig, str) else sig.get("description", str(sig))
                findings.append({
                    "signal": "ai_detected_anomaly",
                    "category": "ai_reasoning",
                    "score": 15,
                    "severity": "medium",
                    "description": sig_text,
                })

        # 6. Weighted Risk Scoring (Phase 6 & 10)
        total_risk = 0
        seen_signals = set()
        suspicious_signals_list: List[str] = []

        for finding in findings:
            sig_name = finding.get("signal", "unknown_signal")
            desc = finding.get("description", sig_name)
            weight = finding.get("score") or get_signal_weight(sig_name)

            if sig_name not in seen_signals:
                total_risk += weight
                seen_signals.add(sig_name)
            else:
                total_risk += int(weight * 0.5)

            if desc not in suspicious_signals_list:
                suspicious_signals_list.append(desc)

        risk_score = min(100, max(0, total_risk))

        # 7. Status Mapping:
        # 0–29: verified
        # 30–59: review_required (normal priority)
        # 60+: review_required (high priority)
        if risk_score >= 60:
            verification_status = "review_required"
            review_required = True
            priority = "high"
            human_review_reason = "Visible inconsistencies detected (High Priority)."
        elif risk_score >= 30:
            verification_status = "review_required"
            review_required = True
            priority = "normal"
            human_review_reason = "Visible inconsistencies detected."
        else:
            verification_status = "verified"
            review_required = False
            priority = "low"
            human_review_reason = None

        return {
            "verification_status": verification_status,
            "risk_score": risk_score,
            "review_required": review_required,
            "priority": priority,
            "suspicious_signals": suspicious_signals_list,
            "human_review_reason": human_review_reason,
            "verified_by_ai": verified_by_ai,
            "findings": findings,
            "qr_discrepancies": qr_discrepancies,
        }


authenticity_manager = AuthenticityManager()
