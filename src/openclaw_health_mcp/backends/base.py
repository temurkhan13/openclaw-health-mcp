"""Abstract base class for health backends.

Every backend implements 7 component-probe methods. Higher-level classification
(overall HealthLevel, critical_findings list, severity rules) lives in `analysis.py`
and consumes whatever a backend produces.

Backends should never raise on missing data — return UNKNOWN with notes instead.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from openclaw_health_mcp.types import (
    CronHealthSummary,
    DiskUsage,
    GatewayStatus,
    RecentErrorsResponse,
    ResourceMetrics,
    Severity,
    SkillRegistryCheck,
    UpgradeStatus,
)


class HealthBackend(ABC):
    """Contract every health backend must satisfy."""

    name: str = "base"
    """Backend identifier — also the value of OPENCLAW_HEALTH_BACKEND that selects it."""

    @abstractmethod
    async def get_gateway_status(self) -> GatewayStatus:
        """Return current gateway process status — alive/dead, uptime, recent restarts."""

    @abstractmethod
    async def get_resource_metrics(self) -> ResourceMetrics:
        """Return CPU/memory/swap/load snapshot + 24h OOM count."""

    @abstractmethod
    async def get_recent_errors(
        self,
        window_hours: int = 24,
        min_severity: Severity = Severity.WARNING,
    ) -> RecentErrorsResponse:
        """Return error/warning log entries newer than window_hours, filtered to >= min_severity."""

    @abstractmethod
    async def get_skill_registry_check(self) -> SkillRegistryCheck:
        """Return skill-registry counts + light heuristic flags.

        Deeper static analysis lives in `openclaw-skill-vetter-mcp`; this method
        should be cheap and broad.
        """

    @abstractmethod
    async def get_upgrade_status(self) -> UpgradeStatus:
        """Return last upgrade attempt outcome + regression markers."""

    @abstractmethod
    async def get_cron_health(self) -> CronHealthSummary:
        """Return basic cron summary. Backends should set silentwatch_available=True
        when an installed silentwatch-mcp could provide richer data on the same source.
        """

    @abstractmethod
    async def get_disk_usage(self) -> DiskUsage:
        """Return root-disk usage + log-directory accounting."""
