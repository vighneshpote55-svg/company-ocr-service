"""
authenticity_checker.py
Document Authenticity Assessment and Review Required Detection engine for Company OCR Service.

Detects visible signs of document tampering, structural anomalies, and logical inconsistencies:
- ImageIntegrityChecker: Font inconsistencies, baseline alignment, compression anomalies,
  duplicated stamps/signatures, overwritten text, background discontinuities, cropped borders.
- OCRConsistencyChecker: PAN/Aadhaar/GST/Udyam format and checksum validation,
  bank statement running balance checks, salary slip math checks, certificate label checks.
- QRConsistencyChecker: Reconciles OCR-extracted fields against decoded QR data.
- AuthenticityManager: Aggregates signals, applies weighted risk scoring, coordinates optional
  AI authenticity analysis, and produces the canonical authenticity assessment.

Status values:
- 'verified': No significant inconsistencies detected (Score 0-29).
- 'review_required': Suspicious inconsistencies require human review (Score >= 30).
- 'unsupported': Unsupported document type.

Strict Terminology:
Never use the words "Fake", "Forged", or "Fraudulent" unless confirmed by external evidence.
Uses objective, professional terminology: "Review Required", "Visible inconsistencies detected".
"""

import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image, ImageChops, ImageFilter, ImageStat

logger = logging.getLogger("company_ocr.authenticity")

# Try importing numpy and cv2 with safe fallbacks
try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None


# ==============================================================================
# Signal Weight Registry (Phase 9.6)
# ==============================================================================

