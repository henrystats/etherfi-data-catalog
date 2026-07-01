import asyncio

from etherfi_catalog import catalog as catalog_module
from etherfi_catalog import server as mcp_server
from etherfi_catalog.catalog import plan_etherfi_query, search_datasets


ADDRESS = "0x21823686d5Aa48FE8DD5Af0def9C94f3A1003d75"
ADDRESS_LOWER = ADDRESS.lower()
EXACT_FAILED_PROMPT = (
    f"Using only the etherfi-catalog MCP, how much does this address have in ether.fi? {ADDRESS}"
)


def _fail_if_live_sql_runs(monkeypatch):
    def fail(sql):
        raise AssertionError(f"prompt regression should not execute live Dune SQL: {sql}")

    monkeypatch.setattr(catalog_module, "_execute_dune_sql", fail)


def _render(value) -> str:
    return str(value).lower()


def _dataset_names(plan: dict) -> list[str]:
    return [row["name"] for row in plan.get("recommended_datasets", [])]


def _assert_filter(plan: dict, field: str, value, operator: str = "=") -> None:
    assert {"field": field, "operator": operator, "value": value} in plan["preferred_filters"]


def _assert_not_cash_profile(plan: dict) -> None:
    rendered = _render(plan)
    assert "dune.ether_fi.result_etherfi_cash_events" not in rendered
    assert "dune.ether_fi.result_etherfi_assets_under_management" not in rendered
    assert "assets under management" not in rendered
    assert "dune.ether_fi.result_etherfi_addresses" not in rendered
    assert "cash identity" not in rendered
    assert "cash safe" not in rendered
    assert "cash-safe" not in rendered
    assert "cash profile" not in rendered
    assert "canonical address registry" not in rendered


def _assert_generic_address_protocol_holder_plan(plan: dict) -> None:
    assert _dataset_names(plan) == ["etherfi_protocol_token_holders"]
    assert plan["recommended_tool"] == "get_protocol_token_holders"
    assert plan["recommended_tool_parameters"]["address"] == ADDRESS_LOWER
    assert plan["recommended_tool_parameters"]["token_symbol"] is None
    _assert_filter(plan, "address", ADDRESS_LOWER)
    assert "address = " + ADDRESS_LOWER in plan["suggested_sql_skeleton"]
    assert "FROM dune.ether_fi.result_etherfi_protocol_token_holders" in plan["suggested_sql_skeleton"]
    assert "FROM dune.ether_fi.result_etherfi_assets_under_management" not in plan["suggested_sql_skeleton"]
    assert "token_balance" in plan["suggested_sql_skeleton"]
    assert "value_usd" not in plan["suggested_sql_skeleton"]
    assert "token_amount" not in plan["suggested_sql_skeleton"]
    rendered = _render(plan)
    assert "latest" in rendered
    assert "current" in rendered
    assert "protocol token holdings" in rendered
    _assert_not_cash_profile(plan)


def _registered_tool_descriptions() -> dict[str, str]:
    tools = asyncio.run(mcp_server.server.list_tools())
    return {tool.name: (tool.description or "").lower() for tool in tools}


def _registered_tools_by_name() -> dict:
    tools = asyncio.run(mcp_server.server.list_tools())
    return {tool.name: tool for tool in tools}


def test_protocol_holder_tool_schema_accepts_address_without_token_filter():
    tools = _registered_tools_by_name()
    holder_schema = tools["get_protocol_token_holders"].inputSchema
    properties = holder_schema["properties"]

    assert "address" in properties
    assert "token_symbol" in properties
    assert "token_address" in properties
    assert "address" not in holder_schema.get("required", [])
    assert "token_symbol" not in holder_schema.get("required", [])
    assert "token_address" not in holder_schema.get("required", [])


def test_cash_safe_check_tool_schema_exposes_public_registry_lookup_parameters():
    tools = _registered_tools_by_name()
    schema = tools["check_cash_safe_address"].inputSchema
    properties = schema["properties"]

    assert "address" in properties
    assert "blockchain" in properties
    assert "execute_live" in properties
    assert "address" in schema.get("required", [])
    assert "blockchain" not in schema.get("required", [])
    assert "execute_live" not in schema.get("required", [])


