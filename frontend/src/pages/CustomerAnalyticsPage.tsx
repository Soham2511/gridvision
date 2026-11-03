import React, { useEffect, useState } from 'react';
import { analyticsService } from '../services/analyticsService';
import {
  CustomerSegmentationData,
  IndustrySegmentItem,
  TimeOfDayConsumptionItem,
  RegionalDemandItem,
} from '../types/analytics';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorState } from '../components/common/ErrorState';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  LabelList,
} from 'recharts';
import { Info } from 'lucide-react';

interface DemoBadgeProps {
  tooltipText: string;
}

const DemoDataBadge: React.FC<DemoBadgeProps> = ({ tooltipText }) => {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', position: 'relative' }}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '3px 10px',
          borderRadius: '9999px',
          backgroundColor: '#E0F2FE',
          color: '#0284C7',
          fontSize: '0.68rem',
          fontWeight: 700,
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
        }}
      >
        DEMO DATA
      </span>
      <div
        style={{ position: 'relative', display: 'flex', alignItems: 'center' }}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <Info
          size={16}
          color="#94A3B8"
          style={{ cursor: 'pointer', transition: 'color 0.15s ease' }}
          onMouseEnter={(e) => {
            (e.currentTarget as unknown as SVGElement).style.color = '#0284C7';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as unknown as SVGElement).style.color = '#94A3B8';
          }}
        />
        {showTooltip && (
          <div
            style={{
              position: 'absolute',
              top: '125%',
              right: 0,
              width: '270px',
              backgroundColor: '#0F172A',
              color: '#F8FAFC',
              fontSize: '0.74rem',
              padding: '0.65rem 0.85rem',
              borderRadius: '8px',
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.35)',
              zIndex: 60,
              lineHeight: 1.45,
              pointerEvents: 'none',
            }}
          >
            {tooltipText}
          </div>
        )}
      </div>
    </div>
  );
};

export const CustomerAnalyticsPage: React.FC = () => {
  const [data, setData] = useState<CustomerSegmentationData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    analyticsService
      .getCustomerSegmentationData()
      .then((res) => {
        if (mounted) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load customer segmentation data.');
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', padding: '0.5rem 0' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: 800, color: '#0F172A', letterSpacing: '-0.025em', margin: 0 }}>
            Customer Segmentation
          </h1>
          <p style={{ fontSize: '0.95rem', color: '#64748B', marginTop: '6px' }}>
            Explore customer composition and energy-use patterns across regions.
          </p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))', gap: '1.5rem' }}>
          <LoadingSkeleton height="340px" />
          <LoadingSkeleton height="340px" />
        </div>
        <LoadingSkeleton height="380px" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ padding: '1rem 0' }}>
        <ErrorState
          title="Customer Segmentation Unavailable"
          message={error || 'Failed to retrieve telemetry segmentation records.'}
        />
      </div>
    );
  }

  const { totalCustomers, industrySegments, timeOfDayConsumption, regionalMonthlyDemand } = data;

interface DonutHoverCardProps {
  active?: boolean;
  payload?: ReadonlyArray<{
    payload?: IndustrySegmentItem;
    [key: string]: unknown;
  }>;
}

const DonutHoverCard: React.FC<DonutHoverCardProps> = ({ active, payload }) => {
  if (!active || !payload || !payload.length || !payload[0].payload) return null;
  const seg = payload[0].payload;
  return (
    <div
      style={{
        backgroundColor: '#FFFFFF',
        border: '1px solid #E2E8F0',
        borderRadius: '10px',
        padding: '0.75rem 0.95rem',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.08)',
        minWidth: '170px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
        <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: seg.color }} />
        <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0F172A' }}>{seg.name}</span>
      </div>
      <div style={{ fontSize: '0.78rem', color: '#64748B', margin: '2px 0' }}>
        Customers: <strong style={{ color: '#0F172A' }}>{seg.count.toLocaleString()}</strong>
      </div>
      <div style={{ fontSize: '0.78rem', color: '#64748B' }}>
        Segment Share: <strong style={{ color: seg.color }}>{seg.sharePct}%</strong>
      </div>
    </div>
  );
};

interface TimeOfDayHoverCardProps {
  active?: boolean;
  payload?: ReadonlyArray<{
    payload?: TimeOfDayConsumptionItem;
    [key: string]: unknown;
  }>;
}

const TimeOfDayHoverCard: React.FC<TimeOfDayHoverCardProps> = ({ active, payload }) => {
  if (!active || !payload || !payload.length || !payload[0].payload) return null;
  const item = payload[0].payload;
  return (
    <div
      style={{
        backgroundColor: '#FFFFFF',
        border: '1px solid #E2E8F0',
        borderRadius: '10px',
        padding: '0.75rem 0.95rem',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.08)',
        minWidth: '190px',
      }}
    >
      <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0F172A', marginBottom: '4px' }}>
        {item.periodLabel}
      </div>
      <div style={{ fontSize: '0.8rem', color: '#64748B' }}>
        Consumption: <strong style={{ color: item.color }}>{item.consumptionMwh.toLocaleString()} MWh</strong>
      </div>
      <div style={{ fontSize: '0.74rem', color: '#94A3B8', marginTop: '4px' }}>
        {((item.consumptionMwh / 8470) * 100).toFixed(1)}% of diurnal load
      </div>
    </div>
  );
};

