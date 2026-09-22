import React from 'react';
import { Outlet } from 'react-router-dom';
import { Shield, Lock, Cpu } from 'lucide-react';

export const AuthLayout: React.FC = () => {
  return (
    <div className="auth-viewport-wrapper">
      <div className="auth-ambient-glow auth-ambient-glow-1" />
      <div className="auth-ambient-glow auth-ambient-glow-2" />

      <div className="auth-container">
        {/* Brand Header */}
        <div className="auth-brand-header">
          <div className="auth-brand-logo-pill">
            <Shield className="auth-brand-icon" />
          </div>
          <h1 className="auth-brand-title">Company OCR</h1>
          <p className="auth-brand-subtitle">Document Intelligence Platform</p>
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
            <Shield className="w-3.5 h-3.5 mr-1" /> Isolated Multi-Tenant
          </span>
        </div>
      </div>
    </div>
  );
};

export default AuthLayout;
