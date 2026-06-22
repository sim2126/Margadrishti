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

export interface CopilotResponse {
  answer: string;
  tool_calls: string[];
  model: string;
  provenance: Array<Record<string, unknown>>;
}
