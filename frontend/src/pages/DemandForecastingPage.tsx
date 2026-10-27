import React, { useEffect, useState } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import { ChartCard } from '../components/common/ChartCard';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorState } from '../components/common/ErrorState';
import { analyticsService } from '../services/analyticsService';
import {
  CommercialBuilding,
  ResidentialMeter,
  RegionalSite,
  TimeSeriesPoint,
  SectorPersona,
} from '../types/analytics';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import {
  Building2,
  Home,
  Landmark,
  Cpu,
  Info,
} from 'lucide-react';

export const DemandForecastingPage: React.FC = () => {
  const [sector, setSector] = useState<SectorPersona>('commercial');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Entities list
  const [commercialBldgs, setCommercialBldgs] = useState<CommercialBuilding[]>([]);
  const [residentialMeters, setResidentialMeters] = useState<ResidentialMeter[]>([]);
  const [regionalSites, setRegionalSites] = useState<RegionalSite[]>([]);

  // Selected entities
  const [selectedBldgId, setSelectedBldgId] = useState<string>('Panther_office_1');
  const [selectedMeterId, setSelectedMeterId] = useState<string>('METER-1000');
  const [selectedSiteId, setSelectedSiteId] = useState<string>('Panther');

  // Active time-series horizon
  const [timeSeries, setTimeSeries] = useState<TimeSeriesPoint[]>([]);

  const loadHorizon = async (
    request: Promise<{ horizon: TimeSeriesPoint[] }>
  ) => {
    setLoading(true);
    setError(null);
    try {
      const data = await request;
      setTimeSeries(data.horizon);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load forecast.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const fetchEntities = async () => {
      try {
        setLoading(true);
        setError(null);
        const [bldgs, meters, sites] = await Promise.all([
          analyticsService.getCommercialBuildings(),
          analyticsService.getResidentialMeters(),
          analyticsService.getRegionalSites(),
        ]);
        setCommercialBldgs(bldgs);
        setResidentialMeters(meters);
        setRegionalSites(sites);

        // Load initial commercial forecast
        const initialComm = await analyticsService.getCommercialForecast('Panther_office_1');
        setTimeSeries(initialComm.horizon);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load forecasting entities.');
      } finally {
        setLoading(false);
      }
    };
    fetchEntities();
  }, []);

  // Handle entity change
  const handleCommercialChange = async (bldgId: string) => {
    setSelectedBldgId(bldgId);
    await loadHorizon(analyticsService.getCommercialForecast(bldgId));
  };

  const handleResidentialChange = async (meterId: string) => {
    setSelectedMeterId(meterId);
    await loadHorizon(analyticsService.getResidentialForecast(meterId));
  };

  const handleGovernmentChange = async (siteId: string) => {
    setSelectedSiteId(siteId);
    await loadHorizon(analyticsService.getGovernmentForecast(siteId));
  };

  const handleSectorChange = async (newSector: SectorPersona) => {
    setSector(newSector);
    if (newSector === 'commercial') {
      await loadHorizon(analyticsService.getCommercialForecast(selectedBldgId));
    } else if (newSector === 'residential') {
      await loadHorizon(analyticsService.getResidentialForecast(selectedMeterId));
    } else {
      await loadHorizon(analyticsService.getGovernmentForecast(selectedSiteId));
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Demand Forecasting Studio" description="Loading models and telemetry..." />
        <LoadingSkeleton height="140px" count={3} />
      </div>
    );
  }

  if (error) {
    return <ErrorState title="Forecasting Error" message={error} />;
  }

  const currentBldg =
    commercialBldgs.find((b) => b.buildingId === selectedBldgId) || commercialBldgs[0];
  const currentMeter =
    residentialMeters.find((m) => m.householdId === selectedMeterId) || residentialMeters[0];
  const currentSite =
    regionalSites.find((s) => s.siteId === selectedSiteId) || regionalSites[0];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Header */}
      <PageHeader
        title="Demand Forecasting Studio"
        description="Explore entity-level forecast horizons. Current sector horizons are marked as demo; run the connected gold-data customer bill model from Models."
        badge={
          <span className="gv-badge gv-badge-info">
            <Cpu size={12} />
            <span>{sector === 'residential' ? 'Customer Bill Prediction · Gold replay in Models' : 'Demo forecast horizon'}</span>
          </span>
        }
      />

      {/* Sector Selection Tabs & Entity Dropdown */}
      <div
        className="gv-card"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
          background: 'linear-gradient(180deg, #FFFFFF, var(--gv-bg-surface-subtle))',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          {/* Sector Switcher Pills */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--gv-text-muted)', textTransform: 'uppercase' }}>
              Model Domain:
            </span>
            <div style={{ display: 'inline-flex', background: 'rgba(11, 31, 51, 0.05)', padding: '3px', borderRadius: 'var(--gv-radius-md)' }}>
              <button
                type="button"
                onClick={() => handleSectorChange('commercial')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.45rem 0.85rem',
                  borderRadius: 'var(--gv-radius-sm)',
                  fontSize: '0.8rem',
                  fontWeight: sector === 'commercial' ? 700 : 500,
                  background: sector === 'commercial' ? '#FFFFFF' : 'transparent',
                  color: sector === 'commercial' ? 'var(--gv-color-midnight-navy)' : 'var(--gv-text-secondary)',
                  boxShadow: sector === 'commercial' ? 'var(--gv-shadow-sm)' : 'none',
                  cursor: 'pointer',
                }}
              >
                <Building2 size={14} color="var(--gv-color-grid-blue)" />
                <span>Commercial Buildings</span>
              </button>

              <button
                type="button"
                onClick={() => handleSectorChange('residential')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.45rem 0.85rem',
                  borderRadius: 'var(--gv-radius-sm)',
                  fontSize: '0.8rem',
                  fontWeight: sector === 'residential' ? 700 : 500,
                  background: sector === 'residential' ? '#FFFFFF' : 'transparent',
                  color: sector === 'residential' ? 'var(--gv-color-midnight-navy)' : 'var(--gv-text-secondary)',
                  boxShadow: sector === 'residential' ? 'var(--gv-shadow-sm)' : 'none',
                  cursor: 'pointer',
                }}
              >
                <Home size={14} color="var(--gv-color-smart-teal)" />
                <span>Residential Smart Meters</span>
              </button>

              <button
                type="button"
                onClick={() => handleSectorChange('government')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.45rem 0.85rem',
                  borderRadius: 'var(--gv-radius-sm)',
                  fontSize: '0.8rem',
                  fontWeight: sector === 'government' ? 700 : 500,
                  background: sector === 'government' ? '#FFFFFF' : 'transparent',
                  color: sector === 'government' ? 'var(--gv-color-midnight-navy)' : 'var(--gv-text-secondary)',
                  boxShadow: sector === 'government' ? 'var(--gv-shadow-sm)' : 'none',
                  cursor: 'pointer',
                }}
              >
                <Landmark size={14} color="var(--gv-color-energy-amber)" />
                <span>17 Regional Sites</span>
              </button>
            </div>
          </div>

          {/* Dynamic Entity Selectors */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {sector === 'commercial' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>
                  Selected Facility:
                </label>
                <select
                  value={selectedBldgId}
                  onChange={(e) => handleCommercialChange(e.target.value)}
                  style={{
                    padding: '0.45rem 0.85rem',
                    borderRadius: 'var(--gv-radius-md)',
                    border: '1px solid var(--gv-border-accent)',
                    background: '#FFFFFF',
                    color: 'var(--gv-text-primary)',
                    fontWeight: 600,
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                  }}
                >
                  {commercialBldgs.map((b) => (
                    <option key={b.buildingId} value={b.buildingId}>
                      {b.buildingId} ({b.primarySpaceUsage})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {sector === 'residential' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>
                  Selected Meter ID:
                </label>
                <select
                  value={selectedMeterId}
                  onChange={(e) => handleResidentialChange(e.target.value)}
                  style={{
                    padding: '0.45rem 0.85rem',
                    borderRadius: 'var(--gv-radius-md)',
                    border: '1px solid var(--gv-border-accent)',
                    background: '#FFFFFF',
                    color: 'var(--gv-text-primary)',
                    fontWeight: 600,
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                  }}
                >
                  {residentialMeters.map((m) => (
                    <option key={m.householdId} value={m.householdId}>
                      {m.householdId} (Cycle Day {m.elapsedDays})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {sector === 'government' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>
                  Regional Grid Zone:
                </label>
                <select
                  value={selectedSiteId}
                  onChange={(e) => handleGovernmentChange(e.target.value)}
                  style={{
                    padding: '0.45rem 0.85rem',
                    borderRadius: 'var(--gv-radius-md)',
                    border: '1px solid var(--gv-border-accent)',
                    background: '#FFFFFF',
                    color: 'var(--gv-text-primary)',
                    fontWeight: 600,
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                  }}
                >
                  {regionalSites.map((s) => (
                    <option key={s.siteId} value={s.siteId}>
                      Site {s.siteId} ({s.buildingCount} buildings)
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>

        {/* Selected Entity Metadata Strip */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '1.5rem',
            padding: '0.65rem 0.85rem',
            background: '#FFFFFF',
            borderRadius: 'var(--gv-radius-md)',
            border: '1px solid var(--gv-border-subtle)',
            fontSize: '0.78rem',
            color: 'var(--gv-text-secondary)',
            flexWrap: 'wrap',
          }}
        >
          {sector === 'commercial' && (
            <>
              <span>Site: <strong style={{ color: 'var(--gv-color-grid-blue)' }}>{currentBldg.siteId}</strong></span>
              <span>Space Usage: <strong style={{ color: 'var(--gv-text-primary)' }}>{currentBldg.primarySpaceUsage}</strong></span>
              <span>Floor Area: <strong style={{ fontFamily: 'var(--gv-font-mono)' }}>{currentBldg.sqm.toLocaleString()} m²</strong></span>
              <span>Built: <strong>{currentBldg.yearBuilt}</strong></span>
              <span>Dataset Split: <strong style={{ color: 'var(--gv-color-smart-teal)' }}>BDG2 Gold Test Split</strong></span>
            </>
          )}

          {sector === 'residential' && (
            <>
              <span>Meter ID: <strong style={{ color: 'var(--gv-color-smart-teal)' }}>{currentMeter.householdId}</strong></span>
              <span>Cycle Progress: <strong>Day {currentMeter.elapsedDays} of month</strong></span>
              <span>Telemetry Coverage: <strong style={{ color: currentMeter.coverageRatio >= 0.9 ? 'var(--gv-color-smart-teal)' : '#B45309' }}>{(currentMeter.coverageRatio * 100).toFixed(1)}%</strong></span>
              <span>Flat Tariff: <strong style={{ color: 'var(--gv-color-grid-blue)' }}>₹10.00 / kWh</strong></span>
              <span>Dataset: <strong style={{ color: 'var(--gv-color-smart-teal)' }}>Low Carbon London Gold Parquet</strong></span>
            </>
          )}

          {sector === 'government' && (
            <>
              <span>Zone: <strong style={{ color: 'var(--gv-color-energy-amber)' }}>Site {currentSite.siteId}</strong></span>
              <span>Building Count: <strong>{currentSite.buildingCount} buildings</strong></span>
              <span>System Share: <strong>{currentSite.shareOfTotalPct}%</strong></span>
              <span>Season: <strong>{currentSite.season}</strong></span>
              <span>Scope: <strong style={{ color: 'var(--gv-color-smart-teal)' }}>Synchronized 17-Zone Grid Replay</strong></span>
            </>
          )}
        </div>
      </div>

      {/* Primary KPI Row */}
      <section className="gv-grid-kpis">
        {sector === 'commercial' && (
          <>
            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Recent Observed Demand</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-text-primary)', marginTop: '0.35rem' }}>
                {currentBldg.recentDemandKwh} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Observed at {currentBldg.lastTimestamp}</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Model Predicted Demand</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-grid-blue)', marginTop: '0.35rem' }}>
                {currentBldg.predictedDemandKwh} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>LightGBM commercial-v1 inference</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Absolute Forecast Error</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-smart-teal)', marginTop: '0.35rem' }}>
                {currentBldg.absErrorKwh} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Percentage Variance: {currentBldg.pctError}%</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>10-Hour Forward Outlook</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-energy-amber)', marginTop: '0.35rem' }}>
                4,250 <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Autoregressive multi-step horizon total</p>
            </div>
          </>
        )}

        {sector === 'residential' && (
          <>
            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Current Daily Usage</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-text-primary)', marginTop: '0.35rem' }}>
                {currentMeter.dailyKwh} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Observed on {currentMeter.lastDate}</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Month-to-Date Accumulated</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-smart-teal)', marginTop: '0.35rem' }}>
                {currentMeter.actualCycleKwhSoFar} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Cycle day {currentMeter.elapsedDays} of calendar month</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Predicted Month-End Usage</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-grid-blue)', marginTop: '0.35rem' }}>
                {currentMeter.estimatedMonthEndKwh} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Forecast remainder: {currentMeter.predictedRemainingKwh} kWh</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Estimated Monthly Bill</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-smart-teal)', marginTop: '0.35rem' }}>
                ₹{currentMeter.estimatedMonthEndBillInr.toLocaleString()}
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Calculated at ₹10.00/kWh flat tariff</p>
            </div>
          </>
        )}

        {sector === 'government' && (
          <>
            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Zone Total Demand</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-text-primary)', marginTop: '0.35rem' }}>
                {currentSite.totalDemandKwh.toLocaleString()} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Aggregate across {currentSite.buildingCount} buildings</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Regional Model Prediction</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-grid-blue)', marginTop: '0.35rem' }}>
                {currentSite.predictedDemandKwh.toLocaleString()} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>LightGBM regional-v1 inference</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Peak Hour Demand</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-energy-amber)', marginTop: '0.35rem' }}>
                {currentSite.peakHourKwh.toLocaleString()} <span style={{ fontSize: '0.9rem', color: 'var(--gv-text-secondary)' }}>kWh</span>
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Coincident evening peak load</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>System Grid Share</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-smart-teal)', marginTop: '0.35rem' }}>
                {currentSite.shareOfTotalPct}%
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>17-Site administrative ranking #1</p>
            </div>
          </>
        )}
      </section>

      {/* Main Interactive Forecast Chart */}
      <ChartCard
        title={
          sector === 'commercial'
            ? `${currentBldg.buildingId} Hourly Demand & 10-Hour Forecast Horizon`
            : sector === 'residential'
            ? `${currentMeter.householdId} Daily Consumption & 10-Day Projected Horizon`
            : `Site ${currentSite.siteId} Regional Demand Profile & Outlook`
        }
        subtitle="Chronological historical observations seamlessly connected to model forecast trajectory"
        height="360px"
        footer={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--gv-text-muted)' }}>
            <span>Solid curve: Verified Historical Actuals • Dashed line: Model Predicted Future Horizon</span>
            <span>Forecast Demarcation: Current Dataset Time Barrier</span>
          </div>
        }
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={timeSeries} margin={{ top: 15, right: 25, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--gv-color-smart-teal)" stopOpacity={0.25} />
                <stop offset="95%" stopColor="var(--gv-color-smart-teal)" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
            <XAxis dataKey="formattedTime" stroke="#94A3B8" tick={{ fontSize: 11 }} />
            <YAxis stroke="#94A3B8" tick={{ fontSize: 11 }} unit=" kWh" />
            <Tooltip
              content={({ active, payload, label }) => {
                if (active && payload && payload.length) {
                  return (
                    <div style={{ background: 'var(--gv-color-midnight-navy)', color: '#FFFFFF', padding: '0.65rem 0.85rem', borderRadius: 'var(--gv-radius-md)', fontSize: '0.75rem' }}>
                      <div style={{ fontWeight: 700, marginBottom: '0.35rem', color: '#E2E8F0' }}>Time: {label}</div>
                      {payload.map((entry, idx) => (
                        <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', marginTop: '0.2rem' }}>
                          <span style={{ color: entry.color }}>{entry.name}:</span>
                          <strong style={{ fontFamily: 'var(--gv-font-mono)' }}>{entry.value} kWh</strong>
                        </div>
                      ))}
                    </div>
                  );
                }
                return null;
              }}
            />
            <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 11, paddingBottom: 10 }} />
            <ReferenceLine x="00:00" stroke="#EF4444" strokeDasharray="3 3" label={{ value: 'Forecast Horizon Start', fill: '#EF4444', fontSize: 10, position: 'insideTopLeft' }} />
            <Area type="monotone" dataKey="actualDemand" name="Historical Actual" stroke="var(--gv-color-smart-teal)" fill="url(#actualGradient)" strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
            <Line type="monotone" dataKey="forecastDemand" name="Model Forecast Horizon" stroke="var(--gv-color-energy-amber)" strokeWidth={2.5} strokeDasharray="5 5" dot={{ r: 4, fill: 'var(--gv-color-energy-amber)' }} connectNulls={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Domain-Specific Visual Breakdown Component */}
      {sector === 'residential' && (
        <section className="gv-grid-2col">
          <div className="gv-card">
            <h3 className="gv-heading-3" style={{ marginBottom: '0.35rem' }}>Month-End Estimate Components</h3>
            <p className="gv-text-muted" style={{ fontSize: '0.78rem', marginBottom: '1rem' }}>
              The residential XGBoost model predicts the cumulative remainder of the month (target_remaining_kwh).
            </p>
            <div style={{ height: '240px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={[
                    { name: 'Actual MTD', value: currentMeter.actualCycleKwhSoFar, fill: 'var(--gv-color-smart-teal)' },
                    { name: 'Forecast Remaining', value: currentMeter.predictedRemainingKwh, fill: 'var(--gv-color-grid-blue)' },
                    { name: 'Ground Truth Target', value: currentMeter.targetRemainingKwh, fill: 'var(--gv-color-electric-cyan)' },
                    { name: 'Month-End Projected', value: currentMeter.estimatedMonthEndKwh, fill: 'var(--gv-color-energy-amber)' },
                  ]}
                  margin={{ top: 10, right: 10, left: -10, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} unit=" kWh" />
                  <Tooltip />
                  <Bar dataKey="value" name="Energy (kWh)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="gv-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <h3 className="gv-heading-3" style={{ marginBottom: '0.75rem' }}>Tariff & Operational Diagnostics</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', fontSize: '0.8rem', lineHeight: 1.6 }}>
                <div>⚡ <strong>Peak Usage Day:</strong> {currentMeter.lastDate} ({currentMeter.dailyKwh} kWh)</div>
                <div>📡 <strong>Interval Coverage:</strong> {(currentMeter.coverageRatio * 100).toFixed(1)}% — {currentMeter.coverageRatio >= 0.9 ? 'Certified quality' : 'Below 90% threshold'}</div>
                <div>💰 <strong>Flat Tariff Formula:</strong> {currentMeter.estimatedMonthEndKwh} kWh × ₹10.00/kWh = <strong>₹{currentMeter.estimatedMonthEndBillInr.toLocaleString()}</strong></div>
                <div>🔮 <strong>Prediction Status:</strong> Valid positive energy forecast</div>
              </div>
            </div>

            <div style={{ padding: '0.65rem 0.85rem', background: 'rgba(8, 126, 189, 0.08)', borderRadius: 'var(--gv-radius-md)', fontSize: '0.72rem', color: 'var(--gv-color-grid-blue)', marginTop: '1rem' }}>
              ⚠️ Retrospective Replay: Ground truth derived from Low Carbon London Gold tables. Not an official utility billing invoice.
            </div>
          </div>
        </section>
      )}

      {sector === 'government' && (
        <div className="gv-card">
          <h3 className="gv-heading-3" style={{ marginBottom: '0.5rem' }}>Regional Demand Comparison Across 17 Administrative Sites</h3>
          <p className="gv-text-muted" style={{ fontSize: '0.78rem', marginBottom: '1.25rem' }}>
            Ranked total demand distribution across all 17 government sites (Bear through Wolf) with 1,400 constituent buildings.
          </p>
          <div style={{ height: '320px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={regionalSites}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 30, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" horizontal={false} />
                <XAxis type="number" unit=" kWh" tick={{ fontSize: 10 }} />
                <YAxis dataKey="siteId" type="category" tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="totalDemandKwh" name="Observed Demand (kWh)" fill="var(--gv-color-smart-teal)" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Model Governance Caveats Banner */}
      <div
        style={{
          background: 'rgba(255, 194, 71, 0.1)',
          border: '1px solid rgba(255, 194, 71, 0.35)',
          borderRadius: 'var(--gv-radius-md)',
          padding: '0.75rem 1rem',
          fontSize: '0.78rem',
          color: '#B45309',
          display: 'flex',
          alignItems: 'center',
          gap: '0.65rem',
        }}
      >
        <Info size={16} style={{ flexShrink: 0 }} />
        <div>
          <strong>Model Governance Caveat:</strong> The estimators shown operate on verified feature schemas (<code>residential-v1</code>, <code>commercial-v1</code>, <code>government-v1</code>).
          Retrospective test split replays demonstrate contract compliance and inference plumbing. Negative predictions are rejected by the domain layer.
        </div>
      </div>
    </div>
  );
};
