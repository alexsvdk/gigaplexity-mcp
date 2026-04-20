"""Tests for search() retry-on-auth-failure flow."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from gigaplexity.client import GigaChatClient, GigaChatError
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


def _sse_body(*events: dict) -> bytes:
    """Build raw SSE bytes from event dicts."""
    parts: list[bytes] = []
    for e in events:
        parts.append(b"data: " + json.dumps(e).encode() + b"\n\n")
    return b"".join(parts)


def _success_sse() -> bytes:
    return _sse_body(
        {"status": "IN_PROGRESS", "contentDelta": [{"role": "ASSISTANT", "delta": "Hello"}]},
        {"status": "READY", "message": {"id": "m1", "content": []}},
    )


def _mock_http_with_stream(stream_fn) -> MagicMock:
    """Create a mock httpx.AsyncClient whose .stream() returns context managers."""
    mock_http = MagicMock(spec=httpx.AsyncClient)
    mock_http.stream = stream_fn  # regular function, returns ctx manager
    mock_http.is_closed = False
    # Make _get_http() return this mock
    return mock_http


class _FakeStreamContext:
    """Fake async context manager for httpx.stream()."""

    def __init__(self, response, *, is_streaming: bool):
        self._response = response
        self._is_streaming = is_streaming

    async def __aenter__(self):
        if self._is_streaming:
            return _FakeStreamingResponse(self._response)
        return self._response

    async def __aexit__(self, *args):
        pass


class _FakeStreamingResponse:
    """Wraps an httpx.Response to support async text iteration for SSE."""

    def __init__(self, response):
        self._content = response.content
        self.status_code = response.status_code
        self.headers = response.headers

    async def aread(self):
        return self._content

    @property
    def text(self):
        return self._content.decode()

    def json(self):
        return json.loads(self._content)

    async def aiter_bytes(self):
        yield self._content

    async def aiter_text(self):
        yield self._content.decode()


def _error_response(status_code: int, message: str = "Error") -> _FakeStreamContext:
    return _FakeStreamContext(
        httpx.Response(
            status_code=status_code,
            headers=[("content-type", "application/json")],
            content=json.dumps({"message": message}).encode(),
            request=httpx.Request("POST", "https://giga.chat/api/test"),
        ),
        is_streaming=False,
    )


def _success_response(body: bytes | None = None) -> _FakeStreamContext:
    return _FakeStreamContext(
        httpx.Response(
            status_code=200,
            headers=[("content-type", "text/event-stream")],
            content=body or _success_sse(),
            request=httpx.Request("POST", "https://giga.chat/api/test"),
        ),
        is_streaming=True,
    )


# --------------------------------------------------------------------------
# Retry tests
# --------------------------------------------------------------------------

class TestSearchRetryOnAuth:
    """Verify that search() retries once on 401/403 after refreshing."""

    @pytest.mark.asyncio
    async def test_retries_on_401_then_succeeds(self):
        settings = _make_settings()
        client = GigaChatClient(settings)

        force_refresh_calls = 0

        async def mock_force_refresh(http):
            nonlocal force_refresh_calls
            force_refresh_calls += 1
            client._token_manager._current_cookies = "_sm_sess=fresh; _sm_user_id=uid"
            client._token_manager._last_refresh = time.monotonic()
            return True

        client._token_manager.force_refresh = mock_force_refresh
        client._token_manager._last_refresh = time.monotonic()

        call_count = 0

        def stream_fn(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _error_response(401, "Unauthorized")
            return _success_response()

        client._http = _mock_http_with_stream(stream_fn)

        result = await client.search("test query", SearchMode.ASK)

        assert call_count == 2
        assert force_refresh_calls == 1
        assert result.text == "Hello"

    @pytest.mark.asyncio
    async def test_retries_on_403_then_succeeds(self):
        settings = _make_settings()
        client = GigaChatClient(settings)

        async def mock_force_refresh(http):
            client._token_manager._current_cookies = "_sm_sess=fresh; _sm_user_id=uid"
            client._token_manager._last_refresh = time.monotonic()
            return True

        client._token_manager.force_refresh = mock_force_refresh
        client._token_manager._last_refresh = time.monotonic()

        call_count = 0

        def stream_fn(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _error_response(403, "Forbidden")
            return _success_response()

        client._http = _mock_http_with_stream(stream_fn)

        result = await client.search("test query", SearchMode.ASK)
        assert call_count == 2
        assert result.text == "Hello"

    @pytest.mark.asyncio
    async def test_does_not_retry_more_than_once(self):
        settings = _make_settings()
        client = GigaChatClient(settings)

        async def mock_force_refresh(http):
            client._token_manager._current_cookies = "_sm_sess=still-bad"
            return True

        client._token_manager.force_refresh = mock_force_refresh
        client._token_manager._last_refresh = time.monotonic()

        def stream_fn(method, url, **kwargs):
            return _error_response(401, "Unauthorized")

        client._http = _mock_http_with_stream(stream_fn)

        with pytest.raises(GigaChatError, match="401"):
            await client.search("test query", SearchMode.ASK)

    @pytest.mark.asyncio
    async def test_no_retry_if_refresh_fails(self):
        settings = _make_settings()
        client = GigaChatClient(settings)

        async def mock_force_refresh(http):
            return False  # refresh failed

        client._token_manager.force_refresh = mock_force_refresh
        client._token_manager._last_refresh = time.monotonic()

        call_count = 0

        def stream_fn(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return _error_response(401, "Unauthorized")

        client._http = _mock_http_with_stream(stream_fn)

        with pytest.raises(GigaChatError, match="401"):
            await client.search("test query", SearchMode.ASK)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_500(self):
        """500 errors should not trigger auth retry."""
        settings = _make_settings()
        client = GigaChatClient(settings)
        client._token_manager._last_refresh = time.monotonic()

        call_count = 0

        def stream_fn(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return _error_response(500, "Internal Server Error")

        client._http = _mock_http_with_stream(stream_fn)

        with pytest.raises(GigaChatError, match="500"):
            await client.search("test query", SearchMode.ASK)

        assert call_count == 1


class TestProactiveRefreshOnSearch:
    """Verify ensure_valid_token is called before every search."""

    @pytest.mark.asyncio
    async def test_ensure_valid_token_called_before_request(self):
        settings = _make_settings()
        client = GigaChatClient(settings)

        ensure_called = False

        async def mock_ensure(http):
            nonlocal ensure_called
            ensure_called = True

        client._token_manager.ensure_valid_token = mock_ensure

        def stream_fn(method, url, **kwargs):
            return _success_response()

        client._http = _mock_http_with_stream(stream_fn)

        await client.search("test", SearchMode.ASK)
        assert ensure_called is True
