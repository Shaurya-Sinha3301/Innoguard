"""Reconciliation pipeline: validate, match, check duplicates, apply policy, decide."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from invoiceguard.domain.decision import Decision, Signals, Thresholds, decide
from invoiceguard.domain.duplicates import (
    DuplicateResult,
    find_duplicates,
    normalize_invoice_number,
)
from invoiceguard.domain.matching import MatchResult, three_way_match
from invoiceguard.domain.models import (
    ExistingInvoice,
    GoodsReceipt,
    Invoice,
    PurchaseOrder,
    Tolerances,
)
from invoiceguard.domain.policy import PolicyConfig, PolicyResult, apply_policy
from invoiceguard.domain.validation import ValidationIssue, validate_invoice


@dataclass(frozen=True)
class Reconciliation:
    decision: Decision
    match: MatchResult
    validation_issues: tuple[ValidationIssue, ...]
    duplicates: DuplicateResult
    policy: PolicyResult


def reconcile(
    invoice: Invoice,
    po: PurchaseOrder | None,
    receipts: Iterable[GoodsReceipt],
    existing: Iterable[ExistingInvoice] = (),
    *,
    extraction_confidence: Decimal = Decimal(1),
    previously_invoiced: Mapping[str, Decimal] | None = None,
    tolerances: Tolerances = Tolerances(),
    policy_config: PolicyConfig = PolicyConfig(),
    thresholds: Thresholds = Thresholds(),
) -> Reconciliation:
    issues = validate_invoice(invoice, tolerances)
    match = three_way_match(invoice, po, receipts, tolerances, previously_invoiced)
    duplicates = find_duplicates(
        invoice_file_hash=invoice.file_hash,
        vendor_id=invoice.vendor_id,
        number_norm=normalize_invoice_number(invoice.invoice_number),
        existing=existing,
    )
    policy = apply_policy(invoice, match, issues, duplicates, policy_config)
    decision = decide(
        Signals(
            extraction_confidence=extraction_confidence,
            match_quality=match.match_quality,
            policy=policy,
            exact_duplicate=duplicates.exact,
        ),
        thresholds,
    )
    return Reconciliation(decision, match, issues, duplicates, policy)
