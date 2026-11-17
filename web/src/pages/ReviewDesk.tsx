import { useQuery } from "@tanstack/react-query";
import { FileSearch, ListChecks, ScanText, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Invoice } from "../api";
import {
  Empty,
  ErrorNote,
  Module,
  num,
  ReasonTag,
  Row,
  Segmented,
  SkeletonRows,
  Table,
  td,
  th,
} from "../components/ui";
import { age, money, percent } from "../format";
import { primaryReasons, reasonInfo } from "../reasons";

const ORIENTATION_KEY = "invoiceguard.orientationDismissed";

function readDismissed(): boolean {
  try {
    return localStorage.getItem(ORIENTATION_KEY) === "1";
  } catch {
    return false;
  }
}

function Orientation() {
  const [hidden, setHidden] = useState(readDismissed);
  if (hidden) return null;
  const steps = [
    { icon: ScanText, title: "A model reads the PDF", text: "Every value is stored with the exact text it came from. The model never decides." },
    { icon: ListChecks, title: "Code checks it", text: "Three-way match against the PO and goods receipt, arithmetic, duplicates and policy." },
    { icon: FileSearch, title: "You decide the rest", text: "Only invoices that clear every check are auto-approved. Everything else lands here, with its reasons." },
  ];
  return (
    <Module
      title="How InvoiceGuard decides"
      className="lg:col-span-12"
      extra={
        <button
          type="button"
          aria-label="Hide this explanation"
          className="rounded-sm p-0.5 text-ink-2 hover:bg-line hover:text-ink"
          onClick={() => {
            try {
              localStorage.setItem(ORIENTATION_KEY, "1");
            } catch {
              /* not persisted; hidden for this visit */
            }
            setHidden(true);
          }}
        >
          <X aria-hidden className="h-4 w-4" />
        </button>
      }
      bodyClassName="grid divide-y divide-line md:grid-cols-3 md:divide-x md:divide-y-0"
    >
      {steps.map(({ icon: Icon, title, text }) => (
        <div key={title} className="flex gap-2.5 px-3 py-2.5">
          <Icon aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-ink-2" />
          <p className="text-sm">
            <b className="font-semibold">{title}.</b> <span className="text-ink-2">{text}</span>
          </p>
        </div>
      ))}
    </Module>
  );
}

function QueueTable({ rows }: { rows: Invoice[] }) {
  const now = Date.now();
  return (
    <Table label="Invoices waiting for a decision">
      <thead>
        <tr>
          <th className={th}>Invoice</th>
          <th className={th}>Vendor</th>
          <th className={th}>PO</th>
          <th className={th}>Why it's here</th>
          <th className={`${th} text-right`}>Total</th>
          <th className={`${th} text-right`}>Waiting</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((inv) => {
          const reasons = primaryReasons(inv.reasons ?? []);
          return (
            <Row key={inv.id}>
              <td className={td}>
                <Link to={`/invoices/${inv.id}`} className="font-mono text-[13px] font-semibold text-ink underline decoration-line underline-offset-4 hover:decoration-red">
                  {inv.invoice_number ?? "Unread document"}
                </Link>
              </td>
              <td className={`${td} font-mono text-[13px]`}>{inv.vendor_id ?? "—"}</td>
              <td className={`${td} font-mono text-[13px] text-ink-2`}>{inv.po_number ?? "—"}</td>
              <td className={td}>
                <span className="flex gap-1">
                  {reasons.slice(0, 2).map((r) => (
                    <ReasonTag key={r} code={r} title />
                  ))}
                  {reasons.length > 2 && <span className="text-xs text-ink-2">+{reasons.length - 2}</span>}
                </span>
              </td>
              <td className={`${td} ${num}`}>
                <span className="text-ink-3">{inv.currency}</span> {money(inv.total)}
              </td>
              <td className={`${td} ${num} text-ink-2`}>{age(inv.created_at, now)}</td>
            </Row>
          );
        })}
      </tbody>
    </Table>
  );
}

