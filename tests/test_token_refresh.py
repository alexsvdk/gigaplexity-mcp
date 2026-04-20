"""Unit tests for TokenRefreshManager — async token refresh logic."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gigaplexity.token_refresh import TokenRefreshManager, CHECK_ENDPOINT
from gigaplexity.token_store import TokenStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(
    *,
    original_token: str = "original-jwt-token",
    cookies: str = "_sm_sess=original-jwt-token; _sm_user_id=uid-123",
    base_url: str = "https://giga.chat",
    store: TokenStore | None = None,
    refresh_interval: float = 3600,
) -> TokenRefreshManager:
    return TokenRefreshManager(
        original_token=original_token,
        current_cookies=cookies,
        base_url=base_url,
        user_agent="test-agent",
        store=store,
        refresh_interval=refresh_interval,
    )


def _mock_check_response(
    *,
    status_code: int = 200,
    body: dict | None = None,
    set_cookies: dict[str, str] | None = None,
) -> httpx.Response:
    """Create a mock httpx.Response for /api/check."""
    if body is None:
        body = {"result": True, "internalNetwork": False, "invalidNetwork": False}

    raw_headers: list[tuple[str, str]] = [
        ("content-type", "application/json"),
    ]
    if set_cookies:
        for name, value in set_cookies.items():
            raw_headers.append(
                ("set-cookie", f"{name}={value}; Expires=Sun, 19 Jul 2026 22:08:19 GMT; Path=/api; HttpOnly; Secure")
            )

    import json as _json
    resp = httpx.Response(
        status_code=status_code,
        headers=raw_headers,
        content=_json.dumps(body).encode(),
        request=httpx.Request("GET", "https://giga.chat/api/check"),
    )
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTokenRefreshInit:
    def test_initial_cookies_stored(self):
        mgr = _make_manager()
        assert "_sm_sess=original-jwt-token" in mgr.current_cookies

    def test_restores_persisted_token(self, tmp_path: Path):
        store = TokenStore(tmp_path / "store.json")
        store.save_token("original-jwt-token", "persisted-fresh-token")

        mgr = _make_manager(store=store)
        assert "_sm_sess=persisted-fresh-token" in mgr.current_cookies

    def test_no_store_no_crash(self):
        mgr = _make_manager(store=None)
        assert mgr.current_cookies  # just has the initial cookies


class TestEnsureValidToken:
    @pytest.mark.asyncio
    async def test_skips_if_recently_refreshed(self):
        mgr = _make_manager(refresh_interval=3600)
        # Simulate a recent refresh
        mgr._last_refresh = time.monotonic()

        http = AsyncMock(spec=httpx.AsyncClient)
        await mgr.ensure_valid_token(http)
        # No HTTP call should have been made
        http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_refreshes_if_interval_elapsed(self):
        mgr = _make_manager(refresh_interval=0.0)  # always stale
        mgr._last_refresh = 0

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(return_value=_mock_check_response(
            set_cookies={"_sm_sess": "new-token", "_sm_user_id": "uid-123"}
        ))

        await mgr.ensure_valid_token(http)
        http.get.assert_called_once()
        assert "_sm_sess=new-token" in mgr.current_cookies

    @pytest.mark.asyncio
    async def test_no_duplicate_refresh_under_lock(self):
        """Double-check pattern: concurrent calls should only refresh once."""
        mgr = _make_manager(refresh_interval=3600)
        mgr._last_refresh = 0  # force stale

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(return_value=_mock_check_response(
            set_cookies={"_sm_sess": "new"}
        ))

        # Run two concurrent ensure_valid_token calls
        await asyncio.gather(
            mgr.ensure_valid_token(http),
            mgr.ensure_valid_token(http),
        )
        # Only one HTTP call should have been made (double-check pattern)
        assert http.get.call_count == 1


class TestForceRefresh:
    @pytest.mark.asyncio
    async def test_force_refresh_succeeds(self):
        mgr = _make_manager()

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(return_value=_mock_check_response(
            set_cookies={"_sm_sess": "force-refreshed"}
        ))

        result = await mgr.force_refresh(http)
        assert result is True
        assert "_sm_sess=force-refreshed" in mgr.current_cookies

    @pytest.mark.asyncio
    async def test_force_refresh_updates_last_refresh_time(self):
        mgr = _make_manager()
        assert mgr._last_refresh == 0.0

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(return_value=_mock_check_response())

        await mgr.force_refresh(http)
        assert mgr._last_refresh > 0

    @pytest.mark.asyncio
    async def test_force_refresh_persists_to_store(self, tmp_path: Path):
        store = TokenStore(tmp_path / "store.json")
        mgr = _make_manager(store=store)

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(return_value=_mock_check_response(
            set_cookies={"_sm_sess": "stored-fresh", "_sm_user_id": "uid"}
        ))

        await mgr.force_refresh(http)

        # Verify the store was updated
        assert store.get_fresh_token("original-jwt-token") == "stored-fresh"


class TestRefreshFailures:
    @pytest.mark.asyncio
    async def test_http_error_returns_false(self):
        mgr = _make_manager()

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(return_value=_mock_check_response(
            status_code=500,
            body={"error": "internal"},
        ))

        # httpx won't raise on status_code unless we call raise_for_status()
        # Our implementation calls raise_for_status(), so mock that
        resp = _mock_check_response(status_code=500, body={"error": "internal"})
        http.get = AsyncMock(return_value=resp)

        result = await mgr.force_refresh(http)
        assert result is False

    @pytest.mark.asyncio
    async def test_result_false_returns_false(self):
        mgr = _make_manager()

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(return_value=_mock_check_response(
            body={"result": False}
        ))

        result = await mgr.force_refresh(http)
        assert result is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        mgr = _make_manager()

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        result = await mgr.force_refresh(http)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_set_cookie_still_succeeds(self):
        """If the token is still fresh, server may not send Set-Cookie."""
        mgr = _make_manager()
        original_cookies = mgr.current_cookies

        http = AsyncMock(spec=httpx.AsyncClient)
        http.get = AsyncMock(return_value=_mock_check_response(
            set_cookies=None,  # no new cookies
        ))

        result = await mgr.force_refresh(http)
        assert result is True
        assert mgr.current_cookies == original_cookies  # unchanged


class TestCookieUpdating:
    def test_apply_token_replaces_existing(self):
        mgr = _make_manager(cookies="_sm_sess=old; _sm_user_id=uid; _gigachat_language=en")
        mgr._apply_token_to_cookies("new-jwt")
        assert "_sm_sess=new-jwt" in mgr.current_cookies
        assert "_sm_user_id=uid" in mgr.current_cookies
        assert "_gigachat_language=en" in mgr.current_cookies
        assert "old" not in mgr.current_cookies

    def test_apply_token_adds_if_missing(self):
        mgr = _make_manager(cookies="_sm_user_id=uid; _gigachat_language=en")
        mgr._apply_token_to_cookies("new-jwt")
        assert mgr.current_cookies.startswith("_sm_sess=new-jwt")

    def test_parse_set_cookies(self):
        """Test parsing of Set-Cookie headers from httpx.Response."""
        resp = _mock_check_response(
            set_cookies={
                "_sm_sess": "fresh-jwt",
                "_sm_user_id": "uid-456",
            }
        )
        cookies = TokenRefreshManager._parse_set_cookies(resp)
        assert cookies["_sm_sess"] == "fresh-jwt"
        assert cookies["_sm_user_id"] == "uid-456"

    def test_parse_set_cookies_empty(self):
        resp = _mock_check_response(set_cookies=None)
        cookies = TokenRefreshManager._parse_set_cookies(resp)
        assert cookies == {}
