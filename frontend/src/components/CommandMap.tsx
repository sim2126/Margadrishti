import { MapboxOverlay } from "@deck.gl/mapbox";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { ScatterplotLayer } from "@deck.gl/layers";
import { latLngToCell } from "h3-js";
import { useMemo, useState } from "react";
import { Map as MapGL, useControl } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCii } from "@/lib/api";
import type { CiiSegment } from "@/lib/types";
import { ciiColor } from "@/lib/utils";
import { useTheme } from "@/store/theme";
import { useUi } from "@/store/ui";

// Keyless CARTO basemaps — dark-matter for the dark theme, positron for light.
const BASEMAP_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const H3_RES = 9; // ~170m cells: readable city-scale heatmap
const INITIAL = { longitude: 77.625, latitude: 12.932, zoom: 12.4, pitch: 48, bearing: -18 };

interface Hex {
  hex: string;
  cii: number;
  top: CiiSegment;
  count: number;
}

function aggregateToHex(segments: CiiSegment[]): Hex[] {
  const byHex = new Map<string, Hex>();
  for (const s of segments) {
    const hex = latLngToCell(s.centroid_lat, s.centroid_lon, H3_RES);
    const cur = byHex.get(hex);
    if (!cur) byHex.set(hex, { hex, cii: s.cii, top: s, count: s.observed_count });
    else {
      cur.count += s.observed_count;
      if (s.cii > cur.cii) {
        cur.cii = s.cii;
        cur.top = s;
      }
    }
  }
  return [...byHex.values()];
}

function DeckOverlay(props: { layers: unknown[]; interleaved?: boolean }) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props as never));
  overlay.setProps(props as never);
  return null;
}

