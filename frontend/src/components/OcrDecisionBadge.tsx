import React from 'react';
import { Zap, Scan, CheckCircle, AlertTriangle, AlertCircle, FileText, Sparkles } from 'lucide-react';
import type { DocumentItem, EngineInfo } from '../types';

interface OcrDecisionBadgeProps {
  document: DocumentItem;
  engineInfo?: EngineInfo | null;
}

export const OcrDecisionBadge: React.FC<OcrDecisionBadgeProps> = ({ document, engineInfo }) => {
  const isBypassed = !document.ocr_required;
  const isError = document.status === 'error' || document.status === 'failed';
  const isUnknown =
    document.doc_type === 'unknown' ||
    document.document_type === 'Unknown Document';

  const engineName =
    document.text_source === 'rapid_ocr'
      ? 'RapidOCR'
      : document.text_source === 'paddle_ocr'
      ? 'PaddleOCR'
      : engineInfo?.display_name || 'OCR Engine';

  // Resolve actual detected document type name
  const docTypeTitle =
    document.document_type &&
    document.document_type !== 'Unsupported Document' &&
    document.document_type !== 'Ai Analyzed' &&
    document.document_type !== 'Unknown Document'
      ? document.document_type
      : document.doc_type &&
        document.doc_type !== 'unknown' &&
        document.doc_type !== 'ai_analyzed'
      ? document.doc_type
          .replace(/_/g, ' ')
          .replace(/\b\w/g, (l) => l.toUpperCase())
      : 'Scanned Document';

  // Resolve issuing authority or bank name when available
  const fields = document.extracted_fields || document.fields || {};
  const issuer =
    document.issuer ||
    fields.bank_name ||
    fields.employer_name ||
    fields.utility_provider ||
    fields.issuing_authority ||
    (document.doc_type === 'pan' ? 'Income Tax Department' : null) ||
    (document.doc_type === 'aadhaar' ? 'UIDAI' : null) ||
    (document.doc_type === 'passport' ? 'Republic of India' : null);

  const displayTitle =
    docTypeTitle !== 'Scanned Document'
      ? issuer
        ? `${docTypeTitle} • ${issuer}`
        : docTypeTitle
      : null;

  const bannerTitle = isError
    ? '❌ OCR Extraction Failed — Document Unreadable'
    : isUnknown
    ? 'Unknown Document'
    : displayTitle
    ? isBypassed
      ? `⚡ ${displayTitle} — Text Layer Detected`
      : `🔍 ${displayTitle} — ${engineName} Executed`
    : isBypassed
    ? '⚡ Text Layer Detected — OCR Pass Bypassed'
    : `🔍 Scanned Document — ${engineName} Executed`;

  const bannerDesc = isError
    ? (document.reason ||
        'The engine returned empty text or zero confidence. Please ensure the document is clear, correctly rotated, and high contrast.')
    : isUnknown
    ? 'Offline OCR completed successfully.'
    : isBypassed
    ? 'PDF contains a clean digital text layer (≥ 50 characters). Extracted directly with zero character distortion.'
    : `Raster image or scanned document processed via ${engineName} neural OCR pass with line confidence scoring.`;

  return (
    <div
      className={`ocr-decision-banner ${
        isError ? 'error' : isBypassed ? 'bypassed' : isUnknown ? 'unknown-badge-style' : 'paddle'
      }`}
      style={
        isError
          ? {
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              borderColor: 'rgba(239, 68, 68, 0.3)',
            }
          : isUnknown
          ? {
              backgroundColor: 'rgba(99, 102, 241, 0.08)',
              borderColor: 'rgba(99, 102, 241, 0.25)',
            }
          : undefined
      }
    >
      <div className="decision-left">
        <div
          className="decision-icon"
          style={{
            backgroundColor: isError
              ? 'rgba(239, 68, 68, 0.2)'
              : isBypassed
              ? 'rgba(16, 185, 129, 0.2)'
              : 'rgba(99, 102, 241, 0.2)',
            color: isError ? '#ef4444' : isBypassed ? '#34d399' : '#818cf8',
          }}
        >
          {isError ? <AlertCircle size={22} /> : isBypassed ? <Zap size={22} /> : <Scan size={22} />}
        </div>
        <div>
          <div
            className="decision-title"
            style={{
              color: isError ? '#ef4444' : isBypassed ? '#34d399' : '#a5b4fc',
            }}
          >
            {bannerTitle}
          </div>
          <div className="decision-desc">
            {bannerDesc}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '0.65rem', alignItems: 'center', flexWrap: 'wrap' }}>
        {isUnknown ? (
          <>
            <div
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'rgba(16, 185, 129, 0.15)',
                color: '#34d399',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                fontSize: '0.78rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              <CheckCircle size={14} />
              <span>OCR Completed</span>
            </div>

            <div
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'rgba(129, 140, 248, 0.15)',
                color: '#818cf8',
                border: '1px solid rgba(129, 140, 248, 0.3)',
                fontSize: '0.78rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              <FileText size={14} />
              <span>Raw Text Available</span>
            </div>

            <div
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'rgba(59, 130, 246, 0.15)',
                color: '#60a5fa',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                fontSize: '0.78rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
              }}
            >
              <Sparkles size={14} />
              <span>AI Mode Recommended</span>
            </div>
          </>
        ) : null}

        <div
          style={{
            padding: '0.35rem 0.75rem',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'rgba(255, 255, 255, 0.08)',
            fontSize: '0.78rem',
            fontFamily: 'var(--font-mono)',
          }}
        >
          Confidence: <strong>{
            typeof document.confidence === 'number'
              ? Math.round(document.confidence * 100)
              : typeof (document as any).confidence === 'string' && !isNaN(parseFloat((document as any).confidence))
              ? Math.round(parseFloat((document as any).confidence) * (parseFloat((document as any).confidence) <= 1 ? 100 : 1))
              : 95
          }%</strong>
        </div>

        <div
          style={{
            padding: '0.35rem 0.75rem',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'rgba(255, 255, 255, 0.08)',
            fontSize: '0.78rem',
          }}
        >
          {document.pages || 1} {(document.pages || 1) === 1 ? 'Page' : 'Pages'}
        </div>

        {!isUnknown && (document.checksum_valid !== undefined || document.status === 'warning') && (
          <div
            style={{
              padding: '0.35rem 0.75rem',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: document.checksum_valid ? 'var(--success-bg)' : 'var(--warning-bg)',
              color: document.checksum_valid ? '#34d399' : '#fbbf24',
              border: `1px solid ${document.checksum_valid ? 'var(--success-border)' : 'var(--warning-border)'}`,
              fontSize: '0.78rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            {document.checksum_valid ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
            {document.checksum_valid
              ? 'Checksums Verified'
              : (document.checksum_reason || document.reason || 'Checksum Warning')}
          </div>
        )}
      </div>
    </div>
  );
};
