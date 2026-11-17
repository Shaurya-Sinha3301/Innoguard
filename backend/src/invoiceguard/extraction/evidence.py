"""Check that each extracted value is backed by text that really is in the document.

The model reports its own confidence, which is not calibrated. This check is independent:
if the quoted snippet cannot be found in the PDF's text, the field's confidence is capped,
which sends the invoice to a human.
"""

import re
from dataclasses import replace
from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader

from invoiceguard.extraction.normalizer import FieldRecord

UNVERIFIED_CAP = Decimal("0.5")


def page_texts(pdf: bytes) -> list[str]:
    return [page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages]


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def check_evidence(
    records: list[FieldRecord], texts: list[str]
) -> tuple[list[FieldRecord], list[str]]:
    pages = [_squash(t) for t in texts]
    everything = " ".join(pages)
    checked: list[FieldRecord] = []
    issues: list[str] = []
    for record in records:
        if not record.value:
            checked.append(record)
            continue
        snippet = _squash(record.snippet or "")
        on_page = (
            record.page is not None
            and 1 <= record.page <= len(pages)
            and snippet in pages[record.page - 1]
        )
        if snippet and (on_page or snippet in everything):
            checked.append(record)
        else:
            issues.append(f"EVIDENCE_NOT_FOUND:{record.field}")
            checked.append(replace(record, confidence=min(record.confidence, UNVERIFIED_CAP)))
    return checked, issues
