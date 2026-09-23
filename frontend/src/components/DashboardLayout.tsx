import React, { useState, useEffect } from 'react';
import { FileText, Clock, Eye, ArrowRight } from 'lucide-react';
import type { AppMode, DashboardStats as StatsType, DocumentItem, EngineInfo, SupportedType, AIProviderConfig } from '../types';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import type { NavTab } from './Sidebar';
import { DashboardStats } from './DashboardStats';
import { DocumentsTable } from './DocumentsTable';
import { UploadCard } from './UploadCard';
import { AIModeView } from './AIModeView';
import { PageHeader } from './PageHeader';
import { SettingsPage } from './SettingsPage';

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

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return 'Recently';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return 'Recently';
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch {
    return 'Recently';
  }
}

function getDocStatusBadge(doc: DocumentItem): { label: string; colorClass: string } {
  if (doc.status === 'failed' || doc.status === 'error') {
    return { label: 'Failed', colorClass: 'pill-failed' };
  }
  if (doc.status === 'processing') {
    return { label: 'Processing', colorClass: 'pill-processing' };
  }
  if (doc.verification_status === 'review_required' || doc.review_required) {
    return { label: 'Review Required', colorClass: 'pill-review' };
  }
  return { label: 'Verified', colorClass: 'pill-verified' };
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

        <main className={`content-body ${currentTab === 'settings' ? 'content-body-settings' : ''}`}>
          {/* 1. Document Inspection Mode: strictly for Offline Mode verification */}
          {selectedDoc && inspectContent && mode === 'offline' ? (
            inspectContent
          ) : currentTab === 'settings' ? (
            /* Settings Full-Page System */
            <SettingsPage
              onNotify={onNotify}
              onRefreshAiConfig={onRefreshAiConfig}
              stats={stats}
              documents={documents}
            />
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
            /* 4. Offline Mode Primary Dashboard: Welcome Banner -> Stats -> 2-Column Responsive Grid */
            <div className="dashboard-view-wrapper">
              {/* Simplified Welcome Banner */}
              <div className="dashboard-welcome-banner">
                <div className="welcome-banner-text">
                  <h2 className="welcome-banner-title">
                    Welcome back, Incraax Automation 👋
                  </h2>
                  <p className="welcome-banner-subtitle">
                    Manage your documents, run OCR, and analyze them with AI.
                  </p>
                </div>
              </div>

              {/* Dashboard Metric Cards (5 cards in one balanced row) */}
              <DashboardStats
                stats={stats}
                engineInfo={engineInfo}
                documents={documents}
                aiConfig={aiConfig}
                onNavigateTab={(tab) => onSelectTab(tab)}
              />

              {/* Primary Dashboard Grid: 2-Column Split (Offline OCR Upload + Recent Documents) */}
              <div className="dashboard-content-split">
                {/* Left Column: Primary Offline OCR Action */}
                <div className="dashboard-primary-column">
                  <UploadCard
                    supportedTypes={supportedTypes}
                    onUploadSuccess={onDocumentUploaded}
                    onError={(msg) => onNotify(msg, 'error')}
                    onSwitchToAiMode={() => onSelectMode('ai')}
                    onRefresh={onRefresh}
                  />
                </div>

                {/* Right Column: Recent Documents Feed */}
                <div className="dashboard-secondary-column">
                  <div className="recent-docs-card">
                    <div className="recent-card-header">
                      <div className="recent-card-title-wrap">
                        <h3 className="recent-card-title">Recent Documents</h3>
                        <span className="recent-count-tag">{documents.length}</span>
                      </div>
                      <button
                        type="button"
                        className="btn-link view-all-btn"
                        onClick={() => onSelectTab('repository')}
                        title="View all documents in Vault"
                      >
                        <span>View all</span>
                        <ArrowRight size={13} />
                      </button>
                    </div>

                    <div className="recent-docs-list">
                      {documents.length === 0 ? (
                        <div className="recent-docs-empty">
                          <FileText size={32} className="empty-icon" />
                          <p className="empty-title">No documents yet</p>
                          <p className="empty-desc">
                            Ingested files will appear here for fast inspection.
                          </p>
                        </div>
                      ) : (
                        documents.slice(0, 5).map((doc) => {
                          const statusInfo = getDocStatusBadge(doc);
                          return (
                            <div
                              key={doc.id}
                              className="recent-doc-row"
                              onClick={() => onSelectDocument(doc)}
                              role="button"
                              tabIndex={0}
                              title={`Inspect ${doc.filename}`}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault();
                                  onSelectDocument(doc);
                                }
                              }}
                            >
                              <div className="recent-doc-icon-wrap">
                                <FileText size={18} />
                              </div>
                              <div className="recent-doc-details">
                                <div className="recent-doc-name" title={doc.filename}>
                                  {doc.filename}
                                </div>
                                <div className="recent-doc-meta">
                                  <span className="recent-doc-time">
                                    <Clock size={11} />
                                    {formatRelativeTime(doc.created_at || (doc as any).timestamp)}
                                  </span>
                                  <span className={`recent-doc-status-pill ${statusInfo.colorClass}`}>
                                    {statusInfo.label}
                                  </span>
                                </div>
                              </div>
                              <button
                                type="button"
                                className="recent-doc-view-btn"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onSelectDocument(doc);
                                }}
                                title="Inspect document"
                                aria-label={`Inspect ${doc.filename}`}
                              >
                                <Eye size={15} />
                              </button>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
