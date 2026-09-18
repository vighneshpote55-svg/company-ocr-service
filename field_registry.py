"""
field_registry.py
Central Field Registry for AI Mode in company-ocr-service:
- Single source of truth for all document field definitions, canonical keys, aliases, and intent detection patterns.
- Human-friendly formatters for dates (e.g., 22/06/2007 -> 22 June 2007) and statement periods (e.g., 30 July 2025 – 30 July 2026).
- Strict validation rules and anti-substitution guards (e.g., IFSC never returns Bank Name; Customer Number never returns Account Number).
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ==============================================================================
# Date & Statement Period Formatters
# ==============================================================================

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


def format_date_human(date_str: str) -> str:
    """
    Format numeric dates (e.g., '22/06/2007', '2007-06-22', '01-04-2025')
    into human-friendly strings: '22 June 2007'.
    Leaves already formatted text intact.
    """
    if not date_str or not isinstance(date_str, str):
        return str(date_str or "")

    cleaned = date_str.strip()

    # Pattern DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$", cleaned)
    if m:
        d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mon <= 12 and 1 <= d <= 31:
            return f"{d:02d} {MONTH_NAMES[mon]} {y}"

    # Pattern YYYY-MM-DD
    m2 = re.match(r"^(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})$", cleaned)
    if m2:
        y, mon, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        if 1 <= mon <= 12 and 1 <= d <= 31:
            return f"{d:02d} {MONTH_NAMES[mon]} {y}"

    return cleaned


def format_statement_period_human(sp: Any) -> str:
    """
    Format statement period into clean human-readable format:
    e.g. '30 July 2025 – 30 July 2026'.
    Never outputs raw Python dictionary syntax.
    """
    f_date = ""
    t_date = ""

    if isinstance(sp, dict):
        f_date = sp.get("from_date") or sp.get("from") or ""
        t_date = sp.get("to_date") or sp.get("to") or ""
    elif isinstance(sp, str) and sp.strip():
        # Check stringified dict e.g. "{'from_date':'30/07/2025','to_date':'30/07/2026'}"
        m_f = re.search(r"['\"](?:from_date|from)['\"]\s*:\s*['\"]([^'\"]+)['\"]", sp)
        m_t = re.search(r"['\"](?:to_date|to)['\"]\s*:\s*['\"]([^'\"]+)['\"]", sp)
        if m_f:
            f_date = m_f.group(1)
        if m_t:
            t_date = m_t.group(1)

        if not f_date and not t_date:
            # Check 'From : DD/MM/YYYY To : DD/MM/YYYY' or 'DD/MM/YYYY to DD/MM/YYYY'
            m_range = re.search(
                r"(?:from\s*:?\s*)?([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{4})\s*(?:to|–|-|till|through)\s*:?\s*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{4})",
                sp,
                re.I,
            )
            if not m_range:
                m_range = re.search(
                    r"(?:from\s*:?\s*)?([0-9]{4}[/\-\.][0-9]{1,2}[/\-\.][0-9]{1,2})\s*(?:to|–|-|till|through)\s*:?\s*([0-9]{4}[/\-\.][0-9]{1,2}[/\-\.][0-9]{1,2})",
                    sp,
                    re.I,
                )
            if m_range:
                f_date = m_range.group(1)
                t_date = m_range.group(2)

    f_human = format_date_human(f_date) if f_date else ""
    t_human = format_date_human(t_date) if t_date else ""

    if f_human and t_human:
        return f"{f_human} – {t_human}"
    elif f_human:
        return f"From {f_human}"
    elif t_human:
        return f"Up to {t_human}"
    return str(sp or "")


# ==============================================================================
# Field Definition Dataclass
# ==============================================================================

@dataclass
class FieldDefinition:
    canonical_key: str
    display_name: str
    intent_keywords: List[str]
    intent_regexes: List[str]
    extracted_keys: List[str]
    ocr_patterns: List[str]
    validator: Optional[Callable[[str], bool]] = None
    formatter: Optional[Callable[[Any], str]] = None
    prohibited_substitutions: List[str] = field(default_factory=list)
    applies_to_doc_types: List[str] = field(default_factory=list)


# ==============================================================================
# Field Registry
# ==============================================================================

FIELD_REGISTRY: Dict[str, FieldDefinition] = {
    # 1. PAN Number
    "pan_number": FieldDefinition(
        canonical_key="pan_number",
        display_name="PAN Number",
        intent_keywords=[
            "pan", "pan number", "pan no", "pan card number", "permanent account number",
            "panno", "pan_num"
        ],
        intent_regexes=[
            r"\bpan\b",
            r"\bpan\s*(?:no\.?|num(?:ber)?|card)\b",
            r"\bpermanent\s*account\s*number\b"
        ],
        extracted_keys=["pan_number", "pan", "pan_card_number"],
        ocr_patterns=[
            r"\b([A-Z]{5}[0-9]{4}[A-Z])\b"
        ],
        validator=lambda v: bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", str(v).strip().upper())),
        formatter=lambda v: str(v).strip().upper(),
        prohibited_substitutions=["gstin", "aadhaar", "ifsc", "account_number"],
        applies_to_doc_types=["PAN Card", "pan"],
    ),

    # 2. GSTIN
    "gstin": FieldDefinition(
        canonical_key="gstin",
        display_name="GSTIN",
        intent_keywords=[
            "gstin", "gst number", "gst no", "gst registration", "gstin number",
            "goods and services tax number", "gst code"
        ],
        intent_regexes=[
            r"\bgstin\b",
            r"\bgst\s*(?:no\.?|num(?:ber)?|code)\b",
            r"\bgst\s*registration\s*number\b"
        ],
        extracted_keys=["gstin", "gst_number", "gst_no"],
        ocr_patterns=[
            r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b"
        ],
        validator=lambda v: bool(re.match(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$", re.sub(r"\s+", "", str(v)).upper())),
        formatter=lambda v: re.sub(r"\s+", "", str(v)).upper(),
        prohibited_substitutions=["pan_number", "account_number", "ifsc"],
        applies_to_doc_types=["GST Registration Certificate", "gst_certificate", "gst"],
    ),

    # 3. IFSC Code
    "ifsc": FieldDefinition(
        canonical_key="ifsc",
        display_name="IFSC Code",
        intent_keywords=[
            "ifsc", "ifsc code", "ifs code", "rtgs code", "neft code", "rtgs/neft",
            "neft/ifsc", "ifsc no"
        ],
        intent_regexes=[
            r"\bifsc\b",
            r"\bifs\s*code\b",
            r"\brtgs\b",
            r"\bneft\b"
        ],
        extracted_keys=["ifsc", "ifsc_code", "ifs_code"],
        ocr_patterns=[
            r"\b([A-Z]{4}0[A-Z0-9]{6})\b"
        ],
        validator=lambda v: bool(re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", str(v).strip().upper())),
        formatter=lambda v: str(v).strip().upper(),
        prohibited_substitutions=["bank_name", "branch", "address", "account_number"],
        applies_to_doc_types=["Bank Statement", "bank_statement", "bank_passbook", "cancelled_cheque"],
    ),

    # 4. Branch
    "branch": FieldDefinition(
        canonical_key="branch",
        display_name="Branch",
        intent_keywords=[
            "branch", "branch name", "sol branch", "branch office", "which branch",
            "bank branch", "sol name"
        ],
        intent_regexes=[
            r"\bbranch\b",
            r"\bsol\s*branch\b",
            r"\bbranch\s*(?:name|office)?\b"
        ],
        extracted_keys=["branch", "branch_name", "branch_office"],
        ocr_patterns=[
            r"(?:Branch\s*(?:Office|Name)?\s*[:\-]\s*)([A-Za-z0-9\s,\[\]\(\)\.\/-]+?)(?=[ \t]*(?:\r?\n\r?\n|\r?\n[A-Z0-9\s]+:|$|Account|IFSC|MICR|Tel|Scheme|Opening|Joint|\bS\.NO\b))"
        ],
        validator=lambda v: bool(v and len(str(v).strip()) >= 3 and not re.search(r"^(?:Statement|Account|Balance|Customer|Period|Number|Name\(SOL\))$", str(v).strip(), re.I)),
        formatter=lambda v: re.sub(r"\s+", " ", str(v)).strip(),
        prohibited_substitutions=["address", "bank_name", "ifsc", "account_holder"],
        applies_to_doc_types=["Bank Statement", "bank_statement", "bank_passbook", "cancelled_cheque"],
    ),

    # 5. Customer Number
    "customer_number": FieldDefinition(
        canonical_key="customer_number",
        display_name="Customer Number",
        intent_keywords=[
            "customer no", "customer number", "customer id", "cust id", "cust no",
            "cif number", "cif no", "cif", "customer identification", "customer code"
        ],
        intent_regexes=[
            r"\bcustomer\s*(?:no\.?|num(?:ber)?|id|code)\b",
            r"\bcust\s*(?:no\.?|id)\b",
            r"\bcif\s*(?:no\.?|num(?:ber)?)?\b"
        ],
        extracted_keys=["customer_number", "customer_id", "cust_id", "cif", "cif_no", "cif_number"],
        ocr_patterns=[
            r"(?:Customer\s*(?:No\.?|Number|ID)|Cust\s*ID|CIF\s*(?:No\.?|Number)?)[\s:]*([A-Za-z0-9]+)"
        ],
        validator=lambda v: bool(v and str(v).strip().isalnum() and len(str(v).strip()) >= 4),
        formatter=lambda v: str(v).strip(),
        prohibited_substitutions=["account_number", "ifsc", "pan_number"],
        applies_to_doc_types=["Bank Statement", "bank_statement", "bank_passbook"],
    ),

    # 6. Account Holder
    "account_holder": FieldDefinition(
        canonical_key="account_holder",
        display_name="Account Holder",
        intent_keywords=[
            "account holder", "acc holder", "account held by", "who holds the account",
            "name of the account holder", "name of account holder", "account name",
            "who is the account holder", "account holder name", "account owner",
            "holder name"
        ],
        intent_regexes=[
            r"\baccount\s*holder(?:\s*name)?\b",
            r"\baccount\s*held\s*by\b",
            r"\bwho\s*holds\b",
            r"\bholder\s*name\b"
        ],
        extracted_keys=["account_holder", "account_holder_name", "cardholder_name", "name"],
        ocr_patterns=[
            r"(?:Account\s*Holder(?:\s*Name)?|Customer\s*Name|खातेदाराचे\s*नाव|खाताधारक\s*का\s*नाम)[\s:]*([A-Za-z][A-Za-z\s.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|Account\s*No|A/C|Address|Joint|Customer\s*ID|CIF|Nominee|IFSC|Branch))",
            r"(?:(?:Mr\.|Mrs\.|Ms\.|Shri|Smt\.)\s+([A-Za-z][A-Za-z\s.'-]{2,40}?))(?=[ \t]*(?:\r?\n|$|Account|A/C|Address|Branch|IFSC))"
        ],
        validator=lambda v: bool(v and len(str(v).strip()) >= 3 and not re.search(r"\b(Statement|Account|Balance|Branch|Bank|Customer|Number|IFSC)\b", str(v).strip(), re.I)),
        formatter=lambda v: re.sub(r"\s+", " ", str(v)).strip(),
        prohibited_substitutions=["bank_name", "branch", "father_name"],
        applies_to_doc_types=["Bank Statement", "bank_statement", "bank_passbook", "cancelled_cheque"],
    ),

    # 7. Account Number
    "account_number": FieldDefinition(
        canonical_key="account_number",
        display_name="Account Number",
        intent_keywords=[
            "account number", "account no", "a/c no", "a/c number", "acc no", "acc number",
            "bank account number"
        ],
        intent_regexes=[
            r"\baccount\s*(?:no\.?|num(?:ber)?)\b",
            r"\ba/c\s*(?:no\.?|num(?:ber)?)\b",
            r"\bacc\s*(?:no\.?|num(?:ber)?)\b"
        ],
        extracted_keys=["account_number", "account_number_masked", "account_num"],
        ocr_patterns=[
            r"(?:Account\s*(?:Number|No\.?)|A/C\s*(?:Number|No\.?))[\s:]*([X\d]{6,18})"
        ],
        validator=lambda v: bool(v and re.search(r"[X\d]{6,18}", str(v).strip(), re.I)),
        formatter=lambda v: ("X" * (len(str(v).strip()) - 4) + str(v).strip()[-4:]) if len(str(v).strip()) > 6 and not str(v).strip().startswith("X") else str(v).strip(),
        prohibited_substitutions=["customer_number", "ifsc", "micr"],
        applies_to_doc_types=["Bank Statement", "bank_statement", "bank_passbook", "cancelled_cheque"],
    ),

    # 8. Statement Period
    "statement_period": FieldDefinition(
        canonical_key="statement_period",
        display_name="Statement Period",
        intent_keywords=[
            "statement period", "statement duration", "period of statement",
            "duration of statement", "period of the statement", "statement date range",
            "transaction period"
        ],
        intent_regexes=[
            r"\bstatement\s*(?:period|duration|dates?)\b",
            r"\bperiod\s*of\s*(?:the\s*)?statement\b",
            r"\btransaction\s*period\b"
        ],
        extracted_keys=["statement_period", "transaction_period", "period"],
        ocr_patterns=[
            r"(?:Transaction\s*Period|Statement\s*Period|Period)[\s:]*(?:\(\s*)?(?:From\s*[:]\s*)?([A-Za-z0-9\/\-\.]+)\s*(?:to|-|To\s*[:])\s*([A-Za-z0-9\/\-\.]+)"
        ],
        validator=lambda v: bool(v),
        formatter=format_statement_period_human,
        prohibited_substitutions=["date_of_birth", "registration_date"],
        applies_to_doc_types=["Bank Statement", "bank_statement"],
    ),

    # 9. Date of Birth (DOB)
    "date_of_birth": FieldDefinition(
        canonical_key="date_of_birth",
        display_name="Date of Birth",
        intent_keywords=[
            "date of birth", "dob", "birth date", "birthdate", "when born", "born on"
        ],
        intent_regexes=[
            r"\bdate\s*of\s*birth\b",
            r"\bdob\b",
            r"\bbirth\s*date\b",
            r"\bborn\b"
        ],
        extracted_keys=["date_of_birth", "dob", "birth_date"],
        ocr_patterns=[
            r"(?:Date\s*of\s*Birth|DOB|जन्म\s*तारीख|जन्म\s*दिनांक)[\s:]*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{4})",
            r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b"
        ],
        validator=lambda v: bool(v and re.search(r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}", str(v))),
        formatter=format_date_human,
        prohibited_substitutions=["registration_date", "statement_period", "validity_date"],
        applies_to_doc_types=["PAN Card", "pan", "aadhaar", "passport", "driving_licence"],
    ),

    # 10. Father's Name
    "father_name": FieldDefinition(
        canonical_key="father_name",
        display_name="Father's Name",
        intent_keywords=[
            "father's name", "father name", "father", "fathers name", "parent name"
        ],
        intent_regexes=[
            r"\bfather['’]?s?\s*name\b",
            r"\bfather\b"
        ],
        extracted_keys=["father_name", "fathers_name", "father"],
        ocr_patterns=[
            r"(?:Father(?:'s)?\s*Name|वडिलांचे\s*नाव|पिता\s*का\s*नाम)[\s:]*([A-Za-z][A-Za-z\s.'-]{2,40}?)(?=[ \t]*(?:\r?\n|$|Date|DOB|Permanent|PAN))"
        ],
        validator=lambda v: bool(v and len(str(v).strip()) >= 3 and not re.search(r"\b(Income|Department|Govt|India|Permanent)\b", str(v).strip(), re.I)),
        formatter=lambda v: re.sub(r"\s+", " ", str(v)).strip(),
        prohibited_substitutions=["account_holder", "name"],
        applies_to_doc_types=["PAN Card", "pan", "driving_licence"],
    ),

    # 11. Bank Name
    "bank_name": FieldDefinition(
        canonical_key="bank_name",
        display_name="Bank Name",
        intent_keywords=[
            "bank name", "name of the bank", "which bank", "name of bank", "banking institution"
        ],
        intent_regexes=[
            r"\bbank\s*name\b",
            r"\bwhich\s*bank\b",
            r"\bname\s*of\s*(?:the\s*)?bank\b"
        ],
        extracted_keys=["bank_name", "bank", "institution_name"],
        ocr_patterns=[
            r"(?:Bank\s*Name|Name\s*of\s*Bank)[\s:]*([A-Za-z\s&]+?)(?=[ \t]*(?:\r?\n|$|Branch|IFSC|A/C))",
            r"\b(AXIS\s*BANK|STATE\s*BANK\s*OF\s*INDIA|HDFC\s*BANK|ICICI\s*BANK|PUNJAB\s*NATIONAL\s*BANK|BANK\s*OF\s*BARODA|CANARA\s*BANK|UNION\s*BANK|KOTAK\s*MAHINDRA|INDUSIND\s*BANK|YES\s*BANK|IDBI\s*BANK)\b"
        ],
        validator=lambda v: bool(v and len(str(v).strip()) >= 3),
        formatter=lambda v: re.sub(r"\s+", " ", str(v)).strip(),
        prohibited_substitutions=["ifsc", "branch", "account_holder"],
        applies_to_doc_types=["Bank Statement", "bank_statement", "bank_passbook", "cancelled_cheque"],
    ),

    # 12. Opening Balance
    "opening_balance": FieldDefinition(
        canonical_key="opening_balance",
        display_name="Opening Balance",
        intent_keywords=[
            "opening balance", "start balance", "initial balance", "starting balance"
        ],
        intent_regexes=[
            r"\bopening\s*balance\b",
            r"\bstart(?:ing)?\s*balance\b"
        ],
        extracted_keys=["opening_balance", "open_balance", "start_balance"],
        ocr_patterns=[
            r"(?:Opening\s*Balance|Start\s*Balance)[\s:]*(?:INR|Rs\.?|₹)?\s*([\d,]+\.?\d*)"
        ],
        validator=lambda v: bool(v and re.search(r"[\d,]+\.?\d*", str(v))),
        formatter=lambda v: str(v).strip(),
        prohibited_substitutions=["closing_balance"],
        applies_to_doc_types=["Bank Statement", "bank_statement"],
    ),

    # 13. Closing Balance
    "closing_balance": FieldDefinition(
        canonical_key="closing_balance",
        display_name="Closing Balance",
        intent_keywords=[
            "closing balance", "end balance", "ending balance", "final balance"
        ],
        intent_regexes=[
            r"\bclosing\s*balance\b",
            r"\bend(?:ing)?\s*balance\b"
        ],
        extracted_keys=["closing_balance", "close_balance", "end_balance"],
        ocr_patterns=[
            r"(?:Closing\s*Balance|End\s*Balance)[\s:]*(?:INR|Rs\.?|₹)?\s*([\d,]+\.?\d*)"
        ],
        validator=lambda v: bool(v and re.search(r"[\d,]+\.?\d*", str(v))),
        formatter=lambda v: str(v).strip(),
        prohibited_substitutions=["opening_balance"],
        applies_to_doc_types=["Bank Statement", "bank_statement"],
    ),

    # 14. Total Transactions
    "total_transactions": FieldDefinition(
        canonical_key="total_transactions",
        display_name="Total Transactions",
        intent_keywords=[
            "total transaction", "total transactions", "transaction count",
            "how many transactions", "sum of transactions", "transaction volume"
        ],
        intent_regexes=[
            r"\btotal\s*transactions?\b",
            r"\bhow\s*many\s*transactions\b",
            r"\btransaction\s*(?:count|volume)\b"
        ],
        extracted_keys=["transactions", "total_transactions"],
        ocr_patterns=[],
        validator=lambda v: bool(v),
        formatter=None,
        prohibited_substitutions=[],
        applies_to_doc_types=["Bank Statement", "bank_statement"],
    ),

    # 15. Legal Name (GST / Corporate)
    "legal_name": FieldDefinition(
        canonical_key="legal_name",
        display_name="Legal Name",
        intent_keywords=[
            "legal name", "legal business name", "registered legal name", "company legal name"
        ],
        intent_regexes=[
            r"\blegal\s*name\b",
            r"\blegal\s*business\s*name\b"
        ],
        extracted_keys=["legal_name", "business_name", "company_name"],
        ocr_patterns=[
            r"(?:Legal\s*Name(?:[\s/]*(?:of\s+Taxpayer)?)?)[\s:]*([A-Za-z0-9][A-Za-z0-9 \t,\.\-&_]{1,70}?)(?=[ \t]*(?:\r?\n|$|Trade\s*Name|GSTIN|Constitution|Date|Address))"
        ],
        validator=lambda v: bool(v and len(str(v).strip()) >= 3),
        formatter=lambda v: re.sub(r"\s+", " ", str(v)).strip(),
        prohibited_substitutions=["trade_name"],
        applies_to_doc_types=["GST Registration Certificate", "gst_certificate", "certificate_of_incorporation"],
    ),

    # 16. Trade Name
    "trade_name": FieldDefinition(
        canonical_key="trade_name",
        display_name="Trade Name",
        intent_keywords=[
            "trade name", "doing business as", "dba"
        ],
        intent_regexes=[
            r"\btrade\s*name\b",
            r"\bd/b/a\b"
        ],
        extracted_keys=["trade_name"],
        ocr_patterns=[
            r"(?<!Additional\s)\bTrade\s*Name(?:\s*,\s*if\s*any)?[\s:]+([A-Za-z0-9][A-Za-z0-9 \t,\.\-&]{1,70}?)(?=[ \t]*(?:\r?\n|$|Constitution|Legal\s*Name|GSTIN|Date|Address))"
        ],
        validator=lambda v: bool(v and len(str(v).strip()) >= 3),
        formatter=lambda v: re.sub(r"\s+", " ", str(v)).strip(),
        prohibited_substitutions=["legal_name"],
        applies_to_doc_types=["GST Registration Certificate", "gst_certificate"],
    ),

    # 17. Registration Date (GST / Udyam)
    "registration_date": FieldDefinition(
        canonical_key="registration_date",
        display_name="Registration Date",
        intent_keywords=[
            "registration date", "date of registration", "date of liability", "effective date of registration"
        ],
        intent_regexes=[
            r"\bregistration\s*date\b",
            r"\bdate\s*of\s*registration\b",
            r"\bdate\s*of\s*liability\b"
        ],
        extracted_keys=["registration_date", "date_of_registration", "date_of_liability"],
        ocr_patterns=[
            r"(?:Date\s*of\s*(?:Registration|Liability)|Registration\s*Date)[\s:]*([0-9]{1,2}[/\-\.][0-9]{1,2}[/\-\.][0-9]{4})"
        ],
        validator=lambda v: bool(v and re.search(r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}", str(v))),
        formatter=format_date_human,
        prohibited_substitutions=["date_of_birth"],
        applies_to_doc_types=["GST Registration Certificate", "gst_certificate", "udyam"],
    ),

    # 18. Constitution of Business
    "constitution_of_business": FieldDefinition(
        canonical_key="constitution_of_business",
        display_name="Constitution of Business",
        intent_keywords=[
            "constitution", "constitution of business", "business constitution", "entity type"
        ],
        intent_regexes=[
            r"\bconstitution(?:\s*of\s*business)?\b",
            r"\btype\s*of\s*constitution\b"
        ],
        extracted_keys=["constitution_of_business", "constitution"],
        ocr_patterns=[
            r"(?:Constitution\s*of\s*Business)[\s:]*([A-Za-z\s]+?)(?=[ \t]*(?:\r?\n|$|Address|Date|Period))"
        ],
        validator=lambda v: bool(v and len(str(v).strip()) >= 3),
        formatter=lambda v: re.sub(r"\s+", " ", str(v)).strip(),
        prohibited_substitutions=["principal_place_of_business"],
        applies_to_doc_types=["GST Registration Certificate", "gst_certificate"],
    ),

    # 19. Principal Place of Business
    "principal_place_of_business": FieldDefinition(
        canonical_key="principal_place_of_business",
        display_name="Principal Place of Business",
        intent_keywords=[
            "principal place of business", "place of business", "registered office address", "business address"
        ],
        intent_regexes=[
            r"\bprincipal\s*place(?:\s*of\s*business)?\b",
            r"\bplace\s*of\s*business\b",
            r"\bregistered\s*office\b"
        ],
        extracted_keys=["principal_place_of_business", "address", "registered_office"],
        ocr_patterns=[
            r"(?:Principal\s*Place\s*of\s*Business|Address)[\s:]*([A-Za-z0-9\s,\[\]\(\)\.\/-]+?)(?=[ \t]*(?:\r?\n\r?\n|$|Details|State|Date))"
        ],
        validator=lambda v: bool(v and len(str(v).strip()) >= 5),
        formatter=lambda v: re.sub(r"\s+", " ", str(v)).strip(),
        prohibited_substitutions=["branch", "constitution_of_business"],
        applies_to_doc_types=["GST Registration Certificate", "gst_certificate"],
    ),
}


# ==============================================================================
# Intent Detection Engine
# ==============================================================================

def detect_field_intent(query: str, doc_type: str = "") -> Optional[FieldDefinition]:
    """
    Resolve user query to a canonical FieldDefinition.
    Supports common wording variations, abbreviations, and regexes.
    Checks doc_type compatibility to avoid misinterpreting document-specific queries.
    """
    if not query or not isinstance(query, str):
        return None

    q = query.strip().lower()

    # Normalize punctuation and extra spaces
    norm_q = re.sub(r"[?!.,]", " ", q)
    norm_q = re.sub(r"\s+", " ", norm_q).strip()

    # Pre-checks for strict priority / disambiguation
    # IFSC code disambiguation: "ifsc" must NEVER be treated as bank name or branch
    if "ifsc" in norm_q or "rtgs" in norm_q or "neft" in norm_q:
        return FIELD_REGISTRY["ifsc"]

    # Customer Number vs Account Number disambiguation
    if any(k in norm_q for k in ["customer", "cif", "cust id", "cust no"]):
        return FIELD_REGISTRY["customer_number"]

    # Statement Period disambiguation
    if ("statement" in norm_q or "period" in norm_q or "duration" in norm_q) and ("period" in norm_q or "duration" in norm_q):
        return FIELD_REGISTRY["statement_period"]

    # Account Holder disambiguation
    if any(k in norm_q for k in ["account holder", "acc holder", "account held by", "who holds the account", "account name", "holder name"]):
        return FIELD_REGISTRY["account_holder"]

    # Father's Name vs Individual Name
    if "father" in norm_q:
        return FIELD_REGISTRY["father_name"]

    # Match each field definition in registry
    for fdef in FIELD_REGISTRY.values():
        # 1. Direct keyword match
        for kw in fdef.intent_keywords:
            if kw in norm_q:
                # Check for negative bounds (e.g. "pan" matching inside "company" or "span")
                if re.search(r"\b" + re.escape(kw) + r"\b", norm_q):
                    return fdef

        # 2. Intent regex match
        for rx in fdef.intent_regexes:
            if re.search(rx, norm_q):
                return fdef

    # Contextual check: "name" in PAN Card -> account holder / cardholder
    if "name" in norm_q and "pan" in doc_type.lower() and "father" not in norm_q:
        return FIELD_REGISTRY["account_holder"]

    return None


# ==============================================================================
# Field Lookup Pipeline
# ==============================================================================

def lookup_field_value(
    field_def: FieldDefinition,
    extracted_fields: Dict[str, Any],
    ocr_text: str,
    doc_type: str = "",
) -> Tuple[Optional[str], str]:
    """
    Look up a field according to the canonical hierarchy:
    1. Structured extracted_fields
    2. OCR Text search using validated patterns
    3. Anti-substitution validation
    Returns (resolved_value, source_type):
    - source_type: 'extracted', 'ocr', 'not_found', 'prohibited'
    """
    val: Optional[Any] = None
    source = "not_found"

    # Step 1: Check canonical and alias keys in structured extracted_fields
    for key in field_def.extracted_keys:
        if key in extracted_fields and extracted_fields[key] is not None:
            raw_cand = extracted_fields[key]
            if str(raw_cand).strip() and str(raw_cand).strip().lower() != "none":
                val = raw_cand
                source = "extracted"
                break

    # Special handling for total_transactions calculation
    if field_def.canonical_key == "total_transactions":
        txns = extracted_fields.get("transactions")
        if isinstance(txns, list) and txns:
            tot_amt = 0.0
            cr_amt = 0.0
            dr_amt = 0.0
            cr_count = 0
            dr_count = 0
            for t in txns:
                try:
                    amt = float(str(t.get("amount", "0")).replace(",", ""))
                    tot_amt += amt
                    ttype = str(t.get("type", "")).upper()
                    if "CR" in ttype:
                        cr_amt += amt
                        cr_count += 1
                    elif "DR" in ttype:
                        dr_amt += amt
                        dr_count += 1
                except (ValueError, TypeError):
                    pass
            formatted = (
                f"I found a total transaction amount of ₹{tot_amt:,.2f} across the {len(txns)} transactions visible in this statement.\n\n"
                f"• Credits / Deposits: ₹{cr_amt:,.2f} ({cr_count} transactions)\n"
                f"• Debits / Withdrawals: ₹{dr_amt:,.2f} ({dr_count} transactions)"
            )
            return formatted, "extracted"

    # Special handling for GSTIN in OCR text: support whitespace tolerance
    if not val and field_def.canonical_key == "gstin":
        for l in ocr_text.splitlines():
            no_space = re.sub(r"[ \t]+", "", l)
            m = re.search(r"([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])", no_space)
            if m:
                val = m.group(1).upper()
                source = "ocr"
                break

    # Step 2: Search OCR text if missing from structured keys
    if not val and ocr_text:
        for pat in field_def.ocr_patterns:
            m = re.search(pat, ocr_text, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if field_def.validator is None or field_def.validator(cand):
                    val = cand
                    source = "ocr"
                    break

    # If nothing found
    if not val:
        return None, "not_found"

    # Step 3: Anti-substitution guards
    str_val = str(val).strip()
    if field_def.canonical_key == "ifsc":
        # IFSC must NEVER be a bank name or branch
        if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", str_val.upper()):
            return None, "prohibited"
        if any(b in str_val.upper() for b in ["STATE BANK", "AXIS", "HDFC", "ICICI", "BANK"]):
            return None, "prohibited"

    elif field_def.canonical_key == "customer_number":
        # Customer number must NEVER be account number
        acc = extracted_fields.get("account_number") or ""
        if acc and str_val == str(acc).strip():
            return None, "prohibited"

    elif field_def.canonical_key == "pan_number":
        # PAN must NEVER be GSTIN (15 chars)
        if len(str_val) != 10:
            return None, "prohibited"

    elif field_def.canonical_key == "date_of_birth":
        # DOB must NEVER be statement period or registration date
        if "to" in str_val.lower() or "–" in str_val:
            return None, "prohibited"

    # Step 4: Format value
    if field_def.formatter:
        formatted_val = field_def.formatter(val)
    else:
        formatted_val = str_val

    return formatted_val, source
