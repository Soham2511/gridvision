import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Download, MapPin, Play, RefreshCw, ShieldCheck } from 'lucide-react';
import { usePersona } from '../context';
import {
  AnomalyAnalysisRequest,
  AnomalyEntity,
  AnomalyEvent,
  AnomalyModel,
  AnomalyRun,
  AnomalyRunResult,
  AnomalyWindow,
  anomalyService,
} from '../services/anomalyService';
import { AnomalyMap } from '../components/anomaly/AnomalyMap';
import { EvaluationMetrics } from '../components/anomaly/EvaluationMetrics';

type Tab = 'monitor' | 'results';

const panelStyle: React.CSSProperties = {
  background: 'var(--gv-bg-surface)',
  border: '1px solid var(--gv-border-subtle)',
  borderRadius: 'var(--gv-radius-lg)',
  padding: '1.1rem',
  boxShadow: 'var(--gv-shadow-sm)',
};

const buttonStyle: React.CSSProperties = {
  border: '1px solid var(--gv-border-medium)',
  borderRadius: 'var(--gv-radius-md)',
  background: 'var(--gv-bg-surface)',
  color: 'var(--gv-text-primary)',
  padding: '0.55rem 0.8rem',
  fontWeight: 650,
  cursor: 'pointer',
};

const inputStyle: React.CSSProperties = {
  padding: '0.55rem 0.65rem',
  border: '1px solid var(--gv-border-medium)',
  borderRadius: 'var(--gv-radius-md)',
  color: 'var(--gv-text-primary)',
  background: 'var(--gv-bg-surface)',
};

const scopeColor: Record<AnomalyEvent['event_scope'], string> = {
  SINGLE_CUSTOMER: '#EF4444',
  LOCAL_AREA: '#F59E0B',
  MULTI_AREA: '#087EBD',
};

const formatDuration = (seconds: number): string => {
  const hours = seconds / 3600;
  return hours < 1 ? `${Math.max(1, Math.round(seconds / 60))} min` : `${hours.toFixed(1)} hr`;
};

const formatCustomers = (count: number): string =>
  `${count.toLocaleString()} customer${count === 1 ? '' : 's'}`;

const formatDate = (value: string): string => {
  const explicitZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  const sourceParts = value.match(
    /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?$/,
  );
  const parsed = explicitZone
    ? new Date(value)
    : sourceParts
      ? new Date(Date.UTC(
          Number(sourceParts[1]),
          Number(sourceParts[2]) - 1,
          Number(sourceParts[3]),
          Number(sourceParts[4] ?? 0),
          Number(sourceParts[5] ?? 0),
          Number(sourceParts[6] ?? 0),
        ))
      : new Date(value);
  if (!Number.isFinite(parsed.getTime())) return 'Date unavailable';
  const dateTimeOptions: Intl.DateTimeFormatOptions = explicitZone
    ? {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
          timeZoneName: 'short',
      }
    : {
        dateStyle: 'medium',
        ...(sourceParts && !sourceParts[4] ? {} : { timeStyle: 'short' }),
        ...(sourceParts ? { timeZone: 'UTC' } : {}),
      };
  const formatter = new Intl.DateTimeFormat(undefined, dateTimeOptions);
  const formatted = formatter.format(parsed);
  return sourceParts && !explicitZone && sourceParts[4]
    ? `${formatted} (source time; timezone unspecified)`
    : formatted;
};

const activeEntityId = (entity: string): number | null => {
  const match = entity.match(/^\d+$/) ?? entity.match(/(\d+)$/);
  return match ? Number(match[1]) : null;
};

