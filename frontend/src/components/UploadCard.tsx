import React, { useState, useRef } from 'react';
import {
  UploadCloud,
  Sparkles,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  FileCheck2,
  CheckCircle2,
  FileText,
  Loader2,
  Eye,
  FileUp,
} from 'lucide-react';
import type { SupportedType, DocumentItem, UploadProgress } from '../types';
import { api } from '../services/api';

interface UploadCardProps {
  supportedTypes: SupportedType[];
  onUploadSuccess: (doc: DocumentItem) => void;
  onError: (msg: string) => void;
  onSwitchToAiMode?: () => void;
  onRefresh?: () => void;
}

export const UploadCard: React.FC<UploadCardProps> = ({
  supportedTypes,
  onUploadSuccess,
  onError,
  onSwitchToAiMode,
  onRefresh,
}) => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('auto');
  const [expectedData, setExpectedData] = useState<string>('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [unsupportedError, setUnsupportedError] = useState<string | null>(null);
  const [activeFile, setActiveFile] = useState<{ name: string; size: number } | null>(null);
  const [completedDoc, setCompletedDoc] = useState<DocumentItem | null>(null);

  const [progress, setProgress] = useState<UploadProgress>({
    step: 'idle',
    percent: 0,
    message: '',
  });

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
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleFile = async (file: File) => {
    const validExtensions = ['.pdf', '.png', '.jpg', '.jpeg', '.webp'];
    const hasValidExt = validExtensions.some((ext) =>
      file.name.toLowerCase().endsWith(ext)
    );

    if (!hasValidExt) {
      onError(`Invalid file type. Supported formats: PDF, PNG, JPG, WEBP.`);
      return;
    }

    if (file.size > 25 * 1024 * 1024) {
      onError(`File size (${(file.size / (1024 * 1024)).toFixed(1)}MB) exceeds 25MB limit.`);
      return;
    }

    setUnsupportedError(null);
    setCompletedDoc(null);
    setActiveFile({ name: file.name, size: file.size });
    setIsProcessing(true);
    setProgress({ step: 'uploading', percent: 25, message: 'Uploading document...' });

    try {
      setTimeout(() => {
        setProgress({ step: 'analyzing', percent: 50, message: 'Analyzing document...' });
      }, 300);

      setTimeout(() => {
        setProgress({ step: 'extracting', percent: 75, message: 'Extracting content...' });
      }, 700);

      setTimeout(() => {
        setProgress({ step: 'verifying', percent: 90, message: 'Classifying & verifying document...' });
      }, 1050);

      const doc = await api.uploadOfflineDocument(file, selectedType, expectedData || undefined);

      if (doc.supported === false && !doc.id) {
        setIsProcessing(false);
        setActiveFile(null);
        setCompletedDoc(null);
        const rejectionMsg =
          doc.message ||
          'This document is not one of the 22 supported Offline document types. Switch to AI Mode.';
        setUnsupportedError(rejectionMsg);
        onError(rejectionMsg);
        return;
      }

      setUnsupportedError(null);
      setProgress({ step: 'done', percent: 100, message: 'Document successfully processed!' });
      const completedDocItem = doc as unknown as DocumentItem;
      setCompletedDoc(completedDocItem);
      setIsProcessing(false);
      if (onRefresh) onRefresh();
    } catch (err: any) {
      setIsProcessing(false);
      setActiveFile(null);
      setCompletedDoc(null);
      setUnsupportedError(null);
      setProgress({ step: 'error', percent: 0, message: err.message || 'Processing failed' });
      onError(err.message || 'Upload and processing failed');
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleResetForNewUpload = () => {
    setCompletedDoc(null);
    setActiveFile(null);
    setUnsupportedError(null);
    setProgress({ step: 'idle', percent: 0, message: '' });
  };

  const nonAutoSupportedTypes = supportedTypes.filter((t) => t.id !== 'auto');

  const isUnknownDoc =
    completedDoc &&
    (completedDoc.doc_type === 'unknown' || completedDoc.document_type === 'Unknown Document');

  return (
    <div className="upload-workspace-card">
      {/* Workspace Header */}
      <div className="upload-workspace-header">
        <div className="upload-mode-badge offline-badge">
          <ShieldCheck size={16} />
          <span>Offline Mode • Zero Cloud Callouts</span>
        </div>
        <h2 className="upload-main-title">Offline Document Ingestion</h2>
        <p className="upload-main-subtitle">
          Local, air-gapped OCR processing for 22 predefined document formats with automated verification and PII protection.
        </p>
      </div>

      {/* Visually Attractive Unsupported Document Banner (shown strictly when classification completes and document is unsupported) */}
      {!isProcessing && !completedDoc && unsupportedError && (
        <div className="unsupported-document-banner-attractive" role="alert">
          <div className="unsupported-banner-glow" aria-hidden="true" />
          <div className="unsupported-banner-content">
            <div className="unsupported-icon-circle">
              <AlertTriangle size={24} />
            </div>
            <div>
              <h4 className="unsupported-title">Unsupported in Offline Mode</h4>
              <p className="unsupported-desc">
                {unsupportedError}
              </p>
            </div>
          </div>
          {onSwitchToAiMode && (
            <button
              className="btn btn-primary switch-ai-glow-btn"
              onClick={onSwitchToAiMode}
            >
              <Sparkles size={16} />
              <span>Switch to AI Mode</span>
              <ArrowRight size={15} />
            </button>
          )}
        </div>
      )}

      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp"
        style={{ display: 'none' }}
        onChange={handleFileInputChange}
        disabled={isProcessing}
      />

      {/* Completed State: Success Animation + Actions */}
      {completedDoc ? (
        <div className="upload-completed-card">
          <div className="upload-success-icon-wrap">
            <CheckCircle2 size={48} className="success-pulse-icon" />
          </div>
          <h3 className="upload-completed-title">
            {isUnknownDoc ? 'Offline OCR Completed' : 'Ingestion Successful'}
          </h3>
          <p className="upload-completed-subtitle">
            {isUnknownDoc ? (
              <>
                <strong>{completedDoc.filename}</strong> has been scanned using Offline OCR.{' '}
                <span className="text-success font-bold">Raw text is ready.</span> Switch to AI Mode for structured analysis.
              </>
            ) : (
              <>
                <strong>{completedDoc.filename}</strong> has been extracted and verified with{' '}
                <span className="text-success font-bold">{Math.round(completedDoc.confidence * 100)}%</span> confidence.
              </>
            )}
          </p>

          <div className="upload-completed-actions" style={{ flexWrap: 'wrap', justifyContent: 'center' }}>
            <button
              className="btn btn-primary btn-lg"
              onClick={() => onUploadSuccess(completedDoc)}
            >
              <Eye size={17} />
              <span>{isUnknownDoc ? 'View Document & Text' : 'View Extracted Fields'}</span>
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleResetForNewUpload}
            >
              <FileCheck2 size={16} />
              <span>Upload Another Document</span>
            </button>
            {isUnknownDoc && onSwitchToAiMode && (
              <button
                className="btn btn-primary switch-ai-glow-btn"
                onClick={onSwitchToAiMode}
              >
                <Sparkles size={16} />
                <span>Switch to AI Mode</span>
                <ArrowRight size={15} />
              </button>
            )}
          </div>
        </div>
      ) : isProcessing ? (
        /* Processing State: Filename, size, progress bar, spinner */
        <div className="upload-active-progress-card">
          <div className="upload-active-file-header">
            <div className="upload-file-icon">
              <FileText size={26} color="var(--primary)" />
            </div>
            <div className="upload-file-details">
              <div className="upload-file-name">{activeFile?.name || 'Document'}</div>
              <div className="upload-file-size">
                {activeFile ? `${(activeFile.size / 1024).toFixed(1)} KB` : ''} • Local OCR Engine Pipeline
              </div>
            </div>
            <div className="upload-spinner-wrap">
              <Loader2 size={24} className="spin-anim" color="var(--primary)" />
            </div>
          </div>

          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${progress.percent}%` }}
            />
          </div>

          <div className="progress-status-row">
            <span className="progress-status-msg">{progress.message}</span>
            <span className="progress-status-pct">{progress.percent}%</span>
          </div>
        </div>
      ) : (
        /* Before Upload: Drag & Drop Documents, Browse Files, PDF • PNG • JPG • WEBP */
        <>
          <div
            className={`enterprise-dropzone ${dragActive ? 'drag-active' : ''}`}
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
            <div className="dropzone-illustration-wrap">
              <div className="illustration-glow-ring" />
              <div className="illustration-icon-box">
                <FileUp size={36} className="illustration-file-icon" />
                <UploadCloud size={24} className="illustration-cloud-icon" />
              </div>
            </div>

            <div className="dropzone-headline">
              <span className="dropzone-lead">Drag & Drop Documents</span> or{' '}
              <span className="dropzone-browse-cta">Browse Files</span>
            </div>

            <p className="dropzone-formats-badge">
              PDF • PNG • JPG • WEBP
            </p>

            <span className="dropzone-limit-hint">
              Maximum file size 25MB • Automated digital text detection & OCR fallback
            </span>
          </div>

          {/* Model Selection Bar */}
          <div className="upload-options-bar">
            <div className="form-group-field">
              <label className="field-select-label">Target Document Profile</label>
              <select
                className="modern-select"
                value={selectedType}
                onChange={(e) => {
                  setSelectedType(e.target.value);
                  setUnsupportedError(null);
                }}
                disabled={isProcessing}
              >
                <option value="auto">⚡ Auto-Detect Type (Local Pattern Matcher)</option>
                {nonAutoSupportedTypes.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.category})
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              className="btn btn-secondary advanced-toggle-btn"
              onClick={() => setShowAdvanced(!showAdvanced)}
            >
              <Sparkles size={15} />
              <span>{showAdvanced ? 'Hide Cross-Check' : 'Cross-Check Verification'}</span>
              {showAdvanced ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </button>
          </div>

          {showAdvanced && (
            <div className="advanced-options-panel">
              <label className="field-select-label">Expected Customer Data (JSON Cross-Check)</label>
              <textarea
                className="modern-textarea"
                rows={3}
                placeholder='{"name": "VIKRAM SHARMA", "pan": "ABCDE1234F", "dob": "15/08/1985"}'
                value={expectedData}
                onChange={(e) => setExpectedData(e.target.value)}
              />
              <span className="field-helper-note">
                Provide expected record attributes to calculate fuzzy verification scores and highlight discrepancies.
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
};
