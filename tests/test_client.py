"""Unit tests for GigaChat client (mocked HTTP)."""

import json

import pytest

from gigaplexity.client import GigaChatClient
from gigaplexity.config import GigaplexitySettings
from gigaplexity.models import SearchMode


def _make_settings(**overrides) -> GigaplexitySettings:
    defaults = {
        "sm_sess": "test-jwt-token",
        "user_id": "test-user-id",
        "project_id": "test-project-id",
    }
    defaults.update(overrides)
    return GigaplexitySettings(**defaults)


def _sse_lines(*events: dict | str) -> bytes:
    """Build raw SSE response bytes from event dicts."""
    lines = []
    for event in events:
        if isinstance(event, str):
            lines.append(event.encode())
        else:
            lines.append(b"data: " + json.dumps(event).encode())
        lines.append(b"")
    return b"\n".join(lines) + b"\n"


class TestClientConfig:
    def test_headers_contain_required_fields(self):
        settings = _make_settings()
        headers = settings.build_headers("req-123")
        assert headers["x-request-id"] == "req-123"
        assert headers["x-project-id"] == "test-project-id"
        assert headers["x-sm-user-id"] == "test-user-id"
        assert headers["X-Application-Name"] == "gigachat-b2c-web"
        assert "text/event-stream" in headers["Accept"]

    def test_cookie_string_from_individual(self):
        settings = _make_settings()
        cookies = settings.build_cookie_string()
        assert "_sm_sess=test-jwt-token" in cookies
        assert "_sm_user_id=test-user-id" in cookies

    def test_cookie_string_override(self):
        settings = _make_settings(cookies="full-cookie-string")
        assert settings.build_cookie_string() == "full-cookie-string"


class TestSSEParsing:
    def test_process_delta_text(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "ASSISTANT",
                            "delta": "Hello ",
                            "markup": [],
                        }
                    ],
                }
            ),
            result,
        )
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "ASSISTANT",
                            "delta": "world!",
                            "markup": [],
                        }
                    ],
                }
            ),
            result,
        )
        assert result.text == "Hello world!"

    def test_process_citations(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "ASSISTANT",
                            "delta": "Answer",
                            "markup": [
                                {
                                    "key": "1",
                                    "title": "Source",
                                    "url": "https://example.com",
                                    "type": "FOOTNOTE",
                                }
                            ],
                        }
                    ],
                }
            ),
            result,
        )
        assert len(result.citations) == 1
        assert result.citations[0].url == "https://example.com"

    def test_process_reasoning_steps(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "reasoningSteps": [
                        {"type": "TEXT", "value": "Let me think..."}
                    ],
                }
            ),
            result,
        )
        assert len(result.reasoning_steps) == 1
        assert result.reasoning_steps[0].value == "Let me think..."

    def test_process_research_log(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "aiAgentData": {
                        "reasoning": "Searching for sources...",
                    },
                }
            ),
            result,
        )
        assert "Searching for sources..." in result.research_log

    def test_process_research_response(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "aiAgentData": {
                        "response": "# Report\nFindings...",
                    },
                }
            ),
            result,
        )
        assert "# Report" in result.text

    def test_process_final_content(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        client._process_event(
            json.dumps(
                {
                    "status": "READY",
                    "message": {
                        "id": "msg-1",
                        "model": "GigaChat-3-Ultra",
                        "content": [
                            {
                                "value": "Final answer here",
                                "markup": [
                                    {
                                        "key": "1",
                                        "title": "Src",
                                        "url": "https://src.com",
                                    }
                                ],
                            }
                        ],
                    },
                }
            ),
            result,
        )
        assert result.text == "Final answer here"
        assert result.model == "GigaChat-3-Ultra"
        assert len(result.citations) == 1

    def test_skip_function_in_progress(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "FUNCTION_IN_PROGRESS",
                            "frontendData": {},
                        }
                    ],
                }
            ),
            result,
        )
        assert result.text == ""

    def test_dedup_citations(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        event = json.dumps(
            {
                "status": "IN_PROGRESS",
                "contentDelta": [
                    {
                        "role": "ASSISTANT",
                        "delta": "text",
                        "markup": [
                            {"key": "1", "title": "S", "url": "https://a.com"},
                        ],
                    }
                ],
            }
        )
        client._process_event(event, result)
        client._process_event(event, result)
        assert len(result.citations) == 1

    def test_non_json_data_ignored(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        client._process_event(":keep-alive", result)
        assert result.text == ""
