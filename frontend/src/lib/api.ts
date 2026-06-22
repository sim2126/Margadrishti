import { useMutation, useQuery } from "@tanstack/react-query";
import type {
  CiiMapResponse,
  CopilotResponse,
  DeploymentPlanResponse,
  ForecastResponse,
  SegmentDetail,
  TrendsResponse,
} from "./types";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${path}`);
  return r.json() as Promise<T>;
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
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

export const useZones = () => useQuery({ queryKey: ["zones"], queryFn: () => get<{ zones: string[] }>("/zones") });

export const useDeploymentPlan = () =>
  useMutation({
    mutationFn: (body: { zone: string; n_units: number; shift_minutes?: number }) =>
      post<DeploymentPlanResponse>("/deployment/plan", body),
  });

export const useCopilot = () =>
  useMutation({
    mutationFn: (body: { question: string; lang?: string }) => post<CopilotResponse>("/copilot/ask", body),
  });
