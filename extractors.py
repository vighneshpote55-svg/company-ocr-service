"""
extractors.py
Domain-specific extractors for 13 document types in Company-Server OCR service:
- PAN, Aadhaar, Cancelled Cheque, Udyam, FSSAI, Shop & Establishment,
  Bank Statement, Salary Slip, Utility Bill, Passport, Voter ID, Driving Licence, ITR.
- Enforces strict PII minimisation allowlists at source.
- Tracks per-field confidence from PaddleOCR lines.
- Handles multi-page table merges for bank statements.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from ocr_engine import OCRDocumentResult, OCRLine


# ==============================================================================
# Helper Masking & Normalization Functions
# ==============================================================================

def mask_account_number(acc: Optional[str]) -> Optional[str]:
    """Mask bank account number leaving only the last 4 digits visible."""
    if not acc:
        return None
    clean = re.sub(r"\D", "", acc)
    if len(clean) >= 4:
        prefix_len = max(6, len(clean) - 4)
        return "X" * prefix_len + clean[-4:]
    return "XXXXXX" + clean


def mask_aadhaar(uid: Optional[str]) -> Optional[str]:
    """Mask Aadhaar number to XXXXXXXX1234."""
    if not uid:
        return None
    clean = re.sub(r"\D", "", uid)
    if len(clean) >= 4:
        return "XXXXXXXX" + clean[-4:]
    return "XXXXXXXX" + clean


def mask_person_name(name: Optional[str]) -> Optional[str]:
    """Partially mask person name if requested (e.g. for salary slip)."""
    if not name:
        return None
    parts = name.strip().split()
    if len(parts) == 1:
        return parts[0][0] + "*" * max(1, len(parts[0]) - 1)
    return parts[0] + " " + parts[-1][0] + "*" * max(1, len(parts[-1]) - 1)


def mask_address(addr: Optional[str]) -> Optional[str]:
    """Partially mask residential or property address to protect PII.
    Redacts specific unit/flat/door/building/street numbers while preserving
    locality, city, state, and postal code for downstream verification.
    """
    if not addr:
        return None
    clean = addr.strip()
    clean = re.sub(r"[ \t]+", " ", clean)

    # If comma-separated address
    parts = [p.strip() for p in clean.split(",") if p.strip()]
    if len(parts) >= 2:
        premise_kw = re.compile(
            r"^(?:flat|plot|house|door|shop|unit|room|bldg|building|wing|tower|block|floor|no\.?|#|\d+)",
            re.IGNORECASE,
        )
        cut_idx = 0
        while cut_idx < len(parts) - 1:
            if premise_kw.search(parts[cut_idx]) or cut_idx == 0:
                cut_idx += 1
                if cut_idx < len(parts) - 1 and re.search(r"^(?:bldg|building|wing|tower|block|floor)\b", parts[cut_idx], re.I):
                    cut_idx += 1
                break
            else:
                break
        preserved = ", ".join(parts[cut_idx:])
        return f"XXXX, {preserved}" if preserved else f"XXXX {clean[-10:]}"

    # Non-comma separated: replace leading unit/door/number
    masked = re.sub(
        r"^(?:(?:flat|plot|house|door|shop|unit|room|bldg|building|no\.?|#)\s*)?[0-9A-Za-z\-\/]+(?:\s+(?:road|marg|street|lane|bldg|building|floor))?\s*",
        "XXXX ",
        clean,
        flags=re.IGNORECASE,
    )
    if masked == clean:
        masked = "XXXX " + clean[10:].strip() if len(clean) > 15 else "XXXX"
    return masked.strip()


def find_line_confidence(pattern: str, lines: List[OCRLine], default_conf: float = 0.95) -> float:
    """Find the confidence score of the OCR line matching a specific regex pattern."""
    regex = re.compile(pattern, re.IGNORECASE)
    for line in lines:
        if regex.search(line.text):
            return round(line.confidence, 4)
    return default_conf


# Known field labels that might be captured as residual bleed on a subsequent line
RESIDUAL_LABEL_LINES = {
    "purpose", "sno", "sno.", "s.no", "s.no.", "sr no", "sr. no", "sr.no",
    "classification year", "enterprise type", "type of enterprise", "major activity",
    "social category", "date of incorporation", "date of commencement",
    "permanent account number", "pan", "date of birth", "dob", "father's name", "father name",
    "mother's name", "husband's name", "address", "status", "form number",
    "acknowledgement number", "assessment year", "ay", "total income", "taxes paid",
    "gender", "sex", "nationality", "expiry date", "date of expiry", "issue date", "date of issue",
    "valid till", "valid from", "kind of business", "nature of business", "registration number",
    "reg no", "licence number", "license number", "fssai licence number",
    "ifsc", "ifsc code", "branch", "bank name", "account number", "account holder",
    "consumer number", "bill date", "due date", "bill amount", "total amount",
    "current year business loss", "book profit", "net tax payable",
    "gstin", "trade name", "legal name", "constitution of business", "date of registration",
    "corporate identity number", "cin", "registrar of companies", "company name",
    "partnership deed", "firm name", "partner", "partner name", "profit sharing ratio",
    "lessor", "lessee", "landlord", "tenant", "monthly rent", "security deposit", "lease period",
    "gross salary", "tax deducted", "tan", "tan number", "employer name", "employee name",
    "passbook", "account holder name", "cif no", "customer id",
    "property id", "property tax", "tax paid", "assessment no", "tax amount",
    "iec", "iec number", "importer exporter code", "dgft", "entity name",
}


import logging
logger = logging.getLogger(__name__)


def clean_field_value(val: Any, field_name: Optional[str] = None, doc_type: Optional[str] = None) -> Any:
    """
    Sanitize extracted field value to prevent boundary bleeds into subsequent field labels:
    1. Cut off at first double newline.
    2. Discard subsequent lines if they match known section/field headers.
    3. Strip trailing whitespace and colons/dashes.
    4. Structured logging (NO PII) when trimming occurs, with warning on suspicious leftovers.
    """
    if not isinstance(val, str):
        if isinstance(val, list):
            return [clean_field_value(item, field_name=field_name, doc_type=doc_type) for item in val]
        return val
    # 1. Immediately cut off at double newline (multi-field gap in OCR/PDF text)
    first_block = re.split(r"\r?\n\s*\r?\n", val.strip())[0].strip()
    if not first_block:
        if val.strip():
            logger.info(
                "clean_field_value trimmed residual bleed: field=%s doc_type=%s",
                field_name or "unknown",
                doc_type or "unknown",
            )
        return ""

    # 2. Inspect individual lines
    lines = [l.strip() for l in first_block.splitlines() if l.strip()]
    if not lines:
        return ""

    cleaned_lines = [lines[0]]
    for line in lines[1:]:
        norm = re.sub(r"[:\-_.]", " ", line).strip().lower()
        norm_words = norm.split()

        is_label = False
        if norm in RESIDUAL_LABEL_LINES:
            is_label = True
        else:
            for lbl in RESIDUAL_LABEL_LINES:
                if norm == lbl or norm.startswith(lbl + " ") or (len(norm_words) <= 3 and lbl in norm):
                    is_label = True
                    break
        if is_label:
            break
        cleaned_lines.append(line)

    res = " ".join(cleaned_lines).strip()
    # Strip any trailing colons, hyphens, or commas
    res = re.sub(r"[\s,:;\-]+$", "", res).strip()

    # Log when clean_field_value actually trims something (no PII: field name and doc_type only)
    if res != val:
        logger.info(
            "clean_field_value trimmed residual bleed: field=%s doc_type=%s",
            field_name or "unknown",
            doc_type or "unknown",
        )

    # Suspicious leftover check (contains newline or unusually long > 80 chars)
    if "\n" in res or len(res) > 80:
        logger.warning(
            "clean_field_value output suspicious (length=%d, has_newline=%s): field=%s doc_type=%s",
            len(res),
            "\n" in res,
            field_name or "unknown",
            doc_type or "unknown",
        )

    return res


# ==============================================================================
# 1. PAN Extractor
# ==============================================================================

def extract_pan(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # PAN Number pattern: 5 letters, 4 digits, 1 letter
    pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text)
    if pan_match:
        fields["pan_number"] = pan_match.group(1)
        confidences["pan_number"] = find_line_confidence(pan_match.group(1), all_lines)

    # DOB pattern: DD/MM/YYYY
    dob_match = re.search(r"\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b", text)
    if dob_match:
        fields["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        confidences["dob"] = find_line_confidence(r"\b\d{2}[/\-\.]\d{2}[/\-\.]\d{4}\b", all_lines)

    # Name extraction
    name_match = re.search(
        r"(?:Name|NAME)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Father|DOB|Date|Permanent|PAN|Purpose)\b))",
        text,
        re.IGNORECASE,
    )
    if name_match:
        cand = clean_field_value(name_match.group(1))
        if not re.search(r"^(?:Father|DOB|Date|Permanent|PAN|Purpose|Demo Value|Field)\b", cand, re.I):
            fields["name"] = cand
            confidences["name"] = find_line_confidence(fields["name"], all_lines)

    # Father's Name
    father_match = re.search(
        r"(?:Father['’]?s?\s*Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Purpose|DOB|Date|Name|Permanent|PAN)\b))",
        text,
        re.IGNORECASE,
    )
    if father_match:
        cand = clean_field_value(father_match.group(1))
        if not re.search(r"^(?:Purpose|DOB|Date|Name|Permanent|PAN)\b", cand, re.I):
            fields["father_name"] = cand
            confidences["father_name"] = find_line_confidence(fields["father_name"], all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 2. Aadhaar Extractor (with Masking & PII Strip)
# ==============================================================================

def extract_aadhaar(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Check for Aadhaar number pattern: 4 digits + 4 digits + 4 digits, or masked XXXX XXXX 1234
    uid_match = re.search(r"\b(\d{4}\s\d{4}\s\d{4}|\d{12})\b", text)
    masked_match = re.search(r"\b([X\d]{4}\s[X\d]{4}\s\d{4})\b", text, re.IGNORECASE)

    raw_uid = None
    if uid_match:
        raw_uid = uid_match.group(1).replace(" ", "")
        fields["raw_aadhaar"] = raw_uid  # Used internally by verifier, stripped before output
        masked_val = mask_aadhaar(raw_uid)
        fields["aadhaar_number"] = masked_val
        fields["aadhaar_number_masked"] = masked_val
        conf = find_line_confidence(r"\d{4}\s\d{4}\s\d{4}|\d{12}", all_lines)
        confidences["aadhaar_number"] = conf
        confidences["aadhaar_number_masked"] = conf
    elif masked_match:
        masked_val = masked_match.group(1).upper()
        fields["aadhaar_number"] = masked_val
        fields["aadhaar_number_masked"] = masked_val
        conf = find_line_confidence(r"[X\d]{4}\s[X\d]{4}\s\d{4}", all_lines)
        confidences["aadhaar_number"] = conf
        confidences["aadhaar_number_masked"] = conf

    # Name
    name_match = re.search(
        r"(?:Name)[\s:]*(?:\r?\n)?[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Aadhaar|DOB|Date|Gender|Address|Father|Mother|Husband|Year|YOB)\b))",
        text,
        re.IGNORECASE,
    )
    if name_match:
        cand = clean_field_value(name_match.group(1))
        if not re.search(r"^(?:Aadhaar|DOB|Gender|Address|Date|Year|YOB)\b", cand, re.I):
            fields["name"] = cand
            confidences["name"] = find_line_confidence(fields["name"], all_lines)

    # DOB / Year of Birth
    dob_match = re.search(r"(?:DOB|Date of Birth)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if dob_match:
        fields["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        confidences["dob"] = find_line_confidence(dob_match.group(1), all_lines)
    else:
        yob_match = re.search(r"(?:Year of Birth|YOB)[\s:]+(\d{4})", text, re.IGNORECASE)
        if yob_match:
            fields["dob"] = yob_match.group(1)
            confidences["dob"] = find_line_confidence(yob_match.group(1), all_lines)

    # Gender
    gender_match = re.search(r"\b(MALE|FEMALE|TRANSGENDER)\b", text, re.IGNORECASE)
    if gender_match:
        fields["gender"] = gender_match.group(1).capitalize()
        confidences["gender"] = find_line_confidence(gender_match.group(1), all_lines)

    # NOTE: Address is intentionally stripped from response to prevent PII leakage.
    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 3. Cancelled Cheque Extractor
# ==============================================================================

def extract_cancelled_cheque(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Marking
    if re.search(r"\bCANCELLED\b", text, re.IGNORECASE):
        fields["marking"] = "CANCELLED"
        confidences["marking"] = 1.0

    # Account Number
    acc_match = re.search(r"(?:A/C\s*No\.?|Account\s*Number)[\s:]*([X\d]{6,18})", text, re.IGNORECASE)
    if acc_match:
        raw_acc = acc_match.group(1)
        fields["account_number_masked"] = mask_account_number(raw_acc)
        confidences["account_number_masked"] = find_line_confidence(raw_acc, all_lines)

    # IFSC
    ifsc_match = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
    if ifsc_match:
        fields["ifsc"] = ifsc_match.group(1)
        confidences["ifsc"] = find_line_confidence(ifsc_match.group(1), all_lines)

    # Bank Name & Branch
    bank_match = re.search(r"(?:Bank\s*Name|Bank)[\s:]*([A-Za-z][A-Za-z \t.&'-]+?BANK)\b", text, re.IGNORECASE)
    if bank_match:
        fields["bank_name"] = clean_field_value(bank_match.group(1))
    branch_match = re.search(
        r"(?:Branch)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,.'-]{1,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:IFSC|IFS|A/C|Account|Cheque|Chq|Payee)\b))",
        text,
        re.IGNORECASE,
    )
    if branch_match:
        fields["branch"] = clean_field_value(branch_match.group(1))

    # Cheque Number
    chq_match = re.search(r"(?:Cheque\s*Number|Chq\s*No)[\s:]*(\d{6})", text, re.IGNORECASE)
    if chq_match:
        fields["cheque_number"] = chq_match.group(1)
        confidences["cheque_number"] = find_line_confidence(chq_match.group(1), all_lines)

    # Account Holder
    holder_match = re.search(
        r"(?:Account\s*Holder|Payee|Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Branch|IFSC|IFS|A/C|Account|Cheque|Chq|CANCELLED)\b))",
        text,
        re.IGNORECASE,
    )
    if holder_match:
        cand = clean_field_value(holder_match.group(1))
        if not re.search(r"^(?:Branch|IFSC|A/C|Account|Cheque|CANCELLED)\b", cand, re.I):
            fields["account_holder"] = cand
            confidences["account_holder"] = find_line_confidence(fields["account_holder"], all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 4. Udyam Registration Extractor
# ==============================================================================

def extract_udyam(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Udyam Registration Number: UDYAM-XX-00-0000000
    urn_match = re.search(r"\b(UDYAM-[A-Z]{2}-\d{2}-\d{7})\b", text, re.IGNORECASE)
    if urn_match:
        fields["udyam_registration_number"] = urn_match.group(1).upper()
        confidences["udyam_registration_number"] = find_line_confidence(urn_match.group(1), all_lines)

    # Enterprise Name
    name_match = re.search(
        r"(?:Enterprise\s*Name|Name of Enterprise)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,60}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:SNo|S\.No|Type of Enterprise|Classification|Major Activity|Social Category|Date|Official Address)\b))",
        text,
        re.IGNORECASE,
    )
    if name_match:
        fields["enterprise_name"] = clean_field_value(name_match.group(1))
        confidences["enterprise_name"] = find_line_confidence(fields["enterprise_name"], all_lines)

    # Type of Enterprise (Micro / Small / Medium)
    type_match = re.search(r"\b(Micro|Small|Medium)\b", text, re.IGNORECASE)
    if type_match:
        fields["enterprise_type"] = type_match.group(1).capitalize()
        confidences["enterprise_type"] = 0.98

    # Major Activity (Services / Manufacturing)
    activity_match = re.search(r"\b(Services|Manufacturing)\b", text, re.IGNORECASE)
    if activity_match:
        fields["major_activity"] = activity_match.group(1).capitalize()
        confidences["major_activity"] = 0.98

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 5. FSSAI Certificate Extractor
# ==============================================================================

def extract_fssai(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # 14-digit FSSAI License Number
    lic_match = re.search(r"\b(\d{14})\b", text)
    if lic_match:
        fields["fssai_licence_number"] = lic_match.group(1)
        confidences["fssai_licence_number"] = find_line_confidence(lic_match.group(1), all_lines)

    # Business Name
    biz_match = re.search(
        r"(?:Business\s*Name|Name of Food Business Operator)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,60}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:FSSAI|Licence|License|Kind of Business|Valid|Period)\b))",
        text,
        re.IGNORECASE,
    )
    if biz_match:
        fields["business_name"] = clean_field_value(biz_match.group(1))
        confidences["business_name"] = find_line_confidence(fields["business_name"], all_lines)

    # Kind of Business
    kind_match = re.search(
        r"(?:Kind of Business)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,50}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Valid|Licence|License|Business Name)\b))",
        text,
        re.IGNORECASE,
    )
    if kind_match:
        fields["kind_of_business"] = clean_field_value(kind_match.group(1))

    # Validity
    valid_from = re.search(r"(?:Valid From)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if valid_from:
        fields["valid_from"] = valid_from.group(1)
    valid_till = re.search(r"(?:Valid Till)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if valid_till:
        fields["valid_till"] = valid_till.group(1)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 6. Shop & Establishment Extractor (Per-State Template Registry)
# ==============================================================================

SHOP_ESTABLISHMENT_STATE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "MH": {
        "state_name": "Maharashtra",
        "state_code": "MH",
        "verified": True,
        "authority_patterns": [
            r"Government\s+of\s+Maharashtra",
            r"Labour\s+Department[,\s]+Maharashtra",
            r"Aaple\s*Sarkar",
            r"Municipal\s+Corporation\s+of\s+Greater\s+Mumbai",
            r"Pune\s+Municipal\s+Corporation",
            r"\bMAHARASHTRA\b",
        ],
        "reg_no_patterns": [
            r"(?:Registration\s*Number|Reg\s*No\.?|Certificate\s*No\.?)[\s:]*([A-Za-z0-9\-\/]{5,30})",
            r"\b(SHOP-[A-Z0-9\-]+)\b",
            r"\b(MH[0-9A-Z\-\/]{6,25})\b",
        ],
        "issuing_authority_default": "Government of Maharashtra",
    },
    "DL": {
        "state_name": "Delhi",
        "state_code": "DL",
        "verified": False,
        "authority_patterns": [
            r"Government\s+of\s+NCT\s+of\s+Delhi",
            r"Labour\s+Department[,\s]+Delhi",
            r"NCT\s+of\s+Delhi",
            r"\bDELHI\b",
        ],
        "reg_no_patterns": [
            r"(?:Registration\s*Number|Reg\s*No\.?|Certificate\s*No\.?)[\s:]*([A-Za-z0-9\-\/]{5,30})",
            r"\b(DL[0-9A-Z\-\/]{5,25})\b",
            r"\b(D-SE\/[0-9A-Z\-\/]+)\b",
        ],
        "issuing_authority_default": "Government of NCT of Delhi",
    },
    "KA": {
        "state_name": "Karnataka",
        "state_code": "KA",
        "verified": False,
        "authority_patterns": [
            r"Government\s+of\s+Karnataka",
            r"Labour\s+Department[,\s]+Karnataka",
            r"e-Karmika",
            r"\bKARNATAKA\b",
            r"\bBENGALURU\b",
            r"\bBANGALORE\b",
        ],
        "reg_no_patterns": [
            r"(?:Registration\s*Number|Reg\s*No\.?|Certificate\s*No\.?)[\s:]*([A-Za-z0-9\-\/]{5,30})",
            r"\b(KA[0-9A-Z\-\/]{5,25})\b",
            r"\b(KSC\/[0-9A-Z\-\/]+)\b",
        ],
        "issuing_authority_default": "Government of Karnataka",
    },
}


def extract_shop_establishment(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # State template detection
    matched_state = None
    for state_code, state_cfg in SHOP_ESTABLISHMENT_STATE_REGISTRY.items():
        for pat in state_cfg["authority_patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                matched_state = state_code
                break
        if matched_state:
            break

    if matched_state:
        cfg = SHOP_ESTABLISHMENT_STATE_REGISTRY[matched_state]
        fields["state"] = matched_state
        fields["state_name"] = cfg["state_name"]
        fields["issuing_authority"] = cfg["issuing_authority_default"]
        fields["template_matched"] = True
        fields["template_verified"] = bool(cfg.get("verified", False))
        confidences["state"] = 0.98
        confidences["template_matched"] = 1.0
        confidences["template_verified"] = 1.0

        # State-specific registration number patterns
        for reg_pat in cfg["reg_no_patterns"]:
            reg_match = re.search(reg_pat, text, re.IGNORECASE)
            if reg_match:
                fields["registration_number"] = reg_match.group(1).strip()
                confidences["registration_number"] = find_line_confidence(fields["registration_number"], all_lines)
                break
    else:
        fields["state"] = None
        fields["template_matched"] = False
        fields["template_verified"] = False

    # Fallback / Generic Registration Number if not matched by state template
    if not fields.get("registration_number"):
        reg_match = re.search(r"(?:Registration\s*Number|Reg\s*No\.?)[\s:]*([A-Za-z0-9\-\/]{5,25})", text, re.IGNORECASE)
        if reg_match:
            fields["registration_number"] = reg_match.group(1).strip()
            confidences["registration_number"] = find_line_confidence(reg_match.group(1), all_lines)

    # Establishment Name
    est_match = re.search(
        r"(?:Name\s*of\s*Establishment|(?<!&\s)(?<!and\s)(?<!of\s)\bEstablishment\b)[\s:]+([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,60}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Registration|Reg|Employer|Nature\s*of\s*Business|Address)\b))",
        text,
        re.IGNORECASE,
    )
    if est_match:
        fields["establishment_name"] = clean_field_value(est_match.group(1), field_name="establishment_name", doc_type="shop_establishment")
        confidences["establishment_name"] = find_line_confidence(fields["establishment_name"], all_lines)

    # Employer Name
    emp_match = re.search(
        r"(?:Employer|Name of Employer)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Registration|Reg|Establishment|Nature of Business)\b))",
        text,
        re.IGNORECASE,
    )
    if emp_match:
        fields["employer_name"] = clean_field_value(emp_match.group(1), field_name="employer_name", doc_type="shop_establishment")
        confidences["employer_name"] = find_line_confidence(fields["employer_name"], all_lines)

    # Nature of Business
    nature_match = re.search(
        r"(?:Nature of Business)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Registration|Reg|Employer|Date)\b))",
        text,
        re.IGNORECASE,
    )
    if nature_match:
        fields["nature_of_business"] = clean_field_value(nature_match.group(1), field_name="nature_of_business", doc_type="shop_establishment")
        confidences["nature_of_business"] = find_line_confidence(fields["nature_of_business"], all_lines)

    cleaned_fields = {
        k: (clean_field_value(v, field_name=k, doc_type="shop_establishment") if isinstance(v, str) else v)
        for k, v in fields.items()
    }
    return cleaned_fields, confidences


# ==============================================================================
# 7. Bank Statement Extractor (Multi-Page Table Merge & Strict PII Allowlist)
# ==============================================================================

def extract_bank_statement(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Bank statement extractor:
    - Merges transaction tables across ALL pages
    - Applies strict PII allowlist:
      ALLOWLIST = {bank_name, account_number_masked, statement_period, closing_balance, transactions}
      NO full account numbers, NO residential addresses, NO full DOB!
    """
    all_lines = [line for page in doc_res.pages for line in page.lines]
    full_text = doc_res.full_text
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Masked Account Number
    acc_match = re.search(r"(?:Account\s*No\.?|A/C\s*No\.?)[\s:]*([X\d]{6,18})", full_text, re.IGNORECASE)
    if acc_match:
        raw_acc = acc_match.group(1)
        fields["account_number_masked"] = mask_account_number(raw_acc)
        confidences["account_number_masked"] = find_line_confidence(raw_acc, all_lines)

    # Bank Name
    bank_match = re.search(r"(?:Bank\s*Name|Bank)[\s:]*([A-Za-z][A-Za-z \t.&'-]+?BANK)\b", full_text, re.IGNORECASE)
    if bank_match:
        fields["bank_name"] = clean_field_value(bank_match.group(1))

    # Statement Period
    period_match = re.search(r"(?:Statement\s*Period|Period)[\s:]+([0-9\/\-\.]+)\s*(?:to|-)\s*([0-9\/\-\.]+)", full_text, re.IGNORECASE)
    if period_match:
        fields["statement_period"] = {
            "from_date": period_match.group(1).strip(),
            "to_date": period_match.group(2).strip(),
        }

    # Closing Balance
    bal_match = re.search(r"(?:Closing\s*Balance|Balance)[\s:]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)", full_text, re.IGNORECASE)
    if bal_match:
        fields["closing_balance"] = bal_match.group(1).replace(",", "")
        confidences["closing_balance"] = find_line_confidence(bal_match.group(1), all_lines)

    # Multi-page transactions table parsing and chronological merging
    transactions: List[Dict[str, Any]] = []
    # Match standard bank transaction rows: Date, Description/Particulars, Amount/Withdrawal/Deposit, Balance
    row_pattern = re.compile(
        r"(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\s+([A-Za-z0-9\s\-/\*]+?)\s+([\d,]+\.?\d*)\s+(CR|DR|Cr|Dr)?\s*([\d,]+\.?\d*)?",
        re.IGNORECASE,
    )

    for page in doc_res.pages:
        for line in page.lines:
            match = row_pattern.search(line.text)
            if match:
                txn = {
                    "date": match.group(1),
                    "description": match.group(2).strip(),
                    "amount": match.group(3).replace(",", ""),
                    "type": match.group(4).upper() if match.group(4) else "DR",
                    "balance": match.group(5).replace(",", "") if match.group(5) else None,
                }
                transactions.append(txn)

    fields["transactions"] = transactions
    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 8. Salary Slip Extractor (Strict PII Allowlist)
