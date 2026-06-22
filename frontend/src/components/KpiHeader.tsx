import { Activity } from "lucide-react";
import { useHealth, useTrends, useZones } from "@/lib/api";
import { useUi } from "@/store/ui";
import { StatLabel } from "./ui";

export function KpiHeader() {
  const zone = useUi((s) => s.zone);
  const setZone = useUi((s) => s.setZone);
  const { data: trends } = useTrends();
  const { data: zonesData } = useZones();
  const { data: health } = useHealth();

  const zones = trends?.zones ?? [];
  const totalObserved = zones.reduce((a, z) => a + z.observed_count, 0);
  const totalSegments = zones.reduce((a, z) => a + z.n_segments, 0);
  const meanCii = zones.length ? zones.reduce((a, z) => a + z.mean_cii, 0) / zones.length : 0;

  return (
    <header className="flex items-center justify-between gap-6 border-b bg-[--color-surface] px-5 py-3">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-[--radius] bg-[--color-brand]/15">
          <Activity className="h-5 w-5 text-[--color-brand]" />
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight text-[--color-fg]">ParkIQ</div>
          <div className="text-[11px] text-[--color-muted]">Command Center · Bengaluru Traffic Police</div>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-center gap-2">
        <Kpi label="Observed enforcement" value={totalObserved.toLocaleString()} hint="not prevalence" />
        <Kpi label="Segments tracked" value={totalSegments.toLocaleString()} />
        <Kpi label="Mean CII" value={meanCii.toFixed(3)} />
        <Kpi label="Zones" value={String(zones.length)} />
      </div>

      <div className="flex items-center gap-3">
        <select
          value={zone ?? ""}
          onChange={(e) => setZone(e.target.value || null)}
          className="h-9 rounded-[--radius] border bg-[--color-surface-2] px-2 text-sm text-[--color-fg]"
        >
          <option value="">All zones</option>
          {(zonesData?.zones ?? []).map((z) => (
            <option key={z} value={z}>
              {z}
            </option>
          ))}
        </select>
        <div className="text-right">
          <StatLabel>Model</StatLabel>
          <div className="text-[11px] text-[--color-muted]">
            {(health?.model_version as string) ?? "—"}
          </div>
        </div>
      </div>
    </header>
  );
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-[120px] rounded-[--radius] border bg-[--color-surface-2]/40 px-4 py-1.5">
      <div className="flex items-baseline gap-1.5">
        <span className="text-lg font-semibold tabular-nums text-[--color-fg]">{value}</span>
        {hint && <span className="text-[10px] text-[--color-muted]">{hint}</span>}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-[--color-muted]">{label}</div>
    </div>
  );
}
