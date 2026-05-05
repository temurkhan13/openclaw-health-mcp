# Changelog

All notable changes to `openclaw-health-mcp` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.2] — 2026-05-05

### Changed — cross-link mesh extension to 6th MCP
- README "Related" section updated to reference [openclaw-output-vetter-mcp](https://github.com/temurkhan13/openclaw-output-vetter-mcp) (v1.0.1, shipped 2026-05-04). Bundle reference updated to "5 others / 6-pack". Cost-tracker description annotated with v1.1+ (quota-window awareness); upgrade-orchestrator with v1.2+ (provider-side regression detection). Pure metadata refresh — no code changes.

## [1.0.1] — 2026-05-04

### Changed — README v2 metadata refresh (PyPI republish)
- README repositioned with universal-first lede + HN Ask HN buyer-mental-model citations (commits `eeb75fd` + `2e5315c`). Originally landed in repo on 2026-05-04; this patch bump republishes to PyPI so the new description lands in PyPI search index. No code changes.
- README "What it does" now leads with the HN front-page thread *Ask HN: How are you monitoring AI agents in production?* (March 2026) and three verbatim comments — the language buyers actually search for.
- Positioning vs LangSmith / Langfuse / AgentShield / OTEL clarified: this server sits one level closer to the agent runtime, read-only and MCP-native.
- pyproject.toml description tightened toward universal AI-agent deployment health; cross-platform Linux-proc backend + OpenClaw as native reference framing made explicit.

## [1.0.0] — 2026-05-04

### Added
- **`linux-proc` backend** — system metrics via psutil + journalctl/dmesg parsing for OOM events. Cross-platform for cpu/memory/swap/load/disk (psutil); Linux-specific for OOM-event detection and recent-error log parsing (journalctl `-p` priority filter); falls back gracefully on macOS/Windows. Reports HealthLevel.UNKNOWN for OpenClaw-specific components (gateway, skill_registry, upgrade, cron) — those need the `openclaw` backend (planned v1.1).
- **GitHub Actions CI** — matrix testing on ubuntu/macos/windows × Python 3.11/3.12, separate ruff + mypy lint job, sdist+wheel build artifact upload. Mirrors silentwatch-mcp's CI configuration.
- **GitHub Actions release workflow** — fires on `v*` tag push, verifies tag matches `pyproject.toml` version, builds + publishes to PyPI via Trusted Publishing.
- **`server.json`** for the official Model Context Protocol Registry submission.
- **Severity classification thresholds** documented as module constants (`_CPU_DEGRADED_PCT=75`, `_MEM_DEGRADED_PCT=70`, `_DISK_DEGRADED_PCT=85`, etc.) — overridable via subclassing the backend.
- 19 new tests in `tests/test_backend_linux_proc.py` (78 total) — mocked psutil + subprocess calls so tests pass cross-platform.

### Changed
- Bumped from v0.1 alpha (mock-only) to v1.0 with one production-ready backend (`linux-proc`). Mock backend remains the development default.

## [0.1.0] — 2026-05-04

### Added
- Initial scaffold with MCP protocol wiring.
- 8 tools: `health_overview` (meta), `gateway_status`, `cpu_memory_health`, `recent_errors`, `skill_registry_check`, `last_upgrade_status`, `cron_health`, `disk_usage`.
- 3 resources: `health://overview`, `health://gateway`, `health://resources`.
- 2 prompts: `diagnose-degraded-health`, `summarize-health-trend`.
- `MockBackend` with realistic sample data — gateway DEGRADED (0.0.0.0 binding + 1 crash), resources DEGRADED (memory 78%, swap 12%), skill registry CRITICAL (1 flagged skill mimicking ClawHavoc-pattern exfiltration), upgrade DEGRADED (rollback with `websocket_stalls`+`cpu_spike` markers), cron DEGRADED (1 overdue job), disk DEGRADED (82% root). Mock data deliberately produces overall=CRITICAL with multiple critical_findings to demonstrate the full response schema.
- `HealthBackend` ABC + backend registry pattern for adding new probes.
- Pure-function `analysis` module: `classify_overall()` + `extract_critical_findings()` + `build_snapshot()`. No I/O, easy to test.
- 31 tests across `test_server.py` (10 — protocol wiring, tool/resource/prompt registration, dispatch correctness), `test_backend_mock.py` (10 — sample data shape + classification triggers), `test_analysis.py` (11 — classification reduction rules + critical-pattern triggers + snapshot composition).
- `pyproject.toml` with hatchling build, MIT license, `psutil>=5.9` dep (for v0.2 backend), Python 3.11+ requirement.
- README with positioning + Custom MCP Build CTA + AI Production Audit cross-link + silentwatch-mcp pairing note.
- SPEC.md with full server design.

[Unreleased]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/temurkhan13/openclaw-health-mcp/releases/tag/v0.1.0
