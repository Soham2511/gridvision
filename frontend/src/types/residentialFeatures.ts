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
  unit_cost_inr: number;
  total_cost_inr: number;
  provenance: string;
}

export interface EnergyPlanTier {
  tier_name: string;
  tagline: string;
  total_equipment_cost_inr: number;
  estimated_connected_load_kw: number;
  diversified_peak_demand_kw: number;
  estimated_monthly_consumption_kwh: number;
  estimated_monthly_bill_inr: number;
  estimated_annual_bill_inr: number;
  energy_savings_vs_standard_pct: number;
  solar_pv_kwp?: number;
  solar_generation_monthly_kwh?: number;
  net_monthly_bill_inr?: number;
  equipment_schedule: PlannedEquipmentItem[];
  key_features: string[];
}

export interface HouseEnergyPlanningResult {
  property_summary: Record<string, any>;
  preliminary_connected_load_kw: number;
  diversified_maximum_demand_kw: number;
  recommended_plan: EnergyPlanTier;
  alternative_plans: EnergyPlanTier[];
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
