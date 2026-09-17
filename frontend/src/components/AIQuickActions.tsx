import React from 'react';
import {
  FileText,
  Key,
  Calendar,
  DollarSign,
  Download,
  Zap,
} from 'lucide-react';
import type { AiAnalysisResult } from '../types';

interface AIQuickActionsProps {
  document: AiAnalysisResult;
  onTriggerPrompt: (prompt: string) => void;
  onDownloadAnalysis: () => void;
}

export const AIQuickActions: React.FC<AIQuickActionsProps> = ({
  document,
  onTriggerPrompt,
  onDownloadAnalysis,
}) => {
  const actions = [
    {
      id: 'summarize',
      title: 'Summarize',
      subtitle: 'Generate concise executive overview',
      icon: <FileText size={18} className="ai-action-card-icon text-primary" />,
      onClick: () => onTriggerPrompt('Summarize this document with key provisions and scope.'),
    },
    {
      id: 'extract-info',
      title: 'Extract Key Information',
      subtitle: 'Identify parties, roles, and entities',
      icon: <Key size={18} className="ai-action-card-icon text-ai" />,
      onClick: () => onTriggerPrompt('Extract all key entities, parties, employee/employer details, and identification numbers.'),
    },
    {
      id: 'find-dates',
      title: 'Find Dates',
      subtitle: 'Effective dates, deadlines & milestones',
      icon: <Calendar size={18} className="ai-action-card-icon text-warning" />,
      onClick: () => onTriggerPrompt('List all dates, effective periods, deadlines, joining dates, or milestones found in this document.'),
    },
    {
      id: 'find-financials',
      title: 'Find Financial Values',
      subtitle: 'Salaries, compensations & payment terms',
      icon: <DollarSign size={18} className="ai-action-card-icon text-success" />,
      onClick: () => onTriggerPrompt('Identify all compensation amounts, salary details, payment milestones, fees, or monetary values.'),
    },
    {
      id: 'download-analysis',
      title: 'Download Analysis',
      subtitle: `Export ${document.filename} as JSON`,
      icon: <Download size={18} className="ai-action-card-icon text-primary" />,
      onClick: onDownloadAnalysis,
    },
  ];

  return (
    <div className="ai-quick-actions-section">
      <div className="ai-quick-actions-header">
        <div className="ai-quick-badge-wrap">
          <Zap size={14} className="ai-quick-badge-icon" />
          <span className="ai-quick-badge-label">Quick Actions</span>
        </div>
        <span className="ai-quick-hint">Click any action to query the assistant or download results</span>
      </div>

      <div className="ai-quick-actions-grid">
        {actions.map((act) => (
          <button
            key={act.id}
            type="button"
            className="ai-quick-action-card"
            onClick={act.onClick}
          >
            <div className="ai-quick-action-icon-wrap">
              {act.icon}
            </div>
            <div className="ai-quick-action-content">
              <span className="ai-quick-action-title">{act.title}</span>
              <span className="ai-quick-action-subtitle">{act.subtitle}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};
