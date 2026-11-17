"""Seeded generator of synthetic PO + goods receipt + invoice scenarios with ground truth.

All data is synthetic. Each scenario carries a label and the outcome a correct system
should reach, so decisions can be scored against known truth.
"""

import hashlib
import random
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from invoiceguard.domain.decision import Outcome
from invoiceguard.domain.duplicates import normalize_invoice_number
from invoiceguard.domain.models import (
    ExistingInvoice,
    GoodsReceipt,
    Invoice,
    InvoiceLine,
    PoLine,
    PurchaseOrder,
    ReceiptLine,
)
from invoiceguard.domain.money import quantize_money

TAX_RATE = Decimal("0.05")


class CaseLabel(StrEnum):
    CLEAN = "CLEAN"
    PARTIAL_RECEIPT_BILLED_CORRECTLY = "PARTIAL_RECEIPT_BILLED_CORRECTLY"
    PARTIAL_RECEIPT_OVERBILLED = "PARTIAL_RECEIPT_OVERBILLED"
    PRICE_VARIANCE = "PRICE_VARIANCE"
    QTY_OVER_ORDERED = "QTY_OVER_ORDERED"
    NO_RECEIPT = "NO_RECEIPT"
    NO_PO = "NO_PO"
    VENDOR_MISMATCH = "VENDOR_MISMATCH"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"
    DUPLICATE_EXACT = "DUPLICATE_EXACT"
    DUPLICATE_BUSINESS_KEY = "DUPLICATE_BUSINESS_KEY"
    HIGH_VALUE = "HIGH_VALUE"


# Labels whose invoices are genuinely wrong. HIGH_VALUE is a clean invoice that policy
# still routes to a human, so it is not "bad" but is expected to need review.
_GOOD = {CaseLabel.CLEAN, CaseLabel.PARTIAL_RECEIPT_BILLED_CORRECTLY, CaseLabel.HIGH_VALUE}

_EXPECTED = {
    CaseLabel.CLEAN: Outcome.AUTO_APPROVE,
    CaseLabel.PARTIAL_RECEIPT_BILLED_CORRECTLY: Outcome.AUTO_APPROVE,
    CaseLabel.DUPLICATE_EXACT: Outcome.REJECT,
}


@dataclass(frozen=True)
class Scenario:
    label: CaseLabel
    invoice: Invoice
    po: PurchaseOrder | None
    receipts: tuple[GoodsReceipt, ...]
    existing_invoices: tuple[ExistingInvoice, ...]

    @property
    def expected_outcome(self) -> Outcome:
        return _EXPECTED.get(self.label, Outcome.NEEDS_REVIEW)

    @property
    def is_bad(self) -> bool:
        return self.label not in _GOOD


