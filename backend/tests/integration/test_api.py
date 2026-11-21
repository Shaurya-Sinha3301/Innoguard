import random

import pytest
from fastapi.testclient import TestClient

from invoiceguard.api import deps, ratelimit
from invoiceguard.api.main import app
from invoiceguard.api.schemas import InvoiceIn
from invoiceguard.config import settings
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.seed import seed_master_data

pytestmark = pytest.mark.usefixtures("clean_db")

ASHA = {"X-API-Key": "key-asha"}
RAVI = {"X-API-Key": "key-ravi"}


class MemoryCounter:
    def __init__(self):
        self.counts = {}

    def incr(self, key, ttl_seconds):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


@pytest.fixture
def client(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "api_keys", "key-asha:asha,key-ravi:ravi")
    monkeypatch.setattr(ratelimit, "counter", MemoryCounter())

    def override_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[deps.get_session] = override_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def payload_for(session_factory, label, index):
    scenario = generate_scenario(random.Random(index), index, label)
    with session_factory() as session:
        seed_master_data(session, scenario)
        session.commit()
    inv = scenario.invoice
    return {
        "invoice_number": inv.invoice_number,
        "vendor_id": inv.vendor_id,
        "po_number": inv.po_number,
        "currency": inv.currency,
        "lines": [
            {"sku": ln.sku, "qty": str(ln.qty), "unit_price": str(ln.unit_price)}
            for ln in inv.lines
        ],
        "subtotal": str(inv.subtotal),
        "tax": str(inv.tax),
        "total": str(inv.total),
        "file_hash": inv.file_hash,
    }


def test_me_returns_the_reviewer_for_the_key(client):
    assert client.get("/me", headers=RAVI).json()["name"] == "ravi"
    assert client.get("/me").status_code == 401


def test_missing_or_wrong_key_is_rejected(client):
    assert client.get("/invoices").status_code == 401
    assert client.get("/invoices", headers={"X-API-Key": "nope"}).status_code == 401


