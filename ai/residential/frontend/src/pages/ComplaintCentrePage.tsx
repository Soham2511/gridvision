import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Plus,
  RefreshCw,
  Search,
  CheckCircle,
  XCircle,
  FileText,
  AlertCircle,
  Sparkles,
  Clock,
  Calendar,
  Users,
  ArrowUpDown,
  Tag,
  Shield,
  Check,
} from 'lucide-react';
import { Complaint, ComplaintCategory } from '../types/complaints';
import { complaintService } from '../services/complaintService';
import {
  ComplaintCard,
  ComplaintDetailModal,
  ComplaintRegistrationModal,
} from '../components/complaints';
import { usePersona } from '../../../../../frontend/src/context';

type StatusFilterType = 'ALL' | 'PENDING' | 'RESOLVED' | 'REJECTED';
type PersonaFilterType = 'ALL' | 'RESIDENTIAL' | 'COMMERCIAL' | 'GOVERNMENT';
type DurationFilterType = 'ALL' | 'TODAY' | 'WEEK' | 'MONTH' | 'QUARTER';
type SortOptionType = 'date_desc' | 'date_asc' | 'severity_desc' | 'severity_asc';

export const ComplaintCentrePage: React.FC = () => {
  const { currentPersona, activeEntity } = usePersona();
  const isGovernment = currentPersona === 'government';

  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [categories, setCategories] = useState<ComplaintCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  // Filters & Search & Sort
  const [statusFilter, setStatusFilter] = useState<StatusFilterType>('ALL');
  const [personaFilter, setPersonaFilter] = useState<PersonaFilterType>('ALL');
  const [durationFilter, setDurationFilter] = useState<DurationFilterType>('ALL');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [sortOption, setSortOption] = useState<SortOptionType>('date_desc');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [selectedComplaint, setSelectedComplaint] = useState<Complaint | null>(null);

  // Load Categories
  const fetchCategories = useCallback(async () => {
    setCategoriesLoading(true);
    try {
      const seg = isGovernment ? 'RESIDENTIAL' : currentPersona === 'commercial' ? 'COMMERCIAL' : 'RESIDENTIAL';
      const data = await complaintService.getCategories(seg);
      setCategories(data);
    } catch (err: any) {
      console.error('Failed to load complaint categories:', err);
    } finally {
      setCategoriesLoading(false);
    }
  }, [isGovernment, currentPersona]);

  // Load Complaints: Government sees all grid complaints; citizens see ONLY their own
  const fetchComplaints = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const targetEntity = isGovernment ? undefined : activeEntity;
      const data = await complaintService.getComplaints(undefined, undefined, undefined, targetEntity);
      setComplaints(data);
    } catch (err: any) {
      console.error('Failed to load complaints:', err);
      setError(err?.message || 'Unable to retrieve complaints. Please ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  }, [isGovernment, activeEntity]);

  useEffect(() => {
    fetchCategories();
    fetchComplaints();
  }, [fetchCategories, fetchComplaints, activeEntity, currentPersona]);

  const handleComplaintSubmitted = (newComplaint: Complaint) => {
    setComplaints((prev) => [newComplaint, ...prev.filter((c) => c.id !== newComplaint.id)]);
  };

  const handleStatusUpdate = async (complaintId: string, newStatus: string, note?: string) => {
    try {
      const updated = await complaintService.updateComplaintStatus(complaintId, newStatus, note);
      setComplaints((prev) =>
        prev.map((c) => (c.id === complaintId ? { ...c, status: updated.status } : c))
      );
      setSelectedComplaint((prev) =>
        prev && prev.id === complaintId ? { ...prev, status: updated.status } : prev
      );
      setActionFeedback(
        `Ticket #${complaintId} marked as ${newStatus}. Website notification created & customer email dispatched.`
      );
      setTimeout(() => setActionFeedback(null), 6000);
    } catch (err: any) {
      console.error('Failed to update complaint status:', err);
      alert(`Could not update status: ${err?.message || 'Unknown error'}`);
    }
  };

  // Helper for Severity rank calculation
  const getSeverityScore = (c: Complaint): number => {
    if (c.severity_result?.severity_score != null) {
      return c.severity_result.severity_score;
    }
    const level = (c.severity_result?.severity_level || '').toLowerCase();
    if (level === 'critical') return 400;
    if (level === 'high') return 300;
    if (level === 'medium') return 200;
    if (level === 'low') return 100;
    return 0;
  };

  // Helper for Duration filter
  const matchesDuration = (createdAtStr: string, dur: DurationFilterType): boolean => {
    if (dur === 'ALL') return true;
    const time = new Date(createdAtStr).getTime();
    if (isNaN(time)) return true;
    const diffMs = Date.now() - time;
    if (dur === 'TODAY') return diffMs <= 24 * 60 * 60 * 1000;
    if (dur === 'WEEK') return diffMs <= 7 * 24 * 60 * 60 * 1000;
    if (dur === 'MONTH') return diffMs <= 30 * 24 * 60 * 60 * 1000;
    if (dur === 'QUARTER') return diffMs <= 90 * 24 * 60 * 60 * 1000;
    return true;
  };

  // Extract unique category options from complaints and known categories
  const availableCategories = useMemo(() => {
    const map = new Map<string, string>();
    categories.forEach((cat) => map.set(cat.category_id, cat.label));
    complaints.forEach((c) => {
      if (c.category_id && !map.has(c.category_id)) {
        map.set(c.category_id, c.category_label || c.category_id);
      }
    });
    return Array.from(map.entries()).map(([id, label]) => ({ id, label }));
  }, [categories, complaints]);

  // Status mapping
  const isPendingStatus = (status: string) =>
    ['REGISTERED', 'SUBMITTED', 'VALIDATING', 'SCORING'].includes(status.toUpperCase());
  const isResolvedStatus = (status: string) => status.toUpperCase() === 'RESOLVED';
  const isRejectedStatus = (status: string) =>
    ['REJECTED', 'INVALID'].includes(status.toUpperCase());

  // Filtered and sorted complaints list
  const filteredComplaints = useMemo(() => {
    let result = complaints.filter((c) => {
      // 1. Strict user-specific isolation for non-government personas
      if (!isGovernment && activeEntity) {
        const cleanTarget = activeEntity.replace(/^(METER-|usr-)/i, '').toLowerCase();
        const cid = (c.customer_id || '').replace(/^(METER-|usr-)/i, '').toLowerCase();
        const mid = (c.meter_id || '').replace(/^(METER-|usr-)/i, '').toLowerCase();
        if (cid !== cleanTarget && mid !== cleanTarget) {
          return false;
        }
      }

      // 2. Status Filter
      if (statusFilter === 'PENDING' && !isPendingStatus(c.status)) return false;
      if (statusFilter === 'RESOLVED' && !isResolvedStatus(c.status)) return false;
      if (statusFilter === 'REJECTED' && !isRejectedStatus(c.status)) return false;

      // 3. Persona Filter (Government view)
      if (isGovernment && personaFilter !== 'ALL') {
        const seg = (c.customer_segment || '').toUpperCase();
        if (seg !== personaFilter) return false;
      }

      // 4. Duration Filter
      if (!matchesDuration(c.created_at, durationFilter)) return false;

      // 5. Category Filter
      if (categoryFilter !== 'ALL') {
        if (c.category_id !== categoryFilter && c.category_label !== categoryFilter) return false;
      }

      // 6. Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesTitle = c.title.toLowerCase().includes(q);
        const matchesCategory = (c.category_label || c.category_id || '').toLowerCase().includes(q);
        const matchesId = c.id.toLowerCase().includes(q);
        const matchesDesc = (c.description || '').toLowerCase().includes(q);
        const matchesCust = (c.customer_id || '').toLowerCase().includes(q);
        const matchesMeter = (c.meter_id || '').toLowerCase().includes(q);
        if (!matchesTitle && !matchesCategory && !matchesId && !matchesDesc && !matchesCust && !matchesMeter) {
          return false;
        }
      }

      return true;
    });

    // 7. Sorting
    result.sort((a, b) => {
      if (sortOption === 'date_desc') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      if (sortOption === 'date_asc') {
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      }
      if (sortOption === 'severity_desc') {
        return getSeverityScore(b) - getSeverityScore(a);
      }
      if (sortOption === 'severity_asc') {
        return getSeverityScore(a) - getSeverityScore(b);
      }
      return 0;
    });

    return result;
  }, [
    complaints,
    isGovernment,
    activeEntity,
    statusFilter,
    personaFilter,
    durationFilter,
    categoryFilter,
    sortOption,
    searchQuery,
  ]);

  // Aggregate counts
  const pendingCount = useMemo(
    () => complaints.filter((c) => isPendingStatus(c.status)).length,
    [complaints]
  );
  const resolvedCount = useMemo(
    () => complaints.filter((c) => isResolvedStatus(c.status)).length,
    [complaints]
  );
  const rejectedCount = useMemo(
    () => complaints.filter((c) => isRejectedStatus(c.status)).length,
    [complaints]
  );

  return (
    <div
      style={{
        maxWidth: '1380px',
        margin: '0 auto',
        padding: '1.5rem 1.75rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem',
        fontFamily: 'var(--gv-font-sans)',
      }}
    >
      {/* Action Notification Toast Banner */}
      {actionFeedback && (
        <div
          style={{
            background: '#F0FDF4',
            border: '1px solid #86EFAC',
            borderRadius: '10px',
            padding: '0.85rem 1.25rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            color: '#15803D',
            boxShadow: 'var(--gv-shadow-sm)',
            fontSize: '0.85rem',
            fontWeight: 600,
          }}
        >
          <Check size={18} color="#16A34A" />
          <span>{actionFeedback}</span>
        </div>
      )}

      {/* 1. Page Header (Dedicated distinct design for Government vs Citizen) */}
      {isGovernment ? (
        <div
          style={{
            background: 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)',
            borderRadius: '16px',
            padding: '1.75rem 2rem',
            color: '#FFFFFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1.5rem',
            flexWrap: 'wrap',
            boxShadow: '0 4px 12px rgba(15, 23, 42, 0.15)',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.5rem' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'rgba(59, 130, 246, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#60A5FA',
                }}
              >
                <Shield size={18} />
              </div>
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  color: '#93C5FD',
                  background: 'rgba(30, 58, 138, 0.4)',
                  padding: '3px 9px',
                  borderRadius: '999px',
                  border: '1px solid rgba(147, 197, 253, 0.3)',
                }}
              >
                Government Regulatory Directorate
              </span>
            </div>
            <h1
              style={{
                fontSize: '1.75rem',
                fontWeight: 800,
                color: '#FFFFFF',
                letterSpacing: '-0.02em',
                margin: '0 0 0.35rem 0',
              }}
            >
              Grid Complaints Resolution Clearinghouse
            </h1>
            <p
              style={{
                color: '#94A3B8',
                fontSize: '0.875rem',
                maxWidth: '860px',
                margin: 0,
                lineHeight: 1.5,
              }}
            >
              Central authority console for reviewing all residential, commercial, and public power grievances.
              Assess physical telemetry validation, update resolution status (Pending, Resolved, Rejected), and
              trigger automatic customer email alerts and in-app notifications.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button
              onClick={fetchComplaints}
              title="Refresh grid complaint database"
              style={{
                height: '42px',
                padding: '0 1rem',
                borderRadius: '8px',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                background: 'rgba(255, 255, 255, 0.1)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                color: '#FFFFFF',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.82rem',
                transition: 'all 0.15s ease',
              }}
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              <span>Refresh Records</span>
            </button>
          </div>
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: '1.25rem',
            flexWrap: 'wrap',
            paddingBottom: '1.25rem',
            borderBottom: '1px solid var(--gv-border-subtle)',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <h1
                style={{
                  fontSize: '1.65rem',
                  fontWeight: 800,
                  color: 'var(--gv-color-midnight-navy)',
                  letterSpacing: '-0.02em',
                  margin: 0,
                }}
              >
                My Complaints & Service Tickets
              </h1>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  color: '#0F766E',
                  background: '#E0F7F5',
                  border: '1px solid #99F6E4',
                  padding: '3px 8px',
                  borderRadius: '999px',
                }}
              >
                Account: {activeEntity}
              </span>
            </div>
            <p
              style={{
                color: 'var(--gv-text-secondary)',
                fontSize: '0.875rem',
                maxWidth: '860px',
                marginTop: '0.35rem',
                lineHeight: 1.55,
                marginBottom: 0,
              }}
            >
              Submit and track issues related to electricity supply, meter readings, billing, or equipment for your
              active facility/household. Grievances are cross-referenced with your physical telemetry data.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button
              onClick={fetchComplaints}
              title="Refresh my complaints"
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '8px',
                border: '1px solid var(--gv-border-medium)',
                background: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--gv-text-secondary)',
                cursor: 'pointer',
                boxShadow: 'var(--gv-shadow-sm)',
              }}
            >
              <RefreshCw size={17} className={loading ? 'animate-spin' : ''} />
            </button>

            <button
              onClick={() => setIsRegisterModalOpen(true)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.65rem 1.25rem',
                background: 'var(--gv-color-smart-teal)',
                color: '#FFFFFF',
                border: '1px solid var(--gv-color-smart-teal)',
                borderRadius: '8px',
                fontSize: '0.85rem',
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: '0 2px 4px rgba(0, 184, 169, 0.25)',
                transition: 'all 0.15s ease',
              }}
            >
              <Plus size={18} />
              <span>Register a New Complaint</span>
            </button>
          </div>
        </div>
      )}

      {/* 2. Stat Overview Summary Cards (Total, Pending, Resolved, Rejected) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
        }}
      >
        {/* Total Logged */}
        <div
          style={{
            background: '#FFFFFF',
            border: '1px solid var(--gv-border-subtle)',
            borderRadius: '12px',
            padding: '1.15rem 1.35rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: 'var(--gv-shadow-sm)',
          }}
        >
          <div>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                color: 'var(--gv-text-muted)',
                display: 'block',
              }}
            >
              {isGovernment ? 'Total Grid Logged' : 'My Total Logged'}
            </span>
            <span
              style={{
                fontSize: '1.85rem',
                fontWeight: 800,
                color: 'var(--gv-text-primary)',
                marginTop: '0.15rem',
                display: 'block',
                lineHeight: 1.1,
              }}
            >
              {complaints.length}
            </span>
          </div>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'var(--gv-bg-surface-subtle)',
              border: '1px solid var(--gv-border-subtle)',
              color: 'var(--gv-text-secondary)',
            }}
          >
            <FileText size={22} />
          </div>
        </div>

        {/* Pending */}
        <div
          style={{
            background: '#FFFFFF',
            border: '1px solid var(--gv-border-subtle)',
            borderRadius: '12px',
            padding: '1.15rem 1.35rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: 'var(--gv-shadow-sm)',
          }}
        >
          <div>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                color: '#D97706',
                display: 'block',
              }}
            >
              Pending / Under Review
            </span>
            <span
              style={{
                fontSize: '1.85rem',
                fontWeight: 800,
                color: '#D97706',
                marginTop: '0.15rem',
                display: 'block',
                lineHeight: 1.1,
              }}
            >
              {pendingCount}
            </span>
          </div>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: '#FEF3C7',
              border: '1px solid #FDE68A',
              color: '#D97706',
            }}
          >
            <Clock size={22} />
          </div>
        </div>

        {/* Resolved */}
        <div
          style={{
            background: '#FFFFFF',
            border: '1px solid var(--gv-border-subtle)',
            borderRadius: '12px',
            padding: '1.15rem 1.35rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: 'var(--gv-shadow-sm)',
          }}
        >
          <div>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                color: '#16A34A',
                display: 'block',
              }}
            >
              Resolved & Closed
            </span>
            <span
              style={{
                fontSize: '1.85rem',
                fontWeight: 800,
                color: '#16A34A',
                marginTop: '0.15rem',
                display: 'block',
                lineHeight: 1.1,
              }}
            >
              {resolvedCount}
            </span>
          </div>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: '#DCFCE7',
              border: '1px solid #BBF7D0',
              color: '#16A34A',
            }}
          >
            <CheckCircle size={22} />
          </div>
        </div>

        {/* Rejected / Invalid */}
        <div
          style={{
            background: '#FFFFFF',
            border: '1px solid var(--gv-border-subtle)',
            borderRadius: '12px',
            padding: '1.15rem 1.35rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: 'var(--gv-shadow-sm)',
          }}
        >
          <div>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                color: '#DC2626',
                display: 'block',
              }}
            >
              Rejected / Invalid
            </span>
            <span
              style={{
                fontSize: '1.85rem',
                fontWeight: 800,
                color: '#DC2626',
                marginTop: '0.15rem',
                display: 'block',
                lineHeight: 1.1,
              }}
            >
              {rejectedCount}
            </span>
          </div>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: '#FEE2E2',
              border: '1px solid #FECACA',
              color: '#DC2626',
            }}
          >
            <XCircle size={22} />
          </div>
        </div>
      </div>

      {/* 3. Comprehensive Filter & Sort Bar */}
      <div
        style={{
          background: '#FFFFFF',
          border: '1px solid var(--gv-border-subtle)',
          borderRadius: '12px',
          padding: '1rem 1.25rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
          boxShadow: 'var(--gv-shadow-sm)',
        }}
      >
        {/* Row 1: Status Filter Tabs + Search Input */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
        >
          {/* Status Tabs */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              background: '#F1F5F9',
              padding: '3px',
              borderRadius: '8px',
              gap: '2px',
            }}
          >
            <button
              onClick={() => setStatusFilter('ALL')}
              style={{
                padding: '0.45rem 0.95rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: statusFilter === 'ALL' ? 700 : 600,
                color: statusFilter === 'ALL' ? 'var(--gv-text-primary)' : 'var(--gv-text-secondary)',
                background: statusFilter === 'ALL' ? '#FFFFFF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                boxShadow: statusFilter === 'ALL' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              All ({complaints.length})
            </button>
            <button
              onClick={() => setStatusFilter('PENDING')}
              style={{
                padding: '0.45rem 0.95rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: statusFilter === 'PENDING' ? 700 : 600,
                color: statusFilter === 'PENDING' ? '#D97706' : 'var(--gv-text-secondary)',
                background: statusFilter === 'PENDING' ? '#FFFFFF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                boxShadow: statusFilter === 'PENDING' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              Pending ({pendingCount})
            </button>
            <button
              onClick={() => setStatusFilter('RESOLVED')}
              style={{
                padding: '0.45rem 0.95rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: statusFilter === 'RESOLVED' ? 700 : 600,
                color: statusFilter === 'RESOLVED' ? '#16A34A' : 'var(--gv-text-secondary)',
                background: statusFilter === 'RESOLVED' ? '#FFFFFF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                boxShadow: statusFilter === 'RESOLVED' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              Resolved ({resolvedCount})
            </button>
            <button
              onClick={() => setStatusFilter('REJECTED')}
              style={{
                padding: '0.45rem 0.95rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                fontWeight: statusFilter === 'REJECTED' ? 700 : 600,
                color: statusFilter === 'REJECTED' ? '#DC2626' : 'var(--gv-text-secondary)',
                background: statusFilter === 'REJECTED' ? '#FFFFFF' : 'transparent',
                border: 'none',
                cursor: 'pointer',
                boxShadow: statusFilter === 'REJECTED' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              Rejected ({rejectedCount})
            </button>
          </div>

          {/* Search Box */}
          <div style={{ position: 'relative', minWidth: '280px', flex: '1 1 280px', maxWidth: '420px' }}>
            <Search
              size={15}
              style={{
                position: 'absolute',
                left: '0.75rem',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--gv-text-muted)',
                pointerEvents: 'none',
              }}
            />
            <input
              type="text"
              placeholder={isGovernment ? 'Search across all tickets, meters, or IDs...' : 'Search my complaints...'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: '100%',
                padding: '0.5rem 0.75rem 0.5rem 2.25rem',
                border: '1px solid var(--gv-border-medium)',
                borderRadius: '8px',
                fontSize: '0.8rem',
                background: '#FFFFFF',
                color: 'var(--gv-text-primary)',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
        </div>

        {/* Row 2: Secondary Dropdown Filters (Persona, Duration, Category, Sort) */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '1rem',
            flexWrap: 'wrap',
            paddingTop: '0.5rem',
            borderTop: '1px solid var(--gv-border-subtle)',
          }}
        >
          {/* Persona Filter (Government view only) */}
          {isGovernment && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Users size={14} color="var(--gv-text-secondary)" />
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>
                Sector:
              </span>
              <select
                value={personaFilter}
                onChange={(e) => setPersonaFilter(e.target.value as PersonaFilterType)}
                style={{
                  fontSize: '0.78rem',
                  padding: '0.35rem 0.65rem',
                  borderRadius: '6px',
                  border: '1px solid var(--gv-border-medium)',
                  background: '#FFFFFF',
                  color: 'var(--gv-text-primary)',
                  fontWeight: 600,
                  outline: 'none',
                  cursor: 'pointer',
                }}
              >
                <option value="ALL">All Sectors</option>
                <option value="RESIDENTIAL">Residential</option>
                <option value="COMMERCIAL">Commercial</option>
                <option value="GOVERNMENT">Government</option>
              </select>
            </div>
          )}

          {/* Duration Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Calendar size={14} color="var(--gv-text-secondary)" />
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>
              Duration:
            </span>
            <select
              value={durationFilter}
              onChange={(e) => setDurationFilter(e.target.value as DurationFilterType)}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.65rem',
                borderRadius: '6px',
                border: '1px solid var(--gv-border-medium)',
                background: '#FFFFFF',
                color: 'var(--gv-text-primary)',
                fontWeight: 600,
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="ALL">All Time</option>
              <option value="TODAY">Today (Last 24h)</option>
              <option value="WEEK">Last 7 Days</option>
              <option value="MONTH">Last 30 Days</option>
              <option value="QUARTER">Last 90 Days</option>
            </select>
          </div>

          {/* Category Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Tag size={14} color="var(--gv-text-secondary)" />
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>
              Category:
            </span>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.65rem',
                borderRadius: '6px',
                border: '1px solid var(--gv-border-medium)',
                background: '#FFFFFF',
                color: 'var(--gv-text-primary)',
                fontWeight: 600,
                outline: 'none',
                cursor: 'pointer',
                maxWidth: '200px',
              }}
            >
              <option value="ALL">All Categories</option>
              {availableCategories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {/* Sort Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginLeft: 'auto' }}>
            <ArrowUpDown size={14} color="var(--gv-text-secondary)" />
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--gv-text-secondary)' }}>
              Sort:
            </span>
            <select
              value={sortOption}
              onChange={(e) => setSortOption(e.target.value as SortOptionType)}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.65rem',
                borderRadius: '6px',
                border: '1px solid var(--gv-border-medium)',
                background: '#FFFFFF',
                color: 'var(--gv-text-primary)',
                fontWeight: 600,
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="date_desc">Date: Newest First</option>
              <option value="date_asc">Date: Oldest First</option>
              <option value="severity_desc">Severity: Highest First</option>
              <option value="severity_asc">Severity: Lowest First</option>
            </select>
          </div>
        </div>
      </div>

      {/* 4. Complaints Grid / List */}
      {loading ? (
        <div
          style={{
            padding: '5rem 1rem',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.75rem',
            color: 'var(--gv-text-muted)',
          }}
        >
          <RefreshCw size={28} className="animate-spin" color="#00B8A9" />
          <p style={{ fontSize: '0.85rem', fontWeight: 600 }}>Loading complaint registry...</p>
        </div>
      ) : error ? (
        <div
          style={{
            padding: '2rem',
            borderRadius: '16px',
            background: '#FEF2F2',
            border: '1px solid #FECACA',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '0.75rem',
          }}
        >
          <AlertCircle size={36} color="#DC2626" />
          <h3 style={{ fontWeight: 800, fontSize: '1.05rem', color: '#991B1B', margin: 0 }}>
            Error Loading Complaints
          </h3>
          <p style={{ fontSize: '0.8rem', color: '#B91C1C', maxWidth: '480px', margin: 0 }}>{error}</p>
          <button
            onClick={fetchComplaints}
            style={{
              padding: '0.5rem 1.25rem',
              borderRadius: '8px',
              background: '#DC2626',
              color: '#FFFFFF',
              fontSize: '0.8rem',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
              marginTop: '0.5rem',
            }}
          >
            Retry
          </button>
        </div>
      ) : filteredComplaints.length === 0 ? (
        <div
          style={{
            padding: '4rem 1.5rem',
            borderRadius: '16px',
            background: '#FFFFFF',
            border: '2px dashed var(--gv-border-medium)',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '1rem',
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: '#E0F7F5',
              color: '#00B8A9',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid #99F6E4',
            }}
          >
            <Sparkles size={24} />
          </div>
          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--gv-text-primary)', margin: 0 }}>
              {complaints.length === 0
                ? isGovernment
                  ? 'No Complaints Registered Across the Grid'
                  : 'No Complaints Registered for This User'
                : 'No Complaints Match Your Filters'}
            </h3>
            <p
              style={{
                fontSize: '0.8rem',
                color: 'var(--gv-text-muted)',
                maxWidth: '440px',
                margin: '0.35rem auto 0 auto',
                lineHeight: 1.5,
              }}
            >
              {complaints.length === 0
                ? isGovernment
                  ? 'All consumer, commercial, and municipal power distribution sectors have zero open grievance records.'
                  : `Currently there are no service tickets filed under account / meter ${activeEntity}. If you are facing power issues, click below to log a ticket.`
                : 'Try adjusting your status tabs, duration, category filter or search query.'}
            </p>
          </div>
          {complaints.length === 0 && !isGovernment && (
            <button
              onClick={() => setIsRegisterModalOpen(true)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.65rem 1.25rem',
                background: 'var(--gv-color-smart-teal)',
                color: '#FFFFFF',
                borderRadius: '8px',
                fontSize: '0.82rem',
                fontWeight: 700,
                border: 'none',
                cursor: 'pointer',
                boxShadow: '0 2px 4px rgba(0, 184, 169, 0.25)',
              }}
            >
              <Plus size={16} />
              <span>Register First Complaint</span>
            </button>
          )}
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
            gap: '1.15rem',
          }}
        >
          {filteredComplaints.map((c) => (
            <ComplaintCard
              key={c.id}
              complaint={c}
              onClick={(complaint) => setSelectedComplaint(complaint)}
              isGovernment={isGovernment}
              onStatusUpdate={handleStatusUpdate}
            />
          ))}
        </div>
      )}

      {/* 5. Modals */}
      <ComplaintRegistrationModal
        isOpen={isRegisterModalOpen}
        onClose={() => setIsRegisterModalOpen(false)}
        onComplaintSubmitted={handleComplaintSubmitted}
        categories={categories}
        isLoadingCategories={categoriesLoading}
      />

      <ComplaintDetailModal
        complaint={selectedComplaint}
        onClose={() => setSelectedComplaint(null)}
        isGovernment={isGovernment}
        onStatusUpdate={handleStatusUpdate}
      />
    </div>
  );
};
