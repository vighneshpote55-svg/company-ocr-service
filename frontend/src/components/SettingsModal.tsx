import React, { useState, useEffect } from 'react';
import {
  Settings,
  X,
  Check,
  Globe,
  Shield,
  Lock,
  Key,
  RefreshCw,
  Server,
  Fingerprint,
  UserCheck,
  ShieldAlert,
  Sparkles,
  Bot,
  Cpu,
} from 'lucide-react';
import { api, normalizeOpenRouterConfig } from '../services/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onSaved }) => {
  const currentConfig = api.getConfig();
  const [baseUrl, setBaseUrl] = useState(currentConfig.baseUrl);
  const [clientId, setClientId] = useState(currentConfig.clientId || '');
  const [clientSecret, setClientSecret] = useState(currentConfig.clientSecret || '');
  const [bearerToken, setBearerToken] = useState(currentConfig.token || '');
  const [apiKey, setApiKey] = useState(currentConfig.apiKey || '');
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [connectionLatency, setConnectionLatency] = useState<number | null>(null);

  // AI Model Configuration State
  const [aiProvider, setAiProvider] = useState<'local' | 'external'>('local');
  const [externalProviderName, setExternalProviderName] = useState('openrouter');
  const [aiModel, setAiModel] = useState('qwen2.5vl:3b');
  const [aiApiKey, setAiApiKey] = useState('');
  const [aiBaseUrl, setAiBaseUrl] = useState('');
  const [isAiKeyConfigured, setIsAiKeyConfigured] = useState(false);
  const [isTestingAi, setIsTestingAi] = useState(false);
  const [aiTestResult, setAiTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Sync state with api config whenever modal opens
  useEffect(() => {
    if (isOpen) {
      const cfg = api.getConfig();
      setBaseUrl(cfg.baseUrl);
      setClientId(cfg.clientId || '');
      setClientSecret(cfg.clientSecret || '');
      setBearerToken(cfg.token || '');
      setApiKey(cfg.apiKey || '');
      setTestResult(null);

      // Load AI Model Configuration from backend
      api.getAiConfig()
        .then((aiCfg) => {
          const isExt = aiCfg.mode === 'external';
          setAiProvider(isExt ? 'external' : 'local');
          const prov = aiCfg.active_provider !== 'ollama' && aiCfg.active_provider !== 'local' ? aiCfg.active_provider : 'openrouter';
          setExternalProviderName(prov);
          const norm = normalizeOpenRouterConfig(prov, aiCfg.active_model, aiCfg.base_url);
          setAiModel(norm.model || (isExt ? 'nvidia/nemotron-3-ultra-550b-a55b:free' : 'qwen2.5vl:3b'));
          setAiBaseUrl(norm.baseUrl || (isExt ? 'https://openrouter.ai/api/v1' : ''));
          setIsAiKeyConfigured(Boolean(aiCfg.api_key_configured));
          setAiApiKey('');
          setAiTestResult(null);
        })
        .catch(() => {
          setAiProvider('local');
          setAiModel('qwen2.5vl:3b');
        });
    }
  }, [isOpen]);

  // Handle ESC key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    const start = performance.now();
    try {
      api.updateConfig({ baseUrl, token: bearerToken || undefined, apiKey: apiKey || undefined });
      const health = await api.checkHealth();
      const latency = Math.round(performance.now() - start);
      setConnectionLatency(latency);
      setTestResult({
        ok: true,
        message: `Connected successfully (${latency}ms latency) • FastAPI Service v${health.version || '1.0.0'}`,
      });
    } catch (err: any) {
      setTestResult({
        ok: false,
        message: `Connection failed: ${err.message || 'Cannot reach FastAPI backend.'}`,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleMintToken = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      api.updateConfig({ baseUrl });
      const token = await api.mintToken(clientId, clientSecret);
      setBearerToken(token);
      setTestResult({
        ok: true,
        message: 'Successfully minted and saved JWT access token!',
      });
    } catch (err: any) {
      setTestResult({
        ok: false,
        message: `Failed to mint token: ${err.message}`,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleTestAiConnection = async () => {
    setIsTestingAi(true);
    setAiTestResult(null);
    try {
      const norm = normalizeOpenRouterConfig(externalProviderName, aiModel, aiBaseUrl);
      const candidate = {
        provider: aiProvider === 'local' ? 'local' : (norm.provider || externalProviderName),
        model: aiProvider === 'local' ? 'qwen2.5vl:3b' : (norm.model || aiModel),
        api_key: aiApiKey || undefined,
        base_url: aiProvider === 'local' ? undefined : (norm.baseUrl || aiBaseUrl || undefined),
      };
      const res = await api.testAiConnection(candidate);
      setAiTestResult({
        ok: res.success,
        message: res.message,
      });
      if (aiProvider === 'external') {
        if (norm.baseUrl && norm.baseUrl !== aiBaseUrl) setAiBaseUrl(norm.baseUrl);
        if (norm.model && norm.model !== aiModel) setAiModel(norm.model);
      }
    } catch (err: any) {
      setAiTestResult({
        ok: false,
        message: `Connection failed: ${err.message || 'Error reaching provider.'}`,
      });
    } finally {
      setIsTestingAi(false);
    }
  };

  const handleSave = async () => {
    api.updateConfig({
      baseUrl,
      clientId,
      clientSecret,
      token: bearerToken || undefined,
      apiKey: apiKey || undefined,
    });

    try {
      if (aiProvider === 'local') {
        await api.updateAiConfig({
          provider: 'local',
          model: 'qwen2.5vl:3b',
        });
      } else {
        const norm = normalizeOpenRouterConfig(externalProviderName, aiModel, aiBaseUrl);
        await api.updateAiConfig({
          provider: norm.provider || externalProviderName,
          model: norm.model || aiModel,
          api_key: aiApiKey || undefined,
          base_url: norm.baseUrl || aiBaseUrl || undefined,
        });
      }
    } catch (err: any) {
      console.error('Failed to update AI config on backend:', err);
    }

    await onSaved();
    onClose();
  };

  return (
    <div className="settings-page-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="settings-panel-container"
        onClick={(e) => e.stopPropagation()}
        tabIndex={-1}
      >
        {/* Header: Gear icon, Title, Subtitle, Circular Close Button */}
        <div className="settings-panel-header">
          <div className="settings-header-left">
            <div className="settings-gear-circle">
              <Settings size={22} className="settings-gear-icon" />
            </div>
            <div className="settings-title-wrap">
              <h2 className="settings-main-title">API Connection & Auth Settings</h2>
              <p className="settings-main-subtitle">
                Configure your API endpoint and authentication credentials to connect with the AI service.
              </p>
            </div>
          </div>

          <button
            className="settings-close-circle-btn"
            onClick={onClose}
            title="Close settings"
            aria-label="Close settings dialog"
          >
            <X size={18} />
          </button>
        </div>

        {/* 4 Status Cards */}
        <div className="settings-status-cards-grid">
          {/* 1. API Connection */}
          <div className="settings-status-card">
            <div className="status-card-top">
              <div className="status-icon-wrap icon-blue">
                <Server size={18} />
              </div>
              <span className="status-pill-badge badge-green">
                {connectionLatency ? `${connectionLatency}ms` : 'Connected'}
              </span>
            </div>
            <div className="status-card-title">API Connection</div>
            <p className="status-card-desc">FastAPI Backend live pipeline</p>
          </div>

          {/* 2. Authentication */}
          <div className="settings-status-card">
            <div className="status-card-top">
              <div className="status-icon-wrap icon-purple">
                <Fingerprint size={18} />
              </div>
              <span className="status-pill-badge badge-green">OAuth2 / JWT</span>
            </div>
            <div className="status-card-title">Authentication</div>
            <p className="status-card-desc">Dynamic token & secret auth</p>
          </div>

          {/* 3. Client Access */}
          <div className="settings-status-card">
            <div className="status-card-top">
              <div className="status-icon-wrap icon-green">
                <UserCheck size={18} />
              </div>
              <span className="status-pill-badge badge-green">Ready</span>
            </div>
            <div className="status-card-title">Client Access</div>
            <p className="status-card-desc">Client credential grant flow</p>
          </div>

          {/* 4. Access Control */}
          <div className="settings-status-card">
            <div className="status-card-top">
              <div className="status-icon-wrap icon-amber">
                <ShieldAlert size={18} />
              </div>
              <span className="status-pill-badge badge-green">Active</span>
            </div>
            <div className="status-card-title">Access Control</div>
            <p className="status-card-desc">Zero-trust credential guard</p>
          </div>
        </div>

        {/* Settings Body Form */}
        <div className="settings-panel-body">
          {/* Section 1: FastAPI Base URL */}
          <div className="settings-form-section">
            <label className="settings-input-label" htmlFor="fastapi-base-url">
              FastAPI Base URL
            </label>
            <div className="settings-input-wrapper">
              <div className="settings-input-left-icon" aria-hidden="true">
                <Globe size={18} />
              </div>
              <input
                id="fastapi-base-url"
                type="text"
                className="settings-input-field"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:8000"
              />
            </div>
            <span className="settings-field-hint">
              Target endpoint for local neural OCR processing and AI document extraction services.
            </span>
          </div>

          {/* Section 2: Client Credentials (Client ID & Client Secret) */}
          <div className="settings-form-section">
            <div className="settings-section-title-row">
              <div className="settings-section-heading">Client Credentials Flow</div>
              <span className="settings-endpoint-pill">POST /auth/token</span>
            </div>

            <div className="settings-two-col-grid">
              <div className="settings-field-col">
                <label className="settings-input-label" htmlFor="client-id-input">
                  Client ID
                </label>
                <div className="settings-input-wrapper">
                  <div className="settings-input-left-icon" aria-hidden="true">
                    <Shield size={18} />
                  </div>
                  <input
                    id="client-id-input"
                    type="text"
                    className="settings-input-field"
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder="Enter registered Client ID"
                  />
                </div>
              </div>

              <div className="settings-field-col">
                <label className="settings-input-label" htmlFor="client-secret-input">
                  Client Secret
                </label>
                <div className="settings-input-wrapper">
                  <div className="settings-input-left-icon" aria-hidden="true">
                    <Lock size={18} />
                  </div>
                  <input
                    id="client-secret-input"
                    type="password"
                    className="settings-input-field"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    placeholder="••••••••••••••••"
                  />
                </div>
              </div>
            </div>

            <div className="settings-mint-action-row">
              <button
                type="button"
                className="btn btn-secondary settings-mint-btn"
                onClick={handleMintToken}
                disabled={isTesting || !clientId || !clientSecret}
              >
                <Sparkles size={15} />
                <span>Mint JWT Access Token</span>
              </button>
              <span className="settings-field-hint-inline">
                Exchanges client credentials for a signed HMAC-SHA256 JWT bearer token.
              </span>
            </div>
          </div>

          {/* Section 3: Direct Bearer Token & Static X-API-Key */}
          <div className="settings-form-section">
            <div className="settings-two-col-grid">
              <div className="settings-field-col">
                <label className="settings-input-label" htmlFor="bearer-token-input">
                  Direct Bearer Token (Optional)
                </label>
                <div className="settings-input-wrapper">
                  <div className="settings-input-left-icon" aria-hidden="true">
                    <Key size={18} />
                  </div>
                  <input
                    id="bearer-token-input"
                    type="password"
                    className="settings-input-field"
                    value={bearerToken}
                    onChange={(e) => setBearerToken(e.target.value)}
                    placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                  />
                </div>
              </div>

              <div className="settings-field-col">
                <label className="settings-input-label" htmlFor="api-key-input">
                  Static X-API-Key (Optional)
                </label>
                <div className="settings-input-wrapper">
                  <div className="settings-input-left-icon" aria-hidden="true">
                    <Key size={18} />
                  </div>
                  <input
                    id="api-key-input"
                    type="password"
                    className="settings-input-field"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Static enterprise header key"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Section 4: AI Model Configuration */}
          <div className="settings-form-section">
            <div className="settings-section-title-row">
              <div className="settings-section-heading">AI Model Configuration</div>
              <span className="settings-endpoint-pill">AI Mode Engine</span>
            </div>

            <div className="settings-two-col-grid">
              <div className="settings-field-col">
                <label className="settings-input-label" htmlFor="ai-provider-select">
                  Provider
                </label>
                <div className="settings-input-wrapper">
                  <div className="settings-input-left-icon" aria-hidden="true">
                    <Bot size={18} />
                  </div>
                  <select
                    id="ai-provider-select"
                    className="settings-input-field"
                    value={aiProvider}
                    onChange={(e) => {
                      const val = e.target.value as 'local' | 'external';
                      setAiProvider(val);
                      if (val === 'local') {
                        setAiModel('qwen2.5vl:3b');
                      } else {
                        if (!aiModel || aiModel === 'qwen2.5vl:3b') {
                          setAiModel('nvidia/nemotron-3-ultra-550b-a55b:free');
                        }
                        if (!aiBaseUrl) {
                          setAiBaseUrl('https://openrouter.ai/api/v1');
                        }
                      }
                    }}
                  >
                    <option value="local">Local Ollama (Offline / Private)</option>
                    <option value="external">External Provider (OpenRouter / OpenAI / Custom)</option>
                  </select>
                </div>
                <span className="settings-field-hint">
                  {aiProvider === 'local'
                    ? 'Runs locally via Ollama. No external API key required; inference stays private.'
                    : 'Routes AI Mode analysis to an external cloud or custom OpenAI-compatible endpoint.'}
                </span>
              </div>

              {aiProvider === 'external' ? (
                <div className="settings-field-col">
                  <label className="settings-input-label" htmlFor="external-provider-select">
                    External Service
                  </label>
                  <div className="settings-input-wrapper">
                    <div className="settings-input-left-icon" aria-hidden="true">
                      <Globe size={18} />
                    </div>
                    <select
                      id="external-provider-select"
                      className="settings-input-field"
                      value={externalProviderName}
                      onChange={(e) => {
                        const prov = e.target.value;
                        setExternalProviderName(prov);
                        if (prov === 'openrouter') {
                          setAiModel('nvidia/nemotron-3-ultra-550b-a55b:free');
                          setAiBaseUrl('https://openrouter.ai/api/v1');
                        } else if (prov === 'openai') {
                          setAiModel('gpt-4o-mini');
                          setAiBaseUrl('https://api.openai.com/v1');
                        }
                      }}
                    >
                      <option value="openrouter">OpenRouter</option>
                      <option value="openai">OpenAI</option>
                      <option value="custom">Custom OpenAI-Compatible</option>
                    </select>
                  </div>
                  <span className="settings-field-hint">
                    Select OpenRouter, OpenAI, or a custom API gateway.
                  </span>
                </div>
              ) : (
                <div className="settings-field-col">
                  <label className="settings-input-label" htmlFor="ai-model-input">
                    Model
                  </label>
                  <div className="settings-input-wrapper">
                    <div className="settings-input-left-icon" aria-hidden="true">
                      <Cpu size={18} />
                    </div>
                    <input
                      id="ai-model-input"
                      type="text"
                      className="settings-input-field"
                      value="qwen2.5vl:3b"
                      disabled
                    />
                  </div>
                  <span className="settings-field-hint">
                    Default vision model: qwen2.5vl:3b (mandatory local fallback).
                  </span>
                </div>
              )}
            </div>

            {/* External Provider Configuration */}
            {aiProvider === 'external' && (
              <>
                <div className="settings-two-col-grid" style={{ marginTop: '16px' }}>
                  <div className="settings-field-col">
                    <label className="settings-input-label" htmlFor="ai-model-input-ext">
                      Model ID
                    </label>
                    <div className="settings-input-wrapper">
                      <div className="settings-input-left-icon" aria-hidden="true">
                        <Cpu size={18} />
                      </div>
                      <input
                        id="ai-model-input-ext"
                        type="text"
                        className="settings-input-field"
                        value={aiModel}
                        onChange={(e) => setAiModel(e.target.value)}
                        placeholder="nvidia/nemotron-3-ultra-550b-a55b:free"
                      />
                    </div>
                    <span className="settings-field-hint">
                      Model identifier (e.g. nvidia/nemotron-3-ultra-550b-a55b:free).
                    </span>
                  </div>

                  <div className="settings-field-col">
                    <label className="settings-input-label" htmlFor="ai-base-url-input">
                      Base URL
                    </label>
                    <div className="settings-input-wrapper">
                      <div className="settings-input-left-icon" aria-hidden="true">
                        <Globe size={18} />
                      </div>
                      <input
                        id="ai-base-url-input"
                        type="text"
                        className="settings-input-field"
                        value={aiBaseUrl}
                        onChange={(e) => setAiBaseUrl(e.target.value)}
                        placeholder="https://openrouter.ai/api/v1"
                      />
                    </div>
                    <span className="settings-field-hint">
                      API endpoint (e.g. https://openrouter.ai/api/v1).
                    </span>
                  </div>
                </div>

                <div className="settings-two-col-grid" style={{ marginTop: '16px' }}>
                  <div className="settings-field-col">
                    <label className="settings-input-label" htmlFor="ai-api-key-input">
                      API Key
                    </label>
                    <div className="settings-input-wrapper">
                      <div className="settings-input-left-icon" aria-hidden="true">
                        <Key size={18} />
                      </div>
                      <input
                        id="ai-api-key-input"
                        type="password"
                        className="settings-input-field"
                        value={aiApiKey}
                        onChange={(e) => setAiApiKey(e.target.value)}
                        placeholder={isAiKeyConfigured ? '•••••••••••••••• (Configured)' : 'Enter external provider API key'}
                      />
                    </div>
                    <span className="settings-field-hint">
                      API keys are stored exclusively in backend memory and never in browser storage.
                    </span>
                  </div>
                </div>

                {externalProviderName === 'openrouter' && (
                  <div
                    style={{
                      marginTop: '14px',
                      padding: '12px 16px',
                      background: '#f8fafc',
                      borderRadius: '8px',
                      border: '1px solid #cbd5e1',
                      fontSize: '12.5px',
                      lineHeight: '1.6',
                    }}
                  >
                    <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: '4px' }}>
                      OpenRouter Recommended Configuration:
                    </div>
                    <div style={{ color: '#475569' }}>
                      • <strong>Provider:</strong> OpenRouter<br />
                      • <strong>Model:</strong> <code>nvidia/nemotron-3-ultra-550b-a55b:free</code><br />
                      • <strong>Base URL:</strong> <code>https://openrouter.ai/api/v1</code>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* AI Test Connection Action */}
            <div className="settings-mint-action-row" style={{ marginTop: '16px' }}>
              <button
                type="button"
                className="btn btn-secondary settings-mint-btn"
                onClick={handleTestAiConnection}
                disabled={isTestingAi}
              >
                <RefreshCw size={15} className={isTestingAi ? 'spin-anim' : ''} />
                <span>{isTestingAi ? 'Testing AI Connection...' : 'Test AI Connection'}</span>
              </button>
              <span className="settings-field-hint-inline">
                {aiProvider === 'local'
                  ? 'Verifies local Ollama server connectivity and Qwen2.5-VL model availability.'
                  : 'Pings the external provider endpoint to verify API key and model availability.'}
              </span>
            </div>

            {/* AI Connection Test Banner */}
            {aiTestResult && (
              <div
                className={`settings-feedback-banner ${aiTestResult.ok ? 'feedback-success' : 'feedback-error'}`}
                role="alert"
                style={{ marginTop: '14px' }}
              >
                <div className="feedback-icon">
                  {aiTestResult.ok ? <Check size={18} /> : <X size={18} />}
                </div>
                <div className="feedback-message">{aiTestResult.message}</div>
              </div>
            )}
          </div>

          {/* Test Status Banner */}
          {testResult && (
            <div
              className={`settings-feedback-banner ${testResult.ok ? 'feedback-success' : 'feedback-error'}`}
              role="alert"
            >
              <div className="feedback-icon">
                {testResult.ok ? <Check size={18} /> : <X size={18} />}
              </div>
              <div className="feedback-message">{testResult.message}</div>
            </div>
          )}
        </div>

        {/* Footer Buttons: Left Test Ping, Right Save Configuration */}
        <div className="settings-panel-footer">
          <button
            type="button"
            className="btn btn-secondary settings-test-btn"
            onClick={handleTestConnection}
            disabled={isTesting}
          >
            <RefreshCw size={15} className={isTesting ? 'spin-anim' : ''} />
            <span>{isTesting ? 'Pinging Endpoint...' : 'Test Connection'}</span>
          </button>

          <button
            type="button"
            className="btn btn-primary settings-save-btn"
            onClick={handleSave}
          >
            <Check size={16} />
            <span>Save Configuration</span>
          </button>
        </div>
      </div>
    </div>
  );
};
