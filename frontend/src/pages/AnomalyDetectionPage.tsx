import React, { useEffect, useState } from 'react';
import { PageHeader } from '../components/common/PageHeader';
import { StatusBadge } from '../components/common/StatusBadge';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { ErrorState } from '../components/common/ErrorState';
import { analyticsService } from '../services/analyticsService';
import { AnomalyEvent } from '../types/analytics';
import {
  AlertCircle,
  Search,
  X,
  ShieldAlert,
  Info,
} from 'lucide-react';

export const AnomalyDetectionPage: React.FC = () => {
  const [anomalies, setAnomalies] = useState<AnomalyEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Search & Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  // Selected event for deep diagnostic drawer
  const [selectedEvent, setSelectedEvent] = useState<AnomalyEvent | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const res = await analyticsService.getAnomalyEvents();
        setAnomalies(res);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load anomalies.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleStatusUpdate = async (eventId: string, newStatus: AnomalyEvent['status']) => {
    // Optimistic UI update
    setAnomalies((prev) =>
      prev.map((item) => (item.id === eventId ? { ...item, status: newStatus } : item))
    );
    if (selectedEvent && selectedEvent.id === eventId) {
      setSelectedEvent((prev) => (prev ? { ...prev, status: newStatus } : null));
    }

    try {
      await analyticsService.updateAnomalyStatus(eventId, newStatus);
    } catch (err) {
      console.error('Failed to update anomaly status via API:', err);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <PageHeader title="Anomaly Detection & Grid Integrity" description="Auditing telemetry..." />
        <LoadingSkeleton height="120px" count={3} />
      </div>
    );
  }

  if (error) {
    return <ErrorState title="Anomaly Telemetry Offline" message={error} />;
  }

  const filtered = anomalies.filter((item) => {
    const matchesSearch =
      item.entityId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.entityName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.anomalyType.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesSeverity = severityFilter === 'all' || item.severity === severityFilter;
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;

    return matchesSearch && matchesSeverity && matchesStatus;
  });

  const criticalCount = anomalies.filter((a) => a.severity === 'critical').length;
  const warningCount = anomalies.filter((a) => a.severity === 'warning').length;
  const resolvedCount = anomalies.filter((a) => a.status === 'resolved').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', position: 'relative' }}>
      {/* Page Header */}
      <PageHeader
        title="Anomaly Detection & Grid Integrity"
        description="Continuous statistical monitoring, unsupervised outlier scoring, and root-cause diagnostics across substations and meters."
        badge={
          <span className="gv-badge gv-badge-danger">
            <AlertCircle size={12} />
            <span>{anomalies.filter((a) => a.status !== 'resolved').length} Active Alerts</span>
          </span>
        }
      />

      {/* Summary KPI Cards */}
      <section className="gv-grid-kpis">
        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Total Flagged Events</span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-text-primary)', marginTop: '0.35rem' }}>
            {anomalies.length}
          </div>
          <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Observed in current rolling audit</p>
        </div>

        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Critical Grid Alarms</span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-status-danger)', marginTop: '0.35rem' }}>
            {criticalCount}
          </div>
          <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>&gt;40% deviation from baseline</p>
        </div>

        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Baseload Inefficiencies</span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#B45309', marginTop: '0.35rem' }}>
            {warningCount}
          </div>
          <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Unoccupied hours drift & sensor drops</p>
        </div>

        <div className="gv-card">
          <span className="gv-text-muted" style={{ fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase' }}>Resolved & Cleared</span>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--gv-color-smart-teal)', marginTop: '0.35rem' }}>
            {resolvedCount}
          </div>
          <p className="gv-text-muted" style={{ fontSize: '0.72rem', marginTop: '0.35rem' }}>Verified and closed by dispatch</p>
        </div>
      </section>

      {/* Search & Filter Bar */}
      <div
        className="gv-card"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        {/* Search Input */}
        <div style={{ position: 'relative', minWidth: '280px', flex: 1 }}>
          <Search size={15} color="var(--gv-text-muted)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
          <input
            type="text"
            placeholder="Search entity ID, facility name, or anomaly pattern..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              padding: '0.45rem 0.75rem 0.45rem 2rem',
              borderRadius: 'var(--gv-radius-md)',
              border: '1px solid var(--gv-border-medium)',
              fontSize: '0.82rem',
              color: 'var(--gv-text-primary)',
            }}
          />
        </div>

        {/* Severity Filter Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--gv-text-muted)' }}>Severity:</span>
          {(['all', 'critical', 'warning', 'info'] as const).map((sev) => (
            <button
              key={sev}
              type="button"
              onClick={() => setSeverityFilter(sev)}
              style={{
                fontSize: '0.72rem',
                fontWeight: severityFilter === sev ? 700 : 500,
                padding: '0.25rem 0.65rem',
                borderRadius: 'var(--gv-radius-sm)',
                background: severityFilter === sev ? 'var(--gv-color-midnight-navy)' : 'var(--gv-bg-surface-subtle)',
                color: severityFilter === sev ? '#FFFFFF' : 'var(--gv-text-secondary)',
                border: '1px solid var(--gv-border-subtle)',
                cursor: 'pointer',
              }}
            >
              {sev.toUpperCase()}
            </button>
          ))}
        </div>

        {/* Status Filter Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
          <span style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--gv-text-muted)' }}>Status:</span>
          {(['all', 'investigating', 'confirmed', 'resolved'] as const).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setStatusFilter(st)}
              style={{
                fontSize: '0.72rem',
                fontWeight: statusFilter === st ? 700 : 500,
                padding: '0.25rem 0.65rem',
                borderRadius: 'var(--gv-radius-sm)',
                background: statusFilter === st ? 'var(--gv-color-smart-teal)' : 'var(--gv-bg-surface-subtle)',
                color: statusFilter === st ? '#FFFFFF' : 'var(--gv-text-secondary)',
                border: '1px solid var(--gv-border-subtle)',
                cursor: 'pointer',
              }}
            >
              {st.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Comprehensive Anomaly Table */}
      <div className="gv-card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto', width: '100%' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.8rem' }}>
            <thead>
              <tr style={{ background: 'var(--gv-bg-surface-subtle)', borderBottom: '1px solid var(--gv-border-medium)' }}>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Entity ID</th>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Facility / Feeder</th>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Anomaly Pattern</th>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Observed vs Baseline</th>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Deviation</th>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Severity</th>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--gv-text-secondary)' }}>Status</th>
                <th style={{ padding: '0.75rem 1rem', fontWeight: 700, color: 'var(--gv-text-secondary)', textAlign: 'right' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr
                  key={item.id}
                  style={{
                    borderBottom: '1px solid var(--gv-border-subtle)',
                    transition: 'background var(--gv-transition-fast)',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--gv-bg-surface-subtle)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <td style={{ padding: '0.85rem 1rem', fontFamily: 'var(--gv-font-mono)', fontWeight: 700, color: 'var(--gv-color-grid-blue)' }}>
                    {item.entityId}
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <div style={{ fontWeight: 600, color: 'var(--gv-text-primary)' }}>{item.entityName}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)' }}>{item.entityType}</div>
                  </td>
                  <td style={{ padding: '0.85rem 1rem', color: 'var(--gv-text-secondary)' }}>
                    {item.anomalyType}
                  </td>
                  <td style={{ padding: '0.85rem 1rem', fontFamily: 'var(--gv-font-mono)' }}>
                    <strong style={{ color: 'var(--gv-text-primary)' }}>{item.observedDemandKw} kW</strong> / {item.baselineDemandKw} kW
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <span style={{ fontWeight: 700, color: item.deviationPercent > 30 ? 'var(--gv-status-danger)' : '#B45309' }}>
                      {item.deviationPercent > 0 ? `+${item.deviationPercent}%` : `${item.deviationPercent}%`}
                    </span>
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <StatusBadge status={item.severity} />
                  </td>
                  <td style={{ padding: '0.85rem 1rem' }}>
                    <StatusBadge status={item.status} showIcon={false} />
                  </td>
                  <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                    <button
                      type="button"
                      onClick={() => setSelectedEvent(item)}
                      style={{
                        padding: '0.35rem 0.75rem',
                        borderRadius: 'var(--gv-radius-sm)',
                        background: 'rgba(8, 126, 189, 0.08)',
                        color: 'var(--gv-color-grid-blue)',
                        border: '1px solid rgba(8, 126, 189, 0.25)',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      Investigate →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Slide-Over Anomaly Diagnostic Drawer */}
      {selectedEvent && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            width: '440px',
            maxWidth: '100vw',
            height: '100vh',
            background: 'var(--gv-bg-surface)',
            borderLeft: '1px solid var(--gv-border-accent)',
            boxShadow: 'var(--gv-shadow-lg)',
            zIndex: 100,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            padding: '1.5rem',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', borderBottom: '1px solid var(--gv-border-subtle)', paddingBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                <ShieldAlert size={20} color="var(--gv-status-danger)" />
                <h3 className="gv-heading-2">Anomaly Diagnostic Panel</h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedEvent(null)}
                style={{ cursor: 'pointer', color: 'var(--gv-text-muted)' }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <div>
                <div style={{ fontFamily: 'var(--gv-font-mono)', fontSize: '0.85rem', fontWeight: 700, color: 'var(--gv-color-grid-blue)' }}>
                  {selectedEvent.entityId}
                </div>
                <div style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--gv-text-primary)' }}>
                  {selectedEvent.entityName}
                </div>
              </div>
              <StatusBadge status={selectedEvent.severity} />
            </div>

            <div
              style={{
                padding: '0.85rem',
                background: 'var(--gv-bg-surface-subtle)',
                borderRadius: 'var(--gv-radius-md)',
                marginBottom: '1.25rem',
              }}
            >
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '0.5rem' }}>
                <div>
                  <span style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)', fontWeight: 600 }}>OBSERVED LOAD</span>
                  <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--gv-text-primary)' }}>
                    {selectedEvent.observedDemandKw} kW
                  </div>
                </div>
                <div>
                  <span style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)', fontWeight: 600 }}>BASELINE NORM</span>
                  <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--gv-text-secondary)' }}>
                    {selectedEvent.baselineDemandKw} kW
                  </div>
                </div>
              </div>
              <div style={{ fontSize: '0.75rem', color: selectedEvent.deviationPercent > 30 ? 'var(--gv-status-danger)' : '#B45309', fontWeight: 700 }}>
                Deviation: {selectedEvent.deviationPercent > 0 ? `+${selectedEvent.deviationPercent}%` : `${selectedEvent.deviationPercent}%`} from expected threshold
              </div>
            </div>

            {/* Root Cause Analysis */}
            <div style={{ marginBottom: '1.25rem' }}>
              <h4 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--gv-text-secondary)', textTransform: 'uppercase', marginBottom: '0.35rem' }}>
                Algorithmic Root Cause Diagnosis
              </h4>
              <p style={{ fontSize: '0.82rem', color: 'var(--gv-text-primary)', lineHeight: 1.45, background: 'rgba(8, 126, 189, 0.05)', padding: '0.75rem', borderRadius: 'var(--gv-radius-md)', border: '1px solid rgba(8, 126, 189, 0.15)' }}>
                {selectedEvent.rootCauseDiagnosis || 'Automated feature attribution indicates atypical interval draw.'}
              </p>
            </div>

            {/* Recommended Action */}
            <div style={{ marginBottom: '1.25rem' }}>
              <h4 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--gv-text-secondary)', textTransform: 'uppercase', marginBottom: '0.35rem' }}>
                Recommended Corrective Action
              </h4>
              <p style={{ fontSize: '0.82rem', color: 'var(--gv-text-primary)', lineHeight: 1.45, background: 'rgba(0, 184, 169, 0.05)', padding: '0.75rem', borderRadius: 'var(--gv-radius-md)', border: '1px solid rgba(0, 184, 169, 0.15)' }}>
                {selectedEvent.recommendedAction || 'Schedule physical meter audit and verify current transformer connections.'}
              </p>
            </div>
          </div>

          {/* Status Controls */}
          <div style={{ borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--gv-text-muted)', textTransform: 'uppercase' }}>
              Update Investigation Status
            </span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => handleStatusUpdate(selectedEvent.id, 'confirmed')}
                style={{
                  padding: '0.5rem',
                  borderRadius: 'var(--gv-radius-md)',
                  background: 'var(--gv-status-warning-bg)',
                  color: '#B45309',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                  fontWeight: 700,
                  fontSize: '0.78rem',
                  cursor: 'pointer',
                }}
              >
                Confirm Anomaly
              </button>
              <button
                type="button"
                onClick={() => handleStatusUpdate(selectedEvent.id, 'resolved')}
                style={{
                  padding: '0.5rem',
                  borderRadius: 'var(--gv-radius-md)',
                  background: 'var(--gv-status-success-bg)',
                  color: 'var(--gv-color-smart-teal)',
                  border: '1px solid rgba(0, 184, 169, 0.3)',
                  fontWeight: 700,
                  fontSize: '0.78rem',
                  cursor: 'pointer',
                }}
              >
                Mark as Resolved
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Methodology Disclaimer */}
      <div
        style={{
          background: 'rgba(8, 126, 189, 0.05)',
          border: '1px solid rgba(8, 126, 189, 0.2)',
          borderRadius: 'var(--gv-radius-md)',
          padding: '0.75rem 1rem',
          fontSize: '0.75rem',
          color: 'var(--gv-color-grid-blue)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
        }}
      >
        <Info size={16} style={{ flexShrink: 0 }} />
        <span>
          <strong>Detection Methodology:</strong> GridVision couples Isolation Forest ensemble trees with adaptive rolling standard deviation thresholds (±3σ)
          to flag both point anomalies and structural baseload drift.
        </span>
      </div>
    </div>
  );
};
