"""Unit tests for the preflight auth check."""

from __future__ import annotations

import base64
import json
import time

import httpx
import pytest

from gigaplexity.config import GigaplexitySettings
from gigaplexity.preflight import run_preflight


def _make_jwt(payload: dict) -> str:
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"header.{b64.decode()}.signature"


def _make_settings(
    *,
    sm_sess: str | None = None,
    project_id: str = "test-project-id",
    user_id: str = "test-user-id",
    cookies: str | None = None,
    preflight_skew_seconds: int = 60,
    preflight_on_start: bool = True,
) -> GigaplexitySettings:
    # If neither sm_sess nor cookies is provided, fall back to a far-future
    # JWT so callers that don't care about expiry can ignore JWT math.
    if sm_sess is None and cookies is None:
        sm_sess = _make_jwt({"exp": int(time.time()) + 3600})
    return GigaplexitySettings(
        sm_sess=sm_sess,
        cookies=cookies,
        user_id=user_id,
        project_id=project_id,
        preflight_on_start=preflight_on_start,
        preflight_skew_seconds=preflight_skew_seconds,
    )


def _build_async_client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(
        base_url="https://giga.chat",
        transport=transport,
        timeout=httpx.Timeout(5.0),
    )


class TestPreflightOk:
    @pytest.mark.asyncio
    async def test_ok_when_check_returns_result_true(self):
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            assert request.url.path == "/api/check"
            return httpx.Response(200, json={"result": True})

        client = _build_async_client(handler)
        settings = _make_settings()
        result = await run_preflight(settings, http=client)
        assert result.ok is True
        assert result.should_refresh is False
        assert result.reason == "ok"
        assert called["n"] == 1


class TestPreflightHttpErrors:
    @pytest.mark.asyncio
    async def test_401_triggers_should_refresh(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                text='{"message":"Unauthorized"}',
                headers={"content-type": "application/json"},
            )

        client = _build_async_client(handler)
        settings = _make_settings()
        result = await run_preflight(settings, http=client)
        assert result.ok is False
        assert result.should_refresh is True
        assert result.reason == "not_authorized"

    @pytest.mark.asyncio
    async def test_403_triggers_should_refresh(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="forbidden")

        client = _build_async_client(handler)
        settings = _make_settings()
        result = await run_preflight(settings, http=client)
        assert result.should_refresh is True
        assert result.reason == "not_authorized"

    @pytest.mark.asyncio
    async def test_500_triggers_should_refresh_with_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        client = _build_async_client(handler)
        settings = _make_settings()
        result = await run_preflight(settings, http=client)
        assert result.ok is False
        assert result.should_refresh is True
        assert result.reason == "http_error"

    @pytest.mark.asyncio
    async def test_200_with_result_false_is_not_authorized(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"result": False, "message": "expired"})

        client = _build_async_client(handler)
        settings = _make_settings()
        result = await run_preflight(settings, http=client)
        assert result.ok is False
        assert result.should_refresh is True
        assert result.reason == "not_authorized"


class TestPreflightNetwork:
    @pytest.mark.asyncio
    async def test_network_error_does_not_request_refresh(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated offline")

        client = _build_async_client(handler)
        settings = _make_settings()
        result = await run_preflight(settings, http=client)
        assert result.ok is False
        assert result.should_refresh is False
        assert result.reason == "network_error"
        assert "ConnectError" in result.detail


class TestPreflightJwt:
    @pytest.mark.asyncio
    async def test_expired_jwt_skips_network(self):
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            return httpx.Response(200, json={"result": True})

        client = _build_async_client(handler)
        expired = _make_jwt({"exp": int(time.time()) - 60})
        settings = _make_settings(sm_sess=expired)
        result = await run_preflight(settings, http=client)
        assert result.ok is False
        assert result.should_refresh is True
        assert result.reason == "jwt_expired"
        assert called["n"] == 0  # No network call made.

    @pytest.mark.asyncio
    async def test_jwt_within_skew_triggers_refresh_without_network(self):
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            return httpx.Response(200, json={"result": True})

        client = _build_async_client(handler)
        # Expires in 5s, skew is 60s → treated as expired locally.
        soon = _make_jwt({"exp": int(time.time()) + 5})
        settings = _make_settings(
            sm_sess=soon, preflight_skew_seconds=60
        )
        result = await run_preflight(settings, http=client)
        assert result.reason == "jwt_expired"
        assert result.should_refresh is True
        assert called["n"] == 0

    @pytest.mark.asyncio
    async def test_invalid_jwt_treated_as_expired(self):
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            return httpx.Response(200, json={"result": True})

        client = _build_async_client(handler)
        settings = _make_settings(sm_sess="not-a-jwt")
        result = await run_preflight(settings, http=client)
        assert result.reason == "jwt_expired"
        assert result.should_refresh is True
        assert called["n"] == 0

    @pytest.mark.asyncio
    async def test_custom_skew_keeps_far_future_token_alive(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"result": True})

        client = _build_async_client(handler)
        # Token expires in 30s; with skew 0 it is still valid; with skew 60
        # it would already be considered expired. We choose skew 0 explicitly.
        soon = _make_jwt({"exp": int(time.time()) + 30})
        settings = _make_settings(sm_sess=soon, preflight_skew_seconds=0)
        result = await run_preflight(settings, http=client)
        assert result.ok is True
        assert result.reason == "ok"


class TestPreflightCookiesFallback:
    @pytest.mark.asyncio
    async def test_jwt_parsed_from_full_cookie_string(self):
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            return httpx.Response(200, json={"result": True})

        client = _build_async_client(handler)
        expired = _make_jwt({"exp": int(time.time()) - 60})
        cookies = (
            f"_sm_sess={expired}; _sm_user_id=test-user-id; "
            "sticky_cookie_dp=dp"
        )
        settings = _make_settings(sm_sess=None, cookies=cookies)
        result = await run_preflight(settings, http=client)
        assert result.reason == "jwt_expired"
        assert result.should_refresh is True
        assert called["n"] == 0

    @pytest.mark.asyncio
    async def test_no_jwt_in_cookies_treated_as_expired(self):
        called = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["n"] += 1
            return httpx.Response(200, json={"result": True})

        client = _build_async_client(handler)
        # Cookie string with no _sm_sess → can't decode JWT locally.
        settings = _make_settings(
            sm_sess="placeholder", cookies="other=cookie; _sm_sess=garbage"
        )
        result = await run_preflight(settings, http=client)
        assert result.reason == "jwt_expired"
        assert result.should_refresh is True
        assert called["n"] == 0
