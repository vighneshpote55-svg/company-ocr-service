import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Sparkles,
  CheckCircle2,
  RefreshCw,
  FileText,
  FileCode,
  ShieldCheck,
  UploadCloud,
  RotateCcw,
  Layers,
  Cpu,
} from 'lucide-react';
import type { AiAnalysisResult, ChatMessage, UploadProgress, AIProviderConfig, DocumentItem } from '../types';
import { normalizeAiDocument } from '../types';
import { api } from '../services/api';
import { AIUploadCard } from './AIUploadCard';
import { AISummaryCard } from './AISummaryCard';
import { AIKeyFindingsCard } from './AIKeyFindingsCard';
import { AIQuickActions } from './AIQuickActions';
import { AIChatPanel } from './AIChatPanel';
import { DocumentPreview } from './DocumentPreview';
import { ExtractedFields } from './ExtractedFields';
import { ExtractedTextViewer } from './ExtractedTextViewer';
import { JsonResultViewer } from './JsonResultViewer';

interface AIModeViewProps {
  onNotify: (message: string, type?: 'success' | 'error' | 'info') => void;
  onSwitchToOffline?: () => void;
  onRefresh?: () => void;
  onDocumentUploaded?: (doc: any) => void;
  aiConfig?: AIProviderConfig | null;
  onRefreshAiConfig?: () => Promise<AIProviderConfig | null | void>;
  selectedDoc?: DocumentItem | null;
  onClearSelectedDoc?: () => void;
}

