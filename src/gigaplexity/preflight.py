"""Startup preflight check for the GigaChat session cookie.

The GigaChat web app exposes ``GET /api/check`` to verify whether the
current ``_sm_sess`` cookie is still valid. The token itself is a
short-lived JWT (lifetime ~5 min in the wild), so we run this check
once on MCP server start, plus a cheap local JWT ``exp`` comparison to
avoid a round-trip for clearly-expired cookies.

The preflight NEVER raises — it returns a :class:`PreflightResult` so
the caller can decide how to react. Network errors are downgraded to
``ok=False, should_refresh=False`` so they don't block startup: better
to try a real request and surface the real error there.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from gigaplexity.config import GigaplexitySettings
from gigaplexity.jwt_utils import is_jwt_expired, jwt_exp

logger = logging.getLogger(__name__)


PREFLIGHT_ENDPOINT = "/api/check"


@dataclass
class PreflightResult:
    """Outcome of the startup auth preflight check."""

    ok: bool
    reason: str  # "ok" | "http_error" | "not_authorized" | "network_error" | "jwt_expired"
    detail: str
    should_refresh: bool


def _extract_sm_sess(settings: GigaplexitySettings) -> str | None:
    if settings.sm_sess:
        return settings.sm_sess
    if not settings.cookies:
        return None
    for part in settings.cookies.split(";"):
        part = part.strip()
        if part.startswith("_sm_sess="):
            return part[len("_sm_sess=") :]
    return None


async def run_preflight(
    settings: GigaplexitySettings,
    *,
    http: httpx.AsyncClient | None = None,
) -> PreflightResult:
    """Run a single, non-throwing auth preflight check.

    Order of operations:

    1. Decode JWT locally and check ``exp`` (with a configurable skew).
       If it is expired, return immediately — no network call.
    2. Otherwise, perform ``GET /api/check`` with the same headers as a
       regular request.
       * HTTP 200 with ``result=true`` → ``ok=True``.
       * HTTP 401/403 → ``should_refresh=True`` (token rejected by server).
       * Any other non-200 → ``should_refresh=True`` with ``reason="http_error"``.
       * Network error → ``ok=False``, ``should_refresh=False`` (warning only).
    """
    # 1. Local JWT exp check.
    token = _extract_sm_sess(settings)
    if is_jwt_expired(token, skew_seconds=settings.preflight_skew_seconds):
        exp = jwt_exp(token)
        detail = (
            "JWT from _sm_sess is expired"
            + (f" (exp={exp})" if exp is not None else "")
        )
        logger.warning("Preflight: %s — refresh required", detail)
        return PreflightResult(
            ok=False,
            reason="jwt_expired",
            detail=detail,
            should_refresh=True,
        )

    # 2. Network check.
    owns_client = http is None
    client = http or httpx.AsyncClient(
        base_url=settings.base_url,
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=True,
    )
    try:
        request_id = "preflight-" + str(id(settings))
        headers = settings.build_attachments_headers(request_id)
        try:
            resp = await client.get(PREFLIGHT_ENDPOINT, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("Preflight network error: %s", exc)
            return PreflightResult(
                ok=False,
                reason="network_error",
                detail=f"{type(exc).__name__}: {exc}",
                should_refresh=False,
            )

        status = resp.status_code
        # Some GigaChat error responses are JSON, others are plain text.
        body_text = resp.text or ""
        body_lower = body_text.lower()
        body_json: dict | None = None
        if body_text:
            try:
                parsed = resp.json()
                if isinstance(parsed, dict):
                    body_json = parsed
            except Exception:
                body_json = None

        if status == 200:
            if body_json is not None and body_json.get("result") is True:
                return PreflightResult(
                    ok=True,
                    reason="ok",
                    detail="ok",
                    should_refresh=False,
                )
            # 200 with result=false (or non-JSON body) is still a "not authorized"
            # signal — same as a 401 in practice.
            logger.info(
                "Preflight: /api/check returned 200 but result is not true: %s",
                body_text[:200],
            )
            return PreflightResult(
                ok=False,
                reason="not_authorized",
                detail=body_text[:300] or "result!=true",
                should_refresh=True,
            )

        if status in (401, 403):
            logger.info(
                "Preflight: not authorized (HTTP %d): %s", status, body_text[:200]
            )
            return PreflightResult(
                ok=False,
                reason="not_authorized",
                detail=body_text[:300] or f"HTTP {status}",
                should_refresh=True,
            )

        logger.info(
            "Preflight: unexpected HTTP %d: %s", status, body_text[:200]
        )
        # Be lenient on benign markers — sometimes a stale CDN returns 5xx
        # but the token itself is fine. Treat any non-2xx as a "should refresh"
        # hint so the user can decide.
        _ = body_lower  # kept for future markers
        return PreflightResult(
            ok=False,
            reason="http_error",
            detail=f"HTTP {status}: {body_text[:200]}",
            should_refresh=True,
        )
    finally:
        if owns_client:
            await client.aclose()
