import React from 'react';
import { AlertCircle, RotateCcw } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Data Retrieval Error',
  message = 'An unexpected error occurred while communicating with the telemetry service.',
  onRetry,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2.5rem 1.5rem',
        textAlign: 'center',
        background: 'var(--gv-status-danger-bg)',
        borderRadius: 'var(--gv-radius-lg)',
        border: '1px solid rgba(239, 68, 68, 0.3)',
      }}
    >
      <AlertCircle size={36} color="var(--gv-status-danger)" style={{ marginBottom: '0.75rem' }} />
      <h4 style={{ fontSize: '1rem', fontWeight: 700, color: '#991B1B', marginBottom: '0.35rem' }}>
        {title}
      </h4>
      <p style={{ fontSize: '0.85rem', color: '#B91C1C', maxWidth: '420px', marginBottom: onRetry ? '1rem' : 0 }}>
        {message}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.45rem 1rem',
            background: 'var(--gv-status-danger)',
            color: '#FFFFFF',
            borderRadius: 'var(--gv-radius-md)',
            fontSize: '0.8rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          <RotateCcw size={14} />
          <span>Retry Operation</span>
        </button>
      )}
    </div>
  );
};
