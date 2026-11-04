/**
 * GridVision — Analytics Service Interface
 * Connects React frontend components to the Flask REST API.
 * Uses centralized apiClient driven by VITE_API_BASE_URL.
 */

import { apiClient, type ApiCredentials } from './apiClient';
import {
  CommercialBuilding,
  ResidentialMeter,
  RegionalSite,
  RegionalRankingItem,
  TimeSeriesPoint,
  PeakDemandAnalysis,
  AnomalyEvent,
  CustomerSegment,
  DiurnalCurvePoint,
  BusinessInsight,
  HouseholdOverview,
  HistoricalInsightsData,
  CommercialDashboardData,
  GovernmentRegionItem,
  GovernmentDashboardData,
  CustomerSegmentationData,
  PlatformHealthSummary,
  KpiMetric,
  PairedCommercialForecast,
} from '../types/analytics';

export interface OverviewApiResponse {
  kpis: KpiMetric[];
  peakAnalysis: PeakDemandAnalysis;
  activeAnomaliesCount: number;
}

export interface CurtailmentResult {
  curtailmentMw: number;
  durationHours: number;
  originalPeakMw: number;
  newPeakMw: number;
  peakCapacityLimitMw: number;
  originalReserveMarginPct: number;
  newReserveMarginPct: number;
  riskLevel: string;
  dispatchConfirmed: boolean;
  dispatchTimestamp: string;
  message: string;
}

export interface CommercialEvidenceReference {
  source_id: string;
  source_type: string;
  locator?: string | null;
  excerpt?: string | null;
  synthetic: boolean;
}

export interface CommercialSpecialistResult {
  status: string;
  findings: string[];
  evidence_refs: CommercialEvidenceReference[];
  assumptions: string[];
  conflicts: string[];
  data: Record<string, unknown>;
  error?: { code: string; message: string } | null;
}

export interface CommercialScheduleProposal {
  proposal_id: string;
  status: string;
  schedule: Array<Record<string, unknown>>;
  calculated_cost_inr?: number | null;
  calculated_savings_inr?: number | null;
  battery_dispatch?: unknown;
  approval_required_before_use: boolean;
  equipment_controlled: false;
}

export interface CommercialWorkflowResponse {
  request_id: string;
  factory_id: string;
  status: 'passed' | 'incomplete' | 'needs_rework' | 'escalated';
  summary: string;
  findings: string[];
  evidence_refs: CommercialEvidenceReference[];
  assumptions: string[];
  conflicts: string[];
  errors: string[];
  validation: { status: string; issues: string[]; evidence_count: number };
  specialist_results: Record<string, CommercialSpecialistResult>;
  execution_trace: CommercialExecutionTraceEvent[];
  schedule_proposal?: CommercialScheduleProposal;
}

export interface CommercialExecutionTraceEvent {
  node_id: string;
  status: 'completed' | 'warning' | 'error';
  duration_ms: number;
  message?: string;
}

export interface UploadedRagDocument {
  source_id: string;
  size_bytes: number;
  page_count: number;
}

class AnalyticsService {
  public getApiBaseUrl(): string {
    return apiClient.getBaseUrl();
  }

  // --- Executive Overview ---
  async getOverview(): Promise<OverviewApiResponse> {
    return apiClient.get<OverviewApiResponse>('/overview');
  }

  // --- Commercial Facilities ---
  async getCommercialBuildings(): Promise<CommercialBuilding[]> {
    return apiClient.get<CommercialBuilding[]>('/entities/commercial');
  }

  async getCommercialForecast(buildingId: string): Promise<{
    building: CommercialBuilding;
    horizon: TimeSeriesPoint[];
  }> {
    return apiClient.get<{
      building: CommercialBuilding;
      horizon: TimeSeriesPoint[];
    }>(`/forecast/commercial/${encodeURIComponent(buildingId)}`);
  }

