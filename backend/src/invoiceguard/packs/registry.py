"""All installed packs, validated when the process starts."""

from invoiceguard.packs.base import Pack
from invoiceguard.packs.invoices import PACK as INVOICES

_PACKS: dict[str, Pack] = {INVOICES.id: INVOICES}


def list_packs() -> list[Pack]:
    return list(_PACKS.values())


def get_pack(pack_id: str) -> Pack | None:
    return _PACKS.get(pack_id)
