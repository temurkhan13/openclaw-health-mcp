"""Overall-health classification + critical-findings extraction.

Pure functions, no I/O. Backends produce per-component data; this module
consumes it and produces the aggregate HealthSnapshot.

Classification rules (deliberately simple — easy to override in production):
  CRITICAL  if any component is CRITICAL, OR any "critical pattern" matches
  DEGRADED  if any component is DEGRADED (and none CRITICAL)
  HEALTHY   if all components HEALTHY
  UNKNOWN   if no component reports HEALTHY/DEGRADED/CRITICAL (all UNKNOWN)
"""
from __future__ import annotations

from datetime import UTC, datetime

from openclaw_health_mcp.types import (
    CronHealthSummary,
    DiskUsage,
    GatewayStatus,
    HealthLevel,
    HealthSnapshot,
    ResourceMetrics,
    SkillRegistryCheck,
    UpgradeStatus,
)


def classify_overall(component_levels: list[HealthLevel]) -> HealthLevel:
    """Reduce a list of per-component HealthLevels to one overall classification."""
    if any(level == HealthLevel.CRITICAL for level in component_levels):
        return HealthLevel.CRITICAL
    if any(level == HealthLevel.DEGRADED for level in component_levels):
        return HealthLevel.DEGRADED
    if any(level == HealthLevel.HEALTHY for level in component_levels):
        return HealthLevel.HEALTHY
    return HealthLevel.UNKNOWN


def extract_critical_findings(
    gateway: GatewayStatus,
    resources: ResourceMetrics,
    skill_registry: SkillRegistryCheck,
    upgrade: UpgradeStatus,
    cron: CronHealthSummary,
    disk: DiskUsage,
) -> list[str]:
    """Build a flat human-readable list of critical findings, ordered by severity.

    A finding is "critical" if (a) the component reports CRITICAL, or (b) a specific
    pattern triggers regardless of component classification (e.g., gateway down,
    OOM events, disk >95%). DEGRADED components contribute findings only if they
    have notes worth surfacing.
    """
    findings: list[str] = []

    # Gateway
    if not gateway.is_alive:
        findings.append("[CRITICAL] Gateway is not alive — agents cannot receive or dispatch requests.")
    elif gateway.health == HealthLevel.CRITICAL:
        findings.extend(f"[CRITICAL] Gateway: {note}" for note in gateway.notes)
    elif gateway.crashes_24h is not None and gateway.crashes_24h >= 3:
        findings.append(
            f"[CRITICAL] Gateway crashed {gateway.crashes_24h} times in 24h — investigate crash-loop pattern."
        )

    # Resources
    if resources.oom_events_24h > 0:
        findings.append(
            f"[CRITICAL] {resources.oom_events_24h} OOM kill(s) in 24h "
            f"— kernel killed processes due to memory pressure."
        )
    if resources.memory_percent is not None and resources.memory_percent >= 95.0:
        findings.append(
            f"[CRITICAL] Memory at {resources.memory_percent:.1f}% — OOM imminent."
        )
    if resources.swap_percent is not None and resources.swap_percent >= 50.0:
        findings.append(
            f"[CRITICAL] Swap at {resources.swap_percent:.1f}% — system thrashing, expect severe latency."
        )

    # Skill registry
    if skill_registry.health == HealthLevel.CRITICAL:
        for skill in skill_registry.skills_flagged_suspicious:
            findings.append(
                f"[CRITICAL] Skill flagged suspicious: '{skill}'. Disable until vetted (see openclaw-skill-vetter-mcp)."
            )
        if not skill_registry.skills_flagged_suspicious:
            for note in skill_registry.notes:
                findings.append(f"[CRITICAL] Skill registry: {note}")

    # Upgrade
    if upgrade.last_upgrade_outcome == "failure":
        findings.append(
            f"[CRITICAL] Last upgrade ({upgrade.last_upgrade_from_version}→{upgrade.last_upgrade_to_version}) "
            f"failed. System may be in inconsistent state."
        )
    elif upgrade.last_upgrade_outcome == "rollback":
        markers = (
            ", ".join(upgrade.regression_markers)
            if upgrade.regression_markers
            else "no markers recorded"
        )
        findings.append(
            f"[DEGRADED] Last upgrade rolled back "
            f"({upgrade.last_upgrade_from_version}→{upgrade.last_upgrade_to_version}). "
            f"Regression markers: {markers}."
        )

    # Disk
    if disk.root_used_percent is not None and disk.root_used_percent >= 95.0:
        findings.append(f"[CRITICAL] Root disk at {disk.root_used_percent:.1f}% — risk of write failure imminent.")
    elif disk.root_used_percent is not None and disk.root_used_percent >= 85.0:
        findings.append(
            f"[DEGRADED] Root disk at {disk.root_used_percent:.1f}% — set up log rotation before reaching 95%."
        )

    # Cron — basic; richer findings come from silentwatch-mcp
    if cron.overdue_jobs > 0:
        findings.append(
            f"[DEGRADED] {cron.overdue_jobs} cron job(s) overdue. "
            f"Install silentwatch-mcp for silent-failure detection."
        )

    return findings


def build_snapshot(
    gateway: GatewayStatus,
    resources: ResourceMetrics,
    skill_registry: SkillRegistryCheck,
    upgrade: UpgradeStatus,
    cron: CronHealthSummary,
    disk: DiskUsage,
) -> HealthSnapshot:
    """Compose a HealthSnapshot from per-component results."""
    component_summary: dict[str, HealthLevel] = {
        "gateway": gateway.health,
        "resources": resources.overall_health,
        "skill_registry": skill_registry.health,
        "upgrade": upgrade.health,
        "cron": cron.health,
        "disk": disk.health,
    }

    overall = classify_overall(list(component_summary.values()))
    findings = extract_critical_findings(gateway, resources, skill_registry, upgrade, cron, disk)

    return HealthSnapshot(
        captured_at=datetime.now(UTC),
        overall_health=overall,
        gateway=gateway,
        resources=resources,
        skill_registry=skill_registry,
        upgrade=upgrade,
        cron=cron,
        disk=disk,
        component_summary=component_summary,
        critical_findings=findings,
    )
