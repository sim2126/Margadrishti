import { FileText, MapPinned, MousePointer2, ShieldCheck } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useAreaDeploymentPlan, useAreaSummary, useDeploymentPlan, useZones } from "@/lib/api";
import type { AreaDeploymentPlanResponse, DeploymentPlanResponse, RouteModel } from "@/lib/types";
import { cn, ciiCss } from "@/lib/utils";
import { useUi } from "@/store/ui";
import { Button, StatLabel } from "./ui";

type Mode = "zone" | "area";

export function DeploymentPanel() {
  const zoneFilter = useUi((s) => s.zone);
  const areaPolygon = useUi((s) => s.areaPolygon);
  const areaDrawing = useUi((s) => s.areaDrawing);
  const setAreaDrawing = useUi((s) => s.setAreaDrawing);
  const clearArea = useUi((s) => s.clearArea);
  const select = useUi((s) => s.select);
  const setActivePlan = useUi((s) => s.setActivePlan);
  const { data: zonesData } = useZones();
  const zones = zonesData?.zones ?? [];
  const [mode, setMode] = useState<Mode>("zone");
  const [zone, setZone] = useState<string>("");
  const [units, setUnits] = useState(3);
  const [shift, setShift] = useState(240);
  const plan = useDeploymentPlan();
  const areaPlan = useAreaDeploymentPlan();
  const areaSummary = useAreaSummary(areaPolygon, 8);

  const effectiveZone = zone || zoneFilter || zones[0] || "";
  const areaReady = areaPolygon.length >= 3;

  useEffect(() => {
    if (areaReady) setMode("area");
  }, [areaReady]);

  useEffect(() => {
    if (plan.data) setActivePlan(plan.data);
  }, [plan.data, setActivePlan]);

  useEffect(() => {
    if (areaPlan.data) setActivePlan(areaPlan.data);
  }, [areaPlan.data, setActivePlan]);

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-(--color-brand)" />
          <StatLabel>Patrol deployment</StatLabel>
        </div>
        <p className="mt-1 text-xs text-(--color-muted)">
          Generate advisory patrol plans from jurisdiction hotspots or a drawn operational area.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2 rounded-(--radius) border bg-(--color-surface-2)/30 p-1">
        <ModeButton active={mode === "zone"} onClick={() => setMode("zone")}>
          Jurisdiction
        </ModeButton>
        <ModeButton active={mode === "area"} onClick={() => setMode("area")}>
          Drawn area
        </ModeButton>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {mode === "zone" ? (
          <Field label="Zone" span={3}>
            <select
              value={effectiveZone}
              onChange={(e) => setZone(e.target.value)}
              className="h-9 w-full rounded-(--radius) border bg-(--color-surface) px-2 text-sm text-(--color-fg)"
            >
              {zones.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </select>
          </Field>
        ) : (
          <div className="col-span-3 rounded-(--radius) border bg-(--color-surface-2)/25 p-3">
            <div className="flex items-start gap-2">
              <MapPinned className="mt-0.5 h-4 w-4 shrink-0 text-(--color-brand)" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-(--color-fg)">
                  {areaReady ? "Operational area selected" : "No area selected"}
                </div>
                <div className="mt-0.5 text-xs text-(--color-muted)">
                  {areaReady
                    ? `${areaPolygon.length} polygon points. Summary is generated from segment centroids inside the area.`
                    : "Use Draw area on the map, then click 3+ points around a corridor or market."}
                </div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant={areaDrawing ? "primary" : "outline"} onClick={() => setAreaDrawing(!areaDrawing)}>
                <MousePointer2 className="h-3.5 w-3.5" />
                {areaDrawing ? "Drawing on" : "Draw on map"}
              </Button>
              <Button size="sm" variant="outline" onClick={clearArea} disabled={!areaPolygon.length}>
                Clear
              </Button>
            </div>
          </div>
        )}

        <Field label="Units">
          <NumInput value={units} min={1} max={20} onChange={setUnits} />
        </Field>
        <Field label="Shift (min)" span={2}>
          <NumInput value={shift} min={30} max={720} step={30} onChange={setShift} />
        </Field>
      </div>

      {mode === "area" && <AreaSummaryCard summary={areaSummary} onSelect={select} />}

      {mode === "zone" ? (
        <Button
          onClick={() => effectiveZone && plan.mutate({ zone: effectiveZone, n_units: units, shift_minutes: shift })}
          disabled={plan.isPending || !effectiveZone}
        >
          {plan.isPending ? "Optimising…" : "Generate jurisdiction plan"}
        </Button>
      ) : (
        <Button
          onClick={() =>
            areaReady && areaPlan.mutate({ polygon: areaPolygon, limit: 80, n_units: units, shift_minutes: shift })
          }
          disabled={areaPlan.isPending || !areaReady}
        >
          {areaPlan.isPending ? "Optimising…" : "Generate area plan"}
        </Button>
      )}

      {plan.isError && <p className="text-sm text-impact-4">Could not build plan for that zone.</p>}
      {areaPlan.isError && <p className="text-sm text-impact-4">Could not build plan for that area.</p>}

      {mode === "zone" && plan.data && <PlanResult plan={plan.data} title={`Zone plan · ${plan.data.zone}`} />}
      {mode === "area" && areaPlan.data && (
        <PlanResult plan={areaPlan.data} title={`Area plan · ${areaPlan.data.area_id}`} />
      )}
    </div>
  );
}

