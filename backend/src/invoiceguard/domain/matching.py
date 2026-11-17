"""Three-way matching: invoice against purchase order and goods receipts."""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from invoiceguard.domain.models import GoodsReceipt, Invoice, PurchaseOrder, Tolerances
from invoiceguard.domain.money import within_tolerance


class DiscrepancyCode(StrEnum):
    NO_PO = "NO_PO"
    NO_RECEIPT = "NO_RECEIPT"
    VENDOR_MISMATCH = "VENDOR_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    UNKNOWN_SKU = "UNKNOWN_SKU"
    PRICE_VARIANCE = "PRICE_VARIANCE"
    QTY_OVER_ORDERED = "QTY_OVER_ORDERED"
    QTY_OVER_RECEIVED = "QTY_OVER_RECEIVED"


# Header-level problems make the whole match untrustworthy, so quality drops to zero.
_HEADER_CODES = {
    DiscrepancyCode.NO_PO,
    DiscrepancyCode.NO_RECEIPT,
    DiscrepancyCode.VENDOR_MISMATCH,
    DiscrepancyCode.CURRENCY_MISMATCH,
}


@dataclass(frozen=True)
class Discrepancy:
    code: DiscrepancyCode
    sku: str | None
    detail: str


@dataclass(frozen=True)
class MatchResult:
    discrepancies: tuple[Discrepancy, ...]
    # Share of invoice lines with no discrepancy, from 0 to 1. Zero on any header-level problem.
    match_quality: Decimal


def three_way_match(
    invoice: Invoice,
    po: PurchaseOrder | None,
    receipts: Iterable[GoodsReceipt],
    tolerances: Tolerances = Tolerances(),
    previously_invoiced: Mapping[str, Decimal] | None = None,
) -> MatchResult:
    """Compare invoice lines to the PO (price, ordered quantity) and receipts (received quantity).

    `previously_invoiced` holds quantities already billed per SKU on earlier invoices
    against the same PO, so split invoices cannot exceed what was ordered or received.
    """
    if po is None:
        return MatchResult(
            (Discrepancy(DiscrepancyCode.NO_PO, None, f"no PO found for {invoice.po_number}"),),
            Decimal(0),
        )

    receipt_list = list(receipts)
    prior = previously_invoiced or {}
    found: list[Discrepancy] = []

    if po.vendor_id != invoice.vendor_id:
        found.append(
            Discrepancy(
                DiscrepancyCode.VENDOR_MISMATCH,
                None,
                f"invoice vendor {invoice.vendor_id}, PO vendor {po.vendor_id}",
            )
        )
    if po.currency != invoice.currency:
        found.append(
            Discrepancy(
                DiscrepancyCode.CURRENCY_MISMATCH,
                None,
                f"invoice currency {invoice.currency}, PO currency {po.currency}",
            )
        )
    if not receipt_list:
        found.append(Discrepancy(DiscrepancyCode.NO_RECEIPT, None, "no goods receipt on file"))

    po_lines = {line.sku: line for line in po.lines}
    received: dict[str, Decimal] = defaultdict(Decimal)
    for receipt in receipt_list:
        for line in receipt.lines:
            received[line.sku] += line.qty

    qty_factor = Decimal(1) + tolerances.qty_pct / Decimal(100)
    bad_skus: set[str] = set()

    for line in invoice.lines:
        po_line = po_lines.get(line.sku)
        if po_line is None:
            found.append(
                Discrepancy(DiscrepancyCode.UNKNOWN_SKU, line.sku, "SKU is not on the PO")
            )
            bad_skus.add(line.sku)
            continue

        if not within_tolerance(line.unit_price, po_line.unit_price, tolerances.price_pct):
            found.append(
                Discrepancy(
                    DiscrepancyCode.PRICE_VARIANCE,
                    line.sku,
                    f"invoice price {line.unit_price}, PO price {po_line.unit_price}",
                )
            )
            bad_skus.add(line.sku)

        billed = line.qty + prior.get(line.sku, Decimal(0))
        if billed > po_line.qty * qty_factor:
            found.append(
                Discrepancy(
                    DiscrepancyCode.QTY_OVER_ORDERED,
                    line.sku,
                    f"billed {billed}, ordered {po_line.qty}",
                )
            )
            bad_skus.add(line.sku)

        if receipt_list and billed > received.get(line.sku, Decimal(0)) * qty_factor:
            found.append(
                Discrepancy(
                    DiscrepancyCode.QTY_OVER_RECEIVED,
                    line.sku,
                    f"billed {billed}, received {received.get(line.sku, Decimal(0))}",
                )
            )
            bad_skus.add(line.sku)

    if any(d.code in _HEADER_CODES for d in found) or not invoice.lines:
        quality = Decimal(0)
    else:
        good = sum(1 for line in invoice.lines if line.sku not in bad_skus)
        quality = Decimal(good) / Decimal(len(invoice.lines))

    return MatchResult(tuple(found), quality)
