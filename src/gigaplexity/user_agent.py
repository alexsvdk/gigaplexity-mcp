"""User-Agent generation with realistic browser/platform distributions."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Literal, TypeVar

BrowserName = Literal["chrome", "yandex", "safari", "firefox"]

RU_BROWSER_WEIGHTS: dict[BrowserName, float] = {
    "chrome": 0.49,
    "yandex": 0.38,
    "safari": 0.09,
    "firefox": 0.03,
}

GLOBAL_BROWSER_WEIGHTS: dict[BrowserName, float] = {
    "chrome": 0.65,
    "yandex": 0.04,
    "safari": 0.24,
    "firefox": 0.07,
}

_VERSION_BUCKET_WEIGHTS = [0.55, 0.25, 0.12, 0.08]


@dataclass(frozen=True)
class VersionSpec:
    browser: str
    chromium: str | None = None


_VERSION_POOLS: dict[BrowserName, list[VersionSpec]] = {
    "chrome": [
        VersionSpec("135"),
        VersionSpec("134"),
        VersionSpec("133"),
        VersionSpec("132"),
        VersionSpec("131"),
        VersionSpec("130"),
    ],
    "yandex": [
        VersionSpec("25.2.0.0", chromium="135"),
        VersionSpec("25.1.0.0", chromium="134"),
        VersionSpec("24.12.0.0", chromium="133"),
        VersionSpec("24.10.0.0", chromium="132"),
        VersionSpec("24.8.0.0", chromium="131"),
        VersionSpec("24.6.0.0", chromium="130"),
    ],
    "safari": [
        VersionSpec("18.4"),
        VersionSpec("18.3"),
        VersionSpec("18.2"),
        VersionSpec("17.6"),
        VersionSpec("17.5"),
        VersionSpec("17.4"),
    ],
    "firefox": [
        VersionSpec("137"),
        VersionSpec("136"),
        VersionSpec("135"),
        VersionSpec("134"),
        VersionSpec("133"),
        VersionSpec("132"),
    ],
}


T = TypeVar("T")


def _weighted_choice(items: list[T], weights: list[float], rng: random.Random) -> T:
    return rng.choices(items, weights=weights, k=1)[0]


def _resolve_rng(seed: str | None) -> random.Random:
    if seed is None:
        return random.Random()
    if seed.lstrip("-").isdigit():
        return random.Random(int(seed))
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def choose_browser(locale: str = "ru", rng: random.Random | None = None) -> BrowserName:
    rng = rng or random.Random()
    profiles = {"ru": RU_BROWSER_WEIGHTS, "global": GLOBAL_BROWSER_WEIGHTS}
    if locale not in profiles:
        raise ValueError("GIGACHAT_USER_AGENT_LOCALE must be 'ru' or 'global'")
    profile = profiles[locale]
    browsers = list(profile.keys())
    return _weighted_choice(browsers, [profile[b] for b in browsers], rng)


def choose_version(browser: BrowserName, rng: random.Random | None = None) -> VersionSpec:
    rng = rng or random.Random()
    versions = _VERSION_POOLS[browser]
    bucket = _weighted_choice([0, 1, 2, 3], _VERSION_BUCKET_WEIGHTS, rng)
    if bucket < 3:
        return versions[bucket]
    return rng.choice(versions[3:])


def _choose_platform(browser: BrowserName, rng: random.Random) -> str:
    if browser == "safari":
        return _weighted_choice(
            ["mac", "iphone", "ipad"],
            [0.65, 0.25, 0.10],
            rng,
        )
    if browser == "yandex":
        return _weighted_choice(["windows", "android"], [0.78, 0.22], rng)
    if browser == "chrome":
        return _weighted_choice(["windows", "android", "mac"], [0.55, 0.30, 0.15], rng)
    return _weighted_choice(["windows", "android", "mac", "linux"], [0.58, 0.20, 0.12, 0.10], rng)


def build_user_agent(
    browser: BrowserName, version: VersionSpec, rng: random.Random | None = None
) -> str:
    rng = rng or random.Random()
    platform = _choose_platform(browser, rng)

    if browser == "safari":
        if platform == "mac":
            return (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                f"Version/{version.browser} Safari/605.1.15"
            )
        if platform == "iphone":
            return (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                f"Version/{version.browser} Mobile/15E148 Safari/604.1"
            )
        return (
            "Mozilla/5.0 (iPad; CPU OS 18_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            f"Version/{version.browser} Mobile/15E148 Safari/604.1"
        )

    if browser == "yandex":
        chromium = version.chromium or "135"
        if platform == "windows":
            return (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chromium}.0.0.0 YaBrowser/{version.browser} Safari/537.36"
            )
        return (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chromium}.0.0.0 Mobile Safari/537.36 YaBrowser/{version.browser}"
        )

    if browser == "chrome":
        if platform == "windows":
            return (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{version.browser}.0.0.0 Safari/537.36"
            )
        if platform == "android":
            return (
                "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{version.browser}.0.0.0 Mobile Safari/537.36"
            )
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{version.browser}.0.0.0 Safari/537.36"
        )

    if platform == "windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:"
            f"{version.browser}.0) Gecko/20100101 Firefox/{version.browser}.0"
        )
    if platform == "android":
        return (
            "Mozilla/5.0 (Android 14; Mobile; rv:"
            f"{version.browser}.0) Gecko/{version.browser}.0 Firefox/{version.browser}.0"
        )
    if platform == "mac":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:"
            f"{version.browser}.0) Gecko/20100101 Firefox/{version.browser}.0"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64; rv:"
        f"{version.browser}.0) Gecko/20100101 Firefox/{version.browser}.0"
    )


def generate_user_agent(locale: str = "ru", seed: str | None = None) -> str:
    rng = _resolve_rng(seed)
    browser = choose_browser(locale=locale, rng=rng)
    version = choose_version(browser, rng=rng)
    return build_user_agent(browser, version, rng=rng)
