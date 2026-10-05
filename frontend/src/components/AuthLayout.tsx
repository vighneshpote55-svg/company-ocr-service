import React, { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Shield, Lock, Cpu, Sun, Moon } from 'lucide-react';

export const AuthLayout: React.FC = () => {
  const [isDark, setIsDark] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('theme_preference');
      if (saved) return saved === 'dark';
      return true; // Default dark
    } catch {
      return true;
    }
  });

  useEffect(() => {
    try {
      if (isDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.documentElement.classList.add('dark');
        localStorage.setItem('theme_preference', 'dark');
      } else {
        document.documentElement.setAttribute('data-theme', 'light');
        document.documentElement.classList.remove('dark');
        localStorage.setItem('theme_preference', 'light');
      }
    } catch {
      // Ignore
    }
  }, [isDark]);

  const toggleTheme = () => {
    setIsDark((prev) => !prev);
  };

  return (
    <div className="auth-viewport-wrapper">
      {/* Top Bar with Theme Toggle */}
      <div className="auth-top-actions">
        <button
          type="button"
          onClick={toggleTheme}
          className="auth-theme-toggle-btn"
          title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          aria-label={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-600" />}
          <span>{isDark ? 'Light Mode' : 'Dark Mode'}</span>
        </button>
      </div>

      <div className="auth-ambient-glow auth-ambient-glow-1" />
      <div className="auth-ambient-glow auth-ambient-glow-2" />

      <div className="auth-container">
        {/* Brand Header */}
        <div className="auth-brand-header">
          <div className="auth-brand-logo-pill">
            <Shield className="auth-brand-icon" />
          </div>
          <h1 className="auth-brand-title">DocPilot AI</h1>
          <p className="auth-brand-subtitle">Enterprise Document Intelligence & OCR Platform</p>
        </div>

        {/* Centered Glassmorphism Card */}
        <div className="auth-card">
          <Outlet />
        </div>

        {/* Security Trust Badges */}
        <div className="auth-trust-footer">
          <span className="auth-trust-badge">
            <Lock className="w-3.5 h-3.5 mr-1" /> AES-256-GCM Encrypted
          </span>
          <span className="auth-trust-dot">•</span>
          <span className="auth-trust-badge">
            <Cpu className="w-3.5 h-3.5 mr-1" /> Local & External AI
          </span>
          <span className="auth-trust-dot">•</span>
          <span className="auth-trust-badge">
            <Shield className="w-3.5 h-3.5 mr-1" /> Isolated Client Vault
          </span>
        </div>
      </div>
    </div>
  );
};

export default AuthLayout;
