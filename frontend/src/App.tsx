import React, { useState, useEffect, useCallback } from 'react';
import {
  FileText,
  FileCode,
  ShieldCheck,
  ArrowLeft,
  Share2,
} from 'lucide-react';

import type { DocumentItem, SupportedType, DashboardStats as StatsType, EngineInfo, AppMode, AIProviderConfig } from './types';
import { normalizeAiDocument } from './types';
import { api } from './services/api';
import { DashboardLayout } from './components/DashboardLayout';
import { ErrorBoundary } from './components/ErrorBoundary';
import type { NavTab } from './components/Sidebar';
import { OcrDecisionBadge } from './components/OcrDecisionBadge';
import { DocumentPreview } from './components/DocumentPreview';
import { ExtractedFields } from './components/ExtractedFields';
import { ExtractedTextViewer } from './components/ExtractedTextViewer';
import { JsonResultViewer } from './components/JsonResultViewer';
import { SettingsModal } from './components/SettingsModal';
import { ConfirmClearModal } from './components/ConfirmClearModal';
import { LoginView } from './components/LoginView';
import { Toast } from './components/Toast';
import type { ToastMessage } from './components/Toast';

type InspectTab = 'fields' | 'text' | 'json';

export const App: React.FC = () => {
  const [appMode, setAppMode] = useState<AppMode>('offline');
  const [currentTab, setCurrentTab] = useState<NavTab>('dashboard');
  const [inspectTab, setInspectTab] = useState<InspectTab>('fields');
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);

  const [supportedTypes, setSupportedTypes] = useState<SupportedType[]>([]);
  const [engineInfo, setEngineInfo] = useState<EngineInfo | null>(null);
  const [aiConfig, setAiConfig] = useState<AIProviderConfig | null>(null);
  const [stats, setStats] = useState<StatsType>({
    total: 0,
    ocr_processed: 0,
    ocr_not_required: 0,
    completed: 0,
    failed: 0,
  });
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [authEnabled, setAuthEnabled] = useState<boolean>(false);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(api.isAuthenticated());
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isClearModalOpen, setIsClearModalOpen] = useState<boolean>(false);
  const [isClearingVault, setIsClearingVault] = useState<boolean>(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const refreshAiConfig = useCallback(async () => {
    try {
      const cfg = await api.getAiConfig();
      setAiConfig(cfg);
      return cfg;
    } catch (err) {
      console.warn('Could not load AI configuration:', err);
      return null;
    }
  }, []);

  const addToast = (message: string, type: 'success' | 'error' | 'info' = 'success') => {
    const id = String(Date.now());
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const loadData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      // 1. Check health & dynamic backend auth status
      await api.checkHealth();
      setIsBackendConnected(true);

      const [authStatus, typesData, engineData, aiCfgData] = await Promise.all([
        api.checkAuthStatus().catch(() => ({ auth_enabled: false, auth_mode: 'disabled' })),
        api.getSupportedTypes().catch(() => []),
        api.getEngineInfo().catch(() => null),
        api.getAiConfig().catch(() => null),
      ]);

      const isEnabled = Boolean(authStatus.auth_enabled);
      setAuthEnabled(isEnabled);
      const authed = api.isAuthenticated();
      setIsAuthenticated(authed);

      setSupportedTypes(typesData);
      if (engineData) setEngineInfo(engineData);
      if (aiCfgData) setAiConfig(aiCfgData);

      // Only fetch protected data if not gated by enabled auth
      if (isEnabled && !authed) {
        return;
      }

      // 2. Fetch protected stats and documents in parallel
      const [statsData, docsData] = await Promise.all([
        api.getStats().catch(() => ({
          total: 0,
          ocr_processed: 0,
          ocr_not_required: 0,
          completed: 0,
          failed: 0,
        })),
        api.getDocuments({ limit: 200 }).catch(() => ({ items: [], total: 0 })),
      ]);

      setStats(statsData);
      if (docsData && Array.isArray(docsData.items)) {
        setDocuments(docsData.items);
      }
    } catch (err: any) {
      setIsBackendConnected(false);
      addToast('Cannot connect to FastAPI OCR server. Check settings or start backend.', 'error');
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const unsubscribeAuth = api.onUnauthorized(() => {
      if (api.isAuthEnabled()) {
        setIsAuthenticated(false);
        addToast('Session expired or unauthorized. Please sign in again.', 'info');
      }
    });

    loadData();

    // Periodic health poll every 25 seconds
    const interval = setInterval(async () => {
      try {
        await api.checkHealth();
        setIsBackendConnected(true);
      } catch {
        setIsBackendConnected(false);
      }
    }, 25000);

    return () => {
      unsubscribeAuth();
      clearInterval(interval);
    };
  }, [loadData]);

  const handleDocumentUploaded = (doc: DocumentItem) => {
    console.error('[App] handleDocumentUploaded received document payload:', doc);
    const normalized = normalizeAiDocument(doc);
    console.error('[App] handleDocumentUploaded normalized document:', normalized);

    // In Offline Mode, immediately route to the inspection view.
    // In AI Mode, keep the user in the rich AIModeView workspace.
    if (appMode === 'offline') {
      setSelectedDoc(normalized);
      setInspectTab('fields');
    }
    addToast(`Successfully processed "${normalized.filename}"!`, 'success');

    // Ensure new upload does not replace previous vault records with only the newest document
    setDocuments((prev) => {
      const exists = prev.some((d) => d.id === normalized.id);
      return exists ? prev.map((d) => (d.id === normalized.id ? normalized : d)) : [normalized, ...prev];
    });
    loadData();
  };

  const handleDeleteDocument = async (id: string) => {
    try {
      const ok = await api.deleteDocument(id);
      if (ok) {
        addToast('Document deleted from vault', 'success');
        if (selectedDoc?.id === id) {
          setSelectedDoc(null);
        }
        loadData();
      }
    } catch (err: any) {
      addToast(`Delete failed: ${err.message}`, 'error');
    }
  };

  const handleClearAllDocuments = async () => {
    setIsClearingVault(true);
    try {
      const res = await api.clearAllDocuments();
      if (res.success) {
        setIsClearModalOpen(false);
        if (selectedDoc) {
          setSelectedDoc(null);
        }
        addToast('All documents deleted successfully.', 'success');
        await loadData();
      } else {
        addToast(res.message || 'Failed to delete documents', 'error');
      }
    } catch (err: any) {
      addToast(`Failed to delete documents: ${err.message || err}`, 'error');
    } finally {
      setIsClearingVault(false);
    }
  };


  // Only gate the dashboard if the backend actually reports auth is enabled AND user has no valid token
  if (authEnabled && !isAuthenticated) {
    return (
      <>
        <LoginView
          onLoginSuccess={() => {
            setIsAuthenticated(true);
            loadData();
          }}
        />
        <Toast toasts={toasts} onDismiss={removeToast} />
      </>
    );
  }

  // Document Inspection Component View
  const renderInspectionContent = () => {
    if (!selectedDoc) return null;

    return (
      <div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '1.25rem',
          }}
        >
          <button
            className="btn btn-secondary"
            onClick={() => setSelectedDoc(null)}
            style={{ padding: '0.45rem 0.85rem' }}
          >
            <ArrowLeft size={16} />
            <span>Back to {currentTab === 'repository' ? 'Document Vault' : 'Dashboard'}</span>
          </button>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn btn-secondary"
              onClick={() => {
                navigator.clipboard.writeText(window.location.href);
                addToast('Inspection link copied', 'info');
              }}
              style={{ padding: '0.45rem 0.85rem' }}
            >
              <Share2 size={15} />
              <span>Share</span>
            </button>

            <button
              className="btn btn-danger"
              onClick={() => {
                if (window.confirm(`Delete "${selectedDoc.filename}" from vault?`)) {
                  handleDeleteDocument(selectedDoc.id);
                }
              }}
              style={{ padding: '0.45rem 0.85rem' }}
            >
              <span>Delete</span>
            </button>
          </div>
        </div>

        {/* Decision Banner */}
        <OcrDecisionBadge document={selectedDoc} engineInfo={engineInfo} />

        {/* 2-Column Inspection Grid */}
        <div className="result-grid">
          {/* Left Column: Visual Document Preview */}
          <DocumentPreview document={selectedDoc} />

          {/* Right Column: Tabbed Inspector */}
          <div className="inspect-panel">
            <div className="tabs-nav">
              <button
                className={`tab-btn ${inspectTab === 'fields' ? 'active' : ''}`}
                onClick={() => setInspectTab('fields')}
              >
                <ShieldCheck size={16} />
                <span>Extracted Fields</span>
              </button>

              <button
                className={`tab-btn ${inspectTab === 'text' ? 'active' : ''}`}
                onClick={() => setInspectTab('text')}
              >
                <FileText size={16} />
                <span>Extracted Text ({selectedDoc.extracted_text?.length || 0} chars)</span>
              </button>

              <button
                className={`tab-btn ${inspectTab === 'json' ? 'active' : ''}`}
                onClick={() => setInspectTab('json')}
              >
                <FileCode size={16} />
                <span>Raw JSON Payload</span>
              </button>
            </div>

            <div className="tab-content">
              {inspectTab === 'fields' && (
                <ExtractedFields
                  document={selectedDoc}
                  onCopyToast={addToast}
                  onSwitchToAiMode={() => setAppMode('ai')}
                />
              )}

              {inspectTab === 'text' && (
                <ExtractedTextViewer
                  text={selectedDoc.extracted_text}
                  filename={selectedDoc.filename}
                  onCopyToast={addToast}
                />
              )}

              {inspectTab === 'json' && (
                <JsonResultViewer document={selectedDoc} onCopyToast={addToast} />
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <ErrorBoundary>
      <DashboardLayout
        mode={appMode}
        onSelectMode={(mode) => {
          setAppMode(mode);
          setSelectedDoc(null);
          loadData();
          refreshAiConfig();
        }}
        currentTab={currentTab}
        onSelectTab={(tab) => {
          setCurrentTab(tab);
          setSelectedDoc(null);
          loadData();
          refreshAiConfig();
        }}
        isBackendConnected={isBackendConnected}
        isRefreshing={isRefreshing}
        onRefresh={() => {
          loadData();
          refreshAiConfig();
        }}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onLogout={
          authEnabled
            ? () => {
                api.logout();
                setIsAuthenticated(false);
                addToast('Signed out successfully.', 'info');
              }
            : undefined
        }
        engineInfo={engineInfo}
        supportedTypes={supportedTypes}
        stats={stats}
        documents={documents}
        aiConfig={aiConfig}
        onRefreshAiConfig={refreshAiConfig}
        onDocumentUploaded={handleDocumentUploaded}
        onDeleteDocument={handleDeleteDocument}
        onClearAll={() => setIsClearModalOpen(true)}
        onSelectDocument={(doc) => {
          setSelectedDoc(doc);
          if (appMode === 'ai') {
            setCurrentTab('dashboard');
          }
        }}
        onClearSelectedDoc={() => setSelectedDoc(null)}
        onNotify={addToast}
        selectedDoc={selectedDoc}
        inspectContent={renderInspectionContent()}
      />

      {/* Clear All Confirmation Modal */}
      <ConfirmClearModal
        isOpen={isClearModalOpen}
        onClose={() => setIsClearModalOpen(false)}
        onConfirm={handleClearAllDocuments}
        isDeleting={isClearingVault}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        onSaved={async () => {
          addToast('Settings saved. Refreshing data...', 'info');
          await Promise.all([
            loadData(),
            refreshAiConfig(),
          ]);
        }}
      />

      {/* Toast Notifications */}
      <Toast toasts={toasts} onDismiss={removeToast} />
    </ErrorBoundary>
  );
};

export default App;
