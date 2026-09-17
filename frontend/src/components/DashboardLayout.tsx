import React, { useState } from 'react';
import type { AppMode, DashboardStats as StatsType, DocumentItem, EngineInfo, SupportedType } from '../types';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import type { NavTab } from './Sidebar';
import { DashboardStats } from './DashboardStats';
import { DocumentsTable } from './DocumentsTable';
import { UploadCard } from './UploadCard';
import { AIModeView } from './AIModeView';

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
  // Actions
  onDocumentUploaded: (doc: DocumentItem) => void;
  onDeleteDocument: (id: string) => void;
  onSelectDocument: (doc: DocumentItem) => void;
  onNotify: (message: string, type?: 'success' | 'error' | 'info') => void;
  // Optional inspection view when inspecting a single document
  selectedDoc?: DocumentItem | null;
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
  onDocumentUploaded,
  onDeleteDocument,
  onSelectDocument,
  onNotify,
  selectedDoc,
  inspectContent,
}) => {
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  return (
    <div className="app-layout">
      {/* Shared Sidebar */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={onSelectTab}
        onOpenSettings={onOpenSettings}
        engineInfo={engineInfo}
        appMode={mode}
        onSelectMode={onSelectMode}
        isOpenMobile={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />

      <div className="main-content">
        {/* Shared Header */}
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
        />

        <main className="content-body">
          {/* Inspection View if a document is selected */}
          {selectedDoc && inspectContent ? (
            inspectContent
          ) : currentTab === 'repository' ? (
            /* Document Vault Full Page */
            <div>
              <div style={{ marginBottom: '1.5rem' }}>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.35rem', color: 'var(--text-main)' }}>
                  Stored Document Vault
                </h2>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  Search, inspect, and retrieve previously processed documents with full verification metrics.
                </p>
              </div>

              <DocumentsTable
                documents={documents}
                supportedTypes={supportedTypes}
                onSelectDocument={onSelectDocument}
                onDeleteDocument={onDeleteDocument}
                onRefresh={onRefresh}
                isLoading={isRefreshing}
                engineInfo={engineInfo}
              />
            </div>
          ) : currentTab === 'upload' ? (
            /* Dedicated Upload Tab Workspace */
            <div className="workspace-container mode-fade-enter" key={mode}>
              {mode === 'offline' ? (
                <UploadCard
                  supportedTypes={supportedTypes}
                  onUploadSuccess={onDocumentUploaded}
                  onError={(msg) => onNotify(msg, 'error')}
                  onSwitchToAiMode={() => onSelectMode('ai')}
                />
              ) : (
                <AIModeView
                  onNotify={onNotify}
                  onSwitchToOffline={() => onSelectMode('offline')}
                />
              )}
            </div>
          ) : (
            /* Shared Dashboard: Stats -> Center Workspace -> Recent Documents */
            <>
              {/* Dashboard Stats (Identical in both modes) */}
              <DashboardStats
                stats={stats}
                engineInfo={engineInfo}
                documents={documents}
                onNavigateTab={(tab) => onSelectTab(tab)}
              />

              {/* Main Workspace Switching (UploadCard or AIModeView) */}
              <div className="workspace-container mode-fade-enter" key={mode}>
                {mode === 'offline' ? (
                  <UploadCard
                    supportedTypes={supportedTypes}
                    onUploadSuccess={onDocumentUploaded}
                    onError={(msg) => onNotify(msg, 'error')}
                    onSwitchToAiMode={() => onSelectMode('ai')}
                  />
                ) : (
                  <AIModeView
                    onNotify={onNotify}
                    onSwitchToOffline={() => onSelectMode('offline')}
                  />
                )}
              </div>

              {/* Recent Documents Table (Identical in both modes) */}
              <div style={{ marginTop: '2.5rem' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '1rem',
                  }}
                >
                  <h2 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-main)' }}>
                    Recent Document Ingestions
                  </h2>
                  <button
                    className="btn btn-ghost"
                    onClick={() => onSelectTab('repository')}
                    style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--primary)' }}
                  >
                    View All in Vault →
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
            </>
          )}
        </main>
      </div>
    </div>
  );
};
