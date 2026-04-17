"""Integration tests — require real credentials in environment.

Run with: pytest -m integration
"""

import os
from pathlib import Path

import pytest

from gigaplexity.client import GigaChatClient
from gigaplexity.config import load_settings
from gigaplexity.models import SearchMode

pytestmark = pytest.mark.integration

SKIP_REASON = "Set GIGACHAT_SM_SESS or GIGACHAT_COOKIES to run integration tests"
needs_creds = pytest.mark.skipif(
    not (os.environ.get("GIGACHAT_SM_SESS") or os.environ.get("GIGACHAT_COOKIES")),
    reason=SKIP_REASON,
)

TEST_FILES_DIR = Path(__file__).parent.parent / "hars" / "test_files"


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


@needs_creds
@pytest.mark.asyncio
async def test_ask_with_pdf():
    """Test ask with a PDF attachment."""
    pdf_path = TEST_FILES_DIR / "PDF 2.0 image with BPC.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Test file not found: {pdf_path}")

    settings = load_settings()
    client = GigaChatClient(settings)
    try:
        attachments = await client.upload_files([str(pdf_path)])
        assert len(attachments) == 1
        assert attachments[0].hash
        assert attachments[0].key

        result = await client.search(
            "What is this PDF about? Describe briefly.",
            SearchMode.ASK,
            attachments=attachments,
        )
        assert result.text, "Expected non-empty response text"
        print(f"\n--- ASK+PDF RESULT ---\n{result.format_markdown()[:500]}")
    finally:
        await client.close()


@needs_creds
@pytest.mark.asyncio
async def test_ask_with_image():
    """Test ask with an image attachment."""
    img_path = TEST_FILES_DIR / "gachiakuta-riyo-trailer.jpg"
    if not img_path.exists():
        pytest.skip(f"Test file not found: {img_path}")

    settings = load_settings()
    client = GigaChatClient(settings)
    try:
        attachments = await client.upload_files([str(img_path)])
        assert len(attachments) == 1
        assert attachments[0].hash
        assert attachments[0].key

        result = await client.search(
            "What is shown in this image? Describe briefly.",
            SearchMode.ASK,
            attachments=attachments,
        )
        assert result.text, "Expected non-empty response text"
        print(f"\n--- ASK+IMAGE RESULT ---\n{result.format_markdown()[:500]}")
    finally:
        await client.close()


@needs_creds
@pytest.mark.asyncio
async def test_ask_with_audio():
    """Test ask with an audio attachment."""
    audio_path = TEST_FILES_DIR / "Phone_ARU_ON.wav"
    if not audio_path.exists():
        pytest.skip(f"Test file not found: {audio_path}")

    settings = load_settings()
    client = GigaChatClient(settings)
    try:
        attachments = await client.upload_files([str(audio_path)])
        assert len(attachments) == 1
        assert attachments[0].hash
        assert attachments[0].key
        assert attachments[0].audio_duration is not None

        result = await client.search(
            "What is in this audio recording? Describe briefly.",
            SearchMode.ASK,
            attachments=attachments,
        )
        assert result.text, "Expected non-empty response text"
        print(f"\n--- ASK+AUDIO RESULT ---\n{result.format_markdown()[:500]}")
    finally:
        await client.close()
