import { useCii } from "@/lib/api";
import { cn, ciiCss, ciiLabel } from "@/lib/utils";
import { useUi } from "@/store/ui";
import { Badge, StatLabel } from "./ui";

export function HotspotList() {
  const zone = useUi((s) => s.zone);
  const selected = useUi((s) => s.selectedSegment);
  const select = useUi((s) => s.select);
  const { data, isLoading } = useCii(zone, 200);

  const top = (data?.segments ?? []).slice(0, 50);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <StatLabel>Hotspots {zone ? `· ${zone}` : "· all zones"}</StatLabel>
        <span className="text-[11px] text-[--color-muted]">{top.length} segments</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-4 text-sm text-[--color-muted]">Loading…</p>}
        {top.map((s, i) => (
          <button
            key={s.physical_id}
            onClick={() => select(s.physical_id)}
            className={cn(
              "flex w-full items-center gap-3 border-b border-[--color-border]/60 px-4 py-2.5 text-left transition-colors hover:bg-[--color-surface-2]",
              selected === s.physical_id && "bg-[--color-surface-2]",
            )}
          >
            <span className="w-5 shrink-0 text-right text-xs tabular-nums text-[--color-muted]">
              {i + 1}
            </span>
            <span
              className="h-8 w-1 shrink-0 rounded-full"
              style={{ background: ciiCss(s.cii) }}
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-[--color-fg]">{s.name ?? "Unnamed road"}</span>
              <span className="block truncate text-[11px] text-[--color-muted]">
                {s.junction ?? s.zone ?? "—"} · {s.observed_count} observed
              </span>
            </span>
            <Badge
              className="shrink-0"
              style={{ borderColor: ciiCss(s.cii), color: ciiCss(s.cii) }}
            >
              {s.cii.toFixed(2)}
            </Badge>
          </button>
        ))}
        {!isLoading && top.length === 0 && (
          <p className="p-4 text-sm text-[--color-muted]">No segments for this filter.</p>
        )}
      </div>
      {top[0] && (
        <div className="border-t px-4 py-2 text-[11px] text-[--color-muted]">
          Top: {ciiLabel(top[0].cii)} impact — {top[0].label}
        </div>
      )}
    </div>
  );
}
