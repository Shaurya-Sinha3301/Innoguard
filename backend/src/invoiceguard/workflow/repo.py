"""Load domain objects from the database for the reconciliation engine."""

import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.domain import models as d

# Invoices in these states count as billed quantity against a PO.
_BILLED_STATES = ("AUTO_APPROVED", "APPROVED", "POSTING", "POSTED")


def load_po(session: Session, po_number: str | None) -> d.PurchaseOrder | None:
    if po_number is None:
        return None
    row = session.get(m.PurchaseOrder, po_number)
    if row is None:
        return None
    return d.PurchaseOrder(
        row.po_number,
        row.vendor_id,
        row.currency,
        tuple(d.PoLine(line.sku, line.qty, line.unit_price) for line in row.lines),
    )


def load_receipts(session: Session, po_number: str | None) -> tuple[d.GoodsReceipt, ...]:
    if po_number is None:
        return ()
    rows = session.scalars(
        select(m.GoodsReceipt).where(m.GoodsReceipt.po_number == po_number)
    ).all()
    return tuple(
        d.GoodsReceipt(
            row.receipt_id,
            row.po_number,
            tuple(d.ReceiptLine(line.sku, line.qty) for line in row.lines),
        )
        for row in rows
    )


def load_existing(
    session: Session, *, exclude_id: uuid.UUID, file_hash: str, vendor_id: str, number_norm: str
) -> tuple[d.ExistingInvoice, ...]:
    """Invoices that could be duplicates of this one (same file, or same vendor and number)."""
    rows = session.execute(
        select(m.Invoice.id, m.Invoice.file_hash, m.Invoice.vendor_id, m.Invoice.number_norm).where(
            m.Invoice.id != exclude_id,
            or_(
                m.Invoice.file_hash == file_hash,
                (m.Invoice.vendor_id == vendor_id) & (m.Invoice.number_norm == number_norm),
            ),
        )
    ).all()
    return tuple(
        d.ExistingInvoice(str(r.id), r.file_hash, r.vendor_id, r.number_norm) for r in rows
    )


def previously_invoiced(
    session: Session, *, po_number: str | None, exclude_id: uuid.UUID
) -> dict[str, Decimal]:
    """Quantities already billed per SKU on other accepted invoices against the same PO."""
    if po_number is None:
        return {}
    rows = session.execute(
        select(m.InvoiceLine.sku, func.sum(m.InvoiceLine.qty))
        .join(m.Invoice, m.Invoice.id == m.InvoiceLine.invoice_id)
        .where(
            m.Invoice.po_number == po_number,
            m.Invoice.id != exclude_id,
            m.Invoice.status.in_(_BILLED_STATES),
        )
        .group_by(m.InvoiceLine.sku)
    ).all()
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for sku, qty in rows:
        totals[sku] = qty
    return dict(totals)


def to_domain_invoice(row: m.Invoice) -> d.Invoice:
    return d.Invoice(
        invoice_number=row.invoice_number,
        vendor_id=row.vendor_id,
        po_number=row.po_number,
        currency=row.currency,
        lines=tuple(
            d.InvoiceLine(line.sku, line.qty, line.unit_price)
            for line in sorted(row.lines, key=lambda x: x.line_no)
        ),
        subtotal=row.subtotal,
        tax=row.tax,
        total=row.total,
        file_hash=row.file_hash,
    )
