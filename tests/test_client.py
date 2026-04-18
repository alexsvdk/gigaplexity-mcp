"""Unit tests for GigaChat client (mocked HTTP)."""

import json

import pytest

from gigaplexity.client import GigaChatClient, _EventMetrics, _StreamingProgressTracker
from gigaplexity.config import GigaplexitySettings
from gigaplexity.models import SearchMode


def _make_settings(**overrides) -> GigaplexitySettings:
    defaults = {
        "cookies": None,
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
        tool_names = client._process_event(
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
        assert tool_names == []

    def test_function_in_progress_tool_name_extracted_from_frontend_data(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        tool_names = client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "FUNCTION_IN_PROGRESS",
                            "frontendData": {
                                "function": {
                                    "name": "web_search",
                                }
                            },
                        }
                    ],
                }
            ),
            result,
        )
        assert result.text == ""
        assert tool_names == ["web_search"]

    def test_function_in_progress_tool_name_extracted_from_value(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="")
        tool_names = client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "FUNCTION_IN_PROGRESS",
                            "value": "web_search",
                        }
                    ],
                }
            ),
            result,
        )
        assert result.text == ""
        assert tool_names == ["web_search"]

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


class TestProgressTracker:
    def test_research_jumps_to_milestone_on_generation_start(self):
        tracker = _StreamingProgressTracker(SearchMode.RESEARCH)

        updates = tracker.update(
            _EventMetrics(status="IN_PROGRESS", tool_names=[], generated_chars=0, started_generating=False)
        )
        assert updates
        assert updates[-1][0] < 0.70

        updates = tracker.update(
            _EventMetrics(
                status="IN_PROGRESS",
                tool_names=[],
                generated_chars=0,
                generated_text="prefix </details> summary",
                started_generating=True,
            )
        )
        assert updates
        assert any(message == "Summarizing" for _, message in updates)
        assert any(progress == pytest.approx(0.70) for progress, _ in updates)

    def test_generation_progress_eases_and_stays_below_cap_until_ready(self):
        tracker = _StreamingProgressTracker(SearchMode.RESEARCH)

        tracker.update(
            _EventMetrics(status="IN_PROGRESS", tool_names=[], generated_chars=0, started_generating=True)
        )

        tracker.update(
            _EventMetrics(
                status="IN_PROGRESS",
                tool_names=[],
                generated_chars=0,
                generated_text="before </details> ",
                started_generating=False,
            )
        )

        first = tracker.update(
            _EventMetrics(
                status="IN_PROGRESS",
                tool_names=[],
                generated_chars=5000,
                generated_text="summary part 1",
                started_generating=False,
            )
        )
        second = tracker.update(
            _EventMetrics(
                status="IN_PROGRESS",
                tool_names=[],
                generated_chars=5000,
                generated_text="summary part 2",
                started_generating=False,
            )
        )
        third = tracker.update(
            _EventMetrics(
                status="IN_PROGRESS",
                tool_names=[],
                generated_chars=5000,
                generated_text="summary part 3",
                started_generating=False,
            )
        )

        first_progress = first[-1][0]
        second_progress = second[-1][0]
        third_progress = third[-1][0]

        assert 0.70 < first_progress < 0.96
        assert first_progress < second_progress < third_progress < 0.96

        gap1 = second_progress - first_progress
        gap2 = third_progress - second_progress
        assert gap2 < gap1

    def test_ready_sets_progress_to_one(self):
        tracker = _StreamingProgressTracker(SearchMode.ASK)

        tracker.update(
            _EventMetrics(status="IN_PROGRESS", tool_names=["web_search"], generated_chars=120, started_generating=True)
        )
        updates = tracker.update(
            _EventMetrics(status="READY", tool_names=[], generated_chars=0, started_generating=False)
        )

        assert updates
        assert updates[-1][0] == pytest.approx(1.0)
        assert updates[-1][1] == "Completed"


