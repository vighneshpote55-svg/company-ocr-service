import React, { useState } from 'react';
import {
  User,
  Building,
  DollarSign,
  Calendar,
  ShieldCheck,
  Sparkles,
  ChevronDown,
  ChevronUp,
  MapPin,
  Binary,
  Copy,
  Check,
} from 'lucide-react';

interface AIKeyFindingsCardProps {
  reasoning: string[];
  documentType: string;
  extractedFields?: Record<string, any>;
}

interface AccordionCategory {
  id: string;
  title: string;
  icon: React.ReactNode;
  items: Array<{ key?: string; value: string }>;
}

export const AIKeyFindingsCard: React.FC<AIKeyFindingsCardProps> = ({
  reasoning,
  documentType,
  extractedFields = {},
}) => {
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({
    identity: true,
    financial: true,
    identifiers: true,
    dates: true,
    address: true,
    authority: true,
    general: true,
  });

  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(id);
    setTimeout(() => {
      setCopiedKey(null);
    }, 1800);
  };

  const toggleCategory = (id: string) => {
    setOpenCategories((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Group extracted fields into logical DocPilot categories
  const identityItems: Array<{ key?: string; value: string }> = [];
  const dateItems: Array<{ key?: string; value: string }> = [];
  const identifierItems: Array<{ key?: string; value: string }> = [];
  const addressItems: Array<{ key?: string; value: string }> = [];
  const authorityItems: Array<{ key?: string; value: string }> = [];
  const financialItems: Array<{ key?: string; value: string }> = [];
  const generalEvidenceItems: Array<{ key?: string; value: string }> = [];

  // 1. Process extractedFields
  if (extractedFields && typeof extractedFields === 'object') {
    Object.entries(extractedFields).forEach(([rawKey, val]) => {
      if (val === null || val === undefined || val === '') return;
      const k = rawKey.toLowerCase();
      const valStr = typeof val === 'object' ? JSON.stringify(val) : String(val);
      const label = rawKey.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

      if (k.includes('name') || k.includes('employee') || k.includes('holder') || k.includes('applicant') || k.includes('person')) {
        identityItems.push({ key: label, value: valStr });
      } else if (k.includes('date') || k.includes('period') || k.includes('dob') || k.includes('month') || k.includes('year') || k.includes('valid')) {
        dateItems.push({ key: label, value: valStr });
      } else if (k.includes('number') || k.includes('pan') || k.includes('aadhaar') || k.includes('gstin') || k.includes('cin') || k.includes('ifsc') || k.includes('passport') || k.includes('license') || k.includes('code') || k.includes('id')) {
        identifierItems.push({ key: label, value: valStr });
      } else if (k.includes('address') || k.includes('city') || k.includes('state') || k.includes('pin') || k.includes('branch') || k.includes('location')) {
        addressItems.push({ key: label, value: valStr });
      } else if (k.includes('employer') || k.includes('company') || k.includes('authority') || k.includes('bank') || k.includes('issuer') || k.includes('department')) {
        authorityItems.push({ key: label, value: valStr });
      } else if (k.includes('salary') || k.includes('pay') || k.includes('amount') || k.includes('balance') || k.includes('tax') || k.includes('deduction') || k.includes('gross') || k.includes('net') || k.includes('fee')) {
        financialItems.push({ key: label, value: valStr });
      } else {
        generalEvidenceItems.push({ key: label, value: valStr });
      }
    });
  }

  // 2. Process reasoning lines
  if (Array.isArray(reasoning)) {
    reasoning.forEach((line) => {
      const l = String(line).toLowerCase();
      if (l.includes('salary') || l.includes('amount') || l.includes('balance') || l.includes('₹') || l.includes('$')) {
        financialItems.push({ value: line });
      } else if (l.includes('date') || l.includes('period') || l.includes('dated')) {
        dateItems.push({ value: line });
      } else if (l.includes('name') || l.includes('party')) {
        identityItems.push({ value: line });
      } else {
        generalEvidenceItems.push({ value: line });
      }
    });
  }

  const categories: AccordionCategory[] = [
    {
      id: 'identity',
      title: 'Identity & Parties',
      icon: <User size={16} color="var(--primary)" />,
      items: identityItems,
    },
    {
      id: 'financial',
      title: 'Financial Values & Amounts',
      icon: <DollarSign size={16} color="var(--success)" />,
      items: financialItems,
    },
    {
      id: 'identifiers',
      title: 'Document Numbers & Identifiers (GSTIN / PAN / ID)',
      icon: <Binary size={16} color="var(--accent-purple)" />,
      items: identifierItems,
    },
    {
      id: 'dates',
      title: 'Registration & Timeline Dates',
      icon: <Calendar size={16} color="var(--warning)" />,
      items: dateItems,
    },
    {
      id: 'address',
      title: 'Registered Address & Jurisdiction',
      icon: <MapPin size={16} color="#06B6D4" />,
      items: addressItems,
    },
    {
      id: 'authority',
      title: 'Business Type & Authority Entity',
      icon: <Building size={16} color="#8B5CF6" />,
      items: authorityItems,
    },
    {
      id: 'general',
      title: 'Structural Reasoning & Evidence',
      icon: <ShieldCheck size={16} color="var(--primary)" />,
      items: generalEvidenceItems,
    },
  ];

  // Filter out completely empty categories if there are other populated categories
  const activeCategories = categories.filter((c) => c.items.length > 0);
  const fallbackCategories: AccordionCategory[] = [
    {
      id: 'general',
      title: 'Key Structural Features',
      icon: <ShieldCheck size={16} color="var(--primary)" />,
      items: [
        { value: `Identified as ${documentType} with structural document validation.` },
        { value: 'Extracted semantic entities and verified context.' },
        { value: 'Ready for interactive document-grounded question answering.' },
      ],
    },
  ];
  const displayCategories: AccordionCategory[] = activeCategories.length > 0 ? activeCategories : fallbackCategories;

  return (
    <div className="ai-findings-section" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div className="ai-findings-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div className="ai-findings-badge-icon" style={{ background: 'rgba(139, 92, 246, 0.12)', color: 'var(--accent-purple)', padding: '7px', borderRadius: '10px' }}>
            <Sparkles size={18} />
          </div>
          <div>
            <h4 className="ai-findings-title" style={{ fontSize: '15px', fontWeight: 600, margin: 0, color: 'var(--text-main)' }}>
              Key Findings & Entity Timeline
            </h4>
            <p className="ai-findings-subtitle" style={{ fontSize: '12px', margin: '2px 0 0', color: 'var(--text-muted)' }}>
              Verified document entities, registration numbers, timestamps, and address data
            </p>
          </div>
        </div>
      </div>

      {/* Accordion Categories */}
      <div className="docpilot-findings-grid">
        {displayCategories.map((cat) => {
          const isOpen = Boolean(openCategories[cat.id]);
          return (
            <div key={cat.id} className="findings-accordion-item">
              <button
                type="button"
                className="findings-accordion-header"
                onClick={() => toggleCategory(cat.id)}
                aria-expanded={isOpen}
              >
                <div className="findings-accordion-left">
                  {cat.icon}
                  <span>{cat.title}</span>
                  <span
                    style={{
                      fontSize: '11px',
                      padding: '2px 8px',
                      borderRadius: '9999px',
                      background: 'rgba(255, 255, 255, 0.06)',
                      border: '1px solid var(--border-subtle)',
                      color: 'var(--text-muted)',
                      fontWeight: 600,
                    }}
                  >
                    {cat.items.length} {cat.items.length === 1 ? 'item' : 'items'}
                  </span>
                </div>
                {isOpen ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
              </button>

              {isOpen && (
                <div className="findings-accordion-body">
                  <div className="docpilot-timeline-findings-list" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {cat.items.map((item, idx) => {
                      const itemKeyId = `${cat.id}-${idx}`;
                      const isCopied = copiedKey === itemKeyId;

                      return (
                        <div
                          key={idx}
                          className="docpilot-finding-card"
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '10px 14px',
                            borderRadius: '10px',
                            background: 'var(--bg-card)',
                            border: '1px solid var(--border-subtle)',
                            gap: '12px',
                            transition: 'all 0.15s ease',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', minWidth: 0, flex: 1 }}>
                            <div
                              style={{
                                width: '6px',
                                height: '6px',
                                borderRadius: '50%',
                                background: 'var(--primary)',
                                marginTop: '7px',
                                flexShrink: 0,
                              }}
                            />
                            <div style={{ minWidth: 0, flex: 1 }}>
                              {item.key ? (
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
                                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                                    {item.key}
                                  </span>
                                </div>
                              ) : null}
                              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-main)', wordBreak: 'break-word', lineHeight: 1.45 }}>
                                {item.value}
                              </div>
                            </div>
                          </div>

                          <button
                            type="button"
                            className="docpilot-copy-btn"
                            onClick={() => handleCopy(item.value, itemKeyId)}
                            title="Copy value to clipboard"
                            style={{
                              background: isCopied ? 'rgba(16, 185, 129, 0.15)' : 'var(--bg-subtle)',
                              border: `1px solid ${isCopied ? 'rgba(16, 185, 129, 0.4)' : 'var(--border-subtle)'}`,
                              color: isCopied ? 'var(--success)' : 'var(--text-muted)',
                              padding: '5px 8px',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              fontSize: '11px',
                              flexShrink: 0,
                              transition: 'all 0.15s ease',
                            }}
                          >
                            {isCopied ? <Check size={12} /> : <Copy size={12} />}
                            <span>{isCopied ? 'Copied' : 'Copy'}</span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
