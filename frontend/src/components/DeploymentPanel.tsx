import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useDeploymentPlan, useZones } from "@/lib/api";
import { Button, StatLabel } from "./ui";
import { useUi } from "@/store/ui";

export function DeploymentPanel() {
  const zoneFilter = useUi((s) => s.zone);
  const { data: zonesData } = useZones();
  const zones = zonesData?.zones ?? [];
  const [zone, setZone] = useState<string>("");
  const [units, setUnits] = useState(3);
  const [shift, setShift] = useState(240);
  const plan = useDeploymentPlan();

  const effectiveZone = zone || zoneFilter || zones[0] || "";

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-[--color-brand]" />
          <StatLabel>Patrol deployment</StatLabel>
        </div>
        <p className="mt-1 text-xs text-[--color-muted]">
          Generate a patrol plan from current hotspots. Advisory — needs human approval.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Field label="Zone" span={3}>
          <select
            value={effectiveZone}
            onChange={(e) => setZone(e.target.value)}
            className="h-9 w-full rounded-[--radius] border bg-[--color-surface] px-2 text-sm text-[--color-fg]"
          >
            {zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Units">
          <NumInput value={units} min={1} max={20} onChange={setUnits} />
        </Field>
        <Field label="Shift (min)" span={2}>
          <NumInput value={shift} min={30} max={720} step={30} onChange={setShift} />
        </Field>
      </div>

      <Button
        onClick={() => effectiveZone && plan.mutate({ zone: effectiveZone, n_units: units, shift_minutes: shift })}
        disabled={plan.isPending || !effectiveZone}
      >
        {plan.isPending ? "Optimising…" : "Generate plan"}
      </Button>

      {plan.isError && <p className="text-sm text-[--color-impact-4]">Could not build plan (check zone).</p>}

      {plan.data && (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2 text-center">
            <Mini label="Units" value={String(plan.data.routes.length)} />
            <Mini label="Utility" value={plan.data.total_priority_utility.toFixed(2)} />
            <Mini label="Coverage" value={`${(plan.data.coverage_fraction * 100).toFixed(0)}%`} />
          </div>
          {plan.data.routes.map((r) => (
            <div key={r.unit} className="rounded-[--radius] border bg-[--color-surface-2]/30 p-3">
              <div className="mb-1.5 flex justify-between text-xs">
                <span className="font-medium text-[--color-fg]">Unit {r.unit + 1}</span>
                <span className="text-[--color-muted]">
                  {r.stops.length} stops · {Math.round(r.minutes)} min
                </span>
              </div>
              <ol className="space-y-1 text-[11px] text-[--color-muted]">
                {r.stops.slice(0, 8).map((st, i) => (
                  <li key={st.physical_id} className="truncate">
                    {i + 1}. {st.label}
                  </li>
                ))}
                {r.stops.length > 8 && <li>+{r.stops.length - 8} more…</li>}
              </ol>
            </div>
          ))}
          <div className="rounded-[--radius] border border-[--color-impact-2]/40 bg-[--color-impact-2]/10 p-2.5 text-[11px] text-[--color-impact-2]">
            ⚠ {plan.data.method_caveats}
          </div>
          <div className="rounded-[--radius] border p-2.5 text-[11px] text-[--color-muted]">
            Solver: {plan.data.solver}. Advisory only — requires human approval before tasking.
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, span, children }: { label: string; span?: number; children: React.ReactNode }) {
  return (
    <label className={span === 3 ? "col-span-3" : span === 2 ? "col-span-2" : ""}>
      <span className="mb-1 block text-[11px] text-[--color-muted]">{label}</span>
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
      className="h-9 w-full rounded-[--radius] border bg-[--color-surface] px-2 text-sm text-[--color-fg]"
      {...p}
    />
  );
}
function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[--radius] border bg-[--color-surface-2]/40 py-2">
      <div className="text-[10px] uppercase tracking-wider text-[--color-muted]">{label}</div>
      <div className="text-base font-semibold tabular-nums text-[--color-fg]">{value}</div>
    </div>
  );
}
