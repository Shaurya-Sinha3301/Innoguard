"""Pack 2: employee expense claims checked against the card statement and spending policy.

This pack exists to show the core is generic: it plugs into the same extraction, approval,
posting, audit and agent machinery as the invoices pack and adds no branches to any of it.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from invoiceguard.domain.decision import Thresholds
from invoiceguard.extraction.records import NormalizedCase
from invoiceguard.packs.base import Manifest, PackReconciliation, load_manifest
from invoiceguard.packs.expenses import repo
from invoiceguard.packs.expenses.models import ExpensePolicy, ExpenseTolerances
from invoiceguard.packs.expenses.normalizer import normalize_expense
from invoiceguard.packs.expenses.rules import find_card_transaction, reconcile_expense
from invoiceguard.packs.expenses.schema import SYSTEM_PROMPT, USER_PROMPT, ExtractedExpense

LOOKUPS = ("employee", "category", "card_transactions")
MAX_ROWS = 50


def submitted_on(row: Any) -> date:
    """The day a claim was submitted, which its age is judged against."""
    data = row.data or {}
    if data.get("submitted_on"):
        return date.fromisoformat(data["submitted_on"])
    return row.created_at.date()


@dataclass(frozen=True)
class ExpensePack:
    id: str
    manifest: Manifest
    extraction_model: type[BaseModel] = ExtractedExpense
    system_prompt: str = SYSTEM_PROMPT
    user_prompt: str = USER_PROMPT
    lookup_names: tuple[str, ...] = LOOKUPS

    # What the rules use comes from the manifest, so there is one place to read and change it.
    def _thresholds(self) -> Thresholds:
        t = self.manifest.thresholds
        return Thresholds(t.min_extraction_confidence, t.min_match_quality)

    def _tolerances(self) -> ExpenseTolerances:
        t = self.manifest.tolerances
        return ExpenseTolerances(t.amount_abs, t.date_window_days, t.max_claim_age_days)

    def _policy(self) -> ExpensePolicy:
        return ExpensePolicy(self.manifest.thresholds.max_auto_amount)

    def normalize(self, extracted: Any, file_hash: str) -> NormalizedCase:
        return normalize_expense(extracted, file_hash)

    def apply_extracted(self, row: Any, value: Any) -> None:
        repo.write_expense(row, value)

    def _inputs(self, session: Session, row: Any):
        expense = repo.to_domain_expense(row)
        return (
            expense,
            repo.load_employee(session, expense.employee_id),
            repo.load_category(session, expense.category),
            repo.load_transactions(session, expense.card_last4),
            repo.load_existing(session, exclude_id=row.id, expense=expense),
        )

    def reconcile(self, session: Session, row: Any, confidence: Decimal) -> PackReconciliation:
        expense, employee, category, transactions, existing = self._inputs(session, row)
        result = reconcile_expense(
            expense,
            employee,
            category,
            transactions,
            existing,
            today=submitted_on(row),
            extraction_confidence=confidence,
            tolerances=self._tolerances(),
            policy=self._policy(),
            thresholds=self._thresholds(),
        )
        txn = result.card.transaction
        return PackReconciliation(
            decision=result.decision,
            matched_payload={
                "match_quality": result.match_quality,
                "discrepancies": list(result.hard_violations),
                "card_transaction": txn.txn_id if txn else None,
            },
        )

    def context(self, session: Session, row: Any) -> dict[str, Any]:
        """What the claim was checked against, for the case page."""
        if not (row.data or {}).get("employee_id"):
            return {}
        expense, employee, category, transactions, _ = self._inputs(session, row)
        match = find_card_transaction(expense, transactions, self._tolerances())
        txn = match.transaction
        return {
            "employee": employee
            and {
                "employee_id": employee.employee_id,
                "name": employee.name,
                "card_last4": employee.card_last4,
            },
            "category": category
            and {
                "category": category.category,
                "cap": str(category.cap),
                "blocked": category.blocked,
            },
            "card_transaction": txn
            and {
                "txn_id": txn.txn_id,
                "merchant": txn.merchant,
                "txn_date": txn.txn_date.isoformat(),
                "amount": str(txn.amount),
                "currency": txn.currency,
                "clean": match.clean,
            },
            "claim": {
                "employee_id": expense.employee_id,
                "merchant": expense.merchant,
                "expense_date": expense.expense_date.isoformat(),
                "card_last4": expense.card_last4,
                "category": expense.category,
                "total": str(expense.total),
                "currency": expense.currency,
            },
            "submitted_on": submitted_on(row).isoformat(),
            "max_auto_amount": str(self._policy().max_auto_amount),
        }

    def lookup(self, session: Session, name: str, key: str) -> Any:
        from invoiceguard.db import models as m
        from invoiceguard.mcp_server.tools import ToolInputError, _check_id

        if name not in LOOKUPS:
            raise ToolInputError(f"name must be one of: {', '.join(LOOKUPS)}")
        _check_id("key", key)
        if name == "employee":
            row = session.get(m.Employee, key)
            return row and {
                "employee_id": row.employee_id,
                "name": row.name,
                "card_last4": row.card_last4,
            }
        if name == "category":
            row = session.get(m.ExpenseCategory, key.lower())
            return row and {"category": row.category, "cap": str(row.cap), "blocked": row.blocked}
        rows = session.scalars(
            select(m.CardTransaction)
            .where(m.CardTransaction.card_last4 == key)
            .order_by(m.CardTransaction.txn_date.desc())
            .limit(MAX_ROWS)
        ).all()
        return [
            {
                "txn_id": r.txn_id,
                "merchant": r.merchant,
                "txn_date": r.txn_date.isoformat(),
                "amount": str(r.amount),
                "currency": r.currency,
            }
            for r in rows
        ]


_MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
PACK = ExpensePack(id=_MANIFEST.id, manifest=_MANIFEST)
