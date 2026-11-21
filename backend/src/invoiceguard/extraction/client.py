"""Model clients for document extraction, behind one small interface.

Callers depend on `Extractor`, so the provider can change without touching the workflow.
Errors are split into transient (worth retrying) and permanent (send to a human).
"""

import base64
import time
from dataclasses import dataclass
from typing import Protocol

import anthropic
from pydantic import BaseModel

from invoiceguard.extraction.prompts import SYSTEM_PROMPT, USER_PROMPT  # noqa: F401
from invoiceguard.extraction.schema import ExtractedInvoice  # noqa: F401


@dataclass(frozen=True)
class LlmUsage:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class ExtractionResponse:
    extracted: BaseModel  # the pack's extraction model, filled in
    usage: LlmUsage

    @property
    def invoice(self) -> BaseModel:
        """Kept for callers written when invoices were the only workflow."""
        return self.extracted


class ExtractionError(Exception):
    """Extraction could not produce a result; the invoice needs a human."""


class TransientExtractionError(Exception):
    """A temporary failure (rate limit, network, server error); retrying may succeed."""


class Extractor(Protocol):
    def extract(self, pdf: bytes, pack: str | None = None) -> ExtractionResponse: ...


class ClaudeExtractor:
    """Extraction with the Anthropic API, using structured outputs."""

    provider = "anthropic"

    def __init__(self, model: str, client: anthropic.Anthropic | None = None) -> None:
        self.model = model
        # Credentials come from the environment (ANTHROPIC_API_KEY or an `ant` profile).
        self.client = client or anthropic.Anthropic(max_retries=0)

    def extract(self, pdf: bytes, pack: str | None = None) -> ExtractionResponse:
        from invoiceguard.packs.registry import require_pack

        spec = require_pack(pack)
        started = time.perf_counter()
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=spec.system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": base64.b64encode(pdf).decode("ascii"),
                                },
                            },
                            {"type": "text", "text": spec.user_prompt},
                        ],
                    }
                ],
                output_format=spec.extraction_model,
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
            raise TransientExtractionError(type(exc).__name__) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientExtractionError(f"server error {exc.status_code}") from exc
            raise ExtractionError(f"request rejected ({exc.status_code})") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.stop_reason == "refusal":
            raise ExtractionError("the model declined to process this document")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise ExtractionError(f"no usable output (stop reason {response.stop_reason})")

        return ExtractionResponse(
            extracted=response.parsed_output,
            usage=LlmUsage(
                provider=self.provider,
                model=self.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=latency_ms,
            ),
        )
