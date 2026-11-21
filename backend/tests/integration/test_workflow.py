import random
from decimal import Decimal

import pytest
import sqlalchemy as sa

from invoiceguard.db import models as m
from invoiceguard.domain.decision import Outcome
from invoiceguard.generator.cases import CaseLabel, generate, generate_scenario
from invoiceguard.generator.seed import seed_master_data
from invoiceguard.workflow import audit
from invoiceguard.workflow.errors import IllegalTransition, NotApproved, StaleVersion
from invoiceguard.workflow.posting import PostOutcome, post_invoice
from invoiceguard.workflow.service import (
    approve_invoice,
    edit_invoice,
    reject_invoice,
    submit_invoice,
)

pytestmark = pytest.mark.usefixtures("clean_db")

_STATUS_FOR = {
    Outcome.AUTO_APPROVE: "AUTO_APPROVED",
    Outcome.NEEDS_REVIEW: "NEEDS_REVIEW",
    Outcome.REJECT: "REJECTED",
}


def submit(session_factory, label, index):
    scenario = generate_scenario(random.Random(index), index, label)
    with session_factory() as session:
        seed_master_data(session, scenario)
        row = submit_invoice(session, scenario.invoice)
        session.commit()
        return row.id, scenario


def event_types(session, case_id):
    return session.scalars(
        sa.select(m.AuditEvent.event_type)
        .where(m.AuditEvent.case_id == case_id)
        .order_by(m.AuditEvent.id)
    ).all()


def test_database_pipeline_reaches_the_expected_state_for_every_case(session_factory):
    with session_factory() as session:
        scenarios = list(generate(seed=3, count=36))
        for scenario in scenarios:
            seed_master_data(session, scenario)
        rows = [(s, submit_invoice(session, s.invoice)) for s in scenarios]
        session.commit()
        wrong = [
            (s.label.value, row.status)
            for s, row in rows
            if row.status != _STATUS_FOR[s.expected_outcome]
        ]
    assert wrong == []


def test_clean_invoice_is_auto_approved_with_an_audit_trail(session_factory):
    case_id, _ = submit(session_factory, CaseLabel.CLEAN, 1)
    with session_factory() as session:
        row = session.get(m.Case, case_id)
        assert row.status == "AUTO_APPROVED"
        approval = session.scalars(sa.select(m.Approval)).one()
        assert (approval.decision, approval.reviewer, approval.case_version) == (
            "AUTO_APPROVE",
            "system",
            1,
        )
        events = event_types(session, case_id)
    assert events[0] == "invoice.received"
    assert events.count("invoice.state_changed") == 3  # VALIDATED, MATCHED, AUTO_APPROVED
    assert events[-1] == "approval.recorded"


def test_unapproved_invoice_cannot_be_posted(session_factory):
    case_id, _ = submit(session_factory, CaseLabel.PRICE_VARIANCE, 2)
    with session_factory() as session, pytest.raises(NotApproved):
        post_invoice(session, case_id, actor="worker")


def test_reviewer_approval_then_post_then_repeat_is_idempotent(session_factory):
    case_id, _ = submit(session_factory, CaseLabel.PRICE_VARIANCE, 3)
    with session_factory() as session:
        approve_invoice(
            session, case_id, reviewer="asha", expected_version=1, reason="price confirmed"
        )
        first = post_invoice(session, case_id, actor="worker")
        session.commit()
    with session_factory() as session:
        second = post_invoice(session, case_id, actor="worker")
        session.commit()
        postings = session.scalar(sa.select(sa.func.count()).select_from(m.Posting))
        status = session.get(m.Case, case_id).status
    assert first.outcome is PostOutcome.POSTED
    assert second.outcome is PostOutcome.ALREADY_PROCESSED
    assert first.idempotency_key == second.idempotency_key
    assert postings == 1
    assert status == "POSTED"


def test_stale_version_decision_is_refused(session_factory):
    case_id, _ = submit(session_factory, CaseLabel.PRICE_VARIANCE, 4)
    with session_factory() as session, pytest.raises(StaleVersion):
        approve_invoice(
            session, case_id, reviewer="asha", expected_version=7, reason="looks fine"
        )


def test_a_reason_is_required(session_factory):
    case_id, _ = submit(session_factory, CaseLabel.PRICE_VARIANCE, 5)
    with session_factory() as session, pytest.raises(ValueError):
        approve_invoice(session, case_id, reviewer="asha", expected_version=1, reason="  ")


def test_rejected_invoice_cannot_be_approved_afterwards(session_factory):
    case_id, _ = submit(session_factory, CaseLabel.PRICE_VARIANCE, 6)
    with session_factory() as session:
        reject_invoice(
            session, case_id, reviewer="asha", expected_version=1, reason="wrong price"
        )
        session.commit()
    with session_factory() as session, pytest.raises(IllegalTransition):
        approve_invoice(
            session, case_id, reviewer="asha", expected_version=1, reason="changed my mind"
        )


def test_material_edit_voids_the_approval_and_blocks_posting(session_factory):
    case_id, _ = submit(session_factory, CaseLabel.CLEAN, 7)  # auto-approved at version 1
    with session_factory() as session:
        row = edit_invoice(
            session,
            case_id,
            actor="asha",
            expected_version=1,
            reason="supplier sent a corrected total",
            total=Decimal("999.00"),
        )
        session.commit()
        assert (row.status, row.version) == ("NEEDS_REVIEW", 2)
        events = event_types(session, case_id)
    assert "approval.voided" in events
    with session_factory() as session, pytest.raises(NotApproved):
        post_invoice(session, case_id, actor="worker")


def test_edit_rejects_fields_that_are_not_editable(session_factory):
    case_id, _ = submit(session_factory, CaseLabel.CLEAN, 8)
    with session_factory() as session, pytest.raises(ValueError):
        edit_invoice(
            session, case_id, actor="asha", expected_version=1, reason="x", file_hash="abc"
        )


def test_failed_post_rolls_back_and_a_retry_posts_exactly_once(session_factory, monkeypatch):
    case_id, _ = submit(session_factory, CaseLabel.CLEAN, 9)
    real_record = audit.record

    def failing_record(session, **kwargs):
        if kwargs["event_type"] == "posting.posted":
            raise RuntimeError("simulated crash while posting")
        return real_record(session, **kwargs)

    monkeypatch.setattr(audit, "record", failing_record)
    with session_factory() as session:
        with pytest.raises(RuntimeError):
            post_invoice(session, case_id, actor="worker")
        session.rollback()
    monkeypatch.setattr(audit, "record", real_record)

    with session_factory() as session:
        assert session.scalar(sa.select(sa.func.count()).select_from(m.Posting)) == 0
        assert session.get(m.Case, case_id).status == "AUTO_APPROVED"
        result = post_invoice(session, case_id, actor="worker")
        session.commit()
        assert result.outcome is PostOutcome.POSTED
        assert session.scalar(sa.select(sa.func.count()).select_from(m.Posting)) == 1
