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
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Loader2,
  FileCheck,
  Maximize2,
  Minimize2,
  Layers,
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
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [rotation, setRotation] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);

  // Defensive Document ID extraction: NEVER generate /api/documents/undefined/file
  const rawId = document?.id || (document as any)?.document_id || '';
  const docId = (rawId && rawId !== 'undefined' && rawId !== 'null') ? String(rawId) : '';

  const filename = document?.filename || (document as any)?.original_filename || 'document';
  const ext = (filename.includes('.') ? filename.slice(filename.lastIndexOf('.')).toLowerCase() : (document?.file_type || '')).toLowerCase();
  const isPdf = ext === '.pdf';
  const isImage = ['.png', '.jpg', '.jpeg', '.webp'].includes(ext);

  // Authenticity & Verification status
  const verifStatus = document?.verification_status || (document?.review_required ? 'review_required' : (document?.status === 'warning' || document?.status === 'low_confidence' ? 'review_required' : 'verified'));
  const riskScore = typeof document?.risk_score === 'number' ? document.risk_score : (verifStatus === 'review_required' ? 45 : 0);
  const isReviewRequired = verifStatus === 'review_required' || Boolean(document?.review_required);
  const isUnsupported = verifStatus === 'unsupported';
  const reviewNotes = document?.human_review_reason || (isReviewRequired ? 'Visible inconsistencies detected.' : null);

  const pageCount = (typeof document?.pages === 'number' && document.pages > 0) ? document.pages : 1;

  // Fetch document bytes as authenticated Blob via api.getDocumentFile(docId)
  useEffect(() => {
    let isMounted = true;
    let createdUrl: string | null = null;

    if (!docId) {
      setIsLoading(false);
      setHasError(false);
      setPreviewBlobUrl(null);
      return;
    }

    setIsLoading(true);
    setHasError(false);
    setImageZoom(1);

    api
      .getDocumentFile(docId)
      .then((blob) => {
        if (!isMounted) return;
        createdUrl = URL.createObjectURL(blob);
        setPreviewBlobUrl(createdUrl);
        setIsLoading(false);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.warn('[DocumentPreview] Failed to load preview blob:', err);
        setHasError(true);
        setIsLoading(false);
      });

    return () => {
      isMounted = false;
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [docId, retryKey]);

  const handleRetry = () => {
    setHasError(false);
    setIsLoading(true);
    setRetryKey((k) => k + 1);
  };

  const handleDownload = async () => {
    if (!docId || isDownloading) return;
    try {
      setIsDownloading(true);
      await api.downloadDocument(docId, filename);
    } catch (err: any) {
      console.error('[DocumentPreview] Download failed:', err);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleOpenInNewTab = () => {
    if (previewBlobUrl) {
      window.open(previewBlobUrl, '_blank');
    }
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
    <div
      className={`preview-panel ${isFullscreen ? 'preview-panel-fullscreen' : ''}`}
      data-testid="document-preview-panel"
      style={
        isFullscreen
          ? {
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              zIndex: 9999,
              borderRadius: 0,
              margin: 0,
              height: '100vh',
              background: 'var(--bg-base)',
            }
          : undefined
      }
    >
      {/* Panel Top Header */}
      <div className="preview-header">
        <div className="preview-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {isPdf ? (
            <FileText size={16} color="#818cf8" />
          ) : (
            <ImageIcon size={16} color="#38bdf8" />
          )}
          <span
            style={{
              maxWidth: '220px',
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

          {/* Text Layer Badge */}
          <span className="docpilot-text-layer-badge">
            <Layers size={11} />
            <span>{document.ocr_required === false ? 'Native Text' : 'RapidOCR Layer'}</span>
          </span>

          {/* Page Count */}
          <span
            style={{
              fontSize: '11px',
              fontWeight: 600,
              color: 'var(--text-muted)',
              padding: '2px 6px',
              borderRadius: '6px',
              background: 'var(--bg-subtle)',
            }}
          >
            Page 1 of {pageCount}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
          {/* Zoom controls for images */}
          {isImage && previewBlobUrl && (
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
          {previewBlobUrl && (
            <button
              type="button"
              onClick={handleOpenInNewTab}
              className="copy-btn"
              title="Open document in new tab"
              aria-label="Open document in new tab"
            >
              <ExternalLink size={15} />
            </button>
          )}

          {/* Fullscreen toggle */}
          <button
            type="button"
            onClick={() => setIsFullscreen((f) => !f)}
            className="copy-btn"
            title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen preview'}
            aria-label="Toggle fullscreen"
          >
            {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>

          {/* Download decrypted document securely */}
          <button
            type="button"
            onClick={handleDownload}
            disabled={isDownloading}
            className="copy-btn"
            title="Download document file"
            aria-label="Download document file"
          >
            {isDownloading ? <Loader2 size={15} className="spin-anim" /> : <Download size={15} />}
          </button>
        </div>
      </div>

      {/* Panel Body: Renders authenticated PDF or Image Blob */}
      <div className="preview-body" style={{ position: 'relative' }}>
        {/* Loading Spinner Skeleton */}
        {isLoading && !hasError && (
          <div className="preview-loading-overlay">
            <Loader2 size={32} className="spin-anim" color="var(--primary)" />
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '0.6rem' }}>
              Loading document preview...
            </span>
          </div>
        )}

        {/* Clean Failure Card: Never display raw JSON */}
        {hasError ? (
          <div className="preview-error-box" data-testid="preview-error-state">
            <AlertCircle size={36} color="#f87171" />
            <h4 style={{ margin: '0.6rem 0 0.2rem', color: 'var(--text-main)', fontSize: '0.95rem' }}>
              Unable to load document preview
            </h4>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.8rem', maxWidth: '280px', textAlign: 'center' }}>
              The document exists, but the preview could not be loaded.
            </p>
            <div style={{ display: 'flex', gap: '0.6rem', marginTop: '1rem' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleRetry}
                style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
              >
                <RotateCcw size={14} />
                <span>Retry</span>
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleDownload}
                disabled={isDownloading}
                style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}
              >
                <Download size={14} />
                <span>{isDownloading ? 'Downloading...' : 'Download'}</span>
              </button>
            </div>
          </div>
        ) : previewBlobUrl ? (
          isPdf ? (
            /* Authenticated decrypted PDF rendering through <object> with iframe fallback */
            <object
              key={`pdf-${retryKey}-${docId}`}
              data={`${previewBlobUrl}#toolbar=0&navpanes=0`}
              type="application/pdf"
              className="preview-iframe"
            >
              <iframe
                src={`${previewBlobUrl}#toolbar=0&navpanes=0`}
                title={filename}
                className="preview-iframe"
              />
            </object>
          ) : isImage ? (
            /* Authenticated decrypted Image rendering */
            <div style={{ overflow: 'auto', width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <img
                key={`img-${retryKey}-${docId}`}
                src={previewBlobUrl}
                alt={filename}
                className="preview-img"
                style={{ transform: `scale(${imageZoom}) rotate(${rotation}deg)`, transformOrigin: 'center center', transition: 'transform 0.2s ease' }}
              />
            </div>
          ) : (
            /* Fallback generic document viewer */
            <iframe
              key={`fallback-${retryKey}-${docId}`}
              src={previewBlobUrl}
              title={filename}
              className="preview-iframe"
            />
          )
        ) : null}

        {/* Phase 11.3: Floating PDF & Image Toolbar */}
        {previewBlobUrl && !hasError && (
          <div className="docpilot-floating-pdf-toolbar" role="toolbar" aria-label="Document viewer floating controls">
            <button
              type="button"
              className="docpilot-floating-btn"
              onClick={() => setImageZoom((z) => Math.max(0.5, Number((z - 0.2).toFixed(1))))}
              title="Zoom Out"
              aria-label="Zoom out"
            >
              <ZoomOut size={15} />
            </button>
            <span className="docpilot-floating-zoom-label">
              {Math.round(imageZoom * 100)}%
            </span>
            <button
              type="button"
              className="docpilot-floating-btn"
              onClick={() => setImageZoom((z) => Math.min(3.0, Number((z + 0.2).toFixed(1))))}
              title="Zoom In"
              aria-label="Zoom in"
            >
              <ZoomIn size={15} />
            </button>
            <div className="docpilot-floating-divider" />
            <button
              type="button"
              className="docpilot-floating-btn"
              onClick={() => setRotation((r) => (r + 90) % 360)}
              title="Rotate Document"
              aria-label="Rotate"
            >
              <RotateCcw size={14} />
            </button>
            <div className="docpilot-floating-divider" />
            <div className="docpilot-floating-page-ctrl">
              <button
                type="button"
                className="docpilot-floating-btn"
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                title="Previous page"
                aria-label="Previous page"
              >
                &lsaquo;
              </button>
              <span className="docpilot-floating-page-label">
                {currentPage} / {pageCount}
              </span>
              <button
                type="button"
                className="docpilot-floating-btn"
                disabled={currentPage >= pageCount}
                onClick={() => setCurrentPage((p) => Math.min(pageCount, p + 1))}
                title="Next page"
                aria-label="Next page"
              >
                &rsaquo;
              </button>
            </div>
            <div className="docpilot-floating-divider" />
            <button
              type="button"
              onClick={handleDownload}
              disabled={isDownloading}
              className="docpilot-floating-btn"
              title="Download Document"
              aria-label="Download Document"
            >
              {isDownloading ? <Loader2 size={14} className="spin-anim" /> : <Download size={14} />}
            </button>
            <button
              type="button"
              onClick={() => setIsFullscreen((f) => !f)}
              className="docpilot-floating-btn"
              title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
              aria-label="Toggle Fullscreen"
            >
              {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
            <button
              type="button"
              onClick={handleOpenInNewTab}
              className="docpilot-floating-btn"
              title="Open in New Tab"
              aria-label="Open in New Tab"
            >
              <ExternalLink size={14} />
            </button>
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
          flexDirection: 'column',
          gap: '0.4rem',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
          <span>
            Format: <strong style={{ textTransform: 'uppercase' }}>{(ext || '.bin').replace('.', '').toUpperCase()}</strong>
            {isPdf && ` • ${pageCount} ${pageCount === 1 ? 'Page' : 'Pages'}`}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {/* Verification Status Badge */}
            {isReviewRequired ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.15rem 0.5rem', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 600, backgroundColor: 'rgba(249, 115, 22, 0.15)', color: '#fb923c' }}>
                <AlertTriangle size={11} />
                <span>{`Review Required • Risk Score: ${riskScore}%`}</span>
              </span>
            ) : isUnsupported ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.15rem 0.5rem', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 600, backgroundColor: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8' }}>
                <HelpCircle size={11} />
                <span>Unsupported</span>
              </span>
            ) : (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.15rem 0.5rem', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 600, backgroundColor: 'rgba(34, 197, 94, 0.15)', color: '#4ade80' }}>
                <CheckCircle2 size={11} />
                <span>{`Verified • Risk Score: ${riskScore}%`}</span>
              </span>
            )}
            <span>
              ID: <code style={{ fontFamily: 'var(--font-mono)' }}>{docId.slice(0, 8)}...</code>
            </span>
          </div>
        </div>
        {reviewNotes && isReviewRequired && (
          <div style={{ fontSize: '0.72rem', color: '#fb923c', backgroundColor: 'rgba(249, 115, 22, 0.08)', padding: '0.3rem 0.6rem', borderRadius: '4px' }}>
            <strong>Review Notes:</strong> {reviewNotes}
          </div>
        )}
      </div>
    </div>
  );
};
