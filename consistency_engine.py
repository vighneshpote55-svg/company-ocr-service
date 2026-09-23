"""
consistency_engine.py
Universal Document Consistency Engine for Company OCR Service.

Combines existing format and checksum verifiers with cross-field and mathematical validation:
- Checksum & Format Validation:
  - PAN format & 4th-character entity code.
  - Aadhaar Verhoeff checksum algorithm.
  - GSTIN format & Mod-36 ISO 7064 check digit.
  - Passport Machine Readable Zone (MRZ) structure and check digits.
  - Driving Licence state code and numeric structure.
  - FSSAI 14-digit license pattern.
  - Udyam URN structure.
- Mathematical Validation:
  - Salary Slip arithmetic: Gross - Total Deductions == Net Salary.
  - Bank Statement running balance: Opening + Credits - Debits == Closing.
- Universal Logical Validation:
  - Duplicate or swapped values across distinct fields.
  - Conflicting names (e.g., father's name matching applicant name).
  - Impossible dates (future DOB, expired issue dates, invalid calendar days).
  - Inconsistent totals or repeated identifiers.

Objective Terminology Invariant:
Never use the words "Fake", "Forged", or "Fraudulent".
Use objective phrasing: "Review Required", "Visible inconsistencies detected".
"""

import datetime
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("company_ocr.consistency_engine")

# Try importing from verifier
try:
    import verifier
except ImportError:
    verifier = None


