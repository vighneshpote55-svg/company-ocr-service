import React, { useState, useEffect } from 'react';
import { ShieldCheck } from 'lucide-react';
import type { AppMode, DashboardStats as StatsType, DocumentItem, EngineInfo, SupportedType, AIProviderConfig } from '../types';
import { useAuth } from '../context/AuthContext';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import type { NavTab } from './Sidebar';
import { DashboardStats } from './DashboardStats';
import { DocumentsTable } from './DocumentsTable';
import { UploadCard } from './UploadCard';
import { AIModeView } from './AIModeView';
import { PageHeader } from './PageHeader';

export interface DashboardLayoutProps {
  mode: AppMode;
  onSelectMode: (mode: AppMode) => void;
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  // Header controls
  isBackendConnected: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
  onOpenSettings: () => void;
  onLogout?: () => void;
  // Engine & Types
  engineInfo?: EngineInfo | null;
  supportedTypes: SupportedType[];
  // Stats & Documents
  stats: StatsType;
  documents: DocumentItem[];
  // AI Config & Refresh
  aiConfig?: AIProviderConfig | null;
  onRefreshAiConfig?: () => Promise<AIProviderConfig | null | void>;
  // Actions
  onDocumentUploaded: (doc: DocumentItem) => void;
  onDeleteDocument: (id: string) => void;
  onClearAll?: () => void;
  onSelectDocument: (doc: DocumentItem) => void;
  onNotify: (message: string, type?: 'success' | 'error' | 'info') => void;
  // Optional inspection view when inspecting a single document
  selectedDoc?: DocumentItem | null;
  onClearSelectedDoc?: () => void;
  inspectContent?: React.ReactNode;
}

