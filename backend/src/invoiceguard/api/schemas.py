import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LineIn(BaseModel):
    sku: str = Field(min_length=1)
    qty: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class InvoiceIn(BaseModel):
    invoice_number: str = Field(min_length=1)
    vendor_id: str = Field(min_length=1)
    po_number: str | None = None
    currency: str = Field(min_length=3, max_length=3)
    lines: list[LineIn] = Field(min_length=1)
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    file_hash: str = Field(min_length=1)


class DecisionIn(BaseModel):
    expected_version: int
    reason: str = Field(min_length=1)


class EditIn(DecisionIn):
    changes: dict[str, Any] = Field(min_length=1)


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    vendor_id: str
    po_number: str | None
    currency: str
    total: Decimal
    status: str
    version: int
    created_at: datetime


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_no: int
    sku: str
    qty: Decimal
    unit_price: Decimal


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_version: int
    amount: Decimal
    reviewer: str
    decision: str
    reason: str | None
    created_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    actor: str
    payload: dict[str, Any]
    duration_ms: int | None
    created_at: datetime


class InvoiceDetail(InvoiceOut):
    subtotal: Decimal
    tax: Decimal
    lines: list[LineOut]
    approvals: list[ApprovalOut]
    timeline: list[AuditOut]


class PostOut(BaseModel):
    outcome: str
    invoice_id: uuid.UUID
    idempotency_key: str
