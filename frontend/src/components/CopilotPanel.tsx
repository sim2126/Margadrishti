import { Send, Sparkles } from "lucide-react";
import { useState } from "react";
import { useCopilot } from "@/lib/api";
import { Button, StatLabel } from "./ui";

const SUGGESTIONS = [
  "Top congestion-impact spots right now",
  "Where should I deploy 3 units in Madiwala?",
  "Observed enforcement density by zone",
];

export function CopilotPanel() {
  const [q, setQ] = useState("");
  const copilot = useCopilot();
  const ask = (text: string) => text.trim() && copilot.mutate({ question: text });

  return (
    <div className="flex h-full flex-col p-4">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-(--color-brand)" />
        <StatLabel>Enforcement Copilot</StatLabel>
      </div>
      <p className="mt-1 text-xs text-(--color-muted)">
        Answers from your data only — never invents numbers. Plans are advisory.
      </p>

      <div className="my-3 flex-1 overflow-y-auto rounded-(--radius) border bg-(--color-surface-2)/30 p-3">
        {copilot.isPending && <p className="text-sm text-(--color-muted)">Thinking…</p>}
        {copilot.isError && <p className="text-sm text-impact-4">Copilot unavailable.</p>}
        {copilot.data ? (
          <div className="space-y-2">
            <p className="text-sm leading-relaxed text-(--color-fg)">{copilot.data.answer}</p>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {copilot.data.tool_calls.map((t, i) => (
                <span key={i} className="rounded-full border px-2 py-0.5 text-[10px] text-(--color-muted)">
                  {t}
                </span>
              ))}
              <span className="rounded-full border px-2 py-0.5 text-[10px] text-(--color-muted)">
                {copilot.data.model}
              </span>
            </div>
          </div>
        ) : (
          !copilot.isPending && (
            <div className="space-y-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => {
                    setQ(s);
                    ask(s);
                  }}
                  className="block w-full rounded-(--radius) border border-(--color-border)/60 px-3 py-2 text-left text-xs text-(--color-muted) hover:bg-(--color-surface-2)"
                >
                  {s}
                </button>
              ))}
            </div>
          )
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
        className="flex gap-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask about hotspots, forecasts, deployment…"
          className="h-9 flex-1 rounded-(--radius) border bg-(--color-surface) px-3 text-sm text-(--color-fg) placeholder:text-(--color-muted) focus:outline-none focus:ring-2 focus:ring-(--color-brand)"
        />
        <Button size="icon" type="submit" disabled={copilot.isPending}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
