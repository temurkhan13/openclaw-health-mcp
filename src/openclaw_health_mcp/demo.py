"""Synthetic demo — `openclaw-health-mcp-demo` console script.

Run ``openclaw-health-mcp-demo`` after ``pip install openclaw-health-mcp`` to
see the health checks fire against the bundled mock backend in ~30 seconds.

The mock backend is hand-crafted to exhibit a representative mix of health
states an operator might encounter post-upgrade:

- Gateway: alive but DEGRADED (1 crash in last 24h, bound to 0.0.0.0)
- CPU + memory: memory at 78% (DEGRADED) — elevated on a 2GB VPS
- Recent errors: WARNING-and-above events from the last 24h
- Skills: a CRITICAL flag — `clawhub-trending-bot-v2` posting to a non-allowlist
  host (the ClawHavoc-pattern exfiltration)
- Upgrade: rollback 2 days ago (WebSocket stalls + CPU spikes), pinned older
- Cron: 1 job overdue 72h
- Disk: 82% root used, gateway.log alone is 1.2 GB

Output mirrors what the MCP server would return via the ``health_overview``
tool — but rendered as a one-page operator-readable summary instead of JSON.

This is observability-only — no I/O outside the in-memory mock, no API keys.
"""
from __future__ import annotations

import asyncio
import sys

from openclaw_health_mcp import __version__
from openclaw_health_mcp.backends.mock import MockBackend
from openclaw_health_mcp.types import HealthLevel


# ANSI color codes — only used if stderr is a TTY.
def _is_tty() -> bool:
    try:
        return sys.stderr.isatty()
    except Exception:
        return False


_USE_COLOR = _is_tty()


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s


def _bold(s: str) -> str: return _c("1", s)
def _red(s: str) -> str: return _c("31", s)
def _yellow(s: str) -> str: return _c("33", s)
def _green(s: str) -> str: return _c("32", s)
def _cyan(s: str) -> str: return _c("36", s)
def _dim(s: str) -> str: return _c("2", s)


def _health_badge(h: HealthLevel) -> str:
    if h == HealthLevel.HEALTHY:
        return _green("✓ HEALTHY")
    if h == HealthLevel.DEGRADED:
        return _yellow("⚠ DEGRADED")
    if h == HealthLevel.CRITICAL:
        return _red("✗ CRITICAL")
    return _dim(h.value.upper())


def _section(title: str) -> None:
    print(_bold(f"  {title}"), file=sys.stderr)


def _kv(label: str, value: str) -> None:
    print(f"    {_dim(label):<28s}{value}", file=sys.stderr)


def _note(s: str) -> None:
    print(_dim(f"    · {s}"), file=sys.stderr)


