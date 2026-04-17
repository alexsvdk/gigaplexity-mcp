"""MCP server exposing GigaChat web search tools."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from gigaplexity.client import GigaChatClient
from gigaplexity.config import load_settings
from gigaplexity.models import SearchMode

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "gigaplexity",
    instructions="GigaChat-powered web search — ask, research, and reason",
)

_client: GigaChatClient | None = None


def _get_client() -> GigaChatClient:
    global _client
    if _client is None:
        settings = load_settings()
        _client = GigaChatClient(settings)
    return _client


@mcp.tool()
async def ask(query: str, file_paths: list[str] | None = None) -> str:
    """Search the web and get a concise answer with citations.

    Uses GigaChat to search the internet and provide a direct answer
    to your question, similar to Perplexity AI's quick search.
    Optionally attach files (documents, images, or audio) for the model to analyze.

    Args:
        query: The question or search query.
        file_paths: Optional list of absolute file paths to attach.
            All files must be of the same type category:
            documents (pdf, docx, txt, code files, etc.),
            images (jpg, png, webp, etc.),
            or audio (mp3, wav, ogg, etc.).

    Returns:
        Answer text with source citations in markdown format.
    """
    client = _get_client()
    attachments = None
    if file_paths:
        attachments = await client.upload_files(file_paths)
    result = await client.search(query, SearchMode.ASK, attachments=attachments)
    return result.format_markdown()


@mcp.tool()
async def research(
    query: str,
    domains: list[str] | None = None,
    extended: bool = False,
) -> str:
    """Conduct deep web research on a topic.

    Performs multi-step research: decomposes the query, searches multiple
    sources, collects data, and synthesizes a comprehensive report with
    citations. Takes longer but produces thorough results.

    Args:
        query: The research topic or question.
        domains: Optional list of domains to restrict search to.
        extended: Whether to use extended research mode for even deeper analysis.

    Returns:
        Detailed research report in markdown with citations and research log.
    """
    client = _get_client()
    result = await client.search(
        query,
        SearchMode.RESEARCH,
        domains=domains,
        extended_research=extended,
    )
    return result.format_markdown()


@mcp.tool()
async def reason(query: str) -> str:
    """Think through a problem step-by-step with web search.

    Uses GigaChat's reasoning model to break down complex questions,
    think through them methodically, and provide well-reasoned answers
    backed by web sources.

    Args:
        query: The question or problem to reason about.

    Returns:
        Reasoned answer with thinking steps and citations in markdown format.
    """
    client = _get_client()
    result = await client.search(query, SearchMode.REASON)
    return result.format_markdown()


def main() -> None:
    """Entry point for the MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
