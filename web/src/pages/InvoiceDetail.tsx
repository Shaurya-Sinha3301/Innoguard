import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Boxes,
  Cpu,
  ExternalLink,
  FileText,
  Flag,
  Gavel,
  History,
  ScanText,
  UserCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Link, useParams } from "react-router-dom";
import { api, type AuditEvent, type InvoiceDetail } from "../api";
import {
  Button,
  cx,
  Empty,
  ErrorNote,
  Module,
  num,
  ReasonTag,
  SkeletonRows,
  StatusBadge,
  Table,
  td,
  th,
} from "../components/ui";
import { clock, humanize, isSimulated, money, qty, when } from "../format";
import { reasonInfo } from "../reasons";

const PRICE_TOLERANCE = 0.02;
const LOW_CONFIDENCE = 0.9;

/* ---------- Three-way match: invoice line vs PO line vs goods received ---------- */

function ThreeWayMatch({ inv }: { inv: InvoiceDetail }) {
  const po = inv.purchase_order;
  const flag = "bg-red-tint font-semibold text-red";
  if (!inv.lines.length) return <Empty title="No lines yet">The document has not been read yet.</Empty>;
  return (
    <>
      {!po && inv.po_number && (
        <p className="flex items-center gap-2 border-b border-line bg-red-tint px-4 py-2 text-sm text-red">
          <AlertTriangle aria-hidden className="h-4 w-4" />
          No purchase order on file for <span className="font-mono">{inv.po_number}</span>.
        </p>
      )}
      <Table label="Invoice lines against purchase order and goods received">
        <thead>
          <tr>
            <th className={th}>Item</th>
            <th className={`${th} text-right`}>Invoiced qty</th>
            <th className={`${th} text-right`}>Received</th>
            <th className={`${th} text-right`}>Ordered</th>
            <th className={`${th} text-right`}>Invoice price</th>
            <th className={`${th} text-right`}>PO price</th>
            <th className={`${th} text-right`}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {inv.lines.map((line) => {
            const poLine = po?.lines.find((p) => p.sku === line.sku);
            const invoiced = Number(line.qty);
            const price = Number(line.unit_price);
            const received = inv.receipt_count ? Number(inv.received[line.sku] ?? 0) : null;
            const overReceived = received !== null && invoiced > received;
            const overOrdered = poLine ? invoiced > Number(poLine.qty) : false;
            const priceOff = poLine
              ? Math.abs(price - Number(poLine.unit_price)) > Number(poLine.unit_price) * PRICE_TOLERANCE
              : false;
            return (
              <tr key={line.line_no}>
                <td className={cx(td, "font-mono text-[13px]", po && !poLine && flag)}>
                  {line.sku}
                  {po && !poLine && <span className="ml-1 font-sans text-xs">not on PO</span>}
                </td>
                <td className={cx(td, num, (overReceived || overOrdered) && flag)}>{qty(line.qty)}</td>
                <td className={cx(td, num, overReceived && flag)}>
                  {received === null ? <span className="text-red">none</span> : qty(received)}
                </td>
                <td className={cx(td, num, overOrdered && flag)}>{poLine ? qty(poLine.qty) : "—"}</td>
                <td className={cx(td, num, priceOff && flag)}>{money(line.unit_price)}</td>
                <td className={cx(td, num, priceOff && flag)}>{poLine ? money(poLine.unit_price) : "—"}</td>
                <td className={cx(td, num)}>{money(String(invoiced * price))}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot className="text-sm">
          {(
            [
              ["Subtotal", inv.subtotal],
              ["Tax", inv.tax],
              ["Total", inv.total],
            ] as const
          ).map(([label, value]) => (
            <tr key={label}>
              <td colSpan={6} className={cx(td, "text-right", label === "Total" ? "font-semibold" : "text-ink-2")}>
                {label}
              </td>
              <td className={cx(td, num, label === "Total" && "font-semibold")}>{money(value)}</td>
            </tr>
          ))}
        </tfoot>
      </Table>
      <p className="px-4 py-2 text-xs text-ink-2">
        Highlighted cells disagree. Price tolerance 2%; quantities must match exactly. Received sums {inv.receipt_count}{" "}
        goods receipt{inv.receipt_count === 1 ? "" : "s"} on {po?.po_number ?? inv.po_number ?? "the PO"}.
      </p>
    </>
  );
}

/* ---------- Extracted values with their evidence ---------- */

function Evidence({ id }: { id: string }) {
  const fields = useQuery({ queryKey: ["extraction", id], queryFn: () => api.extraction(id) });
  if (fields.isLoading) return <SkeletonRows rows={5} cols={3} />;
  if (!fields.data?.length) return <Empty title="Submitted as data">This invoice arrived as structured data, so nothing was read from a document.</Empty>;
  return (
    <Table label="Extracted values and the text they came from">
      <thead>
        <tr>
          <th className={th}>Field</th>
          <th className={th}>Value</th>
          <th className={`${th} text-right`}>Confidence</th>
          <th className={th}>Quoted from the PDF</th>
        </tr>
      </thead>
      <tbody>
        {fields.data.map((f) => {
          const low = Number(f.confidence) < LOW_CONFIDENCE;
          return (
            <tr key={f.field}>
              <td className={cx(td, "text-ink-2")}>{humanize(f.field)}</td>
              <td className={cx(td, "font-mono text-[13px]")}>{f.value ?? "—"}</td>
              <td className={cx(td, num, low && "bg-red-tint font-semibold text-red")}>
                {low && <span className="sr-only">Low confidence: </span>}
                {Number(f.confidence).toFixed(2)}
              </td>
              <td className={cx(td, "max-w-[18rem] truncate text-ink-2")} title={f.snippet ?? undefined}>
                {f.snippet ? (
                  <>
                    <span className="text-ink-3">p.{f.page ?? "?"}</span> “{f.snippet}”
                  </>
                ) : (
                  <span className="text-red">no evidence</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

/* ---------- The decision ---------- */

function Decision({ inv }: { inv: InvoiceDetail }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [total, setTotal] = useState("");
  const [confirming, setConfirming] = useState<"reject" | "post" | null>(null);
  const done = (message: string) => () => {
    setReason("");
    setTotal("");
    setConfirming(null);
    toast.success(message);
    void queryClient.invalidateQueries();
  };
  const failed = (e: unknown) => {
    setConfirming(null);
    toast.error(e instanceof Error ? e.message : "That did not work");
  };
  const approve = useMutation({ mutationFn: () => api.approve(inv.id, inv.version, reason.trim()), onSuccess: done("Approved"), onError: failed });
  const reject = useMutation({ mutationFn: () => api.reject(inv.id, inv.version, reason.trim()), onSuccess: done("Rejected"), onError: failed });
  const edit = useMutation({ mutationFn: () => api.edit(inv.id, inv.version, reason.trim(), { total }), onSuccess: done("Saved as a new version; earlier approvals no longer count"), onError: failed });
  const post = useMutation({
    mutationFn: () => api.post(inv.id),
    onSuccess: (r) => done(r.outcome === "POSTED" ? "Posted to the system of record" : "Already posted; nothing changed")(),
    onError: failed,
  });
  const replay = useMutation({ mutationFn: () => api.replay(inv.id), onSuccess: done("Sent back through extraction"), onError: failed });
  const error = approve.error ?? reject.error ?? edit.error ?? post.error ?? replay.error;
  const busy = approve.isPending || reject.isPending || edit.isPending || post.isPending || replay.isPending;

  const reviewable = inv.status === "NEEDS_REVIEW";
  const postable = inv.status === "APPROVED" || inv.status === "AUTO_APPROVED";
  const editable = reviewable || postable;
  const hasReason = reason.trim().length > 0;
  const validTotal = /^\d+(\.\d{1,4})?$/.test(total);

  return (
    <div className="space-y-4 p-4">
      <ErrorNote error={error} />
      {editable && (
        <div className="space-y-1">
          <label htmlFor="reason" className="text-sm font-semibold">
            Reason <span className="font-normal text-ink-2">(required, saved to the audit trail)</span>
          </label>
          <textarea
            id="reason"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="For example: price increase agreed with the supplier on 12 Nov"
            className="w-full resize-y rounded-lg border border-line px-3 py-2 text-sm placeholder:text-ink-3"
          />
        </div>
      )}
      {reviewable && (
        <div className="flex flex-wrap gap-2">
          <Button size="lg" disabled={!hasReason || busy} onClick={() => approve.mutate()}>
            Approve version {inv.version}
          </Button>
          {confirming === "reject" ? (
            <>
              <Button size="lg" variant="danger" disabled={busy} onClick={() => reject.mutate()}>
                Confirm reject
              </Button>
              <Button size="lg" variant="ghost" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
            </>
          ) : (
            <Button size="lg" variant="danger" disabled={!hasReason || busy} onClick={() => setConfirming("reject")}>
              Reject
            </Button>
          )}
        </div>
      )}
      {postable && (
        <div className="space-y-1">
          {confirming === "post" ? (
            <div className="flex flex-wrap gap-2">
              <Button size="lg" disabled={busy} onClick={() => post.mutate()}>
                Confirm post
              </Button>
              <Button size="lg" variant="ghost" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
            </div>
          ) : (
            <Button size="lg" disabled={busy} onClick={() => setConfirming("post")}>
              Post to system of record
            </Button>
          )}
          <p className="text-xs text-ink-2">Posting is idempotent: a second attempt is recorded and does nothing.</p>
        </div>
      )}
      {post.data && (
        <p className="text-sm">
          {post.data.outcome === "POSTED" ? "Posted." : "Already posted; nothing changed."}{" "}
          <span className="font-mono text-xs text-ink-2">key {post.data.idempotency_key.slice(0, 12)}</span>
        </p>
      )}
      {inv.status === "FAILED" && (
        <div className="space-y-1">
          <Button disabled={busy} onClick={() => replay.mutate()}>
            Replay extraction
          </Button>
          <p className="text-xs text-ink-2">Sends the document back through extraction. Safe to repeat.</p>
        </div>
      )}
      {editable && (
        <details className="border-t border-line pt-2">
          <summary className="cursor-pointer text-sm font-semibold">Correct the total</summary>
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="text-sm" htmlFor="total">
              New total
              <input
                id="total"
                inputMode="decimal"
                value={total}
                onChange={(e) => setTotal(e.target.value)}
                className="mt-1 block h-9 w-36 rounded-lg border border-line px-2 font-mono text-sm"
              />
            </label>
            <Button variant="secondary" disabled={!hasReason || !validTotal || busy} onClick={() => edit.mutate()}>
              Save as version {inv.version + 1}
            </Button>
          </div>
          <p className="mt-1 text-xs text-ink-2">An edit creates a new version and voids every approval of this one.</p>
        </details>
      )}
      {!editable && inv.status !== "FAILED" && (
        <p className="text-sm text-ink-2">
          {inv.status === "POSTED" ? "Posted. No further action." : inv.status === "REJECTED" ? "Rejected. No further action." : "Being processed."}
        </p>
      )}
    </div>
  );
}

/* ---------- Supporting modules ---------- */

function DocumentPreview({ id }: { id: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const doc = useQuery({ queryKey: ["document", id], queryFn: () => api.document(id), retry: false });
  useEffect(() => {
    if (!doc.data) return;
    const objectUrl = URL.createObjectURL(doc.data);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [doc.data]);
  if (doc.isError) return <Empty title="No document">This invoice was submitted as structured data.</Empty>;
  if (!url) return <SkeletonRows rows={6} cols={1} />;
  return (
    <div>
      <iframe title="Invoice PDF" src={url} className="h-[560px] w-full bg-white" />
      <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-1 border-t border-line px-4 py-2.5 text-sm hover:underline">
        <ExternalLink aria-hidden className="h-3.5 w-3.5" /> Open the PDF in a new tab
      </a>
    </div>
  );
}

function describe(e: AuditEvent): string {
  if (e.event_type === "invoice.state_changed") {
    return `${humanize(String(e.payload.from))} → ${humanize(String(e.payload.to))}`;
  }
  return humanize(e.event_type);
}

function AuditTrail({ inv }: { inv: InvoiceDetail }) {
  return (
    <Table label="Audit trail">
      <thead>
        <tr>
          <th className={th}>Time</th>
          <th className={th}>Event</th>
          <th className={th}>By</th>
          <th className={th}>Detail</th>
        </tr>
      </thead>
      <tbody>
        {inv.timeline.map((e) => (
          <tr key={e.id}>
            <td className={cx(td, "font-mono text-[13px] text-ink-2")} title={when(e.created_at)}>
              {clock(e.created_at)}
            </td>
            <td className={td}>{describe(e)}</td>
            <td className={cx(td, "text-ink-2")}>{e.actor}</td>
            <td className={cx(td, "max-w-[22rem] truncate text-ink-2")}>
              {typeof e.payload.reason === "string" ? `“${e.payload.reason}”` : ""}
              {Array.isArray(e.payload.reasons) && (e.payload.reasons as string[]).map((r) => reasonInfo(r).label).join(", ")}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function InvoiceDetailPage() {
  const { id = "" } = useParams();
  const invoice = useQuery({ queryKey: ["invoice", id], queryFn: () => api.invoice(id), refetchInterval: 4000 });
  const queue = useQuery({ queryKey: ["invoices", "NEEDS_REVIEW"], queryFn: () => api.listInvoices("NEEDS_REVIEW") });
  // The next invoice after this one in the oldest-first queue, if this one is in it.
  const ordered = [...(queue.data ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const at = ordered.findIndex((r) => r.id === id);
  const nextId = ordered.find((r, i) => r.id !== id && i > at)?.id ?? null;

  if (invoice.error) return <ErrorNote error={invoice.error} />;
  if (!invoice.data) return <SkeletonRows rows={12} cols={4} />;
  const inv = invoice.data;
  const reasons = inv.reasons;
  const reviewing = inv.status === "NEEDS_REVIEW";

  return (
    <div className="space-y-4">
      <Link to="/review" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft aria-hidden className="h-4 w-4" /> Back to the queue
      </Link>

      <section aria-label="Invoice summary" className="flex flex-wrap items-center justify-between gap-6 rounded-2xl border border-line bg-surface p-6">
        <div className="min-w-0">
          <p className="label-mono">Invoice</p>
          <h1 className="mt-1 break-all font-display text-2xl font-bold tracking-tight">
            {inv.invoice_number ?? "Uploaded document"}
          </h1>
          <ul className="mt-3 flex flex-wrap gap-2 text-sm">
            {[
              ["Vendor", inv.vendor_id ?? "—"],
              ["PO", inv.po_number ?? "—"],
              ["Version", String(inv.version)],
              ["Received", when(inv.created_at)],
            ].map(([k, v]) => (
              <li key={k} className="rounded-lg border border-line px-3 py-1">
                <span className="text-ink-2">{k}</span> <span className="font-mono text-[13px]">{v}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-line bg-fill-2 p-4 sm:min-w-64">
          <div className="flex items-center justify-between gap-3">
            <p className="label-mono">Total</p>
            <StatusBadge status={inv.status} />
          </div>
          <p className="mt-2 font-display text-xl font-bold tracking-tight">
            <span className="text-ink-3">{inv.currency}</span> {money(inv.total)}
          </p>
          {nextId && (
            <Link
              to={`/invoices/${nextId}`}
              className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
            >
              Next in queue <ArrowRight aria-hidden className="h-4 w-4" />
            </Link>
          )}
        </div>
      </section>

      {reasons.length > 0 && (
        <Module icon={Flag} title={reviewing ? "Why it needs your decision" : "Why it was flagged"} count={reasons.length} alert={reviewing}>
          <ul className="grid gap-x-6 gap-y-2 px-4 py-3 sm:grid-cols-2">
            {reasons.map((r) => (
              <li key={r} className="flex items-start gap-2 text-sm">
                <ReasonTag code={r} />
                <span className="text-ink-2">{reasonInfo(r).explain}</span>
              </li>
            ))}
          </ul>
        </Module>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-12">
        <Module icon={Boxes} title="Three-way match" className="lg:col-span-8" extra={<span className="font-mono text-xs text-ink-2">{inv.purchase_order?.po_number ?? ""}</span>}>
          <ThreeWayMatch inv={inv} />
        </Module>
        <Module icon={Gavel} title="Decision" className="lg:col-span-4">
          <Decision inv={inv} />
        </Module>

        <Module icon={ScanText} title="Read from the document" className="lg:col-span-7">
          <Evidence id={id} />
        </Module>
        <Module icon={FileText} title="Document" className="lg:col-span-5">
          <DocumentPreview id={id} />
        </Module>

        <Module icon={History} title="Audit trail" count={inv.timeline.length} className="lg:col-span-8" extra={inv.trace_id ? <span className="font-mono text-xs text-ink-2">trace {inv.trace_id.slice(0, 8)}</span> : null}>
          <AuditTrail inv={inv} />
        </Module>
        <div className="space-y-4 lg:col-span-4">
          <Module icon={UserCheck} title="Approvals" count={inv.approvals.length}>
            {inv.approvals.length === 0 ? (
              <p className="px-4 py-3 text-sm text-ink-2">No approvals yet.</p>
            ) : (
              <ul className="divide-y divide-line">
                {inv.approvals.map((a, i) => (
                  <li key={i} className="px-4 py-2.5 text-sm">
                    <span className="font-semibold">{humanize(a.decision)}</span> by {a.reviewer} · v{a.invoice_version} ·{" "}
                    <span className="font-mono text-[13px]">{money(a.amount)}</span>
                    {a.invoice_version !== inv.version && <span className="ml-1 text-xs font-semibold text-red">void, older version</span>}
                    {a.reason && <p className="truncate text-ink-2">“{a.reason}”</p>}
                  </li>
                ))}
              </ul>
            )}
          </Module>
          <Module icon={Cpu} title="Model calls" count={inv.llm_calls.length}>
            {inv.llm_calls.length === 0 ? (
              <p className="px-4 py-3 text-sm text-ink-2">No model calls for this invoice.</p>
            ) : (
              <ul className="divide-y divide-line">
                {inv.llm_calls.map((c, i) => (
                  <li key={i} className="flex flex-wrap justify-between gap-x-3 px-4 py-2.5 text-sm">
                    <span>
                      {c.model}
                      {isSimulated(c.provider) && <span className="ml-1 text-xs font-semibold text-amber">simulated</span>}
                    </span>
                    <span className="font-mono text-[13px] text-ink-2">
                      {c.input_tokens}/{c.output_tokens} tok · {c.latency_ms} ms · ${Number(c.cost_usd).toFixed(4)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Module>
        </div>
      </div>
    </div>
  );
}
