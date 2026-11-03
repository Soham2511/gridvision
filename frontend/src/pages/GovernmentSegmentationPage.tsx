import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  MapPin,
  RefreshCw,
  Target,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { LoadingSkeleton } from '../components/common/LoadingSkeleton';
import { usePersona } from '../context';
import { segmentationService } from '../services/segmentationService';
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
import '../styles/segmentation.css';

const GeographicPointsMap = React.lazy(() =>
  import('../components/segmentation/GeographicPointsMap').then((module) => ({
    default: module.GeographicPointsMap,
  })),
);

const PAGE_SIZE = 20;
const REGION_PAGE_SIZE = 100;
const numberFormat = new Intl.NumberFormat('en-US');
const buildingTypeColor = (index: number) =>
  `hsl(${Math.round((index * 137.508) % 360)} 66% 48%)`;

const formatNumber = (value: number | null | undefined, digits = 0) =>
  value == null || !Number.isFinite(value)
    ? '—'
    : value.toLocaleString('en-US', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });

const formatFeature = (value: string) =>
  value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

const formatModelGroup = (value: string) =>
  value === 'SHARED_SMALL_CATEGORIES' ? 'Shared small-category model' : value;

const getPriorityFactors = (priority: SurveyPriority): string[] => {
  let explanation: unknown = priority.priority_explanation;
  if (typeof explanation === 'string') {
    try {
      explanation = JSON.parse(explanation);
    } catch {
      return [];
    }
  }
  if (!explanation || typeof explanation !== 'object') return [];
  return Object.entries(explanation as Record<string, unknown>)
    .filter(([, value]) => value && typeof value === 'object' && 'score' in value)
    .map(([factor, value]) => {
      const score = (value as { score?: number }).score;
      return `${formatFeature(factor)} ${formatNumber(score, 0)}`;
    });
};

const periodTick = (period: SegmentationPeriod) => (value: number) => {
  if (period === 'hourly') return `${String(value).padStart(2, '0')}:00`;
  if (period === 'daily') return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][value] ?? String(value);
  return ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][value - 1] ?? String(value);
};

