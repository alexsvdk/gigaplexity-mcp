"""Unit tests for TokenStore — persistent token mapping."""

import json
from pathlib import Path

import pytest

from gigaplexity.token_store import TokenStore


@pytest.fixture()
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "tokens.json"


class TestTokenStoreBasic:
    def test_empty_store_returns_none(self, store_path: Path):
        store = TokenStore(store_path)
        assert store.get_fresh_token("original-token") is None

    def test_save_and_retrieve(self, store_path: Path):
        store = TokenStore(store_path)
        store.save_token("original-token", "fresh-token")
        assert store.get_fresh_token("original-token") == "fresh-token"

    def test_save_with_cookies(self, store_path: Path):
        store = TokenStore(store_path)
        cookies = {"_sm_sess": "fresh", "_sm_user_id": "uid"}
        store.save_token("original", "fresh", cookies=cookies)

        retrieved = store.get_fresh_cookies("original")
        assert retrieved["_sm_sess"] == "fresh"
        assert retrieved["_sm_user_id"] == "uid"

    def test_overwrite_token(self, store_path: Path):
        store = TokenStore(store_path)
        store.save_token("original", "fresh-v1")
        store.save_token("original", "fresh-v2")
        assert store.get_fresh_token("original") == "fresh-v2"

    def test_remove_entry(self, store_path: Path):
        store = TokenStore(store_path)
        store.save_token("original", "fresh")
        store.remove("original")
        assert store.get_fresh_token("original") is None

    def test_remove_nonexistent_is_noop(self, store_path: Path):
        store = TokenStore(store_path)
        store.remove("nonexistent")  # should not raise


class TestTokenStoreMultipleInstances:
    def test_multiple_tokens_coexist(self, store_path: Path):
        store = TokenStore(store_path)
        store.save_token("token-A", "fresh-A")
        store.save_token("token-B", "fresh-B")
        assert store.get_fresh_token("token-A") == "fresh-A"
        assert store.get_fresh_token("token-B") == "fresh-B"

    def test_independent_removal(self, store_path: Path):
        store = TokenStore(store_path)
        store.save_token("token-A", "fresh-A")
        store.save_token("token-B", "fresh-B")
        store.remove("token-A")
        assert store.get_fresh_token("token-A") is None
        assert store.get_fresh_token("token-B") == "fresh-B"


class TestTokenStorePersistence:
    def test_survives_reload(self, store_path: Path):
        store1 = TokenStore(store_path)
        store1.save_token("original", "fresh")

        # Create a new store from the same path
        store2 = TokenStore(store_path)
        assert store2.get_fresh_token("original") == "fresh"

    def test_file_format_is_valid_json(self, store_path: Path):
        store = TokenStore(store_path)
        store.save_token("abc" * 30, "fresh-val")

        data = json.loads(store_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        # Key should be first 64 chars
        key = ("abc" * 30)[:64]
        assert key in data
        assert data[key]["sm_sess"] == "fresh-val"

    def test_corrupted_file_starts_fresh(self, store_path: Path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("not valid json {{{", encoding="utf-8")

        store = TokenStore(store_path)
        assert store.get_fresh_token("anything") is None
        # Should still be able to save
        store.save_token("original", "fresh")
        assert store.get_fresh_token("original") == "fresh"

    def test_empty_file_starts_fresh(self, store_path: Path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("", encoding="utf-8")

        store = TokenStore(store_path)
        assert store.get_fresh_token("anything") is None

    def test_creates_parent_directories(self, tmp_path: Path):
        deep_path = tmp_path / "a" / "b" / "c" / "tokens.json"
        store = TokenStore(deep_path)
        store.save_token("original", "fresh")

        assert deep_path.exists()
        store2 = TokenStore(deep_path)
        assert store2.get_fresh_token("original") == "fresh"
