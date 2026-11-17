"""Policy: which findings block auto-approval. Hard violations override model confidence."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from invoiceguard.domain.duplicates import DuplicateResult
from invoiceguard.domain.matching import MatchResult
from invoiceguard.domain.models import Invoice
from invoiceguard.domain.validation import ValidationIssue


@dataclass(frozen=True)
class PolicyConfig:
    # Invoices above this total always go to a human, whatever the confidence.
    max_auto_total: Decimal = Decimal("10000")


@dataclass(frozen=True)
class PolicyResult:
    eligible: bool
    hard_violations: tuple[str, ...]


def apply_policy(
    invoice: Invoice,
    match: MatchResult,
    validation_issues: Iterable[ValidationIssue],
    duplicates: DuplicateResult,
    config: PolicyConfig = PolicyConfig(),
) -> PolicyResult:
    violations: list[str] = []

    for issue in validation_issues:
        violations.append(issue.code.value)
    for discrepancy in match.discrepancies:
        code = discrepancy.code.value
        if code not in violations:
            violations.append(code)
    if duplicates.exact:
        violations.append("DUPLICATE_EXACT")
    if duplicates.business_key:
        violations.append("DUPLICATE_BUSINESS_KEY")
    if invoice.total > config.max_auto_total:
        violations.append("HIGH_VALUE")

    return PolicyResult(eligible=not violations, hard_violations=tuple(violations))
