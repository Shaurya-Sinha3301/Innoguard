from invoiceguard.config import settings
from invoiceguard.db.session import SessionLocal
from invoiceguard.extraction.cache import DbCachedExtractor
from invoiceguard.extraction.client import ClaudeExtractor, Extractor


def build_extractor() -> Extractor:
    """Live mode records every response; replay mode never calls the model."""
    if settings.extraction_mode == "replay":
        return DbCachedExtractor(SessionLocal)
    return DbCachedExtractor(SessionLocal, ClaudeExtractor(settings.extraction_model))
