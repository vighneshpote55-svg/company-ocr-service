import React, { useState } from 'react';
import { FileText, Download, ExternalLink, ZoomIn, ZoomOut, Image as ImageIcon } from 'lucide-react';
import type { DocumentItem } from '../types';
import { api } from '../services/api';

interface DocumentPreviewProps {
  document: DocumentItem;
}

export const DocumentPreview: React.FC<DocumentPreviewProps> = ({ document }) => {
  const [imageZoom, setImageZoom] = useState(1);
  const docId = document.id || (document as any).document_id || '';
  const filename = document.filename || 'document';
  const isPdf = filename.toLowerCase().endsWith('.pdf');
  const fileUrl = document.file_url || (docId ? api.getFileUrl(docId) : '');

  const formatBytes = (bytes?: number) => {
    if (!bytes || bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className="preview-panel">
      <div className="preview-header">
        <div className="preview-title">
          {isPdf ? <FileText size={16} color="#818cf8" /> : <ImageIcon size={16} color="#38bdf8" />}
          <span style={{ maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {document.filename}
          </span>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-subtle)' }}>
            ({formatBytes(document.file_size)})
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
          {!isPdf && (
            <>
              <button
                className="copy-btn"
                onClick={() => setImageZoom((z) => Math.max(0.6, z - 0.2))}
                title="Zoom out"
              >
                <ZoomOut size={15} />
              </button>
              <button
                className="copy-btn"
                onClick={() => setImageZoom((z) => Math.min(2.5, z + 0.2))}
                title="Zoom in"
              >
                <ZoomIn size={15} />
              </button>
            </>
          )}

          <a
            href={fileUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="copy-btn"
            title="Open original in new tab"
          >
            <ExternalLink size={15} />
          </a>

          <a
            href={docId ? api.getFileUrl(docId, true) : '#'}
            download={filename}
            className="copy-btn"
            title="Download document file"
          >
            <Download size={15} />
          </a>
        </div>
      </div>

      <div className="preview-body">
        {isPdf ? (
          <iframe
            src={fileUrl ? `${fileUrl}#toolbar=0&navpanes=0` : ''}
            title={filename}
            className="preview-iframe"
          />
        ) : (
          <img
            src={fileUrl}
            alt={filename}
            className="preview-img"
            style={{ transform: `scale(${imageZoom})` }}
          />
        )}
      </div>

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
        <span>Format: <strong style={{ textTransform: 'uppercase' }}>{(document.file_type || (isPdf ? '.pdf' : '.png')).replace('.', '').toUpperCase()}</strong></span>
        <span>Storage ID: <code style={{ fontFamily: 'var(--font-mono)' }}>{(docId || 'unknown').slice(0, 8)}...</code></span>
      </div>
    </div>
  );
};
