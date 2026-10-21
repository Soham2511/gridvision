import React from 'react';
import { RefreshCw, Radio } from 'lucide-react';

interface PageHeaderProps {
  title: string;
  description?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  badge,
  actions,
  onRefresh,
  isRefreshing = false,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '1.5rem',
        flexWrap: 'wrap',
        gap: '1rem',
      }}
    >
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.35rem' }}>
          <h1 className="gv-heading-1">{title}</h1>
          {badge}
        </div>
        {description && (
          <p className="gv-text-subtle" style={{ maxWidth: '800px' }}>
            {description}
          </p>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <div className="gv-mock-notice">
          <Radio size={14} color="var(--gv-color-grid-blue)" />
          <span>Demonstration Mode • Mock Telemetry</span>
        </div>

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.45rem 0.85rem',
              background: 'var(--gv-bg-surface)',
              border: '1px solid var(--gv-border-subtle)',
              borderRadius: 'var(--gv-radius-md)',
              fontSize: '0.8rem',
              fontWeight: 600,
              color: 'var(--gv-text-secondary)',
              cursor: 'pointer',
              transition: 'all var(--gv-transition-fast)',
            }}
            title="Refresh dashboard data"
          >
            <RefreshCw
              size={14}
              style={{
                animation: isRefreshing ? 'spin 1s linear infinite' : 'none',
              }}
            />
            <span>Refresh</span>
          </button>
        )}

        {actions}
      </div>
    </div>
  );
};