function AreaSummaryCard({
  summary,
  onSelect,
}: {
  summary: ReturnType<typeof useAreaSummary>;
  onSelect: (id: string | null) => void;
}) {
  if (summary.isLoading) {
    return <div className="rounded-(--radius) border p-3 text-sm text-(--color-muted)">Summarising selected area…</div>;
  }
  if (!summary.data) {
    return (
      <div className="rounded-(--radius) border border-dashed p-3 text-sm text-(--color-muted)">
        Draw at least three points to see area summary and candidate hotspots.
      </div>
    );
  }
  const s = summary.data;
  return (
    <div className="space-y-3 rounded-(--radius) border bg-(--color-surface-2)/25 p-3">
      <div className="grid grid-cols-4 gap-2 text-center">
        <Mini label="Segments" value={String(s.n_segments)} />
        <Mini label="Observed" value={s.observed_count.toLocaleString()} />
        <Mini label="Mean CII" value={s.mean_cii.toFixed(2)} />
        <Mini label="Max CII" value={s.max_cii.toFixed(2)} />
      </div>
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <StatLabel>Top area candidates</StatLabel>
          <span className="text-[10px] text-(--color-muted)">{s.zones.slice(0, 2).join(", ")}</span>
        </div>
        <div className="space-y-1">
          {s.top_segments.slice(0, 5).map((seg, i) => (
            <button
              key={seg.physical_id}
              onClick={() => onSelect(seg.physical_id)}
              className="flex w-full items-center gap-2 rounded-(--radius) border border-(--color-border)/50 px-2 py-1.5 text-left hover:bg-(--color-surface-2)"
            >
              <span className="w-4 text-right text-[10px] tabular-nums text-(--color-muted)">{i + 1}</span>
              <span className="h-5 w-1 rounded-full" style={{ background: ciiCss(seg.cii) }} />
              <span className="min-w-0 flex-1 truncate text-xs text-(--color-fg)">{seg.label}</span>
              <span className="text-[10px] tabular-nums text-(--color-muted)">{seg.cii.toFixed(2)}</span>
            </button>
          ))}
        </div>
      </div>
      <p className="text-[11px] text-(--color-muted)">{s.caveats}</p>
    </div>
  );
}

