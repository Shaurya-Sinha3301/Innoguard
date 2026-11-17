"""SQLAlchemy models. Currency and invoice_type columns exist now so Release 2 extends them."""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MONEY = sa.Numeric(18, 4)


class Base(DeclarativeBase):
    pass


def _now() -> sa.sql.elements.TextClause:
    return sa.text("now()")


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    name: Mapped[str] = mapped_column(sa.Text)
    tax_id: Mapped[str | None] = mapped_column(sa.Text)


class VendorAlias(Base):
    __tablename__ = "vendor_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[str] = mapped_column(sa.ForeignKey("vendors.vendor_id"))
    alias: Mapped[str] = mapped_column(sa.Text, unique=True)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    vendor_id: Mapped[str] = mapped_column(sa.ForeignKey("vendors.vendor_id"))
    currency: Mapped[str] = mapped_column(sa.String(3))

    lines: Mapped[list["PoLine"]] = relationship(cascade="all, delete-orphan")


class PoLine(Base):
    __tablename__ = "po_lines"
    __table_args__ = (sa.UniqueConstraint("po_number", "sku", name="uq_po_lines_po_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(sa.ForeignKey("purchase_orders.po_number"))
    sku: Mapped[str] = mapped_column(sa.Text)
    qty: Mapped[Decimal] = mapped_column(MONEY)
    unit_price: Mapped[Decimal] = mapped_column(MONEY)


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"

    receipt_id: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    po_number: Mapped[str] = mapped_column(sa.ForeignKey("purchase_orders.po_number"))
    received_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )

    lines: Mapped[list["ReceiptLine"]] = relationship(cascade="all, delete-orphan")


class ReceiptLine(Base):
    __tablename__ = "receipt_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[str] = mapped_column(sa.ForeignKey("goods_receipts.receipt_id"))
    sku: Mapped[str] = mapped_column(sa.Text)
    qty: Mapped[Decimal] = mapped_column(MONEY)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        sa.Index("ix_invoices_file_hash", "file_hash"),
        sa.Index("ix_invoices_vendor_number_norm", "vendor_id", "number_norm"),
        sa.Index("ix_invoices_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    # Header fields are empty for an uploaded document until extraction fills them.
    invoice_number: Mapped[str | None] = mapped_column(sa.Text)
    number_norm: Mapped[str | None] = mapped_column(sa.Text)
    vendor_id: Mapped[str | None] = mapped_column(sa.Text)
    po_number: Mapped[str | None] = mapped_column(sa.Text)
    currency: Mapped[str | None] = mapped_column(sa.String(3))
    invoice_type: Mapped[str] = mapped_column(sa.Text, server_default="INVOICE")
    subtotal: Mapped[Decimal | None] = mapped_column(MONEY)
    tax: Mapped[Decimal | None] = mapped_column(MONEY)
    total: Mapped[Decimal | None] = mapped_column(MONEY)
    file_hash: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(sa.Text, server_default="RECEIVED")
    version: Mapped[int] = mapped_column(server_default="1")
    trace_id: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )

    lines: Mapped[list["InvoiceLine"]] = relationship(cascade="all, delete-orphan")


class Document(Base):
    """The uploaded file. Stored in Postgres for Release 1; object storage is Release 2."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("invoices.id"), unique=True)
    filename: Mapped[str] = mapped_column(sa.Text)
    content_type: Mapped[str] = mapped_column(sa.Text)
    template_id: Mapped[str | None] = mapped_column(sa.Text)
    data: Mapped[bytes] = mapped_column(sa.LargeBinary)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("invoices.id"))
    line_no: Mapped[int]
    sku: Mapped[str] = mapped_column(sa.Text)
    qty: Mapped[Decimal] = mapped_column(MONEY)
    unit_price: Mapped[Decimal] = mapped_column(MONEY)


class ExtractionField(Base):
    """One extracted value with its confidence and where in the document it came from."""

    __tablename__ = "extraction_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("invoices.id"))
    field: Mapped[str] = mapped_column(sa.Text)
    value: Mapped[str | None] = mapped_column(sa.Text)
    confidence: Mapped[Decimal] = mapped_column(sa.Numeric(5, 4))
    page: Mapped[int | None]
    snippet: Mapped[str | None] = mapped_column(sa.Text)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("invoices.id"))
    invoice_version: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(MONEY)
    reviewer: Mapped[str] = mapped_column(sa.Text)
    decision: Mapped[str] = mapped_column(sa.Text)
    reason: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )


class Posting(Base):
    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(sa.Text, unique=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("invoices.id"))
    invoice_version: Mapped[int]
    status: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )


class OutboxMessage(Base):
    __tablename__ = "outbox"
    __table_args__ = (sa.Index("ix_outbox_status_available", "status", "available_at"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    topic: Mapped[str] = mapped_column(sa.Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(sa.Text, server_default="PENDING")
    attempts: Mapped[int] = mapped_column(server_default="0")
    available_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )


class FailedJob(Base):
    __tablename__ = "failed_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("invoices.id"))
    task: Mapped[str] = mapped_column(sa.Text)
    error: Mapped[str] = mapped_column(sa.Text)
    attempts: Mapped[int]
    status: Mapped[str] = mapped_column(sa.Text, server_default="FAILED")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )
    replayed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class LlmCall(Base):
    """Cost and latency record for every model call."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("invoices.id"))
    step: Mapped[str] = mapped_column(sa.Text)
    provider: Mapped[str] = mapped_column(sa.Text)
    model: Mapped[str] = mapped_column(sa.Text)
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    latency_ms: Mapped[int]
    tokens_per_second: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 4))
    cost_usd: Mapped[Decimal] = mapped_column(sa.Numeric(12, 6))
    trace_id: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )


class ExtractionRecording(Base):
    """A recorded model response keyed by file hash, shared by every service in replay mode."""

    __tablename__ = "extraction_recordings"

    file_hash: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    simulated: Mapped[bool] = mapped_column(server_default=sa.false())
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )


class AuditEvent(Base):
    """Append-only. A database trigger rejects UPDATE, DELETE and TRUNCATE."""

    __tablename__ = "audit_events"
    __table_args__ = (
        sa.Index("ix_audit_events_invoice", "invoice_id", "id"),
        sa.Index("ix_audit_events_trace", "trace_id"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    trace_id: Mapped[str | None] = mapped_column(sa.Text)
    event_type: Mapped[str] = mapped_column(sa.Text)
    actor: Mapped[str] = mapped_column(sa.Text)
    payload: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    duration_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=_now()
    )
