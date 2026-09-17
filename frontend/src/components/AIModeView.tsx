import React, { useState, useRef, useEffect } from 'react';
import {
  Sparkles,
  UploadCloud,
  Send,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  Bot,
  User,
  HelpCircle,
  FileCheck,
  Copy,
  Check,
  ShieldCheck,
  ArrowRight,
  FileUp,
} from 'lucide-react';
import type { AiAnalysisResult, ChatMessage, UploadProgress } from '../types';
import { api } from '../services/api';
import { ProcessingTimeline } from './ProcessingTimeline';

interface AIModeViewProps {
  onNotify: (message: string, type?: 'success' | 'error' | 'info') => void;
  onSwitchToOffline?: () => void;
}

const SUGGESTED_QUESTIONS = [
  'What is the employee name?',
  'What is the joining date?',
  'What is the salary or compensation?',
  'Who is the employer or issuing authority?',
  'Summarize the primary purpose of this agreement.',
  'Does this document contain an expiration or termination clause?',
  'What are the confidentiality obligations outlined?',
];

export const AIModeView: React.FC<AIModeViewProps> = ({ onNotify, onSwitchToOffline }) => {
  const [analyzedDoc, setAnalyzedDoc] = useState<AiAnalysisResult | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState<UploadProgress>({
    step: 'idle',
    percent: 0,
    message: '',
  });
  const [dragActive, setDragActive] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isAiThinking, setIsAiThinking] = useState(false);
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getAiStatus()
      .then((status) => {
        setAiConfigured(status.configured);
      })
      .catch(() => {
        setAiConfigured(false);
      });
  }, []);

  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isAiThinking]);

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
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  };

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
        setProgress({ step: 'analyzing', percent: 50, message: 'Extracting text layer and structure...' });
      }, 350);

      setTimeout(() => {
        setProgress({ step: 'extracting', percent: 75, message: 'AI classifying document & generating reasoning...' });
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
            content: `I have analyzed **${result.filename}** and classified it as **${result.document_type}** (${result.confidence} confidence).\n\n${result.summary}\n\nYou can ask any questions regarding this document below.`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        onNotify(`Document "${result.filename}" analyzed successfully with AI!`, 'success');
      }, 400);
    } catch (err: any) {
      setIsProcessing(false);
      setProgress({ step: 'error', percent: 0, message: err.message || 'AI Analysis failed' });
      onNotify(err.message || 'AI document analysis failed', 'error');
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleSendMessage = async (queryText?: string) => {
    const textToSend = (queryText || inputQuery).trim();
    if (!textToSend || !analyzedDoc || isAiThinking) return;

    const userMsg: ChatMessage = {
      id: String(Date.now()),
      role: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputQuery('');
    setIsAiThinking(true);

    try {
      const historyPayload = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const reply = await api.chatAiDocument(analyzedDoc.document_id, textToSend, historyPayload);

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

  const handleCopyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgId(id);
    onNotify('Copied to clipboard', 'info');
    setTimeout(() => setCopiedMsgId(null), 1800);
  };

  const resetSession = () => {
    if (window.confirm('Clear the current document and start a new AI session?')) {
      setAnalyzedDoc(null);
      setMessages([]);
      setInputQuery('');
    }
  };

  return (
    <div className="ai-workspace-container">
      {/* AI Configuration Notice if no API key is detected */}
      {aiConfigured === false && (
        <div className="ai-config-warning-banner">
          <AlertCircle size={20} color="var(--warning)" />
          <div style={{ flex: 1 }}>
            <strong>AI Provider Notice:</strong> No <code>AI_API_KEY</code> detected in environment. Configure an API key (OpenRouter / OpenAI / Gemini) to enable conversational document intelligence.
          </div>
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

      {/* Upload Dropzone (shown when no document is active) */}
      {!analyzedDoc && (
        <div className="upload-workspace-card ai-variant">
          <div className="upload-workspace-header">
            <div className="upload-mode-badge ai-badge">
              <Sparkles size={16} />
              <span>AI Mode • Universal Document Intelligence</span>
            </div>
            <h2 className="upload-main-title">Analyze Any Document with AI</h2>
            <p className="upload-main-subtitle">
              Upload documents beyond the 22 predefined offline types (e.g. contracts, NDAs, offer letters, court notices). The AI classifies the structure, extracts semantic meaning, and answers questions.
            </p>
          </div>

          {isProcessing ? (
            <ProcessingTimeline progress={progress} />
          ) : (
            <div
              className={`enterprise-dropzone ai-dropzone ${dragActive ? 'drag-active' : ''}`}
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
                <div className="illustration-glow-ring ai-glow" />
                <div className="illustration-icon-box ai-icon-box">
                  <FileUp size={36} className="illustration-file-icon" />
                  <UploadCloud size={24} className="illustration-cloud-icon" />
                </div>
              </div>

              <div className="dropzone-headline">
                <span className="dropzone-lead">Drag & Drop Documents</span> or{' '}
                <span className="dropzone-browse-cta ai-cta">Browse Files</span>
              </div>

              <p className="dropzone-formats-badge">
                PDF • PNG • JPG • WEBP
              </p>

              <div className="dropzone-ai-capabilities">
                <span className="capability-pill">⚡ Neural Type Classification</span>
                <span className="capability-pill">💬 Interactive Context Chat</span>
                <span className="capability-pill">🔒 Isolated Session</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Document Loaded: Analysis Card + ChatGPT-Style Conversation */}
      {analyzedDoc && (
        <div className="ai-chat-interface-layout">
          {/* Top Document Summary Card */}
          <div className="ai-summary-card">
            <div className="ai-summary-card-header">
              <div className="ai-doc-info-block">
                <div className="ai-doc-icon-wrap">
                  <FileCheck size={22} />
                </div>
                <div>
                  <div className="ai-doc-name-row">
                    <span className="ai-doc-filename" title={analyzedDoc.filename}>
                      {analyzedDoc.filename}
                    </span>
                    <span className={`ai-confidence-badge ${analyzedDoc.confidence}`}>
                      {analyzedDoc.confidence.toUpperCase()} CONFIDENCE
                    </span>
                  </div>
                  <div className="ai-meta-details">
                    <span>{((analyzedDoc.file_size || 0) / 1024).toFixed(1)} KB</span>
                    <span className="dot-sep">•</span>
                    <span>{analyzedDoc.pages || 1} {analyzedDoc.pages === 1 ? 'Page' : 'Pages'}</span>
                    <span className="dot-sep">•</span>
                    <span>Source: {analyzedDoc.text_source || 'PDF Layer'}</span>
                  </div>
                </div>
              </div>

              <div className="ai-card-actions">
                <button
                  className="btn btn-secondary"
                  onClick={() => fileInputRef.current?.click()}
                  title="Upload a different document"
                >
                  <UploadCloud size={15} />
                  <span>Upload New</span>
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={resetSession}
                  title="Reset session"
                  aria-label="Reset session"
                >
                  <RotateCcw size={15} />
                </button>
              </div>
            </div>

            {/* Document Classification & Reasoning */}
            <div className="ai-classification-panel">
              <div className="ai-type-callout">
                <span className="ai-type-label">DETECTED DOCUMENT TYPE</span>
                <span className="ai-type-value">{analyzedDoc.document_type}</span>
              </div>

              <div className="ai-summary-section">
                <span className="ai-type-label">DOCUMENT SUMMARY</span>
                <p className="ai-summary-body">{analyzedDoc.summary}</p>
              </div>

              {analyzedDoc.reasoning && analyzedDoc.reasoning.length > 0 && (
                <div className="ai-reasoning-section">
                  <span className="ai-type-label">REASONING & EVIDENCE</span>
                  <ul className="ai-reasoning-bullets">
                    {analyzedDoc.reasoning.map((item, idx) => (
                      <li key={idx} className="ai-reasoning-item">
                        <CheckCircle2 size={15} className="ai-reasoning-check" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* ChatGPT-Style Modern Chat View */}
          <div className="chatgpt-chat-card">
            <div className="chatgpt-chat-header">
              <div className="chatgpt-header-title-wrap">
                <div className="chatgpt-bot-avatar">
                  <Bot size={18} />
                </div>
                <div>
                  <h4 className="chatgpt-title">Document Intelligence Assistant</h4>
                  <p className="chatgpt-subtitle">
                    Grounded context strictly anchored to <strong>{analyzedDoc.filename}</strong>
                  </p>
                </div>
              </div>

              {onSwitchToOffline && (
                <button
                  className="btn btn-ghost switch-offline-btn"
                  onClick={onSwitchToOffline}
                >
                  <ShieldCheck size={14} />
                  <span>Offline Mode</span>
                  <ArrowRight size={13} />
                </button>
              )}
            </div>

            {/* Scrollable Message History */}
            <div className="chatgpt-messages-container">
              {messages.map((msg) => (
                <div key={msg.id} className={`chatgpt-bubble-row ${msg.role}`}>
                  <div className={`chatgpt-avatar ${msg.role}`}>
                    {msg.role === 'assistant' ? <Bot size={18} /> : <User size={18} />}
                  </div>

                  <div className="chatgpt-bubble-body">
                    <div className="chatgpt-bubble-meta">
                      <span className="chatgpt-sender-name">
                        {msg.role === 'assistant' ? 'AI Assistant' : 'You'}
                      </span>
                      <span className="chatgpt-timestamp">{msg.timestamp}</span>
                    </div>

                    <div className="chatgpt-bubble-content">
                      {msg.content.split('\n\n').map((paragraph, pIdx) => (
                        <p key={pIdx} className="chatgpt-paragraph">
                          {paragraph}
                        </p>
                      ))}
                    </div>

                    {msg.role === 'assistant' && (
                      <div className="chatgpt-msg-actions">
                        <button
                          className="chatgpt-copy-btn"
                          onClick={() => handleCopyMessage(msg.id, msg.content)}
                          title="Copy answer"
                          aria-label="Copy answer"
                        >
                          {copiedMsgId === msg.id ? (
                            <Check size={13} color="var(--success)" />
                          ) : (
                            <Copy size={13} />
                          )}
                          <span>{copiedMsgId === msg.id ? 'Copied' : 'Copy'}</span>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {isAiThinking && (
                <div className="chatgpt-bubble-row assistant">
                  <div className="chatgpt-avatar assistant">
                    <Bot size={18} />
                  </div>
                  <div className="chatgpt-bubble-body">
                    <div className="chatgpt-bubble-meta">
                      <span className="chatgpt-sender-name">AI Assistant</span>
                    </div>
                    <div className="chatgpt-typing-indicator">
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                      <span className="typing-dot" />
                    </div>
                  </div>
                </div>
              )}

              <div ref={chatBottomRef} />
            </div>

            {/* Quick Suggestions Chips Bar */}
            <div className="chatgpt-suggestions-bar">
              <span className="suggestions-label">
                <HelpCircle size={13} /> Suggested:
              </span>
              <div className="suggestions-scroll">
                {SUGGESTED_QUESTIONS.map((q, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="suggestion-chip-btn"
                    onClick={() => handleSendMessage(q)}
                    disabled={isAiThinking}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>

            {/* Sticky Chat Input Bar */}
            <div className="chatgpt-input-sticky-bar">
              <form
                className="chatgpt-input-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSendMessage();
                }}
              >
                <input
                  type="text"
                  className="chatgpt-input-field"
                  placeholder={`Ask anything about ${analyzedDoc.filename}... (e.g. "What is the employee name?")`}
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  disabled={isAiThinking}
                />
                <button
                  type="submit"
                  className="btn btn-primary chatgpt-send-btn"
                  disabled={!inputQuery.trim() || isAiThinking}
                  title="Send message"
                  aria-label="Send message"
                >
                  <Send size={16} />
                  <span>Send</span>
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
