"""The expense rules: receipt against card statement against company policy.

Plain, tested code with no database. The same shape as invoice matching: a claim is checked
against what the company already knows, every finding is a named reason, and a hard finding
blocks auto-approval whatever the model's confidence was.

These thresholds and rules are assumptions for a synthetic company. They are written down in
the pack manifest and meant to be confirmed with the people who run the policy.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from invoiceguard.domain.decision import Decision, Signals, Thresholds, decide
from invoiceguard.domain.policy import PolicyResult
from invoiceguard.packs.expenses.models import (
    CardTransaction,
    CategoryRule,
    Employee,
    ExistingClaim,
    Expense,
    ExpensePolicy,
    ExpenseTolerances,
)


def normalize_merchant(name: str) -> str:
    """'STARBUCKS #1042' and 'Starbucks' compare equal: lower case, letters and digits only,
    store numbers dropped."""
    text = re.sub(r"#\s*\d+", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", text)


def same_merchant(receipt: str, statement: str) -> bool:
    a, b = normalize_merchant(receipt), normalize_merchant(statement)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


@dataclass(frozen=True)
class CardMatch:
    transaction: CardTransaction | None
    clean: bool  # found, and the amount and currency agree


@dataclass(frozen=True)
class ExpenseReconciliation:
    decision: Decision
    card: CardMatch
    hard_violations: tuple[str, ...]
    exact_duplicate: bool
    match_quality: Decimal


def find_card_transaction(
    expense: Expense,
    transactions: Iterable[CardTransaction],
    tolerances: ExpenseTolerances,
) -> CardMatch:
    """The statement line that pays for this receipt: same card, same merchant, close date.
    If several qualify, the one whose amount is nearest wins."""
    candidates = [
        t
        for t in transactions
        if t.card_last4 == expense.card_last4
        and same_merchant(expense.merchant, t.merchant)
        and abs((t.txn_date - expense.expense_date).days) <= tolerances.date_window_days
    ]
    if not candidates:
        return CardMatch(None, False)
    best = min(candidates, key=lambda t: abs(t.amount - expense.total))
    clean = (
        abs(best.amount - expense.total) <= tolerances.amount_abs
        and best.currency == expense.currency
    )
    return CardMatch(best, clean)


def reconcile_expense(
    expense: Expense,
    employee: Employee | None,
    category: CategoryRule | None,
    transactions: Iterable[CardTransaction],
    existing: Iterable[ExistingClaim],
    *,
    today: date,
    extraction_confidence: Decimal = Decimal(1),
    tolerances: ExpenseTolerances = ExpenseTolerances(),
    policy: ExpensePolicy = ExpensePolicy(),
    thresholds: Thresholds = Thresholds(),
) -> ExpenseReconciliation:
    transactions = list(transactions)
    violations: list[str] = []

    if employee is None:
        violations.append("UNKNOWN_EMPLOYEE")
    elif employee.card_last4 != expense.card_last4:
        violations.append("WRONG_CARD")

    if category is None:
        violations.append("UNKNOWN_CATEGORY")
    elif category.blocked:
        violations.append("CATEGORY_BLOCKED")
    elif expense.total > category.cap:
        violations.append("OVER_CATEGORY_CAP")

    if expense.expense_date > today:
        violations.append("DATE_IN_FUTURE")
    elif (today - expense.expense_date).days > tolerances.max_claim_age_days:
        violations.append("CLAIM_TOO_OLD")

    card = find_card_transaction(expense, transactions, tolerances)
    if card.transaction is None:
        violations.append("NO_CARD_TRANSACTION")
    elif not card.clean:
        violations.append(
            "CURRENCY_MISMATCH"
            if card.transaction.currency != expense.currency
            else "AMOUNT_MISMATCH"
        )

    merchant = normalize_merchant(expense.merchant)
    exact = False
    duplicate = False
    for claim in existing:
        if claim.file_hash == expense.file_hash:
            exact = True
        elif (
            claim.employee_id == expense.employee_id
            and claim.merchant_norm == merchant
            and claim.expense_date == expense.expense_date
            and claim.total == expense.total
        ):
            duplicate = True
    if duplicate:
        violations.append("DUPLICATE_CLAIM")

    if policy.max_auto_amount is not None and expense.total > policy.max_auto_amount:
        violations.append("HIGH_VALUE")

    match_quality = Decimal(1) if card.clean else Decimal(0)
    decision = decide(
        Signals(
            extraction_confidence=extraction_confidence,
            match_quality=match_quality,
            policy=PolicyResult(eligible=not violations, hard_violations=tuple(violations)),
            exact_duplicate=exact,
        ),
        thresholds,
    )
    return ExpenseReconciliation(decision, card, tuple(violations), exact, match_quality)
