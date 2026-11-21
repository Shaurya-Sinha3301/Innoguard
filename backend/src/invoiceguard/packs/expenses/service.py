"""Submit and seed expense claims without a document (demo data, tests, structured feeds).

Documents go through the normal upload and extraction path. This is the structured route,
the counterpart of `submit_invoice` for invoices.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from invoiceguard.db import models as m
from invoiceguard.packs.expenses import repo
from invoiceguard.packs.expenses.generator import ExpenseScenario
from invoiceguard.packs.expenses.models import Expense
from invoiceguard.workflow import audit
from invoiceguard.workflow.service import SYSTEM, apply_reconciliation
from invoiceguard.workflow.state_machine import InvoiceState as S


def submit_expense(
    session: Session,
    expense: Expense,
    *,
    submitted_on: date,
    actor: str = SYSTEM,
    trace_id: str | None = None,
    extraction_confidence: Decimal = Decimal(1),
) -> m.Case:
    row = m.Case(
        pack_id=repo.PACK_ID,
        file_hash=expense.file_hash,
        status=S.RECEIVED.value,
        version=1,
        trace_id=trace_id or uuid.uuid4().hex,
    )
    repo.write_expense(row, expense)
    row.data = {**row.data, "submitted_on": submitted_on.isoformat()}
    session.add(row)
    session.flush()
    audit.record(
        session,
        event_type="invoice.received",
        actor=actor,
        case_id=row.id,
        trace_id=row.trace_id,
        payload={"employee_id": expense.employee_id, "total": expense.total},
    )
    apply_reconciliation(session, row, actor=actor, extraction_confidence=extraction_confidence)
    return row


def seed_reference_data(session: Session, scenario: ExpenseScenario) -> None:
    """Write a scenario's employee, spending policy, card statement and earlier claims."""
    employee = scenario.employee
    if employee is not None and session.get(m.Employee, employee.employee_id) is None:
        session.add(
            m.Employee(
                employee_id=employee.employee_id, name=employee.name, card_last4=employee.card_last4
            )
        )
    for rule in scenario.categories:
        if session.get(m.ExpenseCategory, rule.category) is None:
            session.add(
                m.ExpenseCategory(category=rule.category, cap=rule.cap, blocked=rule.blocked)
            )
    for t in scenario.transactions:
        if session.get(m.CardTransaction, t.txn_id) is None:
            session.add(
                m.CardTransaction(
                    txn_id=t.txn_id,
                    card_last4=t.card_last4,
                    merchant=t.merchant,
                    txn_date=t.txn_date,
                    amount=t.amount,
                    currency=t.currency,
                )
            )
    for claim in scenario.existing:
        session.add(
            m.Case(
                id=uuid.uuid4(),
                pack_id=repo.PACK_ID,
                invoice_number=claim.case_id,
                vendor_id=claim.merchant_norm,
                currency="INR",
                total=claim.total,
                subtotal=claim.total,
                tax=Decimal(0),
                file_hash=claim.file_hash,
                status="POSTED",
                version=1,
                data={
                    "employee_id": claim.employee_id,
                    "expense_date": claim.expense_date.isoformat(),
                    "card_last4": "0000",
                    "category": "meals",
                },
            )
        )
    session.flush()
