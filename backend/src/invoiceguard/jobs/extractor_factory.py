from pathlib import Path

from invoiceguard.config import settings
from invoiceguard.extraction.cache import CachedExtractor
from invoiceguard.extraction.client import ClaudeExtractor, Extractor


def build_extractor() -> Extractor:
    """Live mode records every response to the cache; replay mode never calls the model."""
    cache_dir = Path(settings.extraction_cache_dir)
    if settings.extraction_mode == "replay":
        return CachedExtractor(cache_dir)
    return CachedExtractor(cache_dir, ClaudeExtractor(settings.extraction_model))
