"""Write a generated scenario's master data (vendor, PO, receipts, existing invoices) to the DB."""

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.generator.cases import Scenario


def seed_master_data(session: Session, scenario: Scenario) -> None:
    po = scenario.po
    if po is not None:
        if session.get(m.Vendor, po.vendor_id) is None:
            session.add(m.Vendor(vendor_id=po.vendor_id, name=f"Vendor {po.vendor_id}"))
            session.flush()
        po_row = m.PurchaseOrder(
            po_number=po.po_number, vendor_id=po.vendor_id, currency=po.currency
        )
        po_row.lines = [
            m.PoLine(sku=line.sku, qty=line.qty, unit_price=line.unit_price) for line in po.lines
        ]
        session.add(po_row)
        session.flush()

        # Receipts only exist against a PO that exists.
        for receipt in scenario.receipts:
            receipt_row = m.GoodsReceipt(receipt_id=receipt.receipt_id, po_number=receipt.po_number)
            receipt_row.lines = [
                m.ReceiptLine(sku=line.sku, qty=line.qty) for line in receipt.lines
            ]
            session.add(receipt_row)

    for existing in scenario.existing_invoices:
        session.add(
            m.Case(
                id=uuid.uuid4(),
                invoice_number=existing.case_id,
                number_norm=existing.number_norm,
                vendor_id=existing.vendor_id,
                po_number=None,
                currency="INR",
                subtotal=Decimal(0),
                tax=Decimal(0),
                total=Decimal(0),
                file_hash=existing.file_hash,
                status="POSTED",
                version=1,
            )
        )
    session.flush()
