"""GigaChat exception types."""

from __future__ import annotations


class GigaChatError(Exception):
    """Raised when the GigaChat API returns an error."""


# Tokens used in error messages / body checks.
# `GC-ATT-E005` is emitted by the attachments upload endpoint when the
# short-lived `_sm_sess` has already expired; the search endpoint uses
# the more generic "token has expired" wording in the same situation.
_AUTH_EXPIRED_BODY_MARKERS = ("token has expired", "GC-ATT-E005")


def is_auth_expired_response(status_code: int, body: str) -> bool:
    """Return True if a GigaChat response indicates an expired session.

    Detection rules (kept narrow to avoid false positives on transient errors):
      * HTTP 401 or 403
      * body contains "token has expired" (case-insensitive)
      * body contains the attachments-specific code "GC-ATT-E005"
    """
    if status_code in (401, 403):
        return True
    if not body:
        return False
    lower = body.lower()
    for marker in _AUTH_EXPIRED_BODY_MARKERS:
        if marker.lower() in lower:
            return True
    return False


class AuthExpiredError(GigaChatError):
    """Raised when the GigaChat session cookie has expired.

    Auto-refresh is intentionally NOT supported from this client: a full
    refresh requires a browser SSO round-trip through Keymaster. Instead
    we surface a clear, actionable error and let the user refresh their
    cookies manually.
    """

    DEFAULT_MESSAGE = (
        "GigaChat session has expired: the `_sm_sess` cookie is no longer valid. "
        "Auto-refresh requires a browser SSO round-trip and is not available from "
        "this MCP server. To recover, open https://giga.chat in a logged-in browser, "
        "open DevTools → Network, send any message in the chat, find the request to "
        "`sessions/request`, copy the full `Cookie` header value, and update the "
        "`GIGACHAT_COOKIES` (or `GIGACHAT_SM_SESS`) environment variable in your "
        "MCP client configuration, then restart the server."
    )

    def __init__(self, detail: str = "") -> None:
        if detail:
            message = f"{self.DEFAULT_MESSAGE}\n\nDetail: {detail}"
        else:
            message = self.DEFAULT_MESSAGE
        super().__init__(message)
        self.detail = detail
