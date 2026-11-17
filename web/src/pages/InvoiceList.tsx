import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Empty, ErrorNote, Module, num, Row, Segmented, SkeletonRows, StatusBadge, Table, td, th } from "../components/ui";
import { money, when } from "../format";
import { primaryReasons, reasonInfo } from "../reasons";

const FILTERS = [
  { value: "", label: "All" },
  { value: "NEEDS_REVIEW", label: "Needs review" },
  { value: "AUTO_APPROVED", label: "Auto-approved" },
  { value: "APPROVED", label: "Approved" },
  { value: "POSTED", label: "Posted" },
  { value: "REJECTED", label: "Rejected" },
  { value: "FAILED", label: "Failed" },
];

export default function InvoiceList() {
  const [status, setStatus] = useState("");
  const query = useQuery({
    queryKey: ["invoices", status],
    queryFn: () => api.listInvoices(status || undefined),
    refetchInterval: 5000,
  });

  return (
    <Module title="All invoices" count={query.data?.length}>
      <div className="border-b border-line px-3 py-2">
        <Segmented label="Filter by status" value={status} onChange={setStatus} options={FILTERS} />
      </div>
      <ErrorNote error={query.error} />
      {query.isLoading && <SkeletonRows rows={12} cols={6} />}
      {query.data?.length === 0 && <Empty title="No invoices match">Try another status, or upload a document.</Empty>}
      {query.data && query.data.length > 0 && (
        <Table label="Invoices, newest first">
          <thead>
            <tr>
              <th className={th}>Invoice</th>
              <th className={th}>Vendor</th>
              <th className={th}>PO</th>
              <th className={th}>Status</th>
              <th className={th}>Last decision reason</th>
              <th className={`${th} text-right`}>Total</th>
              <th className={th}>Received</th>
            </tr>
          </thead>
          <tbody>
            {query.data.map((inv) => {
              const reasons = primaryReasons(inv.reasons ?? []);
              return (
                <Row key={inv.id}>
                  <td className={td}>
                    <Link to={`/invoices/${inv.id}`} className="font-mono text-[13px] font-semibold underline decoration-line underline-offset-4 hover:decoration-red">
                      {inv.invoice_number ?? "Unread document"}
                    </Link>
                  </td>
                  <td className={`${td} font-mono text-[13px]`}>{inv.vendor_id ?? "—"}</td>
                  <td className={`${td} font-mono text-[13px] text-ink-2`}>{inv.po_number ?? "—"}</td>
                  <td className={td}>
                    <StatusBadge status={inv.status} />
                  </td>
                  <td className={`${td} text-ink-2`}>{reasons.length ? reasons.map((r) => reasonInfo(r).label).join(", ") : "—"}</td>
                  <td className={`${td} ${num}`}>
                    <span className="text-ink-3">{inv.currency}</span> {money(inv.total)}
                  </td>
                  <td className={`${td} text-ink-2`}>{when(inv.created_at)}</td>
                </Row>
              );
            })}
          </tbody>
        </Table>
      )}
    </Module>
  );
}
