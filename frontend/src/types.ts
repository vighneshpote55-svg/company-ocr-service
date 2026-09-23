/**
 * Document OCR Web Application - Types
 */

export type DocumentStatus = 'completed' | 'low_confidence' | 'warning' | 'failed' | 'error' | 'processing';

export type VerificationStatus = 'verified' | 'review_required' | 'unsupported' | string;

export type TextSource = 'embedded_pdf_text' | 'paddle_ocr' | 'rapid_ocr' | string;

export interface EngineInfo {
  engine: string;
  display_name: string;
  version: string;
  device: string;
  status: string;
  backend?: string;
  [key: string]: any;
}

export interface SupportedType {
  id: string;
  name: string;
  category: string;
}

export interface DashboardStats {
  total: number;
  total_documents?: number;
  ocr_processed: number;
  ocr_not_required: number;
  completed: number;
  failed: number;
  offline_documents?: number;
  ai_documents?: number;
  total_storage_bytes?: number;
  total_storage_mb?: number;
}

export interface DocumentItem {
  id: string;
  document_id?: string;
  filename: string;
  file_path: string;
  file_size: number;
  file_type: string;
  doc_type: string;
  document_type: string;
  issuer?: string | null;
  evidence?: string[];
  reasoning?: string[];
  summary?: string;
  ocr_required: boolean;
  text_source: TextSource;
  status: DocumentStatus;
  confidence: number;
  confidence_level?: string;
  pages: number;
  reason?: string | null;
  extracted_fields: Record<string, any>;
  fields?: Record<string, any>;
  raw_fields?: Record<string, any>;
  field_confidences: Record<string, number>;
  extracted_text: string;
  raw_text?: string;
  ocr_text?: string;
  checksum_valid?: boolean;
  checksum_reason?: string | null;
  cross_check?: {
    match: boolean;
    confidence: number;
    score: number;
    discrepancies: string[];
    matches?: string[];
  } | null;
  has_preview: boolean;
  preview_url: string | null;
  file_url: string;
  created_at: string;
  is_local_ai?: boolean;
  model_used?: string;
  ai_analysis?: any;
  verification_status?: VerificationStatus;
  review_required?: boolean;
  risk_score?: number;
  suspicious_signals?: Array<string | { signal: string; severity?: string; description?: string }>;
  human_review_reason?: string | null;
  verified_by_ai?: boolean;
  verification_timestamp?: string;
}

export interface UploadProgress {
  step: 'idle' | 'uploading' | 'analyzing' | 'extracting' | 'verifying' | 'done' | 'error';
  percent: number;
  message: string;
}

export interface AuthConfig {
  baseUrl: string;
  authMode: 'none' | 'jwt' | 'api_key';
  token?: string;
  apiKey?: string;
  clientId?: string;
  clientSecret?: string;
}

export interface AuthStatusResponse {
  auth_enabled: boolean;
  auth_mode: string;
}

export type AppMode = 'offline' | 'ai';

export interface AiAnalysisResult {
  id?: string;
  document_id: string;
  filename: string;
  document_type: string;
  confidence: 'high' | 'medium' | 'low' | string | number;
  confidence_level?: string;
  summary: string;
  reasoning: string[];
  evidence?: string[];
  extracted_fields?: Record<string, any>;
  file_url: string;
  preview_url?: string | null;
  file_size: number;
  pages: number;
  text_source: string;
  extracted_text: string;
  raw_text?: string;
  ocr_text?: string;
  is_local_ai?: boolean;
  model_used?: string;
  processing_time_seconds?: number;
  doc_type?: string;
  file_type?: string;
  file_path?: string;
  status?: DocumentStatus;
  ocr_required?: boolean;
  created_at?: string;
  has_preview?: boolean;
  verification_status?: VerificationStatus;
  review_required?: boolean;
  risk_score?: number;
  suspicious_signals?: Array<string | { signal: string; severity?: string; description?: string }>;
  human_review_reason?: string | null;
  verified_by_ai?: boolean;
  verification_timestamp?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  citations?: string[];
}

export interface OllamaStatusResponse {
  reachable: boolean;
  model_installed: boolean;
  model: string;
  installed_models?: string[];
  message?: string;
  error?: string;
}

export interface AIProviderConfig {
  active_provider: string;
  active_model: string;
  mode: 'local' | 'external';
  api_key_configured: boolean;
  base_url?: string;
  ollama_available?: boolean;
  local_fallback_available?: boolean;
  fallback_on_error?: boolean;
}

export interface AIProviderStatus {
  active_provider: string;
  active_model: string;
  mode: 'local' | 'external';
  api_key_configured: boolean;
  ollama_available: boolean;
  local_fallback_available: boolean;
  message?: string;
}

