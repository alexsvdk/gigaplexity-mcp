# Fix GigaChat Neo Protocol Breakdown

## Goal
Restore MCP compatibility with the current GigaChat web protocol observed in `hars/giga.chat.har`, while keeping existing text streaming behavior and providing actionable diagnostics for attachment upload failures.

## Assumptions
- Text chat endpoints still accept the existing SSE parser shape.
- New sessions should be created server-side; the client should not send a synthetic `sessionId` for new requests.
- Attachment upload still needs live browser cookies/tokens; without a file-upload HAR, this task can only improve header alignment and error diagnostics, not invent an unobserved upload protocol.

## Subtasks

### 1. HAR-style request payload
- Dependencies: Existing `build_request_payload()` behavior in `src/gigaplexity/models.py`.
- Expected artifacts: Updated payload builder and regression tests.
- Definition of Done:
  - New-session payload contains `text`, `agent`, optional `model`, `aiAgent`, and `files`.
  - New-session payload does not contain `sessionId` or `featureFlags`.
  - ASK mode explicitly sends `GigaChat-3-Ultra`.

### 2. Server-owned session ID parsing
- Dependencies: SSE `ACCEPTED` event format and `SearchResult.session_id`.
- Expected artifacts: Client event parsing update and tests.
- Definition of Done:
  - `SearchResult.session_id` is populated from server SSE data when present.
  - Client no longer relies on a locally generated new-session UUID.
  - Existing message/model parsing remains compatible.

### 3. Header alignment by API surface
- Dependencies: Current `GigaplexitySettings.build_headers()` callers.
- Expected artifacts: Header helper methods for back-web/SSE/profile/attachments where useful.
- Definition of Done:
  - Default app identity is `gigachat-b2c-web-neo` and version `0.2.10`.
  - Existing common header expectations remain covered by tests.
  - Attachment and chat callers can use context-specific `Accept`/`Content-Type` without mutating unrelated defaults.

### 4. Attachment upload diagnostics
- Dependencies: `_create_otr()` and `_upload_file()` error paths.
- Expected artifacts: More specific `GigaChatError` message and unit test.
- Definition of Done:
  - Expired attachment token errors mention refreshing browser cookies and capturing upload HAR if needed.
  - Original HTTP status and server body snippet remain visible.
  - Upload flow remains otherwise unchanged until a real upload HAR is available.

### 5. Verification
- Dependencies: Code and test changes.
- Expected artifacts: Passing targeted tests and broader local test suite when possible.
- Definition of Done:
  - Unit tests for protocol changes pass.
  - Full pytest suite is attempted and any unrelated/environment failures are clearly reported.
  - A subagent validates completion against this breakdown before final response.

## Validation Results
- Focused protocol tests: `uv run --with pytest --with pytest-asyncio pytest tests/test_models.py tests/test_client.py` → 60 passed.
- Clean full suite without credentials: `env -u GIGACHAT_COOKIES -u GIGACHAT_SM_SESS -u GIGACHAT_PROJECT_ID -u GIGACHAT_USER_ID uv run --with pytest --with pytest-asyncio pytest` → 65 passed, 6 skipped.
- Live text integrations with `.env`: `uv run --with pytest --with pytest-asyncio pytest -m integration tests/test_integration.py -k 'test_ask_real or test_reason_real or test_research_real' -vv` → 3 passed, 3 deselected.
- Live attachment integrations with `.env`: upload fails with HTTP 401 `GC-ATT-E005`; the server says the attachment token expired at `2026-06-10T21:29:27Z`. This validates the new diagnostic but does not prove attachment upload is fixed.
- Subagent validation: attempted twice with the `Explore` agent, but Copilot reported the monthly credit limit was reached, so this DoD item is blocked externally.

## GitHub Issue Draft

### Title
GigaChat Neo protocol changes break MCP chat/session payloads and attachment uploads need fresh token handling evidence

### Problem
The GigaChat web client now uses the Neo app identity and creates new chat sessions with a minimal `/sessions/request` payload. The MCP client still sent older web identity headers plus a synthetic client-side `sessionId` and `featureFlags`, which made it brittle against the current protocol. Attachment uploads also return `GC-ATT-E005` with the current test cookies because the browser-issued attachment token is expired.

### Evidence
- HAR text request payload contains only `text`, `agent`, and `model` for ASK mode.
- HAR profile init uses `X-Application-Name: gigachat-b2c-web-neo` and `X-Application-Version: 0.2.10`.
- SSE `ACCEPTED` events provide the authoritative server `sessionId`.
- Live attachment upload returns HTTP 401 `GC-ATT-E005` with an explicit token-expired timestamp.

### Expected Outcome
- Text ask/reason/research requests work against the current GigaChat Neo protocol.
- New sessions are server-owned, with `sessionId` captured from SSE instead of invented locally.
- Attachment failures identify expired browser upload tokens and request fresh cookies/HAR evidence.

### Remaining Need
To truly repair attachment uploads, capture a fresh successful browser HAR while uploading a file with non-expired cookies/tokens. Keep that HAR private and redact cookies, authorization headers, and tokens before sharing. The current HAR does not include a successful upload request, and the current `.env` token is expired.

## Pull Request Draft

### Title
Align GigaChat client with Neo chat protocol and improve attachment diagnostics

### Summary
- Switch default GigaChat app identity to `gigachat-b2c-web-neo` version `0.2.10`.
- Align profile init and API-specific request headers with the observed HAR.
- Send HAR-style new-session chat payloads without synthetic `sessionId` or `featureFlags`.
- Capture server-owned `sessionId` from SSE `ACCEPTED` events.
- Add an actionable expired-token hint for attachment upload `GC-ATT-E005` failures.
- Add regression coverage for payload shape, headers, SSE session parsing, and attachment diagnostics.

### Validation
- `uv run --with pytest --with pytest-asyncio pytest tests/test_models.py tests/test_client.py` → 60 passed.
- `env -u GIGACHAT_COOKIES -u GIGACHAT_SM_SESS -u GIGACHAT_PROJECT_ID -u GIGACHAT_USER_ID uv run --with pytest --with pytest-asyncio pytest` → 65 passed, 6 skipped.
- `set -a; source .env; set +a; uv run --with pytest --with pytest-asyncio pytest -m integration tests/test_integration.py -k 'test_ask_real or test_reason_real or test_research_real' -vv` → 3 passed, 3 deselected.

### Notes
- Live attachment tests still fail with `GC-ATT-E005` because the upload token in `.env` is expired. This PR improves the diagnosis and keeps upload headers aligned, but a real upload-flow fix needs a fresh successful upload HAR. HAR files must stay private or be redacted before sharing because they can contain session credentials.
- Subagent completion validation was required by the original prompt but could not be completed because Copilot returned the monthly credit-limit error.
