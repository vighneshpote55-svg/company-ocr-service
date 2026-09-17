import React from 'react';

export interface SectionCardProps {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export const SectionCard: React.FC<SectionCardProps> = ({
  title,
  subtitle,
  icon,
  action,
  children,
  className = '',
}) => {
  return (
    <section className={`section-card ${className}`}>
      <div className="section-card-header">
        <div className="section-card-title-group">
          {icon && <span className="section-card-icon">{icon}</span>}
          <div>
            <h3 className="section-card-title">{title}</h3>
            {subtitle && <p className="section-card-subtitle">{subtitle}</p>}
          </div>
        </div>
        {action && <div className="section-card-action">{action}</div>}
      </div>
      <div className="section-card-content">{children}</div>
    </section>
  );
};
