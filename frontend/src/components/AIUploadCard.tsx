import React, { useRef, useState } from 'react';
import {
  Sparkles,
  UploadCloud,
  FileUp,
  Shield,
  Cpu,
} from 'lucide-react';
import type { UploadProgress } from '../types';
import { ProcessingTimeline } from './ProcessingTimeline';

interface AIUploadCardProps {
  onUpload: (file: File) => void;
  isProcessing: boolean;
  progress: UploadProgress;
}

const SUPPORTED_FORMATS = ['PDF', 'PNG', 'JPG', 'JPEG', 'WEBP'];

export const AIUploadCard: React.FC<AIUploadCardProps> = ({
  onUpload,
  isProcessing,
  progress,
}) => {
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0] && !isProcessing) {
      onUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0] && !isProcessing) {
      onUpload(e.target.files[0]);
    }
  };

  return (
    <div className="ai-upload-workspace-card">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp"
        style={{ display: 'none' }}
        onChange={handleFileInputChange}
        disabled={isProcessing}
      />

      {isProcessing ? (
        <div className="ai-upload-processing-container">
          <div className="ai-processing-header">
            <div className="ai-processing-spinner-wrap">
              <Sparkles size={24} className="ai-pulse-icon" />
            </div>
            <div>
              <h3 className="ai-processing-title">Analyzing Customer Document</h3>
              <p className="ai-processing-subtitle">
                Extracting textual structure, recognizing document category, and generating AI insights...
              </p>
            </div>
          </div>
          <ProcessingTimeline progress={progress} />
        </div>
      ) : (
        <div
          className={`ai-enterprise-dropzone ${dragActive ? 'drag-active' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
        >
          <div className="ai-illustration-container">
            <div className="ai-illustration-ring" />
            <div className="ai-illustration-center">
              <FileUp size={40} className="ai-icon-file" />
              <UploadCloud size={24} className="ai-icon-cloud" />
            </div>
          </div>

          <div className="ai-dropzone-content">
            <h3 className="ai-dropzone-headline">
              Drag & Drop Any Document or <span className="ai-browse-highlight">Browse Files</span>
            </h3>
            <p className="ai-dropzone-sub">
              Universal document analysis: Contracts, NDAs, Invoices, Letters, Reports, Certificates, and more
            </p>

            <div className="ai-format-pills-row">
              {SUPPORTED_FORMATS.map((fmt) => (
                <span key={fmt} className="ai-format-pill">
                  {fmt}
                </span>
              ))}
            </div>

            <div className="ai-capabilities-grid">
              <div className="ai-capability-item">
                <Cpu size={15} className="ai-cap-icon" />
                <span>Neural Type Classification</span>
              </div>
              <div className="ai-capability-item">
                <Sparkles size={15} className="ai-cap-icon" />
                <span>Key Information Extraction</span>
              </div>
              <div className="ai-capability-item">
                <Shield size={15} className="ai-cap-icon" />
                <span>Isolated Client Context</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
