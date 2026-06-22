import { Pause, Play } from "lucide-react";
import { useEffect, useRef } from "react";
import { useUi } from "@/store/ui";
import { Button } from "./ui";

const fmt = (h: number) => `${String(h).padStart(2, "0")}:00 IST`;

export function TimeScrubber() {
  const hour = useUi((s) => s.hour);
  const setHour = useUi((s) => s.setHour);
  const timer = useRef<number | null>(null);
  const playing = useRef(false);

  useEffect(() => () => void (timer.current && clearInterval(timer.current)), []);

  const toggle = () => {
    if (playing.current) {
      timer.current && clearInterval(timer.current);
      playing.current = false;
    } else {
      playing.current = true;
      timer.current = window.setInterval(() => {
        useUi.setState((s) => ({ hour: (s.hour + 1) % 24 }));
      }, 700);
    }
  };

  return (
    <div className="flex items-center gap-4 border-t bg-[--color-surface] px-5 py-2.5">
      <Button variant="outline" size="icon" onClick={toggle} title="Animate the day">
        {playing.current ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <span className="w-24 shrink-0 text-sm font-medium tabular-nums text-[--color-fg]">{fmt(hour)}</span>
      <input
        type="range"
        min={0}
        max={23}
        value={hour}
        onChange={(e) => setHour(Number(e.target.value))}
        className="h-1 flex-1 cursor-pointer appearance-none rounded-full bg-[--color-surface-2] accent-[--color-brand]"
      />
      <span className="shrink-0 text-[11px] text-[--color-muted]">
        Time-of-day scrubber · map shows all-day aggregate (time-sliced CII pending API)
      </span>
    </div>
  );
}
