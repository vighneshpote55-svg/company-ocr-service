import React from 'react';
import {
  Sparkles,
  Search,
  Calendar,
  DollarSign,
} from 'lucide-react';
import type { AiAnalysisResult } from '../types';

interface AIQuickActionsProps {
  document: AiAnalysisResult;
  onTriggerPrompt: (prompt: string) => void;
  onDownloadAnalysis?: () => void;
}

export const AIQuickActions: React.FC<AIQuickActionsProps> = ({
  document: _document,
  onTriggerPrompt,
  onDownloadAnalysis: _onDownloadAnalysis,
}) => {
  const actions = [
    {
      id: 'summarize',
      label: 'Summarize',
      title: 'Summarize Document',
      icon: <Sparkles size={14} color="var(--primary)" />,
      onClick: () => onTriggerPrompt('Summarize this document with key provisions, primary parties, and essential scope. Cite page references.'),
      isPrimary: true,
    },
    {
      id: 'extract-fields',
      label: 'Extract Fields',
      title: 'Extract Fields',
      icon: <Search size={14} color="var(--accent-purple)" />,
      onClick: () => onTriggerPrompt('Extract all primary structured fields, verified entities, and identifiers from this document. Cite page references for each field.'),
      isPrimary: false,
    },
    {
      id: 'find-dates',
      label: 'Find Dates',
      title: 'Find Dates',
      icon: <Calendar size={14} color="var(--warning)" />,
      onClick: () => onTriggerPrompt('Find and list all dates, effective periods, deadlines, and milestones in this document. Cite page references.'),
      isPrimary: false,
    },
    {
      id: 'find-numbers',
      label: 'Find Numbers',
      title: 'Find Numbers',
      icon: <DollarSign size={14} color="var(--success)" />,
      onClick: () => onTriggerPrompt('Find and list all monetary amounts, numerical figures, balances, and quantities in this document. Cite page references.'),
      isPrimary: false,
    },
  ];

  return (
    <div className="docpilot-quick-actions-bar" role="toolbar" aria-label="DocPilot Quick Actions">
      {actions.map((act) => (
        <button
          key={act.id}
          type="button"
          className={`docpilot-action-pill ${act.isPrimary ? 'primary' : ''}`}
          onClick={act.onClick}
          title={act.title || act.label}
          aria-label={act.title || act.label}
        >
          {act.icon}
          <span>{act.label}</span>
        </button>
      ))}
    </div>
  );
};
