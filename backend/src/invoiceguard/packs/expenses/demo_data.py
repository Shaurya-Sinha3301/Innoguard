"""Load synthetic demo expense claims into a running system.

For each claim it writes the employee, spending policy and card statement, renders the claim
PDF, stores a *simulated* extraction (provider "fake") so the pipeline runs with no API key,
and submits the PDF through the normal upload path. Nothing here is real data, and the
simulated records can never be mistaken for model output. Dates are relative to today, so
the claims are always recent enough to be valid.

    python -m invoiceguard.packs.expenses.demo_data --count 12
"""

import argparse
import dataclasses
import random
from datetime import date

from invoiceguard.db.session import SessionLocal
from invoiceguard.extraction.cache import record
from invoiceguard.extraction.fakes import FakeExtractor
from invoiceguard.jobs.documents import submit_document
from invoiceguard.packs.expenses import service
from invoiceguard.packs.expenses.fakes import truth_as_extraction
from invoiceguard.packs.expenses.generator import (
    TEMPLATES,
    ExpenseLabel,
    generate_expense_scenario,
    render_expense_pdf,
)

DEMO_LABELS = (
    ExpenseLabel.CLEAN,
    ExpenseLabel.OVER_CATEGORY_CAP,
    ExpenseLabel.CLEAN,
    ExpenseLabel.AMOUNT_MISMATCH,
    ExpenseLabel.NO_CARD_TRANSACTION,
    ExpenseLabel.CATEGORY_BLOCKED,
    ExpenseLabel.HIGH_VALUE,
    ExpenseLabel.WRONG_CARD,
)


def prepare(count: int, start_index: int) -> list[str]:
    done: list[str] = []
    today = date.today()
    for i in range(count):
        index = start_index + i
        label = DEMO_LABELS[i % len(DEMO_LABELS)]
        template = TEMPLATES[i % len(TEMPLATES)]
        scenario = generate_expense_scenario(random.Random(index), index, label, today)
        scenario = dataclasses.replace(scenario, existing=())  # the demo has no duplicates
        pdf = render_expense_pdf(scenario.expense, template)
        simulated = FakeExtractor(truth_as_extraction(scenario.expense, template)).extract(pdf)
        record(SessionLocal, pdf, simulated, simulated=True)
        with SessionLocal() as session:
            service.seed_reference_data(session, scenario)
            submit_document(
                session,
                pdf,
                filename=f"claim-{scenario.expense.employee_id}.pdf",
                actor="demo-loader",
                template_id=template,
                pack_id="expenses",
            )
            session.commit()
        done.append(f"{index}-{label.value.lower()}-{template}")
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description="Load synthetic demo expense claims")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--start-index", type=int, default=70000)
    args = parser.parse_args()
    for name in prepare(args.count, args.start_index):
        print(name)


if __name__ == "__main__":
    main()
