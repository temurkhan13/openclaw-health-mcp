# Changelog

All notable changes to `openclaw-health-mcp` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/temurkhan13/openclaw-health-mcp/releases/tag/v0.1.0
