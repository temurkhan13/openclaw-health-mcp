"""linux-proc backend — system metrics via psutil + log parsing for errors.

Cross-platform via psutil for cpu/memory/swap/load/disk. Linux-only for OOM-event
detection (parses `journalctl` or `dmesg`) and recent-error log parsing (parses
`/var/log/syslog` or journald). Falls back gracefully on macOS/Windows: those
methods return what they can and note the limitation.

Reports HealthLevel.UNKNOWN for OpenClaw-specific components (gateway,
skill_registry, upgrade, cron). Use the `openclaw` backend for those, or run
silentwatch-mcp alongside for richer cron data.
"""
from __future__ import annotations

import contextlib
import os
import platform
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

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

try:
    import psutil
except ImportError:  # pragma: no cover - psutil declared in deps; this is defense
    psutil = None  # type: ignore[assignment, unused-ignore]


# ──────────────────── Severity classification thresholds ────────────────────

_CPU_DEGRADED_PCT = 75.0
_CPU_CRITICAL_PCT = 95.0
_MEM_DEGRADED_PCT = 70.0
_MEM_CRITICAL_PCT = 95.0
_SWAP_DEGRADED_PCT = 20.0
_SWAP_CRITICAL_PCT = 50.0
_DISK_DEGRADED_PCT = 85.0
_DISK_CRITICAL_PCT = 95.0


def _now() -> datetime:
    return datetime.now(UTC)


def _classify_pct(value: float | None, *, degraded: float, critical: float) -> HealthLevel:
    """Single-threshold classification used for cpu/memory/swap/disk percentages."""
    if value is None:
        return HealthLevel.UNKNOWN
    if value >= critical:
        return HealthLevel.CRITICAL
    if value >= degraded:
        return HealthLevel.DEGRADED
    return HealthLevel.HEALTHY


def _max_level(*levels: HealthLevel) -> HealthLevel:
    """Reduce levels: CRITICAL > DEGRADED > HEALTHY > UNKNOWN."""
    rank = {
        HealthLevel.UNKNOWN: 0,
        HealthLevel.HEALTHY: 1,
        HealthLevel.DEGRADED: 2,
        HealthLevel.CRITICAL: 3,
    }
    return max(levels, key=lambda level: rank[level])


def _safe_run(cmd: list[str], timeout_seconds: int = 5) -> str:
    """Run `cmd` and return stdout, or empty string on any error.

    Used for journalctl/dmesg/du calls that may not exist on every host. Errors
    are swallowed by design — backends should never raise on missing tools.
    """
    if shutil.which(cmd[0]) is None:
        return ""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout or ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


# ──────────────────── OOM event detection (Linux) ────────────────────


_OOM_PATTERNS = [
    re.compile(r"Out of memory: Killed process"),
    re.compile(r"oom-kill:"),
    re.compile(r"oom_reaper"),
]


def _count_oom_events_24h() -> int:
    """Count OOM-killer invocations in last 24h via journalctl or dmesg."""
    if platform.system() != "Linux":
        return 0
    output = _safe_run(["journalctl", "--since=24 hours ago", "--no-pager", "-q"])
    if not output:
        # Fallback to dmesg (newer dmesg supports -T for timestamps; counts are approximate)
        output = _safe_run(["dmesg", "-T"])
    if not output:
        return 0
    count = 0
    for line in output.splitlines():
        if any(p.search(line) for p in _OOM_PATTERNS):
            count += 1
    return count


# ──────────────────── Severity-line parsing ────────────────────


_SEVERITY_TOKENS: dict[str, Severity] = {
    "DEBUG": Severity.DEBUG,
    "INFO": Severity.INFO,
    "WARNING": Severity.WARNING,
    "WARN": Severity.WARNING,
    "ERROR": Severity.ERROR,
    "ERR": Severity.ERROR,
    "CRITICAL": Severity.CRITICAL,
    "CRIT": Severity.CRITICAL,
    "ALERT": Severity.CRITICAL,
    "EMERG": Severity.CRITICAL,
}


def _detect_severity(line: str) -> Severity | None:
    """Best-effort severity tag detection in a syslog/journalctl line."""
    upper = line.upper()
    for token, sev in _SEVERITY_TOKENS.items():
        # Match `[ERROR]`, `<error>`, ` ERROR `, ` ERROR:` patterns
        if (
            f"[{token}]" in upper
            or f"<{token.lower()}>" in line.lower()
            or f" {token} " in upper
            or f" {token}:" in upper
            or upper.startswith(f"{token} ")
            or upper.startswith(f"{token}:")
        ):
            return sev
    return None


