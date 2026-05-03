"""Mock backend — realistic sample data for protocol-wiring verification.

Default backend during development. Lets users verify their MCP client
connection (Claude Desktop config, tool registration, response parsing) before
plugging in a real OpenClaw deployment.

Sample data deliberately includes:
  - Gateway DEGRADED (binds 0.0.0.0, 2 restarts in 24h)
  - Resources DEGRADED (memory at 78%, no OOM)
  - Skill registry CRITICAL (1 skill flagged suspicious)
  - Disk DEGRADED (logs growing fast)
  - Cron DEGRADED (1 overdue job)
  - Recent errors include 3 warnings + 1 error
  - Last upgrade rolled back

so the meta tool `health_overview` returns CRITICAL with a believable critical_findings list.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from openclaw_health_mcp.backends.base import HealthBackend
from openclaw_health_mcp.types import (
    CronHealthSummary,
    DiskUsage,
    ErrorEntry,
    GatewayStatus,
    HealthLevel,
    RecentErrorsResponse,
    ResourceMetrics,
    Severity,
    SkillRegistryCheck,
    UpgradeStatus,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _ago(**kwargs: int) -> datetime:
    return _now() - timedelta(**kwargs)


_ALL_SAMPLE_ERRORS: list[ErrorEntry] = [
    ErrorEntry(
        timestamp=_ago(minutes=12),
        severity=Severity.ERROR,
        source="gateway",
        message="WebSocket disconnect (code=1006), client=channel:telegram, reconnecting (attempt 3/10)",
    ),
    ErrorEntry(
        timestamp=_ago(minutes=47),
        severity=Severity.WARNING,
        source="gateway",
        message="Plugin 'web-search' exceeded action budget (21/20), throttled for 60s",
    ),
    ErrorEntry(
        timestamp=_ago(hours=2, minutes=8),
        severity=Severity.WARNING,
        source="skill:web-search",
        message="Empty result set for query template; falling back to cached response",
    ),
    ErrorEntry(
        timestamp=_ago(hours=4, minutes=33),
        severity=Severity.WARNING,
        source="cron:audit-snapshot",
        message="Run completed exit=0 but stdout was empty (silent-failure detected by silentwatch-mcp)",
    ),
    ErrorEntry(
        timestamp=_ago(hours=11, minutes=2),
        severity=Severity.INFO,
        source="gateway",
        message="Restart triggered by config reload (intentional)",
    ),
]


class MockBackend(HealthBackend):
    """In-memory backend with hand-crafted sample data."""

    name = "mock"

    async def get_gateway_status(self) -> GatewayStatus:
        return GatewayStatus(
            is_alive=True,
            last_restarted_at=_ago(hours=4, minutes=33),
            uptime_seconds=4 * 3600 + 33 * 60,
            pid=14872,
            bind_address="0.0.0.0:18789",
            restarts_24h=2,
            crashes_24h=1,
            health=HealthLevel.DEGRADED,
            notes=[
                "Bound to 0.0.0.0 — gateway is publicly exposed (default config). "
                "Bind to 127.0.0.1 unless intentional.",
                "1 unintentional crash in last 24h (post 2026.4.26 upgrade regression).",
            ],
        )

    async def get_resource_metrics(self) -> ResourceMetrics:
        return ResourceMetrics(
            cpu_percent=42.7,
            memory_percent=78.3,
            memory_used_mb=1602.0,
            memory_total_mb=2048.0,
            swap_percent=12.5,
            swap_used_mb=128.0,
            oom_events_24h=0,
            load_average_1m=1.42,
            load_average_5m=1.28,
            load_average_15m=1.12,
            cpu_health=HealthLevel.HEALTHY,
            memory_health=HealthLevel.DEGRADED,
            overall_health=HealthLevel.DEGRADED,
            notes=[
                "Memory at 78% — elevated for a 2GB VPS. Watch for OOM if a cron-heavy hour spikes load.",
            ],
        )

    async def get_recent_errors(
        self,
        window_hours: int = 24,
        min_severity: Severity = Severity.WARNING,
    ) -> RecentErrorsResponse:
        cutoff = _ago(hours=window_hours)
        severity_order = {
            Severity.DEBUG: 0,
            Severity.INFO: 1,
            Severity.WARNING: 2,
            Severity.ERROR: 3,
            Severity.CRITICAL: 4,
        }
        min_rank = severity_order[min_severity]
        filtered = [
            e
            for e in _ALL_SAMPLE_ERRORS
            if e.timestamp >= cutoff and severity_order[e.severity] >= min_rank
        ]
        return RecentErrorsResponse(
            window_hours=window_hours,
            min_severity=min_severity,
            total_count=len(filtered),
            entries=filtered,
            truncated=False,
        )

    async def get_skill_registry_check(self) -> SkillRegistryCheck:
        return SkillRegistryCheck(
            total_skills=47,
            enabled_skills=42,
            skills_added_24h=2,
            skills_modified_24h=0,
            skills_with_external_http=11,
            skills_flagged_suspicious=["clawhub-trending-bot-v2"],
            health=HealthLevel.CRITICAL,
            notes=[
                "Skill 'clawhub-trending-bot-v2' added in last 24h, makes HTTP POST to non-allowlisted host (raw IP). "
                "Possible ClawHavoc-pattern exfiltration. Disable until vetted via openclaw-skill-vetter-mcp.",
                "11 of 42 enabled skills make external HTTP calls. Run skill-vetter for full audit.",
            ],
        )

    async def get_upgrade_status(self) -> UpgradeStatus:
        return UpgradeStatus(
            current_version="2026.4.23",
            last_upgrade_at=_ago(days=2, hours=4),
            last_upgrade_from_version="2026.4.23",
            last_upgrade_to_version="2026.4.26",
            last_upgrade_outcome="rollback",
            regression_markers=["websocket_stalls", "cpu_spike"],
            available_version="2026.4.30",
            health=HealthLevel.DEGRADED,
            notes=[
                "Upgrade 2026.4.23→2026.4.26 was rolled back 2 days ago after WebSocket stalls + CPU spikes.",
                "Pinned to 2026.4.23. Check upstream changelog for 2026.4.30 regression fixes before re-attempting.",
            ],
        )

    async def get_cron_health(self) -> CronHealthSummary:
        return CronHealthSummary(
            total_jobs=6,
            overdue_jobs=1,
            failed_runs_24h=0,
            successful_runs_24h=42,
            success_rate_24h=42 / 50 if 50 else 0.0,
            health=HealthLevel.DEGRADED,
            silentwatch_available=False,
            notes=[
                "1 cron job overdue: audit-snapshot last ran 72h ago (schedule: every 15 min).",
                "Install silentwatch-mcp for silent-failure detection (output-empty-on-exit-0 cases).",
            ],
        )

    async def get_disk_usage(self) -> DiskUsage:
        return DiskUsage(
            root_used_percent=82.4,
            root_used_gb=16.5,
            root_total_gb=20.0,
            log_directory="/var/log/openclaw",
            log_directory_size_mb=2840.0,
            log_directory_growth_mb_24h=187.0,
            largest_log_files=[
                "/var/log/openclaw/gateway.log (1242.0 MB)",
                "/var/log/openclaw/skill-runs.log.1 (628.5 MB)",
                "/var/log/openclaw/cron.log (412.3 MB)",
            ],
            health=HealthLevel.DEGRADED,
            notes=[
                "Root disk at 82% — set up log rotation before crossing 90%.",
                "Log directory grew 187 MB in last 24h. gateway.log dominates (1.24 GB).",
            ],
        )
