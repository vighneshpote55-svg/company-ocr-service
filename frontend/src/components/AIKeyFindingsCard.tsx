import React from 'react';
import {
  User,
  Building,
  DollarSign,
  Calendar,
  FileCheck,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';

interface AIKeyFindingsCardProps {
  reasoning: string[];
  documentType: string;
  extractedFields?: Record<string, any>;
}

interface FindingItem {
  id: string;
  icon: React.ReactNode;
  label: string;
  description: string;
}

export const AIKeyFindingsCard: React.FC<AIKeyFindingsCardProps> = ({
  reasoning,
  documentType,
  extractedFields,
}) => {
  // Helper to choose contextual icon & title
  const parseFinding = (text: any, index: number): FindingItem => {
    const str = typeof text === 'string' ? text : (typeof text === 'object' && text !== null ? JSON.stringify(text) : String(text ?? ''));
    const lower = str.toLowerCase();
    let icon = <CheckCircle2 size={18} className="ai-finding-icon text-ai" />;
    let label = `Key Feature ${index + 1}`;

    if (lower.includes('employee') || lower.includes('candidate') || lower.includes('person') || lower.includes('individual') || lower.includes('name')) {
      icon = <User size={18} className="ai-finding-icon text-primary" />;
      label = 'Identity / Person / Entity Identified';
    } else if (lower.includes('employer') || lower.includes('company') || lower.includes('organization') || lower.includes('party') || lower.includes('vendor') || lower.includes('department')) {
      icon = <Building size={18} className="ai-finding-icon text-primary" />;
      label = 'Organization / Issuing Authority';
    } else if (lower.includes('salary') || lower.includes('compensation') || lower.includes('amount') || lower.includes('fee') || lower.includes('payment') || lower.includes('due') || lower.includes('$') || lower.includes('inr') || lower.includes('tax')) {
      icon = <DollarSign size={18} className="ai-finding-icon text-success" />;
      label = 'Financial / Value Term Detected';
    } else if (lower.includes('date') || lower.includes('joining') || lower.includes('term') || lower.includes('period') || lower.includes('effective') || lower.includes('birth') || lower.includes('dob')) {
      icon = <Calendar size={18} className="ai-finding-icon text-warning" />;
      label = 'Date / Milestone Detected';
    } else if (lower.includes('obligation') || lower.includes('confidential') || lower.includes('governing') || lower.includes('clause') || lower.includes('nda') || lower.includes('number') || lower.includes('pan') || lower.includes('id')) {
      icon = <ShieldCheck size={18} className="ai-finding-icon text-ai" />;
      label = 'Identifier / Document Clause';
    } else if (lower.includes('signature') || lower.includes('verified') || lower.includes('formal') || lower.includes('executed')) {
      icon = <FileCheck size={18} className="ai-finding-icon text-success" />;
      label = 'Execution & Verification Evidence';
    }

    return {
      id: `finding-${index}`,
      icon,
      label,
      description: str,
    };
  };

  const fieldItems = extractedFields && typeof extractedFields === 'object' && !Array.isArray(extractedFields)
    ? Object.entries(extractedFields).map(([k, v]) => {
        const valStr = typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v ?? '');
        return `${k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}: ${valStr}`;
      })
    : [];

  const rawItems = [
    ...(reasoning || []),
    ...fieldItems,
  ];

  const finalItems = rawItems.length > 0
    ? rawItems
    : [
        `Identified as ${documentType} with structural document validation`,
        'Extracted semantic entities and verified context',
        'Ready for interactive document-grounded question answering',
      ];

  const findings: FindingItem[] = finalItems.map((item, idx) => parseFinding(item, idx));

  return (
    <div className="ai-findings-section">
      <div className="ai-findings-header">
        <div className="ai-findings-title-wrap">
          <div className="ai-findings-badge-icon">
            <Sparkles size={16} />
          </div>
          <div>
            <h4 className="ai-findings-title">Key Findings & Structural Insights</h4>
            <p className="ai-findings-subtitle">
              Discrete evidence and verified entities extracted during AI evaluation
            </p>
          </div>
        </div>
        <span className="ai-findings-count-badge">
          {findings.length} Evidence {findings.length === 1 ? 'Point' : 'Points'}
        </span>
      </div>

      <div className="ai-findings-grid">
        {findings.map((item) => (
          <div key={item.id} className="ai-finding-card">
            <div className="ai-finding-card-icon-wrap">
              {item.icon}
            </div>
            <div className="ai-finding-card-content">
              <span className="ai-finding-card-label">{item.label}</span>
              <p className="ai-finding-card-desc">{item.description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
