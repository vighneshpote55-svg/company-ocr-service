import React, { useEffect } from 'react';
import { Trash2, AlertTriangle, X } from 'lucide-react';

interface ConfirmClearModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isDeleting?: boolean;
}

export const ConfirmClearModal: React.FC<ConfirmClearModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  isDeleting = false,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isDeleting) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isDeleting, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="modal-overlay"
      onClick={() => {
        if (!isDeleting) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="clear-modal-title"
    >
      <div
        className="modal-content confirm-clear-modal-card"
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: '460px',
          padding: '24px 26px',
        }}
      >
        {/* Header Icon + Close */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '12px',
              backgroundColor: 'rgba(239, 68, 68, 0.12)',
              color: '#ef4444',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid rgba(239, 68, 68, 0.25)',
            }}
          >
            <Trash2 size={22} />
          </div>

          <button
            onClick={onClose}
            disabled={isDeleting}
            className="btn btn-ghost"
            style={{ padding: '6px', borderRadius: '8px', color: 'var(--text-muted)' }}
            aria-label="Close dialog"
          >
            <X size={18} />
          </button>
        </div>

        {/* Title */}
        <h3
          id="clear-modal-title"
          style={{
            fontSize: '1.25rem',
            fontWeight: 700,
            color: 'var(--text-main)',
            margin: '0 0 8px 0',
            letterSpacing: '-0.01em',
          }}
        >
          Delete all documents?
        </h3>

        {/* Message */}
        <p
          style={{
            fontSize: '0.92rem',
            color: 'var(--text-muted)',
            lineHeight: 1.5,
            margin: '0 0 24px 0',
          }}
        >
          This will permanently remove every uploaded document from the Document Vault. This action cannot be undone.
        </p>

        {/* Danger notice warning */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            backgroundColor: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            borderRadius: '10px',
            padding: '10px 14px',
            marginBottom: '24px',
            fontSize: '0.85rem',
            color: '#ef4444',
          }}
        >
          <AlertTriangle size={16} style={{ flexShrink: 0 }} />
          <span>All original uploads, thumbnails, and extraction results will be deleted.</span>
        </div>

        {/* Action Buttons */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
          }}
        >
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isDeleting}
            style={{ padding: '0.55rem 1.1rem', fontWeight: 500 }}
          >
            Cancel
          </button>

          <button
            type="button"
            className="btn btn-danger"
            onClick={onConfirm}
            disabled={isDeleting}
            style={{
              padding: '0.55rem 1.25rem',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Trash2 size={15} />
            <span>{isDeleting ? 'Deleting...' : 'Delete All'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
