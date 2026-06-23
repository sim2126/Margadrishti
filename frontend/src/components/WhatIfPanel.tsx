import { FlaskConical, X } from "lucide-react";
import { useState } from "react";
import { useSegment, useSimulateBlockage } from "@/lib/api";
import { ciiCss } from "@/lib/utils";
import { useUi } from "@/store/ui";
import { Button, StatLabel } from "./ui";

export function WhatIfPanel() {
  const segment = useUi((s) => s.selectedSegment);
  const sim = useUi((s) => s.sim);
  const setSim = useUi((s) => s.setSim);
  const { data: seg } = useSegment(segment);
  const [lanes, setLanes] = useState(1);
  const [minutes, setMinutes] = useState(45);
  const run = useSimulateBlockage();

  if (!segment)
    return (
      <Empty>Select a segment on the map or hotspot list, then test what happens if illegal
        parking blocks a lane there.</Empty>
    );

  const onRun = () =>
    run.mutate(
      { segment_id: segment, lanes_blocked: lanes, minutes },
      { onSuccess: (r) => setSim(r) },
    );

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <div className="flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-(--color-brand)" />
          <StatLabel>Lane-blockage simulation</StatLabel>
        </div>
        {seg && (
          <p className="mt-1 truncate text-xs text-(--color-muted)">
            {seg.name ?? "Unnamed road"}{seg.junction ? ` · ${seg.junction}` : ""}
          </p>
        )}
      </div>

      <div className="space-y-3">
        <Slider label="Lanes blocked" value={lanes} min={1} max={3} onChange={setLanes} suffix={lanes > 1 ? "lanes" : "lane"} />
        <Slider label="Duration" value={minutes} min={5} max={180} step={5} onChange={setMinutes} suffix="min" />
      </div>

      <Button onClick={onRun} disabled={run.isPending}>
        {run.isPending ? "Simulating…" : "Run simulation"}
      </Button>
      {sim && (
        <Button variant="ghost" size="sm" onClick={() => setSim(null)} className="self-start">
          <X className="h-3.5 w-3.5" /> Clear from map
        </Button>
      )}

      {run.isError && <p className="text-sm text-impact-4">Could not simulate this segment.</p>}

      {sim && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 text-center">
            <Mini label="Capacity" value={`${sim.capacity_before_vph}→${sim.capacity_after_vph}`} sub="veh/hr" />
            <Mini label="Loss" value={`${Math.round(sim.capacity_loss_fraction * 100)}%`} accent={ciiCss(sim.capacity_loss_fraction)} />
            <Mini label="Spillover" value={sim.spillover_index.toFixed(2)} />
          </div>
          <div className="rounded-(--radius) border bg-(--color-surface-2)/40 px-3 py-2 text-xs text-(--color-muted)">
            Est. exposure: <span className="text-(--color-fg)">{sim.est_vehicle_minutes_affected.toLocaleString()}</span> vehicle-minutes ·{" "}
            <span className="text-(--color-fg)">{sim.affected.length}</span> downstream segments affected
          </div>

          <div>
            <StatLabel>Most affected downstream</StatLabel>
            <ol className="mt-2 space-y-1">
              {sim.affected.slice(0, 8).map((a) => (
                <li key={a.physical_id} className="flex items-center gap-2 text-xs">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: ciiCss(Math.min(1, a.impact * 3)) }} />
                  <span className="min-w-0 flex-1 truncate text-(--color-fg)">{a.name ?? "Unnamed road"}</span>
                  <span className="text-(--color-muted)">hop {a.hop} · {a.impact.toFixed(2)}</span>
                </li>
              ))}
            </ol>
          </div>

          <div className="rounded-(--radius) border border-impact-2/40 bg-impact-2/10 p-2.5 text-[11px] text-impact-2">
            ⚠ {sim.caveats}
          </div>
          <div className="text-[10px] text-(--color-muted)">evidence {sim.evidence_id} · kind: {sim.kind}</div>
        </div>
      )}
    </div>
  );
}

function Slider({
  label, value, min, max, step = 1, suffix, onChange,
}: { label: string; value: number; min: number; max: number; step?: number; suffix?: string; onChange: (n: number) => void }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-(--color-muted)">{label}</span>
        <span className="tabular-nums text-(--color-fg)">{value} {suffix}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 w-full cursor-pointer appearance-none rounded-full bg-(--color-surface-2) accent-(--color-brand)"
      />
    </div>
  );
}

function Mini({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="rounded-(--radius) border bg-(--color-surface-2)/40 py-2">
      <div className="text-[10px] uppercase tracking-wider text-(--color-muted)">{label}</div>
      <div className="text-sm font-semibold tabular-nums" style={{ color: accent }}>{value}</div>
      {sub && <div className="text-[9px] text-(--color-muted)">{sub}</div>}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-(--color-muted)">
      {children}
    </div>
  );
}
