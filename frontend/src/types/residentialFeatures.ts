/**
 * GridVision — Residential Energy Platform Feature Types
 * Authoritative contracts matching backend Pydantic domain models.
 */

export type ResidentialFeatureId =
  | 'general_chat'
  | 'house_energy_planning'
  | 'appliance_analysis'
  | 'cost_management';

export type QuestionInputType =
  | 'text'
  | 'number'
  | 'currency'
  | 'dropdown'
  | 'multi_select'
  | 'boolean'
  | 'radio';

export interface QuestionOption {
  value: string;
  label: string;
  description?: string;
}

export interface QuestionCondition {
  depends_on_field: string;
  operator: 'equals' | 'not_equals' | 'in' | 'greater_than';
  expected_value: any;
}

export interface QuestionField {
  field_id: string;
  label: string;
  description?: string;
  tooltip?: string;
  input_type: QuestionInputType;
  required: boolean;
  unit?: string;
  placeholder?: string;
  default_value?: any;
  min_value?: number;
  max_value?: number;
  options?: QuestionOption[];
  conditional_visibility?: QuestionCondition;
  category: string;
  prefill_from_context_key?: string;
}

export interface QuestionnaireSchema {
  feature_id: string;
  title: string;
  subtitle: string;
  description: string;
  field_groups: string[];
  fields: QuestionField[];
}

export interface CalculationAuditItem {
  metric_name: string;
  value: any;
  unit?: string;
  provenance: string;
  methodology: string;
  inputs_used: Record<string, any>;
  notes?: string;
}

// --- Feature 1: House Energy Planning Result ---
export interface PlannedEquipmentItem {
  item_name: string;
  category: string;
  quantity: number;
  rated_power_w: number;
  efficiency_standard: string;
  estimated_daily_hours: number;
  estimated_monthly_kwh: number;
  unit_cost_inr?: number | null;
  total_cost_inr?: number | null;
  cost_status?: 'verified' | 'unavailable' | 'customer_estimate';
  room_assignment?: string | null;
  is_provision_only?: boolean;
  notes?: string | null;
  provenance: string;
}

export interface RoomScheduleItem {
  room_name: string;
  room_type: string;
  equipment: PlannedEquipmentItem[];
  total_connected_load_w: number;
  ac_provision: boolean;
  notes?: string | null;
}

export interface BudgetSummary {
  lighting_fans_cost_inr?: number | null;
  cooling_cost_inr?: number | null;
  water_heating_cost_inr?: number | null;
  other_equipment_cost_inr?: number | null;
  total_equipment_cost_inr: number;
  allocated_budget_inr: number;
  budget_exceeded: boolean;
  budget_variance_inr: number;
  cost_coverage: 'complete' | 'partial' | 'unavailable';
  unpriced_items: string[];
  wiring_installation_note?: string;
}

export interface PracticalRecommendationItem {
  title: string;
  category: string;
  rationale: string;
  source: string;
  expected_benefit: string;
  is_quantitative: boolean;
  estimated_monthly_savings_inr?: number | null;
  estimated_monthly_kwh_saved?: number | null;
}

export interface SolarReadinessAnalysis {
  status: 'feasibility_estimated' | 'preliminary_readiness' | 'not_requested';
  roof_area_available_m2?: number | null;
  roof_access?: 'private' | 'shared' | null;
  recommended_system_kwp?: number | null;
  estimated_monthly_generation_kwh?: number | null;
  estimated_gross_cost_inr?: number | null;
  mnre_estimated_subsidy_inr?: number | null;
  net_investment_inr?: number | null;
  estimated_annual_savings_inr?: number | null;
  simple_payback_years?: number | null;
  feasibility_notes: string[];
  missing_inputs: string[];
}

export interface EvReadinessAnalysis {
  status: 'readiness_planned' | 'not_requested';
  ev_category?: 'two_wheeler' | 'four_wheeler' | 'both' | null;
  recommended_charger_type: string;
  recommended_circuit_rating: string;
  dedicated_circuit_required: boolean;
  safety_guidelines: string[];
  discom_verification_needed: string[];
}

export interface EnergyPlanTier {
  tier_name: string;
  tagline: string;
  total_equipment_cost_inr: number;
  cost_coverage?: 'complete' | 'partial' | 'unavailable';
  estimated_connected_load_kw: number;
  diversified_peak_demand_kw: number;
  recommended_supply_phase?: string;
  supply_phase_advisory?: string;
  estimated_monthly_consumption_kwh: number;
  estimated_monthly_bill_inr: number;
  estimated_annual_bill_inr: number;
  bill_calculation_status?: 'calculated' | 'unavailable';
  bill_calculation_notes?: string | null;
  energy_savings_vs_standard_pct: number;
  solar_pv_kwp?: number | null;
  solar_generation_monthly_kwh?: number | null;
  net_monthly_bill_inr?: number | null;
  equipment_schedule: PlannedEquipmentItem[];
  key_features: string[];
}

