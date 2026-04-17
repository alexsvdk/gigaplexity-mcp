"""GigaChat HTTP client with SSE streaming support."""

from __future__ import annotations

import json
import logging
import uuid

import httpx
from httpx_sse import aconnect_sse

from gigaplexity.config import GigaplexitySettings
from gigaplexity.models import (
    Citation,
    ReasoningStep,
    SearchMode,
    SearchResult,
    build_request_payload,
)

logger = logging.getLogger(__name__)


class GigaChatError(Exception):
    """Raised when the GigaChat API returns an error."""

REQUEST_ENDPOINT = "/api/giga-back-web/api/v0/sessions/request"
DEFAULT_TIMEOUT = 120.0


class GigaChatClient:
    """Async client for GigaChat web search API."""

    def __init__(self, settings: GigaplexitySettings) -> None:
        self.settings = settings
        self._http: httpx.AsyncClient | None = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self.settings.base_url,
                timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=10.0),
                follow_redirects=True,
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    def _new_request_id(self) -> str:
        return str(uuid.uuid4())

    def _new_session_id(self) -> str:
        return str(uuid.uuid4())

    async def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.ASK,
        *,
        domains: list[str] | None = None,
        extended_research: bool = False,
        tone: str = "",
    ) -> SearchResult:
        """Execute a search query and return aggregated results."""
        session_id = self._new_session_id()
        request_id = self._new_request_id()
        headers = self.settings.build_headers(request_id)
        payload = build_request_payload(
            query,
            mode,
            session_id,
            domains=domains,
            extended_research=extended_research,
            tone=tone,
        )

        logger.debug("Sending %s request: %s", mode.value, query[:80])
        http = await self._get_http()

        result = SearchResult(
            text="",
            mode=mode,
            session_id=session_id,
        )

        # Use streaming request so SSE events arrive incrementally
        async with http.stream(
            "POST",
            REQUEST_ENDPOINT,
            json=payload,
            headers=headers,
        ) as response:
            content_type = response.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                # Non-streaming response — likely an error (auth failure, etc.)
                await response.aread()
                try:
                    error_body = response.json()
                    error_msg = (
                        error_body.get("message")
                        or error_body.get("error")
                        or str(error_body)
                    )
                except Exception:
                    error_msg = response.text[:500]
                raise GigaChatError(
                    f"API error (HTTP {response.status_code}): {error_msg}"
                )

            # Parse SSE stream
            from httpx_sse import EventSource

            event_source = EventSource(response)
            async for event in event_source.aiter_sse():
                if event.data:
                    self._process_event(event.data, result)

        return result

    def _process_event(self, raw_data: str, result: SearchResult) -> None:
        """Process a single SSE event and update the result."""
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.debug("Non-JSON SSE data: %s", raw_data[:100])
            return

        status = data.get("status")

        # Extract message ID from initial event
        message = data.get("message", {})
        if message.get("id") and not result.message_id:
            result.message_id = message["id"]

        # Extract model from final message
        if message.get("model"):
            result.model = message["model"]

        # Process content deltas (streaming text)
        for delta in data.get("contentDelta", []):
            self._process_delta(delta, result)

        # Process reasoning steps (reason mode)
        for step in data.get("reasoningSteps", []):
            result.reasoning_steps.append(
                ReasoningStep(
                    type=step.get("type", "TEXT"),
                    value=step.get("value", ""),
                )
            )

        # Process reasoning deltas
        reasoning_delta = data.get("reasoningDelta")
        if reasoning_delta:
            if result.reasoning_steps:
                result.reasoning_steps[-1].value += reasoning_delta
            else:
                result.reasoning_steps.append(
                    ReasoningStep(type="TEXT", value=reasoning_delta)
                )

        # Process research agent data
        ai_agent_data = data.get("aiAgentData", {})
        reasoning_log = ai_agent_data.get("reasoning")
        if reasoning_log:
            if isinstance(reasoning_log, list):
                for entry in reasoning_log:
                    log_text = entry.get("log", "") if isinstance(entry, dict) else str(entry)
                    if log_text:
                        result.research_log += log_text + "\n"
            elif isinstance(reasoning_log, str):
                result.research_log += reasoning_log + "\n"

        # Process research response delta
        response_delta = ai_agent_data.get("response")
        if response_delta:
            if isinstance(response_delta, list):
                for entry in response_delta:
                    text = entry.get("text", "") if isinstance(entry, dict) else str(entry)
                    if text:
                        result.text += text
            elif isinstance(response_delta, str):
                result.text += response_delta

        # Process final content (when status is READY)
        if status == "READY" and message.get("content"):
            # Only use final content if we didn't accumulate via deltas
            if not result.text:
                for content_item in message["content"]:
                    value = content_item.get("value", "")
                    if value:
                        result.text += value
                    # Extract citations from final content
                    for markup in content_item.get("markup", []):
                        if markup.get("url"):
                            citation = Citation(
                                key=str(markup.get("key", "")),
                                title=markup.get("title", ""),
                                url=markup["url"],
                                type=markup.get("type", "FOOTNOTE"),
                            )
                            if not any(c.url == citation.url for c in result.citations):
                                result.citations.append(citation)

    def _process_delta(self, delta: dict, result: SearchResult) -> None:
        """Process a single content delta."""
        role = delta.get("role", "")

        if role == "FUNCTION_IN_PROGRESS":
            # Function call in progress (e.g. web_search) — skip
            return

        text = delta.get("delta", "") or delta.get("value", "")
        if text and role in ("ASSISTANT", ""):
            result.text += text

        # Extract citations from markup
        for markup in delta.get("markup", []):
            if markup.get("url"):
                citation = Citation(
                    key=str(markup.get("key", "")),
                    title=markup.get("title", ""),
                    url=markup["url"],
                    type=markup.get("type", "FOOTNOTE"),
                )
                if not any(c.url == citation.url for c in result.citations):
                    result.citations.append(citation)
