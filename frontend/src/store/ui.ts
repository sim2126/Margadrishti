import { create } from "zustand";
import type { LonLat, SimulationResult } from "@/lib/types";

export type PanelTab = "detail" | "whatif" | "copilot" | "deploy";
export type TimeMode = "all_day" | "hourly";

interface UiState {
  selectedSegment: string | null;
  zone: string | null; // null = all zones
  timeMode: TimeMode;
  hour: number; // 0..23 time-of-day scrubber
  panel: PanelTab;
  sim: SimulationResult | null; // active what-if result (drives map highlight)
  areaDrawing: boolean;
  areaPolygon: LonLat[];
  select: (id: string | null) => void;
  setZone: (z: string | null) => void;
  setTimeMode: (m: TimeMode) => void;
  setHour: (h: number) => void;
  setPanel: (p: PanelTab) => void;
  setSim: (r: SimulationResult | null) => void;
  setAreaDrawing: (on: boolean) => void;
  addAreaPoint: (p: LonLat) => void;
  undoAreaPoint: () => void;
  clearArea: () => void;
}

export const useUi = create<UiState>((set) => ({
  selectedSegment: null,
  zone: null,
  timeMode: "all_day",
  hour: 18, // evening peak, a sensible default for parking enforcement
  panel: "detail",
  sim: null,
  areaDrawing: false,
  areaPolygon: [],
  select: (id) => set((s) => ({ selectedSegment: id, panel: id ? "detail" : s.panel })),
  setZone: (z) => set({ zone: z, selectedSegment: null, sim: null }),
  setTimeMode: (m) => set({ timeMode: m }),
  setHour: (h) => set({ hour: h }),
  setPanel: (p) => set({ panel: p }),
  setSim: (r) => set({ sim: r }),
  setAreaDrawing: (on) => set((s) => ({ areaDrawing: on, panel: on ? "deploy" : s.panel })),
  addAreaPoint: (p) => set((s) => ({ areaPolygon: [...s.areaPolygon, p], panel: "deploy" })),
  undoAreaPoint: () => set((s) => ({ areaPolygon: s.areaPolygon.slice(0, -1) })),
  clearArea: () => set({ areaPolygon: [], areaDrawing: false }),
}));