export const AnomalyDetectionPage: React.FC = () => {
  const { currentPersona, activeEntity } = usePersona();
  const persona = currentPersona ?? 'household';
  const isGovernment = persona === 'government';
  const [tab, setTab] = useState<Tab>('monitor');
  const [model, setModel] = useState<AnomalyModel | null>(null);
  const [entities, setEntities] = useState<AnomalyEntity[]>([]);
  const [runs, setRuns] = useState<AnomalyRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [run, setRun] = useState<AnomalyRunResult | null>(null);
  const [runLoading, setRunLoading] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState('');
  const [anomalyTypeFilter, setAnomalyTypeFilter] = useState('all');
  const [scopeFilter, setScopeFilter] = useState('all');
  const [minimumScore, setMinimumScore] = useState('0');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [customerIdsInput, setCustomerIdsInput] = useState('');
  const [spatialRadiusKm, setSpatialRadiusKm] = useState('5');
  const [h3Resolution, setH3Resolution] = useState('8');
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mapError, setMapError] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const runRequestSequence = useRef(0);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [modelResponse, runResponse] = await Promise.all([
        anomalyService.getModel(),
        anomalyService.getRuns(50),
      ]);
      setModel(modelResponse);
      setRuns(runResponse.items);
      const defaultDate = modelResponse.dataset.startDate?.slice(0, 10) ?? '';
      setStartDate((current) => current || defaultDate);
      setEndDate((current) => current || defaultDate);
      setSelectedRunId((current) => (
        runResponse.items.some((item) => item.analysis_id === current)
          ? current
          : runResponse.items.find((item) => item.status === 'completed')?.analysis_id ?? ''
      ));
      if (persona === 'government') {
        try {
          const entityResponse = await anomalyService.getEntities(0, 10_000);
          setEntities(entityResponse.items);
          setMapError(
            entityResponse.total > entityResponse.items.length
              ? `Map loaded ${entityResponse.items.length.toLocaleString()} of ${entityResponse.total.toLocaleString()} customer locations.`
              : null,
          );
        } catch (entityError) {
          setMapError(entityError instanceof Error ? entityError.message : 'Customer locations could not be loaded.');
        }
      } else {
        setEntities([]);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load anomaly model data.');
    } finally {
      setLoading(false);
    }
  }, [persona]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectedRunStatus = runs.find(
    (item) => item.analysis_id === selectedRunId,
  )?.status;
  const hasActiveRuns = runs.some(
    (item) => item.status === 'queued' || item.status === 'running',
  );

  const loadRun = useCallback(async (runId: string) => {
    const requestSequence = ++runRequestSequence.current;
    setRun(null);
    if (!runId) {
      setRunLoading(false);
      return;
    }
    setRunLoading(true);
    setError(null);
    try {
      const detail = await anomalyService.getRun(runId);
      if (requestSequence !== runRequestSequence.current) return;
      setRun(detail.status === 'completed' ? {
        run_id: detail.analysis_id,
        status: detail.status,
        request: detail.request,
        metadata: detail.metadata ?? {},
        metrics: detail.metrics ?? {},
        events: detail.events ?? [],
        anomaly_windows: detail.anomaly_windows ?? [],
        affected_customer_ids: detail.affected_customer_ids ?? [],
      } : null);
    } catch (loadError) {
      if (requestSequence !== runRequestSequence.current) return;
      setError(loadError instanceof Error ? loadError.message : 'Unable to load application results.');
    } finally {
      if (requestSequence === runRequestSequence.current) setRunLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRun(selectedRunId);
  }, [loadRun, selectedRunId, selectedRunStatus]);

  useEffect(() => {
    if (!hasActiveRuns) return undefined;
    const intervalId = window.setInterval(() => {
      void anomalyService.getRuns(50).then((response) => {
        setRuns(response.items);
        setSelectedRunId((current) => (
          response.items.some((item) => item.analysis_id === current)
            ? current
            : response.items.find((item) => item.status === 'completed')?.analysis_id ?? ''
        ));
        if (!response.items.some(
          (item) => item.status === 'queued' || item.status === 'running',
        )) {
          setError(null);
        }
      }).catch((pollError: unknown) => {
        setError(
          pollError instanceof Error
            ? pollError.message
            : 'Unable to refresh the persisted application run status.',
        );
      });
    }, 2000);
    return () => window.clearInterval(intervalId);
  }, [hasActiveRuns]);

  const windows = useMemo(() => run?.anomaly_windows ?? [], [run?.anomaly_windows]);
  const events = useMemo(
    () =>
      (run?.events ?? []).map((event) => {
        if (event.spatial_clusters?.length) return event;
        const records = windows.filter(
          (window) =>
            window.event_id === event.event_id &&
            window.event_spatial_cluster_id &&
            Number.isFinite(window.latitude) &&
            Number.isFinite(window.longitude),
        );
        const clusterIds = [
          ...new Set(
            records
              .map((window) => window.event_spatial_cluster_id)
              .filter((clusterId): clusterId is string => Boolean(clusterId)),
          ),
        ];
        const clusters = clusterIds.map((clusterId) => {
          const locations = new Map(
            records
              .filter((window) => window.event_spatial_cluster_id === clusterId)
              .map((window) => [
                window.customer_id,
                { latitude: window.latitude, longitude: window.longitude },
              ]),
          );
          const customerLocations = [...locations.entries()];
          const latitude = customerLocations.reduce(
            (sum, [, location]) => sum + location.latitude,
            0,
          ) / customerLocations.length;
          const longitude = customerLocations.reduce(
            (sum, [, location]) => sum + location.longitude,
            0,
          ) / customerLocations.length;
          const extent = Math.max(
            ...customerLocations.map(([, location]) => {
              const radians = Math.PI / 180;
              const latitudeDelta = (location.latitude - latitude) * radians;
              const longitudeDelta = (location.longitude - longitude) * radians;
              const haversine =
                Math.sin(latitudeDelta / 2) ** 2 +
                Math.cos(latitude * radians) *
                  Math.cos(location.latitude * radians) *
                  Math.sin(longitudeDelta / 2) ** 2;
              return 2 * 6371.0088 * Math.asin(Math.sqrt(haversine)) * 2;
            }),
            0,
          );
          return {
            cluster_id: clusterId,
            customer_ids: customerLocations.map(([customerId]) => customerId),
            latitude_center: latitude,
            longitude_center: longitude,
            spatial_extent_km: extent,
          };
        });
        return clusters.length ? { ...event, spatial_clusters: clusters } : event;
      }),
    [run?.events, windows],
  );
  const filteredEvents = useMemo(
    () =>
      events.filter((event) => {
        const typeMatches =
          anomalyTypeFilter === 'all' || event.anomaly_types.includes(anomalyTypeFilter);
        const scopeMatches = scopeFilter === 'all' || event.event_scope === scopeFilter;
        const scoreMatches = event.max_anomaly_score >= Number(minimumScore);
        return typeMatches && scopeMatches && scoreMatches;
      }),
    [anomalyTypeFilter, events, minimumScore, scopeFilter],
  );
  const selectedEvent =
    filteredEvents.find((event) => event.event_id === selectedEventId) ?? filteredEvents[0] ?? null;
  const anomalyTypes = useMemo(
    () => [...new Set(events.flatMap((event) => event.anomaly_types))].sort(),
    [events],
  );
  const selectRun = (runId: string) => {
    setSelectedRunId(runId);
    setSelectedEventId('');
    setRun(null);
    setError(null);
  };

  useEffect(() => {
    if (!filteredEvents.some((event) => event.event_id === selectedEventId)) {
      setSelectedEventId(filteredEvents[0]?.event_id ?? '');
    }
  }, [filteredEvents, selectedEventId]);

  const executeAnalysis = async () => {
    if (!startDate || !endDate) {
      setError('Choose both a start date and an end date.');
      return;
    }
    let customerIds: number[] | null = null;
    if (customerIdsInput.trim()) {
      const entries = customerIdsInput
        .split(',')
        .map((item) => item.trim());
      const parsed = entries.map(Number);
      if (!parsed.length || parsed.some((value) => !Number.isInteger(value) || value <= 0)) {
        setError('Enter one or more valid customer IDs, separated by commas.');
        return;
      }
      customerIds = [...new Set(parsed)];
    }
    if (!Number.isInteger(Number(h3Resolution)) || Number(h3Resolution) < 0 || Number(h3Resolution) > 15) {
      setError('H3 resolution must be an integer from 0 to 15.');
      return;
    }
    if (!Number.isFinite(Number(spatialRadiusKm)) || Number(spatialRadiusKm) <= 0 || Number(spatialRadiusKm) > 100) {
      setError('Spatial radius must be greater than 0 and no more than 100 km.');
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const request: AnomalyAnalysisRequest = {
        customer_ids: customerIds,
        start_date: startDate,
        end_date: endDate,
        h3_resolution: Number(h3Resolution),
        spatial_radius_km: Number(spatialRadiusKm),
        maximum_start_time_difference_minutes: 30,
        minimum_temporal_overlap: 0.25,
        maximum_interval_gap_minutes: 60,
      };
      const result = await anomalyService.runAnalysis(request, persona, activeEntity);
      setRun(result);
      setSelectedRunId(result.run_id);
      setSelectedEventId(result.events[0]?.event_id ?? '');
      const response = await anomalyService.getRuns(50);
      setRuns(response.items);
    } catch (analysisError) {
      setError(analysisError instanceof Error ? analysisError.message : 'Anomaly analysis failed.');
    } finally {
      setRunning(false);
    }
  };

  const download = async (runId: string, filename: string) => {
    setDownloadError(null);
    try {
      const blob = await anomalyService.downloadRunFile(runId, filename);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (downloadFailure) {
      setDownloadError(
        downloadFailure instanceof Error ? downloadFailure.message : `Unable to download ${filename}.`,
      );
    }
  };

  if (loading) {
    return <div role="status" style={panelStyle}>Loading saved anomaly model and application runs…</div>;
  }
  if (error && !model) {
    return <div role="alert" style={{ ...panelStyle, color: 'var(--gv-status-danger)' }}>{error}</div>;
  }

  const linkedEntityId = activeEntityId(activeEntity);
  const personaEvents = events.filter((event) => linkedEntityId !== null && event.customer_ids.includes(linkedEntityId));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
            <AlertTriangle size={21} color="var(--gv-status-warning)" />
            <h1 className="gv-heading-1" style={{ margin: 0 }}>
              {isGovernment ? 'Grid Anomaly Monitoring' : 'Anomaly Alerts'}
            </h1>
          </div>
          <p className="gv-text-subtle" style={{ marginTop: '0.35rem' }}>
            Saved-model anomaly detection, customer impact localization, and application results.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
          <span className={`gv-badge ${model?.status === 'configured' ? 'gv-badge-success' : 'gv-badge-danger'}`}>
            <ShieldCheck size={13} /> {model?.status === 'configured' ? model.selectedModel : 'Model unavailable'}
          </span>
          <button type="button" style={buttonStyle} onClick={() => void refresh()}>
            <RefreshCw size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} /> Refresh
          </button>
        </div>
      </header>

      {model?.sourceNotice && (
        <div role="status" style={{ ...panelStyle, borderColor: 'var(--gv-status-warning)', color: 'var(--gv-text-secondary)' }}>
          <strong>Source limitation:</strong> {model.sourceNotice} Detector outputs are not confirmed outages or live meter readings.
        </div>
      )}

      {model?.status !== 'configured' && (
        <div role="alert" style={{ ...panelStyle, color: 'var(--gv-status-danger)' }}>
          {model?.error ?? 'The saved anomaly model is not configured. No predicted results are shown.'}
        </div>
      )}
      {error && <div role="alert" style={{ ...panelStyle, color: 'var(--gv-status-danger)' }}>{error}</div>}

      {isGovernment ? (
        <>
          <nav aria-label="Anomaly monitoring sections" style={{ display: 'flex', gap: '0.5rem' }}>
            {(['monitor', 'results'] as const).map((value) => (
              <button
                type="button"
                key={value}
                onClick={() => setTab(value)}
                aria-pressed={tab === value}
                style={{
                  ...buttonStyle,
                  background: tab === value ? 'var(--gv-color-midnight-navy)' : 'var(--gv-bg-surface)',
                  color: tab === value ? '#fff' : 'var(--gv-text-primary)',
                }}
              >
                {value === 'monitor' ? 'Monitoring' : 'Application Results'}
              </button>
            ))}
          </nav>
          {tab === 'monitor' ? (
            <GovernmentMonitor
              model={model}
              entities={entities}
              events={filteredEvents}
              selectedEvent={selectedEvent}
              selectedEventId={selectedEventId}
              onSelectEvent={setSelectedEventId}
              anomalyTypes={anomalyTypes}
              anomalyTypeFilter={anomalyTypeFilter}
              setAnomalyTypeFilter={setAnomalyTypeFilter}
              scopeFilter={scopeFilter}
              setScopeFilter={setScopeFilter}
              minimumScore={minimumScore}
              setMinimumScore={setMinimumScore}
              runs={runs}
              selectedRunId={selectedRunId}
              run={run}
              runLoading={runLoading}
              setSelectedRunId={selectRun}
              startDate={startDate}
              setStartDate={setStartDate}
              endDate={endDate}
              setEndDate={setEndDate}
              customerIdsInput={customerIdsInput}
              setCustomerIdsInput={setCustomerIdsInput}
              spatialRadiusKm={spatialRadiusKm}
              setSpatialRadiusKm={setSpatialRadiusKm}
              h3Resolution={h3Resolution}
              setH3Resolution={setH3Resolution}
              executeAnalysis={executeAnalysis}
              running={running}
              mapError={mapError}
            />
          ) : (
            <ApplicationResults
              runs={runs}
              selectedRunId={selectedRunId}
              selectedRun={runs.find((item) => item.analysis_id === selectedRunId) ?? null}
              onSelectRun={selectRun}
              download={download}
              downloadError={downloadError}
            />
          )}
        </>
      ) : (
        <PersonaAlerts
          persona={persona}
          entity={activeEntity}
          entityId={linkedEntityId}
          events={personaEvents}
          windows={windows.filter((window) => window.customer_id === linkedEntityId)}
          model={model}
          runs={runs}
        />
      )}
    </div>
  );
};