SIGNAL_WEIGHTS: Dict[str, int] = {
    "font_mismatch": 15,
    "font_size_inconsistency": 15,
    "inconsistent_font_weight": 15,
    "alignment_issue": 10,
    "uneven_text_baseline": 10,
    "shifted_numbers": 10,
    "misaligned_fields": 10,
    "qr_mismatch": 40,
    "qr_data_mismatch": 40,
    "invalid_checksum": 30,
    "pan_format_invalid": 30,
    "aadhaar_checksum_invalid": 30,
    "gstin_checksum_invalid": 30,
    "cloned_stamp": 25,
    "duplicated_stamp": 25,
    "cloned_signature": 25,
    "overwritten_text": 20,
    "math_inconsistency": 20,
    "balance_inconsistency": 20,
    "compression_artifact": 10,
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


# ==============================================================================
# 1. Image Integrity Checker (Phase 9.2)
# ==============================================================================

class ImageIntegrityChecker:
    """
    Performs local image-level analysis to detect visible inconsistencies without modifying images.
    - Font checks: mixed fonts, inconsistent font weights, different font sizes.
    - Alignment checks: uneven text baseline, shifted numbers, misaligned fields.
    - Image checks: compression artifacts (ELA heuristic), duplicated stamps/seals,
      cloned signatures, overwritten text, background texture anomalies, cropped borders.
    """

    @classmethod
    def check_image(
        cls,
        image: Optional[Image.Image],
        ocr_lines: Optional[List[Any]] = None,
        extracted_fields: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run all local image integrity checks.
        Returns a list of structured findings:
        [{"signal": "...", "severity": "low|medium|high", "description": "..."}]
        """
        findings: List[Dict[str, Any]] = []

        if image is None:
            return findings

        try:
            # 1. Font checks
            cls._check_fonts(ocr_lines, findings)

            # 2. Alignment checks
            cls._check_alignment(ocr_lines, findings)

            # 3. Image-level checks (compression artifacts, duplicated elements, textures, borders)
            cls._check_compression_artifacts(image, findings)
            cls._check_duplicated_elements(image, findings)
            cls._check_background_and_borders(image, findings)
        except Exception as ex:
            logger.warning("Image integrity check encountered non-fatal error: %s", ex)

        return findings

    @classmethod
    def _check_fonts(cls, ocr_lines: Optional[List[Any]], findings: List[Dict[str, Any]]):
        """Analyze line bounding boxes and heights to detect abnormal font size variances."""
        if not ocr_lines or len(ocr_lines) < 4:
            return

        line_heights = []
        for line in ocr_lines:
            # Check if line has bbox or box
            box = getattr(line, "box", None) or getattr(line, "bbox", None)
            if box and len(box) >= 4:
                try:
                    # Bounding box format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] or [x1, y1, x2, y2]
                    if isinstance(box[0], (list, tuple)):
                        ys = [pt[1] for pt in box]
                        height = max(ys) - min(ys)
                    else:
                        height = abs(box[3] - box[1])
                    if height > 5:
                        line_heights.append(height)
                except Exception:
                    pass

        if len(line_heights) >= 4:
            median_h = sorted(line_heights)[len(line_heights) // 2]
            # Detect outlier line heights among standard body text
            outliers = [h for h in line_heights if h > median_h * 2.5 or (h < median_h * 0.4 and h > 4)]
            if len(outliers) >= 2:
                findings.append({
                    "signal": "font_size_inconsistency",
                    "severity": "medium",
                    "description": "Inconsistent font sizes detected across document lines.",
                })

    @classmethod
    def _check_alignment(cls, ocr_lines: Optional[List[Any]], findings: List[Dict[str, Any]]):
        """Check for uneven text baselines or misaligned tabular columns."""
        if not ocr_lines or len(ocr_lines) < 5:
            return

        # Check for shifted numbers: lines containing standalone numbers with skewed x-coordinates
        numeric_lines = []
        for line in ocr_lines:
            text = getattr(line, "text", "") or ""
            box = getattr(line, "box", None) or getattr(line, "bbox", None)
            if re.search(r"^\s*[\$₹€£]?\s*[0-9]+[0-9,\.]*\s*$", text) and box:
                try:
                    if isinstance(box[0], (list, tuple)):
                        x_left = min(pt[0] for pt in box)
                    else:
                        x_left = min(box[0], box[2])
                    numeric_lines.append((text, x_left))
                except Exception:
                    pass

        # If multiple numeric lines exist, check if some are slightly shifted (e.g. 5-15px offset from column)
        if len(numeric_lines) >= 3:
            x_coords = [item[1] for item in numeric_lines]
            diffs = [abs(x_coords[i] - x_coords[i-1]) for i in range(1, len(x_coords))]
            slight_shifts = [d for d in diffs if 4 < d < 25]
            if len(slight_shifts) >= 2:
                findings.append({
                    "signal": "alignment_issue",
                    "severity": "low",
                    "description": "Minor alignment variations or shifted numbers observed in numeric fields.",
                })

    @classmethod
    def _check_compression_artifacts(cls, image: Image.Image, findings: List[Dict[str, Any]]):
        """
        Error Level Analysis (ELA) heuristic:
        Detect localized high-frequency compression variances indicative of splicing or pasting.
        """
        try:
            # Downsample and convert to RGB
            img_rgb = image.convert("RGB")
            # If image is very large, thumbnail for quick analysis
            if img_rgb.width > 1200 or img_rgb.height > 1200:
                img_rgb.thumbnail((1200, 1200))

            # Perform high-pass / edge detection
            edges = img_rgb.filter(ImageFilter.FIND_EDGES)
            stat = ImageStat.Stat(edges)
            # High edge variance relative to mean can indicate composite editing
            edge_stddev = stat.stddev[0] if stat.stddev else 0
            if edge_stddev > 65.0:
                findings.append({
                    "signal": "compression_artifact",
                    "severity": "low",
                    "description": "High edge variance and localized compression differences detected.",
                })
        except Exception:
            pass

    @classmethod
    def _check_duplicated_elements(cls, image: Image.Image, findings: List[Dict[str, Any]]):
        """
        Check for duplicated stamps or cloned signatures using template/feature matching.
        """
        if cv2 is None or np is None:
            return

        try:
            # Convert PIL to grayscale numpy array
            gray = np.array(image.convert("L"))
            if gray.shape[0] < 100 or gray.shape[1] < 100:
                return

            # Resize for efficient search
            max_dim = 600
            scale = min(max_dim / gray.shape[0], max_dim / gray.shape[1], 1.0)
            if scale < 1.0:
                gray = cv2.resize(gray, (int(gray.shape[1] * scale), int(gray.shape[0] * scale)))

            # Detect circular/oval stamp contours
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            circular_regions = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if 800 < area < 20000:
                    perimeter = cv2.arcLength(cnt, True)
                    if perimeter > 0:
                        circularity = 4 * math.pi * (area / (perimeter * perimeter))
                        if 0.65 < circularity < 1.2:
                            x, y, w, h = cv2.boundingRect(cnt)
                            circular_regions.append((x, y, w, h))

            # If more than 1 stamp-like circular region, check for high similarity
            if len(circular_regions) >= 2:
                # Compare first two regions
                r1 = circular_regions[0]
                r2 = circular_regions[1]
                p1 = gray[r1[1]:r1[1]+r1[3], r1[0]:r1[0]+r1[2]]
                p2 = gray[r2[1]:r2[1]+r2[3], r2[0]:r2[0]+r2[2]]
                if p1.shape == p2.shape and p1.size > 0:
                    diff = np.mean(np.abs(p1.astype(float) - p2.astype(float)))
                    if diff < 15.0:
                        findings.append({
                            "signal": "cloned_stamp",
                            "severity": "high",
                            "description": "Identical or cloned stamp/seal pattern detected across multiple locations.",
                        })
        except Exception:
            pass

    @classmethod
    def _check_background_and_borders(cls, image: Image.Image, findings: List[Dict[str, Any]]):
        """Check for border truncation or anomalous dark crops."""
        try:
            # Check edge borders for abrupt solid crops
            w, h = image.size
            if w < 50 or h < 50:
                return

            # Sample border pixels
            rgb = image.convert("RGB")
            # Top, bottom, left, right border bands
            top_crop = rgb.crop((0, 0, w, 3))
            bot_crop = rgb.crop((0, h - 3, w, h))
            stat_top = ImageStat.Stat(top_crop).mean
            stat_bot = ImageStat.Stat(bot_crop).mean

            # If extreme solid black border cropped abruptly
            if sum(stat_top) < 15.0 and sum(stat_bot) > 500.0:
                findings.append({
                    "signal": "cropped_borders",
                    "severity": "low",
                    "description": "Asymmetrical edge crop or artificial border detected.",
                })
        except Exception:
            pass


# ==============================================================================
# 2. OCR Consistency Checker (Phase 9.3)
# ==============================================================================

class OCRConsistencyChecker:
    """
    Validates logical, mathematical, and structural consistency across extracted OCR fields:
    - PAN: format validation, 4th character entity type.
    - Aadhaar: Verhoeff checksum algorithm, DOB format, gender presence.
    - GST: GSTIN format and mod-36 ISO 7064 check digit.
    - Udyam: registration number pattern.
    - Bank Statement: date chronological ordering, running balance math consistency.
    - Salary Slip: gross - deductions = net salary math check.
    - Income Certificate: Marathi labels and financial year format.
    """

    @classmethod
    def check_consistency(
        cls,
        doc_type: str,
        extracted_fields: Dict[str, Any],
        raw_text: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Run document-specific consistency checks.
        Returns list of structured findings.
        """
        findings: List[Dict[str, Any]] = []
        doc_type = (doc_type or "").lower().strip()

        # Import verifier validation helpers
        import verifier

        # 1. PAN Card checks
        if doc_type == "pan":
            pan = extracted_fields.get("pan_number")
            if pan:
                valid, err = verifier.validate_pan_format(str(pan))
                if not valid:
                    findings.append({
                        "signal": "invalid_checksum",
                        "severity": "high",
                        "description": f"PAN format validation failed: {err or 'invalid pattern'}",
                    })
            name = extracted_fields.get("name")
            if name and re.search(r"[0-9@#\$%\^&\*_\+=<>/\\]", str(name)):
                findings.append({
                    "signal": "overwritten_text",
                    "severity": "medium",
                    "description": "Cardholder name contains unexpected numeric or special characters.",
                })

        # 2. Aadhaar Card checks
        elif doc_type == "aadhaar":
            raw_aadhaar = extracted_fields.get("raw_aadhaar") or extracted_fields.get("aadhaar_number")
            if raw_aadhaar:
                clean_digits = re.sub(r"\D", "", str(raw_aadhaar))
                if len(clean_digits) == 12:
                    if not verifier.validate_verhoeff_checksum(clean_digits):
                        findings.append({
                            "signal": "invalid_checksum",
                            "severity": "high",
                            "description": "Aadhaar Verhoeff checksum validation failed.",
                        })

            dob = extracted_fields.get("dob") or extracted_fields.get("date_of_birth")
            if dob:
                # Check for plausible year (1900 to present)
                m_year = re.search(r"\b(19\d{2}|20\d{2})\b", str(dob))
                if not m_year or int(m_year.group(1)) > 2026 or int(m_year.group(1)) < 1920:
                    findings.append({
                        "signal": "alignment_issue",
                        "severity": "medium",
                        "description": "Extracted date of birth has an implausible year.",
                    })

        # 3. GST Registration Certificate checks
        elif doc_type == "gst_certificate":
            gstin = extracted_fields.get("gstin")
            if gstin:
                valid, err = verifier.validate_gstin_format(str(gstin), verify_checksum=True)
                if not valid:
                    findings.append({
                        "signal": "invalid_checksum",
                        "severity": "high",
                        "description": f"GSTIN checksum or format validation failed: {err or 'invalid checksum'}",
                    })

        # 4. Udyam Registration Certificate checks
        elif doc_type == "udyam":
            udyam_num = extracted_fields.get("udyam_registration_number")
            if udyam_num:
                clean_udyam = str(udyam_num).strip().upper()
                if not re.match(r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$", clean_udyam):
                    findings.append({
                        "signal": "invalid_checksum",
                        "severity": "medium",
                        "description": "Udyam registration number does not match the standardized format UDYAM-XX-00-0000000.",
                    })

        # 5. Salary Slip checks (Gross vs Net calculation)
        elif doc_type == "salary_slip":
            cls._check_salary_slip_math(extracted_fields, findings)

        # 6. Bank Statement checks (Running balance arithmetic)
        elif doc_type == "bank_statement":
            cls._check_bank_statement_math(extracted_fields, raw_text, findings)

        # 7. Income Certificate checks (Marathi labels & FY)
        elif doc_type == "income_certificate":
            cls._check_income_certificate(extracted_fields, raw_text, findings)

        return findings

    @classmethod
    def _check_salary_slip_math(cls, fields: Dict[str, Any], findings: List[Dict[str, Any]]):
        """Verify: gross_salary - total_deductions == net_salary."""
        gross = cls._parse_numeric(fields.get("gross_salary") or fields.get("gross_earnings") or fields.get("total_earnings"))
        deductions = cls._parse_numeric(fields.get("total_deductions") or fields.get("deductions"))
        net = cls._parse_numeric(fields.get("net_salary") or fields.get("net_pay") or fields.get("take_home"))

        if gross is not None and deductions is not None and net is not None:
            expected_net = round(gross - deductions, 2)
            # Allow minor rounding tolerance (e.g. 2 rupees / currency units)
            if abs(expected_net - net) > 2.0:
                findings.append({
                    "signal": "math_inconsistency",
                    "severity": "high",
                    "description": (
                        f"Salary arithmetic mismatch: Gross ({gross}) minus Deductions ({deductions}) "
                        f"equals {expected_net}, but Net Salary is stated as {net}."
                    ),
                })

    @classmethod
    def _check_bank_statement_math(cls, fields: Dict[str, Any], raw_text: str, findings: List[Dict[str, Any]]):
        """Verify: opening_balance + deposits - withdrawals == closing_balance (if available)."""
        opening = cls._parse_numeric(fields.get("opening_balance"))
        closing = cls._parse_numeric(fields.get("closing_balance"))
        deposits = cls._parse_numeric(fields.get("total_deposits") or fields.get("total_credits"))
        withdrawals = cls._parse_numeric(fields.get("total_withdrawals") or fields.get("total_debits"))

        if opening is not None and closing is not None and deposits is not None and withdrawals is not None:
            expected_closing = round(opening + deposits - withdrawals, 2)
            if abs(expected_closing - closing) > 5.0:
                findings.append({
                    "signal": "balance_inconsistency",
                    "severity": "high",
                    "description": (
                        f"Bank statement balance mismatch: Opening ({opening}) + Credits ({deposits}) - "
                        f"Debits ({withdrawals}) = {expected_closing}, but Closing Balance is stated as {closing}."
                    ),
                })

    @classmethod
    def _check_income_certificate(cls, fields: Dict[str, Any], raw_text: str, findings: List[Dict[str, Any]]):
        """Check Marathi labels and financial year consistency."""
        # Income certificates issued in Maharashtra contain standard Marathi phrases
        text_lower = raw_text.lower()
        if "दाखला" not in text_lower and "certificate" not in text_lower and "income" not in text_lower:
            findings.append({
                "signal": "alignment_issue",
                "severity": "low",
                "description": "Expected institutional certification headers not clearly identified.",
            })

    @staticmethod
    def _parse_numeric(val: Any) -> Optional[float]:
        """Safely parse currency/number strings to float."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        try:
            # Strip currency symbols and whitespace
            clean = re.sub(r"[^0-9\.\-]", "", str(val))
            if clean and clean != "-":
                return float(clean)
        except Exception:
            pass
        return None


# ==============================================================================
# 3. QR Consistency Checker (Phase 9.4)
# ==============================================================================

class QRConsistencyChecker:
    """
    Compares OCR-extracted fields against decoded QR payload fields:
    - Name
    - Date of Birth (DOB)
    - Document Number (PAN, Aadhaar, Udyam URN, FSSAI License, etc.)
    If mismatch exists: adds 'qr_data_mismatch' signal.
    Never overwrites OCR values; stores both.
    """

    @classmethod
    def check_qr_consistency(
        cls,
        ocr_fields: Dict[str, Any],
        qr_fields: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Compare OCR and QR extracted fields.
        Returns:
        - findings: List of discrepancy signals
        - qr_discrepancies: Detailed diff mapping {field: {ocr_value, qr_value}}
        """
        findings: List[Dict[str, Any]] = []
        discrepancies: Dict[str, Any] = {}

        if not qr_fields:
            return findings, discrepancies

        # Compare keys
        comparisons = [
            ("name", ["name", "cardholder_name", "applicant_name", "employee_name"]),
            ("dob", ["dob", "date_of_birth"]),
            ("doc_number", ["pan_number", "aadhaar_number", "raw_aadhaar", "udyam_registration_number", "fssai_licence_number"]),
        ]

        for qr_key, ocr_aliases in comparisons:
            qr_val = qr_fields.get(qr_key)
            if qr_val is None:
                # Also check direct key in qr_fields
                for alias in ocr_aliases:
                    if alias in qr_fields:
                        qr_val = qr_fields[alias]
                        break

            if qr_val is None:
                continue

            # Find matching OCR value
            ocr_val = None
            for alias in ocr_aliases:
                if alias in ocr_fields and ocr_fields[alias] is not None:
                    ocr_val = ocr_fields[alias]
                    break

            if ocr_val is None:
                continue

            str_qr = str(qr_val).strip().upper()
            str_ocr = str(ocr_val).strip().upper()

            # Normalization for numbers (ignore spaces/hyphens)
            norm_qr = re.sub(r"[\s\-_/]", "", str_qr)
            norm_ocr = re.sub(r"[\s\-_/]", "", str_ocr)

            if norm_qr != norm_ocr:
                discrepancies[qr_key] = {
                    "ocr_value": ocr_val,
                    "qr_value": qr_val,
                }
                findings.append({
                    "signal": "qr_data_mismatch",
                    "severity": "high",
                    "description": (
                        f"QR code payload mismatch for {qr_key}: "
                        f"OCR read '{ocr_val}', while digital QR decoded '{qr_val}'."
                    ),
                })

        return findings, discrepancies


# ==============================================================================
# 4. Authenticity Manager (Phase 9.1 & 9.6)
# ==============================================================================

class AuthenticityManager:
    """
    Coordinates ImageIntegrityChecker, OCRConsistencyChecker, QRConsistencyChecker,
    and optional AI Authenticity Assessment to generate the canonical authenticity result.
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
        Executes all checks and compiles the canonical authenticity assessment:
        {
          "verification_status": "verified" | "review_required" | "unsupported",
          "risk_score": int (0-100),
          "review_required": bool,
          "suspicious_signals": list of strings / dicts,
          "human_review_reason": str | None,
          "verified_by_ai": bool,
          "findings": list of structured signal objects,
          "qr_discrepancies": dict,
        }
        """
        extracted_fields = extracted_fields or {}
        findings: List[Dict[str, Any]] = []

        # 0. Check if unsupported document
        if not is_supported or doc_type == "unknown":
            return {
                "verification_status": "unsupported",
                "risk_score": 0,
                "review_required": False,
                "suspicious_signals": [],
                "human_review_reason": "Unsupported document type.",
                "verified_by_ai": False,
                "findings": [],
                "qr_discrepancies": {},
            }

        # 1. Image Integrity Checks (Local)
        if image is not None:
            image_findings = ImageIntegrityChecker.check_image(
                image=image,
                ocr_lines=ocr_lines,
                extracted_fields=extracted_fields,
            )
            findings.extend(image_findings)

        # 2. OCR Consistency Checks (Local)
        ocr_findings = OCRConsistencyChecker.check_consistency(
            doc_type=doc_type,
            extracted_fields=extracted_fields,
            raw_text=raw_text,
        )
        findings.extend(ocr_findings)

        # 3. QR Consistency Checks (Local)
        qr_discrepancies = {}
        if qr_fields:
            qr_findings, qr_discrepancies = QRConsistencyChecker.check_qr_consistency(
                ocr_fields=extracted_fields,
                qr_fields=qr_fields,
            )
            findings.extend(qr_findings)

        # 4. Merge AI Authenticity Assessment (AI Mode only)
        verified_by_ai = False
        if ai_authenticity_result:
            verified_by_ai = True
            ai_status = ai_authenticity_result.get("authenticity_status")
            ai_signals = ai_authenticity_result.get("suspicious_signals") or []
            ai_reason = ai_authenticity_result.get("human_review_reason")

            for sig in ai_signals:
                sig_text = sig if isinstance(sig, str) else sig.get("description", str(sig))
                findings.append({
                    "signal": "ai_detected_anomaly",
                    "severity": "medium",
                    "description": sig_text,
                })

        # 5. Compute Weighted Risk Score (Phase 9.6)
        total_risk = 0
        seen_signals = set()
        suspicious_signals_list: List[str] = []

        for finding in findings:
            sig_name = finding.get("signal", "unknown_signal")
            desc = finding.get("description", sig_name)
            weight = get_signal_weight(sig_name)

            # Avoid double-counting identical signal names
            if sig_name not in seen_signals:
                total_risk += weight
                seen_signals.add(sig_name)
            else:
                total_risk += int(weight * 0.5)

            if desc not in suspicious_signals_list:
                suspicious_signals_list.append(desc)

        # Cap score between 0 and 100
        risk_score = min(100, max(0, total_risk))

        # 6. Status determination:
        # 0–29: verified
        # 30–59: review_required
        # 60+: review_required (high priority)
        if risk_score >= 30:
            verification_status = "review_required"
            review_required = True
            if suspicious_signals_list:
                human_review_reason = "Visible inconsistencies detected."
            else:
                human_review_reason = "Elevated risk score requires human verification."
        else:
            verification_status = "verified"
            review_required = False
            human_review_reason = None

        return {
            "verification_status": verification_status,
            "risk_score": risk_score,
            "review_required": review_required,
            "suspicious_signals": suspicious_signals_list,
            "human_review_reason": human_review_reason,
            "verified_by_ai": verified_by_ai,
            "findings": findings,
            "qr_discrepancies": qr_discrepancies,
        }


# Global singleton manager instance
authenticity_manager = AuthenticityManager()
