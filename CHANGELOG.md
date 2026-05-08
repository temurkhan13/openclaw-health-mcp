# Changelog

All notable changes to `openclaw-health-mcp` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.5] — 2026-05-08

### Added — `openclaw-health-mcp-demo` console script (V1 of cross-product UX retrofit)

A new console script that runs all 7 health checks against the bundled mock backend and prints a one-page operator-readable health overview in ~30 seconds. Intended for the first-30-seconds-after-install moment.

The mock backend is hand-crafted to exhibit a representative mix of post-upgrade health states:

- Gateway DEGRADED (1 crash post 2026.4.26 upgrade, bound to 0.0.0.0)
- CPU + memory DEGRADED (memory 78% on a 2GB VPS)
- Recent errors: 4 WARNING+ entries from gateway / web-search skill
- Skills CRITICAL (`clawhub-trending-bot-v2` flagged for ClawHavoc-pattern exfiltration)
- Upgrade DEGRADED (2026.4.23→2026.4.26 rollback 2 days ago)
- Cron DEGRADED (1 job overdue 72h)
- Disk DEGRADED (82% root, gateway.log alone is 1.2 GB)

Output mirrors what the MCP server returns via the `health_overview` tool — but rendered as a plain-English summary instead of JSON.

**Usage:**

```
$ pip install openclaw-health-mcp
$ openclaw-health-mcp-demo
openclaw-health-mcp v1.0.5 · synthetic demo

  Gateway · ⚠ DEGRADED
    alive:                yes
    crashes (24h):        1
  ...
  Skill registry · ✗ CRITICAL
    flagged:              clawhub-trending-bot-v2
  ...

  Verdict: ✗ CRITICAL — at least one component requires immediate attention.
```

**No external I/O.** Demo runs against the in-memory mock backend; no network, no API keys, no filesystem access. Safe to run anywhere.

Adds a second console-script entry (`openclaw-health-mcp-demo`) alongside the existing MCP server entry.

## [1.0.4] — 2026-05-08

### Added — first-run startup banner (visibility-after-install fix, V2 of cross-product UX retrofit)

When the server starts via `python -m openclaw_health_mcp` or the console script, the first stderr line is now a one-line value-prove receipt:

```
openclaw-health-mcp v1.0.4 ready · gateway/skills/logs/upgrade-status checks · backend=mock
```

Before v1.0.4 the server started silently — operators who'd just `pip install`ed had no immediate signal of what the server actually does. The banner is the first-30-seconds value moment that was previously missing.

**Suppressible:** set `OPENCLAW_HEALTH_QUIET=1` (or `true` / `yes`) to skip the banner.

**No protocol behavior changed.** Banner is stderr-only; stdout (the MCP JSON-RPC channel) is untouched. Pure observability addition.

## [1.0.3] — 2026-05-06

### Changed — overnight Phase 1B + 2B docs/test refresh

Bundles two commits already on main as a single PyPI republish:

- [`25b4b4c`](https://github.com/temurkhan13/openclaw-health-mcp/commit/25b4b4c) **test:** server-protocol coverage gap-fillers (Phase 1B). Tests-only — registration / dispatch / unknown-tool fallback; raises `server.py` coverage 65% → 86%. Note: the invalid-severity defensive branch is unreachable through the MCP protocol's enum-validator, documented as known-uncovered.
- [`edd8906`](https://github.com/temurkhan13/openclaw-health-mcp/commit/edd8906) **docs:** SPEC.md drift fix. Pre-existing SPEC header read "v0.1 (alpha — mock backend only) / 31 tests" but the package shipped v1.0.x five+ months back with the linux-proc backend production-ready and 74 tests passing. SPEC now correctly reflects the v1.0.x surface.

No code or detection-rule changes. Patch bump republishes to PyPI so the SPEC text matches the rendered "Project description" page.

## [1.0.2] — 2026-05-05

### Changed — cross-link mesh extension to 6th MCP
- README "Related" section updated to reference [openclaw-output-vetter-mcp](https://github.com/temurkhan13/openclaw-output-vetter-mcp) (v1.0.1, shipped 2026-05-04). Bundle reference updated to "5 others / 6-pack". Cost-tracker description annotated with v1.1+ (quota-window awareness); upgrade-orchestrator with v1.2+ (provider-side regression detection). Pure metadata refresh — no code changes.

## [1.0.1] — 2026-05-04

### Changed — README v2 metadata refresh (PyPI republish)
- README repositioned with universal-first lede + HN Ask HN buyer-mental-model citations (commits `76ff0c9` + `b7a7429`). Originally landed in repo on 2026-05-04; this patch bump republishes to PyPI so the new description lands in PyPI search index. No code changes.
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

[Unreleased]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/temurkhan13/openclaw-health-mcp/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/temurkhan13/openclaw-health-mcp/releases/tag/v0.1.0
