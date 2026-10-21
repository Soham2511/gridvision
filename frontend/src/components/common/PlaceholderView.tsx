import React from 'react';
import { PageHeader } from './PageHeader';
import { Cpu } from 'lucide-react';

interface PlannedFeature {
  title: string;
  description: string;
  deliverablePhase: string;
  backendIntegration: string;
}

interface PlaceholderViewProps {
  pageTitle: string;
  pageDescription: string;
  phaseTag: string;
  icon: React.ReactNode;
  overviewSummary: string;
  plannedFeatures: PlannedFeature[];
}

export const PlaceholderView: React.FC<PlaceholderViewProps> = ({
  pageTitle,
  pageDescription,
  phaseTag,
  icon,
  overviewSummary,
  plannedFeatures,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <PageHeader
        title={pageTitle}
        description={pageDescription}
        badge={<span className="gv-badge gv-badge-info">{phaseTag}</span>}
      />

      {/* Overview Banner */}
      <div
        className="gv-card"
        style={{
          borderLeft: '4px solid var(--gv-color-smart-teal)',
          background: 'linear-gradient(180deg, #FFFFFF, var(--gv-bg-surface-subtle))',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: 'var(--gv-radius-md)',
              background: 'var(--gv-status-success-bg)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--gv-color-smart-teal)',
              flexShrink: 0,
            }}
          >
            {icon}
          </div>
          <div>
            <h3 className="gv-heading-2" style={{ marginBottom: '0.35rem' }}>
              Planned Capability Scope
            </h3>
            <p className="gv-text-subtle" style={{ lineHeight: 1.5, maxWidth: '900px' }}>
              {overviewSummary}
            </p>
          </div>
        </div>
      </div>

      {/* Architecture & Engineering Specifications */}
      <div>
        <h3 className="gv-heading-3" style={{ marginBottom: '0.85rem' }}>
          Planned Implementation Roadmap & Endpoints
        </h3>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '1.25rem',
          }}
        >
          {plannedFeatures.map((feat, index) => (
            <div
              key={index}
              className="gv-card"
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.65rem' }}>
                  <span className="gv-badge gv-badge-neutral">{feat.deliverablePhase}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: 'var(--gv-color-grid-blue)', fontSize: '0.72rem', fontWeight: 600 }}>
                    <Cpu size={12} />
                    <span>MLflow / Flask</span>
                  </div>
                </div>

                <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--gv-text-primary)', marginBottom: '0.45rem' }}>
                  {feat.title}
                </h4>

                <p style={{ fontSize: '0.8rem', color: 'var(--gv-text-secondary)', lineHeight: 1.45, marginBottom: '0.85rem' }}>
                  {feat.description}
                </p>
              </div>

              <div
                style={{
                  background: 'var(--gv-bg-surface-subtle)',
                  padding: '0.55rem 0.75rem',
                  borderRadius: 'var(--gv-radius-md)',
                  fontSize: '0.72rem',
                  color: 'var(--gv-text-muted)',
                  borderTop: '1px solid var(--gv-border-subtle)',
                }}
              >
                <div style={{ fontWeight: 600, color: 'var(--gv-text-secondary)', marginBottom: '0.2rem' }}>
                  Target Endpoint Contract:
                </div>
                <code style={{ fontFamily: 'var(--gv-font-mono)', color: 'var(--gv-color-grid-blue)' }}>
                  {feat.backendIntegration}
                </code>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
