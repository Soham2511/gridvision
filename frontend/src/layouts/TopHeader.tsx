import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { usePersona } from '../context';
import {
  Bell,
  Calendar,
  ChevronDown,
  X,
  Layers,
} from 'lucide-react';

export interface TopHeaderProps {
  showLogo?: boolean;
  isAdmin?: boolean;
}

export const TopHeader: React.FC<TopHeaderProps> = ({
  showLogo: propShowLogo,
  isAdmin: propIsAdmin,
}) => {
  const [showNotifications, setShowNotifications] = useState(false);
  const location = useLocation();
  const { currentPersona } = usePersona();

  const isPlatformScope =
    location.pathname === '/' ||
    location.pathname === '/landing' ||
    location.pathname === '/health';

  const showLogo = propShowLogo !== undefined ? propShowLogo : isPlatformScope;
  const isAdmin = propIsAdmin !== undefined ? propIsAdmin : isPlatformScope;

  const personaLabel =
    currentPersona === 'commercial'
      ? 'Commercial'
      : currentPersona === 'government'
      ? 'Government & Utilities'
      : 'Residential';

  let pageLabel = 'Dashboard';
  if (location.pathname.includes('/historical')) {
    pageLabel = 'Historical Insights';
  } else if (location.pathname.includes('/assistant')) {
    pageLabel = 'AI Assistant';
  } else if (location.pathname.includes('/profile')) {
    pageLabel = 'Profile';
  } else if (location.pathname.includes('/forecasting')) {
    pageLabel = 'Demand Forecasting';
  } else if (location.pathname.includes('/peak-demand')) {
    pageLabel = 'Peak Demand';
  } else if (location.pathname.includes('/anomalies')) {
    pageLabel = 'Anomaly Detection';
  } else if (location.pathname.includes('/customers')) {
    pageLabel = 'Customer Segmentation';
  } else if (location.pathname.includes('/insights')) {
    pageLabel = 'Actionable Insights';
  }

  const notifications = [
    {
      id: 'notif-1',
      title: 'Peak Alert Notice',
      message: 'Thursday 18:30 projected demand exceeds 88% capacity limit.',
      time: '12m ago',
      type: 'warning',
    },
    {
      id: 'notif-2',
      title: 'North Substation Anomaly',
      message: 'Sudden +42.5% spike detected at SUB-NORTH-104.',
      time: '34m ago',
      type: 'danger',
    },
    {
      id: 'notif-3',
      title: 'Airflow Batch Sync Simulated',
      message: 'Telemetry feature cache refreshed with mock baseline.',
      time: '1h ago',
      type: 'success',
    },
  ];

  return (
    <header
      style={{
        height: 'var(--gv-header-height)',
        backgroundColor: '#FFFFFF',
        borderBottom: '1px solid #E2E8F0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 2rem',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.02)',
      }}
    >
      {/* Left: Branding Logo OR Dynamic Breadcrumbs */}
      {showLogo ? (
        <Link
          to="/"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            textDecoration: 'none',
          }}
        >
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #00A396, #087EBD)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <Layers size={18} color="#FFFFFF" />
          </div>
          <div>
            <div style={{ fontSize: '1.15rem', fontWeight: 800, letterSpacing: '-0.02em', color: '#0B1F33', lineHeight: 1.1 }}>
              Grid<span style={{ color: '#00A396' }}>Vision</span>
            </div>
            <div style={{ fontSize: '0.58rem', fontWeight: 700, color: '#00A396', letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: '2px' }}>
              Energy Intelligence
            </div>
          </div>
        </Link>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
          <span style={{ color: '#64748B', fontWeight: 500 }}>{personaLabel}</span>
          <span style={{ color: '#94A3B8' }}>&gt;</span>
          <span style={{ fontWeight: 600, color: '#0B1F33' }}>{pageLabel}</span>
        </div>
      )}

      {/* Right: Operational controls & Profile */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', position: 'relative' }}>
        {/* Live timestamp */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Calendar size={18} color="#64748B" />
          <div style={{ display: 'flex', flexDirection: 'column', textAlign: 'left', lineHeight: 1.2 }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#0B1F33' }}>
              19 Oct 2026, 10:30 AM
            </span>
            <span style={{ fontSize: '0.68rem', color: '#64748B' }}>
              Asia/Kolkata (IST)
            </span>
          </div>
        </div>

        {/* Notifications Icon with Badge */}
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            onClick={() => setShowNotifications(!showNotifications)}
            style={{
              position: 'relative',
              width: '36px',
              height: '36px',
              borderRadius: 'var(--gv-radius-md)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: showNotifications ? 'var(--gv-bg-surface-subtle)' : 'transparent',
              border: '1px solid var(--gv-border-subtle)',
              color: 'var(--gv-text-secondary)',
              cursor: 'pointer',
              transition: 'all var(--gv-transition-fast)',
            }}
            title="System Notifications"
          >
            <Bell size={17} />
            <span
              style={{
                position: 'absolute',
                top: '-3px',
                right: '-3px',
                width: '16px',
                height: '16px',
                borderRadius: '50%',
                background: 'var(--gv-status-danger)',
                color: '#FFFFFF',
                fontSize: '0.62rem',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '2px solid #FFFFFF',
              }}
            >
              3
            </span>
          </button>

          {/* Notifications Dropdown Drawer */}
          {showNotifications && (
            <div
              style={{
                position: 'absolute',
                top: '46px',
                right: 0,
                width: '320px',
                background: 'var(--gv-bg-surface)',
                border: '1px solid var(--gv-border-accent)',
                borderRadius: 'var(--gv-radius-lg)',
                boxShadow: 'var(--gv-shadow-lg)',
                padding: '1rem',
                zIndex: 100,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--gv-text-primary)' }}>
                  Grid Alerts & Activity
                </span>
                <button
                  type="button"
                  onClick={() => setShowNotifications(false)}
                  style={{ cursor: 'pointer', color: 'var(--gv-text-muted)' }}
                >
                  <X size={15} />
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
                {notifications.map((n) => (
                  <div
                    key={n.id}
                    style={{
                      padding: '0.6rem 0.75rem',
                      borderRadius: 'var(--gv-radius-md)',
                      background: 'var(--gv-bg-surface-subtle)',
                      borderLeft: `3px solid ${
                        n.type === 'danger'
                          ? 'var(--gv-status-danger)'
                          : n.type === 'warning'
                          ? 'var(--gv-color-energy-amber)'
                          : 'var(--gv-color-smart-teal)'
                      }`,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--gv-text-primary)' }}>
                        {n.title}
                      </span>
                      <span style={{ fontSize: '0.65rem', color: 'var(--gv-text-muted)' }}>
                        {n.time}
                      </span>
                    </div>
                    <p style={{ fontSize: '0.72rem', color: 'var(--gv-text-secondary)', lineHeight: 1.35 }}>
                      {n.message}
                    </p>
                  </div>
                ))}
              </div>

              <div style={{ marginTop: '0.75rem', textAlign: 'center', borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '0.5rem' }}>
                <span style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)' }}>
                  Simulated telemetry notifications
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Profile Entry Point */}
        <Link
          to="/profile"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.65rem',
            padding: '0.25rem 0.5rem',
            borderRadius: '999px',
            textDecoration: 'none',
            transition: 'background 0.15s ease',
          }}
          title={isAdmin ? 'User Profile: Admin' : 'User Profile: Rohit Sharma'}
        >
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%',
              backgroundColor: '#D1E5EE',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#0B1F33',
              fontWeight: 700,
              fontSize: '0.88rem',
            }}
          >
            {isAdmin ? 'A' : 'R'}
          </div>
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#0B1F33' }}>
            {isAdmin ? 'Admin' : 'Rohit Sharma'}
          </span>
          <ChevronDown size={14} color="#64748B" />
        </Link>
      </div>
    </header>
  );
};
