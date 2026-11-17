from decimal import Decimal

from invoiceguard.domain.matching import DiscrepancyCode, three_way_match
from invoiceguard.domain.models import (
    GoodsReceipt,
    Invoice,
    InvoiceLine,
    PoLine,
    PurchaseOrder,
    ReceiptLine,
    Tolerances,
)

D = Decimal


def make_po(qty="10", price="100.00"):
    return PurchaseOrder("PO-1", "V001", "INR", (PoLine("SKU-A", D(qty), D(price)),))


def make_receipt(qty="10", receipt_id="GR-1"):
    return GoodsReceipt(receipt_id, "PO-1", (ReceiptLine("SKU-A", D(qty)),))


def make_invoice(qty="10", price="100.00", vendor="V001", sku="SKU-A"):
    line = InvoiceLine(sku, D(qty), D(price))
    subtotal = line.qty * line.unit_price
    return Invoice("INV-1", vendor, "PO-1", "INR", (line,), subtotal, D(0), subtotal, "hash")


def codes(result):
    return {d.code for d in result.discrepancies}


def test_clean_match():
    result = three_way_match(make_invoice(), make_po(), [make_receipt()])
    assert result.discrepancies == ()
    assert result.match_quality == D(1)


def test_missing_po():
    result = three_way_match(make_invoice(), None, [make_receipt()])
    assert codes(result) == {DiscrepancyCode.NO_PO}
    assert result.match_quality == D(0)


def test_missing_receipt_is_a_header_problem():
    result = three_way_match(make_invoice(), make_po(), [])
    assert codes(result) == {DiscrepancyCode.NO_RECEIPT}
    assert result.match_quality == D(0)


def test_billing_more_than_received():
    result = three_way_match(make_invoice(qty="10"), make_po(), [make_receipt(qty="8")])
    assert codes(result) == {DiscrepancyCode.QTY_OVER_RECEIVED}
    assert result.match_quality == D(0)


def test_billing_exactly_what_was_received_is_clean():
    result = three_way_match(make_invoice(qty="8"), make_po(), [make_receipt(qty="8")])
    assert result.discrepancies == ()


def test_multiple_receipts_are_summed():
    receipts = [make_receipt(qty="4", receipt_id="GR-1"), make_receipt(qty="6", receipt_id="GR-2")]
    result = three_way_match(make_invoice(qty="10"), make_po(), receipts)
    assert result.discrepancies == ()


def test_price_variance_beyond_tolerance_only():
    within = three_way_match(make_invoice(price="101.50"), make_po(), [make_receipt()])
    assert within.discrepancies == ()
    result = three_way_match(make_invoice(price="103.00"), make_po(), [make_receipt()])
    assert codes(result) == {DiscrepancyCode.PRICE_VARIANCE}


def test_quantity_tolerance_is_configurable():
    loose = Tolerances(qty_pct=D("10"))
    result = three_way_match(
        make_invoice(qty="11"), make_po(), [make_receipt(qty="11")], loose
    )
    assert result.discrepancies == ()


def test_over_ordered_quantity():
    result = three_way_match(make_invoice(qty="12"), make_po(), [make_receipt(qty="12")])
    assert codes(result) == {DiscrepancyCode.QTY_OVER_ORDERED}


def test_split_invoices_within_the_order_are_clean():
    # 4 already billed + 6 now = 10, which equals the quantity ordered and received.
    result = three_way_match(
        make_invoice(qty="6"), make_po(), [make_receipt()], previously_invoiced={"SKU-A": D("4")}
    )
    assert result.discrepancies == ()


def test_split_invoices_cannot_exceed_the_order():
    # 6 already billed + 6 now = 12, more than the 10 ordered and received.
    result = three_way_match(
        make_invoice(qty="6"), make_po(), [make_receipt()], previously_invoiced={"SKU-A": D("6")}
    )
    assert codes(result) == {DiscrepancyCode.QTY_OVER_ORDERED, DiscrepancyCode.QTY_OVER_RECEIVED}


def test_unknown_sku_and_vendor_mismatch():
    result = three_way_match(make_invoice(sku="SKU-Z", vendor="V002"), make_po(), [make_receipt()])
    assert DiscrepancyCode.UNKNOWN_SKU in codes(result)
    assert DiscrepancyCode.VENDOR_MISMATCH in codes(result)
    assert result.match_quality == D(0)
