import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { TimeSeriesPoint } from '../../types/analytics';

interface DemandTrendsChartProps {
  data: TimeSeriesPoint[];
}

export const DemandTrendsChart: React.FC<DemandTrendsChartProps> = ({ data }) => {
  const peakLimit: number = (data.length > 0 && (data[0].peakThresholdMw || data[0].peakThreshold)) ? Number(data[0].peakThresholdMw || data[0].peakThreshold) : 460;
  const chartData = data.map((d) => ({
    ...d,
    actualDemandMw: d.actualDemandMw !== undefined ? d.actualDemandMw : d.actualDemand,
    forecastDemandMw: d.forecastDemandMw !== undefined ? d.forecastDemandMw : d.forecastDemand,
  }));

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={chartData}
          margin={{ top: 10, right: 20, left: -10, bottom: 0 }}
        >
          <defs>
            <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--gv-color-smart-teal)" stopOpacity={0.25} />
              <stop offset="95%" stopColor="var(--gv-color-smart-teal)" stopOpacity={0.0} />
            </linearGradient>
            <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--gv-color-grid-blue)" stopOpacity={0.25} />
              <stop offset="95%" stopColor="var(--gv-color-grid-blue)" stopOpacity={0.0} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />

          <XAxis
            dataKey="formattedTime"
            stroke="#94A3B8"
            tick={{ fontSize: 11, fill: '#64748B' }}
            tickLine={false}
            axisLine={{ stroke: '#CBD5E1' }}
          />

          <YAxis
            stroke="#94A3B8"
            tick={{ fontSize: 11, fill: '#64748B' }}
            tickLine={false}
            axisLine={false}
            unit=" MW"
            domain={['auto', 'auto']}
          />

          <Tooltip
            content={({ active, payload, label }) => {
              if (active && payload && payload.length) {
                return (
                  <div
                    style={{
                      background: 'var(--gv-color-midnight-navy)',
                      color: '#FFFFFF',
                      padding: '0.65rem 0.85rem',
                      borderRadius: 'var(--gv-radius-md)',
                      boxShadow: 'var(--gv-shadow-lg)',
                      fontSize: '0.75rem',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      minWidth: '180px',
                    }}
                  >
                    <p style={{ fontWeight: 700, marginBottom: '0.35rem', color: '#E2E8F0' }}>
                      Time: {label}
                    </p>
                    {payload.map((entry, index) => {
                      if (entry.value === null || entry.value === undefined) return null;
                      return (
                        <div
                          key={`item-${index}`}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: '0.75rem',
                            marginTop: '0.2rem',
                          }}
                        >
                          <span style={{ color: entry.color, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: entry.color }} />
                            {entry.name}:
                          </span>
                          <span style={{ fontWeight: 700, fontFamily: 'var(--gv-font-mono)' }}>
                            {entry.value} MW
                          </span>
                        </div>
                      );
                    })}
                    <div style={{ marginTop: '0.45rem', paddingTop: '0.35rem', borderTop: '1px solid rgba(255, 255, 255, 0.15)', fontSize: '0.68rem', color: '#94A3B8' }}>
                      Mock demonstration series
                    </div>
                  </div>
                );
              }
              return null;
            }}
          />

          <Legend
            verticalAlign="top"
            align="right"
            iconType="circle"
            wrapperStyle={{ paddingBottom: '10px', fontSize: '11px', color: '#475569' }}
          />

          <ReferenceLine
            y={peakLimit}
            stroke="#EF4444"
            strokeDasharray="4 4"
            label={{
              value: `Peak Alert Threshold (${peakLimit} MW)`,
              fill: '#EF4444',
              fontSize: 10,
              position: 'insideTopLeft',
            }}
          />

          <Area
            type="monotone"
            dataKey="actualDemandMw"
            name="Historical Actual Demand"
            stroke="var(--gv-color-smart-teal)"
            strokeWidth={2.5}
            fillOpacity={1}
            fill="url(#actualGradient)"
            dot={{ r: 3, fill: 'var(--gv-color-smart-teal)' }}
            activeDot={{ r: 5 }}
            connectNulls={false}
          />

          <Line
            type="monotone"
            dataKey="forecastDemandMw"
            name="Forecasted Demand (Mock)"
            stroke="var(--gv-color-grid-blue)"
            strokeWidth={2.5}
            strokeDasharray="5 5"
            dot={{ r: 3, fill: 'var(--gv-color-grid-blue)' }}
            activeDot={{ r: 5 }}
            connectNulls={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