export const DashboardLayout: React.FC<DashboardLayoutProps> = ({
  mode,
  onSelectMode,
  currentTab,
  onSelectTab,
  isBackendConnected,
  isRefreshing,
  onRefresh,
  onOpenSettings,
  onLogout,
  engineInfo,
  supportedTypes,
  stats,
  documents,
  aiConfig,
  onRefreshAiConfig,
  onDocumentUploaded,
  onDeleteDocument,
  onClearAll,
  onSelectDocument,
  onNotify,
  selectedDoc,
  onClearSelectedDoc,
  inspectContent,
}) => {
  const { user } = useAuth();
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('theme_preference');
      if (saved) return saved === 'dark';
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      if (isDarkMode) {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.documentElement.classList.add('dark');
        localStorage.setItem('theme_preference', 'dark');
      } else {
        document.documentElement.setAttribute('data-theme', 'light');
        document.documentElement.classList.remove('dark');
        localStorage.setItem('theme_preference', 'light');
      }
    } catch {
      // Ignore storage errors in restricted contexts
    }
  }, [isDarkMode]);

  const toggleTheme = () => {
    setIsDarkMode((prev) => !prev);
  };

  return (
    <div className={`app-layout ${isSidebarCollapsed ? 'layout-collapsed' : ''}`}>
      {/* Shared Sidebar with Collapsible & Mobile Drawer Support */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={onSelectTab}
        onOpenSettings={onOpenSettings}
        engineInfo={engineInfo}
        appMode={mode}
        onSelectMode={onSelectMode}
        isOpenMobile={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed((prev) => !prev)}
      />

      <div className={`main-content ${isSidebarCollapsed ? 'content-collapsed' : ''}`}>
        {/* Sticky Unified Top Header */}
        <Header
          mode={mode}
          onModeChange={onSelectMode}
          isBackendConnected={isBackendConnected}
          onOpenSettings={onOpenSettings}
          onRefresh={onRefresh}
          onLogout={onLogout}
          isRefreshing={isRefreshing}
          onToggleMobileSidebar={() => setIsMobileSidebarOpen((prev) => !prev)}
          isMobileSidebarOpen={isMobileSidebarOpen}
          isDarkMode={isDarkMode}
          onToggleTheme={toggleTheme}
        />

        <main className="content-body">
          {/* 1. Document Inspection Mode: strictly for Offline Mode verification */}
          {selectedDoc && inspectContent && mode === 'offline' ? (
            inspectContent
          ) : currentTab === 'repository' ? (
            /* 2. Document Vault Full View */
            <div className="vault-view-wrapper mode-fade-enter">
              <PageHeader
                title="Document Vault"
                subtitle="Secure document repository with cryptographic checksums and verification histories."
              />

              <DocumentsTable
                documents={documents}
                supportedTypes={supportedTypes}
                onSelectDocument={onSelectDocument}
                onDeleteDocument={onDeleteDocument}
                onClearAll={onClearAll}
                onRefresh={onRefresh}
                isLoading={isRefreshing}
                engineInfo={engineInfo}
              />
            </div>
          ) : mode === 'ai' ? (
            /* 3. DocPilot AI Mode: Dedicated Full-screen Document Intelligence Workspace */
            <div className="docpilot-fullscreen-workspace-wrapper mode-fade-enter">
              <AIModeView
                onNotify={onNotify}
                onSwitchToOffline={() => onSelectMode('offline')}
                onRefresh={onRefresh}
                onDocumentUploaded={onDocumentUploaded}
                aiConfig={aiConfig}
                onRefreshAiConfig={onRefreshAiConfig}
                selectedDoc={selectedDoc}
                onClearSelectedDoc={onClearSelectedDoc}
              />
            </div>
          ) : (
            /* 4. Offline Mode Primary Dashboard: Welcome Banner -> Stats -> Centered Workspace -> Recent Ingestions */
            <div className="dashboard-view-wrapper">
              {/* Personalized Welcome Banner */}
              <div className="dashboard-welcome-banner">
                <div className="welcome-banner-text">
                  <h2 className="welcome-banner-title">
                    Welcome back, {user?.full_name || user?.email?.split('@')[0] || 'Member'} 👋
                  </h2>
                  <p className="welcome-banner-subtitle">
                    Multi-tenant workspace with isolated Document Vault, deterministic RapidOCR, and contextual AI reasoning.
                  </p>
                </div>
                <div className="welcome-banner-badge">
                  <ShieldCheck size={16} />
                  <span>Secure Tenant Isolation</span>
                </div>
              </div>

              {/* Dashboard Metric Cards (4 cards: Total, Offline, AI, Storage) */}
              <DashboardStats
                stats={stats}
                engineInfo={engineInfo}
                documents={documents}
                aiConfig={aiConfig}
                onNavigateTab={(tab) => onSelectTab(tab)}
              />

              {/* Centered Large Workspace Card (Offline Mode Upload Card) */}
              <div className="main-workspace-card-wrapper mode-fade-enter" key={mode}>
                <UploadCard
                  supportedTypes={supportedTypes}
                  onUploadSuccess={onDocumentUploaded}
                  onError={(msg) => onNotify(msg, 'error')}
                  onSwitchToAiMode={() => onSelectMode('ai')}
                  onRefresh={onRefresh}
                />
              </div>

              {/* Recent Ingestions Table */}
              <div className="recent-documents-section">
                <div className="recent-section-header">
                  <div>
                    <h3 className="recent-section-title">Recent Ingestions</h3>
                    <p className="recent-section-subtitle">
                      Latest documents verified across active pipelines
                    </p>
                  </div>
                  <button
                    className="btn btn-ghost view-vault-link-btn"
                    onClick={() => onSelectTab('repository')}
                  >
                    <span>View all in Document Vault</span>
                    <span aria-hidden="true">→</span>
                  </button>
                </div>

                <DocumentsTable
                  documents={documents.slice(0, 5)}
                  supportedTypes={supportedTypes}
                  onSelectDocument={onSelectDocument}
                  onDeleteDocument={onDeleteDocument}
                  onRefresh={onRefresh}
                  isLoading={isRefreshing}
                  engineInfo={engineInfo}
                />
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
