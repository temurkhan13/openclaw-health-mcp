"""Tests for the mock backend — verifies the sample data has the right shape
and triggers expected health classifications.
"""
from __future__ import annotations

import pytest

from openclaw_health_mcp.backends.mock import MockBackend
from openclaw_health_mcp.types import (
    CronHealthSummary,
    DiskUsage,
    GatewayStatus,
    HealthLevel,
    RecentErrorsResponse,
    ResourceMetrics,
    Severity,
    SkillRegistryCheck,
    UpgradeStatus,
)


@pytest.fixture
def backend() -> MockBackend:
    return MockBackend()


async def test_gateway_status_shape(backend: MockBackend) -> None:
    g = await backend.get_gateway_status()
    assert isinstance(g, GatewayStatus)
    assert g.is_alive is True
    assert g.bind_address is not None
    assert g.health == HealthLevel.DEGRADED
    assert any("0.0.0.0" in n for n in g.notes), "expected note about 0.0.0.0 binding"


async def test_resource_metrics_shape(backend: MockBackend) -> None:
    r = await backend.get_resource_metrics()
    assert isinstance(r, ResourceMetrics)
    assert r.cpu_percent is not None and 0.0 <= r.cpu_percent <= 100.0
    assert r.memory_percent is not None and 0.0 <= r.memory_percent <= 100.0
    assert r.oom_events_24h >= 0
    assert r.overall_health in (HealthLevel.HEALTHY, HealthLevel.DEGRADED, HealthLevel.CRITICAL)


async def test_recent_errors_default_filters(backend: MockBackend) -> None:
    response = await backend.get_recent_errors()
    assert isinstance(response, RecentErrorsResponse)
    assert response.window_hours == 24
    assert response.min_severity == Severity.WARNING
    # Default should exclude INFO entries
    assert all(e.severity != Severity.INFO for e in response.entries)
    # Should include the WARNING + ERROR sample entries
    assert len(response.entries) >= 3


async def test_recent_errors_min_severity_error(backend: MockBackend) -> None:
    response = await backend.get_recent_errors(min_severity=Severity.ERROR)
    assert all(e.severity in (Severity.ERROR, Severity.CRITICAL) for e in response.entries)


async def test_recent_errors_window_filter(backend: MockBackend) -> None:
    short = await backend.get_recent_errors(window_hours=1)
    long = await backend.get_recent_errors(window_hours=24)
    assert len(short.entries) <= len(long.entries)


async def test_skill_registry_check_critical(backend: MockBackend) -> None:
    s = await backend.get_skill_registry_check()
    assert isinstance(s, SkillRegistryCheck)
    assert s.health == HealthLevel.CRITICAL
    assert len(s.skills_flagged_suspicious) >= 1
    assert s.total_skills > 0


async def test_upgrade_status_rollback(backend: MockBackend) -> None:
    u = await backend.get_upgrade_status()
    assert isinstance(u, UpgradeStatus)
    assert u.last_upgrade_outcome == "rollback"
    assert "websocket_stalls" in u.regression_markers
    assert u.health == HealthLevel.DEGRADED


async def test_cron_health_basic(backend: MockBackend) -> None:
    c = await backend.get_cron_health()
    assert isinstance(c, CronHealthSummary)
    assert c.total_jobs > 0
    assert c.overdue_jobs >= 1
    assert 0.0 <= c.success_rate_24h <= 1.0


async def test_disk_usage_shape(backend: MockBackend) -> None:
    d = await backend.get_disk_usage()
    assert isinstance(d, DiskUsage)
    assert d.root_used_percent is not None and 0.0 <= d.root_used_percent <= 100.0
    assert d.log_directory is not None
    assert len(d.largest_log_files) > 0


async def test_backend_name_attribute(backend: MockBackend) -> None:
    assert backend.name == "mock"
