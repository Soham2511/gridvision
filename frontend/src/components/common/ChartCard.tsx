import React from 'react';

interface ChartCardProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  height?: string | number;
}

export const ChartCard: React.FC<ChartCardProps> = ({
  title,
  subtitle,
  actions,
  children,
  footer,
  height = '340px',
}) => {
  return (
    <div className="gv-card" style={{ display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: '1.25rem',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        <div>
          <h3 className="gv-heading-3">{title}</h3>
          {subtitle && (
            <p className="gv-text-muted" style={{ marginTop: '0.2rem' }}>
              {subtitle}
            </p>
          )}
        </div>
        {actions && <div>{actions}</div>}
      </div>

      <div style={{ height, width: '100%', position: 'relative' }}>
        {children}
      </div>

      {footer && (
        <div
          style={{
            marginTop: '1rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid var(--gv-border-subtle)',
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
};
