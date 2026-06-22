import { useSegment } from "@/lib/api";
import { ciiCss, ciiLabel } from "@/lib/utils";
import { useUi } from "@/store/ui";
import { Badge, StatLabel } from "./ui";

function WhyBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="text-[--color-muted]">{label}</span>
        <span className="tabular-nums text-[--color-fg]">{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[--color-surface-2]">
        <div
          className="h-full rounded-full bg-[--color-brand]"
          style={{ width: `${Math.max(2, value * 100)}%` }}
        />
      </div>
    </div>
  );
}

export function SegmentDetail() {
  const id = useUi((s) => s.selectedSegment);
  const { data: d, isLoading } = useSegment(id);

  if (!id)
    return (
      <Empty>Select a hotspot on the map or the list to inspect its drivers and history.</Empty>
    );
  if (isLoading || !d) return <Empty>Loading segment…</Empty>;

  return (
    <div className="flex flex-col gap-5 overflow-y-auto p-4">
      <div>
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-lg font-semibold leading-tight text-[--color-fg]">
            {d.name ?? "Unnamed road"}
          </h2>
          <Badge style={{ borderColor: ciiCss(d.cii), color: ciiCss(d.cii) }}>
            {ciiLabel(d.cii)}
          </Badge>
        </div>
        <p className="mt-0.5 text-xs text-[--color-muted]">
          {d.junction ?? "—"} · {d.zone ?? "—"}
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="CII" value={d.cii.toFixed(3)} accent={ciiCss(d.cii)} />
        <Stat label="Pred. risk" value={d.predicted_risk?.toFixed(3) ?? "—"} />
        <Stat label="Observed" value={String(d.observed_count)} />
        <Stat label="Approval" value={d.approval_rate != null ? `${(d.approval_rate * 100).toFixed(0)}%` : "—"} />
        <Stat label="Officers" value={String(d.n_officers ?? "—")} />
        <Stat label="Active hrs" value={String(d.active_hours ?? "—")} />
      </div>

      <div>
        <StatLabel>Why this score</StatLabel>
        <div className="mt-2 space-y-2.5">
          {Object.entries(d.why).map(([k, v]) => (
            <WhyBar key={k} label={k.replace(/_/g, " ")} value={v} />
          ))}
        </div>
      </div>

      <Provenance d={d.provenance} />
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-[--radius] border bg-[--color-surface-2]/40 px-3 py-2">
      <StatLabel>{label}</StatLabel>
      <div className="mt-0.5 text-lg font-semibold tabular-nums" style={{ color: accent }}>
        {value}
      </div>
    </div>
  );
}

function Provenance({ d }: { d: import("@/lib/types").Provenance }) {
  return (
    <div className="rounded-[--radius] border border-[--color-border]/60 bg-[--color-surface-2]/30 p-3 text-[11px] text-[--color-muted]">
      <div className="mb-1 font-medium text-[--color-fg]">Provenance</div>
      <div>as of {d.as_of} · model {d.model_version}</div>
      <div>data {d.dataset_version} · features {d.feature_version}</div>
      {d.cii_risk_is_interim_biased && (
        <div className="mt-1 text-[--color-impact-3]">
          ⚠ CII risk term is interim (raw density) — bias-adjusted after model run.
        </div>
      )}
      {d.note && <div className="mt-1 italic">{d.note}</div>}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-[--color-muted]">
      {children}
    </div>
  );
}
