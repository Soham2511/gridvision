import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/common/PageHeader';
import { KpiCard } from '../components/common/KpiCard';
import { ChartCard } from '../components/common/ChartCard';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorState } from '../components/common/ErrorState';
import { StatusBadge } from '../components/common/StatusBadge';
import { DemandTrendsChart } from '../components/dashboard/DemandTrendsChart';
import { analyticsService } from '../services/analyticsService';
import {
  KpiMetric,
  TimeSeriesPoint,
  PeakDemandAnalysis,
  AnomalyEvent,
  CustomerSegment,
  BusinessInsight,
} from '../types/analytics';
import {
  AlertTriangle,
  Users,
  Lightbulb,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Clock,
} from 'lucide-react';

export const OverviewPage: React.FC = () => {
  const [kpis, setKpis] = useState<KpiMetric[]>([]);
  const [trends, setTrends] = useState<TimeSeriesPoint[]>([]);
  const [peakAnalysis, setPeakAnalysis] = useState<PeakDemandAnalysis | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([]);
  const [segments, setSegments] = useState<CustomerSegment[]>([]);
  const [insights, setInsights] = useState<BusinessInsight[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);

  const loadData = async (refresh = false) => {
    try {
      if (refresh) setIsRefreshing(true);
      setError(null);

      const [overviewData, commData, anomData, segData, insData] = await Promise.all([
        analyticsService.getOverview(),
        analyticsService.getCommercialForecast('Panther_office_1'),
        analyticsService.getAnomalyEvents(),
        analyticsService.getCustomerSegments(),
        analyticsService.getBusinessInsights(),
      ]);

      setPeakAnalysis(overviewData.peakAnalysis);
      setAnomalies(anomData);
      setSegments(segData);
      setInsights(insData);
      setTrends(commData.horizon);
      setKpis(overviewData.kpis);
      setLastSyncedAt(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retrieve overview metrics.');
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Executive Overview" description="Loading system telemetry..." />
        <div className="gv-grid-kpis">
          <LoadingSkeleton height="130px" count={4} />
        </div>
        <LoadingSkeleton height="320px" count={1} />
      </div>
    );
  }

  if (error || !peakAnalysis) {
    return (
      <ErrorState
        title="Telemetry Offline"
        message={error || 'Unable to connect to telemetry service.'}
        onRetry={() => {
          setLoading(true);
          loadData();
        }}
      />
    );
  }

  const criticalAnomalies = anomalies.filter((a) => a.severity === 'critical');
  const primaryInsights = insights.slice(0, 2);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Header */}
      <PageHeader
        title="GridVision Executive Overview"
        description="High-level operational summary across demand forecasting, peak capacity risk, anomaly detection, and customer profiling."
        onRefresh={() => loadData(true)}
        isRefreshing={isRefreshing}
        badge={
          <span className="gv-badge gv-badge-success">
            <CheckCircle2 size={12} />
            <span>Backend API Connected</span>
          </span>
        }
      />

      {/* System Status Banner */}
      <div
        style={{
          background: 'rgba(8, 126, 189, 0.05)',
          border: '1px solid rgba(8, 126, 189, 0.2)',
          borderRadius: 'var(--gv-radius-md)',
          padding: '0.65rem 1rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.5rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.78rem', color: 'var(--gv-color-grid-blue)' }}>
          <ShieldCheck size={16} />
          <span>
            <strong>Executive Snapshot:</strong> Click any analytical domain card below to navigate directly to its dedicated deep-dive studio.
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.72rem', color: 'var(--gv-text-muted)' }}>
          <Clock size={12} />
          <span>
            Backend sync: {lastSyncedAt?.toLocaleString() ?? 'Pending'}
          </span>
        </div>
      </div>

      {/* 1. High-Level KPI Summary Cards */}
      <section className="gv-grid-kpis">
        {kpis.map((kpi) => (
          <KpiCard key={kpi.id} metric={kpi} />
        ))}
      </section>

      {/* 2. Compact Snapshot Rows: Demand Trends & Peak Capacity */}
      <section className="gv-grid-2col">
        {/* Demand Forecasting Snapshot */}
        <ChartCard
          title="Demand Trajectory Snapshot"
          subtitle="Recent hourly observations vs projected 10-hour horizon (Panther Commercial)"
          height="280px"
          actions={
            <Link
              to="/forecasting"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.78rem',
                fontWeight: 700,
                color: 'var(--gv-color-smart-teal)',
                textDecoration: 'none',
              }}
            >
              <span>Forecasting Studio</span>
              <ArrowRight size={14} />
            </Link>
          }
        >
          <DemandTrendsChart data={trends} />
        </ChartCard>

        {/* Peak Demand Capacity Snapshot */}
        <div className="gv-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
              <div>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--gv-text-muted)', textTransform: 'uppercase' }}>
                  Peak Stress Monitor
                </span>
                <h3 className="gv-heading-2" style={{ marginTop: '0.2rem' }}>
                  Capacity Margin
                </h3>
              </div>
              <StatusBadge status={peakAnalysis.riskLevel} label={`${peakAnalysis.riskLevel.toUpperCase()} RISK`} />
            </div>

            <div
              style={{
                padding: '0.85rem',
                background: 'var(--gv-bg-surface-subtle)',
                borderRadius: 'var(--gv-radius-md)',
                marginBottom: '1rem',
              }}
            >
              <div style={{ fontSize: '0.72rem', color: 'var(--gv-text-muted)', fontWeight: 600 }}>NEXT COINCIDENT PEAK</div>
              <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--gv-text-primary)' }}>
                {peakAnalysis.expectedPeakMw} MW
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gv-color-grid-blue)', fontWeight: 600, marginTop: '0.2rem' }}>
                {peakAnalysis.expectedPeakTime}
              </div>
            </div>

            <div style={{ marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '0.35rem' }}>
                <span style={{ color: 'var(--gv-text-secondary)', fontWeight: 600 }}>System Capacity Buffer</span>
                <strong style={{ color: 'var(--gv-color-smart-teal)' }}>{peakAnalysis.reserveMarginPct}% Reserve</strong>
              </div>
              <div style={{ height: '8px', background: '#E2E8F0', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${(peakAnalysis.currentLoadMw / peakAnalysis.peakCapacityLimitMw) * 100}%`, background: 'var(--gv-color-smart-teal)' }} />
              </div>
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '0.75rem' }}>
            <Link
              to="/peak-demand"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.78rem',
                fontWeight: 700,
                color: 'var(--gv-color-grid-blue)',
                textDecoration: 'none',
              }}
            >
              <span>Open Peak Demand Planner</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </section>

      {/* 3. Secondary Snapshots: Anomaly Alert Bar + Customer Segment Highlights */}
      <section className="gv-grid-2col">
        {/* Anomaly Center Snapshot */}
        <div className="gv-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <AlertTriangle size={18} color="var(--gv-status-danger)" />
                <h3 className="gv-heading-2">Grid Anomaly Alert</h3>
              </div>
              <span className="gv-badge gv-badge-danger">
                {criticalAnomalies.length} Critical Event
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
              {anomalies.slice(0, 2).map((item) => (
                <div
                  key={item.id}
                  style={{
                    padding: '0.65rem 0.85rem',
                    borderRadius: 'var(--gv-radius-md)',
                    background: 'var(--gv-bg-surface-subtle)',
                    borderLeft: `3px solid ${item.severity === 'critical' ? 'var(--gv-status-danger)' : 'var(--gv-color-energy-amber)'}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span style={{ fontFamily: 'var(--gv-font-mono)', fontWeight: 700, fontSize: '0.78rem', color: 'var(--gv-color-grid-blue)' }}>
                        {item.entityId}
                      </span>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gv-text-primary)' }}>
                        {item.entityName}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--gv-text-muted)', marginTop: '0.15rem' }}>
                      {item.anomalyType} • Deviation: <strong>{item.deviationPercent > 0 ? `+${item.deviationPercent}%` : `${item.deviationPercent}%`}</strong>
                    </div>
                  </div>
                  <StatusBadge status={item.status} showIcon={false} />
                </div>
              ))}
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '0.75rem', marginTop: '0.75rem' }}>
            <Link
              to="/anomalies"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.78rem',
                fontWeight: 700,
                color: 'var(--gv-status-danger)',
                textDecoration: 'none',
              }}
            >
              <span>Investigate All Anomalies</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>

        {/* Customer Segmentation Snapshot */}
        <div className="gv-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <Users size={18} color="var(--gv-color-smart-teal)" />
                <h3 className="gv-heading-2">Customer Demand Distribution</h3>
              </div>
              <span className="gv-badge gv-badge-neutral">3 Sectors</span>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', height: '10px', borderRadius: '5px', overflow: 'hidden', marginBottom: '0.45rem' }}>
                {segments.map((seg) => (
                  <div key={seg.id} style={{ width: `${seg.sharePercentage}%`, background: seg.color }} />
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--gv-text-muted)' }}>
                {segments.map((seg) => (
                  <span key={seg.id} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: seg.color }} />
                    {seg.name.split(' ')[0]} ({seg.sharePercentage}%)
                  </span>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem', fontSize: '0.78rem' }}>
              {segments.map((s) => (
                <div key={s.id} style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--gv-text-secondary)', padding: '0.35rem 0', borderBottom: '1px solid var(--gv-border-subtle)' }}>
                  <span>{s.name} ({s.entityCount.toLocaleString()} meters)</span>
                  <strong style={{ fontFamily: 'var(--gv-font-mono)', color: 'var(--gv-text-primary)' }}>{s.demandMwh} MWh</strong>
                </div>
              ))}
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '0.75rem', marginTop: '0.75rem' }}>
            <Link
              to="/customers"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.78rem',
                fontWeight: 700,
                color: 'var(--gv-color-smart-teal)',
                textDecoration: 'none',
              }}
            >
              <span>Explore Customer Profiles & Tariffs</span>
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </section>

      {/* 4. Strategic Business Insights Preview */}
      <section className="gv-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <Lightbulb size={18} color="var(--gv-color-smart-teal)" />
            <h3 className="gv-heading-2">Executive Takeaways & Optimization</h3>
          </div>
          <Link
            to="/insights"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.35rem',
              fontSize: '0.78rem',
              fontWeight: 700,
              color: 'var(--gv-color-grid-blue)',
              textDecoration: 'none',
            }}
          >
            <span>View All Insights ({insights.length})</span>
            <ArrowRight size={14} />
          </Link>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
          {primaryInsights.map((ins) => (
            <div
              key={ins.id}
              style={{
                padding: '0.85rem 1rem',
                borderRadius: 'var(--gv-radius-md)',
                background: 'var(--gv-bg-surface-subtle)',
                border: '1px solid var(--gv-border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--gv-color-grid-blue)', textTransform: 'uppercase' }}>
                  {ins.category.replace('_', ' ')}
                </span>
                <StatusBadge status={ins.urgency} label={`${ins.urgency} Priority`} />
              </div>
              <h4 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--gv-text-primary)', marginBottom: '0.25rem' }}>
                {ins.title}
              </h4>
              <p style={{ fontSize: '0.78rem', color: 'var(--gv-text-secondary)', lineHeight: 1.4, marginBottom: '0.5rem' }}>
                {ins.description}
              </p>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 600 }}>
                <span style={{ color: 'var(--gv-color-grid-blue)' }}>{ins.impactMetric}</span>
                <span style={{ color: 'var(--gv-color-smart-teal)' }}>{ins.potentialValue}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};
