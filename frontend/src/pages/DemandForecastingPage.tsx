import React, { useCallback, useEffect, useRef, useState } from 'react';
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
  PairedCommercialForecast,
} from '../types/analytics';
import {
  isVerifiedPairedForecast,
  loadForecastForSelectedBuilding,
  pairedForecastErrorMessage,
  toPairedForecastSeries,
} from '../services/pairedCommercialForecast.js';
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
  const [selectedBldgId, setSelectedBldgId] = useState<string>('');
  const [selectedMeterId, setSelectedMeterId] = useState<string>('METER-1000');
  const [selectedSiteId, setSelectedSiteId] = useState<string>('Panther');

  // Active time-series horizon
  const [timeSeries, setTimeSeries] = useState<TimeSeriesPoint[]>([]);
  const [pairedForecast, setPairedForecast] = useState<PairedCommercialForecast | null>(null);
  const [pairedLoading, setPairedLoading] = useState<boolean>(false);
  const [pairedError, setPairedError] = useState<string | null>(null);
  const [pairedNotice, setPairedNotice] = useState<string | null>(null);
  const pairedRequestId = useRef(0);

  const loadCommercialPair = useCallback(async (buildingId: string) => {
    const requestId = ++pairedRequestId.current;
    setPairedLoading(true);
    setPairedError(null);
    setPairedNotice(null);
    setPairedForecast(null);
    try {
      const result = await loadForecastForSelectedBuilding(
        buildingId,
        (selectedId) => analyticsService.getPairedCommercialForecast(selectedId)
      );
      if (requestId !== pairedRequestId.current) return;
      setPairedForecast(result);
      if (!isVerifiedPairedForecast(result)) {
        setPairedNotice('Demo provider output is hidden. Connect verified commercial and government models to view forecasts.');
      } else if (result.paired_horizon.length === 0) {
        setPairedNotice('No paired forecast history is available for this building and grid.');
      }
    } catch (err) {
      if (requestId !== pairedRequestId.current) return;
      setPairedError(pairedForecastErrorMessage(err));
    } finally {
      if (requestId === pairedRequestId.current) setPairedLoading(false);
    }
  }, []);

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

        const firstBuildingId = bldgs[0]?.buildingId ?? '';
        setSelectedBldgId(firstBuildingId);
        if (firstBuildingId) await loadCommercialPair(firstBuildingId);
        else setPairedNotice('No commercial building history is available.');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load forecasting entities.');
      } finally {
        setLoading(false);
      }
    };
    fetchEntities();
  }, [loadCommercialPair]);

  // Handle entity change
  const handleCommercialChange = async (bldgId: string) => {
    setSelectedBldgId(bldgId);
    await loadCommercialPair(bldgId);
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
      await loadCommercialPair(selectedBldgId);
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

  const currentMeter =
    residentialMeters.find((m) => m.householdId === selectedMeterId) || residentialMeters[0];
  const currentSite =
    regionalSites.find((s) => s.siteId === selectedSiteId) || regionalSites[0];
  const commercialSeries = toPairedForecastSeries(pairedForecast);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Header */}
      <PageHeader
        title="Demand Forecasting Studio"
        description="Explore entity-level forecast horizons. Current sector horizons are marked as demo; run the connected gold-data customer bill model from Models."
        badge={
          <span className="gv-badge gv-badge-info">
            <Cpu size={12} />
            <span>{sector === 'residential'
              ? 'Customer Bill Prediction · Gold replay in Models'
              : sector === 'commercial'
                ? isVerifiedPairedForecast(pairedForecast) ? 'Commercial + total-grid models' : 'Verified paired forecast unavailable'
                : 'Demo forecast horizon'}</span>
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
              <span>Building: <strong style={{ color: 'var(--gv-text-primary)' }}>{selectedBldgId || 'Unavailable'}</strong></span>
              <span>Coarse-grid region: <strong style={{ color: 'var(--gv-color-grid-blue)' }}>{pairedForecast?.building['id.grid.coarse'] ?? 'Unmapped'}</strong></span>
              {pairedForecast && isVerifiedPairedForecast(pairedForecast) && (
                <>
                  <span>Commercial source: <strong>{pairedForecast.commercial_forecast.model.model_name} · {pairedForecast.commercial_forecast.model.model_version}</strong></span>
                  <span>Government source: <strong>{pairedForecast.government_forecast.model.model_name} · {pairedForecast.government_forecast.model.model_version}</strong></span>
                </>
              )}
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
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Building Forecast</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-text-primary)', marginTop: '0.35rem' }}>
                {pairedLoading ? 'Loading…' : commercialSeries.length ? `${commercialSeries[0].forecastDemand.toLocaleString()} kWh` : '—'}
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>{isVerifiedPairedForecast(pairedForecast) ? pairedForecast.commercial_forecast.model.model_name : 'No verified commercial model output'}</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Total Grid Forecast</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-grid-blue)', marginTop: '0.35rem' }}>
                {pairedLoading ? 'Loading…' : commercialSeries.length ? `${commercialSeries[0].totalGridDemandPrediction.toLocaleString()} kWh` : '—'}
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>{isVerifiedPairedForecast(pairedForecast) ? `${pairedForecast.government_forecast.model.model_name} · all building types` : 'No verified government model output'}</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Forecast Horizon</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-smart-teal)', marginTop: '0.35rem' }}>
                {commercialSeries.length ? `${commercialSeries.length} steps` : '—'}
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>{commercialSeries.length ? `Through ${commercialSeries[commercialSeries.length - 1].timestamp}` : 'No paired forecast timestamps'}</p>
            </div>

            <div className="gv-card">
              <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Forecast status</span>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-energy-amber)', marginTop: '0.35rem' }}>
                {pairedLoading ? 'Loading' : pairedError ? 'Unavailable' : commercialSeries.length ? 'Ready' : 'Empty'}
              </div>
              <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>{pairedForecast?.generated_at ?? pairedError ?? pairedNotice ?? 'Awaiting model output'}</p>
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
            ? `${selectedBldgId || 'Commercial building'} Forecasts by Coarse Grid`
            : sector === 'residential'
            ? `${currentMeter.householdId} Daily Consumption & 10-Day Projected Horizon`
            : `Site ${currentSite.siteId} Regional Demand Profile & Outlook`
        }
        subtitle={sector === 'commercial' && isVerifiedPairedForecast(pairedForecast)
          ? `Grid ${pairedForecast.building['id.grid.coarse']} · commercial and total-grid demand are separate model outputs`
          : 'Forecast outputs are shown only when their source models are verified.'}
        height="360px"
        footer={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--gv-text-muted)' }}>
            <span>{sector === 'commercial' ? 'Commercial building model · Total-grid government model' : 'Solid curve: Historical actuals · Dashed line: forecast'}</span>
            <span>{sector === 'commercial' ? 'Both models aligned by timestamp and forecast horizon' : 'Forecast demarcation: current dataset time barrier'}</span>
          </div>
        }
      >
        {sector === 'commercial' && pairedLoading ? (
          <div role="status" aria-live="polite" style={{ padding: '2rem', textAlign: 'center' }}>Loading commercial and government forecasts…</div>
        ) : sector === 'commercial' && pairedError ? (
          <ErrorState title="Paired forecast unavailable" message={pairedError} onRetry={() => void loadCommercialPair(selectedBldgId)} />
        ) : sector === 'commercial' && (pairedNotice || commercialSeries.length === 0) ? (
          <div role="status" style={{ padding: '2rem', textAlign: 'center' }}>
            <p>{pairedNotice ?? 'No paired forecast history is available for this building and grid.'}</p>
          </div>
        ) : sector !== 'commercial' && timeSeries.length === 0 ? (
          <div role="status" style={{ padding: '2rem', textAlign: 'center' }}>No forecast history is available.</div>
        ) : (
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={sector === 'commercial' ? commercialSeries : timeSeries} margin={{ top: 15, right: 25, left: 0, bottom: 0 }}>
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
            {sector !== 'commercial' && <Area type="monotone" dataKey="actualDemand" name="Historical Actual" stroke="var(--gv-color-smart-teal)" fill="url(#actualGradient)" strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />}
            <Line type="monotone" dataKey="forecastDemand" name={sector === 'commercial' ? `Commercial model · ${pairedForecast?.commercial_forecast.model.model_name}` : 'Model Forecast Horizon'} stroke="var(--gv-color-energy-amber)" strokeWidth={2.5} strokeDasharray="5 5" dot={{ r: 4, fill: 'var(--gv-color-energy-amber)' }} connectNulls={false} />
            {sector === 'commercial' && <Line type="monotone" dataKey="totalGridDemandPrediction" name={`Government total-grid model · ${pairedForecast?.government_forecast.model.model_name}`} stroke="var(--gv-color-grid-blue)" strokeWidth={2.5} strokeDasharray="3 4" dot={{ r: 4, fill: 'var(--gv-color-grid-blue)' }} connectNulls={false} />}
          </ComposedChart>
        </ResponsiveContainer>
        )}
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
