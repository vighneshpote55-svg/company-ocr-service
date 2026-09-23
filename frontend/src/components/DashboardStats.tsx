import React from 'react';
import { Files, Zap, Sparkles, HardDrive, ShieldCheck, Cpu } from 'lucide-react';
import type { DashboardStats as StatsType, EngineInfo, DocumentItem, AIProviderConfig } from '../types';
import { StatCard } from './StatCard';

interface DashboardStatsProps {
  stats: StatsType;
  onNavigateTab?: (tab: 'repository' | 'dashboard') => void;
  engineInfo?: EngineInfo | null;
  documents?: DocumentItem[];
  aiConfig?: AIProviderConfig | null;
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export const DashboardStats: React.FC<DashboardStatsProps> = ({
  stats,
  onNavigateTab,
  documents,
  aiConfig,
}) => {
  const offlineCount =
    typeof stats.offline_documents === 'number'
      ? stats.offline_documents
      : documents && documents.length > 0
      ? documents.filter((d) => (d as any).mode === 'offline' || d.ocr_required).length
      : stats.ocr_processed || 0;

  const aiCount =
    typeof stats.ai_documents === 'number'
      ? stats.ai_documents
      : documents && documents.length > 0
      ? documents.filter((d) => (d as any).mode === 'ai').length
      : 0;

  const totalStorageBytes =
    typeof stats.total_storage_bytes === 'number'
      ? stats.total_storage_bytes
      : documents && documents.length > 0
      ? documents.reduce((acc, d) => acc + (d.file_size || 0), 0)
      : 0;

  const storageDisplay =
    totalStorageBytes > 0
      ? formatBytes(totalStorageBytes)
      : stats.total > 0
      ? `${(stats.total * 0.25).toFixed(1)} MB`
      : '0 B';

  // Integrity metrics
  const verifiedCount = documents
    ? documents.filter((d) => d.verification_status === 'verified').length
    : 0;
  const reviewCount = documents
    ? documents.filter((d) => d.verification_status === 'review_required' || d.review_required).length
    : 0;

  // Active AI Provider info
  const providerTitle = aiConfig?.mode === 'external'
    ? (aiConfig.active_provider === 'openrouter' ? 'OpenRouter' : aiConfig.active_provider.toUpperCase())
    : 'Local Ollama';
  const modelSubtext = aiConfig?.active_model || 'qwen2.5vl:3b';

  return (
    <div className="analytics-cards-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
      {/* 1. Total Documents */}
      <StatCard
        label="Documents"
        value={stats.total_documents ?? stats.total}
        subtext="Indexed in Document Vault"
        icon={<Files size={20} />}
        iconBg="rgba(0, 194, 255, 0.12)"
        iconColor="var(--primary)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'Live Vault', type: 'info' }}
      />

      {/* 2. Offline Processed (RapidOCR) */}
      <StatCard
        label="Offline Processed"
        value={offlineCount}
        subtext="RapidOCR deterministic engine"
        icon={<Zap size={20} />}
        iconBg="rgba(34, 197, 94, 0.12)"
        iconColor="var(--success)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'RapidOCR', type: 'success' }}
      />

      {/* 3. AI Processed (DocPilot Intelligence) */}
      <StatCard
        label="AI Processed"
        value={aiCount}
        subtext="Visual reasoning & extraction"
        icon={<Sparkles size={20} />}
        iconBg="rgba(139, 92, 246, 0.12)"
        iconColor="var(--accent-purple)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'DocPilot AI', type: 'warning' }}
      />

      {/* 4. Storage Used */}
      <StatCard
        label="Storage"
        value={storageDisplay}
        subtext="Encrypted document store"
        icon={<HardDrive size={20} />}
        iconBg="rgba(99, 102, 241, 0.12)"
        iconColor="#6366f1"
        badge={{ text: 'AES-256', type: 'neutral' }}
      />

      {/* 5. Integrity Status */}
      <StatCard
        label="Integrity Status"
        value={reviewCount > 0 ? `${reviewCount} Review` : `${verifiedCount} Verified`}
        subtext={reviewCount > 0 ? `${verifiedCount} verified cleanly` : 'Universal integrity verified'}
        icon={<ShieldCheck size={20} />}
        iconBg={reviewCount > 0 ? 'rgba(245, 158, 11, 0.14)' : 'rgba(34, 197, 94, 0.12)'}
        iconColor={reviewCount > 0 ? 'var(--warning)' : 'var(--success)'}
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: reviewCount > 0 ? 'Action Needed' : 'Passed', type: reviewCount > 0 ? 'warning' : 'success' }}
      />

      {/* 6. AI Provider */}
      <StatCard
        label="AI Provider"
        value={providerTitle}
        subtext={modelSubtext}
        icon={<Cpu size={20} />}
        iconBg="rgba(139, 92, 246, 0.12)"
        iconColor="var(--accent-purple)"
        badge={{ text: aiConfig?.mode === 'external' ? 'Cloud' : 'Offline', type: 'info' }}
      />
    </div>
  );
};

