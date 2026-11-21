"""Posting grants: a person releases one approved case, once, for a short time."""

import random
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa

from invoiceguard.db import models as m
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.seed import seed_master_data
from invoiceguard.workflow import grants
from invoiceguard.workflow.errors import GrantInvalid, NotApproved
from invoiceguard.workflow.posting import PostOutcome
from invoiceguard.workflow.service import edit_invoice, submit_invoice

pytestmark = pytest.mark.usefixtures("clean_db")


def make_case(session_factory, label, index):
    scenario = generate_scenario(random.Random(index), index, label)
    with session_factory() as session:
        seed_master_data(session, scenario)
        row = submit_invoice(session, scenario.invoice)
        session.commit()
        return row.id


def issue(session_factory, case_id, ttl=15):
    with session_factory() as session:
        grant = grants.issue_grant(session, case_id, issued_by="asha", ttl_minutes=ttl)
        session.commit()
        return grant.id


def test_a_case_waiting_for_review_cannot_be_released(session_factory):
    case_id = make_case(session_factory, CaseLabel.PRICE_VARIANCE, 5)
    with session_factory() as session, pytest.raises(NotApproved):
        grants.issue_grant(session, case_id, issued_by="asha")


def test_a_grant_posts_once_and_is_then_spent(session_factory):
    case_id = make_case(session_factory, CaseLabel.CLEAN, 1)
    grant = issue(session_factory, case_id)
    with session_factory() as session:
        result = grants.post_with_grant(session, case_id, grant, actor="mcp:bot")
        session.commit()
    assert result.outcome is PostOutcome.POSTED
    with session_factory() as session, pytest.raises(GrantInvalid, match="already been used"):
        grants.post_with_grant(session, case_id, grant, actor="mcp:bot")
    with session_factory() as session:
        spent = session.get(m.PostingGrant, grant)
        assert spent.used_by == "mcp:bot" and spent.used_at is not None


def test_an_expired_grant_is_refused(session_factory):
    case_id = make_case(session_factory, CaseLabel.CLEAN, 1)
    grant = issue(session_factory, case_id)
    with session_factory() as session:
        session.execute(
            sa.update(m.PostingGrant).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()
    with session_factory() as session, pytest.raises(GrantInvalid, match="expired"):
        grants.post_with_grant(session, case_id, grant, actor="mcp:bot")


def test_a_grant_does_not_survive_a_change_to_the_case(session_factory):
    case_id = make_case(session_factory, CaseLabel.CLEAN, 1)
    grant = issue(session_factory, case_id)
    with session_factory() as session:
        row = session.get(m.Case, case_id)
        edit_invoice(
            session,
            case_id,
            actor="asha",
            expected_version=row.version,
            reason="corrected total",
            total=row.total + Decimal("1"),
        )
        session.commit()
    with session_factory() as session, pytest.raises(GrantInvalid, match="changed"):
        grants.post_with_grant(session, case_id, grant, actor="mcp:bot")


def test_a_grant_is_for_one_case_only(session_factory):
    first = make_case(session_factory, CaseLabel.CLEAN, 1)
    second = make_case(session_factory, CaseLabel.CLEAN, 2)
    grant = issue(session_factory, first)
    with session_factory() as session, pytest.raises(GrantInvalid, match="no such grant"):
        grants.post_with_grant(session, second, grant, actor="mcp:bot")


@pytest.mark.parametrize("ttl", [0, 61])
def test_the_lifetime_of_a_grant_is_bounded(session_factory, ttl):
    case_id = make_case(session_factory, CaseLabel.CLEAN, 1)
    with session_factory() as session, pytest.raises(ValueError):
        grants.issue_grant(session, case_id, issued_by="asha", ttl_minutes=ttl)


def test_a_refusal_and_a_use_are_both_audited(session_factory):
    case_id = make_case(session_factory, CaseLabel.CLEAN, 1)
    grant = issue(session_factory, case_id)
    with session_factory() as session:
        grants.post_with_grant(session, case_id, grant, actor="mcp:bot")
        session.commit()
    with session_factory() as session:
        try:
            grants.post_with_grant(session, case_id, grant, actor="mcp:bot")
        except GrantInvalid:
            session.commit()
    with session_factory() as session:
        events = session.scalars(
            sa.select(m.AuditEvent.event_type)
            .where(m.AuditEvent.event_type.like("grant.%"))
            .order_by(m.AuditEvent.id)
        ).all()
    assert events == ["grant.issued", "grant.used", "grant.refused"]


def test_two_agents_racing_on_one_grant_post_exactly_once(session_factory):
    case_id = make_case(session_factory, CaseLabel.CLEAN, 1)
    grant = issue(session_factory, case_id)
    workers = 5
    barrier = threading.Barrier(workers)
    results: list[str] = []
    lock = threading.Lock()

    def work(name):
        with session_factory() as session:
            barrier.wait()
            try:
                outcome = grants.post_with_grant(session, case_id, grant, actor=name).outcome
                session.commit()
                label = outcome.value
            except GrantInvalid:
                session.commit()
                label = "REFUSED"
            with lock:
                results.append(label)

    threads = [threading.Thread(target=work, args=(f"mcp:bot{i}",)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("POSTED") == 1
    assert results.count("REFUSED") == workers - 1
    with session_factory() as session:
        assert session.scalar(sa.select(sa.func.count()).select_from(m.Posting)) == 1
