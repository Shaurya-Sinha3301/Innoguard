"""Reliability of background work: outbox, dispatcher, retries, dead letter and replay."""

import random
import threading
import time
import uuid
from collections import Counter

import pytest
import sqlalchemy as sa

from invoiceguard.db import models as m
from invoiceguard.extraction.fakes import FakeExtractor, truth_as_extraction
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.pdf import render_invoice_pdf
from invoiceguard.generator.seed import seed_master_data
from invoiceguard.jobs.documents import replay_failed, submit_document
from invoiceguard.jobs.extract_job import JobOutcome, run_extraction_job
from invoiceguard.jobs.outbox import dispatch_pending
from invoiceguard.workflow.errors import IllegalTransition

pytestmark = pytest.mark.usefixtures("clean_db")


def upload(session_factory, index, label=CaseLabel.CLEAN):
    scenario = generate_scenario(random.Random(index), index, label)
    pdf = render_invoice_pdf(scenario.invoice, "classic")
    with session_factory() as session:
        seed_master_data(session, scenario)
        row = submit_document(session, pdf, filename=f"{index}.pdf", actor="uploader")
        session.commit()
        return row.id, truth_as_extraction(scenario.invoice, "classic")


def outbox_rows(session_factory):
    with session_factory() as session:
        return session.scalars(sa.select(m.OutboxMessage).order_by(m.OutboxMessage.id)).all()


def make_due(engine):
    """Skip the retry backoff so the next dispatch pass picks the rows up."""
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE outbox SET available_at = now() - interval '1 second'"))


def drive(session_factory, case_id, extractor, max_attempts=4):
    """Run the job the way the queue would: retry until it stops asking to."""
    for attempt in range(1, 20):
        outcome = run_extraction_job(
            session_factory, case_id, extractor, attempt=attempt, max_attempts=max_attempts
        )
        if outcome is not JobOutcome.RETRY:
            return outcome
    raise AssertionError("job never finished")


def status(session_factory, case_id):
    with session_factory() as session:
        return session.get(m.Case, case_id).status


def test_upload_writes_its_job_in_the_same_transaction(session_factory):
    case_id, _ = upload(session_factory, 1)
    rows = outbox_rows(session_factory)
    assert [(r.topic, r.payload, r.status) for r in rows] == [
        ("invoice.extract", {"case_id": str(case_id)}, "PENDING")
    ]


def test_a_rolled_back_upload_leaves_no_job(session_factory):
    scenario = generate_scenario(random.Random(2), 2, CaseLabel.CLEAN)
    pdf = render_invoice_pdf(scenario.invoice, "classic")
    with session_factory() as session:
        submit_document(session, pdf, filename="x.pdf", actor="u")
        session.rollback()
    assert outbox_rows(session_factory) == []


def test_broker_outage_keeps_jobs_until_it_recovers(session_factory, engine):
    ids = [upload(session_factory, i)[0] for i in range(3, 6)]

    def broker_down(topic, payload, message_id):
        raise ConnectionError("redis unavailable")

    down = dispatch_pending(session_factory, broker_down)
    assert (down.sent, down.failed) == (0, 3)
    assert {r.status for r in outbox_rows(session_factory)} == {"PENDING"}
    assert {r.attempts for r in outbox_rows(session_factory)} == {1}

    # Backoff: rows are not due again immediately.
    published: list[str] = []
    assert (
        dispatch_pending(session_factory, lambda t, p, i: published.append(p["case_id"])).sent
        == 0
    )

    make_due(engine)
    up = dispatch_pending(session_factory, lambda t, p, i: published.append(p["case_id"]))
    assert up.sent == 3
    assert sorted(published) == sorted(str(i) for i in ids)  # every job, exactly once
    assert dispatch_pending(session_factory, lambda t, p, i: published.append("again")).sent == 0


