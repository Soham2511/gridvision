import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { TopHeader } from '../layouts/TopHeader';
import { analyticsService } from '../services/analyticsService';
import { PlatformHealthSummary, ModelRegistryItem, CustomerBillModel, RegisteredModel } from '../types/analytics';
import { modelService } from '../services/modelService';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorState } from '../components/common/ErrorState';
import {
  Building2,
  MapPin,
  Clock,
  Database,
  MoreVertical,
  Check,
  FileCode,
  Activity,
  Layers,
} from 'lucide-react';

const mapRegistryModel = (model: RegisteredModel): ModelRegistryItem => {
  const rmse = model.testMetrics?.rmse_kwh ?? 0;
  return {
    id: model.modelId,
    modelName: model.name,
    personaUsed: model.domain,
    version: model.modelVersion === 'not_deployed' ? 'Not deployed' : `v${model.modelVersion}`,
    status: model.status === 'configured' ? 'Configured' : 'Unavailable',
    lastInference:
      model.status === 'configured'
        ? 'Ready for on-demand inference'
        : model.error ?? 'Unavailable',
    mse: Math.pow(rmse, 2),
    rmse,
    r2: model.testMetrics?.r2 ?? 0,
  };
};

export const DataModelHealthPage: React.FC = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<PlatformHealthSummary | null>(null);
  const [customerModel, setCustomerModel] = useState<CustomerBillModel | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    Promise.all([
      analyticsService.getPlatformHealthSummary(),
      modelService.getModelCatalog(),
    ])
      .then(([platform, registry]) => {
        if (mounted) {
          const registeredCustomer = registry.find(
            (model) => model.modelId === 'customer-bill-prediction'
          );
          if (
            !registeredCustomer?.dataset ||
            !registeredCustomer.testMetrics ||
            !registeredCustomer.features ||
            registeredCustomer.tariffInrPerKwh === undefined
          ) {
            throw new Error(
              registeredCustomer?.error ??
                'Customer gold dataset and model metadata are unavailable.'
            );
          }
          const model: CustomerBillModel = {
            ...registeredCustomer,
            dataset: registeredCustomer.dataset,
            testMetrics: registeredCustomer.testMetrics,
            features: registeredCustomer.features,
            tariffInrPerKwh: registeredCustomer.tariffInrPerKwh,
          };
          setCustomerModel(model);
          setData({
            ...platform,
            totalBuildings: model.dataset.entities,
            totalRegions: model.dataset.regions,
            dataTimeInterval: 'Cutoff snapshots',
            totalDataAccumulated: `${model.dataset.rows.toLocaleString()} rows`,
            dataAccumulatedSubtext: `${model.dataset.startMonth} – ${model.dataset.endMonth}`,
            lastUpdated: model.dataset.version,
            models: registry.map((item) => mapRegistryModel(item)),
          });
          setLoading(false);
        }
      })
      .catch((err) => {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load platform health telemetry.');
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  const handleActionClick = (model: ModelRegistryItem, actionType: string) => {
    setActiveMenuId(null);
    if (!customerModel || model.id !== customerModel.modelId) {
      setActionNotice('Customer model details are unavailable.');
      return;
    }

    const showNotice = (message: string) => {
      setActionNotice(message);
      window.setTimeout(() => setActionNotice(null), 5000);
    };

    if (actionType === 'Open Model Workbench') {
      navigate('/models');
      return;
    }

    if (actionType === 'Inspect Schema') {
      showNotice(
        `Input features (${customerModel.features.length}): ${customerModel.features.join(', ')}`
      );
      return;
    }

    if (actionType === 'Show Test Metrics') {
      const { mae_kwh: mae, rmse_kwh: rmse, r2 } = customerModel.testMetrics;
      showNotice(
        `Held-out test metrics for ${model.modelName}: MAE ${mae?.toFixed(2) ?? '—'} kWh, RMSE ${rmse?.toFixed(2) ?? '—'} kWh, R² ${r2?.toFixed(4) ?? '—'}.`
      );
      return;
    }

    if (actionType === 'Download Model Metadata') {
      const blob = new Blob([JSON.stringify(customerModel, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${customerModel.modelId}-metadata.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      showNotice(`Downloaded metadata for ${model.modelName}.`);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#F8FAFC',
        display: 'flex',
        flexDirection: 'column',
        fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif",
      }}
    >
      {/* 1. Platform Top Header (Admin Identity + GridVision Branding) */}
      <TopHeader showLogo={true} isAdmin={true} />

      {/* 2. Main Page Body */}
      <main
        style={{
          flex: 1,
          maxWidth: '1240px',
          margin: '0 auto',
          width: '100%',
          padding: '2.25rem 2rem 4rem 2rem',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: '1.75rem',
        }}
      >
        {/* Page Title & Subtitle */}
        <div>
          <h1
            style={{
              fontSize: '2.1rem',
              fontWeight: 800,
              color: '#0F172A',
              letterSpacing: '-0.025em',
              margin: '0 0 0.35rem 0',
              lineHeight: 1.15,
            }}
          >
            Data & Model Health
          </h1>
          <p
            style={{
              fontSize: '0.95rem',
              color: '#64748B',
              margin: 0,
              fontWeight: 500,
            }}
          >
            Monitor data availability, pipeline health and model performance across the GridVision platform.
          </p>
        </div>

        {/* Action feedback toast */}
        {actionNotice && (
          <div
            style={{
              backgroundColor: '#ECFDF5',
              border: '1px solid #A7F3D0',
              color: '#065F46',
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              fontSize: '0.85rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <Check size={16} />
            <span>{actionNotice}</span>
          </div>
        )}

        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1.25rem' }}>
              <LoadingSkeleton height="110px" count={4} />
            </div>
            <LoadingSkeleton height="360px" />
          </div>
        ) : error || !data ? (
          <ErrorState
            title="Platform Telemetry Offline"
            message={error || 'Failed to retrieve model registry status.'}
          />
        ) : (
          <>
            {/* 3. Four Platform Summary KPI Cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                gap: '1.25rem',
              }}
            >
              {/* Card 1: Total Buildings */}
              <div
                style={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: '12px',
                  border: '1px solid #E2E8F0',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                  padding: '1.4rem 1.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1.25rem',
                }}
              >
                <div
                  style={{
                    width: '46px',
                    height: '46px',
                    borderRadius: '50%',
                    backgroundColor: '#E0F2FE',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Building2 size={24} color="#0284C7" />
                </div>
                <div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0F172A' }}>
                    Gold Dataset Entities
                  </div>
                  <div
                    style={{
                      fontSize: '1.9rem',
                      fontWeight: 800,
                      color: '#0F172A',
                      lineHeight: 1.15,
                      margin: '2px 0',
                    }}
                  >
                    {data.totalBuildings}
                  </div>
                  <div style={{ fontSize: '0.76rem', color: '#64748B' }}>
                    Entities in the customer gold dataset
                  </div>
                </div>
              </div>

              {/* Card 2: Total Regions */}
              <div
                style={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: '12px',
                  border: '1px solid #E2E8F0',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                  padding: '1.4rem 1.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1.25rem',
                }}
              >
                <div
                  style={{
                    width: '46px',
                    height: '46px',
                    borderRadius: '50%',
                    backgroundColor: '#DCFCE7',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <MapPin size={24} color="#16A34A" />
                </div>
                <div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0F172A' }}>
                    Total Regions
                  </div>
                  <div
                    style={{
                      fontSize: '1.9rem',
                      fontWeight: 800,
                      color: '#0F172A',
                      lineHeight: 1.15,
                      margin: '2px 0',
                    }}
                  >
                    {data.totalRegions}
                  </div>
                  <div style={{ fontSize: '0.76rem', color: '#64748B' }}>
                    Regions with available data
                  </div>
                </div>
              </div>

              {/* Card 3: Data Time Interval */}
              <div
                style={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: '12px',
                  border: '1px solid #E2E8F0',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                  padding: '1.4rem 1.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1.25rem',
                }}
              >
                <div
                  style={{
                    width: '46px',
                    height: '46px',
                    borderRadius: '50%',
                    backgroundColor: '#F3E8FF',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Clock size={24} color="#7C3AED" />
                </div>
                <div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0F172A' }}>
                    Data Time Interval
                  </div>
                  <div
                    style={{
                      fontSize: '1.9rem',
                      fontWeight: 800,
                      color: '#0F172A',
                      lineHeight: 1.15,
                      margin: '2px 0',
                    }}
                  >
                    {data.dataTimeInterval}
                  </div>
                  <div style={{ fontSize: '0.76rem', color: '#64748B' }}>
                    Granularity of ingested data
                  </div>
                </div>
              </div>

              {/* Card 4: Total Data Accumulated */}
              <div
                style={{
                  backgroundColor: '#FFFFFF',
                  borderRadius: '12px',
                  border: '1px solid #E2E8F0',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                  padding: '1.4rem 1.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1.25rem',
                }}
              >
                <div
                  style={{
                    width: '46px',
                    height: '46px',
                    borderRadius: '50%',
                    backgroundColor: '#FFEDD5',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}
                >
                  <Database size={24} color="#EA580C" />
                </div>
                <div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0F172A' }}>
                    Total Data Accumulated
                  </div>
                  <div
                    style={{
                      fontSize: '1.9rem',
                      fontWeight: 800,
                      color: '#0F172A',
                      lineHeight: 1.15,
                      margin: '2px 0',
                    }}
                  >
                    {data.totalDataAccumulated}
                  </div>
                  <div style={{ fontSize: '0.76rem', color: '#64748B' }}>
                    {data.dataAccumulatedSubtext}
                  </div>
                </div>
              </div>
            </div>

            {/* 4. Model Registry Table Card */}
            <div
              style={{
                backgroundColor: '#FFFFFF',
                borderRadius: '12px',
                border: '1px solid #E2E8F0',
                boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
                padding: '1.75rem',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {/* Section Header */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '1.5rem',
                  flexWrap: 'wrap',
                  gap: '0.75rem',
                }}
              >
                <div>
                  <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0F172A', margin: 0 }}>
                    Model Registry
                  </h2>
                  <p style={{ fontSize: '0.84rem', color: '#64748B', margin: '4px 0 0 0' }}>
                    Overview of deployed models, their usage across personas, and performance metrics.
                  </p>
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '0.78rem',
                    color: '#64748B',
                    fontWeight: 500,
                  }}
                >
                  <Clock size={14} color="#64748B" />
                  <span>Gold dataset version: {data.lastUpdated}</span>
                </div>
              </div>

              {/* Table Container */}
              <div style={{ overflowX: 'auto', width: '100%' }}>
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    textAlign: 'left',
                    fontSize: '0.85rem',
                  }}
                >
                  {/* Table Head */}
                  <thead>
                    {/* Upper Header Row */}
                    <tr
                      style={{
                        backgroundColor: '#F8FAFC',
                        borderBottom: '1px solid #E2E8F0',
                        color: '#0F172A',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                      }}
                    >
                      <th style={{ padding: '0.85rem 1rem' }}>Model Name</th>
                      <th style={{ padding: '0.85rem 1rem' }}>Persona Used</th>
                      <th style={{ padding: '0.85rem 1rem' }}>Version</th>
                      <th style={{ padding: '0.85rem 1rem' }}>Status</th>
                      <th style={{ padding: '0.85rem 1rem' }}>Last Inference</th>
                      <th
                        colSpan={3}
                        style={{
                          padding: '0.85rem 1rem',
                          textAlign: 'center',
                          borderLeft: '1px solid #E2E8F0',
                          borderRight: '1px solid #E2E8F0',
                          color: '#0F172A',
                        }}
                      >
                        Metrics
                      </th>
                      <th style={{ padding: '0.85rem 1rem', textAlign: 'center' }}>Actions</th>
                    </tr>
                    {/* Sub-header for Metrics */}
                    <tr
                      style={{
                        backgroundColor: '#F8FAFC',
                        borderBottom: '1px solid #E2E8F0',
                        color: '#64748B',
                        fontSize: '0.74rem',
                        fontWeight: 600,
                      }}
                    >
                      <th colSpan={5} style={{ padding: 0 }} />
                      <th style={{ padding: '0.45rem 0.75rem', textAlign: 'right', borderLeft: '1px solid #E2E8F0' }}>
                        MSE ↓
                      </th>
                      <th style={{ padding: '0.45rem 0.75rem', textAlign: 'right' }}>
                        RMSE ↓
                      </th>
                      <th style={{ padding: '0.45rem 0.75rem', textAlign: 'right', borderRight: '1px solid #E2E8F0' }}>
                        R² ↑
                      </th>
                      <th style={{ padding: 0 }} />
                    </tr>
                  </thead>

                  {/* Table Body */}
                  <tbody>
                    {data.models.map((model) => (
                      <tr
                        key={model.id}
                        style={{
                          borderBottom: '1px solid #F1F5F9',
                          transition: 'background-color 0.15s ease',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F8FAFC')}
                        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                      >
                        {/* Model Name */}
                        <td style={{ padding: '1rem', fontWeight: 700, color: '#0F172A' }}>
                          {model.modelName}
                        </td>

                        {/* Persona Used */}
                        <td style={{ padding: '1rem', color: '#334155', fontWeight: 500 }}>
                          {model.personaUsed}
                        </td>

                        {/* Version */}
                        <td style={{ padding: '1rem', color: '#64748B', fontFamily: 'monospace', fontSize: '0.82rem' }}>
                          {model.version}
                        </td>

                        {/* Status */}
                        <td style={{ padding: '1rem' }}>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '6px',
                              padding: '3px 10px',
                              borderRadius: '9999px',
                              fontSize: '0.76rem',
                              fontWeight: 600,
                              backgroundColor:
                                model.status === 'Active'
                                  ? '#DCFCE7'
                                  : model.status === 'Monitoring'
                                  ? '#FEF3C7'
                                  : model.status === 'Configured'
                                  ? '#E0F2FE'
                                  : model.status === 'Unavailable'
                                  ? '#FEE2E2'
                                  : '#F1F5F9',
                              color:
                                model.status === 'Active'
                                  ? '#15803D'
                                  : model.status === 'Monitoring'
                                  ? '#B45309'
                                  : model.status === 'Configured'
                                  ? '#0369A1'
                                  : model.status === 'Unavailable'
                                  ? '#B91C1C'
                                  : '#64748B',
                            }}
                          >
                            <span
                              style={{
                                width: '6px',
                                height: '6px',
                                borderRadius: '50%',
                                backgroundColor:
                                  model.status === 'Active'
                                    ? '#16A34A'
                                    : model.status === 'Monitoring'
                                    ? '#D97706'
                                    : model.status === 'Configured'
                                    ? '#0284C7'
                                    : model.status === 'Unavailable'
                                    ? '#DC2626'
                                    : '#94A3B8',
                              }}
                            />
                            <span>{model.status}</span>
                          </span>
                        </td>

                        {/* Last Inference */}
                        <td style={{ padding: '1rem', color: '#334155', fontWeight: 500 }}>
                          {model.lastInference}
                        </td>

                        {/* MSE */}
                        <td
                          style={{
                            padding: '1rem 0.75rem',
                            textAlign: 'right',
                            borderLeft: '1px solid #F1F5F9',
                            color: '#0F172A',
                            fontFamily: 'monospace',
                            fontWeight: 600,
                          }}
                        >
                          {model.mse.toFixed(3)}
                        </td>

                        {/* RMSE */}
                        <td
                          style={{
                            padding: '1rem 0.75rem',
                            textAlign: 'right',
                            color: '#0F172A',
                            fontFamily: 'monospace',
                            fontWeight: 600,
                          }}
                        >
                          {model.rmse.toFixed(3)}
                        </td>

                        {/* R² */}
                        <td
                          style={{
                            padding: '1rem 0.75rem',
                            textAlign: 'right',
                            borderRight: '1px solid #F1F5F9',
                            color: '#0F172A',
                            fontFamily: 'monospace',
                            fontWeight: 600,
                          }}
                        >
                          {model.r2.toFixed(2)}
                        </td>

                        {/* Actions */}
                        <td style={{ padding: '1rem', textAlign: 'center', position: 'relative' }}>
                          {model.id === 'customer-bill-prediction' && <button
                            type="button"
                            onClick={() =>
                              setActiveMenuId(activeMenuId === model.id ? null : model.id)
                            }
                            aria-label={`Actions for ${model.modelName}`}
                            style={{
                              background: 'transparent',
                              border: 'none',
                              cursor: 'pointer',
                              color: '#64748B',
                              padding: '4px',
                              borderRadius: '4px',
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                            }}
                          >
                            <MoreVertical size={16} />
                          </button>}

                          {/* Context Menu Dropdown */}
                          {model.id === 'customer-bill-prediction' && activeMenuId === model.id && (
                            <div
                              style={{
                                position: 'absolute',
                                right: '10px',
                                top: '35px',
                                backgroundColor: '#FFFFFF',
                                border: '1px solid #E2E8F0',
                                borderRadius: '8px',
                                boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.15)',
                                zIndex: 50,
                                minWidth: '180px',
                                padding: '4px',
                                textAlign: 'left',
                              }}
                            >
                              <button
                                type="button"
                                onClick={() => handleActionClick(model, 'Open Model Workbench')}
                                style={{
                                  width: '100%',
                                  padding: '8px 12px',
                                  fontSize: '0.78rem',
                                  fontWeight: 500,
                                  color: '#334155',
                                  background: 'transparent',
                                  border: 'none',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '8px',
                                }}
                                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F1F5F9')}
                                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                              >
                                <Activity size={14} color="#087EBD" />
                                <span>Open Model Workbench</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => handleActionClick(model, 'Inspect Schema')}
                                style={{
                                  width: '100%',
                                  padding: '8px 12px',
                                  fontSize: '0.78rem',
                                  fontWeight: 500,
                                  color: '#334155',
                                  background: 'transparent',
                                  border: 'none',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '8px',
                                }}
                                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F1F5F9')}
                                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                              >
                                <FileCode size={14} color="#64748B" />
                                <span>Inspect Schema</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => handleActionClick(model, 'Show Test Metrics')}
                                style={{
                                  width: '100%',
                                  padding: '8px 12px',
                                  fontSize: '0.78rem',
                                  fontWeight: 500,
                                  color: '#334155',
                                  background: 'transparent',
                                  border: 'none',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '8px',
                                }}
                                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F1F5F9')}
                                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                              >
                                <Activity size={14} color="#00A389" />
                                <span>Show Test Metrics</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => handleActionClick(model, 'Download Model Metadata')}
                                style={{
                                  width: '100%',
                                  padding: '8px 12px',
                                  fontSize: '0.78rem',
                                  fontWeight: 500,
                                  color: '#334155',
                                  background: 'transparent',
                                  border: 'none',
                                  borderRadius: '4px',
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '8px',
                                }}
                                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#F1F5F9')}
                                onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                              >
                                <Layers size={14} color="#64748B" />
                                <span>Download Model Metadata</span>
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
};
