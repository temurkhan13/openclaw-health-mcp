"""CLI entry point — run via `python -m openclaw_health_mcp` or the `openclaw-health-mcp` console script."""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress

from mcp.server.stdio import stdio_server

from openclaw_health_mcp import __version__
from openclaw_health_mcp.server import build_server


def _emit_startup_banner(backend: str) -> None:
    """Print a one-line value-prove banner to stderr at startup.

    Goes to stderr (stdout is reserved for MCP JSON-RPC protocol traffic).
    Suppressible via `OPENCLAW_HEALTH_QUIET=1` for users who pipe stderr to a log file.
    """
    if os.environ.get("OPENCLAW_HEALTH_QUIET", "").strip() in {"1", "true", "yes"}:
        return
    banner = (
        f"openclaw-health-mcp v{__version__} ready · "
        f"gateway/skills/logs/upgrade-status checks · "
        f"backend={backend}"
    )
    print(banner, file=sys.stderr, flush=True)


def main() -> None:
    """Run the MCP server, OR dispatch to a subcommand.

    Subcommands:
    - ``monitor [args]`` → long-running NDJSON event stream (Aufgaard's monitor framework).
    """
    if len(sys.argv) >= 2 and sys.argv[1] == "monitor":
        from openclaw_health_mcp.monitor import main as monitor_main
        sys.exit(monitor_main())

    backend = os.environ.get("OPENCLAW_HEALTH_BACKEND", "mock")
    _emit_startup_banner(backend)

    async def _run() -> None:
        server = build_server(backend_name=backend)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    with suppress(KeyboardInterrupt):
        asyncio.run(_run())


if __name__ == "__main__":
    main()
    sys.exit(0)
