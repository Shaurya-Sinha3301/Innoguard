import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileSearch, ListChecks, ScanText, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Invoice } from "../api";
import {
  Button,
  Chip,
  cx,
  Empty,
  ErrorNote,
  Module,
  ReasonTag,
  Segmented,
  SegmentedBar,
  SkeletonRows,
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
      extra={
        <button
          type="button"
          aria-label="Hide this explanation"
          className="rounded-md p-1 text-ink-2 hover:bg-fill hover:text-ink"
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
        <div key={title} className="flex gap-3 px-4 py-3.5">
          <Icon aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-ink-2" />
          <p className="text-sm">
            <b className="font-semibold">{title}.</b> <span className="text-ink-2">{text}</span>
          </p>
        </div>
      ))}
    </Module>
  );
}

function QueueRow({ inv, now }: { inv: Invoice; now: number }) {
  const reasons = primaryReasons(inv.reasons ?? []);
  return (
    <li>
      <Link
        to={`/invoices/${inv.id}`}
        className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1.5 rounded-xl border border-line bg-surface px-4 py-3 transition-colors hover:border-ink-3 hover:bg-fill-2 sm:grid-cols-[150px_1fr_auto_64px]"
      >
        <span className="justify-self-start">
          <Chip>{inv.invoice_number ?? "Unread document"}</Chip>
        </span>
        <span className="order-3 col-span-2 flex min-w-0 flex-wrap items-center gap-1.5 sm:order-none sm:col-span-1">
          <span className="font-mono text-[13px] text-ink">{inv.vendor_id ?? "No vendor"}</span>
          <span className="font-mono text-xs text-ink-3">{inv.po_number ?? "no PO"}</span>
          {reasons.slice(0, 2).map((r) => (
            <ReasonTag key={r} code={r} title />
          ))}
          {reasons.length > 2 && <span className="text-xs text-ink-2">+{reasons.length - 2}</span>}
        </span>
        <span className="text-right font-mono text-[14px] tabular-nums">
          <span className="text-ink-3">{inv.currency}</span> {money(inv.total)}
        </span>
        <span className="hidden text-right font-mono text-xs text-ink-2 sm:block">{age(inv.created_at, now)}</span>
      </Link>
    </li>
  );
}

