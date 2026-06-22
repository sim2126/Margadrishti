# ParkIQ Frontend — Command Center

Dark, data-dense command-center UI for the Bengaluru Traffic Police. Map-first single
operational picture: **where + why + how bad**, on one screen.

## Stack (2026 production SaaS)

- **Vite + React 19 + TypeScript** — fast dashboard build, no SSR overhead
- **Tailwind v4 + owned shadcn-style primitives** (`components/ui.tsx`) — CSS-first theme
- **TanStack Query** (server state) + **Zustand** (UI state)
- **MapLibre GL** (`react-map-gl`) base map + **deck.gl** `MapboxOverlay` / `H3HexagonLayer`
- Keyless **CARTO dark-matter** basemap (no API token required)

## Layout

```
┌─────────────────────────── KPI header (observed density · segments · mean CII · model) ──┐
│ Hotspots rail │            deck.gl H3 CII heatmap (3D)            │ Detail / Copilot /     │
│ (ranked CII)  │            + hover tooltip + legend               │ Deploy  (tabbed)       │
└───────────────────────────── time-of-day scrubber ───────────────────────────────────────┘
```

- **Command map** — segment CII aggregated to H3 cells (res 9) client-side, extruded +
  coloured by the warm impact ramp; click a hex → inspect its top segment.
- **Detail** — CII, predicted risk, observed counts, the "why" breakdown, and full
  **provenance** (as-of, model/data/feature versions, interim-bias flag).
- **Copilot** — asks the read-only `/copilot/ask` service; shows tool calls + model.
- **Deploy** — zone/units/shift → `/deployment/plan`; routes, coverage, the method
  caveats, and the human-approval notice.

## Run

```bash
cp .env.example .env          # set VITE_API_URL / VITE_TILES_URL
npm install
npm run dev                   # http://localhost:5173
npm run build                 # typecheck + production build
```

Point `VITE_API_URL` at the running ParkIQ API (`docker compose up`, or `make api`).

## Honest notes

- The map currently shows the **all-day aggregate**; the time-of-day scrubber animates a
  clock and is wired into UI state, but per-hour map shading needs a **time-sliced CII
  endpoint** (tracked in `../backend_remaining.md`).
- H3 cells are derived from segment centroids on the client; once the API serves vector
  tiles (`tiles_cii` via Martin) at city scale, the heatmap can switch to MVT tiles.
