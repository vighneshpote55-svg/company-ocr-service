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
  QrCode,
  Binary,
  LayoutGrid,
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

  // Gauge calculations (Circumference for r=38 is ~238.76)
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (Math.min(100, Math.max(0, riskScore)) / 100) * circumference;
  const gaugeColor = riskScore >= 60 ? '#EF4444' : riskScore >= 30 ? '#F59E0B' : '#22C55E';

  // Subsystem integrity checks
  const hasQrMismatch = signals.some((s) => String(s).toLowerCase().includes('qr'));
  const hasChecksumMismatch = signals.some((s) => String(s).toLowerCase().includes('checksum') || String(s).toLowerCase().includes('math') || String(s).toLowerCase().includes('deduction'));
  const hasLayoutAnomaly = signals.some((s) => String(s).toLowerCase().includes('duplicate') || String(s).toLowerCase().includes('overlap') || String(s).toLowerCase().includes('alignment'));

  return (
    <div className="ai-analysis-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Top Document Summary Strip */}
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

      {/* Phase 11.7: 4 Compact Metadata Dashboard Cards */}
      <div className="docpilot-metadata-4grid" role="region" aria-label="Document Metadata Summary">
        {/* Card 1: Confidence */}
        <div className="docpilot-meta-card">
          <div className="docpilot-meta-card-header">
            <span className="docpilot-meta-card-label">Confidence</span>
            <div className={`docpilot-meta-icon-badge ${confidenceLower}`}>
              <CheckCircle2 size={16} />
            </div>
          </div>
          <div className="docpilot-meta-card-value">
            {typeof rawConf === 'number' ? `${Math.round(rawConf * 100)}%` : rawConf}
          </div>
          <span className="docpilot-meta-card-sub">{confidenceLabel}</span>
        </div>

        {/* Card 2: Pages & Size */}
        <div className="docpilot-meta-card">
          <div className="docpilot-meta-card-header">
            <span className="docpilot-meta-card-label">Pages</span>
            <div className="docpilot-meta-icon-badge blue">
              <FileCode size={16} />
            </div>
          </div>
          <div className="docpilot-meta-card-value">
            {document.pages || 1} {document.pages === 1 ? 'Page' : 'Pages'}
          </div>
          <span className="docpilot-meta-card-sub">{formattedSize} KB • {document.text_source || 'PDF Layer'}</span>
        </div>

        {/* Card 3: Document Type */}
        <div className="docpilot-meta-card">
          <div className="docpilot-meta-card-header">
            <span className="docpilot-meta-card-label">Document Type</span>
            <div className="docpilot-meta-icon-badge purple">
              <Layers size={16} />
            </div>
          </div>
          <div className="docpilot-meta-card-value doc-type-val" title={document.document_type}>
            {document.document_type || 'Unknown'}
          </div>
          <span className="docpilot-meta-card-sub">AI Classified</span>
        </div>

        {/* Card 4: Verification */}
        <div className="docpilot-meta-card">
          <div className="docpilot-meta-card-header">
            <span className="docpilot-meta-card-label">Verification</span>
            <div className={`docpilot-meta-icon-badge ${isReviewRequired ? 'warning' : 'success'}`}>
              {isReviewRequired ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
            </div>
          </div>
          <div className={`docpilot-meta-card-value ${isReviewRequired ? 'text-warning' : 'text-success'}`}>
            {isReviewRequired ? 'Review Required' : 'Verified'}
          </div>
          <span className="docpilot-meta-card-sub">
            {isReviewRequired ? `Risk Score: ${riskScore}%` : 'Risk Score: 0% • Authentic'}
          </span>
        </div>
      </div>

      {/* DocPilot Circular Risk Gauge & Subsystem Integrity Strip */}
      <div className="docpilot-circular-gauge-card" style={{ marginTop: '0.25rem' }}>
        <div className="docpilot-gauge-wrap">
          <div style={{ position: 'relative', width: '100px', height: '100px' }}>
            <svg className="circular-gauge-svg" viewBox="0 0 100 100">
              <circle
                className="circular-gauge-bg"
                cx="50"
                cy="50"
                r={radius}
              />
              <circle
                className="circular-gauge-progress"
                cx="50"
                cy="50"
                r={radius}
                stroke={gaugeColor}
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
              />
            </svg>
            <div className="gauge-center-text">
              <div className="gauge-percent" style={{ color: gaugeColor }}>
                {riskScore}%
              </div>
              <div className="gauge-label">
                Risk
              </div>
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <span style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-main)' }}>
                Document Integrity Assessment
              </span>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: '9999px',
                  backgroundColor: isReviewRequired ? 'rgba(245, 158, 11, 0.15)' : 'rgba(34, 197, 94, 0.15)',
                  color: isReviewRequired ? 'var(--warning)' : 'var(--success)',
                  border: `1px solid ${isReviewRequired ? 'rgba(245, 158, 11, 0.3)' : 'rgba(34, 197, 94, 0.3)'}`,
                }}
              >
                {isReviewRequired ? 'Review Required' : isUnsupported ? 'Unsupported' : 'Verified'}
              </span>
            </div>
            <p style={{ margin: 0, fontSize: '12.5px', color: 'var(--text-muted)' }}>
              Objective checks across layout, OCR, security features, and AI reasoning
            </p>
          </div>
        </div>

        {/* Subsystem Integrity Status Chips */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '8px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              fontSize: '12px',
            }}
          >
            <QrCode size={14} color={hasQrMismatch ? 'var(--warning)' : 'var(--success)'} />
            <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>
              QR: {hasQrMismatch ? 'Mismatch' : 'Valid'}
            </span>
          </div>

          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '8px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              fontSize: '12px',
            }}
          >
            <Binary size={14} color={hasChecksumMismatch ? 'var(--warning)' : 'var(--success)'} />
            <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>
              Checksum: {hasChecksumMismatch ? 'Inconsistent' : 'Valid'}
            </span>
          </div>

          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '8px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              fontSize: '12px',
            }}
          >
            <LayoutGrid size={14} color={hasLayoutAnomaly ? 'var(--warning)' : 'var(--success)'} />
            <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>
              Layout: {hasLayoutAnomaly ? 'Anomaly' : 'Consistent'}
            </span>
          </div>
        </div>
      </div>

      {/* Review Required Alert / Inconsistencies Panel */}
      {isReviewRequired && (
        <div
          className="review-required-panel"
          data-testid="review-required-panel"
          style={{
            padding: '14px 18px',
            borderRadius: '12px',
            backgroundColor: 'rgba(249, 115, 22, 0.08)',
            border: '1px solid rgba(249, 115, 22, 0.25)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.4rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#fb923c', fontWeight: 600, fontSize: '0.92rem' }}>
                <ShieldAlert size={16} />
                <span>Document Integrity Assessment</span>
              </div>
              <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                Objective checks across layout, OCR, security features, and AI reasoning
              </div>
            </div>
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#fb923c', backgroundColor: 'rgba(249, 115, 22, 0.15)', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
              Review Required • Risk Score: {riskScore}% ({riskScore}/100)
            </span>
          </div>

          <div style={{ marginTop: '0.45rem', marginBottom: '0.35rem', fontSize: '0.84rem', fontWeight: 600, color: '#fb923c' }}>
            Visible inconsistencies detected
          </div>

          {document.human_review_reason && (
            <p style={{ margin: '0 0 0.4rem', fontSize: '0.82rem', color: 'var(--text-main)' }}>
              {document.human_review_reason}
            </p>
          )}

          {signals.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              {signals.map((sig, idx) => (
                <li key={idx} style={{ marginBottom: '0.25rem' }}>
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
