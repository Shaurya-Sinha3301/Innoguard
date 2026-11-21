"""Record-and-replay of model responses, keyed by the document's file hash.

Live runs record each response; CI, evaluation and the hosted demo replay them, so results
are reproducible and cost nothing. A replay-only cache refuses to call the model at all.

Two stores: files (evaluation recordings committed to the repo) and the database (shared
by every hosted service, since separate services do not share a disk).
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from invoiceguard.db.models import ExtractionRecording
from invoiceguard.extraction.client import ExtractionError, ExtractionResponse, Extractor, LlmUsage


def _encode(response: ExtractionResponse) -> dict[str, Any]:
    return {"extracted": response.extracted.model_dump(), "usage": asdict(response.usage)}


def _decode(data: dict[str, Any], pack: str | None) -> ExtractionResponse:
    from invoiceguard.packs.registry import require_pack

    model = require_pack(pack).extraction_model
    # Recordings made before packs existed stored the invoice under "invoice".
    payload = data["extracted"] if "extracted" in data else data["invoice"]
    return ExtractionResponse(
        extracted=model.model_validate(payload),
        usage=LlmUsage(**data["usage"]),
    )


def file_hash(pdf: bytes) -> str:
    return hashlib.sha256(pdf).hexdigest()


class CachedExtractor:
    """File-backed cache, used for evaluation recordings."""

    def __init__(self, cache_dir: Path, inner: Extractor | None = None) -> None:
        self.cache_dir = Path(cache_dir)
        self.inner = inner  # None means replay only

    def _path(self, pdf: bytes) -> Path:
        return self.cache_dir / f"{file_hash(pdf)}.json"

    def extract(self, pdf: bytes, pack: str | None = None) -> ExtractionResponse:
        path = self._path(pdf)
        if path.exists():
            return _decode(json.loads(path.read_text(encoding="utf-8")), pack)
        if self.inner is None:
            raise ExtractionError(f"no recorded extraction for {path.name}")
        response = self.inner.extract(pdf, pack)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_encode(response), indent=2, sort_keys=True), encoding="utf-8")
        return response


class DbCachedExtractor:
    """Database-backed cache, used by the running services."""

    def __init__(self, session_factory: sessionmaker, inner: Extractor | None = None) -> None:
        self.session_factory = session_factory
        self.inner = inner

    def extract(self, pdf: bytes, pack: str | None = None) -> ExtractionResponse:
        key = file_hash(pdf)
        with self.session_factory() as session:
            row = session.get(ExtractionRecording, key)
            if row is not None:
                return _decode(row.payload, pack)
        if self.inner is None:
            raise ExtractionError(f"no recorded extraction for {key}")
        response = self.inner.extract(pdf, pack)
        record(self.session_factory, pdf, response, simulated=False)
        return response


def record(
    session_factory: sessionmaker, pdf: bytes, response: ExtractionResponse, *, simulated: bool
) -> None:
    with session_factory() as session:
        session.execute(
            pg_insert(ExtractionRecording)
            .values(file_hash=file_hash(pdf), payload=_encode(response), simulated=simulated)
            .on_conflict_do_nothing(index_elements=["file_hash"])
        )
        session.commit()
