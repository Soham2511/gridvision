import React, { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { usePersona } from '../context';
import { useAuth } from '../context/AuthContext';
import {
  aiLayerService,
  cleanNotificationBody,
  extractReportIdFromNotification,
  NotificationRecord,
} from '../services/aiLayerService';
import {
  Bell,
  Calendar,
  ChevronDown,
  Download,
  X,
  Layers,
  LogOut,
  LogIn,
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
  const [notifications, setNotifications] = useState<NotificationRecord[]>([]);
  const location = useLocation();
  const navigate = useNavigate();
  const { currentPersona, activeEntity } = usePersona();
  const { user, isAuthenticated, logout } = useAuth();
  const persona = currentPersona ?? 'household';
  const entityId = persona === 'household' || persona === 'commercial' ? activeEntity : undefined;

  const refreshNotifications = useCallback(async () => {
    try {
      const stored = await aiLayerService.listNotifications(persona, entityId);
      setNotifications([...stored.items].sort(
        (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
      ));
    } catch {
      setNotifications([]);
    }
  }, [persona, entityId]);

  useEffect(() => {
    let inFlight = false;
    const refreshWhenVisible = async () => {
      if (inFlight || document.visibilityState === 'hidden') return;
      inFlight = true;
      try {
        await refreshNotifications();
      } finally {
        inFlight = false;
      }
    };

    void refreshWhenVisible();
    const intervalId = window.setInterval(() => void refreshWhenVisible(), 5_000);
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [refreshNotifications]);

  const markNotificationRead = async (notificationId: string) => {
    try {
      await aiLayerService.markRead(notificationId, persona, entityId);
    } catch {
      return;
    }
    await refreshNotifications();
  };

  const handleDownloadReport = async (reportId: string) => {
    try {
      const blob = await aiLayerService.downloadReport(reportId, 'pdf', persona, entityId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `gridvision-anomaly-report-${reportId}.pdf`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch {
      // no-op
    }
  };

  const isPlatformScope =
    location.pathname === '/' ||
    location.pathname === '/landing' ||
    location.pathname === '/health';

  const showLogo = propShowLogo !== undefined ? propShowLogo : isPlatformScope;
  const isAdmin = propIsAdmin !== undefined ? propIsAdmin : isPlatformScope;

  const userDisplayName = user?.username
    ? user.username
    : user?.email
    ? user.email
    : isAdmin
    ? 'Admin'
    : currentPersona === 'government'
    ? 'Grid Operations Admin'
    : currentPersona === 'commercial'
    ? 'Facility Manager'
    : 'Household Resident';

  const userInitial = user?.username
    ? user.username.charAt(0).toUpperCase()
    : user?.email
    ? user.email.charAt(0).toUpperCase()
    : isAdmin
    ? 'A'
    : currentPersona === 'government'
    ? 'G'
    : currentPersona === 'commercial'
    ? 'C'
    : 'H';

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

  const unreadCount = notifications.filter((notification) => !notification.read_at).length;

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
            {unreadCount > 0 && (
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
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
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
                {notifications.filter((notification) => !notification.read_at).slice(0, 5).map((n) => {
                  const reportId = extractReportIdFromNotification(n);
                  const displayBody = cleanNotificationBody(n.body);

                  return (
                    <div
                      key={n.notification_id}
                      style={{
                        padding: '0.6rem 0.75rem',
                        borderRadius: 'var(--gv-radius-md)',
                        background: 'var(--gv-bg-surface-subtle)',
                        borderLeft: `3px solid ${
                          n.notification_type === 'anomaly' || n.notification_type === 'danger' || n.notification_type === 'anomaly_alert'
                            ? 'var(--gv-status-danger)'
                            : n.notification_type === 'warning'
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
                          {new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      {displayBody && (
                        <p style={{ fontSize: '0.72rem', color: 'var(--gv-text-secondary)', lineHeight: 1.35 }}>
                          {displayBody}
                        </p>
                      )}
                      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: '0.35rem' }}>
                        {reportId && (
                          <button
                            type="button"
                            onClick={() => void handleDownloadReport(reportId)}
                            style={{
                              fontSize: '0.68rem',
                              fontWeight: 600,
                              color: '#ffffff',
                              background: 'var(--gv-color-smart-teal)',
                              border: 'none',
                              borderRadius: 'var(--gv-radius-sm)',
                              padding: '0.2rem 0.5rem',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                            }}
                          >
                            <Download size={11} />
                            Download PDF
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => void markNotificationRead(n.notification_id)}
                          style={{ fontSize: '0.68rem', color: 'var(--gv-color-grid-blue)', background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  );
                })}
                {unreadCount === 0 && <p className="gv-text-subtle">No new alerts or activity.</p>}
              </div>

              <div style={{ marginTop: '0.75rem', textAlign: 'center', borderTop: '1px solid var(--gv-border-subtle)', paddingTop: '0.5rem' }}>
                <span style={{ fontSize: '0.7rem', color: 'var(--gv-text-muted)' }}>
                  Alerts and activity are shared with Notifications.
                </span>
              </div>
              <div style={{ marginTop: '0.6rem', textAlign: 'center' }}>
                <Link to="/app/notifications" onClick={() => setShowNotifications(false)} style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--gv-color-grid-blue)' }}>
                  View all notifications
                </Link>
              </div>
            </div>
          )}
        </div>

        {isAuthenticated ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
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
              title={`User Profile: ${userDisplayName}`}
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
                {userInitial}
              </div>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#0B1F33' }}>
                {userDisplayName}
              </span>
              <ChevronDown size={14} color="#64748B" />
            </Link>

            <button
              type="button"
              onClick={async () => {
                await logout();
                navigate('/login');
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                background: 'none',
                border: '1px solid var(--gv-border-subtle, #E2E8F0)',
                borderRadius: '8px',
                padding: '0.35rem 0.65rem',
                color: '#64748B',
                fontSize: '0.78rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title="Sign out of your session"
            >
              <LogOut size={14} />
              <span>Sign Out</span>
            </button>
          </div>
        ) : (
          <Link
            to="/login"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              backgroundColor: 'var(--gv-color-smart-teal, #00A396)',
              color: '#FFFFFF',
              borderRadius: '8px',
              padding: '0.4rem 0.85rem',
              fontSize: '0.82rem',
              fontWeight: 600,
              textDecoration: 'none',
              boxShadow: '0 2px 4px rgba(0, 163, 150, 0.2)',
            }}
          >
            <LogIn size={14} />
            <span>Sign In</span>
          </Link>
        )}
      </div>
    </header>
  );
};
