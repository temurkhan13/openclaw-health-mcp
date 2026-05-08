"""Markdown rendering for openclaw-health overview reports."""
from __future__ import annotations

from openclaw_health_mcp.types import (
    CronHealthSummary,
    DiskUsage,
    GatewayStatus,
    HealthLevel,
    RecentErrorsResponse,
    ResourceMetrics,
    SkillRegistryCheck,
    UpgradeStatus,
)


def _badge(h: HealthLevel) -> str:
    if h == HealthLevel.HEALTHY:
        return "✓ HEALTHY"
    if h == HealthLevel.DEGRADED:
        return "⚠ DEGRADED"
    if h == HealthLevel.CRITICAL:
        return "✗ CRITICAL"
    return h.value.upper()


def render_health_overview(
    *,
    gateway: GatewayStatus,
    resources: ResourceMetrics,
    errors: RecentErrorsResponse,
    skills: SkillRegistryCheck,
    upgrade: UpgradeStatus,
    cron: CronHealthSummary,
    disk: DiskUsage,
    backend_name: str,
    version: str,
) -> str:
    """Render a complete health overview as a one-page markdown summary."""
    lines: list[str] = []
    lines.append("## openclaw-health · deployment health overview")
    lines.append("")

    levels = [
        gateway.health,
        resources.overall_health,
        skills.health,
        upgrade.health,
        cron.health,
        disk.health,
    ]
    if any(h == HealthLevel.CRITICAL for h in levels):
        verdict = "✗ CRITICAL — at least one component requires immediate attention"
    elif any(h == HealthLevel.DEGRADED for h in levels):
        verdict = "⚠ DEGRADED — multiple components are off baseline"
    else:
        verdict = "✓ HEALTHY — all checks within expected ranges"
    lines.append(f"**Backend:** `{backend_name}`  ·  **Verdict:** {verdict}")
    lines.append("")

    # Component summary table
    lines.append("| Component | Health | Key signal |")
    lines.append("|---|---|---|")
    lines.append(
        f"| Gateway | {_badge(gateway.health)} | "
        f"{'alive' if gateway.is_alive else 'DOWN'}, "
        f"uptime {gateway.uptime_seconds // 3600}h, "
        f"{gateway.crashes_24h} crash(es) in 24h |"
    )
    lines.append(
        f"| CPU + Memory | {_badge(resources.overall_health)} | "
        f"CPU {resources.cpu_percent}%, "
        f"memory {resources.memory_percent}% "
        f"({resources.memory_used_mb:.0f}/{resources.memory_total_mb:.0f} MB) |"
    )
    lines.append(
        f"| Recent errors ({errors.window_hours}h) | "
        f"{'⚠' if errors.total_count > 0 else '✓'} | "
        f"{errors.total_count} entr(ies) ≥ {errors.min_severity.value} |"
    )
    lines.append(
        f"| Skill registry | {_badge(skills.health)} | "
        f"{skills.enabled_skills}/{skills.total_skills} enabled, "
        f"{skills.skills_with_external_http} with external HTTP, "
        f"{len(skills.skills_flagged_suspicious)} flagged |"
    )
    lines.append(
        f"| Last upgrade | {_badge(upgrade.health)} | "
        f"current `{upgrade.current_version}`"
        + (f", available `{upgrade.available_version}`" if upgrade.available_version else "")
        + (f", last outcome: {upgrade.last_upgrade_outcome}" if upgrade.last_upgrade_outcome else "")
        + " |"
    )
    lines.append(
        f"| Cron | {_badge(cron.health)} | "
        f"{cron.total_jobs} jobs, {cron.overdue_jobs} overdue, "
        f"{cron.success_rate_24h:.0%} 24h success rate |"
    )
    lines.append(
        f"| Disk | {_badge(disk.health)} | "
        f"root {disk.root_used_percent}% "
        f"({disk.root_used_gb:.1f}/{disk.root_total_gb:.1f} GB), "
        f"log dir +{disk.log_directory_growth_mb_24h:.0f} MB/24h |"
    )
    lines.append("")

    # Notes — the actionable bits
    has_notes = any([
        gateway.notes,
        resources.notes,
        skills.notes,
        upgrade.notes,
        cron.notes,
        getattr(disk, "notes", None),
    ])
    if has_notes:
        lines.append("### Notes & action items")
        lines.append("")
        for label, notes in [
            ("Gateway", gateway.notes),
            ("CPU + Memory", resources.notes),
            ("Skill registry", skills.notes),
            ("Last upgrade", upgrade.notes),
            ("Cron", cron.notes),
            ("Disk", getattr(disk, "notes", []) or []),
        ]:
            if not notes:
                continue
            lines.append(f"**{label}:**")
            for n in notes:
                lines.append(f"- {n}")
            lines.append("")

    if errors.entries:
        lines.append("### Recent errors")
        lines.append("")
        lines.append("| Time | Severity | Source | Message |")
        lines.append("|---|---|---|---|")
        for e in errors.entries[:5]:
            msg = e.message.replace("|", "\\|").replace("\n", " ")
            if len(msg) > 80:
                msg = msg[:79] + "…"
            lines.append(
                f"| {e.timestamp.strftime('%H:%M:%S')} | {e.severity.value} | "
                f"`{e.source}` | {msg} |"
            )
        if errors.total_count > 5:
            lines.append(f"\n_… and {errors.total_count - 5} more_")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"> ℹ Generated by `openclaw-health-mcp-report` v{version} against the `{backend_name}` backend. "
        f"Set `OPENCLAW_HEALTH_BACKEND=openclaw|linux_proc` to run against your real deployment, "
        f"or invoke as an MCP server in Claude Code / Cursor / OpenClaw via the `health_overview` tool."
    )

    return "\n".join(lines)
