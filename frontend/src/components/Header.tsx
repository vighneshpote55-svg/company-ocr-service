import React, { useState, useEffect, useRef } from 'react';
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
import { useAuth } from '../context/AuthContext';

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
  const { user, role, logout: authLogout } = useAuth();
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  const notificationsRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (notificationsRef.current && !notificationsRef.current.contains(target)) {
        setShowNotifications(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(target)) {
        setShowUserMenu(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowNotifications(false);
        setShowUserMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

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
          onClick={() => {
            setShowNotifications(false);
            setShowUserMenu(false);
            onRefresh();
          }}
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
            onClick={() => {
              setShowNotifications(false);
              setShowUserMenu(false);
              onToggleTheme();
            }}
            title={isDarkMode ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
            aria-label="Toggle dark/light theme"
          >
            {isDarkMode ? <Sun size={17} className="sun-icon" /> : <Moon size={17} />}
          </button>
        )}

        {/* Notification Bell / System Status Popover */}
        <div className="header-popover-container" ref={notificationsRef}>
          <button
            className="header-icon-btn notification-btn"
            onClick={() => {
              setShowNotifications((prev) => !prev);
              setShowUserMenu(false);
            }}
            title="System Activity & Notifications"
            aria-label="View notifications"
            aria-expanded={showNotifications}
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
          onClick={() => {
            setShowNotifications(false);
            setShowUserMenu(false);
            onOpenSettings();
          }}
          title="Server & Engine Settings"
          aria-label="Settings shortcut"
        >
          <Settings size={17} />
        </button>

        {/* User Profile Avatar */}
        <div className="header-popover-container" ref={userMenuRef}>
          <button
            className="user-profile-pill-btn"
            onClick={() => {
              setShowUserMenu((prev) => !prev);
              setShowNotifications(false);
            }}
            title="User Profile & Settings"
            aria-label="Open user menu"
            aria-expanded={showUserMenu}
          >
            <div className="user-avatar-circle">
              <User size={15} />
            </div>
            <span className="user-avatar-label">
              {user?.full_name ? user.full_name.split(' ')[0] : (user?.email ? user.email.split('@')[0] : 'User')}
            </span>
          </button>

          {showUserMenu && (
            <div className="header-dropdown-menu user-dropdown-menu">
              <div className="user-dropdown-info">
                <div className="flex items-center justify-between gap-2">
                  <div className="user-dropdown-name">{user?.full_name || 'Operator'}</div>
                  <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded ${role === 'admin' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'bg-slate-800 text-slate-400'}`}>
                    {role}
                  </span>
                </div>
                <div className="user-dropdown-email">{user?.email || 'authenticated'}</div>
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
              <div className="dropdown-divider" />
              <button
                className="dropdown-menu-action text-danger"
                onClick={async () => {
                  setShowUserMenu(false);
                  await authLogout();
                  if (onLogout) onLogout();
                }}
              >
                <LogOut size={15} />
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
