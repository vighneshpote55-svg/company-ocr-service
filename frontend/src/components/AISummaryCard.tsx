import React from 'react';
import { Sparkles, Quote } from 'lucide-react';

interface AISummaryCardProps {
  summary: string;
  documentType: string;
}

export const AISummaryCard: React.FC<AISummaryCardProps> = ({
  summary,
  documentType,
}) => {
  return (
    <div className="ai-summary-card-container">
      <div className="ai-summary-card-header">
        <div className="ai-summary-badge-wrap">
          <div className="ai-summary-badge-icon">
            <Sparkles size={16} />
          </div>
          <span className="ai-summary-badge-text">AI Executive Summary</span>
        </div>
        <span className="ai-summary-doc-tag">{documentType}</span>
      </div>

      <div className="ai-summary-body-wrap">
        <Quote size={24} className="ai-summary-quote-icon" />
        <p className="ai-summary-text">
          {typeof summary === 'string' && summary.trim()
            ? summary
            : (typeof summary === 'object' && summary !== null
            ? JSON.stringify(summary)
            : 'Document analysis completed successfully.')}
        </p>
      </div>
    </div>
  );
};
