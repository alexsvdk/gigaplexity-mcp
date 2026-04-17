# 🔍 Gigaplexity MCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**MCP server that turns GigaChat into a web search engine** — ask questions, conduct deep research, and reason through problems, all powered by GigaChat's internet-connected AI.

Think of it as your own Perplexity-like search, accessible from any MCP-compatible client (Claude Desktop, VS Code Copilot, etc.).

## Features

| Tool | Description | Speed |
|------|-------------|-------|
| `ask` | Quick web search with concise answers and citations. Supports file attachments (documents, images, audio). | ~20s |
| `research` | Deep multi-step research with comprehensive reports | ~45s |
| `reason` | Step-by-step reasoning with web-backed analysis | ~5s |

## ⚠️ Disclaimer / Отказ от ответственности

Данный проект создан исключительно в ознакомительных и **образовательных целях** (Educational / Research purposes only). Автор не призывает к нарушению правил сторонних сервисов.

1.  **Личное использование**: Проект предназначен только для частного использования (Local self-hosting). Любое публичное или коммерческое использование данного MCP-сервера может нарушать законы и правила сервиса.
2.  **Риск блокировки**: Использование неофициальных методов взаимодействия с GigaChat нарушает [Пользовательское соглашение](https://giga.chat/legal/terms) (Terms of Service). ПАО Сбербанк имеет право **заблокировать ваш профиль (Сбер ID)** при обнаружении автоматизированных или нетипичных запросов.
3.  **Авторские права**: Все права на GigaChat, API и торговые марки принадлежат ПАО Сбербанк. Данный проект является независимой реализацией и не связан с официальной командой Sber AI.
4.  **Отсутствие гарантий**: ПО предоставляется по лицензии MIT "как есть". Автор не несет ответственности за любые прямые или косвенные последствия использования данного кода, включая блокировки аккаунтов или утечки данных.

## Quick Start

### 1. Get GigaChat Cookie

You need **one value** from your browser. Log into [giga.chat](https://giga.chat) and open **DevTools** (F12).

#### `GIGACHAT_COOKIES` — full cookie string

1. Go to **Network** tab
2. Send any message in the chat
3. Find the request to `https://giga.chat/api/giga-back-web/api/v0/sessions/request`
4. In the **Headers** tab, find the `Cookie` request header
5. Copy the **entire** value — it looks like `_sm_sess=eyJ...; _sm_user_id=2a4a...; sticky_cookie_dp=...; ...`

> **Tip:** The `_sm_sess` JWT token expires every ~5 minutes, but GigaChat auto-refreshes it. The full cookie string from a recent browser session usually works for a while.

That's it! `user_id` is auto-extracted from the cookie string, and `project_id` is auto-fetched from the profile API.

### 2. Configure MCP Client

Add to your MCP client configuration (Claude Desktop, VS Code, etc.):

```json
{
  "mcpServers": {
    "gigaplexity": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/alexsvdk/gigaplexity-mcp", "gigaplexity-mcp"],
      "env": {
        "GIGACHAT_COOKIES": "_sm_sess=eyJ...; _sm_user_id=2a4a...; sticky_cookie_dp=..."
      }
    }
  }
}
```

### 3. Use It

Ask your MCP client to use the gigaplexity tools:

- *"Search the web for the latest Python 3.13 features"* → `ask`
- *"What's in this PDF?"* (attach a file) → `ask` with `file_paths`
- *"Describe this image"* (attach a photo) → `ask` with `file_paths`
- *"Research the best database solutions for time-series data"* → `research`
- *"Reason about why transformer models work so well"* → `reason`

### File Attachments

The `ask` tool supports file attachments via the `file_paths` parameter. Pass absolute paths to local files:

**Supported file types:**
- **Documents**: pdf, docx, doc, pptx, ppt, xlsx, xls, epub, txt, html, and source code files (py, js, ts, etc.)
- **Images**: jpg, jpeg, png, webp, heic, heif, bmp
- **Audio**: mp3, aac, m4a, opus, wav, ogg

**Important**: All files in a single request must be of the **same category** (e.g. only documents, only images, or only audio). Mixing categories in one request is not supported by the GigaChat API.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GIGACHAT_COOKIES` | ✅* | Full cookie string from DevTools |
| `GIGACHAT_SM_SESS` | ✅* | JWT token (alternative to COOKIES) |
| `GIGACHAT_PROJECT_ID` | ❌ | Project UUID (auto-fetched from profile API) |
| `GIGACHAT_USER_AGENT` | ❌ | Browser User-Agent | 
| `GIGACHAT_BASE_URL` | ❌ | API base URL (default: `https://giga.chat`) | — |
| `GIGACHAT_APP_VERSION` | ❌ | App version (default: `0.94.4`) | — |
| `GIGACHAT_LANGUAGE` | ❌ | Language preference (default: `en`) | — |
| `GIGACHAT_TIMEZONE` | ❌ | Timezone (default: `UTC`) | — |

\* Either `GIGACHAT_COOKIES` (recommended) or `GIGACHAT_SM_SESS` is required. `GIGACHAT_COOKIES` takes priority.

## Development

```bash
# Clone
git clone https://github.com/alexsvdk/gigaplexity-mcp
cd gigaplexity-mcp

# Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest pytest-asyncio

# Run unit tests
pytest

# Run integration tests (requires credentials)
export GIGACHAT_COOKIES="..."
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