export default function ReviewDesk() {
  const queue = useQuery({
    queryKey: ["invoices", "NEEDS_REVIEW"],
    queryFn: () => api.listInvoices("NEEDS_REVIEW"),
    refetchInterval: 5000,
  });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 10000 });
  const [reason, setReason] = useState("all");

  // Oldest first: a review queue is worked in arrival order.
  const rows = useMemo(
    () => [...(queue.data ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at)),
    [queue.data],
  );
  const reasonCounts = useMemo(() => {
    const counts = new Map<string, number>();
    rows.forEach((r) => primaryReasons(r.reasons ?? []).forEach((c) => counts.set(c, (counts.get(c) ?? 0) + 1)));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);
  const shown = reason === "all" ? rows : rows.filter((r) => primaryReasons(r.reasons ?? []).includes(reason));
  const max = Math.max(1, ...reasonCounts.map(([, n]) => n));
  const d = metrics.data?.decisions;

  return (
    <div className="grid gap-2 lg:grid-cols-12">
      <Orientation />

      <Module
        id="queue"
        title="Needs your decision"
        count={rows.length}
        alert
        className="self-start lg:col-span-8"
        extra={<span className="hidden text-xs text-ink-2 sm:inline">Oldest first</span>}
      >
        {reasonCounts.length > 1 && (
          <div className="border-b border-line px-3 py-2">
            <Segmented
              label="Filter by reason"
              value={reason}
              onChange={setReason}
              options={[
                { value: "all", label: "All", count: rows.length },
                ...reasonCounts.map(([code, n]) => ({ value: code, label: reasonInfo(code).label, count: n })),
              ]}
            />
          </div>
        )}
        <ErrorNote error={queue.error} />
        {queue.isLoading && <SkeletonRows rows={10} cols={6} />}
        {queue.data && shown.length === 0 && (
          <Empty title="Nothing waiting for you">
            Every invoice so far either cleared all checks or has been decided.
          </Empty>
        )}
        {shown.length > 0 && <QueueTable rows={shown} />}
      </Module>

      <div className="space-y-2 lg:col-span-4">
      <Module id="reasons" title="Why invoices are waiting" bodyClassName="p-3">
        {reasonCounts.length === 0 ? (
          <p className="text-sm text-ink-2">No open exceptions.</p>
        ) : (
          <ul className="space-y-1.5">
            {reasonCounts.map(([code, n]) => (
              <li key={code} className="grid grid-cols-[1fr_auto] items-center gap-x-2 text-sm">
                <span title={reasonInfo(code).explain}>{reasonInfo(code).label}</span>
                <span className="font-mono text-[13px]">{n}</span>
                <span aria-hidden className="col-span-2 h-1 bg-fill">
                  <span className="block h-1 bg-red" style={{ width: `${(n / max) * 100}%` }} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Module>

      <Module id="decisions" title="Decisions so far" action={{ to: "/metrics", label: "Metrics" }}>
        {d ? (
          <dl className="divide-y divide-line text-sm">
            <div className="flex justify-between px-3 py-1.5">
              <dt>Auto-approved</dt>
              <dd className="font-mono text-[13px]">
                {percent(d.straight_through_rate)} <span className="text-ink-3">· {d.auto_approved} of {d.decided}</span>
              </dd>
            </div>
            <div className="flex justify-between px-3 py-1.5">
              <dt>Sent to a human</dt>
              <dd className="font-mono text-[13px]">
                {percent(d.review_rate)} <span className="text-ink-3">· {d.needs_review} of {d.decided}</span>
              </dd>
            </div>
            <div className="flex justify-between px-3 py-1.5">
              <dt>Rejected as duplicates</dt>
              <dd className="font-mono text-[13px]">{d.rejected}</dd>
            </div>
          </dl>
        ) : (
          <SkeletonRows rows={3} cols={2} />
        )}
      </Module>

      <Module id="pipeline" title="Pipeline" action={{ to: "/failed", label: "Failed jobs" }}>
        <dl className="divide-y divide-line text-sm">
          <div className="flex justify-between px-3 py-1.5">
            <dt>Failed jobs waiting for replay</dt>
            <dd className={`font-mono text-[13px] ${metrics.data?.operations.open_failed_jobs ? "font-semibold text-red" : ""}`}>
              {metrics.data?.operations.open_failed_jobs ?? "—"}
            </dd>
          </div>
          <div className="flex justify-between px-3 py-1.5">
            <dt>Jobs queued in the outbox</dt>
            <dd className="font-mono text-[13px]">{metrics.data?.operations.outbox_pending ?? "—"}</dd>
          </div>
        </dl>
      </Module>
      </div>
    </div>
  );
}
