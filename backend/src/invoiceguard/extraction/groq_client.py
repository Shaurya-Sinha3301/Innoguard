"""Extraction with Groq-hosted models, using strict JSON-schema structured outputs.

Groq models take text, not PDF files, so the PDF's text layer is extracted locally and
sent with page markers. The model still quotes a page and snippet for every value, and the
evidence check verifies those quotes against the same text. PDFs with no text layer
(scans) are refused; scanned documents are a Release 2 item.
"""

import copy
import time
from typing import Any

import groq
from pydantic import ValidationError

from invoiceguard.extraction.client import (
    SYSTEM_PROMPT,
    ExtractionError,
    ExtractionResponse,
    LlmUsage,
    TransientExtractionError,
)
from invoiceguard.extraction.evidence import page_texts
from invoiceguard.extraction.schema import ExtractedInvoice

USER_PROMPT = (
    "Extract the invoice header fields and every line item from the document below. "
    "Use the page markers for the page numbers. Return only the JSON object."
)


def strict_schema(model: type[ExtractedInvoice] = ExtractedInvoice) -> dict[str, Any]:
    """The Pydantic schema rewritten for strict mode: references inlined, every object
    closed with additionalProperties false, every property required."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            node = {k: resolve(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            return node
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def document_text(pdf: bytes) -> str:
    pages = page_texts(pdf)
    if not any(page.strip() for page in pages):
        raise ExtractionError("the PDF has no text layer; scanned documents are not supported yet")
    return "\n\n".join(f"--- Page {i} ---\n{text.strip()}" for i, text in enumerate(pages, start=1))


class GroqExtractor:
    provider = "groq"

    def __init__(self, model: str, client: groq.Groq | None = None) -> None:
        self.model = model
        # The key comes from the GROQ_API_KEY environment variable.
        self.client = client or groq.Groq(max_retries=0)
        self._schema = strict_schema()

    def extract(self, pdf: bytes) -> ExtractionResponse:
        text = document_text(pdf)
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"{USER_PROMPT}\n\n{text}"},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extracted_invoice",
                        "strict": True,
                        "schema": self._schema,
                    },
                },
            )
        except (groq.RateLimitError, groq.APIConnectionError, groq.APITimeoutError) as exc:
            raise TransientExtractionError(type(exc).__name__) from exc
        except groq.APIStatusError as exc:
            if exc.status_code >= 500:
                raise TransientExtractionError(f"server error {exc.status_code}") from exc
            raise ExtractionError(f"request rejected ({exc.status_code})") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise ExtractionError("the model ran out of output tokens")
        try:
            invoice = ExtractedInvoice.model_validate_json(choice.message.content or "")
        except ValidationError as exc:
            raise ExtractionError("the model's output did not match the schema") from exc

        usage = response.usage
        return ExtractionResponse(
            invoice=invoice,
            usage=LlmUsage(
                provider=self.provider,
                model=self.model,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            ),
        )
