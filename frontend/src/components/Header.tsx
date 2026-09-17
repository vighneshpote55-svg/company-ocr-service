import React from 'react';
import { Settings, RefreshCw, LogOut, ShieldCheck, Sparkles, Menu, X } from 'lucide-react';
import type { AppMode } from '../types';

interface HeaderProps {
  mode: AppMode;
  onModeChange: (mode: AppMode) => void;
  isBackendConnected: boolean;
  onOpenSettings: () => void;
  onRefresh: () => void;
  onLogout?: () => void;
  isRefreshing?: boolean;
  onToggleMobileSidebar?: () => void;
  isMobileSidebarOpen?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  mode,
  onModeChange,
  isBackendConnected,
  onOpenSettings,
  onRefresh,
  onLogout,
  isRefreshing = false,
  onToggleMobileSidebar,
  isMobileSidebarOpen = false,
}) => {
  return (
    <header className="top-header">
      <div className="header-left-box">
        {onToggleMobileSidebar && (
          <button
            className="mobile-menu-btn"
            onClick={onToggleMobileSidebar}
            aria-label="Toggle navigation drawer"
          >
            {isMobileSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        )}

        <div className="header-title-box">
          <h1 className="page-title">Company OCR Service</h1>
          <span className="page-subtitle">Local OCR • AI Document Intelligence</span>
        </div>
      </div>

      {/* Centered Shared Mode Switch */}
      <div className="header-mode-switch-wrapper">
        <div className="header-mode-switch" role="tablist" aria-label="Mode selector">
          <button
            role="tab"
            aria-selected={mode === 'offline'}
            className={`header-mode-btn ${mode === 'offline' ? 'active-offline' : ''}`}
            onClick={() => onModeChange('offline')}
          >
            <ShieldCheck size={16} />
            <span>⚡ Offline Mode</span>
          </button>

          <button
            role="tab"
            aria-selected={mode === 'ai'}
            className={`header-mode-btn ${mode === 'ai' ? 'active-ai' : ''}`}
            onClick={() => onModeChange('ai')}
          >
            <Sparkles size={16} />
            <span>🤖 AI Mode</span>
          </button>
        </div>
      </div>

      {/* Header Actions */}
      <div className="header-actions">
        <div className={`status-pill ${isBackendConnected ? 'online' : 'offline'}`}>
          <span className="status-dot" />
          <span>{isBackendConnected ? 'Backend Connected' : 'Disconnected'}</span>
        </div>

        <button
          className="btn btn-secondary"
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Refresh statistics and documents"
          style={{ padding: '0.45rem 0.75rem' }}
        >
          <RefreshCw size={15} className={isRefreshing ? 'spin-anim' : ''} />
          <span style={{ fontSize: '0.8rem' }}>Sync</span>
        </button>

        <button
          className="btn btn-secondary"
          onClick={onOpenSettings}
          style={{ padding: '0.45rem 0.75rem' }}
          title="Server Settings"
        >
          <Settings size={15} />
          <span style={{ fontSize: '0.8rem' }}>Settings</span>
        </button>

        {onLogout && (
          <button
            className="btn btn-secondary"
            onClick={onLogout}
            style={{ padding: '0.45rem 0.75rem' }}
            title="Sign Out"
          >
            <LogOut size={15} color="var(--accent-rose)" />
            <span style={{ fontSize: '0.8rem' }}>Sign Out</span>
          </button>
        )}
      </div>
    </header>
  );
};
