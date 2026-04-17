# Gigaplexity MCP Server — Architecture

## Overview

Gigaplexity is an MCP (Model Context Protocol) server that exposes GigaChat's web search capabilities as tools, similar to Perplexity AI. It reverse-engineers GigaChat's web interface to provide three search modes: **ask**, **research**, and **reason**.

## Protocol

GigaChat uses a REST + SSE (Server-Sent Events) API:

- **Endpoint**: `POST https://giga.chat/api/giga-back-web/api/v0/sessions/request`
- **Auth**: JWT session cookie (`_sm_sess`) + custom headers
- **Streaming**: `text/event-stream` with `data:{JSON}` events
- **Session-based**: Each conversation has a UUID session ID

### Three Modes

| Mode | Agent UUID | Model | Features |
|------|-----------|-------|----------|
| Ask | `019a5d95-ab99-7c86-a31c-610dad03b054` | GigaChat-3-Ultra (default) | Web search + citations |
| Research | `9384a8fd-39e0-4da9-9bc4-da143487449f` | GigaChat-3-Ultra | Deep multi-step research |
| Reason | `7101c625-42ab-45fe-b168-323970c12eba` | GigaChat-2-Reasoning | Step-by-step reasoning |

### File Attachments

Files can be attached to `ask` queries via a two-step upload flow:

#### Upload Flow

1. **Create OTR** (one-time record):
   - `POST /api/attachments/api/v0/gc/otr` with `{"fileType": "<TYPE>"}` (e.g. `"PDF"`, `"IMAGE"`, `"AUDIO"`)
   - Returns `{"otrId": "...", "rootId": "..."}`

2. **Upload file**:
   - `POST /api/attachments-upload/api/v0/gc/otr/{otrId}` as `multipart/form-data`
   - Custom headers: `x-file-size`, `x-file-type` (MIME), `x-file-name` (URL-encoded), `requestid` (UUID)
   - Form field: `file` with randomized filename (`{uuid}{ext}`, no dot) and `application/octet-stream` content type
   - Returns `{"attachmentId": "...", "key": "...", "hash": "..."}`

3. **Send with query**: Include uploaded files in the session request payload:
   ```json
   {
     "text": "What is this file about?",
     "agent": "...",
     "sessionId": "...",
     "files": [
       {
         "hash": "<from upload response>",
         "path": "<key from upload response>",
         "source": "ATTACHMENTS",
         "audio": null | {"duration": <seconds>}
       }
     ]
   }
   ```

#### File Categories

All files in a single request must belong to the **same category** (server restriction):

| Category | OTR fileType | Extensions |
|----------|-------------|------------|
| DOC | `PDF`, `WORD`, `PPTX`, `SPREADSHEET`, `EPUB`, `TEXT` | pdf, docx, doc, pptx, xlsx, txt, py, js, html, etc. |
| IMAGE | `IMAGE` | jpg, jpeg, png, webp, heic, heif, bmp |
| AUDIO | `AUDIO` | mp3, aac, m4a, opus, wav, ogg |

## Project Structure

```
gigaplexity-mcp/
├── pyproject.toml              # Package config (uvx-compatible)
├── README.md                   # Usage & setup
├── ARCHITECTURE.md             # This file
├── LICENSE                     # MIT
├── .env.example                # Template for environment variables
├── src/
│   └── gigaplexity/
│       ├── __init__.py
│       ├── server.py           # MCP server entry point
│       ├── client.py           # GigaChat HTTP client (SSE)
│       ├── models.py           # Pydantic models for requests/responses
│       └── config.py           # Environment-based configuration
└── tests/
    ├── __init__.py
    ├── test_models.py          # Unit tests for models
    ├── test_client.py          # Tests for client (mocked)
    └── test_integration.py     # Integration tests (real API, skipped by default)
```

## Components

### 1. `config.py` — Configuration

Loads all settings from environment variables:
- `GIGACHAT_COOKIES` — Full cookie string (or individual cookie vars)
- `GIGACHAT_SM_SESS` — JWT session token
- `GIGACHAT_USER_ID` — User UUID
- `GIGACHAT_PROJECT_ID` — Project UUID
- `GIGACHAT_USER_AGENT` — Custom User-Agent string
- `GIGACHAT_BASE_URL` — API base URL (default: `https://giga.chat`)
- `GIGACHAT_APP_VERSION` — Application version (default: `0.94.4`)

### 2. `models.py` — Data Models

Pydantic models for:
- `SearchRequest` — Internal representation of a search query
- `SSEEvent` — Parsed SSE event
- `SearchResult` — Aggregated response with text + citations
- `Citation` — Source reference (title, URL)
- `FileCategory` — Enum for attachment categories (DOC, IMAGE, AUDIO)
- `AttachmentInfo` — Uploaded file metadata (hash, key, category)
- `resolve_file_type()` — Maps file extensions to OTR type + category

### 3. `client.py` — GigaChat Client

HTTP client using `httpx` with SSE streaming:
- Creates sessions (generates UUID)
- Sends requests with proper headers/cookies
- Parses SSE stream and aggregates response
- Handles keep-alive and error events
- **Uploads file attachments** (OTR creation + multipart upload)
- Returns structured `SearchResult`

### 4. `server.py` — MCP Server

FastMCP server exposing three tools:
- `ask(query: str, file_paths: list[str] | None)` — Quick web search with citations, optionally with file attachments
- `research(query: str, domains: list[str], extended: bool)` — Deep research
- `reason(query: str)` — Reasoning with web search

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GIGACHAT_SM_SESS` | Yes | JWT session token (`_sm_sess` cookie) |
| `GIGACHAT_USER_ID` | Yes | User UUID (`_sm_user_id` cookie) |
| `GIGACHAT_PROJECT_ID` | Yes | Project UUID (`x-project-id` header) |
| `GIGACHAT_COOKIES` | No | Full cookie string (overrides individual cookies) |
| `GIGACHAT_USER_AGENT` | No | Browser User-Agent |
| `GIGACHAT_BASE_URL` | No | Base URL (default: `https://giga.chat`) |
| `GIGACHAT_APP_VERSION` | No | App version (default: `0.94.4`) |
| `GIGACHAT_LANGUAGE` | No | Language preference (default: `en`) |
| `GIGACHAT_TIMEZONE` | No | Timezone (default: `UTC`) |

## Dependencies

- `mcp[cli]` — MCP SDK for Python
- `httpx` — Async HTTP client
- `httpx-sse` — SSE support for httpx
- `pydantic` — Data validation
- `pydantic-settings` — Settings from env vars

## Installation

```bash
# Via uvx (recommended for MCP)
uvx --from git+https://github.com/alexsvdk/gigaplexity-mcp gigaplexity-mcp

# Via pip
pip install git+https://github.com/alexsvdk/gigaplexity-mcp
```

## MCP Configuration

```json
{
  "mcpServers": {
    "gigaplexity": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/alexsvdk/gigaplexity-mcp", "gigaplexity-mcp"],
      "env": {
        "GIGACHAT_SM_SESS": "your-jwt-token",
        "GIGACHAT_USER_ID": "your-user-id",
        "GIGACHAT_PROJECT_ID": "your-project-id"
      }
    }
  }
}
```
