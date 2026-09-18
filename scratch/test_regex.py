import re
from typing import Any, Dict, List, Optional

def test_logic():
    text = """
    3_EXTENT
    Joint Holder :-  THIRD FLOOR SHOP NO 312 DELUX FORTUNE~C T S NUMBER 2521 AND 2521 2 PIMPRI~PUNE~MAHARASHTRA~411017     Scheme :
    BURGUNDY CURRENT ACCOUNT     currency : INR      
    Customer No : 978738241     IFSC Code : UTIB0001435     MICR Code : 411211022     CKYC Number: **********4308     
    Account Statement Report
    Statement of Axis Bank Account No : 925020052380170 for the period ( From : 30/07/2025 To : 30/07/2026 )
    Opening Balance: INR 0.00
    S.NO Transaction Date Value Date Particulars Amount(INR) Debit/Credit Balance(INR) Cheque Number Branch Name(SOL)
    1 21/11/2025 21/11/2025 CLG/100003/071125/Kalpavruks/ 5,00,000.00 CR 5,00,000.00 100003 AJMERA COMPLEX,PIMPRI,PUNE [MH (2568)
    2 23/11/2025 23/11/2025 NEFT/DH/AXODH32706269231/3EXTEN T/HDFC BANK////// 1.00 DR 4,99,999.00 AJMERA COMPLEX,PIMPRI,PUNE [MH (1435)
    """
    
    # 1. Customer No
    m_cust = re.search(r"(?:Customer\s*(?:No\.?|Number|ID)|Cust\s*ID|CIF\s*(?:No\.?|Number)?)[\s:]*([A-Za-z0-9]+)", text, re.I)
    assert m_cust and m_cust.group(1) == "978738241", f"Cust match failed: {m_cust}"
    print("Customer No:", m_cust.group(1))
    
    # 2. IFSC
    m_ifsc = re.search(r"(?:IFS\s*Code|IFSC(?:\s*Code)?|RTGS/NEFT/IFSC)[\s:]*([A-Z]{4}0[A-Z0-9]{6})|\b([A-Z]{4}0[A-Z0-9]{6})\b", text, re.I)
    ifsc_val = (m_ifsc.group(1) or m_ifsc.group(2)).upper() if m_ifsc else None
    assert ifsc_val == "UTIB0001435", f"IFSC match failed: {ifsc_val}"
    print("IFSC:", ifsc_val)
    
    # 3. Period
    m_period = re.search(r"(?:Transaction\s*Period|Statement\s*Period|Period)[\s:]*(?:\(\s*)?(?:From\s*[:]\s*)?([A-Za-z0-9\/\-\.]+)\s*(?:to|-|To\s*[:])\s*([A-Za-z0-9\/\-\.]+)", text, re.I)
    assert m_period and m_period.group(1) == "30/07/2025" and m_period.group(2) == "30/07/2026"
    print("Period:", m_period.group(1), "to", m_period.group(2))
    
    # 4. Branch
    m_branch = re.search(r"Branch\s*Name(?:\(SOL\))?[\s\S]*?\d+\s+[\d\.\,]+\s+(?:CR|DR)\s+[\d\.\,]+\s+\d*\s*([A-Za-z\s,]+(?:\[[A-Za-z0-9\s\(\)]+\])?)", text, re.I)
    branch_val = None
    if m_branch:
        branch_val = re.sub(r"\s+", " ", m_branch.group(1)).strip()
    assert branch_val and "AJMERA" in branch_val, f"Branch failed: {branch_val}"
    print("Branch:", branch_val)
    
    print("ALL REGEX TESTS PASSED!")

if __name__ == "__main__":
    test_logic()
