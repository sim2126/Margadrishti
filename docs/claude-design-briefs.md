# Margadrishti — Claude Design briefs

Paste these into **Claude Design** (pick **Prototype** for app screens, **Slides** for the
deck). Model: Opus 4.8. Personalise the teal hex to the logo before pasting.

Shared palette (use in all briefs):
- Dark: bg `#0a0c10` · surface `#11151c` · surface-2 `#161b24` · border `#232a35` · text `#e7ecf3` · muted `#8b97a8`
- Brand accent: teal (match logo, ~`#2dd4bf`); brand navy `#071e3b`
- Impact ramp (low→critical): `#1f6feb → #4cc38a → #e3b341 → #f0883e → #f85149`
- Light: bg `#f4f6fa` · surface `#ffffff` · surface-2 `#eef1f6` · border `#d9dfe9` · text `#111722` · muted `#5a6573`
- Font: Inter, tabular numerals. Tone: government command-center, ESRI-credible, Linear/Vercel restraint. Never glossy/consumer.

---

## 1) Command Center (web app) — Prototype

```text
Design "Margadrishti" — a Traffic Operations Command Center for the Bengaluru Traffic
Police. Desktop-first web app. It detects illegal-parking hotspots, scores their
congestion impact (CII), forecasts risk, simulates what-if lane blockages, and recommends
patrol deployments — on data the city already collects. Name shown with a teal SVG mark.

Audience: government traffic-police operators (DCP down to field constable). Vibe: an
operational command center with the credibility of an ESRI real-time crime center and the
restraint of Linear/Vercel. Data-dense, calm, trustworthy. NOT consumer SaaS, no
decorative gradients, no stock art, no emoji.

Theme: dark by DEFAULT + a clean light theme (header toggle, persisted). Map basemap dark
(carto dark-matter) in dark, light (positron) in light. One warm "impact" ramp ONLY for
congestion severity, separate from the teal brand accent.

[Insert shared palette + font from the top of this file.]

Layout — full viewport, NEVER page-scrolls; only inner panels scroll:
- Slim top KPI header: logo + "Margadrishti · Command Center · Bengaluru Traffic Police";
  4 centered KPI tiles — "Observed enforcement 9,408 (label: not prevalence)",
  "Segments tracked 7,284", "Mean CII 0.207", "Zones 8"; right side: zone dropdown
  (All zones), active model badge, dark/light toggle.
- 3 columns: LEFT (320px) ranked hotspot list; CENTER the map; RIGHT (380px) tabbed
  workspace. Each scrolls internally.
- Bottom: full-width time-of-day scrubber (play/pause + 0–23h slider, "18:00 IST"),
  caveat "map shows all-day aggregate".

Center map: dark Bengaluru map with a 3D-extruded H3 hexagon heatmap colored by the impact
ramp (taller/redder = higher CII). Hover tooltip: road label + "CII 0.98 · observed 53".
Small legend Low→Critical. Click a hex → selects segment, fills right rail.

Left rail rows: rank, severity bar, road name with distinct sub-label ("Hosur Road ·
BTP137 – Madiwala Traffic PS Junction · 4176"), "53 observed", CII pill tinted by severity.

Right rail — 4 tabs:
- Detail: title + severity badge; 3×2 stat grid (CII, predicted risk, observed, approval
  rate, officers, active hours); "Why this score" horizontal bars (predicted risk /
  centrality / obstruction); "Evidence & data gaps" card with chips (observed/predicted/
  simulated) + honest bullets ("No live traffic feed", "No flow/speed measurement —
  congestion impact is modelled, not observed", "Direction approximate"); Provenance
  footer (as-of, model version, dataset version).
- What-if: sliders "Lanes blocked (1–3)" + "Duration (min)" + "Run simulation"; results
  show capacity drop (5400→3600 veh/hr, "33% loss"), spillover index, ranked "most
  affected downstream", amber caveat "Simulated estimate, not measured flow". On the map,
  the blocked segment glows teal and affected downstream light up (base hexes dim).
- Copilot: chat ("Enforcement Copilot") with suggestion chips; answers show tool-call
  chips + model name; answers only from data, never invents numbers.
- Deploy: zone + units + shift → "Generate plan"; per-unit route cards (ordered labelled
  stops, minutes, count), coverage %, "priority utility" total, amber method-caveat, and
  a clear "Requires human approval before tasking" notice.

Credibility rules (the differentiator — show them): provenance on every number; CII is a
"prioritisation proxy" not measured congestion; simulation is "modelled, not measured";
system recommends, human approves; show data gaps honestly; counts are "observed
enforcement" not "prevalence"; no vehicle numbers / officer IDs anywhere.

States: hover + selected on hexes/rows; loading skeletons (not spinners); polished empty
states; focus rings; subtle transitions only.

Deliver: dark Command Center (all 4 tabs as states), the What-if ACTIVE state, a light
theme version. Use real Bengaluru names (Koramangala, Hosur Road, 80 Feet Road, Adugodi,
HSR Layout, Madiwala) and realistic numbers.
```

