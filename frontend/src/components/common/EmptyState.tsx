import React from 'react';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No Data Available',
  description = 'There are no active records matching the selected query or timeframe.',
  icon = <Inbox size={36} color="var(--gv-text-muted)" />,
  action,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '3rem 1.5rem',
        textAlign: 'center',
        background: 'var(--gv-bg-surface-subtle)',
        borderRadius: 'var(--gv-radius-lg)',
        border: '1px dashed var(--gv-border-medium)',
      }}
    >
      <div style={{ marginBottom: '1rem' }}>{icon}</div>
      <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--gv-text-primary)', marginBottom: '0.35rem' }}>
        {title}
      </h4>
      <p style={{ fontSize: '0.85rem', color: 'var(--gv-text-secondary)', maxWidth: '400px', marginBottom: action ? '1.25rem' : 0 }}>
        {description}
      </p>
      {action && <div>{action}</div>}
    </div>
  );
};
