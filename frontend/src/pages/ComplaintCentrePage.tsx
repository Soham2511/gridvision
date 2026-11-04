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
} from 'lucide-react';
import { Complaint, ComplaintCategory } from '../types/complaints';
import { complaintService } from '../services/complaintService';
import {
  ComplaintCard,
  ComplaintDetailModal,
  ComplaintRegistrationModal,
} from '../components/complaints';
import { usePersona } from '../context';

export const ComplaintCentrePage: React.FC = () => {
  const { activeEntity } = usePersona();
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [categories, setCategories] = useState<ComplaintCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'REGISTERED' | 'INVALID'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [selectedComplaint, setSelectedComplaint] = useState<Complaint | null>(null);

  // Load Categories
  const fetchCategories = useCallback(async () => {
    setCategoriesLoading(true);
    try {
      const data = await complaintService.getCategories('RESIDENTIAL');
      setCategories(data);
    } catch (err: any) {
      console.error('Failed to load complaint categories:', err);
    } finally {
      setCategoriesLoading(false);
    }
  }, []);

  // Load Complaints
  const fetchComplaints = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await complaintService.getComplaints();
      setComplaints(data);
    } catch (err: any) {
      console.error('Failed to load complaints:', err);
      setError(err?.message || 'Unable to retrieve complaints. Please ensure the backend is running.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCategories();
    fetchComplaints();
  }, [fetchCategories, fetchComplaints, activeEntity]);

  const handleComplaintSubmitted = (newComplaint: Complaint) => {
    setComplaints((prev) => [newComplaint, ...prev.filter((c) => c.id !== newComplaint.id)]);
  };

  // Filtered & Searched list
  const filteredComplaints = useMemo(() => {
    return complaints.filter((c) => {
      // Status filter
      if (statusFilter === 'REGISTERED' && c.status !== 'REGISTERED') return false;
      if (statusFilter === 'INVALID' && c.status !== 'INVALID') return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesTitle = c.title.toLowerCase().includes(q);
        const matchesCategory = (c.category_label || c.category_id).toLowerCase().includes(q);
        const matchesId = c.id.toLowerCase().includes(q);
        const matchesDesc = c.description.toLowerCase().includes(q);
        if (!matchesTitle && !matchesCategory && !matchesId && !matchesDesc) return false;
      }

      return true;
    });
  }, [complaints, statusFilter, searchQuery]);

  const registeredCount = useMemo(
    () => complaints.filter((c) => c.status === 'REGISTERED').length,
    [complaints]
  );
  const invalidCount = useMemo(
    () => complaints.filter((c) => c.status === 'INVALID').length,
    [complaints]
  );

  return (
    <div
      style={{
        maxWidth: '1300px',
        margin: '0 auto',
        padding: '1.5rem 1.75rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem',
        fontFamily: 'var(--gv-font-sans)',
      }}
    >
      {/* 1. Page Header & Action */}
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
              Complaint Centre
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
              AI-Assisted
            </span>
          </div>
          <p
            style={{
              color: 'var(--gv-text-secondary)',
              fontSize: '0.875rem',
              maxWidth: '820px',
              marginTop: '0.35rem',
              lineHeight: 1.55,
              marginBottom: 0,
            }}
          >
            Submit and track issues related to your household's electricity supply, meter, billing and electrical services.
            Complaints are evaluated against real smart-meter telemetry and prioritized using the GridVision Severity Benchmark.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button
            onClick={fetchComplaints}
            title="Refresh complaints"
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

      {/* 2. Stat Overview Summary Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '1rem',
        }}
      >
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
              Total Logged
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
                color: '#0F766E',
                display: 'block',
              }}
            >
              Registered & Scored
            </span>
            <span
              style={{
                fontSize: '1.85rem',
                fontWeight: 800,
                color: '#0F766E',
                marginTop: '0.15rem',
                display: 'block',
                lineHeight: 1.1,
              }}
            >
              {registeredCount}
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
              background: '#E0F7F5',
              border: '1px solid #99F6E4',
              color: '#0F766E',
            }}
          >
            <CheckCircle size={22} />
          </div>
        </div>

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
                color: '#BE123C',
                display: 'block',
              }}
            >
              Contradicted / Invalid
            </span>
            <span
              style={{
                fontSize: '1.85rem',
                fontWeight: 800,
                color: '#BE123C',
                marginTop: '0.15rem',
                display: 'block',
                lineHeight: 1.1,
              }}
            >
              {invalidCount}
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
              background: '#FFF1F2',
              border: '1px solid #FECDD3',
              color: '#BE123C',
            }}
          >
            <XCircle size={22} />
          </div>
        </div>
      </div>

      {/* 3. Filter Bar & Search */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
          flexWrap: 'wrap',
          paddingTop: '0.5rem',
        }}
      >
        {/* Filter Tabs */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            background: '#E2E8F0',
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
            All Complaints ({complaints.length})
          </button>
          <button
            onClick={() => setStatusFilter('REGISTERED')}
            style={{
              padding: '0.45rem 0.95rem',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: statusFilter === 'REGISTERED' ? 700 : 600,
              color: statusFilter === 'REGISTERED' ? '#0F766E' : 'var(--gv-text-secondary)',
              background: statusFilter === 'REGISTERED' ? '#FFFFFF' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              boxShadow: statusFilter === 'REGISTERED' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            Registered ({registeredCount})
          </button>
          <button
            onClick={() => setStatusFilter('INVALID')}
            style={{
              padding: '0.45rem 0.95rem',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: statusFilter === 'INVALID' ? 700 : 600,
              color: statusFilter === 'INVALID' ? '#BE123C' : 'var(--gv-text-secondary)',
              background: statusFilter === 'INVALID' ? '#FFFFFF' : 'transparent',
              border: 'none',
              cursor: 'pointer',
              boxShadow: statusFilter === 'INVALID' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 0.15s ease',
            }}
          >
            Invalid ({invalidCount})
          </button>
        </div>

        {/* Search Input */}
        <div style={{ position: 'relative', minWidth: '280px' }}>
          <Search size={15} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--gv-text-muted)', pointerEvents: 'none' }} />
          <input
            type="text"
            placeholder="Search by title, ID or category..."
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

      {/* 4. Complaints Grid / List */}
      {loading ? (
        <div style={{ padding: '5rem 1rem', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', color: 'var(--gv-text-muted)' }}>
          <RefreshCw size={28} className="animate-spin" color="#00B8A9" />
          <p style={{ fontSize: '0.85rem', fontWeight: 600 }}>Fetching household complaint history...</p>
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
          <h3 style={{ fontWeight: 800, fontSize: '1.05rem', color: '#991B1B', margin: 0 }}>Error Loading Complaints</h3>
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
                ? 'No Complaints Registered Yet'
                : 'No Complaints Match Your Filter'}
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--gv-text-muted)', maxWidth: '440px', margin: '0.35rem auto 0 auto', lineHeight: 1.5 }}>
              {complaints.length === 0
                ? 'If you are experiencing power quality, outage, meter, or billing issues, click below to register a ticket with AI validation.'
                : 'Try adjusting your search query or switching between the All, Registered, and Invalid filters.'}
            </p>
          </div>
          {complaints.length === 0 && (
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
      />
    </div>
  );
};
