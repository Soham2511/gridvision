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
import {
  QuestionnaireSchema,
  HouseEnergyPlanningResult,
  ApplianceScenarioResult,
  CostManagementResult,
  AssistantResponsePayload,
} from '../../../ai/residential/frontend/src/types/residentialFeatures';

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

export interface AssistantChatResponse {
  answer: string;
  persona: string;
  entityId?: string;
  conversationId: string;
  citations: Array<{
    title: string;
    sourceUrl?: string | null;
    page?: number | null;
    publisher?: string | null;
  }>;
  runReferences: string[];
  downloads: Array<{ format: string; label: string; url: string }>;
  artifacts?: Array<{ format: string; label: string; url: string }>;
  assistantRoute?: 'anomaly' | 'government' | 'clarify';
  charts?: Array<{
    title: string;
    kind?: 'map';
    points?: Array<{ id: string; latitude: number; longitude: number; severity: number; scope: string }>;
    series?: Array<{ label: string; items: Record<string, number> }>;
  }>;
  status: string;
}

export interface ConversationSession {
  id: string;
  title: string;
  conversation_id?: string;
  updated_at?: string | null;
  created_at?: string | null;
  active_workflow?: string | null;
  is_archived?: boolean;
  message_count?: number;
  [key: string]: unknown;
}

class AnalyticsService {
  public getApiBaseUrl(): string {
    return apiClient.getBaseUrl();
  }

  // --- Executive Overview ---
  async getOverview(): Promise<OverviewApiResponse> {
    return apiClient.get<OverviewApiResponse>('/overview');
  }

  // --- Commercial Buildings ---
  async getCommercialBuildings(): Promise<CommercialBuilding[]> {
    return apiClient.get<CommercialBuilding[]>('/entities/commercial');
  }

  async getCommercialBuilding(buildingId: string): Promise<CommercialBuilding> {
    return apiClient.get<CommercialBuilding>(`/entities/commercial/${encodeURIComponent(buildingId)}`);
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
    tab: 'building' | 'regional' | 'portfolio' | 'eui' = 'building',
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

  async getResidentialMeter(householdId: string): Promise<ResidentialMeter> {
    return apiClient.get<ResidentialMeter>(`/entities/residential/${encodeURIComponent(householdId)}`);
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
    entityId?: string,
    historyOrConversationId?: { role: 'user' | 'assistant' | 'system'; content: string }[] | string,
    conversationId?: string
  ): Promise<AssistantResponsePayload> {
    let history: { role: 'user' | 'assistant' | 'system'; content: string }[] | undefined;
    let effectiveConversationId = conversationId;
    if (typeof historyOrConversationId === 'string') {
      effectiveConversationId = historyOrConversationId;
    } else if (Array.isArray(historyOrConversationId)) {
      history = historyOrConversationId;
    }
    return apiClient.post<AssistantResponsePayload>(
      '/assistant/chat',
      {
        prompt,
        persona,
        entity_id: entityId,
        history: history || [],
        ...(effectiveConversationId ? { conversation_id: effectiveConversationId } : {}),
      }
    );
  }

  async askAssistantStream(
    prompt: string,
    persona: string,
    entityId: string | undefined,
    conversationId: string,
    onToken: (token: string) => void,
  ): Promise<AssistantChatResponse> {
    const response = await fetch(`${apiClient.getBaseUrl()}/assistant/chat/stream`, {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt,
        persona,
        entity_id: entityId,
        conversation_id: conversationId,
      }),
    });
    if (!response.ok) {
      const errorBody = await response.json().catch(() => null) as {
        error?: { message?: string; details?: unknown };
      } | null;
      const validationDetails = errorBody?.error?.details
        ? ` Details: ${JSON.stringify(errorBody.error.details)}`
        : '';
      throw new Error(
        `${errorBody?.error?.message || `Assistant request failed (${response.status}).`}${validationDetails}`,
      );
    }
    if (!response.body) {
      throw new Error('Assistant streaming response had no body.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let result: AssistantChatResponse | undefined;
    let streamError: string | undefined;
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const dataLine = frame.split('\n').find((line) => line.startsWith('data: '));
        if (dataLine) {
          const event = JSON.parse(dataLine.slice(6)) as {
            type: string;
            data?: string | AssistantChatResponse | { message?: string };
          };
          if (event.type === 'token' && typeof event.data === 'string') {
            onToken(event.data);
          } else if (event.type === 'complete') {
            result = event.data as AssistantChatResponse;
          } else if (event.type === 'error') {
            streamError = (event.data as { message?: string })?.message || 'Assistant stream failed.';
          }
        }
        boundary = buffer.indexOf('\n\n');
      }
      if (done) break;
    }
    if (streamError) throw new Error(streamError);
    if (!result) throw new Error('Assistant stream ended without a final response.');
    return result;
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