class TestResearchCleanup:
    def test_cleanup_removes_details_block_and_duplicated_log_prefix(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(
            text=(
                "<details><summary>Research Log</summary>\n"
                "internal progress\n"
                "</details>\n\n"
                "Conducting initial research on the following query: q\n"
                "step1\n"
                "step2\n"
                "# Final heading\n"
                "Final answer body"
            ),
            mode=SearchMode.RESEARCH,
            research_log=(
                "Conducting initial research on the following query: q\n"
                "step1\n"
                "step2"
            ),
        )

        client._cleanup_result_text(result)
        assert result.text.startswith("# Final heading")
        assert "<details" not in result.text.lower()
        assert "Conducting initial research on the following query:" not in result.text


class TestResearchDedup:
    def test_research_event_dedups_ai_agent_response_when_assistant_delta_present(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="", mode=SearchMode.RESEARCH)
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "ASSISTANT",
                            "delta": "# Research Report\nBody",
                            "markup": [],
                        }
                    ],
                    "aiAgentData": {
                        "response": "# Research Report\nBody",
                    },
                }
            ),
            result,
        )

        assert result.text == "# Research Report\nBody"
        assert result.text.count("# Research Report") == 1

    def test_research_event_uses_ai_agent_response_as_fallback(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="", mode=SearchMode.RESEARCH)
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "FUNCTION_IN_PROGRESS",
                            "frontendData": {"function": {"name": "web_search"}},
                        }
                    ],
                    "aiAgentData": {
                        "response": "# Research Report\nBody",
                    },
                }
            ),
            result,
        )

        assert result.text == "# Research Report\nBody"

    def test_ask_mode_keeps_both_channels_for_compatibility(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="", mode=SearchMode.ASK)
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "contentDelta": [
                        {
                            "role": "ASSISTANT",
                            "delta": "A",
                            "markup": [],
                        }
                    ],
                    "aiAgentData": {
                        "response": "B",
                    },
                }
            ),
            result,
        )

        assert result.text == "AB"

    def test_merge_text_uses_cumulative_snapshot_instead_of_dup_append(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="", mode=SearchMode.RESEARCH)

        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "aiAgentData": {
                        "response": "partial text",
                    },
                }
            ),
            result,
        )
        client._process_event(
            json.dumps(
                {
                    "status": "IN_PROGRESS",
                    "aiAgentData": {
                        "response": "partial text and more",
                    },
                }
            ),
            result,
        )

        assert result.text == "partial text and more"

    def test_cleanup_strips_prefixed_log_when_report_heading_in_same_line(self):
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(
            text=(
                "Conducting initial research on the following query: test"
                "...✍️ Generating report..."
                "# Research Report: Test\n\n"
                "## Abstract\n"
                "Body"
            ),
            mode=SearchMode.RESEARCH,
            research_log="Conducting initial research on the following query: test",
        )

        client._cleanup_result_text(result)
        assert result.text.startswith("# Research Report: Test")
        assert "Conducting initial research" not in result.text

    def test_ready_event_research_uses_last_report_not_concatenation(self):
        """READY message.content may contain the report twice (draft + published).
        Only the last report should be used."""
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="", mode=SearchMode.RESEARCH)

        # Simulate the READY event with log entries + report + log + report
        ready_event = {
            "status": "READY",
            "message": {
                "content": [
                    {"value": "Conducting initial research..."},
                    {"value": "🔍 Searching..."},
                    {"value": "✍️ Generating report..."},
                    {"value": "## Report Title\n\nDraft body"},
                    {"value": "📝 Report generated"},
                    {"value": "Publishing the final research report..."},
                    {"value": "## Report Title\n\nFinal body with edits"},
                ],
            },
        }
        client._process_event(json.dumps(ready_event), result)

        assert result.text == "## Report Title\n\nFinal body with edits"
        assert result.text.count("## Report Title") == 1

    def test_cleanup_handles_duplicate_report_body(self):
        """If text somehow contains the report body twice, keep only the last."""
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(
            text=(
                "# Research Report: Test\n\n## Abstract\nBody\n"
                "📝 Report generated\nPublishing the final research report...\n"
                "# Research Report: Test\n\n## Abstract\nBody\n"
            ),
            mode=SearchMode.RESEARCH,
        )

        client._cleanup_result_text(result)
        assert result.text.count("# Research Report: Test") == 1
        assert result.text.startswith("# Research Report: Test")

    def test_ready_event_research_uses_last_report_not_concatenation(self):
        """READY message.content may contain the report twice (draft + published).
        Only the last report should be used."""
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(text="", mode=SearchMode.RESEARCH)

        # Simulate the READY event with log entries + report + log + report
        ready_event = {
            "status": "READY",
            "message": {
                "content": [
                    {"value": "Conducting initial research..."},
                    {"value": "🔍 Searching..."},
                    {"value": "✍️ Generating report..."},
                    {"value": "## Report Title\n\nDraft body"},
                    {"value": "📝 Report generated"},
                    {"value": "Publishing the final research report..."},
                    {"value": "## Report Title\n\nFinal body with edits"},
                ],
            },
        }
        client._process_event(json.dumps(ready_event), result)

        assert result.text == "## Report Title\n\nFinal body with edits"
        assert result.text.count("## Report Title") == 1

    def test_cleanup_handles_duplicate_report_body(self):
        """If text somehow contains the report body twice, keep only the last."""
        client = GigaChatClient(_make_settings())
        from gigaplexity.models import SearchResult

        result = SearchResult(
            text=(
                "# Research Report: Test\n\n## Abstract\nBody\n"
                "📝 Report generated\nPublishing the final research report...\n"
                "# Research Report: Test\n\n## Abstract\nBody\n"
            ),
            mode=SearchMode.RESEARCH,
        )

        client._cleanup_result_text(result)
        assert result.text.count("# Research Report: Test") == 1
        assert result.text.startswith("# Research Report: Test")
