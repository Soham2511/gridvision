import React from 'react';

export interface CommonChartHoverCardProps {
  active?: boolean;
  payload?: Array<{
    value: number | null | undefined;
    name?: string;
    dataKey?: string;
    color?: string;
    stroke?: string;
    fill?: string;
    payload?: {
      fullDate?: string;
      date?: string;
      totalConsumption?: number;
      [key: string]: unknown;
    };
  }>;
  label?: string;
  unit?: string;
  tariffRate?: number;
  peakTimes?: string[];
  datePrefix?: string;
}

/**
 * CommonChartHoverCard
 * Reusable graph hover tooltip object used across all charts in GridVision.
 * 
 * Modes:
 * 1. Historical Daily Demand Mode:
 *    Displays Peak Daily Demand, Average Daily Demand, and Total Consumption with exact styling matching the design.
 * 2. Real-Time Telemetry / Forecast Mode:
 *    Displays observed telemetry vs forward model predictions, peak demand badge, and tariff cost calculation.
 */
export const CommonChartHoverCard: React.FC<CommonChartHoverCardProps> = ({
  active,
  payload,
  label,
  unit = 'kWh',
  tariffRate = 10.0,
  peakTimes = ['09:00', '20:00', '20:30'],
  datePrefix = '19 Oct 2026',
}) => {
  if (!active || !payload || !payload.length) return null;

  // 1. Check if this is a historical daily demand chart
  const peakDailyItem = payload.find(
    (p) => p.dataKey === 'peakDemand' || p.name === 'Peak Daily Demand'
  );
  const avgDailyItem = payload.find(
    (p) => p.dataKey === 'avgDemand' || p.name === 'Average Daily Demand'
  );

  if (peakDailyItem || avgDailyItem) {
    const rowData = payload[0]?.payload || {};
    const dateTitle = rowData.fullDate || label;
    const totalVal = rowData.totalConsumption;

    return (
      <div
        style={{
          backgroundColor: '#FFFFFF',
          border: '1px solid #E2E8F0',
          borderRadius: '10px',
          padding: '0.85rem 1.15rem',
          boxShadow: '0 10px 25px -4px rgba(11, 31, 51, 0.12), 0 2px 6px rgba(11, 31, 51, 0.04)',
          minWidth: '220px',
          pointerEvents: 'none',
        }}
      >
        <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0B1F33', marginBottom: '0.65rem' }}>
          {dateTitle}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem', fontSize: '0.78rem' }}>
          {peakDailyItem && peakDailyItem.value !== undefined && peakDailyItem.value !== null && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#64748B' }}>
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: '#2563EB',
                    display: 'inline-block',
                    flexShrink: 0,
                  }}
                />
                <span>Peak Daily Demand</span>
              </div>
              <strong style={{ color: '#0B1F33', fontWeight: 700 }}>
                {Number(peakDailyItem.value).toFixed(1)} {unit}
              </strong>
            </div>
          )}

          {avgDailyItem && avgDailyItem.value !== undefined && avgDailyItem.value !== null && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#64748B' }}>
                <span
                  style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: '#00A396',
                    display: 'inline-block',
                    flexShrink: 0,
                  }}
                />
                <span>Average Daily Demand</span>
              </div>
              <strong style={{ color: '#0B1F33', fontWeight: 700 }}>
                {Number(avgDailyItem.value).toFixed(1)} {unit}
              </strong>
            </div>
          )}

          {totalVal !== undefined && totalVal !== null && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '1rem',
                borderTop: '1px solid #F1F5F9',
                paddingTop: '0.45rem',
                marginTop: '0.2rem',
              }}
            >
              <span style={{ color: '#0B1F33', fontWeight: 700 }}>Total Consumption</span>
              <strong style={{ color: '#0B1F33', fontWeight: 800 }}>
                {Number(totalVal).toFixed(1)} {unit}
              </strong>
            </div>
          )}
        </div>
      </div>
    );
  }

  // 2. Real-time Telemetry / Forecast Mode
  const actualItem = payload.find(
    (p) =>
      p.dataKey === 'actualConsumption' ||
      p.dataKey === 'actual' ||
      p.dataKey === 'demand' ||
      p.dataKey === 'actualDemand'
  );
  const predictedItem = payload.find(
    (p) =>
      p.dataKey === 'predictedConsumption' ||
      p.dataKey === 'forecast' ||
      p.dataKey === 'predictedDemand'
  );

  const isPredicted =
    predictedItem &&
    predictedItem.value !== null &&
    predictedItem.value !== undefined &&
    (!actualItem || actualItem.value === null || actualItem.value === undefined);

  const activeValue = isPredicted ? predictedItem?.value : (actualItem?.value ?? payload[0]?.value);

  const isPeak = label ? peakTimes.includes(label) : false;
  const tariffCost = typeof activeValue === 'number' ? (activeValue * tariffRate).toFixed(2) : null;

  return (
    <div
      style={{
        backgroundColor: 'rgba(255, 255, 255, 0.98)',
        backdropFilter: 'blur(12px)',
        border: '1px solid #E2E8F0',
        borderRadius: '12px',
        padding: '0.85rem 1.15rem',
        boxShadow: '0 12px 28px -4px rgba(11, 31, 51, 0.14), 0 4px 10px -2px rgba(11, 31, 51, 0.04)',
        minWidth: '200px',
        pointerEvents: 'none',
      }}
    >
      {/* Tooltip Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.75rem',
          marginBottom: '0.5rem',
          paddingBottom: '0.45rem',
          borderBottom: '1px solid #F1F5F9',
        }}
      >
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748B' }}>
          {datePrefix ? `${datePrefix}, ` : ''}{label}
        </span>
        <span
          style={{
            fontSize: '0.65rem',
            fontWeight: 700,
            padding: '2px 7px',
            borderRadius: '999px',
            backgroundColor: isPredicted ? 'rgba(139, 92, 246, 0.12)' : 'rgba(0, 163, 150, 0.12)',
            color: isPredicted ? '#7C3AED' : '#00A396',
          }}
        >
          {isPredicted ? 'Model Forecast' : 'Observed Telemetry'}
        </span>
      </div>

      {/* Primary Value Display */}
      {typeof activeValue === 'number' ? (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.35rem', marginBottom: '0.4rem' }}>
          <span style={{ fontSize: '1.5rem', fontWeight: 800, color: '#0B1F33', letterSpacing: '-0.02em' }}>
            {activeValue.toFixed(1)}
          </span>
          <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#64748B' }}>
            {unit}
          </span>
        </div>
      ) : null}

      {/* Multi-series Breakdown if both values exist */}
      {actualItem && predictedItem && actualItem.value !== null && predictedItem.value !== null ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', margin: '0.35rem 0', fontSize: '0.74rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748B' }}>
            <span>Observed:</span>
            <strong style={{ color: '#00A396' }}>{actualItem.value?.toFixed(1)} {unit}</strong>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748B' }}>
            <span>Forecast:</span>
            <strong style={{ color: '#8B5CF6' }}>{predictedItem.value?.toFixed(1)} {unit}</strong>
          </div>
        </div>
      ) : null}

      {/* Insights footer */}
      <div style={{ fontSize: '0.72rem', color: '#64748B', display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '0.35rem' }}>
        {isPeak && (
          <div style={{ color: isPredicted ? '#7C3AED' : '#00A396', fontWeight: 700 }}>
            ★ {isPredicted ? 'Evening Peak Demand Window' : 'Daytime Peak Demand Window'}
          </div>
        )}
        {tariffCost && (
          <div>
            Estimated Cost: <strong style={{ color: '#0B1F33' }}>₹{tariffCost}</strong> (flat ₹{tariffRate.toFixed(0)}/{unit})
          </div>
        )}
      </div>
    </div>
  );
};
