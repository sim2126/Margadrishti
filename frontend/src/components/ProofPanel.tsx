import { CheckCircle2, GitBranch, Radar, Route, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { useEvaluationSummary } from "@/lib/api";
import { StatLabel } from "./ui";

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

function fmt(n: number): string {
  return n.toLocaleString("en-IN");
}

export function ProofPanel() {
  const { data } = useEvaluationSummary();
  const heldLgbm = data?.held_out_zone.find((m) => m.model.startsWith("lightgbm"));
  const bestBaseline = data?.held_out_zone
    .filter((m) => !m.model.startsWith("lightgbm"))
    .sort((a, b) => b.pr_auc - a.pr_auc)[0];

  return (
    <section className="border-b bg-(--color-surface) p-3">
      <div className="rounded-(--radius) border bg-(--color-surface-2)/25 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <StatLabel>Problem → Margadrishti answer</StatLabel>
          <span className="rounded-full border border-(--color-brand)/40 bg-(--color-brand)/10 px-2 py-0.5 text-[10px] text-(--color-brand)">
            Theme 1
          </span>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <Answer icon={<Radar />} title="Hotspots" text="Full-city CII heatmap" />
          <Answer icon={<GitBranch />} title="Impact" text="capacity + spillover simulation" />
          <Answer icon={<ShieldCheck />} title="Prioritise" text="risk × road obstruction" />
          <Answer icon={<Route />} title="Act" text="zone/area patrol plans" />
        </div>
      </div>

      <div className="mt-2 rounded-(--radius) border bg-(--color-surface-2)/25 p-3">
        <div className="mb-2 flex items-center gap-1.5">
          <CheckCircle2 className="h-3.5 w-3.5 text-(--color-brand)" />
          <StatLabel>Proof, not decoration</StatLabel>
        </div>
        <div className="grid grid-cols-3 gap-1.5 text-center">
          <Mini label="Rows" value={data ? fmt(data.n_in_scope_rows) : "—"} />
          <Mini label="Segments" value={data ? fmt(data.n_segments) : "—"} />
          <Mini label="Winner" value={data?.winner ?? "—"} />
        </div>
        {heldLgbm && bestBaseline && (
          <div className="mt-2 rounded-(--radius) border border-(--color-brand)/30 bg-(--color-brand)/10 p-2 text-[11px] text-(--color-muted)">
            Held-out-zone PR-AUC:{" "}
            <span className="font-medium text-(--color-fg)">{heldLgbm.pr_auc.toFixed(3)}</span> LightGBM vs{" "}
            <span className="font-medium text-(--color-fg)">{bestBaseline.pr_auc.toFixed(3)}</span> best baseline.
            P@25 <span className="text-(--color-fg)">{pct(heldLgbm.precision_at_25)}</span>.
          </div>
        )}
        <div className="mt-2 text-[11px] leading-relaxed text-(--color-muted)">
          <span className="text-(--color-fg)">Derived prioritisation signals:</span> centrality,
          obstruction, predicted risk, and simulated spillover. No measured speed/volume exists in the
          organiser dataset, so flow impact stays labelled as proxy/simulation.
        </div>
      </div>
    </section>
  );
}

function Answer({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <div className="rounded-(--radius) border border-(--color-border)/60 p-2">
      <div className="mb-0.5 flex items-center gap-1.5 text-[11px] font-medium text-(--color-fg)">
        <span className="[&_svg]:h-3 [&_svg]:w-3 [&_svg]:text-(--color-brand)">{icon}</span>
        {title}
      </div>
      <div className="text-[10px] leading-snug text-(--color-muted)">{text}</div>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-(--radius) border border-(--color-border)/60 py-1.5">
      <div className="truncate px-1 text-sm font-semibold tabular-nums text-(--color-fg)">{value}</div>
      <div className="text-[9px] uppercase tracking-wider text-(--color-muted)">{label}</div>
    </div>
  );
}
