"""Turn the model's strings into typed values with plain, tested code.

Ambiguous input is refused rather than guessed: a wrong amount that looks right is worse
than a field a human has to read.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from invoiceguard.domain.models import Invoice, InvoiceLine
from invoiceguard.extraction.schema import ExtractedInvoice, ExtractedValue

_CURRENCY_TOKENS = re.compile(r"(?i)\b(?:INR|USD|EUR|RS)\b\.?|[₹$€]")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_CURRENCIES = {
    "INR": "INR",
    "RS": "INR",
    "RS.": "INR",
    "₹": "INR",
    "USD": "USD",
    "$": "USD",
    "EUR": "EUR",
    "€": "EUR",
}

REQUIRED = ("invoice_number", "vendor_id", "currency", "subtotal", "tax", "total")
HEADER_FIELDS = ("invoice_number", "vendor_id", "po_number", "currency", "subtotal", "tax", "total")


class NormalizationError(ValueError):
    pass


def parse_amount(raw: str) -> Decimal:
    """Read '1,23,456.50', 'INR 1,234.00' or 'Rs. 99' as a Decimal.

    A comma after the last dot (European style, '1.234,50') is ambiguous here, so it is
    refused instead of guessed.
    """
    text = _CURRENCY_TOKENS.sub("", raw).replace(" ", "").strip()
    if "," in text and "." in text and text.rfind(",") > text.rfind("."):
        raise NormalizationError(f"ambiguous decimal separator in {raw!r}")
    text = text.replace(",", "")
    if not _NUMBER.fullmatch(text):
        raise NormalizationError(f"not a number: {raw!r}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise NormalizationError(f"not a number: {raw!r}") from exc


def normalize_currency(raw: str) -> str:
    key = raw.strip().upper()
    if key in _CURRENCIES:
        return _CURRENCIES[key]
    if re.fullmatch(r"[A-Z]{3}", key):
        return key
    raise NormalizationError(f"unknown currency: {raw!r}")


@dataclass(frozen=True)
class FieldRecord:
    field: str
    value: str | None
    confidence: Decimal
    page: int | None
    snippet: str | None


@dataclass
class Normalized:
    invoice: Invoice | None
    confidence: Decimal
    fields: list[FieldRecord]
    issues: list[str] = field(default_factory=list)


def _conf(value: float) -> Decimal:
    return Decimal(str(round(min(max(value, 0.0), 1.0), 4)))


def normalize(extracted: ExtractedInvoice, file_hash: str) -> Normalized:
    issues: list[str] = []
    records: list[FieldRecord] = []
    values: dict[str, ExtractedValue] = {name: getattr(extracted, name) for name in HEADER_FIELDS}

    for name, item in values.items():
        records.append(
            FieldRecord(name, item.value, _conf(item.confidence), item.page, item.snippet)
        )
        if name in REQUIRED and not (item.value or "").strip():
            issues.append(f"MISSING_FIELD:{name}")

    parsed: dict[str, Decimal] = {}
    for name in ("subtotal", "tax", "total"):
        raw = values[name].value
        if raw:
            try:
                parsed[name] = parse_amount(raw)
            except NormalizationError:
                issues.append(f"UNPARSEABLE:{name}")

    currency = None
    if values["currency"].value:
        try:
            currency = normalize_currency(values["currency"].value)
        except NormalizationError:
            issues.append("UNPARSEABLE:currency")

    lines: list[InvoiceLine] = []
    if not extracted.lines:
        issues.append("MISSING_FIELD:lines")
    for i, line in enumerate(extracted.lines, start=1):
        records.append(
            FieldRecord(
                f"line[{i}]",
                f"{line.sku} | {line.qty} | {line.unit_price}",
                _conf(line.confidence),
                line.page,
                line.snippet,
            )
        )
        try:
            lines.append(
                InvoiceLine(line.sku.strip(), parse_amount(line.qty), parse_amount(line.unit_price))
            )
        except NormalizationError:
            issues.append(f"UNPARSEABLE:line[{i}]")

    confidence = min((r.confidence for r in records if r.value), default=Decimal(0))
    if issues:
        return Normalized(None, confidence, records, issues)

    invoice = Invoice(
        invoice_number=values["invoice_number"].value.strip(),
        vendor_id=values["vendor_id"].value.strip(),
        po_number=(values["po_number"].value or "").strip() or None,
        currency=currency,
        lines=tuple(lines),
        subtotal=parsed["subtotal"],
        tax=parsed["tax"],
        total=parsed["total"],
        file_hash=file_hash,
    )
    return Normalized(invoice, confidence, records, issues)
