import React, { useState, useRef, useEffect } from 'react';
import {
  Sparkles,
  Send,
  RotateCcw,
  Check,
  Copy,
  FolderOpen,
  RefreshCw,
  MoreHorizontal,
  X,
  Paperclip,
  FileText,
  Code,
  Plus,
  ThumbsUp,
  ThumbsDown,
} from 'lucide-react';
import type { ChatMessage, AiAnalysisResult } from '../types';

interface AIChatPanelProps {
  document: AiAnalysisResult;
  documentId?: string;
  filename?: string;
  verification_status?: string;
  messages: ChatMessage[];
  isAiThinking: boolean;
  onSendMessage: (text: string) => void;
  onSwitchToOffline?: () => void;
  onNotify: (message: string, type?: 'success' | 'error' | 'info') => void;
  providerLabel?: string;
  onResetMessages?: () => void;
  onRetryLast?: (query?: string) => void;
  onReconnectContext?: () => void;
  onOpenVault?: () => void;
}

const getSuggestedPrompts = (documentType: string): string[] => {
  const docType = (documentType || '').toLowerCase();
  if (docType.includes('gst') || docType.includes('registration certificate')) {
    return [
      'What is the GSTIN?',
      'What is the legal business name?',
      'What is the trade name?',
      'What is the constitution of business?',
      'What is the principal place of business?',
    ];
  }
  if (docType.includes('pan')) {
    return [
      'What is the PAN number?',
      'Whose name is on the PAN card?',
      'What is the father\'s name?',
      'What is the date of birth?',
    ];
  }
  if (docType.includes('security') || docType.includes('report') || docType.includes('compliance')) {
    return [
      'What are the primary recommendations for optimizing cloud infrastructure security?',
      'What is the compliance status for SOC 2 Type II?',
      'Are there any critical vulnerability findings?',
    ];
  }
  return [
    'Summarize this document.',
    'Extract all key entities.',
    'List all dates in this document.',
    'What is the purpose of this document?',
  ];
};

// Helper to extract citation references from assistant content or metadata
const extractCitations = (content: string, explicitCitations?: string[]): string[] => {
  if (explicitCitations && explicitCitations.length > 0) {
    return explicitCitations;
  }
  const citations = new Set<string>();
  // Match bracketed page citations e.g. [Page 1], [Page 2, Sec 4], [Source: Page 1]
  const bracketMatches = content.match(/\[(?:Source:\s*)?(Page\s*\d+[^\]]*)\]/gi);
  if (bracketMatches) {
    bracketMatches.forEach((m) => {
      const cleaned = m.replace(/[\[\]]/g, '').trim();
      citations.add(cleaned.startsWith('Page') ? cleaned : `Source: ${cleaned}`);
    });
  }
  // Also match inline "Page X" if no brackets found
  if (citations.size === 0) {
    const pageMatches = content.match(/\bPage\s+\d+\b/gi);
    if (pageMatches) {
      pageMatches.forEach((m) => citations.add(m.trim()));
    }
  }
  return Array.from(citations);
};

