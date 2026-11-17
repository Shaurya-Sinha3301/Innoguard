import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Empty, ErrorNote, Module, num, SkeletonRows, StatusBadge, Table, td, th } from "../components/ui";
import { isSimulated, percent } from "../format";
import { reasonInfo } from "../reasons";

export default function Metrics() {
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 10000 });
  if (metrics.error) return <ErrorNote error={metrics.error} />;
  if (!metrics.data) return <SkeletonRows rows={10} cols={4} />;
  const m = metrics.data;
  const d = m.decisions;
  const max = Math.max(1, ...m.exceptions.map((e) => e.count));

  return (
    <div className="grid gap-2 lg:grid-cols-12">
      <p className="border border-amber/40 bg-amber-tint px-3 py-1.5 text-sm text-amber lg:col-span-12">
        Operational figures from this system's own event log, on synthetic demo data. They are not accuracy results;
        accuracy is measured by the evaluation harness against known answers.
      </p>

      <Module title="Decisions" className="lg:col-span-5">
        <Table label="Decisions with their denominators">
          <thead>
            <tr>
              <th className={th}>Measure</th>
              <th className={`${th} text-right`}>Value</th>
              <th className={th}>Out of</th>
            </tr>
          </thead>
          <tbody>
            <tr><td className={td}>Auto-approved</td><td className={`${td} ${num}`}>{percent(d.straight_through_rate)}</td><td className={`${td} text-ink-2`}>{d.auto_approved} of {d.decided} decided</td></tr>
            <tr><td className={td}>Sent to a human</td><td className={`${td} ${num}`}>{percent(d.review_rate)}</td><td className={`${td} text-ink-2`}>{d.needs_review} of {d.decided} decided</td></tr>
            <tr><td className={td}>Rejected automatically</td><td className={`${td} ${num}`}>{d.rejected}</td><td className={`${td} text-ink-2`}>exact duplicates</td></tr>
            <tr><td className={td}>Reviewed by a person</td><td className={`${td} ${num}`}>{m.human_workload.reviewed}</td><td className={`${td} text-ink-2`}>approved or rejected</td></tr>
            <tr><td className={td}>Median time to decide</td><td className={`${td} ${num}`}>{m.human_workload.median_review_seconds === null ? "—" : `${(m.human_workload.median_review_seconds / 60).toFixed(1)} min`}</td><td className={`${td} text-ink-2`}>from entering review</td></tr>
            <tr><td className={td}>Edits</td><td className={`${td} ${num}`}>{m.human_workload.edits}</td><td className={`${td} text-ink-2`}>each voids its approvals</td></tr>
          </tbody>
        </Table>
      </Module>

      <Module title="Why invoices needed a human" className="lg:col-span-4" bodyClassName="p-3">
        {m.exceptions.length === 0 ? (
          <p className="text-sm text-ink-2">No exceptions yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {m.exceptions.map((e) => (
              <li key={e.reason} className="grid grid-cols-[1fr_auto] items-center gap-x-2 text-sm">
                <span title={reasonInfo(e.reason).explain}>{reasonInfo(e.reason).label}</span>
                <span className="font-mono text-[13px]">{e.count}</span>
                <span aria-hidden className="col-span-2 h-1 bg-fill">
                  <span className="block h-1 bg-red" style={{ width: `${(e.count / max) * 100}%` }} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Module>

      <Module title="Invoices by status" className="lg:col-span-3">
        <ul className="divide-y divide-line">
          {Object.entries(m.invoices_by_status)
            .sort((a, b) => b[1] - a[1])
            .map(([status, count]) => (
              <li key={status} className="flex items-center justify-between px-3 py-1.5">
                <StatusBadge status={status} />
                <span className="font-mono text-[13px]">{count}</span>
              </li>
            ))}
          <li className="flex justify-between px-3 py-1.5 text-sm">
            <span>Failed jobs open</span>
            <span className="font-mono text-[13px]">{m.operations.open_failed_jobs}</span>
          </li>
          <li className="flex justify-between px-3 py-1.5 text-sm">
            <span>Outbox queued</span>
            <span className="font-mono text-[13px]">{m.operations.outbox_pending}</span>
          </li>
        </ul>
      </Module>

      <Module title="Model calls" className="lg:col-span-12">
        {m.llm.length === 0 ? (
          <Empty title="No model calls yet" />
        ) : (
          <Table label="Model calls by model">
            <thead>
              <tr>
                <th className={th}>Model</th>
                <th className={`${th} text-right`}>Calls</th>
                <th className={`${th} text-right`}>Cost per request (USD)</th>
                <th className={`${th} text-right`}>Total cost (USD)</th>
                <th className={`${th} text-right`}>P50 latency</th>
                <th className={`${th} text-right`}>P95 latency</th>
                <th className={`${th} text-right`}>Output tokens / s</th>
              </tr>
            </thead>
            <tbody>
              {m.llm.map((row) => (
                <tr key={`${row.provider}-${row.model}`}>
                  <td className={td}>
                    {row.model}
                    {isSimulated(row.provider) && <span className="ml-1.5 text-xs font-semibold text-amber">simulated</span>}
                  </td>
                  <td className={`${td} ${num}`}>{row.calls}</td>
                  <td className={`${td} ${num}`}>{Number(row.cost_per_request_usd).toFixed(6)}</td>
                  <td className={`${td} ${num}`}>{Number(row.total_cost_usd).toFixed(4)}</td>
                  <td className={`${td} ${num}`}>{Math.round(row.p50_latency_ms)} ms</td>
                  <td className={`${td} ${num}`}>{Math.round(row.p95_latency_ms)} ms</td>
                  <td className={`${td} ${num}`}>{row.avg_tokens_per_second ? Number(row.avg_tokens_per_second).toFixed(0) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Module>
    </div>
  );
}