---

## 2) Pitch deck (GRID finale) — Slides

```text
Design a 12-slide investor/government pitch deck for "Margadrishti" — AI-driven parking
intelligence for the Bengaluru Traffic Police (Flipkart GRID finale, Theme 1: Parking-
Induced Congestion). Audience: subject-matter experts + Bengaluru Traffic Police
leadership. Tone: confident, evidence-grounded, government-credible. Dark command-center
aesthetic with a teal accent (NOT a startup-y pastel deck). Big type, one idea per slide,
generous whitespace, real Bengaluru data.

[Insert shared palette + font from the top of this file.]

Slides:
1. Title — "Margadrishti — Parking Intelligence for Targeted Enforcement", tagline
   "See the choke points before they choke the city", BTP + GRID context, teal mark on
   dark.
2. The problem — on-street illegal parking near commercial areas, metro & events chokes
   carriageways. Three pain points as cards: enforcement is patrol-based & reactive; no
   heatmap of violations vs congestion impact; hard to prioritise zones.
3. Why it's hard today — no flow sensors, biased patrol data, static enforcement. One
   honest line: "the city has the data; it lacks the lens."
4. Our approach — one diagram: data the city already collects → map-match to road
   segments → Congestion-Impact Index → forecast → what-if simulation → deployment plan,
   human-approved. Emphasise "no new cameras/sensors/hardware".
5. Differentiator 1 — CII heatmap: a striking 3D H3 hotspot map of Bengaluru; caption
   "where + why + how bad, on one screen". Label CII a prioritisation proxy.
6. Differentiator 2 — What-if flow simulation: "if illegal parking blocks a lane here,
   which downstream junctions back up?" Show a blocked segment + spillover. Caption
   "modelled estimate, validated against speed data — not a black box".
7. Differentiator 3 — Honest, evidence-grounded AI: provenance on every number; observed
   enforcement ≠ prevalence; bias-adjusted risk; model ships only if it beats baselines on
   held-out weeks AND unseen zones; human approves every deployment. "Trust is the
   feature."
8. Live demo moment — a screenshot of the command center with the copilot answering
   "Where should I deploy 3 units in Madiwala tonight?" + a route plan.
9. Scalability — runs on existing violation logs; H3 + road graph scale from one junction
   to all of Karnataka; modular monolith (PostGIS, workers, vector tiles). "No pilot
   hardware to procure."
10. Impact & roadmap — targeted enforcement, measured outcomes (closed loop), Kannada
    field app; phases: heatmap → forecast → simulate → measure.
11. Why us / viability — "a DCP could deploy this tomorrow on data they already own."
12. Ask / close — what we need next (pilot zone, speed-API access), teal mark, contact.

Use real areas (Gandhi Nagar, Chickpete, Shivaji Nagar, Koramangala, Hosur Road) and
realistic figures (≈298K violation records, 8 zones). Avoid buzzword soup, fake metrics,
and any claim that flow/congestion was measured rather than modelled.
```

---

## 3) Field constable — mobile (single screen) — Prototype

```text
Design ONE mobile screen (phone) for "Margadrishti" — the field-constable view. Dark
command-center theme, teal accent, large tap targets, glanceable, minimal. NOT a full app
— one polished frame proving the role.

[Insert shared palette + font from the top of this file.]

Content:
- Top bar: "Your shift · Madiwala · 18:00–22:00 IST", small teal mark, sync status.
- "Your spots this shift": 3–4 large cards, each = road name + junction ("80 Feet Road ·
  UCO Bank Junction"), a severity chip (Critical/High, impact-ramp colour), a one-line
  "why" ("recurring evening wrong-parking; chokes the junction"), distance/ETA, and a map
  pin mini-thumbnail.
- A compact map mini-view with the assigned pins.
- Sticky bottom: one big primary button "Log action" (teal), secondary "Navigate".
- Footer microcopy: "Advisory — confirm on the ground. No vehicle/officer data shown."

Keep it calm and operational: no charts, no clutter, one decision per card. Use real
Bengaluru names and realistic severity.
```
