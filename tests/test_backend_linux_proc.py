"""Tests for the linux-proc backend.

Mocks psutil + subprocess so tests pass on Linux/macOS/Windows without
depending on real /proc data, real journalctl output, or real /var/log access.

Verifies:
- Resource metrics produce correct HealthLevel classification at threshold boundaries
- OOM detection counts journalctl matches
- Recent errors filter by min_severity
- Disk usage reports DEGRADED >85% and CRITICAL >95%
- OpenClaw-specific methods return UNKNOWN with explanatory notes
"""
from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from openclaw_health_mcp.backends.linux_proc import LinuxProcBackend
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
def backend() -> LinuxProcBackend:
    return LinuxProcBackend()


# ──────────────── Helper: fake psutil ────────────────


def _fake_psutil(
    *,
    cpu_pct: float = 30.0,
    mem_pct: float = 50.0,
    mem_used: int = 1024 * 1024 * 1024,
    mem_total: int = 2 * 1024 * 1024 * 1024,
    swap_pct: float = 5.0,
    swap_used: int = 100 * 1024 * 1024,
    disk_pct: float = 50.0,
    disk_used: int = 10 * 1024 ** 3,
    disk_total: int = 20 * 1024 ** 3,
    load: tuple[float, float, float] = (0.5, 0.6, 0.7),
) -> SimpleNamespace:
    """Build a fake psutil module with the given metrics."""
    mem = SimpleNamespace(percent=mem_pct, used=mem_used, total=mem_total)
    swap = SimpleNamespace(percent=swap_pct, used=swap_used)
    disk = SimpleNamespace(percent=disk_pct, used=disk_used, total=disk_total)
    return SimpleNamespace(
        cpu_percent=lambda interval=None: cpu_pct,
        virtual_memory=lambda: mem,
        swap_memory=lambda: swap,
        disk_usage=lambda _path: disk,
        getloadavg=lambda: load,
    )


# ──────────────── Resource metrics ────────────────


@pytest.fixture
def patched_no_oom() -> Iterator[None]:
    """Stub OOM count to 0 so resource_health classification depends only on cpu/mem/swap."""
    with patch("openclaw_health_mcp.backends.linux_proc._count_oom_events_24h", return_value=0):
        yield


async def test_resource_metrics_healthy(backend: LinuxProcBackend, patched_no_oom: None) -> None:
    fake = _fake_psutil(cpu_pct=20.0, mem_pct=40.0, swap_pct=5.0)
    with patch("openclaw_health_mcp.backends.linux_proc.psutil", fake):
        r = await backend.get_resource_metrics()
    assert isinstance(r, ResourceMetrics)
    assert r.cpu_percent == 20.0
    assert r.memory_percent == 40.0
    assert r.cpu_health == HealthLevel.HEALTHY
    assert r.memory_health == HealthLevel.HEALTHY
    assert r.overall_health == HealthLevel.HEALTHY
    assert r.oom_events_24h == 0


async def test_resource_metrics_memory_degraded(
    backend: LinuxProcBackend, patched_no_oom: None
) -> None:
    fake = _fake_psutil(cpu_pct=20.0, mem_pct=78.0)
    with patch("openclaw_health_mcp.backends.linux_proc.psutil", fake):
        r = await backend.get_resource_metrics()
    assert r.memory_health == HealthLevel.DEGRADED
    assert r.overall_health == HealthLevel.DEGRADED
    assert any("Memory at 78" in n for n in r.notes)


async def test_resource_metrics_memory_critical(
    backend: LinuxProcBackend, patched_no_oom: None
) -> None:
    fake = _fake_psutil(cpu_pct=20.0, mem_pct=97.0)
    with patch("openclaw_health_mcp.backends.linux_proc.psutil", fake):
        r = await backend.get_resource_metrics()
    assert r.memory_health == HealthLevel.CRITICAL
    assert r.overall_health == HealthLevel.CRITICAL


