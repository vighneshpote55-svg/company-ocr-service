import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import {
  Search,
  Eye,
  Trash2,
  Download,
  FileText,
  Zap,
  Scan,
  RefreshCw,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Sparkles,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import type { DocumentItem, SupportedType, EngineInfo } from '../types';
import { api } from '../services/api';

/**
 * Traces and formats real document OCR confidence.
 * Returns:
 * - '0%' for failed documents
 * - 'N/A' when confidence is null, undefined, or empty
 * - Rounded percentage string (e.g. '94%', '100%') for valid numeric values
 */
export function formatConfidence(doc: DocumentItem): string {
  const isFailed = doc.status === 'error' || doc.status === 'failed' || doc.verification_status === 'failed';
  if (isFailed) {
    return '0%';
  }

  const raw = doc.confidence !== undefined && doc.confidence !== null
    ? doc.confidence
    : (doc as any).confidence;

  if (raw === undefined || raw === null || raw === '') {
    return 'N/A';
  }

  const num = typeof raw === 'number' ? raw : parseFloat(String(raw));
  if (isNaN(num)) {
    return 'N/A';
  }

  const pct = num <= 1 ? Math.round(num * 100) : Math.round(num);
  return `${pct}%`;
}

interface DocumentsTableProps {
  documents: DocumentItem[];
  supportedTypes: SupportedType[];
  onSelectDocument: (doc: DocumentItem) => void;
  onDeleteDocument: (id: string) => void;
  onClearAll?: () => void;
  onRefresh: () => void;
  isLoading?: boolean;
  engineInfo?: EngineInfo | null;
}

export const DocumentsTable: React.FC<DocumentsTableProps> = ({
  documents,
  supportedTypes,
  onSelectDocument,
  onDeleteDocument,
  onClearAll,
  onRefresh,
  isLoading = false,
  engineInfo,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [modeFilter, setModeFilter] = useState<'all' | 'offline' | 'ai'>('all');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);

  // Server-side filtering and pagination state
  const [serverDocs, setServerDocs] = useState<DocumentItem[] | null>(null);
  const [serverTotal, setServerTotal] = useState<number | null>(null);
  const [isTableLoading, setIsTableLoading] = useState<boolean>(false);
  const isMountedRef = useRef<boolean>(false);

  // 300ms debounce on search input before querying backend
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Reset pagination to page 1 whenever any filter or debounced search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [debouncedSearch, modeFilter, typeFilter, statusFilter]);

  // Query backend with all active filters and pagination
  const fetchFromBackend = useCallback(async () => {
    try {
      setIsTableLoading(true);
      const offset = (currentPage - 1) * pageSize;
      const res = await api.getDocuments({
        search: debouncedSearch.trim() || undefined,
        docType: typeFilter !== 'all' ? typeFilter : undefined,
        mode: modeFilter !== 'all' ? modeFilter : undefined,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        limit: pageSize,
        offset,
      });

      if (res && Array.isArray(res.items)) {
        setServerDocs(res.items);
        setServerTotal(typeof res.total === 'number' ? res.total : res.items.length);
      }
    } catch (err) {
      // In SSR, test environments without active network, or offline mode,
      // fallback smoothly to client-side filtering on documents prop
      console.warn('Backend documents query fallback to local cache:', err);
    } finally {
      setIsTableLoading(false);
    }
  }, [debouncedSearch, modeFilter, typeFilter, statusFilter, currentPage, pageSize]);

  // Fetch when filters or pagination change
  useEffect(() => {
    if (!isMountedRef.current) {
      isMountedRef.current = true;
    }
    fetchFromBackend();
  }, [fetchFromBackend]);

  // Re-sync when parent documents prop updates (e.g. after upload or clear)
  useEffect(() => {
    if (isMountedRef.current) {
      fetchFromBackend();
    }
  }, [documents, fetchFromBackend]);

  const getStatusCategory = (doc: DocumentItem): 'verified' | 'review_required' | 'unsupported' | 'processing' | 'failed' => {
    if (doc.status === 'failed' || doc.status === 'error' || doc.verification_status === 'failed') {
      return 'failed';
    }
    if (doc.status === 'processing') {
      return 'processing';
    }
    if (doc.verification_status === 'unsupported' || (doc.doc_type === 'unknown' && doc.status === 'low_confidence')) {
      return 'unsupported';
    }
    if (
      doc.verification_status === 'review_required' ||
      Boolean(doc.review_required) ||
      (typeof doc.risk_score === 'number' && doc.risk_score >= 30) ||
      doc.status === 'warning' ||
      doc.checksum_valid === false
    ) {
      return 'review_required';
    }
    return 'verified';
  };

  // Client-side fallback filtering (used when server query is loading or in test/SSR mode)
  const clientFilteredDocs = useMemo(() => {
    return documents.filter((doc) => {
      // 1. Search Query
      const query = (debouncedSearch || searchTerm).trim().toLowerCase();
      if (query) {
        const matchName = (doc.filename || '').toLowerCase().includes(query);
        const matchType = `${doc.document_type || ''} ${doc.doc_type || ''}`.toLowerCase().includes(query);
        const matchText = (doc.extracted_text || '').toLowerCase().includes(query);
        if (!matchName && !matchType && !matchText) return false;
      }

      // 2. Mode Filter (Offline vs AI)
      if (modeFilter !== 'all') {
        const isAi = (doc as any).mode === 'ai' || doc.doc_type === 'ai_analyzed' || Boolean((doc as any).ai_analysis);
        if (modeFilter === 'offline' && isAi) return false;
        if (modeFilter === 'ai' && !isAi) return false;
      }

      // 3. Type Filter
      if (typeFilter !== 'all') {
        const target = typeFilter.toLowerCase();
        const docType = (doc.doc_type || '').toLowerCase();
        const docTypeName = (doc.document_type || '').toLowerCase();
        const matchingSupported = supportedTypes.find((t) => t.id.toLowerCase() === target);
        const supportedName = (matchingSupported?.name || '').toLowerCase();

        const matchesDocType = docType === target;
        const matchesDocTypeName =
          Boolean(supportedName) &&
          (docTypeName === supportedName ||
            docTypeName.includes(supportedName) ||
            supportedName.includes(docTypeName));

        const targetSlug = target.replace(/_/g, ' ');
        const matchesSlug = docTypeName.includes(targetSlug) || targetSlug.includes(docTypeName);

        const targetWords = (supportedName || targetSlug).split(/\s+/).filter((w) => w.length > 2);
        const matchesWords = targetWords.length > 0 && targetWords.every((w) => docTypeName.includes(w));

        const matchesAi = target === 'ai_analyzed' && (docType === 'ai_analyzed' || doc.doc_type === 'ai_analyzed');

        if (!matchesDocType && !matchesDocTypeName && !matchesSlug && !matchesWords && !matchesAi) {
          return false;
        }
      }

      // 4. Status Filter
      if (statusFilter !== 'all') {
        const category = getStatusCategory(doc);
        if (statusFilter === 'review' && category === 'review_required') {
          // backwards compatibility with 'review'
        } else if (category !== statusFilter) {
          return false;
        }
      }

      return true;
    });
  }, [documents, searchTerm, debouncedSearch, modeFilter, typeFilter, statusFilter, supportedTypes]);

  // Determine effective display documents and total counts
  const totalItems = serverTotal !== null ? serverTotal : clientFilteredDocs.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const validPage = Math.min(currentPage, totalPages);
  const startIndex = (validPage - 1) * pageSize;

  const displayDocs = useMemo(() => {
    if (serverDocs !== null) {
      return serverDocs;
    }
    return clientFilteredDocs.slice(startIndex, startIndex + pageSize);
  }, [serverDocs, clientFilteredDocs, startIndex, pageSize]);

  const endIndex = Math.min(startIndex + displayDocs.length, totalItems);

  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  const renderStatusBadge = (doc: DocumentItem) => {
    const category = getStatusCategory(doc);

    switch (category) {
      case 'verified':
        return (
          <span className="status-badge-saas badge-verified" data-testid="status-badge-verified" title="Verified Clean Document">
            <CheckCircle2 size={13} />
            <span>Verified</span>
          </span>
        );
      case 'review_required':
        return (
          <span
            className="status-badge-saas badge-review"
            data-testid="status-badge-review-required"
            title={doc.human_review_reason || doc.reason || doc.checksum_reason || 'Review Required'}
            style={{ backgroundColor: 'rgba(249, 115, 22, 0.15)', color: '#fb923c', border: '1px solid rgba(249, 115, 22, 0.3)' }}
          >
            <AlertTriangle size={13} />
            <span>Review Required</span>
          </span>
        );
      case 'unsupported':
        return (
          <span
            className="status-badge-saas badge-unsupported"
            data-testid="status-badge-unsupported"
            title={doc.reason || 'Unsupported Document Type'}
            style={{ backgroundColor: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8', border: '1px solid rgba(148, 163, 184, 0.3)' }}
          >
            <HelpCircle size={13} />
            <span>Unsupported</span>
          </span>
        );
      case 'processing':
        return (
          <span className="status-badge-saas badge-processing" title="Processing Document">
            <Clock size={13} className="spin-anim" />
            <span>Processing</span>
          </span>
        );
      case 'failed':
      default:
        return (
          <span
            className="status-badge-saas badge-failed"
            title={doc.reason || 'Document Ingestion Failed'}
          >
            <AlertCircle size={13} />
            <span>Failed</span>
          </span>
        );
    }
  };

  const renderModeBadge = (doc: DocumentItem) => {
    const isAi = (doc as any).mode === 'ai' || doc.doc_type === 'ai_analyzed' || Boolean((doc as any).ai_analysis);
    if (isAi) {
      return (
        <span className="mode-badge-pill mode-badge-ai" title="Processed with AI Intelligence">
          <Sparkles size={12} />
          <span>AI Mode</span>
        </span>
      );
    }
    return (
      <span className="mode-badge-pill mode-badge-offline" title="Processed with RapidOCR">
        <Zap size={12} />
        <span>RapidOCR</span>
      </span>
    );
  };

  const handleRefresh = async () => {
    await fetchFromBackend();
    onRefresh();
  };

  const handleDelete = (docId: string, filename: string) => {
    if (window.confirm(`Delete "${filename}" from vault?`)) {
      onDeleteDocument(docId);
      if (serverDocs) {
        setServerDocs((prev) => (prev ? prev.filter((d) => (d.id || (d as any).document_id) !== docId) : null));
        setServerTotal((prev) => (prev !== null && prev > 0 ? prev - 1 : 0));
      }
    }
  };

  return (
    <div className="vault-table-container">
      {/* Search and Filtering Toolbar */}
      <div className="vault-toolbar">
        {/* Search Input (320px on desktop, full width on tablet/mobile) */}
        <div className="vault-search-box">
          <Search size={15} className="vault-search-icon" />
          <input
            type="text"
            className="vault-search-input"
            placeholder="Search documents by filename, type, or content..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setCurrentPage(1);
            }}
          />
        </div>

        {/* Filters and Actions Controls Group */}
        <div className="vault-controls-group">
          {/* Filters: Mode, Document Type, and Status */}
          <div className="vault-filters-group">
            <select
              className="vault-filter-select vault-mode-select"
              value={modeFilter}
              onChange={(e) => {
                setModeFilter(e.target.value as any);
                setCurrentPage(1);
              }}
              aria-label="Filter by processing mode"
            >
              <option value="all">All Modes</option>
              <option value="offline">Offline (RapidOCR)</option>
              <option value="ai">AI Intelligence</option>
            </select>

            <select
              className="vault-filter-select vault-type-select"
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value);
                setCurrentPage(1);
              }}
              aria-label="Filter by document type"
            >
              <option value="all">All Document Types</option>
              {supportedTypes
                .filter((t) => t.id !== 'auto')
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
            </select>

            <select
              className="vault-filter-select vault-status-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
              aria-label="Filter by status"
            >
              <option value="all">All Statuses</option>
              <option value="verified">Verified (Green)</option>
              <option value="review_required">Review Required (Orange)</option>
              <option value="unsupported">Unsupported (Gray)</option>
              <option value="failed">Failed (Red)</option>
            </select>
          </div>

          {/* Actions: Refresh & Clear All */}
          <div className="vault-toolbar-actions">
            <button
              className="btn btn-secondary vault-action-btn vault-refresh-btn"
              onClick={handleRefresh}
              disabled={isLoading || isTableLoading}
              title="Refresh table data"
            >
              <RefreshCw size={14} className={isLoading || isTableLoading ? 'spin-anim' : ''} />
              <span>Refresh</span>
            </button>

            {onClearAll && (
              <button
                className="btn btn-danger vault-action-btn vault-clear-all-btn"
                onClick={onClearAll}
                disabled={totalItems === 0 || isLoading}
                title="Clear all documents from Document Vault"
              >
                <Trash2 size={14} />
                <span>Clear All</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Rounded Table Shell with Sticky Header */}
      <div className="vault-table-scroll-wrapper">
        <table className="vault-table">
          <thead>
            <tr>
              <th style={{ width: '56px' }}>Preview</th>
              <th>Document</th>
              <th>Mode</th>
              <th>Type</th>
              <th>Status</th>
              <th>OCR Decision</th>
              <th>Confidence</th>
              <th>Processed At</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {displayDocs.length === 0 ? (
              <tr>
                <td colSpan={9} className="vault-empty-row">
                  <div className="vault-empty-state">
                    <FileText size={36} className="vault-empty-icon" />
                    <h4 className="vault-empty-title">
                      {documents.length === 0 ? 'Document Vault is empty' : 'No documents match your query'}
                    </h4>
                    <p className="vault-empty-subtitle">
                      {documents.length === 0
                        ? 'There are no documents in the vault. Upload or ingest documents to get started.'
                        : 'Try adjusting filters, clearing your search query, or ingest new files.'}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              displayDocs.map((doc, idx) => {
                const docId = doc.id || (doc as any).document_id || '';
                const isBypassed = !doc.ocr_required;
                const isFailed = doc.status === 'error' || doc.status === 'failed';
                const previewUrl = doc.preview_url || (docId ? api.getPreviewUrl(docId) : '');

                const getEngineLabel = () => {
                  if (isBypassed) return 'Text Layer';
                  if (doc.text_source === 'rapid_ocr') return 'RapidOCR';
                  if (doc.text_source === 'paddle_ocr') return 'PaddleOCR';
                  if (engineInfo?.display_name) return engineInfo.display_name;
                  return 'Neural OCR';
                };

                return (
                  <tr
                    key={docId || `${doc.filename}-${idx}`}
                    className={`vault-table-row ${isFailed ? 'row-failed' : ''}`}
                  >
                    <td>
                      {doc.has_preview || previewUrl ? (
                        <img
                          src={previewUrl}
                          alt={doc.filename}
                          className="vault-preview-thumb"
                          loading="lazy"
                          onError={(e) => {
                            // Fallback to placeholder if thumbnail is missing
                            (e.target as HTMLElement).style.display = 'none';
                            const sibling = (e.target as HTMLElement).nextElementSibling;
                            if (sibling) (sibling as HTMLElement).style.display = 'flex';
                          }}
                        />
                      ) : null}
                      {(!doc.has_preview && !previewUrl) && (
                        <div className="vault-preview-placeholder">
                          <FileText size={18} />
                        </div>
                      )}
                    </td>

                    <td>
                      <div
                        className="vault-doc-filename"
                        onClick={() => onSelectDocument(doc)}
                        title="Click to view full inspection"
                      >
                        {doc.filename}
                      </div>
                      <div className="vault-doc-meta">
                        {((doc.file_size || 0) / 1024).toFixed(1)} KB • {doc.pages || 1} {(doc.pages || 1) === 1 ? 'page' : 'pages'}
                      </div>
                    </td>

                    {/* Mode: Offline (RapidOCR) vs AI Mode */}
                    <td>{renderModeBadge(doc)}</td>

                    <td>
                      <span className="doc-type-pill">
                        {doc.document_type || doc.doc_type || 'Unknown'}
                      </span>
                    </td>

                    {/* Status badge: Green = Verified, Orange = Review, Blue = Processing, Red = Failed */}
                    <td>{renderStatusBadge(doc)}</td>

                    <td>
                      <span
                        className={`ocr-decision-chip ${isFailed ? 'decision-failed' : isBypassed ? 'decision-bypassed' : 'decision-neural'}`}
                      >
                        {isFailed ? (
                          <AlertCircle size={13} />
                        ) : isBypassed ? (
                          <Zap size={13} />
                        ) : (
                          <Scan size={13} />
                        )}
                        <span>{getEngineLabel()}</span>
                      </span>
                    </td>

                    <td>
                      <span className="vault-confidence-text" data-testid="doc-confidence">
                        {formatConfidence(doc)}
                      </span>
                    </td>

                    <td>
                      <span className="vault-timestamp-text">{formatDate(doc.created_at)}</span>
                    </td>

                    <td style={{ textAlign: 'right' }}>
                      <div className="vault-actions-cluster">
                        <button
                          className="btn btn-secondary vault-inspect-btn"
                          onClick={() => onSelectDocument(doc)}
                          title="Inspect Document"
                        >
                          <Eye size={14} />
                          <span>Inspect</span>
                        </button>

                        <a
                          href={docId ? api.getFileUrl(docId, true) : '#'}
                          download={doc.filename}
                          className="icon-action-btn"
                          title="Download original file"
                          aria-label="Download original file"
                        >
                          <Download size={14} />
                        </a>

                        <button
                          className="icon-action-btn delete-btn"
                          onClick={() => handleDelete(docId, doc.filename)}
                          title="Delete document"
                          aria-label="Delete document"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls Bar */}
      {totalItems > 0 && (
        <div className="vault-pagination-bar">
          <div className="vault-pagination-left">
            <span className="vault-pagination-text">
              Showing <strong>{startIndex + 1}</strong> to <strong>{endIndex}</strong> of <strong>{totalItems}</strong> documents
            </span>
            <div className="vault-page-size-selector">
              <label htmlFor="vault-page-size">Per page:</label>
              <select
                id="vault-page-size"
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setCurrentPage(1);
                }}
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </select>
            </div>
          </div>

          <div className="vault-pagination-right">
            <button
              className="btn btn-secondary vault-page-nav-btn"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={validPage <= 1}
              aria-label="Previous Page"
            >
              <ChevronLeft size={16} />
              <span>Prev</span>
            </button>

            <span className="vault-page-indicator">
              Page <strong>{validPage}</strong> of <strong>{totalPages}</strong>
            </span>

            <button
              className="btn btn-secondary vault-page-nav-btn"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={validPage >= totalPages}
              aria-label="Next Page"
            >
              <span>Next</span>
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
