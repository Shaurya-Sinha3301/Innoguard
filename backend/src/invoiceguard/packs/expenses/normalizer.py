"""Turn the model's strings into a typed Expense with plain, tested code.

Ambiguous input is refused rather than guessed: a date read the wrong way round that looks
plausible is worse than a field a person has to read.
"""

import re
from datetime import date, datetime
from decimal import Decimal

from invoiceguard.extraction.normalizer import (
    NormalizationError,
    normalize_currency,
    parse_amount,
)
from invoiceguard.extraction.records import FieldRecord, NormalizedCase
from invoiceguard.packs.expenses.models import Expense
from invoiceguard.packs.expenses.schema import ExtractedExpense

FIELDS = (
    "employee_id",
    "merchant",
    "expense_date",
    "currency",
    "total",
    "tax",
    "card_last4",
    "category",
)
REQUIRED = (
    "employee_id",
    "merchant",
    "expense_date",
    "currency",
    "total",
    "card_last4",
    "category",
)

# Day-first formats only ("03/04/2026" is 3 April, as on Indian receipts);
# month-first and two-digit years are refused because they cannot be told apart reliably.
_DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y")
_LAST4 = re.compile(r"(\d{4})\D*$")


def parse_date(raw: str) -> date:
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise NormalizationError(f"unrecognised date: {raw!r}")


def parse_card_last4(raw: str) -> str:
    match = _LAST4.search(raw.strip())
    if not match:
        raise NormalizationError(f"no card digits in {raw!r}")
    return match.group(1)


def _conf(value: float) -> Decimal:
    return Decimal(str(round(min(max(value, 0.0), 1.0), 4)))


def normalize_expense(extracted: ExtractedExpense, file_hash: str) -> NormalizedCase:
    issues: list[str] = []
    records: list[FieldRecord] = []
    values = {name: getattr(extracted, name) for name in FIELDS}

    for name, item in values.items():
        records.append(
            FieldRecord(name, item.value, _conf(item.confidence), item.page, item.snippet)
        )
        if name in REQUIRED and not (item.value or "").strip():
            issues.append(f"MISSING_FIELD:{name}")

    def attempt(name, parse):
        raw = values[name].value
        if not (raw or "").strip():
            return None
        try:
            return parse(raw)
        except NormalizationError:
            issues.append(f"UNPARSEABLE:{name}")
            return None

    expense_date = attempt("expense_date", parse_date)
    currency = attempt("currency", normalize_currency)
    total = attempt("total", parse_amount)
    card = attempt("card_last4", parse_card_last4)
    tax_raw = (values["tax"].value or "").strip()
    tax = attempt("tax", parse_amount) if tax_raw else Decimal(0)  # a receipt may show no tax

    confidence = min((r.confidence for r in records if r.value), default=Decimal(0))
    if issues:
        return NormalizedCase(None, confidence, records, issues)

    expense = Expense(
        employee_id=values["employee_id"].value.strip(),
        merchant=values["merchant"].value.strip(),
        expense_date=expense_date,
        currency=currency,
        total=total,
        tax=tax if tax is not None else Decimal(0),
        card_last4=card,
        category=values["category"].value.strip().lower(),
        file_hash=file_hash,
    )
    return NormalizedCase(expense, confidence, records, issues)
