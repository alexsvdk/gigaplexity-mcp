# Changelog

Все заметные изменения в проекте фиксируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
и проект стремится следовать [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

### Added
- Preflight auth check (`GET /api/check`) on MCP server start, with a configurable JWT `exp` skew to catch clearly-expired cookies locally without a network call. See [`docs/refresh-strategy.md`](docs/refresh-strategy.md).
- `AuthExpiredError` (subclass of `GigaChatError`) with an actionable message explaining how to refresh the `_sm_sess` cookie.
- New env var `GIGACHAT_PREFLIGHT_ON_START` (default `true`) to toggle the preflight check.
- New env var `GIGACHAT_PREFLIGHT_SKEW` (default `60`) — seconds before JWT `exp` to treat the token as expired.
- `gigaplexity.jwt_utils` — small helper module for decoding JWT payloads and checking `exp`.

### Changed
- `GigaChatError` now lives in `gigaplexity.errors`. The export is re-exposed from `gigaplexity.client` for backwards compatibility.
- Mid-flight 401/403, `token has expired`, and `GC-ATT-E005` responses now raise `AuthExpiredError` instead of the generic `GigaChatError`. Attachments upload and search paths both use the new mapping.
- `config.py` decodes JWTs via `gigaplexity.jwt_utils.decode_jwt_payload` (removes a duplicate inline implementation).

### Security
- 

---

## [0.1.0] - 2026-04-17

### Added
- Initial MCP server with tools: `ask`, `research`, `reason`.
- Core client for GigaChat web endpoints.
- SSE response parsing and markdown formatting.
- Unit and integration test foundation.

[Unreleased]: https://github.com/alexsvdk/gigaplexity-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/alexsvdk/gigaplexity-mcp/releases/tag/v0.1.0
