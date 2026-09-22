import React from 'react';
import { Files, Zap, Sparkles, HardDrive } from 'lucide-react';
import type { DashboardStats as StatsType, EngineInfo, DocumentItem } from '../types';
import { StatCard } from './StatCard';

interface DashboardStatsProps {
  stats: StatsType;
  onNavigateTab?: (tab: 'repository' | 'dashboard') => void;
  engineInfo?: EngineInfo | null;
  documents?: DocumentItem[];
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

  return (
    <div className="analytics-cards-grid">
      {/* 1. Total Documents */}
      <StatCard
        label="Total Documents"
        value={stats.total_documents ?? stats.total}
        subtext="Indexed in Document Vault"
        icon={<Files size={20} />}
        iconBg="rgba(37, 99, 235, 0.12)"
        iconColor="var(--primary)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'Live Vault', type: 'info' }}
      />

      {/* 2. Offline Mode (RapidOCR) */}
      <StatCard
        label="Offline Processed"
        value={offlineCount}
        subtext="RapidOCR deterministic engine"
        icon={<Zap size={20} />}
        iconBg="rgba(22, 163, 74, 0.12)"
        iconColor="var(--success)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'RapidOCR', type: 'success' }}
      />

      {/* 3. AI Mode (Intelligence) */}
      <StatCard
        label="AI Intelligence"
        value={aiCount}
        subtext="Local Qwen / External reasoning"
        icon={<Sparkles size={20} />}
        iconBg="rgba(124, 58, 237, 0.12)"
        iconColor="var(--accent-purple)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'AI Mode', type: 'warning' }}
      />

      {/* 4. Storage Used */}
      <StatCard
        label="Storage Used"
        value={storageDisplay}
        subtext="Encrypted document store"
        icon={<HardDrive size={20} />}
        iconBg="rgba(99, 102, 241, 0.12)"
        iconColor="#6366f1"
        badge={{ text: 'AES-256-GCM', type: 'neutral' }}
      />
    </div>
  );
};