async def _run_demo() -> int:
    print(file=sys.stderr)
    print(_bold(f"openclaw-health-mcp v{__version__} · synthetic demo"), file=sys.stderr)
    print(_dim("    gateway/skills/logs/upgrade-status checks against the bundled mock backend"), file=sys.stderr)
    print(file=sys.stderr)

    backend = MockBackend()

    # 1. Gateway
    gw = await backend.get_gateway_status()
    _section(f"Gateway · {_health_badge(gw.health)}")
    _kv("alive:", "yes" if gw.is_alive else _red("no"))
    _kv("uptime:", f"{gw.uptime_seconds // 3600}h {(gw.uptime_seconds % 3600) // 60}m  (pid {gw.pid}, {gw.bind_address})")
    _kv("crashes (24h):", str(gw.crashes_24h))
    for note in gw.notes:
        _note(note)
    print(file=sys.stderr)

    # 2. CPU + memory
    cm = await backend.get_resource_metrics()
    _section(f"CPU + memory · {_health_badge(cm.overall_health)}")
    _kv("CPU:", f"{cm.cpu_percent}%  (load 1m={cm.load_average_1m})")
    _kv("memory:", f"{cm.memory_percent}%  ({cm.memory_used_mb:.0f} / {cm.memory_total_mb:.0f} MB)")
    if cm.swap_percent > 0:
        _kv("swap:", f"{cm.swap_percent}%  ({cm.swap_used_mb:.0f} MB)")
    for note in cm.notes:
        _note(note)
    print(file=sys.stderr)

    # 3. Recent errors
    err = await backend.get_recent_errors()
    _section(f"Recent errors  ·  last {err.window_hours}h, ≥ {err.min_severity.value}")
    _kv("total:", f"{err.total_count} entries")
    for entry in err.entries[:3]:
        _note(f"[{entry.severity.value}] {entry.timestamp.strftime('%H:%M')} {entry.source}: {entry.message}")
    if err.total_count > 3:
        _note(f"... and {err.total_count - 3} more")
    print(file=sys.stderr)

    # 4. Skills
    sk = await backend.get_skill_registry_check()
    _section(f"Skill registry · {_health_badge(sk.health)}")
    _kv("skills:", f"{sk.enabled_skills} enabled / {sk.total_skills} total")
    _kv("added (24h):", str(sk.skills_added_24h))
    _kv("with external HTTP:", str(sk.skills_with_external_http))
    if sk.skills_flagged_suspicious:
        _kv("flagged:", _red(", ".join(sk.skills_flagged_suspicious)))
    for note in sk.notes:
        _note(note)
    print(file=sys.stderr)

    # 5. Upgrade
    up = await backend.get_upgrade_status()
    _section(f"Last upgrade · {_health_badge(up.health)}")
    _kv("current:", up.current_version)
    if up.available_version:
        _kv("available:", up.available_version)
    _kv(
        "last upgrade:",
        f"{up.last_upgrade_from_version} → {up.last_upgrade_to_version} "
        f"({_red(up.last_upgrade_outcome) if up.last_upgrade_outcome == 'rollback' else up.last_upgrade_outcome})",
    )
    if up.regression_markers:
        _kv("regression markers:", ", ".join(up.regression_markers))
    for note in up.notes:
        _note(note)
    print(file=sys.stderr)

    # 6. Cron
    cr = await backend.get_cron_health()
    _section(f"Cron · {_health_badge(cr.health)}")
    _kv("jobs:", f"{cr.total_jobs} total, {cr.overdue_jobs} overdue")
    _kv("runs (24h):", f"{cr.successful_runs_24h} succeeded, {cr.failed_runs_24h} failed")
    _kv("success rate:", f"{cr.success_rate_24h:.0%}")
    for note in cr.notes:
        _note(note)
    print(file=sys.stderr)

    # 7. Disk
    di = await backend.get_disk_usage()
    _section(f"Disk · {_health_badge(di.health)}")
    _kv("root:", f"{di.root_used_percent}%  ({di.root_used_gb:.1f} / {di.root_total_gb:.1f} GB)")
    _kv("log dir:", f"{di.log_directory}  ({di.log_directory_size_mb:.0f} MB, +{di.log_directory_growth_mb_24h:.0f} MB/24h)")
    if di.largest_log_files:
        _note(f"largest: {di.largest_log_files[0]}")
    print(file=sys.stderr)

    # Verdict
    overall_levels = [gw.health, cm.overall_health, sk.health, up.health, cr.health, di.health]
    if any(h == HealthLevel.CRITICAL for h in overall_levels):
        verdict = _red("✗ CRITICAL — at least one component requires immediate attention.")
    elif any(h == HealthLevel.DEGRADED for h in overall_levels):
        verdict = _yellow("⚠ DEGRADED — multiple components are off baseline. Worth investigating.")
    else:
        verdict = _green("✓ HEALTHY — all checks within expected ranges.")
    print(_bold(f"  Verdict: {verdict}"), file=sys.stderr)
    print(file=sys.stderr)
    print(_dim("→ This is the mock backend. To run health checks on YOUR deployment:"), file=sys.stderr)
    print(_dim("  1. Configure the MCP server in Claude Code / Cursor / OpenClaw"), file=sys.stderr)
    print(_dim("  2. Set OPENCLAW_HEALTH_BACKEND=openclaw  (parse ~/.openclaw/) or =linux_proc"), file=sys.stderr)
    print(_dim("  3. Ask: 'How healthy is my OpenClaw deployment right now?'"), file=sys.stderr)
    print(file=sys.stderr)
    print(_dim("docs: https://github.com/temurkhan13/openclaw-health-mcp"), file=sys.stderr)
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run_demo()))


if __name__ == "__main__":
    main()
