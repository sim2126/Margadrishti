import { create } from "zustand";
import type { SimulationResult } from "@/lib/types";

export type PanelTab = "detail" | "whatif" | "copilot" | "deploy";

interface UiState {
  selectedSegment: string | null;
  zone: string | null; // null = all zones
  hour: number; // 0..23 time-of-day scrubber
  panel: PanelTab;
  sim: SimulationResult | null; // active what-if result (drives map highlight)
  select: (id: string | null) => void;
  setZone: (z: string | null) => void;
  setHour: (h: number) => void;
  setPanel: (p: PanelTab) => void;
  setSim: (r: SimulationResult | null) => void;
}

export const useUi = create<UiState>((set) => ({
  selectedSegment: null,
  zone: null,
  hour: 18, // evening peak — a sensible default for parking enforcement
  panel: "detail",
  sim: null,
  select: (id) => set((s) => ({ selectedSegment: id, panel: id ? "detail" : s.panel })),
  setZone: (z) => set({ zone: z, selectedSegment: null, sim: null }),
  setHour: (h) => set({ hour: h }),
  setPanel: (p) => set({ panel: p }),
  setSim: (r) => set({ sim: r }),
}));
