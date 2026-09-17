import React from 'react';
import { Files, CheckCircle2, AlertTriangle, HardDrive } from 'lucide-react';
import type { DashboardStats as StatsType, EngineInfo, DocumentItem } from '../types';

interface DashboardStatsProps {
  stats: StatsType;
  onNavigateTab?: (tab: 'upload' | 'repository') => void;
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
  // Calculate verified vs review required from documents list
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

  // Calculate total storage bytes from documents
  const totalStorageBytes =
    documents && documents.length > 0
      ? documents.reduce((acc, d) => acc + (d.file_size || 0), 0)
      : 0;

  return (
    <div className="stats-grid">
      {/* 1. Total Documents */}
      <div
        className="stat-card"
        style={{ cursor: onNavigateTab ? 'pointer' : 'default' }}
        onClick={() => onNavigateTab?.('repository')}
        title="View all documents in repository"
      >
        <div className="stat-content">
          <span className="stat-label">Total Documents</span>
          <span className="stat-value">{stats.total}</span>
          <span className="stat-subtext">Indexed in repository</span>
        </div>
        <div className="stat-icon-wrapper" style={{ backgroundColor: '#eff6ff', color: '#2563eb' }}>
          <Files size={22} />
        </div>
      </div>

      {/* 2. Verified */}
      <div
        className="stat-card"
        style={{ cursor: onNavigateTab ? 'pointer' : 'default' }}
        onClick={() => onNavigateTab?.('repository')}
        title="Verified clean documents"
      >
        <div className="stat-content">
          <span className="stat-label">Verified</span>
          <span className="stat-value" style={{ color: '#10b981' }}>{verifiedCount}</span>
          <span className="stat-subtext">Clean checks & checksums</span>
        </div>
        <div className="stat-icon-wrapper" style={{ backgroundColor: '#ecfdf5', color: '#10b981' }}>
          <CheckCircle2 size={22} />
        </div>
      </div>

      {/* 3. Review Required */}
      <div
        className="stat-card"
        style={{ cursor: onNavigateTab ? 'pointer' : 'default' }}
        onClick={() => onNavigateTab?.('repository')}
        title="Documents with discrepancies or warnings"
      >
        <div className="stat-content">
          <span className="stat-label">Review Required</span>
          <span className="stat-value" style={{ color: '#f59e0b' }}>{reviewRequiredCount}</span>
          <span className="stat-subtext">Low confidence or warnings</span>
        </div>
        <div className="stat-icon-wrapper" style={{ backgroundColor: '#fffbeb', color: '#f59e0b' }}>
          <AlertTriangle size={22} />
        </div>
      </div>

      {/* 4. Storage Used */}
      <div className="stat-card" title="Total file storage used on disk">
        <div className="stat-content">
          <span className="stat-label">Storage Used</span>
          <span className="stat-value" style={{ color: '#7c3aed' }}>
            {totalStorageBytes > 0 ? formatBytes(totalStorageBytes) : `${stats.total > 0 ? `${(stats.total * 0.25).toFixed(1)} MB` : '0 B'}`}
          </span>
          <span className="stat-subtext">Stored original & previews</span>
        </div>
        <div className="stat-icon-wrapper" style={{ backgroundColor: '#faf5ff', color: '#7c3aed' }}>
          <HardDrive size={22} />
        </div>
      </div>
    </div>
  );
};
