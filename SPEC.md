# `openclaw-health-mcp` — Server Spec

**Version:** v1.0.2
**Status:** mock + linux-proc backends production-ready; openclaw-system backend planned for v1.1
**Tests:** 74 passing (overnight Phase 1B added 15 server-protocol coverage tests)
**Last updated:** 2026-05-06 (overnight Phase 2B drift fix)

---

## Goal (verifiable "done" criterion for v1.0)

A user runs `claude mcp add openclaw-health`, restarts Claude Desktop (or any MCP client), and from inside Claude can:

1. Call `health_overview` and receive a single snapshot covering gateway + resources + skill registry + upgrade + cron + disk, with overall HealthLevel and ranked critical_findings.
2. Call any of the 7 component tools (`gateway_status`, `cpu_memory_health`, etc.) for focused detail.
3. Call `recent_errors(window_hours=24, min_severity=warning)` and get filtered log entries.
4. Read resource `health://overview` for the same snapshot data.
5. Use `diagnose-degraded-health` prompt to walk a snapshot into ranked corrective actions.

All without writing bespoke parsing for `/proc/`, `journalctl`, ClawHub manifest, or OpenClaw config files. All without exposing the data to a third-party SaaS. All using a $0/mo open-source tool.

---

## Non-goals

- **Not a metrics platform.** No time-series store, no Grafana dashboard, no alert routing. Use this MCP server alongside your existing alerting; don't make it the alerting system.
- **Not enterprise-scale.** Designed for single-host or small-cluster (≤10 hosts) OpenClaw deployments. Multi-region federation is a Custom MCP Build engagement.
- **Not vendor-locked.** OpenClaw is the primary target, but the architecture is pluggable; Linux `/proc` reading is generic and `cowork` / Claude Code backends ship in v0.2+.
- **Not a remediation tool.** Read-only. Doesn't restart processes, modify configs, or apply fixes. (That scope creep belongs in a separate `openclaw-upgrade-orchestrator-mcp` — also planned.)
- **Not a deep-static-analysis tool.** `skill_registry_check` does light heuristics (counts + flags). Deep prompt-injection / exfiltration analysis lives in `openclaw-skill-vetter-mcp` (planned MCP #3).

---

## Tool surface

### `health_overview`

```
health_overview() -> HealthSnapshot
```

Returns the full deployment snapshot. No parameters.

**Response shape:**
```json
{
  "captured_at": "2026-05-04T03:58:42Z",
  "overall_health": "critical",
  "gateway": { "is_alive": true, "bind_address": "0.0.0.0:18789", "restarts_24h": 2, "crashes_24h": 1, "health": "degraded", "...": "..." },
  "resources": { "cpu_percent": 42.7, "memory_percent": 78.3, "oom_events_24h": 0, "overall_health": "degraded", "...": "..." },
  "skill_registry": { "total_skills": 47, "skills_flagged_suspicious": ["clawhub-trending-bot-v2"], "health": "critical", "...": "..." },
  "upgrade": { "current_version": "2026.4.23", "last_upgrade_outcome": "rollback", "regression_markers": ["websocket_stalls", "cpu_spike"], "health": "degraded", "...": "..." },
  "cron": { "total_jobs": 6, "overdue_jobs": 1, "health": "degraded", "silentwatch_available": false, "...": "..." },
  "disk": { "root_used_percent": 82.4, "log_directory_size_mb": 2840.0, "health": "degraded", "...": "..." },
  "component_summary": {
    "gateway": "degraded",
    "resources": "degraded",
    "skill_registry": "critical",
    "upgrade": "degraded",
    "cron": "degraded",
    "disk": "degraded"
  },
  "critical_findings": [
    "[CRITICAL] Skill flagged suspicious: 'clawhub-trending-bot-v2'. Disable until vetted (see openclaw-skill-vetter-mcp).",
    "[DEGRADED] Last upgrade rolled back (2026.4.23→2026.4.26). Regression markers: websocket_stalls, cpu_spike.",
    "[DEGRADED] Root disk at 82.4% — set up log rotation before reaching 95%.",
    "[DEGRADED] 1 cron job(s) overdue. Install silentwatch-mcp for silent-failure detection."
  ]
}
```

### `gateway_status`

Returns `GatewayStatus`. Detects 0.0.0.0 binding, distinguishes intentional restarts from crashes.

### `cpu_memory_health`

Returns `ResourceMetrics`. CPU%, memory%, swap%, OOM events in 24h, load averages, per-component HealthLevel, overall HealthLevel.

### `recent_errors`

```
recent_errors(window_hours: int = 24, min_severity: str = "warning") -> RecentErrorsResponse
```

Severity levels: `debug` < `info` < `warning` < `error` < `critical`. Filters to entries with severity ≥ `min_severity` within the last `window_hours`.

### `skill_registry_check`

Returns `SkillRegistryCheck`. Total count, recent adds/modifies in 24h, count of skills with external HTTP, flat list of skill names triggering basic heuristics. Light pass — defer to `openclaw-skill-vetter-mcp` for deep analysis.

### `last_upgrade_status`

Returns `UpgradeStatus`. Current version + last attempt's from→to + outcome (`success`/`rollback`/`failure`/`in_progress`) + recognized regression markers (`websocket_stalls`, `cpu_spike`, `cron_silent_fail`, etc. — patterns drawn from the gap-map analyses).

### `cron_health`

Returns `CronHealthSummary`. Total jobs, overdue count, 24h success rate. Sets `silentwatch_available=True` when an installed silentwatch-mcp could provide richer data on the same source — caller should query that server too.

### `disk_usage`

Returns `DiskUsage`. Root disk used %, log directory size + 24h growth, top-N largest log files. Flags >85% as DEGRADED, >95% as CRITICAL.

---

## Resource surface

| URI | Returns |
|-----|---------|
| `health://overview` | Full HealthSnapshot (same as `health_overview` tool) |
| `health://gateway` | GatewayStatus only |
| `health://resources` | ResourceMetrics only |

Resources are read-only and idempotent.

---

## Prompt surface

### `diagnose-degraded-health`

Walks the operator through interpreting a `health_overview` snapshot and proposing 3–5 ranked corrective actions, with optional `focus_component` argument to prioritize one component.

### `summarize-health-trend`

Generates a 200-word daily operational digest from `health_overview` + `recent_errors`, ending with the single highest-priority follow-up.

---

## Backend architecture

```
┌─────────────────────────────────┐
│ MCP Server (server.py)          │
│  - tool registration            │
│  - argument validation          │
│  - response serialization       │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│ HealthBackend (backends/base)   │
│  ABC with 7 probe methods:      │
│   - get_gateway_status()        │
│   - get_resource_metrics()      │
│   - get_recent_errors()         │
│   - get_skill_registry_check()  │
│   - get_upgrade_status()        │
│   - get_cron_health()           │
│   - get_disk_usage()            │
└──────────────┬──────────────────┘
               │
        ┌──────┼──────┬──────────┐
        ▼      ▼      ▼          ▼
     ┌────┐ ┌────────────┐ ┌──────────┐
     │mock│ │ linux-proc │ │ openclaw │
     └────┘ └────────────┘ └──────────┘
       v0.1     v0.2            v0.2
```

Each backend implements the 7 probe methods. Higher-level classification (overall HealthLevel, critical-pattern detection) lives in `analysis.py` and consumes whatever backends produce — backends are dumb collectors; analysis is centralized.

### Backend selection

Environment variable `OPENCLAW_HEALTH_BACKEND`:

- `mock` — sample data for protocol-wiring verification (default, ✅ shipped v0.1)
- `linux-proc` — reads `/proc/meminfo`, `/proc/stat`, `/proc/loadavg`, journalctl for OOM (⏳ v0.2)
- `openclaw` — parses OpenClaw config + log directory + ClawHub manifest + upgrade journal (⏳ v0.2)

Multi-backend support (`OPENCLAW_HEALTH_BACKEND=linux-proc,openclaw` — federated) is planned for v0.3.

---

## Health classification rules

Default rules, applied per-component and aggregated to overall:

| Component | HEALTHY | DEGRADED | CRITICAL |
|-----------|---------|----------|----------|
| Gateway | alive, ≤1 restart in 24h, bound to 127.0.0.1 | bound to 0.0.0.0 OR 2–3 crashes/24h | not alive OR ≥4 crashes/24h OR sustained crash-loop |
| Resources | memory<70%, no OOM, swap<20% | memory 70–90%, swap 20–50% | memory ≥95% OR ≥1 OOM kill OR swap ≥50% |
| Skill registry | no flags, no recent adds | adds/modifies in 24h, ≥10% with external HTTP | any skill flagged_suspicious, OR ≥30% external-HTTP |
| Upgrade | success, current pinned to recent stable | rollback, mismatched current/available | failure (system in inconsistent state) |
| Cron | success_rate_24h ≥0.95, no overdue | 0.80 ≤ success ≤0.95 OR ≥1 overdue | success<0.80 OR ≥3 overdue |
| Disk | root <70% | root 70–95% | root ≥95% |

Aggregation: any CRITICAL component → overall CRITICAL. Any DEGRADED → overall DEGRADED. All HEALTHY → overall HEALTHY. All UNKNOWN → overall UNKNOWN.

---

## Security + privacy

- **Read-only.** The server never modifies state, never restarts processes, never deletes logs.
- **Local-only by default.** All backends read local files / system commands; no outbound network calls.
- **Sensitive output redaction.** Configurable via `OPENCLAW_HEALTH_REDACT_PATTERNS` (regex list); matches replaced with `[REDACTED]` before any output reaches the MCP client. Default patterns redact API keys (`sk-[A-Za-z0-9]{20,}`), bearer tokens, and basic-auth headers.
- **No telemetry.** The server doesn't phone home, doesn't write usage stats anywhere, doesn't open ports.

For threat-model detail, see [SECURITY.md](./SECURITY.md) (planned for v0.3).

---

## Test surface

The test suite covers:

- **Protocol wiring** — `tests/test_server.py` verifies all 8 tools, 3 resources, 2 prompts register and that `call_tool` dispatches to the right backend method
- **Backend contract** — `tests/test_backend_mock.py` runs the mock through every method and asserts response shapes
- **Classification logic** — `tests/test_analysis.py` runs the classify_overall / extract_critical_findings / build_snapshot pure functions through known-good and known-bad inputs

Run: `pytest tests/`

Target coverage at v1.0: ≥85% line coverage on `src/`.

---

## Versioning + release

- Semantic versioning, leading to v1.0 once both `linux-proc` + `openclaw` backends ship + tests at target coverage + README + SPEC reviewed
- v0.x releases are pre-PyPI; install from source
- v1.0 published to PyPI as `openclaw-health-mcp`
- Each release tagged on GitHub with a changelog entry

---

## Future scope (post v1.0)

| Idea | Trigger to build |
|------|------------------|
| Backend federation | Demand from clients with mixed-source deployments (likely v0.3) |
| Cowork backend | First Cowork audit client |
| Claude Code backend | First Claude Code-deployed agent client |
| AWS / GCP backends | First cloud-hosted client (likely Custom MCP Build) |
| Webhook emitter (push DEGRADED/CRITICAL events) | Demand signal from ≥3 users |
| Web UI dashboard | Speculative; only if MCP-only access is genuinely a friction for a buyer cohort |

Out of scope (won't build): metrics push to Prometheus/InfluxDB, generic time-series storage, alert routing logic. Those are integration projects, not part of this MCP server.

---

## Lineage

This MCP server is part of the **[AI Production Discipline Framework](https://temurah.gumroad.com/l/ai-production-discipline-framework)** ecosystem. Severity rules trace to **patterns P1.x (gateway/runtime), P2.x (memory/CPU), P5.x (skill/plugin/supply chain), P4.x (configuration/upgrade), P10.x (cron), P9.x (cost/disk)** in the framework's Production Failure Patterns Library.

Companion server: **[silentwatch-mcp](https://github.com/temurkhan13/silentwatch-mcp)** — install both for full operational visibility.

For audit consulting that applies the framework to your specific system: **temur@pixelette.tech**, subject `AI audit inquiry`.
