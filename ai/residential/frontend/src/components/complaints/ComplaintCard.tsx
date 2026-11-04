import React from 'react';
import {
  ZapOff,
  Activity,
  Gauge,
  Receipt,
  ShieldAlert,
  Sun,
  BatteryCharging,
  HelpCircle,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import { Complaint, SeverityLevel, ComplaintStatus } from '../../types/complaints';

interface ComplaintCardProps {
  complaint: Complaint;
  onClick: (complaint: Complaint) => void;
}

export const getCategoryIcon = (iconName?: string, categoryId?: string, size = 18) => {
  const key = (iconName || categoryId || '').toLowerCase();
  if (key.includes('power') || key.includes('interruption') || key.includes('outage')) {
    return <ZapOff size={size} color="#F59E0B" />;
  }
  if (key.includes('voltage') || key.includes('fluctuation') || key.includes('quality')) {
    return <Activity size={size} color="#087EBD" />;
  }
  if (key.includes('meter')) {
    return <Gauge size={size} color="#6366F1" />;
  }
  if (key.includes('bill') || key.includes('consumption')) {
    return <Receipt size={size} color="#10B981" />;
  }
  if (key.includes('safety')) {
    return <ShieldAlert size={size} color="#EF4444" />;
  }
  if (key.includes('solar') || key.includes('energy')) {
    return <Sun size={size} color="#F59E0B" />;
  }
  if (key.includes('ev') || key.includes('charging')) {
    return <BatteryCharging size={size} color="#00B8A9" />;
  }
  return <HelpCircle size={size} color="#64748B" />;
};

const getStatusBadge = (status: ComplaintStatus) => {
  switch (status) {
    case 'REGISTERED':
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            padding: '2px 8px',
            borderRadius: '999px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background: '#E0F7F5',
            color: '#0F766E',
            border: '1px solid #99F6E4',
          }}
        >
          <CheckCircle size={12} color="#0F766E" />
          Registered
        </span>
      );
    case 'INVALID':
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            padding: '2px 8px',
            borderRadius: '999px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background: '#FFF1F2',
            color: '#BE123C',
            border: '1px solid #FECDD3',
          }}
        >
          <XCircle size={12} color="#BE123C" />
          Invalid Complaint
        </span>
      );
    case 'VALIDATING':
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            padding: '2px 8px',
            borderRadius: '999px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background: '#FEF3C7',
            color: '#B45309',
            border: '1px solid #FCD34D',
          }}
        >
          <Clock size={12} color="#B45309" />
          Validating
        </span>
      );
    case 'SCORING':
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            padding: '2px 8px',
            borderRadius: '999px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background: '#E6F3FA',
            color: '#087EBD',
            border: '1px solid #BAE6FD',
          }}
        >
          <Clock size={12} color="#087EBD" />
          Scoring Severity
        </span>
      );
    case 'PROCESSING_FAILED':
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            padding: '2px 8px',
            borderRadius: '999px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background: '#F1F5F9',
            color: '#475569',
            border: '1px solid #CBD5E1',
          }}
        >
          <AlertTriangle size={12} color="#475569" />
          Processing Failed
        </span>
      );
    default:
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.3rem',
            padding: '2px 8px',
            borderRadius: '999px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background: '#F1F5F9',
            color: '#475569',
            border: '1px solid #CBD5E1',
          }}
        >
          <Clock size={12} />
          {status}
        </span>
      );
  }
};

const getSeverityBadge = (level?: SeverityLevel, score?: number) => {
  if (!level && score === undefined) return null;
  const scoreText = score !== undefined ? `${score.toFixed(1)}/100` : '';

  switch (level) {
    case 'Critical':
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            padding: '2px 7px',
            borderRadius: '6px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background: '#FEE2E2',
            color: '#991B1B',
            border: '1px solid #FCA5A5',
          }}
        >
          <ShieldAlert size={12} color="#991B1B" />
          Critical ({scoreText})
        </span>
      );
    case 'High':
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            padding: '2px 7px',
            borderRadius: '6px',
            fontSize: '0.72rem',
            fontWeight: 700,
            background: '#FFEDD5',
            color: '#C2410C',
            border: '1px solid #FDBA74',
          }}
        >
          <AlertTriangle size={12} color="#C2410C" />
          High ({scoreText})
        </span>
      );
    case 'Medium':
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            padding: '2px 7px',
            borderRadius: '6px',
            fontSize: '0.72rem',
            fontWeight: 600,
            background: '#FEF3C7',
            color: '#B45309',
            border: '1px solid #FCD34D',
          }}
        >
          Medium ({scoreText})
        </span>
      );
    case 'Low':
    default:
      return (
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            padding: '2px 7px',
            borderRadius: '6px',
            fontSize: '0.72rem',
            fontWeight: 600,
            background: '#E0F7F5',
            color: '#0F766E',
            border: '1px solid #99F6E4',
          }}
        >
          <ShieldCheck size={12} color="#0F766E" />
          Low ({scoreText})
        </span>
      );
  }
};

