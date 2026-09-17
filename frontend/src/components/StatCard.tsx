import React from 'react';

export interface StatCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  icon: React.ReactNode;
  iconBg?: string;
  iconColor?: string;
  onClick?: () => void;
  badge?: {
    text: string;
    type?: 'success' | 'warning' | 'info' | 'neutral';
  };
  className?: string;
  gradient?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  subtext,
  icon,
  iconBg = 'rgba(37, 99, 235, 0.1)',
  iconColor = 'var(--primary)',
  onClick,
  badge,
  className = '',
  gradient,
}) => {
  return (
    <div
      className={`premium-analytics-card ${onClick ? 'interactive' : ''} ${className}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      style={{
        background: gradient || undefined,
      }}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <div className="analytics-card-header">
        <span className="analytics-card-label">{label}</span>
        <div
          className="analytics-icon-circle"
          style={{ backgroundColor: iconBg, color: iconColor }}
          aria-hidden="true"
        >
          {icon}
        </div>
      </div>

      <div className="analytics-card-body">
        <div className="analytics-card-value">{value}</div>
        {(subtext || badge) && (
          <div className="analytics-meta-row">
            {badge && (
              <span className={`analytics-badge badge-${badge.type || 'neutral'}`}>
                {badge.text}
              </span>
            )}
            {subtext && <span className="analytics-subtext">{subtext}</span>}
          </div>
        )}
      </div>
    </div>
  );
};
