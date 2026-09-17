import React from 'react';
import { FileText, UploadCloud, FolderArchive, BarChart3, Settings, ShieldCheck, Sparkles } from 'lucide-react';
import type { EngineInfo, AppMode } from '../types';

export type NavTab = 'dashboard' | 'upload' | 'repository' | 'analytics';

interface SidebarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  onOpenSettings: () => void;
  engineInfo?: EngineInfo | null;
  appMode: AppMode;
  onSelectMode: (mode: AppMode) => void;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  onOpenSettings,
  engineInfo,
  appMode,
  onSelectMode,
  isOpenMobile = false,
  onCloseMobile,
}) => {
  const engineDisplayName =
    engineInfo?.display_name ||
    (engineInfo?.active_engine === 'rapidocr'
      ? 'RapidOCR'
      : engineInfo?.active_engine === 'paddleocr'
      ? 'PaddleOCR'
      : engineInfo?.engine || 'RapidOCR');
  const deviceName = engineInfo?.device?.toUpperCase() || 'CPU';

  const handleTabClick = (tab: NavTab) => {
    onSelectTab(tab);
    if (onCloseMobile) onCloseMobile();
  };

  const handleModeClick = (mode: AppMode) => {
    onSelectMode(mode);
    if (onCloseMobile) onCloseMobile();
  };

  return (
    <>
      {/* Mobile Drawer Backdrop */}
      <div
        className={`sidebar-backdrop ${isOpenMobile ? 'active' : ''}`}
        onClick={onCloseMobile}
        aria-hidden="true"
      />

      <aside className={`sidebar ${isOpenMobile ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="brand-icon">
            <FileText size={20} />
          </div>
          <div>
            <div className="brand-title">DocuScan AI</div>
            <div className="brand-subtitle">
              {engineInfo ? `${engineDisplayName} Engine` : 'OCR Engine'}
            </div>
          </div>
        </div>

        {/* Mode Highlight in Sidebar */}
        <div className="sidebar-mode-section">
          <div className="sidebar-section-title">ACTIVE MODE</div>
          <div className="sidebar-mode-pills">
            <button
              className={`sidebar-mode-btn ${appMode === 'offline' ? 'active offline' : ''}`}
              onClick={() => handleModeClick('offline')}
              title="Offline Mode: 22 predefined document types via local PaddleOCR"
            >
              <ShieldCheck size={16} />
              <span>Offline Mode</span>
            </button>
            <button
              className={`sidebar-mode-btn ${appMode === 'ai' ? 'active ai' : ''}`}
              onClick={() => handleModeClick('ai')}
              title="AI Mode: Any document classification & interactive chat"
            >
              <Sparkles size={16} />
              <span>AI Mode</span>
            </button>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="sidebar-nav">
          <div className="sidebar-section-title" style={{ padding: '0 0.85rem', marginBottom: '0.4rem' }}>
            NAVIGATION
          </div>
          <button
            className={`nav-item ${currentTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => handleTabClick('dashboard')}
          >
            <BarChart3 size={18} />
            <span>Dashboard</span>
          </button>

          <button
            className={`nav-item ${currentTab === 'upload' ? 'active' : ''}`}
            onClick={() => handleTabClick('upload')}
          >
            <UploadCloud size={18} />
            <span>Upload & Ingest</span>
          </button>

          <button
            className={`nav-item ${currentTab === 'repository' ? 'active' : ''}`}
            onClick={() => handleTabClick('repository')}
          >
            <FolderArchive size={18} />
            <span>Document Vault</span>
          </button>
        </nav>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          <button
            className="nav-item"
            onClick={() => {
              onOpenSettings();
              if (onCloseMobile) onCloseMobile();
            }}
            style={{ width: '100%', justifyContent: 'flex-start' }}
          >
            <Settings size={18} />
            <span>API Connection</span>
          </button>
          <div style={{ padding: '0.75rem 0.85rem 0', fontSize: '0.74rem', color: 'var(--text-subtle)' }}>
            {engineInfo ? `${engineDisplayName} • ${deviceName}` : 'OCR Engine • RapidOCR'}
          </div>
        </div>
      </aside>
    </>
  );
};
