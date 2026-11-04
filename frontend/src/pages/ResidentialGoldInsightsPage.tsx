import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart3,
  Database,
  Home,
  RefreshCw,
  Target,
  TrendingUp,
} from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { CommonMetricCard } from '../components/common';
import { usePersona } from '../context';
import { modelService } from '../services/modelService';
import {
  CustomerBillPrediction,
  CustomerBillRecord,
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
  const { energyUnit, activeEntity, setActiveEntity } = usePersona();
  const [timeRange, setTimeRange] = useState<HistoryRange>('ALL');
  const [history, setHistory] = useState<ResidentialGoldHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [residentialObjectIds, setResidentialObjectIds] = useState<string[]>([]);
  const [residentialObjectIdsLoaded, setResidentialObjectIdsLoaded] = useState(false);
  const [selectedObjectId, setSelectedObjectId] = useState('');
  const [buildingIdInput, setBuildingIdInput] = useState('');
  const [buildingIdVerification, setBuildingIdVerification] = useState<{
    message: string;
    valid: boolean;
  } | null>(null);
  const [verifyingBuildingId, setVerifyingBuildingId] = useState(false);
  const [objectRecords, setObjectRecords] = useState<CustomerBillRecord[]>([]);
  const [objectPrediction, setObjectPrediction] = useState<CustomerBillPrediction | null>(null);
  const [objectLoading, setObjectLoading] = useState(false);
  const [objectError, setObjectError] = useState<string | null>(null);
  const verifiedObjectIds = useRef(new Set<string>());

  useEffect(() => {
    let cancelled = false;
    modelService.getCustomerRecords(200, 0).then((page) => {
      if (cancelled) return;
      const ids = Array.from(
        new Set([
          ...page.items.map((record) => record.entityId),
          ...verifiedObjectIds.current,
        ])
      );
      setResidentialObjectIds(ids);
      const initialId = ids.includes(activeEntity) ? activeEntity : (ids[0] ?? '');
      setSelectedObjectId(initialId);
      setBuildingIdInput(initialId);
      if (initialId && initialId !== activeEntity) setActiveEntity(initialId);
    }).catch((loadError) => {
      if (!cancelled) {
        const message = loadError instanceof Error
          ? loadError.message
          : 'Unable to load residential building IDs.';
        setObjectError(message);
        setError(message);
        setLoading(false);
      }
    }).finally(() => {
      if (!cancelled) setResidentialObjectIdsLoaded(true);
    });
    return () => { cancelled = true; };
  }, [view, activeEntity, setActiveEntity]);

  useEffect(() => {
    if (view !== 'dashboard' || !selectedObjectId) return;
    let cancelled = false;
    setObjectLoading(true);
    setObjectError(null);
    setObjectRecords([]);
    setObjectPrediction(null);
    const loadPrediction = async () => {
      try {
        const records: CustomerBillRecord[] = await modelService.getEntityMonths(selectedObjectId);
        const latestByMonth = new Map<string, CustomerBillRecord>();
        records.forEach((record) => {
          const current = latestByMonth.get(record.monthStart);
          if (!current || record.cutoffDay > current.cutoffDay) {
            latestByMonth.set(record.monthStart, record);
          }
        });
        const monthlyRecords = Array.from(latestByMonth.values()).sort((a, b) =>
          a.monthStart.localeCompare(b.monthStart)
        );
        const latest = monthlyRecords[monthlyRecords.length - 1];
        if (!latest) throw new Error('No model records are available for this building ID.');
        if (!cancelled) setObjectRecords(monthlyRecords);
        const prediction = await modelService.predictCustomerBill(
          selectedObjectId,
          latest.monthStart,
          latest.cutoffDay
        );
        if (!cancelled) setObjectPrediction(prediction);
      } catch (loadError) {
        if (!cancelled) {
          setObjectError(loadError instanceof Error ? loadError.message : 'Unable to load this building prediction.');
        }
      } finally {
        if (!cancelled) setObjectLoading(false);
      }
    };
    void loadPrediction();
    return () => { cancelled = true; };
  }, [view, selectedObjectId]);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    setHistory(null);
    try {
      const result = await modelService.getResidentialGoldHistory(timeRange, activeEntity);
      setHistory(result);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load residential household insights.'
      );
    } finally {
      setLoading(false);
    }
  }, [activeEntity, timeRange]);

  const verifyBuildingId = async () => {
    const buildingId = buildingIdInput.trim();
    setBuildingIdVerification(null);
    if (!/^\d+$/.test(buildingId)) {
      setBuildingIdVerification({
        message: 'Enter a numeric building ID to verify it.',
        valid: false,
      });
      return;
    }

    setVerifyingBuildingId(true);
    try {
      const records = await modelService.getEntityMonths(buildingId);
      if (records.length === 0) {
        setBuildingIdVerification({
          message: `Building ${buildingId} has no Customer Gold records.`,
          valid: false,
        });
        return;
      }

      verifiedObjectIds.current.add(buildingId);
      setResidentialObjectIds((current) =>
        current.includes(buildingId) ? current : [...current, buildingId]
      );
      setSelectedObjectId(buildingId);
      setActiveEntity(buildingId);
      setBuildingIdVerification({
        message: `Building ${buildingId} verified in Customer Gold.`,
        valid: true,
      });
    } catch (verificationError) {
      setBuildingIdVerification({
        message:
          verificationError instanceof Error
            ? `Building ${buildingId} could not be verified: ${verificationError.message}`
            : `Building ${buildingId} could not be verified.`,
        valid: false,
      });
    } finally {
      setVerifyingBuildingId(false);
    }
  };

  useEffect(() => {
    if (
      view === 'history' &&
      residentialObjectIdsLoaded &&
      activeEntity
    ) {
      void loadHistory();
    }
  }, [view, loadHistory, residentialObjectIds, residentialObjectIdsLoaded, activeEntity]);

  const peakMonth = useMemo(() => {
    if (!history?.history.length) return null;
    return history.history.reduce((peak, point) =>
      point.averageActualKwh > peak.averageActualKwh ? point : peak
    );
  }, [history]);
  const selectedMonthlyAverage = useMemo(
    () =>
      objectRecords.length
        ? objectRecords.reduce((total, record) => total + record.actualMonthKwh, 0)
          / objectRecords.length
        : null,
    [objectRecords]
  );
  const selectedPeakMonth = useMemo(
    () =>
      objectRecords.reduce<CustomerBillRecord | null>(
        (peak, record) =>
          !peak || record.actualMonthKwh > peak.actualMonthKwh ? record : peak,
        null
      ),
    [objectRecords]
  );
  const residentialDashboardChartData = useMemo(() => {
    const predictionMonth = objectPrediction?.monthStart;
    const latestMonth = objectRecords[objectRecords.length - 1]?.monthStart;
    const usageForChart = (value: number) =>
      energyUnit === 'MWh' ? value / 1000 : value;
    return objectRecords.map((record) => ({
      month: formatMonth(record.monthStart),
      fullDate: formatMonth(record.monthStart),
      actualUsage:
        predictionMonth === latestMonth && record.monthStart === latestMonth
          ? null
          : usageForChart(record.actualMonthKwh),
      predictedUsage:
        objectPrediction?.monthStart === record.monthStart
          ? usageForChart(objectPrediction.predictedMonthEndKwh)
          : null,
    }));
  }, [energyUnit, objectPrediction, objectRecords]);

  const chartData = useMemo(
    () =>
      history?.history.map((point: ResidentialGoldHistoryPoint) => ({
        ...point,
        month: formatMonth(point.monthStart),
        monthOverMonthChangePercent: point.monthOverMonthChangePercent,
      })) ?? [],
    [history]
  );

  const unit = energyUnit === 'MWh' ? 'MWh' : 'kWh';

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
            Residential household insights
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
              ? 'Selected household energy use and model estimates.'
              : 'Historical monthly household consumption and estimated month-end use.'}
          </p>
        </div>
        {view === 'history' && (
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
        )}
      </header>

      <section
        aria-label="Residential building selection"
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '14px', padding: '1rem 1.2rem' }}
      >
        <div style={{ display: 'flex', alignItems: 'end', flexWrap: 'wrap', gap: '0.75rem' }}>
          <label style={{ display: 'grid', gap: '0.4rem', color: '#334155', fontSize: '0.88rem', fontWeight: 700 }}>
            Building ID
            <select
              aria-label="Residential building ID"
              value={activeEntity}
              onChange={(event) => {
                setSelectedObjectId(event.target.value);
                setBuildingIdInput(event.target.value);
                setBuildingIdVerification(null);
                setActiveEntity(event.target.value);
              }}
              disabled={!residentialObjectIds.length}
              style={{ border: '1px solid #CBD5E1', borderRadius: '8px', background: '#FFFFFF', color: '#0B1F33', padding: '0.55rem 0.7rem', minWidth: '150px' }}
            >
              {!residentialObjectIds.length && <option value="">Loading building IDs…</option>}
              {residentialObjectIds.map((objectId) => <option key={objectId} value={objectId}>{objectId}</option>)}
            </select>
          </label>
          <label style={{ display: 'grid', gap: '0.4rem', color: '#334155', fontSize: '0.88rem', fontWeight: 700 }}>
            Type an ID
            <input
              aria-label="Type residential building ID"
              inputMode="numeric"
              value={buildingIdInput}
              onChange={(event) => {
                setBuildingIdInput(event.target.value);
                setBuildingIdVerification(null);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void verifyBuildingId();
                }
              }}
              placeholder="e.g. 546503"
              style={{ border: '1px solid #CBD5E1', borderRadius: '8px', background: '#FFFFFF', color: '#0B1F33', padding: '0.55rem 0.7rem', minWidth: '150px' }}
            />
          </label>
          <button
            type="button"
            className="gv-button gv-button-secondary"
            onClick={() => void verifyBuildingId()}
            disabled={verifyingBuildingId || !buildingIdInput.trim()}
          >
            {verifyingBuildingId ? 'Verifying…' : 'Verify ID'}
          </button>
        </div>
        {buildingIdVerification && (
          <p
            role={buildingIdVerification.valid ? 'status' : 'alert'}
            style={{
              margin: 0,
              color: buildingIdVerification.valid ? '#047857' : '#991B1B',
              fontSize: '0.84rem',
            }}
          >
            {buildingIdVerification.message}
          </p>
        )}
      </section>

      {view === 'history' && history && (
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
          Historical monthly figures for {history.entityId ? `household ${history.entityId}` : `${history.entityCount.toLocaleString()} households`} from{' '}
          {formatMonth(history.startMonth)} to {formatMonth(history.endMonth)}. Actual use is
          shown alongside the month-end estimate based on usage recorded through day{' '}
          {history.dataset.cutoffDay} of each month. This is historical data, not live household
          usage.
        </div>
      )}

      {view === 'history' && error && (
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

      {view === 'dashboard' ? (
        <>
          {objectError && (
            <div role="alert" style={{ border: '1px solid #FECACA', background: '#FEF2F2', color: '#991B1B', borderRadius: '12px', padding: '0.85rem 1rem' }}>
              {objectError}
            </div>
          )}
          {objectLoading && !objectRecords.length ? (
            <div role="status" style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '16px', color: '#64748B', padding: '3rem 1rem', textAlign: 'center' }}>
              Loading selected household history and estimate…
            </div>
          ) : objectRecords.length > 0 ? (
            <>
              <section
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
                  gap: '1rem',
                }}
              >
                <CommonMetricCard
                  title="Average monthly use"
                  value={selectedMonthlyAverage === null ? '—' : formatUsage(selectedMonthlyAverage, unit)}
                  unit={selectedMonthlyAverage === null ? '' : unit}
                  icon={<BarChart3 size={22} color="#00A396" />}
                  iconBg="#E6F7F5"
                  subtext={`${selectedObjectId} · ${objectRecords.length} months of history`}
                />
                <CommonMetricCard
                  title="Highest monthly use"
                  value={selectedPeakMonth ? formatUsage(selectedPeakMonth.actualMonthKwh, unit) : '—'}
                  unit={selectedPeakMonth ? unit : ''}
                  icon={<TrendingUp size={22} color="#D97706" />}
                  iconBg="#FFF7ED"
                  subtext={selectedPeakMonth ? formatMonth(selectedPeakMonth.monthStart) : undefined}
                />
                <CommonMetricCard
                  title="Predicted month-end use"
                  value={objectPrediction ? formatUsage(objectPrediction.predictedMonthEndKwh, unit) : objectLoading ? '…' : '—'}
                  unit={objectPrediction ? unit : ''}
                  icon={<Target size={22} color="#7C3AED" />}
                  iconBg="#F5F3FF"
                  subtext={objectPrediction ? formatMonth(objectPrediction.monthStart) : 'Registered customer model'}
                />
                <CommonMetricCard
                  title="Predicted month-end bill"
                  value={objectPrediction ? `₹${objectPrediction.predictedBillInr.toLocaleString()}` : objectLoading ? '…' : '—'}
                  unit=""
                  icon={<Database size={22} color="#2563EB" />}
                  iconBg="#EFF6FF"
                  subtext={objectPrediction ? `Recorded bill: ₹${objectPrediction.actualBillInr.toLocaleString()}` : 'Based on selected household'}
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
                    Household consumption history &amp; prediction
                  </h2>
                  <p style={{ color: '#64748B', fontSize: '0.82rem', margin: '0.35rem 0 0' }}>
                    Recorded monthly usage followed by the model estimate for the latest month
                    {objectPrediction ? ` based on usage through day ${objectPrediction.cutoffDay}.` : '.'}
                  </p>
                </div>
                <div style={{ height: '360px', width: '100%' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={residentialDashboardChartData} margin={{ top: 10, right: 20, left: 8, bottom: 8 }}>
                      <CartesianGrid stroke="#F1F5F9" strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="month"
                        tick={{ fontSize: 11, fill: '#64748B' }}
                        axisLine={{ stroke: '#E2E8F0' }}
                        tickLine={false}
                      />
                      <YAxis
                        width={72}
                        tick={{ fontSize: 11, fill: '#64748B' }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(value: number) => value.toLocaleString()}
                        label={{
                          value: `Consumption (${unit})`,
                          angle: -90,
                          position: 'insideLeft',
                          fill: '#64748B',
                          fontSize: 11,
                        }}
                      />
                      <Tooltip
                        formatter={(value, name) => [
                          `${Number(value).toLocaleString()} ${unit}`,
                          name,
                        ]}
                      />
                      <Legend wrapperStyle={{ fontSize: '0.78rem' }} />
                      <Line
                        type="monotone"
                        dataKey="actualUsage"
                        name="Recorded consumption"
                        stroke="#00A396"
                        strokeWidth={2.7}
                        dot={{ r: 3, fill: '#FFFFFF', strokeWidth: 2 }}
                        activeDot={{ r: 5 }}
                        connectNulls={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="predictedUsage"
                        name="Model-predicted month-end"
                        stroke="#7C3AED"
                        strokeWidth={2.5}
                        strokeDasharray="6 4"
                        dot={{ r: 5, fill: '#7C3AED' }}
                        activeDot={{ r: 6 }}
                        connectNulls={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </section>
            </>
          ) : !objectError ? (
            <div role="status" style={{ background: '#FFFFFF', border: '1px solid #E2E8F0', borderRadius: '16px', color: '#64748B', padding: '3rem 1rem', textAlign: 'center' }}>
              {objectLoading ? 'Loading selected household history…' : 'No historical data is available for this household.'}
            </div>
          ) : null}
        </>
      ) : loading && !history ? (
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
          Loading household history…
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
                  title="Average monthly consumption"
                  value={formatUsage(history.averageMonthlyKwhPerEntity, unit)}
                  unit={unit}
                  icon={<BarChart3 size={22} color="#00A396" />}
                  iconBg="#E6F7F5"
                  subtext={`${history.monthsReturned} months shown`}
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
                  title={history.entityCount === 1 ? 'Household included' : 'Households included'}
                  value={history.entityCount.toLocaleString()}
                  unit=""
                  icon={<Database size={22} color="#2563EB" />}
                  iconBg="#EFF6FF"
                  subtext={`${history.monthsReturned} months of household history`}
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
                {history.entityId ? 'Month-over-month change in household use' : 'Month-over-month change in average use'}
              </h2>
              <p style={{ color: '#64748B', fontSize: '0.82rem', margin: '0.35rem 0 0' }}>
                Percentage change in actual household consumption versus the previous calendar month.
              </p>
            </div>
            <div style={{ height: '260px', width: '100%' }}>
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
                    width={72}
                    tick={{ fontSize: 11, fill: '#64748B' }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(value: number) => `${value.toFixed(0)}%`}
                    label={{
                      value: 'Change (%)',
                      angle: -90,
                      position: 'insideLeft',
                      fill: '#64748B',
                      fontSize: 11,
                    }}
                  />
                  <Tooltip
                    formatter={(value) => [
                      value === null || value === undefined
                        ? 'No prior-month comparison'
                        : `${Number(value).toFixed(1)}%`,
                      'Change vs prior month',
                    ]}
                  />
                  <ReferenceLine y={0} stroke="#94A3B8" strokeDasharray="4 4" />
                  <Line
                    type="monotone"
                    dataKey="monthOverMonthChangePercent"
                    name="Change vs prior month"
                    stroke="#2563EB"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: '#FFFFFF', strokeWidth: 2 }}
                    activeDot={{ r: 5 }}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p style={{ color: '#64748B', fontSize: '0.76rem', margin: '0.25rem 0 0' }}>
              {history.entityId
                ? `This compares recorded monthly use for household ${history.entityId}.`
                : 'Monthly household coverage can vary; this compares monthly averages, not a fixed set of matched households.'}
            </p>
          </section>
        </>
      ) : null}
    </main>
  );
};
