"""Pack 1: supplier invoices reconciled against purchase orders and goods receipts."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from invoiceguard.domain.duplicates import normalize_invoice_number
from invoiceguard.extraction.normalizer import normalize
from invoiceguard.extraction.prompts import SYSTEM_PROMPT, USER_PROMPT
from invoiceguard.extraction.records import NormalizedCase
from invoiceguard.extraction.schema import ExtractedInvoice
from invoiceguard.packs.base import Manifest, PackReconciliation, load_manifest

LOOKUPS = ("vendor", "purchase_order", "goods_receipts", "vendor_invoices")


@dataclass(frozen=True)
class InvoicePack:
    id: str
    manifest: Manifest
    extraction_model: type[BaseModel] = ExtractedInvoice
    system_prompt: str = SYSTEM_PROMPT
    user_prompt: str = USER_PROMPT
    lookup_names: tuple[str, ...] = LOOKUPS

    def normalize(self, extracted: Any, file_hash: str) -> NormalizedCase:
        n = normalize(extracted, file_hash)
        return NormalizedCase(n.invoice, n.confidence, n.fields, n.issues)

    def apply_extracted(self, row: Any, value: Any) -> None:
        from invoiceguard.db import models as m

        row.invoice_number = value.invoice_number
        row.number_norm = normalize_invoice_number(value.invoice_number)
        row.vendor_id = value.vendor_id
        row.po_number = value.po_number
        row.currency = value.currency
        row.subtotal = value.subtotal
        row.tax = value.tax
        row.total = value.total
        row.lines = [
            m.CaseLine(line_no=i, sku=line.sku, qty=line.qty, unit_price=line.unit_price)
            for i, line in enumerate(value.lines, start=1)
        ]

    def reconcile(self, session: Session, row: Any, confidence: Decimal) -> PackReconciliation:
        from invoiceguard.workflow.service import reconcile_row

        result = reconcile_row(session, row, confidence)
        return PackReconciliation(
            decision=result.decision,
            matched_payload={
                "match_quality": result.match.match_quality,
                "discrepancies": [d.code.value for d in result.match.discrepancies],
            },
        )

    def context(self, session: Session, row: Any) -> dict[str, Any]:
        return {}  # the invoice case page reads the PO and receipts from the detail itself

    def lookup(self, session: Session, name: str, key: str) -> Any:
        from invoiceguard.mcp_server import tools

        return tools.lookup(session, name, key)


_MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
PACK = InvoicePack(id=_MANIFEST.id, manifest=_MANIFEST)
