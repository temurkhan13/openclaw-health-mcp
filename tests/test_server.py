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


# ─────── Coverage gap fillers (overnight Phase 1B) ───────


async def test_call_tool_cpu_memory_health() -> None:
    """Coverage: server.py:150-151."""
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="cpu_memory_health", arguments={}),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert isinstance(parsed, dict)


async def test_call_tool_recent_errors_default_args() -> None:
    """Coverage: server.py:153-166 — recent_errors with default args."""
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="recent_errors", arguments={}),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert isinstance(parsed, dict)


# Note: server.py:158-165 invalid-severity branch is unreachable via the MCP
# protocol — the input schema's enum validator rejects unknown severity values
# before they reach our code's fallback. Defensive code path retained for safety
# but not test-able through the public surface (same situation as output-vetter's
# defensive type-coercion of non-dict snapshots).


async def test_call_tool_skill_registry_check() -> None:
    """Coverage: server.py:168-169."""
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="skill_registry_check", arguments={}),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert isinstance(parsed, dict)


async def test_call_tool_last_upgrade_status() -> None:
    """Coverage: server.py:171-172."""
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="last_upgrade_status", arguments={}),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert isinstance(parsed, dict)


async def test_call_tool_cron_health() -> None:
    """Coverage: server.py:174-175."""
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="cron_health", arguments={}),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert isinstance(parsed, dict)


async def test_call_tool_disk_usage() -> None:
    """Coverage: server.py:177-178."""
    from mcp.types import CallToolRequest, CallToolRequestParams

    server = build_server("mock")
    handler = server.request_handlers[CallToolRequest]
    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="disk_usage", arguments={}),
        )
    )
    parsed = json.loads(result.root.content[0].text)
    assert isinstance(parsed, dict)


async def test_call_tool_unknown_returns_error() -> None:
    """Coverage: server.py:180."""
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


async def test_read_resource_overview() -> None:
    """Coverage: server.py:209-217."""
    from mcp.types import ReadResourceRequest, ReadResourceRequestParams
    from pydantic import AnyUrl

    server = build_server("mock")
    handler = server.request_handlers[ReadResourceRequest]
    result = await handler(
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=AnyUrl("health://overview")),
        )
    )
    parsed = json.loads(result.root.contents[0].text)
    assert isinstance(parsed, dict)


async def test_read_resource_gateway() -> None:
    """Coverage: server.py:219-220."""
    from mcp.types import ReadResourceRequest, ReadResourceRequestParams
    from pydantic import AnyUrl

    server = build_server("mock")
    handler = server.request_handlers[ReadResourceRequest]
    result = await handler(
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=AnyUrl("health://gateway")),
        )
    )
    parsed = json.loads(result.root.contents[0].text)
    assert isinstance(parsed, dict)


async def test_read_resource_resources_metric() -> None:
    """Coverage: server.py:222-223."""
    from mcp.types import ReadResourceRequest, ReadResourceRequestParams
    from pydantic import AnyUrl

    server = build_server("mock")
    handler = server.request_handlers[ReadResourceRequest]
    result = await handler(
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=AnyUrl("health://resources")),
        )
    )
    parsed = json.loads(result.root.contents[0].text)
    assert isinstance(parsed, dict)


async def test_read_resource_unknown_uri_returns_error() -> None:
    """Coverage: server.py:225 — unknown URI fallback."""
    from mcp.types import ReadResourceRequest, ReadResourceRequestParams
    from pydantic import AnyUrl

    server = build_server("mock")
    handler = server.request_handlers[ReadResourceRequest]
    result = await handler(
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=AnyUrl("health://does-not-exist")),
        )
    )
    parsed = json.loads(result.root.contents[0].text)
    assert "error" in parsed


@pytest.mark.parametrize(
    "prompt_name,args",
    [
        ("diagnose-degraded-health", {}),
        ("diagnose-degraded-health", {"focus_component": "gateway"}),
        ("summarize-health-trend", {}),
    ],
)
async def test_get_prompt_dispatches(prompt_name: str, args: dict) -> None:
    """Coverage: server.py:257-299 — both prompts + focus_component branch."""
    from mcp.types import GetPromptRequest, GetPromptRequestParams

    server = build_server("mock")
    handler = server.request_handlers[GetPromptRequest]
    result = await handler(
        GetPromptRequest(
            method="prompts/get",
            params=GetPromptRequestParams(name=prompt_name, arguments=args),
        )
    )
    text = result.root.messages[0].content.text
    assert len(text) > 50


async def test_get_prompt_unknown_returns_unknown() -> None:
    """Coverage: server.py:301 — unknown prompt fallback."""
    from mcp.types import GetPromptRequest, GetPromptRequestParams

    server = build_server("mock")
    handler = server.request_handlers[GetPromptRequest]
    result = await handler(
        GetPromptRequest(
            method="prompts/get",
            params=GetPromptRequestParams(name="not-a-prompt", arguments={}),
        )
    )
    text = result.root.messages[0].content.text
    assert "Unknown prompt" in text or "not-a-prompt" in text
