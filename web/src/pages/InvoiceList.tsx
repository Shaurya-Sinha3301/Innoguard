import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Card, CardHeader, Empty, ErrorNote, StatusBadge, td, th } from "../components/ui";
import { money, when } from "../format";

const STATUSES = ["", "NEEDS_REVIEW", "AUTO_APPROVED", "APPROVED", "POSTED", "REJECTED", "FAILED", "RECEIVED", "EXTRACTING"];

export default function InvoiceList({ status, title }: { status?: string; title: string }) {
  const [filter, setFilter] = useState(status ?? "");
  const query = useQuery({
    queryKey: ["invoices", filter],
    queryFn: () => api.listInvoices(filter || undefined),
    refetchInterval: 5000,
  });

  return (
    <Card>
      <CardHeader
        title={title}
        action={
          status === undefined && (
            <select
              aria-label="Filter by status"
              className="h-8 rounded border border-border bg-background px-2 text-sm"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s ? s.replace(/_/g, " ").toLowerCase() : "all statuses"}
                </option>
              ))}
            </select>
          )
        }
      />
      <ErrorNote error={query.error} />
      {query.data && query.data.length === 0 && (
        <Empty>{status === "NEEDS_REVIEW" ? "Nothing waiting for review." : "No invoices yet."}</Empty>
      )}
      {query.data && query.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-border">
              <tr>
                <th className={th}>Invoice</th>
                <th className={th}>Vendor</th>
                <th className={th}>PO</th>
                <th className={`${th} text-right`}>Total</th>
                <th className={th}>Status</th>
                <th className={th}>Received</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((inv) => (
                <tr key={inv.id} className="border-b border-border last:border-0 hover:bg-muted/50">
                  <td className={td}>
                    <Link className="font-medium text-primary hover:underline" to={`/invoices/${inv.id}`}>
                      {inv.invoice_number ?? "(not yet read)"}
                    </Link>
                  </td>
                  <td className={td}>{inv.vendor_id ?? "—"}</td>
                  <td className={td}>{inv.po_number ?? "—"}</td>
                  <td className={`${td} text-right tabular-nums`}>{money(inv.total, inv.currency)}</td>
                  <td className={td}>
                    <StatusBadge status={inv.status} />
                  </td>
                  <td className={`${td} text-muted-foreground`}>{when(inv.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
