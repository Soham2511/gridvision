import React, { useState } from 'react';
import { AlertCircle, Filter } from 'lucide-react';
import { AnomalyItem } from '../../types/analytics';
import { StatusBadge } from '../common/StatusBadge';

interface AnomalyTableProps {
  anomalies: AnomalyItem[];
  onViewDetails?: (item: AnomalyItem) => void;
}

export const AnomalyTable: React.FC<AnomalyTableProps> = ({ anomalies, onViewDetails }) => {
  const [filterSeverity, setFilterSeverity] = useState<string>('all');

  const filtered = anomalies.filter((item) => {
    if (filterSeverity === 'all') return true;
    return item.severity === filterSeverity;
  });

  return (
    <div className="gv-card" style={{ display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '1rem',
          flexWrap: 'wrap',
          gap: '0.75rem',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            <AlertCircle size={18} color="var(--gv-status-danger)" />
            <h3 className="gv-heading-2">Detected Grid & Meter Anomalies</h3>
          </div>
          <p className="gv-text-muted" style={{ marginTop: '0.2rem' }}>
            Unusual consumption patterns and sensor telemetry deviations (Mock Samples)
          </p>
        </div>

        {/* Severity Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Filter size={14} color="var(--gv-text-muted)" />
          <span style={{ fontSize: '0.75rem', color: 'var(--gv-text-muted)', fontWeight: 600 }}>Filter:</span>
          {(['all', 'critical', 'warning', 'info'] as const).map((level) => (
            <button
              key={level}
              type="button"
              onClick={() => setFilterSeverity(level)}
              style={{
                fontSize: '0.72rem',
                fontWeight: filterSeverity === level ? 700 : 500,
                padding: '0.2rem 0.55rem',
                borderRadius: 'var(--gv-radius-sm)',
                background: filterSeverity === level ? 'var(--gv-bg-sidebar)' : 'var(--gv-bg-surface-subtle)',
                color: filterSeverity === level ? '#FFFFFF' : 'var(--gv-text-secondary)',
                border: '1px solid var(--gv-border-subtle)',
                cursor: 'pointer',
              }}
            >
              {level.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Table Container */}
      <div style={{ overflowX: 'auto', width: '100%' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.8rem' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--gv-border-medium)', background: 'var(--gv-bg-surface-subtle)' }}>
              <th style={{ padding: '0.65rem 0.75rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>Entity / Meter ID</th>
              <th style={{ padding: '0.65rem 0.75rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>Facility Name</th>
              <th style={{ padding: '0.65rem 0.75rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>Anomaly Type</th>
              <th style={{ padding: '0.65rem 0.75rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>Deviation</th>
              <th style={{ padding: '0.65rem 0.75rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>Observed / Baseline</th>
              <th style={{ padding: '0.65rem 0.75rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>Severity</th>
              <th style={{ padding: '0.65rem 0.75rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => {
              const isPositiveDev = item.deviationPercent > 0;
              return (
                <tr
                  key={item.id}
                  onClick={() => onViewDetails && onViewDetails(item)}
                  style={{
                    borderBottom: '1px solid var(--gv-border-subtle)',
                    transition: 'background var(--gv-transition-fast)',
                    cursor: onViewDetails ? 'pointer' : 'default',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--gv-bg-surface-subtle)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <td style={{ padding: '0.75rem', fontFamily: 'var(--gv-font-mono)', fontWeight: 600, color: 'var(--gv-color-grid-blue)' }}>
                    {item.entityId}
                  </td>
                  <td style={{ padding: '0.75rem', fontWeight: 600, color: 'var(--gv-text-primary)' }}>
                    {item.entityName}
                    <div style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)', fontWeight: 400 }}>
                      {item.entityType}
                    </div>
                  </td>
                  <td style={{ padding: '0.75rem', color: 'var(--gv-text-secondary)' }}>
                    {item.anomalyType}
                  </td>
                  <td style={{ padding: '0.75rem' }}>
                    <span
                      style={{
                        fontWeight: 700,
                        color: Math.abs(item.deviationPercent) > 30 ? 'var(--gv-status-danger)' : '#B45309',
                      }}
                    >
                      {isPositiveDev ? `+${item.deviationPercent}%` : `${item.deviationPercent}%`}
                    </span>
                  </td>
                  <td style={{ padding: '0.75rem', fontFamily: 'var(--gv-font-mono)', color: 'var(--gv-text-secondary)' }}>
                    <strong style={{ color: 'var(--gv-text-primary)' }}>{item.observedDemandKw} kW</strong> / {item.baselineDemandKw} kW
                  </td>
                  <td style={{ padding: '0.75rem' }}>
                    <StatusBadge status={item.severity} />
                  </td>
                  <td style={{ padding: '0.75rem' }}>
                    <StatusBadge status={item.status} showIcon={false} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: '0.85rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--gv-text-muted)' }}>
        <span>Showing {filtered.length} of {anomalies.length} anomaly records</span>
        <span>Detection algorithm: Isolation Forest + Rolling Threshold (Mock Baseline)</span>
      </div>
    </div>
  );
};
