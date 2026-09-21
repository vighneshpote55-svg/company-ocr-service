import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Sparkles,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react';
import type { AiAnalysisResult, ChatMessage, UploadProgress, OllamaStatusResponse } from '../types';
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
}

export const AIModeView: React.FC<AIModeViewProps> = ({
  onNotify,
  onSwitchToOffline,
  onRefresh,
  onDocumentUploaded,
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
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatusResponse | null>(null);
  const [isCheckingOllama, setIsCheckingOllama] = useState(false);

  const fileInputHiddenRef = useRef<HTMLInputElement>(null);

  const fetchOllamaStatus = useCallback(async () => {
    setIsCheckingOllama(true);
    try {
      const status = await api.getOllamaStatus();
      setOllamaStatus(status);
    } catch {
      setOllamaStatus({
        reachable: false,
        model_installed: false,
        model: 'qwen2.5vl:3b',
        error: 'Ollama server is not reachable.',
      });
    } finally {
      setIsCheckingOllama(false);
    }
  }, []);

  useEffect(() => {
    fetchOllamaStatus();
  }, [fetchOllamaStatus]);

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

      setProgress({ step: 'done', percent: 100, message: 'AI Analysis complete!' });
      setTimeout(() => {
        setIsProcessing(false);
        setAnalyzedDoc(result);
        setMessages([
          {
            id: 'init-msg',
            role: 'assistant',
            content: `I analyzed this document and identified it as ${result.document_type} (${result.confidence} confidence).\n\n${result.summary}\n\nYou can ask any questions regarding this document below or use the quick actions.`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        onNotify(`Document "${result.filename}" analyzed successfully with AI!`, 'success');
        if (onRefresh) onRefresh();
        if (onDocumentUploaded) onDocumentUploaded(result);
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
      document_id: analyzedDoc.document_id,
      document_type: analyzedDoc.document_type,
      confidence: analyzedDoc.confidence,
      summary: analyzedDoc.summary,
      evidence: analyzedDoc.reasoning || analyzedDoc.evidence || [],
      extracted_fields: analyzedDoc.extracted_fields || {},
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${analyzedDoc.filename.replace(/\.[^/.]+$/, '')}_ai_analysis.json`;
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

      {/* Local AI Live Status Banner */}
      {ollamaStatus && (
        ollamaStatus.reachable && ollamaStatus.model_installed ? (
          <div className="local-ai-status-banner banner-ready">
            <div className="local-ai-status-left">
              <div className="local-ai-status-icon-wrap icon-success">
                <CheckCircle2 size={20} />
              </div>
              <div className="local-ai-status-content">
                <div className="local-ai-status-title">
                  <strong>Local AI Ready</strong>
                  <span className="local-ai-model-pill">Qwen2.5-VL:3B</span>
                </div>
                <p className="local-ai-status-desc">
                  Ollama (Qwen2.5-VL:3B) is running locally. All AI document analysis is performed completely offline.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="local-ai-status-banner banner-offline">
            <div className="local-ai-status-left">
              <div className="local-ai-status-icon-wrap icon-error">
                <AlertCircle size={20} />
              </div>
              <div className="local-ai-status-content">
                <div className="local-ai-status-title">
                  <strong>Local AI Offline</strong>
                </div>
                <p className="local-ai-status-desc">
                  {!ollamaStatus.reachable
                    ? 'Start Ollama to enable AI document analysis.'
                    : (ollamaStatus.error || 'Start Ollama to enable AI document analysis.')}
                </p>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-secondary local-ai-retry-btn"
              onClick={fetchOllamaStatus}
              disabled={isCheckingOllama}
              title="Check Ollama status again"
            >
              <RefreshCw size={14} className={isCheckingOllama ? 'spin-anim' : ''} />
              <span>{isCheckingOllama ? 'Checking...' : 'Retry'}</span>
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