export function CommandMap() {
  const zone = useUi((s) => s.zone);
  const selected = useUi((s) => s.selectedSegment);
  const select = useUi((s) => s.select);
  const sim = useUi((s) => s.sim);
  const theme = useTheme((s) => s.theme);
  const { data, isLoading, isError } = useCii(zone);
  const [hover, setHover] = useState<{ x: number; y: number; hex: Hex } | null>(null);

  const hexes = useMemo(() => aggregateToHex(data?.segments ?? []), [data]);
  const simActive = !!sim;

  const layer = new H3HexagonLayer({
    id: "cii-h3",
    data: hexes,
    pickable: true,
    extruded: true,
    elevationScale: 18,
    getHexagon: (d: Hex) => d.hex,
    getElevation: (d: Hex) => d.cii * 100,
    getFillColor: (d: Hex) => {
      const [r, g, b] = ciiColor(d.cii);
      const sel = d.top.physical_id === selected;
      const a = simActive ? 60 : sel ? 255 : 165; // dim base when a what-if is active
      return [r, g, b, a] as [number, number, number, number];
    },
    getLineColor: (d: Hex) =>
      (d.top.physical_id === selected ? [255, 255, 255, 255] : [0, 0, 0, 0]) as [number, number, number, number],
    lineWidthMinPixels: 2,
    stroked: true,
    onClick: (info) => info.object && select((info.object as Hex).top.physical_id),
    onHover: (info) =>
      setHover(info.object ? { x: info.x, y: info.y, hex: info.object as Hex } : null),
    updateTriggers: { getFillColor: [selected, simActive], getLineColor: selected },
  });

  // Highlight layer for an active what-if simulation: target + affected downstream.
  const simPoints = sim
    ? [
        ...(sim.target_lat != null && sim.target_lon != null
          ? [{ position: [sim.target_lon, sim.target_lat], impact: 1, isTarget: true }]
          : []),
        ...sim.affected
          .filter((a) => a.centroid_lat != null && a.centroid_lon != null)
          .map((a) => ({ position: [a.centroid_lon!, a.centroid_lat!], impact: a.impact, isTarget: false })),
      ]
    : [];

  const simLayer = new ScatterplotLayer<{ position: number[]; impact: number; isTarget: boolean }>({
    id: "sim-impact",
    data: simPoints,
    pickable: false,
    stroked: true,
    radiusUnits: "pixels",
    lineWidthMinPixels: 1.5,
    getPosition: (d) => d.position as [number, number],
    getRadius: (d) => (d.isTarget ? 11 : 4 + Math.min(1, d.impact * 3) * 8),
    getFillColor: (d) =>
      d.isTarget ? [56, 189, 248, 255] : ([...ciiColor(Math.min(1, d.impact * 3)), 220] as [number, number, number, number]),
    getLineColor: () => [255, 255, 255, 230],
    updateTriggers: { getRadius: sim?.evidence_id, getFillColor: sim?.evidence_id },
  });

  return (
    <div className="relative h-full w-full">
      <MapGL
        initialViewState={INITIAL}
        mapStyle={theme === "light" ? BASEMAP_LIGHT : BASEMAP_DARK}
        attributionControl={false}
      >
        <DeckOverlay layers={simActive ? [layer, simLayer] : [layer]} interleaved />
      </MapGL>

      <div className="pointer-events-none absolute right-4 top-4 rounded-full border bg-(--color-surface)/90 px-2.5 py-1 text-[11px] text-(--color-muted) backdrop-blur">
        H3 r{H3_RES} · 3D impact
      </div>

      {simActive && (
        <div className="absolute left-1/2 top-4 -translate-x-1/2 rounded-full border bg-(--color-surface)/90 px-3 py-1 text-xs text-(--color-fg)">
          What-if active · <span className="text-[#38bdf8]">●</span> blocked segment ·{" "}
          {sim!.affected.length} downstream affected
        </div>
      )}

      {isLoading && (
        <div className="absolute left-1/2 top-4 -translate-x-1/2 rounded-full border bg-(--color-surface)/90 px-3 py-1 text-xs text-(--color-muted)">
          Loading CII surface…
        </div>
      )}
      {!isLoading && isError && (
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 max-w-xs rounded-(--radius) border border-(--color-impact-4)/40 bg-(--color-surface)/95 px-5 py-4 text-center text-sm text-(--color-muted)">
          Couldn't reach the API. Check that the Margadrishti API is running and{" "}
          <code className="text-(--color-fg)">VITE_API_URL</code> points to it.
        </div>
      )}
      {!isLoading && !isError && hexes.length === 0 && (
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-(--radius) border bg-(--color-surface)/95 px-5 py-4 text-center text-sm text-(--color-muted)">
          No CII data for this filter. Run the pipeline (<code className="text-(--color-fg)">make worker</code>)
          or clear the zone filter.
        </div>
      )}
      {hover && (
        <div
          className="pointer-events-none absolute z-10 max-w-[240px] rounded-(--radius) border bg-(--color-surface)/95 px-3 py-2 text-xs shadow-lg"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <div className="font-medium text-(--color-fg)">{hover.hex.top.label}</div>
          <div className="mt-1 text-(--color-muted)">
            CII <span className="text-(--color-fg)">{hover.hex.cii.toFixed(3)}</span> · observed{" "}
            <span className="text-(--color-fg)">{hover.hex.count}</span>
          </div>
        </div>
      )}
      <Legend />
    </div>
  );
}

function Legend() {
  const stops = [0.1, 0.4, 0.65, 0.85, 1];
  return (
    <div className="absolute bottom-4 left-4 rounded-(--radius) border bg-(--color-surface)/90 px-3 py-2 backdrop-blur">
      <div className="mb-1.5 text-[11px] uppercase tracking-wider text-(--color-muted)">
        Congestion-Impact Index
      </div>
      <div className="flex items-center gap-1">
        {stops.map((c) => {
          const [r, g, b] = ciiColor(c);
          return <span key={c} className="h-2.5 w-8" style={{ background: `rgb(${r} ${g} ${b})` }} />;
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-(--color-muted)">
        <span>Low</span>
        <span>Critical</span>
      </div>
    </div>
  );
}
