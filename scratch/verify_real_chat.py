import asyncio
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
import pypdf
from ocr_engine import OCRDocumentResult, OCRPageResult, parse_text_into_ocr_lines
import extractors
import ai_service

async def verify_chat_pipeline():
    pdf_path = "C:/Users/sachi/Downloads/Account_Statement_Report_30-07-2026_1246hrs.PDF"
    reader = pypdf.PdfReader(pdf_path)
    full_text = "\n".join([p.extract_text() or "" for p in reader.pages])
    pages = [OCRPageResult(page_num=i+1, full_text=p.extract_text() or "", lines=parse_text_into_ocr_lines(p.extract_text() or ""), average_confidence=1.0) for i, p in enumerate(reader.pages)]
    doc_res = OCRDocumentResult(full_text=full_text, pages=pages, average_confidence=1.0)
    
    extracted_fields, confidences = extractors.extract_document_fields("bank_statement", doc_res)
    
    stored_analysis = {
        "document_id": "test_axis_doc_123",
        "document_type": "Bank Statement",
        "confidence": "high",
        "summary": "This document is a Bank Statement for account held by SNEHA at Axis Bank.",
        "evidence": ["Bank Statement signatures detected"],
        "extracted_fields": extracted_fields,
    }
    
    print("=== EXTRACTED FIELDS IN STORED CANONICAL ANALYSIS ===")
    for k, v in extracted_fields.items():
        if k != "transactions":
            print(f"  {k}: {v}")
    print(f"  transactions count: {len(extracted_fields.get('transactions', []))}")
    print("=" * 60)
    
    history = []
    
    questions = [
        "What is the bank name?",
        "What is the account number?",
        "What is the account holder?",
        "What is the statement period?",
        "What is the Customer No?",
        "Why?",
        "What is the branch?",
        "What is the IFSC Code?",
        "What is the total transactions amount?",
    ]
    
    for q in questions:
        reply = await ai_service.chat_with_document(
            document_text=full_text,
            filename="Account_Statement_Report_30-07-2026_1246hrs.PDF",
            message=q,
            history=history,
            stored_analysis=stored_analysis,
        )
        print(f"\nUser: {q}")
        print(f"Assistant:\n{reply}")
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": reply})

    # Assertions
    # 1. Bank name
    assert "Axis Bank" in history[1]["content"], "Bank name verification failed"
    # 2. Account number
    assert "0170" in history[3]["content"], "Account number verification failed"
    # 3. Account holder
    assert "SNEHA" in history[5]["content"], "Account holder verification failed"
    assert "individual's name" not in history[5]["content"], "Account holder hallucinated failure"
    # 4. Statement period
    assert "{'from_date'" not in history[7]["content"], "Python dict leaked in statement period"
    assert "30/07/2025" in history[7]["content"] and "30/07/2026" in history[7]["content"], "Statement period dates missing"
    # 5. Customer number
    assert "978738241" in history[9]["content"], "Customer number missing"
    # 6. Follow-up Why?
    assert "employee" not in history[11]["content"].lower(), "Follow-up hallucinated employee name"
    assert "customer number" in history[11]["content"].lower(), "Follow-up did not reference Customer Number"
    # 7. Branch
    assert "AJMERA COMPLEX" in history[13]["content"], "Branch verification failed"
    # 8. IFSC
    assert "UTIB0001435" in history[15]["content"], "IFSC verification failed"
    assert "State Bank of India" not in history[15]["content"], "IFSC hallucinated State Bank of India"
    # 9. Total transactions
    assert "₹" in history[17]["content"] and "Credits" in history[17]["content"], "Total transactions clarification missing"
    
    print("\n" + "=" * 60)
    print("ALL 9 TESTED QUESTIONS PASSED STRICT VERIFICATION!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(verify_chat_pipeline())