interface RegionalHoverCardProps {
  active?: boolean;
  payload?: ReadonlyArray<{
    payload?: RegionalDemandItem;
    [key: string]: unknown;
  }>;
}

const RegionalHoverCard: React.FC<RegionalHoverCardProps> = ({ active, payload }) => {
  if (!active || !payload || !payload.length || !payload[0].payload) return null;
  const reg = payload[0].payload;
  return (
    <div
      style={{
        backgroundColor: '#FFFFFF',
        border: '1px solid #E2E8F0',
        borderRadius: '10px',
        padding: '0.75rem 0.95rem',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.08)',
        minWidth: '180px',
      }}
    >
      <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0F172A', marginBottom: '4px' }}>
        {reg.regionName} Region
      </div>
      <div style={{ fontSize: '0.8rem', color: '#64748B' }}>
        Average Demand: <strong style={{ color: '#00A389' }}>{reg.demandLabel}</strong>
      </div>
      <div style={{ fontSize: '0.74rem', color: '#94A3B8', marginTop: '4px' }}>
        System Share: {((reg.avgDemandMw / 18380) * 100).toFixed(1)}%
      </div>
    </div>
  );
};

interface CustomYAxisTickProps {
  x?: number | string;
  y?: number | string;
  payload?: {
    value?: string;
  };
  timeOfDayData?: TimeOfDayConsumptionItem[];
}

