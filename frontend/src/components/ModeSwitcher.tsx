import React from 'react';
import { ShieldCheck, Sparkles } from 'lucide-react';
import type { AppMode } from '../types';

export interface ModeSwitcherProps {
  mode: AppMode;
  onModeChange: (mode: AppMode) => void;
  className?: string;
}

export const ModeSwitcher: React.FC<ModeSwitcherProps> = ({
  mode,
  onModeChange,
  className = '',
}) => {
  return (
    <div
      className={`premium-mode-switcher ${className}`}
      role="tablist"
      aria-label="Processing Mode Selector"
    >
      {/* Sliding Active Pill Highlight */}
      <div
        className={`mode-slider-pill ${mode === 'ai' ? 'slider-ai' : 'slider-offline'}`}
        aria-hidden="true"
      />

      <button
        role="tab"
        aria-selected={mode === 'offline'}
        className={`mode-switch-btn ${mode === 'offline' ? 'active-offline' : ''}`}
        onClick={() => onModeChange('offline')}
        title="Offline OCR: Local OCR engine for documents"
      >
        <span className="mode-btn-icon">
          <ShieldCheck size={16} />
        </span>
        <span className="mode-btn-text">Offline OCR</span>
      </button>

      <button
        role="tab"
        aria-selected={mode === 'ai'}
        className={`mode-switch-btn ${mode === 'ai' ? 'active-ai' : ''}`}
        onClick={() => onModeChange('ai')}
        title="AI Mode: Universal document intelligence & analysis"
      >
        <span className="mode-btn-icon">
          <Sparkles size={16} />
        </span>
        <span className="mode-btn-text">AI Mode</span>
      </button>
    </div>
  );
};
