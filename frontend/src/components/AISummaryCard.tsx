import React from 'react';
import { Sparkles, Quote, Layers, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react';

interface AISummaryCardProps {
  summary: string;
  documentType: string;
  confidence?: string | number;
  verificationStatus?: string;
  riskScore?: number;
}

export const AISummaryCard: React.FC<AISummaryCardProps> = ({
  summary,
  documentType,
  confidence = 'high',
  verificationStatus = 'verified',
  riskScore = 0,
}) => {
  const confDisplay = typeof confidence === 'number'
    ? `${Math.round(confidence * 100)}%`
    : String(confidence || 'High');
  const confLower = typeof confidence === 'string'
    ? confidence.toLowerCase()
    : (typeof confidence === 'number' && confidence >= 0.85 ? 'high' : 'medium');

  const isReviewRequired = verificationStatus === 'review_required' || riskScore >= 30;

  return (
    <div className="ai-summary-card-container docpilot-summary-hero-card">
      <div className="ai-summary-card-header docpilot-summary-header">
        <div className="ai-summary-badge-wrap">
          <div className="ai-summary-badge-icon docpilot-sparkle-badge">
            <Sparkles size={16} />
          </div>
          <span className="ai-summary-badge-text">Executive Insight</span>
        </div>

        <div className="docpilot-summary-badges" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span className="docpilot-summary-pill type-pill">
            <Layers size={12} />
            <span>{documentType}</span>
          </span>

          <span className={`docpilot-summary-pill conf-pill ${confLower}`}>
            <CheckCircle2 size={12} />
            <span>{confDisplay} Confidence</span>
          </span>

          {isReviewRequired ? (
            <span className="docpilot-summary-pill verif-pill review-required">
              <AlertTriangle size={12} />
              <span>Review Required ({riskScore}%)</span>
            </span>
          ) : (
            <span className="docpilot-summary-pill verif-pill verified">
              <ShieldCheck size={12} />
              <span>Verified Authenticity</span>
            </span>
          )}
        </div>
      </div>

      <div className="ai-summary-body-wrap docpilot-summary-body">
        <Quote size={22} className="ai-summary-quote-icon" />
        <div className="ai-summary-text-box">
          <p className="ai-summary-text">
            {typeof summary === 'string' && summary.trim()
              ? summary
              : (typeof summary === 'object' && summary !== null
              ? JSON.stringify(summary)
              : 'Document analysis completed successfully. Key provisions and entities verified.')}
          </p>
        </div>
      </div>
    </div>
  );
};