export const ComplaintCard: React.FC<ComplaintCardProps> = ({ complaint, onClick }) => {
  const formattedDate = new Date(complaint.created_at).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  const isInvalid = complaint.status === 'INVALID';
  const isRegistered = complaint.status === 'REGISTERED';

  return (
    <div
      onClick={() => onClick(complaint)}
      className="gv-complaint-card"
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        background: '#FFFFFF',
        borderRadius: '12px',
        padding: '1.25rem',
        border: '1px solid var(--gv-border-subtle)',
        borderLeft: isInvalid
          ? '4px solid #EF4444'
          : isRegistered
          ? '4px solid #00B8A9'
          : '4px solid #CBD5E1',
        boxShadow: 'var(--gv-shadow-sm)',
        cursor: 'pointer',
        transition: 'all 0.18s ease',
        minHeight: '220px',
      }}
    >
      <div>
        {/* Top Bar: Category, ID & Status */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: '0.75rem',
            marginBottom: '0.75rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div
              style={{
                width: '34px',
                height: '34px',
                borderRadius: '8px',
                background: 'var(--gv-bg-surface-subtle)',
                border: '1px solid var(--gv-border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              {getCategoryIcon(undefined, complaint.category_id, 18)}
            </div>
            <div>
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  color: 'var(--gv-text-secondary)',
                  letterSpacing: '0.03em',
                  display: 'block',
                }}
              >
                {complaint.category_label || complaint.category_id}
              </span>
              <span
                style={{
                  fontFamily: 'var(--gv-font-mono)',
                  fontSize: '0.72rem',
                  color: 'var(--gv-text-muted)',
                  display: 'block',
                }}
              >
                {complaint.id}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {complaint.severity_result && (
              getSeverityBadge(
                complaint.severity_result.severity_level,
                complaint.severity_result.severity_score
              )
            )}
            {getStatusBadge(complaint.status)}
          </div>
        </div>

        {/* Title */}
        <h3
          style={{
            fontSize: '0.98rem',
            fontWeight: 700,
            color: 'var(--gv-color-midnight-navy)',
            marginBottom: '0.35rem',
            lineHeight: 1.35,
          }}
        >
          {complaint.title}
        </h3>

        {/* Description Excerpt */}
        <p
          style={{
            fontSize: '0.8rem',
            color: 'var(--gv-text-secondary)',
            lineHeight: 1.5,
            marginBottom: '0.85rem',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {complaint.description}
        </p>

        {/* Contextual Status Snippet */}
        {isInvalid && complaint.validation_result && (
          <div
            style={{
              background: '#FFF1F2',
              border: '1px solid #FECDD3',
              borderRadius: '8px',
              padding: '0.65rem 0.85rem',
              marginBottom: '0.75rem',
              fontSize: '0.75rem',
              color: '#9F1239',
              lineHeight: 1.4,
            }}
          >
            <span style={{ fontWeight: 700, display: 'block', marginBottom: '2px' }}>
              Automated Validation Finding:
            </span>
            <span>
              {complaint.validation_result.reason || complaint.validation_result.explanation}
            </span>
          </div>
        )}

        {isRegistered && complaint.severity_result && (
          <div
            style={{
              background: '#F8FAFC',
              border: '1px solid var(--gv-border-subtle)',
              borderRadius: '8px',
              padding: '0.65rem 0.85rem',
              marginBottom: '0.75rem',
              fontSize: '0.75rem',
              color: 'var(--gv-text-secondary)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2px' }}>
              <span style={{ fontWeight: 600 }}>Severity Assessment:</span>
              <span style={{ fontWeight: 800, color: 'var(--gv-text-primary)' }}>
                {complaint.severity_result.severity_score.toFixed(1)} / 100
              </span>
            </div>
            <p
              style={{
                fontStyle: 'italic',
                color: 'var(--gv-text-muted)',
                fontSize: '0.72rem',
                margin: 0,
                display: '-webkit-box',
                WebkitLineClamp: 1,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}
            >
              "{complaint.severity_result.scoring_rationale}"
            </p>
          </div>
        )}
      </div>

      {/* Footer: Date and Action */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingTop: '0.75rem',
          borderTop: '1px solid var(--gv-border-subtle)',
          fontSize: '0.72rem',
          color: 'var(--gv-text-muted)',
        }}
      >
        <span>Submitted {formattedDate}</span>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            fontWeight: 700,
            color: 'var(--gv-color-smart-teal)',
          }}
        >
          <span>View Details</span>
          <ChevronRight size={14} />
        </div>
      </div>
    </div>
  );
};
