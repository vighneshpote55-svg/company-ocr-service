import React from 'react';
import {
  FileCheck,
  UploadCloud,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Layers,
  HardDrive,
  FileCode,
  ShieldAlert,
} from 'lucide-react';
import type { AiAnalysisResult } from '../types';

interface AIAnalysisCardProps {
  document: AiAnalysisResult;
  onUploadNew: () => void;
  onReset: () => void;
}

export const AIAnalysisCard: React.FC<AIAnalysisCardProps> = ({
  document,
  onUploadNew,
  onReset,
}) => {
  const rawConf = (document as any).confidence_level || document.confidence || 'high';
  const confidenceLower = typeof rawConf === 'string'
    ? rawConf.toLowerCase()
    : (typeof rawConf === 'number' && rawConf >= 0.85 ? 'high' : rawConf >= 0.65 ? 'medium' : 'low');
  const confidenceLabel =
    confidenceLower === 'high'
      ? 'High Confidence'
      : confidenceLower === 'medium'
      ? 'Medium Confidence'
      : 'Low Confidence';

  const formattedSize = ((document.file_size || 0) / 1024).toFixed(1);

  // Authenticity & Verification status
  const verifStatus = document.verification_status || (document.review_required ? 'review_required' : 'verified');
  const riskScore = typeof document.risk_score === 'number' ? document.risk_score : 0;
  const isReviewRequired = verifStatus === 'review_required' || Boolean(document.review_required);
  const isUnsupported = verifStatus === 'unsupported';
  const signals = Array.isArray(document.suspicious_signals) ? document.suspicious_signals : [];

  return (
    <div className="ai-analysis-card">
      <div className="ai-analysis-card-top">
        <div className="ai-analysis-header-left">
          <div className="ai-analysis-icon-box">
            <FileCheck size={28} className="ai-analysis-doc-icon" />
          </div>
          <div className="ai-analysis-title-group">
            <div className="ai-analysis-name-row">
              <h3 className="ai-analysis-filename" title={document.filename}>
                {document.filename}
              </h3>
              <span className={`ai-confidence-pill ${confidenceLower}`}>
                <CheckCircle2 size={12} />
                <span>{confidenceLabel}</span>
              </span>

              {/* Verification Status Badge */}
              {isReviewRequired ? (
                <span className="ai-status-pill review-required" data-testid="badge-review-required" style={{ backgroundColor: 'rgba(249, 115, 22, 0.15)', color: '#fb923c', border: '1px solid rgba(249, 115, 22, 0.3)' }}>
                  <AlertTriangle size={12} />
                  <span>🟠 Review Required</span>
                </span>
              ) : isUnsupported ? (
                <span className="ai-status-pill unsupported" data-testid="badge-unsupported" style={{ backgroundColor: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8', border: '1px solid rgba(148, 163, 184, 0.3)' }}>
                  <HelpCircle size={12} />
                  <span>Unsupported</span>
                </span>
              ) : (
                <span className="ai-status-pill verified" data-testid="badge-verified" style={{ backgroundColor: 'rgba(34, 197, 94, 0.15)', color: '#4ade80', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
                  <CheckCircle2 size={12} />
                  <span>Verified</span>
                </span>
              )}

              {/* Risk Score Pill */}
              <span className="ai-status-pill risk-score-pill" style={{ fontSize: '0.75rem', fontWeight: 600, color: isReviewRequired ? '#fb923c' : 'var(--text-muted)' }}>
                <span>{`Risk Score: ${riskScore}%`}</span>
              </span>
            </div>

            <div className="ai-analysis-meta-chips">
              <span className="ai-meta-chip">
                <Layers size={13} />
                <span>Type: <strong>{document.document_type}</strong></span>
              </span>
              <span className="ai-meta-chip">
                <HardDrive size={13} />
                <span>{formattedSize} KB</span>
              </span>
              <span className="ai-meta-chip">
                <FileCode size={13} />
                <span>{document.pages || 1} {document.pages === 1 ? 'Page' : 'Pages'}</span>
              </span>
              <span className="ai-meta-chip">
                <span>Source: {document.text_source || 'PDF Layer'}</span>
              </span>
            </div>
          </div>
        </div>

        <div className="ai-analysis-actions">
          <button
            type="button"
            className="btn btn-secondary ai-action-btn"
            onClick={onUploadNew}
            title="Upload another document for analysis"
          >
            <UploadCloud size={15} />
            <span>Upload New</span>
          </button>
          <button
            type="button"
            className="btn btn-secondary ai-action-btn-icon"
            onClick={onReset}
            title="Reset AI session"
            aria-label="Reset AI session"
          >
            <RotateCcw size={15} />
          </button>
        </div>
      </div>

      {/* Review Required Panel (Phase 9.9) */}
      {isReviewRequired && (
        <div
          className="review-required-panel"
          data-testid="review-required-panel"
          style={{
            marginTop: '0.85rem',
            padding: '0.85rem 1.1rem',
            borderRadius: '8px',
            backgroundColor: 'rgba(249, 115, 22, 0.08)',
            border: '1px solid rgba(249, 115, 22, 0.25)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem', color: '#fb923c', fontWeight: 600, fontSize: '0.88rem' }}>
            <ShieldAlert size={16} />
            <span>Visible inconsistencies detected ({riskScore}% Risk Score)</span>
          </div>
          {document.human_review_reason && (
            <p style={{ margin: '0 0 0.4rem', fontSize: '0.82rem', color: 'var(--text-main)' }}>
              {document.human_review_reason}
            </p>
          )}
          {signals.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              {signals.map((sig, idx) => (
                <li key={idx} style={{ marginBottom: '0.2rem' }}>
                  {typeof sig === 'string' ? sig : (sig.description || sig.signal || JSON.stringify(sig))}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};
