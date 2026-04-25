"""Tests for User-Agent generation and settings integration."""

from __future__ import annotations

import random

from gigaplexity.config import GigaplexitySettings
from gigaplexity.user_agent import choose_browser, generate_user_agent

BROWSER_DISTRIBUTION_TOLERANCE = 0.03
TEST_SEED_ITERATIONS = 2_000


def _make_settings(**overrides) -> GigaplexitySettings:
    defaults = {
        "cookies": None,
        "sm_sess": "test-jwt-token",
        "user_id": "test-user-id",
        "project_id": "test-project-id",
    }
    defaults.update(overrides)
    return GigaplexitySettings(**defaults)


def _detect_browser(ua: str) -> str:
    is_safari_without_chrome = (
        "Version/" in ua and "Safari/" in ua and "Chrome/" not in ua
    )
    if "YaBrowser/" in ua:
        return "yandex"
    if "Firefox/" in ua:
        return "firefox"
    if is_safari_without_chrome:
        return "safari"
    if "Chrome/" in ua:
        return "chrome"
    raise AssertionError(f"Unknown browser in UA: {ua}")


def test_explicit_user_agent_is_used_as_is():
    explicit = "MyCustomUA/1.0"
    settings = _make_settings(user_agent=explicit)
    assert settings.user_agent == explicit


def test_default_user_agent_is_random():
    settings = _make_settings()
    assert settings.user_agent != "random"
    assert settings.user_agent
    assert _detect_browser(settings.user_agent) in {"chrome", "yandex", "safari", "firefox"}


def test_random_seed_in_user_agent_is_stable_for_instance():
    settings = _make_settings(user_agent="random/777")
    headers_first = settings.build_headers("req-1")
    headers_second = settings.build_headers("req-2")
    assert headers_first["User-Agent"] == headers_second["User-Agent"]


def test_ru_distribution_is_within_tolerance():
    rng = random.Random(42)
    sample_size = 10_000
    counts = {"chrome": 0, "yandex": 0, "safari": 0, "firefox": 0}

    for _ in range(sample_size):
        browser = choose_browser(rng=rng)
        counts[browser] += 1

    expected = {"chrome": 0.49, "yandex": 0.38, "safari": 0.09, "firefox": 0.03}
    for browser, target_share in expected.items():
        observed_share = counts[browser] / sample_size
        assert abs(observed_share - target_share) <= BROWSER_DISTRIBUTION_TOLERANCE


def test_generator_never_emits_invalid_browser_platform_pairs():
    for seed in range(TEST_SEED_ITERATIONS):
        ua = generate_user_agent(seed=str(seed))
        browser = _detect_browser(ua)

        if browser == "safari":
            assert "Windows NT" not in ua
            assert "Linux x86_64" not in ua
        if browser == "yandex":
            valid_platform = "Windows NT" in ua or "Android" in ua
            assert valid_platform, f"Invalid Yandex platform UA: {ua}"
