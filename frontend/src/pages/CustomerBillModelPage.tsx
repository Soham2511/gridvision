import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Cpu, Play, ChevronLeft, ChevronRight, Database, CheckCircle2, Layers, BarChart3 } from 'lucide-react';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { PageHeader } from '../components/common/PageHeader';
import { modelService } from '../services/modelService';
import {
  CustomerBillModel,
  CustomerBillPrediction,
  CustomerBillRecord,
  RegisteredModel,
} from '../types/analytics';

const PAGE_SIZE = 50;

export const CustomerBillModelPage: React.FC = () => {
  const [model, setModel] = useState<CustomerBillModel | null>(null);
  const [catalog, setCatalog] = useState<RegisteredModel[]>([]);
  const [activeModelId, setActiveModelId] = useState<string>('customer-bill-prediction');
  const [records, setRecords] = useState<CustomerBillRecord[]>([]);
  const [months, setMonths] = useState<CustomerBillRecord[]>([]);
  const [selectedEntity, setSelectedEntity] = useState('');
  const [selectedMonth, setSelectedMonth] = useState('');
  const [offset, setOffset] = useState(0);
  const [prediction, setPrediction] = useState<CustomerBillPrediction | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMonths, setLoadingMonths] = useState(false);
  const [predicting, setPredicting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedRecord = useMemo(
    () => months.find(
      (record) => `${record.monthStart}:${record.cutoffDay}` === selectedMonth
    ),
    [months, selectedMonth]
  );

  const loadEntityMonths = useCallback(async (entityId: string) => {
    setLoadingMonths(true);
    try {
      const entityMonths = await modelService.getEntityMonths(entityId);
      setMonths(entityMonths);
      const latestRecord = entityMonths[entityMonths.length - 1];
      setSelectedMonth(
        latestRecord
          ? `${latestRecord.monthStart}:${latestRecord.cutoffDay}`
          : ''
      );
      setPrediction(null);
    } catch (err) {
      setMonths([]);
      setSelectedMonth('');
      setError(err instanceof Error ? err.message : 'Unable to load customer months.');
    } finally {
      setLoadingMonths(false);
    }
  }, []);

  const loadPage = useCallback(async (pageOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      const [allModels, page] = await Promise.all([
        modelService.getModelCatalog(),
        modelService.getCustomerRecords(PAGE_SIZE, pageOffset),
      ]);
      setCatalog(allModels);
      const customer = allModels.find(
        (candidate) => candidate.modelId === 'customer-bill-prediction'
      ) as CustomerBillModel | undefined;
      if (customer) {
        setModel(customer);
      }
      setRecords(page.items);
      setOffset(page.offset);
      const nextEntity = page.items[0]?.entityId ?? '';
      setSelectedEntity(nextEntity);
      setPrediction(null);
      if (nextEntity) {
        await loadEntityMonths(nextEntity);
      } else {
        setMonths([]);
        setSelectedMonth('');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load model data.');
    } finally {
      setLoading(false);
    }
  }, [loadEntityMonths]);

  useEffect(() => {
    void loadPage(0);
  }, [loadPage]);

  const handleEntityChange = (entityId: string) => {
    setSelectedEntity(entityId);
    void loadEntityMonths(entityId);
  };

  const handlePredict = async () => {
    if (!selectedEntity || !selectedMonth) return;
    setPredicting(true);
    setError(null);
    try {
      setPrediction(
        await modelService.predictCustomerBill(
          selectedEntity,
          selectedRecord?.monthStart ?? '',
          selectedRecord?.cutoffDay ?? 0
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Customer prediction failed.');
    } finally {
      setPredicting(false);
    }
  };

  if (loading && !model) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Model Workbench" description="Loading registered models and gold datasets..." />
        <LoadingSkeleton height="150px" count={3} />
      </div>
    );
  }

  if (error && !model) {
    return <ErrorState title="Model Workbench Unavailable" message={error} onRetry={() => void loadPage(offset)} />;
  }

  const currentModel = catalog.find((m) => m.modelId === activeModelId) || model;
  if (!currentModel || !currentModel.dataset || !currentModel.testMetrics) return null;

  const maxOffset = Math.max(0, currentModel.dataset.entities - PAGE_SIZE);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Model Selection Tabs */}
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', borderBottom: '1px solid var(--gv-border-subtle)', paddingBottom: '0.75rem', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={() => setActiveModelId('customer-bill-prediction')}
          className={`gv-button ${activeModelId === 'customer-bill-prediction' ? 'gv-button-primary' : 'gv-button-secondary'}`}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <Cpu size={15} /> Customer Bill Prediction (Residential)
        </button>
        <button
          type="button"
          onClick={() => setActiveModelId('government-load-forecasting')}
          className={`gv-button ${activeModelId === 'government-load-forecasting' ? 'gv-button-primary' : 'gv-button-secondary'}`}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <BarChart3 size={15} /> Government Grid Load Forecaster (Utilities)
        </button>
      </div>

      <PageHeader
        title={currentModel.name}
        description={currentModel.description}
        badge={
          <span className={`gv-badge ${currentModel.status === 'configured' ? 'gv-badge-success' : 'gv-badge-danger'}`}>
            <Cpu size={12} />
            <span>{currentModel.status === 'configured' ? `${currentModel.modelVersion} · ${currentModel.provider}` : 'Model unavailable'}</span>
          </span>
        }
      />

      {error && (
        <div role="alert" className="gv-card" style={{ color: 'var(--gv-status-danger)' }}>
          {error}
        </div>
      )}

      <section className="gv-grid-kpis">
        <div className="gv-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--gv-text-muted)', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase' }}>
            <Database size={15} /> Gold records
          </div>
          <strong style={{ display: 'block', fontSize: '1.8rem', marginTop: '0.5rem' }}>{currentModel.dataset.rows.toLocaleString()}</strong>
          <span className="gv-text-muted">{currentModel.dataset.entities.toLocaleString()} entities · {currentModel.dataset.startMonth} to {currentModel.dataset.endMonth}</span>
        </div>
        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase' }}>Held-out validation MAE</span>
          <strong style={{ display: 'block', fontSize: '1.8rem', marginTop: '0.5rem' }}>{currentModel.testMetrics.mae_kwh?.toFixed(2) ?? '—'} kWh</strong>
          <span className="gv-text-muted">RMSE {currentModel.testMetrics.rmse_kwh?.toFixed(2) ?? '—'} kWh · R² {currentModel.testMetrics.r2?.toFixed(4) ?? '—'}</span>
        </div>
        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase' }}>Dataset quality & status</span>
          <strong style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.4rem', marginTop: '0.65rem', color: currentModel.dataset.qualityPassed ? 'var(--gv-color-smart-teal)' : 'var(--gv-status-danger)' }}>
            <CheckCircle2 size={20} /> {currentModel.dataset.qualityPassed ? 'Passed' : 'Not verified'}
          </strong>
          <span className="gv-text-muted">Version {currentModel.dataset.version}</span>
        </div>
      </section>

      {activeModelId === 'customer-bill-prediction' && model && (
        <section className="gv-card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <h2 className="gv-heading-2">Run a gold-record replay</h2>
            <p className="gv-text-muted" style={{ marginTop: '0.3rem' }}>
              Choose a customer and month, then compare the cutoff-time estimate with the known month total. This is a retrospective evaluation, not a live bill.
            </p>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'end', gap: '1rem' }}>
            <label style={{ display: 'grid', gap: '0.4rem', fontSize: '0.8rem', fontWeight: 600 }}>
              Customer entity
              <select value={selectedEntity} onChange={(event) => handleEntityChange(event.target.value)} disabled={!records.length || loadingMonths}>
                {records.map((record) => (
                  <option key={record.entityId} value={record.entityId}>
                    {record.entityId} · {record.buildingType}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: 'grid', gap: '0.4rem', fontSize: '0.8rem', fontWeight: 600 }}>
              Gold month
              <select value={selectedMonth} onChange={(event) => { setSelectedMonth(event.target.value); setPrediction(null); }} disabled={!months.length || loadingMonths}>
                {months.map((record) => (
                  <option key={`${record.monthStart}:${record.cutoffDay}`} value={`${record.monthStart}:${record.cutoffDay}`}>{record.monthStart} · cutoff day {record.cutoffDay}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void handlePredict()}
              disabled={!selectedRecord || predicting || loadingMonths || model.status === 'unavailable'}
              className="gv-button gv-button-primary"
            >
              <Play size={15} /> {predicting ? 'Predicting…' : 'Run model prediction'}
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: 'auto' }}>
              <button type="button" className="gv-button gv-button-secondary" onClick={() => void loadPage(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0 || loading} aria-label="Previous customers">
                <ChevronLeft size={16} /> Previous
              </button>
              <span className="gv-text-muted" style={{ fontSize: '0.78rem' }}>
                {offset + 1}–{Math.min(offset + PAGE_SIZE, model.dataset.entities)} of {model.dataset.entities}
              </span>
              <button type="button" className="gv-button gv-button-secondary" onClick={() => void loadPage(Math.min(maxOffset, offset + PAGE_SIZE))} disabled={offset + PAGE_SIZE >= model.dataset.entities || loading} aria-label="Next customers">
                Next <ChevronRight size={16} />
              </button>
            </div>
          </div>

          {selectedRecord && (
            <div className="gv-text-muted" style={{ fontSize: '0.82rem' }}>
              Cutoff consumption: <strong>{selectedRecord.cumulativeEnergyKwh.toFixed(2)} kWh</strong> · Coverage: <strong>{(selectedRecord.coverageRatio * 100).toFixed(1)}%</strong> · Actual month total: <strong>{selectedRecord.actualMonthKwh.toFixed(2)} kWh</strong>
            </div>
          )}

          {prediction && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '0.8rem', borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '1rem' }}>
              <div><span className="gv-text-muted">Predicted month-end</span><strong style={{ display: 'block', fontSize: '1.3rem' }}>{prediction.predictedMonthEndKwh.toFixed(2)} kWh</strong></div>
              <div><span className="gv-text-muted">Actual month-end</span><strong style={{ display: 'block', fontSize: '1.3rem' }}>{prediction.actualMonthEndKwh.toFixed(2)} kWh</strong></div>
              <div><span className="gv-text-muted">Absolute error</span><strong style={{ display: 'block', fontSize: '1.3rem' }}>{prediction.absoluteErrorKwh.toFixed(2)} kWh</strong></div>
              <div><span className="gv-text-muted">Estimated bill at ₹{model.tariffInrPerKwh.toFixed(2)}/kWh</span><strong style={{ display: 'block', fontSize: '1.3rem' }}>₹{prediction.predictedBillInr.toLocaleString()}</strong></div>
              <div style={{ gridColumn: '1 / -1', fontSize: '0.75rem', color: 'var(--gv-text-muted)' }}>
                {prediction.modelName} v{prediction.modelVersion} · {prediction.provider} · Retrospective Gold replay · Not a customer invoice
              </div>
            </div>
          )}
        </section>
      )}

      {activeModelId === 'government-load-forecasting' && (
        <section className="gv-card" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div>
            <h2 className="gv-heading-2">Dual LightGBM Hybrid Architecture</h2>
            <p className="gv-text-muted" style={{ marginTop: '0.3rem' }}>
              The government load forecaster pairs two LightGBM models trained on 1,000,000 sampled rows with 1,200 estimators each. Validation routing dynamically chooses the lowest-MAE model for each coarse grid zone.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
            <div style={{ padding: '1.25rem', borderRadius: '10px', border: '1px solid var(--gv-border-subtle)', background: 'var(--gv-bg-card-subtle)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700, color: '#0F172A', marginBottom: '0.4rem' }}>
                <Layers size={18} color="#0284C7" /> Model 1: Direct Energy Regressor
              </div>
              <p style={{ fontSize: '0.85rem', color: '#64748B', margin: 0, lineHeight: 1.5 }}>
                Fits LightGBM on <code>target_energy</code> directly. Best suited for high-load industrial and baseline grids with high variance.
              </p>
            </div>
            <div style={{ padding: '1.25rem', borderRadius: '10px', border: '1px solid var(--gv-border-subtle)', background: 'var(--gv-bg-card-subtle)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700, color: '#0F172A', marginBottom: '0.4rem' }}>
                <Layers size={18} color="#0D9488" /> Model 2: Log-Transformed Regressor
              </div>
              <p style={{ fontSize: '0.85rem', color: '#64748B', margin: 0, lineHeight: 1.5 }}>
                Fits LightGBM on <code>log1p(target_energy)</code> and inverts with <code>expm1(max(y, 0))</code>. Optimal for residential and skewed distribution grids.
              </p>
            </div>
          </div>

          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.75rem', color: '#0F172A' }}>
              Engineered Feature Schema ({currentModel.features?.length ?? 36} Features)
            </h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
              {currentModel.features?.map((feature) => (
                <span
                  key={feature}
                  style={{
                    fontSize: '0.75rem',
                    padding: '0.25rem 0.6rem',
                    borderRadius: '6px',
                    background: '#F1F5F9',
                    color: '#334155',
                    fontFamily: 'monospace',
                    fontWeight: 600,
                  }}
                >
                  {feature}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
};
