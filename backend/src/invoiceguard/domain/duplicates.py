"""Duplicate detection layers: exact file hash, then vendor + normalised invoice number.

Release 2 adds near-duplicate and perceptual-hash layers. Posting idempotency is a
separate mechanism and does not replace these checks.
"""

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

from invoiceguard.domain.models import ExistingInvoice


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_invoice_number(number: str) -> str:
    """Uppercase, drop punctuation and spaces, strip leading zeros from digit runs.

    "INV-0042", "inv 42" and "INV42" all normalise to "INV42".
    """
    cleaned = re.sub(r"[^A-Z0-9]", "", number.upper())
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", cleaned)


@dataclass(frozen=True)
class DuplicateResult:
    exact: bool
    business_key: bool
    matched_ids: tuple[str, ...]


def find_duplicates(
    *,
    invoice_file_hash: str,
    vendor_id: str,
    number_norm: str,
    existing: Iterable[ExistingInvoice],
) -> DuplicateResult:
    exact = False
    business = False
    matched: list[str] = []
    for other in existing:
        same_file = other.file_hash == invoice_file_hash
        same_key = other.vendor_id == vendor_id and other.number_norm == number_norm
        if same_file:
            exact = True
        if same_key and not same_file:
            business = True
        if same_file or same_key:
            matched.append(other.case_id)
    return DuplicateResult(exact=exact, business_key=business, matched_ids=tuple(matched))