interface GovernmentMonitorProps {
  model: AnomalyModel | null;
  entities: AnomalyEntity[];
  events: AnomalyEvent[];
  selectedEvent: AnomalyEvent | null;
  selectedEventId: string;
  onSelectEvent: (eventId: string) => void;
  anomalyTypes: string[];
  anomalyTypeFilter: string;
  setAnomalyTypeFilter: (value: string) => void;
  scopeFilter: string;
  setScopeFilter: (value: string) => void;
  minimumScore: string;
  setMinimumScore: (value: string) => void;
  runs: AnomalyRun[];
  selectedRunId: string;
  run: AnomalyRunResult | null;
  runLoading: boolean;
  setSelectedRunId: (value: string) => void;
  startDate: string;
  setStartDate: (value: string) => void;
  endDate: string;
  setEndDate: (value: string) => void;
  customerIdsInput: string;
  setCustomerIdsInput: (value: string) => void;
  spatialRadiusKm: string;
  setSpatialRadiusKm: (value: string) => void;
  h3Resolution: string;
  setH3Resolution: (value: string) => void;
  executeAnalysis: () => void;
  running: boolean;
  mapError: string | null;
}

const GovernmentMonitor: React.FC<GovernmentMonitorProps> = (props) => {
  const {
    model, entities, events, selectedEvent, selectedEventId, onSelectEvent,
    anomalyTypes, anomalyTypeFilter, setAnomalyTypeFilter, scopeFilter,
    setScopeFilter, minimumScore, setMinimumScore, runs, selectedRunId, setSelectedRunId,
    run, runLoading,
    startDate, setStartDate, endDate, setEndDate, customerIdsInput, setCustomerIdsInput,
    spatialRadiusKm, setSpatialRadiusKm, h3Resolution, setH3Resolution, executeAnalysis,
    running, mapError,
  } = props;
  return (
    <>
      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(155px, 1fr))', gap: '0.75rem' }}>
        <Metric label="Model status" value={model?.status ?? 'unknown'} />
        <Metric label="Application status" value={runLoading ? 'Loading…' : runs.find((item) => item.analysis_id === selectedRunId)?.status ?? 'No run selected'} />
        <Metric label="Source customers" value={model?.dataset.customers?.toLocaleString() ?? '—'} />
        <Metric label="Events in run" value={runLoading ? 'Loading…' : metricCount(run?.metrics.localized_event_count)} />
        <Metric label="Affected customers" value={runLoading ? 'Loading…' : metricCount(run?.metrics.affected_customer_count)} />
      </section>
      <p className="gv-text-subtle" style={{ fontSize: '0.78rem' }}>
        Application run created: {runs.find((item) => item.analysis_id === selectedRunId)?.created_at
          ? formatDate(runs.find((item) => item.analysis_id === selectedRunId)?.created_at ?? '')
          : '—'}
        {' · '}Source dataset period: {model?.dataset.startDate
          ? `${formatDate(model.dataset.startDate)} – ${model.dataset.endDate ? formatDate(model.dataset.endDate) : 'unknown'}`
          : 'not available'}
        {' · '}Selected analysis period: {run
          ? `${formatDate(run.request.start_date)} – ${formatDate(run.request.end_date)}`
          : '—'}
      </p>

      <section style={{ ...panelStyle, display: 'grid', gridTemplateColumns: 'minmax(0, 1.7fr) minmax(260px, 1fr)', gap: '1rem' }}>
        <div>
          <h2 className="gv-heading-2" style={{ marginTop: 0 }}>
            <MapPin size={17} style={{ verticalAlign: 'middle', marginRight: 5 }} /> Customer and event map
          </h2>
          <AnomalyMap
            entities={entities}
            events={events}
            selectedEventId={selectedEventId}
            onSelectEvent={onSelectEvent}
          />
          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', paddingTop: '0.6rem', color: 'var(--gv-text-muted)', fontSize: '0.75rem' }}>
            <span><i style={{ display: 'inline-block', width: 9, height: 9, background: '#94A3B8', borderRadius: '50%', marginRight: 5 }} />Normal customer</span>
            <span><i style={{ display: 'inline-block', width: 9, height: 9, background: '#EF4444', borderRadius: '50%', marginRight: 5 }} />Single-customer event</span>
            <span><i style={{ display: 'inline-block', width: 9, height: 9, background: '#F59E0B', borderRadius: '50%', marginRight: 5 }} />Local-area event</span>
            <span><i style={{ display: 'inline-block', width: 9, height: 9, background: '#087EBD', borderRadius: '50%', marginRight: 5 }} />Multi-area event</span>
            <span><i style={{ display: 'inline-block', width: 10, height: 10, border: '2px solid #087EBD', borderRadius: '50%', marginRight: 5 }} />Selected event customer</span>
            <span><i style={{ display: 'inline-block', width: 10, height: 10, border: '1px dashed #52616B', borderRadius: '50%', marginRight: 5 }} />Approximate cluster impact extent</span>
          </div>
          {mapError && <p role="status" className="gv-text-subtle">{mapError}</p>}
        </div>

        <div>
          <h2 className="gv-heading-2" style={{ marginTop: 0 }}>Analysis configuration</h2>
          <label style={fieldLabel}>Start date<input style={inputStyle} type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
          <label style={fieldLabel}>End date<input style={inputStyle} type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
          <label style={fieldLabel}>Customer IDs (blank = all)
            <input style={inputStyle} value={customerIdsInput} onChange={(event) => setCustomerIdsInput(event.target.value)} placeholder="e.g. 680232, 680233" />
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
            <label style={fieldLabel}>Spatial radius (km)<input style={inputStyle} type="number" min="0.1" max="100" step="0.5" value={spatialRadiusKm} onChange={(event) => setSpatialRadiusKm(event.target.value)} /></label>
            <label style={fieldLabel}>H3 resolution<input style={inputStyle} type="number" min="0" max="15" value={h3Resolution} onChange={(event) => setH3Resolution(event.target.value)} /></label>
          </div>
          <button type="button" onClick={executeAnalysis} disabled={running || model?.status !== 'configured'} style={{ ...buttonStyle, width: '100%', marginTop: '0.75rem', background: 'var(--gv-color-midnight-navy)', color: '#fff', opacity: running ? 0.7 : 1 }}>
            <Play size={14} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            {running ? 'Analysis running…' : 'Run anomaly analysis'}
          </button>
          <label style={{ ...fieldLabel, marginTop: '1rem' }}>Application run
            <select style={inputStyle} value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
              <option value="">Select a saved run</option>
              {runs.map((item) => <option key={item.analysis_id} value={item.analysis_id}>{formatDate(item.created_at)} — {item.status}</option>)}
            </select>
          </label>
        </div>
      </section>

      <section style={{ ...panelStyle, display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'end' }}>
        <label style={fieldLabel}>Anomaly type
          <select style={inputStyle} value={anomalyTypeFilter} onChange={(event) => setAnomalyTypeFilter(event.target.value)}>
            <option value="all">All types</option>
            {anomalyTypes.map((type) => <option key={type}>{type}</option>)}
          </select>
        </label>
        <label style={fieldLabel}>Event scope
          <select style={inputStyle} value={scopeFilter} onChange={(event) => setScopeFilter(event.target.value)}>
            <option value="all">All scopes</option>
            <option value="SINGLE_CUSTOMER">SINGLE_CUSTOMER</option>
            <option value="LOCAL_AREA">LOCAL_AREA</option>
            <option value="MULTI_AREA">MULTI_AREA</option>
          </select>
        </label>
        <label style={fieldLabel}>Minimum severity score
          <select style={inputStyle} value={minimumScore} onChange={(event) => setMinimumScore(event.target.value)}>
            <option value="0">All scores</option>
            <option value="0.5">0.50+</option>
            <option value="0.75">0.75+</option>
            <option value="0.9">0.90+</option>
          </select>
        </label>
      </section>

      <section style={panelStyle}>
        <h2 className="gv-heading-2" style={{ marginTop: 0 }}>Event timeline</h2>
        <div style={{ display: 'flex', gap: '0.6rem', overflowX: 'auto', overflowY: 'visible', padding: '0.4rem 0.15rem 0.8rem' }}>
          {events.length ? events.map((event) => (
            <button type="button" key={event.event_id} onClick={() => onSelectEvent(event.event_id)} aria-pressed={selectedEventId === event.event_id} style={{ ...buttonStyle, flex: '0 0 250px', whiteSpace: 'normal', textAlign: 'left', borderColor: scopeColor[event.event_scope], borderWidth: selectedEventId === event.event_id ? 2 : 1, background: selectedEventId === event.event_id ? '#F1F5F9' : '#fff' }}>
              <strong style={{ display: 'block', fontSize: '0.75rem' }}>{formatDate(event.event_start)} – {formatDate(event.event_end)}</strong>
              <span style={{ display: 'block', fontSize: '0.72rem', marginTop: 4 }}>{event.dominant_anomaly_type.replace(/_/g, ' ')} · {event.event_scope.replace(/_/g, ' ')}</span>
              <span style={{ display: 'block', fontSize: '0.7rem', marginTop: 4 }}>{formatCustomers(event.affected_customer_count)} · {formatDuration(event.event_duration)} · score {event.max_anomaly_score.toFixed(2)}</span>
            </button>
          )) : <span className="gv-text-subtle">No model-generated events are available for this run.</span>}
        </div>
      </section>

      <section style={{ ...panelStyle, display: 'grid', gridTemplateColumns: 'minmax(230px, 0.75fr) minmax(300px, 1.25fr)', gap: '1rem' }}>
        <div>
          <h2 className="gv-heading-2" style={{ marginTop: 0 }}>Event details</h2>
          {selectedEvent ? (
            <>
              <dl style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.55rem', fontSize: '0.82rem' }}>
                <dt>Event ID</dt><dd>{selectedEvent.event_id}</dd>
                <dt>Type</dt><dd>{selectedEvent.anomaly_types.join(', ')}</dd>
                <dt>Scope</dt><dd>{selectedEvent.event_scope}</dd>
                <dt>Severity score</dt><dd>{selectedEvent.max_anomaly_score.toFixed(3)}</dd>
                <dt>Duration</dt><dd>{formatDuration(selectedEvent.event_duration)}</dd>
                <dt>Customers affected</dt><dd>{selectedEvent.affected_customer_count}</dd>
                <dt>Spatial clusters</dt><dd>{selectedEvent.spatial_cluster_count}</dd>
                <dt>Cluster IDs</dt><dd>{selectedEvent.spatial_cluster_ids?.join(', ') || '—'}</dd>
                <dt>Geographic centre</dt><dd>{selectedEvent.latitude_center.toFixed(5)}, {selectedEvent.longitude_center.toFixed(5)}</dd>
                <dt>{selectedEvent.event_scope === 'MULTI_AREA' ? 'Overall event span' : 'Impact diameter'}</dt>
                <dd>{selectedEvent.spatial_extent_km.toFixed(2)} km</dd>
                <dt>Customers in event</dt><dd>{selectedEvent.customer_ids.length.toLocaleString()}</dd>
                <dt>Start</dt><dd>{formatDate(selectedEvent.event_start)}</dd>
                <dt>End</dt><dd>{formatDate(selectedEvent.event_end)}</dd>
                <dt>Probable cause</dt><dd>Model signature: {selectedEvent.dominant_anomaly_type.replace(/_/g, ' ')}</dd>
              </dl>
              {selectedEvent.event_scope !== 'SINGLE_CUSTOMER' && (
                <details style={{ marginTop: '0.8rem', fontSize: '0.82rem' }}>
                  <summary style={{ cursor: 'pointer', fontWeight: 650 }}>
                    Affected customer IDs ({selectedEvent.customer_ids.length.toLocaleString()})
                  </summary>
                  <div
                    aria-label={`Customers affected by ${selectedEvent.event_id}`}
                    style={{
                      maxHeight: 180,
                      overflowY: 'auto',
                      marginTop: '0.5rem',
                      padding: '0.55rem',
                      border: '1px solid var(--gv-border-subtle)',
                      borderRadius: 'var(--gv-radius-sm)',
                      overflowWrap: 'anywhere',
                      color: 'var(--gv-text-secondary)',
                    }}
                  >
                    {selectedEvent.customer_ids.join(', ')}
                  </div>
                </details>
              )}
            </>
          ) : <p className="gv-text-subtle">Select an event on the map or timeline to inspect its details.</p>}
        </div>
        <div>
          <h2 className="gv-heading-2" style={{ marginTop: 0 }}>Saved model evaluation</h2>
          <EvaluationMetrics metrics={model?.testMetrics ?? {}} />
        </div>
      </section>
    </>
  );
};

