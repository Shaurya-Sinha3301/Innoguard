"""Render synthetic invoices as PDFs in several vendor layouts.

Templates differ in labels, field order and number formatting so extraction is not tested
against a single layout. Rendering is deterministic (fixed metadata), so the same invoice
and template always give the same bytes and the same file hash.
"""

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from invoiceguard.domain.models import Invoice

TEMPLATES = ("classic", "compact", "ledger")


def format_western(value: Decimal) -> str:
    return f"{value:,.2f}"


def format_indian(value: Decimal) -> str:
    """1234567.5 -> 12,34,567.50 (lakh/crore grouping)."""
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}{whole}.{frac}"


def _qty(value: Decimal) -> str:
    return str(value.normalize()) if value == value.to_integral() else str(value)


@dataclass(frozen=True)
class TemplateStyle:
    title: str
    number_label: str
    vendor_label: str
    po_label: str
    subtotal_label: str
    tax_label: str
    total_label: str
    money: str  # "western", "indian" or "prefixed"


STYLES = {
    "classic": TemplateStyle(
        "TAX INVOICE", "Invoice No:", "Vendor Code:", "PO Ref:", "Subtotal", "GST 5%", "Total INR",
        "western",
    ),
    "compact": TemplateStyle(
        "BILL", "Bill #", "Supplier:", "Purchase Order", "Net amount", "Tax", "Amount due (Rs.)",
        "indian",
    ),
    "ledger": TemplateStyle(
        "Invoice", "Reference", "Supplier ID", "Order", "Sub-total", "Tax (5%)", "Grand total",
        "prefixed",
    ),
}


def printed_money(value: Decimal, template: str) -> str:
    style = STYLES[template].money
    if style == "indian":
        return format_indian(value)
    if style == "prefixed":
        return f"INR {format_western(value)}"
    return format_western(value)


def printed_values(invoice: Invoice, template: str) -> dict[str, str]:
    """The header values exactly as the template prints them."""
    return {
        "invoice_number": invoice.invoice_number,
        "vendor_id": invoice.vendor_id,
        "po_number": invoice.po_number or "",
        "currency": "INR",
        "subtotal": printed_money(invoice.subtotal, template),
        "tax": printed_money(invoice.tax, template),
        "total": printed_money(invoice.total, template),
    }


def render_invoice_pdf(invoice: Invoice, template: str, injection: str | None = None) -> bytes:
    """Render one invoice. `injection` adds hostile text inside the document for testing."""
    style = STYLES[template]
    values = printed_values(invoice, template)
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4, invariant=1)
    canvas.setTitle(f"Invoice {invoice.invoice_number}")
    width, height = A4
    left, y = 50, height - 60

    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(left, y, style.title)
    canvas.setFont("Helvetica", 10)
    y -= 30
    header = [
        (style.number_label, values["invoice_number"]),
        (style.vendor_label, values["vendor_id"]),
        (style.po_label, values["po_number"]),
        ("Currency", values["currency"]),
    ]
    if template == "ledger":
        header.reverse()  # different field order in this layout
    for label, value in header:
        canvas.drawString(left, y, f"{label} {value}")
        y -= 16

    y -= 14
    canvas.setFont("Helvetica-Bold", 10)
    columns = (left, left + 180, left + 260, left + 380)
    for x, heading in zip(columns, ("Item", "Qty", "Unit price", "Amount"), strict=True):
        canvas.drawString(x, y, heading)
    canvas.setFont("Helvetica", 10)
    y -= 16
    for line in invoice.lines:
        amount = line.qty * line.unit_price
        cells = (
            line.sku,
            _qty(line.qty),
            printed_money(line.unit_price, template),
            printed_money(amount, template),
        )
        for x, cell in zip(columns, cells, strict=True):
            canvas.drawString(x, y, cell)
        y -= 16

    y -= 14
    for label, key in (
        (style.subtotal_label, "subtotal"),
        (style.tax_label, "tax"),
        (style.total_label, "total"),
    ):
        canvas.drawString(left + 260, y, f"{label} {values[key]}")
        y -= 16

    if injection:
        canvas.setFont("Helvetica", 7)
        canvas.drawString(left, 60, injection)

    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
