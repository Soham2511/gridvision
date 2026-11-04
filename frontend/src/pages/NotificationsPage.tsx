import React, { useCallback, useEffect, useState } from 'react';
import { usePersona } from '../context';
import { aiLayerService, NotificationRecord } from '../services/aiLayerService';

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

  return (
    <main style={{ display: 'grid', gap: '1rem', maxWidth: 900, margin: '0 auto', width: '100%' }}>
      <header><h1 className="gv-heading-1">Notifications</h1><p className="gv-text-subtle">{entityId ? `Showing notices for Building Profile ID ${entityId}. ` : ''}Alerts and activity for anomaly events and reports.</p></header>
      {error && <div role="alert" className="gv-card">{error}</div>}
      {items.map((item) => (
        <article key={item.notification_id} className="gv-card" style={{ opacity: item.read_at ? 0.72 : 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem' }}><strong>{item.title}</strong><span>{item.read_at ? 'Read' : 'Unread'}</span></div>
          <p>{item.body}</p>
          <time className="gv-text-subtle">{new Date(item.created_at).toLocaleString()}</time>
          {!item.read_at && <button className="gv-button gv-button-secondary" type="button" onClick={() => void markRead(item.notification_id)}>Mark as read</button>}
        </article>
      ))}
      {items.length === 0 && <div className="gv-card">No notifications in this demo context.</div>}
    </main>
  );
};
