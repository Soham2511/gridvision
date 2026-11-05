import React, { useCallback, useEffect, useState } from 'react';
import { Download, Trash2 } from 'lucide-react';
import { usePersona } from '../context';
import {
  aiLayerService,
  cleanNotificationBody,
  extractReportIdFromNotification,
  NotificationRecord,
} from '../services/aiLayerService';

export const NotificationsPage: React.FC = () => {
  const { currentPersona, activeEntity } = usePersona();
  const persona = currentPersona ?? 'household';
  const entityId = persona === 'household' || persona === 'commercial' ? activeEntity : undefined;
  const [items, setItems] = useState<NotificationRecord[]>([]);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      let storedItems: NotificationRecord[] = [];
      try {
        storedItems = (await aiLayerService.listNotifications(persona, entityId)).items;
      } catch (cause) {
        setItems([]);
        setError(cause instanceof Error ? cause.message : 'Notification service is unavailable.');
        return;
      }
      setItems([...storedItems].sort(
        (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
      ));
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Notification service is unavailable.');
    }
  }, [persona, entityId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const markRead = async (id: string) => {
    try {
      await aiLayerService.markRead(id, persona, entityId);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to update notification.');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      setItems((prev) => prev.filter((i) => i.notification_id !== id));
      await aiLayerService.deleteNotification(id, persona, entityId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to delete notification.');
      void refresh();
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm('Are you sure you want to delete all notifications in this view?')) {
      return;
    }
    try {
      setItems([]);
      await aiLayerService.clearAllNotifications(persona, entityId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to clear notifications.');
      void refresh();
    }
  };

  const handleDownload = async (reportId: string) => {
    try {
      const blob = await aiLayerService.downloadReport(reportId, 'pdf', persona, entityId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `gridvision-anomaly-report-${reportId}.pdf`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Report download failed.');
    }
  };

  return (
    <main style={{ display: 'grid', gap: '1rem', maxWidth: 900, margin: '0 auto', width: '100%' }}>
      <header style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
        <div>
          <h1 className="gv-heading-1">Notifications</h1>
          <p className="gv-text-subtle">
            {entityId ? `Showing notices for Building Profile ID ${entityId}. ` : ''}Alerts, complaint updates, and activity for anomaly events.
          </p>
        </div>
        {items.length > 0 && (
          <button
            type="button"
            onClick={() => void handleClearAll()}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.45rem 0.85rem',
              borderRadius: '8px',
              background: '#FEE2E2',
              color: '#B91C1C',
              border: '1px solid #FECACA',
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <Trash2 size={14} />
            <span>Clear All</span>
          </button>
        )}
      </header>
      {error && <div role="alert" className="gv-card">{error}</div>}
      {items.map((item) => {
        const reportId = extractReportIdFromNotification(item);
        const displayBody = cleanNotificationBody(item.body);
        const isAnomaly = item.notification_type === 'anomaly_alert';
        const isComplaint = item.notification_type === 'complaint_status_update';

        return (
          <article key={item.notification_id} className="gv-card" style={{ opacity: item.read_at ? 0.72 : 1, display: 'grid', gap: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {isAnomaly && (
                  <span style={{ background: '#fee2e2', color: '#991b1b', padding: '0.15rem 0.5rem', borderRadius: 4, fontSize: '0.75rem', fontWeight: 600 }}>
                    ANOMALY
                  </span>
                )}
                {isComplaint && (
                  <span style={{ background: '#dbeafe', color: '#1e40af', padding: '0.15rem 0.5rem', borderRadius: 4, fontSize: '0.75rem', fontWeight: 600 }}>
                    COMPLAINT
                  </span>
                )}
                <strong>{item.title}</strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span className="gv-text-subtle" style={{ fontSize: '0.85rem' }}>{item.read_at ? 'Read' : 'Unread'}</span>
                <button
                  type="button"
                  onClick={() => void handleDelete(item.notification_id)}
                  title="Delete this notification"
                  aria-label="Delete notification"
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--gv-text-muted)',
                    cursor: 'pointer',
                    padding: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: '4px',
                    transition: 'color 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#DC2626')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--gv-text-muted)')}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
            {displayBody && <p style={{ margin: 0, color: 'var(--gv-text-secondary)', lineHeight: 1.5 }}>{displayBody}</p>}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.25rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <time className="gv-text-subtle" style={{ fontSize: '0.85rem' }}>{new Date(item.created_at).toLocaleString()}</time>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {reportId && (
                  <button
                    className="gv-button gv-button-primary"
                    type="button"
                    onClick={() => void handleDownload(reportId)}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
                  >
                    <Download size={14} />
                    Download PDF Report
                  </button>
                )}
                {!item.read_at && (
                  <button className="gv-button gv-button-secondary" type="button" onClick={() => void markRead(item.notification_id)}>
                    Mark as read
                  </button>
                )}
                <button
                  className="gv-button gv-button-secondary"
                  type="button"
                  onClick={() => void handleDelete(item.notification_id)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', color: '#DC2626', borderColor: '#FECACA' }}
                >
                  <Trash2 size={13} />
                  Delete
                </button>
              </div>
            </div>
          </article>
        );
      })}
      {items.length === 0 && <div className="gv-card">No notifications in this demo context.</div>}
    </main>
  );
};
