import random

import pytest

from invoiceguard import reporting
from invoiceguard.extraction.cache import DbCachedExtractor, record
from invoiceguard.extraction.client import ExtractionError
from invoiceguard.extraction.fakes import FakeExtractor, truth_as_extraction
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.pdf import render_invoice_pdf
from invoiceguard.generator.seed import seed_master_data
from invoiceguard.workflow.service import approve_invoice, submit_invoice

pytestmark = pytest.mark.usefixtures("clean_db")


def test_summary_counts_decisions_exceptions_and_review_time(session_factory):
    labels = [CaseLabel.CLEAN, CaseLabel.CLEAN, CaseLabel.PRICE_VARIANCE, CaseLabel.NO_RECEIPT]
    ids = []
    with session_factory() as session:
        for index, label in enumerate(labels, start=1):
            scenario = generate_scenario(random.Random(index), index, label)
            seed_master_data(session, scenario)
            ids.append(submit_invoice(session, scenario.invoice).id)
        session.commit()
    with session_factory() as session:
        approve_invoice(session, ids[2], reviewer="asha", expected_version=1, reason="ok")
        session.commit()

    with session_factory() as session:
        data = reporting.summary(session)

    assert data["decisions"]["decided"] == 4
    assert data["decisions"]["auto_approved"] == 2
    assert data["decisions"]["needs_review"] == 2
    assert str(data["decisions"]["straight_through_rate"]) == "0.5000"
    reasons = {e["reason"]: e["count"] for e in data["exceptions"]}
    assert reasons["PRICE_VARIANCE"] == 1
    assert reasons["NO_RECEIPT"] == 1
    assert data["human_workload"]["reviewed"] == 1
    assert data["human_workload"]["median_review_seconds"] is not None
    assert data["operations"] == {"open_failed_jobs": 0, "outbox_pending": 0}


def test_database_recordings_replay_across_sessions(session_factory):
    scenario = generate_scenario(random.Random(5), 5, CaseLabel.CLEAN)
    pdf = render_invoice_pdf(scenario.invoice, "ledger")
    truth = FakeExtractor(truth_as_extraction(scenario.invoice, "ledger")).extract(pdf)

    replay_only = DbCachedExtractor(session_factory)
    with pytest.raises(ExtractionError):
        replay_only.extract(pdf)

    record(session_factory, pdf, truth, simulated=True)
    assert replay_only.extract(pdf).invoice == truth.invoice

    live = FakeExtractor(truth.invoice)
    other_pdf = render_invoice_pdf(scenario.invoice, "classic")
    DbCachedExtractor(session_factory, live).extract(other_pdf)
    DbCachedExtractor(session_factory, live).extract(other_pdf)
    assert live.calls == 1  # second call was served from the recording
