"""Unit tests for data models."""

from gigaplexity.models import (
    Citation,
    ReasoningStep,
    SearchMode,
    SearchResult,
    build_request_payload,
)


class TestBuildRequestPayload:
    def test_ask_mode(self):
        payload = build_request_payload("hello", SearchMode.ASK, "sess-123")
        assert payload == {
            "text": "hello",
            "agent": "019a5d95-ab99-7c86-a31c-610dad03b054",
            "sessionId": "sess-123",
            "featureFlags": [],
        }
        assert "model" not in payload
        assert "aiAgent" not in payload

    def test_research_mode_defaults(self):
        payload = build_request_payload("topic", SearchMode.RESEARCH, "sess-456")
        assert payload["agent"] == "9384a8fd-39e0-4da9-9bc4-da143487449f"
        assert payload["model"] == "GigaChat-3-Ultra"
        assert payload["aiAgent"] == {
            "queryDomains": [],
            "extendedResearch": False,
            "tone": "",
        }

    def test_research_mode_with_options(self):
        payload = build_request_payload(
            "topic",
            SearchMode.RESEARCH,
            "sess-789",
            domains=["example.com"],
            extended_research=True,
            tone="formal",
        )
        assert payload["aiAgent"]["queryDomains"] == ["example.com"]
        assert payload["aiAgent"]["extendedResearch"] is True
        assert payload["aiAgent"]["tone"] == "formal"

    def test_reason_mode(self):
        payload = build_request_payload("why?", SearchMode.REASON, "sess-abc")
        assert payload["agent"] == "7101c625-42ab-45fe-b168-323970c12eba"
        assert payload["model"] == "GigaChat-2-Reasoning"
        assert "aiAgent" not in payload


class TestSearchResult:
    def test_format_markdown_basic(self):
        result = SearchResult(text="Hello world")
        md = result.format_markdown()
        assert "Hello world" in md

    def test_format_markdown_with_citations(self):
        result = SearchResult(
            text="Some answer",
            citations=[
                Citation(key="1", title="Source A", url="https://a.com"),
                Citation(key="2", title="Source B", url="https://b.com"),
            ],
        )
        md = result.format_markdown()
        assert "Some answer" in md
        assert "[Source A](https://a.com)" in md
        assert "[Source B](https://b.com)" in md
        assert "**Sources:**" in md

    def test_format_markdown_with_reasoning(self):
        result = SearchResult(
            text="Final answer",
            reasoning_steps=[
                ReasoningStep(type="TEXT", value="Step 1: think"),
                ReasoningStep(type="TEXT", value="Step 2: conclude"),
            ],
        )
        md = result.format_markdown()
        assert "Reasoning" in md
        assert "Step 1: think" in md
        assert "Final answer" in md

    def test_format_markdown_with_research_log(self):
        result = SearchResult(
            text="Research report",
            research_log="Searching... Found 5 sources...",
        )
        md = result.format_markdown()
        assert "Research Log" in md
        assert "Searching..." in md
        assert "Research report" in md
