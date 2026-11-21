"""Pack 1: supplier invoices reconciled against purchase orders and goods receipts."""

from dataclasses import dataclass
from pathlib import Path

from invoiceguard.packs.base import Manifest, load_manifest


@dataclass(frozen=True)
class InvoicePack:
    id: str
    manifest: Manifest


_MANIFEST = load_manifest(Path(__file__).with_name("manifest.yaml"))
PACK = InvoicePack(id=_MANIFEST.id, manifest=_MANIFEST)
