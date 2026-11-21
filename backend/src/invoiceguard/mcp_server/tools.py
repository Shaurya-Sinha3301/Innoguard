"""Read-only lookups exposed to agents through MCP.

Safety does not rely on the tool names: every call runs in a database transaction marked
READ ONLY with a short statement timeout, inputs are validated, and results are capped.
Release 1 has no write tool; posting stays in the application's posting service.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from invoiceguard.db import models as m

_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_HISTORY = 50
MAX_LINES = 200


class ToolInputError(ValueError):
    pass


def _check_id(name: str, value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ToolInputError(f"{name} must be 1-64 letters, digits, '.', '_' or '-'")
    return value


@contextmanager
def readonly_session(session_factory: sessionmaker) -> Iterator[Session]:
    """A session whose transaction the database itself refuses to let write."""
    with session_factory() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        session.execute(text("SET LOCAL statement_timeout = '2s'"))
        try:
            yield session
        finally:
            session.rollback()


def _money(value) -> str | None:
    return None if value is None else str(value)


def get_vendor(session: Session, vendor_id: str) -> dict[str, Any] | None:
    _check_id("vendor_id", vendor_id)
    row = session.get(m.Vendor, vendor_id)
    if row is None:
        return None
    aliases = session.scalars(
        select(m.VendorAlias.alias).where(m.VendorAlias.vendor_id == vendor_id)
    ).all()
    return {"vendor_id": row.vendor_id, "name": row.name, "aliases": list(aliases)}


def get_purchase_order(session: Session, po_number: str) -> dict[str, Any] | None:
    _check_id("po_number", po_number)
    row = session.get(m.PurchaseOrder, po_number)
    if row is None:
        return None
    return {
        "po_number": row.po_number,
        "vendor_id": row.vendor_id,
        "currency": row.currency,
        "lines": [
            {"sku": line.sku, "qty": _money(line.qty), "unit_price": _money(line.unit_price)}
            for line in row.lines[:MAX_LINES]
        ],
    }


def get_goods_receipts(session: Session, po_number: str) -> list[dict[str, Any]]:
    _check_id("po_number", po_number)
    rows = session.scalars(
        select(m.GoodsReceipt)
        .where(m.GoodsReceipt.po_number == po_number)
        .order_by(m.GoodsReceipt.received_at)
    ).all()
    return [
        {
            "receipt_id": row.receipt_id,
            "received_at": row.received_at.isoformat(),
            "lines": [{"sku": line.sku, "qty": _money(line.qty)} for line in row.lines[:MAX_LINES]],
        }
        for row in rows
    ]


def get_invoice_history(session: Session, vendor_id: str, limit: int = 20) -> list[dict[str, Any]]:
    _check_id("vendor_id", vendor_id)
    if not isinstance(limit, int) or limit < 1:
        raise ToolInputError("limit must be a positive integer")
    rows = session.scalars(
        select(m.Case)
        .where(m.Case.vendor_id == vendor_id)
        .order_by(m.Case.created_at.desc())
        .limit(min(limit, MAX_HISTORY))
    ).all()
    return [
        {
            "invoice_number": row.invoice_number,
            "po_number": row.po_number,
            "total": _money(row.total),
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