export default function ReviewDesk() {
  const queue = useQuery({
    queryKey: ["invoices", "NEEDS_REVIEW"],
    queryFn: () => api.listInvoices("NEEDS_REVIEW"),
    refetchInterval: 5000,
  });
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, refetchInterval: 10000 });
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });
  const navigate = useNavigate();
  const [reason, setReason] = useState("all");
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  // "/" jumps to search, as the hint on the field says.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
  const needle = search.trim().toLowerCase();
  const shown = rows
    .filter((r) => reason === "all" || primaryReasons(r.reasons ?? []).includes(reason))
    .filter(
      (r) => !needle || [r.invoice_number, r.vendor_id, r.po_number].some((v) => v?.toLowerCase().includes(needle)),
    );
  const max = Math.max(1, ...reasonCounts.map(([, n]) => n));
  const d = metrics.data?.decisions;
  const oldest = rows[0];
  const now = Date.now();

  return (
    <div className="grid gap-6 lg:grid-cols-[380px_1fr]">
      {/* Left pane: where the queue stands, and the one action that moves it. */}
      <aside className="flex flex-col gap-5 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto">
        <div>
          <p className="label-mono">Review queue</p>
          <h1 className="mt-1 font-display text-2xl font-bold tracking-tight">Needs your decision</h1>
          {me.data && <p className="mt-1 text-sm text-ink-2">Signed in as {me.data.name}</p>}
        </div>

        <div className="border-t border-line pt-5">
          <div className="flex items-end justify-between gap-3">
            <p className="font-display text-3xl font-bold leading-none tracking-tight">
              {rows.length}
              <span className="ml-2 text-md font-medium text-ink-2">waiting</span>
            </p>
            {d && d.decided > 0 && (
              <span className="label-mono pb-1 text-green">{percent(d.straight_through_rate)} straight through</span>
            )}
          </div>
          <div className="mt-4">
            <SegmentedBar
              value={d?.auto_approved ?? 0}
              total={d?.decided ?? 0}
              label={`${d?.auto_approved ?? 0} of ${d?.decided ?? 0} decided invoices were auto-approved`}
            />
            <div className="label-mono mt-2 flex justify-between">
              <span>Auto-approved {d?.auto_approved ?? "—"}</span>
              <span>Decided {d?.decided ?? "—"}</span>
            </div>
          </div>
        </div>

        <div className="border-t border-line pt-5">
          <div className="mb-2 flex items-center justify-between">
            <p className="label-mono">Why invoices are waiting</p>
            {reason !== "all" && (
              <button type="button" className="text-xs text-ink-2 underline hover:text-ink" onClick={() => setReason("all")}>
                Clear filter
              </button>
            )}
          </div>
          {reasonCounts.length === 0 ? (
            <p className="text-sm text-ink-2">No open exceptions.</p>
          ) : (
            <ul>
              {reasonCounts.map(([code, n]) => (
                <li key={code} className="border-b border-line/70 last:border-0">
                  <button
                    type="button"
                    aria-pressed={reason === code}
                    onClick={() => setReason(reason === code ? "all" : code)}
                    title={reasonInfo(code).explain}
                    className="grid w-full grid-cols-[1fr_auto] items-center gap-x-2 py-2.5 text-left text-sm"
                  >
                    <span className={cx(reason === code ? "font-semibold text-accent" : "text-ink")}>
                      {reasonInfo(code).label}
                    </span>
                    <span className="font-mono text-[13px] text-ink-2">{n}</span>
                    <span aria-hidden className="col-span-2 mt-1.5 h-1 rounded-full bg-fill">
                      <span className="block h-1 rounded-full bg-red" style={{ width: `${(n / max) * 100}%` }} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <dl className="grid grid-cols-2 gap-3 border-t border-line pt-5 text-sm">
          <div>
            <dt className="label-mono">Failed jobs</dt>
            <dd className={cx("mt-1 font-mono text-md", metrics.data?.operations.open_failed_jobs ? "text-red" : "")}>
              <Link to="/failed" className="hover:underline">
                {metrics.data?.operations.open_failed_jobs ?? "—"}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="label-mono">In outbox</dt>
            <dd className="mt-1 font-mono text-md">{metrics.data?.operations.outbox_pending ?? "—"}</dd>
          </div>
        </dl>

        <div className="mt-auto border-t border-line pt-5">
          <p className="mb-3 flex items-center gap-2 text-sm">
            <span aria-hidden className="h-2 w-2 rounded-sm bg-accent" />
            <span className="label-mono">Next</span>
            <b className="truncate font-semibold">
              {oldest ? `Oldest is ${oldest.invoice_number ?? "an unread document"}` : "Nothing waiting"}
            </b>
          </p>
          <Button
            size="lg"
            className="w-full"
            disabled={!oldest}
            onClick={() => oldest && navigate(`/invoices/${oldest.id}`)}
          >
            Review next invoice <ArrowRight aria-hidden className="h-4 w-4" />
          </Button>
          <p className="mt-2 text-xs text-ink-2">Opens the oldest invoice. Nothing is decided until you confirm.</p>
        </div>
      </aside>

      {/* Right pane: the queue itself. */}
      <div className="min-w-0 space-y-4">
        <Orientation />
        <label className="relative block">
          <span className="sr-only">Search the queue by invoice number, vendor or PO</span>
          <Search aria-hidden className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
          <input
            ref={searchRef}
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${rows.length} invoices by number, vendor or PO`}
            className="h-12 w-full rounded-xl border border-line pl-10 pr-10 text-base placeholder:text-ink-3"
          />
          <kbd className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-md border border-line px-1.5 font-mono text-xs text-ink-3">
            /
          </kbd>
        </label>
        {reasonCounts.length > 1 && (
          <Segmented
            label="Filter by reason"
            value={reason}
            onChange={setReason}
            options={[
              { value: "all", label: "All", count: rows.length },
              ...reasonCounts.map(([code, n]) => ({ value: code, label: reasonInfo(code).label, count: n })),
            ]}
          />
        )}
        <ErrorNote error={queue.error} />
        {queue.isLoading && (
          <div className="rounded-xl border border-line bg-surface">
            <SkeletonRows rows={8} cols={5} />
          </div>
        )}
        {queue.data && shown.length === 0 && (
          <div className="rounded-xl border border-line bg-surface">
            <Empty title={rows.length === 0 ? "Nothing waiting for you" : "No invoice matches"}>
              {rows.length === 0
                ? "Every invoice so far either cleared all checks or has been decided."
                : "Try a different search or clear the reason filter."}
            </Empty>
          </div>
        )}
        {shown.length > 0 && (
          <>
            <p className="label-mono">
              {shown.length} {shown.length === 1 ? "invoice" : "invoices"} · oldest first
            </p>
            <ul aria-label="Invoices waiting for a decision" className="space-y-2">
              {shown.map((inv) => (
                <QueueRow key={inv.id} inv={inv} now={now} />
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
