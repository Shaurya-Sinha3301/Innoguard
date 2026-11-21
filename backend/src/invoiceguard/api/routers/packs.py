"""The installed workflow packs and their manifests. The review UI renders from these."""

from fastapi import APIRouter, Depends, HTTPException

from invoiceguard.api.auth import current_user
from invoiceguard.packs.registry import get_pack, list_packs

router = APIRouter(prefix="/packs", tags=["packs"], dependencies=[Depends(current_user)])


@router.get("")
def packs() -> list[dict[str, object]]:
    return [
        {"id": p.id, "name": p.manifest.name, "description": p.manifest.description}
        for p in list_packs()
    ]


@router.get("/{pack_id}")
def pack(pack_id: str) -> dict[str, object]:
    found = get_pack(pack_id)
    if found is None:
        raise HTTPException(status_code=404, detail="unknown pack")
    return found.manifest.model_dump(mode="json")