const fieldLabel: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: '0.3rem',
  fontSize: '0.75rem',
  fontWeight: 650,
  marginBottom: '0.65rem',
  color: 'var(--gv-text-secondary)',
};

const Metric: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={{ ...panelStyle, padding: '0.8rem' }}>
    <span style={{ fontSize: '0.68rem', color: 'var(--gv-text-muted)', textTransform: 'uppercase' }}>{label}</span>
    <strong style={{ display: 'block', fontSize: '1.2rem', color: 'var(--gv-text-primary)', marginTop: 5, overflowWrap: 'anywhere' }}>{value}</strong>
  </div>
);

const metricCount = (value: unknown): string =>
  typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString()
    : '—';

interface ApplicationResultsProps {
  runs: AnomalyRun[];
  selectedRunId: string;
  selectedRun: AnomalyRun | null;
  onSelectRun: (id: string) => void;
  download: (runId: string, filename: string) => void;
  downloadError: string | null;
}

const ApplicationResults: React.FC<ApplicationResultsProps> = ({
  runs, selectedRunId, selectedRun, onSelectRun, download, downloadError,
}) => (
  <section style={panelStyle}>
    <h2 className="gv-heading-2" style={{ marginTop: 0 }}>Application Results</h2>
    <p className="gv-text-subtle">Inspect persisted run results. Creation timestamps describe the application run; event dates describe the source data analysis period.</p>
    {downloadError && <p role="alert" style={{ color: 'var(--gv-status-danger)' }}>{downloadError}</p>}
    {selectedRun && (
      <div style={{ ...panelStyle, margin: '0.8rem 0', display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
        <Metric label="Selected run status" value={selectedRun.status} />
        <Metric label="Run created" value={formatDate(selectedRun.created_at)} />
        <Metric label="Source period" value={`${formatDate(selectedRun.request.start_date)} – ${formatDate(selectedRun.request.end_date)}`} />
        <Metric label="Localized events" value={metricCount(selectedRun.metrics?.localized_event_count)} />
        <Metric label="Affected customers" value={metricCount(selectedRun.metrics?.affected_customer_count)} />
      </div>
    )}
    {!runs.length ? <p className="gv-text-subtle">No saved application runs are available.</p> : (
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
          <thead><tr>{['Run', 'Created', 'Status', 'Date range', 'Events', 'Downloads'].map((header) => <th key={header} style={{ textAlign: 'left', padding: '0.65rem', borderBottom: '1px solid var(--gv-border-subtle)' }}>{header}</th>)}</tr></thead>
          <tbody>
            {runs.map((item) => (
              <tr key={item.analysis_id} style={{ background: selectedRunId === item.analysis_id ? '#F1F5F9' : 'transparent' }}>
                <td style={tableCell}><button type="button" onClick={() => onSelectRun(item.analysis_id)} style={{ ...buttonStyle, padding: '0.35rem 0.5rem', fontFamily: 'var(--gv-font-mono)' }}>{item.analysis_id.slice(0, 12)}</button></td>
                <td style={tableCell}>{formatDate(item.created_at)}</td>
                <td style={tableCell}>{item.status}</td>
                <td style={tableCell}>{formatDate(item.request?.start_date ?? '')} – {formatDate(item.request?.end_date ?? '')}</td>
                <td style={tableCell}>{metricCount(item.metrics?.localized_event_count)}</td>
                <td style={tableCell}>
                  {item.status === 'completed' ? (
                    <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                      {[
                        ['anomaly_records.csv', 'Anomaly records CSV'],
                        ['spatial_temporal_events.csv', 'Spatial-temporal events CSV'],
                        ['geographic_clusters.csv', 'Geographic clusters CSV'],
                        ['evaluation_metrics.json', 'Full evaluation JSON'],
                        ['event_localization_evaluation.json', 'Localization evaluation JSON'],
                        ['events.geojson', 'Events GeoJSON'],
                        ['analysis_result.json', 'Full run JSON'],
                      ].map(([file, label]) => (
                        <button key={file} type="button" title={`Download ${label}`} onClick={() => download(item.analysis_id, file)} style={{ ...buttonStyle, padding: '0.3rem 0.45rem', fontSize: '0.68rem' }}>
                          <Download size={12} style={{ verticalAlign: 'middle', marginRight: 3 }} />{label}
                        </button>
                      ))}
                    </div>
                  ) : <span className="gv-text-subtle">{item.error ?? 'Results unavailable until complete'}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
);

const tableCell: React.CSSProperties = {
  padding: '0.65rem',
  borderBottom: '1px solid var(--gv-border-subtle)',
  verticalAlign: 'top',
};

interface PersonaAlertsProps {
  persona: string;
  entity: string;
  entityId: number | null;
  events: AnomalyEvent[];
  windows: AnomalyWindow[];
  model: AnomalyModel | null;
  runs: AnomalyRun[];
}

const PersonaAlerts: React.FC<PersonaAlertsProps> = ({
  persona, entity, entityId, events, windows, model, runs,
}) => (
  <>
    <section style={{ ...panelStyle, display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
      <div>
        <span className="gv-text-subtle">Selected {persona === 'commercial' ? 'building' : 'customer'}</span>
        <strong style={{ display: 'block', marginTop: 4 }}>{entity}</strong>
      </div>
      <div>
        <span className="gv-text-subtle">Anomaly model</span>
        <strong style={{ display: 'block', marginTop: 4 }}>{model?.status ?? 'unknown'} · {model?.selectedModel ?? 'not deployed'}</strong>
      </div>
      <div>
        <span className="gv-text-subtle">Latest completed application run</span>
        <strong style={{ display: 'block', marginTop: 4 }}>
          {runs.find((item) => item.status === 'completed')?.created_at
            ? formatDate(runs.find((item) => item.status === 'completed')?.created_at ?? '')
            : 'No completed run'}
        </strong>
      </div>
    </section>
    {entityId === null ? (
      <div style={panelStyle} role="status">
        No anomaly-model customer ID is linked to this selected {persona === 'commercial' ? 'building' : 'residential account'}. Alerts are hidden until the account-to-meter mapping is configured.
      </div>
    ) : !events.length ? (
      <div style={panelStyle} role="status">
        No model-generated alerts for linked customer {entityId}. This view does not display other customers’ event records.
      </div>
    ) : (
      <section style={{ display: 'grid', gap: '0.7rem' }} aria-label="Entity anomaly alerts">
        {events.map((event) => {
          const direct = event.event_scope === 'SINGLE_CUSTOMER';
          const duration = windows
            .filter((window) => window.customer_id === entityId)
            .find((window) => event.anomaly_types.includes(window.anomaly_type));
          return (
            <article key={event.event_id} style={{ ...panelStyle, borderLeft: `4px solid ${scopeColor[event.event_scope]}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.7rem', flexWrap: 'wrap' }}>
                <strong>{event.dominant_anomaly_type.replace(/_/g, ' ')} · {event.event_scope.replace(/_/g, ' ')}</strong>
                <span>{direct ? 'Directly affected' : 'Impact-zone notification'}</span>
              </div>
              <p style={{ marginBottom: 0, color: 'var(--gv-text-secondary)', fontSize: '0.82rem' }}>
                Severity {event.max_anomaly_score.toFixed(2)} · {formatDuration(duration?.anomaly_duration ?? event.event_duration)} · {formatDate(event.event_start)} – {formatDate(event.event_end)}
              </p>
              {persona === 'commercial' && (
                <p className="gv-text-subtle" style={{ marginBottom: 0, marginTop: '0.45rem' }}>
                  Business impact: {direct ? 'the linked meter is directly affected.' : 'the linked meter is inside a localized impact event.'}
                </p>
              )}
            </article>
          );
        })}
      </section>
    )}
  </>
);
