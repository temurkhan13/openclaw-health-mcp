"""CLI entry point — run via `python -m openclaw_health_mcp` or the `openclaw-health-mcp` console script."""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress

from mcp.server.stdio import stdio_server

from openclaw_health_mcp.server import build_server


def main() -> None:
    """Boot the MCP server over stdio transport.

    Backend is selected via the `OPENCLAW_HEALTH_BACKEND` env var (default: `mock`).
    """
    backend = os.environ.get("OPENCLAW_HEALTH_BACKEND", "mock")

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