async def test_resource_metrics_swap_critical(
    backend: LinuxProcBackend, patched_no_oom: None
) -> None:
    fake = _fake_psutil(cpu_pct=20.0, mem_pct=60.0, swap_pct=72.0)
    with patch("openclaw_health_mcp.backends.linux_proc.psutil", fake):
        r = await backend.get_resource_metrics()
    assert r.swap_percent == 72.0
    assert r.overall_health == HealthLevel.CRITICAL


async def test_resource_metrics_oom_makes_critical(backend: LinuxProcBackend) -> None:
    """An OOM event in last 24h escalates overall_health to CRITICAL even if cpu/mem look healthy."""
    fake = _fake_psutil(cpu_pct=10.0, mem_pct=30.0, swap_pct=0.0)
    with (
        patch("openclaw_health_mcp.backends.linux_proc.psutil", fake),
        patch("openclaw_health_mcp.backends.linux_proc._count_oom_events_24h", return_value=2),
    ):
        r = await backend.get_resource_metrics()
    assert r.oom_events_24h == 2
    assert r.overall_health == HealthLevel.CRITICAL
    assert any("OOM" in n for n in r.notes)


# ──────────────── Recent errors ────────────────


_SAMPLE_JOURNALCTL_OUTPUT = """\
May  3 04:12:01 host kernel: ERROR: critical syscall failed
May  3 04:13:11 host openclaw[14872]: WARNING: WebSocket disconnect (code=1006)
May  3 04:14:22 host systemd[1]: INFO: Reached target multi-user
May  3 04:15:33 host openclaw[14872]: ERROR: Plugin failed: web-search
"""


async def test_recent_errors_filters_by_min_severity_warning(backend: LinuxProcBackend) -> None:
    with (
        patch("openclaw_health_mcp.backends.linux_proc.platform.system", return_value="Linux"),
        patch(
            "openclaw_health_mcp.backends.linux_proc._safe_run",
            return_value=_SAMPLE_JOURNALCTL_OUTPUT,
        ),
    ):
        response = await backend.get_recent_errors(window_hours=24, min_severity=Severity.WARNING)
    assert isinstance(response, RecentErrorsResponse)
    # 2 ERROR + 1 WARNING; INFO excluded
    assert response.total_count == 3
    severities = {e.severity for e in response.entries}
    assert Severity.INFO not in severities
    assert Severity.ERROR in severities
    assert Severity.WARNING in severities


async def test_recent_errors_filters_by_min_severity_error(backend: LinuxProcBackend) -> None:
    with (
        patch("openclaw_health_mcp.backends.linux_proc.platform.system", return_value="Linux"),
        patch(
            "openclaw_health_mcp.backends.linux_proc._safe_run",
            return_value=_SAMPLE_JOURNALCTL_OUTPUT,
        ),
    ):
        response = await backend.get_recent_errors(window_hours=24, min_severity=Severity.ERROR)
    assert all(e.severity in (Severity.ERROR, Severity.CRITICAL) for e in response.entries)


async def test_recent_errors_returns_empty_on_non_linux(backend: LinuxProcBackend) -> None:
    with patch("openclaw_health_mcp.backends.linux_proc.platform.system", return_value="Windows"):
        response = await backend.get_recent_errors()
    assert response.total_count == 0
    assert response.entries == []


# ──────────────── Disk usage ────────────────


async def test_disk_usage_healthy(backend: LinuxProcBackend) -> None:
    fake = _fake_psutil(disk_pct=50.0, disk_used=10 * 1024 ** 3, disk_total=20 * 1024 ** 3)
    with patch("openclaw_health_mcp.backends.linux_proc.psutil", fake):
        d = await backend.get_disk_usage()
    assert isinstance(d, DiskUsage)
    assert d.root_used_percent == 50.0
    assert d.health == HealthLevel.HEALTHY