function PlanResult({ plan, title }: { plan: DeploymentPlanResponse | AreaDeploymentPlanResponse; title: string }) {
  const routes = plan.routes;
  const area = "area_caveats" in plan ? plan : null;
  const totalStops = routes.reduce((n, r) => n + r.stops.length, 0);
  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium text-(--color-fg)">{title}</div>
        {area && (
          <div className="text-[11px] text-(--color-muted)">
            {area.n_candidate_segments} candidates from {area.n_segments} in-area segments · zones{" "}
            {area.zones.slice(0, 3).join(", ") || "not available"}
          </div>
        )}
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <Mini label="Units" value={String(routes.length)} />
        <Mini label="Utility" value={plan.total_priority_utility.toFixed(2)} />
        <Mini label="Coverage" value={`${(plan.coverage_fraction * 100).toFixed(0)}%`} />
      </div>
      {routes.map((r) => (
        <RouteCard key={r.unit} route={r} />
      ))}
      <Button variant="outline" size="sm" onClick={() => window.print()} className="no-print w-full">
        <FileText className="h-3.5 w-3.5" />
        Print shift brief
      </Button>
      <div className="print-brief rounded-(--radius) border bg-(--color-surface-2)/30 p-4">
        <div className="mb-3">
          <div className="text-base font-semibold text-(--color-fg)">Margadrishti Shift Brief</div>
          <div className="text-xs text-(--color-muted)">{title}</div>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <Mini label="Units" value={String(routes.length)} />
          <Mini label="Stops" value={String(totalStops)} />
          <Mini label="Coverage" value={`${(plan.coverage_fraction * 100).toFixed(0)}%`} />
        </div>
        <div className="mt-3 space-y-2">
          {routes.map((r) => (
            <div key={r.unit} className="rounded-(--radius) border p-2">
              <div className="mb-1 text-xs font-medium text-(--color-fg)">
                Unit {r.unit + 1} · {r.stops.length} stops · {Math.round(r.minutes)} min
              </div>
              <ol className="space-y-0.5 text-[11px] text-(--color-muted)">
                {r.stops.slice(0, 10).map((st, i) => (
                  <li key={st.physical_id}>
                    {i + 1}. {st.label}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
        <div className="mt-3 text-[11px] leading-relaxed text-(--color-muted)">
          Advisory only. Requires human approval before tasking. {plan.method_caveats}
          {area ? ` ${area.area_caveats}` : ""}
        </div>
        <div className="mt-2 text-[10px] text-(--color-muted)">
          as_of={plan.provenance.as_of} · model={plan.provenance.model_version}
        </div>
      </div>
      <div className="rounded-(--radius) border border-impact-2/40 bg-impact-2/10 p-2.5 text-[11px] text-impact-2">
        ⚠ {plan.method_caveats}
      </div>
      {area && (
        <div className="rounded-(--radius) border p-2.5 text-[11px] text-(--color-muted)">
          {area.area_caveats}
        </div>
      )}
      <div className="rounded-(--radius) border p-2.5 text-[11px] text-(--color-muted)">
        Solver: {plan.solver}. Advisory only — requires human approval before tasking.
      </div>
    </div>
  );
}

function RouteCard({ route }: { route: RouteModel }) {
  return (
    <div className="rounded-(--radius) border bg-(--color-surface-2)/30 p-3">
      <div className="mb-1.5 flex justify-between text-xs">
        <span className="font-medium text-(--color-fg)">Unit {route.unit + 1}</span>
        <span className="text-(--color-muted)">
          {route.stops.length} stops · {Math.round(route.minutes)} min
        </span>
      </div>
      <ol className="space-y-1 text-[11px] text-(--color-muted)">
        {route.stops.slice(0, 8).map((st, i) => (
          <li key={st.physical_id} className="truncate">
            {i + 1}. {st.label}
          </li>
        ))}
        {route.stops.length > 8 && <li>+{route.stops.length - 8} more…</li>}
      </ol>
    </div>
  );
}

function ModeButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-[calc(var(--radius)-3px)] px-3 py-1.5 text-xs font-medium transition-colors",
        active ? "bg-(--color-surface) text-(--color-fg) shadow-sm" : "text-(--color-muted) hover:text-(--color-fg)",
      )}
    >
      {children}
    </button>
  );
}

function Field({ label, span, children }: { label: string; span?: number; children: ReactNode }) {
  return (
    <label className={span === 3 ? "col-span-3" : span === 2 ? "col-span-2" : ""}>
      <span className="mb-1 block text-[11px] text-(--color-muted)">{label}</span>
      {children}
    </label>
  );
}

function NumInput({
  value,
  onChange,
  ...p
}: { value: number; onChange: (n: number) => void } & Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "onChange" | "value"
>) {
  return (
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="h-9 w-full rounded-(--radius) border bg-(--color-surface) px-2 text-sm text-(--color-fg)"
      {...p}
    />
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-(--radius) border bg-(--color-surface-2)/40 py-2">
      <div className="text-[10px] uppercase tracking-wider text-(--color-muted)">{label}</div>
      <div className="text-base font-semibold tabular-nums text-(--color-fg)">{value}</div>
    </div>
  );
}