  async getPairedCommercialForecast(buildingId: string): Promise<PairedCommercialForecast> {
    return apiClient.get<PairedCommercialForecast>(
      `/forecast/commercial/${encodeURIComponent(buildingId)}/paired`
    );
  }

  async getCommercialDashboard(
    tab: 'building' | 'regional' = 'building',
    timeRange: '1D' | '7D' | '1M' | '3M' | '1Y' = '1D',
    buildingId: string = 'Panther_office_1'
  ): Promise<CommercialDashboardData> {
    return apiClient.get<CommercialDashboardData>('/dashboard/commercial', {
      tab,
      time_range: timeRange,
      building_id: buildingId,
    });
  }

  // --- Residential Meters ---
  async getResidentialMeters(): Promise<ResidentialMeter[]> {
    return apiClient.get<ResidentialMeter[]>('/entities/residential');
  }

  async getResidentialForecast(householdId: string): Promise<{
    meter: ResidentialMeter;
    horizon: TimeSeriesPoint[];
  }> {
    return apiClient.get<{
      meter: ResidentialMeter;
      horizon: TimeSeriesPoint[];
    }>(`/forecast/residential/${encodeURIComponent(householdId)}`);
  }

  async getGovernmentForecast(siteId: string): Promise<{
    site: RegionalSite;
    horizon: TimeSeriesPoint[];
  }> {
    return apiClient.get<{
      site: RegionalSite;
      horizon: TimeSeriesPoint[];
    }>(`/forecast/government/${encodeURIComponent(siteId)}`);
  }

  async getHouseholdOverview(householdId?: string): Promise<HouseholdOverview> {
    return apiClient.get<HouseholdOverview>('/dashboard/household', {
      household_id: householdId,
    });
  }

  // --- Historical Insights ---
  async getHistoricalInsights(
    persona: string,
    timeRange: '30D' | '90D' | '1Y' | 'ALL' = '30D',
    entityId?: string
  ): Promise<HistoricalInsightsData> {
    return apiClient.get<HistoricalInsightsData>('/historical', {
      persona,
      time_range: timeRange,
      entity_id: entityId,
    });
  }

  // --- Regional Government Grid ---
  async getRegionalSites(): Promise<RegionalSite[]> {
    return apiClient.get<RegionalSite[]>('/entities/government');
  }

  async getRegionalRankings(): Promise<RegionalRankingItem[]> {
    const sites = await this.getRegionalSites();
    return sites.map((s) => ({
      siteId: s.siteId,
      demandKwh: s.totalDemandKwh,
      buildingCount: s.buildingCount,
      percentageOfSystem: s.shareOfTotalPct,
    }));
  }

  // --- Peak Demand Analysis ---
  async getPeakDemandAnalysis(): Promise<PeakDemandAnalysis> {
    return apiClient.get<PeakDemandAnalysis>('/peak-demand');
  }

  async dispatchCurtailment(
    curtailmentMw: number,
    durationHours: number = 2.0
  ): Promise<CurtailmentResult> {
    return apiClient.post<CurtailmentResult>('/peak-demand/curtail', {
      curtailment_mw: curtailmentMw,
      duration_hours: durationHours,
    });
  }

  // --- Anomaly Events ---
  async getAnomalyEvents(
    severity?: string,
    status?: string,
    search?: string
  ): Promise<AnomalyEvent[]> {
    return apiClient.get<AnomalyEvent[]>('/anomalies', {
      severity: severity && severity !== 'all' ? severity : undefined,
      status: status && status !== 'all' ? status : undefined,
      search: search || undefined,
    });
  }

  async updateAnomalyStatus(
    eventId: string,
    newStatus: AnomalyEvent['status']
  ): Promise<AnomalyEvent> {
    return apiClient.patch<AnomalyEvent>(`/anomalies/${encodeURIComponent(eventId)}`, {
      status: newStatus,
    });
  }

  // --- Customer Analytics & Diurnal Curves ---
  async getCustomerSegments(): Promise<CustomerSegment[]> {
    return apiClient.get<CustomerSegment[]>('/customers/segments');
  }

