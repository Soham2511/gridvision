import React, { useEffect, useState } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorState } from '../components/common/ErrorState';
import { analyticsService } from '../services/analyticsService';
import { BusinessInsight, RegionalSite } from '../types/analytics';
import {
  Download,
  CheckCircle2,
  Layers,
} from 'lucide-react';

export const EnergyInsightsPage: React.FC = () => {
  const [insights, setInsights] = useState<BusinessInsight[]>([]);
  const [sites, setSites] = useState<RegionalSite[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [exportNotice, setExportNotice] = useState<boolean>(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [insData, siteData] = await Promise.all([
          analyticsService.getBusinessInsights(),
          analyticsService.getRegionalSites(),
        ]);
        setInsights(insData);
        setSites(siteData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load insights.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleExport = () => {
    const columns = [
      'Category',
      'Sector',
      'Title',
      'Description',
      'Impact',
      'Potential Value',
      'Urgency',
      'Recommendation',
    ];
    const escapeCsv = (value: string) => `"${value.replace(/"/g, '""')}"`;
    const rows = filtered.map((insight) =>
      [
        insight.category,
        insight.sector,
        insight.title,
        insight.description,
        insight.impactMetric,
        insight.potentialValue,
        insight.urgency,
        insight.actionableRecommendation,
      ]
        .map((value) => escapeCsv(String(value)))
        .join(',')
    );
    const blob = new Blob([[columns.map(escapeCsv).join(','), ...rows].join('\r\n')], {
      type: 'text/csv;charset=utf-8',
    });
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = 'gridvision-energy-insights.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
    setExportNotice(true);
    setTimeout(() => setExportNotice(false), 3000);
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Energy Insights & Optimization" description="Synthesizing takeaways..." />
        <LoadingSkeleton height="140px" count={3} />
      </div>
    );
  }

  if (error) {
    return <ErrorState title="Insights Offline" message={error} />;
  }

  const filtered = insights.filter((ins) => {
    if (categoryFilter === 'all') return true;
    return ins.category === categoryFilter;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Page Header */}
      <PageHeader
        title="Energy Insights & Optimization"
        description="Actionable dispatch protocols, energy efficiency opportunities, and regional load redistribution plans."
        badge={<span className="gv-badge gv-badge-success">{insights.length} Algorithmic Recommendations</span>}
        actions={
          <button
            type="button"
            onClick={handleExport}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.45rem 0.95rem',
              borderRadius: 'var(--gv-radius-md)',
              background: 'var(--gv-color-smart-teal)',
              color: '#FFFFFF',
              fontWeight: 700,
              fontSize: '0.8rem',
              cursor: 'pointer',
              border: 'none',
            }}
          >
            <Download size={14} />
            <span>Export Intelligence Report</span>
          </button>
        }
      />

      {exportNotice && (
        <div
          style={{
            background: 'var(--gv-status-success-bg)',
            border: '1px solid rgba(0, 184, 169, 0.4)',
            color: 'var(--gv-color-smart-teal)',
            padding: '0.75rem 1rem',
            borderRadius: 'var(--gv-radius-md)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: '0.85rem',
            fontWeight: 600,
          }}
        >
          <CheckCircle2 size={16} />
          <span>Filtered insights exported as gridvision-energy-insights.csv.</span>
        </div>
      )}

      {/* Category Filter Pills */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--gv-text-muted)', textTransform: 'uppercase' }}>
          Filter Strategy:
        </span>
        {[
          { key: 'all', label: 'All Opportunities' },
          { key: 'peak_shaving', label: 'Peak Shaving' },
          { key: 'efficiency', label: 'Energy Efficiency' },
          { key: 'renewable', label: 'Renewable Integration' },
          { key: 'grid_stress', label: 'Grid Stress & Redistribution' },
        ].map((cat) => (
          <button
            key={cat.key}
            type="button"
            onClick={() => setCategoryFilter(cat.key)}
            style={{
              padding: '0.35rem 0.75rem',
              borderRadius: 'var(--gv-radius-sm)',
              fontSize: '0.75rem',
              fontWeight: categoryFilter === cat.key ? 700 : 500,
              background: categoryFilter === cat.key ? 'var(--gv-color-midnight-navy)' : 'var(--gv-bg-surface)',
              color: categoryFilter === cat.key ? '#FFFFFF' : 'var(--gv-text-secondary)',
              border: '1px solid var(--gv-border-subtle)',
              cursor: 'pointer',
            }}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Primary Insights Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '1.25rem' }}>
        {filtered.map((ins) => (
          <div
            key={ins.id}
            className="gv-card"
            style={{
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              borderLeft: `4px solid ${
                ins.category === 'peak_shaving'
                  ? 'var(--gv-color-grid-blue)'
                  : ins.category === 'efficiency'
                  ? 'var(--gv-color-smart-teal)'
                  : ins.category === 'renewable'
                  ? 'var(--gv-color-energy-amber)'
                  : 'var(--gv-status-danger)'
              }`,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.65rem' }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--gv-color-grid-blue)', textTransform: 'uppercase' }}>
                  {ins.category.replace('_', ' ')} • Sector: {ins.sector}
                </span>
                <StatusBadge status={ins.urgency} label={`${ins.urgency} Urgency`} />
              </div>

              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--gv-text-primary)', marginBottom: '0.45rem' }}>
                {ins.title}
              </h4>

              <p style={{ fontSize: '0.82rem', color: 'var(--gv-text-secondary)', lineHeight: 1.45, marginBottom: '0.85rem' }}>
                {ins.description}
              </p>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '0.5rem',
                  background: 'var(--gv-bg-surface-subtle)',
                  padding: '0.65rem 0.75rem',
                  borderRadius: 'var(--gv-radius-md)',
                  marginBottom: '0.85rem',
                }}
              >
                <div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--gv-text-muted)', fontWeight: 600 }}>PROJECTED IMPACT</div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--gv-color-grid-blue)' }}>{ins.impactMetric}</div>
                </div>
                <div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--gv-text-muted)', fontWeight: 600 }}>POTENTIAL VALUE</div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--gv-color-smart-teal)' }}>{ins.potentialValue}</div>
                </div>
              </div>
            </div>

            <div style={{ borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '0.75rem' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--gv-text-muted)', marginBottom: '0.35rem', fontWeight: 600 }}>
                ACTIONABLE RECOMMENDATION:
              </div>
              <p style={{ fontSize: '0.78rem', color: 'var(--gv-text-primary)', lineHeight: 1.4, fontStyle: 'italic' }}>
                {ins.actionableRecommendation}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Regional Load Redistribution & Wheeling Matrix */}
      <section className="gv-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
              <Layers size={18} color="var(--gv-color-energy-amber)" />
              <h3 className="gv-heading-2">Regional Energy Redistribution Matrix</h3>
            </div>
            <p className="gv-text-muted" style={{ marginTop: '0.2rem' }}>
              Identifies constrained substations and suggests inter-regional power wheeling to balance grid loads.
            </p>
          </div>
          <span className="gv-badge gv-badge-neutral">Government Grid Scope</span>
        </div>

        <div style={{ overflowX: 'auto', width: '100%' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ background: 'var(--gv-bg-surface-subtle)', borderBottom: '1px solid var(--gv-border-medium)' }}>
                <th style={{ padding: '0.65rem 0.75rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Region / Site</th>
                <th style={{ padding: '0.65rem 0.75rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Buildings</th>
                <th style={{ padding: '0.65rem 0.75rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Observed Load</th>
                <th style={{ padding: '0.65rem 0.75rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Peak Capacity Limit</th>
                <th style={{ padding: '0.65rem 0.75rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Stress Level</th>
                <th style={{ padding: '0.65rem 0.75rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Wheeling Recommendation</th>
              </tr>
            </thead>
            <tbody>
              {sites.slice(0, 6).map((site) => {
                const capacityLimit = site.totalDemandKwh * 1.25;
                const utilizationPct = (site.totalDemandKwh / capacityLimit) * 100;
                const isHighStress = utilizationPct > 80;

                return (
                  <tr key={site.siteId} style={{ borderBottom: '1px solid var(--gv-border-subtle)' }}>
                    <td style={{ padding: '0.75rem', fontWeight: 700, color: 'var(--gv-color-grid-blue)' }}>
                      Site {site.siteId}
                    </td>
                    <td style={{ padding: '0.75rem', color: 'var(--gv-text-secondary)' }}>
                      {site.buildingCount}
                    </td>
                    <td style={{ padding: '0.75rem', fontFamily: 'var(--gv-font-mono)' }}>
                      {site.totalDemandKwh.toLocaleString()} kWh
                    </td>
                    <td style={{ padding: '0.75rem', fontFamily: 'var(--gv-font-mono)', color: 'var(--gv-text-secondary)' }}>
                      {Math.round(capacityLimit).toLocaleString()} kWh
                    </td>
                    <td style={{ padding: '0.75rem' }}>
                      <span
                        style={{
                          padding: '0.2rem 0.5rem',
                          borderRadius: 'var(--gv-radius-sm)',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          background: isHighStress ? 'var(--gv-status-warning-bg)' : 'var(--gv-status-success-bg)',
                          color: isHighStress ? '#B45309' : 'var(--gv-color-smart-teal)',
                        }}
                      >
                        {utilizationPct.toFixed(0)}% Load Factor
                      </span>
                    </td>
                    <td style={{ padding: '0.75rem', fontSize: '0.75rem', color: isHighStress ? 'var(--gv-color-grid-blue)' : 'var(--gv-text-muted)' }}>
                      {isHighStress
                        ? `Reroute 8 MW surplus draw to neighboring Site Bear`
                        : `Adequate local reserve buffer available`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
