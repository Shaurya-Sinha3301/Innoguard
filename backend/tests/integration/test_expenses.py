"""The expenses pack running on the same core as invoices: database, extraction, approval and
posting, with no pack-specific branches in the core."""

import random
import re
from pathlib import Path

import pytest
import sqlalchemy as sa

import invoiceguard
from invoiceguard.db import models as m
from invoiceguard.extraction.fakes import FakeExtractor
from invoiceguard.extraction.service import register_upload
from invoiceguard.jobs.extract_job import JobOutcome, run_extraction_job
from invoiceguard.jobs.outbox import TOPIC_EXTRACT  # noqa: F401  (the same queue as invoices)
from invoiceguard.packs.expenses import service as expense_service
from invoiceguard.packs.expenses.fakes import truth_as_extraction
from invoiceguard.packs.expenses.generator import (
    TODAY,
    ExpenseLabel,
    generate_expense_scenario,
    render_expense_pdf,
)
from invoiceguard.workflow.posting import PostOutcome, post_invoice
from invoiceguard.workflow.service import approve_invoice

pytestmark = pytest.mark.usefixtures("clean_db")

_STATUS = {"AUTO_APPROVE": "AUTO_APPROVED", "NEEDS_REVIEW": "NEEDS_REVIEW", "REJECT": "REJECTED"}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    """Claims from documents are judged against a fixed submission day, so the synthetic
    dates stay valid however old this test run is."""
    monkeypatch.setattr("invoiceguard.packs.expenses.submitted_on", lambda row: TODAY)


def submit(session_factory, label, index):
    scenario = generate_expense_scenario(random.Random(index), index, label)
    with session_factory() as session:
        expense_service.seed_reference_data(session, scenario)
        row = expense_service.submit_expense(session, scenario.expense, submitted_on=TODAY)
        session.commit()
        return row.id, scenario


def reasons_of(session, case_id):
    return session.execute(
        sa.text(
            "SELECT payload->'reasons' FROM audit_events WHERE case_id = :c "
            "AND jsonb_typeof(payload->'reasons') = 'array' ORDER BY id DESC LIMIT 1"
        ),
        {"c": case_id},
    ).scalar_one_or_none()


def test_every_label_reaches_its_expected_state_in_the_database(session_factory):
    wrong = []
    for i, label in enumerate(ExpenseLabel):
        for k in range(4):
            case_id, scenario = submit(session_factory, label, 9000 + i * 10 + k)
            with session_factory() as session:
                row = session.get(m.Case, case_id)
                got = row.status
                if got != _STATUS[scenario.expected_outcome.value]:
                    wrong.append((label.value, got))
                elif scenario.expected_reason:
                    assert scenario.expected_reason in reasons_of(session, case_id), label
    assert wrong == []


def test_the_claim_is_stored_with_a_reference_counterparty_and_data(session_factory):
    case_id, scenario = submit(session_factory, ExpenseLabel.CLEAN, 1)
    with session_factory() as session:
        row = session.get(m.Case, case_id)
        assert row.pack_id == "expenses"
        assert row.vendor_id == scenario.expense.merchant
        assert row.total == scenario.expense.total
        assert row.data["employee_id"] == scenario.expense.employee_id
        assert row.data["card_last4"] == scenario.expense.card_last4


def test_a_document_goes_through_the_same_extraction_job_as_an_invoice(session_factory):
    scenario = generate_expense_scenario(random.Random(2), 2, ExpenseLabel.CLEAN)
    pdf = render_expense_pdf(scenario.expense, "classic")
    with session_factory() as session:
        expense_service.seed_reference_data(session, scenario)
        row = register_upload(
            session, pdf, filename="claim.pdf", actor="uploader", pack_id="expenses"
        )
        case_id = row.id
        session.commit()
    extractor = FakeExtractor(truth_as_extraction(scenario.expense, "classic"))
    outcome = run_extraction_job(session_factory, case_id, extractor, attempt=1, max_attempts=3)
    assert outcome is JobOutcome.DONE
    with session_factory() as session:
        row = session.get(m.Case, case_id)
        assert row.status == "AUTO_APPROVED" and row.pack_id == "expenses"
        fields = {f.field: f for f in session.scalars(sa.select(m.ExtractionField))}
        assert fields["total"].snippet and fields["card_last4"].page == 1
        assert row.data["category"] == scenario.expense.category