export const AIChatPanel: React.FC<AIChatPanelProps> = ({
  document,
  documentId,
  filename,
  verification_status,
  messages,
  isAiThinking,
  onSendMessage,
  onSwitchToOffline,
  onNotify,
  providerLabel: _providerLabel,
  onResetMessages,
  onRetryLast,
  onReconnectContext,
  onOpenVault,
}) => {
  const activeDocId = documentId || document.document_id || document.id || '';
  const activeFilename = filename || document.filename || 'document';
  const activeStatus = verification_status || document.verification_status || 'verified';
  const [inputQuery, setInputQuery] = useState('');
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [thumbsFeedback, setThumbsFeedback] = useState<Record<string, 'up' | 'down'>>({});
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const prevDocIdRef = useRef<string>(activeDocId);
  const lastUserQueryRef = useRef<string>('');

  // Reset chat messages whenever documentId changes
  useEffect(() => {
    if (prevDocIdRef.current !== activeDocId) {
      console.log(`[AIChatPanel] documentId changed from "${prevDocIdRef.current}" to "${activeDocId}". Resetting chat messages.`);
      prevDocIdRef.current = activeDocId;
      setInputQuery('');
      if (onResetMessages) {
        onResetMessages();
      }
    }
  }, [activeDocId, onResetMessages]);

  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isAiThinking]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = inputQuery.trim();
    if (!query || isAiThinking) return;

    if (!activeDocId) {
      console.warn('[AIChatPanel] Outgoing chat blocked: documentId is missing or empty.');
      onNotify('No active document selected for chat.', 'error');
      return;
    }

    lastUserQueryRef.current = query;
    console.log('[AIChatPanel] Outgoing chat request with documentId:', activeDocId, 'query:', query);
    onSendMessage(query);
    setInputQuery('');
  };

  const handlePromptClick = (prompt: string) => {
    if (isAiThinking) return;

    if (!activeDocId) {
      console.warn('[AIChatPanel] Outgoing prompt click blocked: documentId is missing or empty.');
      onNotify('No active document selected for chat.', 'error');
      return;
    }

    lastUserQueryRef.current = prompt;
    console.log('[AIChatPanel] Outgoing prompt click with documentId:', activeDocId, 'prompt:', prompt);
    onSendMessage(prompt);
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgId(id);
    onNotify('Response copied to clipboard', 'info');
    setTimeout(() => setCopiedMsgId(null), 2000);
  };

  const toggleThumbs = (id: string, type: 'up' | 'down') => {
    setThumbsFeedback((prev) => ({
      ...prev,
      [id]: prev[id] === type ? undefined! : type,
    }));
  };

  return (
    <div className="docpilot-chat-panel" aria-label="Document AI Assistant">
      {/* 1. Header Bar: Document Intelligence + Action Icons (⟲, ..., ✕) */}
      <div className="docpilot-chat-header">
        <div className="docpilot-chat-title-group">
          <h3 className="docpilot-chat-main-title">Document Intelligence</h3>
          <div className="docpilot-grounded-indicator">
            <span>Grounded in <strong>{activeFilename}</strong></span>
            {activeStatus ? <span className="docpilot-verif-tag">{`Status: ${activeStatus}`}</span> : null}
          </div>
        </div>

        <div className="docpilot-chat-header-actions">
          {onResetMessages && (
            <button
              type="button"
              className="docpilot-icon-action-btn"
              onClick={onResetMessages}
              title="Reset conversation"
            >
              <RotateCcw size={15} />
            </button>
          )}

          <button
            type="button"
            className="docpilot-icon-action-btn"
            title="Conversation Options"
          >
            <MoreHorizontal size={16} />
          </button>

          {onSwitchToOffline && (
            <button
              type="button"
              className="docpilot-icon-action-btn"
              onClick={onSwitchToOffline}
              title="Close panel / Switch to Offline"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* 2. Chat Messages Area */}
      <div className="docpilot-chat-scroll-area">
        {messages.length === 0 ? (
          /* Welcome Card for current active document */
          <div className="docpilot-assistant-card welcome-card">
            <div className="docpilot-assistant-header">
              <div className="docpilot-assistant-badge-icon">
                <Sparkles size={16} color="#00C2FF" />
              </div>
              <span className="docpilot-assistant-name">DocPilot AI Assistant</span>
            </div>
            <div className="docpilot-assistant-body">
              <p className="docpilot-assistant-paragraph">
                Ready to analyze <strong>{activeFilename}</strong>. Ask any question about figures, dates, parties, or provisions. Every answer includes specific page references.
              </p>
            </div>
          </div>
        ) : null}

        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isErrorMsg = !isUser && (msg.content.includes('⚠️') || msg.content.includes('not found') || msg.content.includes('Error'));
          const feedback = thumbsFeedback[msg.id];
          const citationsList = extractCitations(msg.content, msg.citations);

          return (
            <div key={msg.id} className={`docpilot-msg-container ${isUser ? 'user-container' : 'assistant-container'}`}>
              {isUser ? (
                /* User Message Bubble: Sleek dark with glowing cyan border */
                <div className="docpilot-user-bubble-wrap">
                  <div className="docpilot-user-bubble">
                    <p className="docpilot-user-text">{msg.content}</p>
                    <span className="docpilot-msg-timestamp">{msg.timestamp || '3:38 AM'}</span>
                  </div>
                </div>
              ) : (
                /* Assistant Message Card: DocPilot Assistant with citations and feedback */
                <div className="docpilot-assistant-card">
                  {/* Assistant Identity Header */}
                  <div className="docpilot-assistant-header">
                    <div className="docpilot-assistant-badge-icon">
                      <svg width="18" height="18" viewBox="0 0 32 32" fill="none">
                        <path d="M6 24L16 6L26 24L16 19L6 24Z" fill="url(#aiBotGrad)" stroke="#38BDF8" strokeWidth="1.5" />
                        <circle cx="16" cy="14" r="3" fill="#FFFFFF" />
                        <defs>
                          <linearGradient id="aiBotGrad" x1="6" y1="6" x2="26" y2="24" gradientUnits="userSpaceOnUse">
                            <stop stopColor="#00C2FF" />
                            <stop offset="1" stopColor="#0284C7" />
                          </linearGradient>
                        </defs>
                      </svg>
                    </div>
                    <span className="docpilot-assistant-name">DocPilot Assistant</span>
                  </div>

                  {/* Message Content */}
                  <div className={`docpilot-assistant-body ${isErrorMsg ? 'error-body' : ''}`}>
                    {msg.content.split('\n\n').map((para, pIdx) => (
                      <p key={pIdx} className="docpilot-assistant-paragraph">
                        {para}
                      </p>
                    ))}

                    {/* Citations Sub-card */}
                    {!isErrorMsg && citationsList.length > 0 && (
                      <div className="docpilot-citations-card">
                        <div className="docpilot-citations-title">Page Citations</div>
                        <div className="docpilot-citations-pills">
                          {citationsList.map((cite, cIdx) => (
                            <span key={cIdx} className="docpilot-citation-chip">
                              {cite}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Error Recovery Buttons if Error Occurs */}
                    {isErrorMsg && (
                      <div className="docpilot-chat-recovery-bar">
                        <button
                          type="button"
                          className="btn btn-secondary docpilot-recovery-btn"
                          onClick={() => {
                            const query = lastUserQueryRef.current || 'Summarize this document.';
                            if (onRetryLast) {
                              onRetryLast(query);
                            } else {
                              onSendMessage(query);
                            }
                          }}
                          title="Retry query"
                        >
                          <RotateCcw size={12} />
                          <span>Retry</span>
                        </button>

                        <button
                          type="button"
                          className="btn btn-secondary docpilot-recovery-btn"
                          onClick={() => {
                            if (onReconnectContext) {
                              onReconnectContext();
                            } else {
                              onNotify('Document context reconnected. Try your query again.', 'info');
                            }
                          }}
                          title="Reconnect document context"
                        >
                          <RefreshCw size={12} />
                          <span>Reconnect Context</span>
                        </button>

                        {onOpenVault && (
                          <button
                            type="button"
                            className="btn btn-secondary docpilot-recovery-btn"
                            onClick={onOpenVault}
                            title="Open Document Vault"
                          >
                            <FolderOpen size={12} />
                            <span>Open Vault</span>
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Feedback Footer: Thumbs up/down + Copy */}
                  {!isErrorMsg && (
                    <div className="docpilot-assistant-footer">
                      <button
                        type="button"
                        className={`docpilot-feedback-btn ${feedback === 'up' ? 'active' : ''}`}
                        onClick={() => toggleThumbs(msg.id, 'up')}
                        title="Good response"
                      >
                        <ThumbsUp size={13} />
                      </button>

                      <button
                        type="button"
                        className={`docpilot-feedback-btn ${feedback === 'down' ? 'active' : ''}`}
                        onClick={() => toggleThumbs(msg.id, 'down')}
                        title="Needs improvement"
                      >
                        <ThumbsDown size={13} />
                      </button>

                      <button
                        type="button"
                        className="docpilot-feedback-btn"
                        onClick={() => handleCopy(msg.id, msg.content)}
                        title="Copy text"
                      >
                        {copiedMsgId === msg.id ? <Check size={13} color="#10B981" /> : <Copy size={13} />}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {/* AI Typing Indicator */}
        {isAiThinking && (
          <div className="docpilot-assistant-card thinking-card">
            <div className="docpilot-assistant-header">
              <div className="docpilot-assistant-badge-icon">
                <Sparkles size={16} color="#00C2FF" />
              </div>
              <span className="docpilot-assistant-name">DocPilot Assistant</span>
            </div>
            <div className="docpilot-typing-indicator">
              <span className="dot dot-1" />
              <span className="dot dot-2" />
              <span className="dot dot-3" />
            </div>
          </div>
        )}

        <div ref={chatBottomRef} />
      </div>

      {/* 3. Suggested Prompt Chips */}
      <div className="docpilot-chat-suggested-row">
        {getSuggestedPrompts(document.document_type).slice(0, 2).map((prompt, idx) => (
          <button
            key={idx}
            type="button"
            className="docpilot-suggested-pill"
            onClick={() => handlePromptClick(prompt)}
            disabled={isAiThinking}
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* 4. Sticky Bottom Message Input Form */}
      <div className="docpilot-chat-input-container">
        <form className="docpilot-chat-form" onSubmit={handleSubmit}>
          {/* Left Tool Icons */}
          <div className="docpilot-input-left-tools">
            <button type="button" className="docpilot-tool-icon-btn" title="Attach file">
              <Paperclip size={15} />
            </button>
            <button type="button" className="docpilot-tool-icon-btn" title="Reference document">
              <FileText size={15} />
            </button>
          </div>

          {/* Text Input */}
          <input
            ref={inputRef}
            type="text"
            className="docpilot-chat-text-input"
            placeholder={`Ask any question about ${activeFilename}...`}
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            disabled={isAiThinking}
          />

          {/* Right Tool Icons & Send Button */}
          <div className="docpilot-input-right-tools">
            <button type="button" className="docpilot-tool-icon-btn" title="Insert code">
              <Code size={15} />
            </button>
            <button type="button" className="docpilot-tool-icon-btn" title="Add context">
              <Plus size={15} />
            </button>

            <button
              type="submit"
              className="docpilot-chat-send-pill"
              disabled={!inputQuery.trim() || isAiThinking}
              title="Send inquiry"
            >
              <Send size={14} />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
