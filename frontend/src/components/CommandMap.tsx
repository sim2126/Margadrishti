import { MapboxOverlay } from "@deck.gl/mapbox";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { latLngToCell } from "h3-js";
import { useMemo, useState } from "react";
import { Map as MapGL, useControl } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCii } from "@/lib/api";
import type { CiiSegment } from "@/lib/types";
import { ciiColor } from "@/lib/utils";
import { useUi } from "@/store/ui";

// Keyless dark basemap — command-center aesthetic, no API key required.
const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
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
  const { data, isLoading } = useCii(zone);
  const [hover, setHover] = useState<{ x: number; y: number; hex: Hex } | null>(null);

  const hexes = useMemo(() => aggregateToHex(data?.segments ?? []), [data]);

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
      return [r, g, b, sel ? 255 : 165] as [number, number, number, number];
    },
    getLineColor: (d: Hex) =>
      (d.top.physical_id === selected ? [255, 255, 255, 255] : [0, 0, 0, 0]) as [number, number, number, number],
    lineWidthMinPixels: 2,
    stroked: true,
    onClick: (info) => info.object && select((info.object as Hex).top.physical_id),
    onHover: (info) =>
      setHover(info.object ? { x: info.x, y: info.y, hex: info.object as Hex } : null),
    updateTriggers: { getFillColor: selected, getLineColor: selected },
  });

  return (
    <div className="relative h-full w-full">
      <MapGL initialViewState={INITIAL} mapStyle={BASEMAP} attributionControl={false}>
        <DeckOverlay layers={[layer]} interleaved />
      </MapGL>

      {isLoading && (
        <div className="absolute left-1/2 top-4 -translate-x-1/2 rounded-full border bg-[--color-surface]/90 px-3 py-1 text-xs text-[--color-muted]">
          Loading CII surface…
        </div>
      )}
      {!isLoading && hexes.length === 0 && (
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-[--radius] border bg-[--color-surface]/95 px-5 py-4 text-center text-sm text-[--color-muted]">
          No CII data. Point <code className="text-[--color-fg]">VITE_API_URL</code> at the running
          ParkIQ API and ensure the pipeline has published.
        </div>
      )}
      {hover && (
        <div
          className="pointer-events-none absolute z-10 max-w-[240px] rounded-[--radius] border bg-[--color-surface]/95 px-3 py-2 text-xs shadow-lg"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          <div className="font-medium text-[--color-fg]">{hover.hex.top.label}</div>
          <div className="mt-1 text-[--color-muted]">
            CII <span className="text-[--color-fg]">{hover.hex.cii.toFixed(3)}</span> · observed{" "}
            <span className="text-[--color-fg]">{hover.hex.count}</span>
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
    <div className="absolute bottom-4 left-4 rounded-[--radius] border bg-[--color-surface]/90 px-3 py-2 backdrop-blur">
      <div className="mb-1.5 text-[11px] uppercase tracking-wider text-[--color-muted]">
        Congestion-Impact Index
      </div>
      <div className="flex items-center gap-1">
        {stops.map((c) => {
          const [r, g, b] = ciiColor(c);
          return <span key={c} className="h-2.5 w-8" style={{ background: `rgb(${r} ${g} ${b})` }} />;
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-[--color-muted]">
        <span>Low</span>
        <span>Critical</span>
      </div>
    </div>
  );
}