export interface HouseEnergyPlanningResult {
  property_summary: Record<string, any>;
  preliminary_connected_load_kw: number;
  diversified_maximum_demand_kw: number;
  recommended_supply_phase?: string;
  recommended_plan: EnergyPlanTier;
  alternative_plans: EnergyPlanTier[];
  has_room_assignment?: boolean;
  room_wise_schedule?: RoomScheduleItem[];
  unassigned_appliances?: string[];
  budget_summary?: BudgetSummary | null;
  recommendations?: PracticalRecommendationItem[];
  solar_readiness?: SolarReadinessAnalysis | null;
  ev_readiness?: EvReadinessAnalysis | null;
  room_wise_load_summary: Array<{
    roomType: string;
    areaM2: number;
    hasAc: boolean;
    dailyOccupancyHours: number;
  }>;
  solar_potential_analysis?: {
    rooftopAreaAvailableM2: number;
    recommendedSystemKwp: number;
    estimatedMonthlyGenerationKwh: number;
    estimatedGrossCostInr: number;
    mnreEstimatedSubsidyInr: number;
    netInvestmentInr: number;
    estimatedAnnualSavingsInr: number;
    simplePaybackYears?: number;
  };
  audit_trail: CalculationAuditItem[];
  assumptions?: string[];
  missing_or_unverified_inputs?: string[];
  technical_disclaimer: string;
}

// --- Feature 2: Appliance Scenario Result ---
export interface YearCashflow {
  year: number;
  baseline_operating_cost_inr: number;
  proposed_operating_cost_inr: number;
  annual_savings_inr: number;
  cumulative_net_savings_inr: number;
}

export interface ApplianceScenarioResult {
  intention: string;
  existing_annual_kwh: number;
  proposed_annual_kwh: number;
  annual_energy_savings_kwh: number;
  annual_cost_savings_inr: number;
  net_upfront_investment_inr: number;
  simple_payback_years?: number;
  break_even_year?: number;
  total_lifecycle_cost_existing_inr: number;
  total_lifecycle_cost_proposed_inr: number;
  net_lifetime_savings_inr: number;
  return_on_investment_pct?: number;
  co2_reduction_kg_per_year: number;
  cashflows: YearCashflow[];
  sensitivity_scenarios: Array<{
    scenarioName: string;
    dailyHours: number;
    annualSavingsInr: number;
    paybackYears?: number;
  }>;
  recommendation_verdict: string;
  audit_trail: CalculationAuditItem[];
}

// --- Feature 3: Cost Management Result ---
export interface CostSavingStrategy {
  strategy_id: string;
  title: string;
  category: 'zero_cost_behavioral' | 'low_cost_quick_win' | 'appliance_upgrade' | 'rooftop_solar';
  description: string;
  action_steps: string[];
  supporting_evidence: string;
  estimated_monthly_savings_kwh: number;
  estimated_monthly_savings_inr: number;
  estimated_annual_savings_inr: number;
  upfront_investment_inr: number;
  simple_payback_months?: number;
  priority_rank: number;
  is_eligible: boolean;
  eligibility_notes?: string;
  provenance: string;
}

export interface CostManagementResult {
  current_monthly_baseline_kwh: number;
  current_monthly_bill_inr: number;
  target_monthly_savings_inr?: number;
  achievable_monthly_savings_inr: number;
  achievable_annual_savings_inr: number;
  total_investment_required_inr: number;
  blended_payback_years?: number;
  strategies: CostSavingStrategy[];
  package_recommendations: {
    packageName: string;
    includedStrategyIds: string[];
    totalUpfrontCostInr: number;
    monthlySavingsInr: number;
    annualSavingsInr: number;
    blendedPaybackYears?: number;
    estimatedBillReductionPct: number;
  };
  audit_trail: CalculationAuditItem[];
  limitations: string[];
}


export interface DocumentCitation {
  source_id: string;
  document_identifier: string;
  publisher: string;
  section: string;
  clause_id?: string;
  page: number;
  text_snippet: string;
  url?: string;
}

export interface AssistantProvenance {
  knowledge_sources_used?: string[];
  structured_references?: Array<{
    parameter_key: string;
    value: any;
    unit: string;
    source_document: string;
    is_verified: boolean;
  }>;
  calculations?: Array<{
    engine_name: string;
    use_case: string;
    inputs: Record<string, any>;
    key_outputs: Record<string, any>;
  }>;
}

export interface AssistantResponsePayload {
  answer: string;
  content?: string;
  persona: string;
  entityId: string;
  customerName?: string;
  isLlmGenerated?: boolean;
  mode?: string;
  status?: string;
  citations?: DocumentCitation[];
  provenance?: AssistantProvenance;
  assumptions?: string[];
  limitations?: string[];
  missing_information?: string[];
  structured_data?: any;
}
