"""Shared types used across the server and backends.

Canonical response shapes for every tool. Backends produce these; the server
serializes them to MCP `TextContent` blocks.

All datetimes are timezone-aware UTC. Severity classification uses HealthLevel.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HealthLevel(StrEnum):
    """Coarse health classification, applied per-component and overall.

    HEALTHY    — all signals nominal
    DEGRADED   — non-critical anomaly (e.g., elevated CPU but not OOM-imminent)
    CRITICAL   — actionable failure (e.g., gateway crash-loop, swap >50%, disk >95%)
    UNKNOWN    — backend couldn't determine state (missing data, no permission, etc.)
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """Log-line severity tag, used by recent_errors response."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ---------- Component shapes ----------


class GatewayStatus(BaseModel):
    """Status of the OpenClaw gateway process.

    `crashes_24h` is the count of unintentional restarts in the last 24h
    (different from intentional `restarts_24h` triggered by config change /
    deploy). Backends that can't disambiguate may report both as `restarts_24h`
    and leave `crashes_24h=None`.
    """

    model_config = ConfigDict(frozen=True)

    is_alive: bool
    last_restarted_at: datetime | None = None
    uptime_seconds: int | None = None
    pid: int | None = None
    bind_address: str | None = None
    """e.g., "0.0.0.0:18789" — flagged as DEGRADED when 0.0.0.0 (publicly exposed default)."""
    restarts_24h: int = 0
    crashes_24h: int | None = None
    health: HealthLevel = HealthLevel.UNKNOWN
    notes: list[str] = Field(default_factory=list)


class ResourceMetrics(BaseModel):
    """CPU + memory + swap snapshot."""

    model_config = ConfigDict(frozen=True)

    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_used_mb: float | None = None
    memory_total_mb: float | None = None
    swap_percent: float | None = None
    swap_used_mb: float | None = None
    oom_events_24h: int = 0
    """Kernel OOM-killer invocations in the last 24h (read from journalctl/dmesg)."""
    load_average_1m: float | None = None
    load_average_5m: float | None = None
    load_average_15m: float | None = None
    cpu_health: HealthLevel = HealthLevel.UNKNOWN
    memory_health: HealthLevel = HealthLevel.UNKNOWN
    overall_health: HealthLevel = HealthLevel.UNKNOWN
    notes: list[str] = Field(default_factory=list)


class ErrorEntry(BaseModel):
    """A single error/warning log line."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    severity: Severity
    source: str
    """Log source — e.g., "gateway", "skill:web-search", "cron:audit-snapshot"."""
    message: str
    """Truncated to ~500 chars; full text via tail_logs if backend supports."""


class RecentErrorsResponse(BaseModel):
    """Response for `recent_errors`."""

    window_hours: int
    min_severity: Severity
    total_count: int
    entries: list[ErrorEntry]
    truncated: bool = False
    """True when total_count exceeds the returned `entries` length."""


class SkillRegistryCheck(BaseModel):
    """ClawHub / skill registry integrity check.

    Catches the post-ClawHavoc skill-supply-chain risks: skills suddenly added,
    skills with prompt-injection patterns, skills exfiltrating to unknown hosts.
    Light static-check only here; richer analysis is in `openclaw-skill-vetter-mcp`.
    """

    model_config = ConfigDict(frozen=True)

    total_skills: int = 0
    enabled_skills: int = 0
    skills_added_24h: int = 0
    skills_modified_24h: int = 0
    skills_with_external_http: int = 0
    """Skills that make HTTP calls to non-allowlisted hosts."""
    skills_flagged_suspicious: list[str] = Field(default_factory=list)
    """Skill names that triggered any heuristic check (basic — see skill-vetter-mcp)."""
    health: HealthLevel = HealthLevel.UNKNOWN
    notes: list[str] = Field(default_factory=list)


class UpgradeStatus(BaseModel):
    """Last OpenClaw upgrade attempt status."""

    model_config = ConfigDict(frozen=True)

    current_version: str | None = None
    last_upgrade_at: datetime | None = None
    last_upgrade_from_version: str | None = None
    last_upgrade_to_version: str | None = None
    last_upgrade_outcome: str | None = None
    """e.g., "success", "rollback", "failure", "in_progress", or None if no upgrade detected."""
    regression_markers: list[str] = Field(default_factory=list)
    """Known-regression signatures detected post-upgrade (e.g., "websocket_stalls",
    "cpu_spike", "cron_silent_fail" — heuristics from the gap-map analyses)."""
    available_version: str | None = None
    """Latest version available from upstream (None if backend can't check)."""
    health: HealthLevel = HealthLevel.UNKNOWN
    notes: list[str] = Field(default_factory=list)


class CronHealthSummary(BaseModel):
    """Basic cron-job summary. For richer detection (silent failures, output anomalies),
    install `silentwatch-mcp` alongside this server.
    """

    model_config = ConfigDict(frozen=True)

    total_jobs: int = 0
    overdue_jobs: int = 0
    failed_runs_24h: int = 0
    successful_runs_24h: int = 0
    success_rate_24h: float = 0.0
    health: HealthLevel = HealthLevel.UNKNOWN
    silentwatch_available: bool = False
    """Hint to caller: if True, suggests querying silentwatch-mcp for richer data."""
    notes: list[str] = Field(default_factory=list)


class DiskUsage(BaseModel):
    """Disk space + log-directory accounting."""

    model_config = ConfigDict(frozen=True)

    root_used_percent: float | None = None
    root_used_gb: float | None = None
    root_total_gb: float | None = None
    log_directory: str | None = None
    log_directory_size_mb: float | None = None
    log_directory_growth_mb_24h: float | None = None
    largest_log_files: list[str] = Field(default_factory=list)
    """Top-N log files by size, formatted as 'PATH (SIZE_MB)'."""
    health: HealthLevel = HealthLevel.UNKNOWN
    notes: list[str] = Field(default_factory=list)


# ---------- Aggregate ----------


class HealthSnapshot(BaseModel):
    """Full health overview — every component in one structure."""

    model_config = ConfigDict(frozen=True)

    captured_at: datetime
    overall_health: HealthLevel
    gateway: GatewayStatus
    resources: ResourceMetrics
    skill_registry: SkillRegistryCheck
    upgrade: UpgradeStatus
    cron: CronHealthSummary
    disk: DiskUsage
    component_summary: dict[str, HealthLevel]
    """Mapping component-name → HealthLevel for quick scanning."""
    critical_findings: list[str] = Field(default_factory=list)
    """Human-readable strings describing critical issues, ordered by severity."""
