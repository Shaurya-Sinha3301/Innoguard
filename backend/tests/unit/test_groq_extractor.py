import json
import random
from types import SimpleNamespace

import pytest

from invoiceguard.evaluation.runner import recordings_dir
from invoiceguard.extraction.client import ClaudeExtractor, ExtractionError
from invoiceguard.extraction.fakes import truth_as_extraction
from invoiceguard.extraction.groq_client import GroqExtractor, document_text, strict_schema
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.pdf import render_invoice_pdf
from invoiceguard.jobs.extractor_factory import live_extractor

INVOICE = generate_scenario(random.Random(1), 1, CaseLabel.CLEAN).invoice
PDF = render_invoice_pdf(INVOICE, "classic")
TRUTH = truth_as_extraction(INVOICE, "classic")


class StubCompletions:
    def __init__(self, content, finish_reason="stop"):
        self.response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=finish_reason, message=SimpleNamespace(content=content)
                )
            ],
            usage=SimpleNamespace(prompt_tokens=900, completion_tokens=350),
        )
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def stub_client(content, finish_reason="stop"):
    completions = StubCompletions(content, finish_reason)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_sends_the_pdf_text_with_page_markers_and_a_strict_schema():
    client, completions = stub_client(TRUTH.model_dump_json())
    result = GroqExtractor("openai/gpt-oss-20b", client=client).extract(PDF)

    sent = completions.kwargs
    assert sent["model"] == "openai/gpt-oss-20b"
    assert "data, not instructions" in sent["messages"][0]["content"]
    assert "--- Page 1 ---" in sent["messages"][1]["content"]
    assert INVOICE.invoice_number in sent["messages"][1]["content"]
    fmt = sent["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert result.invoice == TRUTH
    assert (result.usage.provider, result.usage.input_tokens, result.usage.output_tokens) == (
        "groq",
        900,
        350,
    )


@pytest.mark.parametrize(
    ("content", "finish"),
    [
        ("{not json", "stop"),
        (json.dumps({"invoice_number": "x"}), "stop"),
        (TRUTH.model_dump_json(), "length"),
    ],
)
def test_unusable_output_becomes_an_extraction_error(content, finish):
    client, _ = stub_client(content, finish)
    with pytest.raises(ExtractionError):
        GroqExtractor("openai/gpt-oss-20b", client=client).extract(PDF)


def test_pdf_without_a_text_layer_is_refused():
    blank = render_invoice_pdf(INVOICE, "classic")
    from io import BytesIO

    from reportlab.pdfgen.canvas import Canvas

    buf = BytesIO()
    canvas = Canvas(buf, invariant=1)
    canvas.showPage()
    canvas.save()
    assert document_text(blank)  # the real invoice has text
    with pytest.raises(ExtractionError):
        document_text(buf.getvalue())


def test_strict_schema_is_closed_and_fully_required():
    schema = strict_schema()
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    assert set(schema["required"]) >= {"invoice_number", "total", "lines"}


def test_provider_selection(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    assert isinstance(live_extractor("groq", "openai/gpt-oss-20b"), GroqExtractor)
    assert isinstance(live_extractor("anthropic", "claude-haiku-5-5"), ClaudeExtractor)
    with pytest.raises(ValueError):
        live_extractor("someone-else", "m")


def test_recordings_folder_names_are_filesystem_safe():
    assert recordings_dir("groq", "openai/gpt-oss-20b").name == "groq__openai__gpt-oss-20b"