export const AIModeView: React.FC<AIModeViewProps> = ({
  onNotify,
  onSwitchToOffline,
  onRefresh,
  onDocumentUploaded,
  aiConfig: propAiConfig,
  onRefreshAiConfig,
  selectedDoc,
  onClearSelectedDoc,
}) => {
  const [analyzedDoc, setAnalyzedDoc] = useState<AiAnalysisResult | null>(() => {
    return selectedDoc ? normalizeAiDocument(selectedDoc) : null;
  });
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState<UploadProgress>({
    step: 'idle',
    percent: 0,
    message: '',
  });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isAiThinking, setIsAiThinking] = useState(false);
  const [aiConfig, setAiConfig] = useState<AIProviderConfig | null>(propAiConfig ?? null);
  const [isCheckingAiConfig, setIsCheckingAiConfig] = useState(false);
  const [activeTab, setActiveTab] = useState<'fields' | 'text' | 'json'>('fields');

  // Synchronize when prop changes
  useEffect(() => {
    if (propAiConfig) {
      setAiConfig(propAiConfig);
    }
  }, [propAiConfig]);

  // Synchronize with external selectedDoc if provided (e.g. inspected from Document Vault while in AI Mode)
  useEffect(() => {
    if (selectedDoc) {
      const normalized = normalizeAiDocument(selectedDoc);
      setAnalyzedDoc(normalized);
      const confStr = normalized.confidence_level || (typeof normalized.confidence === 'number' ? `${Math.round(normalized.confidence * 100)}%` : String(normalized.confidence || 'high'));
      setMessages([
        {
          id: 'init-msg',
          role: 'assistant',
          content: `I analyzed "${normalized.filename}" and identified it as ${normalized.document_type} (${confStr} confidence).\n\n${normalized.summary || ''}\n\nYou can ask any questions regarding this document below or use the quick actions.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    }
  }, [selectedDoc]);

  const fileInputHiddenRef = useRef<HTMLInputElement>(null);

  const fetchAiConfig = useCallback(async () => {
    setIsCheckingAiConfig(true);
    try {
      if (onRefreshAiConfig) {
        const res = await onRefreshAiConfig();
        if (res) {
          setAiConfig(res);
          return;
        }
      }
      const cfg = await api.getAiConfig();
      setAiConfig(cfg);
    } catch (e) {
      console.warn('Failed to fetch AI configuration from /api/ai/config:', e);
    } finally {
      setIsCheckingAiConfig(false);
    }
  }, [onRefreshAiConfig]);

  useEffect(() => {
    if (!propAiConfig) {
      fetchAiConfig();
    }
  }, [fetchAiConfig, propAiConfig]);

  const handleFileUpload = async (file: File) => {
    const validExtensions = ['.pdf', '.png', '.jpg', '.jpeg', '.webp'];
    const hasValidExt = validExtensions.some((ext) =>
      file.name.toLowerCase().endsWith(ext)
    );

    if (!hasValidExt) {
      onNotify('Invalid file type. Please upload a PDF, PNG, JPG, or WEBP.', 'error');
      return;
    }

    if (file.size > 25 * 1024 * 1024) {
      onNotify(`File is too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Max 25MB.`, 'error');
      return;
    }

    setAnalyzedDoc(null);
    setMessages([]);
    setIsProcessing(true);
    setProgress({ step: 'uploading', percent: 20, message: 'Uploading document for AI analysis...' });

    try {
      setTimeout(() => {
        setProgress({ step: 'analyzing', percent: 50, message: 'Extracting text layer and structural tokens...' });
      }, 350);

      setTimeout(() => {
        setProgress({ step: 'extracting', percent: 75, message: 'AI evaluating classification & reasoning...' });
      }, 800);

      const result = await api.analyzeAiDocument(file, (pct) => {
        if (pct < 90) setProgress((prev) => ({ ...prev, percent: pct }));
      });

      const normalizedDoc = normalizeAiDocument(result);

      setProgress({ step: 'done', percent: 100, message: 'AI Analysis complete!' });
      setTimeout(() => {
        setIsProcessing(false);
        setAnalyzedDoc(normalizedDoc);
        const confDisplay = normalizedDoc.confidence_level || (typeof normalizedDoc.confidence === 'number' ? `${Math.round(normalizedDoc.confidence * 100)}%` : String(normalizedDoc.confidence || 'high'));
        setMessages([
          {
            id: 'init-msg',
            role: 'assistant',
            content: `I analyzed this document and identified it as ${normalizedDoc.document_type} (${confDisplay} confidence).\n\n${normalizedDoc.summary || ''}\n\nYou can ask any questions regarding this document below or use the quick actions.`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        onNotify(`Document "${normalizedDoc.filename}" analyzed successfully with AI!`, 'success');
        if (onDocumentUploaded) {
          onDocumentUploaded(normalizedDoc);
        } else if (onRefresh) {
          onRefresh();
        }
      }, 400);
    } catch (err: any) {
      setIsProcessing(false);
      setProgress({ step: 'error', percent: 0, message: err.message || 'AI Analysis failed' });
      onNotify(err.message || 'AI document analysis failed', 'error');
    }
  };

  const handleSendMessage = async (textToSend: string) => {
    const trimmed = textToSend.trim();
    if (!trimmed || !analyzedDoc || isAiThinking) return;

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      role: 'user',
      content: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsAiThinking(true);

    try {
      const historyPayload = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const docId = analyzedDoc.document_id || analyzedDoc.id || '';
      const reply = await api.chatAiDocument(docId, trimmed, historyPayload);

      const aiMsg: ChatMessage = {
        id: String(Date.now() + 1),
        role: 'assistant',
        content: reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: String(Date.now() + 1),
        role: 'assistant',
        content: `⚠️ Error answering query: ${err.message || 'Could not connect to AI service.'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
      onNotify(err.message || 'AI chat request failed', 'error');
    } finally {
      setIsAiThinking(false);
    }
  };

  const handleDownloadAnalysis = () => {
    if (!analyzedDoc) return;
    const payload = {
      document_id: analyzedDoc.document_id || analyzedDoc.id || '',
      document_type: analyzedDoc.document_type || 'Unknown Document',
      confidence: analyzedDoc.confidence,
      summary: analyzedDoc.summary || '',
      evidence: analyzedDoc.reasoning || analyzedDoc.evidence || [],
      extracted_fields: analyzedDoc.extracted_fields || {},
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const safeBaseName = (analyzedDoc.filename || 'document').replace(/\.[^/.]+$/, '');
    link.download = `${safeBaseName}_ai_analysis.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    onNotify('AI Analysis report downloaded', 'success');
  };

  const resetSession = () => {
    if (window.confirm('Clear the current document and return to upload?')) {
      setAnalyzedDoc(null);
      setMessages([]);
      setProgress({ step: 'idle', percent: 0, message: '' });
      if (onClearSelectedDoc) {
        onClearSelectedDoc();
      }
    }
  };

  // Provider Pill Text
  const providerLabel = aiConfig?.mode === 'external'
    ? `${aiConfig.active_provider === 'openrouter' ? 'OpenRouter' : aiConfig.active_provider.toUpperCase()} • ${aiConfig.active_model}`
    : 'Ollama • Qwen2.5-VL 3B';

  const rawConf = (analyzedDoc as any)?.confidence_level || analyzedDoc?.confidence || 'high';
  const confidenceLower = typeof rawConf === 'string'
    ? rawConf.toLowerCase()
    : (typeof rawConf === 'number' && rawConf >= 0.85 ? 'high' : rawConf >= 0.65 ? 'medium' : 'low');
  const confidenceDisplay = typeof rawConf === 'number' ? `${Math.round(rawConf * 100)}%` : rawConf;

  // Extract primary name or entity from extracted fields if available
  const fields = analyzedDoc?.extracted_fields || {};
  const extractedEntityName = fields.name || fields.person_name || fields.full_name || fields.company_name || fields.establishment_name || fields.holder_name || '';

  return (
    <div className="ai-workspace-container">
      {/* Hidden File Input for "Upload New" button */}
      <input
        ref={fileInputHiddenRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files && e.target.files[0]) {
            handleFileUpload(e.target.files[0]);
          }
          if (fileInputHiddenRef.current) {
            fileInputHiddenRef.current.value = '';
          }
        }}
      />

      {/* Main AI Dashboard Header */}
      <div className="ai-dashboard-header">
        <div className="ai-header-top-row">
          <div className="ai-header-badge">
            <Sparkles size={16} className="ai-header-sparkle-icon" />
            <span>AI Mode • Universal Document Intelligence</span>
          </div>
          <div className="ai-header-tagline-capsule">
            <span>Analyze Any Customer Document</span>
          </div>
        </div>

        <h2 className="ai-header-main-title">
          <span className="ai-header-emoji" role="img" aria-label="robot">🤖</span> AI Document Intelligence
        </h2>
        <p className="ai-header-subtitle">
          Intelligent classification, reasoning synthesis, and contextual Q&A for Employment Contracts, NDAs, Lease Agreements, Invoices, Reports, Letters, and custom customer documents.
        </p>
      </div>

      {/* AI Provider Live Status Banner */}
      {aiConfig && (
        aiConfig.mode === 'external' ? (
          <div className="local-ai-status-banner banner-ready" data-testid="ai-provider-status-external">
            <div className="local-ai-status-left">
              <div className="local-ai-status-icon-wrap" style={{ background: '#ede9fe', color: '#7c3aed', padding: '6px', borderRadius: '8px' }}>
                <Sparkles size={20} />
              </div>
              <div className="local-ai-status-content">
                <div className="local-ai-status-title">
                  <strong>External AI Active</strong>
                  <span className="local-ai-model-pill" style={{ background: '#7c3aed', color: '#ffffff' }}>
                    {providerLabel}
                  </span>
                </div>
                <p className="local-ai-status-desc">
                  Connected to external AI provider ({aiConfig.active_provider} / {aiConfig.active_model}). Document analysis uses external endpoint.
                </p>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-secondary local-ai-retry-btn"
              onClick={fetchAiConfig}
              disabled={isCheckingAiConfig}
              title="Refresh provider status"
            >
              <RefreshCw size={14} className={isCheckingAiConfig ? 'spin-anim' : ''} />
              <span>{isCheckingAiConfig ? 'Checking...' : 'Refresh'}</span>
            </button>
          </div>
        ) : (
          <div className="local-ai-status-banner banner-ready" data-testid="ai-provider-status-local">
            <div className="local-ai-status-left">
              <div className="local-ai-status-icon-wrap icon-success">
                <CheckCircle2 size={20} />
              </div>
              <div className="local-ai-status-content">
                <div className="local-ai-status-title">
                  <strong>Local AI Active</strong>
                  <span className="local-ai-model-pill">Ollama • Qwen2.5-VL 3B</span>
                </div>
                <p className="local-ai-status-desc">
                  Ollama (qwen2.5vl:3b) is running locally. All AI document analysis is performed completely offline.
                </p>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-secondary local-ai-retry-btn"
              onClick={fetchAiConfig}
              disabled={isCheckingAiConfig}
              title="Refresh provider status"
            >
              <RefreshCw size={14} className={isCheckingAiConfig ? 'spin-anim' : ''} />
              <span>{isCheckingAiConfig ? 'Checking...' : 'Refresh'}</span>
            </button>
          </div>
        )
      )}

      {/* When no document is loaded or while processing: Upload Area */}
      {!analyzedDoc ? (
        <AIUploadCard
          onUpload={handleFileUpload}
          isProcessing={isProcessing}
          progress={progress}
        />
      ) : (
        /* Document Analyzed: Full 2-Column AI Document Intelligence Workspace */
        <div className="ai-workspace-flow" data-testid="ai-workspace-flow">
          {/* Document Header (Part 5) */}
          <div className="ai-doc-header-card">
            <div className="ai-doc-header-main">
              <div className="ai-doc-header-titles">
                <div className="ai-doc-header-badge-row">
                  <span className="ai-doc-classification-pill">
                    <Layers size={14} />
                    <span>{analyzedDoc.document_type || 'Document'}</span>
                  </span>
                  <span className={`ai-confidence-pill ${confidenceLower}`}>
                    <CheckCircle2 size={13} />
                    <span>Confidence: {confidenceDisplay}</span>
                  </span>
                  <span className="ai-provider-tag-pill">
                    <Cpu size={13} />
                    <span>Provider: {providerLabel}</span>
                  </span>
                  <span className="ai-status-pill verified">
                    <span>Verified by AI</span>
                  </span>
                </div>

                <h3 className="ai-doc-title-text" title={analyzedDoc.filename}>
                  {extractedEntityName ? `${extractedEntityName} — ` : ''}{analyzedDoc.filename}
                </h3>
              </div>

              <div className="ai-doc-header-actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => fileInputHiddenRef.current?.click()}
                  style={{ padding: '0.45rem 0.85rem' }}
                >
                  <UploadCloud size={15} />
                  <span>Upload New</span>
                </button>

                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={resetSession}
                  style={{ padding: '0.45rem 0.85rem' }}
                  title="Clear current document"
                >
                  <RotateCcw size={15} />
                  <span>{selectedDoc ? 'Back to Vault' : 'Reset'}</span>
                </button>
              </div>
            </div>
          </div>

          {/* 2-Column Split AI Document Intelligence Workspace */}
          <div className="ai-workspace-split-2col">
            {/* LEFT COLUMN: Document Preview + Extracted Field Tabs & Intelligence */}
            <div className="ai-left-workspace-column">
              {/* 1. Document Preview */}
              <div className="ai-preview-card-wrap">
                <DocumentPreview document={analyzedDoc as any} />
              </div>

              {/* 2. Document Summary */}
              {analyzedDoc.summary && (
                <AISummaryCard
                  summary={analyzedDoc.summary}
                  documentType={analyzedDoc.document_type}
                />
              )}

              {/* 3. Key Findings & Reasoning */}
              <AIKeyFindingsCard
                reasoning={analyzedDoc.reasoning || analyzedDoc.evidence}
                documentType={analyzedDoc.document_type}
                extractedFields={analyzedDoc.extracted_fields}
              />

              {/* 4. Tabbed Inspector (Extracted Fields, Extracted Text, Raw JSON) */}
              <div className="inspect-panel" style={{ marginTop: '0.5rem' }}>
                <div className="tabs-nav">
                  <button
                    type="button"
                    className={`tab-btn ${activeTab === 'fields' ? 'active' : ''}`}
                    onClick={() => setActiveTab('fields')}
                  >
                    <ShieldCheck size={16} />
                    <span>Extracted Fields</span>
                  </button>

                  <button
                    type="button"
                    className={`tab-btn ${activeTab === 'text' ? 'active' : ''}`}
                    onClick={() => setActiveTab('text')}
                  >
                    <FileText size={16} />
                    <span>Extracted Text ({(analyzedDoc.extracted_text || '').length} chars)</span>
                  </button>

                  <button
                    type="button"
                    className={`tab-btn ${activeTab === 'json' ? 'active' : ''}`}
                    onClick={() => setActiveTab('json')}
                  >
                    <FileCode size={16} />
                    <span>Raw JSON Payload</span>
                  </button>
                </div>

                <div className="tab-content" style={{ padding: '1.25rem' }}>
                  {activeTab === 'fields' && (
                    <ExtractedFields
                      document={analyzedDoc as any}
                      onCopyToast={onNotify}
                      onSwitchToAiMode={undefined}
                    />
                  )}

                  {activeTab === 'text' && (
                    <ExtractedTextViewer
                      text={analyzedDoc.extracted_text || ''}
                      filename={analyzedDoc.filename}
                      onCopyToast={onNotify}
                    />
                  )}

                  {activeTab === 'json' && (
                    <JsonResultViewer
                      document={analyzedDoc as any}
                      onCopyToast={onNotify}
                    />
                  )}
                </div>
              </div>

              {/* 5. Quick Actions */}
              <div style={{ marginTop: '0.5rem' }}>
                <AIQuickActions
                  document={analyzedDoc}
                  onTriggerPrompt={handleSendMessage}
                  onDownloadAnalysis={handleDownloadAnalysis}
                />
              </div>
            </div>

            {/* RIGHT COLUMN: Sticky Grounded Contextual AI Chat */}
            <div className="ai-right-chat-column">
              <div className="ai-sticky-chat-wrapper">
                <AIChatPanel
                  document={analyzedDoc}
                  messages={messages}
                  isAiThinking={isAiThinking}
                  onSendMessage={handleSendMessage}
                  onSwitchToOffline={onSwitchToOffline}
                  onNotify={onNotify}
                  providerLabel={providerLabel}
                />
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
