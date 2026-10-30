import React, { useState, useEffect, useMemo } from 'react';
import { usePersona } from '../context';
import { analyticsService } from '../services/analyticsService';
import {
  CommercialDashboardData,
  GovernmentRegionItem,
  GovernmentDashboardData,
} from '../types/analytics';
import { CommonMetricCard } from '../components/common';
import { CommonChartHoverCard } from '../components/common/CommonChartHoverCard';
import { ResidentialGoldInsightsPage } from './ResidentialGoldInsightsPage';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  ReferenceDot,
  Tooltip,
} from 'recharts';
import {
  Zap,
  BarChart2,
  TrendingUp,
  FileText,
  MapPin,
  ChevronRight,
  Search,
  X,
  Plus,
} from 'lucide-react';

export const PersonaDashboardPage: React.FC = () => {
  const { currentPersona, activeEntity, energyUnit } = usePersona();

  // Active persona (defaults to household / Residential)
  const persona = currentPersona || 'household';
  const isMWh = energyUnit === 'MWh';

  // -------------------------------------------------------------
  // 2. Commercial View State
  // -------------------------------------------------------------
  const [commercialTab, setCommercialTab] = useState<'building' | 'regional'>('building');
  const [commercialRange, setCommercialRange] = useState<'1D' | '7D' | '1M' | '3M' | '1Y'>('1D');
  const [commercialData, setCommercialData] = useState<CommercialDashboardData | null>(null);
  const [commercialLoading, setCommercialLoading] = useState<boolean>(true);

  useEffect(() => {
    if (persona === 'commercial') {
      setCommercialLoading(true);
      analyticsService
        .getCommercialDashboard(commercialTab, commercialRange, activeEntity)
        .then((res) => {
          setCommercialData(res);
          setCommercialLoading(false);
        })
        .catch(() => {
          setCommercialLoading(false);
        });
    }
  }, [persona, commercialTab, commercialRange, activeEntity]);

  // -------------------------------------------------------------
  // 3. Government & Utilities View State (Matches User Screenshot)
  // -------------------------------------------------------------
  // Active tab: 'overall' | 'regional_list' | `region_${regionId}`
  const [govActiveTab, setGovActiveTab] = useState<string>('overall');
  const [openRegionTabs, setOpenRegionTabs] = useState<string[]>([]);
  const [previousGovTab, setPreviousGovTab] = useState<string>('regional_list');
  const [govTimeRange, setGovTimeRange] = useState<'1D' | '7D' | '1M' | '3M' | '1Y'>('1D');
  const [regionSearchQuery, setRegionSearchQuery] = useState<string>('');

  const [governmentRegions, setGovernmentRegions] = useState<GovernmentRegionItem[]>([]);
  const [govDashboardData, setGovDashboardData] = useState<GovernmentDashboardData | null>(null);
  const [govLoading, setGovLoading] = useState<boolean>(true);

  // Load government regions list
  useEffect(() => {
    if (persona === 'government') {
      analyticsService.getGovernmentRegions().then((res) => {
        setGovernmentRegions(res);
      });
    }
  }, [persona]);

  // Load active government dashboard data (overall or selected region)
  useEffect(() => {
    if (persona === 'government') {
      setGovLoading(true);
      if (govActiveTab === 'overall') {
        analyticsService
          .getGovernmentDashboard('overall', undefined, govTimeRange)
          .then((res) => {
            setGovDashboardData(res);
            setGovLoading(false);
          })
          .catch(() => setGovLoading(false));
      } else if (govActiveTab.startsWith('region_')) {
        const regionId = govActiveTab.replace('region_', '');
        analyticsService
          .getGovernmentDashboard('region', regionId, govTimeRange)
          .then((res) => {
            setGovDashboardData(res);
            setGovLoading(false);
          })
          .catch(() => setGovLoading(false));
      } else {
        setGovLoading(false);
      }
    }
  }, [persona, govActiveTab, govTimeRange]);

  // Handler to open a region card in a new closable tab
  const handleOpenRegion = (regionId: string) => {
    if (!openRegionTabs.includes(regionId)) {
      setOpenRegionTabs((prev) => [...prev, regionId]);
    }
    setPreviousGovTab(govActiveTab);
    setGovActiveTab(`region_${regionId}`);
  };

  // Handler to close a region tab
  const handleCloseRegionTab = (e: React.MouseEvent, regionId: string) => {
    e.stopPropagation();
    const remaining = openRegionTabs.filter((id) => id !== regionId);
    setOpenRegionTabs(remaining);
    if (govActiveTab === `region_${regionId}`) {
      // return to previous active tab if still valid, or default to regional_list
      setGovActiveTab(previousGovTab === `region_${regionId}` ? 'regional_list' : previousGovTab);
    }
  };

  // Filtered regions based on search query
  const filteredRegions = useMemo(() => {
    if (!regionSearchQuery.trim()) return governmentRegions;
    return governmentRegions.filter((r) =>
      r.name.toLowerCase().includes(regionSearchQuery.toLowerCase())
    );
  }, [governmentRegions, regionSearchQuery]);

  // -------------------------------------------------------------
  // Callout Renderers
  // -------------------------------------------------------------
  const renderCommercialActualCallout = (props: { cx?: number; cy?: number }) => {
    const { cx, cy } = props;
    if (cx === undefined || cy === undefined || !commercialData?.actualCallout) return null;
    const callout = commercialData.actualCallout;
    return (
      <g transform={`translate(${cx - 75}, ${cy - 88})`}>
        <rect width="150" height="66" rx="10" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="1.2" style={{ filter: 'drop-shadow(0 6px 18px rgba(11, 31, 51, 0.10))' }} />
        <polygon points="67,66 83,66 75,74" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="1.2" />
        <line x1="68" y1="65" x2="82" y2="65" stroke="#FFFFFF" strokeWidth="2" />
        <text x="14" y="20" fontSize="10" fill="#64748B" fontWeight="600">{callout.timestamp}</text>
        <circle cx="18" cy="34" r="3" fill="#00A396" />
        <text x="26" y="37" fontSize="11" fill="#64748B" fontWeight="500">{callout.label}</text>
        <text x="14" y="55" fontSize="15" fill="#0B1F33" fontWeight="800">
          {callout.value.toLocaleString()} <tspan fontSize="11" fontWeight="600" fill="#64748B">kW</tspan>
        </text>
      </g>
    );
  };

  const renderCommercialPredictedCallout = (props: { cx?: number; cy?: number }) => {
    const { cx, cy } = props;
    if (cx === undefined || cy === undefined || !commercialData?.predictedCallout) return null;
    const callout = commercialData.predictedCallout;
    return (
      <g transform={`translate(${cx - 80}, ${cy - 88})`}>
        <rect width="160" height="66" rx="10" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="1.2" style={{ filter: 'drop-shadow(0 6px 18px rgba(11, 31, 51, 0.10))' }} />
        <polygon points="72,66 88,66 80,74" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="1.2" />
        <line x1="73" y1="65" x2="87" y2="65" stroke="#FFFFFF" strokeWidth="2" />
        <text x="14" y="20" fontSize="10" fill="#64748B" fontWeight="600">{callout.timestamp}</text>
        <circle cx="18" cy="34" r="3" fill="#8B5CF6" />
        <text x="26" y="37" fontSize="11" fill="#64748B" fontWeight="500">{callout.label}</text>
        <text x="14" y="55" fontSize="15" fill="#0B1F33" fontWeight="800">
          {callout.value.toLocaleString()} <tspan fontSize="11" fontWeight="600" fill="#64748B">kW</tspan>
        </text>
      </g>
    );
  };

  const renderGovActualCallout = (props: { cx?: number; cy?: number }) => {
    const { cx, cy } = props;
    if (cx === undefined || cy === undefined || !govDashboardData?.actualCallout) return null;
    const callout = govDashboardData.actualCallout;
    return (
      <g transform={`translate(${cx - 75}, ${cy - 88})`}>
        <rect width="150" height="66" rx="10" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="1.2" style={{ filter: 'drop-shadow(0 6px 18px rgba(11, 31, 51, 0.10))' }} />
        <polygon points="67,66 83,66 75,74" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="1.2" />
        <line x1="68" y1="65" x2="82" y2="65" stroke="#FFFFFF" strokeWidth="2" />
        <text x="14" y="20" fontSize="10" fill="#64748B" fontWeight="600">{callout.timestamp}</text>
        <circle cx="18" cy="34" r="3" fill="#00A396" />
        <text x="26" y="37" fontSize="11" fill="#64748B" fontWeight="500">{callout.label}</text>
        <text x="14" y="55" fontSize="15" fill="#0B1F33" fontWeight="800">
          {callout.value.toLocaleString()} <tspan fontSize="11" fontWeight="600" fill="#64748B">MW</tspan>
        </text>
      </g>
    );
  };

  const renderGovPredictedCallout = (props: { cx?: number; cy?: number }) => {
    const { cx, cy } = props;
    if (cx === undefined || cy === undefined || !govDashboardData?.predictedCallout) return null;
    const callout = govDashboardData.predictedCallout;
    return (
      <g transform={`translate(${cx - 80}, ${cy - 88})`}>
        <rect width="160" height="66" rx="10" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="1.2" style={{ filter: 'drop-shadow(0 6px 18px rgba(11, 31, 51, 0.10))' }} />
        <polygon points="72,66 88,66 80,74" fill="#FFFFFF" stroke="#E2E8F0" strokeWidth="1.2" />
        <line x1="73" y1="65" x2="87" y2="65" stroke="#FFFFFF" strokeWidth="2" />
        <text x="14" y="20" fontSize="10" fill="#64748B" fontWeight="600">{callout.timestamp}</text>
        <circle cx="18" cy="34" r="3" fill="#8B5CF6" />
        <text x="26" y="37" fontSize="11" fill="#64748B" fontWeight="500">{callout.label}</text>
        <text x="14" y="55" fontSize="15" fill="#0B1F33" fontWeight="800">
          {callout.value.toLocaleString()} <tspan fontSize="11" fontWeight="600" fill="#64748B">MW</tspan>
        </text>
      </g>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem', maxWidth: '1300px', margin: '0 auto', width: '100%' }}>
      {/* ========================================================= */}
      {/* 1. HOUSEHOLD / RESIDENTIAL VIEW                            */}
      {/* ========================================================= */}
      {persona === 'household' ? (
        <ResidentialGoldInsightsPage view="dashboard" />
      ) : persona === 'commercial' ? (
        /* ========================================================= */
        /* 2. COMMERCIAL DASHBOARD                                   */
        /* ========================================================= */
        <>
          <div>
            <h1 style={{ fontSize: '2.1rem', fontWeight: 800, color: '#0B1F33', margin: '0 0 0.35rem 0', letterSpacing: '-0.025em' }}>
              Hello, Rohit!
            </h1>
            <p style={{ fontSize: '0.95rem', color: '#64748B', margin: 0, fontWeight: 500 }}>
              Here is your commercial energy overview.
            </p>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid #E2E8F0',
              paddingBottom: '0.25rem',
              flexWrap: 'wrap',
              gap: '1rem',
            }}
          >
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setCommercialTab('building')}
                style={{
                  padding: '0.6rem 1.25rem',
                  border: 'none',
                  background: 'transparent',
                  fontSize: '0.92rem',
                  fontWeight: commercialTab === 'building' ? 700 : 500,
                  color: commercialTab === 'building' ? '#0B1F33' : '#64748B',
                  borderBottom: commercialTab === 'building' ? '2.5px solid #00A396' : '2.5px solid transparent',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                My Dashboard
              </button>
              <button
                type="button"
                onClick={() => setCommercialTab('regional')}
                style={{
                  padding: '0.6rem 1.25rem',
                  border: 'none',
                  background: 'transparent',
                  fontSize: '0.92rem',
                  fontWeight: commercialTab === 'regional' ? 700 : 500,
                  color: commercialTab === 'regional' ? '#0B1F33' : '#64748B',
                  borderBottom: commercialTab === 'regional' ? '2.5px solid #00A396' : '2.5px solid transparent',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                Regional Dashboard
              </button>
            </div>

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
              {(['1D', '7D', '1M', '3M', '1Y'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setCommercialRange(r)}
                  style={{
                    padding: '0.4rem 1.05rem',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                    border: 'none',
                    backgroundColor: commercialRange === r ? '#00A396' : 'transparent',
                    color: commercialRange === r ? '#FFFFFF' : '#64748B',
                    boxShadow: commercialRange === r ? '0 2px 8px rgba(0, 163, 150, 0.25)' : 'none',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          {commercialData && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                gap: '1.25rem',
              }}
            >
              <CommonMetricCard
                title="Average Demand"
                value={commercialData.avgDemand.toLocaleString()}
                unit={commercialData.unit}
                icon={<BarChart2 size={22} color="#00A396" />}
                iconBg="#E6F7F5"
                trend={{
                  value: Math.abs(commercialData.avgDemandDeltaPct),
                  direction: commercialData.avgDemandDeltaPct >= 0 ? 'up' : 'down',
                  isIncreaseNegative: true,
                  comparisonText: `vs previous day (${commercialData.prevPeriodAvgDemand.toLocaleString()} ${commercialData.unit})`,
                }}
                hoverBorderColor="rgba(0, 163, 150, 0.4)"
              />
              <CommonMetricCard
                title="Peak Demand"
                value={commercialData.peakDemand.toLocaleString()}
                unit={commercialData.unit}
                icon={<Zap size={22} color="#D97706" fill="#D97706" />}
                iconBg="#FFF7ED"
                subtext={commercialData.peakTimestamp}
                hoverBorderColor="rgba(217, 119, 6, 0.4)"
              />
              <CommonMetricCard
                title="Predicted Peak"
                value={commercialData.predictedPeak.toLocaleString()}
                unit={commercialData.unit}
                icon={<TrendingUp size={22} color="#7C3AED" />}
                iconBg="#F5F3FF"
                subtext={commercialData.predictedPeakTimestamp}
                hoverBorderColor="rgba(124, 58, 237, 0.4)"
              />
              <CommonMetricCard
                title="Predicted Total"
                value={
                  isMWh
                    ? (commercialData.predictedTotal / 1000).toFixed(2)
                    : commercialData.predictedTotal.toLocaleString()
                }
                unit={isMWh ? 'MWh' : commercialData.totalUnit}
                icon={<FileText size={22} color="#2563EB" />}
                iconBg="#EFF6FF"
                subtext={commercialData.predictedTotalHorizon}
                hoverBorderColor="rgba(37, 99, 235, 0.4)"
              />
            </div>
          )}

          <div
            style={{
              backgroundColor: '#FFFFFF',
              borderRadius: '18px',
              border: '1px solid #E2E8F0',
              padding: '1.75rem',
              boxShadow: '0 4px 20px -2px rgba(11, 31, 51, 0.03)',
            }}
          >
            <div style={{ marginBottom: '1.75rem' }}>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0B1F33', margin: '0 0 0.25rem 0' }}>
                Demand vs Time
              </h2>
              <p style={{ fontSize: '0.84rem', color: '#64748B', margin: 0 }}>
                Actual and predicted demand for the selected period.
              </p>
            </div>

            <div style={{ width: '100%', height: '375px' }}>
              {commercialLoading ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94A3B8' }}>
                  Loading commercial telemetry...
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart
                    data={commercialData?.curve || []}
                    margin={{ top: 40, right: 20, left: 10, bottom: 5 }}
                  >
                    <defs>
                      <linearGradient id="commActualGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#00A396" stopOpacity={0.2} />
                        <stop offset="95%" stopColor="#00A396" stopOpacity={0.0} />
                      </linearGradient>
                      <linearGradient id="commPredGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.18} />
                        <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>

                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />

                    <XAxis
                      dataKey="time"
                      tick={{ fontSize: 11, fill: '#64748B', fontWeight: 500 }}
                      axisLine={{ stroke: '#E2E8F0' }}
                      tickLine={false}
                    />

                    <YAxis
                      domain={[0, commercialTab === 'regional' ? 5000 : 1200]}
                      ticks={
                        commercialTab === 'regional'
                          ? [0, 1000, 2000, 3000, 4000, 5000]
                          : [0, 200, 400, 600, 800, 1000, 1200]
                      }
                      width={56}
                      tick={{ fontSize: 11, fill: '#64748B', fontWeight: 500 }}
                      axisLine={false}
                      tickLine={false}
                      label={{
                        value: 'Demand (kW)',
                        angle: -90,
                        position: 'insideLeft',
                        fill: '#64748B',
                        fontSize: 11,
                        fontWeight: 600,
                        dy: 50,
                        dx: 12,
                      }}
                    />

                    <Tooltip content={<CommonChartHoverCard unit="kW" />} />

                    {commercialData?.demarcationTime && (
                      <ReferenceLine
                        x={commercialData.demarcationTime}
                        stroke="#94A3B8"
                        strokeDasharray="4 4"
                        strokeWidth={1.5}
                      />
                    )}

                    {commercialData?.actualCallout && (
                      <ReferenceDot
                        x={commercialData.actualCallout.time}
                        y={commercialData.actualCallout.value}
                        r={4.5}
                        fill="#00A396"
                        stroke="#FFFFFF"
                        strokeWidth={2}
                        label={renderCommercialActualCallout}
                      />
                    )}

                    {commercialData?.predictedCallout && (
                      <ReferenceDot
                        x={commercialData.predictedCallout.time}
                        y={commercialData.predictedCallout.value}
                        r={4.5}
                        fill="#8B5CF6"
                        stroke="#FFFFFF"
                        strokeWidth={2}
                        label={renderCommercialPredictedCallout}
                      />
                    )}

                    <Area
                      type="monotone"
                      dataKey="actualDemand"
                      name="Actual Demand"
                      stroke="#00A396"
                      strokeWidth={2.8}
                      fill="url(#commActualGrad)"
                      dot={false}
                      connectNulls={false}
                    />

                    <Area
                      type="monotone"
                      dataKey="predictedDemand"
                      name="Predicted Demand"
                      stroke="#8B5CF6"
                      strokeWidth={2.8}
                      strokeDasharray="5 5"
                      fill="url(#commPredGrad)"
                      dot={false}
                      connectNulls={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              )}
            </div>

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
                <span>Actual Demand</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.82rem', color: '#64748B', fontWeight: 500 }}>
                <div style={{ width: '26px', height: '0px', borderTop: '2.5px dashed #8B5CF6' }} />
                <span>Predicted Demand</span>
              </div>
            </div>
          </div>
        </>
      ) : (
        /* ========================================================= */
        /* 3. GOVERNMENT & UTILITIES DASHBOARD                       */
        /* (Matches Views 1, 2, 3 of Attached User Reference)       */
        /* ========================================================= */
        <>
          {/* Top Dynamic Tabs & 1D, 7D, 1M, 3M, 1Y Filter Pills */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid #E2E8F0',
              paddingBottom: '0.25rem',
              flexWrap: 'wrap',
              gap: '1rem',
            }}
          >
            {/* Left: Dynamic Tabs Row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', flexWrap: 'wrap' }}>
              {/* Tab 1: Overall Demand */}
              <button
                type="button"
                onClick={() => {
                  setPreviousGovTab(govActiveTab);
                  setGovActiveTab('overall');
                }}
                style={{
                  padding: '0.6rem 1.15rem',
                  border: 'none',
                  background: 'transparent',
                  fontSize: '0.92rem',
                  fontWeight: govActiveTab === 'overall' ? 700 : 500,
                  color: govActiveTab === 'overall' ? '#0B1F33' : '#64748B',
                  borderBottom: govActiveTab === 'overall' ? '2.5px solid #00A396' : '2.5px solid transparent',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                Overall Demand
              </button>

              {/* Tab 2: Regional Dashboard (List of Regions) */}
              <button
                type="button"
                onClick={() => {
                  setPreviousGovTab(govActiveTab);
                  setGovActiveTab('regional_list');
                }}
                style={{
                  padding: '0.6rem 1.15rem',
                  border: 'none',
                  background: 'transparent',
                  fontSize: '0.92rem',
                  fontWeight: govActiveTab === 'regional_list' ? 700 : 500,
                  color: govActiveTab === 'regional_list' ? '#0B1F33' : '#64748B',
                  borderBottom: govActiveTab === 'regional_list' ? '2.5px solid #00A396' : '2.5px solid transparent',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                Regional Dashboard
              </button>

              {/* Dynamic Open Region Tabs with Close Button */}
              {openRegionTabs.map((regId) => {
                const reg = governmentRegions.find((r) => r.id === regId);
                const isTabActive = govActiveTab === `region_${regId}`;
                return (
                  <div
                    key={regId}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.45rem',
                      padding: '0.6rem 1rem',
                      borderBottom: isTabActive ? '2.5px solid #00A396' : '2.5px solid transparent',
                      color: isTabActive ? '#0B1F33' : '#64748B',
                      fontWeight: isTabActive ? 700 : 500,
                      cursor: 'pointer',
                      fontSize: '0.92rem',
                      transition: 'all 0.15s ease',
                    }}
                    onClick={() => {
                      setPreviousGovTab(govActiveTab);
                      setGovActiveTab(`region_${regId}`);
                    }}
                  >
                    <span>{reg?.name || regId}</span>
                    <button
                      type="button"
                      onClick={(e) => handleCloseRegionTab(e, regId)}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#94A3B8',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: '2px',
                        borderRadius: '4px',
                        marginLeft: '2px',
                      }}
                      title="Close tab"
                    >
                      <X size={14} />
                    </button>
                  </div>
                );
              })}

              {/* Optional Add Tab Affordance matching reference (+) */}
              <button
                type="button"
                onClick={() => {
                  setPreviousGovTab(govActiveTab);
                  setGovActiveTab('regional_list');
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '28px',
                  height: '28px',
                  borderRadius: '6px',
                  border: '1px dashed #CBD5E1',
                  background: 'transparent',
                  color: '#64748B',
                  cursor: 'pointer',
                  marginLeft: '0.35rem',
                }}
                title="Browse & Open Regions"
              >
                <Plus size={15} />
              </button>
            </div>

            {/* Right: Working 1D, 7D, 1M, 3M, 1Y Filter Pills */}
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
              {(['1D', '7D', '1M', '3M', '1Y'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setGovTimeRange(r)}
                  style={{
                    padding: '0.4rem 1.05rem',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    borderRadius: '8px',
                    border: 'none',
                    backgroundColor: govTimeRange === r ? '#00A396' : 'transparent',
                    color: govTimeRange === r ? '#FFFFFF' : '#64748B',
                    boxShadow: govTimeRange === r ? '0 2px 8px rgba(0, 163, 150, 0.25)' : 'none',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          {/* VIEW SWITCHER: Regional List vs Dashboard Views */}
          {govActiveTab === 'regional_list' ? (
            /* ========================================================= */
            /* VIEW 2: Regional Dashboard (List of Regions Cards)        */
            /* ========================================================= */
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {/* Header with Title and Search Input */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '1rem',
                  marginTop: '0.5rem',
                }}
              >
                <div>
                  <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#0B1F33', margin: '0 0 0.25rem 0' }}>
                    Select a region to view details
                  </h2>
                  <p style={{ fontSize: '0.85rem', color: '#64748B', margin: 0 }}>
                    Click on a region card to open its dashboard in a new tab.
                  </p>
                </div>

                {/* Search Input matching UI reference */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    padding: '0.45rem 0.85rem',
                    backgroundColor: '#FFFFFF',
                    border: '1px solid #E2E8F0',
                    borderRadius: '8px',
                    width: '240px',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                  }}
                >
                  <Search size={16} color="#94A3B8" />
                  <input
                    type="text"
                    value={regionSearchQuery}
                    onChange={(e) => setRegionSearchQuery(e.target.value)}
                    placeholder="Search regions..."
                    style={{
                      border: 'none',
                      outline: 'none',
                      fontSize: '0.84rem',
                      color: '#0B1F33',
                      width: '100%',
                      background: 'transparent',
                    }}
                  />
                  {regionSearchQuery && (
                    <button
                      type="button"
                      onClick={() => setRegionSearchQuery('')}
                      style={{ border: 'none', background: 'transparent', cursor: 'pointer', padding: 0, color: '#94A3B8' }}
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
              </div>

              {/* Grid of Region Cards (2 rows of 3) */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                  gap: '1.25rem',
                  marginTop: '0.5rem',
                }}
              >
                {filteredRegions.map((region) => {
                  const isUp = region.deltaPct > 0;
                  return (
                    <div
                      key={region.id}
                      onClick={() => handleOpenRegion(region.id)}
                      style={{
                        backgroundColor: '#FFFFFF',
                        border: '1px solid #E2E8F0',
                        borderRadius: '16px',
                        padding: '1.35rem 1.5rem',
                        cursor: 'pointer',
                        boxShadow: '0 2px 8px rgba(11, 31, 51, 0.03)',
                        transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        minHeight: '142px',
                        boxSizing: 'border-box',
                        position: 'relative',
                        overflow: 'hidden',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = 'translateY(-2px)';
                        e.currentTarget.style.boxShadow = '0 10px 22px -4px rgba(11, 31, 51, 0.08)';
                        e.currentTarget.style.borderColor = 'rgba(0, 163, 150, 0.4)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(11, 31, 51, 0.03)';
                        e.currentTarget.style.borderColor = '#E2E8F0';
                      }}
                    >
                      {/* Top Row: Pin Icon, Region Name, Chevron */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                          <div
                            style={{
                              width: '32px',
                              height: '32px',
                              borderRadius: '8px',
                              backgroundColor:
                                region.pinColor === '#10B981'
                                  ? '#ECFDF5'
                                  : region.pinColor === '#7C3AED'
                                  ? '#F5F3FF'
                                  : '#EFF6FF',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                            }}
                          >
                            <MapPin size={17} color={region.pinColor} />
                          </div>
                          <span style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0B1F33' }}>
                            {region.name}
                          </span>
                        </div>
                        <ChevronRight size={17} color="#94A3B8" />
                      </div>

                      {/* Bottom Row: Number on Left, Trend below, Sparkline on Right */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'flex-end',
                          justifyContent: 'space-between',
                          marginTop: '1rem',
                        }}
                      >
                        <div>
                          <div style={{ fontSize: '1.65rem', fontWeight: 800, color: '#0B1F33', lineHeight: 1 }}>
                            {region.currentDemand.toLocaleString()}{' '}
                            <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#64748B' }}>
                              {region.unit}
                            </span>
                          </div>
                          <div
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '2px',
                              marginTop: '0.35rem',
                              fontSize: '0.8rem',
                              fontWeight: 700,
                              color: isUp ? '#EF4444' : '#10B981',
                            }}
                          >
                            <span>{isUp ? '↑' : '↓'}</span>
                            <span>{Math.abs(region.deltaPct)}%</span>
                          </div>
                        </div>

                        {/* Inline SVG Sparkline matching screenshot */}
                        <svg width="100" height="42" viewBox="0 0 100 42" fill="none">
                          <defs>
                            <linearGradient id={`spark-${region.id}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={isUp ? '#EF4444' : '#10B981'} stopOpacity="0.22" />
                              <stop offset="100%" stopColor={isUp ? '#EF4444' : '#10B981'} stopOpacity="0.0" />
                            </linearGradient>
                          </defs>
                          <path
                            d={
                              isUp
                                ? 'M 2 32 Q 28 26, 55 18 T 98 8 L 98 42 L 2 42 Z'
                                : 'M 2 10 Q 28 18, 55 24 T 98 28 L 98 42 L 2 42 Z'
                            }
                            fill={`url(#spark-${region.id})`}
                          />
                          <path
                            d={
                              isUp
                                ? 'M 2 32 Q 28 26, 55 18 T 98 8'
                                : 'M 2 10 Q 28 18, 55 24 T 98 28'
                            }
                            stroke={isUp ? '#EF4444' : '#10B981'}
                            strokeWidth="2.2"
                            strokeLinecap="round"
                            fill="none"
                          />
                        </svg>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            /* ========================================================= */
            /* VIEW 1 (Overall) & VIEW 3 (Selected Region Tab View)      */
            /* ========================================================= */
            <>
              {/* Four KPI Cards */}
              {govDashboardData && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                    gap: '1.25rem',
                  }}
                >
                  <CommonMetricCard
                    title="Average Demand"
                    value={govDashboardData.avgDemand.toLocaleString()}
                    unit={govDashboardData.unit}
                    icon={<BarChart2 size={22} color="#00A396" />}
                    iconBg="#E6F7F5"
                    trend={{
                      value: Math.abs(govDashboardData.avgDemandDeltaPct),
                      direction: govDashboardData.avgDemandDeltaPct >= 0 ? 'up' : 'down',
                      isIncreaseNegative: true,
                      comparisonText: `vs previous day (${govDashboardData.prevPeriodAvgDemand.toLocaleString()} ${govDashboardData.unit})`,
                    }}
                    hoverBorderColor="rgba(0, 163, 150, 0.4)"
                  />

                  <CommonMetricCard
                    title="Peak Demand"
                    value={govDashboardData.peakDemand.toLocaleString()}
                    unit={govDashboardData.unit}
                    icon={<Zap size={22} color="#D97706" fill="#D97706" />}
                    iconBg="#FFF7ED"
                    subtext={govDashboardData.peakTimestamp}
                    hoverBorderColor="rgba(217, 119, 6, 0.4)"
                  />

                  <CommonMetricCard
                    title="Predicted Peak"
                    value={govDashboardData.predictedPeak.toLocaleString()}
                    unit={govDashboardData.unit}
                    icon={<TrendingUp size={22} color="#7C3AED" />}
                    iconBg="#F5F3FF"
                    subtext={govDashboardData.predictedPeakTimestamp}
                    hoverBorderColor="rgba(124, 58, 237, 0.4)"
                  />

                  <CommonMetricCard
                    title="Predicted Total"
                    value={govDashboardData.predictedTotal.toLocaleString()}
                    unit={govDashboardData.totalUnit}
                    icon={<FileText size={22} color="#2563EB" />}
                    iconBg="#EFF6FF"
                    subtext={govDashboardData.predictedTotalHorizon}
                    hoverBorderColor="rgba(37, 99, 235, 0.4)"
                  />
                </div>
              )}

              {/* Demand vs Time Chart Card */}
              <div
                style={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: '18px',
                  border: '1px solid #E2E8F0',
                  padding: '1.75rem',
                  boxShadow: '0 4px 20px -2px rgba(11, 31, 51, 0.03)',
                }}
              >
                <div style={{ marginBottom: '1.75rem' }}>
                  <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0B1F33', margin: '0 0 0.25rem 0' }}>
                    Demand vs Time
                  </h2>
                  <p style={{ fontSize: '0.84rem', color: '#64748B', margin: 0 }}>
                    {govActiveTab === 'overall'
                      ? 'Actual and predicted demand for the selected period.'
                      : `Actual and predicted demand for ${govDashboardData?.regionName || 'selected region'}`}
                  </p>
                </div>

                <div style={{ width: '100%', height: '375px' }}>
                  {govLoading ? (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94A3B8' }}>
                      Loading government grid telemetry...
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart
                        data={govDashboardData?.curve || []}
                        margin={{ top: 40, right: 20, left: 10, bottom: 5 }}
                      >
                        <defs>
                          <linearGradient id="govActualGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#00A396" stopOpacity={0.2} />
                            <stop offset="95%" stopColor="#00A396" stopOpacity={0.0} />
                          </linearGradient>
                          <linearGradient id="govPredGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.18} />
                            <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0.0} />
                          </linearGradient>
                        </defs>

                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F1F5F9" />

                        <XAxis
                          dataKey="time"
                          tick={{ fontSize: 11, fill: '#64748B', fontWeight: 500 }}
                          axisLine={{ stroke: '#E2E8F0' }}
                          tickLine={false}
                        />

                        <YAxis
                          domain={govDashboardData?.yDomain || [0, 12000]}
                          ticks={govDashboardData?.yTicks || [0, 2000, 4000, 6000, 8000, 10000, 12000]}
                          width={56}
                          tick={{ fontSize: 11, fill: '#64748B', fontWeight: 500 }}
                          axisLine={false}
                          tickLine={false}
                          label={{
                            value: 'Demand (MW)',
                            angle: -90,
                            position: 'insideLeft',
                            fill: '#64748B',
                            fontSize: 11,
                            fontWeight: 600,
                            dy: 50,
                            dx: 12,
                          }}
                        />

                        <Tooltip content={<CommonChartHoverCard unit="MW" />} />

                        {govDashboardData?.demarcationTime && (
                          <ReferenceLine
                            x={govDashboardData.demarcationTime}
                            stroke="#94A3B8"
                            strokeDasharray="4 4"
                            strokeWidth={1.5}
                          />
                        )}

                        {govDashboardData?.actualCallout && (
                          <ReferenceDot
                            x={govDashboardData.actualCallout.time}
                            y={govDashboardData.actualCallout.value}
                            r={4.5}
                            fill="#00A396"
                            stroke="#FFFFFF"
                            strokeWidth={2}
                            label={renderGovActualCallout}
                          />
                        )}

                        {govDashboardData?.predictedCallout && (
                          <ReferenceDot
                            x={govDashboardData.predictedCallout.time}
                            y={govDashboardData.predictedCallout.value}
                            r={4.5}
                            fill="#8B5CF6"
                            stroke="#FFFFFF"
                            strokeWidth={2}
                            label={renderGovPredictedCallout}
                          />
                        )}

                        <Area
                          type="monotone"
                          dataKey="actualDemand"
                          name="Actual Demand"
                          stroke="#00A396"
                          strokeWidth={2.8}
                          fill="url(#govActualGrad)"
                          dot={false}
                          connectNulls={false}
                        />

                        <Area
                          type="monotone"
                          dataKey="predictedDemand"
                          name="Predicted Demand"
                          stroke="#8B5CF6"
                          strokeWidth={2.8}
                          strokeDasharray="5 5"
                          fill="url(#govPredGrad)"
                          dot={false}
                          connectNulls={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  )}
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
                    <span>Actual Demand</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.82rem', color: '#64748B', fontWeight: 500 }}>
                    <div style={{ width: '26px', height: '0px', borderTop: '2.5px dashed #8B5CF6' }} />
                    <span>Predicted Demand</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
};
