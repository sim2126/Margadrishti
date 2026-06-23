import { useSegment, useSegmentContext } from "@/lib/api";
import { cn, ciiCss, ciiLabel } from "@/lib/utils";
import { useUi } from "@/store/ui";
import { Badge, StatLabel } from "./ui";

const WHY_LABELS: Record<string, string> = {
  predicted_risk: "Predicted risk",
  centrality: "Network centrality",
  obstruction: "Obstruction footprint",
};

function WhyBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-(--color-fg)">{label}</span>
        <span className="tabular-nums text-(--color-muted)">{pct}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-(--color-surface-2)">
        <div className="h-full rounded-full bg-(--color-brand)" style={{ width: `${Math.max(2, pct)}%` }} />
      </div>
    </div>
  );
}

function KindChip({ kind }: { kind: "observed" | "predicted" | "simulated" }) {
  const tone =
    kind === "observed"
      ? "text-(--color-brand) border-(--color-brand)/40 bg-(--color-brand)/10"
      : kind === "predicted"
        ? "text-[#6aa9ff] border-[#6aa9ff]/40 bg-[#6aa9ff]/10"
        : "text-(--color-impact-2) border-(--color-impact-2)/40 bg-(--color-impact-2)/10";
  return <span className={cn("rounded-full border px-1.5 py-0.5 text-[10px] capitalize", tone)}>{kind}</span>;
}

export function SegmentDetail() {
  const id = useUi((s) => s.selectedSegment);
  const { data: d, isLoading } = useSegment(id);
  const { data: ctx } = useSegmentContext(id);

  if (!id)
    return <Empty>Select a hotspot on the map or the list to inspect its drivers and history.</Empty>;
  if (isLoading || !d) return <Empty>Loading segment…</Empty>;

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-4">
      <div>
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-lg font-semibold leading-tight text-(--color-fg)">
            {d.name ?? "Unnamed road"}
          </h2>
          <Badge style={{ borderColor: ciiCss(d.cii), color: ciiCss(d.cii) }}>{ciiLabel(d.cii)}</Badge>
        </div>
        <p className="mt-0.5 text-xs text-(--color-muted)">
          {d.junction ?? "—"}{d.zone ? ` · ${d.zone} zone` : ""}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="CII proxy" value={d.cii.toFixed(2)} accent={ciiCss(d.cii)} />
        <Stat label="Predicted risk" value={d.predicted_risk?.toFixed(2) ?? "—"} />
        <Stat label="Observed" value={String(d.observed_count)} />
        <Stat label="Approval rate" value={d.approval_rate != null ? `${(d.approval_rate * 100).toFixed(0)}%` : "—"} />
        <Stat label="Officers" value={String(d.n_officers ?? "—")} />
        <Stat label="Active hours" value={String(d.active_hours ?? "—")} />
      </div>

      <div>
        <StatLabel>Why this score</StatLabel>
        <div className="mt-2 space-y-2.5">
          {Object.entries(d.why).map(([k, v]) => (
            <WhyBar key={k} label={WHY_LABELS[k] ?? k.replace(/_/g, " ")} value={v} />
          ))}
        </div>
      </div>

      {ctx && (
        <div className="rounded-(--radius) border border-(--color-border)/60 bg-(--color-surface-2)/30 p-3">
          <div className="mb-2 flex items-center gap-2">
            <StatLabel>Evidence &amp; data gaps</StatLabel>
            <KindChip kind="observed" />
            <KindChip kind="predicted" />
            <KindChip kind="simulated" />
          </div>
          {!ctx.uncertainty.learned_model_shipped && (
            <p className="mb-1.5 text-[11px] text-(--color-impact-2)">
              ⚠ Learned model did not beat baselines on both gates → recency baseline in use.
            </p>
          )}
          <ul className="space-y-1 text-[11px] text-(--color-muted)">
            {ctx.data_gaps.map((g, i) => (
              <li key={i} className="flex gap-1.5">
                <span className="text-(--color-brand)">·</span>
                <span>{g}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Provenance d={d.provenance} />
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-(--radius) border bg-(--color-surface-2)/40 px-3 py-2">
      <div className="text-lg font-semibold tabular-nums" style={{ color: accent }}>
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-(--color-muted)">{label}</div>
    </div>
  );
}

function Provenance({ d }: { d: import("@/lib/types").Provenance }) {
  return (
    <div className="mt-auto rounded-(--radius) border border-(--color-border)/60 bg-(--color-surface-2)/30 p-3 text-[11px] text-(--color-muted)">
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        <span>As-of <span className="text-(--color-fg)">{d.as_of}</span></span>
        <span>Model <span className="text-(--color-fg)">{d.model_version}</span></span>
      </div>
      <div className="mt-0.5">Dataset {d.dataset_version} · features {d.feature_version}</div>
      {d.cii_risk_is_interim_biased && (
        <div className="mt-1 text-(--color-impact-3)">
          ⚠ CII risk term is interim (raw density) — bias-adjusted after model run.
        </div>
      )}
      {d.note && <div className="mt-1 italic">{d.note}</div>}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-(--color-muted)">
      {children}
    </div>
  );
}
