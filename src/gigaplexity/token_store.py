"""Persistent token store — maps original tokens to their refreshed versions.

Stores a JSON file at ``~/.gigaplexity/token_store.json`` (configurable).
Multiple MCP instances with different initial tokens can coexist because
the mapping key is the *original* ``_sm_sess`` value supplied at startup.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DIR = os.path.join("~", ".gigaplexity")
_DEFAULT_FILENAME = "token_store.json"


class TokenStore:
    """JSON-file–backed token persistence.

    File layout::

        {
          "<original_sm_sess_prefix>": {
            "sm_sess": "<latest_sm_sess>",
            "cookies": { "<name>": "<value>", ... }
          },
          ...
        }

    The *key* is the first 64 characters of the original ``_sm_sess`` JWT
    (enough to be unique, short enough for readability in the JSON file).
    """

    _KEY_LEN = 64

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(os.path.expanduser(_DEFAULT_DIR)) / _DEFAULT_FILENAME
        self._path = Path(path)
        self._data: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_fresh_token(self, original_token: str) -> str | None:
        """Return the most recently stored token for *original_token*, or ``None``."""
        key = self._key(original_token)
        entry = self._data.get(key)
        if entry:
            return entry.get("sm_sess")
        return None

    def get_fresh_cookies(self, original_token: str) -> dict[str, str]:
        """Return extra cookies stored alongside the refreshed token."""
        key = self._key(original_token)
        entry = self._data.get(key)
        if entry:
            return dict(entry.get("cookies", {}))
        return {}

    def save_token(
        self,
        original_token: str,
        fresh_token: str,
        cookies: dict[str, str] | None = None,
    ) -> None:
        """Persist a refreshed token (and optional extra cookies)."""
        key = self._key(original_token)
        self._data[key] = {
            "sm_sess": fresh_token,
            "cookies": cookies or {},
        }
        self._flush()
        logger.info("Token refreshed and persisted (key=%s…)", key[:16])

    def remove(self, original_token: str) -> None:
        """Remove an entry."""
        key = self._key(original_token)
        if key in self._data:
            del self._data[key]
            self._flush()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, token: str) -> str:
        return token[: self._KEY_LEN]

    def _load(self) -> None:
        if not self._path.exists():
            self._data = {}
            return
        try:
            text = self._path.read_text(encoding="utf-8")
            self._data = json.loads(text) if text.strip() else {}
            logger.debug("Loaded token store from %s (%d entries)", self._path, len(self._data))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load token store %s: %s — starting fresh", self._path, exc)
            self._data = {}

    def _flush(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as exc:
            logger.error("Failed to write token store %s: %s", self._path, exc)
