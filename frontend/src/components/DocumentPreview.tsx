import React, { useState, useEffect } from 'react';
import {
  FileText,
  Download,
  ExternalLink,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Image as ImageIcon,
  AlertCircle,
  Loader2,
  FileCheck,
} from 'lucide-react';
import type { DocumentItem } from '../types';
import { api } from '../services/api';

interface DocumentPreviewProps {
  document: DocumentItem | null | undefined;
}

export const DocumentPreview: React.FC<DocumentPreviewProps> = ({ document }) => {
  const [imageZoom, setImageZoom] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  // Defensive Document ID extraction: NEVER generate /api/documents/undefined/file
  const rawId = document?.id || (document as any)?.document_id || '';
  const docId = (rawId && rawId !== 'undefined' && rawId !== 'null') ? String(rawId) : '';

  const filename = document?.filename || (document as any)?.original_filename || 'document';
  const ext = (filename.includes('.') ? filename.slice(filename.lastIndexOf('.')).toLowerCase() : (document?.file_type || '')).toLowerCase();
  const isPdf = ext === '.pdf';
  const isImage = ['.png', '.jpg', '.jpeg', '.webp'].includes(ext);

  // Authenticated endpoints through ApiService
  const fileUrl = docId ? api.getFileUrl(docId) : '';
  const downloadUrl = docId ? api.getFileUrl(docId, true) : '#';
  const pageCount = (typeof document?.pages === 'number' && document.pages > 0) ? document.pages : 1;

  // Reset loading and error state when document or retryKey changes
  useEffect(() => {
    if (fileUrl) {
      setIsLoading(true);
      setHasError(false);
      setImageZoom(1);
    } else {
      setIsLoading(false);
      setHasError(false);
    }
  }, [fileUrl, retryKey]);

  const handleRetry = () => {
    setHasError(false);
    setIsLoading(true);
    setRetryKey((k) => k + 1);
  };

  const formatBytes = (bytes?: number) => {
    if (!bytes || bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  if (!document || !docId) {
    return (
      <div className="preview-panel">
        <div className="preview-header">
          <div className="preview-title">
            <FileText size={16} color="var(--text-muted)" />
            <span>Document Preview</span>
          </div>
        </div>
        <div className="preview-body empty-preview">
          <div className="preview-placeholder-box">
            <FileCheck size={36} color="var(--text-subtle)" />
            <p className="preview-placeholder-text">No document loaded for preview</p>
            <span className="preview-placeholder-sub">Upload or select a document to inspect it.</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="preview-panel" data-testid="document-preview-panel">
      {/* Panel Top Header */}
      <div className="preview-header">
        <div className="preview-title">
          {isPdf ? (
            <FileText size={16} color="#818cf8" />
          ) : (
            <ImageIcon size={16} color="#38bdf8" />
          )}
          <span
            style={{
              maxWidth: '200px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontWeight: 600,
            }}
            title={filename}
          >
            {filename}
          </span>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-subtle)' }}>
            ({formatBytes(document.file_size)})
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
          {/* Zoom controls for images */}
          {isImage && (
            <>
              <button
                type="button"
                className="copy-btn"
                onClick={() => setImageZoom((z) => Math.max(0.5, z - 0.2))}
                title="Zoom out"
                aria-label="Zoom out"
              >
                <ZoomOut size={15} />
              </button>
              <button
                type="button"
                className="copy-btn"
                onClick={() => setImageZoom((z) => Math.min(3.0, z + 0.2))}
                title="Zoom in"
                aria-label="Zoom in"
              >
                <ZoomIn size={15} />
              </button>
              <button
                type="button"
                className="copy-btn"
                onClick={() => setImageZoom(1)}
                title="Reset zoom"
                aria-label="Reset zoom"
              >
                <RotateCcw size={13} />
              </button>
            </>
          )}

          {/* Open original file in new browser tab */}
          <a
            href={fileUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="copy-btn"
            title="Open original document in new tab"
            aria-label="Open original document in new tab"
          >
            <ExternalLink size={15} />
          </a>

          {/* Download decrypted document */}
          <a
            href={downloadUrl}
            download={filename}
            className="copy-btn"
            title="Download document file"
            aria-label="Download document file"
          >
            <Download size={15} />
          </a>
        </div>
      </div>

      {/* Panel Body: Renders native PDF or Image */}
      <div className="preview-body" style={{ position: 'relative' }}>
        {/* Loading Spinner Skeleton */}
        {isLoading && !hasError && (
          <div className="preview-loading-overlay">
            <Loader2 size={32} className="spin-anim" color="var(--primary)" />
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '0.6rem' }}>
              Loading decrypted preview...
            </span>
          </div>
        )}

        {/* Error State Fallback */}
        {hasError ? (
          <div className="preview-error-box" data-testid="preview-error-state">
            <AlertCircle size={36} color="#f87171" />
            <h4 style={{ margin: '0.6rem 0 0.2rem', color: 'var(--text-main)', fontSize: '0.95rem' }}>
              Preview unavailable
            </h4>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.8rem', maxWidth: '280px', textAlign: 'center' }}>
              The browser could not display "{filename}" inline. You can retry or download the decrypted file.
            </p>
            <div style={{ display: 'flex', gap: '0.6rem', marginTop: '1rem' }}>
              <button type="button" className="btn btn-secondary" onClick={handleRetry} style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}>
                <RotateCcw size={14} />
                <span>Retry</span>
              </button>
              <a href={downloadUrl} download={filename} className="btn btn-primary" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}>
                <Download size={14} />
                <span>Download</span>
              </a>
            </div>
          </div>
        ) : isPdf ? (
          /* Native decrypted PDF rendering through <object> with iframe fallback */
          <object
            key={`pdf-${retryKey}-${docId}`}
            data={`${fileUrl}#toolbar=0&navpanes=0`}
            type="application/pdf"
            className="preview-iframe"
            onLoad={() => setIsLoading(false)}
            onError={() => {
              setIsLoading(false);
              setHasError(true);
            }}
          >
            <iframe
              src={`${fileUrl}#toolbar=0&navpanes=0`}
              title={filename}
              className="preview-iframe"
              onLoad={() => setIsLoading(false)}
              onError={() => {
                setIsLoading(false);
                setHasError(true);
              }}
            />
          </object>
        ) : (
          /* Decrypted Image rendering */
          <div style={{ overflow: 'auto', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <img
              key={`img-${retryKey}-${docId}`}
              src={fileUrl}
              alt={filename}
              className="preview-img"
              style={{ transform: `scale(${imageZoom})`, transformOrigin: 'center center' }}
              onLoad={() => setIsLoading(false)}
              onError={() => {
                setIsLoading(false);
                setHasError(true);
              }}
            />
          </div>
        )}
      </div>

      {/* Panel Bottom Footer */}
      <div
        style={{
          padding: '0.65rem 1.2rem',
          borderTop: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-surface)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
        }}
      >
        <span>
          Format: <strong style={{ textTransform: 'uppercase' }}>{(ext || '.bin').replace('.', '').toUpperCase()}</strong>
          {isPdf && ` • ${pageCount} ${pageCount === 1 ? 'Page' : 'Pages'}`}
        </span>
        <span>
          Storage ID: <code style={{ fontFamily: 'var(--font-mono)' }}>{docId.slice(0, 8)}...</code>
        </span>
      </div>
    </div>
  );
};

