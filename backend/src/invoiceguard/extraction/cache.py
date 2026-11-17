"""Record-and-replay cache keyed by file hash.

Live runs record each model response to disk; CI and evaluation replay them, so results are
reproducible and cost nothing. A replay-only cache refuses to call the model at all.
"""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from invoiceguard.extraction.client import ExtractionError, ExtractionResponse, Extractor, LlmUsage
from invoiceguard.extraction.schema import ExtractedInvoice


class CachedExtractor:
    def __init__(self, cache_dir: Path, inner: Extractor | None = None) -> None:
        self.cache_dir = Path(cache_dir)
        self.inner = inner  # None means replay only

    def _path(self, pdf: bytes) -> Path:
        return self.cache_dir / f"{hashlib.sha256(pdf).hexdigest()}.json"

    def extract(self, pdf: bytes) -> ExtractionResponse:
        path = self._path(pdf)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return ExtractionResponse(
                invoice=ExtractedInvoice.model_validate(data["invoice"]),
                usage=LlmUsage(**data["usage"]),
            )
        if self.inner is None:
            raise ExtractionError(f"no recorded extraction for {path.name}")

        response = self.inner.extract(pdf)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"invoice": response.invoice.model_dump(), "usage": asdict(response.usage)},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return response
