import React, { useState } from 'react';
import {
  Copy,
  Check,
  ShieldCheck,
  AlertCircle,
  User,
  Calendar,
  CreditCard,
  Building2,
  FileText,
  MapPin,
  Phone,
  Mail,
  Hash,
  DollarSign,
  Briefcase,
  Layers,
  Sparkles,
  ArrowRight,
} from 'lucide-react';
import type { DocumentItem } from '../types';
import { SectionCard } from './SectionCard';

interface ExtractedFieldsProps {
  document: DocumentItem;
  onCopyToast?: (msg: string) => void;
  onSwitchToAiMode?: () => void;
}

const PERSONAL_KEYS = new Set([
  'name',
  'full_name',
  'person_name',
  'employee_name',
  'customer_name',
  'holder_name',
  'applicant_name',
  'father_name',
  'mother_name',
  'spouse_name',
  'dob',
  'date_of_birth',
  'birth_date',
  'gender',
  'sex',
  'age',
  'nationality',
  'address',
  'permanent_address',
  'current_address',
  'phone',
  'mobile',
  'contact',
  'email',
]);

const DOCUMENT_KEYS = new Set([
  'document_number',
  'doc_number',
  'id_number',
  'pan',
  'pan_number',
  'aadhaar',
  'aadhaar_number',
  'voter_id',
  'epic_number',
  'passport_no',
  'passport_number',
  'driving_license_no',
  'dl_number',
  'rc_number',
  'chassis_number',
  'engine_number',
  'issue_date',
  'issued_on',
  'expiry_date',
  'valid_till',
  'valid_until',
  'authority',
  'place_of_issue',
  'issuing_state',
  'registration_date',
]);

const FINANCIAL_KEYS = new Set([
  'account_number',
  'acc_number',
  'account_no',
  'ifsc',
  'ifsc_code',
  'bank_name',
  'bank',
  'branch',
  'micr',
  'salary',
  'net_pay',
  'net_salary',
  'gross_pay',
  'gross_salary',
  'basic_pay',
  'total_amount',
  'amount',
  'tax_amount',
  'gstin',
  'gst_number',
  'invoice_number',
  'invoice_no',
  'employer',
  'company_name',
  'transactions',
]);

function getFieldIcon(key: string) {
  const lower = key.toLowerCase();
  if (lower.includes('name') || lower.includes('gender') || lower.includes('sex')) return <User size={15} />;
  if (lower.includes('date') || lower.includes('dob') || lower.includes('expiry') || lower.includes('valid')) return <Calendar size={15} />;
  if (lower.includes('address') || lower.includes('state') || lower.includes('place')) return <MapPin size={15} />;
  if (lower.includes('phone') || lower.includes('mobile')) return <Phone size={15} />;
  if (lower.includes('email')) return <Mail size={15} />;
  if (lower.includes('account') || lower.includes('pan') || lower.includes('aadhaar') || lower.includes('passport') || lower.includes('license')) return <CreditCard size={15} />;
  if (lower.includes('bank') || lower.includes('company') || lower.includes('employer')) return <Building2 size={15} />;
  if (lower.includes('salary') || lower.includes('amount') || lower.includes('pay') || lower.includes('tax')) return <DollarSign size={15} />;
  if (lower.includes('number') || lower.includes('no') || lower.includes('id')) return <Hash size={15} />;
  return <FileText size={15} />;
}