async def test_disk_usage_degraded_at_88(backend: LinuxProcBackend) -> None:
    fake = _fake_psutil(disk_pct=88.0, disk_used=18 * 1024 ** 3, disk_total=20 * 1024 ** 3)
    with patch("openclaw_health_mcp.backends.linux_proc.psutil", fake):
        d = await backend.get_disk_usage()
    assert d.health == HealthLevel.DEGRADED
    assert any("88" in n for n in d.notes)


async def test_disk_usage_critical_at_97(backend: LinuxProcBackend) -> None:
    fake = _fake_psutil(disk_pct=97.0, disk_used=19 * 1024 ** 3, disk_total=20 * 1024 ** 3)
    with patch("openclaw_health_mcp.backends.linux_proc.psutil", fake):
        d = await backend.get_disk_usage()
    assert d.health == HealthLevel.CRITICAL
    assert any("imminent" in n.lower() for n in d.notes)


# ──────────────── Stubbed OpenClaw-specific methods ────────────────


async def test_gateway_status_unknown_with_note(backend: LinuxProcBackend) -> None:
    g = await backend.get_gateway_status()
    assert isinstance(g, GatewayStatus)
    assert g.health == HealthLevel.UNKNOWN
    assert any("openclaw" in n.lower() for n in g.notes)


async def test_skill_registry_unknown(backend: LinuxProcBackend) -> None:
    s = await backend.get_skill_registry_check()
    assert isinstance(s, SkillRegistryCheck)
    assert s.health == HealthLevel.UNKNOWN


async def test_upgrade_status_unknown(backend: LinuxProcBackend) -> None:
    u = await backend.get_upgrade_status()
    assert isinstance(u, UpgradeStatus)
    assert u.health == HealthLevel.UNKNOWN


async def test_cron_health_unknown_silentwatch_hint(backend: LinuxProcBackend) -> None:
    c = await backend.get_cron_health()
    assert isinstance(c, CronHealthSummary)
    assert c.health == HealthLevel.UNKNOWN
    assert any("silentwatch" in n.lower() for n in c.notes)


# ──────────────── Backend registry ────────────────


def test_linux_proc_in_registry() -> None:
    from openclaw_health_mcp.backends import available_backends, get_backend

    assert "linux-proc" in available_backends()
    backend = get_backend("linux-proc")
    assert backend.name == "linux-proc"


# ──────────────── OOM detection unit ────────────────


def test_count_oom_events_returns_zero_on_non_linux() -> None:
    from openclaw_health_mcp.backends.linux_proc import _count_oom_events_24h

    with patch("openclaw_health_mcp.backends.linux_proc.platform.system", return_value="Darwin"):
        assert _count_oom_events_24h() == 0


def test_count_oom_events_counts_pattern_matches() -> None:
    from openclaw_health_mcp.backends.linux_proc import _count_oom_events_24h

    fake_journalctl = (
        "May  3 12:00 host kernel: Out of memory: Killed process 1234 (python)\n"
        "May  3 13:00 host kernel: just a normal log line\n"
        "May  3 14:00 host kernel: oom-kill: Killed process 5678\n"
    )
    with (
        patch("openclaw_health_mcp.backends.linux_proc.platform.system", return_value="Linux"),
        patch("openclaw_health_mcp.backends.linux_proc._safe_run", return_value=fake_journalctl),
    ):
        assert _count_oom_events_24h() == 2


# ──────────────── Severity detection unit ────────────────


def test_detect_severity_recognizes_common_tokens() -> None:
    from openclaw_health_mcp.backends.linux_proc import _detect_severity

    assert _detect_severity("[ERROR] something broke") == Severity.ERROR
    assert _detect_severity("WARNING: getting slow") == Severity.WARNING
    assert _detect_severity("CRITICAL: system going down") == Severity.CRITICAL
    # No severity token at all — should not classify
    assert _detect_severity("the system completed startup successfully") is None
    # Lowercase 'info' embedded in a tagged line still counts (post-.upper()) — that's intentional;
    # callers default to min_severity=warning which excludes INFO anyway.
    assert _detect_severity("INFO: system completed startup") == Severity.INFO
