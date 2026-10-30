import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Activity, Cpu, Database, Play } from 'lucide-react';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { PageHeader } from '../components/common/PageHeader';
import { modelService } from '../services/modelService';
import { RegisteredModel } from '../types/analytics';

type ForecastPoint = { timestamp: string; horizon_hours: number; prediction: number; actual?: number };
type ForecastEntity = Record<string, unknown>;

const modelIds = new Set(['commercial-building-forecast', 'government-load-forecast']);
const entityKey = (modelId: string, entity: ForecastEntity) => String(
  modelId === 'commercial-building-forecast' ? entity.buildingId : entity.siteId
);

export const ModelWorkbenchPage: React.FC = () => {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<RegisteredModel[]>([]);
  const [selectedId, setSelectedId] = useState('commercial-building-forecast');
  const [entities, setEntities] = useState<ForecastEntity[]>([]);
  const [selectedEntity, setSelectedEntity] = useState('');
  const [points, setPoints] = useState<ForecastPoint[]>([]);
  const [modelInfo, setModelInfo] = useState<{ model_name: string; model_version: string; provider: string; evaluation_status: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [predicting, setPredicting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const forecastModels = useMemo(() => catalog.filter((model) => modelIds.has(model.modelId)), [catalog]);
  const selectedModel = forecastModels.find((model) => model.modelId === selectedId);
  const selectedEntityInfo = entities.find((entity) => entityKey(selectedId, entity) === selectedEntity);

  useEffect(() => {
    let live = true;
    modelService.getModelCatalog().then((items) => {
      if (!live) return;
      setCatalog(items);
      const available = items.find((model) => modelIds.has(model.modelId) && model.status === 'configured');
      if (available) setSelectedId(available.modelId);
    }).catch((err) => live && setError(err instanceof Error ? err.message : 'Unable to load model catalog.'))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    let live = true;
    setEntities([]);
    setSelectedEntity('');
    setPoints([]);
    if (!modelIds.has(selectedId)) return;
    modelService.getForecastModelEntities(selectedId).then(({ items }) => {
      if (!live) return;
      setEntities(items);
      setSelectedEntity(items.length ? entityKey(selectedId, items[0]) : '');
    }).catch((err) => live && setError(err instanceof Error ? err.message : 'Unable to load forecast entities.'));
    return () => { live = false; };
  }, [selectedId]);

  const runPrediction = async () => {
    if (!selectedEntity) return;
    setPredicting(true);
    setError(null);
    try {
      const result = await modelService.predictForecastModel(selectedId, selectedEntity);
      setModelInfo(result.model);
      setPoints(result.horizon);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Forecast inference failed.');
    } finally {
      setPredicting(false);
    }
  };

  if (loading) return <><PageHeader title="Model Workbench" description="Loading registered models..." /><LoadingSkeleton height="150px" count={3} /></>;
  if (error && !catalog.length) return <ErrorState title="Model Catalog Unavailable" message={error} />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <PageHeader title="Model Workbench" description="Inspect model readiness, data contracts, and run forecast replays against the registered champion models." />
      {error && <div role="alert" className="gv-card" style={{ color: 'var(--gv-status-danger)' }}>{error}</div>}
      <section className="gv-grid-kpis">
        {catalog.map((model) => (
          <button key={model.modelId} type="button" onClick={() => model.modelId === 'customer-bill-prediction' ? navigate('/models/customer') : setSelectedId(model.modelId)} className="gv-card" style={{ textAlign: 'left', cursor: 'pointer', border: selectedId === model.modelId ? '2px solid var(--gv-color-smart-teal)' : undefined }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}><Cpu size={18} /><span className={`gv-badge ${model.status === 'configured' ? 'gv-badge-success' : 'gv-badge-danger'}`}>{model.status}</span></div>
            <strong style={{ display: 'block', marginTop: '0.65rem' }}>{model.name}</strong>
            <span className="gv-text-muted">{model.modelVersion} · {model.provider}</span>
            <span className="gv-text-muted" style={{ display: 'block', marginTop: '0.4rem' }}>{model.description}</span>
          </button>
        ))}
      </section>

      {selectedModel && (
        <section className="gv-card" style={{ display: 'grid', gap: '1rem' }}>
          <div><h2 className="gv-heading-2">{selectedModel.name}</h2><p className="gv-text-muted">Registered alias: <strong>{selectedModel.selectedModel}</strong> · Version: <strong>{selectedModel.modelVersion}</strong> · Provider: <strong>{selectedModel.provider}</strong></p></div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
            <div className="gv-card"><Database size={16} /> <strong>{entities.length.toLocaleString()}</strong><div className="gv-text-muted">Forecast entities available</div></div>
            <div className="gv-card"><Activity size={16} /> <strong>{selectedModel.testMetrics?.mae_kwh?.toFixed(2) ?? '—'} kWh</strong><div className="gv-text-muted">Held-out MAE</div></div>
            <div className="gv-card"><Activity size={16} /> <strong>{selectedModel.testMetrics?.rmse_kwh?.toFixed(2) ?? '—'} kWh</strong><div className="gv-text-muted">Held-out RMSE</div></div>
          </div>
          {selectedModel.features?.length ? <details><summary>Input feature schema ({selectedModel.features.length})</summary><p className="gv-text-muted">{selectedModel.features.join(', ')}</p></details> : null}
          <div style={{ display: 'flex', alignItems: 'end', flexWrap: 'wrap', gap: '0.75rem' }}>
            <label style={{ display: 'grid', gap: '0.4rem', fontWeight: 600 }}>Entity
              <select value={selectedEntity} onChange={(event) => { setSelectedEntity(event.target.value); setPoints([]); }} disabled={!entities.length}>
                {entities.map((entity) => <option key={entityKey(selectedId, entity)} value={entityKey(selectedId, entity)}>{entityKey(selectedId, entity)} · {String(entity.name ?? entity.primarySpaceUsage ?? entity.region ?? '')}</option>)}
              </select>
            </label>
            <button type="button" className="gv-button gv-button-primary" onClick={() => void runPrediction()} disabled={!selectedEntity || predicting || selectedModel.status !== 'configured'}><Play size={15} /> {predicting ? 'Running replay…' : 'Run 24-hour replay'}</button>
            {modelInfo && <span className="gv-text-muted">Serving {modelInfo.model_name} v{modelInfo.model_version} from {modelInfo.provider}</span>}
          </div>
          {selectedEntityInfo && <p className="gv-text-muted">Selected entity: {selectedEntity}. This is a chronological held-out replay; actual values are shown alongside predictions for evaluation.</p>}
          {points.length > 0 && <div style={{ overflowX: 'auto' }}><table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}><thead><tr><th>Horizon</th><th>Timestamp</th><th>Predicted demand (kWh)</th><th>Actual (kWh)</th></tr></thead><tbody>{points.map((point) => <tr key={`${point.timestamp}-${point.horizon_hours}`}><td>{point.horizon_hours}h</td><td>{new Date(point.timestamp).toLocaleString()}</td><td>{point.prediction.toFixed(2)}</td><td>{point.actual?.toFixed(2) ?? '—'}</td></tr>)}</tbody></table></div>}
        </section>
      )}
      <Link to="/models/customer" className="gv-text-muted">Open Customer Bill Prediction workbench</Link>
    </div>
  );
};
