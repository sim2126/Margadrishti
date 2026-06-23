import { Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useUi } from "@/store/ui";
import { Button } from "./ui";

const fmt = (h: number) => `${String(h).padStart(2, "0")}:00 IST`;
const PEAKS = [
  { h: 8, label: "AM" },
  { h: 13, label: "Midday" },
  { h: 18, label: "PM" },
  { h: 21, label: "Night" },
];

export function TimeScrubber() {
  const hour = useUi((s) => s.hour);
  const mode = useUi((s) => s.timeMode);
  const setHour = useUi((s) => s.setHour);
  const setMode = useUi((s) => s.setTimeMode);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      useUi.setState((s) => ({ hour: (s.hour + 1) % 24, timeMode: "hourly" }));
    }, 850);
    return () => clearInterval(timer);
  }, [playing]);

  return (
    <div className="flex shrink-0 items-center gap-3 border-t bg-(--color-surface) px-5 py-2.5">
      <Button
        variant="outline"
        size="icon"
        onClick={() => {
          setMode("hourly");
          setPlaying((v) => !v);
        }}
        title="Animate observed enforcement by hour"
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>

      <div className="flex rounded-(--radius) border bg-(--color-surface-2)/50 p-0.5 text-xs">
        <button
          onClick={() => {
            setPlaying(false);
            setMode("all_day");
          }}
          className={cn(
            "rounded-[calc(var(--radius)-3px)] px-2.5 py-1 transition-colors",
            mode === "all_day" ? "bg-(--color-surface) text-(--color-fg)" : "text-(--color-muted)",
          )}
        >
          All-day CII
        </button>
        <button
          onClick={() => setMode("hourly")}
          className={cn(
            "rounded-[calc(var(--radius)-3px)] px-2.5 py-1 transition-colors",
            mode === "hourly" ? "bg-(--color-surface) text-(--color-fg)" : "text-(--color-muted)",
          )}
        >
          Hourly observed
        </button>
      </div>

      <span className="w-24 shrink-0 text-sm font-medium tabular-nums text-(--color-fg)">
        {mode === "hourly" ? fmt(hour) : "All day"}
      </span>
      <input
        type="range"
        min={0}
        max={23}
        value={hour}
        disabled={mode === "all_day"}
        onChange={(e) => {
          setMode("hourly");
          setHour(Number(e.target.value));
        }}
        className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-(--color-surface-2) accent-(--color-brand) disabled:cursor-not-allowed disabled:opacity-45"
      />
      <div className="hidden shrink-0 items-center gap-1 lg:flex">
        {PEAKS.map((p) => (
          <button
            key={p.h}
            onClick={() => {
              setPlaying(false);
              setMode("hourly");
              setHour(p.h);
            }}
            className={cn(
              "rounded-full border px-2 py-0.5 text-[10px] transition-colors",
              mode === "hourly" && hour === p.h
                ? "border-(--color-brand) text-(--color-brand)"
                : "border-(--color-border) text-(--color-muted) hover:text-(--color-fg)",
            )}
          >
            {p.label}
          </button>
        ))}
      </div>
      <span className="hidden max-w-[220px] shrink-0 text-[11px] text-(--color-muted) xl:inline">
        Hourly view shows observed enforcement timing, not true prevalence.
      </span>
    </div>
  );
}
