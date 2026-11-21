"""Deterministic extractors for tests, local demos and CI. They make no network calls."""

from collections.abc import Mapping

from pydantic import BaseModel

from invoiceguard.domain.models import Invoice
from invoiceguard.extraction.client import (
    ExtractionError,
    ExtractionResponse,
    LlmUsage,
    TransientExtractionError,
)
from invoiceguard.extraction.schema import ExtractedInvoice, ExtractedLine, ExtractedValue
from invoiceguard.generator.pdf import _qty, printed_money, printed_values


def truth_as_extraction(
    invoice: Invoice,
    template: str,
    *,
    confidence: float = 0.98,
    overrides: Mapping[str, ExtractedValue] | None = None,
) -> ExtractedInvoice:
    """What a perfect extractor would return for this rendered invoice."""
    printed = printed_values(invoice, template)

    def header(field: str) -> ExtractedValue:
        value = printed[field] or None
        return ExtractedValue(
            value=value, confidence=confidence, page=1 if value else None, snippet=value
        )

    fields = {
        name: header(name)
        for name in (
            "invoice_number",
            "vendor_id",
            "po_number",
            "currency",
            "subtotal",
            "tax",
            "total",
        )
    }
    fields.update(overrides or {})
    lines = [
        ExtractedLine(
            sku=line.sku,
            qty=_qty(line.qty),
            unit_price=printed_money(line.unit_price, template),
            confidence=confidence,
            page=1,
            snippet=line.sku,
        )
        for line in invoice.lines
    ]
    return ExtractedInvoice(**fields, lines=lines)


class FakeExtractor:
    """Returns a fixed extraction, or fails a set number of times first."""

    provider = "fake"
    model = "fake-extractor"

    def __init__(
        self,
        result: BaseModel | None = None,
        *,
        transient_failures: int = 0,
        permanent_error: str | None = None,
    ) -> None:
        self.result = result
        self.transient_failures = transient_failures
        self.permanent_error = permanent_error
        self.calls = 0

    def extract(self, pdf: bytes, pack: str | None = None) -> ExtractionResponse:
        self.calls += 1
        if self.calls <= self.transient_failures:
            raise TransientExtractionError("simulated rate limit")
        if self.permanent_error or self.result is None:
            raise ExtractionError(self.permanent_error or "no result configured")
        return ExtractionResponse(
            extracted=self.result,
            usage=LlmUsage(
                provider=self.provider,
                model=self.model,
                input_tokens=1200,
                output_tokens=300,
                latency_ms=150,
            ),
        )
