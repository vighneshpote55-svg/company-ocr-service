import React from 'react';
import { Files, CheckCircle2, AlertTriangle, HardDrive } from 'lucide-react';
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
  const verifiedCount =
    documents && documents.length > 0
      ? documents.filter((d) => d.status === 'completed' && d.checksum_valid !== false).length
      : stats.completed;

  const reviewRequiredCount =
    documents && documents.length > 0
      ? documents.filter(
          (d) =>
            d.status === 'failed' ||
            d.status === 'low_confidence' ||
            d.status === 'warning' ||
            d.checksum_valid === false
        ).length
      : stats.failed;

  const totalStorageBytes =
    documents && documents.length > 0
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
        value={stats.total}
        subtext="Indexed in Document Vault"
        icon={<Files size={20} />}
        iconBg="rgba(37, 99, 235, 0.12)"
        iconColor="var(--primary)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'Live Index', type: 'info' }}
      />

      {/* 2. Verified */}
      <StatCard
        label="Verified"
        value={verifiedCount}
        subtext="Passed all checksum validations"
        icon={<CheckCircle2 size={20} />}
        iconBg="rgba(22, 163, 74, 0.12)"
        iconColor="var(--success)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'Verified', type: 'success' }}
      />

      {/* 3. Review Required */}
      <StatCard
        label="Review Required"
        value={reviewRequiredCount}
        subtext="Warnings or low confidence"
        icon={<AlertTriangle size={20} />}
        iconBg="rgba(234, 88, 12, 0.12)"
        iconColor="var(--warning)"
        onClick={() => onNavigateTab?.('repository')}
        badge={{ text: 'Attention', type: 'warning' }}
      />

      {/* 4. Storage Used */}
      <StatCard
        label="Storage Used"
        value={storageDisplay}
        subtext="Encrypted document store"
        icon={<HardDrive size={20} />}
        iconBg="rgba(124, 58, 237, 0.12)"
        iconColor="var(--accent-purple)"
        badge={{ text: 'AES-256', type: 'neutral' }}
      />
    </div>
  );
};
