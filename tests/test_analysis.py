"""Tests for analysis.classify_overall, extract_critical_findings, and build_snapshot.

Covers:
- Classification reduction rules (CRITICAL > DEGRADED > HEALTHY > UNKNOWN)
- Specific critical-pattern triggers (gateway down, OOM, swap thrashing, disk >95%)
- Snapshot composition includes all components in component_summary
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from openclaw_health_mcp.analysis import (
    build_snapshot,
    classify_overall,
    extract_critical_findings,
)
from openclaw_health_mcp.backends.mock import MockBackend
from openclaw_health_mcp.types import (
    CronHealthSummary,
    DiskUsage,
    GatewayStatus,
    HealthLevel,
    ResourceMetrics,
    SkillRegistryCheck,
    UpgradeStatus,
)

# ─────────── classify_overall ───────────


def test_classify_overall_critical_dominates() -> None:
    assert (
        classify_overall(
            [HealthLevel.HEALTHY, HealthLevel.DEGRADED, HealthLevel.CRITICAL, HealthLevel.HEALTHY]
        )
        == HealthLevel.CRITICAL
    )


def test_classify_overall_degraded_when_no_critical() -> None:
    assert (
        classify_overall([HealthLevel.HEALTHY, HealthLevel.DEGRADED, HealthLevel.HEALTHY])
        == HealthLevel.DEGRADED
    )


def test_classify_overall_healthy_when_all_healthy() -> None:
    assert classify_overall([HealthLevel.HEALTHY] * 6) == HealthLevel.HEALTHY


def test_classify_overall_unknown_when_all_unknown() -> None:
    assert classify_overall([HealthLevel.UNKNOWN] * 3) == HealthLevel.UNKNOWN


def test_classify_overall_unknown_does_not_block_higher() -> None:
    assert (
        classify_overall([HealthLevel.UNKNOWN, HealthLevel.HEALTHY])
        == HealthLevel.HEALTHY
    )
    assert (
        classify_overall([HealthLevel.UNKNOWN, HealthLevel.DEGRADED])
        == HealthLevel.DEGRADED
    )


# ─────────── critical-finding triggers ───────────


def _empty_components() -> tuple[
    GatewayStatus, ResourceMetrics, SkillRegistryCheck, UpgradeStatus, CronHealthSummary, DiskUsage
]:
    """A neutral-state set of components (everything HEALTHY/UNKNOWN, no triggers)."""
    return (
        GatewayStatus(is_alive=True, health=HealthLevel.HEALTHY),
        ResourceMetrics(
            cpu_percent=20.0,
            memory_percent=40.0,
            swap_percent=0.0,
            oom_events_24h=0,
            cpu_health=HealthLevel.HEALTHY,
            memory_health=HealthLevel.HEALTHY,
            overall_health=HealthLevel.HEALTHY,
        ),
        SkillRegistryCheck(total_skills=10, enabled_skills=10, health=HealthLevel.HEALTHY),
        UpgradeStatus(current_version="2026.4.30", health=HealthLevel.HEALTHY),
        CronHealthSummary(total_jobs=5, overdue_jobs=0, health=HealthLevel.HEALTHY),
        DiskUsage(root_used_percent=40.0, health=HealthLevel.HEALTHY),
    )


def test_findings_empty_when_all_healthy() -> None:
    g, r, s, u, c, d = _empty_components()
    assert extract_critical_findings(g, r, s, u, c, d) == []


def test_finding_gateway_down() -> None:
    _, r, s, u, c, d = _empty_components()
    g = GatewayStatus(is_alive=False, health=HealthLevel.CRITICAL)
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("Gateway is not alive" in f for f in findings)


def test_finding_gateway_crash_loop() -> None:
    _, r, s, u, c, d = _empty_components()
    g = GatewayStatus(is_alive=True, crashes_24h=5, health=HealthLevel.DEGRADED)
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("crashed 5 times" in f for f in findings)


def test_finding_oom_events() -> None:
    g, _, s, u, c, d = _empty_components()
    r = ResourceMetrics(
        cpu_percent=20.0,
        memory_percent=70.0,
        swap_percent=0.0,
        oom_events_24h=2,
        overall_health=HealthLevel.CRITICAL,
    )
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("OOM kill" in f for f in findings)


def test_finding_swap_thrashing() -> None:
    g, _, s, u, c, d = _empty_components()
    r = ResourceMetrics(
        cpu_percent=20.0,
        memory_percent=85.0,
        swap_percent=72.0,
        overall_health=HealthLevel.CRITICAL,
    )
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("Swap at" in f and "thrashing" in f for f in findings)


def test_finding_disk_critical() -> None:
    g, r, s, u, c, _ = _empty_components()
    d = DiskUsage(root_used_percent=97.5, health=HealthLevel.CRITICAL)
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("Root disk at 97.5%" in f for f in findings)


def test_finding_disk_degraded() -> None:
    g, r, s, u, c, _ = _empty_components()
    d = DiskUsage(root_used_percent=88.0, health=HealthLevel.DEGRADED)
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("Root disk at 88.0%" in f and "DEGRADED" in f for f in findings)


def test_finding_upgrade_rollback() -> None:
    g, r, s, _, c, d = _empty_components()
    u = UpgradeStatus(
        current_version="2026.4.23",
        last_upgrade_from_version="2026.4.23",
        last_upgrade_to_version="2026.4.26",
        last_upgrade_outcome="rollback",
        regression_markers=["websocket_stalls"],
        health=HealthLevel.DEGRADED,
    )
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("rolled back" in f for f in findings)


def test_finding_skill_suspicious() -> None:
    g, r, _, u, c, d = _empty_components()
    s = SkillRegistryCheck(
        total_skills=10,
        enabled_skills=10,
        skills_flagged_suspicious=["bad-skill-1"],
        health=HealthLevel.CRITICAL,
    )
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("bad-skill-1" in f for f in findings)


def test_finding_cron_overdue() -> None:
    g, r, s, u, _, d = _empty_components()
    c = CronHealthSummary(total_jobs=5, overdue_jobs=3, health=HealthLevel.DEGRADED)
    findings = extract_critical_findings(g, r, s, u, c, d)
    assert any("3 cron job(s) overdue" in f for f in findings)


# ─────────── build_snapshot ───────────


@pytest.fixture
def backend() -> MockBackend:
    return MockBackend()


async def test_build_snapshot_from_mock(backend: MockBackend) -> None:
    """End-to-end: run mock backend through every component, build a snapshot,
    verify shape + that mock's deliberately-bad data triggers CRITICAL overall."""
    snap = build_snapshot(
        gateway=await backend.get_gateway_status(),
        resources=await backend.get_resource_metrics(),
        skill_registry=await backend.get_skill_registry_check(),
        upgrade=await backend.get_upgrade_status(),
        cron=await backend.get_cron_health(),
        disk=await backend.get_disk_usage(),
    )
    assert snap.overall_health == HealthLevel.CRITICAL
    assert isinstance(snap.captured_at, datetime)
    assert snap.captured_at.tzinfo == UTC
    assert set(snap.component_summary.keys()) == {
        "gateway",
        "resources",
        "skill_registry",
        "upgrade",
        "cron",
        "disk",
    }
    assert len(snap.critical_findings) >= 1, "mock data should produce at least one critical finding"


async def test_build_snapshot_healthy_components() -> None:
    """All-healthy components → overall HEALTHY, no findings."""
    g, r, s, u, c, d = _empty_components()
    snap = build_snapshot(g, r, s, u, c, d)
    assert snap.overall_health == HealthLevel.HEALTHY
    assert snap.critical_findings == []
