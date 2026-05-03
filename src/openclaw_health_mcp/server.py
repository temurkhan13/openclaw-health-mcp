"""MCP server — registers tools, resources, prompts; delegates to backends + analysis."""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    TextContent,
    Tool,
)

from openclaw_health_mcp.analysis import build_snapshot
from openclaw_health_mcp.backends import get_backend
from openclaw_health_mcp.backends.base import HealthBackend
from openclaw_health_mcp.types import Severity

logger = logging.getLogger(__name__)

SERVER_NAME = "openclaw-health"


def build_server(backend_name: str = "mock") -> Server:
    """Construct a configured MCP server with the given backend selected."""
    backend: HealthBackend = get_backend(backend_name)
    server: Server = Server(SERVER_NAME)

    # ─────────────────────────── Tools ───────────────────────────

    @server.list_tools()  # type: ignore[misc, no-untyped-call]
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="health_overview",
                description=(
                    "Full deployment health snapshot — gateway + resources + skill registry + "
                    "upgrade status + cron + disk in one call. Returns overall HealthLevel "
                    "(healthy/degraded/critical/unknown) plus per-component breakdown plus "
                    "ranked critical_findings list. Use this first for a single-pane summary."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="gateway_status",
                description=(
                    "Status of the OpenClaw gateway process: alive/dead, uptime, recent "
                    "restarts (intentional vs crashes), bind address, PID. Flags 0.0.0.0 "
                    "binding (default-publicly-exposed config)."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="cpu_memory_health",
                description=(
                    "CPU% + memory% + swap% snapshot, kernel OOM-kill count over 24h, "
                    "load averages. Each component gets a HealthLevel; CRITICAL when "
                    "OOM-imminent or already triggered."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="recent_errors",
                description=(
                    "Recent error/warning log entries from gateway + skills + cron. "
                    "Filterable by lookback window and minimum severity."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "window_hours": {
                            "type": "integer",
                            "description": "Lookback window in hours (default 24, max 168)",
                            "default": 24,
                        },
                        "min_severity": {
                            "type": "string",
                            "description": (
                                "Minimum severity to return "
                                "(debug/info/warning/error/critical, default warning)"
                            ),
                            "default": "warning",
                            "enum": ["debug", "info", "warning", "error", "critical"],
                        },
                    },
                    "required": [],
                },
            ),
            Tool(
                name="skill_registry_check",
                description=(
                    "ClawHub / skill-registry integrity: total skills, recently added/modified, "
                    "skills with external HTTP endpoints, light heuristic flags. For deep "
                    "static analysis (prompt-injection patterns, exfiltration), install "
                    "openclaw-skill-vetter-mcp."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="last_upgrade_status",
                description=(
                    "Last OpenClaw upgrade attempt: from-version, to-version, outcome "
                    "(success/rollback/failure/in_progress), regression markers detected "
                    "post-upgrade (e.g., websocket_stalls, cpu_spike). Includes available-upstream-version."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="cron_health",
                description=(
                    "Basic cron summary: total jobs, overdue count, 24h success rate. "
                    "For richer detection (silent failures, output anomalies, "
                    "duration drift), install silentwatch-mcp alongside this server. "
                    "When silentwatch_available=True, the caller should query that server too."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
            Tool(
                name="disk_usage",
                description=(
                    "Root-disk usage% + log-directory size + 24h growth + largest log files. "
                    "Flags >85% as DEGRADED, >95% as CRITICAL."
                ),
                inputSchema={"type": "object", "properties": {}, "required": []},
            ),
        ]

    @server.call_tool()  # type: ignore[misc, no-untyped-call]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        logger.debug("call_tool name=%s args=%s", name, arguments)

        if name == "health_overview":
            gateway = await backend.get_gateway_status()
            resources = await backend.get_resource_metrics()
            skill_registry = await backend.get_skill_registry_check()
            upgrade = await backend.get_upgrade_status()
            cron = await backend.get_cron_health()
            disk = await backend.get_disk_usage()
            snapshot = build_snapshot(gateway, resources, skill_registry, upgrade, cron, disk)
            return _serialize(snapshot)

        if name == "gateway_status":
            return _serialize(await backend.get_gateway_status())

        if name == "cpu_memory_health":
            return _serialize(await backend.get_resource_metrics())

        if name == "recent_errors":
            window_hours = max(1, min(int(arguments.get("window_hours", 24)), 168))
            severity_str = str(arguments.get("min_severity", "warning")).lower()
            try:
                min_severity = Severity(severity_str)
            except ValueError:
                return [
                    TextContent(
                        type="text",
                        text=f'{{"error": "Unknown severity: {severity_str!r}. '
                        f'Valid: debug/info/warning/error/critical"}}',
                    )
                ]
            return _serialize(await backend.get_recent_errors(window_hours, min_severity))

        if name == "skill_registry_check":
            return _serialize(await backend.get_skill_registry_check())

        if name == "last_upgrade_status":
            return _serialize(await backend.get_upgrade_status())

        if name == "cron_health":
            return _serialize(await backend.get_cron_health())

        if name == "disk_usage":
            return _serialize(await backend.get_disk_usage())

        return [TextContent(type="text", text=f'{{"error": "Unknown tool: {name}"}}')]

    # ─────────────────────── Resources ────────────────────────

    @server.list_resources()  # type: ignore[misc, no-untyped-call]
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri="health://overview",
                name="Health overview snapshot",
                description="Full deployment health snapshot (overall + per-component + critical findings)",
                mimeType="application/json",
            ),
            Resource(
                uri="health://gateway",
                name="Gateway status",
                description="Current gateway process status",
                mimeType="application/json",
            ),
            Resource(
                uri="health://resources",
                name="CPU + memory metrics",
                description="Current CPU/memory/swap snapshot",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()  # type: ignore[misc, no-untyped-call]
    async def read_resource(uri: str) -> str:
        if uri == "health://overview":
            gateway = await backend.get_gateway_status()
            resources = await backend.get_resource_metrics()
            skill_registry = await backend.get_skill_registry_check()
            upgrade = await backend.get_upgrade_status()
            cron = await backend.get_cron_health()
            disk = await backend.get_disk_usage()
            snapshot = build_snapshot(gateway, resources, skill_registry, upgrade, cron, disk)
            return snapshot.model_dump_json(indent=2)

        if uri == "health://gateway":
            return (await backend.get_gateway_status()).model_dump_json(indent=2)

        if uri == "health://resources":
            return (await backend.get_resource_metrics()).model_dump_json(indent=2)

        return json.dumps({"error": f"Unknown resource URI: {uri}"})

    # ──────────────────────── Prompts ────────────────────────

    @server.list_prompts()  # type: ignore[misc, no-untyped-call]
    async def list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="diagnose-degraded-health",
                description="Walk a HealthSnapshot and propose ranked corrective actions",
                arguments=[
                    PromptArgument(
                        name="focus_component",
                        description=(
                            "Optional component to prioritize "
                            "(gateway/resources/skill_registry/upgrade/cron/disk). "
                            "Omit for overall triage."
                        ),
                        required=False,
                    )
                ],
            ),
            Prompt(
                name="summarize-health-trend",
                description="Daily digest of deployment health activity",
                arguments=[],
            ),
        ]

    @server.get_prompt()  # type: ignore[misc, no-untyped-call]
    async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> GetPromptResult:
        arguments = arguments or {}
        if name == "diagnose-degraded-health":
            focus = arguments.get("focus_component", "").strip().lower()
            focus_clause = (
                f"Prioritize the `{focus}` component in your analysis. "
                if focus
                else "Cover all components but order findings by severity. "
            )
            text = (
                "Call `health_overview` to get the current snapshot. "
                f"{focus_clause}"
                "For each CRITICAL or DEGRADED finding: state the symptom in one sentence, "
                "name the most likely root cause, then propose a specific corrective action "
                "(a config change, a command to run, a setting to flip — not 'investigate further'). "
                "Rank findings by impact-blast-radius (gateway down > OOM > disk full > overdue cron). "
                "Stop at 5 findings to avoid overwhelming the operator."
            )
            return GetPromptResult(
                description="Diagnostic walk-through for degraded deployment",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=text),
                    )
                ],
            )

        if name == "summarize-health-trend":
            text = (
                "Call `health_overview` and `recent_errors` (window_hours=24, min_severity=warning). "
                "Compose a 200-word operational digest: overall HealthLevel, count of CRITICAL "
                "and DEGRADED components, top 3 critical findings, count of warnings + errors in 24h, "
                "and the single highest-priority follow-up the operator should act on today. "
                "End with one sentence: 'Status as of <ISO timestamp>: <healthy/degraded/critical>.'"
            )
            return GetPromptResult(
                description="Daily deployment health digest",
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=text),
                    )
                ],
            )

        return GetPromptResult(
            description=f"Unknown prompt: {name}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=f"Unknown prompt: {name}"),
                )
            ],
        )

    return server


def _serialize(model: Any) -> list[TextContent]:
    """Pydantic model → MCP TextContent (single block, JSON-serialized)."""
    return [TextContent(type="text", text=model.model_dump_json(indent=2))]
