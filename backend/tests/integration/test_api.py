import random

import pytest
from fastapi.testclient import TestClient

from invoiceguard.api import deps
from invoiceguard.api.main import app
from invoiceguard.api.schemas import InvoiceIn
from invoiceguard.config import settings
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.seed import seed_master_data

pytestmark = pytest.mark.usefixtures("clean_db")

ASHA = {"X-API-Key": "key-asha"}
RAVI = {"X-API-Key": "key-ravi"}


@pytest.fixture
def client(session_factory, monkeypatch):
    monkeypatch.setattr(settings, "api_keys", "key-asha:asha,key-ravi:ravi")

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


def test_json_numbers_keep_decimal_precision():
    raw = (
        '{"invoice_number":"A","vendor_id":"V1","currency":"INR",'
        '"lines":[{"sku":"S","qty":3,"unit_price":0.1}],'
        '"subtotal":0.3,"tax":0.0,"total":0.3,"file_hash":"h"}'
    )
    parsed = InvoiceIn.model_validate_json(raw)
    assert str(parsed.lines[0].unit_price) == "0.1"
    assert str(parsed.total) == "0.3"