export const GovernmentSegmentationPage: React.FC = () => {
  const { currentPersona } = usePersona();
  const [overview, setOverview] = useState<SegmentationOverview | null>(null);
  const [profiles, setProfiles] = useState<SegmentationProfile[]>([]);
  const [distribution, setDistribution] = useState<SegmentationDistribution[]>([]);
  const [model, setModel] = useState<SegmentationModelMetadata | null>(null);
  const [regions, setRegions] = useState<SegmentationPage<SegmentationRegion> | null>(null);
  const [assignments, setAssignments] = useState<SegmentationPage<SegmentationAssignment> | null>(null);
  const [priorities, setPriorities] = useState<SegmentationPage<SurveyPriority> | null>(null);
  const [regionDetail, setRegionDetail] = useState<{
    segments: SegmentationRegion[];
    survey_priority: SurveyPriority | null;
  } | null>(null);
  const [timeSeries, setTimeSeries] = useState<SegmentationTimePoint[]>([]);
  const [activeTab, setActiveTab] = useState<'general' | 'behaviour'>('general');
  const [category, setCategory] = useState('');
  const [segmentId, setSegmentId] = useState('');
  const [regionLevel, setRegionLevel] = useState<SegmentationRegionLevel>('coarse');
  const [regionPage, setRegionPage] = useState(1);
  const [selectedRegion, setSelectedRegion] = useState<string | null>(null);
  const [assignmentPage, setAssignmentPage] = useState(1);
  const [priorityPage, setPriorityPage] = useState(1);
  const [period, setPeriod] = useState<SegmentationPeriod>('hourly');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadInitial = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [overviewResult, profilesResult, distributionResult, modelResult] =
        await Promise.all([
          segmentationService.getOverview(),
          segmentationService.getProfiles(),
          segmentationService.getDistribution(),
          segmentationService.getModelMetadata(),
        ]);
      setOverview(overviewResult);
      setProfiles(profilesResult.items);
      setDistribution(distributionResult.items);
      setModel(modelResult);
      setSegmentId((current) => current || profilesResult.items[0]?.segment_id || '');
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load published segmentation outputs.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (currentPersona !== 'government') return;
    void loadInitial();
  }, [currentPersona, loadInitial]);

  const visibleProfiles = useMemo(() => profiles, [profiles]);

  useEffect(() => {
    if (currentPersona !== 'government') return;
    let active = true;
    Promise.all([
      segmentationService.getProfiles(category || undefined),
      segmentationService.getDistribution(category || undefined),
    ])
      .then(([profileResult, distributionResult]) => {
        if (!active) return;
        setProfiles(profileResult.items);
        setDistribution(distributionResult.items);
      })
      .catch((loadError) => {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Unable to filter segmentation categories.');
      });
    return () => { active = false; };
  }, [category, currentPersona]);

  useEffect(() => {
    if (!visibleProfiles.some((profile) => profile.segment_id === segmentId)) {
      setSegmentId(visibleProfiles[0]?.segment_id || '');
    }
  }, [segmentId, visibleProfiles]);

  useEffect(() => {
    if (currentPersona !== 'government') return;
    let active = true;
    segmentationService
      .getRegions({
        level: regionLevel,
        category: category || undefined,
        segment_id: segmentId || undefined,
        page: regionPage,
        page_size: REGION_PAGE_SIZE,
      })
      .then((result) => active && setRegions(result))
      .catch((loadError) => active && setError(loadError instanceof Error ? loadError.message : 'Unable to load regional summaries.'));
    return () => { active = false; };
  }, [category, currentPersona, regionLevel, regionPage, segmentId]);

  useEffect(() => {
    if (currentPersona !== 'government') return;
    let active = true;
    segmentationService
      .getAssignments({
        category: category || undefined,
        segment_id: segmentId || undefined,
        region_level: regionLevel,
        region_id: selectedRegion || undefined,
        page: assignmentPage,
        page_size: PAGE_SIZE,
      })
      .then((result) => active && setAssignments(result))
      .catch((loadError) => active && setError(loadError instanceof Error ? loadError.message : 'Unable to load building assignments.'));
    return () => { active = false; };
  }, [assignmentPage, category, currentPersona, regionLevel, segmentId, selectedRegion]);

  useEffect(() => {
    if (currentPersona !== 'government') return;
    let active = true;
    segmentationService
      .getPriorities({ category: category || undefined, page: priorityPage, page_size: PAGE_SIZE })
      .then((result) => active && setPriorities(result))
      .catch((loadError) => active && setError(loadError instanceof Error ? loadError.message : 'Unable to load survey priorities.'));
    return () => { active = false; };
  }, [category, currentPersona, priorityPage]);

  useEffect(() => {
    if (currentPersona !== 'government' || !segmentId) return;
    let active = true;
    segmentationService
      .getTimeSeries(segmentId, period, category || undefined)
      .then((result) => active && setTimeSeries(result.items))
      .catch((loadError) => active && setError(loadError instanceof Error ? loadError.message : 'Unable to load the segment time profile.'));
    return () => { active = false; };
  }, [category, currentPersona, period, segmentId]);

  useEffect(() => {
    if (currentPersona !== 'government' || !selectedRegion) {
      setRegionDetail(null);
      return;
    }
    let active = true;
    segmentationService
      .getRegionDetail(regionLevel, selectedRegion, category || undefined)
      .then((result) => active && setRegionDetail(result))
      .catch((loadError) => active && setError(loadError instanceof Error ? loadError.message : 'Unable to load region detail.'));
    return () => { active = false; };
  }, [category, currentPersona, regionLevel, selectedRegion]);

  if (currentPersona !== 'government') return <Navigate to="/app" replace />;

  if (loading && !overview) {
    return (
      <div className="gv-seg-page">
        <div className="gv-card"><LoadingSkeleton height="28px" width="45%" /><LoadingSkeleton height="15px" width="70%" /></div>
        <LoadingSkeleton height="125px" count={4} />
        <LoadingSkeleton height="350px" count={2} />
      </div>
    );
  }

  if (!overview && error) {
    return <ErrorState title="Segmentation Data Unavailable" message={error} onRetry={() => void loadInitial()} />;
  }

  if (!overview) return <EmptyState title="No published segmentation run" description="A complete Government segmentation output set has not been published yet." />;

  const categoryOptions = Object.keys(overview.category_building_counts);
  const selectedProfile = profiles.find((profile) => profile.segment_id === segmentId);
  const regionItems = regions?.items ?? [];
  const assignmentItems = assignments?.items ?? [];
  const priorityItems = priorities?.items ?? [];
  const mapPoints = regionItems.filter((region) => region.latitude != null && region.longitude != null);
  const distributionChartItems = distribution.map((item) => ({
    ...item,
    chart_label: category ? item.segment_id : `${item.GeneralUseType} · ${item.segment_id}`,
  }));
  const buildingTypeChartItems = overview.building_type_counts.filter(
    (item) => item.building_count > 0,
  );
  const residentialTypeItems = buildingTypeChartItems.filter(
    (item) => item.ring === 'inner',
  );
  const nonResidentialTypeItems = buildingTypeChartItems.filter(
    (item) => item.ring === 'outer',
  );
  const residentialBuildingCount = residentialTypeItems.reduce(
    (total, item) => total + item.building_count,
    0,
  );
  const regionDemandChartHeight = Math.max(
    280,
    overview.regional_average_energy.length * 26,
  );

  const clearRegionSelection = () => {
    setSelectedRegion(null);
    setAssignmentPage(1);
  };

  return (
    <div className="gv-seg-page">
      <header className="gv-seg-heading">
        <div>
          <h1 className="gv-heading-1">Government Customer Segmentation</h1>
          <p className="gv-text-subtle">
            Groups buildings by observed energy use. Filter by consumer category to compare behaviour profiles and grid locations.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem', flexWrap: 'wrap' }}>
          {/* <span className="gv-seg-status"><Activity size={13} /> Published model outputs</span> */}
          <button type="button" className="gv-button gv-button-secondary" onClick={() => void loadInitial()} disabled={loading}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </header>

      {error && (
        <div role="alert">
          <ErrorState title="Some segmentation data could not be refreshed" message={error} onRetry={() => void loadInitial()} />
        </div>
      )}

      <div className="gv-seg-tabs" role="tablist" aria-label="Segmentation views">
        <button
          id="general-tab"
          className="gv-seg-tab"
          type="button"
          role="tab"
          aria-selected={activeTab === 'general'}
          aria-controls="general-panel"
          onClick={() => setActiveTab('general')}
        >
          General
        </button>
        <button
          id="behaviour-tab"
          className="gv-seg-tab"
          type="button"
          role="tab"
          aria-selected={activeTab === 'behaviour'}
          aria-controls="behaviour-panel"
          onClick={() => setActiveTab('behaviour')}
        >
          Behaviour
        </button>
      </div>

      {activeTab === 'general' && (
        <div id="general-panel" role="tabpanel" aria-labelledby="general-tab" className="gv-seg-tab-panel">
      <div className="gv-seg-grid-2">
        <section className="gv-card gv-seg-card">
          <div className="gv-seg-card-heading">
            <div>
              <h2 className="gv-heading-2">Customer type mix</h2>
              <p className="gv-seg-muted">Residential building groups inside; commercial and other recorded building uses outside.</p>
            </div>
          </div>
          {buildingTypeChartItems.length ? (
            <div className="gv-seg-pie-layout">
              <div className="gv-seg-pie">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Tooltip
                      formatter={(value) => [formatNumber(Number(value)), 'Buildings']}
                      labelFormatter={(_label, payload) => payload[0]?.name ?? ''}
                    />
                    <Pie
                      data={nonResidentialTypeItems}
                      dataKey="building_count"
                      nameKey="label"
                      cx="50%"
                      cy="50%"
                      innerRadius="66%"
                      outerRadius="92%"
                      paddingAngle={0.7}
                      stroke="#fff"
                      strokeWidth={1}
                    >
                      {nonResidentialTypeItems.map((item, index) => (
                        <Cell key={item.label} fill={buildingTypeColor(index + 2)} />
                      ))}
                    </Pie>
                    <Pie
                      data={residentialTypeItems}
                      dataKey="building_count"
                      nameKey="label"
                      cx="50%"
                      cy="50%"
                      innerRadius="43%"
                      outerRadius="64%"
                      paddingAngle={1}
                      stroke="#fff"
                      strokeWidth={1}
                    >
                      {residentialTypeItems.map((item, index) => (
                        <Cell
                          key={item.label}
                          fill={buildingTypeColor(index)}
                        />
                      ))}
                    </Pie>
                    <text
                      x="50%"
                      y="47%"
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fill="#0b1f33"
                      fontSize={13}
                      fontWeight={700}
                    >
                      Residential
                    </text>
                    <text
                      x="50%"
                      y="54%"
                      textAnchor="middle"
                      dominantBaseline="middle"
                      fill="#64748b"
                      fontSize={11}
                    >
                      {numberFormat.format(residentialBuildingCount)} buildings
                    </text>
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul className="gv-seg-pie-legend">
                {buildingTypeChartItems.map((item) => (
                  <li key={item.label}>
                    <span
                      className="gv-seg-pie-swatch"
                      style={{
                        backgroundColor: buildingTypeColor(
                          item.ring === 'inner'
                            ? residentialTypeItems.indexOf(item)
                            : nonResidentialTypeItems.indexOf(item) + 2,
                        ),
                      }}
                    />
                    <span className="gv-seg-pie-label" title={item.label}>{item.label}</span>
                    <strong>{numberFormat.format(item.building_count)}</strong>
                  </li>
                ))}
              </ul>
            </div>
          ) : <EmptyState title="No building types available" description="The published assignments do not contain building-type records." />}
        </section>

        <section className="gv-card gv-seg-card">
          <div className="gv-seg-card-heading">
            <div>
              <h2 className="gv-heading-2">Average demand by region</h2>
              <p className="gv-seg-muted">Mean hourly energy per assigned building in each coarse grid.</p>
            </div>
          </div>
          {overview.regional_average_energy.length ? (
            <div className="gv-seg-region-chart-scroll">
              <div style={{ height: regionDemandChartHeight }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={overview.regional_average_energy}
                    layout="vertical"
                    margin={{ top: 8, right: 18, bottom: 8, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 10 }} />
                    <YAxis
                      type="category"
                      dataKey="region_id"
                      tickFormatter={(value) => `Grid ${value}`}
                      width={58}
                      tick={{ fontSize: 10 }}
                    />
                    <Tooltip
                      labelFormatter={(value) => `Grid ${value}`}
                      formatter={(value, _name, item) => [
                        `${formatNumber(Number(value), 3)} kWh`,
                        `Average per building (${formatNumber(Number(item.payload.building_count))} buildings)`,
                      ]}
                    />
                    <Bar dataKey="average_energy_kwh" name="Average demand" fill="#2563eb" radius={[0, 5, 5, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : <EmptyState title="No regional demand available" description="Regional energy summaries have not been published." />}
        </section>
      </div>
        </div>
      )}

      {activeTab === 'behaviour' && (
        <div id="behaviour-panel" role="tabpanel" aria-labelledby="behaviour-tab" className="gv-seg-tab-panel">
      <section className="gv-seg-kpis" aria-label="Segmentation overview">
        <div className="gv-card gv-seg-kpi">
          <span className="gv-seg-kpi-label">Eligible consumer buildings</span>
          <strong className="gv-seg-kpi-value">{numberFormat.format(overview.eligible_buildings)}</strong>
          <span className="gv-seg-kpi-note">Buildings with enough data for this model</span>
        </div>
        <div className="gv-card gv-seg-kpi">
          <span className="gv-seg-kpi-label">Assigned to a segment</span>
          <strong className="gv-seg-kpi-value">{numberFormat.format(overview.assigned_buildings)}</strong>
          <span className="gv-seg-kpi-note">{numberFormat.format(overview.unassigned_buildings)} without a segment; small categories may share a model</span>
        </div>
        <div className="gv-card gv-seg-kpi">
          <span className="gv-seg-kpi-label">Survey priority regions</span>
          <strong className="gv-seg-kpi-value">{numberFormat.format(overview.region_counts.survey_priority_regions)}</strong>
          <span className="gv-seg-kpi-note">Coarse-grid areas ranked by energy-use indicators</span>
        </div>
        <div className="gv-card gv-seg-kpi">
          <span className="gv-seg-kpi-label">Behaviour segments</span>
          <strong className="gv-seg-kpi-value">{numberFormat.format(profiles.length)}</strong>
          <span className="gv-seg-kpi-note">Profiles in the current category filter</span>
        </div>
      </section>

      <div className="gv-seg-grid-2">
        <section className="gv-card gv-seg-card">
          <div className="gv-seg-card-heading">
            <div>
              <h2 className="gv-heading-2">Behaviour segment distribution</h2>
              <p className="gv-seg-muted">Buildings in each modelled behaviour profile. Category filters apply across the page.</p>
            </div>
            <label className="gv-seg-field">
              Category
              <select value={category} onChange={(event) => {
                setCategory(event.target.value);
                setRegionPage(1);
                setAssignmentPage(1);
                setPriorityPage(1);
                clearRegionSelection();
              }}>
                <option value="">All categories</option>
                {categoryOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
          </div>
          {distributionChartItems.length ? (
            <div className="gv-seg-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={distributionChartItems} margin={{ top: 8, right: 12, left: 0, bottom: 42 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="chart_label" angle={-20} textAnchor="end" interval={0} height={60} tick={{ fontSize: 10 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(value) => [formatNumber(Number(value)), 'Buildings']} />
                  <Bar dataKey="building_count" name="Buildings" fill="#00a396" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <EmptyState title="No segment distribution" description="The published run has no assigned segment records." />}
        </section>

        <section className="gv-card gv-seg-card">
          <div className="gv-seg-card-heading">
            <div>
              <h2 className="gv-heading-2">Selected behaviour profile</h2>
              <p className="gv-seg-muted">Model: {model?.model_version ?? overview.model_version}</p>
            </div>
            <label className="gv-seg-field">
              Segment
              <select value={segmentId} onChange={(event) => {
                setSegmentId(event.target.value);
                setRegionPage(1);
                setAssignmentPage(1);
                clearRegionSelection();
              }}>
                {visibleProfiles.map((profile) => (
                  <option key={profile.segment_id} value={profile.segment_id}>{profile.segment_id}</option>
                ))}
              </select>
            </label>
          </div>
          {selectedProfile ? (
            <>
              <div style={{ display: 'flex', gap: '0.55rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                <span className="gv-badge gv-badge-info">
                  {category || selectedProfile.dominant_general_use_type || selectedProfile.model_category}
                </span>
                <span className="gv-badge gv-badge-neutral">{formatModelGroup(selectedProfile.model_category)}</span>
                <span className="gv-badge gv-badge-neutral">{selectedProfile.algorithm.toUpperCase()}</span>
                <span className="gv-badge gv-badge-neutral">{numberFormat.format(selectedProfile.building_count)} buildings</span>
              </div>
              <h3 className="gv-heading-3">{selectedProfile.segment_name}</h3>
              <p className="gv-seg-muted">Values below are medians for buildings in this profile.</p>
              {selectedProfile.model_category === 'SHARED_SMALL_CATEGORIES' && (
                <p className="gv-seg-note">
                  This segment uses a shared model for smaller consumer categories. Its profile describes the pooled model group.
                </p>
              )}
              <div className="gv-seg-profile-grid">
                {Object.entries(selectedProfile.behaviour_feature_medians).slice(0, 6).map(([feature, value]) => (
                  <div className="gv-seg-profile-stat" key={feature}>
                    <span>{formatFeature(feature)} median</span>
                    <strong>{formatNumber(value, 3)}</strong>
                  </div>
                ))}
              </div>
            </>
          ) : <EmptyState title="Choose a segment" description="Select a segment with a published profile to inspect its measured behaviour." />}
        </section>
      </div>

      <section className="gv-card gv-seg-card">
        <div className="gv-seg-card-heading">
          <div>
            <h2 className="gv-heading-2">Regional map and grid drilldown</h2>
            <p className="gv-seg-muted">Each point is a grid location from the recorded latitude and longitude.</p>
          </div>
          <div className="gv-seg-toolbar" style={{ marginBottom: 0 }}>
            <label className="gv-seg-field">
              Grid level
              <select value={regionLevel} onChange={(event) => {
                setRegionLevel(event.target.value as SegmentationRegionLevel);
                setRegionPage(1);
                clearRegionSelection();
              }}>
                <option value="coarse">Coarse grid</option>
                <option value="finer">Finer grid</option>
              </select>
            </label>
          </div>
        </div>
        <div className="gv-seg-note" style={{ marginBottom: '1rem' }}>
          Circle size shows building count. Select a point to view its grid details and buildings.
        </div>
        {mapPoints.length ? (
          <div className="gv-seg-grid-2">
            <React.Suspense fallback={<div className="gv-seg-map-empty">Loading interactive map…</div>}>
              <GeographicPointsMap
                points={mapPoints}
                selectedRegion={selectedRegion}
                onSelectRegion={(regionId) => {
                  setSelectedRegion(regionId);
                  setAssignmentPage(1);
                }}
              />
            </React.Suspense>
            <div>
              {regionDetail && (
                <div className="gv-seg-note" style={{ marginBottom: '0.75rem' }}>
                  <strong>Selected {regionLevel} region {regionDetail.segments[0]?.region_id ?? selectedRegion}</strong>
                  <div>{numberFormat.format(regionDetail.segments.reduce((sum, row) => sum + row.building_count, 0))} assigned buildings across {regionDetail.segments.length} segment groups.</div>
                </div>
              )}
              <div className="gv-seg-table-wrap">
                <table className="gv-seg-table">
                <thead><tr><th>Region</th><th>Consumer category</th><th>Segment</th><th>Buildings</th><th>Coordinates</th><th /></tr></thead>
                  <tbody>
                    {regionItems.map((region) => {
                      const id = String(region.region_id);
                      const selected = selectedRegion === id;
                      return (
                        <tr key={`${id}-${region.GeneralUseType}-${region.segment_id}`} className={selected ? 'gv-seg-row-selected' : undefined}>
                          <td>{region.region_id}</td><td>{region.GeneralUseType}</td>
                          <td>{region.segment_id}</td>
                          <td>{numberFormat.format(region.building_count)}</td>
                          <td>{formatNumber(region.latitude, 3)}, {formatNumber(region.longitude, 3)}</td>
                          <td><button className="gv-seg-link-button" type="button" onClick={() => {
                            setSelectedRegion(id);
                            setAssignmentPage(1);
                          }}>Buildings</button></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {!regionItems.length && <EmptyState title="No regions match these filters" description="Try another category, segment, or grid level." />}
              </div>
              <Pagination page={regions?.page ?? 1} pages={regions?.pages ?? 0} onChange={setRegionPage} />
            </div>
          </div>
        ) : <EmptyState title="No regional points available" description="There are no coordinate-backed regional summaries for the selected filters." icon={<MapPin size={36} color="var(--gv-text-muted)" />} />}
      </section>

      {regionDetail && (
        <section className="gv-card gv-seg-card">
          <div className="gv-seg-card-heading">
            <div>
              <h2 className="gv-heading-2">Region {selectedRegion} detail</h2>
              <p className="gv-seg-muted">Segment composition and assigned buildings for the selected grid group.</p>
            </div>
            <button type="button" className="gv-button gv-button-secondary" onClick={clearRegionSelection}>Clear region</button>
          </div>
          <div className="gv-seg-table-wrap">
            <table className="gv-seg-table">
                <thead><tr><th>Consumer category</th><th>Segment</th><th>Model group</th><th>Buildings</th><th>Mean energy</th><th>Peak / average</th><th>Variability</th></tr></thead>
                <tbody>{regionDetail.segments.map((row) => (
                  <tr key={`${row.region_id}-${row.GeneralUseType}-${row.segment_id}`}>
                  <td>{row.GeneralUseType}</td><td>{row.segment_id}</td><td>{row.model_category}</td><td>{numberFormat.format(row.building_count)}</td>
                  <td>{formatNumber(row.mean_energy_kwh, 2)} kWh</td><td>{formatNumber(row.mean_peak_to_average_ratio, 2)}</td><td>{formatNumber(row.mean_coefficient_of_variation, 2)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      )}

      <div className="gv-seg-grid-2">
        <section className="gv-card gv-seg-card">
          <div className="gv-seg-card-heading">
            <div>
              <h2 className="gv-heading-2">Segment time profile</h2>
              <p className="gv-seg-muted">Mean energy use (kWh) by hour, day of week, or month for this profile.</p>
            </div>
            <label className="gv-seg-field">
              Period
              <select value={period} onChange={(event) => setPeriod(event.target.value as SegmentationPeriod)}>
                <option value="hourly">Hour of day</option>
                <option value="daily">Day of week</option>
                <option value="monthly">Month</option>
              </select>
            </label>
          </div>
          {timeSeries.length ? (
            <div className="gv-seg-chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={timeSeries} margin={{ top: 8, right: 15, bottom: 6, left: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="period_index" type="number" domain={['dataMin', 'dataMax']} tickFormatter={periodTick(period)} tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip labelFormatter={(value) => periodTick(period)(Number(value))} formatter={(value) => [`${formatNumber(Number(value), 3)} kWh`, 'Mean energy']} />
                  <Line type="monotone" dataKey="mean_energy_kwh" stroke="#087e75" strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : <EmptyState title="No time profile for this segment" description="Published time profiles appear when recorded observations are available." />}
          <p className="gv-seg-muted">Observation window: {overview.observation_start} to {overview.observation_end_exclusive} (end exclusive).</p>
        </section>

        <section className="gv-card gv-seg-card">
          <div className="gv-seg-card-heading">
            <div>
              <h2 className="gv-heading-2">Survey priority regions</h2>
              <p className="gv-seg-muted">Ranks coarse-grid areas by variability, peak use, and segment concentration.</p>
            </div>
            <Target size={20} color="#087e75" />
          </div>
          {priorityItems.length ? (
            <div className="gv-seg-table-wrap">
              <table className="gv-seg-table">
                <thead><tr><th>Rank</th><th>Consumer category</th><th>Coarse grid</th><th>Score</th><th>Buildings</th><th>Factors</th></tr></thead>
                <tbody>{priorityItems.map((priority) => (
                  <tr key={`${priority.GeneralUseType}-${priority.region_id}`}>
                    <td>{priority.priority_rank}</td><td>{priority.GeneralUseType}</td><td>{priority.region_id}</td><td>{formatNumber(priority.priority_score, 1)}</td><td>{numberFormat.format(priority.building_count)}</td>
                    <td><span className="gv-seg-priority-factors">{getPriorityFactors(priority).map((factor) => <span key={factor} className="gv-seg-factor">{factor}</span>)}</span></td>
                  </tr>
                ))}</tbody>
              </table>
              <Pagination page={priorities?.page ?? 1} pages={priorities?.pages ?? 0} onChange={setPriorityPage} />
            </div>
          ) : <EmptyState title="No survey priorities published" description="The completed segmentation run has no priority rows for this category." />}
          <div className="gv-seg-note" style={{ marginTop: '0.9rem' }}>
            These scores describe building use; they are not electric-grid risk scores.
          </div>
        </section>
      </div>

      <section className="gv-card gv-seg-card">
        <div className="gv-seg-card-heading">
          <div>
            <h2 className="gv-heading-2">Building assignments</h2>
            <p className="gv-seg-muted">
              {numberFormat.format(assignments?.total ?? 0)} buildings matching the current category, profile, and region filters{selectedRegion ? ` · ${regionLevel} grid ${selectedRegion}` : ''}
            </p>
          </div>
          <Building2 size={20} color="#087e75" />
        </div>
        {selectedRegion && <button type="button" className="gv-button gv-button-secondary" style={{ marginBottom: '0.75rem' }} onClick={clearRegionSelection}>Show all regions</button>}
        {assignmentItems.length ? (
          <>
            <div className="gv-seg-table-wrap">
              <table className="gv-seg-table">
                <thead><tr><th>Building</th><th>Category</th><th>Segment</th><th>Coarse grid</th><th>Finer grid</th><th>Coverage</th><th>Coordinates</th></tr></thead>
                <tbody>{assignmentItems.map((item) => (
                  <tr key={item.OBJECTID}>
                    <td>{item.OBJECTID}</td><td>{item.GeneralUseType}</td><td>{item.segment_id ?? 'Unassigned'}</td>
                    <td>{item['id.grid.coarse'] ?? '—'}</td><td>{item['id.grid.finer'] ?? '—'}</td>
                    <td>{formatNumber(item.coverage_ratio * 100, 1)}%</td><td>{formatNumber(item.latitude, 3)}, {formatNumber(item.longitude, 3)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <Pagination page={assignments?.page ?? 1} pages={assignments?.pages ?? 0} onChange={setAssignmentPage} />
          </>
        ) : <EmptyState title="No building assignments match" description="Try clearing the region, category, or segment filter." />}
      </section>

        </div>
      )}

    </div>
  );
};

interface PaginationProps {
  page: number;
  pages: number;
  onChange: (page: number) => void;
}

const Pagination: React.FC<PaginationProps> = ({ page, pages, onChange }) => (
  <div className="gv-seg-pagination">
    <span className="gv-seg-muted">Page {page} of {pages || 1}</span>
    <button type="button" className="gv-button gv-button-secondary" aria-label="Previous page" disabled={page <= 1} onClick={() => onChange(page - 1)}>
      <ChevronLeft size={15} />
    </button>
    <button type="button" className="gv-button gv-button-secondary" aria-label="Next page" disabled={pages === 0 || page >= pages} onClick={() => onChange(page + 1)}>
      <ChevronRight size={15} />
    </button>
  </div>
);
