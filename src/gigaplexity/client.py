"""GigaChat HTTP client with SSE streaming support."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import json
import logging
import math
import mimetypes
import re
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx

from gigaplexity.config import GigaplexitySettings
from gigaplexity.models import (
    AttachmentInfo,
    Citation,
    FileCategory,
    ReasoningStep,
    SearchMode,
    SearchResult,
    build_request_payload,
    resolve_file_type,
)

logger = logging.getLogger(__name__)


def _get_audio_duration(path: Path) -> float | None:
    """Try to determine audio duration in seconds (best-effort for WAV)."""
    import struct
    import wave

    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / rate
    except Exception:
        pass
    return None


class GigaChatError(Exception):
    """Raised when the GigaChat API returns an error."""

REQUEST_ENDPOINT = "/api/giga-back-web/api/v0/sessions/request"
OTR_ENDPOINT = "/api/attachments/api/v0/gc/otr"
UPLOAD_ENDPOINT = "/api/attachments-upload/api/v0/gc/otr"
DEFAULT_TIMEOUT = 120.0


@dataclass
class _EventMetrics:
    """Metrics extracted from one parsed SSE event."""

    status: str = ""
    tool_names: list[str] | None = None
    generated_chars: int = 0
    generated_text: str = ""
    started_generating: bool = False


class _StreamingProgressTracker:
    """Phase-based progress tracker with slow easing near milestones."""

    _EXPECTED_OUTPUT_CHARS: dict[SearchMode, int] = {
        SearchMode.ASK: 1400,
        SearchMode.REASON: 600,
        SearchMode.RESEARCH: 18000,
    }

    _GENERATION_START_MILESTONE: dict[SearchMode, float] = {
        SearchMode.ASK: 0.45,
        SearchMode.REASON: 0.55,
        SearchMode.RESEARCH: 0.70,
    }

    _GENERATION_CAP: dict[SearchMode, float] = {
        SearchMode.ASK: 0.93,
        SearchMode.REASON: 0.94,
        SearchMode.RESEARCH: 0.96,
    }

    def __init__(self, mode: SearchMode) -> None:
        self.mode = mode
        self.progress = 0.0
        self.last_emitted_progress = -1.0
        self.last_emitted_message = ""
        self.event_count = 0
        self.generated_chars_total = 0
        self.seen_tool_names: set[str] = set()
        self.research_details_closed = mode != SearchMode.RESEARCH
        self._details_tag_tail = ""

        self.expected_chars = self._EXPECTED_OUTPUT_CHARS.get(mode, 1200)
        self.generation_start_milestone = self._GENERATION_START_MILESTONE.get(mode, 0.5)
        self.generation_cap = self._GENERATION_CAP.get(mode, 0.95)

    def update(self, metrics: _EventMetrics) -> list[tuple[float, str]]:
        updates: list[tuple[float, str]] = []
        status = metrics.status

        if status == "ACCEPTED":
            maybe = self._emit(0.03, "Request accepted")
            if maybe:
                updates.append(maybe)

        if status == "IN_PROGRESS":
            self.event_count += 1
            if self.mode == SearchMode.RESEARCH and not self.research_details_closed:
                pre_summary_cap = self.generation_start_milestone - 0.02
                thinking_target = pre_summary_cap * (1 - math.exp(-0.05 * self.event_count))
                maybe = self._emit(thinking_target, "Researching")
            else:
                thinking_target = self.generation_start_milestone * (1 - math.exp(-0.18 * self.event_count))
                maybe = self._emit(thinking_target, "Analyzing sources")
            if maybe:
                updates.append(maybe)

        for tool_name in metrics.tool_names or []:
            if tool_name in self.seen_tool_names:
                continue
            self.seen_tool_names.add(tool_name)
            if self.mode == SearchMode.RESEARCH and not self.research_details_closed:
                max_before_summary = self.generation_start_milestone - 0.02
                target = max(self.progress, min(max_before_summary, self.progress + 0.02))
            else:
                target = max(self.progress, min(self.generation_start_milestone - 0.05, self.progress + 0.08))
            maybe = self._emit(target, f"Calling {tool_name}")
            if maybe:
                updates.append(maybe)

        summary_chars = metrics.generated_chars
        if self.mode == SearchMode.RESEARCH and not self.research_details_closed:
            closed, chars_after_close = self._detect_research_details_closed(metrics.generated_text)
            summary_chars = 0
            if closed:
                self.research_details_closed = True
                summary_chars = chars_after_close
                maybe = self._emit(self.generation_start_milestone, "Summarizing")
                if maybe:
                    updates.append(maybe)

        if self.mode == SearchMode.RESEARCH and self.research_details_closed and self.progress < self.generation_start_milestone:
            maybe = self._emit(self.generation_start_milestone, "Summarizing")
            if maybe:
                updates.append(maybe)

        if metrics.started_generating and (self.mode != SearchMode.RESEARCH or self.research_details_closed):
            maybe = self._emit(self.generation_start_milestone, "Generating final response")
            if maybe:
                updates.append(maybe)

        if summary_chars > 0:
            self.generated_chars_total += summary_chars
            ratio = self.generated_chars_total / max(1, self.expected_chars)
            eased = 1 - math.exp(-3.0 * ratio)
            target = self.generation_start_milestone + (
                self.generation_cap - self.generation_start_milestone
            ) * eased
            message = "Summarizing" if self.mode == SearchMode.RESEARCH else "Generating final response"
            maybe = self._emit(target, message)
            if maybe:
                updates.append(maybe)

        if status == "READY":
            maybe = self._emit(1.0, "Completed")
            if maybe:
                updates.append(maybe)

        return updates

    def _emit(self, target_progress: float, message: str) -> tuple[float, str] | None:
        next_progress = max(self.progress, min(1.0, target_progress))
        progress_diff = next_progress - self.last_emitted_progress

        should_emit = (
            self.last_emitted_progress < 0
            or progress_diff >= 0.01
            or message != self.last_emitted_message
            or next_progress >= 1.0
        )
        if not should_emit:
            self.progress = next_progress
            return None

        self.progress = next_progress
        self.last_emitted_progress = next_progress
        self.last_emitted_message = message
        return next_progress, message

    def _detect_research_details_closed(self, generated_text: str) -> tuple[bool, int]:
        """Detect if `</details>` appears in streamed text and count chars after it."""
        if not generated_text:
            return False, 0

        combined = self._details_tag_tail + generated_text
        marker = "</details>"
        lower_combined = combined.lower()
        marker_index = lower_combined.find(marker)

        self._details_tag_tail = combined[-32:]
        if marker_index < 0:
            return False, 0

        after_marker = combined[marker_index + len(marker):]
        chars_after = len(after_marker)
        return True, chars_after


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

    async def _create_otr(self, file_type: str) -> dict:
        """Create an OTR (one-time record) for a file upload.

        Returns dict with ``otrId`` and ``rootId``.
        """
        http = await self._get_http()
        request_id = self._new_request_id()
        headers = self.settings.build_headers(request_id)
        headers["Accept"] = "application/json, text/plain, */*"
        headers["Content-Type"] = "application/json"

        resp = await http.post(
            OTR_ENDPOINT,
            json={"fileType": file_type},
            headers=headers,
        )
        if resp.status_code != 201:
            raise GigaChatError(
                f"Failed to create OTR (HTTP {resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    async def _upload_file(
        self,
        otr_id: str,
        file_path: Path,
        mime_type: str,
    ) -> dict:
        """Upload a file to an existing OTR slot.

        Returns dict with ``attachmentId``, ``key``, ``hash``, etc.
        """
        http = await self._get_http()
        request_id = self._new_request_id()
        headers = self.settings.build_headers(request_id)
        headers["Accept"] = "application/json, text/plain, */*"
        # Remove JSON content-type — httpx will set multipart
        headers.pop("Content-Type", None)

        file_size = file_path.stat().st_size
        headers["x-file-size"] = str(file_size)
        headers["x-file-type"] = mime_type
        headers["x-file-name"] = quote(file_path.name)
        headers["requestid"] = str(uuid.uuid4())

        # The browser sends a random UUID + extension (no dot) as filename
        ext = file_path.suffix.lstrip(".")
        upload_filename = f"{uuid.uuid4()}{ext}"

        with open(file_path, "rb") as f:
            files = {"file": (upload_filename, f, "application/octet-stream")}
            resp = await http.post(
                f"{UPLOAD_ENDPOINT}/{otr_id}",
                files=files,
                headers=headers,
            )

        if resp.status_code != 201:
            raise GigaChatError(
                f"Failed to upload file (HTTP {resp.status_code}): {resp.text[:300]}"
            )
        return resp.json()

    async def upload_files(self, file_paths: list[str]) -> list[AttachmentInfo]:
        """Upload files and return attachment metadata for use in a search request.

        All files must belong to the same category (DOC, IMAGE, or AUDIO).

        Raises:
            ValueError: If files span multiple categories or extension is unsupported.
            GigaChatError: On API errors.
        """
        if not file_paths:
            return []

        infos: list[AttachmentInfo] = []
        categories: set[FileCategory] = set()

        for fp in file_paths:
            path = Path(fp)
            if not path.is_file():
                raise ValueError(f"File not found: {fp}")
            ext = path.suffix.lstrip(".")
            if not ext:
                raise ValueError(f"Cannot determine file type (no extension): {fp}")
            _, cat = resolve_file_type(ext)
            categories.add(cat)

        if len(categories) > 1:
            raise ValueError(
                f"All files must be of the same category. "
                f"Got mixed categories: {', '.join(c.value for c in categories)}. "
                f"GigaChat only allows files of one type per request "
                f"(e.g. only documents, only images, or only audio)."
            )

        for fp in file_paths:
            path = Path(fp)
            ext = path.suffix.lstrip(".")
            file_type, category = resolve_file_type(ext)

            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

            otr = await self._create_otr(file_type)
            otr_id = otr["otrId"]
            logger.debug("Created OTR %s for %s (%s)", otr_id, path.name, file_type)

            upload_resp = await self._upload_file(otr_id, path, mime_type)
            logger.debug("Uploaded %s → %s", path.name, upload_resp.get("key"))

            # For audio files, try to read duration
            audio_duration: float | None = None
            if category == FileCategory.AUDIO:
                audio_duration = _get_audio_duration(path)

            infos.append(
                AttachmentInfo(
                    hash=upload_resp["hash"],
                    key=upload_resp["key"],
                    category=category,
                    audio_duration=audio_duration,
                )
            )

        return infos

    async def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.ASK,
        *,
        domains: list[str] | None = None,
        extended_research: bool = False,
        tone: str = "",
        attachments: list[AttachmentInfo] | None = None,
        on_progress: Callable[[float, str], Awaitable[None]] | None = None,
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
            attachments=attachments,
        )

        logger.debug("Sending %s request: %s", mode.value, query[:80])
        http = await self._get_http()

        result = SearchResult(
            text="",
            mode=mode,
            session_id=session_id,
        )

        # Use streaming request so SSE events arrive incrementally
        progress_tracker = _StreamingProgressTracker(mode)
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
                    try:
                        data = json.loads(event.data)
                    except json.JSONDecodeError:
                        logger.debug("Non-JSON SSE data: %s", event.data[:100])
                        continue

                    before_text_len = len(result.text)
                    tool_names = self._process_event_data(data, result)
                    generated_text = result.text[before_text_len:]
                    generated_chars = len(generated_text)

                    metrics = _EventMetrics(
                        status=str(data.get("status") or ""),
                        tool_names=tool_names,
                        generated_chars=generated_chars,
                        generated_text=generated_text,
                        started_generating=before_text_len == 0 and len(result.text) > 0,
                    )

                    if on_progress:
                        for progress, message in progress_tracker.update(metrics):
                            await on_progress(progress, message)

        self._cleanup_result_text(result)
        return result

    def _cleanup_result_text(self, result: SearchResult) -> None:
        """Remove duplicated research-progress text from final body."""
        if result.mode != SearchMode.RESEARCH or not result.text:
            return

        text = result.text

        # 1. Strip <details> blocks
        while True:
            stripped = text.lstrip()
            if not stripped.lower().startswith("<details"):
                break
            end_index = stripped.lower().find("</details>")
            if end_index < 0:
                break
            text = stripped[end_index + len("</details>"):].lstrip()

        # 2. Strip research_log prefix
        log = result.research_log.strip()
        stripped_text = text.lstrip()
        if log and stripped_text.startswith(log):
            text = stripped_text[len(log):].lstrip()
            stripped_text = text.lstrip()

        # 3. Find the last markdown heading that looks like a report start.
        #    This handles both cases: log prefix before report, and
        #    report appearing twice (draft + published).
        report_markers = ["# Research Report", "## Research Report"]
        last_report_pos = -1
        for marker in report_markers:
            pos = stripped_text.rfind(marker)
            if pos > last_report_pos:
                last_report_pos = pos

        if last_report_pos > 0:
            # There's a report heading not at the very start — check if
            # the text before it contains log/progress markers
            prefix = stripped_text[:last_report_pos]
            has_log_markers = any(
                m in prefix
                for m in (
                    "Conducting initial research",
                    "Generating report",
                    "Report generated",
                    "Publishing the final research report",
                )
            )
            # Also treat it as a duplicate if the same heading exists earlier
            first_pos = -1
            for marker in report_markers:
                pos = stripped_text.find(marker)
                if pos >= 0 and (first_pos < 0 or pos < first_pos):
                    first_pos = pos
            has_duplicate = first_pos >= 0 and first_pos < last_report_pos

            if has_log_markers or has_duplicate:
                text = stripped_text[last_report_pos:].lstrip()
                result.text = text
                return

        # 4. Fallback: find any markdown heading after log-like prefix
        if stripped_text.startswith("Conducting initial research on the following query:"):
            heading_match = re.search(r"(?m)^#{1,6}\s", stripped_text)
            if heading_match:
                text = stripped_text[heading_match.start():].lstrip()
                result.text = text
                return

        # 5. Handle inline log prefix before heading (no newline)
        heading_match = re.search(r"#{1,6}\s", stripped_text)
        if heading_match and heading_match.start() > 0:
            prefix = stripped_text[:heading_match.start()]
            if any(
                m in prefix
                for m in (
                    "Conducting initial research",
                    "Generating report",
                    "Report generated",
                    "Publishing",
                )
            ):
                text = stripped_text[heading_match.start():].lstrip()

        result.text = text

    def _merge_text(self, current: str, incoming: str) -> str:
        """Merge streamed text chunks handling both deltas and cumulative snapshots."""
        if not incoming:
            return current
        if not current:
            return incoming
        if incoming == current:
            return current
        if incoming.startswith(current):
            return incoming
        if current.endswith(incoming):
            return current
        return current + incoming

    def _process_event(self, raw_data: str, result: SearchResult) -> list[str]:
        """Process a single SSE event and update the result."""
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.debug("Non-JSON SSE data: %s", raw_data[:100])
            return []

        return self._process_event_data(data, result)

    def _process_event_data(self, data: dict, result: SearchResult) -> list[str]:
        """Process a parsed SSE event and update the result."""

        tool_names: list[str] = []
        assistant_delta_appended = False

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
            role = delta.get("role", "")
            text = delta.get("delta", "") or delta.get("value", "")
            if text and role in ("ASSISTANT", ""):
                assistant_delta_appended = True
            tool_name = self._process_delta(delta, result)
            if tool_name:
                tool_names.append(tool_name)

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
        should_append_response_delta = response_delta and not (
            result.mode == SearchMode.RESEARCH and assistant_delta_appended
        )
        if should_append_response_delta:
            if isinstance(response_delta, list):
                for entry in response_delta:
                    text = entry.get("text", "") if isinstance(entry, dict) else str(entry)
                    if text:
                        result.text = self._merge_text(result.text, text)
            elif isinstance(response_delta, str):
                result.text = self._merge_text(result.text, response_delta)

        # Process final content (when status is READY)
        if status == "READY" and message.get("content"):
            # Only use final content if we didn't accumulate via deltas
            if not result.text:
                if result.mode == SearchMode.RESEARCH:
                    # RESEARCH message.content contains log entries interleaved
                    # with report text. The report may appear twice (draft +
                    # published). Use only the last report-like item (starts
                    # with markdown heading) to avoid duplication.
                    last_report = ""
                    log_parts: list[str] = []
                    for content_item in message["content"]:
                        value = content_item.get("value", "")
                        if value:
                            stripped_val = value.strip()
                            if stripped_val.startswith("#"):
                                last_report = value
                            else:
                                log_parts.append(value)
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
                    if last_report:
                        result.text = last_report
                    else:
                        # Fallback: concatenate everything
                        for content_item in message["content"]:
                            value = content_item.get("value", "")
                            if value:
                                result.text = self._merge_text(result.text, value)
                    if log_parts and not result.research_log.strip():
                        result.research_log = "".join(log_parts)
                else:
                    for content_item in message["content"]:
                        value = content_item.get("value", "")
                        if value:
                            result.text = self._merge_text(result.text, value)
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

        return tool_names

    def _process_delta(self, delta: dict, result: SearchResult) -> str | None:
        """Process a single content delta."""
        role = delta.get("role", "")

        if role == "FUNCTION_IN_PROGRESS":
            return self._extract_tool_name(delta)

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

        return None

    def _extract_tool_name(self, delta: dict) -> str | None:
        """Best-effort extraction of in-progress function/tool name from delta payload."""
        candidate_sources: list[dict] = [delta]

        frontend_data = delta.get("frontendData")
        if isinstance(frontend_data, dict):
            candidate_sources.insert(0, frontend_data)
            nested_function = frontend_data.get("function")
            if isinstance(nested_function, dict):
                candidate_sources.insert(0, nested_function)

        for source in candidate_sources:
            for key in ("toolName", "functionName", "name", "tool"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        for key in ("value", "delta"):
            value = delta.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text

        return None
