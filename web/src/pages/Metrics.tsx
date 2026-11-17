import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Card, CardHeader, Empty, ErrorNote, td, th } from "../components/ui";
import { humanize, percent } from "../format";

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
    </Card>
  );
}

export default function Metrics() {
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 10000 });
  if (metrics.error) return <ErrorNote error={metrics.error} />;
  if (!metrics.data) return <Empty>Loading…</Empty>;
  const m = metrics.data;
  const maxException = Math.max(1, ...m.exceptions.map((e) => e.count));

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        What the running system did, from its own event log. These are operational figures on synthetic demo data,
        not accuracy results; accuracy comes from the evaluation harness.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Invoices decided" value={String(m.decisions.decided)} />
        <Stat
          label="Straight-through"
          value={percent(m.decisions.straight_through_rate)}
          note={`${m.decisions.auto_approved} auto-approved`}
        />
        <Stat label="Sent to review" value={percent(m.decisions.review_rate)} note={`${m.decisions.needs_review} invoices`} />
        <Stat
          label="Median review time"
          value={
            m.human_workload.median_review_seconds === null
              ? "—"
              : `${(m.human_workload.median_review_seconds / 60).toFixed(1)} min`
          }
          note={`${m.human_workload.reviewed} reviewed · ${m.human_workload.edits} edits`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Why invoices need a human" />
          {m.exceptions.length === 0 ? (
            <Empty>No exceptions yet.</Empty>
          ) : (
            <ul className="space-y-2 p-4">
              {m.exceptions.map((e) => (
                <li key={e.reason} className="text-sm">
                  <div className="flex justify-between">
                    <span>{humanize(e.reason)}</span>
                    <span className="tabular-nums text-muted-foreground">{e.count}</span>
                  </div>
                  <div className="mt-1 h-2 rounded bg-muted">
                    <div className="h-2 rounded bg-warning" style={{ width: `${(e.count / maxException) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader title="Operations" />
          <dl className="grid grid-cols-2 gap-4 p-4 text-sm">
            <div>
              <dt className="text-muted-foreground">Open failed jobs</dt>
              <dd className="text-xl font-semibold tabular-nums">{m.operations.open_failed_jobs}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Outbox pending</dt>
              <dd className="text-xl font-semibold tabular-nums">{m.operations.outbox_pending}</dd>
            </div>
            {Object.entries(m.invoices_by_status).map(([status, count]) => (
              <div key={status}>
                <dt className="text-muted-foreground">{humanize(status)}</dt>
                <dd className="tabular-nums">{count}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>

      <Card>
        <CardHeader title="Model calls" />
        {m.llm.length === 0 ? (
          <Empty>No model calls yet.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-border">
                <tr>
                  <th className={th}>Model</th>
                  <th className={`${th} text-right`}>Calls</th>
                  <th className={`${th} text-right`}>Cost / request (USD)</th>
                  <th className={`${th} text-right`}>P50 latency</th>
                  <th className={`${th} text-right`}>P95 latency</th>
                  <th className={`${th} text-right`}>Tokens / s</th>
                </tr>
              </thead>
              <tbody>
                {m.llm.map((row) => (
                  <tr key={`${row.provider}-${row.model}`} className="border-b border-border last:border-0">
                    <td className={td}>
                      {row.model}
                      {row.provider === "fake" && <span className="ml-2 text-xs text-warning">simulated</span>}
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{row.calls}</td>
                    <td className={`${td} text-right tabular-nums`}>{Number(row.cost_per_request_usd).toFixed(6)}</td>
                    <td className={`${td} text-right tabular-nums`}>{Math.round(row.p50_latency_ms)} ms</td>
                    <td className={`${td} text-right tabular-nums`}>{Math.round(row.p95_latency_ms)} ms</td>
                    <td className={`${td} text-right tabular-nums`}>
                      {row.avg_tokens_per_second ? Number(row.avg_tokens_per_second).toFixed(0) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
