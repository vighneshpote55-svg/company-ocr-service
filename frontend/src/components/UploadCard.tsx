import React, { useState, useRef } from 'react';
import { UploadCloud, Sparkles, ChevronDown, ChevronUp, AlertCircle, ArrowRight, ShieldCheck } from 'lucide-react';
import type { SupportedType, DocumentItem, UploadProgress } from '../types';
import { api } from '../services/api';
import { ProcessingTimeline } from './ProcessingTimeline';

interface UploadCardProps {
  supportedTypes: SupportedType[];
  onUploadSuccess: (doc: DocumentItem) => void;
  onError: (msg: string) => void;
  onSwitchToAiMode?: () => void;
}

export const UploadCard: React.FC<UploadCardProps> = ({
  supportedTypes,
  onUploadSuccess,
  onError,
  onSwitchToAiMode,
}) => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('auto');
  const [expectedData, setExpectedData] = useState<string>('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [unsupportedError, setUnsupportedError] = useState<string | null>(null);
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
      onError(`Invalid file type. Please upload a PDF, PNG, JPG, or WEBP.`);
      return;
    }

    if (file.size > 25 * 1024 * 1024) {
      onError(`File is too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Maximum size is 25MB.`);
      return;
    }

    setUnsupportedError(null);
    setIsProcessing(true);
    setProgress({ step: 'uploading', percent: 20, message: 'Uploading document payload...' });

    try {
      setTimeout(() => {
        setProgress({ step: 'analyzing', percent: 45, message: 'Checking embedded text layer (pdftotext)...' });
      }, 300);

      setTimeout(() => {
        setProgress({ step: 'extracting', percent: 70, message: 'Classifying document against supported types...' });
      }, 700);

      setTimeout(() => {
        setProgress({ step: 'verifying', percent: 90, message: 'Validating checksums & masking PII...' });
      }, 1000);

      const doc = await api.uploadOfflineDocument(file, selectedType, expectedData || undefined);

      if (doc.supported === false) {
        setIsProcessing(false);
        const rejectionMsg =
          doc.message ||
          'This document type is not supported in Offline Mode. Please use AI Mode for unknown documents.';
        setUnsupportedError(rejectionMsg);
        onError(rejectionMsg);
        return;
      }

      setProgress({ step: 'done', percent: 100, message: 'Document analysis complete!' });
      setTimeout(() => {
        setIsProcessing(false);
        onUploadSuccess(doc as unknown as DocumentItem);
      }, 400);
    } catch (err: any) {
      setIsProcessing(false);
      setProgress({ step: 'error', percent: 0, message: err.message || 'Processing failed' });
      onError(err.message || 'Upload and processing failed');
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const nonAutoSupportedTypes = supportedTypes.filter((t) => t.id !== 'auto');

  return (
    <div className="upload-card">
      <div className="upload-header">
        <div>
          <div className="offline-mode-badge-pill">
            <ShieldCheck size={16} />
            <span>Offline Mode • Local PaddleOCR Engine</span>
          </div>
          <h2 className="upload-title" style={{ marginTop: '0.6rem' }}>
            Ingest & Verify Predefined Document
          </h2>
          <p className="upload-subtitle">
            Strictly processes supported document types using the local OCR pipeline without external AI APIs. If your document is not on the supported list, use <strong>AI Mode</strong>.
          </p>
        </div>
      </div>

      {/* Unsupported Document Rejection Notice */}
      {unsupportedError && (
        <div className="offline-unsupported-banner">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1 }}>
            <AlertCircle size={22} color="var(--accent-amber)" style={{ flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-main)' }}>
                Document Not Supported in Offline Mode
              </div>
              <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                {unsupportedError}
              </div>
            </div>
          </div>
          {onSwitchToAiMode && (
            <button
              className="btn btn-primary"
              onClick={onSwitchToAiMode}
              style={{ padding: '0.45rem 0.9rem', fontSize: '0.82rem', whiteSpace: 'nowrap' }}
            >
              <Sparkles size={14} />
              <span>Switch to AI Mode</span>
              <ArrowRight size={14} />
            </button>
          )}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp"
        style={{ display: 'none' }}
        onChange={handleFileInputChange}
        disabled={isProcessing}
      />

      {isProcessing ? (
        <ProcessingTimeline progress={progress} />
      ) : (
        <>
          <div
            className={`dropzone ${dragActive ? 'drag-active' : ''}`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="dropzone-icon">
              <UploadCloud size={28} />
            </div>
            <div className="dropzone-text">Click to browse or drag & drop files here</div>
            <div className="dropzone-subtext">PDF documents (digital or scanned), PNG, JPG up to 25MB</div>
            <div className="file-types-badge-row">
              <span className="file-badge">PDF (Auto text layer detection)</span>
              <span className="file-badge">PNG</span>
              <span className="file-badge">JPG / JPEG</span>
              <span className="file-badge">WEBP</span>
            </div>
          </div>

          <div className="upload-controls-grid">
            <div className="form-group">
              <label className="form-label">Predefined Document Type</label>
              <select
                className="form-select"
                value={selectedType}
                onChange={(e) => {
                  setSelectedType(e.target.value);
                  setUnsupportedError(null);
                }}
                disabled={isProcessing}
              >
                <option value="auto">⚡ Auto-Detect Type (Local Signature Matcher)</option>
                {nonAutoSupportedTypes.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.category})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ alignSelf: 'flex-start', marginTop: 'auto' }}
                onClick={() => setShowAdvanced(!showAdvanced)}
              >
                <Sparkles size={15} />
                <span>{showAdvanced ? 'Hide Advanced Options' : 'Cross-Check Verification (Optional)'}</span>
                {showAdvanced ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              </button>
            </div>
          </div>

          {/* Supported Document Catalog Preview */}
          <div className="supported-catalog-box">
            <div className="supported-catalog-header">
              <span>Supported Document Types ({nonAutoSupportedTypes.length}):</span>
            </div>
            <div className="supported-tags-cloud">
              {nonAutoSupportedTypes.map((t) => (
                <span
                  key={t.id}
                  className={`supported-tag ${selectedType === t.id ? 'active' : ''}`}
                  onClick={() => setSelectedType(t.id)}
                  title={`Select ${t.name}`}
                >
                  {t.name}
                </span>
              ))}
            </div>
          </div>

          {showAdvanced && (
            <div style={{ marginTop: '1.25rem', paddingTop: '1.25rem', borderTop: '1px solid var(--border-subtle)' }}>
              <div className="form-group">
                <label className="form-label">Expected Data JSON (For Automated Cross-Check)</label>
                <textarea
                  className="form-textarea"
                  rows={3}
                  placeholder='{"name": "VIKRAM SHARMA", "pan": "ABCDE1234F", "dob": "15/08/1985"}'
                  value={expectedData}
                  onChange={(e) => setExpectedData(e.target.value)}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--text-subtle)' }}>
                  Provide expected customer records to test fuzzy cross-checking and discrepancy calculation.
                </span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};
