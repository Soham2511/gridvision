import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  Database,
  Home,
  RefreshCw,
  Target,
  TrendingUp,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { CommonMetricCard } from '../components/common';
import { usePersona } from '../context';
import { modelService } from '../services/modelService';
import {
  ResidentialGoldHistory,
  ResidentialGoldHistoryPoint,
} from '../types/analytics';

type HistoryRange = ResidentialGoldHistory['timeRange'];
type PageView = 'dashboard' | 'history';

const ranges: Array<{ value: HistoryRange; label: string }> = [
  { value: '3M', label: '3 months' },
  { value: '6M', label: '6 months' },
  { value: '1Y', label: '1 year' },
  { value: 'ALL', label: 'All data' },
];
const buildingTypeColors = ['#00A396', '#7C3AED', '#2563EB', '#D97706'];

const formatUsage = (value: number, unit: string): string => {
  if (unit === 'MWh') {
    const mwh = value / 1000;
    return mwh < 1 ? mwh.toFixed(3) : mwh.toFixed(2);
  }
  return Math.round(value).toLocaleString();
};

const formatMonth = (month: string): string =>
  new Date(`${month}T00:00:00`).toLocaleDateString(undefined, {
    month: 'short',
    year: 'numeric',
  });

export const ResidentialGoldInsightsPage: React.FC<{ view?: PageView }> = ({
  view = 'history',
}) => {
  const { energyUnit } = usePersona();
  const [timeRange, setTimeRange] = useState<HistoryRange>('ALL');
  const [history, setHistory] = useState<ResidentialGoldHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await modelService.getResidentialGoldHistory(timeRange);
      setHistory(result);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load residential gold-dataset insights.'
      );
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const peakMonth = useMemo(() => {
    if (!history?.history.length) return null;
    return history.history.reduce((peak, point) =>
      point.averageActualKwh > peak.averageActualKwh ? point : peak
    );
  }, [history]);

  const chartData = useMemo(
    () =>
      history?.history.map((point: ResidentialGoldHistoryPoint) => ({
        ...point,
        month: formatMonth(point.monthStart),
        cohortProjectionKwh: point.averageProjectionKwh * point.entityCount,
      })) ?? [],
    [history]
  );

  const unit = energyUnit === 'MWh' ? 'MWh' : 'kWh';
  const modelMae = history?.model.testMetrics.mae_kwh;
  const features = history?.model.features ?? [];

  return (
    <main
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem',
        maxWidth: '1300px',
        margin: '0 auto',
        width: '100%',
      }}
    >
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.55rem',
              color: '#00A396',
              fontSize: '0.76rem',
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              marginBottom: '0.45rem',
            }}
          >
            <Home size={16} />
            Residential gold dataset
          </div>
          <h1
            style={{
              fontSize: '2.1rem',
              fontWeight: 800,
              color: '#0B1F33',
              margin: '0 0 0.4rem',
              letterSpacing: '-0.025em',
            }}
          >
            {view === 'dashboard' ? 'Residential Energy Dashboard' : 'Historical Energy Insights'}
          </h1>
          <p style={{ fontSize: '0.92rem', color: '#64748B', margin: 0 }}>
            {view === 'dashboard'
              ? 'Gold-dataset trends, sample-cohort usage, and model projections.'
              : 'Monthly household usage and model projections from the trained gold-data cohort.'}
          </p>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem' }}>
          {ranges.map((range) => (
            <button
              key={range.value}
              type="button"
              onClick={() => setTimeRange(range.value)}
              aria-pressed={timeRange === range.value}
              style={{
                border: `1px solid ${timeRange === range.value ? '#00A396' : '#E2E8F0'}`,
                borderRadius: '9px',
                background: timeRange === range.value ? '#E6F7F5' : '#FFFFFF',
                color: timeRange === range.value ? '#007F75' : '#64748B',
                cursor: 'pointer',
                padding: '0.55rem 0.8rem',
                fontSize: '0.78rem',
                fontWeight: 700,
              }}
            >
              {range.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => void loadHistory()}
            disabled={loading}
            aria-label="Refresh residential historical insights"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              border: '1px solid #E2E8F0',
              borderRadius: '9px',
              background: '#FFFFFF',
              color: '#334155',
              cursor: loading ? 'wait' : 'pointer',
              padding: '0.55rem 0.8rem',
              fontSize: '0.78rem',
              fontWeight: 700,
            }}
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>
      </header>

      {history && (
        <div
          role="note"
          style={{
            border: '1px solid #BFDBFE',
            background: '#EFF6FF',
            borderRadius: '12px',
            color: '#1E3A5F',
            fontSize: '0.84rem',
            lineHeight: 1.55,
            padding: '0.85rem 1rem',
          }}
        >
          This is a retrospective profile of {history.entityCount.toLocaleString()} modeled
          customer entities in the gold sample, covering {formatMonth(history.startMonth)} to{' '}
          {formatMonth(history.endMonth)}. It is not live household telemetry. Each month uses
          the latest available cutoff snapshot (day {history.dataset.cutoffDay}).
        </div>
      )}

      {error && (
        <div
          role="alert"
          style={{
            background: '#FEF2F2',
            border: '1px solid #FECACA',
            borderRadius: '12px',
            color: '#991B1B',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            padding: '0.9rem 1rem',
          }}
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void loadHistory()}
            style={{
              border: '1px solid #FCA5A5',
              borderRadius: '8px',
              background: '#FFFFFF',
              color: '#991B1B',
              cursor: 'pointer',
              padding: '0.45rem 0.7rem',
              fontWeight: 700,
            }}
          >
            Retry
          </button>
        </div>
      )}

      {loading && !history ? (
        <div
          role="status"
          style={{
            background: '#FFFFFF',
            border: '1px solid #E2E8F0',
            borderRadius: '16px',
            color: '#64748B',
            padding: '3rem 1rem',
            textAlign: 'center',
          }}
        >
          Loading gold-dataset history…
        </div>
      ) : history ? (
        <>
          <section
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
              gap: '1rem',
            }}
          >
            <CommonMetricCard
              title="Average monthly use per entity"
              value={formatUsage(history.averageMonthlyKwhPerEntity, unit)}
              unit={unit}
              icon={<BarChart3 size={22} color="#00A396" />}
              iconBg="#E6F7F5"
              subtext={`${history.monthsReturned} gold months`}
            />
            <CommonMetricCard
              title="Highest average-use month"
              value={peakMonth ? formatUsage(peakMonth.averageActualKwh, unit) : '—'}
              unit={unit}
              icon={<TrendingUp size={22} color="#D97706" />}
              iconBg="#FFF7ED"
              subtext={peakMonth ? formatMonth(peakMonth.monthStart) : undefined}
            />
            <CommonMetricCard
              title="Model holdout MAE"
              value={
                modelMae === undefined
                  ? '—'
                  : formatUsage(modelMae, unit)
              }
              unit={modelMae === undefined ? '' : unit}
              icon={<Target size={22} color="#7C3AED" />}
              iconBg="#F5F3FF"
              subtext="Training test split"
            />
            <CommonMetricCard
              title="Gold sample entities"
              value={history.entityCount.toLocaleString()}
              unit=""
              icon={<Database size={22} color="#2563EB" />}
              iconBg="#EFF6FF"
              subtext={`${history.dataset.sourceRows.toLocaleString()} cutoff snapshots`}
            />
          </section>

          <section
            style={{
              background: '#FFFFFF',
              border: '1px solid #E2E8F0',
              borderRadius: '16px',
              boxShadow: '0 4px 20px -2px rgba(11, 31, 51, 0.03)',
              padding: '1.4rem 1.5rem 1rem',
            }}
          >
            <div style={{ marginBottom: '1rem' }}>
              <h2 style={{ color: '#0B1F33', fontSize: '1.1rem', margin: 0 }}>
                Monthly use per modeled household
              </h2>
              <p style={{ color: '#64748B', fontSize: '0.82rem', margin: '0.35rem 0 0' }}>
                Mean actual month-end energy compared with the projection available at the final cutoff.
              </p>
            </div>
            <div style={{ height: '340px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 20, left: 8, bottom: 8 }}>
                  <CartesianGrid stroke="#F1F5F9" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 11, fill: '#64748B' }}
                    axisLine={{ stroke: '#E2E8F0' }}
                    tickLine={false}
                  />
                  <YAxis
                    width={68}
                    tick={{ fontSize: 11, fill: '#64748B' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(value: number) => formatUsage(value, unit)}
                    label={{
                      value: `${unit} per entity`,
                      angle: -90,
                      position: 'insideLeft',
                      fill: '#64748B',
                      fontSize: 11,
                    }}
                  />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="averageActualKwh"
                    name="Actual month-end use"
                    stroke="#00A396"
                    strokeWidth={2.7}
                    dot={{ r: 3, fill: '#FFFFFF', strokeWidth: 2 }}
                    activeDot={{ r: 5 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="averageProjectionKwh"
                    name="Cutoff-day projection"
                    stroke="#7C3AED"
                    strokeWidth={2.2}
                    strokeDasharray="6 4"
                    dot={{ r: 3, fill: '#FFFFFF', strokeWidth: 2 }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '1.2rem',
                color: '#64748B',
                fontSize: '0.78rem',
                marginTop: '0.25rem',
              }}
            >
              <span><strong style={{ color: '#00A396' }}>●</strong> Actual use</span>
              <span><strong style={{ color: '#7C3AED' }}>●</strong> Model projection</span>
              <span>Values are monthly means per entity, not cohort totals.</span>
            </div>
          </section>

          <section
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
              gap: '1rem',
            }}
          >
            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #E2E8F0',
                borderRadius: '16px',
                padding: '1.25rem 1.25rem 0.75rem',
              }}
            >
              <h2 style={{ color: '#0B1F33', fontSize: '1rem', margin: '0 0 0.3rem' }}>
                Sample-cohort monthly consumption
              </h2>
              <p style={{ color: '#64748B', fontSize: '0.78rem', margin: '0 0 0.65rem' }}>
                Total actual energy vs projected energy across the included entities.
              </p>
              <div style={{ height: '280px', width: '100%' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 8, left: 4, bottom: 8 }}>
                    <CartesianGrid stroke="#F1F5F9" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#64748B' }} />
                    <YAxis
                      width={64}
                      tick={{ fontSize: 10, fill: '#64748B' }}
                      tickFormatter={(value: number) => formatUsage(value, unit)}
                    />
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: '0.72rem' }} />
                    <Bar
                      dataKey="cohortActualKwh"
                      name="Actual cohort use"
                      fill="#00A396"
                      radius={[4, 4, 0, 0]}
                    />
                    <Bar
                      dataKey="cohortProjectionKwh"
                      name="Projected cohort use"
                      fill="#8B5CF6"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div
              style={{
                background: '#FFFFFF',
                border: '1px solid #E2E8F0',
                borderRadius: '16px',
                padding: '1.25rem 1.25rem 0.75rem',
              }}
            >
              <h2 style={{ color: '#0B1F33', fontSize: '1rem', margin: '0 0 0.3rem' }}>
                Household types in the sample
              </h2>
              <p style={{ color: '#64748B', fontSize: '0.78rem', margin: '0 0 0.65rem' }}>
                Entity mix from the latest gold-data month.
              </p>
              <div style={{ height: '280px', width: '100%' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={history.buildingTypeBreakdown}
                      dataKey="entityCount"
                      nameKey="buildingType"
                      innerRadius="55%"
                      outerRadius="80%"
                      paddingAngle={3}
                      label={({ name, percent }) =>
                        `${String(name).replace(/-/g, ' ')} ${((percent ?? 0) * 100).toFixed(0)}%`
                      }
                    >
                      {history.buildingTypeBreakdown.map((group, index) => (
                        <Cell
                          key={group.buildingType}
                          fill={buildingTypeColors[index % buildingTypeColors.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend wrapperStyle={{ fontSize: '0.72rem' }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          <section
            style={{
              background: '#FFFFFF',
              border: '1px solid #E2E8F0',
              borderRadius: '16px',
              padding: '1.25rem 1.5rem 0.8rem',
            }}
          >
            <h2 style={{ color: '#0B1F33', fontSize: '1rem', margin: '0 0 0.3rem' }}>
              Monthly model projection error
            </h2>
            <p style={{ color: '#64748B', fontSize: '0.78rem', margin: '0 0 0.65rem' }}>
              Mean absolute difference between cutoff-day projection and actual month-end use per entity.
            </p>
            <div style={{ height: '260px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                  <CartesianGrid stroke="#F1F5F9" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#64748B' }} />
                  <YAxis
                    width={68}
                    tick={{ fontSize: 10, fill: '#64748B' }}
                    tickFormatter={(value: number) => formatUsage(value, unit)}
                  />
                  <Tooltip />
                  <Bar
                    dataKey="averageAbsoluteErrorKwh"
                    name="Mean absolute error"
                    fill="#D97706"
                    radius={[5, 5, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section
            style={{
              background: '#FFFFFF',
              border: '1px solid #E2E8F0',
              borderRadius: '16px',
              padding: '1.35rem 1.5rem',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                flexWrap: 'wrap',
                gap: '1rem',
              }}
            >
              <div>
                <h2 style={{ color: '#0B1F33', fontSize: '1.05rem', margin: 0 }}>
                  Model and training
                </h2>
                <p style={{ color: '#64748B', fontSize: '0.82rem', margin: '0.4rem 0 0' }}>
                  {history.model.description}
                </p>
              </div>
              <span
                style={{
                  background: '#F5F3FF',
                  borderRadius: '999px',
                  color: '#6D28D9',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  padding: '0.4rem 0.7rem',
                }}
              >
                {history.model.name} · v{history.model.version}
              </span>
            </div>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '0.65rem 1.4rem',
                color: '#475569',
                fontSize: '0.82rem',
                marginTop: '1rem',
              }}
            >
              <span>Test RMSE: {history.model.testMetrics.rmse_kwh?.toFixed(1) ?? '—'} kWh</span>
              <span>Test R²: {history.model.testMetrics.r2?.toFixed(4) ?? '—'}</span>
              <span>Dataset quality: {history.dataset.qualityPassed ? 'Passed' : 'Not confirmed'}</span>
              <span>Dataset version: {history.dataset.version}</span>
            </div>
            <details style={{ marginTop: '1rem' }}>
              <summary
                style={{
                  color: '#2563EB',
                  cursor: 'pointer',
                  fontSize: '0.82rem',
                  fontWeight: 700,
                }}
              >
                View {features.length} training features
              </summary>
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '0.45rem',
                  marginTop: '0.8rem',
                }}
              >
                {features.map((feature) => (
                  <span
                    key={feature}
                    style={{
                      background: '#F8FAFC',
                      border: '1px solid #E2E8F0',
                      borderRadius: '7px',
                      color: '#475569',
                      fontFamily: 'monospace',
                      fontSize: '0.72rem',
                      padding: '0.35rem 0.5rem',
                    }}
                  >
                    {feature}
                  </span>
                ))}
              </div>
            </details>
          </section>

          <section
            style={{
              background: '#FFFFFF',
              border: '1px solid #E2E8F0',
              borderRadius: '16px',
              padding: '1.2rem 1.5rem',
            }}
          >
            <h2 style={{ color: '#0B1F33', fontSize: '1.05rem', margin: '0 0 0.9rem' }}>
              Sample household mix
            </h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem' }}>
              {history.buildingTypeBreakdown.map((group) => (
                <div
                  key={group.buildingType}
                  style={{
                    background: '#F8FAFC',
                    border: '1px solid #E2E8F0',
                    borderRadius: '10px',
                    color: '#334155',
                    fontSize: '0.84rem',
                    padding: '0.7rem 0.85rem',
                  }}
                >
                  <strong>{group.entityCount.toLocaleString()}</strong>{' '}
                  {group.buildingType.replace(/-/g, ' ')}
                </div>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
};
