"""Simulated extraction errors for safety testing.

Each error mimics something a real model can get wrong. Results from this extractor show
whether the controls catch such errors; they say nothing about how often a real model
makes them. Every record it produces is labelled provider "simulated-noise".
"""

import hashlib
import random

from invoiceguard.domain.models import Invoice
from invoiceguard.extraction.client import ExtractionResponse, LlmUsage
from invoiceguard.extraction.fakes import truth_as_extraction
from invoiceguard.extraction.schema import ExtractedInvoice, ExtractedValue

ERROR_KINDS = (
    "total_digit",  # wrong digit in the total, quoted as evidence that is not in the PDF
    "unit_price_digit",  # wrong digit in a line's unit price, with a truthful-looking snippet
    "dropped_line",  # a line item is missed
    "po_digit",  # wrong purchase order number
    "vendor_digit",  # wrong vendor code
    "low_confidence",  # the model reports it is unsure about one field
)


def _bump_digit(text: str, rng: random.Random) -> str:
    positions = [i for i, ch in enumerate(text) if ch.isdigit()]
    if not positions:
        return text + "1"
    i = rng.choice(positions)
    new = str((int(text[i]) + rng.randint(1, 8)) % 10)
    return text[:i] + new + text[i + 1 :]


def corrupt(extracted: ExtractedInvoice, kind: str, rng: random.Random) -> ExtractedInvoice:
    data = extracted.model_copy(deep=True)
    if kind == "total_digit" and data.total.value:
        wrong = _bump_digit(data.total.value, rng)
        data.total = ExtractedValue(value=wrong, confidence=0.97, page=1, snippet=wrong)
    elif kind == "unit_price_digit" and data.lines:
        line = rng.choice(data.lines)
        line.unit_price = _bump_digit(line.unit_price, rng)
    elif kind == "dropped_line" and len(data.lines) > 1:
        data.lines.pop(rng.randrange(len(data.lines)))
    elif kind == "po_digit" and data.po_number.value:
        wrong = _bump_digit(data.po_number.value, rng)
        data.po_number = ExtractedValue(value=wrong, confidence=0.96, page=1, snippet=wrong)
    elif kind == "vendor_digit" and data.vendor_id.value:
        wrong = _bump_digit(data.vendor_id.value, rng)
        data.vendor_id = ExtractedValue(value=wrong, confidence=0.96, page=1, snippet=wrong)
    elif kind == "low_confidence":
        data.subtotal = data.subtotal.model_copy(update={"confidence": 0.55})
    return data


class NoisyExtractor:
    """Perfect extraction with a seeded share of cases corrupted by one simulated error."""

    provider = "simulated-noise"
    model = "noisy-oracle"

    def __init__(self, truth: dict[str, tuple[Invoice, str]], *, rate: float, seed: int = 7):
        self.truth = truth  # pdf hash -> (invoice, template)
        self.rate = rate
        self.seed = seed
        self.applied: dict[str, str | None] = {}

    def extract(self, pdf: bytes) -> ExtractionResponse:
        key = hashlib.sha256(pdf).hexdigest()
        invoice, template = self.truth[key]
        rng = random.Random(f"{self.seed}:{key}")
        extracted = truth_as_extraction(invoice, template)
        kind = rng.choice(ERROR_KINDS) if rng.random() < self.rate else None
        if kind:
            extracted = corrupt(extracted, kind, rng)
        self.applied[key] = kind
        return ExtractionResponse(
            invoice=extracted,
            usage=LlmUsage(self.provider, self.model, 0, 0, 0),
        )
