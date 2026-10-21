/**
 * GridVision — Analytics Domain TypeScript Definitions
 * Accurately models the multi-persona domain logic from the reference project
 * (Residential Month-End, Commercial BDG2 Buildings, Government 17-Site Regional Grid).
 */

export type TrendDirection = 'up' | 'down' | 'neutral';
export type SeverityLevel = 'critical' | 'warning' | 'info' | 'success';
export type TimeRange = '24h' | '7d' | '30d' | '90d' | '1Y';
export type SectorPersona = 'commercial' | 'residential' | 'government';

export interface KpiMetric {
  id: string;
  title: string;
  value: string | number;
  unit: string;
  changePercent?: number;
  changePeriod?: string;
  trend?: TrendDirection;
  isPositiveGood?: boolean;
  subtext: string;
  badge?: string;
  badgeVariant?: 'cyan' | 'teal' | 'amber' | 'neutral' | 'danger';
  category?: 'consumption' | 'forecast' | 'peak' | 'anomaly' | 'efficiency';
}

export interface TimeSeriesPoint {
  timestamp: string;
  formattedTime: string;
  actualDemand: number | null;
  forecastDemand: number | null;
  actualDemandMw?: number | null;
  forecastDemandMw?: number | null;
  upperConfidence?: number | null;
  lowerConfidence?: number | null;
  peakThreshold?: number | null;
  peakThresholdMw?: number | null;
  unit?: string;
}

export type AnomalyItem = AnomalyEvent;
export type PeakDemandSummary = PeakDemandAnalysis;

export interface CommercialBuilding {
  buildingId: string;
  siteId: string;
  primarySpaceUsage: string;
  sqm: number;
  yearBuilt: number;
  recentDemandKwh: number;
  predictedDemandKwh: number;
  absErrorKwh: number;
  pctError: number;
  lastTimestamp: string;
}

export interface ResidentialMeter {
  householdId: string;
  dailyKwh: number;
  actualCycleKwhSoFar: number;
  targetRemainingKwh: number;
  predictedRemainingKwh: number;
  estimatedMonthEndKwh: number;
  estimatedMonthEndBillInr: number;
  coverageRatio: number;
  elapsedDays: number;
  lastDate: string;
}

export interface HouseholdConsumptionPoint {
  time: string;
  actualConsumption: number | null;
  predictedConsumption: number | null;
  actualNote?: string;
  predictedNote?: string;
  fullDate?: string;
}

export interface HouseholdOverview {
  householdId: string;
  userName: string;
  timeRange?: string;
  currentDailyUsageKwh: number;
  dailyAvgKwh: number;
  dailyAvgChangePct: number;
  prev7DaysAvgKwh: number;
  monthlyAvgKwh: number;
  monthlyAvgChangePct: number;
  prevMonthKwh: number;
  predictedMonthEndKwh: number;
  predictedMonthEndBillInr?: number;
  tariffRate?: number;
  demarcationTime?: string;
  actualCallout?: {
    time: string;
    value: number;
    dateText: string;
    label: string;
    color: string;
  };
  predictedCallout?: {
    time: string;
    value: number;
    dateText: string;
    label: string;
    color: string;
  };
  consumptionCurve: HouseholdConsumptionPoint[];
}

export interface RegionalSite {
  siteId: string;
  buildingCount: number;
  totalDemandKwh: number;
  predictedDemandKwh: number;
  peakHourKwh: number;
  shareOfTotalPct: number;
  season: string;
}

export interface PeakDemandAnalysis {
  expectedPeakMw: number;
  expectedPeakTime: string;
  currentLoadMw: number;
  peakCapacityLimitMw: number;
  reserveMarginPct: number;
  riskLevel: 'low' | 'moderate' | 'elevated' | 'critical';
  historicalCyclePeakMw: number;
  mitigationStrategy: string;
  hourlyDistribution: { hour: number; hourLabel: string; avgDemandMw: number; peakFrequencyPct: number }[];
  dailyPeakTimeline: { date: string; dayLabel: string; peakMw: number; thresholdMw: number }[];
}

export interface AnomalyEvent {
  id: string;
  entityId: string;
  entityName: string;
  entityType: 'Substation' | 'Commercial Facility' | 'Residential Feeder' | 'Industrial Plant';
  detectedAt: string;
  anomalyType: 'Unusual Spike' | 'Baseload Drift' | 'Sensor Drop' | 'Phase Imbalance' | 'Negative Energy';
  severity: SeverityLevel;
  deviationPercent: number;
  baselineDemandKw: number;
  observedDemandKw: number;
  status: 'investigating' | 'confirmed' | 'resolved' | 'dismissed';
  rootCauseDiagnosis?: string;
  recommendedAction?: string;
}

export interface CustomerSegment {
  id: string;
  name: string;
  sharePercentage: number;
  demandMwh: number;
  entityCount: number;
  growthPct: number;
  color: string;
  description: string;
  avgDailyKwh: number;
  peakWindow: string;
}