# ==============================================================================

def extract_salary_slip(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Salary slip extractor:
    - Applies strict PII allowlist:
      ALLOWLIST = {employer_name, employee_name_masked, net_pay, pay_period}
      NO full account numbers, NO residential addresses, NO full DOB!
    """
    all_lines = [line for page in doc_res.pages for line in page.lines]
    text = doc_res.full_text
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Employer Name
    emp_match = re.search(
        r"(?:Company(?:\s*Name)?|Employer(?:\s*Name)?)[\s:]+([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{2,60}?(?:LIMITED|PRIVATE\s+LIMITED|PVT\.?\s*LTD\.?|LTD\.?|CORP|INC|DEMO)?)\b(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Employee|Name|Emp\s*ID|Month|Net|Basic|HRA)\b))",
        text,
        re.IGNORECASE,
    )
    if emp_match:
        cand = clean_field_value(emp_match.group(1), field_name="employer_name", doc_type="salary_slip")
        if not re.search(r"^(?:LIMITED|PRIVATE|PVT|LTD)\b", cand, re.I):
            fields["employer_name"] = cand

    if not fields.get("employer_name"):
        # Check first prominent header line (e.g. "DEMO COMPANY PRIVATE LIMITED - SALARY SLIP" or "DEMO COMPANY PVT LTD")
        header_match = re.search(
            r"^[ \t]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{2,60}(?:LIMITED|PRIVATE\s+LIMITED|PVT\.?\s*LTD\.?|LTD\.?|CORPORATION|SERVICES|ENTERPRISES|TECHNOLOGIES|COMPANY))\b",
            text,
            re.MULTILINE | re.IGNORECASE,
        )
        if header_match:
            fields["employer_name"] = clean_field_value(header_match.group(1), field_name="employer_name", doc_type="salary_slip")

    # Employee Name (Raw and Masked)
    name_match = re.search(
        r"(?:Employee(?:\s*Name)?|Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:ID|Emp\s*ID|Designation|Department|Net|Gross|Month|Pay\s*Period)\b))",
        text,
        re.IGNORECASE,
    )
    if name_match:
        raw_name = clean_field_value(name_match.group(1))
        fields["raw_employee_name"] = raw_name
        fields["employee_name"] = raw_name
        fields["employee_name_masked"] = mask_person_name(raw_name)
        confidences["employee_name_masked"] = find_line_confidence(raw_name, all_lines)

    # Net Pay
    net_match = re.search(r"(?:Net\s*Salary|Net\s*Pay|Net\s*Amount)[\s:]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
    if net_match:
        fields["net_pay"] = net_match.group(1).replace(",", "")
        confidences["net_pay"] = find_line_confidence(net_match.group(1), all_lines)

    # Pay Period / Month
    month_match = re.search(r"(?:Month|Pay\s*Period)[\s:]+([A-Za-z]+\s*\d{4}|\d{2}/\d{4})", text, re.IGNORECASE)
    if month_match:
        fields["pay_period"] = month_match.group(1).strip()
        confidences["pay_period"] = find_line_confidence(fields["pay_period"], all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 9. Utility Bill Extractor (Strict PII Allowlist)
# ==============================================================================

def extract_utility_bill(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Utility bill extractor:
    - Applies strict PII allowlist:
      ALLOWLIST = {utility_provider, consumer_number, bill_date, due_date, bill_amount}
      NO residential address, NO sensitive private identifiers!
    """
    all_lines = [line for page in doc_res.pages for line in page.lines]
    text = doc_res.full_text
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Utility Provider
    provider_match = re.search(
        r"(?:Provider|Company|Board)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,50}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Consumer|Bill|Due|Date|Amount|CA\s*No|Connection)\b))",
        text,
        re.IGNORECASE,
    )
    if provider_match:
        fields["utility_provider"] = clean_field_value(provider_match.group(1))
    else:
        # Check standard utility keywords
        if "ELECTRICITY" in text.upper():
            fields["utility_provider"] = "Electricity Distribution Board"
        elif "WATER" in text.upper():
            fields["utility_provider"] = "Water Supply Department"
        elif "GAS" in text.upper():
            fields["utility_provider"] = "Natural Gas Corporation"

    # Consumer Number
    consumer_match = re.search(r"(?:Consumer\s*No\.?|CA\s*No\.?|Account\s*No\.?|Connection\s*ID)[\s:]*([A-Za-z0-9\-]{6,20})", text, re.IGNORECASE)
    if consumer_match:
        fields["consumer_number"] = consumer_match.group(1)
        confidences["consumer_number"] = find_line_confidence(consumer_match.group(1), all_lines)

    # Bill Date
    bdate_match = re.search(r"(?:Bill\s*Date)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if bdate_match:
        fields["bill_date"] = bdate_match.group(1).replace("-", "/").replace(".", "/")

    # Due Date
    ddate_match = re.search(r"(?:Due\s*Date)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if ddate_match:
        fields["due_date"] = ddate_match.group(1).replace("-", "/").replace(".", "/")

    # Bill Amount
    amt_match = re.search(r"(?:Total\s*Amount|Amount\s*Due|Bill\s*Amount)[\s:]+(?:Rs\.?|INR)?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
    if amt_match:
        fields["bill_amount"] = amt_match.group(1).replace(",", "")
        confidences["bill_amount"] = find_line_confidence(amt_match.group(1), all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 10. Passport Extractor
# ==============================================================================

def extract_passport(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    all_lines = [line for page in doc_res.pages for line in page.lines]
    text = doc_res.full_text
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Passport Number (1 letter + 7 digits)
    pass_match = re.search(r"\b([A-PR-WYa-pr-wy][0-9]{7}|[A-Z][0-9]{7})\b", text)
    if pass_match:
        fields["passport_number"] = pass_match.group(1).upper()
        confidences["passport_number"] = find_line_confidence(pass_match.group(1), all_lines)

    # Surname
    sur_match = re.search(
        r"(?:Surname)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,30}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Given|Given\s*Name|Nationality|Passport|DOB|Date)\b))",
        text,
        re.IGNORECASE,
    )
    if sur_match:
        fields["surname"] = clean_field_value(sur_match.group(1))
        confidences["surname"] = find_line_confidence(fields["surname"], all_lines)

    # Given Name
    given_match = re.search(
        r"(?:Given\s*Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,30}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Surname|Nationality|Passport|DOB|Date)\b))",
        text,
        re.IGNORECASE,
    )
    if given_match:
        fields["given_name"] = clean_field_value(given_match.group(1))
        confidences["given_name"] = find_line_confidence(fields["given_name"], all_lines)

    # Combine into name for unified cross-checking
    if "given_name" in fields and "surname" in fields:
        fields["name"] = f"{fields['given_name']} {fields['surname']}"
    elif "given_name" in fields:
        fields["name"] = fields["given_name"]

    # Nationality
    nat_match = re.search(r"(?:Nationality)[\s:]+([A-Za-z]+)", text, re.IGNORECASE)
    if nat_match:
        fields["nationality"] = nat_match.group(1).strip()

    # DOB
    dob_match = re.search(r"(?:Date of Birth|DOB)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if dob_match:
        fields["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        confidences["dob"] = find_line_confidence(dob_match.group(1), all_lines)

    # Expiry Date
    exp_match = re.search(r"(?:Date of Expiry|Expiry\s*Date)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if exp_match:
        fields["expiry_date"] = exp_match.group(1).replace("-", "/").replace(".", "/")

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 11. Voter ID Extractor
# ==============================================================================

def extract_voter_id(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    all_lines = [line for page in doc_res.pages for line in page.lines]
    text = doc_res.full_text
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # EPIC Number: 3 letters + 7 digits (or alphanumeric formats)
    epic_match = re.search(r"\b([A-Z]{3}[0-9]{7})\b", text)
    if epic_match:
        fields["epic_number"] = epic_match.group(1)
        confidences["epic_number"] = find_line_confidence(epic_match.group(1), all_lines)

    # Name
    name_match = re.search(
        r"(?:Name|Elector['’]?s?\s*Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Father|Husband|Relative|DOB|Date|Age|Gender|EPIC)\b))",
        text,
        re.IGNORECASE,
    )
    if name_match:
        fields["name"] = clean_field_value(name_match.group(1))
        confidences["name"] = find_line_confidence(fields["name"], all_lines)

    # Relative / Father Name
    rel_match = re.search(
        r"(?:Father['’]?s?\s*Name|Husband['’]?s?\s*Name|Relative['’]?s?\s*Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:DOB|Date|Age|Gender|EPIC|Address)\b))",
        text,
        re.IGNORECASE,
    )
    if rel_match:
        fields["relative_name"] = clean_field_value(rel_match.group(1))

    # DOB / Age
    dob_match = re.search(r"(?:DOB|Date of Birth)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if dob_match:
        fields["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
    else:
        age_match = re.search(r"(?:Age)[\s:]+(\d{1,2})", text, re.IGNORECASE)
        if age_match:
            fields["age"] = int(age_match.group(1))

    # Gender
    gender_match = re.search(r"\b(MALE|FEMALE)\b", text, re.IGNORECASE)
    if gender_match:
        fields["gender"] = gender_match.group(1).capitalize()

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 12. Driving Licence Extractor
# ==============================================================================

def extract_driving_licence(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    all_lines = [line for page in doc_res.pages for line in page.lines]
    text = doc_res.full_text
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Driving Licence Number: State code (2) + RTO code (2) + Year (4) + 7 digits (or with spaces)
    dl_match = re.search(r"\b([A-Z]{2}[0-9]{2}\s?[0-9]{4}[0-9]{7}|[A-Z]{2}[0-9]{2}\s?[0-9A-Z]{11,15})\b", text)
    if dl_match:
        fields["licence_number"] = dl_match.group(1).strip()
        confidences["licence_number"] = find_line_confidence(fields["licence_number"], all_lines)

    # Name
    name_match = re.search(
        r"(?:Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,35}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:DOB|Date|Licence|License|Issue|Valid|Vehicle)\b))",
        text,
        re.IGNORECASE,
    )
    if name_match:
        fields["name"] = clean_field_value(name_match.group(1))
        confidences["name"] = find_line_confidence(fields["name"], all_lines)

    # DOB
    dob_match = re.search(r"(?:DOB|Date of Birth)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if dob_match:
        fields["dob"] = dob_match.group(1).replace("-", "/").replace(".", "/")
        confidences["dob"] = find_line_confidence(dob_match.group(1), all_lines)

    # Issue Date
    issue_match = re.search(r"(?:Issue Date|Date of Issue)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if issue_match:
        fields["issue_date"] = issue_match.group(1).replace("-", "/").replace(".", "/")

    # Valid Till
    valid_match = re.search(r"(?:Valid Till|Validity)[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})", text, re.IGNORECASE)
    if valid_match:
        fields["valid_till"] = valid_match.group(1).replace("-", "/").replace(".", "/")

    # Vehicle Class
    class_match = re.search(r"\b(LMV|MCWG|MCWOG|TRANS|HGMV|HPMV)\b", text)
    if class_match:
        fields["vehicle_class"] = class_match.group(1)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 13. ITR (Income Tax Return) Extractor
# ==============================================================================

def extract_itr(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    all_lines = [line for page in doc_res.pages for line in page.lines]
    text = doc_res.full_text
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Acknowledgement Number (15 digits)
    ack_match = re.search(r"(?:Acknowledgement\s*Number|Ack\s*No\.?)[\s:]*(\d{15})", text, re.IGNORECASE)
    if ack_match:
        fields["acknowledgement_number"] = ack_match.group(1)
        confidences["acknowledgement_number"] = find_line_confidence(ack_match.group(1), all_lines)

    # Assessment Year (20XX-YY)
    ay_match = re.search(r"(?:Assessment\s*Year|AY)[\s:]*(\d{4}[-\/]\d{2,4})", text, re.IGNORECASE)
    if ay_match:
        fields["assessment_year"] = ay_match.group(1)

    # PAN
    pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text)
    if pan_match:
        fields["pan_number"] = pan_match.group(1)
        confidences["pan_number"] = find_line_confidence(pan_match.group(1), all_lines)

    # Name
    name_match = re.search(
        r"(?:Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{1,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:PAN|Address|Status|Form|Acknowledgement|Ack|Date|Father)\b))",
        text,
        re.IGNORECASE,
    )
    if name_match:
        fields["name"] = clean_field_value(name_match.group(1))
        confidences["name"] = find_line_confidence(fields["name"], all_lines)

    # Total Income
    inc_match = re.search(
        r"(?:Total\s*Income(?:[^\n\d]*?round[^\n]*)?)[\s:]+(?:(?:(?:Row\s*)?\d+[A-Za-z]?)\b[\s:]+)?(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if inc_match:
        fields["total_income"] = inc_match.group(1).replace(",", "")
        confidences["total_income"] = find_line_confidence(inc_match.group(1), all_lines)

    # Taxes Paid
    tax_match = re.search(
        r"(?:Taxes\s*Paid|Total\s*Tax(?:es)?\s*Paid)[\s:]+(?:(?:(?:Row\s*)?\d+[A-Za-z]?)\b[\s:]+)?(?:Rs\.?|INR)?\s*([\d,]+(?:\.\d{2})?)",
        text,
        re.IGNORECASE,
    )
    if tax_match:
        fields["taxes_paid"] = tax_match.group(1).replace(",", "")

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 14. GST Certificate Extractor
# ==============================================================================

def extract_gst_certificate(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # GSTIN: 15 alphanumeric characters
    gstin_match = re.search(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b", text)
    if gstin_match:
        fields["gstin"] = gstin_match.group(1).upper()
        confidences["gstin"] = find_line_confidence(gstin_match.group(1), all_lines)

    # Legal Name
    legal_match = re.search(
        r"(?:Legal\s*Name(?:[\s/]*(?:of\s+Taxpayer)?)?)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,70}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Trade\s*Name|GSTIN|Constitution|Date|Address|Period)\b))",
        text,
        re.IGNORECASE,
    )
    if legal_match:
        fields["legal_name"] = clean_field_value(legal_match.group(1), "legal_name", "gst_certificate")
        confidences["legal_name"] = find_line_confidence(fields["legal_name"], all_lines)

    # Trade Name
    trade_match = re.search(
        r"(?:Trade\s*Name(?:,\s*if\s*any)?)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,70}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Constitution|Legal\s*Name|GSTIN|Date|Address|Period)\b))",
        text,
        re.IGNORECASE,
    )
    if trade_match:
        fields["trade_name"] = clean_field_value(trade_match.group(1), "trade_name", "gst_certificate")
        confidences["trade_name"] = find_line_confidence(fields["trade_name"], all_lines)

    # Registration Date
    reg_date = re.search(
        r"(?:Date\s*of\s*(?:liability|Registration|Validity))[\s:]+(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        text,
        re.IGNORECASE,
    )
    if reg_date:
        fields["registration_date"] = reg_date.group(1)
        confidences["registration_date"] = find_line_confidence(reg_date.group(1), all_lines)

    # Constitution of Business
    const_match = re.search(
        r"(?:Constitution\s*of\s*Business)[\s:]*([A-Za-z][A-Za-z \t,\.\-&]{1,50}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Type|Date|Address|Particulars|Period)\b))",
        text,
        re.IGNORECASE,
    )
    if const_match:
        fields["constitution_of_business"] = clean_field_value(const_match.group(1), "constitution_of_business", "gst_certificate")
        confidences["constitution_of_business"] = find_line_confidence(fields["constitution_of_business"], all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 15. Certificate of Incorporation Extractor
# ==============================================================================

def extract_certificate_of_incorporation(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # CIN: 21 alphanumeric characters
    cin_match = re.search(r"\b([UL][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6})\b", text)
    if cin_match:
        fields["cin"] = cin_match.group(1).upper()
        confidences["cin"] = find_line_confidence(cin_match.group(1), all_lines)

    # Company Name
    co_match = re.search(
        r"(?:hereby\s*certifies\s*that\s+|Name\s*of\s*the\s*Company[\s:]*)([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{2,80}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:is\s+incorporated|under\s+the|CIN|Corporate|Date|Given\s+under)\b))",
        text,
        re.IGNORECASE,
    )
    if co_match:
        fields["company_name"] = clean_field_value(co_match.group(1), "company_name", "certificate_of_incorporation")
        confidences["company_name"] = find_line_confidence(fields["company_name"], all_lines)

    # Date of Incorporation
    doi_match = re.search(
        r"(?:incorporated\s*(?:under\s*the\s*Companies\s*Act.*?)?on\s*this|Date\s*of\s*Incorporation[\s:]*|dated\s*this\s+)\s*([A-Za-z0-9 \t]{3,50}?\b\d{4}|\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        text,
        re.IGNORECASE,
    )
    if doi_match:
        fields["date_of_incorporation"] = clean_field_value(doi_match.group(1), "date_of_incorporation", "certificate_of_incorporation")
        confidences["date_of_incorporation"] = find_line_confidence(fields["date_of_incorporation"], all_lines)

    # Registrar Office
    roc_match = re.search(
        r"(?:Registrar\s*of\s*Companies|ROC)[\s,:-]*([A-Za-z][A-Za-z \t,\.\-]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Ministry|Government|Companies\s*Act|CIN|Corporate)\b))",
        text,
        re.IGNORECASE,
    )
    if roc_match:
        fields["registrar_office"] = clean_field_value(roc_match.group(1), "registrar_office", "certificate_of_incorporation")
        confidences["registrar_office"] = find_line_confidence(fields["registrar_office"], all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 16. Partnership Deed Extractor
# ==============================================================================

def extract_partnership_deed(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Firm Name
    firm_match = re.search(
        r"(?:name\s*(?:and|&)\s*style\s*of\s*[:\s]*|firm\s*name[\s:]*|M/S[\s\.]*)([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{2,60}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:hereinafter|having|place\s+of\s+business|partners|date|ratio)\b))",
        text,
        re.IGNORECASE,
    )
    if firm_match:
        fields["firm_name"] = clean_field_value(firm_match.group(1), "firm_name", "partnership_deed")
        confidences["firm_name"] = find_line_confidence(fields["firm_name"], all_lines)

    # Partner Names: Schema difference - returns List[str]
    partner_names: List[str] = []
    partner_patterns = [
        r"(?:Party\s*of\s*(?:the\s*)?(?:First|Second|Third|Fourth|[1-4])\s*Part|Partner\s*[0-9]+|Between\s+(?:Mr\.|Shri|Smt\.)?)[\s,:-]*([A-Za-z][A-Za-z \t.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:hereinafter|son\s+of|daughter\s+of|wife\s+of|residing|party|and)\b))",
        r"(?:(?:^|\n)\s*(?:[0-9]+[\.\)]|Partner\s*[0-9]+[\.:]))\s*([A-Za-z][A-Za-z \t.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:hereinafter|son\s+of|daughter\s+of|wife\s+of|residing|party|and)\b))",
    ]
    seen_partners = set()
    for pat in partner_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw_cand = clean_field_value(m.group(1), "partner_names", "partnership_deed")
            cand_norm = raw_cand.strip().upper()
            if cand_norm and cand_norm not in seen_partners and len(cand_norm) > 2:
                if not re.search(r"^(?:PARTNERSHIP|DEED|FIRM|THE|PROFIT|CAPITAL)\b", cand_norm):
                    seen_partners.add(cand_norm)
                    partner_names.append(raw_cand.strip())
    fields["partner_names"] = partner_names
    fields["raw_partner_names"] = partner_names
    conf_val = 0.95 if partner_names else 0.5
    confidences["partner_names"] = conf_val
    confidences["raw_partner_names"] = conf_val

    # Masked variant for PII minimisation: First name + initial per mask_person_name
    partner_names_masked = [mask_person_name(p) for p in partner_names if p]
    fields["partner_names_masked"] = partner_names_masked
    confidences["partner_names_masked"] = conf_val

    # Date of Deed
    deed_date = re.search(
        r"(?:executed\s*on\s*(?:this)?|dated\s*(?:this)?|date\s*of\s*(?:deed|execution)[\s:]*)(\d{1,2}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?[A-Za-z]+\s+\d{4}|\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        text,
        re.IGNORECASE,
    )
    if deed_date:
        fields["date_of_deed"] = clean_field_value(deed_date.group(1), "date_of_deed", "partnership_deed")
        confidences["date_of_deed"] = find_line_confidence(fields["date_of_deed"], all_lines)

    # Profit Sharing Ratio
    ratio_match = re.search(
        r"(?:Profit\s*(?:and|&)\s*Loss\s*(?:sharing)?\s*ratio|profit\s*sharing\s*ratio)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t%:,\.\-/]{1,50}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:The\s+parties|Capital|Bank|Accounts|Duration)\b))",
        text,
        re.IGNORECASE,
    )
    if ratio_match:
        fields["profit_sharing_ratio"] = clean_field_value(ratio_match.group(1), "profit_sharing_ratio", "partnership_deed")
        confidences["profit_sharing_ratio"] = find_line_confidence(fields["profit_sharing_ratio"], all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 17. Rent Agreement Extractor
# ==============================================================================

def extract_rent_agreement(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Lessor Name
    lessor_match = re.search(
        r"(?:LESSOR|LANDLORD|FIRST\s*PARTY)[\s,:-]*([A-Za-z][A-Za-z \t.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:hereinafter|son\s+of|daughter\s+of|wife\s+of|residing|and|lessee|tenant|second\s+party)\b))",
        text,
        re.IGNORECASE,
    )
    lessor_name = clean_field_value(lessor_match.group(1), "lessor_name", "rent_agreement") if lessor_match else None
    if lessor_name:
        fields["raw_lessor_name"] = lessor_name
        fields["lessor_name_masked"] = mask_person_name(lessor_name)
        confidences["lessor_name_masked"] = find_line_confidence(lessor_name, all_lines)

    # Lessee Name
    lessee_match = re.search(
        r"(?:LESSEE|TENANT|SECOND\s*PARTY)[\s,:-]*([A-Za-z][A-Za-z \t.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:hereinafter|son\s+of|daughter\s+of|wife\s+of|residing|and|lessor|premises|rent)\b))",
        text,
        re.IGNORECASE,
    )
    lessee_name = clean_field_value(lessee_match.group(1), "lessee_name", "rent_agreement") if lessee_match else None
    if lessee_name:
        fields["raw_lessee_name"] = lessee_name
        fields["lessee_name_masked"] = mask_person_name(lessee_name)
        confidences["lessee_name_masked"] = find_line_confidence(lessee_name, all_lines)

    # Property Address
    addr_match = re.search(
        r"(?:Premises\s*(?:situated\s*at|at)|Demised\s*Premises|Property\s*Address)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-\/]{5,100}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Monthly\s*Rent|Rent|Period|Term|Security\s*Deposit)\b))",
        text,
        re.IGNORECASE,
    )
    prop_addr = clean_field_value(addr_match.group(1), "property_address", "rent_agreement") if addr_match else None
    if prop_addr:
        fields["raw_property_address"] = prop_addr
        fields["property_address_masked"] = mask_address(prop_addr)
        confidences["property_address_masked"] = find_line_confidence(prop_addr, all_lines)

    # Monthly Rent
    rent_match = re.search(
        r"(?:Monthly\s*Rent|Rent\s*per\s*month)[\s:]*(?:Rs\.?|INR)?\s*([0-9,]+(?:\.[0-9]{2})?)",
        text,
        re.IGNORECASE,
    )
    if rent_match:
        fields["monthly_rent"] = rent_match.group(1).replace(",", "")
        confidences["monthly_rent"] = find_line_confidence(rent_match.group(1), all_lines)

    # Agreement Start Date
    start_match = re.search(
        r"(?:commencing\s*(?:from|on)?|lease\s*period\s*from|start\s*date)[\s:]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if start_match:
        fields["agreement_start_date"] = clean_field_value(start_match.group(1), "agreement_start_date", "rent_agreement")
        confidences["agreement_start_date"] = find_line_confidence(fields["agreement_start_date"], all_lines)

    # Agreement End Date
    end_match = re.search(
        r"(?:expiring\s*(?:on)?|ending\s*(?:on)?|lease\s*period\s*to|valid\s*(?:till|to)|end\s*date)[\s:]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if end_match:
        fields["agreement_end_date"] = clean_field_value(end_match.group(1), "agreement_end_date", "rent_agreement")
        confidences["agreement_end_date"] = find_line_confidence(fields["agreement_end_date"], all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 18. Form 16 Extractor
# ==============================================================================

def extract_form_16(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Employee PAN
    pan_match = re.search(
        r"(?:PAN\s*(?:of\s*(?:the\s*)?Employee)?|Employee\s*PAN)[\s:]*([A-Z]{5}[0-9]{4}[A-Z])",
        text,
        re.IGNORECASE,
    )
    if pan_match:
        fields["pan_number"] = pan_match.group(1).upper()
        confidences["pan_number"] = find_line_confidence(pan_match.group(1), all_lines)

    # Employer TAN
    tan_match = re.search(
        r"(?:TAN\s*(?:of\s*(?:the\s*)?Deductor|Employer)?|Deductor\s*TAN)[\s:]*([A-Z]{4}[0-9]{5}[A-Z])",
        text,
        re.IGNORECASE,
    )
    if tan_match:
        fields["tan_number"] = tan_match.group(1).upper()
        confidences["tan_number"] = find_line_confidence(tan_match.group(1), all_lines)

    # Employer Name
    er_match = re.search(
        r"(?:Name\s*and\s*address\s*of\s*the\s*Employer|Name\s*of\s*(?:the\s*)?(?:Employer|Deductor))[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{2,60}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:PAN|TAN|Employee|Address|Assessment|Period)\b))",
        text,
        re.IGNORECASE,
    )
    if er_match:
        fields["employer_name"] = clean_field_value(er_match.group(1), "employer_name", "form_16")
        confidences["employer_name"] = find_line_confidence(fields["employer_name"], all_lines)

    # Employee Name
    ee_match = re.search(
        r"(?:Name\s*of\s*(?:the\s*)?Employee)[\s:]*([A-Za-z][A-Za-z \t.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:PAN|Designation|Address|Assessment|Period)\b))",
        text,
        re.IGNORECASE,
    )
    ee_name = clean_field_value(ee_match.group(1), "employee_name", "form_16") if ee_match else None
    if ee_name:
        fields["raw_employee_name"] = ee_name
        fields["employee_name_masked"] = mask_person_name(ee_name)
        confidences["employee_name_masked"] = find_line_confidence(ee_name, all_lines)

    # Assessment Year
    ay_match = re.search(
        r"(?:Assessment\s*Year|AY)[\s:]*([0-9]{4}\s*-\s*(?:[0-9]{2}|[0-9]{4}))",
        text,
        re.IGNORECASE,
    )
    if ay_match:
        fields["assessment_year"] = re.sub(r"\s+", "", ay_match.group(1))
        confidences["assessment_year"] = find_line_confidence(ay_match.group(1), all_lines)

    # Gross Salary
    gross_match = re.search(
        r"(?:Gross\s*Salary|Total\s*Salary|Gross\s*Total\s*Income)[\s:]*(?:Rs\.?|INR)?\s*([0-9,]+(?:\.[0-9]{2})?)",
        text,
        re.IGNORECASE,
    )
    if gross_match:
        fields["gross_salary"] = gross_match.group(1).replace(",", "")
        confidences["gross_salary"] = find_line_confidence(gross_match.group(1), all_lines)

    # Tax Deducted
    tds_match = re.search(
        r"(?:Total\s*Tax\s*Deducted|Tax\s*Deducted\s*at\s*Source|TDS\s*Deducted)[\s:]*(?:Rs\.?|INR)?\s*([0-9,]+(?:\.[0-9]{2})?)",
        text,
        re.IGNORECASE,
    )
    if tds_match:
        fields["tax_deducted"] = tds_match.group(1).replace(",", "")
        confidences["tax_deducted"] = find_line_confidence(tds_match.group(1), all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 19. Bank Passbook Extractor
# ==============================================================================

def extract_bank_passbook(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Bank Name
    bank_match = re.search(
        r"(?:(?:^|\r?\n)\s*([A-Za-z \t]{3,35}?\bBANK(?:\s+OF\s+[A-Za-z \t]+)?)|Bank\s*Name[\s:]*([A-Za-z][A-Za-z \t,\.\-&]{2,40}?))(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Branch|IFSC|A/C|Account)\b))",
        text,
        re.IGNORECASE,
    )
    if bank_match:
        cand = (bank_match.group(1) or bank_match.group(2) or "").strip()
        cand = cand.splitlines()[0].strip()
        cand = re.sub(r"\s*(?:SAVINGS\s+BANK\s+PASS\s*BOOK|PASS\s*BOOK).*", "", cand, flags=re.I).strip()
        if cand:
            fields["bank_name"] = clean_field_value(cand, "bank_name", "bank_passbook")
            confidences["bank_name"] = find_line_confidence(fields["bank_name"], all_lines)

    # Branch
    branch_match = re.search(
        r"(?:Branch\s*(?:Name)?|Branch\s*Code)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:IFSC|Account|A/C|MICR|CIF|Customer)\b))",
        text,
        re.IGNORECASE,
    )
    if branch_match:
        fields["branch"] = clean_field_value(branch_match.group(1), "branch", "bank_passbook")
        confidences["branch"] = find_line_confidence(fields["branch"], all_lines)

    # IFSC
    ifsc_match = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
    if ifsc_match:
        fields["ifsc"] = ifsc_match.group(1).upper()
        confidences["ifsc"] = find_line_confidence(ifsc_match.group(1), all_lines)

    # Account Number
    acc_match = re.search(r"(?:Account\s*(?:No|Number)|A/C\s*(?:No|Number)?)[\s:]*([0-9]{9,18})", text, re.IGNORECASE)
    if acc_match:
        raw_acc = acc_match.group(1)
        fields["raw_account_number"] = raw_acc
        fields["account_number_masked"] = mask_account_number(raw_acc)
        confidences["account_number_masked"] = find_line_confidence(raw_acc, all_lines)

    # Account Holder Name
    holder_match = re.search(
        r"(?:Account\s*Holder(?:\s*Name)?|Name\s*of\s*Account\s*Holder|Customer\s*Name|(?<!Branch\s)(?<!Bank\s)\bName)[\s:]*([A-Za-z][A-Za-z \t.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Account|A/C|IFSC|CIF|Customer|Branch)\b))",
        text,
        re.IGNORECASE,
    )
    holder_name = clean_field_value(holder_match.group(1), "account_holder_name", "bank_passbook") if holder_match else None
    if holder_name:
        fields["raw_account_holder_name"] = holder_name
        fields["account_holder_name_masked"] = mask_person_name(holder_name)
        confidences["account_holder_name_masked"] = find_line_confidence(holder_name, all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 20. Property Tax Receipt Extractor
# ==============================================================================

def extract_property_tax_receipt(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # Property ID / Number
    pid_match = re.search(
        r"(?:Property\s*(?:ID|No|Number)|Assessment\s*No|Index\s*No|Tax\s*Bill\s*No)[\s:]*([A-Za-z0-9\-\/]{4,25})",
        text,
        re.IGNORECASE,
    )
    if pid_match:
        fields["property_id"] = pid_match.group(1)
        confidences["property_id"] = find_line_confidence(pid_match.group(1), all_lines)

    # Owner Name
    owner_match = re.search(
        r"(?:Owner\s*Name|Name\s*of\s*(?:the\s*)?Owner|Tax\s*Payer\s*Name)[\s:]*([A-Za-z][A-Za-z \t.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:Property|Ward|Zone|Address|Assessment|Tax|Amount)\b))",
        text,
        re.IGNORECASE,
    )
    owner_name = clean_field_value(owner_match.group(1), "owner_name", "property_tax_receipt") if owner_match else None
    if owner_name:
        fields["raw_owner_name"] = owner_name
        fields["owner_name_masked"] = mask_person_name(owner_name)
        confidences["owner_name_masked"] = find_line_confidence(owner_name, all_lines)

    # Tax Amount Paid
    tax_match = re.search(
        r"(?:Tax\s*Amount\s*Paid|Total\s*Amount\s*Paid|Amount\s*Paid)[\s:]*(?:Rs\.?|INR)?\s*([0-9,]+(?:\.[0-9]{2})?)",
        text,
        re.IGNORECASE,
    )
    if tax_match:
        fields["tax_amount_paid"] = tax_match.group(1).replace(",", "")
        confidences["tax_amount_paid"] = find_line_confidence(tax_match.group(1), all_lines)

    # Payment Date
    date_match = re.search(
        r"(?:Payment\s*Date|Receipt\s*Date|Date\s*of\s*Payment)[\s:]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        fields["payment_date"] = date_match.group(1)
        confidences["payment_date"] = find_line_confidence(date_match.group(1), all_lines)

    # Assessment Year
    ay_match = re.search(
        r"(?:Assessment\s*Year|AY)[\s:]*([0-9]{4}\s*-\s*(?:[0-9]{2}|[0-9]{4}))",
        text,
        re.IGNORECASE,
    )
    if ay_match:
        fields["assessment_year"] = re.sub(r"\s+", "", ay_match.group(1))
        confidences["assessment_year"] = find_line_confidence(ay_match.group(1), all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# 21. IEC Certificate Extractor
# ==============================================================================

def extract_iec_certificate(doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    text = doc_res.full_text
    all_lines = [line for page in doc_res.pages for line in page.lines]
    fields: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}

    # IEC Number (10 alphanumeric / PAN)
    iec_match = re.search(r"(?:IEC\s*(?:Number|No)?|Import\s*Export\s*Code)[\s:]*([A-Z0-9]{10})", text, re.IGNORECASE)
    if iec_match:
        fields["iec_number"] = iec_match.group(1).upper()
        confidences["iec_number"] = find_line_confidence(iec_match.group(1), all_lines)

    # Entity Name
    ent_match = re.search(
        r"(?:Name\s*of\s*(?:the\s*)?(?:Firm|Entity|Company)|Entity\s*Name)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{2,60}?)(?=[ \t]*(?:\r?\n|$|(?:\b|(?<=[a-z0-9A-Z]))(?:IEC|PAN|Date|Address|Branch|Director)\b))",
        text,
        re.IGNORECASE,
    )
    if ent_match:
        fields["entity_name"] = clean_field_value(ent_match.group(1), "entity_name", "iec_certificate")
        confidences["entity_name"] = find_line_confidence(fields["entity_name"], all_lines)

    # Issue Date
    date_match = re.search(
        r"(?:Date\s*of\s*Issue|Issue\s*Date)[\s:]*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        fields["issue_date"] = date_match.group(1)
        confidences["issue_date"] = find_line_confidence(date_match.group(1), all_lines)

    # PAN Number
    pan_match = re.search(r"(?:PAN|Permanent\s*Account\s*Number)[\s:]*([A-Z]{5}[0-9]{4}[A-Z])", text, re.IGNORECASE)
    if pan_match:
        fields["pan_number"] = pan_match.group(1).upper()
        confidences["pan_number"] = find_line_confidence(pan_match.group(1), all_lines)

    cleaned_fields = {k: clean_field_value(v) for k, v in fields.items()}
    return cleaned_fields, confidences


# ==============================================================================
# Dispatcher & PII Minimisation Enforcer
# ==============================================================================

EXTRACTOR_REGISTRY = {
    "pan": extract_pan,
    "aadhaar": extract_aadhaar,
    "cancelled_cheque": extract_cancelled_cheque,
    "udyam": extract_udyam,
    "fssai": extract_fssai,
    "shop_establishment": extract_shop_establishment,
    "bank_statement": extract_bank_statement,
    "salary_slip": extract_salary_slip,
    "utility_bill": extract_utility_bill,
    "passport": extract_passport,
    "voter_id": extract_voter_id,
    "driving_licence": extract_driving_licence,
    "itr": extract_itr,
    "gst_certificate": extract_gst_certificate,
    "certificate_of_incorporation": extract_certificate_of_incorporation,
    "partnership_deed": extract_partnership_deed,
    "rent_agreement": extract_rent_agreement,
    "form_16": extract_form_16,
    "bank_passbook": extract_bank_passbook,
    "property_tax_receipt": extract_property_tax_receipt,
    "iec_certificate": extract_iec_certificate,
}

# Strict PII allowlist: fields not in allowlist are strictly stripped before leaving the service
PII_ALLOWLIST = {
    "bank_statement": {"bank_name", "account_number_masked", "statement_period", "closing_balance", "transactions"},
    "salary_slip": {"employer_name", "employee_name_masked", "net_pay", "pay_period"},
    "utility_bill": {"utility_provider", "consumer_number", "bill_date", "due_date", "bill_amount"},
    "rent_agreement": {"lessor_name_masked", "lessee_name_masked", "property_address_masked", "monthly_rent", "agreement_start_date", "agreement_end_date"},
    "form_16": {"employer_name", "employee_name_masked", "pan_number", "tan_number", "assessment_year", "gross_salary", "tax_deducted"},
    "bank_passbook": {"bank_name", "branch", "ifsc", "account_number_masked", "account_holder_name_masked"},
    "property_tax_receipt": {"property_id", "owner_name_masked", "tax_amount_paid", "payment_date", "assessment_year"},
    "partnership_deed": {"firm_name", "partner_names_masked", "date_of_deed", "profit_sharing_ratio"},
}


def extract_document_fields_raw(doc_type: str, doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Run appropriate extractor for doc_type and return RAW fields (including unmasked
    values like raw_aadhaar and employee_name) for verification and cross-checking.
    """
    extractor = EXTRACTOR_REGISTRY.get(doc_type)
    if not extractor:
        return {}, {}
    fields, confidences = extractor(doc_res)
    cleaned_fields = {
        k: (clean_field_value(v, field_name=k, doc_type=doc_type) if isinstance(v, str) else v)
        for k, v in fields.items()
    }
    return cleaned_fields, confidences


def sanitize_extracted_fields(doc_type: str, fields: Dict[str, Any], confidences: Dict[str, float]) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Sanitize extracted fields AFTER verification and cross-check.
    - Applies strict PII allowlist for bank_statement, salary_slip, utility_bill.
    - Strictly strips all 'raw_' prefix keys and transient unmasked identifiers.
    """
    # 1. Apply PII allowlist filtering if applicable
    if doc_type in PII_ALLOWLIST:
        allowed = PII_ALLOWLIST[doc_type]
        filtered_fields = {k: v for k, v in fields.items() if k in allowed}
        filtered_conf = {k: v for k, v in confidences.items() if k in allowed}
        return filtered_fields, filtered_conf

    # 2. General cleanup: strip any key starting with 'raw_' or transient unmasked names
    cleaned_fields = {}
    cleaned_conf = {}
    transient_sensitive_keys = {
        "raw_aadhaar", "raw_account_number", "raw_employee_name",
        "raw_lessor_name", "raw_lessee_name", "raw_property_address",
        "raw_owner_name", "raw_account_holder_name",
        "raw_partner_names", "partner_names",
    }

    for k, v in fields.items():
        if k.startswith("raw_") or k in transient_sensitive_keys:
            continue
        cleaned_fields[k] = v

    for k, v in confidences.items():
        if k.startswith("raw_") or k in transient_sensitive_keys:
            continue
        cleaned_conf[k] = v

    return cleaned_fields, cleaned_conf


def extract_document_fields(doc_type: str, doc_res: OCRDocumentResult) -> Tuple[Dict[str, Any], Dict[str, float]]:
    """
    Convenience method: runs raw extraction and immediately sanitizes fields.
    For internal workflows, prefer extract_document_fields_raw -> verify -> sanitize_extracted_fields.
    """
    raw_fields, confidences = extract_document_fields_raw(doc_type, doc_res)
    return sanitize_extracted_fields(doc_type, raw_fields, confidences)

