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
  'What is the salary?',
  'Who is the employer?',
  'Summarize this document.',
  'What documents or information are mentioned?',
  'Does this document contain an expiry date?',
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

  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Check AI status on mount
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

    // Reset old document context and start fresh AI session
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
        // Initial welcoming message from AI
        setMessages([
          {
            id: 'init-msg',
            role: 'assistant',
            content: `I have analyzed **${result.filename}** and identified it as **${result.document_type}** (${result.confidence} confidence).\n\n${result.summary}\n\nYou can now ask me any questions about this document below!`,
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
      // Build history for multi-turn context
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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const resetSession = () => {
    if (window.confirm('Clear the current document and start a new AI session?')) {
      setAnalyzedDoc(null);
      setMessages([]);
      setInputQuery('');
    }
  };

  return (
    <div className="ai-mode-container">
      {/* AI Configuration Banner if API key not detected */}
      {aiConfigured === false && (
        <div className="ai-config-warning-banner">
          <AlertCircle size={20} color="var(--accent-amber)" />
          <div style={{ flex: 1 }}>
            <strong>AI Provider Notice:</strong> No <code>AI_API_KEY</code> detected in environment.
            Please set <code>AI_API_KEY</code> in your <code>.env</code> file (or configure OpenRouter / OpenAI / Gemini).
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

      {/* Upload Dropzone (shown if no document is loaded or if uploading) */}
      {!analyzedDoc && (
        <div className="upload-card ai-upload-card">
          <div className="upload-header">
            <div className="ai-mode-badge-pill">
              <Sparkles size={16} />
              <span>AI Mode Document Intelligence</span>
            </div>
            <h2 className="upload-title" style={{ marginTop: '0.6rem' }}>
              Upload Any Document for AI Analysis
            </h2>
            <p className="upload-subtitle">
              Upload documents not included in the predefined Offline Mode list (e.g. employment contracts, non-disclosure agreements, offer letters, notices). The AI will detect the document type, explain its contents, and answer questions.
            </p>
          </div>

          {isProcessing ? (
            <ProcessingTimeline progress={progress} />
          ) : (
            <div
              className={`dropzone ${dragActive ? 'drag-active' : ''}`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="dropzone-icon" style={{ background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(6, 182, 212, 0.2))' }}>
                <UploadCloud size={32} color="var(--accent-cyan)" />
              </div>
              <div className="dropzone-text" style={{ fontSize: '1.05rem', fontWeight: 600 }}>
                Click to browse or drag & drop any document here
              </div>
              <div className="dropzone-subtext">
                Employment Contracts, NDAs, Invoices, Agreements, Leases, or Custom Certificates (PDF, PNG, JPG up to 25MB)
              </div>
              <div className="file-types-badge-row">
                <span className="file-badge">⚡ Auto Document Type Classification</span>
                <span className="file-badge">💬 Interactive Chat Context</span>
                <span className="file-badge">🔒 Isolated Session</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Document Loaded View: Analysis Card + Chat Interface */}
      {analyzedDoc && (
        <div className="ai-session-layout">
          {/* Top Document Summary & Analysis Card */}
          <div className="ai-doc-card">
            <div className="ai-doc-card-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: 0 }}>
                <div className="ai-doc-icon">
                  <FileCheck size={24} color="var(--accent-cyan)" />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
                    <span className="ai-filename" title={analyzedDoc.filename}>
                      {analyzedDoc.filename}
                    </span>
                    <span className={`ai-confidence-badge ${analyzedDoc.confidence}`}>
                      {analyzedDoc.confidence.toUpperCase()} CONFIDENCE
                    </span>
                  </div>
                  <div className="ai-meta-row">
                    <span>{((analyzedDoc.file_size || 0) / 1024).toFixed(1)} KB</span>
                    <span>•</span>
                    <span>{analyzedDoc.pages || 1} {analyzedDoc.pages === 1 ? 'Page' : 'Pages'}</span>
                    <span>•</span>
                    <span>Source: {analyzedDoc.text_source || 'PDF Layer'}</span>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => fileInputRef.current?.click()}
                  title="Upload a different document"
                  style={{ padding: '0.45rem 0.85rem' }}
                >
                  <UploadCloud size={15} />
                  <span>Upload New Document</span>
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={resetSession}
                  title="Reset session"
                  style={{ padding: '0.45rem 0.75rem' }}
                >
                  <RotateCcw size={15} />
                </button>
              </div>
            </div>

            {/* Classification & Reasoning Section */}
            <div className="ai-classification-box">
              <div className="ai-classification-item">
                <div className="ai-label">DETECTED DOCUMENT TYPE</div>
                <div className="ai-detected-type">{analyzedDoc.document_type}</div>
              </div>

              <div className="ai-classification-item" style={{ marginTop: '0.75rem' }}>
                <div className="ai-label">AI EXPLANATION</div>
                <p className="ai-summary-text">{analyzedDoc.summary}</p>
              </div>

              {analyzedDoc.reasoning && analyzedDoc.reasoning.length > 0 && (
                <div className="ai-classification-item" style={{ marginTop: '0.75rem' }}>
                  <div className="ai-label">KEY EVIDENCE & REASONING</div>
                  <ul className="ai-reasoning-list">
                    {analyzedDoc.reasoning.map((point, idx) => (
                      <li key={idx}>
                        <CheckCircle2 size={14} color="var(--accent-emerald)" style={{ marginTop: '2px', flexShrink: 0 }} />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Chat Interface */}
          <div className="ai-chat-card">
            <div className="ai-chat-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <Bot size={20} color="var(--primary)" />
                <div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 600, margin: 0 }}>Document Assistant Chat</h3>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Context grounded strictly in <strong>{analyzedDoc.filename}</strong>
                  </div>
                </div>
              </div>

              {onSwitchToOffline && (
                <button
                  className="btn btn-ghost"
                  onClick={onSwitchToOffline}
                  style={{ fontSize: '0.78rem' }}
                >
                  Switch to Offline Mode →
                </button>
              )}
            </div>

            {/* Chat Message Stream */}
            <div className="ai-chat-messages">
              {messages.map((msg) => (
                <div key={msg.id} className={`chat-bubble-row ${msg.role}`}>
                  <div className="chat-avatar">
                    {msg.role === 'assistant' ? <Bot size={18} /> : <User size={18} />}
                  </div>
                  <div className="chat-bubble-content">
                    <div className="chat-bubble-meta">
                      <span className="chat-sender">{msg.role === 'assistant' ? 'AI Assistant' : 'You'}</span>
                      <span className="chat-time">{msg.timestamp}</span>
                    </div>
                    <div className="chat-bubble-text">
                      {msg.content.split('\n\n').map((para, i) => (
                        <p key={i} style={{ marginBottom: i < msg.content.split('\n\n').length - 1 ? '0.6rem' : 0 }}>
                          {para}
                        </p>
                      ))}
                    </div>
                  </div>
                </div>
              ))}

              {isAiThinking && (
                <div className="chat-bubble-row assistant">
                  <div className="chat-avatar">
                    <Bot size={18} />
                  </div>
                  <div className="chat-bubble-content">
                    <div className="chat-bubble-meta">
                      <span className="chat-sender">AI Assistant</span>
                    </div>
                    <div className="chat-typing-indicator">
                      <span className="dot" />
                      <span className="dot" />
                      <span className="dot" />
                    </div>
                  </div>
                </div>
              )}

              <div ref={chatBottomRef} />
            </div>

            {/* Quick Suggestion Chips */}
            <div className="ai-suggestion-chips-bar">
              <span style={{ fontSize: '0.75rem', color: 'var(--text-subtle)', marginRight: '0.4rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <HelpCircle size={13} /> Suggested:
              </span>
              {SUGGESTED_QUESTIONS.map((q, idx) => (
                <button
                  key={idx}
                  className="suggestion-chip"
                  onClick={() => handleSendMessage(q)}
                  disabled={isAiThinking}
                >
                  {q}
                </button>
              ))}
            </div>

            {/* Chat Input Bar */}
            <div className="ai-chat-input-bar">
              <input
                type="text"
                className="ai-chat-input"
                placeholder={`Ask anything about ${analyzedDoc.filename}... (e.g. "What is the joining date?")`}
                value={inputQuery}
                onChange={(e) => setInputQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isAiThinking}
              />
              <button
                className="btn btn-primary ai-send-btn"
                onClick={() => handleSendMessage()}
                disabled={!inputQuery.trim() || isAiThinking}
              >
                <Send size={16} />
                <span>Send</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
