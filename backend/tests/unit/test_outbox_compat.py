"""Outbox rows written before the cases rename carry "invoice_id". They must still be sent."""

import pytest

from invoiceguard.jobs import tasks


@pytest.mark.parametrize("key", ["case_id", "invoice_id"])
def test_publish_accepts_both_payload_keys(monkeypatch, key):
    sent = []
    monkeypatch.setattr(
        tasks.extract_invoice,
        "apply_async",
        lambda args, task_id, retry: sent.append((args, task_id)),
    )
    tasks.publish("invoice.extract", {key: "abc"}, 7)
    assert sent == [(["abc"], "outbox-7")]


def test_publish_refuses_an_unknown_topic():
    with pytest.raises(ValueError):
        tasks.publish("something.else", {"case_id": "abc"}, 1)
