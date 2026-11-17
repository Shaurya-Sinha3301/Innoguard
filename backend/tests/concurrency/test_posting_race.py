"""The headline reliability test: several workers post the same approved invoice at once.

Exactly one posting must succeed, every other worker must get an already-processed result,
and the audit log must record both outcomes. The test runs against real Postgres, because
row locks and unique constraints are what make this safe.
"""

import random
import threading
from collections import Counter

import pytest
import sqlalchemy as sa

from invoiceguard.db import models as m
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.seed import seed_master_data
from invoiceguard.workflow import posting
from invoiceguard.workflow.posting import PostOutcome, post_invoice
from invoiceguard.workflow.service import submit_invoice

pytestmark = pytest.mark.usefixtures("clean_db")

ROUNDS = 12


def _seed_approved_invoice(session_factory, index):
    scenario = generate_scenario(random.Random(index), index, CaseLabel.CLEAN)
    with session_factory() as session:
        seed_master_data(session, scenario)
        row = submit_invoice(session, scenario.invoice)
        session.commit()
        assert row.status == "AUTO_APPROVED"
        return row.id


def _race(session_factory, invoice_id, workers):
    barrier = threading.Barrier(workers)
    outcomes: list[PostOutcome] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def work(name):
        with session_factory() as session:
            barrier.wait()  # release every worker at the same moment
            try:
                result = post_invoice(session, invoice_id, actor=name)
                session.commit()
                with lock:
                    outcomes.append(result.outcome)
            except BaseException as exc:  # reported by the assertions below
                session.rollback()
                with lock:
                    errors.append(exc)

    threads = [threading.Thread(target=work, args=(f"worker-{i}",)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return outcomes, errors


def test_unique_constraint_alone_still_prevents_a_double_post(session_factory, monkeypatch):
    """Defence in depth: with the row lock switched off, the database unique constraint on
    the idempotency key must still allow exactly one posting."""
    monkeypatch.setattr(
        posting, "lock_invoice", lambda session, invoice_id: session.get(m.Invoice, invoice_id)
    )
    workers = 6
    for round_no in range(ROUNDS):
        invoice_id = _seed_approved_invoice(session_factory, 5000 + round_no)

        outcomes, errors = _race(session_factory, invoice_id, workers)

        assert errors == []
        assert Counter(outcomes) == {
            PostOutcome.POSTED: 1,
            PostOutcome.ALREADY_PROCESSED: workers - 1,
        }
        with session_factory() as session:
            postings = session.scalar(
                sa.select(sa.func.count())
                .select_from(m.Posting)
                .where(m.Posting.invoice_id == invoice_id)
            )
        assert postings == 1


@pytest.mark.parametrize("workers", [2, 6])
def test_concurrent_posts_of_one_invoice_post_exactly_once(session_factory, workers):
    for round_no in range(ROUNDS):
        invoice_id = _seed_approved_invoice(session_factory, 1000 + workers * 100 + round_no)

        outcomes, errors = _race(session_factory, invoice_id, workers)

        assert errors == []
        counts = Counter(outcomes)
        assert counts[PostOutcome.POSTED] == 1
        assert counts[PostOutcome.ALREADY_PROCESSED] == workers - 1

        with session_factory() as session:
            postings = session.scalar(
                sa.select(sa.func.count())
                .select_from(m.Posting)
                .where(m.Posting.invoice_id == invoice_id)
            )
            status = session.get(m.Invoice, invoice_id).status
            events = Counter(
                session.scalars(
                    sa.select(m.AuditEvent.event_type).where(m.AuditEvent.invoice_id == invoice_id)
                ).all()
            )
        assert postings == 1
        assert status == "POSTED"
        assert events["posting.posted"] == 1
        assert events["posting.already_processed"] == workers - 1