# ──────────────────── Disk + log directory ────────────────────


def _candidate_log_dirs() -> list[Path]:
    """Possible log directory locations to inspect (first existing wins)."""
    overrides: list[Path] = []
    env = os.environ.get("OPENCLAW_HEALTH_LOG_DIR", "")
    if env:
        overrides.append(Path(env))
    return [
        *overrides,
        Path("/var/log/openclaw"),
        Path.home() / ".openclaw" / "logs",
        Path("/var/log"),
    ]


def _dir_size_mb(path: Path) -> float:
    """Sum total bytes of regular files inside `path` (1-level deep is fine for logs)."""
    if not path.exists() or not path.is_dir():
        return 0.0
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return 0.0
    return total / (1024 * 1024)


def _largest_files(path: Path, n: int = 5) -> list[str]:
    """Top-N largest files in `path` formatted 'PATH (SIZE_MB)'."""
    if not path.exists() or not path.is_dir():
        return []
    sizes: list[tuple[Path, float]] = []
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    size_mb = entry.stat().st_size / (1024 * 1024)
                    sizes.append((entry, size_mb))
            except OSError:
                continue
    except OSError:
        return []
    sizes.sort(key=lambda x: x[1], reverse=True)
    return [f"{p} ({size_mb:.1f} MB)" for p, size_mb in sizes[:n]]


# ──────────────────── Backend ────────────────────