def _digest(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _money(rng: random.Random, low: int, high: int) -> Decimal:
    return Decimal(rng.randint(low * 100, high * 100)) / Decimal(100)


def _build_invoice(
    *,
    number: str,
    vendor_id: str,
    po_number: str | None,
    lines: tuple[InvoiceLine, ...],
    file_hash: str,
    total_override: Decimal | None = None,
) -> Invoice:
    subtotal = quantize_money(sum((line.qty * line.unit_price for line in lines), Decimal(0)))
    tax = quantize_money(subtotal * TAX_RATE)
    return Invoice(
        invoice_number=number,
        vendor_id=vendor_id,
        po_number=po_number,
        currency="INR",
        lines=lines,
        subtotal=subtotal,
        tax=tax,
        total=total_override if total_override is not None else subtotal + tax,
        file_hash=file_hash,
    )


def generate_scenario(rng: random.Random, index: int, label: CaseLabel) -> Scenario:
    vendor_id = f"V{rng.randint(1, 9):03d}"
    po_number = f"PO-{index:05d}"
    number = f"INV-{index:04d}"

    big = label is CaseLabel.HIGH_VALUE
    n_lines = rng.randint(1, 4)
    po_lines = tuple(
        PoLine(
            sku=f"SKU-{rng.randint(1, 500):03d}-{i}",
            qty=Decimal(rng.randint(50, 80) if big else rng.randint(2, 15)),
            unit_price=_money(rng, 250, 400) if big else _money(rng, 5, 150),
        )
        for i in range(n_lines)
    )
    po = PurchaseOrder(po_number, vendor_id, "INR", po_lines)
    full_receipt = GoodsReceipt(
        f"GR-{index:05d}", po_number, tuple(ReceiptLine(p.sku, p.qty) for p in po_lines)
    )

    invoice_lines = tuple(InvoiceLine(p.sku, p.qty, p.unit_price) for p in po_lines)
    receipts: tuple[GoodsReceipt, ...] = (full_receipt,)
    existing: list[ExistingInvoice] = []
    invoice_po: PurchaseOrder | None = po
    invoice_vendor = vendor_id
    invoice_number = number
    total_override: Decimal | None = None
    file_hash = _digest("file", index, vendor_id, number)

    if label in (
        CaseLabel.PARTIAL_RECEIPT_BILLED_CORRECTLY,
        CaseLabel.PARTIAL_RECEIPT_OVERBILLED,
    ):
        half = {p.sku: Decimal(int(p.qty) // 2) for p in po_lines}
        receipts = (
            GoodsReceipt(
                f"GR-{index:05d}",
                po_number,
                tuple(ReceiptLine(sku, qty) for sku, qty in half.items()),
            ),
        )
        if label is CaseLabel.PARTIAL_RECEIPT_BILLED_CORRECTLY:
            invoice_lines = tuple(
                InvoiceLine(p.sku, half[p.sku], p.unit_price) for p in po_lines
            )
    elif label is CaseLabel.PRICE_VARIANCE:
        first = po_lines[0]
        bumped = quantize_money(first.unit_price * Decimal("1.10"))
        invoice_lines = (InvoiceLine(first.sku, first.qty, bumped), *invoice_lines[1:])
    elif label is CaseLabel.QTY_OVER_ORDERED:
        first = po_lines[0]
        invoice_lines = (
            InvoiceLine(first.sku, first.qty + Decimal(2), first.unit_price),
            *invoice_lines[1:],
        )
    elif label is CaseLabel.NO_RECEIPT:
        receipts = ()
    elif label is CaseLabel.NO_PO:
        invoice_po = None
    elif label is CaseLabel.VENDOR_MISMATCH:
        invoice_vendor = "V999"
    elif label is CaseLabel.TOTAL_MISMATCH:
        subtotal = sum((ln.qty * ln.unit_price for ln in invoice_lines), Decimal(0))
        total_override = quantize_money(subtotal * (1 + TAX_RATE)) + Decimal("1.00")
    elif label is CaseLabel.DUPLICATE_EXACT:
        existing.append(
            ExistingInvoice(
                f"existing-{index}", file_hash, vendor_id, normalize_invoice_number(number)
            )
        )
    elif label is CaseLabel.DUPLICATE_BUSINESS_KEY:
        existing.append(
            ExistingInvoice(
                f"existing-{index}",
                _digest("other-file", index),
                vendor_id,
                normalize_invoice_number(number),
            )
        )
        invoice_number = f"inv {index}"  # same invoice number, different formatting

    # Unrelated invoices already on file, so duplicate checks are not tested in isolation.
    for k in range(rng.randint(0, 3)):
        existing.append(
            ExistingInvoice(
                f"other-{index}-{k}",
                _digest("unrelated", index, k),
                f"V{rng.randint(10, 99):03d}",
                normalize_invoice_number(f"X-{rng.randint(1000, 9999)}"),
            )
        )

    invoice = _build_invoice(
        number=invoice_number,
        vendor_id=invoice_vendor,
        po_number=po_number,
        lines=invoice_lines,
        file_hash=file_hash,
        total_override=total_override,
    )
    return Scenario(label, invoice, invoice_po, receipts, tuple(existing))


def generate(seed: int, count: int) -> Iterator[Scenario]:
    """Yield `count` scenarios, cycling through every label so each is well represented."""
    rng = random.Random(seed)
    labels = list(CaseLabel)
    for index in range(count):
        yield generate_scenario(rng, index, labels[index % len(labels)])
