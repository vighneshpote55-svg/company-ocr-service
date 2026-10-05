import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  Bell,
  Sun,
  Moon,
  Settings,
  RefreshCw,
  LogOut,
  Menu,
  X,
  Sparkles,
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
  const { user, logout: authLogout } = useAuth();
  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [uiScale, setUiScale] = useState<string>(() => {
    try {
      return localStorage.getItem('ui_scaling_preference') || '100';
    } catch {
      return '100';
    }
  });

  const handleCycleScale = () => {
    const next = uiScale === '100' ? '125' : uiScale === '125' ? '150' : '100';
    setUiScale(next);
    try {
      localStorage.setItem('ui_scaling_preference', next);
      const ratio = next === '100' ? 1 : Number(next) / 100;
      (document.documentElement.style as any).zoom = ratio === 1 ? '' : String(ratio);
      window.dispatchEvent(new CustomEvent('docpilot_scale_changed', { detail: next }));
    } catch {
      // safe swallow
    }
  };

  useEffect(() => {
    const handleScaleEvent = (e: any) => {
      if (e.detail) setUiScale(e.detail);
    };
    window.addEventListener('docpilot_scale_changed', handleScaleEvent);
    return () => window.removeEventListener('docpilot_scale_changed', handleScaleEvent);
  }, []);

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

  const displayName = user?.full_name || (user?.email ? user.email.split('@')[0] : 'Sarah J.');

  return (
    <header className="top-header docpilot-top-header">
      {/* Left: Mobile Drawer Button & [←] DocPilot Back Link */}
      <div className="docpilot-header-left">
        {onToggleMobileSidebar && (
          <button
            className="mobile-menu-btn"
            onClick={onToggleMobileSidebar}
            aria-label="Toggle navigation drawer"
          >
            {isMobileSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        )}

        <div className="docpilot-header-breadcrumb">
          <button
            type="button"
            className="docpilot-header-back-btn"
            onClick={onRefresh}
            title="DocPilot Workspace"
          >
            <ArrowLeft size={16} />
            <span>DocPilot</span>
          </button>
        </div>
      </div>

      {/* Center: Mode Switcher (Seamless toggle between Offline & AI Mode) */}
      <div className="docpilot-header-center">
        <ModeSwitcher mode={mode} onModeChange={onModeChange} />
        {mode === 'ai' && (
          <span className="docpilot-header-ai-pill">
            <Sparkles size={13} />
            <span>DocPilot AI Mode</span>
          </span>
        )}
      </div>

      {/* Right: Notification Bell, Refresh, Theme Toggle, Settings, Profile Avatar */}
      <div className="docpilot-header-right">
        {/* Notifications Icon Button */}
        <div className="header-popover-container" ref={notificationsRef}>
          <button
            className="docpilot-header-icon-btn"
            onClick={() => {
              setShowNotifications((prev) => !prev);
              setShowUserMenu(false);
            }}
            title="Notifications"
            aria-label="Notifications"
          >
            <Bell size={17} />
            <span className="docpilot-notification-dot" />
          </button>

          {showNotifications && (
            <div className="header-dropdown-menu notifications-dropdown">
              <div className="dropdown-header">
                <span className="dropdown-title">Notifications</span>
                <span className="dropdown-tag">2 New</span>
              </div>
              <div className="dropdown-list">
                <div className="dropdown-item unread">
                  <div className="dropdown-item-dot" />
                  <div>
                    <p className="dropdown-item-title">Security Audit Report Indexed</p>
                    <span className="dropdown-item-time">2 mins ago • AI Mode</span>
                  </div>
                </div>
                <div className="dropdown-item unread">
                  <div className="dropdown-item-dot" />
                  <div>
                    <p className="dropdown-item-title">Cryptographic Checksum Verified</p>
                    <span className="dropdown-item-time">10 mins ago • Clean</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Sync / Refresh */}
        <button
          className="docpilot-header-icon-btn"
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Synchronize Data"
          aria-label="Synchronize Data"
        >
          <RefreshCw size={15} className={isRefreshing ? 'spin-anim' : ''} />
        </button>

        {/* Theme Toggle */}
        {onToggleTheme && (
          <button
            className="docpilot-header-icon-btn"
            onClick={onToggleTheme}
            title={isDarkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            aria-label="Toggle Theme"
          >
            {isDarkMode ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        )}

        {/* UI Scale / Zoom Adjustment Button */}
        <button
          className="docpilot-header-icon-btn scale-toggle-btn"
          onClick={handleCycleScale}
          title={`Interface Scaling: ${uiScale}% (Click to cycle: 100% → 125% → 150%)`}
          aria-label="Adjust Interface Scaling"
        >
          <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '-0.02em' }}>
            {uiScale}%
          </span>
        </button>

        {/* Settings */}
        <button
          className="docpilot-header-icon-btn"
          onClick={onOpenSettings}
          title="Settings"
          aria-label="Settings"
        >
          <Settings size={16} />
        </button>

        {/* User Profile Avatar with Online Indicator */}
        <div className="header-popover-container" ref={userMenuRef}>
          <div
            className="docpilot-header-avatar-wrap"
            onClick={() => {
              setShowUserMenu((prev) => !prev);
              setShowNotifications(false);
            }}
            style={{ cursor: 'pointer' }}
            title={`${displayName} (Admin)`}
          >
            <div className="docpilot-header-avatar">
              {displayName.charAt(0).toUpperCase()}
            </div>
            <span
              className="docpilot-avatar-online-dot"
              style={{
                background: isBackendConnected ? '#10B981' : '#EF4444',
              }}
            />
          </div>

          {showUserMenu && (
            <div className="header-dropdown-menu docpilot-profile-dropdown">
              <div className="dropdown-user-header">
                <div className="dropdown-user-avatar-wrap">
                  <div className="dropdown-user-avatar">
                    {displayName.charAt(0).toUpperCase()}
                  </div>
                </div>
                <div className="dropdown-user-meta">
                  <p className="dropdown-user-name" title={displayName}>{displayName}</p>
                  <span className="dropdown-user-role-badge">Admin</span>
                </div>
              </div>

              <div className="dropdown-divider" />

              <div className="dropdown-menu-items">
                <button
                  className="dropdown-action-btn"
                  onClick={() => {
                    setShowUserMenu(false);
                    onOpenSettings();
                  }}
                >
                  <Settings size={15} />
                  <span>AI Providers & Settings</span>
                </button>

                <button
                  className="dropdown-action-btn danger"
                  onClick={async () => {
                    setShowUserMenu(false);
                    if (onLogout) {
                      onLogout();
                    } else {
                      await authLogout();
                    }
                  }}
                >
                  <LogOut size={15} />
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
