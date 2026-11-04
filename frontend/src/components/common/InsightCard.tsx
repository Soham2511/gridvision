import React from 'react';
import { Lightbulb, ShieldAlert, SunMedium, Zap, ArrowRight } from 'lucide-react';
import { BusinessInsight } from '../../types/analytics';
import { StatusBadge } from './StatusBadge';

interface InsightCardProps {
  insight: BusinessInsight;
  onActionClick?: (id: string) => void;
}

export const InsightCard: React.FC<InsightCardProps> = ({ insight, onActionClick }) => {
  const getCategoryIcon = () => {
    switch (insight.category) {
      case 'peak_shaving':
        return <Zap size={16} color="var(--gv-color-grid-blue)" />;
      case 'efficiency':
        return <Lightbulb size={16} color="var(--gv-color-smart-teal)" />;
      case 'renewable':
        return <SunMedium size={16} color="var(--gv-color-energy-amber)" />;
      case 'grid_stress':
        return <ShieldAlert size={16} color="var(--gv-status-danger)" />;
      default:
        return <Lightbulb size={16} color="var(--gv-color-grid-blue)" />;
    }
  };

  const getCategoryLabel = () => {
    switch (insight.category) {
      case 'peak_shaving':
        return 'Peak Shaving';
      case 'efficiency':
        return 'Energy Efficiency';
      case 'renewable':
        return 'Renewable Integration';
      case 'grid_stress':
        return 'Grid Stress';
      default:
        return 'Takeaway';
    }
  };

  return (
    <div
      className="gv-card"
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        borderLeft: '4px solid var(--gv-color-grid-blue)',
      }}
    >
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.65rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            {getCategoryIcon()}
            <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--gv-text-muted)' }}>
              {getCategoryLabel()}
            </span>
          </div>
          <StatusBadge status={insight.urgency} label={`${insight.urgency} Priority`} />
        </div>

        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--gv-text-primary)', marginBottom: '0.45rem' }}>
          {insight.title}
        </h4>

        <p style={{ fontSize: '0.82rem', color: 'var(--gv-text-secondary)', lineHeight: 1.45, marginBottom: '0.85rem' }}>
          {insight.description}
        </p>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '0.5rem',
            background: 'var(--gv-bg-surface-subtle)',
            padding: '0.6rem 0.75rem',
            borderRadius: 'var(--gv-radius-md)',
            marginBottom: '0.75rem',
          }}
        >
          <div>
            <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--gv-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
              Target Impact
            </span>
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--gv-color-grid-blue)' }}>
              {insight.impactMetric}
            </span>
          </div>
          <div>
            <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--gv-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
              Potential Value
            </span>
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--gv-color-smart-teal)' }}>
              {insight.potentialValue}
            </span>
          </div>
        </div>
      </div>

      <div
        style={{
          borderTop: '1px solid var(--gv-border-subtle)',
          paddingTop: '0.65rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--gv-text-muted)', fontStyle: 'italic', maxWidth: '75%' }}>
          {insight.actionableRecommendation}
        </span>
        <button
          type="button"
          onClick={() => onActionClick && onActionClick(insight.id)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            fontSize: '0.75rem',
            fontWeight: 700,
            color: 'var(--gv-color-grid-blue)',
            cursor: 'pointer',
          }}
        >
          <span>Act</span>
          <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
};
