# Company OCR Service — Architectural Guardrails & Invariants

## Core Principles & Regression Prevention
1. **Preserve Offline OCR Logic**:
   - RapidOCR is the primary, offline OCR engine.
   - Never replace RapidOCR with cloud AI for standard offline processing.
   - All 22 predefined document extractors, regex rules, and checksum validations must remain strictly functional.

2. **Dual-Mode Architecture**:
   - **Offline Mode**: Uses local RapidOCR + rule-based extractors + local/Supabase storage. Operates with zero cloud AI dependencies.
   - **AI Mode**: Uses AI Provider Manager (local Ollama Qwen2.5-VL or external OpenRouter / Google Gemini) for open-ended classification, reasoning synthesis, and grounded chat.

3. **Authentication & Media Serving**:
   - All protected backend endpoints require `Depends(get_current_user)` enforcing Supabase Bearer JWTs.
   - Native HTML tags (`<object>`, `<img>`, `<iframe>`) do not send custom headers. File previews must be fetched via authenticated API (`getDocumentFile(docId)`), converted to local Blob object URLs (`URL.createObjectURL(blob)`), and cleaned up with `URL.revokeObjectURL()`.
   - On HTTP 401, the frontend must attempt session refresh (`handleAuthFailureAndRefresh()`) and retry once before invoking logout.

4. **Security & Privacy Invariants**:
   - Document files are encrypted at rest with AES-256-GCM (`encryption.py`) before saving to Supabase Storage or local cache.
   - **User Isolation**: Users must only access their own documents (`user_id` check in database and storage). Accessing another user's document must return `404 Not Found`.
   - **Zero Secrets / Contents Logging**: Never log raw JWTs, API keys, document text, or document bytes in application or audit logs. Only log metadata: `user_id`, `document_id`, `status`, `duration_ms`.

5. **Document Authenticity & Review Required Terminology**:
   - Statuses: `verified`, `review_required`, `unsupported`.
   - Never use speculative words like "fake", "forged", or "fraudulent". Use objective terminology like "Visible inconsistencies detected" or "Review Required".

6. **Extracted Text State Synchronization**:
   - Extracted OCR text must be synchronized across `extracted_text`, `raw_text`, and `ocr_text` in both backend responses and `normalizeAiDocument()`.
   - Preview loading or failure must never wipe out or reset OCR text or fields to `0 chars`.
