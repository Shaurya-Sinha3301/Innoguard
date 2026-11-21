"""Plain domain types for expense claims (no database dependency)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Expense:
    """One receipt claimed by an employee, as read from the claim document."""

    employee_id: str
    merchant: str
    expense_date: date
    currency: str
    total: Decimal
    tax: Decimal
    card_last4: str
    category: str
    file_hash: str


@dataclass(frozen=True)
class Employee:
    employee_id: str
    name: str
    card_last4: str


@dataclass(frozen=True)
class CategoryRule:
    """The company's rule for one spending category."""

    category: str
    cap: Decimal  # the most one claim in this category may be
    blocked: bool = False  # never reimbursable (for example gifts, alcohol)


@dataclass(frozen=True)
class CardTransaction:
    """A line on the company card statement."""

    txn_id: str
    card_last4: str
    merchant: str  # the statement descriptor, which rarely matches the receipt exactly
    txn_date: date
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class ExistingClaim:
    """A claim already on file, used for duplicate detection."""

    case_id: str
    file_hash: str
    employee_id: str
    merchant_norm: str
    expense_date: date
    total: Decimal


@dataclass(frozen=True)
class ExpenseTolerances:
    amount_abs: Decimal = Decimal("0.01")  # receipt versus card statement
    date_window_days: int = 3  # receipt date versus statement date
    max_claim_age_days: int = 60  # how old a claim may be when it is submitted


@dataclass(frozen=True)
class ExpensePolicy:
    max_auto_amount: Decimal = Decimal("5000")  # larger claims always go to a person
