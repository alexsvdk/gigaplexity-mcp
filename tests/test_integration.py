"""Integration tests — require real credentials in environment.

Run with: pytest -m integration
"""

import os

import pytest

from gigaplexity.client import GigaChatClient
from gigaplexity.config import load_settings
from gigaplexity.models import SearchMode

pytestmark = pytest.mark.integration

SKIP_REASON = "Set GIGACHAT_SM_SESS to run integration tests"
needs_creds = pytest.mark.skipif(
    not os.environ.get("GIGACHAT_SM_SESS"), reason=SKIP_REASON
)


@needs_creds
@pytest.mark.asyncio
async def test_ask_real():
    settings = load_settings()
    client = GigaChatClient(settings)
    try:
        result = await client.search("What is Python?", SearchMode.ASK)
        assert result.text, "Expected non-empty response text"
        assert result.mode == SearchMode.ASK
        print(f"\n--- ASK RESULT ---\n{result.format_markdown()[:500]}")
    finally:
        await client.close()


@needs_creds
@pytest.mark.asyncio
async def test_research_real():
    settings = load_settings()
    client = GigaChatClient(settings)
    try:
        result = await client.search(
            "Best Python web frameworks in 2026", SearchMode.RESEARCH
        )
        assert result.text, "Expected non-empty response text"
        assert result.mode == SearchMode.RESEARCH
        print(f"\n--- RESEARCH RESULT ---\n{result.format_markdown()[:500]}")
    finally:
        await client.close()


@needs_creds
@pytest.mark.asyncio
async def test_reason_real():
    settings = load_settings()
    client = GigaChatClient(settings)
    try:
        result = await client.search(
            "Why is the sky blue? Explain step by step.", SearchMode.REASON
        )
        assert result.text, "Expected non-empty response text"
        assert result.mode == SearchMode.REASON
        print(f"\n--- REASON RESULT ---\n{result.format_markdown()[:500]}")
    finally:
        await client.close()
