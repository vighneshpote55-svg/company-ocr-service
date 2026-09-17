import React, { useState } from 'react';
import {
  RefreshCw,
  LogOut,
  Menu,
  X,
  Sun,
  Moon,
  Bell,
  User,
  Settings,
  CheckCircle2,
  SlidersHorizontal,
} from 'lucide-react';
import type { AppMode } from '../types';
import { ModeSwitcher } from './ModeSwitcher';

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
  isDarkMode?: boolean;
  onToggleTheme?: () => void;
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
  isDarkMode = false,
  onToggleTheme,
}) => {
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  return (
    <header className="top-header glass-header">
      {/* Left: Branding */}
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

      {/* Center: Mode Switcher (identical position in both modes) */}
      <div className="header-mode-switch-wrapper">
        <ModeSwitcher mode={mode} onModeChange={onModeChange} />
      </div>

      {/* Right: Notifications, Theme Toggle, Settings Shortcut, User Profile */}
      <div className="header-right-box">
        {/* Backend Status Dot */}
        <div
          className={`status-pill ${isBackendConnected ? 'online' : 'offline'}`}
          title={isBackendConnected ? 'FastAPI Neural Backend connected' : 'Backend offline'}
        >
          <span className="status-dot" />
          <span className="status-text">{isBackendConnected ? 'Online' : 'Offline'}</span>
        </div>

        {/* Sync Refresh Button */}
        <button
          className="header-icon-btn"
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Synchronize vault data and metrics"
          aria-label="Synchronize data"
        >
          <RefreshCw size={17} className={isRefreshing ? 'spin-anim' : ''} />
        </button>

        {/* Theme Toggle Button */}
        {onToggleTheme && (
          <button
            className="header-icon-btn theme-toggle-btn"
            onClick={onToggleTheme}
            title={isDarkMode ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
            aria-label="Toggle dark/light theme"
          >
            {isDarkMode ? <Sun size={17} className="sun-icon" /> : <Moon size={17} />}
          </button>
        )}

        {/* Notification Bell */}
        <div className="header-popover-container">
          <button
            className="header-icon-btn notification-btn"
            onClick={() => {
              setShowNotifications(!showNotifications);
              setShowUserMenu(false);
            }}
            title="System Activity & Notifications"
            aria-label="View notifications"
          >
            <Bell size={17} />
            <span className="notification-indicator" />
          </button>

          {showNotifications && (
            <div className="header-dropdown-menu notification-menu">
              <div className="dropdown-header">
                <span className="dropdown-title">System Status</span>
                <span className="dropdown-tag">Healthy</span>
              </div>
              <div className="dropdown-list">
                <div className="dropdown-item">
                  <CheckCircle2 size={16} color="var(--success)" className="dropdown-item-icon" />
                  <div>
                    <p className="dropdown-item-title">Neural Engine Operational</p>
                    <span className="dropdown-item-time">Local OCR & PII Guard active</span>
                  </div>
                </div>
                <div className="dropdown-item">
                  <SlidersHorizontal size={16} color="var(--primary)" className="dropdown-item-icon" />
                  <div>
                    <p className="dropdown-item-title">22 Document Classifiers Ready</p>
                    <span className="dropdown-item-time">Zero cloud dependency</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Settings Shortcut */}
        <button
          className="header-icon-btn settings-shortcut-btn"
          onClick={onOpenSettings}
          title="Server & Engine Settings"
          aria-label="Settings shortcut"
        >
          <Settings size={17} />
        </button>

        {/* User Profile Avatar */}
        <div className="header-popover-container">
          <button
            className="user-profile-pill-btn"
            onClick={() => {
              setShowUserMenu(!showUserMenu);
              setShowNotifications(false);
            }}
            title="User Profile & Settings"
            aria-label="Open user menu"
          >
            <div className="user-avatar-circle">
              <User size={15} />
            </div>
            <span className="user-avatar-label">User Profile</span>
          </button>

          {showUserMenu && (
            <div className="header-dropdown-menu user-dropdown-menu">
              <div className="user-dropdown-info">
                <div className="user-dropdown-name">Enterprise Operator</div>
                <div className="user-dropdown-email">operator@company-ocr.internal</div>
              </div>
              <div className="dropdown-divider" />
              <button
                className="dropdown-menu-action"
                onClick={() => {
                  setShowUserMenu(false);
                  onOpenSettings();
                }}
              >
                <Settings size={15} />
                <span>Engine & Network Configuration</span>
              </button>
              {onLogout && (
                <>
                  <div className="dropdown-divider" />
                  <button
                    className="dropdown-menu-action text-danger"
                    onClick={() => {
                      setShowUserMenu(false);
                      onLogout();
                    }}
                  >
                    <LogOut size={15} />
                    <span>Sign Out</span>
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
