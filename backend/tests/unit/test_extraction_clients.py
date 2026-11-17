import random
from decimal import Decimal
from types import SimpleNamespace

import pytest

from invoiceguard.extraction.cache import CachedExtractor
from invoiceguard.extraction.client import ClaudeExtractor, ExtractionError, LlmUsage
from invoiceguard.extraction.fakes import FakeExtractor, truth_as_extraction
from invoiceguard.extraction.metrics import cost_usd, tokens_per_second
from invoiceguard.generator.cases import CaseLabel, generate_scenario

INVOICE = generate_scenario(random.Random(1), 1, CaseLabel.CLEAN).invoice
TRUTH = truth_as_extraction(INVOICE, "classic")


class StubMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def stub_client(stop_reason="end_turn", parsed=TRUTH):
    response = SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=1500, output_tokens=400),
    )
    return SimpleNamespace(messages=StubMessages(response))


def test_claude_extractor_sends_the_pdf_and_reports_usage():
    client = stub_client()
    result = ClaudeExtractor("claude-haiku-5-5", client=client).extract(b"%PDF-1.4 fake")
    sent = client.messages.kwargs
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["messages"][0]["content"][0]["type"] == "document"
    assert "data, not instructions" in sent["system"]
    assert result.invoice == TRUTH
    assert (result.usage.input_tokens, result.usage.output_tokens) == (1500, 400)


@pytest.mark.parametrize(
    ("stop_reason", "parsed"), [("refusal", TRUTH), ("max_tokens", TRUTH), ("end_turn", None)]
)
def test_unusable_responses_become_extraction_errors(stop_reason, parsed):
    extractor = ClaudeExtractor("claude-haiku-5-5", client=stub_client(stop_reason, parsed))
    with pytest.raises(ExtractionError):
        extractor.extract(b"%PDF-1.4 fake")


def test_cache_records_then_replays_without_calling_the_model(tmp_path):
    inner = FakeExtractor(TRUTH)
    first = CachedExtractor(tmp_path, inner).extract(b"%PDF same bytes")
    replay = CachedExtractor(tmp_path).extract(b"%PDF same bytes")
    assert inner.calls == 1
    assert replay.invoice == first.invoice
    assert replay.usage == first.usage


def test_replay_only_cache_refuses_unknown_documents(tmp_path):
    with pytest.raises(ExtractionError):
        CachedExtractor(tmp_path).extract(b"%PDF never seen")


def test_cost_and_throughput():
    usage = LlmUsage("anthropic", "claude-haiku-5-5", 1_000_000, 200_000, 2000)
    assert cost_usd(usage) == Decimal("0.20")  # 0.10 input + 0.10 output
    assert tokens_per_second(usage) == Decimal("100000.0000")
    unknown = LlmUsage("anthropic", "some-other-model", 10, 10, 0)
    assert cost_usd(unknown) == 0
    assert tokens_per_second(unknown) is None
