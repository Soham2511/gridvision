import { apiClient } from './apiClient';
import {
  CustomerBillModel,
  CustomerBillPrediction,
  CustomerBillRecord,
  PaginatedCustomerRecords,
  RegisteredModel,
  ResidentialBuildingProfile,
  ResidentialGoldHistory,
} from '../types/analytics';

const isCustomerBillModel = (
  model: RegisteredModel | undefined
): model is CustomerBillModel =>
  Boolean(
    model?.dataset &&
      model.testMetrics &&
      model.features &&
      model.tariffInrPerKwh !== undefined
  );

class ModelService {
  async getModelCatalog(): Promise<RegisteredModel[]> {
    const response = await apiClient.get<{ models: RegisteredModel[] }>('/models');
    return response.models;
  }

  async getCustomerBillModel(): Promise<CustomerBillModel> {
    const model = (await this.getModelCatalog()).find(
      (item) => item.modelId === 'customer-bill-prediction'
    );
    if (model?.provenanceStatus === 'unverified') {
      throw new Error(model.reason ?? 'Customer Gold data provenance is unverified.');
    }
    if (!isCustomerBillModel(model)) {
      throw new Error(
        model?.error ?? 'Customer bill prediction model or its gold dataset is unavailable.'
      );
    }
    return model;
  }

  async getForecastModelEntities(modelId: string): Promise<{ items: Array<Record<string, unknown>> }> {
    return apiClient.get<{ items: Array<Record<string, unknown>> }>(`/models/${encodeURIComponent(modelId)}/entities`);
  }

  async predictForecastModel(modelId: string, entityId: string, horizonHours = 24): Promise<{
    model: { model_name: string; model_version: string; provider: string; evaluation_status: string };
    entity_id: string;
    horizon: Array<{ timestamp: string; horizon_hours: number; prediction: number; actual?: number }>;
  }> {
    return apiClient.post(`/models/${encodeURIComponent(modelId)}/predict`, {
      entity_id: entityId,
      horizon_hours: horizonHours,
    });
  }

  async getCustomerRecords(
    limit = 50,
    offset = 0
  ): Promise<PaginatedCustomerRecords> {
    return apiClient.get<PaginatedCustomerRecords>(
      '/models/customer-bill-prediction/records',
      { limit, offset }
    );
  }

  async getEntityMonths(entityId: string): Promise<CustomerBillRecord[]> {
    return apiClient.get<CustomerBillRecord[]>(
      `/models/customer-bill-prediction/records/${encodeURIComponent(entityId)}`
    );
  }

  async getResidentialBuildingProfile(
    entityId: string
  ): Promise<ResidentialBuildingProfile> {
    return apiClient.get<ResidentialBuildingProfile>(
      `/models/customer-bill-prediction/profile/${encodeURIComponent(entityId)}`
    );
  }

  async getResidentialGoldHistory(
    timeRange: ResidentialGoldHistory['timeRange'] = 'ALL',
    entityId?: string
  ): Promise<ResidentialGoldHistory> {
    return apiClient.get<ResidentialGoldHistory>(
      '/models/customer-bill-prediction/history',
      { time_range: timeRange, entity_id: entityId }
    );
  }

  async predictCustomerBill(
    entityId: string,
    monthStart: string,
    cutoffDay: number
  ): Promise<CustomerBillPrediction> {
    return apiClient.post<CustomerBillPrediction>(
      '/models/customer-bill-prediction/predict',
      { entity_id: entityId, month_start: monthStart, cutoff_day: cutoffDay }
    );
  }
}

export const modelService = new ModelService();
