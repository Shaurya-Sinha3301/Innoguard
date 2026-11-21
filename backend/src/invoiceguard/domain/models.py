"""Plain domain types used by the reconciliation engine (no database dependency)."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PoLine:
    sku: str
    qty: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class PurchaseOrder:
    po_number: str
    vendor_id: str
    currency: str
    lines: tuple[PoLine, ...]


@dataclass(frozen=True)
class ReceiptLine:
    sku: str
    qty: Decimal


@dataclass(frozen=True)
class GoodsReceipt:
    receipt_id: str
    po_number: str
    lines: tuple[ReceiptLine, ...]


@dataclass(frozen=True)
class InvoiceLine:
    sku: str
    qty: Decimal
    unit_price: Decimal


@dataclass(frozen=True)
class Invoice:
    invoice_number: str
    vendor_id: str
    po_number: str | None
    currency: str
    lines: tuple[InvoiceLine, ...]
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    file_hash: str


@dataclass(frozen=True)
class ExistingInvoice:
    """An invoice already on file, used for duplicate detection."""

    case_id: str
    file_hash: str
    vendor_id: str
    number_norm: str


@dataclass(frozen=True)
class Tolerances:
    price_pct: Decimal = Decimal("2")
    qty_pct: Decimal = Decimal("0")
    amount_abs: Decimal = Decimal("0.01")
