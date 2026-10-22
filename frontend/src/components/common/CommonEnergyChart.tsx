import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
} from 'recharts';
import { Activity } from 'lucide-react';
import { CommonChartHoverCard } from './CommonChartHoverCard';
import { HouseholdConsumptionPoint } from '../../types/analytics';

export interface ChartCalloutPoint {
  time: string;
  value: number;
  dateText: string;
  label: string;
  color: string;
}

export interface CommonEnergyChartProps {
  title?: string;
  subtitle?: string;
  data: HouseholdConsumptionPoint[];
  timeRange: '1D' | '7D' | '1M' | '3M' | '1Y' | 'ALL';
  onTimeRangeChange: (range: '1D' | '7D' | '1M' | '3M' | 'ALL' | '1Y') => void;
  timeRangeOptions?: Array<'1D' | '7D' | '1M' | '3M' | '1Y' | 'ALL'>;
  demarcationTime?: string;
  actualCallout?: ChartCalloutPoint;
  predictedCallout?: ChartCalloutPoint;
  tariffRate?: number;
}

export const CommonEnergyChart: React.FC<CommonEnergyChartProps> = ({
  title = 'Energy Consumption',
  subtitle = 'Hourly observed telemetry (00:00–12:00) with autoregressive model forward forecast (12:00–24:00)',
  data,
  timeRange,
  onTimeRangeChange,
  timeRangeOptions = ['1D', '7D', '1M', '3M', '1Y', 'ALL'],
  demarcationTime = '12:00',
  actualCallout = {
    time: '09:00',
    value: 3.2,
    dateText: '19 Oct 2026, 09:00 AM',
    label: 'Consumption',
    color: '#00A396',
  },
  predictedCallout = {
    time: '20:30',
    value: 3.8,
    dateText: '19 Oct 2026, 08:00 PM',
    label: 'Predicted Consumption',
    color: '#8B5CF6',
  },
  tariffRate = 10.0,
}) => {
  // SVG Callout Renderer for Actual Peak (auto-flips when near top of viewport)
  const renderActualCallout = (props: { cx?: number; cy?: number }) => {
    const { cx, cy } = props;
    if (cx === undefined || cy === undefined) return null;
    const isTopClipped = cy < 95;
    const translateY = isTopClipped ? cy + 12 : cy - 88;
    return (
      <g transform={`translate(${cx - 75}, ${translateY})`}>
        <rect
          width="150"
          height="66"
          rx="10"
          fill="#FFFFFF"
          stroke="#E2E8F0"
          strokeWidth="1.2"
          style={{ filter: 'drop-shadow(0 6px 18px rgba(11, 31, 51, 0.12))' }}
        />
        {isTopClipped ? (
          <polygon
            points="67,0 83,0 75,-8"
            fill="#FFFFFF"
            stroke="#E2E8F0"
            strokeWidth="1.2"
          />
        ) : (
          <polygon
            points="67,66 83,66 75,74"
            fill="#FFFFFF"
            stroke="#E2E8F0"
            strokeWidth="1.2"
          />
        )}
        <text x="14" y="20" fontSize="10" fill="#64748B" fontWeight="600">
          {actualCallout.dateText}
        </text>
        <circle cx="18" cy="34" r="3" fill={actualCallout.color} />
        <text x="26" y="37" fontSize="11" fill="#64748B" fontWeight="500">
          {actualCallout.label}
        </text>
        <text x="14" y="55" fontSize="15" fill="#0B1F33" fontWeight="800">
          {actualCallout.value.toFixed(1)} <tspan fontSize="11" fontWeight="600" fill="#64748B">kWh</tspan>
        </text>
      </g>
    );
  };

  // SVG Callout Renderer for Predicted Peak (auto-flips when near top of viewport)
  const renderPredictedCallout = (props: { cx?: number; cy?: number }) => {
    const { cx, cy } = props;
    if (cx === undefined || cy === undefined) return null;
    const isTopClipped = cy < 95;
    const translateY = isTopClipped ? cy + 12 : cy - 88;
    return (
      <g transform={`translate(${cx - 80}, ${translateY})`}>
        <rect
          width="160"
          height="66"
          rx="10"
          fill="#FFFFFF"
          stroke="#E2E8F0"
          strokeWidth="1.2"
          style={{ filter: 'drop-shadow(0 6px 18px rgba(11, 31, 51, 0.12))' }}
        />
        {isTopClipped ? (
          <polygon
            points="72,0 88,0 80,-8"
            fill="#FFFFFF"
            stroke="#E2E8F0"
            strokeWidth="1.2"
          />
        ) : (
          <polygon
            points="72,66 88,66 80,74"
            fill="#FFFFFF"
            stroke="#E2E8F0"
            strokeWidth="1.2"
          />
        )}
        <text x="14" y="20" fontSize="10" fill="#64748B" fontWeight="600">
          {predictedCallout.dateText}
        </text>
        <circle cx="18" cy="34" r="3" fill={predictedCallout.color} />
        <text x="26" y="37" fontSize="11" fill="#64748B" fontWeight="500">
          {predictedCallout.label}
        </text>
        <text x="14" y="55" fontSize="15" fill="#0B1F33" fontWeight="800">
          {predictedCallout.value.toFixed(1)} <tspan fontSize="11" fontWeight="600" fill="#64748B">kWh</tspan>
        </text>
      </g>
    );
  };

  // Dynamic Y-domain based on data values
  const maxVal = React.useMemo(() => {
    let max = 0;
    if (data && data.length) {
      for (const d of data) {
        if (d.actualConsumption !== null && d.actualConsumption !== undefined) {
          max = Math.max(max, d.actualConsumption);
        }
        if (d.predictedConsumption !== null && d.predictedConsumption !== undefined) {
          max = Math.max(max, d.predictedConsumption);
        }
      }
    }
    return max;
  }, [data]);

  const yDomain: [number, number] = React.useMemo(() => {
    if (timeRange === '1D') {
      return [0, Math.max(3, Math.ceil(maxVal * 1.35))];
    }
    if (timeRange === '7D' || timeRange === '1M' || timeRange === '3M') {
      return [0, Math.max(12, Math.ceil(maxVal * 1.25))];
    }
    return [0, Math.max(100, Math.ceil(maxVal * 1.2))];
  }, [timeRange, maxVal]);

  const hasActualCallout = Boolean(actualCallout && data && data.some((d) => d.time === actualCallout.time));
  const hasPredictedCallout = Boolean(predictedCallout && data && data.some((d) => d.time === predictedCallout.time));

  return (
    <div
      style={{
        backgroundColor: '#FFFFFF',
        borderRadius: '18px',
        border: '1px solid #E2E8F0',
        padding: '1.75rem',
        boxShadow: '0 4px 20px -2px rgba(11, 31, 51, 0.03)',
      }}
    >
      {/* Chart Header with Time Range Controller */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1.75rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={18} color="#00A396" />
            <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0B1F33', margin: 0 }}>
              {title}
            </h2>
          </div>
          {subtitle && (
            <p style={{ fontSize: '0.78rem', color: '#64748B', margin: '0.2rem 0 0 0' }}>
              {subtitle}
            </p>
          )}
        </div>

        {/* Time Range Selector */}
        <div
          style={{
            display: 'flex',
            gap: '0.25rem',
            backgroundColor: '#F8FAFC',
            padding: '3px',
            borderRadius: '10px',
            border: '1px solid #E2E8F0',
          }}
        >
          {timeRangeOptions.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => onTimeRangeChange(r)}
              style={{
                padding: '0.35rem 0.85rem',
                fontSize: '0.78rem',
                fontWeight: 600,
                borderRadius: '8px',
                border: 'none',
                backgroundColor: timeRange === r ? '#00A396' : 'transparent',
                color: timeRange === r ? '#FFFFFF' : '#64748B',
                boxShadow: timeRange === r ? '0 2px 8px rgba(0, 163, 150, 0.25)' : 'none',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Time Series Area/Line Chart */}
      <div style={{ width: '100%', height: '375px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 48, right: 24, left: 10, bottom: 5 }}>
            <defs>
              <linearGradient id="actualGradientCommon" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00A396" stopOpacity={0.22} />
                <stop offset="95%" stopColor="#00A396" stopOpacity={0.0} />
              </linearGradient>
              <linearGradient id="predictedGradientCommon" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.18} />
                <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.0} />
              </linearGradient>
              <filter id="tealGlowCommon" x="-20%" y="-20%" width="140%" height="140%">
                <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#00A396" floodOpacity="0.25" />
              </filter>
            </defs>

            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />

            <XAxis
              dataKey="time"
              ticks={
                timeRange === '1D'
                  ? ['00:00', '02:00', '04:00', '06:00', '08:00', '10:00', '12:00', '14:00', '16:00', '18:00', '20:00', '22:00']
                  : undefined
              }
              minTickGap={16}
              tick={{ fontSize: 11, fill: '#64748B', fontWeight: 500 }}
              axisLine={{ stroke: '#E2E8F0' }}
              tickLine={false}
            />

            <YAxis
              domain={yDomain}
              width={54}
              tick={{ fontSize: 11, fill: '#64748B', fontWeight: 500 }}
              axisLine={false}
              tickLine={false}
              label={{
                value: 'Consumption (kWh)',
                angle: -90,
                position: 'insideLeft',
                fill: '#64748B',
                fontSize: 11,
                fontWeight: 600,
                dy: 55,
                dx: 12,
              }}
            />

            {/* Common Interactive Tooltip */}
            <Tooltip content={<CommonChartHoverCard tariffRate={tariffRate} />} />

            {/* Demarcation line */}
            {demarcationTime && (
              <ReferenceLine
                x={demarcationTime}
                stroke="#94A3B8"
                strokeDasharray="4 4"
                strokeWidth={1.5}
                label={{
                  value: `${demarcationTime} Demarcation`,
                  position: 'top',
                  fill: '#94A3B8',
                  fontSize: 10,
                  fontWeight: 600,
                }}
              />
            )}

            {/* Actual Peak Callout */}
            {hasActualCallout && actualCallout && (
              <ReferenceDot
                x={actualCallout.time}
                y={actualCallout.value}
                r={5}
                fill={actualCallout.color}
                stroke="#FFFFFF"
                strokeWidth={2.5}
                label={renderActualCallout}
              />
            )}

            {/* Predicted Peak Callout */}
            {hasPredictedCallout && predictedCallout && (
              <ReferenceDot
                x={predictedCallout.time}
                y={predictedCallout.value}
                r={5}
                fill={predictedCallout.color}
                stroke="#FFFFFF"
                strokeWidth={2.5}
                label={renderPredictedCallout}
              />
            )}

            {/* Actual Consumption Area & Line */}
            <Area
              type="monotone"
              dataKey="actualConsumption"
              name="Actual Consumption"
              stroke="#00A396"
              strokeWidth={2.8}
              fill="url(#actualGradientCommon)"
              dot={false}
              connectNulls={false}
              filter="url(#tealGlowCommon)"
            />

            {/* Predicted Consumption Area & Line */}
            <Area
              type="monotone"
              dataKey="predictedConsumption"
              name="Predicted Consumption"
              stroke="#8B5CF6"
              strokeWidth={2.8}
              strokeDasharray="5 5"
              fill="url(#predictedGradientCommon)"
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Bottom Legend */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '2.5rem',
          marginTop: '1.25rem',
          borderTop: '1px solid #F1F5F9',
          paddingTop: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.82rem', color: '#64748B', fontWeight: 500 }}>
          <div style={{ width: '26px', height: '3px', backgroundColor: '#00A396', borderRadius: '2px' }} />
          <span>Actual Consumption</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.82rem', color: '#64748B', fontWeight: 500 }}>
          <div style={{ width: '26px', height: '0px', borderTop: '2.5px dashed #8B5CF6' }} />
          <span>Predicted Consumption</span>
        </div>
      </div>
    </div>
  );
};
