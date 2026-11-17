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

    # Header fields are null for an uploaded document until extraction completes.
    id: uuid.UUID
    invoice_number: str | None
    vendor_id: str | None
    po_number: str | None
    currency: str | None
    total: Decimal | None
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


class LlmCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    tokens_per_second: Decimal | None
    cost_usd: Decimal


class InvoiceDetail(InvoiceOut):
    subtotal: Decimal | None
    tax: Decimal | None
    trace_id: str | None
    lines: list[LineOut]
    approvals: list[ApprovalOut]
    timeline: list[AuditOut]
    llm_calls: list[LlmCallOut]


class ExtractionFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
    value: str | None
    confidence: Decimal
    page: int | None
    snippet: str | None


class FailedJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: uuid.UUID | None
    task: str
    error: str
    attempts: int
    status: str
    created_at: datetime


class PostOut(BaseModel):
    outcome: str
    invoice_id: uuid.UUID
    idempotency_key: str
