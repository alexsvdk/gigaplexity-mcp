"""Automatic JWT token refresh for GigaChat sessions.

Calls ``GET /api/check`` to obtain a fresh ``_sm_sess`` cookie,
exactly the same way the official GigaChat web app does.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from gigaplexity.token_store import TokenStore

logger = logging.getLogger(__name__)

CHECK_ENDPOINT = "/api/check"
_DEFAULT_REFRESH_INTERVAL = 3600  # 1 hour


class TokenRefreshManager:
    """Manages the lifecycle of a GigaChat JWT token.

    * **Proactive** refresh — before every request if the token is older
      than ``refresh_interval`` seconds.
    * **Reactive** refresh — on-demand when the caller signals an auth
      failure (call :meth:`force_refresh`).

    Thread-safe via :class:`asyncio.Lock`.
    """

    def __init__(
        self,
        *,
        original_token: str,
        current_cookies: str,
        base_url: str,
        user_agent: str,
        store: TokenStore | None = None,
        refresh_interval: float = _DEFAULT_REFRESH_INTERVAL,
    ) -> None:
        self._original_token = original_token
        self._current_cookies = current_cookies
        self._base_url = base_url
        self._user_agent = user_agent
        self._store = store
        self._refresh_interval = refresh_interval
        self._lock = asyncio.Lock()
        self._last_refresh: float = 0.0

        # Restore persisted token (if any)
        if store:
            persisted = store.get_fresh_token(original_token)
            if persisted and persisted != original_token:
                self._apply_token_to_cookies(persisted)
                self._last_refresh = time.monotonic()
                logger.info("Restored persisted token (original=%s…)", original_token[:16])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_cookies(self) -> str:
        """Latest cookie string (may differ from the one passed at init)."""
        return self._current_cookies

    async def ensure_valid_token(self, http: httpx.AsyncClient) -> None:
        """Refresh the token if enough time has elapsed since the last refresh."""
        now = time.monotonic()
        if now - self._last_refresh < self._refresh_interval:
            return
        async with self._lock:
            # Double-check after acquiring the lock
            if time.monotonic() - self._last_refresh < self._refresh_interval:
                return
            await self._do_refresh(http)

    async def force_refresh(self, http: httpx.AsyncClient) -> bool:
        """Force an immediate refresh (e.g. after a 401/403).

        Returns ``True`` if the refresh succeeded.
        """
        async with self._lock:
            return await self._do_refresh(http)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _do_refresh(self, http: httpx.AsyncClient) -> bool:
        logger.debug("Refreshing token via %s …", CHECK_ENDPOINT)
        try:
            resp = await http.get(
                CHECK_ENDPOINT,
                headers={
                    "Cookie": self._current_cookies,
                    "Accept": "*/*",
                    "User-Agent": self._user_agent,
                    "Referer": f"{self._base_url}/",
                },
                timeout=10.0,
            )
            resp.raise_for_status()

            body = resp.json()
            if not body.get("result"):
                logger.warning("Token check returned result=false: %s", body)
                return False

            # Parse Set-Cookie headers for updated tokens
            updated_cookies = self._parse_set_cookies(resp)
            if updated_cookies:
                new_sm_sess = updated_cookies.get("_sm_sess")
                if new_sm_sess:
                    self._apply_token_to_cookies(new_sm_sess)
                    if self._store:
                        self._store.save_token(
                            self._original_token,
                            new_sm_sess,
                            updated_cookies,
                        )
                    logger.info("Token refreshed successfully")
                else:
                    logger.debug("No new _sm_sess in Set-Cookie (token still fresh)")
            else:
                logger.debug("No Set-Cookie headers — token still fresh")

            self._last_refresh = time.monotonic()
            return True

        except httpx.HTTPStatusError as exc:
            logger.error("Token refresh failed (HTTP %d): %s", exc.response.status_code, exc.response.text[:200])
            return False
        except Exception as exc:
            logger.error("Token refresh failed: %s", exc)
            return False

    def _apply_token_to_cookies(self, new_sm_sess: str) -> None:
        """Replace ``_sm_sess=…`` inside the current cookie string."""
        parts = self._current_cookies.split(";")
        replaced = False
        new_parts: list[str] = []
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("_sm_sess="):
                new_parts.append(f"_sm_sess={new_sm_sess}")
                replaced = True
            else:
                new_parts.append(part.strip())
        if not replaced:
            new_parts.insert(0, f"_sm_sess={new_sm_sess}")
        self._current_cookies = "; ".join(new_parts)

    @staticmethod
    def _parse_set_cookies(resp: httpx.Response) -> dict[str, str]:
        """Extract cookie name→value from raw ``Set-Cookie`` headers."""
        result: dict[str, str] = {}
        for header_value in resp.headers.multi_items():
            if header_value[0].lower() != "set-cookie":
                continue
            raw = header_value[1]
            # The value before the first ';' is the name=value pair
            cookie_part = raw.split(";", 1)[0].strip()
            if "=" in cookie_part:
                name, _, value = cookie_part.partition("=")
                result[name.strip()] = value.strip()
        return result
