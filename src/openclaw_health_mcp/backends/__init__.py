"""Backend registry — adding a new health backend is a single-file change.

To add a backend:
  1. Subclass `HealthBackend` (see backends/base.py)
  2. Implement the 7 abstract methods (one per component)
  3. Register here by mapping `name` → constructor

Selection is via the `OPENCLAW_HEALTH_BACKEND` env var (default: `mock`).
"""
from __future__ import annotations

from openclaw_health_mcp.backends.base import HealthBackend
from openclaw_health_mcp.backends.linux_proc import LinuxProcBackend
from openclaw_health_mcp.backends.mock import MockBackend

_REGISTRY: dict[str, type[HealthBackend]] = {
    "mock": MockBackend,
    "linux-proc": LinuxProcBackend,
}


def get_backend(name: str) -> HealthBackend:
    """Construct a backend by name. Raises KeyError on unknown name."""
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise KeyError(f"Unknown backend: {name!r}. Available: {available}")
    return _REGISTRY[name]()


def available_backends() -> list[str]:
    """List backend names registered in this build."""
    return sorted(_REGISTRY.keys())


__all__ = ["HealthBackend", "LinuxProcBackend", "MockBackend", "available_backends", "get_backend"]