def test_generic_address_balance_routes_to_protocol_holders(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(f"How much does this address have in ether.fi? {ADDRESS}")

    _assert_generic_address_protocol_holder_plan(plan)


def test_exact_manual_generic_address_prompt_routes_to_protocol_holders(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(EXACT_FAILED_PROMPT)

    _assert_generic_address_protocol_holder_plan(plan)


def test_mcp_tool_descriptions_steer_generic_address_prompt_away_from_aum_cash():
    descriptions = _registered_tool_descriptions()

    planner_doc = descriptions["plan_etherfi_query"]
    assert "generic address balance" in planner_doc
    assert "etherfi_protocol_token_holders" in planner_doc
    assert "cash-safe validation" in planner_doc
    assert "etherfi_cash_addresses" in planner_doc

    aum_doc = descriptions["get_assets_under_management_balances"]
    assert "managed/internal/protocol-controlled" in aum_doc
    assert "do not use for generic ether.fi wallet/address balance" in aum_doc
    assert "how much does this address have" in aum_doc
    assert "etherfi_protocol_token_holders" in aum_doc

    holder_doc = descriptions["get_protocol_token_holders"]
    assert "address-only lookups" in holder_doc
    assert "user/wallet holdings" in holder_doc
    assert "invested balances" in holder_doc
    assert "how much does this address have in ether.fi" in holder_doc
    assert "default route for generic address balance questions" in holder_doc
    assert "token_symbol and token_address are optional filters" in holder_doc

    cash_safe_check_doc = descriptions["check_cash_safe_address"]
    assert "public-registry check" in cash_safe_check_doc
    assert "etherfi_cash_addresses" in cash_safe_check_doc
    assert "dune.ether_fi.result_etherfi_cash_addresses" in cash_safe_check_doc
    assert "not private/internal address registries" in cash_safe_check_doc

    for cash_tool_name in (
        "get_cash_events",
        "get_cash_holdings_timeseries",
        "get_cash_safe_profile",
        "get_cash_token_totals",
        "get_top_cash_users",
    ):
        cash_doc = descriptions[cash_tool_name]
        assert "only" in cash_doc
        assert "explicit" in cash_doc
        assert "do not use for generic ether.fi address/wallet balance prompts" in cash_doc


def test_invested_address_defaults_to_current_protocol_holders(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(f"How much has {ADDRESS} invested in ether.fi?")

    assert _dataset_names(plan) == ["etherfi_protocol_token_holders"]
    _assert_filter(plan, "address", ADDRESS_LOWER)
    assert "historical deposits" not in plan["interpreted_question"].lower()
    _assert_not_cash_profile(plan)


def test_wallet_token_holdings_route_to_protocol_holders(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(f"What ether.fi tokens does {ADDRESS} hold?")

    assert _dataset_names(plan) == ["etherfi_protocol_token_holders"]
    _assert_filter(plan, "address", ADDRESS_LOWER)
    assert "token_balance" in plan["suggested_metrics"]
    assert "token_symbol" in plan["suggested_sql_skeleton"]
    _assert_not_cash_profile(plan)


def test_cash_safe_validation_prompt_routes_to_public_registry(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(f"Is this address an ether.fi Cash safe? {ADDRESS}")

    assert _dataset_names(plan) == ["etherfi_cash_addresses"]
    assert plan["question_class"] == "single-entity lookup"
    assert plan["recommended_tool"] == "check_cash_safe_address"
    assert plan["recommended_tool_parameters"]["address"] == ADDRESS_LOWER
    _assert_filter(plan, "address", ADDRESS_LOWER)
    rendered = _render(plan)
    assert "dune.ether_fi.result_etherfi_cash_addresses" in rendered
    assert "private/internal protocol address registries" in rendered
    assert "dune.ether_fi.result_etherfi_addresses" not in rendered
    assert "FROM dune.ether_fi.result_etherfi_cash_addresses" in plan["suggested_sql_skeleton"]


def test_check_cash_safe_prompt_routes_to_public_registry_without_live_call(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(
        f"Check if {ADDRESS} is a Cash safe. Do not make live Dune calls."
    )

    assert _dataset_names(plan) == ["etherfi_cash_addresses"]
    assert plan["recommended_tool"] == "check_cash_safe_address"
    assert plan["recommended_tool_parameters"]["execute_live"] is False
    assert "address = " + ADDRESS_LOWER in plan["suggested_sql_skeleton"]


def test_generic_address_dataset_search_returns_protocol_holders_not_aum_or_cash():
    results = search_datasets(f"How much does this address have in ether.fi? {ADDRESS}")
    names = [dataset["name"] for dataset in results]

    assert "etherfi_protocol_token_holders" in names
    assert "dune.ether_fi.result_etherfi_assets_under_management" not in names
    assert "dune.ether_fi.result_etherfi_cash_events" not in names
    assert "dune.ether_fi.result_etherfi_addresses" not in names


def test_generic_address_balance_terms_search_prefers_protocol_holders_not_aum():
    results = search_datasets("address balance ether.fi wallet holdings")
    names = [dataset["name"] for dataset in results]

    assert names[0] == "etherfi_protocol_token_holders"
    assert "dune.ether_fi.result_etherfi_assets_under_management" not in names
    assert "dune.ether_fi.result_etherfi_cash_events" not in names


def test_explicit_aum_managed_address_prompt_allows_aum_route(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(
        f"What AUM balances does ether.fi have for this managed address? {ADDRESS}"
    )

    assert _dataset_names(plan) == ["dune.ether_fi.result_etherfi_assets_under_management"]
    _assert_filter(plan, "address", ADDRESS_LOWER)
    rendered = _render(plan)
    assert "managed/internal" in rendered
    assert "not generic user wallet holdings" in rendered
    assert "FROM dune.ether_fi.result_etherfi_assets_under_management" in plan["suggested_sql_skeleton"]


def test_explicit_internal_owned_address_prompt_allows_aum_route(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(
        f"Show assets under management for this ether.fi-owned address: {ADDRESS}"
    )

    assert _dataset_names(plan) == ["dune.ether_fi.result_etherfi_assets_under_management"]
    _assert_filter(plan, "address", ADDRESS_LOWER)
    assert "FROM dune.ether_fi.result_etherfi_assets_under_management" in plan["suggested_sql_skeleton"]
    assert "etherfi_protocol_token_holders" in _render(plan)


def test_deposited_into_routes_to_protocol_events_deposit(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(f"How much has {ADDRESS} deposited into ether.fi?")

    assert _dataset_names(plan) == ["dune.ether_fi.result_etherfi_protocol_events"]
    _assert_filter(plan, "event_type", "deposit")
    _assert_filter(plan, "address", ADDRESS_LOWER)
    rendered = _render(plan)
    assert "historical" in rendered
    assert "event_type = 'deposit'" in plan["suggested_sql_skeleton"]
    assert "address = " + ADDRESS_LOWER in plan["suggested_sql_skeleton"]
    assert "dune.ether_fi.result_etherfi_cash_events" not in rendered


def test_ambiguous_deposited_in_mentions_protocol_interpretations(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(f"How much does this address have deposited in ether.fi? {ADDRESS}")

    names = _dataset_names(plan)
    assert "etherfi_protocol_token_holders" in names
    assert "dune.ether_fi.result_etherfi_protocol_events" in names
    _assert_filter(plan, "address", ADDRESS_LOWER)
    _assert_filter(plan, "event_type", "deposit")
    rendered = _render(plan)
    assert "current holdings" in rendered
    assert "historical deposits" in rendered
    assert "dune.ether_fi.result_etherfi_cash_events" not in rendered
    assert "cash identity" not in rendered


def test_cash_specific_safe_prompt_does_not_use_protocol_holders(monkeypatch):
    _fail_if_live_sql_runs(monkeypatch)

    plan = plan_etherfi_query(f"How much ether.fi Cash balance does this safe have? {ADDRESS}")

    rendered = _render(plan)
    assert "cash" in rendered
    assert "etherfi_protocol_token_holders" not in rendered
