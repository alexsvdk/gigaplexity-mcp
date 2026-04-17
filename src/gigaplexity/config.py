"""Environment-based configuration for Gigaplexity."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class GigaplexitySettings(BaseSettings):
    """Settings loaded from environment variables.

    Required:
        GIGACHAT_SM_SESS: JWT session token
        GIGACHAT_USER_ID: User UUID
        GIGACHAT_PROJECT_ID: Project UUID

    Optional:
        GIGACHAT_COOKIES: Full cookie string (overrides individual cookies)
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

    # Required
    sm_sess: str
    user_id: str
    project_id: str

    # Optional
    cookies: str | None = None
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

    def build_cookie_string(self) -> str:
        """Build the full cookie header value."""
        if self.cookies:
            return self.cookies

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
            "x-project-id": self.project_id,
            "x-sm-user-id": self.user_id,
        }


def load_settings() -> GigaplexitySettings:
    """Load settings from environment variables."""
    return GigaplexitySettings()  # type: ignore[call-arg]
