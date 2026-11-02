import { apiClient } from './apiClient';
import {
  SegmentationAssignment,
  SegmentationDistribution,
  SegmentationModelMetadata,
  SegmentationOverview,
  SegmentationPage,
  SegmentationPeriod,
  SegmentationProfile,
  SegmentationRegion,
  SegmentationRegionLevel,
  SegmentationTimePoint,
  SurveyPriority,
} from '../types/segmentation';

const ROOT = '/government/segmentation';

interface ItemsResponse<T> {
  items: T[];
}

export const segmentationService = {
  getOverview: () => apiClient.get<SegmentationOverview>(`${ROOT}/overview`),

  getModelMetadata: () =>
    apiClient.get<SegmentationModelMetadata>(`${ROOT}/model`),

  getProfiles: (category?: string) =>
    apiClient.get<ItemsResponse<SegmentationProfile>>(`${ROOT}/profiles`, {
      category,
    }),

  getDistribution: (category?: string) =>
    apiClient.get<ItemsResponse<SegmentationDistribution>>(
      `${ROOT}/distribution`,
      { category },
    ),

  getTimeSeries: (
    segmentId: string,
    period: SegmentationPeriod,
    category?: string,
  ) =>
    apiClient.get<ItemsResponse<SegmentationTimePoint>>(
      `${ROOT}/profiles/${encodeURIComponent(segmentId)}/time-series`,
      { period, category },
    ),

  getRegions: (params: {
    level: SegmentationRegionLevel;
    category?: string;
    segment_id?: string;
    region_id?: string;
    page: number;
    page_size: number;
  }) => apiClient.get<SegmentationPage<SegmentationRegion>>(`${ROOT}/regions`, params),

  getRegionDetail: (level: SegmentationRegionLevel, regionId: string, category?: string) =>
    apiClient.get<{
      level: SegmentationRegionLevel;
      region_id: number;
      segments: SegmentationRegion[];
      survey_priority: SurveyPriority | null;
    }>(`${ROOT}/regions/${level}/${encodeURIComponent(regionId)}`, { category }),

  getAssignments: (params: {
    category?: string;
    segment_id?: string;
    region_level: SegmentationRegionLevel;
    region_id?: string;
    page: number;
    page_size: number;
  }) =>
    apiClient.get<SegmentationPage<SegmentationAssignment>>(
      `${ROOT}/assignments`,
      params,
    ),

  getPriorities: (params: { category?: string; page: number; page_size: number }) =>
    apiClient.get<SegmentationPage<SurveyPriority>>(`${ROOT}/priorities`, params),
};