  async getDiurnalCurves(): Promise<DiurnalCurvePoint[]> {
    return apiClient.get<DiurnalCurvePoint[]>('/customers/diurnal-curves');
  }

  async getCustomerSegmentationData(): Promise<CustomerSegmentationData> {
    return apiClient.get<CustomerSegmentationData>('/customers/segmentation-matrix');
  }

  // --- Business Insights ---
  async getBusinessInsights(category?: string, sector?: string): Promise<BusinessInsight[]> {
    return apiClient.get<BusinessInsight[]>('/energy-insights', {
      category: category && category !== 'all' ? category : undefined,
      sector: sector && sector !== 'all' ? sector : undefined,
    });
  }

  // --- Platform Data & Model Health ---
  async getPlatformHealthSummary(): Promise<PlatformHealthSummary> {
    return apiClient.get<PlatformHealthSummary>('/platform/health');
  }

  // --- Government & Utilities Dashboard Data ---
  async getGovernmentRegions(
    timeRange: '1D' | '7D' | '1M' | '3M' | '1Y' = '1D'
  ): Promise<GovernmentRegionItem[]> {
    return apiClient.get<GovernmentRegionItem[]>('/dashboard/government/regions', {
      time_range: timeRange,
    });
  }

  async getGovernmentDashboard(
    viewType: 'overall' | 'region' = 'overall',
    regionId?: string,
    timeRange: '1D' | '7D' | '1M' | '3M' | '1Y' = '1D'
  ): Promise<GovernmentDashboardData> {
    return apiClient.get<GovernmentDashboardData>('/dashboard/government', {
      view_type: viewType,
      region_id: regionId,
      time_range: timeRange,
    });
  }

  // --- AI Domain Assistant ---
  async askAssistant(
    prompt: string,
    persona: string = 'household',
    entityId?: string
  ): Promise<{ answer: string; persona: string; entityId: string | null; status: string; availability: string }> {
    return apiClient.post<{ answer: string; persona: string; entityId: string | null; status: string; availability: string }>(
      '/assistant/chat',
      {
        prompt,
        persona,
        entity_id: entityId,
      }
    );
  }

  async validateCommercialSession(
    credentials: ApiCredentials,
  ): Promise<{ user_id: string; factory_id: string; scope: string }> {
    return apiClient.postAuthenticated('/commercial/session', {}, credentials);
  }

  async askCommercialAssistant(
    userGoal: string,
    credentials: ApiCredentials,
    optimizationInputs?: Record<string, unknown>,
  ): Promise<CommercialWorkflowResponse> {
    return apiClient.postLongAuthenticated<CommercialWorkflowResponse>(
      '/commercial/workflow',
      {
        user_goal: userGoal,
        factory_id: 'automotive-parts-demo',
        ...(optimizationInputs ? { optimization_inputs: optimizationInputs } : {}),
      },
      credentials,
    );
  }

  async uploadCommercialRagDocument(
    file: File,
    credentials: ApiCredentials,
  ): Promise<{
    source_id: string;
    size_bytes: number;
    page_count?: number;
    chunk_count?: number;
    status: string;
  }> {
    return apiClient.uploadAuthenticated(
      '/commercial/rag/documents',
      file,
      credentials,
    );
  }

  async getCommercialRagDocuments(
    credentials: ApiCredentials,
  ): Promise<{
    documents: UploadedRagDocument[];
    index_counts: Record<string, number>;
  }> {
    return apiClient.getAuthenticated('/commercial/rag/documents', credentials);
  }

  async decideScheduleProposal(
    proposalId: string,
    decision: 'approved' | 'rejected',
    credentials: ApiCredentials,
  ): Promise<{ proposal_id: string; status: string; equipment_controlled: false }> {
    return apiClient.postAuthenticated(
      `/commercial/schedules/${encodeURIComponent(proposalId)}/approval`,
      { decision },
      credentials,
    );
  }
}

export const analyticsService = new AnalyticsService();
