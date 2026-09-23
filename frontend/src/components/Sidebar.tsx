import React, { useState } from 'react';
import {
  LayoutDashboard,
  FileText,
  Search,
  Sparkles,
  Users,
  Settings,
  ChevronLeft,
  ChevronRight,
  Globe,
  LogOut,
  X,
  ChevronDown,
  ShieldCheck,
} from 'lucide-react';
import type { EngineInfo, AppMode } from '../types';
import { useAuth } from '../context/AuthContext';

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
  onLogout?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  onOpenSettings,
  engineInfo: _engineInfo,
  appMode,
  onSelectMode,
  isOpenMobile = false,
  onCloseMobile,
  isCollapsed = false,
  onToggleCollapse,
  onLogout,
}) => {
  const { user, logout: authLogout } = useAuth();
  const [activeProject, setActiveProject] = useState<'alpha' | 'beta' | 'delta'>('alpha');
  const [isProjectsOpen, setIsProjectsOpen] = useState(true);

  const handleNavClick = (tab: NavTab) => {
    onSelectTab(tab);
    if (onCloseMobile) onCloseMobile();
  };

  const handleModeClick = (mode: AppMode) => {
    onSelectMode(mode);
    onSelectTab('dashboard');
    if (onCloseMobile) onCloseMobile();
  };

  const handleLogoutClick = async () => {
    if (onLogout) {
      onLogout();
    } else {
      await authLogout();
    }
  };

  const displayName = user?.full_name || (user?.email ? user.email.split('@')[0] : 'Sarah J.');

  return (
    <>
      {/* Mobile Drawer Backdrop */}
      <div
        className={`sidebar-backdrop ${isOpenMobile ? 'active' : ''}`}
        onClick={onCloseMobile}
        aria-hidden="true"
      />

      <aside className={`sidebar docpilot-sidebar dark-floating-sidebar ${isCollapsed ? 'collapsed' : ''} ${isOpenMobile ? 'open' : ''}`}>
        {/* 1. Sidebar Header: DocPilot AI Logo */}
        <div className="docpilot-sidebar-header">
          <div className="docpilot-brand-wrap" onClick={() => handleNavClick('dashboard')} style={{ cursor: 'pointer' }}>
            {/* Stylized DocPilot AI Gradient Icon */}
            <div className="docpilot-logo-icon">
              <svg width="24" height="24" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M6 24L16 6L26 24L16 19L6 24Z"
                  fill="url(#dpGradient)"
                  stroke="#38BDF8"
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                />
                <circle cx="16" cy="14" r="3" fill="#FFFFFF" />
                <defs>
                  <linearGradient id="dpGradient" x1="6" y1="6" x2="26" y2="24" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#00C2FF" />
                    <stop offset="1" stopColor="#0284C7" />
                  </linearGradient>
                </defs>
              </svg>
            </div>

            {!isCollapsed && (
              <div className="docpilot-brand-text">
                <span className="docpilot-brand-main">DocPilot</span>
                <span className="docpilot-brand-ai">AI</span>
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

        {/* 2. Main Navigation Links */}
        <div className="docpilot-sidebar-nav-scroll">
          <nav className="docpilot-sidebar-menu" aria-label="DocPilot Navigation">
            {/* Dashboard (Active Pill with glowing border) */}
            <button
              className={`docpilot-nav-item ${currentTab === 'dashboard' && appMode === 'ai' ? 'active-glowing' : ''}`}
              onClick={() => {
                handleModeClick('ai');
              }}
              title="Dashboard"
            >
              <div className="docpilot-nav-icon">
                <LayoutDashboard size={18} />
              </div>
              {!isCollapsed && <span className="docpilot-nav-label">Dashboard</span>}
            </button>

            {/* My Documents (Vault) */}
            <button
              className={`docpilot-nav-item ${currentTab === 'repository' ? 'active-glowing' : ''}`}
              onClick={() => handleNavClick('repository')}
              title="My Documents"
            >
              <div className="docpilot-nav-icon">
                <FileText size={18} />
              </div>
              {!isCollapsed && <span className="docpilot-nav-label">My Documents</span>}
            </button>

            {/* Search */}
            <button
              className="docpilot-nav-item"
              onClick={() => handleNavClick('repository')}
              title="Search Documents"
            >
              <div className="docpilot-nav-icon">
                <Search size={18} />
              </div>
              {!isCollapsed && <span className="docpilot-nav-label">Search</span>}
            </button>

            {/* AI Tools / Mode Switcher */}
            <button
              className={`docpilot-nav-item ${appMode === 'ai' ? 'highlighted' : ''}`}
              onClick={() => handleModeClick('ai')}
              title="AI Tools & Analysis"
            >
              <div className="docpilot-nav-icon">
                <Sparkles size={18} />
              </div>
              {!isCollapsed && (
                <div className="docpilot-nav-label-group">
                  <span className="docpilot-nav-label">AI Tools</span>
                  <span className="docpilot-mini-tag">Active</span>
                </div>
              )}
            </button>

            {/* Offline OCR Engine */}
            <button
              className={`docpilot-nav-item ${appMode === 'offline' ? 'active-glowing' : ''}`}
              onClick={() => handleModeClick('offline')}
              title="Offline Mode (RapidOCR 22 Document Types)"
            >
              <div className="docpilot-nav-icon">
                <ShieldCheck size={18} />
              </div>
              {!isCollapsed && (
                <div className="docpilot-nav-label-group">
                  <span className="docpilot-nav-label">Offline OCR</span>
                  <span className="docpilot-mini-tag green">22 Types</span>
                </div>
              )}
            </button>

            {/* Teams */}
            <button
              className="docpilot-nav-item"
              onClick={() => onSelectTab('dashboard')}
              title="Teams & Permissions"
            >
              <div className="docpilot-nav-icon">
                <Users size={18} />
              </div>
              {!isCollapsed && <span className="docpilot-nav-label">Teams</span>}
            </button>

            {/* Settings */}
            <button
              className="docpilot-nav-item"
              onClick={() => {
                onOpenSettings();
                if (onCloseMobile) onCloseMobile();
              }}
              title="Settings & AI Providers"
            >
              <div className="docpilot-nav-icon">
                <Settings size={18} />
              </div>
              {!isCollapsed && <span className="docpilot-nav-label">Settings</span>}
            </button>
          </nav>
        </div>

        {/* 3. Sidebar Bottom Section: Multi-tenant Workspace & User Profile */}
        <div className="docpilot-sidebar-bottom">
          {/* Multi-tenant Workspace Capsule */}
          {!isCollapsed && (
            <div className="docpilot-workspace-card">
              <div
                className="docpilot-workspace-card-header"
                onClick={() => setIsProjectsOpen((p) => !p)}
                style={{ cursor: 'pointer' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Globe size={13} color="#00C2FF" />
                  <span className="docpilot-workspace-card-title">Multi-tenant workspace</span>
                </div>
                <ChevronDown
                  size={13}
                  color="#94A3B8"
                  style={{
                    transform: isProjectsOpen ? 'rotate(180deg)' : 'none',
                    transition: 'transform 0.15s ease',
                  }}
                />
              </div>

              {isProjectsOpen && (
                <div className="docpilot-projects-list">
                  <div className="docpilot-projects-lbl">Projects</div>
                  <div
                    className={`docpilot-project-item ${activeProject === 'alpha' ? 'active' : ''}`}
                    onClick={() => setActiveProject('alpha')}
                  >
                    <span className="project-badge blue">A</span>
                    <span className="project-name">Alpha</span>
                  </div>
                  <div
                    className={`docpilot-project-item ${activeProject === 'beta' ? 'active' : ''}`}
                    onClick={() => setActiveProject('beta')}
                  >
                    <span className="project-badge teal">S</span>
                    <span className="project-name">Beta</span>
                  </div>
                  <div
                    className={`docpilot-project-item ${activeProject === 'delta' ? 'active' : ''}`}
                    onClick={() => setActiveProject('delta')}
                  >
                    <span className="project-badge magenta">R</span>
                    <span className="project-name">Delta</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* User Profile Footer */}
          <div className="docpilot-user-footer">
            <button
              className="docpilot-logout-btn"
              onClick={handleLogoutClick}
              title="Sign Out"
              aria-label="Sign Out"
            >
              <LogOut size={16} />
            </button>

            <div className="docpilot-user-info">
              <div className="docpilot-user-avatar">
                {displayName.charAt(0).toUpperCase()}
              </div>
              {!isCollapsed && (
                <div className="docpilot-user-details">
                  <div className="docpilot-user-name" title={displayName}>{displayName}</div>
                  <div className="docpilot-user-role">Admin</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};
