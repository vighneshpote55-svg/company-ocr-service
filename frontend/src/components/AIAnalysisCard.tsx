import React from 'react';
import {
  FileCheck,
  UploadCloud,
  RotateCcw,
  CheckCircle2,
  Layers,
  HardDrive,
  FileCode,
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
  const confidenceLower = (document.confidence || 'high').toLowerCase();
  const confidenceLabel =
    confidenceLower === 'high'
      ? 'High Confidence'
      : confidenceLower === 'medium'
      ? 'Medium Confidence'
      : 'Low Confidence';

  const formattedSize = ((document.file_size || 0) / 1024).toFixed(1);

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
              <span className="ai-status-pill verified">
                <span>Verified by AI</span>
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
    </div>
  );
};