export interface AIConnectionTestResult {
  success: boolean;
  provider: string;
  model: string;
  message: string;
  latency_ms?: number;
}

export interface AiStatusResponse {
  configured: boolean;
  provider: string;
  model: string;
  base_url: string;
  message?: string;
  ollama?: OllamaStatusResponse;
}

export interface OfflineUploadResult {
  supported: boolean;
  status: string;
  message?: string;
  doc_type?: string;
  document_type?: string;
  confidence?: number;
  extracted_text?: string;
  [key: string]: any;
}

/**
 * Normalizes any document or AI analysis payload to ensure safe property access
 * across both DocumentItem and AiAnalysisResult consumer components.
 */
export function normalizeAiDocument(raw: any): DocumentItem & AiAnalysisResult {
  if (!raw || typeof raw !== 'object') {
    raw = {};
  }

  // 1. Resolve ID safely
  const id = String(raw.id || raw.document_id || `doc_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`);

  // 2. Resolve Filename & Extension safely
  const filename = String(raw.filename || 'uploaded_document');
  const dotIdx = filename.lastIndexOf('.');
  const detectedExt = dotIdx !== -1 ? filename.slice(dotIdx).toLowerCase() : '.pdf';
  const file_type = raw.file_type ? String(raw.file_type) : detectedExt;

  // 3. Resolve Document Type & Classification
  const document_type = String(raw.document_type || raw.doc_type || 'Unknown Document');
  const isUnknown =
    document_type === 'Unknown Document' ||
    document_type === 'unknown' ||
    raw.doc_type === 'unknown';
  const doc_type = raw.doc_type || (isUnknown ? 'unknown' : 'ai_analyzed');

  // 4. Resolve Confidence (both numeric and string representations)
  let confNum = 0.95;
  let confStr: 'high' | 'medium' | 'low' = 'high';

  if (typeof raw.confidence === 'number') {
    confNum = Math.min(1, Math.max(0, raw.confidence));
    confStr = confNum >= 0.85 ? 'high' : confNum >= 0.65 ? 'medium' : 'low';
  } else if (typeof raw.confidence === 'string') {
    const lower = raw.confidence.toLowerCase().trim();
    if (lower === 'high') {
      confNum = 0.95;
      confStr = 'high';
    } else if (lower === 'medium') {
      confNum = 0.80;
      confStr = 'medium';
    } else if (lower === 'low') {
      confNum = 0.50;
      confStr = 'low';
    } else {
      const parsed = parseFloat(lower);
      if (!isNaN(parsed)) {
        confNum = parsed > 1 ? parsed / 100 : Math.max(0, parsed);
        confStr = confNum >= 0.85 ? 'high' : confNum >= 0.65 ? 'medium' : 'low';
      }
    }
  }

  // 5. Resolve Reasoning & Evidence safely as string[]
  const rawReasoning = Array.isArray(raw.reasoning)
    ? raw.reasoning
    : (typeof raw.reasoning === 'string' ? [raw.reasoning] : []);
  const rawEvidence = Array.isArray(raw.evidence)
    ? raw.evidence
    : (typeof raw.evidence === 'string' ? [raw.evidence] : []);
  const combinedEvidence: string[] = Array.from(new Set([...rawReasoning, ...rawEvidence]))
    .filter(item => item !== null && item !== undefined)
    .map(item => (typeof item === 'string' ? item : JSON.stringify(item)));

  // 6. Resolve Summary safely as string
  let summary = 'Document analysis completed successfully.';
  if (typeof raw.summary === 'string' && raw.summary.trim()) {
    summary = raw.summary;
  } else if (typeof raw.summary === 'object' && raw.summary !== null) {
    summary = JSON.stringify(raw.summary);
  } else if (isUnknown) {
    summary = `I analyzed "${filename}". The document type could not be confidently identified, but the full text and structural tokens have been extracted.`;
  }

  // 7. Resolve Extracted Fields safely as Record<string, any>
  let extracted_fields: Record<string, any> = {};
  if (typeof raw.extracted_fields === 'object' && raw.extracted_fields !== null && !Array.isArray(raw.extracted_fields)) {
    extracted_fields = raw.extracted_fields;
  } else if (typeof raw.fields === 'object' && raw.fields !== null && !Array.isArray(raw.fields)) {
    extracted_fields = raw.fields;
  }

  // 8. Resolve URLs defensively: never produce /api/documents/undefined/file
  const file_url = raw.file_url || (id && id !== 'undefined' && id !== 'null' ? `/api/documents/${id}/file` : '');
  const preview_url = raw.preview_url !== undefined ? raw.preview_url : (id && id !== 'undefined' && id !== 'null' ? `/api/documents/${id}/preview` : '');

  // 9. Resolve Authenticity & Verification fields (Phase 9)
  let verification_status: VerificationStatus = 'verified';
  if (raw.verification_status) {
    verification_status = raw.verification_status;
  } else if (isUnknown || doc_type === 'unknown') {
    verification_status = 'unsupported';
  } else if (raw.review_required || (typeof raw.risk_score === 'number' && raw.risk_score >= 30)) {
    verification_status = 'review_required';
  }

  const review_required = raw.review_required !== undefined
    ? Boolean(raw.review_required)
    : (verification_status === 'review_required');

  const risk_score = typeof raw.risk_score === 'number'
    ? Math.min(100, Math.max(0, raw.risk_score))
    : (verification_status === 'review_required' ? 45 : 0);

  const rawSignals = Array.isArray(raw.suspicious_signals) ? raw.suspicious_signals : [];
  const suspicious_signals = rawSignals.map((s: any) =>
    typeof s === 'string' ? s : (s?.description || s?.signal || JSON.stringify(s))
  );

  const human_review_reason = raw.human_review_reason || (review_required ? 'Visible inconsistencies detected.' : null);
  const verified_by_ai = raw.verified_by_ai !== undefined ? Boolean(raw.verified_by_ai) : true;
  const verification_timestamp = raw.verification_timestamp || raw.created_at || new Date().toISOString();

  return {
    id,
    document_id: id,
    filename,
    file_path: raw.file_path || '',
    file_size: typeof raw.file_size === 'number' ? raw.file_size : 0,
    file_type,
    doc_type,
    document_type,
    issuer: raw.issuer || null,
    evidence: combinedEvidence,
    reasoning: combinedEvidence,
    ocr_required: raw.ocr_required !== undefined ? Boolean(raw.ocr_required) : false,
    text_source: String(raw.text_source || 'ai_mode'),
    status: (raw.status === 'failed' || raw.status === 'error') ? 'failed' : 'completed',
    confidence: confNum,
    confidence_level: confStr,
    pages: typeof raw.pages === 'number' && raw.pages > 0 ? raw.pages : 1,
    reason: raw.reason || null,
    extracted_fields,
    fields: extracted_fields,
    raw_fields: extracted_fields,
    field_confidences: (typeof raw.field_confidences === 'object' && raw.field_confidences !== null) ? raw.field_confidences : {},
    extracted_text: (
      (typeof raw.extracted_text === 'string' && raw.extracted_text) ||
      (typeof raw.raw_text === 'string' && raw.raw_text) ||
      (typeof raw.ocr_text === 'string' && raw.ocr_text) ||
      (typeof raw.text === 'string' && raw.text) ||
      (typeof raw.ocr_result?.raw_text === 'string' && raw.ocr_result.raw_text) ||
      (typeof raw.ocr_result?.text === 'string' && raw.ocr_result.text) ||
      ''
    ),
    raw_text: (
      (typeof raw.raw_text === 'string' && raw.raw_text) ||
      (typeof raw.extracted_text === 'string' && raw.extracted_text) ||
      (typeof raw.ocr_text === 'string' && raw.ocr_text) ||
      (typeof raw.text === 'string' && raw.text) ||
      (typeof raw.ocr_result?.raw_text === 'string' && raw.ocr_result.raw_text) ||
      (typeof raw.ocr_result?.text === 'string' && raw.ocr_result.text) ||
      ''
    ),
    ocr_text: (
      (typeof raw.ocr_text === 'string' && raw.ocr_text) ||
      (typeof raw.extracted_text === 'string' && raw.extracted_text) ||
      (typeof raw.raw_text === 'string' && raw.raw_text) ||
      (typeof raw.text === 'string' && raw.text) ||
      (typeof raw.ocr_result?.raw_text === 'string' && raw.ocr_result.raw_text) ||
      (typeof raw.ocr_result?.text === 'string' && raw.ocr_result.text) ||
      ''
    ),
    checksum_valid: raw.checksum_valid !== undefined ? Boolean(raw.checksum_valid) : undefined,
    checksum_reason: raw.checksum_reason || null,
    cross_check: raw.cross_check || null,
    has_preview: Boolean(raw.has_preview || raw.preview_url),
    preview_url,
    file_url,
    created_at: raw.created_at || new Date().toISOString(),
    summary,
    is_local_ai: raw.is_local_ai !== undefined ? Boolean(raw.is_local_ai) : true,
    model_used: raw.model_used || 'qwen2.5vl:3b',
    ai_analysis: raw.ai_analysis || null,
    verification_status,
    review_required,
    risk_score,
    suspicious_signals,
    human_review_reason,
    verified_by_ai,
    verification_timestamp,
  };
}
