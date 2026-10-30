import React from 'react';

export interface MetricTrendInfo {
  value: number | string;
  direction?: 'up' | 'down' | 'neutral';
  isIncreaseNegative?: boolean; // In energy consumption, higher usage is often marked red (up = warning)
  comparisonText?: string; // e.g. "vs previous 7 days (15.0 kWh)"
}

export interface CommonMetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  icon: React.ReactNode;
  iconBg?: string;
  badgeText?: string;
  badgeColor?: string;
  badgeBg?: string;
  trend?: MetricTrendInfo;
  subtext?: string;
  hoverBorderColor?: string;
  onClick?: () => void;
}

/**
 * CommonMetricCard
 * Reusable metric card object used across all GridVision analytics dashboards.
 * 
 * Layout Architecture:
 * - Height: Tuned balanced height (min-height 150px) with comfortable breathing room.
 * - Top Row: Icon symbol badge at the top-left (42x42px rounded container),
 *   with optional top-right status badge.
 * - Bottom Block:
 *   - Title label positioned cleanly above the metrics.
 *   - Content row: Large metric value + unit on the LEFT.
 *   - Trend info: Increased prominence percentage size (1.08rem, bold) and comparison note strictly on the RIGHT.
 * 
 * Guarantees identical horizontal and vertical baselines across cards with and without percentage.
 */
export const CommonMetricCard: React.FC<CommonMetricCardProps> = ({
  title,
  value,
  unit = 'kWh',
  icon,
  iconBg = '#E6F7F5',
  badgeText,
  badgeColor = '#00A396',
  badgeBg = 'rgba(0, 163, 150, 0.1)',
  trend,
  subtext,
  hoverBorderColor = 'rgba(0, 163, 150, 0.35)',
  onClick,
}) => {
  const isUp = trend?.direction === 'up' || (typeof trend?.value === 'number' && trend.value > 0);
  const isDown = trend?.direction === 'down' || (typeof trend?.value === 'number' && trend.value < 0);

  // In energy consumption, increased demand is flagged in red, decreased in green
  const trendColor = trend?.isIncreaseNegative
    ? isUp
      ? '#EF4444'
      : '#10B981'
    : isUp
    ? '#10B981'
    : '#EF4444';

  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      style={{
        backgroundColor: '#FFFFFF',
        borderRadius: '16px',
        border: '1px solid #E2E8F0',
        padding: '1.35rem 1.45rem',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        boxShadow: '0 2px 8px rgba(11, 31, 51, 0.03)',
        transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
        minHeight: '150px',
        boxSizing: 'border-box',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.boxShadow = '0 12px 24px -4px rgba(11, 31, 51, 0.08)';
        e.currentTarget.style.borderColor = hoverBorderColor;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = '0 2px 8px rgba(11, 31, 51, 0.03)';
        e.currentTarget.style.borderColor = '#E2E8F0';
      }}
    >
      {/* Top Row: Symbol / Icon at top-left, optional status badge at top-right */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div
          style={{
            width: '42px',
            height: '42px',
            borderRadius: '12px',
            backgroundColor: iconBg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          {icon}
        </div>

        {badgeText && (
          <span
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              padding: '3px 8px',
              borderRadius: '999px',
              backgroundColor: badgeBg,
              color: badgeColor,
              letterSpacing: '0.02em',
            }}
          >
            {badgeText}
          </span>
        )}
      </div>

      {/* Bottom Block: Title on top, Row with Value on left and Trend on right */}
      <div style={{ marginTop: '0.95rem' }}>
        {/* Title: Identical height and vertical position across all cards */}
        <div
          style={{
            fontSize: '0.84rem',
            color: '#64748B',
            fontWeight: 500,
            marginBottom: '0.35rem',
            lineHeight: 1.2,
          }}
        >
          {title}
        </div>

        {/* Row: Metric Value on Left, Trend on Right */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'space-between',
            gap: '0.75rem',
          }}
        >
          {/* Left: Value & Unit */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.35rem' }}>
            <span
              style={{
                fontSize: '1.95rem',
                fontWeight: 800,
                color: '#0B1F33',
                letterSpacing: '-0.025em',
                lineHeight: 1,
              }}
            >
              {value}
            </span>
            {unit && (
              <span style={{ fontSize: '0.95rem', fontWeight: 600, color: '#64748B' }}>
                {unit}
              </span>
            )}
          </div>

          {/* Right: Trend percentage (increased font size) & comparison text strictly aligned on right */}
          {trend ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-end',
                textAlign: 'right',
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '2px',
                  color: trendColor,
                  fontWeight: 800,
                  fontSize: '1.08rem',
                  lineHeight: 1.15,
                }}
              >
                <span style={{ fontSize: '1.18rem', fontWeight: 800 }}>
                  {isUp ? '↑' : isDown ? '↓' : ''}
                </span>
                <span>{trend.value}%</span>
              </div>
              {trend.comparisonText && (
                <span
                  style={{
                    fontSize: '0.7rem',
                    color: '#94A3B8',
                    marginTop: '2px',
                    whiteSpace: 'nowrap',
                    fontWeight: 400,
                  }}
                >
                  {trend.comparisonText}
                </span>
              )}
            </div>
          ) : subtext ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-end',
                textAlign: 'right',
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: '0.72rem', color: '#94A3B8' }}>{subtext}</span>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