class LinuxProcBackend(HealthBackend):
    """psutil + journalctl + filesystem-walking backend.

    Implements: resource metrics, disk usage, recent errors. Returns UNKNOWN
    for openclaw-specific components (gateway, skill_registry, upgrade, cron).
    """

    name = "linux-proc"

    async def get_gateway_status(self) -> GatewayStatus:
        return GatewayStatus(
            is_alive=False,
            health=HealthLevel.UNKNOWN,
            notes=[
                "linux-proc backend doesn't know about the OpenClaw gateway. "
                "Use the `openclaw` backend or set OPENCLAW_HEALTH_BACKEND=openclaw.",
            ],
        )

    async def get_resource_metrics(self) -> ResourceMetrics:
        if psutil is None:  # pragma: no cover  # type: ignore[unreachable]
            return ResourceMetrics(  # type: ignore[unreachable]
                overall_health=HealthLevel.UNKNOWN,
                notes=["psutil not installed."],
            )

        try:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
        except Exception:  # noqa: BLE001 - psutil errors are platform-specific; degrade gracefully
            return ResourceMetrics(
                overall_health=HealthLevel.UNKNOWN,
                notes=["psutil call failed; backend cannot read metrics."],
            )

        load_1m = load_5m = load_15m = None
        if hasattr(psutil, "getloadavg"):
            with contextlib.suppress(OSError, AttributeError):
                load_1m, load_5m, load_15m = psutil.getloadavg()

        oom = _count_oom_events_24h()

        cpu_h = _classify_pct(cpu, degraded=_CPU_DEGRADED_PCT, critical=_CPU_CRITICAL_PCT)
        mem_h = _classify_pct(mem.percent, degraded=_MEM_DEGRADED_PCT, critical=_MEM_CRITICAL_PCT)
        swap_h = _classify_pct(swap.percent, degraded=_SWAP_DEGRADED_PCT, critical=_SWAP_CRITICAL_PCT)
        oom_h = HealthLevel.CRITICAL if oom > 0 else HealthLevel.HEALTHY
        overall = _max_level(cpu_h, mem_h, swap_h, oom_h)

        notes: list[str] = []
        if mem.percent >= _MEM_DEGRADED_PCT:
            notes.append(f"Memory at {mem.percent:.1f}% — watch for OOM under spike load.")
        if swap.percent >= _SWAP_DEGRADED_PCT:
            notes.append(f"Swap at {swap.percent:.1f}% — system may be paging heavily.")
        if oom > 0:
            notes.append(
                f"{oom} OOM kill event(s) detected in last 24h via journalctl/dmesg."
            )

        return ResourceMetrics(
            cpu_percent=cpu,
            memory_percent=mem.percent,
            memory_used_mb=mem.used / (1024 * 1024),
            memory_total_mb=mem.total / (1024 * 1024),
            swap_percent=swap.percent,
            swap_used_mb=swap.used / (1024 * 1024),
            oom_events_24h=oom,
            load_average_1m=load_1m,
            load_average_5m=load_5m,
            load_average_15m=load_15m,
            cpu_health=cpu_h,
            memory_health=mem_h,
            overall_health=overall,
            notes=notes,
        )

    async def get_recent_errors(
        self,
        window_hours: int = 24,
        min_severity: Severity = Severity.WARNING,
    ) -> RecentErrorsResponse:
        if platform.system() != "Linux":
            return RecentErrorsResponse(
                window_hours=window_hours,
                min_severity=min_severity,
                total_count=0,
                entries=[],
                truncated=False,
            )

        # journalctl with priority filter — err=3 captures err+crit+alert+emerg, warning=4 adds warn
        priority = "err" if min_severity in (Severity.ERROR, Severity.CRITICAL) else "warning"
        output = _safe_run(
            [
                "journalctl",
                f"--since={window_hours} hours ago",
                "--no-pager",
                "-q",
                "-p",
                priority,
                "-n",
                "500",
            ]
        )

        severity_order = {
            Severity.DEBUG: 0,
            Severity.INFO: 1,
            Severity.WARNING: 2,
            Severity.ERROR: 3,
            Severity.CRITICAL: 4,
        }
        min_rank = severity_order[min_severity]

        entries: list[ErrorEntry] = []
        for line in output.splitlines():
            sev = _detect_severity(line) or Severity.WARNING
            if severity_order[sev] < min_rank:
                continue
            entries.append(
                ErrorEntry(
                    timestamp=_now(),
                    severity=sev,
                    source="syslog",
                    message=line[:500],
                )
            )

        return RecentErrorsResponse(
            window_hours=window_hours,
            min_severity=min_severity,
            total_count=len(entries),
            entries=entries,
            truncated=len(entries) >= 500,
        )

    async def get_skill_registry_check(self) -> SkillRegistryCheck:
        return SkillRegistryCheck(
            health=HealthLevel.UNKNOWN,
            notes=["linux-proc backend doesn't read OpenClaw skill registry. Use `openclaw` backend."],
        )

    async def get_upgrade_status(self) -> UpgradeStatus:
        return UpgradeStatus(
            health=HealthLevel.UNKNOWN,
            notes=["linux-proc backend doesn't know OpenClaw upgrade history. Use `openclaw` backend."],
        )

    async def get_cron_health(self) -> CronHealthSummary:
        return CronHealthSummary(
            health=HealthLevel.UNKNOWN,
            silentwatch_available=False,
            notes=[
                "linux-proc backend doesn't read OpenClaw cron data. "
                "Install silentwatch-mcp for cron monitoring, or use the `openclaw` backend.",
            ],
        )

    async def get_disk_usage(self) -> DiskUsage:
        if psutil is None:  # pragma: no cover  # type: ignore[unreachable]
            return DiskUsage(health=HealthLevel.UNKNOWN, notes=["psutil not installed."])  # type: ignore[unreachable]

        # Pick the root partition usage
        try:
            usage = psutil.disk_usage("/")
            root_pct = usage.percent
            root_used_gb = usage.used / (1024 ** 3)
            root_total_gb = usage.total / (1024 ** 3)
        except (OSError, AttributeError):
            try:
                usage = psutil.disk_usage(os.environ.get("SYSTEMDRIVE", "C:") + os.sep)
                root_pct = usage.percent
                root_used_gb = usage.used / (1024 ** 3)
                root_total_gb = usage.total / (1024 ** 3)
            except (OSError, AttributeError):
                return DiskUsage(health=HealthLevel.UNKNOWN, notes=["disk_usage call failed."])

        # Find a log directory
        log_dir: Path | None = None
        for candidate in _candidate_log_dirs():
            if candidate.exists() and candidate.is_dir():
                log_dir = candidate
                break

        log_size_mb: float | None = None
        largest: list[str] = []
        if log_dir is not None:
            log_size_mb = _dir_size_mb(log_dir)
            largest = _largest_files(log_dir, n=5)

        disk_h = _classify_pct(root_pct, degraded=_DISK_DEGRADED_PCT, critical=_DISK_CRITICAL_PCT)

        notes: list[str] = []
        if root_pct >= _DISK_CRITICAL_PCT:
            notes.append(f"Root disk at {root_pct:.1f}% — write failure imminent.")
        elif root_pct >= _DISK_DEGRADED_PCT:
            notes.append(f"Root disk at {root_pct:.1f}% — set up rotation before reaching 95%.")

        return DiskUsage(
            root_used_percent=root_pct,
            root_used_gb=root_used_gb,
            root_total_gb=root_total_gb,
            log_directory=str(log_dir) if log_dir else None,
            log_directory_size_mb=log_size_mb,
            log_directory_growth_mb_24h=None,
            largest_log_files=largest,
            health=disk_h,
            notes=notes,
        )
