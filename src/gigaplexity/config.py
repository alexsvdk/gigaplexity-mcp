"""Environment-based configuration for Gigaplexity."""

from __future__ import annotations

import logging
import uuid

import httpx
from pydantic import model_validator
from pydantic_settings import BaseSettings

from gigaplexity.jwt_utils import decode_jwt_payload
from gigaplexity.user_agent import generate_user_agent

_PROFILE_URL = "https://giga.chat/api/profile/api/v0/mobile/init"
DEFAULT_APP_NAME = "gigachat-b2c-web-neo"
DEFAULT_APP_VERSION = "0.2.10"
logger = logging.getLogger(__name__)


def _parse_cookie(cookies: str, name: str) -> str | None:
    """Extract a cookie value from a cookie header string."""
    for part in cookies.split(";"):
        part = part.strip()
        if part.startswith(f"{name}="):
            return part[len(name) + 1 :]
    return None


def _extract_user_id(cookies: str | None, sm_sess: str | None) -> str | None:
    """Extract user_id from JWT 'usr' field in _sm_sess cookie."""
    token = sm_sess
    if not token and cookies:
        token = _parse_cookie(cookies, "_sm_sess")
    if not token:
        return None
    payload = decode_jwt_payload(token)
    return payload.get("usr")


def _fetch_gigachat_id(
    cookie_string: str,
    *,
    app_name: str = DEFAULT_APP_NAME,
    app_version: str = DEFAULT_APP_VERSION,
) -> str | None:
    """Fetch gigachatId (project_id) from profile API."""
    try:
        resp = httpx.post(
            _PROFILE_URL,
            headers={
                "Accept": "application/json",
                "Cookie": cookie_string,
                "Content-Type": "application/json",
                "Origin": "https://giga.chat",
                "Referer": "https://giga.chat/",
                "X-Application-Name": app_name,
                "X-Application-Version": app_version,
                "X-Request-Id": str(uuid.uuid4()),
            },
            json={},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["user"]["gigachatId"]
    except Exception:
        return None


class GigaplexitySettings(BaseSettings):
    """Settings loaded from environment variables.

    Required:
        GIGACHAT_COOKIES: Full cookie string (recommended), OR
        GIGACHAT_SM_SESS: JWT session token (alternative)

    Optional (auto-resolved):
        GIGACHAT_PROJECT_ID: Project UUID (auto-fetched from profile API)
        GIGACHAT_USER_AGENT: Browser User-Agent or random[/seed]
        GIGACHAT_BASE_URL: API base URL
        GIGACHAT_APP_VERSION: Application version
        GIGACHAT_LANGUAGE: Language preference
        GIGACHAT_TIMEZONE: Timezone
        GIGACHAT_STICKY_DP: sticky_cookie_dp value
        GIGACHAT_STICKY_KM: sticky_cookie_km value
        GIGACHAT_BP_CHALLENGE: bp_challenge value
    """

    model_config = {"env_prefix": "GIGACHAT_"}

    # Auth (cookies or sm_sess required)
    cookies: str | None = None
    sm_sess: str | None = None
    project_id: str | None = None

    # Resolved at runtime (not configurable)
    user_id: str | None = None

    # Optional
    user_agent: str = "random"
    base_url: str = "https://giga.chat"
    app_version: str = DEFAULT_APP_VERSION
    app_name: str = DEFAULT_APP_NAME
    language: str = "en"
    timezone: str = "UTC"

    # Optional additional cookies
    sticky_dp: str | None = None
    sticky_km: str | None = None
    bp_challenge: str | None = None

    # Preflight auth check (see preflight.py)
    preflight_on_start: bool = True
    preflight_skew_seconds: int = 60

    @model_validator(mode="after")
    def _resolve_from_cookies(self) -> GigaplexitySettings:
        """Auto-extract user_id from JWT, auto-fetch project_id from profile."""
        if not self.cookies and not self.sm_sess:
            raise ValueError(
                "Either GIGACHAT_COOKIES or GIGACHAT_SM_SESS must be set"
            )

        # user_id from JWT "usr" field (skip if already provided)
        if not self.user_id:
            user_id = _extract_user_id(self.cookies, self.sm_sess)
            if not user_id:
                raise ValueError(
                    "Could not extract user_id from JWT — ensure GIGACHAT_COOKIES "
                    "or GIGACHAT_SM_SESS contains a valid _sm_sess token"
                )
            self.user_id = user_id

        # project_id from profile API
        if not self.project_id:
            cookie_str = self.cookies or self.build_cookie_string()
            giga_id = _fetch_gigachat_id(
                cookie_str,
                app_name=self.app_name,
                app_version=self.app_version,
            )
            if giga_id:
                self.project_id = giga_id
            else:
                raise ValueError(
                    "GIGACHAT_PROJECT_ID is required (could not auto-fetch "
                    "from profile API — set it manually)"
                )

        self._resolve_user_agent()
        return self

    def _resolve_user_agent(self) -> None:
        ua_value = (self.user_agent or "random").strip()
        if ua_value in {"random", "random/"}:
            self.user_agent = generate_user_agent()
            logger.debug("Selected random User-Agent: %s", self.user_agent)
            return
        if ua_value.startswith("random/"):
            seed_part = ua_value.split("/", 1)[1]
            seed = seed_part if seed_part else None
            self.user_agent = generate_user_agent(seed=seed)
            logger.debug("Selected random User-Agent: %s", self.user_agent)
            return

        self.user_agent = ua_value

    def build_cookie_string(self) -> str:
        """Build the full cookie header value."""
        if self.cookies:
            return self.cookies

        if not self.sm_sess:
            raise ValueError(
                "Either GIGACHAT_COOKIES or GIGACHAT_SM_SESS must be set"
            )

        parts = [
            f"_sm_sess={self.sm_sess}",
            f"_sm_user_id={self.user_id}",
            f"_gigachat_language={self.language}",
        ]
        if self.sticky_dp:
            parts.append(f"sticky_cookie_dp={self.sticky_dp}")
        if self.sticky_km:
            parts.append(f"sticky_cookie_km={self.sticky_km}")
        if self.bp_challenge:
            parts.append(f"bp_challenge={self.bp_challenge}")
        return "; ".join(parts)

    def build_headers(
        self,
        request_id: str,
        *,
        accept: str = "text/event-stream, application/json",
        content_type: str | None = "application/json",
    ) -> dict[str, str]:
        """Build common request headers."""
        headers = {
            "Accept": accept,
            "Cookie": self.build_cookie_string(),
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": self.user_agent,
            "X-Application-Name": self.app_name,
            "X-Application-Version": self.app_version,
            "X-User-Timezone": self.timezone,
            "x-request-id": request_id,
            "x-project-id": self.project_id,  # type: ignore[dict-item]
            "x-sm-user-id": self.user_id,  # type: ignore[dict-item]
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def build_back_web_headers(self, request_id: str) -> dict[str, str]:
        """Build headers for GigaChat back-web SSE requests."""
        return self.build_headers(
            request_id,
            accept="text/event-stream, application/json",
            content_type="application/json",
        )

    def build_attachments_headers(
        self,
        request_id: str,
        *,
        multipart: bool = False,
    ) -> dict[str, str]:
        """Build headers for attachments OTR and upload requests."""
        return self.build_headers(
            request_id,
            accept="application/json, text/plain, */*",
            content_type=None if multipart else "application/json",
        )


def load_settings() -> GigaplexitySettings:
    """Load settings from environment variables."""
    return GigaplexitySettings()  # type: ignore[call-arg]
