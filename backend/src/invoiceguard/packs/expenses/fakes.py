"""Deterministic and simulated extractors for expense claims. No network calls.

`truth_as_extraction` is what a perfect reader returns. `NoisyExpenseExtractor` corrupts a
seeded share of them with errors a real model can make, to show whether the controls catch
them. Results say nothing about how often a real model makes such errors; every record it
produces is labelled provider "simulated-noise".
"""

import hashlib
import random
from collections.abc import Mapping

from invoiceguard.extraction.client import ExtractionResponse, LlmUsage
from invoiceguard.extraction.schema import ExtractedValue
from invoiceguard.packs.expenses.generator import printed_values
from invoiceguard.packs.expenses.models import Expense
from invoiceguard.packs.expenses.schema import ExtractedExpense

ERROR_KINDS = (
    "total_digit",  # wrong digit in the total, quoted text that is not in the document
    "total_digit_real_quote",  # wrong total, but the quote is real text from the document
    "date_digit",  # wrong digit in the date, unverifiable quote
    "card_digit",  # wrong card digits, unverifiable quote
    "employee_digit",  # wrong employee id, unverifiable quote
    "merchant_swap",  # a different merchant, unverifiable quote
    "low_confidence",  # the model says it is unsure about one field
)


def truth_as_extraction(
    expense: Expense,
    template: str,
    *,
    confidence: float = 0.98,
    overrides: Mapping[str, ExtractedValue] | None = None,
) -> ExtractedExpense:
    printed = printed_values(expense, template)

    def field(name: str) -> ExtractedValue:
        value = printed[name] or None
        return ExtractedValue(
            value=value, confidence=confidence, page=1 if value else None, snippet=value
        )

    fields = {name: field(name) for name in printed}
    fields.update(overrides or {})
    return ExtractedExpense(**fields)


def _bump_digit(text: str, rng: random.Random) -> str:
    positions = [i for i, ch in enumerate(text) if ch.isdigit()]
    if not positions:
        return text + "1"
    i = rng.choice(positions)
    return text[:i] + str((int(text[i]) + rng.randint(1, 8)) % 10) + text[i + 1 :]


def corrupt(extracted: ExtractedExpense, kind: str, rng: random.Random) -> ExtractedExpense:
    data = extracted.model_copy(deep=True)

    def wrong(name: str, *, real_quote: bool = False) -> None:
        current = getattr(data, name)
        bad = _bump_digit(current.value, rng)
        setattr(
            data,
            name,
            ExtractedValue(
                value=bad,
                confidence=0.97,
                page=1,
                snippet=current.snippet if real_quote else bad,
            ),
        )

    if kind == "total_digit":
        wrong("total")
    elif kind == "total_digit_real_quote":
        wrong("total", real_quote=True)
    elif kind == "date_digit":
        wrong("expense_date")
    elif kind == "card_digit":
        wrong("card_last4")
    elif kind == "employee_digit":
        wrong("employee_id")
    elif kind == "merchant_swap":
        data.merchant = ExtractedValue(
            value="Unknown Vendor", confidence=0.96, page=1, snippet="Unknown Vendor"
        )
    elif kind == "low_confidence":
        data.tax = data.tax.model_copy(update={"confidence": 0.55})
    return data


class NoisyExpenseExtractor:
    """Perfect extraction with a seeded share of cases corrupted by one simulated error."""

    provider = "simulated-noise"
    model = "noisy-oracle-expenses"

    def __init__(self, truth: dict[str, tuple[Expense, str]], *, rate: float, seed: int = 7):
        self.truth = truth  # pdf hash -> (expense, template)
        self.rate = rate
        self.seed = seed
        self.applied: dict[str, str | None] = {}

    def extract(self, pdf: bytes, pack: str | None = None) -> ExtractionResponse:
        key = hashlib.sha256(pdf).hexdigest()
        expense, template = self.truth[key]
        rng = random.Random(f"{self.seed}:{key}")
        extracted = truth_as_extraction(expense, template)
        kind = rng.choice(ERROR_KINDS) if rng.random() < self.rate else None
        if kind:
            extracted = corrupt(extracted, kind, rng)
        self.applied[key] = kind
        return ExtractionResponse(
            extracted=extracted, usage=LlmUsage(self.provider, self.model, 0, 0, 0)
        )
