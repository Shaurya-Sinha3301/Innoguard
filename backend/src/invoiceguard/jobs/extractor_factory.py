from invoiceguard.config import settings
from invoiceguard.db.session import SessionLocal
from invoiceguard.extraction.cache import DbCachedExtractor
from invoiceguard.extraction.client import ClaudeExtractor, Extractor

PROVIDERS = ("groq", "anthropic")


def live_extractor(provider: str, model: str) -> Extractor:
    """The model client for a provider. Both sit behind the same Extractor interface."""
    if provider == "groq":
        from invoiceguard.extraction.groq_client import GroqExtractor

        return GroqExtractor(model)
    if provider == "anthropic":
        return ClaudeExtractor(model)
    raise ValueError(f"unknown extraction provider {provider!r}; use one of {PROVIDERS}")


def build_extractor() -> Extractor:
    """Live mode records every response; replay mode never calls the model."""
    if settings.extraction_mode == "replay":
        return DbCachedExtractor(SessionLocal)
    return DbCachedExtractor(
        SessionLocal, live_extractor(settings.extraction_provider, settings.extraction_model)
    )
