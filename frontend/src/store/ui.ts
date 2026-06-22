import { create } from "zustand";

export type PanelTab = "detail" | "copilot" | "deploy";

interface UiState {
  selectedSegment: string | null;
  zone: string | null; // null = all zones
  hour: number; // 0..23 time-of-day scrubber
  panel: PanelTab;
  select: (id: string | null) => void;
  setZone: (z: string | null) => void;
  setHour: (h: number) => void;
  setPanel: (p: PanelTab) => void;
}

export const useUi = create<UiState>((set) => ({
  selectedSegment: null,
  zone: null,
  hour: 18, // evening peak — a sensible default for parking enforcement
  panel: "detail",
  select: (id) => set((s) => ({ selectedSegment: id, panel: id ? "detail" : s.panel })),
  setZone: (z) => set({ zone: z, selectedSegment: null }),
  setHour: (h) => set({ hour: h }),
  setPanel: (p) => set({ panel: p }),
}));
