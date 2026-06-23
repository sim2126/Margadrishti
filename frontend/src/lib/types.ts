// Mirrors the backend response models (margadrishti/api/models.py). Provenance travels with
// every analytical payload so the UI can always show source / as-of / versions.

export interface Provenance {
  source: string;
  generated_at: string;
  as_of: string;
  dataset_version: string;
  feature_version: string;
  road_network_version: string;
  cii_version: string;
  model_version: string;
  cii_risk_is_interim_biased: boolean;
  note: string | null;
}

export interface CiiSegment {
  physical_id: string;
  name: string | null;
  label: string;
  junction: string | null;
  highway: string | null;
  zone: string | null;
  cii: number;
  observed_count: number;
  approval_rate: number | null;
  centroid_lat: number;
  centroid_lon: number;
  component_risk: number;
  component_centrality: number;
  component_obstruction: number;
}

export interface CiiMapResponse {
  segments: CiiSegment[];
  provenance: Provenance;
}

export interface TimeSlicedSegment {
  physical_id: string;
  name: string | null;
  label: string;
  junction: string | null;
  zone: string | null;
  cii: number;
  window_observed_count: number;
  hour_intensity: number;
  centroid_lat: number;
  centroid_lon: number;
}

export interface TimeSlicedCiiResponse {
  hour: number | null;
  day_of_week: number | null;
  temporal_basis: string;
  is_observed_not_prevalence: boolean;
  note: string;
  segments: TimeSlicedSegment[];
  provenance: Provenance;
}

export interface SurfaceSegment extends CiiSegment {
  window_observed_count?: number;
  hour_intensity?: number;
}

export interface CiiSurfaceResponse {
  mode: "all_day" | "hourly";
  hour: number | null;
  temporal_basis: string;
  is_observed_not_prevalence: boolean;
  note: string;
  segments: SurfaceSegment[];
  provenance: Provenance;
}

export interface SegmentDetail {
  physical_id: string;
  name: string | null;
  label: string;
  junction: string | null;
  zone: string | null;
  cii: number;
  predicted_risk: number | null;
  observed_count: number;
  approved_count: number | null;
  approval_rate: number | null;
  n_officers: number | null;
  active_hours: number | null;
  why: Record<string, number>;
  provenance: Provenance;
}

export interface ForecastItem {
  physical_id: string;
  name: string | null;
  label: string;
  junction: string | null;
  zone: string | null;
  risk: number;
  cii: number | null;
  centroid_lat: number;
  centroid_lon: number;
}
export interface ForecastResponse {
  items: ForecastItem[];
  provenance: Provenance;
}

export interface ZoneTrend {
  zone: string | null;
  n_segments: number;
  observed_count: number;
  mean_cii: number;
}
export interface TrendsResponse {
  label: string;
  zones: ZoneTrend[];
  provenance: Provenance;
}

export interface RouteStop {
  physical_id: string;
  label: string;
  centroid_lat: number | null;
  centroid_lon: number | null;
}
export interface RouteModel {
  unit: number;
  stops: RouteStop[];
  priority_utility: number;
  minutes: number;
}
export interface DeploymentPlanResponse {
  zone: string;
  routes: RouteModel[];
  total_priority_utility: number;
  coverage_fraction: number;
  solver: string;
  method_caveats: string;
  requires_human_approval: boolean;
  provenance: Provenance;
}

export interface LonLat {
  lon: number;
  lat: number;
}

export interface AreaSegment {
  physical_id: string;
  name: string | null;
  label: string;
  junction: string | null;
  zone: string | null;
  cii: number;
  observed_count: number;
  predicted_risk: number | null;
  priority_utility: number;
  centroid_lat: number;
  centroid_lon: number;
}

export interface AreaSummaryResponse {
  area_id: string;
  method: "centroid_in_polygon";
  n_segments: number;
  observed_count: number;
  mean_cii: number;
  max_cii: number;
  zones: string[];
  top_segments: AreaSegment[];
  caveats: string;
  provenance: Provenance;
}

export interface AreaDeploymentPlanResponse {
  area_id: string;
  method: "centroid_in_polygon";
  n_segments: number;
  n_candidate_segments: number;
  zones: string[];
  routes: RouteModel[];
  total_priority_utility: number;
  coverage_fraction: number;
  solver: string;
  method_caveats: string;
  area_caveats: string;
  requires_human_approval: boolean;
  provenance: Provenance;
}

export interface EvalMetric {
  model: string;
  pr_auc: number;
  precision_at_25: number;
  recall_at_25: number;
  n_test_rows: number;
}

export interface EvaluationSummaryResponse {
  model_version: string;
  winner: string;
  a_candidate_shipped: boolean;
  n_input_rows: number;
  n_in_scope_rows: number;
  n_segments: number;
  road_network_version: string;
  rolling_origin: EvalMetric[];
  held_out_zone: EvalMetric[];
  feature_importance: Record<string, number>;
  key_findings: string[];
  caveats: string;
  provenance: Provenance;
}

export interface CopilotResponse {
  answer: string;
  tool_calls: string[];
  model: string;
  provenance: Array<Record<string, unknown>>;
  mode: "live" | "fallback";
  notice: string | null;
}

export interface AffectedSegment {
  physical_id: string;
  name: string | null;
  junction: string | null;
  hop: number;
  impact: number;
  centroid_lat: number | null;
  centroid_lon: number | null;
}

export interface SimulationResult {
  evidence_id: string;
  kind: string;
  target_segment: string;
  target_name: string | null;
  target_lat: number | null;
  target_lon: number | null;
  lanes: number;
  lanes_blocked: number;
  minutes: number;
  capacity_before_vph: number;
  capacity_after_vph: number;
  capacity_loss_fraction: number;
  local_impact: number;
  spillover_index: number;
  est_vehicle_minutes_affected: number;
  affected: AffectedSegment[];
  assumptions: Record<string, unknown>;
  caveats: string;
}

export interface TrafficContext {
  as_of: string;
  generated_at: string;
  focus: { type: string; id: string; name: string | null; zone: string | null };
  horizon_minutes: number;
  observed: { kind: string; cii: number | null; observed_count: number | null };
  predicted: { kind: string; risk: number | null; model_version: string | null; note: string };
  neighborhood: { kind: string; hops: number; segments: Array<{ physical_id: string; name: string | null; hop: number }> };
  simulation: SimulationResult | null;
  uncertainty: {
    cii_risk_is_interim_biased: boolean;
    learned_model_shipped: boolean;
    mean_match_confidence: number | null;
  };
  data_gaps: string[];
  provenance: Provenance;
}