def test_concurrent_dispatchers_never_send_a_message_twice(session_factory):
    for i in range(10, 40):
        upload(session_factory, i)
    published: list[int] = []
    lock = threading.Lock()

    def slow_publish(topic, payload, message_id):
        time.sleep(0.01)
        with lock:
            published.append(message_id)

    threads = [
        threading.Thread(
            target=dispatch_pending, args=(session_factory, slow_publish), kwargs={"limit": 10}
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    while dispatch_pending(session_factory, slow_publish).sent:
        pass

    counts = Counter(published)
    assert len(counts) == 30
    assert set(counts.values()) == {1}


def test_transient_failures_are_retried_then_succeed(session_factory):
    case_id, truth = upload(session_factory, 50)
    extractor = FakeExtractor(truth, transient_failures=2)
    assert drive(session_factory, case_id, extractor) is JobOutcome.DONE
    assert extractor.calls == 3
    assert status(session_factory, case_id) == "AUTO_APPROVED"


def test_exhausted_retries_dead_letter_then_replay_succeeds(session_factory):
    case_id, truth = upload(session_factory, 51)
    flaky = FakeExtractor(truth, transient_failures=10)
    assert drive(session_factory, case_id, flaky, max_attempts=3) is JobOutcome.FAILED
    assert flaky.calls == 3
    assert status(session_factory, case_id) == "FAILED"
    with session_factory() as session:
        job = session.scalars(sa.select(m.FailedJob)).one()
        assert "retries exhausted after 3" in job.error

    with session_factory() as session:
        replay_failed(session, case_id, actor="ops")
        session.commit()
    assert status(session_factory, case_id) == "RECEIVED"
    assert [r.status for r in outbox_rows(session_factory)] == ["PENDING", "PENDING"]

    assert drive(session_factory, case_id, FakeExtractor(truth)) is JobOutcome.DONE
    assert status(session_factory, case_id) == "AUTO_APPROVED"
    with session_factory() as session:
        job = session.scalars(sa.select(m.FailedJob)).one()
        assert (job.status, job.replayed_at is not None) == ("REPLAYED", True)


def test_permanent_failure_is_not_retried(session_factory):
    case_id, _ = upload(session_factory, 52)
    extractor = FakeExtractor(permanent_error="the model declined this document")
    assert drive(session_factory, case_id, extractor) is JobOutcome.FAILED
    assert extractor.calls == 1


def test_only_failed_invoices_can_be_replayed(session_factory):
    case_id, _ = upload(session_factory, 53)
    with session_factory() as session, pytest.raises(IllegalTransition):
        replay_failed(session, case_id, actor="ops")


def test_duplicate_delivery_is_harmless(session_factory):
    case_id, truth = upload(session_factory, 54)
    assert drive(session_factory, case_id, FakeExtractor(truth)) is JobOutcome.DONE
    again = FakeExtractor(truth)
    assert drive(session_factory, case_id, again) is JobOutcome.SKIPPED
    assert again.calls == 0
    with session_factory() as session:
        assert session.scalar(sa.select(sa.func.count()).select_from(m.LlmCall)) == 1


def test_two_workers_on_the_same_job_complete_it_once(session_factory):
    case_id, truth = upload(session_factory, 55)
    barrier = threading.Barrier(2)
    outcomes: list[JobOutcome] = []

    class SlowFake(FakeExtractor):
        def extract(self, pdf, pack=None):
            time.sleep(0.05)
            return super().extract(pdf, pack)

    def work():
        barrier.wait()
        outcomes.append(
            run_extraction_job(
                session_factory, case_id, SlowFake(truth), attempt=1, max_attempts=3
            )
        )

    threads = [threading.Thread(target=work) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == sorted([JobOutcome.DONE, JobOutcome.SKIPPED])
    with session_factory() as session:
        calls = session.scalar(sa.select(sa.func.count()).select_from(m.LlmCall))
        fields = session.scalar(
            sa.select(sa.func.count())
            .select_from(m.ExtractionField)
            .where(m.ExtractionField.case_id == case_id)
        )
    assert calls == 1
    assert fields == len(truth.lines) + 7


def test_unknown_invoice_job_is_skipped(session_factory):
    outcome = run_extraction_job(
        session_factory, uuid.uuid4(), FakeExtractor(), attempt=1, max_attempts=3
    )
    assert outcome is JobOutcome.SKIPPED
