export type SegmentationPeriod = 'hourly' | 'daily' | 'monthly';
export type SegmentationRegionLevel = 'coarse' | 'finer';

export interface SegmentationDistribution {
  GeneralUseType: string;
  segment_id: string;
  model_category: string;
  building_count: number;
  share_of_assigned_buildings: number;
}

export interface SegmentationProfile {
  segment_id: string;
  segment_name: string;
  model_category: string;
  building_count: number;
  share_of_model_buildings: number;
  algorithm: string;
  behaviour_feature_medians: Record<string, number>;
  dominant_general_use_type?: string | null;
}

export interface SegmentationOverview {
  model_version: string;
  observation_start: string;
  observation_end_exclusive: string;
  eligible_buildings: number;
  assigned_buildings: number;
  unassigned_buildings: number;
  category_building_counts: Record<string, number>;
  building_type_counts: Array<{
    ring: 'inner' | 'outer';
    label: string;
    building_count: number;
  }>;
  regional_average_energy: Array<{
    region_id: number;
    average_energy_kwh: number;
    building_count: number;
  }>;
  segments: SegmentationDistribution[];
  region_counts: {
    coarse_segment_rows: number;
    finer_segment_rows: number;
    survey_priority_regions: number;
  };
}

export interface SegmentationRegion {
  region_id: number;
  GeneralUseType: string;
  segment_id: string;
  model_category: string;
  building_count: number;
  mean_energy_kwh: number | null;
  mean_p95_energy_kwh: number | null;
  mean_peak_to_average_ratio: number | null;
  mean_coefficient_of_variation: number | null;
  mean_coverage_ratio: number | null;
  mean_cluster_probability: number | null;
  latitude: number | null;
  longitude: number | null;
}

export interface SegmentationAssignment {
  OBJECTID: number;
  GeneralUseType: string;
  SpecificUseType: string;
  'building.type': string;
  'id.grid.coarse': number | null;
  'id.grid.finer': number | null;
  'id.tract': string | null;
  latitude: number | null;
  longitude: number | null;
  coverage_ratio: number;
  observed_hours: number;
  segment_id: string | null;
  model_category: string | null;
  cluster_probability: number | null;
}

export interface SegmentationTimePoint {
  segment_id: string;
  model_category: string;
  period_index: number;
  mean_energy_kwh: number;
  contributing_buildings: number;
}

export interface SurveyPriority {
  GeneralUseType: string;
  region_id: number;
  priority_rank: number;
  priority_score: number;
  building_count: number;
  target_segment_buildings: number;
  dominant_segment: string;
  dominant_model_category: string;
  latitude: number | null;
  longitude: number | null;
  priority_explanation: Record<string, unknown> | string;
}

export interface SegmentationPage<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface SegmentationModelMetadata {
  model_version: string;
  observation_start: string;
  observation_end_exclusive: string;
  assignment_count: number;
  unassigned_feature_buildings: number;
  trained_models: Array<{
    model_category: string;
    algorithm: string;
    building_count: number;
    cluster_ids: string[];
    evaluation: Record<string, unknown>;
  }>;
}
