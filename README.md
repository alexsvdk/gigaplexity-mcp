# 🔍 Gigaplexity MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**MCP server that turns GigaChat into a web search engine** — ask questions, conduct deep research, and reason through problems, all powered by GigaChat's internet-connected AI.

Think of it as your own Perplexity-like search, accessible from any MCP-compatible client (Claude Desktop, VS Code Copilot, etc.).

## Features

| Tool | Description | Speed |
|------|-------------|-------|
| `ask` | Quick web search with concise answers and citations | ~20s |
| `research` | Deep multi-step research with comprehensive reports | ~45s |
| `reason` | Step-by-step reasoning with web-backed analysis | ~5s |

## Quick Start

### 1. Get GigaChat Credentials

1. Log into [giga.chat](https://giga.chat) in your browser
2. Open DevTools → Application → Cookies
3. Copy the values of: `_sm_sess`, `_sm_user_id`
4. From any API request headers, copy: `x-project-id`

### 2. Configure MCP Client

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "gigaplexity": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/a1exs/gigaplexity-mcp", "gigaplexity-mcp"],
      "env": {
        "GIGACHAT_SM_SESS": "your-jwt-token-here",
        "GIGACHAT_USER_ID": "your-user-uuid",
        "GIGACHAT_PROJECT_ID": "your-project-uuid"
      }
    }
  }
}
```

### 3. Use It

Ask your MCP client to use the gigaplexity tools:

- *"Search the web for the latest Python 3.13 features"* → `ask`
- *"Research the best database solutions for time-series data"* → `research`
- *"Reason about why transformer models work so well"* → `reason`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GIGACHAT_SM_SESS` | ✅ | JWT session token (`_sm_sess` cookie) |
| `GIGACHAT_USER_ID` | ✅ | User UUID (`_sm_user_id` cookie) |
| `GIGACHAT_PROJECT_ID` | ✅ | Project UUID (`x-project-id` header) |
| `GIGACHAT_COOKIES` | ❌ | Full cookie string (overrides individual cookies) |
| `GIGACHAT_USER_AGENT` | ❌ | Browser User-Agent string |
| `GIGACHAT_BASE_URL` | ❌ | API base URL (default: `https://giga.chat`) |
| `GIGACHAT_APP_VERSION` | ❌ | App version (default: `0.94.4`) |
| `GIGACHAT_LANGUAGE` | ❌ | Language preference (default: `en`) |
| `GIGACHAT_TIMEZONE` | ❌ | Timezone (default: `UTC`) |

## Development

```bash
# Clone
git clone https://github.com/a1exs/gigaplexity-mcp
cd gigaplexity-mcp

# Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"

# Run unit tests
pytest

# Run integration tests (requires credentials)
export GIGACHAT_SM_SESS="..."
export GIGACHAT_USER_ID="..."
export GIGACHAT_PROJECT_ID="..."
pytest -m integration -s
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed protocol analysis and design decisions.

## How It Works

Gigaplexity reverse-engineers GigaChat's web interface to access its search capabilities:

1. **Authentication** — Uses your browser session cookies (JWT) to authenticate
2. **Request** — Sends queries to GigaChat's internal API with the appropriate mode (ask/research/reason)
3. **Streaming** — Parses Server-Sent Events (SSE) to collect the full response
4. **Formatting** — Aggregates text, citations, reasoning steps, and research logs into clean markdown

Each mode uses a different AI agent and model:
- **Ask**: `GigaChat-3-Ultra` with web search
- **Research**: `GigaChat-3-Ultra` with deep research agent
- **Reason**: `GigaChat-2-Reasoning` with step-by-step thinking

## License

[MIT](LICENSE)
