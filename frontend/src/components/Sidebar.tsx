import React from 'react';
import {
  BarChart3,
  FolderArchive,
  ShieldCheck,
  Sparkles,
  Settings,
  ChevronLeft,
  ChevronRight,
  FileText,
  X,
  Cpu,
} from 'lucide-react';
import type { EngineInfo, AppMode } from '../types';

export type NavTab = 'dashboard' | 'repository';

interface SidebarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  onOpenSettings: () => void;
  engineInfo?: EngineInfo | null;
  appMode: AppMode;
  onSelectMode: (mode: AppMode) => void;
  isOpenMobile?: boolean;
  onCloseMobile?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
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
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const engineDisplayName =
    engineInfo?.display_name ||
    (engineInfo?.active_engine === 'rapidocr'
      ? 'RapidOCR'
      : engineInfo?.active_engine === 'paddleocr'
      ? 'PaddleOCR'
      : engineInfo?.engine || 'RapidOCR');
  const deviceName = engineInfo?.device?.toUpperCase() || 'CPU';

  const handleNavClick = (tab: NavTab) => {
    onSelectTab(tab);
    if (onCloseMobile) onCloseMobile();
  };

  const handleModeClick = (mode: AppMode) => {
    onSelectMode(mode);
    onSelectTab('dashboard');
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

      <aside className={`sidebar dark-floating-sidebar ${isCollapsed ? 'collapsed' : ''} ${isOpenMobile ? 'open' : ''}`}>
        {/* Sidebar Header */}
        <div className="sidebar-header">
          <div className="brand-logo-wrap">
            <div className="brand-icon">
              <FileText size={18} />
            </div>
            {!isCollapsed && (
              <div className="brand-info-wrap">
                <div className="brand-title">DocuScan Pro</div>
                <div className="brand-subtitle">{engineDisplayName} Core</div>
              </div>
            )}
          </div>

          {/* Desktop Collapse Toggle */}
          {onToggleCollapse && (
            <button
              className="sidebar-collapse-btn desktop-only"
              onClick={onToggleCollapse}
              title={isCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
              aria-label={isCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
            >
              {isCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            </button>
          )}

          {/* Mobile Close Button */}
          {onCloseMobile && (
            <button
              className="sidebar-close-btn mobile-only"
              onClick={onCloseMobile}
              aria-label="Close Sidebar"
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* Navigation Sections */}
        <div className="sidebar-scroll-area">
          <nav className="sidebar-nav" aria-label="Main Navigation">
            {/* 1. Dashboard */}
            <button
              className={`nav-pill-item ${currentTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => handleNavClick('dashboard')}
              title="Dashboard Overview"
            >
              <span className="active-blue-indicator" aria-hidden="true" />
              <span className="nav-pill-icon">
                <BarChart3 size={18} />
              </span>
              {!isCollapsed && <span className="nav-pill-label">Dashboard</span>}
            </button>

            {/* 2. Document Vault */}
            <button
              className={`nav-pill-item ${currentTab === 'repository' ? 'active' : ''}`}
              onClick={() => handleNavClick('repository')}
              title="Document Vault"
            >
              <span className="active-blue-indicator" aria-hidden="true" />
              <span className="nav-pill-icon">
                <FolderArchive size={18} />
              </span>
              {!isCollapsed && <span className="nav-pill-label">Document Vault</span>}
            </button>

            <div className="sidebar-divider" />

            {!isCollapsed && <div className="sidebar-section-heading">OPERATING MODES</div>}

            {/* 3. Offline Mode */}
            <button
              className={`nav-pill-item mode-item ${appMode === 'offline' && currentTab === 'dashboard' ? 'active offline-active' : ''}`}
              onClick={() => handleModeClick('offline')}
              title="Offline Mode (22 Local Document Types)"
            >
              <span className="active-blue-indicator" aria-hidden="true" />
              <span className="nav-pill-icon text-primary">
                <ShieldCheck size={18} />
              </span>
              {!isCollapsed && (
                <div className="nav-pill-label-group">
                  <span className="nav-pill-label">Offline Mode</span>
                  <span className="nav-pill-badge">22 Types</span>
                </div>
              )}
            </button>

            {/* 4. AI Mode */}
            <button
              className={`nav-pill-item mode-item ${appMode === 'ai' && currentTab === 'dashboard' ? 'active ai-active' : ''}`}
              onClick={() => handleModeClick('ai')}
              title="AI Mode (Intelligent Chat & Classification)"
            >
              <span className="active-blue-indicator" aria-hidden="true" />
              <span className="nav-pill-icon text-ai">
                <Sparkles size={18} />
              </span>
              {!isCollapsed && (
                <div className="nav-pill-label-group">
                  <span className="nav-pill-label">AI Mode</span>
                  <span className="nav-pill-badge ai-badge">Neural</span>
                </div>
              )}
            </button>
          </nav>
        </div>

        {/* Sidebar Footer */}
        <div className="sidebar-footer">
          {/* 5. Settings */}
          <button
            className="nav-pill-item settings-item"
            onClick={() => {
              onOpenSettings();
              if (onCloseMobile) onCloseMobile();
            }}
            title="Settings & API Configuration"
          >
            <span className="active-blue-indicator" aria-hidden="true" />
            <span className="nav-pill-icon">
              <Settings size={18} />
            </span>
            {!isCollapsed && <span className="nav-pill-label">Settings</span>}
          </button>

          {!isCollapsed && (
            <div className="sidebar-engine-tag">
              <Cpu size={13} className="engine-cpu-icon" />
              <span>{engineDisplayName} • {deviceName}</span>
            </div>
          )}
        </div>
      </aside>
    </>
  );
};
