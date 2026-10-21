import React, { useState, useEffect, useMemo } from 'react';
import { usePersona } from '../context';
import { analyticsService } from '../services/analyticsService';
import { HistoricalInsightsData } from '../types/analytics';
import { CommonMetricCard, CommonChartHoverCard } from '../components/common';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceDot,
} from 'recharts';
import {
  Calendar,
  BarChart2,
  BarChart3,
  Zap,
} from 'lucide-react';

export const HistoricalAnalysisPage: React.FC = () => {
  const { currentPersona, activeEntity, energyUnit } = usePersona();
  const persona = currentPersona || 'household';

  const isMWh = energyUnit === 'MWh';

  // Active time filter: 30D (default), 90D, 1Y, ALL
  const [timeRange, setTimeRange] = useState<'30D' | '90D' | '1Y' | 'ALL'>('30D');
  const [historicalData, setHistoricalData] = useState<HistoricalInsightsData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // Load historical analytics dynamically based on persona, active entity, and time range
  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    analyticsService
      .getHistoricalInsights(persona, timeRange, activeEntity)
      .then((res) => {
        if (isMounted) {
          setHistoricalData(res);
          setLoading(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [persona, activeEntity, timeRange]);

  // Subtitle personalized by sector persona
  const subtitle = useMemo(() => {
    if (persona === 'commercial') {
      return `Analyze facility demand & peak load trends over time for ${activeEntity || 'Panther_office_1'}`;
    }
    if (persona === 'government') {
      return 'Analyze system-wide grid demand & substation capacity history across 17 regional zones';
    }
    return 'Analyze your household energy consumption over time';
  }, [persona, activeEntity]);

  // Find peak day data point to anchor the visual demarcation pin
  const peakPoint = useMemo(() => {
    if (!historicalData || !historicalData.historyCurve.length) return null;
    let max = historicalData.historyCurve[0];
    for (const p of historicalData.historyCurve) {
      if (p.peakDemand > max.peakDemand) {
        max = p;
      }
    }
    return max;
  }, [historicalData]);

  // Dynamic Y-axis scale based on persona
  const { yDomain, yTicks } = useMemo(() => {
    if (persona === 'commercial') {
      return { yDomain: [0, 360] as [number, number], yTicks: [0, 60, 120, 180, 240, 300, 360] };
    }
    if (persona === 'government') {
      return { yDomain: [250, 500] as [number, number], yTicks: [250, 300, 350, 400, 450, 500] };
    }
    // Residential: Dynamic scale based on peak consumption point
    const peak = peakPoint?.peakDemand || 8;
    const maxVal = Math.max(8, Math.ceil(peak * 1.25));
    const step = Math.max(2, Math.ceil(maxVal / 5));
    const ticks = [0, step, step * 2, step * 3, step * 4, step * 5];
    return { yDomain: [0, step * 5] as [number, number], yTicks: ticks };
  }, [persona, peakPoint]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1.75rem',
        maxWidth: '1300px',
        margin: '0 auto',
        width: '100%',
      }}
    >
      {/* ========================================================= */}
      {/* 1. Header with Page Title & 30D / 90D / 1Y / ALL Filters */}
      {/* ========================================================= */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '2.1rem',
              fontWeight: 800,
              color: '#0B1F33',
              margin: '0 0 0.35rem 0',
              letterSpacing: '-0.025em',
            }}
          >
            Historical Insights
          </h1>
          <p style={{ fontSize: '0.95rem', color: '#64748B', margin: 0, fontWeight: 500 }}>
            {subtitle}
          </p>
        </div>

        {/* Working 30D, 90D, 1Y, and ALL filters */}
        <div
          style={{
            display: 'flex',
            gap: '0.25rem',
            backgroundColor: '#F8FAFC',
            padding: '4px',
            borderRadius: '10px',
            border: '1px solid #E2E8F0',
          }}
        >
          {(['30D', '90D', '1Y', 'ALL'] as const).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setTimeRange(r)}
              style={{
                padding: '0.4rem 1.05rem',
                fontSize: '0.8rem',
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

      {/* ========================================================= */}
      {/* 2. Four KPI Cards using CommonMetricCard                  */}
      {/* ========================================================= */}
      {historicalData && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '1.25rem',
          }}
        >
          {/* Card 1: History Returned */}
          <CommonMetricCard
            title="History Returned"
            value={historicalData.daysReturned}
            unit="Days"
            icon={<Calendar size={22} color="#2563EB" />}
            iconBg="#EFF6FF"
            subtext={`${historicalData.startDate} – ${historicalData.endDate}`}
            hoverBorderColor="rgba(37, 99, 235, 0.4)"
          />

          {/* Card 2: Average Daily Consumption / Usage */}
          <CommonMetricCard
            title="Average Daily Usage"
            value={
              historicalData.unit === 'kWh' && isMWh
                ? (historicalData.avgDailyConsumption / 1000).toFixed(3)
                : historicalData.avgDailyConsumption.toFixed(1)
            }
            unit={historicalData.unit === 'kWh' && isMWh ? 'MWh' : historicalData.unit}
            icon={<BarChart2 size={22} color="#00A396" />}
            iconBg="#E6F7F5"
            hoverBorderColor="rgba(0, 163, 150, 0.4)"
          />

          {/* Card 3: Average Monthly Consumption / Usage */}
          <CommonMetricCard
            title="Average Monthly Usage"
            value={
              historicalData.unit === 'kWh' && isMWh
                ? (historicalData.avgMonthlyConsumption / 1000).toFixed(2)
                : Math.round(historicalData.avgMonthlyConsumption)
            }
            unit={historicalData.unit === 'kWh' && isMWh ? 'MWh' : historicalData.unit}
            icon={<BarChart3 size={22} color="#7C3AED" />}
            iconBg="#F5F3FF"
            hoverBorderColor="rgba(124, 58, 237, 0.4)"
          />

          {/* Card 4: Peak Consumption */}
          <CommonMetricCard
            title="Peak Consumption"
            value={
              historicalData.unit === 'kWh' && isMWh
                ? (historicalData.peakConsumption / 1000).toFixed(3)
                : historicalData.peakConsumption.toFixed(1)
            }
            unit={historicalData.unit === 'kWh' && isMWh ? 'MWh' : historicalData.unit}
            icon={<Zap size={22} color="#D97706" fill="#D97706" />}
            iconBg="#FFF7ED"
            subtext={historicalData.peakTimestamp}
            hoverBorderColor="rgba(217, 119, 6, 0.4)"
          />
        </div>
      )}

      {/* ========================================================= */}
      {/* 3. Daily Energy Consumption Line & Area Chart             */}
      {/* ========================================================= */}
      <div
        style={{
          backgroundColor: '#FFFFFF',
          borderRadius: '18px',
          border: '1px solid #E2E8F0',
          padding: '1.75rem',
          boxShadow: '0 4px 20px -2px rgba(11, 31, 51, 0.03)',
        }}
      >
        {/* Chart Header: Title on Left, Legend on Right */}
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
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0B1F33', margin: 0 }}>
            Daily Energy Consumption
          </h2>

          {/* Top-right Legend matching screenshot */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.82rem', color: '#64748B', fontWeight: 600 }}>
              <span
                style={{
                  width: '9px',
                  height: '9px',
                  borderRadius: '50%',
                  backgroundColor: '#2563EB',
                  display: 'inline-block',
                }}
              />
              <span>Peak Daily Demand</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.82rem', color: '#64748B', fontWeight: 600 }}>
              <span
                style={{
                  width: '9px',
                  height: '9px',
                  borderRadius: '50%',
                  backgroundColor: '#00A396',
                  display: 'inline-block',
                }}
              />
              <span>Average Daily Demand</span>
            </div>
          </div>
        </div>

        {/* Time-Series Line / Area Chart */}
        <div style={{ width: '100%', height: '375px' }}>
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94A3B8' }}>
              Loading historical telemetry...
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={historicalData?.historyCurve || []}
                margin={{ top: 25, right: 20, left: 10, bottom: 5 }}
              >
                <defs>
                  {/* Subtle Peak Demand Gradient */}
                  <linearGradient id="peakDailyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2563EB" stopOpacity={0.16} />
                    <stop offset="95%" stopColor="#2563EB" stopOpacity={0.0} />
                  </linearGradient>

                  {/* Subtle Average Demand Gradient */}
                  <linearGradient id="avgDailyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00A396" stopOpacity={0.16} />
                    <stop offset="95%" stopColor="#00A396" stopOpacity={0.0} />
                  </linearGradient>
                </defs>

                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />

                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: '#64748B', fontWeight: 500 }}
                  axisLine={{ stroke: '#E2E8F0' }}
                  tickLine={false}
                  interval={timeRange === '30D' ? 2 : timeRange === '90D' ? 7 : 'preserveEnd'}
                />

                <YAxis
                  domain={yDomain}
                  ticks={yTicks}
                  width={56}
                  tick={{ fontSize: 11, fill: '#64748B', fontWeight: 500 }}
                  axisLine={false}
                  tickLine={false}
                  label={{
                    value: `Consumption (${historicalData?.unit || 'kWh'})`,
                    angle: -90,
                    position: 'insideLeft',
                    fill: '#64748B',
                    fontSize: 11,
                    fontWeight: 600,
                    dy: 60,
                    dx: 12,
                  }}
                />

                {/* Common Interactive Tooltip */}
                <Tooltip
                  content={
                    <CommonChartHoverCard
                      unit={historicalData?.unit || 'kWh'}
                      datePrefix=""
                    />
                  }
                />

                {/* Vertical demarcation on the peak day */}
                {peakPoint && (
                  <ReferenceLine
                    x={peakPoint.date}
                    stroke="#94A3B8"
                    strokeDasharray="4 4"
                    strokeWidth={1.5}
                  />
                )}

                {/* Anchor dots on peak day */}
                {peakPoint && (
                  <>
                    <ReferenceDot
                      x={peakPoint.date}
                      y={peakPoint.peakDemand}
                      r={4.5}
                      fill="#2563EB"
                      stroke="#FFFFFF"
                      strokeWidth={2}
                    />
                    <ReferenceDot
                      x={peakPoint.date}
                      y={peakPoint.avgDemand}
                      r={4.5}
                      fill="#00A396"
                      stroke="#FFFFFF"
                      strokeWidth={2}
                    />
                  </>
                )}

                {/* Peak Daily Demand Line & Area */}
                <Area
                  type="monotone"
                  dataKey="peakDemand"
                  name="Peak Daily Demand"
                  stroke="#2563EB"
                  strokeWidth={2.4}
                  fill="url(#peakDailyGrad)"
                  dot={{ r: 2.5, fill: '#FFFFFF', stroke: '#2563EB', strokeWidth: 1.8 }}
                  activeDot={{ r: 5, fill: '#2563EB', stroke: '#FFFFFF', strokeWidth: 2 }}
                />

                {/* Average Daily Demand Line & Area */}
                <Area
                  type="monotone"
                  dataKey="avgDemand"
                  name="Average Daily Demand"
                  stroke="#00A396"
                  strokeWidth={2.4}
                  fill="url(#avgDailyGrad)"
                  dot={{ r: 2.5, fill: '#FFFFFF', stroke: '#00A396', strokeWidth: 1.8 }}
                  activeDot={{ r: 5, fill: '#00A396', stroke: '#FFFFFF', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
};
