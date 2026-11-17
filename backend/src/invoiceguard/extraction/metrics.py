"""Cost, latency and throughput for every model call, stored per invoice."""

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from invoiceguard.db.models import LlmCall
from invoiceguard.extraction.client import LlmUsage

# USD per million tokens (input, output), from each provider's published price list
# (checked 2026-11-18; re-check before quoting costs). Claude Haiku 5.5 is priced higher
# above 100K prompt tokens, which invoices stay under.
PRICES_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "openai/gpt-oss-20b": (Decimal("0.075"), Decimal("0.30")),
    "openai/gpt-oss-120b": (Decimal("0.15"), Decimal("0.60")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-sonnet-5-5": (Decimal("2.00"), Decimal("10.00")),
    "claude-opus-5-5": (Decimal("4.00"), Decimal("20.00")),
}
_MILLION = Decimal(1_000_000)


def cost_usd(usage: LlmUsage) -> Decimal:
    prices = PRICES_PER_MTOK.get(usage.model)
    if prices is None:
        return Decimal(0)
    input_price, output_price = prices
    return (input_price * usage.input_tokens + output_price * usage.output_tokens) / _MILLION


def tokens_per_second(usage: LlmUsage) -> Decimal | None:
    if usage.latency_ms <= 0:
        return None
    return (Decimal(usage.output_tokens) * 1000 / Decimal(usage.latency_ms)).quantize(
        Decimal("0.0001")
    )


def record_llm_call(
    session: Session,
    *,
    invoice_id: uuid.UUID | None,
    step: str,
    usage: LlmUsage,
    trace_id: str | None,
) -> None:
    session.add(
        LlmCall(
            invoice_id=invoice_id,
            step=step,
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=usage.latency_ms,
            tokens_per_second=tokens_per_second(usage),
            cost_usd=cost_usd(usage).quantize(Decimal("0.000001")),
            trace_id=trace_id,
        )
    )
