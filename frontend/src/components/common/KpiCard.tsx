import React from 'react';
import { ArrowUpRight, ArrowDownRight, Minus, Zap, TrendingUp, AlertTriangle, Activity, BarChart2 } from 'lucide-react';
import { KpiMetric } from '../../types/analytics';

interface KpiCardProps {
  metric: KpiMetric;
}

/**
 * KpiCard
 * Standard KPI Metric Card with increased height and spacious layout.
 * Symbol is kept at the top-right/top-left, with value and trend cleanly aligned.
 */
export const KpiCard: React.FC<KpiCardProps> = ({ metric }) => {
  const getCategoryIcon = () => {
    switch (metric.category) {
      case 'consumption':
        return <Zap size={18} color="var(--gv-color-smart-teal)" />;
      case 'forecast':
        return <TrendingUp size={18} color="var(--gv-color-grid-blue)" />;
      case 'peak':
        return <Activity size={18} color="var(--gv-color-energy-amber)" />;
      case 'anomaly':
        return <AlertTriangle size={18} color="var(--gv-status-danger)" />;
      case 'efficiency':
        return <BarChart2 size={18} color="var(--gv-color-smart-teal)" />;
      default:
        return <Zap size={18} color="var(--gv-color-grid-blue)" />;
    }
  };

  const changePercent = metric.changePercent ?? 0;
  const isPositiveDelta = changePercent > 0;
  const isNeutralDelta = changePercent === 0;

  // For consumption/peak/anomaly, lower is often better; for efficiency, higher is better.
  const isGoodTrend = metric.isPositiveGood !== undefined ? (metric.isPositiveGood ? isPositiveDelta : !isPositiveDelta) : true;

  return (
    <div
      className="gv-card"
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        minHeight: '168px',
        padding: '1.5rem',
        boxSizing: 'border-box',
      }}
    >
      {/* Top Row: Symbol at top with Title */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.85rem' }}>
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: 'var(--gv-radius-md)',
              background: 'var(--gv-bg-surface-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {getCategoryIcon()}
          </div>
          <span
            style={{
              fontSize: '0.74rem',
              fontWeight: 600,
              color: 'var(--gv-text-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
            }}
          >
            {metric.category}
          </span>
        </div>

        <div style={{ fontSize: '0.84rem', color: 'var(--gv-text-muted)', fontWeight: 500, marginBottom: '0.35rem' }}>
          {metric.title}
        </div>
      </div>

      {/* Bottom Block: Value on left, Trend on right */}
      <div style={{ marginTop: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.35rem' }}>
            <span style={{ fontSize: '1.95rem', fontWeight: 800, color: 'var(--gv-text-primary)', letterSpacing: '-0.02em', lineHeight: 1 }}>
              {metric.value}
            </span>
            {metric.unit && (
              <span style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>
                {metric.unit}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', textAlign: 'right' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.2rem',
                fontSize: '0.8rem',
                fontWeight: 700,
                padding: '0.15rem 0.45rem',
                borderRadius: 'var(--gv-radius-sm)',
                background: isNeutralDelta
                  ? 'var(--gv-bg-surface-subtle)'
                  : isGoodTrend
                  ? 'var(--gv-status-success-bg)'
                  : 'var(--gv-status-warning-bg)',
                color: isNeutralDelta
                  ? 'var(--gv-text-muted)'
                  : isGoodTrend
                  ? 'var(--gv-status-success)'
                  : '#B45309',
              }}
            >
              {isNeutralDelta ? (
                <Minus size={12} />
              ) : isPositiveDelta ? (
                <ArrowUpRight size={12} />
              ) : (
                <ArrowDownRight size={12} />
              )}
              {Math.abs(changePercent)}%
            </span>
            {metric.changePeriod && (
              <span style={{ fontSize: '0.68rem', color: 'var(--gv-text-muted)', marginTop: '2px' }}>
                {metric.changePeriod}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
