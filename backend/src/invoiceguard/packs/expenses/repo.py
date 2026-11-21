"""Load expense domain objects from the database, and write a claim onto a case row."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.packs.expenses import models as d
from invoiceguard.packs.expenses.rules import normalize_merchant

PACK_ID = "expenses"


def load_employee(session: Session, employee_id: str) -> d.Employee | None:
    row = session.get(m.Employee, employee_id)
    return None if row is None else d.Employee(row.employee_id, row.name, row.card_last4)


def load_category(session: Session, category: str) -> d.CategoryRule | None:
    row = session.get(m.ExpenseCategory, category)
    return None if row is None else d.CategoryRule(row.category, row.cap, row.blocked)


def load_transactions(session: Session, card_last4: str) -> tuple[d.CardTransaction, ...]:
    rows = session.scalars(
        select(m.CardTransaction).where(m.CardTransaction.card_last4 == card_last4)
    ).all()
    return tuple(
        d.CardTransaction(r.txn_id, r.card_last4, r.merchant, r.txn_date, r.amount, r.currency)
        for r in rows
    )


def load_existing(
    session: Session, *, exclude_id: uuid.UUID, expense: d.Expense
) -> tuple[d.ExistingClaim, ...]:
    """Claims that could duplicate this one: the same file, or the same person, merchant,
    day and amount."""
    rows = session.execute(
        select(m.Case).where(
            m.Case.id != exclude_id,
            m.Case.pack_id == PACK_ID,
            or_(
                m.Case.file_hash == expense.file_hash,
                (m.Case.data["employee_id"].astext == expense.employee_id)
                & (m.Case.data["expense_date"].astext == expense.expense_date.isoformat())
                & (m.Case.total == expense.total),
            ),
        )
    ).scalars()
    return tuple(
        d.ExistingClaim(
            str(r.id),
            r.file_hash,
            r.data.get("employee_id", ""),
            normalize_merchant(r.vendor_id or ""),
            date.fromisoformat(r.data["expense_date"]),
            r.total,
        )
        for r in rows
        if r.data.get("expense_date") and r.total is not None
    )


def to_domain_expense(row: m.Case) -> d.Expense:
    data = row.data
    return d.Expense(
        employee_id=data["employee_id"],
        merchant=row.vendor_id,
        expense_date=date.fromisoformat(data["expense_date"]),
        currency=row.currency,
        total=row.total,
        tax=row.tax if row.tax is not None else Decimal(0),
        card_last4=data["card_last4"],
        category=data["category"],
        file_hash=row.file_hash,
    )


def write_expense(row: m.Case, expense: d.Expense) -> None:
    """Put a typed claim on the case row. The shared columns carry what every pack has (a
    reference, the counterparty, the amount); the rest lives in `data`."""
    row.invoice_number = f"{expense.employee_id} {expense.expense_date.isoformat()}"
    row.vendor_id = expense.merchant
    row.currency = expense.currency
    row.total = expense.total
    row.subtotal = expense.total - expense.tax
    row.tax = expense.tax
    row.data = {
        "employee_id": expense.employee_id,
        "expense_date": expense.expense_date.isoformat(),
        "card_last4": expense.card_last4,
        "category": expense.category,
    }
