import asyncio
import importlib
from types import SimpleNamespace

from mcp.server.fastmcp import FastMCP
import pytest


EXPECTED_METADATA_AND_PLANNING_TOOLS = {
    "search_datasets",
    "get_dataset_details",
    "search_dashboards",
    "get_dashboard_details",
    "get_dataset_status",
    "list_stale_datasets",
    "get_catalog_health_summary",
    "plan_etherfi_query",
    "check_cash_safe_address",
}


def _server_module():
    return importlib.import_module("etherfi_catalog.server")


def _tool_names(server: FastMCP) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


class FakeMCPServer:
    def __init__(self):
        self.settings = SimpleNamespace(host="127.0.0.1", port=8000)
        self.runs: list[dict] = []

    def run(self, *, transport: str):
        self.runs.append({"transport": transport})


def test_run_config_defaults_to_stdio_with_local_http_defaults(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    monkeypatch.delenv("MCP_PORT", raising=False)
    server_module = _server_module()

    config = server_module.parse_server_run_config([], environ={})

    assert config.transport == "stdio"
    assert config.host == "127.0.0.1"
    assert config.port == 8001


def test_run_config_accepts_explicit_stdio(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    server_module = _server_module()

    config = server_module.parse_server_run_config(["--transport", "stdio"], environ={})

    assert config.transport == "stdio"


def test_run_config_accepts_streamable_http_cli_args(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    server_module = _server_module()

    config = server_module.parse_server_run_config(
        ["--transport", "streamable-http", "--host", "127.0.0.1", "--port", "8001"],
        environ={},
    )

    assert config.transport == "streamable-http"
    assert config.host == "127.0.0.1"
    assert config.port == 8001


def test_run_config_uses_env_with_cli_precedence():
    server_module = _server_module()

    config = server_module.parse_server_run_config(
        ["--transport", "stdio", "--host", "127.0.0.1", "--port", "8001"],
        environ={
            "MCP_TRANSPORT": "streamable-http",
            "MCP_HOST": "0.0.0.0",
            "MCP_PORT": "9999",
        },
    )

    assert config.transport == "stdio"
    assert config.host == "127.0.0.1"
    assert config.port == 8001


def test_run_config_rejects_invalid_transport():
    server_module = _server_module()

    with pytest.raises(SystemExit):
        server_module.parse_server_run_config(["--transport", "invalid"], environ={})

    with pytest.raises(ValueError, match="Unsupported MCP transport"):
        server_module.parse_server_run_config([], environ={"MCP_TRANSPORT": "invalid"})


def test_run_config_rejects_invalid_port():
    server_module = _server_module()

    with pytest.raises(ValueError, match="MCP_PORT must be an integer"):
        server_module.parse_server_run_config([], environ={"MCP_PORT": "not-a-port"})


def test_run_server_preserves_stdio_without_http_settings():
    server_module = _server_module()
    fake_server = FakeMCPServer()

    server_module.run_server(
        fake_server,
        server_module.ServerRunConfig(transport="stdio", host="127.0.0.1", port=8001),
    )

    assert fake_server.runs == [{"transport": "stdio"}]
    assert fake_server.settings.host == "127.0.0.1"
    assert fake_server.settings.port == 8000


def test_run_server_configures_streamable_http_host_and_port():
    server_module = _server_module()
    fake_server = FakeMCPServer()

    server_module.run_server(
        fake_server,
        server_module.ServerRunConfig(
            transport="streamable-http",
            host="127.0.0.1",
            port=8001,
        ),
    )

    assert fake_server.runs == [{"transport": "streamable-http"}]
    assert fake_server.settings.host == "127.0.0.1"
    assert fake_server.settings.port == 8001


def test_server_imports_and_creates_fastmcp_without_dune_key(monkeypatch):
    monkeypatch.delenv("DUNE_API_KEY", raising=False)

    server_module = importlib.reload(_server_module())

    assert isinstance(server_module.server, FastMCP)


def test_metadata_and_planning_tools_are_registered_without_dune_key(monkeypatch):
    monkeypatch.delenv("DUNE_API_KEY", raising=False)
    server_module = _server_module()

    registered_tools = _tool_names(server_module.server)

    assert EXPECTED_METADATA_AND_PLANNING_TOOLS <= registered_tools


def test_registered_metadata_tool_can_be_called_without_dune_key(monkeypatch):
    monkeypatch.delenv("DUNE_API_KEY", raising=False)
    server_module = _server_module()

    result = asyncio.run(
        server_module.server.call_tool(
            "search_datasets",
            {"query": "cash events"},
        )
    )

    rendered = str(result).lower()
    assert "cash" in rendered


def test_metadata_and_planning_wrappers_work_without_dune_key(monkeypatch):
    monkeypatch.delenv("DUNE_API_KEY", raising=False)
    server_module = _server_module()

    dataset_results = server_module.search_datasets("cash events")
    dataset_details = server_module.get_dataset_details("dune.ether_fi.result_etherfi_cash_events")
    dashboard_results = server_module.search_dashboards("cash")
    dashboard_details = server_module.get_dashboard_details("etherfi_cash")
    dataset_status = server_module.get_dataset_status("dune.ether_fi.result_etherfi_cash_events")
    stale_datasets = server_module.list_stale_datasets()
    health_summary = server_module.get_catalog_health_summary()
    plan = server_module.plan_etherfi_query("Which dataset should I use for Cash events?")

    assert dataset_results
    assert dataset_details is not None
    assert dashboard_results
    assert dashboard_details is not None
    assert dataset_status is not None
    assert isinstance(stale_datasets, list)
    assert health_summary["total_datasets"] > 0
    assert plan["tool_name"] == "plan_etherfi_query"
    assert plan["executed_live"] is False


def test_live_capable_tool_planning_mode_does_not_require_dune_key(monkeypatch):
    monkeypatch.delenv("DUNE_API_KEY", raising=False)

    def fail_if_live_sql_runs(sql):
        raise AssertionError("planning mode should not execute live Dune SQL")

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fail_if_live_sql_runs)
    server_module = _server_module()

    result = server_module.get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=False,
    )
    cash_safe_result = server_module.check_cash_safe_address(
        "0x1111111111111111111111111111111111111111",
        execute_live=False,
    )

    assert "suggested_sql" in result
    assert "rows" not in result
    assert "suggested_sql" in cash_safe_result
    assert cash_safe_result["executed_live"] is False


def test_live_capable_tool_fails_clearly_without_dune_key(monkeypatch):
    monkeypatch.delenv("DUNE_API_KEY", raising=False)
    server_module = _server_module()

    result = server_module.get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
    )

    assert result["executed_live"] is False
    assert "error" in result
    assert "DUNE_API_KEY" in result["error"]
