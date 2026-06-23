import { useMutation, useQuery } from "@tanstack/react-query";
import type {
  AreaDeploymentPlanResponse,
  AreaSummaryResponse,
  CiiMapResponse,
  CiiSurfaceResponse,
  CopilotResponse,
  DeploymentPlanResponse,
  EvaluationSummaryResponse,
  ForecastResponse,
  LonLat,
  SegmentDetail,
  SimulationResult,
  SurfaceSegment,
  TimeSlicedCiiResponse,
  TrafficContext,
  TrendsResponse,
} from "./types";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// One id per page load — lets the backend apply its per-session copilot cap.
const SESSION_ID = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${path}`);
  return r.json() as Promise<T>;
}
async function post<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${path}`);
  return r.json() as Promise<T>;
}

export const useHealth = () => useQuery({ queryKey: ["health"], queryFn: () => get<Record<string, unknown>>("/health") });

export const useCii = (zone?: string | null, limit = 2000) =>
  useQuery({
    queryKey: ["cii", zone ?? "all", limit],
    queryFn: () => get<CiiMapResponse>(`/segments/cii?limit=${limit}${zone ? `&zone=${encodeURIComponent(zone)}` : ""}`),
  });

function toSurfaceSegment(s: CiiMapResponse["segments"][number]): SurfaceSegment {
  return {
    ...s,
    window_observed_count: s.observed_count,
    hour_intensity: s.cii,
  };
}

function toHourlySurfaceSegment(s: TimeSlicedCiiResponse["segments"][number]): SurfaceSegment {
  return {
    ...s,
    highway: null,
    approval_rate: null,
    observed_count: s.window_observed_count,
    component_risk: 0,
    component_centrality: 0,
    component_obstruction: 0,
  };
}

export const useCiiSurface = (
  zone?: string | null,
  mode: "all_day" | "hourly" = "all_day",
  hour: number | null = null,
  limit = 2000,
) =>
  useQuery({
    queryKey: ["cii-surface", zone ?? "all", mode, hour ?? "all", limit],
    queryFn: async (): Promise<CiiSurfaceResponse> => {
      if (mode === "hourly" && hour != null) {
        const path = `/segments/cii/hourly?hour=${hour}&limit=${limit}${zone ? `&zone=${encodeURIComponent(zone)}` : ""}`;
        const r = await get<TimeSlicedCiiResponse>(path);
        return {
          mode: "hourly",
          hour: r.hour,
          temporal_basis: r.temporal_basis,
          is_observed_not_prevalence: r.is_observed_not_prevalence,
          note: r.note,
          segments: r.segments.map(toHourlySurfaceSegment),
          provenance: r.provenance,
        };
      }
      const r = await get<CiiMapResponse>(`/segments/cii?limit=${limit}${zone ? `&zone=${encodeURIComponent(zone)}` : ""}`);
      return {
        mode: "all_day",
        hour: null,
        temporal_basis: "all_day_cii",
        is_observed_not_prevalence: true,
        note: r.provenance.note ?? "CII is a prioritisation proxy, not measured congestion.",
        segments: r.segments.map(toSurfaceSegment),
        provenance: r.provenance,
      };
    },
  });

export const useSegment = (physicalId: string | null) =>
  useQuery({
    enabled: !!physicalId,
    queryKey: ["segment", physicalId],
    queryFn: () => get<SegmentDetail>(`/segments/${encodeURIComponent(physicalId!)}`),
  });

export const useForecast = (zone?: string | null, limit = 25) =>
  useQuery({
    queryKey: ["forecast", zone ?? "all", limit],
    queryFn: () => get<ForecastResponse>(`/forecast?limit=${limit}${zone ? `&zone=${encodeURIComponent(zone)}` : ""}`),
  });

export const useTrends = () => useQuery({ queryKey: ["trends"], queryFn: () => get<TrendsResponse>("/analytics/trends") });

export const useEvaluationSummary = () =>
  useQuery({ queryKey: ["evaluation"], queryFn: () => get<EvaluationSummaryResponse>("/analytics/evaluation") });

export const useZones = () => useQuery({ queryKey: ["zones"], queryFn: () => get<{ zones: string[] }>("/zones") });

export const useDeploymentPlan = () =>
  useMutation({
    mutationFn: (body: { zone: string; n_units: number; shift_minutes?: number }) =>
      post<DeploymentPlanResponse>("/deployment/plan", body),
  });

const polygonKey = (polygon: LonLat[]) =>
  polygon.map((p) => `${p.lon.toFixed(6)},${p.lat.toFixed(6)}`).join("|");

export const useAreaSummary = (polygon: LonLat[], limit = 8) =>
  useQuery({
    enabled: polygon.length >= 3,
    queryKey: ["area-summary", polygonKey(polygon), limit],
    queryFn: () => post<AreaSummaryResponse>("/area/summary", { polygon, limit }),
  });

export const useAreaDeploymentPlan = () =>
  useMutation({
    mutationFn: (body: { polygon: LonLat[]; limit?: number; n_units: number; shift_minutes?: number }) =>
      post<AreaDeploymentPlanResponse>("/area/deployment/plan", body),
  });

export const useCopilot = () =>
  useMutation({
    mutationFn: (body: { question: string; lang?: string }) =>
      post<CopilotResponse>("/copilot/ask", body, { "x-session-id": SESSION_ID }),
  });

export const useSimulateBlockage = () =>
  useMutation({
    mutationFn: (body: { segment_id: string; lanes_blocked: number; minutes: number }) =>
      post<SimulationResult>("/simulate/blockage", body),
  });

export const useSegmentContext = (physicalId: string | null) =>
  useQuery({
    enabled: !!physicalId,
    queryKey: ["context", physicalId],
    queryFn: () => get<TrafficContext>(`/context/segment/${encodeURIComponent(physicalId!)}`),
  });
