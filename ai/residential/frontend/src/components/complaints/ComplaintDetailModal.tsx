import React, { useState } from 'react';
import {
  X,
  Copy,
  Check,
  CheckCircle,
  XCircle,
  Clock,
  ShieldAlert,
  PhoneCall,
  Activity,
  FileText,
  Info,
} from 'lucide-react';
import { Complaint } from '../../types/complaints';
import { getCategoryIcon } from './ComplaintCard';

interface ComplaintDetailModalProps {
  complaint: Complaint | null;
  onClose: () => void;
}

export const ComplaintDetailModal: React.FC<ComplaintDetailModalProps> = ({
  complaint,
  onClose,
}) => {
  const [copied, setCopied] = useState(false);

  if (!complaint) return null;

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(complaint, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formattedCreated = new Date(complaint.created_at).toLocaleString();
  const isInvalid = complaint.status === 'INVALID';
  const isRegistered = complaint.status === 'REGISTERED';
  const val = complaint.validation_result;
  const sev = complaint.severity_result;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(11, 31, 51, 0.65)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '1.5rem',
        fontFamily: 'var(--gv-font-sans)',
      }}
    >
      <div
        style={{
          background: '#FFFFFF',
          borderRadius: '16px',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
          border: '1px solid var(--gv-border-subtle)',
          width: '100%',
          maxWidth: '860px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '1.25rem 1.5rem',
            background: 'var(--gv-bg-surface-subtle)',
            borderBottom: '1px solid var(--gv-border-subtle)',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: '1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
            <div
              style={{
                width: '44px',
                height: '44px',
                borderRadius: '10px',
                background: '#FFFFFF',
                border: '1px solid var(--gv-border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: 'var(--gv-shadow-sm)',
                flexShrink: 0,
              }}
            >
              {getCategoryIcon(undefined, complaint.category_id, 24)}
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
                <span
                  style={{
                    fontFamily: 'var(--gv-font-mono)',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    color: 'var(--gv-text-muted)',
                    background: '#E2E8F0',
                    padding: '2px 6px',
                    borderRadius: '4px',
                  }}
                >
                  {complaint.id}
                </span>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    color: '#0F766E',
                    background: '#E0F7F5',
                    border: '1px solid #99F6E4',
                    padding: '2px 8px',
                    borderRadius: '999px',
                  }}
                >
                  {complaint.category_label || complaint.category_id}
                </span>
                {isRegistered && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: '#0F766E',
                      background: '#E0F7F5',
                      border: '1px solid #99F6E4',
                      padding: '2px 8px',
                      borderRadius: '999px',
                    }}
                  >
                    <CheckCircle size={12} color="#0F766E" /> Registered
                  </span>
                )}
                {isInvalid && (
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: '#BE123C',
                      background: '#FFF1F2',
                      border: '1px solid #FECDD3',
                      padding: '2px 8px',
                      borderRadius: '999px',
                    }}
                  >
                    <XCircle size={12} color="#BE123C" /> Invalid Complaint
                  </span>
                )}
              </div>
              <h2
                style={{
                  fontSize: '1.25rem',
                  fontWeight: 800,
                  color: 'var(--gv-color-midnight-navy)',
                  lineHeight: 1.3,
                  margin: 0,
                }}
              >
                {complaint.title}
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', fontSize: '0.75rem', color: 'var(--gv-text-muted)', marginTop: '0.25rem' }}>
                <span>Submitted: {formattedCreated}</span>
                <span>•</span>
                <span>Meter: <strong style={{ fontFamily: 'var(--gv-font-mono)', color: 'var(--gv-text-primary)' }}>{complaint.meter_id}</strong></span>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              onClick={handleCopyJson}
              title="Copy JSON representation"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.45rem 0.75rem',
                borderRadius: '6px',
                border: '1px solid var(--gv-border-medium)',
                background: '#FFFFFF',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: 'var(--gv-text-secondary)',
                cursor: 'pointer',
              }}
            >
              {copied ? <Check size={14} color="#00B8A9" /> : <Copy size={14} />}
              <span>{copied ? 'Copied' : 'Copy JSON'}</span>
            </button>
            <button
              onClick={onClose}
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '6px',
                border: 'none',
                background: 'transparent',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--gv-text-muted)',
                cursor: 'pointer',
              }}
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Modal Scrollable Body */}
        <div
          style={{
            padding: '1.5rem',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
            fontSize: '0.85rem',
            color: 'var(--gv-text-primary)',
          }}
        >
          {/* Description Block */}
          <div
            style={{
              background: '#FFFFFF',
              borderRadius: '12px',
              border: '1px solid var(--gv-border-subtle)',
              padding: '1.25rem',
              boxShadow: 'var(--gv-shadow-sm)',
            }}
          >
            <div
              style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                color: 'var(--gv-text-muted)',
                marginBottom: '0.5rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
              }}
            >
              <FileText size={14} /> Description & Resident Account
            </div>
            <p style={{ color: 'var(--gv-text-primary)', whiteSpace: 'pre-wrap', lineHeight: 1.55, margin: 0 }}>
              {complaint.description}
            </p>

            {/* Category-Specific Form Fields */}
            {complaint.category_data && Object.keys(complaint.category_data).length > 0 && (
              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--gv-border-subtle)' }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--gv-text-secondary)', display: 'block', marginBottom: '0.5rem' }}>
                  Category Specific Responses:
                </span>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '0.65rem',
                  }}
                >
                  {Object.entries(complaint.category_data).map(([k, v]) => (
                    <div
                      key={k}
                      style={{
                        padding: '0.65rem 0.85rem',
                        borderRadius: '8px',
                        background: 'var(--gv-bg-surface-subtle)',
                        border: '1px solid var(--gv-border-subtle)',
                        fontSize: '0.78rem',
                      }}
                    >
                      <span style={{ color: 'var(--gv-text-muted)', display: 'block', textTransform: 'capitalize', fontWeight: 600, marginBottom: '2px' }}>
                        {k.replace(/_/g, ' ')}
                      </span>
                      <span style={{ fontWeight: 700, color: 'var(--gv-text-primary)' }}>
                        {Array.isArray(v)
                          ? v.join(', ')
                          : typeof v === 'boolean'
                          ? v ? 'Yes' : 'No'
                          : String(v || '—')}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* AI Validation Outcome Block */}
          {val && (
            <div
              style={{
                borderRadius: '12px',
                padding: '1.25rem',
                border: val.outcome === 'INVALID'
                  ? '1px solid #FECDD3'
                  : val.outcome === 'PLAUSIBLE'
                  ? '1px solid #A7F3D0'
                  : '1px solid #FDE68A',
                background: val.outcome === 'INVALID'
                  ? '#FFF1F2'
                  : val.outcome === 'PLAUSIBLE'
                  ? '#ECFDF5'
                  : '#FFFBEB',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {val.outcome === 'INVALID' ? (
                    <XCircle color="#E11D48" size={22} style={{ flexShrink: 0 }} />
                  ) : val.outcome === 'PLAUSIBLE' ? (
                    <CheckCircle color="#059669" size={22} style={{ flexShrink: 0 }} />
                  ) : (
                    <Info color="#D97706" size={22} style={{ flexShrink: 0 }} />
                  )}
                  <div>
                    <h3
                      style={{
                        fontWeight: 800,
                        fontSize: '1rem',
                        margin: 0,
                        color: val.outcome === 'INVALID' ? '#9F1239' : val.outcome === 'PLAUSIBLE' ? '#065F46' : '#92400E',
                      }}
                    >
                      AI Validation:{' '}
                      {val.outcome === 'INVALID'
                        ? 'Demonstrably Contradicted (Invalid)'
                        : val.outcome === 'PLAUSIBLE'
                        ? 'Plausible (Confirmed by Telemetry or Precedence)'
                        : 'Inconclusive (Proceeding to Severity Assessment)'}
                    </h3>
                    <p style={{ fontSize: '0.75rem', opacity: 0.9, margin: '2px 0 0 0' }}>{val.reason}</p>
                  </div>
                </div>

                <span
                  style={{
                    fontFamily: 'var(--gv-font-mono)',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: '4px',
                    background: '#FFFFFF',
                    border: '1px solid currentColor',
                  }}
                >
                  {val.outcome}
                </span>
              </div>

              <p
                style={{
                  fontSize: '0.8rem',
                  lineHeight: 1.55,
                  background: 'rgba(255, 255, 255, 0.85)',
                  padding: '0.75rem 1rem',
                  borderRadius: '8px',
                  border: '1px solid rgba(0,0,0,0.06)',
                  marginBottom: '0.85rem',
                }}
              >
                {val.explanation}
              </p>

              {/* Data Coverage & Timestamps */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '1rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  paddingTop: '0.5rem',
                  borderTop: '1px solid rgba(0,0,0,0.08)',
                  flexWrap: 'wrap',
                }}
              >
                <span>Coverage: <strong>{val.data_coverage}</strong></span>
                {val.timestamps_checked && val.timestamps_checked.length > 0 && (
                  <span>Checked Intervals: <strong>{val.timestamps_checked.length} intervals</strong></span>
                )}
                <span>Validated at: {new Date(val.validated_at).toLocaleTimeString()}</span>
              </div>

              {/* Evidence Items Table */}
              {val.evidence_items && val.evidence_items.length > 0 && (
                <div
                  style={{
                    background: '#FFFFFF',
                    borderRadius: '8px',
                    border: '1px solid var(--gv-border-subtle)',
                    overflow: 'hidden',
                    boxShadow: 'var(--gv-shadow-sm)',
                    marginTop: '0.85rem',
                  }}
                >
                  <div
                    style={{
                      background: 'var(--gv-bg-surface-subtle)',
                      padding: '0.5rem 0.85rem',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      color: 'var(--gv-text-secondary)',
                      borderBottom: '1px solid var(--gv-border-subtle)',
                    }}
                  >
                    Telemetry Verification Evidence
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.78rem' }}>
                      <thead>
                        <tr style={{ background: '#F8FAFC', color: 'var(--gv-text-muted)', borderBottom: '1px solid var(--gv-border-subtle)' }}>
                          <th style={{ padding: '0.55rem 0.75rem', fontWeight: 600 }}>Telemetry Metric</th>
                          <th style={{ padding: '0.55rem 0.75rem', fontWeight: 600 }}>Observed Reading</th>
                          <th style={{ padding: '0.55rem 0.75rem', fontWeight: 600 }}>Expected Reference</th>
                          <th style={{ padding: '0.55rem 0.75rem', fontWeight: 600 }}>Evaluation Finding</th>
                        </tr>
                      </thead>
                      <tbody>
                        {val.evidence_items.map((item, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid var(--gv-border-subtle)' }}>
                            <td style={{ padding: '0.55rem 0.75rem', fontWeight: 700 }}>
                              {item.metric_name}
                              <span style={{ display: 'block', fontSize: '0.68rem', color: 'var(--gv-text-muted)', fontWeight: 400 }}>
                                {item.source_tool}
                              </span>
                            </td>
                            <td style={{ padding: '0.55rem 0.75rem', fontFamily: 'var(--gv-font-mono)' }}>
                              {item.observed_value !== undefined ? String(item.observed_value) : '—'}
                            </td>
                            <td style={{ padding: '0.55rem 0.75rem', fontFamily: 'var(--gv-font-mono)', color: 'var(--gv-text-muted)' }}>
                              {item.expected_or_contradicting_value !== undefined ? String(item.expected_or_contradicting_value) : '—'}
                            </td>
                            <td style={{ padding: '0.55rem 0.75rem' }}>
                              {item.finding}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Customer Care Escalation Banner for Invalid Complaints */}
          {isInvalid && complaint.customer_care_escalation && (
            <div
              style={{
                background: '#FEF3C7',
                border: '1px solid #FCD34D',
                borderRadius: '12px',
                padding: '1.15rem',
                color: '#78350F',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem',
              }}
            >
              <PhoneCall color="#B45309" size={22} style={{ flexShrink: 0, marginTop: '2px' }} />
              <div style={{ fontSize: '0.8rem', lineHeight: 1.5 }}>
                <h4 style={{ fontWeight: 800, fontSize: '0.92rem', color: '#78350F', margin: '0 0 0.25rem 0' }}>
                  Customer Care Escalation Available
                </h4>
                <p style={{ margin: 0 }}>{complaint.customer_care_escalation.advisory}</p>
                {complaint.customer_care_escalation.customer_care_contact && (
                  <div style={{ marginTop: '0.5rem', fontWeight: 700 }}>
                    Support Helpline: {complaint.customer_care_escalation.customer_care_contact}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Severity Scoring Section */}
          {sev && (
            <div
              style={{
                background: '#FFFFFF',
                borderRadius: '12px',
                border: '1px solid var(--gv-border-subtle)',
                padding: '1.25rem',
                boxShadow: 'var(--gv-shadow-sm)',
                display: 'flex',
                flexDirection: 'column',
                gap: '1rem',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingBottom: '0.75rem',
                  borderBottom: '1px solid var(--gv-border-subtle)',
                  flexWrap: 'wrap',
                  gap: '0.75rem',
                }}
              >
                <div>
                  <h3
                    style={{
                      fontWeight: 800,
                      fontSize: '1.05rem',
                      color: 'var(--gv-color-midnight-navy)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      margin: 0,
                    }}
                  >
                    <Activity size={20} color="#00B8A9" />
                    Severity Assessment & Benchmark Scoring
                  </h3>
                  <span style={{ fontSize: '0.72rem', color: 'var(--gv-text-muted)', fontFamily: 'var(--gv-font-mono)' }}>
                    Benchmark: {sev.benchmark_version}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                  <div style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--gv-text-muted)', display: 'block' }}>
                      Severity Score
                    </span>
                    <span style={{ fontSize: '1.75rem', fontWeight: 900, color: 'var(--gv-text-primary)' }}>
                      {sev.severity_score.toFixed(1)}
                      <span style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--gv-text-muted)' }}> / 100</span>
                    </span>
                  </div>
                  <div
                    style={{
                      padding: '0.45rem 0.85rem',
                      borderRadius: '8px',
                      fontSize: '0.85rem',
                      fontWeight: 800,
                      background: sev.severity_level === 'Critical' ? '#FEE2E2' : sev.severity_level === 'High' ? '#FFEDD5' : sev.severity_level === 'Medium' ? '#FEF3C7' : '#E0F7F5',
                      color: sev.severity_level === 'Critical' ? '#991B1B' : sev.severity_level === 'High' ? '#C2410C' : sev.severity_level === 'Medium' ? '#B45309' : '#0F766E',
                      border: '1px solid currentColor',
                    }}
                  >
                    {sev.severity_level} Priority
                  </div>
                </div>
              </div>

              {/* Rationale */}
              <div
                style={{
                  padding: '0.85rem 1rem',
                  borderRadius: '8px',
                  background: 'var(--gv-bg-surface-subtle)',
                  border: '1px solid var(--gv-border-subtle)',
                  fontSize: '0.8rem',
                  lineHeight: 1.5,
                }}
              >
                <span style={{ fontWeight: 700, color: 'var(--gv-text-primary)', display: 'block', marginBottom: '2px' }}>
                  Scoring Rationale:
                </span>
                {sev.scoring_rationale}
              </div>

              {/* Safety Override Notice */}
              {sev.factor_breakdown?.safety_override_applied && (
                <div
                  style={{
                    padding: '0.85rem 1rem',
                    borderRadius: '8px',
                    background: '#FEF2F2',
                    border: '1px solid #FECACA',
                    fontSize: '0.8rem',
                    color: '#991B1B',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '0.5rem',
                  }}
                >
                  <ShieldAlert size={18} color="#DC2626" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <span style={{ fontWeight: 800 }}>Statutory Safety Override Applied:</span>
                    <p style={{ margin: '2px 0 0 0' }}>{sev.factor_breakdown.override_reason || 'Safety hazard automatically clamped to mandatory priority floor.'}</p>
                  </div>
                </div>
              )}

              {/* Factor Breakdown Bars */}
              {sev.factor_breakdown && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', paddingTop: '0.5rem' }}>
                  <span style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--gv-text-muted)' }}>
                    Weighted Benchmark Factors
                  </span>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.85rem' }}>
                    {/* Safety Risk */}
                    <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--gv-bg-surface-subtle)', border: '1px solid var(--gv-border-subtle)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '0.78rem' }}>
                        <span style={{ fontWeight: 600 }}>Safety Risk (35%)</span>
                        <span style={{ fontWeight: 700, fontFamily: 'var(--gv-font-mono)' }}>{sev.factor_breakdown.safety_risk.toFixed(1)}/100</span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: '#E2E8F0', borderRadius: '999px', overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(100, Math.max(0, sev.factor_breakdown.safety_risk))}%`, height: '100%', background: '#EF4444', borderRadius: '999px' }} />
                      </div>
                    </div>

                    {/* Disruption Extent */}
                    <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--gv-bg-surface-subtle)', border: '1px solid var(--gv-border-subtle)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '0.78rem' }}>
                        <span style={{ fontWeight: 600 }}>Disruption Extent (25%)</span>
                        <span style={{ fontWeight: 700, fontFamily: 'var(--gv-font-mono)' }}>{sev.factor_breakdown.disruption_extent.toFixed(1)}/100</span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: '#E2E8F0', borderRadius: '999px', overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(100, Math.max(0, sev.factor_breakdown.disruption_extent))}%`, height: '100%', background: '#F97316', borderRadius: '999px' }} />
                      </div>
                    </div>

                    {/* Duration Factor */}
                    <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--gv-bg-surface-subtle)', border: '1px solid var(--gv-border-subtle)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '0.78rem' }}>
                        <span style={{ fontWeight: 600 }}>Duration Factor (15%)</span>
                        <span style={{ fontWeight: 700, fontFamily: 'var(--gv-font-mono)' }}>{sev.factor_breakdown.duration_factor.toFixed(1)}/100</span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: '#E2E8F0', borderRadius: '999px', overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(100, Math.max(0, sev.factor_breakdown.duration_factor))}%`, height: '100%', background: '#F59E0B', borderRadius: '999px' }} />
                      </div>
                    </div>

                    {/* Recurrence Factor */}
                    <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--gv-bg-surface-subtle)', border: '1px solid var(--gv-border-subtle)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '0.78rem' }}>
                        <span style={{ fontWeight: 600 }}>Recurrence (15%)</span>
                        <span style={{ fontWeight: 700, fontFamily: 'var(--gv-font-mono)' }}>{sev.factor_breakdown.recurrence_factor.toFixed(1)}/100</span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: '#E2E8F0', borderRadius: '999px', overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(100, Math.max(0, sev.factor_breakdown.recurrence_factor))}%`, height: '100%', background: '#6366F1', borderRadius: '999px' }} />
                      </div>
                    </div>

                    {/* Essential Services */}
                    <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'var(--gv-bg-surface-subtle)', border: '1px solid var(--gv-border-subtle)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '0.78rem' }}>
                        <span style={{ fontWeight: 600 }}>Essential Services (10%)</span>
                        <span style={{ fontWeight: 700, fontFamily: 'var(--gv-font-mono)' }}>{sev.factor_breakdown.essential_services_impact.toFixed(1)}/100</span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: '#E2E8F0', borderRadius: '999px', overflow: 'hidden' }}>
                        <div style={{ width: `${Math.min(100, Math.max(0, sev.factor_breakdown.essential_services_impact))}%`, height: '100%', background: '#00B8A9', borderRadius: '999px' }} />
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Status History Timeline */}
          {complaint.status_history && complaint.status_history.length > 0 && (
            <div
              style={{
                background: '#FFFFFF',
                borderRadius: '12px',
                border: '1px solid var(--gv-border-subtle)',
                padding: '1.25rem',
                boxShadow: 'var(--gv-shadow-sm)',
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--gv-text-muted)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Clock size={14} /> Audit Trail & Status History
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', paddingLeft: '0.5rem' }}>
                {complaint.status_history.map((h, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', fontSize: '0.78rem' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#00B8A9', marginTop: '5px', flexShrink: 0 }} />
                    <div>
                      <div style={{ fontWeight: 700, color: 'var(--gv-text-primary)' }}>
                        {h.from_status ? `${h.from_status} → ` : ''}
                        <span style={{ color: '#00B8A9' }}>{h.to_status}</span>
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)', fontFamily: 'var(--gv-font-mono)' }}>
                        {new Date(h.timestamp).toLocaleString()}
                      </div>
                      {h.note && <div style={{ color: 'var(--gv-text-secondary)', marginTop: '2px' }}>{h.note}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '1rem 1.5rem',
            background: 'var(--gv-bg-surface-subtle)',
            borderTop: '1px solid var(--gv-border-subtle)',
            display: 'flex',
            justifyContent: 'flex-end',
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '0.55rem 1.25rem',
              borderRadius: '8px',
              background: 'var(--gv-color-midnight-navy)',
              color: '#FFFFFF',
              fontWeight: 700,
              fontSize: '0.8rem',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            Close Details
          </button>
        </div>
      </div>
    </div>
  );
};
