import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Sparkles,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react';
import type { AiAnalysisResult, ChatMessage, UploadProgress, AIProviderConfig } from '../types';
import { normalizeAiDocument } from '../types';
import { api } from '../services/api';
import { AIUploadCard } from './AIUploadCard';
import { AIAnalysisCard } from './AIAnalysisCard';
import { AISummaryCard } from './AISummaryCard';
import { AIKeyFindingsCard } from './AIKeyFindingsCard';
import { AIQuickActions } from './AIQuickActions';
import { AIChatPanel } from './AIChatPanel';

interface AIModeViewProps {
  onNotify: (message: string, type?: 'success' | 'error' | 'info') => void;
  onSwitchToOffline?: () => void;
  onRefresh?: () => void;
  onDocumentUploaded?: (doc: any) => void;
  aiConfig?: AIProviderConfig | null;
  onRefreshAiConfig?: () => Promise<AIProviderConfig | null | void>;
}

export const AIModeView: React.FC<AIModeViewProps> = ({
  onNotify,
  onSwitchToOffline,
  onRefresh,
  onDocumentUploaded,
  aiConfig: propAiConfig,
  onRefreshAiConfig,
}) => {
  const [analyzedDoc, setAnalyzedDoc] = useState<AiAnalysisResult | null>(null);
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

  // Synchronize when prop changes
  useEffect(() => {
    if (propAiConfig) {
      setAiConfig(propAiConfig);
    }
  }, [propAiConfig]);

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

      console.error('[AI Mode] Raw AI analysis response received:', result);
      const normalizedDoc = normalizeAiDocument(result);
      console.error('[AI Mode] Normalized AI document payload:', normalizedDoc);

      setProgress({ step: 'done', percent: 100, message: 'AI Analysis complete!' });
      setTimeout(() => {
        setIsProcessing(false);
        setAnalyzedDoc(normalizedDoc);
        setMessages([
          {
            id: 'init-msg',
            role: 'assistant',
            content: `I analyzed this document and identified it as ${normalizedDoc.document_type} (${normalizedDoc.confidence_level || normalizedDoc.confidence} confidence).\n\n${normalizedDoc.summary}\n\nYou can ask any questions regarding this document below or use the quick actions.`,
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

      const reply = await api.chatAiDocument(analyzedDoc.document_id, trimmed, historyPayload);

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
    if (window.confirm('Clear the current document and start a new AI session?')) {
      setAnalyzedDoc(null);
      setMessages([]);
      setProgress({ step: 'idle', percent: 0, message: '' });
    }
  };

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
                    {aiConfig.active_provider === 'openrouter' ? 'OpenRouter' : aiConfig.active_provider.toUpperCase()} • {aiConfig.active_model}
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
                  <span className="local-ai-model-pill">Ollama • qwen2.5vl:3b</span>
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

      {/* When no document is loaded or while processing */}
      {!analyzedDoc ? (
        <AIUploadCard
          onUpload={handleFileUpload}
          isProcessing={isProcessing}
          progress={progress}
        />
      ) : (
        /* Document Analyzed: Full SaaS Flow */
        <div className="ai-results-flow-container">
          {/* 1. AI Analysis Card */}
          <AIAnalysisCard
            document={analyzedDoc}
            onUploadNew={() => fileInputHiddenRef.current?.click()}
            onReset={resetSession}
          />

          {/* 2. Document Summary */}
          <AISummaryCard
            summary={analyzedDoc.summary}
            documentType={analyzedDoc.document_type}
          />

          {/* 3. Key Findings */}
          <AIKeyFindingsCard
            reasoning={analyzedDoc.reasoning}
            documentType={analyzedDoc.document_type}
            extractedFields={analyzedDoc.extracted_fields}
          />

          {/* 4. Quick Actions */}
          <AIQuickActions
            document={analyzedDoc}
            onTriggerPrompt={handleSendMessage}
            onDownloadAnalysis={handleDownloadAnalysis}
          />

          {/* 5. AI Chat Assistant */}
          <AIChatPanel
            document={analyzedDoc}
            messages={messages}
            isAiThinking={isAiThinking}
            onSendMessage={handleSendMessage}
            onSwitchToOffline={onSwitchToOffline}
            onNotify={onNotify}
          />
        </div>
      )}
    </div>
  );
};
