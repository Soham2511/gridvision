export type CustomerSegment = 'RESIDENTIAL' | 'COMMERCIAL' | 'GOVERNMENT';

export type ComplaintStatus =
  | 'SUBMITTED'
  | 'VALIDATING'
  | 'INVALID'
  | 'SCORING'
  | 'REGISTERED'
  | 'RESOLVED'
  | 'REJECTED'
  | 'PROCESSING_FAILED';

export type ValidationOutcome = 'INVALID' | 'PLAUSIBLE' | 'INCONCLUSIVE';

export type SeverityLevel = 'Low' | 'Medium' | 'High' | 'Critical';

export interface FormFieldOption {
  value: string;
  label: string;
  description?: string;
}

export interface CategoryFormField {
  field_id: string;
  label: string;
  field_type: 'text' | 'textarea' | 'select' | 'multi_select' | 'boolean' | 'number' | 'datetime' | 'date';
  required: boolean;
  default_value?: any;
  placeholder?: string;
  helper_text?: string;
  tooltip?: string;
  options?: FormFieldOption[];
  min_value?: number;
  max_value?: number;
}

export interface ComplaintCategory {
  category_id: string;
  label: string;
  customer_segment: string;
  description: string;
  icon_name: string;
  badge?: string;
  safety_critical: boolean;
  fields: CategoryFormField[];
  guidance_notes?: string;
}

export interface EvidenceItem {
  source_tool: string;
  metric_name: string;
  observed_value: any;
  expected_or_contradicting_value?: any;
  timestamp_range?: string;
  finding: string;
  supports_invalidation: boolean;
}

export interface ValidationResult {
  outcome: ValidationOutcome;
  reason: string;
  explanation: string;
  evidence_items: EvidenceItem[];
  data_coverage: string;
  timestamps_checked: string[];
  validated_at: string;
}

export interface ScoringFactorBreakdown {
  safety_risk: number;
  disruption_extent: number;
  duration_factor: number;
  recurrence_factor: number;
  essential_services_impact: number;
  safety_override_applied: boolean;
  override_reason?: string;
}

export interface SeverityResult {
  severity_score: number;
  severity_level: SeverityLevel;
  scoring_rationale: string;
  factor_breakdown: ScoringFactorBreakdown;
  benchmark_version: string;
  scored_at: string;
}

export interface StatusTransition {
  from_status?: string;
  to_status: string;
  timestamp: string;
  note?: string;
}

export interface Complaint {
  id: string;
  customer_id: string;
  meter_id: string;
  customer_segment: CustomerSegment;
  category_id: string;
  category_label: string;
  title: string;
  description: string;
  category_data: Record<string, any>;
  status: ComplaintStatus;
  validation_result?: ValidationResult;
  severity_result?: SeverityResult;
  status_history: StatusTransition[];
  customer_care_escalation?: {
    escalation_available: boolean;
    customer_care_contact?: string;
    advisory: string;
  };
  registration_metadata?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface SubmitComplaintPayload {
  category_id: string;
  title: string;
  description: string;
  category_data: Record<string, any>;
  customer_segment?: string;
  entity_id?: string;
  meter_id?: string;
}

