import React from 'react';
import { Activity, Clock, ShieldAlert } from 'lucide-react';
import { PeakDemandSummary } from '../../types/analytics';
import { StatusBadge } from '../common/StatusBadge';

interface PeakDemandWidgetProps {
  data: PeakDemandSummary;
}

export const PeakDemandWidget: React.FC<PeakDemandWidgetProps> = ({ data }) => {
  const currentRatio = (data.currentLoadMw / data.peakCapacityLimitMw) * 100;
  const peakRatio = (data.expectedPeakMw / data.peakCapacityLimitMw) * 100;

  return (
    <div className="gv-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <div>
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Peak Demand Summary
            </span>
            <h3 className="gv-heading-2" style={{ marginTop: '0.2rem' }}>
              Capacity & Risk Monitor
            </h3>
          </div>
          <StatusBadge status={data.riskLevel} label={`${data.riskLevel.toUpperCase()} RISK`} />
        </div>

        {/* Big Peak Metric Card */}
        <div
          style={{
            background: 'var(--gv-bg-surface-subtle)',
            borderRadius: 'var(--gv-radius-md)',
            padding: '1rem',
            border: '1px solid var(--gv-border-subtle)',
            marginBottom: '1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--gv-text-muted)', fontSize: '0.75rem', marginBottom: '0.35rem' }}>
            <Activity size={14} color="var(--gv-color-energy-amber)" />
            <span style={{ fontWeight: 600 }}>ANTICIPATED PEAK LOAD</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem' }}>
            <span style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--gv-text-primary)', letterSpacing: '-0.02em', lineHeight: 1 }}>
              {data.expectedPeakMw}
            </span>
            <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>
              MW
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--gv-text-secondary)', fontSize: '0.75rem', marginTop: '0.45rem' }}>
            <Clock size={13} color="var(--gv-color-grid-blue)" />
            <span style={{ fontWeight: 500 }}>Window: {data.expectedPeakTime}</span>
          </div>
        </div>

        {/* Capacity Limit Visual Meter */}
        <div style={{ marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 600, marginBottom: '0.35rem' }}>
            <span style={{ color: 'var(--gv-text-secondary)' }}>Grid Capacity Utilization</span>
            <span style={{ color: 'var(--gv-text-primary)', fontFamily: 'var(--gv-font-mono)' }}>
              {data.currentLoadMw} MW / {data.peakCapacityLimitMw} MW ({Math.round(currentRatio)}%)
            </span>
          </div>

          {/* Progress Bar Container */}
          <div
            style={{
              position: 'relative',
              height: '10px',
              background: '#E2E8F0',
              borderRadius: 'var(--gv-radius-full)',
              overflow: 'hidden',
            }}
          >
            {/* Current Load Fill */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                height: '100%',
                width: `${currentRatio}%`,
                background: 'var(--gv-color-smart-teal)',
                borderRadius: 'var(--gv-radius-full)',
                zIndex: 2,
              }}
            />
            {/* Projected Peak Fill (Ghost) */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                height: '100%',
                width: `${peakRatio}%`,
                background: 'rgba(255, 194, 71, 0.4)',
                borderRight: '2px solid var(--gv-color-energy-amber)',
                zIndex: 1,
              }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--gv-text-muted)', marginTop: '0.35rem' }}>
            <span>Reserve Margin: <strong style={{ color: 'var(--gv-color-smart-teal)' }}>{data.reserveMarginPct}%</strong></span>
            <span>Historical Cycle Peak: {data.historicalCyclePeakMw} MW</span>
          </div>
        </div>
      </div>

      {/* Mitigation Strategy Alert Box */}
      <div
        style={{
          background: 'rgba(8, 126, 189, 0.06)',
          border: '1px solid rgba(8, 126, 189, 0.2)',
          borderRadius: 'var(--gv-radius-md)',
          padding: '0.75rem 0.85rem',
          display: 'flex',
          gap: '0.65rem',
        }}
      >
        <ShieldAlert size={16} color="var(--gv-color-grid-blue)" style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--gv-color-grid-blue)', textTransform: 'uppercase' }}>
            Recommended Protocol
          </span>
          <p style={{ fontSize: '0.78rem', color: 'var(--gv-text-secondary)', marginTop: '0.15rem', lineHeight: 1.35 }}>
            {data.mitigationStrategy}
          </p>
        </div>
      </div>
    </div>
  );
};