def test_submit_review_post_flow_records_the_key_holder_as_reviewer(client, session_factory):
    body = payload_for(session_factory, CaseLabel.PRICE_VARIANCE, 1)

    created = client.post("/invoices", json=body, headers=ASHA)
    assert created.status_code == 201
    invoice = created.json()
    assert (invoice["status"], invoice["version"]) == ("NEEDS_REVIEW", 1)
    path = f"/invoices/{invoice['id']}"

    # Posting before approval is refused.
    assert client.post(f"{path}/post", headers=ASHA).status_code == 409

    approved = client.post(
        f"{path}/approve",
        json={"expected_version": 1, "reason": "price confirmed by phone"},
        headers=RAVI,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    first = client.post(f"{path}/post", headers=ASHA).json()
    second = client.post(f"{path}/post", headers=ASHA).json()
    assert first["outcome"] == "POSTED"
    assert second["outcome"] == "ALREADY_PROCESSED"
    assert first["idempotency_key"] == second["idempotency_key"]

    detail = client.get(path, headers=ASHA).json()
    assert detail["status"] == "POSTED"
    reviewers = {(a["decision"], a["reviewer"]) for a in detail["approvals"]}
    assert ("APPROVE", "ravi") in reviewers
    events = [e["event_type"] for e in detail["timeline"]]
    assert "posting.posted" in events and "posting.already_processed" in events


def test_stale_version_and_unknown_invoice(client, session_factory):
    body = payload_for(session_factory, CaseLabel.PRICE_VARIANCE, 2)
    invoice = client.post("/invoices", json=body, headers=ASHA).json()

    stale = client.post(
        f"/invoices/{invoice['id']}/approve",
        json={"expected_version": 9, "reason": "ok"},
        headers=ASHA,
    )
    assert stale.status_code == 409

    missing = client.post(
        "/invoices/00000000-0000-0000-0000-000000000000/approve",
        json={"expected_version": 1, "reason": "ok"},
        headers=ASHA,
    )
    assert missing.status_code == 404


def test_edit_voids_approval_and_blocks_posting(client, session_factory):
    body = payload_for(session_factory, CaseLabel.CLEAN, 3)
    invoice = client.post("/invoices", json=body, headers=ASHA).json()
    assert invoice["status"] == "AUTO_APPROVED"

    edited = client.post(
        f"/invoices/{invoice['id']}/edit",
        json={
            "expected_version": 1,
            "reason": "supplier corrected the total",
            "changes": {"total": "1.00"},
        },
        headers=ASHA,
    )
    assert edited.status_code == 200
    assert (edited.json()["status"], edited.json()["version"]) == ("NEEDS_REVIEW", 2)
    assert client.post(f"/invoices/{invoice['id']}/post", headers=ASHA).status_code == 409


def test_list_filters_by_status(client, session_factory):
    client.post("/invoices", json=payload_for(session_factory, CaseLabel.CLEAN, 4), headers=ASHA)
    client.post(
        "/invoices", json=payload_for(session_factory, CaseLabel.PRICE_VARIANCE, 5), headers=ASHA
    )
    review = client.get("/invoices", params={"status": "NEEDS_REVIEW"}, headers=ASHA).json()
    assert [i["status"] for i in review] == ["NEEDS_REVIEW"]


def test_invalid_payload_is_a_422(client):
    assert client.post("/invoices", json={"invoice_number": "x"}, headers=ASHA).status_code == 422


def test_document_upload_queues_extraction(client, session_factory):
    from invoiceguard.db import models as m
    from invoiceguard.generator.pdf import render_invoice_pdf

    scenario = generate_scenario(random.Random(20), 20, CaseLabel.CLEAN)
    pdf = render_invoice_pdf(scenario.invoice, "compact")
    resp = client.post(
        "/documents", files={"file": ("inv.pdf", pdf, "application/pdf")}, headers=ASHA
    )
    assert resp.status_code == 202
    body = resp.json()
    assert (body["status"], body["total"]) == ("RECEIVED", None)

    doc = client.get(f"/invoices/{body['id']}/document", headers=ASHA)
    assert doc.status_code == 200
    assert doc.content == pdf
    with session_factory() as session:
        assert session.query(m.OutboxMessage).count() == 1


def test_non_pdf_upload_is_a_422(client):
    resp = client.post(
        "/documents", files={"file": ("x.txt", b"hello", "text/plain")}, headers=ASHA
    )
    assert resp.status_code == 422


def test_replay_of_a_healthy_invoice_is_a_409(client, session_factory):
    body = payload_for(session_factory, CaseLabel.CLEAN, 21)
    invoice = client.post("/invoices", json=body, headers=ASHA).json()
    assert client.post(f"/invoices/{invoice['id']}/replay", headers=ASHA).status_code == 409
    assert client.get("/failed-jobs", headers=ASHA).json() == []


def test_writes_are_rate_limited_per_reviewer(client, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_writes_per_minute", 2)
    body = payload_for(session_factory, CaseLabel.CLEAN, 30)
    invoice = client.post("/invoices", json=body, headers=ASHA).json()
    path = f"/invoices/{invoice['id']}/post"
    assert client.post(path, headers=ASHA).status_code == 200  # second write this minute
    assert client.post(path, headers=ASHA).status_code == 429  # third is refused
    assert client.post(path, headers=RAVI).status_code == 200  # other reviewers unaffected
    assert client.get("/invoices", headers=ASHA).status_code == 200  # reads are not limited


def test_kill_switch_pauses_writes_but_not_reads(client, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "writes_enabled", False)
    body = payload_for(session_factory, CaseLabel.CLEAN, 31)
    assert client.post("/invoices", json=body, headers=ASHA).status_code == 503
    assert client.get("/invoices", headers=ASHA).status_code == 200


def test_queue_rows_carry_reasons_and_detail_carries_po_and_receipts(client, session_factory):
    body = payload_for(session_factory, CaseLabel.PARTIAL_RECEIPT_OVERBILLED, 40)
    invoice = client.post("/invoices", json=body, headers=ASHA).json()

    rows = client.get("/invoices", params={"status": "NEEDS_REVIEW"}, headers=ASHA).json()
    assert rows[0]["reasons"][0] == "QTY_OVER_RECEIVED"

    detail = client.get(f"/invoices/{invoice['id']}", headers=ASHA).json()
    assert detail["reasons"][0] == "QTY_OVER_RECEIVED"
    po = detail["purchase_order"]
    assert po["po_number"] == body["po_number"]
    assert {line["sku"] for line in po["lines"]} == {line["sku"] for line in body["lines"]}
    assert detail["receipt_count"] == 1
    first = body["lines"][0]
    assert float(detail["received"][first["sku"]]) < float(first["qty"])  # partial receipt


def test_json_numbers_keep_decimal_precision():
    raw = (
        '{"invoice_number":"A","vendor_id":"V1","currency":"INR",'
        '"lines":[{"sku":"S","qty":3,"unit_price":0.1}],'
        '"subtotal":0.3,"tax":0.0,"total":0.3,"file_hash":"h"}'
    )
    parsed = InvoiceIn.model_validate_json(raw)
    assert str(parsed.lines[0].unit_price) == "0.1"
    assert str(parsed.total) == "0.3"


def test_packs_need_a_key(client):
    assert client.get("/packs").status_code == 401
    assert client.get("/packs/invoices").status_code == 401


def test_packs_lists_the_installed_packs(client):
    body = client.get("/packs", headers=ASHA).json()
    assert [p["id"] for p in body] == ["invoices", "expenses"]


def test_pack_manifest_carries_reasons_thresholds_and_layout(client):
    body = client.get("/packs/invoices", headers=ASHA).json()
    assert body["id"] == "invoices"
    assert any(r["code"] == "PRICE_VARIANCE" for r in body["reasons"])
    assert body["thresholds"]["min_extraction_confidence"] == "0.90"
    assert body["tolerances"]["price_pct"] == "2"
    assert "three_way_match" in body["detail_sections"]


def test_unknown_pack_is_a_404(client):
    assert client.get("/packs/payroll", headers=ASHA).status_code == 404
