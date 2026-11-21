"""Seeded synthetic expense claims with ground truth, and their receipt PDFs.

All data is synthetic. Each scenario carries a label and the outcome a correct system should
reach, so decisions can be scored against known truth. Three receipt layouts differ in
labels, date format, amount format and how the card is printed; "slip" is held out of
development, as "ledger" is for invoices.
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from invoiceguard.domain.decision import Outcome
from invoiceguard.generator.pdf import format_indian, format_western
from invoiceguard.packs.expenses.models import (
    CardTransaction,
    CategoryRule,
    Employee,
    ExistingClaim,
    Expense,
)
from invoiceguard.packs.expenses.rules import normalize_merchant

TODAY = date(2026, 11, 20)  # the "submission date" every scenario is judged against
TEMPLATES = ("classic", "compact", "slip")
HELD_OUT_TEMPLATES = ("slip",)

CATEGORIES = (
    CategoryRule("meals", Decimal("3000")),
    CategoryRule("fuel", Decimal("5000")),
    CategoryRule("software", Decimal("20000")),
    CategoryRule("lodging", Decimal("15000")),
    CategoryRule("travel", Decimal("40000")),
    CategoryRule("gifts", Decimal("0"), blocked=True),
    CategoryRule("alcohol", Decimal("0"), blocked=True),
)
_MERCHANTS = (
    "Starbucks",
    "Uber India",
    "Cafe Coffee Day",
    "Indian Oil",
    "Zomato",
    "Taj Hotels",
    "Amazon Business",
    "Ola Cabs",
)


class ExpenseLabel(StrEnum):
    CLEAN = "CLEAN"
    OVER_CATEGORY_CAP = "OVER_CATEGORY_CAP"
    CATEGORY_BLOCKED = "CATEGORY_BLOCKED"
    NO_CARD_TRANSACTION = "NO_CARD_TRANSACTION"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    WRONG_CARD = "WRONG_CARD"
    UNKNOWN_EMPLOYEE = "UNKNOWN_EMPLOYEE"
    DATE_IN_FUTURE = "DATE_IN_FUTURE"
    CLAIM_TOO_OLD = "CLAIM_TOO_OLD"
    DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
    DUPLICATE_EXACT = "DUPLICATE_EXACT"
    HIGH_VALUE = "HIGH_VALUE"


# HIGH_VALUE is a clean claim that policy still sends to a person, so it is not "bad".
_GOOD = {ExpenseLabel.CLEAN, ExpenseLabel.HIGH_VALUE}
_EXPECTED_REASON = {
    ExpenseLabel.OVER_CATEGORY_CAP: "OVER_CATEGORY_CAP",
    ExpenseLabel.CATEGORY_BLOCKED: "CATEGORY_BLOCKED",
    ExpenseLabel.NO_CARD_TRANSACTION: "NO_CARD_TRANSACTION",
    ExpenseLabel.AMOUNT_MISMATCH: "AMOUNT_MISMATCH",
    ExpenseLabel.WRONG_CARD: "WRONG_CARD",
    ExpenseLabel.UNKNOWN_EMPLOYEE: "UNKNOWN_EMPLOYEE",
    ExpenseLabel.DATE_IN_FUTURE: "DATE_IN_FUTURE",
    ExpenseLabel.CLAIM_TOO_OLD: "CLAIM_TOO_OLD",
    ExpenseLabel.DUPLICATE_CLAIM: "DUPLICATE_CLAIM",
    ExpenseLabel.DUPLICATE_EXACT: "DUPLICATE_EXACT",
    ExpenseLabel.HIGH_VALUE: "HIGH_VALUE",
}


@dataclass(frozen=True)
class ExpenseScenario:
    label: ExpenseLabel
    expense: Expense
    employee: Employee | None
    categories: tuple[CategoryRule, ...]
    transactions: tuple[CardTransaction, ...]
    existing: tuple[ExistingClaim, ...]

    @property
    def expected_outcome(self) -> Outcome:
        if self.label is ExpenseLabel.CLEAN:
            return Outcome.AUTO_APPROVE
        if self.label is ExpenseLabel.DUPLICATE_EXACT:
            return Outcome.REJECT
        return Outcome.NEEDS_REVIEW

    @property
    def expected_reason(self) -> str | None:
        return _EXPECTED_REASON.get(self.label)

    @property
    def is_bad(self) -> bool:
        return self.label not in _GOOD


def _digest(*parts: object) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()


def _money(rng: random.Random, low: int, high: int) -> Decimal:
    return Decimal(rng.randint(low * 100, high * 100)) / 100


def generate_expense_scenario(
    rng: random.Random, index: int, label: ExpenseLabel
) -> ExpenseScenario:
    merchant = rng.choice(_MERCHANTS)
    card = f"{rng.randint(1000, 9999)}"
    employee_id = f"E-{index}"
    employee: Employee | None = Employee(employee_id, f"Employee {index}", card)
    category = rng.choice(("meals", "fuel"))
    total = _money(rng, 150, 2800)
    expense_date = TODAY - timedelta(days=rng.randint(1, 30))
    txn_amount_delta = Decimal(0)
    txn_card = card
    has_txn = True
    existing: list[ExistingClaim] = []
    file_hash = _digest("receipt", index)
    claim_card = card

    if label is ExpenseLabel.OVER_CATEGORY_CAP:
        category, total = "meals", _money(rng, 3200, 4800)
    elif label is ExpenseLabel.CATEGORY_BLOCKED:
        category, total = rng.choice(("gifts", "alcohol")), _money(rng, 500, 2000)
    elif label is ExpenseLabel.NO_CARD_TRANSACTION:
        has_txn = False
    elif label is ExpenseLabel.AMOUNT_MISMATCH:
        txn_amount_delta = Decimal("120.00")
    elif label is ExpenseLabel.WRONG_CARD:
        other = f"{(int(card) % 9000) + 1000 + 1}"
        claim_card = txn_card = other if other != card else "1234"
    elif label is ExpenseLabel.UNKNOWN_EMPLOYEE:
        employee = None
    elif label is ExpenseLabel.DATE_IN_FUTURE:
        expense_date = TODAY + timedelta(days=rng.randint(2, 20))
    elif label is ExpenseLabel.CLAIM_TOO_OLD:
        expense_date = TODAY - timedelta(days=rng.randint(90, 200))
    elif label is ExpenseLabel.HIGH_VALUE:
        category, total = "travel", _money(rng, 6000, 14000)
    elif label is ExpenseLabel.DUPLICATE_CLAIM:
        existing.append(
            ExistingClaim(
                f"existing-{index}",
                _digest("other-file", index),
                employee_id,
                normalize_merchant(merchant),
                expense_date,
                total,
            )
        )
    elif label is ExpenseLabel.DUPLICATE_EXACT:
        existing.append(
            ExistingClaim(
                f"existing-{index}",
                file_hash,
                employee_id,
                normalize_merchant(merchant),
                expense_date,
                total,
            )
        )

    # Unrelated claims already on file, so duplicate checks are not tested in isolation.
    for k in range(rng.randint(0, 3)):
        existing.append(
            ExistingClaim(
                f"other-{index}-{k}",
                _digest("unrelated", index, k),
                f"E-x{rng.randint(10, 99)}",
                normalize_merchant(rng.choice(_MERCHANTS)),
                TODAY - timedelta(days=rng.randint(1, 40)),
                _money(rng, 100, 900),
            )
        )

    transactions: list[CardTransaction] = []
    if has_txn:
        transactions.append(
            CardTransaction(
                f"txn-{index}",
                txn_card,
                f"{merchant.upper()} #{rng.randint(100, 999)}",
                expense_date + timedelta(days=rng.randint(0, 1)),
                total + txn_amount_delta,
                "INR",
            )
        )
    # Unrelated statement lines.
    for k in range(rng.randint(0, 2)):
        transactions.append(
            CardTransaction(
                f"noise-{index}-{k}",
                f"{rng.randint(1000, 9999)}",
                rng.choice(_MERCHANTS).upper(),
                TODAY - timedelta(days=rng.randint(1, 40)),
                _money(rng, 100, 900),
                "INR",
            )
        )

    expense = Expense(
        employee_id=employee_id,
        merchant=merchant,
        expense_date=expense_date,
        currency="INR",
        total=total,
        tax=(total * Decimal("0.05")).quantize(Decimal("0.01")),
        card_last4=claim_card,
        category=category,
        file_hash=file_hash,
    )
    return ExpenseScenario(
        label, expense, employee, CATEGORIES, tuple(transactions), tuple(existing)
    )


# ---------------------------------------------------------------- receipt rendering


@dataclass(frozen=True)
class Style:
    title: str
    employee: str
    merchant: str
    date: str
    total: str
    tax: str
    card: str
    category: str


STYLES = {
    "classic": Style(
        "EXPENSE CLAIM", "Employee ID:", "Merchant:", "Date:", "Total INR", "GST", "Card:",
        "Category:",
    ),
    "compact": Style(
        "Claim + receipt", "Emp:", "Vendor", "Dated", "Amount (Rs.)", "Tax", "Paid by", "Type",
    ),
    "slip": Style(
        "Reimbursement slip", "Staff No", "Paid to", "Purchased on", "Amount paid", "VAT/GST",
        "Paid with", "Expense type",
    ),
}


def printed_values(expense: Expense, template: str) -> dict[str, str]:
    """The values exactly as the template prints them."""
    last4 = expense.card_last4
    if template == "classic":
        date_text, card = expense.expense_date.isoformat(), f"XXXX XXXX XXXX {last4}"
        money = format_western
        category = expense.category.capitalize()
    elif template == "compact":
        date_text, card = expense.expense_date.strftime("%d %b %Y"), f"**** {last4}"
        money = format_indian
        category = expense.category.upper()
    else:
        date_text, card = expense.expense_date.strftime("%d/%m/%Y"), f"Card ending {last4}"

        def money(v: Decimal) -> str:
            return f"INR {format_western(v)}"

        category = expense.category
    return {
        "employee_id": expense.employee_id,
        "merchant": expense.merchant,
        "expense_date": date_text,
        "currency": "INR",
        "total": money(expense.total),
        "tax": money(expense.tax),
        "card_last4": card,
        "category": category,
    }


def render_expense_pdf(expense: Expense, template: str, injection: str | None = None) -> bytes:
    """Render one claim. `injection` adds hostile text inside the document for testing."""
    style = STYLES[template]
    values = printed_values(expense, template)
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4, invariant=1)
    canvas.setTitle(f"Expense {expense.employee_id}")
    _, height = A4
    left, y = 50, height - 60

    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(left, y, style.title)
    canvas.setFont("Helvetica", 10)
    y -= 30
    rows = [
        (style.employee, values["employee_id"]),
        (style.merchant, values["merchant"]),
        (style.date, values["expense_date"]),
        (style.card, values["card_last4"]),
        (style.category, values["category"]),
        ("Currency", values["currency"]),
        (style.tax, values["tax"]),
        (style.total, values["total"]),
    ]
    if template == "slip":
        rows.reverse()  # a different field order in this layout
    for label, value in rows:
        canvas.drawString(left, y, f"{label} {value}")
        y -= 18

    if injection:
        canvas.setFont("Helvetica", 7)
        canvas.drawString(left, 60, injection)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
