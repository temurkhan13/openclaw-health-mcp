"""`python -m openclaw_health_mcp monitor` — long-running NDJSON event stream.

Used by Aufgaard's monitor framework. Polls deployment vitals on the configured
interval and emits one NDJSON line per critical-state transition (gateway-down,
memory-critical, skill-flagged, etc.).

Aufgaard's notification template references: ``component``, ``state``, ``message``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

from openclaw_health_mcp import __version__
from openclaw_health_mcp.backends.linux_proc import LinuxProcBackend
from openclaw_health_mcp.backends.mock import MockBackend
from openclaw_health_mcp.types import HealthLevel


logger = logging.getLogger(__name__)


def _build_backend(name: str):
    if name in {"linux_proc", "linux-proc"}:
        return LinuxProcBackend()
    return MockBackend()


def _parse_duration(s: str) -> float:
    s = s.strip().lower()
    if not s:
        return 60.0
    if s.endswith("ms"):
        return float(s[:-2]) / 1000.0
    if s.endswith("s"):
        return float(s[:-1])
    if s.endswith("m"):
        return float(s[:-1]) * 60.0
    if s.endswith("h"):
        return float(s[:-1]) * 3600.0
    return float(s)


def _emit(event: dict) -> None:
    print(json.dumps(event, default=str), flush=True)


def _health_severity(level: HealthLevel) -> str:
    if level == HealthLevel.CRITICAL:
        return "critical"
    if level == HealthLevel.DEGRADED:
        return "high"
    return "info"


def _summarize(notes: list[str], default: str) -> str:
    """First non-empty note, truncated; or fallback default."""
    for n in notes:
        if n:
            return n[:200]
    return default


async def _poll_once(backend, last_states: dict) -> int:
    """One poll cycle. Emits NDJSON for components that transition to DEGRADED or CRITICAL.

    Returns count of new events emitted.
    """
    components = []

    gateway = await backend.get_gateway_status()
    components.append((
        "gateway",
        gateway.health,
        _summarize(
            gateway.notes,
            f"alive={gateway.is_alive}, crashes_24h={gateway.crashes_24h}",
        ),
    ))

    cpu_mem = await backend.get_resource_metrics()
    components.append((
        "cpu_memory",
        cpu_mem.overall_health,
        _summarize(
            cpu_mem.notes,
            f"cpu={cpu_mem.cpu_percent}% memory={cpu_mem.memory_percent}%",
        ),
    ))

    skills = await backend.get_skill_registry_check()
    components.append((
        "skill_registry",
        skills.health,
        _summarize(
            skills.notes,
            f"flagged: {','.join(skills.skills_flagged_suspicious) or 'none'}",
        ),
    ))

    upgrade = await backend.get_upgrade_status()
    components.append((
        "upgrade",
        upgrade.health,
        _summarize(
            upgrade.notes,
            f"current={upgrade.current_version}, last_outcome={upgrade.last_upgrade_outcome}",
        ),
    ))

    cron = await backend.get_cron_health()
    components.append((
        "cron",
        cron.health,
        _summarize(
            cron.notes,
            f"{cron.overdue_jobs} overdue / {cron.total_jobs} total",
        ),
    ))

    disk = await backend.get_disk_usage()
    components.append((
        "disk",
        disk.health,
        _summarize(
            getattr(disk, "notes", []) or [],
            f"root {disk.root_used_percent}% used",
        ),
    ))

    new_count = 0
    for component, level, message in components:
        prev = last_states.get(component, HealthLevel.HEALTHY)
        # Emit if transitioned INTO degraded/critical (from healthy or different level)
        if level in (HealthLevel.DEGRADED, HealthLevel.CRITICAL) and level != prev:
            _emit({
                "type": "health_alert",
                "component": component,
                "state": level.value.upper(),
                "previous_state": prev.value.upper() if hasattr(prev, "value") else "HEALTHY",
                "message": message,
                "datetime": datetime.now(timezone.utc).isoformat(),
                "severity": _health_severity(level),
            })
            new_count += 1
        last_states[component] = level

    return new_count


async def _run_monitor(interval_seconds: float) -> int:
    backend_name = os.environ.get("OPENCLAW_HEALTH_BACKEND", "mock")
    backend = _build_backend(backend_name)

    if not os.environ.get("OPENCLAW_HEALTH_QUIET", "").strip() in {"1", "true", "yes"}:
        print(
            f"openclaw-health-mcp v{__version__} monitor · backend={backend_name} · poll={interval_seconds:.0f}s · stdout=ndjson",
            file=sys.stderr,
            flush=True,
        )

    last_states: dict = {}

    try:
        await _poll_once(backend, last_states)
    except Exception:
        logger.exception("initial poll failed")

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await _poll_once(backend, last_states)
        except asyncio.CancelledError:
            return 0
        except Exception:
            logger.exception("poll cycle failed; continuing")


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("OPENCLAW_HEALTH_LOG_LEVEL", "WARNING"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        prog="openclaw-health-mcp monitor",
        description="Long-running NDJSON event stream of deployment health alerts.",
    )
    parser.add_argument("--poll", default="60s", help="Poll interval (default: 60s)")
    parser.add_argument("--interval", default=None, help="Alias for --poll")
    parser.add_argument("--format", choices=["ndjson"], default="ndjson")

    args_list = sys.argv[1:]
    if args_list and args_list[0] == "monitor":
        args_list = args_list[1:]
    args = parser.parse_args(args_list)

    interval = _parse_duration(args.interval or args.poll)

    try:
        return asyncio.run(_run_monitor(interval))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
