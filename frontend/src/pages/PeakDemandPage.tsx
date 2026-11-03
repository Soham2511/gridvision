import React, { useEffect, useState } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import { ChartCard } from '../components/common/ChartCard';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorState } from '../components/common/ErrorState';
import { analyticsService } from '../services/analyticsService';
import { PeakDemandAnalysis } from '../types/analytics';
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import {
  ShieldAlert,
  Sliders,
  Zap,
  CheckCircle2,
} from 'lucide-react';

export const PeakDemandPage: React.FC = () => {
  const [data, setData] = useState<PeakDemandAnalysis | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Interactive ADR Curtailment Simulation
  const [curtailmentMw, setCurtailmentMw] = useState<number>(15);
  const [dispatchConfirmed, setDispatchConfirmed] = useState<boolean>(false);
  const [dispatchMessage, setDispatchMessage] = useState<string | null>(null);
  const [dispatchError, setDispatchError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await analyticsService.getPeakDemandAnalysis();
        setData(res);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load peak analysis.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Peak Demand & Capacity Planning" description="Analyzing peak stress windows..." />
        <LoadingSkeleton height="150px" count={3} />
      </div>
    );
  }

  if (error || !data) {
    return <ErrorState title="Peak Analysis Offline" message={error || 'No peak data available.'} />;
  }

  // Dynamic simulation values
  const simulatedPeakMw = data.expectedPeakMw - curtailmentMw;
  const simulatedReservePct = ((data.peakCapacityLimitMw - simulatedPeakMw) / data.peakCapacityLimitMw) * 100;
  const simulatedSavingsInr = curtailmentMw * 160000; // ₹160,000 per MW capacity charge tariff

  const handleDispatch = async () => {
    setDispatchError(null);
    setDispatchMessage(null);
    try {
      const result = await analyticsService.dispatchCurtailment(curtailmentMw);
      setDispatchConfirmed(true);
      setDispatchMessage(result.message);
      setTimeout(() => setDispatchConfirmed(false), 4000);
    } catch (err) {
      setDispatchConfirmed(false);
      setDispatchError(err instanceof Error ? err.message : 'Demand response dispatch failed.');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Header */}
      <PageHeader
        title="Peak Demand & Capacity Planning"
        description="Predicting coincident peak windows, monitoring reserve capacity margins, and simulating demand-response curtailment."
        badge={<StatusBadge status={data.riskLevel} label={`${data.riskLevel.toUpperCase()} RISK WINDOW`} />}
      />

      {/* Primary Capacity Stress Row */}
      <section className="gv-grid-kpis">
        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Current Grid Load</span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-text-primary)', marginTop: '0.35rem' }}>
            {data.currentLoadMw} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>MW</span>
          </div>
          <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>69.8% of system capacity ceiling</p>
        </div>

        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Anticipated Coincident Peak</span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-energy-amber)', marginTop: '0.35rem' }}>
            {data.expectedPeakMw} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>MW</span>
          </div>
          <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Projected: {data.expectedPeakTime}</p>
        </div>

        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>System Reserve Margin</span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-smart-teal)', marginTop: '0.35rem' }}>
            {data.reserveMarginPct}%
          </div>
          <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>57.4 MW buffer before alert trip</p>
        </div>

        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>System Capacity Ceiling</span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-grid-blue)', marginTop: '0.35rem' }}>
            {data.peakCapacityLimitMw} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>MW</span>
          </div>
          <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>17-Site thermal transformer limit</p>
        </div>
      </section>

      {/* Charts Row: Hourly Peak Diurnal Frequency & Daily Peak Timeline */}
      <section className="gv-grid-2col">
        {/* Hourly Peak Diurnal Probability */}
        <ChartCard
          title="24-Hour Diurnal Peak Probability"
          subtitle="Frequency distribution of coincident peak occurrences across the 24-hour cycle"
          height="300px"
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data.hourlyDistribution} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
              <XAxis dataKey="hourLabel" stroke="#94A3B8" tick={{ fontSize: 10 }} />
              <YAxis yAxisId="left" stroke="#94A3B8" tick={{ fontSize: 10 }} unit=" MW" />
              <YAxis yAxisId="right" orientation="right" stroke="#FFC247" tick={{ fontSize: 10 }} unit="%" />
              <Tooltip />
              <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 10, paddingBottom: 5 }} />
              <Bar yAxisId="left" dataKey="avgDemandMw" name="Average Hourly Load (MW)" fill="var(--gv-color-grid-blue)" radius={[4, 4, 0, 0]} />
              <Line yAxisId="right" type="monotone" dataKey="peakFrequencyPct" name="Peak Occurrence Probability (%)" stroke="var(--gv-color-energy-amber)" strokeWidth={2.5} dot={{ r: 4, fill: 'var(--gv-color-energy-amber)' }} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Daily Peak Timeline */}
        <ChartCard
          title="Daily Peak Timeline & Horizon"
          subtitle="Observed daily peaks vs projected peaks against the 460 MW warning line"
          height="300px"
        >
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data.dailyPeakTimeline} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
              <XAxis dataKey="dayLabel" stroke="#94A3B8" tick={{ fontSize: 10 }} />
              <YAxis stroke="#94A3B8" tick={{ fontSize: 10 }} unit=" MW" domain={[300, 520]} />
              <Tooltip />
              <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 10, paddingBottom: 5 }} />
              <ReferenceLine y={460} stroke="#EF4444" strokeDasharray="4 4" label={{ value: 'Peak Warning (460 MW)', fill: '#EF4444', fontSize: 10, position: 'insideTopLeft' }} />
              <Bar dataKey="peakMw" name="Daily Peak (MW)" fill="var(--gv-color-smart-teal)" radius={[4, 4, 0, 0]} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
      </section>

      {/* Interactive Demand Response Simulation Tool */}
      <section className="gv-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <Sliders size={20} color="var(--gv-color-smart-teal)" />
              <h3 className="gv-heading-2">Automated Demand Response (ADR) Simulation</h3>
            </div>
            <p className="gv-text-muted" style={{ marginTop: '0.2rem' }}>
              Adjust proposed industrial curtailment to evaluate peak reduction, reserve margin enhancement, and tariff savings.
            </p>
          </div>
          {dispatchConfirmed && (
            <span className="gv-badge gv-badge-success">
              <CheckCircle2 size={13} />
              <span>{dispatchMessage || 'Simulated ADR signal dispatched'}</span>
            </span>
          )}
        </div>
        {dispatchError && (
          <div role="alert" className="gv-badge gv-badge-danger" style={{ marginBottom: '1rem' }}>
            {dispatchError}
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem', alignItems: 'center' }}>
          <div>
            <label style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', fontWeight: 700, marginBottom: '0.5rem' }}>
              <span>Target Load Curtailment / Shifting</span>
              <strong style={{ color: 'var(--gv-color-grid-blue)', fontFamily: 'var(--gv-font-mono)' }}>{curtailmentMw} MW</strong>
            </label>
            <input
              type="range"
              min="0"
              max="35"
              step="5"
              value={curtailmentMw}
              onChange={(e) => setCurtailmentMw(Number(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--gv-color-smart-teal)', cursor: 'pointer' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--gv-text-muted)', marginTop: '0.25rem' }}>
              <span>0 MW (Baseline)</span>
              <span>15 MW (Recommended)</span>
              <span>35 MW (Emergency)</span>
            </div>
          </div>

          {/* Simulation Output Cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div style={{ padding: '0.75rem', background: 'var(--gv-bg-surface-subtle)', borderRadius: 'var(--gv-radius-md)' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)', fontWeight: 600 }}>SIMULATED PEAK LOAD</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--gv-text-primary)', marginTop: '0.2rem' }}>
                {simulatedPeakMw.toFixed(1)} MW
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--gv-color-smart-teal)', fontWeight: 600 }}>
                -{curtailmentMw} MW reduction
              </div>
            </div>

            <div style={{ padding: '0.75rem', background: 'var(--gv-bg-surface-subtle)', borderRadius: 'var(--gv-radius-md)' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)', fontWeight: 600 }}>ENHANCED RESERVE MARGIN</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--gv-color-smart-teal)', marginTop: '0.2rem' }}>
                {simulatedReservePct.toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--gv-text-secondary)' }}>
                Baseline was {data.reserveMarginPct}%
              </div>
            </div>
          </div>

          {/* Action Callout */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <div style={{ fontSize: '0.78rem', color: 'var(--gv-text-secondary)' }}>
              Estimated Demand Tariff Reduction: <strong style={{ color: 'var(--gv-color-smart-teal)' }}>₹{simulatedSavingsInr.toLocaleString()}</strong>
            </div>
            <button
              type="button"
              onClick={handleDispatch}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.45rem',
                padding: '0.65rem 1.25rem',
                background: 'var(--gv-color-smart-teal)',
                color: '#FFFFFF',
                borderRadius: 'var(--gv-radius-md)',
                fontSize: '0.85rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              <Zap size={15} />
              <span>Dispatch Automated Demand Response</span>
            </button>
          </div>
        </div>
      </section>

      {/* Operational Protocol Callout */}
      <div
        style={{
          background: 'rgba(8, 126, 189, 0.06)',
          border: '1px solid rgba(8, 126, 189, 0.2)',
          borderRadius: 'var(--gv-radius-md)',
          padding: '0.85rem 1.1rem',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.85rem',
        }}
      >
        <ShieldAlert size={20} color="var(--gv-color-grid-blue)" style={{ flexShrink: 0, marginTop: '2px' }} />
        <div>
          <h4 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--gv-color-midnight-navy)', marginBottom: '0.25rem' }}>
            Grid Dispatch Standard Operating Procedure (SOP)
          </h4>
          <p style={{ fontSize: '0.78rem', color: 'var(--gv-text-secondary)', lineHeight: 1.5 }}>
            {data.mitigationStrategy} Advance notifications ensure Tier-1 commercial HVAC and regional pumping systems ramp down before the 17:00 coincident grid ramp.
          </p>
        </div>
      </div>
    </div>
  );
};
