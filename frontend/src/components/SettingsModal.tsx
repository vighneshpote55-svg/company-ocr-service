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
  Sparkles,
  Bot,
  Cpu,
  User,
  KeyRound,
  LogOut,
  CheckCircle2,
  AlertCircle,
  Sliders,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { api, normalizeOpenRouterConfig } from '../services/api';
import { useAuth } from '../context/AuthContext';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void | Promise<void>;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose, onSaved }) => {
  const { user, role, updateProfile, updatePassword, signOutAllSessions } = useAuth();
  const isAdmin = role === 'admin';
  const currentConfig = api.getConfig();
  const [baseUrl, setBaseUrl] = useState(currentConfig.baseUrl);
  const [clientId, setClientId] = useState(currentConfig.clientId || '');
  const [clientSecret, setClientSecret] = useState(currentConfig.clientSecret || '');
  const [bearerToken, setBearerToken] = useState(currentConfig.token || '');
  const [apiKey, setApiKey] = useState(currentConfig.apiKey || '');
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [connectionLatency, setConnectionLatency] = useState<number | null>(null);

  // Tab State: 'ai' vs 'account'
  const [settingsTab, setSettingsTab] = useState<'ai' | 'account'>('ai');

  // Advanced / Administrator Settings Accordion State
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);

  // Account Management State
  const [fullNameInput, setFullNameInput] = useState(user?.full_name || '');
  const [isUpdatingName, setIsUpdatingName] = useState(false);
  const [nameStatus, setNameStatus] = useState<{ ok: boolean; message: string } | null>(null);

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isUpdatingPassword, setIsUpdatingPassword] = useState(false);
  const [passwordStatus, setPasswordStatus] = useState<{ ok: boolean; message: string } | null>(null);

  const [isSigningOutAll, setIsSigningOutAll] = useState(false);
  const [signOutAllStatus, setSignOutAllStatus] = useState<{ ok: boolean; message: string } | null>(null);

  // AI Model Configuration State
  const [activeAiConfig, setActiveAiConfig] = useState<any>(null);
  const [selectedProvider, setSelectedProvider] = useState<'local' | 'openai' | 'openrouter' | 'custom'>('local');
  const [aiModel, setAiModel] = useState('qwen2.5vl:3b');
  const [aiApiKey, setAiApiKey] = useState('');
  const [aiBaseUrl, setAiBaseUrl] = useState('');
  const [isAiKeyConfigured, setIsAiKeyConfigured] = useState(false);
  const [isTestingAi, setIsTestingAi] = useState(false);
  const [aiTestResult, setAiTestResult] = useState<{ ok: boolean; isWarning?: boolean; message: string } | null>(null);

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
          setActiveAiConfig(aiCfg);
          const p = (aiCfg.active_provider || 'local').toLowerCase().trim();
          if (p === 'ollama' || p === 'local') {
            setSelectedProvider('local');
            setAiModel(aiCfg.active_model || 'qwen2.5vl:3b');
            setAiBaseUrl('');
          } else if (p === 'openai') {
            setSelectedProvider('openai');
            setAiModel(aiCfg.active_model || 'gpt-4o-mini');
            setAiBaseUrl(aiCfg.base_url || 'https://api.openai.com/v1');
          } else if (p === 'openrouter' || p === 'open_router') {
            setSelectedProvider('openrouter');
            const norm = normalizeOpenRouterConfig('openrouter', aiCfg.active_model, aiCfg.base_url);
            setAiModel(norm.model || 'google/gemini-2.5-flash');
            setAiBaseUrl(norm.baseUrl || 'https://openrouter.ai/api/v1');
          } else {
            setSelectedProvider('custom');
            setAiModel(aiCfg.active_model || '');
            setAiBaseUrl(aiCfg.base_url || '');
          }
          setIsAiKeyConfigured(Boolean(aiCfg.api_key_configured));
          setAiApiKey('');
          setAiTestResult(null);
        })
        .catch(() => {
          setSelectedProvider('local');
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
    if (!isAdmin) {
      setTestResult({
        ok: false,
        message: 'Connection test unavailable — administrator permission required.',
      });
      return;
    }
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
      const errMsg = err?.message || '';
      const isPerm =
        errMsg.toLowerCase().includes('permission') ||
        errMsg.toLowerCase().includes('forbidden') ||
        errMsg.toLowerCase().includes('403') ||
        errMsg.toLowerCase().includes('administrator');

      if (isPerm) {
        setTestResult({
          ok: false,
          message: 'Connection test unavailable — administrator permission required.',
        });
      } else {
        setTestResult({
          ok: false,
          message: `Connection failed: ${errMsg || 'Cannot reach FastAPI backend.'}`,
        });
      }
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
      const targetModel = selectedProvider === 'local'
        ? 'qwen2.5vl:3b'
        : (aiModel || (selectedProvider === 'openai' ? 'gpt-4o-mini' : 'google/gemini-2.5-flash'));
      const targetBaseUrl = selectedProvider === 'local'
        ? undefined
        : (aiBaseUrl || (selectedProvider === 'openai' ? 'https://api.openai.com/v1' : (selectedProvider === 'openrouter' ? 'https://openrouter.ai/api/v1' : undefined)));

      const norm = selectedProvider === 'openrouter'
        ? normalizeOpenRouterConfig('openrouter', targetModel, targetBaseUrl)
        : null;

      const candidate = {
        provider: selectedProvider,
        model: norm?.model || targetModel,
        api_key: aiApiKey || undefined,
        base_url: norm?.baseUrl || targetBaseUrl,
      };

      const res = await api.testAiConnection(candidate);
      if (res.latency_ms) {
        setConnectionLatency(res.latency_ms);
      }
      setAiTestResult({
        ok: res.success,
        isWarning: false,
        message: res.message,
      });
      if (selectedProvider === 'openrouter' && norm) {
        if (norm.baseUrl && norm.baseUrl !== aiBaseUrl) setAiBaseUrl(norm.baseUrl);
        if (norm.model && norm.model !== aiModel) setAiModel(norm.model);
      }
    } catch (err: any) {
      const errMsg = err?.message || '';
      const isPerm =
        errMsg.toLowerCase().includes('permission') ||
        errMsg.toLowerCase().includes('forbidden') ||
        errMsg.toLowerCase().includes('403') ||
        errMsg.toLowerCase().includes('administrator');

      if (isPerm) {
        setAiTestResult({
          ok: false,
          isWarning: true,
          message: 'Connection test unavailable — administrator permission required.',
        });
      } else {
        setAiTestResult({
          ok: false,
          isWarning: false,
          message: `Connection test failed: ${errMsg || 'Error reaching provider.'}`,
        });
      }
    } finally {
      setIsTestingAi(false);
    }
  };

  const handleUpdateName = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullNameInput.trim()) return;
    setIsUpdatingName(true);
    setNameStatus(null);
    const res = await updateProfile(fullNameInput.trim());
    setIsUpdatingName(false);
    if (res.error) {
      setNameStatus({ ok: false, message: res.error });
    } else {
      setNameStatus({ ok: true, message: 'Profile name updated successfully!' });
    }
  };

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 6) {
      setPasswordStatus({ ok: false, message: 'Password must be at least 6 characters long.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordStatus({ ok: false, message: 'Passwords do not match.' });
      return;
    }
    setIsUpdatingPassword(true);
    setPasswordStatus(null);
    const res = await updatePassword(newPassword);
    setIsUpdatingPassword(false);
    if (res.error) {
      setPasswordStatus({ ok: false, message: res.error });
    } else {
      setPasswordStatus({ ok: true, message: 'Password updated successfully!' });
      setNewPassword('');
      setConfirmPassword('');
    }
  };

  const handleSignOutAll = async () => {
    if (!window.confirm('Are you sure you want to sign out of all active devices and sessions?')) return;
    setIsSigningOutAll(true);
    setSignOutAllStatus(null);
    const res = await signOutAllSessions();
    setIsSigningOutAll(false);
    if (res.error) {
      setSignOutAllStatus({ ok: false, message: res.error });
    } else {
      onClose();
      window.location.href = '/login';
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
      if (selectedProvider === 'local') {
        const updated = await api.updateAiConfig({
          provider: 'local',
          model: 'qwen2.5vl:3b',
        });
        if (updated) {
          setActiveAiConfig(updated);
          setIsAiKeyConfigured(Boolean(updated.api_key_configured));
        }
      } else {
        const targetModel = aiModel || (selectedProvider === 'openai' ? 'gpt-4o-mini' : 'google/gemini-2.5-flash');
        const targetBaseUrl = aiBaseUrl || (selectedProvider === 'openai' ? 'https://api.openai.com/v1' : (selectedProvider === 'openrouter' ? 'https://openrouter.ai/api/v1' : undefined));
        const norm = selectedProvider === 'openrouter'
          ? normalizeOpenRouterConfig('openrouter', targetModel, targetBaseUrl)
          : null;

        const updated = await api.updateAiConfig({
          provider: selectedProvider,
          model: norm?.model || targetModel,
          api_key: aiApiKey || undefined,
          base_url: norm?.baseUrl || targetBaseUrl,
        });
        if (updated) {
          setActiveAiConfig(updated);
          setIsAiKeyConfigured(Boolean(updated.api_key_configured));
        }
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
              <h2 className="settings-main-title">Settings & AI Configuration</h2>
              <p className="settings-main-subtitle">
                Configure AI reasoning models, system preferences, and account security.
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

        {/* Settings Tab Selector */}
        <div className="settings-nav-tabs">
          <button
            type="button"
            className={`settings-nav-tab-btn ${settingsTab === 'ai' ? 'active' : ''}`}
            onClick={() => setSettingsTab('ai')}
          >
            <Sparkles size={16} />
            <span>AI Configuration</span>
            <span className={`settings-role-tag ${isAdmin ? 'admin' : 'user'}`}>
              {isAdmin ? 'Admin' : 'User'}
            </span>
          </button>

          <button
            type="button"
            className={`settings-nav-tab-btn ${settingsTab === 'account' ? 'active' : ''}`}
            onClick={() => setSettingsTab('account')}
          >
            <User size={16} />
            <span>Account & Security</span>
          </button>
        </div>

        {settingsTab === 'ai' ? (
          <>
            <div className="settings-panel-body">
              {/* 1. Live AI Status Banner */}
              <div className="settings-live-status-banner">
                <div className="status-banner-main">
                  <div className="status-pulse-indicator">
                    <span className={`status-pulse-dot ${selectedProvider !== 'local' ? 'dot-purple' : 'dot-green'}`} />
                    <Bot size={20} className="status-bot-icon" />
                  </div>
                  <div className="status-banner-meta">
                    <div className="status-banner-title-row">
                      <span className="status-engine-name">
                        {selectedProvider === 'local' && 'Local Ollama Engine'}
                        {selectedProvider === 'openai' && 'OpenAI Cloud AI'}
                        {selectedProvider === 'openrouter' && 'OpenRouter Cloud AI'}
                        {selectedProvider === 'custom' && 'Custom AI Gateway'}
                      </span>
                      <span className="status-model-chip">
                        {selectedProvider === 'local'
                          ? 'qwen2.5vl:3b'
                          : (aiModel || (selectedProvider === 'openai' ? 'gpt-4o-mini' : 'google/gemini-2.5-flash'))}
                      </span>
                      <span
                        className={`status-connection-badge ${
                          aiTestResult
                            ? aiTestResult.ok
                              ? 'badge-connected'
                              : aiTestResult.isWarning
                              ? 'badge-idle'
                              : 'badge-failed'
                            : selectedProvider === 'local'
                            ? 'badge-connected'
                            : activeAiConfig?.provider === selectedProvider && isAiKeyConfigured
                            ? 'badge-connected'
                            : 'badge-idle'
                        }`}
                      >
                        {aiTestResult
                          ? aiTestResult.ok
                            ? 'Connected'
                            : aiTestResult.isWarning
                            ? 'Protected'
                            : 'Connection test failed'
                          : selectedProvider === 'local'
                          ? 'Connected'
                          : activeAiConfig?.provider === selectedProvider && isAiKeyConfigured
                          ? 'Connected'
                          : 'Not Tested'}
                      </span>
                    </div>
                    <div className="status-banner-subtext">
                      {selectedProvider === 'local' && `Private air-gapped inference active on this device (offline & secure).${connectionLatency ? ` • ${connectionLatency}ms` : ''}`}
                      {selectedProvider === 'openai' && `Direct OpenAI API integration • ${isAiKeyConfigured || aiApiKey ? 'API Key Configured' : 'API Key Required'}${connectionLatency ? ` • ${connectionLatency}ms latency` : ''}`}
                      {selectedProvider === 'openrouter' && `OpenRouter model gateway • ${isAiKeyConfigured || aiApiKey ? 'API Key Configured' : 'API Key Required'}${connectionLatency ? ` • ${connectionLatency}ms latency` : ''}`}
                      {selectedProvider === 'custom' && `OpenAI-compatible endpoint • ${aiBaseUrl || 'Custom Base URL'}${connectionLatency ? ` • ${connectionLatency}ms latency` : ''}`}
                    </div>
                  </div>
                </div>

                <div className="status-banner-actions">
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm test-connection-pill-btn"
                    onClick={handleTestAiConnection}
                    disabled={isTestingAi}
                    title="Test AI Model connectivity"
                  >
                    <RefreshCw size={13} className={isTestingAi ? 'spin-anim' : ''} />
                    <span>{isTestingAi ? 'Testing...' : 'Test AI Connection'}</span>
                  </button>
                </div>
              </div>

              {/* AI Test Status Banner */}
              {aiTestResult && (
                <div
                  className={`settings-feedback-banner ${
                    aiTestResult.ok
                      ? 'feedback-success'
                      : aiTestResult.isWarning
                      ? 'feedback-warning'
                      : 'feedback-error'
                  }`}
                  role="alert"
                >
                  <div className="feedback-icon">
                    {aiTestResult.ok ? (
                      <CheckCircle2 size={16} />
                    ) : aiTestResult.isWarning ? (
                      <Lock size={16} />
                    ) : (
                      <AlertCircle size={16} />
                    )}
                  </div>
                  <div className="feedback-message">{aiTestResult.message}</div>
                </div>
              )}

              {/* 2. Primary Section: AI Model Configuration */}
              <div className="settings-form-section primary-ai-section">
                <div className="settings-section-title-row">
                  <div>
                    <h3 className="settings-section-heading">AI Model Configuration</h3>
                    <p className="settings-section-subheading">
                      Primary reasoning model for document extraction and contextual analysis.
                    </p>
                  </div>
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
                        value={selectedProvider}
                        onChange={(e) => {
                          const val = e.target.value as 'local' | 'openai' | 'openrouter' | 'custom';
                          setSelectedProvider(val);
                          setAiTestResult(null);
                          if (val === 'local') {
                            setAiModel('qwen2.5vl:3b');
                            setAiBaseUrl('');
                          } else if (val === 'openai') {
                            if (!aiModel || aiModel === 'qwen2.5vl:3b' || aiModel.includes('/')) {
                              setAiModel('gpt-4o-mini');
                            }
                            setAiBaseUrl('https://api.openai.com/v1');
                          } else if (val === 'openrouter') {
                            if (!aiModel || aiModel === 'qwen2.5vl:3b' || !aiModel.includes('/')) {
                              setAiModel('google/gemini-2.5-flash');
                            }
                            setAiBaseUrl('https://openrouter.ai/api/v1');
                          } else if (val === 'custom') {
                            if (aiModel === 'qwen2.5vl:3b') {
                              setAiModel('');
                            }
                          }
                        }}
                      >
                        <option value="local">Local Ollama (Offline / Private)</option>
                        <optgroup label="External Provider (OpenRouter / OpenAI / Custom)">
                          <option value="openai">OpenAI</option>
                          <option value="openrouter">OpenRouter</option>
                          <option value="custom">Custom / OpenAI-compatible API</option>
                        </optgroup>
                      </select>
                    </div>
                    <span className="settings-field-hint">
                      {selectedProvider === 'local' && 'Private air-gapped inference on this device.'}
                      {selectedProvider === 'openai' && 'Direct OpenAI cloud inference with GPT-4o models.'}
                      {selectedProvider === 'openrouter' && 'Unified API routing to 200+ frontier models.'}
                      {selectedProvider === 'custom' && 'Connect to any OpenAI-compatible inference endpoint.'}
                    </span>
                  </div>

                  {selectedProvider === 'local' ? (
                    <div className="settings-field-col">
                      <label className="settings-input-label" htmlFor="ai-model-input">
                        Model <span className="settings-badge-read-only">Deterministic</span>
                      </label>
                      <div className="settings-input-wrapper is-read-only">
                        <div className="settings-input-left-icon" aria-hidden="true">
                          <Cpu size={18} />
                        </div>
                        <input
                          id="ai-model-input"
                          type="text"
                          className="settings-input-field"
                          value="qwen2.5vl:3b"
                          disabled
                          readOnly
                        />
                      </div>
                      <span className="settings-field-hint">
                        Active vision engine: Qwen2.5-VL 3B (local inference).
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
                          value={aiModel}
                          onChange={(e) => setAiModel(e.target.value)}
                          placeholder={
                            selectedProvider === 'openai'
                              ? 'gpt-4o-mini'
                              : selectedProvider === 'openrouter'
                              ? 'google/gemini-2.5-flash'
                              : 'e.g. llama-3.2-11b-vision or custom-model'
                          }
                        />
                      </div>
                      {selectedProvider === 'openai' && (
                        <div className="settings-suggestion-chips">
                          <span className="suggestion-label">Suggestions:</span>
                          {['gpt-4o-mini', 'gpt-4o', 'o3-mini'].map((m) => (
                            <button
                              key={m}
                              type="button"
                              className={`suggestion-chip ${aiModel === m ? 'active' : ''}`}
                              onClick={() => setAiModel(m)}
                            >
                              {m}
                            </button>
                          ))}
                        </div>
                      )}
                      {selectedProvider === 'openrouter' && (
                        <div className="settings-suggestion-chips">
                          <span className="suggestion-label">Suggestions:</span>
                          {[
                            { label: 'Gemini 2.5 Flash', id: 'google/gemini-2.5-flash' },
                            { label: 'Nemotron 550B', id: 'nvidia/nemotron-3-ultra-550b-a55b:free' },
                            { label: 'Llama 3.3 70B', id: 'meta-llama/llama-3.3-70b-instruct:free' },
                          ].map((item) => (
                            <button
                              key={item.id}
                              type="button"
                              className={`suggestion-chip ${aiModel === item.id ? 'active' : ''}`}
                              onClick={() => setAiModel(item.id)}
                            >
                              {item.label}
                            </button>
                          ))}
                        </div>
                      )}
                      {selectedProvider === 'custom' && (
                        <span className="settings-field-hint">
                          Model ID matching your external OpenAI-compatible service.
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* External Provider Detailed Inputs (Row 2) */}
                {selectedProvider !== 'local' && (
                  <div className="external-provider-fields" style={{ marginTop: '1rem' }}>
                    <div className="settings-two-col-grid">
                      <div className="settings-field-col">
                        <label className="settings-input-label" htmlFor="ai-base-url-input">
                          {selectedProvider === 'openai'
                            ? 'Base URL (Optional)'
                            : selectedProvider === 'custom'
                            ? 'Base URL (Required)'
                            : 'Endpoint Base URL'}
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
                            placeholder={
                              selectedProvider === 'openai'
                                ? 'https://api.openai.com/v1 (Default)'
                                : selectedProvider === 'openrouter'
                                ? 'https://openrouter.ai/api/v1'
                                : 'e.g. http://localhost:8000/v1'
                            }
                          />
                        </div>
                        <span className="settings-field-hint">
                          {selectedProvider === 'openai' && 'Defaults to official OpenAI endpoint.'}
                          {selectedProvider === 'openrouter' && 'OpenRouter API endpoint.'}
                          {selectedProvider === 'custom' && 'Root URL to the /v1 endpoint of your model service.'}
                        </span>
                      </div>

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
                            placeholder={
                              isAiKeyConfigured
                                ? '•••••••••••••••• (Configured in Memory)'
                                : selectedProvider === 'openai'
                                ? 'Enter OpenAI API Key (sk-...)'
                                : selectedProvider === 'openrouter'
                                ? 'Enter OpenRouter API Key (sk-or-...)'
                                : 'Enter API Key (optional if unauthenticated)'
                            }
                          />
                        </div>
                        <span className="settings-field-hint">
                          API keys are encrypted in backend storage and never exposed or logged.
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* 3. Collapsible Accordion: Advanced / Administrator Settings */}
              <div className="settings-advanced-accordion">
                <button
                  type="button"
                  className="settings-advanced-toggle"
                  onClick={() => setIsAdvancedOpen(!isAdvancedOpen)}
                  aria-expanded={isAdvancedOpen}
                >
                  <div className="advanced-toggle-left">
                    <Sliders size={16} className="advanced-icon" />
                    <div className="advanced-title-group">
                      <span className="advanced-title">Advanced / Administrator Settings</span>
                      <span className="advanced-subtext">FastAPI endpoint, client credentials & access tokens</span>
                    </div>
                  </div>
                  <div className="advanced-toggle-right">
                    <span className="settings-role-tag admin">Admin</span>
                    {isAdvancedOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </div>
                </button>

                {isAdvancedOpen && (
                  <div className="settings-advanced-content">
                    {/* Backend Base URL */}
                    <div className="settings-field-group">
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
                          disabled={!isAdmin}
                          onChange={(e) => setBaseUrl(e.target.value)}
                          placeholder="http://localhost:8000"
                        />
                      </div>
                      <span className="settings-field-hint">
                        Target endpoint for backend OCR and AI services.
                      </span>
                    </div>

                    {/* Client Credentials */}
                    <div className="settings-two-col-grid" style={{ marginTop: '1rem' }}>
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
                            disabled={!isAdmin}
                            onChange={(e) => setClientId(e.target.value)}
                            placeholder="Client ID"
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
                            disabled={!isAdmin}
                            onChange={(e) => setClientSecret(e.target.value)}
                            placeholder="••••••••••••••••"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="settings-mint-action-row" style={{ marginTop: '0.85rem' }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={handleMintToken}
                        disabled={isTesting || !clientId || !clientSecret || !isAdmin}
                      >
                        <Sparkles size={14} />
                        <span>Mint JWT Access Token</span>
                      </button>
                      <span className="settings-field-hint-inline">
                        Exchanges client credentials for a signed HMAC-SHA256 JWT bearer token.
                      </span>
                    </div>

                    {/* Direct Bearer Token & Static X-API-Key */}
                    <div className="settings-two-col-grid" style={{ marginTop: '1rem' }}>
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
                            disabled={!isAdmin}
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
                            disabled={!isAdmin}
                            onChange={(e) => setApiKey(e.target.value)}
                            placeholder="Static header key"
                          />
                        </div>
                      </div>
                    </div>

                    {/* Backend Endpoint Ping */}
                    <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={handleTestConnection}
                        disabled={isTesting}
                      >
                        <RefreshCw size={13} className={isTesting ? 'spin-anim' : ''} />
                        <span>{isTesting ? 'Pinging Endpoint...' : 'Ping Backend Endpoint'}</span>
                      </button>
                      {testResult && (
                        <span style={{ fontSize: '0.8rem', color: testResult.ok ? 'var(--success)' : 'var(--danger)', fontWeight: 500 }}>
                          {testResult.message}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Footer Buttons */}
            <div className="settings-panel-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
              >
                <span>Cancel</span>
              </button>

              <button
                type="button"
                className="btn btn-primary settings-save-btn"
                onClick={handleSave}
              >
                <Check size={16} />
                <span>Save Changes</span>
              </button>
            </div>
          </>
        ) : (
      /* Account & Security Tab */
      <div className="settings-account-panel">
        {/* Profile Details Card */}
        <div className="settings-card-container">
          <div className="settings-card-header">
            <div className="settings-card-icon-wrap icon-blue">
              <User size={18} />
            </div>
            <div>
              <h3 className="settings-card-title">Profile Information</h3>
              <p className="settings-card-subtitle">Your personal account credentials and role</p>
            </div>
          </div>

          <div className="settings-card-body">
            <div className="settings-account-grid">
              <div className="settings-account-info-box">
                <span className="settings-info-label">Email Address</span>
                <span className="settings-info-value">{user?.email || 'N/A'}</span>
              </div>

              <div className="settings-account-info-box">
                <span className="settings-info-label">Current Role</span>
                <div>
                  <span className={`settings-role-tag ${role}`}>
                    {role === 'admin' ? 'Administrator' : 'Standard User'}
                  </span>
                </div>
              </div>
            </div>

            <form onSubmit={handleUpdateName} className="settings-account-form" style={{ marginTop: '1.25rem' }}>
              <label className="settings-input-label" htmlFor="settings-full-name">
                Full Name
              </label>
              <div className="settings-input-action-row">
                <input
                  id="settings-full-name"
                  type="text"
                  className="settings-input-field"
                  value={fullNameInput}
                  onChange={(e) => setFullNameInput(e.target.value)}
                  placeholder="Enter your full name"
                />
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isUpdatingName || !fullNameInput.trim()}
                >
                  <span>{isUpdatingName ? 'Saving...' : 'Save Name'}</span>
                </button>
              </div>

              {nameStatus && (
                <div className={`settings-inline-alert ${nameStatus.ok ? 'alert-success' : 'alert-error'}`}>
                  {nameStatus.ok ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                  <span>{nameStatus.message}</span>
                </div>
              )}
            </form>
          </div>
        </div>

        {/* Change Password Card */}
        <div className="settings-card-container">
          <div className="settings-card-header">
            <div className="settings-card-icon-wrap icon-purple">
              <KeyRound size={18} />
            </div>
            <div>
              <h3 className="settings-card-title">Change Password</h3>
              <p className="settings-card-subtitle">Update your password to keep your account secure</p>
            </div>
          </div>

          <div className="settings-card-body">
            <form onSubmit={handleUpdatePassword} className="settings-account-form">
              <div className="settings-two-col-grid">
                <div className="settings-field-col">
                  <label className="settings-input-label" htmlFor="settings-new-password">
                    New Password
                  </label>
                  <input
                    id="settings-new-password"
                    type="password"
                    className="settings-input-field"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="At least 6 characters"
                  />
                </div>

                <div className="settings-field-col">
                  <label className="settings-input-label" htmlFor="settings-confirm-password">
                    Confirm New Password
                  </label>
                  <input
                    id="settings-confirm-password"
                    type="password"
                    className="settings-input-field"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat new password"
                  />
                </div>
              </div>

              <div style={{ marginTop: '1rem' }}>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isUpdatingPassword || !newPassword}
                >
                  <span>{isUpdatingPassword ? 'Updating...' : 'Update Password'}</span>
                </button>
              </div>

              {passwordStatus && (
                <div className={`settings-inline-alert ${passwordStatus.ok ? 'alert-success' : 'alert-error'}`}>
                  {passwordStatus.ok ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                  <span>{passwordStatus.message}</span>
                </div>
              )}
            </form>
          </div>
        </div>

        {/* Session Revocation Card */}
        <div className="settings-card-container">
          <div className="settings-card-header">
            <div className="settings-card-icon-wrap icon-amber">
              <LogOut size={18} />
            </div>
            <div>
              <h3 className="settings-card-title">Session Management</h3>
              <p className="settings-card-subtitle">Revoke all active tokens across mobile and other browsers</p>
            </div>
          </div>

          <div className="settings-card-body">
            <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', margin: '0 0 1rem', lineHeight: '1.5' }}>
              Lost a device or signed in from a shared computer? Clicking below immediately revokes all refresh tokens, terminating active sessions everywhere.
            </p>

            <button
              type="button"
              className="btn btn-danger"
              onClick={handleSignOutAll}
              disabled={isSigningOutAll}
            >
              <LogOut size={15} />
              <span>{isSigningOutAll ? 'Revoking Sessions...' : 'Sign Out of All Devices'}</span>
            </button>

            {signOutAllStatus && (
              <div className="settings-inline-alert alert-error" style={{ marginTop: '0.75rem' }}>
                <AlertCircle size={14} />
                <span>{signOutAllStatus.message}</span>
              </div>
            )}
          </div>
        </div>

        {/* Account Tab Footer */}
        <div className="settings-panel-footer">
          <div></div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
          >
            <span>Close</span>
          </button>
        </div>
      </div>
    )}

      </div>
    </div>
  );
};