export const ExtractedFields: React.FC<ExtractedFieldsProps> = ({
  document,
  onCopyToast,
  onSwitchToAiMode,
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const fields = document.extracted_fields || document.fields || {};
  const confidences = document.field_confidences || {};
  const fieldKeys = Object.keys(fields).filter((k) => fields[k] !== null && fields[k] !== undefined);

  const handleCopy = (key: string, val: any) => {
    const textVal = Array.isArray(val)
      ? val.join(', ')
      : typeof val === 'object' && val !== null
      ? JSON.stringify(val)
      : String(val);
    navigator.clipboard.writeText(textVal);
    setCopiedKey(key);
    if (onCopyToast) onCopyToast(`Copied ${key.replace(/_/g, ' ')} to clipboard`);
    setTimeout(() => setCopiedKey(null), 1800);
  };

  const formatKeyName = (key: string) => {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (l) => l.toUpperCase());
  };

  const isUnknown =
    document.doc_type === 'unknown' ||
    document.document_type === 'Unknown Document';

  if (fieldKeys.length === 0) {
    if (isUnknown) {
      const isAiAnalyzed = document.doc_type === 'ai_analyzed' || (document as any).is_local_ai;
      return (
        <div
          className="empty-fields-state unknown-doc-fields-state"
          style={{ textAlign: 'left', maxWidth: '640px', margin: '1.5rem auto' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
            <div
              className="unsupported-icon-circle"
              style={{ backgroundColor: 'rgba(99, 102, 241, 0.15)', color: '#818cf8' }}
            >
              <Sparkles size={24} />
            </div>
            <div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, margin: 0, color: 'var(--text-main)' }}>
                Unknown Document
              </h3>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                {isAiAnalyzed ? 'AI Document Analysis completed' : 'Offline OCR completed successfully'}
              </span>
            </div>
          </div>

          <p style={{ fontSize: '0.92rem', lineHeight: '1.5', color: 'var(--text-main)', marginBottom: '0.75rem' }}>
            {isAiAnalyzed
              ? 'This document was evaluated by AI Universal Intelligence.'
              : 'This document has been successfully scanned using Offline OCR.'}
          </p>
          <p style={{ fontSize: '0.88rem', lineHeight: '1.5', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
            {isAiAnalyzed
              ? 'Specific discrete key-value fields were not detected in standard format. You can inspect raw content in the "Extracted Text" tab or query the AI assistant.'
              : 'The document is not one of the 22 supported Offline document types, so structured extraction and verification are unavailable in Offline Mode.'}
          </p>

          {!isAiAnalyzed && (
            <>
              <div
                style={{
                  backgroundColor: 'rgba(255, 255, 255, 0.04)',
                  border: '1px solid var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: '1rem 1.25rem',
                  marginBottom: '1.5rem',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: '0.88rem', color: 'var(--text-main)', marginBottom: '0.5rem' }}>
                  You can switch to AI Mode for:
                </div>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: '1.25rem',
                    fontSize: '0.85rem',
                    color: 'var(--text-muted)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.35rem',
                  }}
                >
                  <li>Document identification</li>
                  <li>Detailed field extraction</li>
                  <li>Document understanding</li>
                  <li>Question answering</li>
                  <li>Summary generation</li>
                </ul>
              </div>

              {onSwitchToAiMode && (
                <button
                  className="btn btn-primary switch-ai-glow-btn"
                  onClick={onSwitchToAiMode}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  <Sparkles size={16} />
                  <span>Switch to AI Mode</span>
                  <ArrowRight size={15} />
                </button>
              )}
            </>
          )}
        </div>
      );
    }

    return (
      <div className="empty-fields-state">
        <AlertCircle size={36} className="empty-fields-icon" />
        <div className="empty-fields-title">No structured fields detected</div>
        <div className="empty-fields-subtitle">
          Document type is unclassified or no regex patterns matched. View the "Extracted Text" tab for full raw text.
        </div>
      </div>
    );
  }

  // Split into categories
  const personalKeys = fieldKeys.filter((k) => PERSONAL_KEYS.has(k.toLowerCase()));
  const documentKeys = fieldKeys.filter((k) => DOCUMENT_KEYS.has(k.toLowerCase()));
  const financialKeys = fieldKeys.filter((k) => FINANCIAL_KEYS.has(k.toLowerCase()));
  const otherKeys = fieldKeys.filter(
    (k) =>
      !PERSONAL_KEYS.has(k.toLowerCase()) &&
      !DOCUMENT_KEYS.has(k.toLowerCase()) &&
      !FINANCIAL_KEYS.has(k.toLowerCase())
  );

  const renderFieldItem = (key: string) => {
    const value = fields[key];
    const conf = confidences[key];
    const icon = getFieldIcon(key);
    const isNullOrEmpty = value === null || value === undefined || (typeof value === 'string' && value.trim() === '');
    const isBool = typeof value === 'boolean';

    return (
      <div key={key} className="field-item-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        <div className="field-item-header">
          <div className="field-label-wrap">
            <span className="field-type-icon">{icon}</span>
            <span className="field-label">{formatKeyName(key)}</span>
          </div>

          <div className="field-header-actions">
            {conf !== undefined && (
              <span
                className="field-conf-badge"
                style={{
                  color: conf >= 0.85 ? '#16a34a' : conf >= 0.65 ? '#ea580c' : '#dc2626',
                  backgroundColor:
                    conf >= 0.85
                      ? 'rgba(22, 163, 74, 0.1)'
                      : conf >= 0.65
                      ? 'rgba(234, 88, 12, 0.1)'
                      : 'rgba(220, 38, 38, 0.1)',
                }}
              >
                {Math.round(conf * 100)}%
              </span>
            )}
            <button
              type="button"
              className="copy-btn"
              onClick={() => handleCopy(key, isNullOrEmpty ? 'Not found' : isBool ? (value ? 'Yes' : 'No') : value)}
              title="Copy field value"
              aria-label={`Copy ${key}`}
            >
              {copiedKey === key ? <Check size={14} color="#16a34a" /> : <Copy size={14} />}
            </button>
          </div>
        </div>

        <div className="field-value-box">
          {isNullOrEmpty ? (
            <span className="field-text-value not-found" style={{ color: 'var(--text-subtle)', fontStyle: 'italic', fontWeight: 500 }}>
              Not found
            </span>
          ) : isBool ? (
            <span className="field-text-value" style={{ wordBreak: 'break-word', overflowWrap: 'anywhere', userSelect: 'text' }}>
              {value ? 'Yes' : 'No'}
            </span>
          ) : Array.isArray(value) ? (
            <div className="field-array-list">
              {value.map((item, idx) => (
                <span key={idx} className="field-tag-item" style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                  {typeof item === 'object' && item !== null
                    ? item.date
                      ? `${item.date} • ${item.type ? item.type + ' ' : ''}${item.amount} • Bal: ${item.balance || '-'} • ${item.description || ''}`
                      : JSON.stringify(item)
                    : String(item)}
                </span>
              ))}
            </div>
          ) : typeof value === 'object' && value !== null ? (
            <pre className="field-json-pre" style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>{JSON.stringify(value, null, 2)}</pre>
          ) : (
            <span className="field-text-value" style={{ wordBreak: 'break-word', overflowWrap: 'anywhere', userSelect: 'text' }}>
              {String(value)}
            </span>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="extracted-fields-wrapper">
      {document.cross_check && (
        <div
          className="cross-check-banner"
          style={{
            backgroundColor: document.cross_check.match ? 'var(--success-bg)' : 'var(--warning-bg)',
            borderColor: document.cross_check.match ? 'var(--success-border)' : 'var(--warning-border)',
          }}
        >
          <div className="cross-check-header">
            <ShieldCheck size={18} color={document.cross_check.match ? 'var(--success)' : 'var(--warning)'} />
            <span>Cross-Check Verification Score: {Math.round(document.cross_check.score * 100)}%</span>
          </div>
          {document.cross_check.discrepancies?.length > 0 && (
            <div className="cross-check-discrepancies">
              Discrepancies: {document.cross_check.discrepancies.join(', ')}
            </div>
          )}
        </div>
      )}

      <div className="field-sections-stack">
        {/* 1. Personal Information */}
        {personalKeys.length > 0 && (
          <SectionCard
            title="Personal Information"
            subtitle="Extracted identity, bio, and contact attributes"
            icon={<User size={18} />}
          >
            <div className="fields-two-column-grid">
              {personalKeys.map(renderFieldItem)}
            </div>
          </SectionCard>
        )}

        {/* 2. Document Information */}
        {documentKeys.length > 0 && (
          <SectionCard
            title="Document Information"
            subtitle="Document identifiers, validity dates, and registry parameters"
            icon={<CreditCard size={18} />}
          >
            <div className="fields-two-column-grid">
              {documentKeys.map(renderFieldItem)}
            </div>
          </SectionCard>
        )}

        {/* 3. Financial & Business Information */}
        {financialKeys.length > 0 && (
          <SectionCard
            title="Financial & Business Details"
            subtitle="Banking coordinates, compensations, and corporate data"
            icon={<Briefcase size={18} />}
          >
            <div className="fields-two-column-grid">
              {financialKeys.map(renderFieldItem)}
            </div>
          </SectionCard>
        )}

        {/* 4. Additional Extracted Data */}
        {otherKeys.length > 0 && (
          <SectionCard
            title={
              personalKeys.length === 0 && documentKeys.length === 0 && financialKeys.length === 0
                ? 'Extracted Document Fields'
                : 'Additional Extracted Fields'
            }
            subtitle="Other structural attributes discovered in the payload"
            icon={<Layers size={18} />}
          >
            <div className="fields-two-column-grid">
              {otherKeys.map(renderFieldItem)}
            </div>
          </SectionCard>
        )}
      </div>
    </div>
  );
};