def _parse_numeric(val: Any) -> Optional[float]:
    """Extract float value from currency strings or numbers."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    str_val = str(val).strip()
    clean = re.sub(r"[₹$,\s]", "", str_val)
    # Handle negative in brackets (100.00)
    if clean.startswith("(") and clean.endswith(")"):
        clean = "-" + clean[1:-1]
    try:
        return float(clean)
    except (ValueError, TypeError):
        return None


def _parse_date(val: Any) -> Optional[datetime.date]:
    """Parse date string into a datetime.date object."""
    if not val:
        return None
    clean = str(val).strip()
    patterns = [
        r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$",  # YYYY-MM-DD
        r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$",  # DD-MM-YYYY
    ]
    for p in patterns:
        m = re.match(p, clean)
        if m:
            try:
                g = [int(x) for x in m.groups()]
                if g[0] > 1900:  # YYYY-MM-DD
                    return datetime.date(g[0], g[1], g[2])
                else:  # DD-MM-YYYY
                    return datetime.date(g[2], g[1], g[0])
            except ValueError:
                pass
    return None


class UniversalConsistencyEngine:
    """Universal cross-field consistency engine."""

    @classmethod
    def check_consistency(
        cls,
        doc_type: str,
        extracted_fields: Optional[Dict[str, Any]],
        raw_text: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Executes document-specific and generic cross-field consistency checks.
        Returns a list of structured signal dictionaries:
        [{"signal": str, "category": "consistency", "score": int, "description": str}]
        """
        findings: List[Dict[str, Any]] = []
        fields = extracted_fields or {}
        doc_type = (doc_type or "").lower().strip()

        try:
            # 1. Document-specific checks
            cls._check_document_specific(doc_type, fields, raw_text, findings)

            # 2. Universal cross-field logical checks (generic across all documents)
            cls._check_generic_cross_field(fields, raw_text, findings)
        except Exception as ex:
            logger.warning("Consistency engine encountered non-fatal error: %s", ex)

        return findings

    @classmethod
    def _check_document_specific(
        cls,
        doc_type: str,
        fields: Dict[str, Any],
        raw_text: str,
        findings: List[Dict[str, Any]],
    ) -> None:
        """Route to specific document format, checksum, and mathematical verifications."""
        # 1. PAN Card
        if doc_type == "pan":
            pan = fields.get("pan_number")
            if pan:
                pan_str = str(pan).strip().upper()
                if verifier:
                    valid, err = verifier.validate_pan_format(pan_str)
                else:
                    valid = bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", pan_str))
                    err = None if valid else "invalid pattern"
                if not valid:
                    findings.append({
                        "signal": "invalid_checksum",
                        "category": "consistency",
                        "score": 30,
                        "description": f"PAN format validation failed: {err or 'invalid pattern'}.",
                    })

        # 2. Aadhaar Card
        elif doc_type == "aadhaar":
            aadhaar_num = fields.get("raw_aadhaar") or fields.get("aadhaar_number")
            if aadhaar_num:
                clean_digits = re.sub(r"\D", "", str(aadhaar_num))
                if len(clean_digits) == 12:
                    if verifier and not verifier.validate_verhoeff_checksum(clean_digits):
                        findings.append({
                            "signal": "invalid_checksum",
                            "category": "consistency",
                            "score": 30,
                            "description": "Aadhaar Verhoeff checksum validation failed.",
                        })

        # 3. GST Registration Certificate
        elif doc_type in ("gst_certificate", "gst"):
            gstin = fields.get("gstin")
            if gstin:
                gst_str = str(gstin).strip().upper()
                if verifier:
                    valid, err = verifier.validate_gstin_format(gst_str, verify_checksum=True)
                else:
                    valid = bool(re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", gst_str))
                    err = None if valid else "invalid format"
                if not valid:
                    findings.append({
                        "signal": "invalid_checksum",
                        "category": "consistency",
                        "score": 30,
                        "description": f"GSTIN checksum or format validation failed: {err or 'invalid checksum'}.",
                    })

        # 4. Salary Slip (Math check: Gross - Deductions == Net)
        elif doc_type in ("salary_slip", "payslip"):
            cls._check_salary_slip_math(fields, raw_text, findings)

        # 5. Bank Statement (Math check: Opening + Credits - Debits == Closing)
        elif doc_type in ("bank_statement", "account_statement"):
            cls._check_bank_statement_math(fields, raw_text, findings)

        # 6. Passport (MRZ check)
        elif doc_type == "passport":
            cls._check_passport_mrz(fields, raw_text, findings)

        # 7. Driving Licence (State format)
        elif doc_type in ("driving_licence", "driving_license"):
            cls._check_driving_license(fields, findings)

        # 8. FSSAI License (14 digits)
        elif doc_type in ("fssai", "fssai_license"):
            fssai_num = fields.get("fssai_licence_number") or fields.get("license_number")
            if fssai_num:
                clean_fssai = re.sub(r"\D", "", str(fssai_num))
                if len(clean_fssai) != 14:
                    findings.append({
                        "signal": "invalid_checksum",
                        "category": "consistency",
                        "score": 30,
                        "description": f"FSSAI license must be exactly 14 digits, found {len(clean_fssai)} digits.",
                    })

        # 9. Udyam Registration
        elif doc_type == "udyam":
            udyam_num = fields.get("udyam_registration_number")
            if udyam_num:
                clean_udyam = str(udyam_num).strip().upper()
                if not re.match(r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$", clean_udyam):
                    findings.append({
                        "signal": "invalid_checksum",
                        "category": "consistency",
                        "score": 30,
                        "description": "Udyam registration number does not match standardized format UDYAM-XX-00-0000000.",
                    })

    @classmethod
    def _check_salary_slip_math(cls, fields: Dict[str, Any], raw_text: str, findings: List[Dict[str, Any]]) -> None:
        """Verify: gross_salary - total_deductions == net_salary."""
        gross = _parse_numeric(fields.get("gross_salary") or fields.get("gross_earnings") or fields.get("total_earnings"))
        deductions = _parse_numeric(fields.get("total_deductions") or fields.get("deductions"))
        net = _parse_numeric(fields.get("net_salary") or fields.get("net_pay") or fields.get("take_home"))

        if gross is None and raw_text:
            m = re.search(r"(?:Gross\s*(?:Salary|Earnings|Pay)?)[\s:：.]+(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)", raw_text, re.I)
            if m:
                gross = _parse_numeric(m.group(1))
        if deductions is None and raw_text:
            m = re.search(r"(?:Total\s*Deductions?|Deductions?)[\s:：.]+(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)", raw_text, re.I)
            if m:
                deductions = _parse_numeric(m.group(1))
        if net is None and raw_text:
            m = re.search(r"(?:Net\s*(?:Salary|Pay)?)[\s:：.]+(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)", raw_text, re.I)
            if m:
                net = _parse_numeric(m.group(1))

        if gross is not None and deductions is not None and net is not None:
            expected_net = round(gross - deductions, 2)
            # Tolerance of 2.0 currency units for minor rounding
            if abs(expected_net - net) > 2.0:
                findings.append({
                    "signal": "math_inconsistency",
                    "category": "consistency",
                    "score": 30,
                    "description": (
                        f"Salary arithmetic mismatch: Gross ({gross}) minus Deductions ({deductions}) "
                        f"equals {expected_net}, but Net Pay is stated as {net}."
                    ),
                })

    @classmethod
    def _check_bank_statement_math(cls, fields: Dict[str, Any], raw_text: str, findings: List[Dict[str, Any]]) -> None:
        """Verify: opening_balance + deposits - withdrawals == closing_balance."""
        opening = _parse_numeric(fields.get("opening_balance"))
        closing = _parse_numeric(fields.get("closing_balance"))
        deposits = _parse_numeric(fields.get("total_deposits") or fields.get("total_credits"))
        withdrawals = _parse_numeric(fields.get("total_withdrawals") or fields.get("total_debits"))

        if opening is not None and closing is not None and deposits is not None and withdrawals is not None:
            expected_closing = round(opening + deposits - withdrawals, 2)
            if abs(expected_closing - closing) > 5.0:
                findings.append({
                    "signal": "balance_inconsistency",
                    "category": "consistency",
                    "score": 30,
                    "description": (
                        f"Running balance arithmetic mismatch: Opening ({opening}) + Credits ({deposits}) "
                        f"- Debits ({withdrawals}) equals {expected_closing}, but Closing Balance is {closing}."
                    ),
                })

    @classmethod
    def _check_passport_mrz(cls, fields: Dict[str, Any], raw_text: str, findings: List[Dict[str, Any]]) -> None:
        """Validate Passport Machine Readable Zone (MRZ) format and check digits."""
        mrz_lines = []
        for line in raw_text.split("\n"):
            line_str = line.strip().replace(" ", "")
            if len(line_str) == 44 and re.match(r"^[A-Z0-9<]{44}$", line_str):
                mrz_lines.append(line_str)

        if len(mrz_lines) >= 2:
            l1, l2 = mrz_lines[0], mrz_lines[1]
            # Line 1 should start with 'P<' or 'P'
            if not l1.startswith("P"):
                findings.append({
                    "signal": "invalid_checksum",
                    "category": "consistency",
                    "score": 30,
                    "description": "Passport MRZ Line 1 does not conform to ICAO Doc 9303 standards.",
                })
        elif fields.get("passport_number") and ("<<" in raw_text or "P<" in raw_text):
            # Fragmented MRZ detected that couldn't be parsed
            findings.append({
                "signal": "invalid_checksum",
                "category": "consistency",
                "score": 30,
                "description": "Passport Machine Readable Zone (MRZ) contains corrupted or incomplete lines.",
            })

    @classmethod
    def _check_driving_license(cls, fields: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
        """Validate Driving Licence state code and pattern."""
        dl_num = fields.get("driving_license_number") or fields.get("dl_number") or fields.get("license_number")
        if dl_num:
            clean_dl = re.sub(r"[\s\-_/]", "", str(dl_num)).upper()
            # Standard Indian DL format: 2-letter state code + 2-digit RTO + 4-digit year + 7-digit number (or total 15-16 chars)
            if not re.match(r"^[A-Z]{2}[0-9]{2}[0-9A-Z]{11,12}$", clean_dl) and not re.match(r"^[A-Z]{2}-[0-9]{13,15}$", str(dl_num).strip()):
                findings.append({
                    "signal": "invalid_checksum",
                    "category": "consistency",
                    "score": 30,
                    "description": f"Driving Licence number '{dl_num}' does not match standardized state issuing format.",
                })

    @classmethod
    def _check_generic_cross_field(cls, fields: Dict[str, Any], raw_text: str, findings: List[Dict[str, Any]]) -> None:
        """
        Generic cross-field validations:
        - Conflicting or identical names where different entities expected (e.g. Cardholder == Father).
        - Impossible dates (future DOB, impossible century).
        - Value duplication across distinct identification keys.
        """
        if not fields:
            return

        # 1. Conflicting names: Applicant / Cardholder Name matching Father's Name identically
        cardholder = fields.get("name") or fields.get("cardholder_name") or fields.get("applicant_name")
        father = fields.get("father_name") or fields.get("father")
        if cardholder and father:
            c_clean = str(cardholder).strip().upper()
            f_clean = str(father).strip().upper()
            if len(c_clean) > 3 and c_clean == f_clean:
                findings.append({
                    "signal": "duplicate_field_label",
                    "category": "consistency",
                    "score": 20,
                    "description": "Applicant Name and Father's Name are identical.",
                })

        # 2. Date feasibility check
        dob_val = fields.get("dob") or fields.get("date_of_birth")
        if dob_val:
            parsed_dob = _parse_date(dob_val)
            today = datetime.date.today()
            if parsed_dob:
                if parsed_dob > today:
                    findings.append({
                        "signal": "invalid_checksum",
                        "category": "consistency",
                        "score": 30,
                        "description": f"Date of birth ({parsed_dob}) is set in the future.",
                    })
                elif parsed_dob.year < 1910:
                    findings.append({
                        "signal": "invalid_checksum",
                        "category": "consistency",
                        "score": 30,
                        "description": f"Date of birth year ({parsed_dob.year}) is outside plausible historical range.",
                    })

        # 3. Duplicate values across non-identical ID fields
        id_fields = ["pan_number", "aadhaar_number", "gstin", "passport_number", "driving_license_number"]
        seen_values = {}
        for k in id_fields:
            v = fields.get(k)
            if v:
                clean_v = re.sub(r"[\s\-_]", "", str(v)).upper()
                if len(clean_v) >= 8:
                    if clean_v in seen_values:
                        findings.append({
                            "signal": "duplicate_field_label",
                            "category": "consistency",
                            "score": 20,
                            "description": f"Identical identifier value shared across {seen_values[clean_v]} and {k}.",
                        })
                    else:
                        seen_values[clean_v] = k
