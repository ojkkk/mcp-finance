"""MCP discovery and process-level behavior regression tests."""

import asyncio
import io
import sys
from contextlib import redirect_stdout
from importlib.metadata import version

from mcp_finance import __version__
from mcp_finance.server import TOOL_HANDLERS
from mcp_finance.server import mcp as server


def test_public_tools_match_registered_handlers():
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    assert len(tools) == 31
    assert names == set(TOOL_HANDLERS)
    assert {"walk_forward", "monte_carlo_test"} <= names


def test_public_schemas_include_handler_parameters():
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    screener = tools["stock_screener"].input_schema["properties"]
    assert {"min_gross_margin", "min_net_margin", "min_revenue_growth"} <= set(screener)

    optimize = tools["optimize_strategy"].input_schema["properties"]
    assert {"optimization_method", "n_trials", "initial_capital"} <= set(optimize)

    walk_forward = tools["walk_forward"].input_schema
    monte_carlo = tools["monte_carlo_test"].input_schema
    assert walk_forward["required"] == ["code"]
    assert "train_years" in walk_forward["properties"]
    assert monte_carlo["required"] == ["code"]
    assert "n_simulations" in monte_carlo["properties"]


def test_call_tool_does_not_replace_process_stdout():
    observed = []

    def handler(value: str = "x") -> dict:
        observed.append(sys.stdout)
        print("data source diagnostic")
        return {"ok": True}

    server.add_tool(handler, name="stdout_probe")
    try:
        output = io.StringIO()
        with redirect_stdout(output):
            result = asyncio.run(server.call_tool("stdout_probe", {}))
    finally:
        server.remove_tool("stdout_probe")

    assert observed == [output]
    assert output.getvalue() == "data source diagnostic\n"
    assert '"ok": true' in result.content[0].text


def test_package_and_project_versions_match():
    assert version("mcp-markets") == __version__
