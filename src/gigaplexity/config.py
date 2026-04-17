"""Environment-based configuration for Gigaplexity."""

from __future__ import annotations

import httpx
from pydantic import model_validator
from pydantic_settings import BaseSettings

_PROFILE_URL = "https://giga.chat/api/profile/api/v0/mobile/init"


def _parse_cookie(cookies: str, name: str) -> str | None:
    """Extract a cookie value from a cookie header string."""
    for part in cookies.split(";"):
        part = part.strip()
        if part.startswith(f"{name}="):
            return part[len(name) + 1 :]
    return None


def _fetch_gigachat_id(cookie_string: str) -> str | None:
    """Fetch gigachatId (project_id) from profile API."""
    try:
        resp = httpx.post(
            _PROFILE_URL,
            headers={"Cookie": cookie_string, "Content-Type": "application/json"},
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

    Optional:
        GIGACHAT_USER_ID: User UUID (auto-extracted from cookies if not set)
        GIGACHAT_PROJECT_ID: Project UUID (auto-fetched from profile if not set)
        GIGACHAT_USER_AGENT: Browser User-Agent
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
    user_id: str | None = None
    project_id: str | None = None

    # Optional
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15"
    )
    base_url: str = "https://giga.chat"
    app_version: str = "0.94.4"
    language: str = "en"
    timezone: str = "UTC"

    # Optional additional cookies
    sticky_dp: str | None = None
    sticky_km: str | None = None
    bp_challenge: str | None = None

    @model_validator(mode="after")
    def _resolve_from_cookies(self) -> GigaplexitySettings:
        """Auto-extract user_id from cookies, auto-fetch project_id from profile."""
        if not self.cookies and not self.sm_sess:
            raise ValueError(
                "Either GIGACHAT_COOKIES or GIGACHAT_SM_SESS must be set"
            )

        if self.cookies and not self.user_id:
            extracted = _parse_cookie(self.cookies, "_sm_user_id")
            if extracted:
                self.user_id = extracted

        if not self.user_id:
            raise ValueError(
                "GIGACHAT_USER_ID is required (or must be present as "
                "_sm_user_id in GIGACHAT_COOKIES)"
            )

        if not self.project_id:
            cookie_str = self.cookies or self.build_cookie_string()
            giga_id = _fetch_gigachat_id(cookie_str)
            if giga_id:
                self.project_id = giga_id
            else:
                raise ValueError(
                    "GIGACHAT_PROJECT_ID is required (could not auto-fetch "
                    "from profile API — set it manually)"
                )

        return self

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

    def build_headers(self, request_id: str) -> dict[str, str]:
        """Build common request headers."""
        return {
            "Accept": "text/event-stream, application/json",
            "Content-Type": "application/json",
            "Cookie": self.build_cookie_string(),
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": self.user_agent,
            "X-Application-Name": "gigachat-b2c-web",
            "X-Application-Version": self.app_version,
            "X-User-Timezone": self.timezone,
            "x-request-id": request_id,
            "x-project-id": self.project_id,  # type: ignore[dict-item]
            "x-sm-user-id": self.user_id,  # type: ignore[dict-item]
        }


def load_settings() -> GigaplexitySettings:
    """Load settings from environment variables."""
    return GigaplexitySettings()  # type: ignore[call-arg]
