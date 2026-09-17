import React, { useRef, useEffect, useState } from 'react';
import {
  Bot,
  User,
  Send,
  Copy,
  Check,
  ShieldCheck,
  ArrowRight,
  HelpCircle,
} from 'lucide-react';
import type { ChatMessage, AiAnalysisResult } from '../types';

interface AIChatPanelProps {
  document: AiAnalysisResult;
  messages: ChatMessage[];
  isAiThinking: boolean;
  onSendMessage: (text: string) => void;
  onSwitchToOffline?: () => void;
  onNotify: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const SUGGESTED_PROMPTS = [
  'What is the employee name?',
  'What is the joining date?',
  'What is the salary?',
  'Summarize this document.',
  'What are the important clauses?',
];

export const AIChatPanel: React.FC<AIChatPanelProps> = ({
  document,
  messages,
  isAiThinking,
  onSendMessage,
  onSwitchToOffline,
  onNotify,
}) => {
  const [inputQuery, setInputQuery] = useState('');
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isAiThinking]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const query = inputQuery.trim();
    if (!query || isAiThinking) return;
    onSendMessage(query);
    setInputQuery('');
  };

  const handlePromptClick = (prompt: string) => {
    if (isAiThinking) return;
    onSendMessage(prompt);
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgId(id);
    onNotify('Response copied to clipboard', 'info');
    setTimeout(() => setCopiedMsgId(null), 2000);
  };

  return (
    <div className="ai-chat-assistant-card">
      {/* Header Bar */}
      <div className="ai-chat-header-bar">
        <div className="ai-chat-header-title-box">
          <div className="ai-chat-bot-avatar">
            <Bot size={20} />
          </div>
          <div>
            <div className="ai-chat-title-row">
              <h4 className="ai-chat-title">Document AI Assistant</h4>
              <span className="ai-chat-live-badge">
                <span className="ai-chat-live-dot" />
                <span>Context Loaded</span>
              </span>
            </div>
            <p className="ai-chat-subtitle">
              Answers strictly grounded in <strong>{document.filename}</strong> ({document.document_type})
            </p>
          </div>
        </div>

        {onSwitchToOffline && (
          <button
            type="button"
            className="btn btn-ghost ai-switch-offline-btn"
            onClick={onSwitchToOffline}
            title="Switch back to Offline Mode"
          >
            <ShieldCheck size={14} />
            <span>Offline Mode</span>
            <ArrowRight size={13} />
          </button>
        )}
      </div>

      {/* Messages Scroll Area */}
      <div className="ai-chat-messages-area">
        {messages.map((msg) => {
          const isAssistant = msg.role === 'assistant';
          return (
            <div key={msg.id} className={`ai-chat-message-row ${msg.role}`}>
              <div className={`ai-chat-avatar ${msg.role}`}>
                {isAssistant ? <Bot size={18} /> : <User size={18} />}
              </div>

              <div className="ai-chat-bubble-container">
                <div className="ai-chat-bubble-header">
                  <span className="ai-chat-sender">
                    {isAssistant ? 'Document AI' : 'You'}
                  </span>
                  <span className="ai-chat-timestamp">{msg.timestamp}</span>
                </div>

                <div className={`ai-chat-bubble-body ${msg.role}`}>
                  {msg.content.split('\n\n').map((para, idx) => (
                    <p key={idx} className="ai-chat-paragraph">
                      {para}
                    </p>
                  ))}
                </div>

                {isAssistant && (
                  <div className="ai-chat-bubble-actions">
                    <button
                      type="button"
                      className="ai-chat-action-copy-btn"
                      onClick={() => handleCopy(msg.id, msg.content)}
                      title="Copy response"
                    >
                      {copiedMsgId === msg.id ? (
                        <>
                          <Check size={13} className="text-success" />
                          <span className="text-success">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy size={13} />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* AI Typing Indicator */}
        {isAiThinking && (
          <div className="ai-chat-message-row assistant thinking">
            <div className="ai-chat-avatar assistant">
              <Bot size={18} />
            </div>
            <div className="ai-chat-bubble-container">
              <div className="ai-chat-bubble-header">
                <span className="ai-chat-sender">Document AI</span>
                <span className="ai-chat-typing-label">Analyzing context...</span>
              </div>
              <div className="ai-chat-typing-dots">
                <span className="dot dot-1" />
                <span className="dot dot-2" />
                <span className="dot dot-3" />
              </div>
            </div>
          </div>
        )}

        <div ref={chatBottomRef} />
      </div>

      {/* Suggested Prompts Strip */}
      <div className="ai-chat-suggested-strip">
        <div className="ai-suggested-label">
          <HelpCircle size={13} />
          <span>Suggested:</span>
        </div>
        <div className="ai-suggested-scroll">
          {SUGGESTED_PROMPTS.map((prompt, idx) => (
            <button
              key={idx}
              type="button"
              className="ai-suggested-chip"
              onClick={() => handlePromptClick(prompt)}
              disabled={isAiThinking}
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Sticky Bottom Message Input Form */}
      <div className="ai-chat-input-sticky">
        <form className="ai-chat-form" onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            type="text"
            className="ai-chat-input"
            placeholder={`Ask any question about ${document.filename}... (e.g. "What is the employee name?")`}
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            disabled={isAiThinking}
          />
          <button
            type="submit"
            className="btn btn-primary ai-chat-send-btn"
            disabled={!inputQuery.trim() || isAiThinking}
            title="Send inquiry"
          >
            <Send size={15} />
            <span>Send</span>
          </button>
        </form>
        <div className="ai-chat-input-hint">
          <span>Press Enter ↵ to send • Grounded strictly on uploaded document context</span>
        </div>
      </div>
    </div>
  );
};
