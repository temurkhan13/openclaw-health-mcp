"""openclaw-health-mcp — MCP server exposing OpenClaw deployment health."""

__version__ = "0.1.0"

from openclaw_health_mcp.server import build_server

__all__ = ["__version__", "build_server"]