  // --- Persistent Conversation Sessions ---
  async listConversations(params?: {
    include_archived?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<ConversationSession[]> {
    return apiClient.get<ConversationSession[]>('/assistant/conversations', params);
  }

  async createConversation(payload?: {
    title?: string;
    meter_id?: string;
  }): Promise<ConversationSession> {
    return apiClient.post<ConversationSession>('/assistant/conversations', payload || {});
  }

  async getConversation(conversationId: string): Promise<{
    session: ConversationSession;
    messages: Array<{
      id: string;
      role: 'user' | 'assistant' | 'system';
      content: string;
      mode?: string;
      created_at?: string;
    }>;
  }> {
    return apiClient.get<{
      session: ConversationSession;
      messages: Array<{
        id: string;
        role: 'user' | 'assistant' | 'system';
        content: string;
        mode?: string;
        created_at?: string;
      }>;
    }>(`/assistant/conversations/${encodeURIComponent(conversationId)}`);
  }

  async updateConversation(
    conversationId: string,
    payload: { title?: string; is_archived?: boolean }
  ): Promise<ConversationSession> {
    return apiClient.patch<ConversationSession>(
      `/assistant/conversations/${encodeURIComponent(conversationId)}`,
      payload
    );
  }

  async deleteConversation(conversationId: string): Promise<{ deleted: boolean; conversation_id: string }> {
    return apiClient.delete<{ deleted: boolean; conversation_id: string }>(
      `/assistant/conversations/${encodeURIComponent(conversationId)}`
    );
  }

  // --- Dedicated Residential Features ---
  async getResidentialQuestionnaire(featureId: string): Promise<QuestionnaireSchema> {
    return apiClient.get<QuestionnaireSchema>(`/residential/questionnaires/${encodeURIComponent(featureId)}`);
  }

  async planHouseEnergy(payload: Record<string, unknown>): Promise<HouseEnergyPlanningResult> {
    const res = await apiClient.post<Record<string, unknown>>('/residential/plan-house-energy', payload);
    return ((res && (res as { results?: HouseEnergyPlanningResult }).results)
      ? (res as { results: HouseEnergyPlanningResult }).results
      : res) as HouseEnergyPlanningResult;
  }

  async analyzeApplianceScenario(payload: Record<string, unknown>): Promise<ApplianceScenarioResult> {
    const res = await apiClient.post<Record<string, unknown>>('/residential/analyze-appliance', payload);
    return ((res && (res as { results?: ApplianceScenarioResult }).results)
      ? (res as { results: ApplianceScenarioResult }).results
      : res) as ApplianceScenarioResult;
  }

  async manageEnergyCost(payload: Record<string, unknown>): Promise<CostManagementResult> {
    const res = await apiClient.post<Record<string, unknown>>('/residential/manage-cost', payload);
    return ((res && (res as { results?: CostManagementResult }).results)
      ? (res as { results: CostManagementResult }).results
      : res) as CostManagementResult;
  }

  async createResidentialSession(
    featureId: string,
    entityId?: string
  ): Promise<{ session_id: string; status: string }> {
    return apiClient.post<{ session_id: string; status: string }>('/residential/sessions', {
      feature_id: featureId,
      entity_id: entityId,
    });
  }

  async updateResidentialSession(
    sessionId: string,
    payload: Record<string, unknown>
  ): Promise<{ session_id: string; status: string }> {
    return apiClient.put<{ session_id: string; status: string }>(
      `/residential/sessions/${encodeURIComponent(sessionId)}`,
      payload
    );
  }
}

export const analyticsService = new AnalyticsService();
