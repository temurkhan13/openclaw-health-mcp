"""Server protocol-wiring tests.

Verifies:
- All 8 tools register with valid schemas
- All 3 resources register
- All 2 prompts register
- call_tool dispatches correctly to backend methods
- Bad backend names raise KeyError
"""
from __future__ import annotations

import json

import pytest

from openclaw_health_mcp.backends import available_backends, get_backend
from openclaw_health_mcp.server import build_server


def test_build_server_with_mock() -> None:
    server = build_server(backend_name="mock")
    assert server is not None
    assert server.name == "openclaw-health"


def test_build_server_invalid_backend() -> None:
    with pytest.raises(KeyError):
        build_server(backend_name="does-not-exist")


def test_available_backends_includes_mock() -> None:
    assert "mock" in available_backends()


def test_get_backend_mock_returns_instance() -> None:
    backend = get_backend("mock")
    assert backend.name == "mock"


# ─────────── tool / resource / prompt registration via direct handler call ───────────
#
# We can't easily invoke MCP server.list_tools() outside a connected client, but
# the decorators register the handlers as attributes. We verify by calling the
# underlying handler functions through the request-handling internals.


async def test_list_tools_returns_eight_tools() -> None:
    """The server should expose exactly the 8 tools we register."""
    from mcp.types import ListToolsRequest

    server = build_server("mock")
    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    tools = result.root.tools
    names = {t.name for t in tools}
    expected = {
        "health_overview",
        "gateway_status",
        "cpu_memory_health",
        "recent_errors",
        "skill_registry_check",
        "last_upgrade_status",
        "cron_health",
        "disk_usage",
    }
    assert names == expected, f"missing or extra tools. got: {names}"


async def test_list_tools_schemas_are_valid() -> None:
    """Each tool must have an inputSchema with at least 'type': 'object'."""
    from mcp.types import ListToolsRequest

    server = build_server("mock")
    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    for tool in result.root.tools:
        assert isinstance(tool.inputSchema, dict)
        assert tool.inputSchema.get("type") == "object"


async def test_call_tool_health_overview() -> None:
    """Invoke health_overview through the server handler — verify it returns valid JSON
    with the expected snapshot shape."""
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="health_overview", arguments={}),
        )
    )
    content = result.root.content
    assert len(content) == 1
    assert content[0].type == "text"
    parsed = json.loads(content[0].text)
    assert "overall_health" in parsed
    assert "component_summary" in parsed
    assert parsed["overall_health"] in {"healthy", "degraded", "critical", "unknown"}


async def test_call_tool_gateway_status() -> None:
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="gateway_status", arguments={}),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert "is_alive" in parsed
    assert isinstance(parsed["is_alive"], bool)


async def test_call_tool_recent_errors_with_severity() -> None:
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="recent_errors",
                arguments={"window_hours": 24, "min_severity": "error"},
            ),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert parsed["window_hours"] == 24
    assert parsed["min_severity"] == "error"
    # All entries must be ERROR or CRITICAL
    for entry in parsed["entries"]:
        assert entry["severity"] in {"error", "critical"}


async def test_call_tool_recent_errors_invalid_severity() -> None:
    """Invalid severity should be rejected at the MCP schema layer (enum constraint)
    before reaching our handler. Response is a validation-error text, not JSON."""
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="recent_errors",
                arguments={"min_severity": "absurd"},
            ),
        )
    )
    text = result.root.content[0].text
    # Either MCP's schema validator rejected it OR our custom handler did —
    # both are acceptable, both must mention 'absurd' so the caller knows what's wrong.
    assert "absurd" in text
    # Must also surface that this is a validation/error condition, not a successful response.
    assert any(token in text.lower() for token in ("error", "validation", "not one of"))


async def test_call_tool_unknown_tool() -> None:
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="not_a_real_tool", arguments={}),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert "error" in parsed
    assert "not_a_real_tool" in parsed["error"]


async def test_list_resources_returns_three() -> None:
    from mcp.types import ListResourcesRequest

    server = build_server("mock")
    handler = server.request_handlers[ListResourcesRequest]
    result = await handler(ListResourcesRequest(method="resources/list"))
    resources = result.root.resources
    uris = {str(r.uri) for r in resources}
    assert {"health://overview", "health://gateway", "health://resources"} <= uris


async def test_list_prompts_returns_two() -> None:
    from mcp.types import ListPromptsRequest

    server = build_server("mock")
    handler = server.request_handlers[ListPromptsRequest]
    result = await handler(ListPromptsRequest(method="prompts/list"))
    names = {p.name for p in result.root.prompts}
    assert names == {"diagnose-degraded-health", "summarize-health-trend"}
