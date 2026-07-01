from argparse import ArgumentParser
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os

from mcp.server.fastmcp import FastMCP

from etherfi_catalog.catalog import compare_datasets as compare_catalog_datasets
from etherfi_catalog.catalog import check_cash_safe_address as check_cash_safe_address_data
from etherfi_catalog.catalog import diagnose_token_price_coverage as diagnose_token_price_coverage_data
from etherfi_catalog.catalog import find_price_tokens as find_price_tokens_data
from etherfi_catalog.catalog import get_assets_under_management_balances as get_aum_balances_plan
from etherfi_catalog.catalog import get_catalog_health_summary as get_catalog_health_summary_data
from etherfi_catalog.catalog import get_cash_events as get_cash_events_data
from etherfi_catalog.catalog import get_cash_holdings_timeseries as get_cash_holdings_timeseries_data
from etherfi_catalog.catalog import get_cash_safe_profile as get_cash_safe_profile_data
from etherfi_catalog.catalog import get_cash_token_totals as get_cash_token_totals_data
from etherfi_catalog.catalog import get_dashboard_details as get_catalog_dashboard_details
from etherfi_catalog.catalog import get_dashboard_status as get_catalog_dashboard_status
from etherfi_catalog.catalog import get_dataset_details as get_catalog_dataset_details
from etherfi_catalog.catalog import get_dataset_status as get_catalog_dataset_status
from etherfi_catalog.catalog import get_protocol_token_holders as get_protocol_token_holders_data
from etherfi_catalog.catalog import get_protocol_token_tvl as get_protocol_token_tvl_data
from etherfi_catalog.catalog import get_protocol_token_tvl_timeseries as get_protocol_token_tvl_timeseries_data
from etherfi_catalog.catalog import get_protocol_events as get_protocol_events_data
from etherfi_catalog.catalog import get_token_price as get_token_price_data
from etherfi_catalog.catalog import get_token_price_by_symbol as get_token_price_by_symbol_data
from etherfi_catalog.catalog import get_token_prices_batch as get_token_prices_batch_data
from etherfi_catalog.catalog import get_top_cash_users as get_top_cash_users_data
from etherfi_catalog.catalog import list_stale_datasets as list_catalog_stale_datasets
from etherfi_catalog.catalog import plan_etherfi_query as plan_etherfi_query_data
from etherfi_catalog.catalog import search_dashboards as search_catalog_dashboards
from etherfi_catalog.catalog import search_datasets as search_catalog_datasets


server = FastMCP("etherfi-catalog")


SUPPORTED_TRANSPORTS = ("stdio", "streamable-http")
DEFAULT_TRANSPORT = "stdio"
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8001


@dataclass(frozen=True)
class ServerRunConfig:
    transport: str = DEFAULT_TRANSPORT
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT


