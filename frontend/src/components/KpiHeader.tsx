import { Moon, Sun } from "lucide-react";
import { useHealth, useTrends, useZones } from "@/lib/api";
import { useTheme } from "@/store/theme";
import { useUi } from "@/store/ui";
import { BrandMark } from "./BrandLogo";
import { Button, StatLabel } from "./ui";

export function KpiHeader() {
  const zone = useUi((s) => s.zone);
  const setZone = useUi((s) => s.setZone);
  const { data: trends } = useTrends();
  const { data: zonesData } = useZones();
  const { data: health, isError: apiDown } = useHealth();
  const theme = useTheme((s) => s.theme);
  const toggleTheme = useTheme((s) => s.toggle);

  const zones = trends?.zones ?? [];
  const totalObserved = zones.reduce((a, z) => a + z.observed_count, 0);
  const totalSegments = zones.reduce((a, z) => a + z.n_segments, 0);
  const meanCii = zones.length ? zones.reduce((a, z) => a + z.mean_cii, 0) / zones.length : 0;

  return (
    <header className="flex items-center justify-between gap-6 border-b bg-[--color-surface] px-5 py-3">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-[--radius] bg-[--color-logo-tile] ring-1 ring-inset ring-[--color-border]">
          <BrandMark className="h-8 w-8" decorative />
        </div>
        <div>
          <div className="text-[15px] font-semibold leading-tight tracking-[-0.01em] text-[--color-fg]">
            Margadrishti
          </div>
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
        {apiDown ? (
          <span
            className="flex items-center gap-1.5 rounded-full border border-[--color-impact-4]/40 bg-[--color-impact-4]/10 px-2.5 py-1 text-[11px] text-[--color-impact-4]"
            title="Cannot reach the Margadrishti API (VITE_API_URL)"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-[--color-impact-4]" /> API offline
          </span>
        ) : (
          <div className="text-right">
            <StatLabel>Model</StatLabel>
            <div className="text-[11px] text-[--color-muted]">
              {(health?.model_version as string) ?? "—"}
            </div>
          </div>
        )}
        <Button
          variant="outline"
          size="icon"
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
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
