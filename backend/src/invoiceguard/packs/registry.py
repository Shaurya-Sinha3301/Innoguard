"""All installed packs, validated when the process starts."""

from invoiceguard.packs.base import Pack
from invoiceguard.packs.expenses import PACK as EXPENSES
from invoiceguard.packs.invoices import PACK as INVOICES

_PACKS: dict[str, Pack] = {INVOICES.id: INVOICES, EXPENSES.id: EXPENSES}


def list_packs() -> list[Pack]:
    return list(_PACKS.values())


def get_pack(pack_id: str) -> Pack | None:
    return _PACKS.get(pack_id)


DEFAULT_PACK = "invoices"


def require_pack(pack_id: str | None) -> Pack:
    """The pack by id, defaulting to invoices for callers written before there were two."""
    found = _PACKS.get(pack_id or DEFAULT_PACK)
    if found is None:
        raise KeyError(f"unknown pack {pack_id!r}")
    return found
