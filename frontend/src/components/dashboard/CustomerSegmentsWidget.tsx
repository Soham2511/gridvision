import React from 'react';
import { Users, Building, Landmark, ArrowUpRight } from 'lucide-react';
import { CustomerSegment } from '../../types/analytics';

interface CustomerSegmentsWidgetProps {
  segments: CustomerSegment[];
}

export const CustomerSegmentsWidget: React.FC<CustomerSegmentsWidgetProps> = ({ segments }) => {
  const getSegmentIcon = (id: string) => {
    switch (id) {
      case 'seg-comm-ind':
        return <Building size={16} color="var(--gv-color-grid-blue)" />;
      case 'seg-residential':
        return <Users size={16} color="var(--gv-color-smart-teal)" />;
      case 'seg-gov-inst':
        return <Landmark size={16} color="var(--gv-color-energy-amber)" />;
      default:
        return <Building size={16} color="var(--gv-color-grid-blue)" />;
    }
  };

  return (
    <div className="gv-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <div>
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Segmentation Intelligence
            </span>
            <h3 className="gv-heading-2" style={{ marginTop: '0.2rem' }}>
              Customer & Asset Breakdown
            </h3>
          </div>
          <span className="gv-badge gv-badge-neutral">
            3 Primary Classes
          </span>
        </div>

        {/* Multi-segment stacked progress bar */}
        <div style={{ marginBottom: '1.25rem' }}>
          <div
            style={{
              display: 'flex',
              height: '12px',
              borderRadius: 'var(--gv-radius-full)',
              overflow: 'hidden',
              marginBottom: '0.5rem',
            }}
          >
            {segments.map((seg) => (
              <div
                key={seg.id}
                style={{
                  width: `${seg.sharePercentage}%`,
                  background: seg.color,
                  transition: 'width 0.4s ease',
                }}
                title={`${seg.name}: ${seg.sharePercentage}%`}
              />
            ))}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--gv-text-muted)' }}>
            {segments.map((seg) => (
              <span key={seg.id} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: seg.color }} />
                {seg.name.split(' ')[0]} ({seg.sharePercentage}%)
              </span>
            ))}
          </div>
        </div>

        {/* Detailed Segment Cards */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {segments.map((seg) => (
            <div
              key={seg.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.75rem',
                borderRadius: 'var(--gv-radius-md)',
                background: 'var(--gv-bg-surface-subtle)',
                border: '1px solid var(--gv-border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <div
                  style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: 'var(--gv-radius-md)',
                    background: '#FFFFFF',
                    border: '1px solid var(--gv-border-subtle)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {getSegmentIcon(seg.id)}
                </div>
                <div>
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--gv-text-primary)' }}>
                    {seg.name}
                  </h4>
                  <p style={{ fontSize: '0.72rem', color: 'var(--gv-text-muted)' }}>
                    {seg.entityCount.toLocaleString()} tracked meters • {seg.description}
                  </p>
                </div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 700, fontFamily: 'var(--gv-font-mono)', color: 'var(--gv-text-primary)' }}>
                  {seg.demandMwh} MWh
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '0.2rem', fontSize: '0.7rem', color: seg.growthPct >= 0 ? 'var(--gv-color-smart-teal)' : 'var(--gv-color-grid-blue)', fontWeight: 600 }}>
                  <ArrowUpRight size={11} />
                  <span>{seg.growthPct > 0 ? `+${seg.growthPct}%` : `${seg.growthPct}%`} YoY</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--gv-border-subtle)', fontSize: '0.73rem', color: 'var(--gv-text-muted)' }}>
        Asset profiling based on Building Data Genome 2 (BDG2) archetype classification.
      </div>
    </div>
  );
};