def parse_server_run_config(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> ServerRunConfig:
    env = environ if environ is not None else os.environ
    parser = ArgumentParser(description="Run the ether.fi catalog MCP server.")
    parser.add_argument(
        "--transport",
        choices=SUPPORTED_TRANSPORTS,
        default=None,
        help="MCP transport to run. Defaults to stdio.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host for streamable-http mode. Defaults to 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for streamable-http mode. Defaults to 8001.",
    )
    args = parser.parse_args(argv)

    transport = args.transport or env.get("MCP_TRANSPORT", DEFAULT_TRANSPORT)
    if transport not in SUPPORTED_TRANSPORTS:
        supported = ", ".join(SUPPORTED_TRANSPORTS)
        raise ValueError(f"Unsupported MCP transport: {transport}. Supported transports: {supported}.")

    host = args.host or env.get("MCP_HOST", DEFAULT_HTTP_HOST)
    port_value = args.port if args.port is not None else env.get("MCP_PORT", str(DEFAULT_HTTP_PORT))
    try:
        port = int(port_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"MCP_PORT must be an integer, got {port_value!r}.") from exc

    return ServerRunConfig(transport=transport, host=host, port=port)


def run_server(mcp_server: FastMCP, config: ServerRunConfig) -> None:
    if config.transport == "streamable-http":
        mcp_server.settings.host = config.host
        mcp_server.settings.port = config.port
    mcp_server.run(transport=config.transport)


def main(argv: Sequence[str] | None = None) -> None:
    try:
        config = parse_server_run_config(argv)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from None
    run_server(server, config)


@server.tool(name="search_datasets")
def search_datasets(query: str) -> list[dict]:
    """Search dataset metadata by simple substring matching."""
    return search_catalog_datasets(query)


@server.tool(name="search_dashboards")
def search_dashboards(query: str) -> list[dict]:
    """Search dashboard metadata by simple substring matching."""
    return search_catalog_dashboards(query)


@server.tool(name="get_dashboard_details")
def get_dashboard_details(name: str) -> dict | None:
    """Return metadata for a single dashboard by name."""
    return get_catalog_dashboard_details(name)


@server.tool(name="get_dashboard_status")
def get_dashboard_status(name: str) -> dict | None:
    """Return status information for a single dashboard by name."""
    return get_catalog_dashboard_status(name)


@server.tool(name="get_catalog_health_summary")
def get_catalog_health_summary() -> dict:
    """Return a health summary for datasets and dashboards in the catalog."""
    return get_catalog_health_summary_data()


@server.tool(name="plan_etherfi_query")
def plan_etherfi_query(question: str, execute_live: bool = False) -> dict:
    """Route natural-language ether.fi questions without live execution. Cash-safe validation routes to etherfi_cash_addresses/check_cash_safe_address; generic address balance/holdings routes to etherfi_protocol_token_holders."""
    return plan_etherfi_query_data(question=question, execute_live=execute_live)


@server.tool(name="get_assets_under_management_balances")
def get_assets_under_management_balances(
    address: str,
    as_of_date: str | None = None,
    execute_live: bool = False,
) -> dict:
    """Return AUM/product balance rows only for explicit AUM, managed/internal/protocol-controlled, treasury, address registry, or product-deployment prompts. Do not use for generic ether.fi wallet/address balance, invested-balance, token-holding, or "how much does this address have" prompts; use plan_etherfi_query or etherfi_protocol_token_holders."""
    return get_aum_balances_plan(address, as_of_date=as_of_date, execute_live=execute_live)


@server.tool(name="get_cash_events")
def get_cash_events(
    event_type: str | None = None,
    user_safe: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    mode: str = "summary",
    execute_live: bool = False,
    limit: int = 100,
) -> dict:
    """Return a planning or live response only for explicit ether.fi Cash spend, cashback, borrow, repay, or liquidation events. Do not use for generic ether.fi address/wallet balance prompts."""
    return get_cash_events_data(
        event_type=event_type,
        user_safe=user_safe,
        start_date=start_date,
        end_date=end_date,
        mode=mode,
        execute_live=execute_live,
        limit=limit,
    )


@server.tool(name="get_cash_holdings_timeseries")
def get_cash_holdings_timeseries(
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = None,
    granularity: str = "day",
    token_symbol: str | None = None,
    token_symbols: list[str] | None = None,
    token_address: str | None = None,
    blockchain: str | None = None,
    group_by: str | None = None,
    category_preset: str | None = None,
    categories: list[str] | None = None,
    execute_live: bool = False,
) -> dict:
    """Return a planning or live response only for explicit ether.fi Cash holdings time-series prompts. Do not use for generic ether.fi address/wallet balance prompts."""
    return get_cash_holdings_timeseries_data(
        start_date=start_date,
        end_date=end_date,
        period=period,
        granularity=granularity,
        token_symbol=token_symbol,
        token_symbols=token_symbols,
        token_address=token_address,
        blockchain=blockchain,
        group_by=group_by,
        category_preset=category_preset,
        categories=categories,
        execute_live=execute_live,
    )


@server.tool(name="get_cash_safe_profile")
def get_cash_safe_profile(
    address: str,
    as_of_date: str | None = None,
    recent_days: int = 30,
    validate_cash_identity: bool = False,
    execute_live: bool = False,
) -> dict:
    """Return a planning or live Cash-safe profile only when the user explicitly says Cash, safe, card, user_safe, or Cash activity. For a pure "is this a Cash safe?" check, use check_cash_safe_address. Do not use for generic ether.fi address/wallet balance prompts."""
    return get_cash_safe_profile_data(
        address=address,
        as_of_date=as_of_date,
        recent_days=recent_days,
        validate_cash_identity=validate_cash_identity,
        execute_live=execute_live,
    )


@server.tool(name="check_cash_safe_address")
def check_cash_safe_address(
    address: str,
    blockchain: str | None = None,
    execute_live: bool = False,
) -> dict:
    """Return a planning or live public-registry check for whether an address is an ether.fi Cash safe. Uses etherfi_cash_addresses / dune.ether_fi.result_etherfi_cash_addresses, not private/internal address registries."""
    return check_cash_safe_address_data(
        address=address,
        blockchain=blockchain,
        execute_live=execute_live,
    )


@server.tool(name="get_cash_token_totals")
def get_cash_token_totals(
    as_of_date: str | None = None,
    token_symbol: str | None = None,
    token_address: str | None = None,
    blockchain: str | None = None,
    execute_live: bool = False,
) -> dict:
    """Return a planning or live response only for explicit ether.fi Cash token population totals. Do not use for generic ether.fi address/wallet balance prompts."""
    return get_cash_token_totals_data(
        as_of_date=as_of_date,
        token_symbol=token_symbol,
        token_address=token_address,
        blockchain=blockchain,
        execute_live=execute_live,
    )


@server.tool(name="get_top_cash_users")
def get_top_cash_users(
    as_of_date: str | None = None,
    limit: int = 10,
    min_total_usd: float | None = None,
    token_symbol: str | None = None,
    token_address: str | None = None,
    blockchain: str | None = None,
    execute_live: bool = False,
) -> dict:
    """Return a planning or live response only for explicit ether.fi Cash user/safe holding rankings. Do not use for generic ether.fi address/wallet balance prompts."""
    return get_top_cash_users_data(
        as_of_date=as_of_date,
        limit=limit,
        min_total_usd=min_total_usd,
        token_symbol=token_symbol,
        token_address=token_address,
        blockchain=blockchain,
        execute_live=execute_live,
    )


@server.tool(name="get_protocol_token_holders")
def get_protocol_token_holders(
    address: str | None = None,
    token_symbol: str | None = None,
    token_address: str | None = None,
    as_of_date: str | None = None,
    include_defi: bool = False,
    exclude_identified_defi: bool = False,
    mode: str = "summary",
    limit: int = 100,
    execute_live: bool = False,
) -> dict:
    """Return a planning or live response for ether.fi protocol token holders. Accepts address-only lookups for user/wallet holdings, invested balances, token balances, and generic "how much does this address have in ether.fi?" prompts; token_symbol and token_address are optional filters. This is the default route for generic address balance questions; use include_defi only for explicit DeFi exposure requests."""
    return get_protocol_token_holders_data(
        address=address,
        token_symbol=token_symbol,
        token_address=token_address,
        as_of_date=as_of_date,
        include_defi=include_defi,
        exclude_identified_defi=exclude_identified_defi,
        mode=mode,
        limit=limit,
        execute_live=execute_live,
    )


@server.tool(name="get_protocol_events")
def get_protocol_events(
    project: str | None = None,
    strategy_symbol: str | None = None,
    strategy_address: str | None = None,
    event_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    mode: str = "summary",
    execute_live: bool = False,
    limit: int = 100,
) -> dict:
    """Return a planning or live response for ether.fi protocol events such as historical deposits and withdrawals."""
    return get_protocol_events_data(
        project=project,
        strategy_symbol=strategy_symbol,
        strategy_address=strategy_address,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        mode=mode,
        execute_live=execute_live,
        limit=limit,
    )


@server.tool(name="get_protocol_token_tvl")
def get_protocol_token_tvl(
    strategy_symbol: str | None = None,
    strategy_symbols: list[str] | None = None,
    strategy_address: str | None = None,
    as_of_date: str | None = None,
    mode: str = "summary",
    execute_live: bool = False,
    limit: int = 100,
) -> dict:
    """Return a planning or live response for ether.fi protocol token TVL."""
    return get_protocol_token_tvl_data(
        strategy_symbol=strategy_symbol,
        strategy_symbols=strategy_symbols,
        strategy_address=strategy_address,
        as_of_date=as_of_date,
        mode=mode,
        execute_live=execute_live,
        limit=limit,
    )


@server.tool(name="get_protocol_token_tvl_timeseries")
def get_protocol_token_tvl_timeseries(
    strategy_symbol: str | None = None,
    strategy_symbols: list[str] | None = None,
    strategy_address: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    period: str | None = None,
    granularity: str = "day",
    execute_live: bool = False,
) -> dict:
    """Return a planning or live response for ether.fi protocol token TVL timeseries, including month-end history."""
    return get_protocol_token_tvl_timeseries_data(
        strategy_symbol=strategy_symbol,
        strategy_symbols=strategy_symbols,
        strategy_address=strategy_address,
        start_date=start_date,
        end_date=end_date,
        period=period,
        granularity=granularity,
        execute_live=execute_live,
    )


@server.tool(name="get_token_price")
def get_token_price(
    token_address: str,
    blockchain: str | None = None,
    as_of_timestamp: str | None = None,
    granularity: str = "minute",
    execute_live: bool = False,
) -> dict:
    """Return a planning or live response for ether.fi enriched token price lookup."""
    return get_token_price_data(
        token_address=token_address,
        blockchain=blockchain,
        as_of_timestamp=as_of_timestamp,
        granularity=granularity,
        execute_live=execute_live,
    )


@server.tool(name="find_price_tokens")
def find_price_tokens(
    token_symbol: str | None = None,
    token_project: str | None = None,
    blockchain: str | None = None,
    limit: int = 20,
    execute_live: bool = False,
) -> dict:
    """Return a planning or live response for resolving token candidates before price lookup."""
    return find_price_tokens_data(
        token_symbol=token_symbol,
        token_project=token_project,
        blockchain=blockchain,
        limit=limit,
        execute_live=execute_live,
    )


@server.tool(name="get_token_price_by_symbol")
def get_token_price_by_symbol(
    token_symbol: str,
    blockchain: str | None = None,
    token_project: str | None = None,
    as_of_timestamp: str | None = None,
    granularity: str = "minute",
    execute_live: bool = False,
) -> dict:
    """Resolve a token symbol to a unique candidate, then return an enriched token price."""
    return get_token_price_by_symbol_data(
        token_symbol=token_symbol,
        blockchain=blockchain,
        token_project=token_project,
        as_of_timestamp=as_of_timestamp,
        granularity=granularity,
        execute_live=execute_live,
    )


@server.tool(name="get_token_prices_batch")
def get_token_prices_batch(
    token_addresses: list[str],
    blockchain: str | None = None,
    as_of_timestamp: str | None = None,
    granularity: str = "daily",
    execute_live: bool = False,
) -> dict:
    """Return a planning or live response for batch enriched token price lookup."""
    return get_token_prices_batch_data(
        token_addresses=token_addresses,
        blockchain=blockchain,
        as_of_timestamp=as_of_timestamp,
        granularity=granularity,
        execute_live=execute_live,
    )


@server.tool(name="diagnose_token_price_coverage")
def diagnose_token_price_coverage(
    token_address: str,
    blockchain: str | None = None,
    execute_live: bool = False,
) -> dict:
    """Return a planning or live diagnostic response for token price coverage."""
    return diagnose_token_price_coverage_data(
        token_address=token_address,
        blockchain=blockchain,
        execute_live=execute_live,
    )


@server.tool(name="get_dataset_details")
def get_dataset_details(name: str) -> dict | None:
    """Return metadata for a single dataset by name."""
    return get_catalog_dataset_details(name)


@server.tool(name="get_dataset_status")
def get_dataset_status(name: str) -> dict | None:
    """Return status information for a single dataset by name."""
    return get_catalog_dataset_status(name)


@server.tool(name="list_stale_datasets")
def list_stale_datasets() -> list[dict]:
    """Return datasets whose freshness evaluation is currently stale."""
    return list_catalog_stale_datasets()


@server.tool(name="compare_datasets")
def compare_datasets(name_a: str, name_b: str) -> dict:
    """Compare two datasets using the catalog metadata."""
    return compare_catalog_datasets(name_a, name_b)


if __name__ == "__main__":
    main()
