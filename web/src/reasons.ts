/** Plain-language names and explanations for the reason codes the backend records. The loaded
 * pack manifest is the source of truth; the table below is only the fallback before it loads. */
import { allManifests, getPack } from "./pack";

type Reason = { label: string; explain: string };

const REASONS: Record<string, Reason> = {
  PRICE_VARIANCE: { label: "Price variance", explain: "A unit price differs from the PO price by more than the 2% tolerance." },
  QTY_OVER_RECEIVED: { label: "Billed over received", explain: "The invoice bills more units than the goods receipts show arrived." },
  QTY_OVER_ORDERED: { label: "Billed over ordered", explain: "The invoice bills more units than the purchase order ordered." },
  NO_RECEIPT: { label: "No goods receipt", explain: "Nothing has been recorded as received against this PO." },
  NO_PO: { label: "No purchase order", explain: "The PO number on the invoice does not match a purchase order on file." },
  VENDOR_MISMATCH: { label: "Vendor mismatch", explain: "The vendor on the invoice is not the vendor on the purchase order." },
  CURRENCY_MISMATCH: { label: "Currency mismatch", explain: "The invoice currency differs from the purchase order currency." },
  UNKNOWN_SKU: { label: "Item not on PO", explain: "An invoice line is for an item the purchase order does not include." },
  LINE_SUM_MISMATCH: { label: "Lines don't add up", explain: "The line amounts do not sum to the subtotal printed on the invoice." },
  TOTAL_MISMATCH: { label: "Total doesn't add up", explain: "Subtotal plus tax does not equal the total printed on the invoice." },
  NO_LINES: { label: "No line items", explain: "No line items could be read from the invoice." },
  DUPLICATE_EXACT: { label: "Exact duplicate", explain: "The same file has been submitted before." },
  DUPLICATE_BUSINESS_KEY: { label: "Possible duplicate", explain: "This vendor already has an invoice with the same number." },
  HIGH_VALUE: { label: "High value", explain: "Above the auto-approval limit, so policy always asks a human." },
  LOW_EXTRACTION_CONFIDENCE: { label: "Low read confidence", explain: "At least one field was read with low confidence or without matching evidence." },
  LOW_MATCH_QUALITY: { label: "Lines don't match", explain: "Not every invoice line matched its PO and receipt cleanly." },
  EXTRACTION_INCOMPLETE: { label: "Incomplete read", explain: "Required fields could not be read, so the invoice was not reconciled." },
  EXTRACTION_FAILED: { label: "Read failed", explain: "The document could not be read." },
};

const PREFIXED: Record<string, Reason> = {
  MISSING_FIELD: { label: "Missing field", explain: "A required field was not found on the document" },
  UNPARSEABLE: { label: "Unreadable value", explain: "A value could not be read as a number or code" },
  EVIDENCE_NOT_FOUND: { label: "Unverified value", explain: "The text quoted for this value is not in the PDF" },
};

export function reasonInfo(code: string): Reason {
  const packs = [getPack(), ...allManifests()].filter((m): m is NonNullable<typeof m> => m !== null);
  for (const pack of packs) {
    const declared = pack.reasons.find((x) => x.code === code);
    if (declared) return declared;
  }
  if (packs.length === 0 && REASONS[code]) return REASONS[code];
  const [prefix, field] = code.split(":");
  const prefixed = packs.flatMap((m) => m.reason_prefixes).find((x) => x.code === prefix) ?? PREFIXED[prefix];
  if (field && prefixed) {
    return { label: `${prefixed.label}: ${field}`, explain: `${prefixed.explain} (${field}).` };
  }
  return { label: code.replace(/_/g, " ").toLowerCase(), explain: "" };
}

/** Reasons worth showing in a compact list. "Lines don't match" is implied by any
 * line-level reason, so it only shows on its own. */
export function primaryReasons(codes: string[]): string[] {
  const implied = getPack()?.implied_reason ?? "LOW_MATCH_QUALITY";
  const rest = codes.filter((c) => c !== implied);
  return rest.length ? rest : codes;
}
