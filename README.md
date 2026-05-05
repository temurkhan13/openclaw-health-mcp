# openclaw-health-mcp

<!-- mcp-name: io.github.temurkhan13/openclaw-health-mcp -->

> **MCP server for AI agent deployment health** — gateway status, CPU/RAM/swap, recent errors from journalctl/dmesg, skill-registry integrity, upgrade outcomes, cron + disk usage in a single tool call. Each component gets a HEALTHY/DEGRADED/CRITICAL classification, with overall rollup + ranked critical findings. **Linux-proc backend works on any Linux/macOS/Windows host; OpenClaw operators get native `~/.openclaw/` parsing as a built-in reference implementation.** Keywords: AI agent health, production AI monitoring, deployment readiness, MCP infrastructure observability.

[![Status: v1.0.0](https://img.shields.io/badge/status-v1.0.0-brightgreen)](https://github.com/temurkhan13/openclaw-health-mcp) [![Tests: 59 passing](https://img.shields.io/badge/tests-59%20passing-brightgreen)](./tests) [![License: MIT](https://img.shields.io/badge/license-MIT-blue)](./LICENSE) [![MCP](https://img.shields.io/badge/protocol-MCP-purple)](https://modelcontextprotocol.io/) [![PyPI](https://img.shields.io/pypi/v/openclaw-health-mcp)](https://pypi.org/project/openclaw-health-mcp/)

---

## What it does

Anyone running production AI agents needs a single tool that answers "is this deployment healthy right now?" without SSH'ing in to run six separate commands. The HN front-page thread [Ask HN: How are you monitoring AI agents in production?](https://news.ycombinator.com/item?id=47301395) (March 2026) made the gap explicit — the most-upvoted comments described:

- *"observability and governance cannot live inside the agent framework. They have to live in an independent execution layer"* — the framework-level monitoring leaks audit trail when teams use multiple frameworks
- *"agent makes 10,000 correct $0.02 decisions that collectively don't make sense"* — per-call rate limits miss systemic patterns
- The gap that "actually hurts during post-mortems" — knowing whether a model drifted, context window failed, or tool misbehaved

Existing options (LangSmith, Langfuse, AgentShield, OTEL/LGTM) sit at the framework or proxy layer. **`openclaw-health-mcp` sits one level closer to the agent runtime** — read-only, local, MCP-native — surfacing infrastructure-layer health (gateway, CPU/RAM, recent errors, skill-registry, upgrade outcome, cron, disk) to the same Claude conversation that's running the agent. Works on any Linux/macOS/Windows host out of the box via the `linux-proc` backend; OpenClaw operators get an additional native backend that parses `~/.openclaw/` paths.

```
> claude: is my OpenClaw deployment healthy?
[MCP tool: health_overview]
overall_health: critical
component_summary:
  gateway: degraded         (bound to 0.0.0.0, 1 crash in 24h)
  resources: degraded       (memory at 78%, swap at 12%)
  skill_registry: critical  (skill 'clawhub-trending-bot-v2' flagged suspicious)
  upgrade: degraded         (last upgrade rolled back)
  cron: degraded            (1 overdue job)
  disk: degraded            (root at 82%, log dir +187 MB/24h)

critical_findings:
  [CRITICAL] Skill 'clawhub-trending-bot-v2' flagged — possible exfiltration. Disable.
  [DEGRADED] Last upgrade 2026.4.23→2026.4.26 rolled back: websocket_stalls, cpu_spike.
  [DEGRADED] Root disk at 82% — set up log rotation before reaching 95%.
  [DEGRADED] 1 cron job(s) overdue. Install silentwatch-mcp for silent-failure detection.
```

---

## Why `openclaw-health-mcp`

Three things that existing tools (Datadog, Prometheus, raw `top`/`free`/`df`) don't do for OpenClaw specifically:

1. **OpenClaw-aware probes.** Detects 0.0.0.0-binding (the default-publicly-exposed misconfig per the 135k exposed-instances stat), parses ClawHub skill-registry diffs, recognizes named upgrade-regression patterns (`websocket_stalls`, `cpu_spike` post-2026.4.26), distinguishes intentional restarts from crashes.
2. **MCP-native, no integration layer.** Claude Desktop, Cline, Continue, OpenClaw agents — any MCP-aware client queries directly. No Grafana plugin, no API wrapper, no JSON to parse manually.
3. **Composable with the rest of the production-AI MCP stack.** Pairs with [silentwatch-mcp](https://github.com/temurkhan13/silentwatch-mcp) (cron silent-failure detection — `cron_health` here is intentionally basic and defers to silentwatch when present). Skill-registry vetting in this server is light heuristics; deep static analysis goes in `openclaw-skill-vetter-mcp` (planned).

Built for the **SMB self-hoster** running OpenClaw on a $40 VPS where Datadog is overkill — but the OpenClaw-specific patterns are valuable on enterprise infra too.

---

## Tool surface

The server registers these MCP tools (full spec in [SPEC.md](./SPEC.md)):

| Tool | Returns |
|------|---------|
| `health_overview` | Full snapshot — every component + overall HealthLevel + ranked critical findings |
| `gateway_status` | Gateway alive/dead, uptime, restarts, crashes, bind address |
| `cpu_memory_health` | CPU/memory/swap snapshot + 24h OOM count + load averages |
| `recent_errors(window_hours, min_severity)` | Recent error/warning entries, filterable by lookback + severity |
| `skill_registry_check` | Skill counts, recent additions/modifications, light heuristic flags |
| `last_upgrade_status` | From-version, to-version, outcome, regression markers, available upgrade |
| `cron_health` | Basic cron summary (defers to silentwatch-mcp when richer detection wanted) |
| `disk_usage` | Root disk + log directory size + 24h growth + largest log files |

Resources:

- `health://overview` — full snapshot (same as `health_overview` tool)
- `health://gateway` — gateway-only
- `health://resources` — CPU/memory-only

Prompts:

- `diagnose-degraded-health` — diagnostic walk-through, ranked corrective actions
- `summarize-health-trend` — daily operational digest

---

## Quickstart

### Install

```bash
pip install openclaw-health-mcp
```

### Configure for Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "openclaw-health": {
      "command": "python",
      "args": ["-m", "openclaw_health_mcp"],
      "env": {
        "OPENCLAW_HEALTH_BACKEND": "mock"
      }
    }
  }
}
```

Restart Claude Desktop. Test:

> Show me a full health snapshot of my OpenClaw deployment.

The mock backend returns deliberately mixed data (gateway DEGRADED, skill registry CRITICAL, etc.) so the response demonstrates the full schema.

### Backends

| Backend | Status | Description |
|---------|--------|-------------|
| `mock` | ✅ v1.0 | Sample data for protocol-wiring verification (default) |
| `linux-proc` | ✅ v1.0 | psutil-based system metrics (CPU/memory/swap/load/disk) cross-platform; Linux-specific OOM-event detection via `journalctl`/`dmesg`; recent-error log parsing via journalctl. Returns UNKNOWN for OpenClaw-specific components (gateway, skill_registry, upgrade, cron) — those need the `openclaw` backend |
| `openclaw` | ⏳ v1.1 | Parses OpenClaw config + log directory + ClawHub manifest + upgrade journal |

Select via `OPENCLAW_HEALTH_BACKEND` env var. Multi-backend support (federating `linux-proc` system metrics + `openclaw` application-specific) is planned for v1.2.

---

## Roadmap

| Version | Scope | Status |
|---------|-------|--------|
| v0.1 | Protocol wiring, mock backend, 8 tools / 3 resources / 2 prompts, 40 tests | ✅ |
| v1.0 | `linux-proc` backend (psutil + journalctl/dmesg OOM detection + log parsing); GitHub Actions CI matrix; PyPI Trusted Publishing; MCP Registry submission; 59 tests | ✅ |
| v1.1 | `openclaw` backend — parses OpenClaw config, log dir, ClawHub manifest, upgrade journal | ⏳ |
| v1.2 | Backend federation (`linux-proc + openclaw`); expanded log sources | ⏳ |
| v1.x | `cowork` backend, custom backend SDK, webhook emitter for alerts | ⏳ |

---

## Need this adapted to your stack?

`openclaw-health-mcp` ships with a mock backend at v0.1 (Linux + OpenClaw backends in v0.2). If your AI agent runtime is different — Claude Code, Cowork, custom Python services, agent harnesses on AWS / GCP — and you want the same single-pane health visibility for it, that's a **Custom MCP Build** engagement.

| Tier | Scope | Investment | Timeline |
|------|-------|------------|----------|
| Simple | Single backend adapter for an existing runtime with documented logging/metrics | **$8,000–$10,000** | 1–2 weeks |
| Standard | Custom backend + custom severity rules + integration with your existing alerting | **$15,000–$20,000** | 2–4 weeks |
| Complex | Multi-backend federation + RBAC + audit-log integration + on-call workflow | **$25,000–$35,000** | 4–8 weeks |

**To engage:**
1. Email **temur@pixelette.tech** with subject `Custom MCP Build inquiry`
2. Include: a 1-paragraph description of your stack + which tier you're considering
3. Reply within 2 business days with a 30-min discovery call slot

This server is part of a **production-AI infrastructure MCP suite** — companion to [silentwatch-mcp](https://github.com/temurkhan13/silentwatch-mcp) (cron silent-failure detection) and the upcoming [AI Production Discipline Framework Notion template](https://temurah.gumroad.com/l/ai-production-discipline-framework) (the methodology these tools operationalize).

---

## Production AI audits

If you're running production AI and want an outside practitioner to score readiness, find the failure patterns already present, and write the corrective-action plan — that's what this MCP is built into supporting:

| Tier | Scope | Investment | Timeline |
|------|-------|------------|----------|
| Audit Lite | One system, top-5 findings, written report | **$1,500** | 1 week |
| Audit Standard | Full audit, all 14 patterns, 5 Cs findings, 90-day follow-up | **$3,000** | 2–3 weeks |
| Audit + Workshop | Standard audit + 2-day team workshop + first monthly audit included | **$7,500** | 3–4 weeks |

Same email channel: **temur@pixelette.tech** with subject `AI audit inquiry`.

---

## Contributing

PRs welcome. Backends are intentionally pluggable — see `src/openclaw_health_mcp/backends/` for the contract.

To add a new backend:

1. Subclass `HealthBackend` in `backends/<your_backend>.py`
2. Implement the 7 abstract probe methods (one per component)
3. Register in `backends/__init__.py`
4. Add tests in `tests/test_backend_<your_backend>.py`

Bug reports + feature requests: open a GitHub issue.

---

## License

MIT — see [LICENSE](./LICENSE).

---

## Related

- [Production-AI MCP Suite (Gumroad bundle)](https://temurah.gumroad.com/l/production-ai-mcp-suite) — this server plus 5 others in one curated 6-pack bundle with a decision tree, day-one drill, and Custom MCP Build CTA. $99, or $49 with `LAUNCH50` for the first 30 days.
- [silentwatch-mcp](https://github.com/temurkhan13/silentwatch-mcp) — cron silent-failure detection. Install alongside this server for richer `cron_health` data.
- [openclaw-cost-tracker-mcp](https://github.com/temurkhan13/openclaw-cost-tracker-mcp) — token-cost telemetry + 429 prediction (v1.1+)
- [openclaw-skill-vetter-mcp](https://github.com/temurkhan13/openclaw-skill-vetter-mcp) — ClawHub skill security vetting
- [openclaw-upgrade-orchestrator-mcp](https://github.com/temurkhan13/openclaw-upgrade-orchestrator-mcp) — read-only upgrade advisor + provider-side regression detection (v1.2+)
- [openclaw-output-vetter-mcp](https://github.com/temurkhan13/openclaw-output-vetter-mcp) — agent claim verification (inline grounding-check + swallowed-exception scanner + multi-turn transcript review)
- [AI Production Discipline Framework](https://temurah.gumroad.com/l/ai-production-discipline-framework) — Notion template, $29 — the methodology these MCP tools implement.
- [SPEC.md](./SPEC.md) — full server design.
- [Model Context Protocol](https://modelcontextprotocol.io/) — protocol overview.

---

Built by [Temur Khan](https://www.notion.so/@temurkhan) — independent practitioner on production AI systems.
Contact: **temur@pixelette.tech**
