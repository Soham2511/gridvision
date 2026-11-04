import { apiClient } from './apiClient';

export interface ReportRecord {
  report_id: string;
  report_type: string;
  context: string;
  created_at: string;
  payload?: {
    pdfArtifactId?: string | null;
    generationStatus?: 'complete' | 'partial' | 'failed';
    metadata?: {
      entityId?: string;
      subject?: { entityId?: string; persona?: string };
      period?: { label?: string; start?: string; end?: string } | string;
    };
  };
}

export interface NotificationRecord {
  notification_id: string;
  event_key: string;
  notification_type: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
}

class AILayerService {
  createReport(persona: string, entityId?: string) {
    const reportType = persona === 'government' ? 'government_analytics' : 'monthly_consumption';
    const timeRange = persona === 'household' ? '1Y' : 'ALL';
    return apiClient.post<ReportRecord>('/ai/reports', {
      report_type: reportType,
      persona,
      time_range: timeRange,
      ...(entityId ? { building_id: entityId } : {}),
    });
  }

  listReports(persona: string, entityId?: string) {
    return apiClient.get<{ items: ReportRecord[] }>('/ai/reports', { persona, building_id: entityId });
  }

  downloadReport(reportId: string, format: 'html' | 'pdf', persona: string, entityId?: string) {
    const params = new URLSearchParams({ persona });
    if (entityId) params.set('building_id', entityId);
    return apiClient.getBlob(`/ai/reports/${encodeURIComponent(reportId)}/download/${format}?${params}`);
  }

  emailReport(reportId: string, persona: string, entityId?: string) {
    const params = new URLSearchParams({ persona });
    if (entityId) params.set('building_id', entityId);
    return apiClient.postLong<{ report_id: string; recipient: string; format: string; status: string }>(
      `/ai/reports/${encodeURIComponent(reportId)}/email?${params}`,
      {},
      45000,
    );
  }

  listNotifications(persona: string, entityId?: string) {
    return apiClient.get<{ items: NotificationRecord[]; emailDelivery: string }>(
      '/ai/notifications', { persona, building_id: entityId },
    );
  }

  markRead(notificationId: string, persona: string, entityId?: string) {
    return apiClient.post<NotificationRecord>(
      `/ai/notifications/${encodeURIComponent(notificationId)}/read`,
      {},
      { persona, building_id: entityId },
    );
  }
}

export const aiLayerService = new AILayerService();
