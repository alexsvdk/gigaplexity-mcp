"""Unit tests for jwt_utils helpers."""

from __future__ import annotations

import base64
import json
import time

from gigaplexity.jwt_utils import decode_jwt_payload, is_jwt_expired, jwt_exp


def _make_jwt(payload: dict) -> str:
    """Build an unsigned 3-part JWT for tests."""
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    return f"header.{b64.decode()}.signature"


class TestDecodeJwtPayload:
    def test_decodes_valid_payload(self):
        token = _make_jwt({"usr": "abc", "exp": 12345})
        assert decode_jwt_payload(token) == {"usr": "abc", "exp": 12345}

    def test_returns_empty_for_non_jwt(self):
        assert decode_jwt_payload("not-a-jwt") == {}
        assert decode_jwt_payload("a.b") == {}
        assert decode_jwt_payload("") == {}
        assert decode_jwt_payload(None) == {}

    def test_returns_empty_on_bad_base64(self):
        # Malformed base64 in payload position.
        assert decode_jwt_payload("a.!!!.b") == {}


class TestJwtExp:
    def test_returns_int(self):
        token = _make_jwt({"exp": 1700000000})
        assert jwt_exp(token) == 1700000000

    def test_missing_exp_returns_none(self):
        token = _make_jwt({"usr": "abc"})
        assert jwt_exp(token) is None

    def test_non_integer_exp_returns_none(self):
        token = _make_jwt({"exp": "soon"})
        assert jwt_exp(token) is None

    def test_invalid_token_returns_none(self):
        assert jwt_exp("garbage") is None
        assert jwt_exp(None) is None


class TestIsJwtExpired:
    def test_future_token_not_expired(self):
        token = _make_jwt({"exp": int(time.time()) + 3600})
        assert is_jwt_expired(token) is False

    def test_past_token_expired(self):
        token = _make_jwt({"exp": int(time.time()) - 10})
        assert is_jwt_expired(token) is True

    def test_skew_marks_near_future_as_expired(self):
        # Token expires in 5 seconds, skew is 60s → expired.
        token = _make_jwt({"exp": int(time.time()) + 5})
        assert is_jwt_expired(token, skew_seconds=60) is True

    def test_skew_keeps_comfortable_margin_alive(self):
        token = _make_jwt({"exp": int(time.time()) + 3600})
        assert is_jwt_expired(token, skew_seconds=60) is False

    def test_missing_exp_treated_as_expired(self):
        token = _make_jwt({"usr": "abc"})
        assert is_jwt_expired(token) is True

    def test_invalid_token_treated_as_expired(self):
        assert is_jwt_expired("not-a-jwt") is True
        assert is_jwt_expired(None) is True

    def test_negative_skew_clamped_to_zero(self):
        # 5s in the future, skew -100 → effectively 0 → not yet expired.
        token = _make_jwt({"exp": int(time.time()) + 5})
        assert is_jwt_expired(token, skew_seconds=-100) is False
