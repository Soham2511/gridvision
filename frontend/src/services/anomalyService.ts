import { apiClient } from './apiClient';

export interface AnomalyEntity {
  OBJECTID: number;
  latitude: number;
  longitude: number;
}

export interface AnomalySpatialCluster {
  cluster_id: string;
  customer_ids: number[];
  latitude_center: number;
  longitude_center: number;
  spatial_extent_km: number;
}

export interface AnomalyEvent {
  event_id: string;
  event_scope: 'SINGLE_CUSTOMER' | 'LOCAL_AREA' | 'MULTI_AREA';
  event_start: string;
  event_end: string;
  event_duration: number;
  affected_customer_count: number;
  affected_customer_percentage: number;
  customer_ids: number[];
  anomaly_types: string[];
  dominant_anomaly_type: string;
  spatial_cluster_count: number;
  spatial_cluster_ids?: string[];
  spatial_clusters?: AnomalySpatialCluster[];
  latitude_center: number;
  longitude_center: number;
  spatial_extent_km: number;
  mean_anomaly_score: number;
  max_anomaly_score: number;
}

export interface AnomalyWindow {
  event_id?: string;
  event_spatial_cluster_id?: string;
  customer_id: number;
  anomaly_type: string;
  anomaly_start: string;
  anomaly_end: string;
  anomaly_duration: number;
  latitude: number;
  longitude: number;
  anomaly_score: number;
  severity: number;
}

export interface AnomalyRunResult {
  run_id: string;
  status: 'completed' | 'failed' | 'running' | 'queued';
  request: {
    customer_ids: number[] | null;
    start_date: string;
    end_date: string;
  };
  metadata: Record<string, unknown>;
  metrics: Record<string, unknown>;
  events: AnomalyEvent[];
  anomaly_windows: AnomalyWindow[];
  affected_customer_ids: number[];
}

export interface AnomalyRun {
  analysis_id: string;
  status: AnomalyRunResult['status'];
  created_at: string;
  updated_at: string;
  request: AnomalyRunResult['request'];
  metadata?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  error?: string | null;
  events?: AnomalyEvent[];
  anomaly_windows?: AnomalyWindow[];
  affected_customer_ids?: number[];
}

export interface AnomalyModel {
  modelId: string;
  status: string;
  provider: string;
  modelVersion: string;
  selectedModel: string;
  dataset: {
    startDate: string | null;
    endDate: string | null;
    customers: number;
    rows: number;
  };
  testMetrics: Record<string, unknown>;
  anomalyTypes: string[];
  error?: string;
}

export interface AnomalyAnalysisRequest {
  customer_ids: number[] | null;
  start_date: string;
  end_date: string;
  h3_resolution: number;
  spatial_radius_km: number;
  maximum_start_time_difference_minutes: number;
  minimum_temporal_overlap: number;
  maximum_interval_gap_minutes: number;
}

class AnomalyService {
  async getModel(): Promise<AnomalyModel> {
    return apiClient.get<AnomalyModel>('/models/anomaly-prediction');
  }

  async getEntities(offset = 0, limit = 10_000): Promise<{
    items: AnomalyEntity[];
    offset: number;
    limit: number;
    total: number;
  }> {
    return apiClient.get<{
      items: AnomalyEntity[];
      offset: number;
      limit: number;
      total: number;
    }>('/models/anomaly-prediction/entities', { offset, limit });
  }

  async runAnalysis(request: AnomalyAnalysisRequest): Promise<AnomalyRunResult> {
    return apiClient.postLong<AnomalyRunResult>(
      '/models/anomaly-prediction/predict',
      request,
    );
  }

  async getRuns(limit = 25): Promise<{ items: AnomalyRun[] }> {
    return apiClient.get<{ items: AnomalyRun[] }>(
      '/models/anomaly-prediction/runs',
      { limit },
    );
  }

  async getRun(runId: string): Promise<AnomalyRun> {
    return apiClient.get<AnomalyRun>(
      `/models/anomaly-prediction/runs/${encodeURIComponent(runId)}`,
    );
  }

  async downloadRunFile(runId: string, filename: string): Promise<Blob> {
    return apiClient.getBlob(
      `/models/anomaly-prediction/runs/${encodeURIComponent(runId)}/download/${encodeURIComponent(filename)}`,
    );
  }
}

export const anomalyService = new AnomalyService();