export interface DiurnalCurvePoint {
  hour: number;
  hourLabel: string;
  commercialLoad: number;
  residentialLoad: number;
  governmentLoad: number;
}

export interface BusinessInsight {
  id: string;
  category: 'peak_shaving' | 'efficiency' | 'renewable' | 'grid_stress';
  title: string;
  description: string;
  impactMetric: string;
  potentialValue: string;
  actionableRecommendation: string;
  urgency: 'high' | 'medium' | 'low';
  sector: SectorPersona | 'all';
}

export interface RegionalRankingItem {
  siteId: string;
  demandKwh: number;
  buildingCount: number;
  percentageOfSystem: number;
}

export interface HistoricalDailyDemandPoint {
  date: string; // e.g. "20 Sep", "12 Oct"
  fullDate: string; // e.g. "12 Oct 2026"
  peakDemand: number; // e.g. 4.1
  avgDemand: number; // e.g. 2.3
  totalConsumption: number; // e.g. 28.6
  peakTime?: string; // e.g. "07:00 PM"
}

export interface HistoricalInsightsData {
  persona: string;
  entityId?: string;
  timeRange: '30D' | '90D' | '1Y' | 'ALL';
  daysReturned: number;
  startDate: string;
  endDate: string;
  avgDailyConsumption: number;
  avgMonthlyConsumption: number;
  peakConsumption: number;
  peakTimestamp: string;
  unit: string;
  historyCurve: HistoricalDailyDemandPoint[];
}

export interface CommercialDashboardPoint {
  time: string;
  actualDemand: number | null;
  predictedDemand: number | null;
  fullDate?: string;
}

export interface CommercialDashboardData {
  tab: 'building' | 'regional';
  buildingId: string;
  regionId: string;
  timeRange: '1D' | '7D' | '1M' | '3M' | '1Y';
  avgDemand: number;
  avgDemandDeltaPct: number;
  prevPeriodAvgDemand: number;
  peakDemand: number;
  peakTimestamp: string;
  predictedPeak: number;
  predictedPeakTimestamp: string;
  predictedTotal: number;
  predictedTotalHorizon: string;
  unit: string;
  totalUnit: string;
  actualCallout?: {
    time: string;
    value: number;
    timestamp: string;
    label: string;
  };
  predictedCallout?: {
    time: string;
    value: number;
    timestamp: string;
    label: string;
  };
  demarcationTime?: string;
  curve: CommercialDashboardPoint[];
}

export interface GovernmentRegionItem {
  id: string;
  name: string;
  currentDemand: number;
  predictedDemand: number;
  deltaPct: number;
  isIncreaseNegative?: boolean;
  pinColor: string;
  sparkline: number[];
  unit: string;
}

export interface GovernmentDashboardData {
  viewType: 'overall' | 'region';
  regionId?: string;
  regionName?: string;
  timeRange: '1D' | '7D' | '1M' | '3M' | '1Y';
  avgDemand: number;
  avgDemandDeltaPct: number;
  prevPeriodAvgDemand: number;
  peakDemand: number;
  peakTimestamp: string;
  predictedPeak: number;
  predictedPeakTimestamp: string;
  predictedTotal: number;
  predictedTotalHorizon: string;
  unit: string;
  totalUnit: string;
  actualCallout?: {
    time: string;
    value: number;
    timestamp: string;
    label: string;
  };
  predictedCallout?: {
    time: string;
    value: number;
    timestamp: string;
    label: string;
  };
  demarcationTime?: string;
  yDomain: [number, number];
  yTicks: number[];
  curve: Array<{
    time: string;
    actualDemand: number | null;
    predictedDemand: number | null;
    fullDate?: string;
  }>;
}

export interface IndustrySegmentItem {
  id: string;
  name: string;
  sharePct: number;
  count: number;
  color: string;
}

export interface TimeOfDayConsumptionItem {
  periodKey: string;
  periodName: string;
  timeRange: string;
  periodLabel: string;
  consumptionMwh: number;
  color: string;
}

export interface RegionalDemandItem {
  regionId: string;
  regionName: string;
  avgDemandMw: number;
  demandLabel: string;
  color: string;
}

export interface CustomerSegmentationData {
  totalCustomers: number;
  industrySegments: IndustrySegmentItem[];
  timeOfDayConsumption: TimeOfDayConsumptionItem[];
  regionalMonthlyDemand: RegionalDemandItem[];
}

export interface ModelRegistryItem {
  id: string;
  modelName: string;
  personaUsed: string;
  version: string;
  status: 'Active' | 'Monitoring' | 'Deprecated';
  lastInference: string;
  mse: number;
  rmse: number;
  r2: number;
}

export interface PlatformHealthSummary {
  totalBuildings: number;
  totalRegions: number;
  dataTimeInterval: string;
  totalDataAccumulated: string;
  dataAccumulatedSubtext: string;
  lastUpdated: string;
  models: ModelRegistryItem[];
}

