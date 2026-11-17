"""Deterministic accounting checks on an invoice. The model's numbers are never trusted."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from invoiceguard.domain.models import Invoice, Tolerances
from invoiceguard.domain.money import within_amount


class ValidationCode(StrEnum):
    NO_LINES = "NO_LINES"
    LINE_SUM_MISMATCH = "LINE_SUM_MISMATCH"
    TOTAL_MISMATCH = "TOTAL_MISMATCH"


@dataclass(frozen=True)
class ValidationIssue:
    code: ValidationCode
    detail: str


def validate_invoice(
    invoice: Invoice, tolerances: Tolerances = Tolerances()
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    if not invoice.lines:
        return (ValidationIssue(ValidationCode.NO_LINES, "invoice has no lines"),)

    line_sum = sum((line.qty * line.unit_price for line in invoice.lines), Decimal(0))
    if not within_amount(line_sum, invoice.subtotal, tolerances.amount_abs):
        issues.append(
            ValidationIssue(
                ValidationCode.LINE_SUM_MISMATCH,
                f"lines sum to {line_sum}, subtotal is {invoice.subtotal}",
            )
        )
    if not within_amount(invoice.subtotal + invoice.tax, invoice.total, tolerances.amount_abs):
        issues.append(
            ValidationIssue(
                ValidationCode.TOTAL_MISMATCH,
                f"subtotal + tax is {invoice.subtotal + invoice.tax}, total is {invoice.total}",
            )
        )
    return tuple(issues)
