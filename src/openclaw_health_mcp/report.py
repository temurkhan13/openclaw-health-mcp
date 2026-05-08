"""`openclaw-health-mcp-report` console script — markdown health overview."""
from __future__ import annotations

import asyncio
import os
import sys

from openclaw_health_mcp import __version__
from openclaw_health_mcp.backends.linux_proc import LinuxProcBackend
from openclaw_health_mcp.backends.mock import MockBackend
from openclaw_health_mcp.render import render_health_overview


def _build_backend(name: str):
    if name in {"linux_proc", "linux-proc"}:
        return LinuxProcBackend()
    return MockBackend()


async def _run() -> int:
    backend_name = os.environ.get("OPENCLAW_HEALTH_BACKEND", "mock")
    backend = _build_backend(backend_name)

    md = render_health_overview(
        gateway=await backend.get_gateway_status(),
        resources=await backend.get_resource_metrics(),
        errors=await backend.get_recent_errors(),
        skills=await backend.get_skill_registry_check(),
        upgrade=await backend.get_upgrade_status(),
        cron=await backend.get_cron_health(),
        disk=await backend.get_disk_usage(),
        backend_name=backend_name,
        version=__version__,
    )
    print(md, file=sys.stdout)
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
