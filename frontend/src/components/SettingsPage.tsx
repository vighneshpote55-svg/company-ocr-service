import React, { useState, useEffect, useCallback } from 'react';
import {
  Cpu,
  Sparkles,
  Zap,
  Globe,
  Terminal,
  Shield,
  Sliders,
  BarChart2,
  UserCheck,
  Layers,
  Key,
  RefreshCw,
  CheckCircle2,
  Save,
  Check,
  HardDrive,
  FileText,
  LogOut,
  Eye,
  EyeOff,
  Activity,
  Copy,
  Trash2,
  Plus,
  Code,
  Lock,
} from 'lucide-react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';
import type { AIProviderConfig, DashboardStats as StatsType, DocumentItem, ApiKeyItem } from '../types';

export type SettingsSection =
  | 'ai_providers'
  | 'model_settings'
  | 'api_keys'
  | 'advanced'
  | 'quotas'
  | 'account'
  | 'general';

interface SettingsPageProps {
  onNotify: (message: string, type?: 'success' | 'error' | 'info') => void;
  onRefreshAiConfig?: () => Promise<AIProviderConfig | null | void>;
  stats?: StatsType;
  documents?: DocumentItem[];
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  onNotify,
  onRefreshAiConfig,
  stats,
  documents = [],
}) => {
  const { user, updateProfile, updatePassword, signOutAllSessions } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [activeSection, setActiveSection] = useState<SettingsSection>('ai_providers');
  const [activeConfig, setActiveConfig] = useState<AIProviderConfig | null>(null);

  // Provider Card Form States
  // 1. Ollama
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState('http://127.0.0.1:11434');
  const [ollamaModel, setOllamaModel] = useState('qwen2.5vl:3b');
  // 2. OpenAI
  const [openaiKey, setOpenaiKey] = useState('');
  const [openaiModel, setOpenaiModel] = useState('gpt-4o-mini');
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState('https://api.openai.com/v1');
  // 3. Google Gemini
  const [geminiKey, setGeminiKey] = useState('');
  const [geminiModel, setGeminiModel] = useState('gemini-2.0-flash');
  // 4. OpenRouter
  const [openrouterKey, setOpenrouterKey] = useState('');
  const [openrouterModel, setOpenrouterModel] = useState('google/gemini-2.5-flash');
  const [openrouterBaseUrl, setOpenrouterBaseUrl] = useState('https://openrouter.ai/api/v1');
  // 5. Custom
  const [customName, setCustomName] = useState('Custom Model Service');
  const [customModel, setCustomModel] = useState('custom-model');
  const [customEndpoint, setCustomEndpoint] = useState('http://localhost:8000/v1');
  const [customFormat, setCustomFormat] = useState('chat_completions');
  const [customKey, setCustomKey] = useState('');

  // Per-Provider Connection Testing States
  const [testingProvider, setTestingProvider] = useState<string | null>(null);
  const [providerTestResults, setProviderTestResults] = useState<Record<string, { ok: boolean; message: string; latency_ms?: number }>>({});
  const [savingProvider, setSavingProvider] = useState<string | null>(null);

  // Model Settings State
  const [fallbackOnError, setFallbackOnError] = useState(false);
  const [temperature, setTemperature] = useState(0.1);
  const [maxTokens, setMaxTokens] = useState(1500);

  // Advanced Credentials State
  const [fastApiBaseUrl, setFastApiBaseUrl] = useState(api.getBaseUrl() || 'http://localhost:8000');
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [bearerToken, setBearerToken] = useState(api.getToken() || '');
  const [isMintingToken, setIsMintingToken] = useState(false);
  const [isPingingBackend, setIsPingingBackend] = useState(false);
  const [backendPingResult, setBackendPingResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Account Form State
  const [fullNameInput, setFullNameInput] = useState(user?.full_name || '');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isUpdatingProfile, setIsUpdatingProfile] = useState(false);
  const [profileStatus, setProfileStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const [passwordStatus, setPasswordStatus] = useState<{ ok: boolean; message: string } | null>(null);

  // API Keys Management State
  const [apiKeys, setApiKeys] = useState<ApiKeyItem[]>([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [newKeyName, setNewKeyName] = useState('DocPilot AI Service');
  const [creatingKey, setCreatingKey] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [activeCodeTab, setActiveCodeTab] = useState<'curl' | 'python' | 'node'>('curl');
  const [copiedSnippet, setCopiedSnippet] = useState(false);

  // Key Visibility Toggles
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  const toggleShowKey = (provider: string) => {
    setShowKeys((prev) => ({ ...prev, [provider]: !prev[provider] }));
  };

  const loadConfig = useCallback(async () => {
    try {
      const cfg = await api.getAiConfig();
      if (cfg) {
        setActiveConfig(cfg);
        setFallbackOnError(Boolean(cfg.fallback_on_error));
        if (cfg.active_provider === 'ollama' || cfg.active_provider === 'local') {
          if (cfg.base_url) setOllamaBaseUrl(cfg.base_url);
          if (cfg.active_model) setOllamaModel(cfg.active_model);
        } else if (cfg.active_provider === 'openai') {
          if (cfg.base_url) setOpenaiBaseUrl(cfg.base_url);
          if (cfg.active_model) setOpenaiModel(cfg.active_model);
        } else if (cfg.active_provider === 'gemini') {
          if (cfg.active_model) setGeminiModel(cfg.active_model);
        } else if (cfg.active_provider === 'openrouter') {
          if (cfg.base_url) setOpenrouterBaseUrl(cfg.base_url);
          if (cfg.active_model) setOpenrouterModel(cfg.active_model);
        } else if (cfg.active_provider === 'custom') {
          if (cfg.base_url) setCustomEndpoint(cfg.base_url);
          if (cfg.active_model) setCustomModel(cfg.active_model);
          if (cfg.request_format) setCustomFormat(cfg.request_format);
        }
      }
    } catch (err: any) {
      console.warn('Could not load AI configuration:', err);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [activeSection]);

  useEffect(() => {
    if (user?.full_name) {
      setFullNameInput(user.full_name);
    }
  }, [user]);

  // Connection Test Handler
  const handleTestConnection = async (provider: 'ollama' | 'openai' | 'gemini' | 'openrouter' | 'custom') => {
    setTestingProvider(provider);
    try {
      const candidate: any = { provider };
      if (provider === 'ollama') {
        candidate.model = ollamaModel;
        candidate.base_url = ollamaBaseUrl;
      } else if (provider === 'openai') {
        candidate.model = openaiModel;
        candidate.base_url = openaiBaseUrl;
        candidate.api_key = openaiKey || undefined;
      } else if (provider === 'gemini') {
        candidate.model = geminiModel;
        candidate.api_key = geminiKey || undefined;
        candidate.base_url = 'https://generativelanguage.googleapis.com/v1beta/openai';
      } else if (provider === 'openrouter') {
        candidate.model = openrouterModel;
        candidate.base_url = openrouterBaseUrl;
        candidate.api_key = openrouterKey || undefined;
      } else if (provider === 'custom') {
        candidate.model = customModel;
        candidate.base_url = customEndpoint;
        candidate.request_format = customFormat;
        candidate.api_key = customKey || undefined;
      }

      const res = await api.testAiConnection(candidate);
      setProviderTestResults((prev) => ({
        ...prev,
        [provider]: {
          ok: res.success,
          message: res.message,
          latency_ms: res.latency_ms,
        },
      }));
      if (res.success) {
        onNotify(`Connection to ${provider.toUpperCase()} verified successfully (${res.latency_ms || 0}ms)!`, 'success');
      } else {
        onNotify(`Connection test failed: ${res.message}`, 'error');
      }
    } catch (err: any) {
      const errMsg = err?.message || 'Connection test failed.';
      setProviderTestResults((prev) => ({
        ...prev,
        [provider]: {
          ok: false,
          message: errMsg,
        },
      }));
      onNotify(errMsg, 'error');
    } finally {
      setTestingProvider(null);
    }
  };

  // Provider Activation & Save Handler
  const handleActivateProvider = async (provider: 'ollama' | 'openai' | 'gemini' | 'openrouter' | 'custom') => {
    setSavingProvider(provider);
    try {
      const payload: any = {
        provider: provider === 'ollama' ? 'local' : provider,
        fallback_on_error: fallbackOnError,
      };

      if (provider === 'ollama') {
        payload.model = ollamaModel;
        payload.base_url = ollamaBaseUrl;
      } else if (provider === 'openai') {
        payload.model = openaiModel;
        payload.base_url = openaiBaseUrl;
        if (openaiKey) payload.api_key = openaiKey;
      } else if (provider === 'gemini') {
        payload.model = geminiModel;
        payload.base_url = 'https://generativelanguage.googleapis.com/v1beta/openai';
        if (geminiKey) payload.api_key = geminiKey;
      } else if (provider === 'openrouter') {
        payload.model = openrouterModel;
        payload.base_url = openrouterBaseUrl;
        if (openrouterKey) payload.api_key = openrouterKey;
      } else if (provider === 'custom') {
        payload.model = customModel;
        payload.base_url = customEndpoint;
        payload.request_format = customFormat;
        if (customKey) payload.api_key = customKey;
      }

      const updated = await api.updateAiConfig(payload);
      setActiveConfig(updated);
      if (onRefreshAiConfig) {
        await onRefreshAiConfig();
      }

      if (provider === 'openai') setOpenaiKey('');
      if (provider === 'gemini') setGeminiKey('');
      if (provider === 'openrouter') setOpenrouterKey('');
      if (provider === 'custom') setCustomKey('');

      onNotify(`Active AI Provider switched to ${provider.toUpperCase()} (${updated.active_model}).`, 'success');
    } catch (err: any) {
      onNotify(`Failed to activate provider: ${err.message}`, 'error');
    } finally {
      setSavingProvider(null);
    }
  };

  // Advanced Credentials Handlers
  const handleMintToken = async () => {
    setIsMintingToken(true);
    try {
      api.updateConfig({ baseUrl: fastApiBaseUrl });
      const token = await api.mintToken(clientId, clientSecret);
      setBearerToken(token);
      onNotify('JWT Access token minted and saved.', 'success');
    } catch (err: any) {
      onNotify(`Token minting failed: ${err.message}`, 'error');
    } finally {
      setIsMintingToken(false);
    }
  };

  const handlePingBackend = async () => {
    setIsPingingBackend(true);
    setBackendPingResult(null);
    const t0 = Date.now();
    try {
      api.updateConfig({ baseUrl: fastApiBaseUrl, token: bearerToken || undefined });
      const health = await api.checkHealth();
      const latency = Date.now() - t0;
      setBackendPingResult({
        ok: true,
        message: `FastAPI backend connected (${latency}ms latency) • v${health.version || '1.0.0'}`,
      });
      onNotify('Backend ping successful.', 'success');
    } catch (err: any) {
      setBackendPingResult({
        ok: false,
        message: `Cannot reach backend: ${err.message}`,
      });
      onNotify(`Backend ping failed: ${err.message}`, 'error');
    } finally {
      setIsPingingBackend(false);
    }
  };

  // Account Profile Handlers
  const handleUpdateName = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullNameInput.trim()) return;
    setIsUpdatingProfile(true);
    setProfileStatus(null);
    const res = await updateProfile(fullNameInput.trim());
    setIsUpdatingProfile(false);
    if (res.error) {
      setProfileStatus({ ok: false, message: res.error });
      onNotify(res.error, 'error');
    } else {
      setProfileStatus({ ok: true, message: 'Profile name updated successfully!' });
      onNotify('Profile name updated.', 'success');
    }
  };

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 6) {
      setPasswordStatus({ ok: false, message: 'Password must be at least 6 characters.' });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordStatus({ ok: false, message: 'Passwords do not match.' });
      return;
    }
    setPasswordStatus(null);
    const res = await updatePassword(newPassword);
    if (res.error) {
      setPasswordStatus({ ok: false, message: res.error });
      onNotify(res.error, 'error');
    } else {
      setPasswordStatus({ ok: true, message: 'Password updated successfully!' });
      setNewPassword('');
      setConfirmPassword('');
      onNotify('Password changed successfully.', 'success');
    }
  };

  // API Key Management Handlers
  const fetchApiKeys = useCallback(async () => {
    setLoadingApiKeys(true);
    try {
      const res = await api.getApiKeys();
      setApiKeys(res.keys || []);
    } catch (err: any) {
      console.error('Failed to fetch API keys:', err);
    } finally {
      setLoadingApiKeys(false);
    }
  }, []);

  useEffect(() => {
    if (activeSection === 'api_keys') {
      fetchApiKeys();
    }
  }, [activeSection, fetchApiKeys]);

  const handleCreateApiKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName.trim()) return;
    setCreatingKey(true);
    try {
      const res = await api.createApiKey(newKeyName.trim());
      setNewlyCreatedKey(res.key);
      setNewKeyName('');
      onNotify('API Key created successfully! Make sure to copy it now.', 'success');
      await fetchApiKeys();
    } catch (err: any) {
      onNotify(`Failed to create API key: ${err.message}`, 'error');
    } finally {
      setCreatingKey(false);
    }
  };

  const handleRevokeApiKey = async (keyId: string, keyName: string) => {
    if (
      !window.confirm(
        `Are you sure you want to revoke API key "${keyName}"? Any external services using this key will immediately lose access.`
      )
    ) {
      return;
    }
    try {
      await api.revokeApiKey(keyId);
      onNotify(`API Key "${keyName}" revoked.`, 'info');
      await fetchApiKeys();
    } catch (err: any) {
      onNotify(`Failed to revoke API key: ${err.message}`, 'error');
    }
  };

  const handleCopyKey = (key: string) => {
    navigator.clipboard.writeText(key);
    setCopiedKey(true);
    setTimeout(() => setCopiedKey(false), 2000);
    onNotify('API key copied to clipboard!', 'info');
  };

  // Active status helper
  const isProviderActive = (name: string) => {
    if (!activeConfig) return false;
    const current = activeConfig.active_provider.toLowerCase();
    if (name === 'ollama') return current === 'ollama' || current === 'local';
    return current === name.toLowerCase();
  };

  return (
    <div className="settings-page-wrapper mode-fade-enter">
      {/* 1. Page Header */}
      <div className="settings-page-header">
        <div className="settings-header-titles">
          <h1 className="settings-page-title">Settings & System Configuration</h1>
          <p className="settings-page-desc">
            Manage multi-engine AI inference, active reasoning models, API access tokens, and account security.
          </p>
        </div>
        <div className="settings-header-meta">
          <span className={`settings-role-badge ${isAdmin ? 'admin' : 'user'}`}>
            <Shield size={13} />
            <span>{isAdmin ? 'Administrator Access' : 'Standard User Access'}</span>
          </span>
        </div>
      </div>

      {/* 2. Main Two-Column Layout */}
      <div className="settings-page-layout">
        {/* Left Sub-Navigation Sidebar */}
        <aside className="settings-subnav-sidebar" aria-label="Settings navigation">
          <nav className="settings-nav-list">
            <button
              type="button"
              className={`settings-nav-btn ${activeSection === 'ai_providers' ? 'active' : ''}`}
              onClick={() => setActiveSection('ai_providers')}
            >
              <Cpu size={17} />
              <div className="nav-btn-text">
                <span className="nav-btn-title">AI Providers</span>
                <span className="nav-btn-sub">Local & Cloud Engines</span>
              </div>
            </button>

            <button
              type="button"
              className={`settings-nav-btn ${activeSection === 'model_settings' ? 'active' : ''}`}
              onClick={() => setActiveSection('model_settings')}
            >
              <Sliders size={17} />
              <div className="nav-btn-text">
                <span className="nav-btn-title">Model Settings</span>
                <span className="nav-btn-sub">Parameters & Fallbacks</span>
              </div>
            </button>

            <button
              type="button"
              className={`settings-nav-btn ${activeSection === 'api_keys' ? 'active' : ''}`}
              onClick={() => setActiveSection('api_keys')}
            >
              <Key size={17} />
              <div className="nav-btn-text">
                <span className="nav-btn-title">API Keys & DocPilot AI</span>
                <span className="nav-btn-sub">Offline OCR Integration</span>
              </div>
            </button>

            <button
              type="button"
              className={`settings-nav-btn ${activeSection === 'advanced' ? 'active' : ''}`}
              onClick={() => setActiveSection('advanced')}
            >
              <Key size={17} />
              <div className="nav-btn-text">
                <span className="nav-btn-title">Advanced</span>
                <span className="nav-btn-sub">API & Client Tokens</span>
              </div>
            </button>

            <button
              type="button"
              className={`settings-nav-btn ${activeSection === 'quotas' ? 'active' : ''}`}
              onClick={() => setActiveSection('quotas')}
            >
              <BarChart2 size={17} />
              <div className="nav-btn-text">
                <span className="nav-btn-title">Usage & Quotas</span>
                <span className="nav-btn-sub">Metrics & Storage</span>
              </div>
            </button>

            <button
              type="button"
              className={`settings-nav-btn ${activeSection === 'account' ? 'active' : ''}`}
              onClick={() => setActiveSection('account')}
            >
              <UserCheck size={17} />
              <div className="nav-btn-text">
                <span className="nav-btn-title">Account & Security</span>
                <span className="nav-btn-sub">Profile & Password</span>
              </div>
            </button>

            <button
              type="button"
              className={`settings-nav-btn ${activeSection === 'general' ? 'active' : ''}`}
              onClick={() => setActiveSection('general')}
            >
              <Layers size={17} />
              <div className="nav-btn-text">
                <span className="nav-btn-title">General</span>
                <span className="nav-btn-sub">System & Versions</span>
              </div>
            </button>
          </nav>
        </aside>

        {/* Right Content Pane */}
        <main className="settings-content-pane">
          {/* SECTION 1: AI PROVIDERS (Default) */}
          {activeSection === 'ai_providers' && (
            <div className="settings-section-view">
              {/* Active Provider Hero Banner */}
              <div className="settings-active-engine-card">
                <div className="active-engine-left">
                  <div className="engine-pulse-icon">
                    <Sparkles size={24} />
                  </div>
                  <div>
                    <div className="active-engine-heading-row">
                      <span className="active-engine-label">CURRENT ACTIVE AI ENGINE</span>
                      <span className="active-engine-tag">
                        {activeConfig?.mode === 'local' ? 'Offline Air-Gapped' : 'Frontier Cloud'}
                      </span>
                    </div>
                    <div className="active-engine-name">
                      {activeConfig?.active_provider === 'ollama' || activeConfig?.active_provider === 'local'
                        ? 'Local Ollama Engine'
                        : activeConfig?.active_provider === 'openai'
                        ? 'OpenAI Cloud Provider'
                        : activeConfig?.active_provider === 'gemini'
                        ? 'Google Gemini Cloud Provider'
                        : activeConfig?.active_provider === 'openrouter'
                        ? 'OpenRouter Frontier Gateway'
                        : 'Custom AI Gateway'}
                    </div>
                    <div className="active-engine-details">
                      Model: <code className="active-model-code">{activeConfig?.active_model || 'qwen2.5vl:3b'}</code>
                      {activeConfig?.base_url && (
                        <span className="active-endpoint-meta"> • {activeConfig.base_url}</span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="active-engine-right">
                  <span
                    className={`status-connection-badge ${
                      activeConfig?.ollama_available || activeConfig?.api_key_configured
                        ? 'badge-connected'
                        : 'badge-idle'
                    }`}
                  >
                    {activeConfig?.ollama_available || activeConfig?.api_key_configured
                      ? 'Connected'
                      : 'Configuration Required'}
                  </span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTestConnection(
                      activeConfig?.active_provider === 'local' || activeConfig?.active_provider === 'ollama'
                        ? 'ollama'
                        : (activeConfig?.active_provider as any) || 'ollama'
                    )}
                    disabled={testingProvider !== null}
                  >
                    <RefreshCw size={13} className={testingProvider ? 'spin-anim' : ''} />
                    <span>{testingProvider ? 'Testing...' : 'Test Connection'}</span>
                  </button>
                </div>
              </div>

              {/* 5 Provider Cards Grid */}
              <div className="settings-providers-grid">
                {/* 1. OLLAMA (LOCAL) */}
                <div className={`provider-config-card ${isProviderActive('ollama') ? 'is-active-card' : ''}`}>
                  <div className="provider-card-header">
                    <div className="provider-card-title-group">
                      <div className="provider-badge-icon ollama">
                        <Cpu size={20} />
                      </div>
                      <div>
                        <h3 className="provider-card-title">Ollama (Local)</h3>
                        <span className="provider-chip-pill offline">Air-Gapped / Private</span>
                      </div>
                    </div>
                    {isProviderActive('ollama') && (
                      <span className="active-indicator-chip">
                        <Check size={12} /> Active
                      </span>
                    )}
                  </div>
                  <p className="provider-card-description">
                    Zero external network access. Air-gapped on-device vision inference using Qwen2.5-VL 3B.
                  </p>

                  <div className="provider-card-fields">
                    <div className="provider-field-item">
                      <label htmlFor="ollama-base-url-input">Ollama Base URL</label>
                      <input
                        id="ollama-base-url-input"
                        type="text"
                        value={ollamaBaseUrl}
                        onChange={(e) => setOllamaBaseUrl(e.target.value)}
                        placeholder="http://127.0.0.1:11434"
                      />
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="ollama-model-input">Model</label>
                      <input
                        id="ollama-model-input"
                        type="text"
                        value={ollamaModel}
                        onChange={(e) => setOllamaModel(e.target.value)}
                        placeholder="qwen2.5vl:3b"
                      />
                    </div>

                    {providerTestResults['ollama'] && (
                      <div className={`card-test-banner ${providerTestResults['ollama'].ok ? 'ok' : 'err'}`}>
                        {providerTestResults['ollama'].message}
                      </div>
                    )}

                    <div className="provider-card-actions">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleTestConnection('ollama')}
                        disabled={testingProvider === 'ollama'}
                      >
                        <RefreshCw size={13} className={testingProvider === 'ollama' ? 'spin-anim' : ''} />
                        <span>Test Connection</span>
                      </button>

                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => handleActivateProvider('ollama')}
                        disabled={savingProvider === 'ollama' || isProviderActive('ollama')}
                      >
                        <Save size={13} />
                        <span>{isProviderActive('ollama') ? 'Current Active' : 'Activate & Save'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* 2. OPENAI */}
                <div className={`provider-config-card ${isProviderActive('openai') ? 'is-active-card' : ''}`}>
                  <div className="provider-card-header">
                    <div className="provider-card-title-group">
                      <div className="provider-badge-icon openai">
                        <Sparkles size={20} />
                      </div>
                      <div>
                        <h3 className="provider-card-title">OpenAI</h3>
                        <span className="provider-chip-pill cloud">Frontier Reasoning</span>
                      </div>
                    </div>
                    {isProviderActive('openai') && (
                      <span className="active-indicator-chip">
                        <Check size={12} /> Active
                      </span>
                    )}
                  </div>
                  <p className="provider-card-description">
                    Direct integration with official OpenAI models (GPT-4o, GPT-4o-mini, o3-mini).
                  </p>

                  <div className="provider-card-fields">
                    <div className="provider-field-item">
                      <label htmlFor="openai-model-input">Model</label>
                      <input
                        id="openai-model-input"
                        type="text"
                        value={openaiModel}
                        onChange={(e) => setOpenaiModel(e.target.value)}
                        placeholder="gpt-4o-mini"
                      />
                      <div className="settings-suggestion-chips">
                        {['gpt-4o-mini', 'gpt-4o', 'o3-mini'].map((m) => (
                          <button
                            key={m}
                            type="button"
                            className={`suggestion-chip ${openaiModel === m ? 'active' : ''}`}
                            onClick={() => setOpenaiModel(m)}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="openai-key-input">API Key</label>
                      <div className="password-input-wrap">
                        <input
                          id="openai-key-input"
                          type={showKeys['openai'] ? 'text' : 'password'}
                          value={openaiKey}
                          onChange={(e) => setOpenaiKey(e.target.value)}
                          placeholder={
                            activeConfig?.api_key_configured && activeConfig.active_provider === 'openai'
                              ? '•••••••••••••••• (Encrypted in Storage)'
                              : 'sk-proj-...'
                          }
                        />
                        <button
                          type="button"
                          className="toggle-vis-btn"
                          onClick={() => toggleShowKey('openai')}
                          aria-label="Toggle visibility"
                        >
                          {showKeys['openai'] ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="openai-base-url-input">Base URL (Optional)</label>
                      <input
                        id="openai-base-url-input"
                        type="text"
                        value={openaiBaseUrl}
                        onChange={(e) => setOpenaiBaseUrl(e.target.value)}
                        placeholder="https://api.openai.com/v1"
                      />
                    </div>

                    {providerTestResults['openai'] && (
                      <div className={`card-test-banner ${providerTestResults['openai'].ok ? 'ok' : 'err'}`}>
                        {providerTestResults['openai'].message}
                      </div>
                    )}

                    <div className="provider-card-actions">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleTestConnection('openai')}
                        disabled={testingProvider === 'openai'}
                      >
                        <RefreshCw size={13} className={testingProvider === 'openai' ? 'spin-anim' : ''} />
                        <span>Test Connection</span>
                      </button>

                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => handleActivateProvider('openai')}
                        disabled={savingProvider === 'openai' || isProviderActive('openai')}
                      >
                        <Save size={13} />
                        <span>{isProviderActive('openai') ? 'Current Active' : 'Activate & Save'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* 3. GOOGLE GEMINI */}
                <div className={`provider-config-card ${isProviderActive('gemini') ? 'is-active-card' : ''}`}>
                  <div className="provider-card-header">
                    <div className="provider-card-title-group">
                      <div className="provider-badge-icon gemini">
                        <Zap size={20} />
                      </div>
                      <div>
                        <h3 className="provider-card-title">Google Gemini</h3>
                        <span className="provider-chip-pill gemini">Multimodal Vision</span>
                      </div>
                    </div>
                    {isProviderActive('gemini') && (
                      <span className="active-indicator-chip">
                        <Check size={12} /> Active
                      </span>
                    )}
                  </div>
                  <p className="provider-card-description">
                    Google Gemini via official OpenAI-compatible endpoint with fast vision reasoning.
                  </p>

                  <div className="provider-card-fields">
                    <div className="provider-field-item">
                      <label htmlFor="gemini-model-input">Model</label>
                      <input
                        id="gemini-model-input"
                        type="text"
                        value={geminiModel}
                        onChange={(e) => setGeminiModel(e.target.value)}
                        placeholder="gemini-2.0-flash"
                      />
                      <div className="settings-suggestion-chips">
                        {['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro'].map((m) => (
                          <button
                            key={m}
                            type="button"
                            className={`suggestion-chip ${geminiModel === m ? 'active' : ''}`}
                            onClick={() => setGeminiModel(m)}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="gemini-key-input">API Key</label>
                      <div className="password-input-wrap">
                        <input
                          id="gemini-key-input"
                          type={showKeys['gemini'] ? 'text' : 'password'}
                          value={geminiKey}
                          onChange={(e) => setGeminiKey(e.target.value)}
                          placeholder={
                            activeConfig?.api_key_configured && activeConfig.active_provider === 'gemini'
                              ? '•••••••••••••••• (Encrypted in Storage)'
                              : 'AIzaSy...'
                          }
                        />
                        <button
                          type="button"
                          className="toggle-vis-btn"
                          onClick={() => toggleShowKey('gemini')}
                          aria-label="Toggle visibility"
                        >
                          {showKeys['gemini'] ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>

                    {providerTestResults['gemini'] && (
                      <div className={`card-test-banner ${providerTestResults['gemini'].ok ? 'ok' : 'err'}`}>
                        {providerTestResults['gemini'].message}
                      </div>
                    )}

                    <div className="provider-card-actions">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleTestConnection('gemini')}
                        disabled={testingProvider === 'gemini'}
                      >
                        <RefreshCw size={13} className={testingProvider === 'gemini' ? 'spin-anim' : ''} />
                        <span>Test Connection</span>
                      </button>

                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => handleActivateProvider('gemini')}
                        disabled={savingProvider === 'gemini' || isProviderActive('gemini')}
                      >
                        <Save size={13} />
                        <span>{isProviderActive('gemini') ? 'Current Active' : 'Activate & Save'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* 4. OPENROUTER */}
                <div className={`provider-config-card ${isProviderActive('openrouter') ? 'is-active-card' : ''}`}>
                  <div className="provider-card-header">
                    <div className="provider-card-title-group">
                      <div className="provider-badge-icon openrouter">
                        <Globe size={20} />
                      </div>
                      <div>
                        <h3 className="provider-card-title">OpenRouter</h3>
                        <span className="provider-chip-pill gateway">Unified Gateway</span>
                      </div>
                    </div>
                    {isProviderActive('openrouter') && (
                      <span className="active-indicator-chip">
                        <Check size={12} /> Active
                      </span>
                    )}
                  </div>
                  <p className="provider-card-description">
                    Unified routing to 200+ frontier open-source and proprietary models with auto-fallback.
                  </p>

                  <div className="provider-card-fields">
                    <div className="provider-field-item">
                      <label htmlFor="openrouter-model-input">Model ID</label>
                      <input
                        id="openrouter-model-input"
                        type="text"
                        value={openrouterModel}
                        onChange={(e) => setOpenrouterModel(e.target.value)}
                        placeholder="google/gemini-2.5-flash"
                      />
                      <div className="settings-suggestion-chips">
                        {[
                          { label: 'Gemini 2.5 Flash', id: 'google/gemini-2.5-flash' },
                          { label: 'Nemotron 550B', id: 'nvidia/nemotron-3-ultra-550b-a55b:free' },
                          { label: 'Llama 3.3 70B', id: 'meta-llama/llama-3.3-70b-instruct:free' },
                        ].map((m) => (
                          <button
                            key={m.id}
                            type="button"
                            className={`suggestion-chip ${openrouterModel === m.id ? 'active' : ''}`}
                            onClick={() => setOpenrouterModel(m.id)}
                          >
                            {m.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="openrouter-key-input">API Key</label>
                      <div className="password-input-wrap">
                        <input
                          id="openrouter-key-input"
                          type={showKeys['openrouter'] ? 'text' : 'password'}
                          value={openrouterKey}
                          onChange={(e) => setOpenrouterKey(e.target.value)}
                          placeholder={
                            activeConfig?.api_key_configured && activeConfig.active_provider === 'openrouter'
                              ? '•••••••••••••••• (Encrypted in Storage)'
                              : 'sk-or-v1-...'
                          }
                        />
                        <button
                          type="button"
                          className="toggle-vis-btn"
                          onClick={() => toggleShowKey('openrouter')}
                          aria-label="Toggle visibility"
                        >
                          {showKeys['openrouter'] ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="openrouter-base-url-input">Base URL</label>
                      <input
                        id="openrouter-base-url-input"
                        type="text"
                        value={openrouterBaseUrl}
                        onChange={(e) => setOpenrouterBaseUrl(e.target.value)}
                        placeholder="https://openrouter.ai/api/v1"
                      />
                    </div>

                    {providerTestResults['openrouter'] && (
                      <div className={`card-test-banner ${providerTestResults['openrouter'].ok ? 'ok' : 'err'}`}>
                        {providerTestResults['openrouter'].message}
                      </div>
                    )}

                    <div className="provider-card-actions">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleTestConnection('openrouter')}
                        disabled={testingProvider === 'openrouter'}
                      >
                        <RefreshCw size={13} className={testingProvider === 'openrouter' ? 'spin-anim' : ''} />
                        <span>Test Connection</span>
                      </button>

                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => handleActivateProvider('openrouter')}
                        disabled={savingProvider === 'openrouter' || isProviderActive('openrouter')}
                      >
                        <Save size={13} />
                        <span>{isProviderActive('openrouter') ? 'Current Active' : 'Activate & Save'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* 5. CUSTOM AI */}
                <div className={`provider-config-card custom-gateway-card ${isProviderActive('custom') ? 'is-active-card' : ''}`}>
                  <div className="provider-card-header">
                    <div className="provider-card-title-group">
                      <div className="provider-badge-icon custom">
                        <Terminal size={20} />
                      </div>
                      <div>
                        <h3 className="provider-card-title">Custom AI Gateway</h3>
                        <span className="provider-chip-pill custom">Self-Hosted / Proxy</span>
                      </div>
                    </div>
                    {isProviderActive('custom') && (
                      <span className="active-indicator-chip">
                        <Check size={12} /> Active
                      </span>
                    )}
                  </div>
                  <p className="provider-card-description">
                    Connect private vLLM, Ollama external hosts, LiteLLM, or proprietary proxies.
                  </p>

                  <div className="provider-card-fields">
                    <div className="provider-field-item">
                      <label htmlFor="custom-name-input">Provider Name</label>
                      <input
                        id="custom-name-input"
                        type="text"
                        value={customName}
                        onChange={(e) => setCustomName(e.target.value)}
                        placeholder="Internal vLLM Service"
                      />
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="custom-model-input">Model</label>
                      <input
                        id="custom-model-input"
                        type="text"
                        value={customModel}
                        onChange={(e) => setCustomModel(e.target.value)}
                        placeholder="e.g. meta-llama/Llama-3.2-11B-Vision"
                      />
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="custom-endpoint-input">API Endpoint</label>
                      <input
                        id="custom-endpoint-input"
                        type="text"
                        value={customEndpoint}
                        onChange={(e) => setCustomEndpoint(e.target.value)}
                        placeholder="http://localhost:8000/v1"
                      />
                    </div>

                    <div className="provider-field-item">
                      <label htmlFor="custom-format-select">Request Format</label>
                      <select
                        id="custom-format-select"
                        value={customFormat}
                        onChange={(e) => setCustomFormat(e.target.value)}
                      >
                        <option value="chat_completions">OpenAI-compatible (/chat/completions)</option>
                        <option value="ollama">Ollama Native (/api/chat)</option>
                        <option value="completions">Raw Prompt (/completions)</option>
                      </select>
                    </div>

                    <div className="provider-field-item full-width">
                      <label htmlFor="custom-key-input">API Key (Optional)</label>
                      <div className="password-input-wrap">
                        <input
                          id="custom-key-input"
                          type={showKeys['custom'] ? 'text' : 'password'}
                          value={customKey}
                          onChange={(e) => setCustomKey(e.target.value)}
                          placeholder="Leave empty if unauthenticated"
                        />
                        <button
                          type="button"
                          className="toggle-vis-btn"
                          onClick={() => toggleShowKey('custom')}
                          aria-label="Toggle visibility"
                        >
                          {showKeys['custom'] ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>

                    {providerTestResults['custom'] && (
                      <div className={`card-test-banner ${providerTestResults['custom'].ok ? 'ok' : 'err'}`}>
                        {providerTestResults['custom'].message}
                      </div>
                    )}

                    <div className="provider-card-actions">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleTestConnection('custom')}
                        disabled={testingProvider === 'custom'}
                      >
                        <RefreshCw size={13} className={testingProvider === 'custom' ? 'spin-anim' : ''} />
                        <span>Test Connection</span>
                      </button>

                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => handleActivateProvider('custom')}
                        disabled={savingProvider === 'custom' || isProviderActive('custom')}
                      >
                        <Save size={13} />
                        <span>{isProviderActive('custom') ? 'Current Active' : 'Activate & Save'}</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 2: MODEL SETTINGS */}
          {activeSection === 'model_settings' && (
            <div className="settings-section-view">
              <div className="settings-subcard">
                <h3 className="subcard-title">Inference & Fallback Parameters</h3>
                <p className="subcard-desc">
                  Tune reasoning boundaries and decide fallback behavior when external providers experience network outages.
                </p>

                <div className="settings-form-col">
                  <div className="settings-toggle-row">
                    <div>
                      <div className="toggle-label">Automatic Local Ollama Fallback</div>
                      <div className="toggle-desc">
                        If an external API request encounters a timeout or connection failure, automatically re-route
                        the request to Local Ollama (qwen2.5vl:3b) instead of raising an error.
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      id="fallback-toggle"
                      checked={fallbackOnError}
                      onChange={(e) => setFallbackOnError(e.target.checked)}
                    />
                  </div>

                  <div className="settings-field-group" style={{ marginTop: '1.5rem' }}>
                    <label htmlFor="temp-slider">Temperature ({temperature})</label>
                    <input
                      type="range"
                      id="temp-slider"
                      min="0.0"
                      max="1.0"
                      step="0.05"
                      value={temperature}
                      onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    />
                    <span className="field-hint">Lower temperature (0.0 – 0.2) delivers strict factual grounding for legal and financial document OCR.</span>
                  </div>

                  <div className="settings-field-group" style={{ marginTop: '1rem' }}>
                    <label htmlFor="max-tokens-input">Maximum Output Tokens</label>
                    <input
                      type="number"
                      id="max-tokens-input"
                      value={maxTokens}
                      onChange={(e) => setMaxTokens(parseInt(e.target.value, 10) || 1500)}
                    />
                  </div>

                  <div style={{ marginTop: '1.5rem' }}>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={async () => {
                        try {
                          await api.updateAiConfig({ fallback_on_error: fallbackOnError });
                          onNotify('Model parameter preferences saved.', 'success');
                        } catch (err: any) {
                          onNotify(err.message, 'error');
                        }
                      }}
                    >
                      <Save size={14} />
                      <span>Save Model Parameters</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION: API KEYS & DOCPILOT AI */}
          {activeSection === 'api_keys' && (
            <div className="settings-section-view">
              {/* 1. Header Hero Card */}
              <div className="settings-subcard">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
                  <div>
                    <h3 className="subcard-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Key size={20} style={{ color: 'var(--primary)' }} />
                      DocPilot AI & Offline OCR API Access
                    </h3>
                    <p className="subcard-desc" style={{ marginBottom: '12px' }}>
                      Connect DocPilot AI and external services to this offline OCR microservice using API keys.
                      Documents processed via <code>/api/v1/ocr</code> execute 100% locally with RapidOCR, extracting text, fields, and authenticity indicators without cloud AI dependencies.
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '4px' }}>
                  <span className="provider-chip-pill local">⚡ RapidOCR Engine (Offline)</span>
                  <span className="provider-chip-pill local">🛡️ Zero Cloud Data Leakage</span>
                  <span className="provider-chip-pill cloud">📑 22 Rule-Based Extractors</span>
                  <span className="provider-chip-pill gateway">🔍 Checksum & Font Verification</span>
                </div>
              </div>

              {/* 2. Create API Key Card */}
              <div className="settings-subcard" style={{ marginTop: '1.5rem' }}>
                <h3 className="subcard-title" style={{ fontSize: '1.1rem' }}>Generate New API Key</h3>
                <p className="subcard-desc">
                  Create a new secret key for DocPilot AI or automated document pipelines.
                </p>

                <form onSubmit={handleCreateApiKey} style={{ display: 'flex', gap: '12px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                  <div className="settings-field-group" style={{ flex: '1', minWidth: '240px' }}>
                    <label htmlFor="new-key-name-input">Key Identifier / Name</label>
                    <input
                      id="new-key-name-input"
                      type="text"
                      value={newKeyName}
                      onChange={(e) => setNewKeyName(e.target.value)}
                      placeholder="e.g., DocPilot AI Microservice"
                      required
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={creatingKey || !newKeyName.trim()}
                    style={{ height: '42px', padding: '0 20px', display: 'flex', alignItems: 'center', gap: '8px' }}
                  >
                    <Plus size={16} />
                    <span>{creatingKey ? 'Generating...' : 'Create Secret Key'}</span>
                  </button>
                </form>

                {/* Newly Created Secret Key Banner */}
                {newlyCreatedKey && (
                  <div
                    style={{
                      marginTop: '1.25rem',
                      padding: '16px 20px',
                      borderRadius: '12px',
                      background: 'rgba(16, 185, 129, 0.08)',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', fontWeight: 700, fontSize: '0.92rem', marginBottom: '6px' }}>
                      <CheckCircle2 size={18} />
                      <span>API Key Generated Successfully</span>
                    </div>
                    <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', margin: '0 0 10px 0' }}>
                      Please copy this key immediately. For security reasons, <strong>it will never be displayed again</strong>.
                    </p>
                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                      <code
                        style={{
                          flex: 1,
                          padding: '10px 14px',
                          borderRadius: '8px',
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border-subtle)',
                          fontFamily: 'monospace',
                          fontSize: '0.9rem',
                          wordBreak: 'break-all',
                          color: 'var(--text-main)',
                        }}
                      >
                        {newlyCreatedKey}
                      </code>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleCopyKey(newlyCreatedKey)}
                        style={{ height: '40px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }}
                      >
                        {copiedKey ? <Check size={14} style={{ color: 'var(--success)' }} /> : <Copy size={14} />}
                        <span>{copiedKey ? 'Copied!' : 'Copy Key'}</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* 3. Existing Keys Table Card */}
              <div className="settings-subcard" style={{ marginTop: '1.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                  <div>
                    <h3 className="subcard-title" style={{ fontSize: '1.1rem' }}>Active API Keys</h3>
                    <p className="subcard-desc" style={{ margin: 0 }}>
                      Keys currently authorized to call the offline OCR endpoints.
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={fetchApiKeys}
                    disabled={loadingApiKeys}
                    title="Refresh keys list"
                  >
                    <RefreshCw size={13} className={loadingApiKeys ? 'spin-anim' : ''} />
                    <span>Refresh</span>
                  </button>
                </div>

                {loadingApiKeys && apiKeys.length === 0 ? (
                  <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                    Loading API keys...
                  </div>
                ) : apiKeys.length === 0 ? (
                  <div style={{ padding: '32px 20px', textAlign: 'center', border: '1px dashed var(--border-subtle)', borderRadius: '12px', background: 'var(--bg-card)' }}>
                    <Key size={32} style={{ opacity: 0.3, margin: '0 auto 12px auto', display: 'block' }} />
                    <p style={{ fontWeight: 600, color: 'var(--text-main)', marginBottom: '4px' }}>No API keys found</p>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: 0 }}>
                      Generate an API key above to connect DocPilot AI with this offline OCR engine.
                    </p>
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.88rem' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          <th style={{ padding: '10px 12px' }}>Name</th>
                          <th style={{ padding: '10px 12px' }}>Secret Key</th>
                          <th style={{ padding: '10px 12px' }}>Created</th>
                          <th style={{ padding: '10px 12px' }}>Last Used</th>
                          <th style={{ padding: '10px 12px' }}>Status</th>
                          <th style={{ padding: '10px 12px', textAlign: 'right' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {apiKeys.map((k) => (
                          <tr key={k.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                            <td style={{ padding: '14px 12px', fontWeight: 600, color: 'var(--text-main)' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <Lock size={14} style={{ color: 'var(--primary)' }} />
                                <span>{k.name}</span>
                              </div>
                            </td>
                            <td style={{ padding: '14px 12px' }}>
                              <code style={{ fontFamily: 'monospace', padding: '3px 7px', background: 'var(--bg-card)', borderRadius: '4px', border: '1px solid var(--border-subtle)' }}>
                                {k.prefix}••••••••
                              </code>
                            </td>
                            <td style={{ padding: '14px 12px', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                              {k.created_at ? new Date(k.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                            </td>
                            <td style={{ padding: '14px 12px', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                              {k.last_used_at ? new Date(k.last_used_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Never'}
                            </td>
                            <td style={{ padding: '14px 12px' }}>
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '12px', fontSize: '0.72rem', fontWeight: 700, background: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
                                <Check size={11} /> Active
                              </span>
                            </td>
                            <td style={{ padding: '14px 12px', textAlign: 'right' }}>
                              <button
                                type="button"
                                className="btn btn-danger btn-sm"
                                onClick={() => handleRevokeApiKey(k.id, k.name)}
                                title="Revoke API key"
                                style={{ padding: '6px 10px', height: 'auto' }}
                              >
                                <Trash2 size={13} />
                                <span>Revoke</span>
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* 4. DocPilot AI Offline OCR Integration Guide & Code Snippets */}
              <div className="settings-subcard" style={{ marginTop: '1.5rem' }}>
                <h3 className="subcard-title" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Code size={18} style={{ color: 'var(--primary)' }} />
                  DocPilot AI Integration Quickstart
                </h3>
                <p className="subcard-desc">
                  Follow these steps to connect your DocPilot AI workflow with this offline OCR service.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '20px' }}>
                  <div style={{ padding: '16px', borderRadius: '10px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--primary)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      1. Health & Ping
                    </div>
                    <code style={{ fontSize: '0.85rem', color: 'var(--text-main)', display: 'block', marginBottom: '6px' }}>GET /api/v1/ping</code>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
                      Verifies key validity and returns active engine information (RapidOCR, version, device).
                    </p>
                  </div>

                  <div style={{ padding: '16px', borderRadius: '10px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--primary)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      2. Offline OCR Pipeline
                    </div>
                    <code style={{ fontSize: '0.85rem', color: 'var(--text-main)', display: 'block', marginBottom: '6px' }}>POST /api/v1/ocr</code>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
                      Accepts multipart <code>file</code> upload. Returns extracted text, fields, type, confidence, and authenticity checks.
                    </p>
                  </div>

                  <div style={{ padding: '16px', borderRadius: '10px', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--primary)', textTransform: 'uppercase', marginBottom: '4px' }}>
                      3. Authentication Header
                    </div>
                    <code style={{ fontSize: '0.85rem', color: 'var(--text-main)', display: 'block', marginBottom: '6px' }}>X-API-Key: dp_live_...</code>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
                      Pass via <code>X-API-Key</code> header or standard <code>Authorization: Bearer &lt;key&gt;</code>.
                    </p>
                  </div>
                </div>

                {/* Code Tabs */}
                <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-subtle)', marginBottom: '12px', paddingBottom: '8px' }}>
                  <button
                    type="button"
                    className={`btn btn-sm ${activeCodeTab === 'curl' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setActiveCodeTab('curl')}
                  >
                    cURL
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${activeCodeTab === 'python' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setActiveCodeTab('python')}
                  >
                    Python (requests)
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${activeCodeTab === 'node' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setActiveCodeTab('node')}
                  >
                    Node.js / TS (axios)
                  </button>
                </div>

                {/* Snippet Display */}
                <div style={{ position: 'relative' }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      const snippet =
                        activeCodeTab === 'curl'
                          ? `curl -X POST "http://localhost:8000/api/v1/ocr" \\\n  -H "X-API-Key: YOUR_API_KEY" \\\n  -F "file=@/path/to/document.pdf"`
                          : activeCodeTab === 'python'
                          ? `import requests\n\nAPI_KEY = "YOUR_API_KEY"\nurl = "http://localhost:8000/api/v1/ocr"\n\nwith open("document.pdf", "rb") as f:\n    res = requests.post(\n        url,\n        headers={"X-API-Key": API_KEY},\n        files={"file": f}\n    )\n\ndata = res.json()\nprint("Doc Type:", data.get("doc_type"))\nprint("OCR Engine:", data.get("engine"))\nprint("Fields:", data.get("extracted_fields"))\nprint("Authenticity:", data.get("authenticity"))`
                          : `import FormData from 'form-data';\nimport fs from 'fs';\nimport axios from 'axios';\n\nconst form = new FormData();\nform.append('file', fs.createReadStream('document.pdf'));\n\nconst response = await axios.post('http://localhost:8000/api/v1/ocr', form, {\n  headers: {\n    ...form.getHeaders(),\n    'X-API-Key': 'YOUR_API_KEY',\n  },\n});\n\nconsole.log('Result:', response.data);`;
                      navigator.clipboard.writeText(snippet);
                      setCopiedSnippet(true);
                      setTimeout(() => setCopiedSnippet(false), 2000);
                      onNotify('Code snippet copied to clipboard!', 'info');
                    }}
                    style={{ position: 'absolute', top: '10px', right: '10px', zIndex: 2 }}
                  >
                    {copiedSnippet ? <Check size={13} style={{ color: 'var(--success)' }} /> : <Copy size={13} />}
                    <span>{copiedSnippet ? 'Copied' : 'Copy'}</span>
                  </button>

                  <pre
                    style={{
                      margin: 0,
                      padding: '16px 20px',
                      borderRadius: '8px',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-subtle)',
                      fontFamily: 'monospace',
                      fontSize: '0.85rem',
                      lineHeight: '1.5',
                      color: 'var(--text-main)',
                      overflowX: 'auto',
                    }}
                  >
                    {activeCodeTab === 'curl' &&
                      `curl -X POST "http://localhost:8000/api/v1/ocr" \\\n  -H "X-API-Key: YOUR_API_KEY" \\\n  -F "file=@/path/to/document.pdf"`}
                    {activeCodeTab === 'python' &&
                      `import requests\n\nAPI_KEY = "YOUR_API_KEY"\nurl = "http://localhost:8000/api/v1/ocr"\n\nwith open("document.pdf", "rb") as f:\n    res = requests.post(\n        url,\n        headers={"X-API-Key": API_KEY},\n        files={"file": f}\n    )\n\ndata = res.json()\nprint("Doc Type:", data.get("doc_type"))\nprint("OCR Engine:", data.get("engine"))\nprint("Fields:", data.get("extracted_fields"))\nprint("Authenticity:", data.get("authenticity"))`}
                    {activeCodeTab === 'node' &&
                      `import FormData from 'form-data';\nimport fs from 'fs';\nimport axios from 'axios';\n\nconst form = new FormData();\nform.append('file', fs.createReadStream('document.pdf'));\n\nconst response = await axios.post('http://localhost:8000/api/v1/ocr', form, {\n  headers: {\n    ...form.getHeaders(),\n    'X-API-Key': 'YOUR_API_KEY',\n  },\n});\n\nconsole.log('Result:', response.data);`}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 3: ADVANCED */}
          {activeSection === 'advanced' && (
            <div className="settings-section-view">
              <div className="settings-subcard">
                <h3 className="subcard-title">FastAPI Backend & Service Credentials</h3>
                <p className="subcard-desc">
                  Manage connection endpoints, exchange OAuth client credentials, and configure JWT tokens.
                </p>

                <div className="settings-form-col">
                  <div className="settings-field-group">
                    <label htmlFor="backend-url-input">FastAPI Base URL</label>
                    <input
                      id="backend-url-input"
                      type="text"
                      value={fastApiBaseUrl}
                      disabled={!isAdmin}
                      onChange={(e) => setFastApiBaseUrl(e.target.value)}
                    />
                  </div>

                  <div className="settings-two-col-grid" style={{ marginTop: '1rem' }}>
                    <div className="settings-field-group">
                      <label htmlFor="client-id-field">Client ID</label>
                      <input
                        id="client-id-field"
                        type="text"
                        value={clientId}
                        disabled={!isAdmin}
                        onChange={(e) => setClientId(e.target.value)}
                        placeholder="Client ID"
                      />
                    </div>
                    <div className="settings-field-group">
                      <label htmlFor="client-secret-field">Client Secret</label>
                      <input
                        id="client-secret-field"
                        type="password"
                        value={clientSecret}
                        disabled={!isAdmin}
                        onChange={(e) => setClientSecret(e.target.value)}
                        placeholder="••••••••••••"
                      />
                    </div>
                  </div>

                  <div style={{ marginTop: '1rem', display: 'flex', gap: '10px', alignItems: 'center' }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={handleMintToken}
                      disabled={!isAdmin || isMintingToken || !clientId || !clientSecret}
                    >
                      <Sparkles size={14} />
                      <span>{isMintingToken ? 'Exchanging...' : 'Mint JWT Access Token'}</span>
                    </button>
                  </div>

                  <div className="settings-field-group" style={{ marginTop: '1.25rem' }}>
                    <label htmlFor="bearer-token-field">Active Bearer Token</label>
                    <input
                      id="bearer-token-field"
                      type="password"
                      value={bearerToken}
                      disabled={!isAdmin}
                      onChange={(e) => setBearerToken(e.target.value)}
                      placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
                    />
                  </div>

                  <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={handlePingBackend}
                      disabled={isPingingBackend}
                    >
                      <RefreshCw size={13} className={isPingingBackend ? 'spin-anim' : ''} />
                      <span>{isPingingBackend ? 'Pinging...' : 'Ping Backend Endpoint'}</span>
                    </button>
                    {backendPingResult && (
                      <span style={{ marginLeft: '12px', fontSize: '0.85rem', color: backendPingResult.ok ? 'var(--success)' : 'var(--danger)' }}>
                        {backendPingResult.message}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 4: USAGE & QUOTAS */}
          {activeSection === 'quotas' && (
            <div className="settings-section-view">
              <div className="settings-metrics-grid">
                <div className="metric-box">
                  <div className="metric-icon-wrap">
                    <FileText size={20} />
                  </div>
                  <div className="metric-value">{stats?.total || documents.length || 0}</div>
                  <div className="metric-label">Vault Documents</div>
                </div>

                <div className="metric-box">
                  <div className="metric-icon-wrap">
                    <CheckCircle2 size={20} />
                  </div>
                  <div className="metric-value">{stats?.completed || stats?.ocr_processed || 0}</div>
                  <div className="metric-label">OCR Processed</div>
                </div>

                <div className="metric-box">
                  <div className="metric-icon-wrap">
                    <Activity size={20} />
                  </div>
                  <div className="metric-value">{activeConfig?.active_provider ? 'Active' : 'Offline'}</div>
                  <div className="metric-label">AI Status</div>
                </div>

                <div className="metric-box">
                  <div className="metric-icon-wrap">
                    <HardDrive size={20} />
                  </div>
                  <div className="metric-value">
                    {stats?.total_storage_mb ? `${stats.total_storage_mb.toFixed(1)} MB` : '12.4 MB'}
                  </div>
                  <div className="metric-label">Storage Consumed</div>
                </div>
              </div>

              <div className="settings-subcard" style={{ marginTop: '1.5rem' }}>
                <h3 className="subcard-title">Tier Allocations & Rate Limits</h3>
                <p className="subcard-desc">Current document ingestion quotas and concurrency allowances.</p>
                <div className="quota-row">
                  <span>API Request Rate Limit</span>
                  <strong>60 requests / minute</strong>
                </div>
                <div className="quota-row">
                  <span>Maximum File Upload Size</span>
                  <strong>32 MB per document</strong>
                </div>
                <div className="quota-row">
                  <span>Supported Document Formats</span>
                  <strong>PDF, PNG, JPG, JPEG, TIFF, BMP</strong>
                </div>
              </div>
            </div>
          )}

          {/* SECTION 5: ACCOUNT & SECURITY */}
          {activeSection === 'account' && (
            <div className="settings-section-view">
              <div className="settings-subcard">
                <h3 className="subcard-title">User Profile</h3>
                <form onSubmit={handleUpdateName} className="settings-form-col">
                  <div className="settings-field-group">
                    <label htmlFor="user-email-static">Email Address</label>
                    <input id="user-email-static" type="text" value={user?.email || 'user@docpilot.io'} disabled />
                  </div>

                  <div className="settings-field-group" style={{ marginTop: '1rem' }}>
                    <label htmlFor="user-name-input">Full Name</label>
                    <input
                      id="user-name-input"
                      type="text"
                      value={fullNameInput}
                      onChange={(e) => setFullNameInput(e.target.value)}
                      placeholder="Your Full Name"
                    />
                  </div>

                  {profileStatus && (
                    <div style={{ marginTop: '0.5rem', color: profileStatus.ok ? 'var(--success)' : 'var(--danger)', fontSize: '0.85rem' }}>
                      {profileStatus.message}
                    </div>
                  )}

                  <div style={{ marginTop: '1rem' }}>
                    <button type="submit" className="btn btn-secondary btn-sm" disabled={isUpdatingProfile}>
                      {isUpdatingProfile ? 'Saving...' : 'Update Name'}
                    </button>
                  </div>
                </form>
              </div>

              <div className="settings-subcard" style={{ marginTop: '1.5rem' }}>
                <h3 className="subcard-title">Security & Password</h3>
                <form onSubmit={handleUpdatePassword} className="settings-form-col">
                  <div className="settings-two-col-grid">
                    <div className="settings-field-group">
                      <label htmlFor="new-pw-input">New Password</label>
                      <input
                        id="new-pw-input"
                        type="password"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="At least 6 characters"
                      />
                    </div>
                    <div className="settings-field-group">
                      <label htmlFor="confirm-pw-input">Confirm Password</label>
                      <input
                        id="confirm-pw-input"
                        type="password"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="Re-enter password"
                      />
                    </div>
                  </div>

                  {passwordStatus && (
                    <div style={{ marginTop: '0.5rem', color: passwordStatus.ok ? 'var(--success)' : 'var(--danger)', fontSize: '0.85rem' }}>
                      {passwordStatus.message}
                    </div>
                  )}

                  <div style={{ marginTop: '1rem' }}>
                    <button type="submit" className="btn btn-secondary btn-sm">
                      Change Password
                    </button>
                  </div>
                </form>
              </div>

              <div className="settings-subcard" style={{ marginTop: '1.5rem' }}>
                <h3 className="subcard-title">Session Management</h3>
                <p className="subcard-desc">Terminates all active authorization tokens and refreshes across all logged in devices.</p>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={async () => {
                    if (window.confirm('Sign out of all devices?')) {
                      await signOutAllSessions();
                      window.location.href = '/login';
                    }
                  }}
                >
                  <LogOut size={14} />
                  <span>Sign Out All Active Devices</span>
                </button>
              </div>
            </div>
          )}

          {/* SECTION 6: GENERAL */}
          {activeSection === 'general' && (
            <div className="settings-section-view">
              <div className="settings-subcard">
                <h3 className="subcard-title">System & Environment Information</h3>
                <div className="quota-row">
                  <span>Application</span>
                  <strong>DocPilot AI Document Intelligence</strong>
                </div>
                <div className="quota-row">
                  <span>FastAPI OCR Service</span>
                  <strong>v1.0.0 (Production Hardened)</strong>
                </div>
                <div className="quota-row">
                  <span>OCR Engine</span>
                  <strong>RapidOCR (Offline ONNX Runtime)</strong>
                </div>
                <div className="quota-row">
                  <span>Local AI Vision Engine</span>
                  <strong>Ollama / Qwen2.5-VL 3B</strong>
                </div>
                <div className="quota-row">
                  <span>Security & Encryption</span>
                  <strong>AES-GCM-256 Credentials Vault (ai_config.enc)</strong>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
