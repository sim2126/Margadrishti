import { FlaskConical, Map as MapIcon, Sparkles, ShieldCheck } from "lucide-react";
import { CommandMap } from "@/components/CommandMap";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CopilotPanel } from "@/components/CopilotPanel";
import { DeploymentPanel } from "@/components/DeploymentPanel";
import { HotspotList } from "@/components/HotspotList";
import { KpiHeader } from "@/components/KpiHeader";
import { SegmentDetail } from "@/components/SegmentDetail";
import { TimeScrubber } from "@/components/TimeScrubber";
import { WhatIfPanel } from "@/components/WhatIfPanel";
import { cn } from "@/lib/utils";
import { useUi, type PanelTab } from "@/store/ui";

const TABS: Array<{ id: PanelTab; label: string; icon: typeof MapIcon }> = [
  { id: "detail", label: "Detail", icon: MapIcon },
  { id: "whatif", label: "What-if", icon: FlaskConical },
  { id: "copilot", label: "Copilot", icon: Sparkles },
  { id: "deploy", label: "Deploy", icon: ShieldCheck },
];

export function CommandCenter() {
  const panel = useUi((s) => s.panel);
  const setPanel = useUi((s) => s.setPanel);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-(--color-bg)">
      <KpiHeader />
      <div className="grid min-h-0 flex-1 grid-cols-[320px_1fr_380px] grid-rows-[minmax(0,1fr)]">
        {/* Left rail — ranked hotspots */}
        <aside className="min-h-0 overflow-hidden border-r bg-(--color-surface)">
          <HotspotList />
        </aside>

        {/* Center — the operational picture */}
        <main className="min-h-0 overflow-hidden">
          <ErrorBoundary label="Map failed to render">
            <CommandMap />
          </ErrorBoundary>
        </main>

        {/* Right rail — contextual workspace (scrolls internally, never the page) */}
        <aside className="flex min-h-0 flex-col overflow-hidden border-l bg-(--color-surface)">
          <div className="flex shrink-0 border-b">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setPanel(t.id)}
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 py-2.5 text-xs font-medium transition-colors",
                  panel === t.id
                    ? "border-b-2 border-(--color-brand) text-(--color-fg)"
                    : "text-(--color-muted) hover:text-(--color-fg)",
                )}
              >
                <t.icon className="h-3.5 w-3.5" />
                {t.label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            {panel === "detail" && <SegmentDetail />}
            {panel === "whatif" && <WhatIfPanel />}
            {panel === "copilot" && <CopilotPanel />}
            {panel === "deploy" && <DeploymentPanel />}
          </div>
        </aside>
      </div>
      <TimeScrubber />
    </div>
  );
}
