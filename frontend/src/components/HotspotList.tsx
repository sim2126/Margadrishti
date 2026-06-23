import { Clock3 } from "lucide-react";
import { useCiiSurface } from "@/lib/api";
import { cn, ciiCss, ciiLabel } from "@/lib/utils";
import { useUi } from "@/store/ui";
import { Badge, StatLabel } from "./ui";

const fmtHour = (h: number) => `${String(h).padStart(2, "0")}:00`;

export function HotspotList() {
  const zone = useUi((s) => s.zone);
  const hour = useUi((s) => s.hour);
  const timeMode = useUi((s) => s.timeMode);
  const selected = useUi((s) => s.selectedSegment);
  const select = useUi((s) => s.select);
  const { data, isLoading } = useCiiSurface(zone, timeMode, hour, 200);

  const top = (data?.segments ?? []).slice(0, 50);
  const hourly = data?.mode === "hourly";

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between">
          <StatLabel>Hotspots {zone ? `· ${zone}` : ""}</StatLabel>
          <span className="text-[11px] text-(--color-muted)">
            {top.length} · {hourly ? `${fmtHour(data.hour ?? hour)} observed` : "by CII"}
          </span>
        </div>
        <p className="mt-0.5 flex items-center gap-1 text-[11px] text-(--color-muted)">
          {hourly && <Clock3 className="h-3 w-3" />}
          {hourly
            ? "Hourly list is observed enforcement timing, not prevalence."
            : "Congestion-Impact Index — a prioritisation proxy."}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-4 text-sm text-(--color-muted)">Loading…</p>}
        {top.map((s, i) => {
          const observed = s.window_observed_count ?? s.observed_count;
          const intensity = s.hour_intensity ?? s.cii;
          return (
            <button
              key={s.physical_id}
              onClick={() => select(s.physical_id)}
              className={cn(
                "flex w-full items-center gap-3 border-b border-(--color-border)/60 px-4 py-2.5 text-left transition-colors hover:bg-(--color-surface-2)",
                selected === s.physical_id && "bg-(--color-surface-2)",
              )}
            >
              <span className="w-5 shrink-0 text-right text-xs tabular-nums text-(--color-muted)">
                {i + 1}
              </span>
              <span
                className="h-8 w-1 shrink-0 rounded-full"
                style={{ background: ciiCss(s.cii), opacity: hourly ? 0.35 + intensity * 0.65 : 1 }}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-(--color-fg)">{s.name ?? "Unnamed road"}</span>
                <span className="block truncate text-[11px] text-(--color-muted)">
                  {s.junction ?? s.zone ?? "—"} · {observed} observed
                  {hourly ? ` · ${Math.round(intensity * 100)}% hour intensity` : ""}
                </span>
              </span>
              <Badge
                className="shrink-0"
                style={{ borderColor: ciiCss(s.cii), color: ciiCss(s.cii) }}
                title="All-day CII proxy"
              >
                {s.cii.toFixed(2)}
              </Badge>
            </button>
          );
        })}
        {!isLoading && top.length === 0 && (
          <p className="p-4 text-sm text-(--color-muted)">No segments for this filter.</p>
        )}
      </div>
      {top[0] && (
        <div className="border-t px-4 py-2 text-[11px] text-(--color-muted)">
          Top: {ciiLabel(top[0].cii)} impact — {top[0].label}
        </div>
      )}
    </div>
  );
}