const CustomYAxisTick: React.FC<CustomYAxisTickProps> = ({ x = 0, y = 0, payload, timeOfDayData = [] }) => {
  if (!payload || !payload.value) return null;
  const item = timeOfDayData.find((d) => d.periodName === payload.value);
  return (
    <g transform={`translate(${x},${y})`}>
      <text x={-12} y={-4} dy={0} textAnchor="end" fill="#0F172A" fontSize={12} fontWeight={600}>
        {item?.periodName || payload.value}
      </text>
      <text x={-12} y={12} dy={0} textAnchor="end" fill="#64748B" fontSize={10} fontWeight={400}>
        {item?.timeRange}
      </text>
    </g>
  );
};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', padding: '0.5rem 0 2rem 0' }}>
      {/* 1. Page Title & Subtitle */}
      <div>
        <h1
          style={{
            fontSize: '2rem',
            fontWeight: 800,
            color: '#0F172A',
            letterSpacing: '-0.025em',
            margin: 0,
            lineHeight: 1.15,
          }}
        >
          Customer Segmentation
        </h1>
        <p style={{ fontSize: '0.95rem', color: '#64748B', marginTop: '6px', marginBottom: 0 }}>
          Explore customer composition and energy-use patterns across regions.
        </p>
      </div>

      {/* 2. Top Row: 2 Equal Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(460px, 1fr))',
          gap: '1.5rem',
          alignItems: 'stretch',
        }}
      >
        {/* Card 1: Customer Segmentation by Industry */}
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Card Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '1.25rem',
            }}
          >
            <h2 style={{ fontSize: '1.08rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
              Customer Segmentation by Industry
            </h2>
            <DemoDataBadge tooltipText="Industry breakdown mapped from regional consumer census and facility archetypes." />
          </div>

          {/* Donut Chart + Aligned Data Table */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1.5rem',
              flex: 1,
              flexWrap: 'wrap',
            }}
          >
            {/* Donut Chart with Centered Total */}
            <div
              style={{
                position: 'relative',
                width: '230px',
                height: '230px',
                flexShrink: 0,
                margin: '0 auto',
              }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={industrySegments}
                    dataKey="count"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={70}
                    outerRadius={105}
                    paddingAngle={2}
                    stroke="none"
                  >
                    {industrySegments.map((entry) => (
                      <Cell key={entry.id} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<DonutHoverCard />} />
                </PieChart>
              </ResponsiveContainer>

              {/* Centered Donut Label */}
              <div
                style={{
                  position: 'absolute',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  textAlign: 'center',
                  pointerEvents: 'none',
                }}
              >
                <div
                  style={{
                    fontSize: '0.78rem',
                    color: '#64748B',
                    fontWeight: 500,
                    marginBottom: '2px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  Total Customers
                </div>
                <div
                  style={{
                    fontSize: '1.55rem',
                    fontWeight: 800,
                    color: '#0F172A',
                    lineHeight: 1,
                    letterSpacing: '-0.02em',
                  }}
                >
                  {totalCustomers.toLocaleString()}
                </div>
              </div>
            </div>

            {/* Legend / Table */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '0.65rem',
                flex: 1,
                minWidth: '220px',
              }}
            >
              {industrySegments.map((s) => (
                <div
                  key={s.id}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '12px 1fr 40px 50px',
                    alignItems: 'center',
                    gap: '0.65rem',
                    fontSize: '0.85rem',
                  }}
                >
                  <span
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: s.color,
                      display: 'inline-block',
                    }}
                  />
                  <span style={{ color: '#334155', fontWeight: 500 }}>{s.name}</span>
                  <span style={{ color: '#0F172A', fontWeight: 600, textAlign: 'right' }}>
                    {s.sharePct}%
                  </span>
                  <span style={{ color: '#64748B', fontWeight: 500, textAlign: 'right' }}>
                    {s.count.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Card 2: Consumption by Time of Day */}
        <div
          style={{
            backgroundColor: '#FFFFFF',
            borderRadius: '12px',
            border: '1px solid #E2E8F0',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
            padding: '1.5rem',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Card Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '1.25rem',
            }}
          >
            <h2 style={{ fontSize: '1.08rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
              Consumption by Time of Day
            </h2>
            <DemoDataBadge tooltipText="Diurnal aggregate electricity consumption partitioned into 6-hour operational intervals." />
          </div>

          {/* Horizontal Bar Chart */}
          <div style={{ flex: 1, minHeight: '230px', width: '100%' }}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart
                layout="vertical"
                data={timeOfDayConsumption}
                margin={{ top: 10, right: 95, left: 15, bottom: 20 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#F1F5F9" />
                <XAxis
                  type="number"
                  domain={[0, 3500]}
                  ticks={[0, 500, 1000, 1500, 2000, 2500, 3000, 3500]}
                  tick={{ fill: '#64748B', fontSize: 11 }}
                  axisLine={{ stroke: '#E2E8F0' }}
                  tickLine={{ stroke: '#E2E8F0' }}
                  label={{
                    value: 'Consumption (MWh)',
                    position: 'insideBottom',
                    offset: -12,
                    style: { fill: '#64748B', fontSize: 11, fontWeight: 500 },
                  }}
                />
                <YAxis
                  type="category"
                  dataKey="periodName"
                  tick={<CustomYAxisTick timeOfDayData={timeOfDayConsumption} />}
                  width={95}
                  axisLine={{ stroke: '#E2E8F0' }}
                  tickLine={false}
                />
                <Tooltip content={<TimeOfDayHoverCard />} />
                <Bar dataKey="consumptionMwh" radius={[0, 6, 6, 0]} barSize={24}>
                  {timeOfDayConsumption.map((entry) => (
                    <Cell key={entry.periodKey} fill={entry.color} />
                  ))}
                  <LabelList
                    dataKey="consumptionMwh"
                    position="right"
                    formatter={(val: unknown) => `${Number(val).toLocaleString()} MWh`}
                    style={{ fill: '#0F172A', fontSize: 12, fontWeight: 700 }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* 3. Bottom Row: Average Monthly Demand by Region */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '12px',
          border: '1px solid #E2E8F0',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.04)',
          padding: '1.5rem',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Card Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '1.25rem',
          }}
        >
          <h2 style={{ fontSize: '1.08rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
            Average Monthly Demand by Region
          </h2>
          <DemoDataBadge tooltipText="Monthly average continuous power draw aggregated across regional utility dispatch nodes." />
        </div>

        {/* Vertical Bar Chart */}
        <div style={{ width: '100%', height: '320px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={regionalMonthlyDemand}
              margin={{ top: 25, right: 30, left: 10, bottom: 10 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />
              <XAxis
                dataKey="regionName"
                tick={{ fill: '#0F172A', fontSize: 12, fontWeight: 600 }}
                axisLine={{ stroke: '#E2E8F0' }}
                tickLine={false}
              />
              <YAxis
                domain={[0, 5000]}
                ticks={[0, 1000, 2000, 3000, 4000, 5000]}
                tick={{ fill: '#64748B', fontSize: 11 }}
                axisLine={{ stroke: '#E2E8F0' }}
                tickLine={{ stroke: '#E2E8F0' }}
                label={{
                  value: 'Average Demand (MW)',
                  angle: -90,
                  position: 'insideLeft',
                  offset: 0,
                  style: { fill: '#64748B', fontSize: 11, fontWeight: 500, textAnchor: 'middle' },
                }}
              />
              <Tooltip content={<RegionalHoverCard />} />
              <Bar dataKey="avgDemandMw" fill="#00A389" radius={[6, 6, 0, 0]} maxBarSize={64}>
                <LabelList
                  dataKey="demandLabel"
                  position="top"
                  offset={8}
                  style={{ fill: '#0F172A', fontSize: 12, fontWeight: 700 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};
