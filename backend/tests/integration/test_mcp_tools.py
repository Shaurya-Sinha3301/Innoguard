import asyncio
import random

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.seed import seed_master_data
from invoiceguard.mcp_server import tools
from invoiceguard.workflow.service import submit_invoice

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture
def seeded(session_factory):
    scenario = generate_scenario(random.Random(3), 3, CaseLabel.PARTIAL_RECEIPT_OVERBILLED)
    with session_factory() as session:
        seed_master_data(session, scenario)
        submit_invoice(session, scenario.invoice)
        session.commit()
    return scenario


def test_purchase_order_and_receipts(session_factory, seeded):
    with tools.readonly_session(session_factory) as session:
        po = tools.get_purchase_order(session, seeded.po.po_number)
        receipts = tools.get_goods_receipts(session, seeded.po.po_number)
    assert po["vendor_id"] == seeded.po.vendor_id
    assert [line["sku"] for line in po["lines"]] == [line.sku for line in seeded.po.lines]
    assert len(receipts) == 1
    assert isinstance(po["lines"][0]["unit_price"], str)  # money is never a float


def test_vendor_and_history(session_factory, seeded):
    with tools.readonly_session(session_factory) as session:
        vendor = tools.get_vendor(session, seeded.po.vendor_id)
        history = tools.get_invoice_history(session, seeded.invoice.vendor_id, limit=500)
        missing = tools.get_vendor(session, "V-NOPE")
    assert vendor["vendor_id"] == seeded.po.vendor_id
    assert missing is None
    assert history[0]["status"] == "NEEDS_REVIEW"
    assert len(history) <= tools.MAX_HISTORY


@pytest.mark.parametrize("bad", ["", "x" * 65, "PO-1; DROP TABLE invoices", "../etc", "PO 1"])
def test_invalid_identifiers_are_rejected(session_factory, bad):
    with tools.readonly_session(session_factory) as session, pytest.raises(tools.ToolInputError):
        tools.get_purchase_order(session, bad)


def test_the_database_refuses_writes_in_a_tool_session(session_factory, seeded):
    with tools.readonly_session(session_factory) as session, pytest.raises(DBAPIError) as exc:
        session.execute(sa.text("UPDATE invoices SET status = 'POSTED'"))
    assert "read-only" in str(exc.value)


def test_server_exposes_only_the_read_only_tools():
    from invoiceguard.mcp_server.server import mcp

    listed = asyncio.run(mcp.list_tools())
    assert sorted(tool.name for tool in listed) == [
        "get_goods_receipts",
        "get_invoice_history",
        "get_purchase_order",
        "get_vendor",
    ]
    assert all(tool.annotations and tool.annotations.read_only_hint for tool in listed)
