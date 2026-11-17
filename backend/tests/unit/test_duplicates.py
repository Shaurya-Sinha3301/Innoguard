import pytest

from invoiceguard.domain.duplicates import file_hash, find_duplicates, normalize_invoice_number
from invoiceguard.domain.models import ExistingInvoice


@pytest.mark.parametrize(
    "raw",
    ["INV-0042", "inv 42", "INV42", "Inv/0042", " inv-042 "],
)
def test_formatting_variants_normalise_together(raw):
    assert normalize_invoice_number(raw) == "INV42"


def test_zeros_inside_numbers_are_kept():
    assert normalize_invoice_number("A-100") == "A100"
    assert normalize_invoice_number("INV-007") == "INV7"


def test_file_hash_is_stable():
    assert file_hash(b"same bytes") == file_hash(b"same bytes")
    assert file_hash(b"a") != file_hash(b"b")


def _existing(**overrides):
    base = {"invoice_id": "e1", "file_hash": "h1", "vendor_id": "V001", "number_norm": "INV42"}
    return ExistingInvoice(**{**base, **overrides})


def test_exact_file_duplicate():
    result = find_duplicates(
        invoice_file_hash="h1", vendor_id="V009", number_norm="OTHER", existing=[_existing()]
    )
    assert result.exact and not result.business_key
    assert result.matched_ids == ("e1",)


def test_business_key_duplicate_with_different_file():
    result = find_duplicates(
        invoice_file_hash="h2", vendor_id="V001", number_norm="INV42", existing=[_existing()]
    )
    assert result.business_key and not result.exact


def test_same_number_from_another_vendor_is_not_a_duplicate():
    result = find_duplicates(
        invoice_file_hash="h2", vendor_id="V002", number_norm="INV42", existing=[_existing()]
    )
    assert not result.exact and not result.business_key
    assert result.matched_ids == ()
