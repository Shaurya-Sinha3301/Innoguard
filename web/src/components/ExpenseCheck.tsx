import { AlertTriangle, Check } from "lucide-react";
import type { InvoiceDetail } from "../api";
import { money } from "../format";
import { cx, Empty, num, Table, td, th } from "./ui";

type Row = { check: string; claim: string; against: string; ok: boolean | null; note?: string };

/** An expense claim laid beside what it was checked against: the employee, the spending
 * policy and the card statement. A row is flagged where the claim and the record disagree. */
export default function ExpenseCheck({ inv }: { inv: InvoiceDetail }) {
  const c = inv.context;
  if (!c || !c.claim) return <Empty title="Not checked yet">The claim has not been read yet.</Empty>;
  const claim = c.claim;
  const txn = c.card_transaction;
  const cap = c.category ? Number(c.category.cap) : null;
  const total = Number(claim.total);
  const days = c.submitted_on
    ? Math.round((new Date(c.submitted_on).getTime() - new Date(claim.expense_date).getTime()) / 86400000)
    : null;
  const limit = c.max_auto_amount ? Number(c.max_auto_amount) : null;

  const rows: Row[] = [
    {
      check: "Employee",
      claim: claim.employee_id,
      against: c.employee ? `${c.employee.name} (${c.employee.employee_id})` : "not in the employee list",
      ok: Boolean(c.employee),
    },
    {
      check: "Card",
      claim: `ending ${claim.card_last4}`,
      against: c.employee ? `issued card ends ${c.employee.card_last4}` : "no card on file",
      ok: c.employee ? c.employee.card_last4 === claim.card_last4 : false,
    },
    {
      check: "Category",
      claim: claim.category,
      against: !c.category
        ? "not a policy category"
        : c.category.blocked
          ? "never reimbursed"
          : `cap ${claim.currency} ${money(c.category.cap)}`,
      ok: Boolean(c.category) && !c.category?.blocked && (cap === null || total <= cap),
    },
    {
      check: "Card statement",
      claim: `${claim.merchant}, ${claim.expense_date}, ${claim.currency} ${money(claim.total)}`,
      against: txn
        ? `${txn.merchant}, ${txn.txn_date}, ${txn.currency} ${money(txn.amount)}`
        : "no matching statement line",
      ok: txn ? txn.clean : false,
    },
    {
      check: "Age of the claim",
      claim: `${claim.expense_date}`,
      against: days === null ? "—" : days < 0 ? "dated after it was submitted" : `${days} days before it was submitted`,
      ok: days === null ? null : days >= 0 && days <= 60,
    },
    {
      check: "Auto-approval limit",
      claim: `${claim.currency} ${money(claim.total)}`,
      against: limit === null ? "none" : `up to ${claim.currency} ${money(String(limit))}`,
      ok: limit === null ? true : total <= limit,
    },
  ];

  return (
    <>
      <Table label="The claim against the employee list, spending policy and card statement">
        <thead>
          <tr>
            <th className={th}>Check</th>
            <th className={th}>The claim says</th>
            <th className={th}>The record says</th>
            <th className={`${th} text-right`}>
              <span className="sr-only">Result</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.check} className={cx(r.ok === false && "bg-red-tint")}>
              <td className={cx(td, "font-semibold")}>{r.check}</td>
              <td className={cx(td, num, "text-left")}>{r.claim}</td>
              <td className={cx(td, "text-ink-2", r.ok === false && "font-semibold text-red")}>{r.against}</td>
              <td className={cx(td, "text-right")}>
                {r.ok === true && (
                  <span className="inline-flex items-center gap-1 text-green">
                    <Check aria-hidden className="h-4 w-4" />
                    <span className="sr-only">Agrees</span>
                  </span>
                )}
                {r.ok === false && (
                  <span className="inline-flex items-center gap-1 text-red">
                    <AlertTriangle aria-hidden className="h-4 w-4" />
                    <span className="sr-only">Disagrees</span>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="px-4 py-2 text-xs text-ink-2">
        Highlighted rows disagree. The receipt must match a card statement line within 3 days and 0.01; these rules are
        assumptions for a synthetic company.
      </p>
    </>
  );
}
