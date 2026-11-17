import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type AuditEvent, type InvoiceDetail } from "../api";
import { Button, Card, CardHeader, Empty, ErrorNote, Input, StatusBadge, td, th } from "../components/ui";
import { humanize, money, when } from "../format";

function latestReasons(timeline: AuditEvent[]): string[] {
  for (const event of [...timeline].reverse()) {
    const reasons = event.payload.reasons;
    if (Array.isArray(reasons) && reasons.length) return reasons as string[];
  }
  return [];
}

function DocumentPreview({ id }: { id: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const doc = useQuery({ queryKey: ["document", id], queryFn: () => api.document(id), retry: false });
  useEffect(() => {
    if (!doc.data) return;
    const objectUrl = URL.createObjectURL(doc.data);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [doc.data]);

  if (doc.isError) return <Empty>No document: this invoice was submitted as structured data.</Empty>;
  if (!url) return <Empty>Loading document…</Empty>;
  return (
    <div>
      <iframe title="Invoice document" src={url} className="h-[640px] w-full" />
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="block border-t border-border px-4 py-2 text-sm text-primary hover:underline"
      >
        Open PDF in a new tab
      </a>
    </div>
  );
}

function Actions({ invoice }: { invoice: InvoiceDetail }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [total, setTotal] = useState("");
  const done = () => {
    setReason("");
    setTotal("");
    queryClient.invalidateQueries();
  };
  const approve = useMutation({ mutationFn: () => api.approve(invoice.id, invoice.version, reason), onSuccess: done });
  const reject = useMutation({ mutationFn: () => api.reject(invoice.id, invoice.version, reason), onSuccess: done });
  const edit = useMutation({
    mutationFn: () => api.edit(invoice.id, invoice.version, reason, { total }),
    onSuccess: done,
  });
  const post = useMutation({ mutationFn: () => api.post(invoice.id), onSuccess: done });
  const replay = useMutation({ mutationFn: () => api.replay(invoice.id), onSuccess: done });
  const error = approve.error ?? reject.error ?? edit.error ?? post.error ?? replay.error;

  const reviewable = invoice.status === "NEEDS_REVIEW";
  const postable = invoice.status === "APPROVED" || invoice.status === "AUTO_APPROVED";
  const editable = reviewable || postable;

  return (
    <Card>
      <CardHeader title="Decision" />
      <div className="space-y-3 p-4">
        <ErrorNote error={error} />
        {editable && (
          <Input
            aria-label="Reason"
            placeholder="Reason (required, recorded in the audit log)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        )}
        <div className="flex flex-wrap gap-2">
          {reviewable && (
            <>
              <Button disabled={!reason.trim() || approve.isPending} onClick={() => approve.mutate()}>
                Approve version {invoice.version}
              </Button>
              <Button variant="danger" disabled={!reason.trim() || reject.isPending} onClick={() => reject.mutate()}>
                Reject
              </Button>
            </>
          )}
          {postable && (
            <Button disabled={post.isPending} onClick={() => post.mutate()}>
              Post to system of record
            </Button>
          )}
          {invoice.status === "FAILED" && (
            <Button disabled={replay.isPending} onClick={() => replay.mutate()}>
              Replay extraction
            </Button>
          )}
        </div>
        {post.data && (
          <p className="text-sm text-muted-foreground">
            Result: {humanize(post.data.outcome)} (key {post.data.idempotency_key.slice(0, 12)}…)
          </p>
        )}
        {editable && (
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <Input
              aria-label="Corrected total"
              className="w-40"
              inputMode="decimal"
              placeholder="Corrected total"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
            />
            <Button
              variant="secondary"
              disabled={!reason.trim() || !/^\d+(\.\d{1,4})?$/.test(total) || edit.isPending}
              onClick={() => edit.mutate()}
            >
              Save edit
            </Button>
            <span className="text-xs text-muted-foreground">An edit creates a new version and voids any approval.</span>
          </div>
        )}
        {!editable && invoice.status !== "FAILED" && (
          <p className="text-sm text-muted-foreground">No action available in this state.</p>
        )}
      </div>
    </Card>
  );
}

export default function InvoiceDetailPage() {
  const { id = "" } = useParams();
  const invoice = useQuery({ queryKey: ["invoice", id], queryFn: () => api.invoice(id), refetchInterval: 4000 });
  const fields = useQuery({ queryKey: ["extraction", id], queryFn: () => api.extraction(id) });

  if (invoice.error) return <ErrorNote error={invoice.error} />;
  if (!invoice.data) return <Empty>Loading…</Empty>;
  const inv = invoice.data;
  const reasons = latestReasons(inv.timeline);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <Link to="/review" className="text-sm text-primary hover:underline">
          ← Review queue
        </Link>
        <h1 className="text-xl font-semibold">{inv.invoice_number ?? "Uploaded document"}</h1>
        <StatusBadge status={inv.status} />
        <span className="text-sm text-muted-foreground">
          version {inv.version} · vendor {inv.vendor_id ?? "—"} · PO {inv.po_number ?? "—"} ·{" "}
          {money(inv.total, inv.currency)}
        </span>
      </div>

      {reasons.length > 0 && (
        <Card className="border-warning/50 bg-warning/5 p-4">
          <h2 className="mb-2 text-sm font-semibold">
            {inv.status === "NEEDS_REVIEW" ? "Why this needs a human" : "Flagged for review because"}
          </h2>
          <ul className="flex flex-wrap gap-2">
            {reasons.map((r) => (
              <li key={r} className="rounded bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning">
                {humanize(r)}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Document" />
          <DocumentPreview id={id} />
        </Card>

        <div className="space-y-4">
          <Actions invoice={inv} />

          <Card>
            <CardHeader title="Extracted fields and evidence" />
            {fields.data && fields.data.length > 0 ? (
              <table className="w-full">
                <thead className="border-b border-border">
                  <tr>
                    <th className={th}>Field</th>
                    <th className={th}>Value</th>
                    <th className={`${th} text-right`}>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {fields.data.map((f) => {
                    const low = Number(f.confidence) < 0.9;
                    return (
                      <tr key={f.field} className="border-b border-border last:border-0">
                        <td className={`${td} text-muted-foreground`}>{f.field}</td>
                        <td className={td} title={f.snippet ? `Page ${f.page ?? "?"}: “${f.snippet}”` : "No evidence quoted"}>
                          {f.value ?? "—"}
                        </td>
                        <td className={`${td} text-right tabular-nums ${low ? "font-medium text-danger" : ""}`}>
                          {Number(f.confidence).toFixed(2)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <Empty>No extraction for this invoice.</Empty>
            )}
          </Card>

          <Card>
            <CardHeader title="Lines" />
            {inv.lines.length ? (
              <table className="w-full">
                <thead className="border-b border-border">
                  <tr>
                    <th className={th}>SKU</th>
                    <th className={`${th} text-right`}>Qty</th>
                    <th className={`${th} text-right`}>Unit price</th>
                  </tr>
                </thead>
                <tbody>
                  {inv.lines.map((l) => (
                    <tr key={l.line_no} className="border-b border-border last:border-0">
                      <td className={td}>{l.sku}</td>
                      <td className={`${td} text-right tabular-nums`}>{Number(l.qty)}</td>
                      <td className={`${td} text-right tabular-nums`}>{money(l.unit_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Empty>No lines yet.</Empty>
            )}
          </Card>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title={`Audit timeline${inv.trace_id ? ` · trace ${inv.trace_id.slice(0, 8)}` : ""}`} />
          <ol className="divide-y divide-border">
            {inv.timeline.map((e) => (
              <li key={e.id} className="px-4 py-2 text-sm">
                <div className="flex flex-wrap justify-between gap-2">
                  <span className="font-medium">
                    {e.event_type === "invoice.state_changed"
                      ? `${humanize(String(e.payload.from))} → ${humanize(String(e.payload.to))}`
                      : humanize(e.event_type)}
                  </span>
                  <span className="text-muted-foreground">
                    {e.actor} · {when(e.created_at)}
                  </span>
                </div>
                {typeof e.payload.reason === "string" && (
                  <p className="text-muted-foreground">“{e.payload.reason}”</p>
                )}
              </li>
            ))}
          </ol>
        </Card>

        <Card>
          <CardHeader title="Model calls" />
          {inv.llm_calls.length ? (
            <table className="w-full">
              <thead className="border-b border-border">
                <tr>
                  <th className={th}>Model</th>
                  <th className={`${th} text-right`}>Tokens in/out</th>
                  <th className={`${th} text-right`}>Latency</th>
                  <th className={`${th} text-right`}>Cost (USD)</th>
                </tr>
              </thead>
              <tbody>
                {inv.llm_calls.map((c, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td className={td}>
                      {c.model}
                      {c.provider === "fake" && <span className="ml-2 text-xs text-warning">simulated</span>}
                    </td>
                    <td className={`${td} text-right tabular-nums`}>
                      {c.input_tokens}/{c.output_tokens}
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{c.latency_ms} ms</td>
                    <td className={`${td} text-right tabular-nums`}>{Number(c.cost_usd).toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty>No model calls for this invoice.</Empty>
          )}
        </Card>
      </div>

      {inv.approvals.length > 0 && (
        <Card>
          <CardHeader title="Approvals" />
          <ul className="divide-y divide-border">
            {inv.approvals.map((a, i) => (
              <li key={i} className="px-4 py-2 text-sm">
                <span className="font-medium">{humanize(a.decision)}</span> by {a.reviewer} on version{" "}
                {a.invoice_version} for {money(a.amount, inv.currency)}
                {a.invoice_version !== inv.version && (
                  <span className="ml-2 text-xs text-danger">void (older version)</span>
                )}
                {a.reason && <span className="text-muted-foreground"> · “{a.reason}”</span>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