def test_a_wrongly_read_total_is_caught_by_the_card_statement(session_factory):
    """The model reads the total wrong but quotes real text, so the evidence check passes.
    The card statement disagrees, so a person still sees it."""
    scenario = generate_expense_scenario(random.Random(3), 3, ExpenseLabel.CLEAN)
    pdf = render_expense_pdf(scenario.expense, "classic")
    extracted = truth_as_extraction(scenario.expense, "classic")
    real_quote = extracted.total.snippet
    wrong = {"value": "9,999.00", "snippet": real_quote}
    extracted.total = extracted.total.model_copy(update=wrong)
    with session_factory() as session:
        expense_service.seed_reference_data(session, scenario)
        row = register_upload(session, pdf, filename="c.pdf", actor="u", pack_id="expenses")
        case_id = row.id
        session.commit()
    fake = FakeExtractor(extracted)
    run_extraction_job(session_factory, case_id, fake, attempt=1, max_attempts=3)
    with session_factory() as session:
        assert session.get(m.Case, case_id).status == "NEEDS_REVIEW"
        assert "AMOUNT_MISMATCH" in reasons_of(session, case_id)


def test_approval_and_posting_work_unchanged_for_an_expense(session_factory):
    case_id, _ = submit(session_factory, ExpenseLabel.OVER_CATEGORY_CAP, 5)
    with session_factory() as session:
        approve_invoice(
            session, case_id, reviewer="asha", expected_version=1, reason="manager approved"
        )
        session.commit()
    with session_factory() as session:
        result = post_invoice(session, case_id, actor="asha")
        session.commit()
    assert result.outcome is PostOutcome.POSTED
    with session_factory() as session:
        assert post_invoice(session, case_id, actor="asha").outcome is PostOutcome.ALREADY_PROCESSED


def test_the_same_claim_twice_is_flagged_as_a_possible_duplicate(session_factory):
    scenario = generate_expense_scenario(random.Random(6), 6, ExpenseLabel.CLEAN)
    with session_factory() as session:
        expense_service.seed_reference_data(session, scenario)
        first = expense_service.submit_expense(session, scenario.expense, submitted_on=TODAY)
        assert first.status == "AUTO_APPROVED"
        again = type(scenario.expense)(**{**scenario.expense.__dict__, "file_hash": "other-file"})
        second = expense_service.submit_expense(session, again, submitted_on=TODAY)
        session.commit()
        assert second.status == "NEEDS_REVIEW"
        assert "DUPLICATE_CLAIM" in reasons_of(session, second.id)


def test_expense_cases_do_not_disturb_invoice_duplicate_checks(session_factory):
    from invoiceguard.workflow import repo

    case_id, scenario = submit(session_factory, ExpenseLabel.CLEAN, 7)
    with session_factory() as session:
        found = repo.load_existing(
            session,
            exclude_id=case_id,
            file_hash="nothing",
            vendor_id=scenario.expense.merchant,
            number_norm="x",
        )
        assert found == ()


def test_the_core_never_names_a_pack():
    """The shared machinery talks to packs only through the Pack interface."""
    root = Path(invoiceguard.__file__).parent
    shared = [
        "workflow/service.py",
        "workflow/posting.py",
        "workflow/grants.py",
        "workflow/suggestions.py",
        "workflow/state_machine.py",
        "workflow/audit.py",
        "extraction/service.py",
        "extraction/cache.py",
        "jobs/extract_job.py",
        "jobs/outbox.py",
        "jobs/tasks.py",
        "jobs/documents.py",
    ]
    pattern = re.compile(r"""["']expenses["']|["']invoices["']""")
    offenders = {
        name: pattern.findall((root / name).read_text(encoding="utf-8")) for name in shared
    }
    assert {k: v for k, v in offenders.items() if v} == {}
