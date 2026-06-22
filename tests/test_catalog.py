from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from etherfi_catalog.catalog import (
    compare_datasets,
    diagnose_token_price_coverage,
    evaluate_freshness,
    find_price_tokens,
    get_assets_under_management_balances,
    get_catalog_health_summary,
    get_cash_events,
    get_cash_holdings_timeseries,
    get_cash_safe_profile,
    get_cash_token_totals,
    get_dashboard_details,
    get_dashboard_status,
    get_dataset_details,
    get_dataset_status,
    get_protocol_events,
    get_protocol_token_holders,
    get_protocol_token_tvl,
    get_protocol_token_tvl_timeseries,
    get_token_price,
    get_token_price_by_symbol,
    get_token_prices_batch,
    get_top_cash_users,
    list_stale_datasets,
    load_dataset_freshness_registry,
    load_dashboard_registry,
    load_datasets,
    plan_etherfi_query,
    resolve_dataset_name,
    search_dashboards,
    search_datasets,
)


ROOT = Path(__file__).resolve().parents[1]


def _relative_yaml_files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.glob("**/*.yaml"))


def test_load_datasets_reads_existing_yaml_files():
    catalog = load_datasets()

    assert "etherfi_protocol_token_holders" in catalog
    assert "etherfi_protocol_token_holders_with_defi" in catalog
    assert "protocol_token_holders" not in catalog
    assert "protocol_token_holders_with_defi" not in catalog
    assert "dune.ether_fi.result_etherfi_addresses" in catalog
    assert catalog["etherfi_protocol_token_holders"]["display_name"] == "Protocol Token Holders"


def test_default_loaders_use_packaged_metadata_outside_repo_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ETHERFI_CATALOG_DATA_DIR", raising=False)
    monkeypatch.delenv("ETHERFI_DATASETS_DIR", raising=False)
    monkeypatch.delenv("ETHERFI_DASHBOARDS_DIR", raising=False)
    monkeypatch.delenv("ETHERFI_STATUS_DIR", raising=False)
    monkeypatch.delenv("ETHERFI_FRESHNESS_PATH", raising=False)

    catalog = load_datasets()
    registry = load_dashboard_registry()
    freshness_registry = load_dataset_freshness_registry()

    assert "dune.ether_fi.result_etherfi_cash_events" in catalog
    assert any(dashboard["name"] == "etherfi_cash" for dashboard in registry["dashboards"])
    assert freshness_registry == {}


def test_packaged_catalog_metadata_mirrors_repo_sources():
    package_data_root = ROOT / "etherfi_catalog" / "data"

    for source_name in ["datasets", "dashboards"]:
        source_root = ROOT / source_name
        package_root = package_data_root / source_name
        source_files = _relative_yaml_files(source_root)
        package_files = _relative_yaml_files(package_root)

        assert package_files == source_files
        for relative_path in source_files:
            assert (package_root / relative_path).read_text(encoding="utf-8") == (
                source_root / relative_path
            ).read_text(encoding="utf-8")

    assert (
        package_data_root / "status" / "dataset_freshness.example.yaml"
    ).read_text(encoding="utf-8") == (
        ROOT / "status" / "dataset_freshness.example.yaml"
    ).read_text(encoding="utf-8")
    assert not (package_data_root / "status" / "dataset_freshness.yaml").exists()


def test_dataset_details_resolve_legacy_names_and_table_aliases():
    catalog = load_datasets()

    direct_by_old_name = get_dataset_details("protocol_token_holders", datasets=catalog, freshness_registry={})
    direct_by_table = get_dataset_details(
        "dune.ether_fi.result_etherfi_protocol_token_holders",
        datasets=catalog,
        freshness_registry={},
    )
    with_defi_by_old_name = get_dataset_details(
        "protocol_token_holders_with_defi",
        datasets=catalog,
        freshness_registry={},
    )

    assert direct_by_old_name is not None
    assert direct_by_old_name["name"] == "etherfi_protocol_token_holders"
    assert direct_by_table is not None
    assert direct_by_table["name"] == "etherfi_protocol_token_holders"
    assert with_defi_by_old_name is not None
    assert with_defi_by_old_name["name"] == "etherfi_protocol_token_holders_with_defi"


def test_dataset_details_accept_legacy_freshness_keys_after_rename():
    details = get_dataset_details(
        "etherfi_protocol_token_holders",
        freshness_registry={
            "protocol_token_holders": {
                "last_updated": "2026-06-17T08:16:16+00:00",
                "query_id": 6213381,
            }
        },
        now=datetime(2026, 6, 17, 10, 16, 16, tzinfo=UTC),
    )

    assert details is not None
    assert details["last_updated"] == "2026-06-17T08:16:16+00:00"
    assert details["freshness"]["refresh_interval_minutes"] == 240
    assert details["freshness"]["status"] == "fresh"


def test_all_dataset_yaml_files_have_unique_names():
    catalog = load_datasets()
    names = [dataset.get("name") for dataset in catalog.values()]

    assert all(names)
    assert len(names) == len(set(names))


def test_all_datasets_have_required_metadata_fields():
    for dataset in load_datasets().values():
        assert dataset.get("name")
        assert dataset.get("display_name")
        assert dataset.get("description")


def test_all_dataset_metadata_links_and_refresh_fields_are_valid():
    catalog = load_datasets()
    dashboard_names = {
        dashboard["name"]
        for dashboard in load_dashboard_registry().get("dashboards", [])
        if dashboard.get("name")
    }
    seen_aliases: set[str] = set()

    for dataset in catalog.values():
        for alias in dataset.get("aliases", []):
            assert alias not in seen_aliases
            seen_aliases.add(alias)

        refresh_interval = dataset.get("refresh_interval_minutes")
        if refresh_interval is not None:
            assert isinstance(refresh_interval, int)
            assert refresh_interval > 0
            assert dataset.get("freshness_timestamp_column")

        source_query_id = dataset.get("source_query_id")
        if source_query_id is not None:
            source_query_url = dataset.get("source_query_url")
            assert source_query_url
            assert str(source_query_id) in source_query_url

        for dashboard_name in dataset.get("related_dashboards", []):
            assert dashboard_name in dashboard_names


def test_addresses_transfers_subtable_metadata_and_search_behavior():
    catalog = load_datasets()

    expected = {
        "addresses_transfers": {
            "table_name": "query_6901789",
            "source_query_id": 6901789,
            "is_subtable": False,
        },
        "addresses_transfers_daily": {
            "table_name": "dune.ether_fi.result_addresses_transfers",
            "source_query_id": 6119694,
            "refresh_interval_minutes": 720,
            "is_subtable": True,
        },
        "addresses_transfers_hourly": {
            "table_name": "dune.ether_fi.result_addresses_transfers_hourly",
            "source_query_id": 6901762,
            "refresh_interval_minutes": 60,
            "is_subtable": True,
        },
        "addresses_transfers_intermediate": {
            "table_name": "dune.ether_fi.result_addresses_transfers_hourly_intermediate",
            "source_query_id": 7576331,
            "refresh_interval_minutes": 240,
            "is_subtable": True,
        },
    }

    for name, fields in expected.items():
        dataset = catalog[name]
        assert dataset["table_name"] == fields["table_name"]
        assert dataset["source_query_id"] == fields["source_query_id"]
        assert dataset["freshness_timestamp_column"] == "last_updated"
        schema_by_name = {column["name"]: column for column in dataset["schema"]}
        assert schema_by_name["last_updated"]["type"] == "timestamp"
        assert schema_by_name["last_updated"]["description"] == "Freshness timestamp column for this dataset."
        assert schema_by_name["block_date"]["type"] == "timestamp"
        if "refresh_interval_minutes" in fields:
            assert dataset["refresh_interval_minutes"] == fields["refresh_interval_minutes"]
        if fields["is_subtable"]:
            assert dataset["is_subtable"] is True
            assert dataset["parent_dataset"] == "addresses_transfers"
            assert dataset["hide_from_dataset_index"] is True
            assert dataset["hide_from_dataset_search"] is True
        else:
            assert not dataset.get("is_subtable")

    main = catalog["addresses_transfers"]
    assert main["refresh_interval_minutes"] == 60
    assert main["live_query"]["query_id"] == 7576959
    assert main["live_query"]["table_name"] == "query_7576959"
    assert main["live_query"]["defaults_to_table_name"] is True
    for dataset_name in main["related_datasets"]:
        assert resolve_dataset_name(dataset_name, catalog) is not None

    addresses_list = catalog["addresses_list"]
    assert addresses_list["table_name"] == "dune.ether_fi.result_addresses_addresses_list"
    assert addresses_list["source_query_id"] == 6118315
    assert addresses_list["refresh_interval_minutes"] == 60
    assert addresses_list["freshness_timestamp_column"] == "last_updated"
    addresses_list_schema = {column["name"]: column for column in addresses_list["schema"]}
    assert set(addresses_list_schema) == {"address", "blockchain", "name", "last_updated"}
    assert addresses_list_schema["last_updated"]["description"] == "Freshness timestamp column for this dataset."
    for dataset_name in addresses_list["related_datasets"]:
        assert resolve_dataset_name(dataset_name, catalog) is not None

    cash_events = catalog["dune.ether_fi.result_etherfi_cash_events"]
    assert cash_events["live_query"]["query_id"] == cash_events["source_query_id"]
    assert cash_events["live_query"]["defaults_to_mat_view"] is True

    broad_results = {dataset["name"] for dataset in search_datasets("address transfers", datasets=catalog, freshness_registry={})}
    assert "addresses_transfers" in broad_results
    assert "addresses_transfers_daily" not in broad_results
    assert "addresses_transfers_hourly" not in broad_results
    assert "addresses_transfers_intermediate" not in broad_results

    exact_results = {
        dataset["name"]
        for dataset in search_datasets(
            "addresses_transfers_hourly",
            datasets=catalog,
            freshness_registry={},
        )
    }
    assert exact_results == {"addresses_transfers_hourly"}


def test_tokens_transfers_subtable_metadata_aliases_and_search_behavior():
    catalog = load_datasets()

    expected = {
        "tokens_transfers": {
            "table_name": "query_6901790",
            "source_query_id": 6901790,
            "refresh_interval_minutes": 60,
            "is_subtable": False,
        },
        "tokens_transfers_daily": {
            "table_name": "dune.ether_fi.result_tokens_transfers",
            "source_query_id": 6102580,
            "refresh_interval_minutes": 720,
            "is_subtable": True,
        },
        "tokens_transfers_hourly": {
            "table_name": "dune.ether_fi.result_tokens_transfers_hourly",
            "source_query_id": 6901763,
            "refresh_interval_minutes": 60,
            "is_subtable": True,
        },
        "tokens_transfers_intermediate": {
            "table_name": "dune.ether_fi.result_token_transfers_hourly_intermediate",
            "source_query_id": 7570243,
            "refresh_interval_minutes": 240,
            "is_subtable": True,
        },
        "tokens_weth_transfers": {
            "table_name": "dune.ether_fi.result_tokens_weth_tfers",
            "source_query_id": 6226918,
            "refresh_interval_minutes": 60,
            "is_subtable": True,
        },
    }

    for name, fields in expected.items():
        dataset = catalog[name]
        assert dataset["table_name"] == fields["table_name"]
        assert dataset["source_query_id"] == fields["source_query_id"]
        assert dataset["refresh_interval_minutes"] == fields["refresh_interval_minutes"]
        assert dataset["freshness_timestamp_column"] == "last_updated"
        schema_by_name = {column["name"]: column for column in dataset["schema"]}
        assert schema_by_name["block_date"]["type"] == "date"
        assert schema_by_name["last_updated"]["type"] == "timestamp"
        assert schema_by_name["last_updated"]["description"] == "Freshness timestamp column for this dataset."
        if fields["is_subtable"]:
            assert dataset["is_subtable"] is True
            assert dataset["parent_dataset"] == "tokens_transfers"
            assert dataset["hide_from_dataset_index"] is True
            assert dataset["hide_from_dataset_search"] is True
        else:
            assert not dataset.get("is_subtable")

    main = catalog["tokens_transfers"]
    assert main["live_query"]["query_id"] == 7576181
    assert main["live_query"]["table_name"] == "query_7576181"
    assert main["live_query"]["defaults_to_table_name"] is True
    for dataset_name in main["related_datasets"]:
        assert resolve_dataset_name(dataset_name, catalog) is not None

    tokens_list = catalog["tokens_list"]
    assert tokens_list["table_name"] == "dune.ether_fi.result_tokens_tokens_list"
    assert tokens_list["source_query_id"] == 6101189
    assert tokens_list["refresh_interval_minutes"] == 60
    assert tokens_list["freshness_timestamp_column"] == "last_updated"
    tokens_list_schema = {column["name"]: column for column in tokens_list["schema"]}
    assert tokens_list_schema["isrebase"]["type"] == "boolean"
    assert tokens_list_schema["last_updated"]["description"] == "Freshness timestamp column for this dataset."
    for dataset_name in tokens_list["related_datasets"]:
        assert resolve_dataset_name(dataset_name, catalog) is not None

    assert resolve_dataset_name("token_transfers", catalog) == "tokens_transfers"
    assert resolve_dataset_name("token_transfers_hourly", catalog) == "tokens_transfers_hourly"
    assert resolve_dataset_name("token_weth_tfers", catalog) == "tokens_weth_transfers"
    assert resolve_dataset_name("tokens_weth_tfers", catalog) == "tokens_weth_transfers"
    assert resolve_dataset_name("dune.ether_fi.result_tokens_transfers", catalog) == "tokens_transfers_daily"

    broad_results = {dataset["name"] for dataset in search_datasets("token transfers", datasets=catalog, freshness_registry={})}
    assert "tokens_transfers" in broad_results
    assert "tokens_transfers_daily" not in broad_results
    assert "tokens_transfers_hourly" not in broad_results
    assert "tokens_transfers_intermediate" not in broad_results
    assert "tokens_weth_transfers" not in broad_results

    assert {
        dataset["name"]
        for dataset in search_datasets(
            "tokens_transfers_hourly",
            datasets=catalog,
            freshness_registry={},
        )
    } == {"tokens_transfers_hourly"}

    assert {
        dataset["name"]
        for dataset in search_datasets(
            "token_weth_tfers",
            datasets=catalog,
            freshness_registry={},
        )
    } == {"tokens_weth_transfers"}


def test_contract_activity_metadata_and_relationships_are_documented():
    catalog = load_datasets()

    expected = {
        "contracts_logs": {
            "table_name": "dune.ether_fi.result_contracts_logs",
            "source_query_id": 6090018,
            "refresh_interval_minutes": 360,
            "schema_columns": {
                "blockchain",
                "block_date",
                "block_time",
                "block_number",
                "contract_address",
                "topic0",
                "topic1",
                "topic2",
                "topic3",
                "data",
                "tx_hash",
                "index",
                "tx_from",
                "last_updated",
            },
        },
        "contracts_traces": {
            "table_name": "dune.ether_fi.result_contracts_traces",
            "source_query_id": 6090651,
            "refresh_interval_minutes": 720,
            "schema_columns": {
                "blockchain",
                "block_date",
                "block_time",
                "block_number",
                "to",
                "trace_address",
                "output",
                "input",
                "tx_hash",
                "last_updated",
            },
        },
        "contracts_addresses_list": {
            "table_name": "dune.ether_fi.result_contracts_addresses_list",
            "source_query_id": 6089538,
            "refresh_interval_minutes": 1440,
            "schema_columns": {
                "contract_address",
                "blockchain",
                "topic0",
                "protocol",
                "last_updated",
            },
        },
    }

    for name, fields in expected.items():
        dataset = catalog[name]
        assert dataset["table_name"] == fields["table_name"]
        assert dataset["source_query_id"] == fields["source_query_id"]
        assert dataset["refresh_interval_minutes"] == fields["refresh_interval_minutes"]
        assert dataset["freshness_timestamp_column"] == "last_updated"
        schema_by_name = {column["name"]: column for column in dataset["schema"]}
        assert set(schema_by_name) == fields["schema_columns"]
        assert schema_by_name["last_updated"]["type"] == "timestamp"
        assert schema_by_name["last_updated"]["description"] == "Freshness timestamp column for this dataset."
        for dataset_name in dataset["related_datasets"]:
            assert resolve_dataset_name(dataset_name, catalog) is not None

    logs = catalog["contracts_logs"]
    assert logs["live_query"]["query_id"] == 6816322
    assert logs["live_query"]["table_name"] == "query_6816322"
    assert logs["live_query"]["defaults_to_table_name"] is True

    assert resolve_dataset_name("dune.ether_fi.result_contracts_logs", catalog) == "contracts_logs"
    assert resolve_dataset_name("dune.ether_fi.result_contracts_traces", catalog) == "contracts_traces"
    assert resolve_dataset_name("dune.ether_fi.result_contracts_addresses_list", catalog) == "contracts_addresses_list"


def test_addresses_traits_metadata_and_relationships_are_documented():
    catalog = load_datasets()
    dataset = catalog["dune.ether_fi.result_addresses_traits"]

    assert dataset["table_name"] == "dune.ether_fi.result_addresses_traits"
    assert dataset["source_query_id"] == 6127413
    assert dataset["source_query_url"] == "https://dune.com/queries/6127413"
    assert dataset["refresh_interval_minutes"] == 2880
    assert dataset["freshness_timestamp_column"] == "last_updated"
    assert dataset["grain"] == "one row per labeled address and blockchain/project context"
    assert dataset["related_dashboards"] == ["etherfi_overview"]

    schema_by_name = {column["name"]: column for column in dataset["schema"]}
    assert set(schema_by_name) == {
        "project",
        "blockchain",
        "address",
        "symbol",
        "name",
        "istoken",
        "isprotocol",
        "label",
        "primary_trait",
        "last_updated",
    }
    assert schema_by_name["name"]["description"].startswith("Human-readable name")
    assert schema_by_name["label"]["description"].startswith("Category/classification label")
    assert schema_by_name["primary_trait"]["description"].startswith("Legacy or helper trait")
    assert schema_by_name["last_updated"]["description"] == "Freshness timestamp column for this dataset."

    for dataset_name in dataset["related_datasets"]:
        assert resolve_dataset_name(dataset_name, catalog) is not None


def test_event_dataset_monitoring_metadata_is_available():
    catalog = load_datasets()

    protocol_events = catalog["dune.ether_fi.result_etherfi_protocol_events"]
    cash_events = catalog["dune.ether_fi.result_etherfi_cash_events"]

    assert protocol_events["live_query"]["query_id"] == protocol_events["source_query_id"]
    assert protocol_events["live_query"]["defaults_to_mat_view"] is True
    assert protocol_events["backups"]["weekly"]["query_id"] is None
    assert protocol_events["backups"]["monthly"]["query_id"] is None
    assert protocol_events["monitoring"]["reconciliation_dimensions"] == [
        "blockchain",
        "event_type",
        "strategy_address",
    ]
    assert protocol_events["monitoring"]["metrics"]["usd_volume"]["column"] == "amount_usd"
    assert protocol_events["monitoring"]["raw_source_sanity"]["contract_dimension"] == "strategy_address"

    assert cash_events["live_query"]["query_id"] == cash_events["source_query_id"]
    assert cash_events["live_query"]["defaults_to_mat_view"] is True
    assert cash_events["backups"]["weekly"]["query_id"] is None
    assert cash_events["backups"]["monthly"]["query_id"] is None
    assert cash_events["monitoring"]["reconciliation_dimensions"] == [
        "blockchain",
        "event_type",
        "contract_address",
    ]
    assert cash_events["monitoring"]["metrics"]["usd_volume"]["column"] == "token_amount_usd"
    assert cash_events["monitoring"]["raw_source_sanity"]["contract_dimension"] == "contract_address"


def test_evaluate_freshness_60_minute_refresh_turns_stale_after_120_minutes():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)

    fresh = evaluate_freshness(
        last_updated,
        60,
        now=last_updated + timedelta(minutes=120),
    )
    stale = evaluate_freshness(
        last_updated,
        60,
        now=last_updated + timedelta(minutes=121),
    )

    assert fresh["status"] == "fresh"
    assert not fresh["is_stale"]
    assert stale["status"] == "stale"
    assert stale["is_stale"]


def test_evaluate_freshness_720_minute_refresh_turns_stale_after_1080_minutes():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)

    fresh = evaluate_freshness(
        last_updated,
        720,
        now=last_updated + timedelta(minutes=1080),
    )
    stale = evaluate_freshness(
        last_updated,
        720,
        now=last_updated + timedelta(minutes=1081),
    )

    assert fresh["status"] == "fresh"
    assert not fresh["is_stale"]
    assert stale["status"] == "stale"
    assert stale["is_stale"]


def test_evaluate_freshness_1440_minute_refresh_turns_stale_after_2160_minutes():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)

    fresh = evaluate_freshness(
        last_updated,
        1440,
        now=last_updated + timedelta(minutes=2160),
    )
    stale = evaluate_freshness(
        last_updated,
        1440,
        now=last_updated + timedelta(minutes=2161),
    )

    assert fresh["status"] == "fresh"
    assert not fresh["is_stale"]
    assert stale["status"] == "stale"
    assert stale["is_stale"]


def test_get_dataset_details_includes_freshness_when_last_updated_is_present():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    dataset = get_dataset_details(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
                "last_updated": last_updated,
            }
        },
        now=last_updated + timedelta(minutes=121),
    )

    assert dataset is not None
    assert dataset["freshness"]["status"] == "stale"


def test_get_dataset_details_includes_warning_when_dataset_is_stale():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    dataset = get_dataset_details(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
                "last_updated": last_updated,
            }
        },
        now=last_updated + timedelta(minutes=121),
    )

    assert dataset is not None
    assert "warning" in dataset
    assert "may be outdated" in dataset["warning"]
    assert "recommended_action" in dataset


def test_get_dataset_details_omits_warning_when_dataset_is_fresh():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    dataset = get_dataset_details(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
                "last_updated": last_updated,
            }
        },
        now=last_updated + timedelta(minutes=120),
    )

    assert dataset is not None
    assert "warning" not in dataset


def test_load_dataset_freshness_registry_reads_yaml_file(tmp_path):
    registry_path = tmp_path / "dataset_freshness.yaml"
    registry_path.write_text("example:\n  last_updated: 2026-01-01T00:00:00Z\n", encoding="utf-8")

    registry = load_dataset_freshness_registry(registry_path)

    assert registry["example"]["last_updated"] == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def test_get_dataset_details_includes_freshness_from_freshness_registry():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    dataset = get_dataset_details(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"example": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=121),
    )

    assert dataset is not None
    assert dataset["freshness"]["status"] == "stale"


def test_get_dataset_details_omits_freshness_when_freshness_registry_entry_is_missing():
    dataset = get_dataset_details(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert dataset is not None
    assert "freshness" not in dataset
    assert "warning" not in dataset


def test_plan_etherfi_query_cash_events_weekly_usdc_spend():
    plan = plan_etherfi_query("I want to see the weekly volume for USDC spends on etherfi-cash.")

    assert plan["tool_name"] == "plan_etherfi_query"
    assert plan["executed_live"] is False
    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_etherfi_cash_events"
    assert {"field": "event_type", "operator": "=", "value": "spend"} in plan["preferred_filters"]
    assert {"field": "token_symbol", "operator": "=", "value": "USDC"} in plan["preferred_filters"]
    assert plan["suggested_grain"] == "week"
    assert "weekly_spend_volume_usd" in plan["suggested_metrics"]
    assert plan["suggested_visualization"]["type"] == "bar_chart"
    assert "line_chart" in plan["suggested_visualization"]["alternatives"]
    assert plan["suggested_chart_title"] == "Weekly USDC spend volume"
    assert "event_type='spend'" in plan["suggested_query_description"]
    assert "token_symbol='USDC'" in plan["suggested_query_description"]
    assert "Cash event volume and Cash balances answer different questions" in plan["suggested_query_description"]
    assert "DATE_TRUNC('week', block_date)" in plan["suggested_sql_skeleton"]
    assert "event_type = 'spend'" in plan["suggested_sql_skeleton"]
    assert "token_symbol = 'USDC'" in plan["suggested_sql_skeleton"]
    assert any("Cash event volume" in caveat for caveat in plan["important_caveats"])


def test_plan_etherfi_query_holder_ambiguity_surfaces_direct_vs_defi():
    plan = plan_etherfi_query(
        "Can you create a Dune query to show the top 100 ether.fi protocol token holders today?"
    )

    dataset_names = {dataset["name"] for dataset in plan["recommended_datasets"]}
    assert "etherfi_protocol_token_holders" in dataset_names
    assert "etherfi_protocol_token_holders_with_defi" in dataset_names
    assert any("direct holders" in reason for reason in plan["why_these_datasets"])
    assert any("DeFi exposure" in note for note in plan["ambiguity_notes"])
    assert "Should indirect DeFi exposure be included?" in plan["clarifying_questions"]
    assert "Should rows attributed to known tracked DeFi contracts be included?" in plan["clarifying_questions"]
    assert "LIMIT 100" in plan["suggested_sql_skeleton"]
    assert any("broader but incomplete" in caveat for caveat in plan["important_caveats"])
    assert any("identified_defi_contract" in caveat for caveat in plan["important_caveats"])
    assert any("tracked DeFi contract name" in caveat for caveat in plan["important_caveats"])
    assert any("identified_defi_contract IS NOT NULL" in caveat for caveat in plan["important_caveats"])
    assert plan["suggested_visualization"]["type"] == "table"
    assert "horizontal_bar_chart" in plan["suggested_visualization"]["alternatives"]
    assert "direct vs with_defi" in plan["suggested_query_description"]
    assert "identified_defi_contract" in plan["suggested_query_description"]
    plan_text = " ".join(
        str(value)
        for value in [
            plan["clarifying_questions"],
            plan["important_caveats"],
            plan["suggested_query_description"],
        ]
    )
    assert "identified_defi_contract = true" not in plan_text


def test_plan_etherfi_query_protocol_tvl_timeseries_monthly():
    plan = plan_etherfi_query("Show monthly TVL for eETH and liquidETH over the last year.")

    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"
    assert {"field": "strategy_symbol", "operator": "IN", "value": ["eETH", "liquidETH"]} in plan["preferred_filters"]
    assert {"field": "day", "operator": "range", "value": "last_1_year"} in plan["preferred_filters"]
    assert plan["suggested_grain"] == "month"
    assert "tvl_usd" in plan["suggested_metrics"]
    assert plan["suggested_visualization"]["type"] == "line_chart"
    assert "grouped_bar_chart" in plan["suggested_visualization"]["alternatives"]
    assert plan["suggested_visualization"]["x"] == "month"
    assert "Monthly protocol TVL" in plan["suggested_chart_title"]
    assert "latest available daily snapshot" in plan["suggested_query_description"]
    assert "DATE_TRUNC('month', day)" in plan["suggested_sql_skeleton"]
    assert "strategy_symbol IN ('eETH', 'liquidETH')" in plan["suggested_sql_skeleton"]
    assert "snapshot" in " ".join(plan["important_caveats"]).lower()


def test_plan_etherfi_query_cash_balance_category_dashboard_guidance():
    plan = plan_etherfi_query("Build a shareable dashboard view for monthly Cash balances by category.")

    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_etherfi_assets_under_management"
    assert {"field": "category_preset", "operator": "=", "value": "cash_balance_buckets"} in plan["preferred_filters"]
    assert plan["suggested_grain"] == "month"
    assert plan["suggested_visualization"]["type"] == "grouped_bar_chart"
    assert "stacked_bar_chart" in plan["suggested_visualization"]["alternatives"]
    assert plan["suggested_visualization"]["series"] == "category"
    assert plan["suggested_chart_title"] == "Monthly Cash balances by category"
    assert "cash_balance_buckets" in plan["suggested_query_description"]
    assert "liquidUSD, liquidETH, liquidBTC, and stables" in plan["suggested_dashboard_description"]
    assert "address_name = 'CASH'" in plan["suggested_sql_skeleton"]


def test_plan_etherfi_query_product_protocol_deployment_uses_token_project_and_net_lending():
    plan = plan_etherfi_query("How much of liquidUSD is held in Aave?")

    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_etherfi_assets_under_management"
    assert {"field": "parent_symbol", "operator": "=", "value": "liquidUSD"} in plan["preferred_filters"]
    assert {"field": "token_project", "operator": "=", "value": "Aave"} in plan["preferred_filters"]
    assert "net_token_balance_usd" in plan["suggested_metrics"]
    assert "raw_token_balance_usd" in plan["suggested_metrics"]
    assert "token_project identifies the deployed protocol" in " ".join(plan["important_caveats"])
    assert "borrow rows are stored as positive raw balances" in " ".join(plan["important_caveats"])
    assert "parent_symbol = 'liquidUSD'" in plan["suggested_sql_skeleton"]
    assert "LOWER(token_project) = LOWER('Aave')" in plan["suggested_sql_skeleton"]
    assert "LOWER(token_project) IN ('aave', 'morpho')" in plan["suggested_sql_skeleton"]
    assert "LOWER(secondary_trait) = 'borrow'" in plan["suggested_sql_skeleton"]
    assert "THEN -COALESCE(token_balance_usd, 0)" in plan["suggested_sql_skeleton"]
    assert "SUM(net_token_balance_usd) AS net_token_balance_usd" in plan["suggested_sql_skeleton"]
    assert plan["suggested_visualization"]["type"] == "table"


def test_plan_etherfi_query_product_protocol_deployment_handles_morpho_prompt():
    plan = plan_etherfi_query("How much liquidETH is deployed in Morpho?")

    assert {"field": "parent_symbol", "operator": "=", "value": "liquidETH"} in plan["preferred_filters"]
    assert {"field": "token_project", "operator": "=", "value": "Morpho"} in plan["preferred_filters"]
    assert "LOWER(token_project) = LOWER('Morpho')" in plan["suggested_sql_skeleton"]
    assert "negating borrow-side secondary_trait rows" in plan["suggested_query_description"]


def test_plan_etherfi_query_product_protocol_deployment_can_group_by_token_project():
    plan = plan_etherfi_query("Show liquidUSD deployment by token_project.")

    assert {"field": "parent_symbol", "operator": "=", "value": "liquidUSD"} in plan["preferred_filters"]
    assert not any(filter_["field"] == "token_project" for filter_ in plan["preferred_filters"])
    assert "parent_symbol = 'liquidUSD'" in plan["suggested_sql_skeleton"]
    assert "LOWER(token_project) = LOWER" not in plan["suggested_sql_skeleton"]
    assert "token_project," in plan["suggested_sql_skeleton"]
    assert "SUM(net_token_balance_usd) AS net_token_balance_usd" in plan["suggested_sql_skeleton"]


def test_plan_etherfi_query_price_defaults_to_daily_enriched_semantics():
    plan = plan_etherfi_query("Create a shareable price chart for liquidETH over the last 90 days.")

    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_tokens_prices_enriched_daily"
    assert plan["suggested_grain"] == "day"
    assert plan["suggested_visualization"]["type"] == "line_chart"
    assert "Daily enriched prices are the safer default" in plan["why_these_datasets"][0]
    assert any("Daily enriched prices are the safer default" in caveat for caveat in plan["important_caveats"])
    assert "COALESCE(token_usd, token_usd_rate)" in plan["suggested_sql_skeleton"]
    assert "Do not describe token_usd_rate as a direct raw USD price feed" in plan["suggested_query_description"]


def test_plan_etherfi_query_rejects_empty_question():
    plan = plan_etherfi_query("  ")

    assert plan["error"] == "question must be a non-empty string."
    assert plan["recommended_datasets"] == []
    assert plan["suggested_sql_skeleton"] is None


def test_plan_etherfi_query_structured_response_shape():
    plan = plan_etherfi_query("Show monthly TVL for eETH and liquidETH over the last year.")

    expected_keys = {
        "interpreted_question",
        "recommended_datasets",
        "why_these_datasets",
        "important_caveats",
        "preferred_filters",
        "suggested_grain",
        "suggested_metrics",
        "join_notes",
        "suggested_sql_skeleton",
        "suggested_visualization",
        "suggested_chart_title",
        "suggested_query_description",
        "suggested_dashboard_description",
        "suggested_next_step",
    }
    assert expected_keys.issubset(plan)
    assert "Use Dune MCP" in plan["suggested_next_step"]


def test_plan_etherfi_query_description_fields_stay_compact():
    plan = plan_etherfi_query("Create a Dune query for weekly USDC Cash spend volume.")

    assert len(plan["suggested_query_description"]) < 240
    assert len(plan["suggested_dashboard_description"]) < 180
    assert len(plan["suggested_chart_title"]) < 80


def test_plan_etherfi_query_execute_live_stays_planning_only():
    plan = plan_etherfi_query("Show monthly TVL for eETH and liquidETH over the last year.", execute_live=True)

    assert plan["execute_live"] is True
    assert plan["executed_live"] is False
    assert "planning tool" in plan["live_mode_note"]


def test_get_dataset_status_returns_status_for_existing_dataset_with_freshness():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    status = get_dataset_status(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"example": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=121),
    )

    assert status is not None
    assert status["name"] == "example"
    assert "freshness" in status
    assert "recommended_action" in status


def test_get_dataset_status_returns_basic_status_without_freshness_snapshot():
    status = get_dataset_status(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert status is not None
    assert status["name"] == "example"
    assert "freshness" not in status


def test_get_dataset_status_returns_none_for_unknown_dataset():
    assert get_dataset_status("missing", datasets={}, freshness_registry={}) is None


def test_search_datasets_includes_warning_for_matching_stale_dataset():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    results = search_datasets(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"example": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=121),
    )

    assert [dataset["name"] for dataset in results] == ["example"]
    assert "warning" in results[0]
    assert "recommended_action" in results[0]


def test_search_datasets_includes_freshness_without_warning_for_matching_fresh_dataset():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    results = search_datasets(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"example": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=120),
    )

    assert [dataset["name"] for dataset in results] == ["example"]
    assert "freshness" in results[0]
    assert "warning" not in results[0]


def test_search_datasets_returns_matching_dataset_without_freshness_snapshot():
    results = search_datasets(
        "example",
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert [dataset["name"] for dataset in results] == ["example"]
    assert "freshness" not in results[0]


def test_list_stale_datasets_returns_only_stale_datasets():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    stale_datasets = list_stale_datasets(
        datasets={
            "stale": {
                "name": "stale",
                "display_name": "Stale Dataset",
                "description": "Stale dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"stale": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=121),
    )

    assert [dataset["name"] for dataset in stale_datasets] == ["stale"]
    assert "recommended_action" in stale_datasets[0]


def test_list_stale_datasets_excludes_fresh_datasets():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    stale_datasets = list_stale_datasets(
        datasets={
            "fresh": {
                "name": "fresh",
                "display_name": "Fresh Dataset",
                "description": "Fresh dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"fresh": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=120),
    )

    assert stale_datasets == []


def test_list_stale_datasets_ignores_datasets_without_freshness_snapshot_data():
    stale_datasets = list_stale_datasets(
        datasets={
            "unknown": {
                "name": "unknown",
                "display_name": "Unknown Dataset",
                "description": "Unknown dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert stale_datasets == []


def test_tvl_dataset_is_loaded_and_searchable():
    catalog = load_datasets()
    results = search_datasets("tvl")

    assert "dune.ether_fi.result_etherfi_protocol_token_tvl" in catalog
    assert "dune.ether_fi.result_etherfi_protocol_token_tvl" in {
        dataset["name"] for dataset in results
    }


def test_assets_under_management_dataset_is_loaded_and_searchable():
    catalog = load_datasets()
    results = search_datasets("assets under management")

    assert "dune.ether_fi.result_etherfi_assets_under_management" in catalog
    assert "dune.ether_fi.result_etherfi_assets_under_management" in {
        dataset["name"] for dataset in results
    }


def test_assets_under_management_metadata_describes_deployment_footprint_not_canonical_tvl():
    dataset = load_datasets()["dune.ether_fi.result_etherfi_assets_under_management"]
    metadata_text = " ".join(
        str(value)
        for key in [
            "query_notes",
            "semantic_notes",
            "use_when",
            "do_not_use_when",
            "important_columns",
            "clarifying_questions",
            "comparison_notes",
        ]
        for value in dataset.get(key, [])
    )

    assert "parent_symbol" in metadata_text
    assert "deployment footprint" in metadata_text
    assert "address-level balances" in metadata_text
    assert "canonical product/token TVL" in metadata_text
    assert "dune.ether_fi.result_etherfi_protocol_token_tvl" in metadata_text
    assert "Cash event activity" in metadata_text
    assert "filter_balance" in metadata_text
    assert dataset["important_columns"]


def test_assets_under_management_metadata_describes_protocol_project_and_lending_netting():
    dataset = load_datasets()["dune.ether_fi.result_etherfi_assets_under_management"]
    metadata_text = " ".join(
        str(value)
        for key in [
            "query_notes",
            "semantic_notes",
            "use_when",
            "important_columns",
            "clarifying_questions",
            "example_user_intents",
        ]
        for value in dataset.get(key, [])
    )

    assert "token_project" in metadata_text
    assert "Aave" in metadata_text
    assert "Morpho" in metadata_text
    assert "secondary_trait" in metadata_text
    assert "borrow rows must be negated" in metadata_text
    assert "supply rows stay positive" in metadata_text


def test_load_dashboard_registry_reads_yaml_file(tmp_path):
    registry_path = tmp_path / "registry.yaml"
    registry_path.write_text("dashboards:\n  - name: sample_dashboard\n", encoding="utf-8")

    registry = load_dashboard_registry(registry_path)

    assert registry["dashboards"][0]["name"] == "sample_dashboard"
    assert registry["dashboards"][0]["category"] == "others"
    assert registry["dashboards"][0]["show_in_core"] is False


def test_load_dashboard_registry_reads_categorized_dashboard_files_and_dedupes_legacy(tmp_path):
    dashboards_dir = tmp_path / "dashboards"
    stake_dir = dashboards_dir / "stake"
    stake_dir.mkdir(parents=True)
    (stake_dir / "etherfi_overview.yaml").write_text(
        "name: etherfi_overview\n"
        "title: ether.fi\n"
        "url: https://dune.com/ether_fi/etherfi\n"
        "show_in_core: true\n"
        "description: Main dashboard.\n"
        "tags:\n"
        "  - overview\n"
        "datasets:\n"
        "  - dune.ether_fi.result_etherfi_protocol_token_tvl\n",
        encoding="utf-8",
    )
    (dashboards_dir / "registry.yaml").write_text(
        "dashboards:\n"
        "  - name: etherfi_overview\n"
        "    title: Duplicate legacy dashboard\n"
        "  - name: old_cash\n"
        "    title: Old Cash\n"
        "    category: cash\n"
        "    featured: true\n",
        encoding="utf-8",
    )

    registry = load_dashboard_registry(dashboards_dir)
    dashboards = {dashboard["name"]: dashboard for dashboard in registry["dashboards"]}

    assert sorted(dashboards) == ["etherfi_overview", "old_cash"]
    assert dashboards["etherfi_overview"]["title"] == "ether.fi"
    assert dashboards["etherfi_overview"]["category"] == "stake"
    assert dashboards["etherfi_overview"]["show_in_core"] is True
    assert dashboards["old_cash"]["category"] == "cash"
    assert dashboards["old_cash"]["show_in_core"] is True


def test_default_dashboard_registry_loads_etherfi_cash_from_cash_category():
    dashboards = {
        dashboard["name"]: dashboard
        for dashboard in load_dashboard_registry().get("dashboards", [])
    }

    assert "etherfi_cash" in dashboards
    assert dashboards["etherfi_cash"]["title"] == "ether.fi Cash"
    assert dashboards["etherfi_cash"]["category"] == "cash"
    assert dashboards["etherfi_cash"]["show_in_core"] is True
    assert dashboards["etherfi_cash"]["url"] == "https://dune.com/ether_fi/etherfi-cash"
    assert "cashback" in dashboards["etherfi_cash"]["tags"]
    assert "user_safe" in dashboards["etherfi_cash"]["tags"]
    assert "dune.ether_fi.result_etherfi_cash_events" in dashboards["etherfi_cash"]["datasets"]


def test_search_dashboards_includes_linked_dataset_warnings_for_stale_datasets():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    results = search_dashboards(
        "example",
        registry={
            "dashboards": [
                {
                    "name": "example_dashboard",
                    "title": "Example",
                    "datasets": ["example_dataset"],
                }
            ]
        },
        datasets={
            "example_dataset": {
                "name": "example_dataset",
                "display_name": "Example Dataset",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"example_dataset": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=121),
    )

    assert [dashboard["name"] for dashboard in results] == ["example_dashboard"]
    assert results[0]["linked_dataset_warnings"][0]["name"] == "example_dataset"
    assert "recommended_action" in results[0]["linked_dataset_warnings"][0]


def test_search_dashboards_omits_linked_dataset_warnings_for_fresh_datasets():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    results = search_dashboards(
        "example",
        registry={
            "dashboards": [
                {
                    "name": "example_dashboard",
                    "title": "Example",
                    "datasets": ["example_dataset"],
                }
            ]
        },
        datasets={
            "example_dataset": {
                "name": "example_dataset",
                "display_name": "Example Dataset",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"example_dataset": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=120),
    )

    assert [dashboard["name"] for dashboard in results] == ["example_dashboard"]
    assert "linked_dataset_warnings" not in results[0]


def test_search_dashboards_returns_normally_with_unknown_dataset_references():
    results = search_dashboards(
        "example",
        registry={
            "dashboards": [
                {
                    "name": "example_dashboard",
                    "title": "Example",
                    "datasets": ["missing_dataset"],
                }
            ]
        },
        datasets={},
        freshness_registry={},
    )

    assert [dashboard["name"] for dashboard in results] == ["example_dashboard"]


def test_search_dashboards_finds_etherfi_overview_by_name_and_dataset():
    name_results = search_dashboards("etherfi")
    dataset_results = search_dashboards("result_etherfi_protocol_token_holders")

    assert [dashboard["name"] for dashboard in name_results] == ["etherfi_overview", "etherfi_cash"]
    assert [dashboard["name"] for dashboard in dataset_results] == ["etherfi_overview"]


def test_get_dashboard_details_returns_etherfi_overview():
    dashboard = get_dashboard_details("etherfi_overview")

    assert dashboard is not None
    assert dashboard["name"] == "etherfi_overview"


def test_get_dashboard_status_returns_linked_dataset_warnings_for_stale_datasets():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    status = get_dashboard_status(
        "example_dashboard",
        registry={
            "dashboards": [
                {
                    "name": "example_dashboard",
                    "title": "Example",
                    "url": "https://example.com",
                    "datasets": ["example_dataset"],
                }
            ]
        },
        datasets={
            "example_dataset": {
                "name": "example_dataset",
                "display_name": "Example Dataset",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"example_dataset": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=121),
    )

    assert status is not None
    assert status["linked_dataset_warnings"][0]["name"] == "example_dataset"
    assert "recommended_action" in status["linked_dataset_warnings"][0]


def test_get_dashboard_status_omits_warnings_for_fresh_datasets():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    status = get_dashboard_status(
        "example_dashboard",
        registry={
            "dashboards": [
                {
                    "name": "example_dashboard",
                    "title": "Example",
                    "url": "https://example.com",
                    "datasets": ["example_dataset"],
                }
            ]
        },
        datasets={
            "example_dataset": {
                "name": "example_dataset",
                "display_name": "Example Dataset",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={"example_dataset": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=120),
    )

    assert status is not None
    assert "linked_dataset_warnings" not in status


def test_get_dashboard_status_returns_none_for_unknown_dashboard():
    assert get_dashboard_status("missing", registry={"dashboards": []}, datasets={}, freshness_registry={}) is None


def test_get_catalog_health_summary_counts_stale_datasets():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    summary = get_catalog_health_summary(
        datasets={
            "stale": {
                "name": "stale",
                "display_name": "Stale Dataset",
                "description": "Stale dataset",
                "refresh_interval_minutes": 60,
            },
            "fresh": {
                "name": "fresh",
                "display_name": "Fresh Dataset",
                "description": "Fresh dataset",
                "refresh_interval_minutes": 60,
            },
        },
        registry={"dashboards": []},
        freshness_registry={
            "stale": {"last_updated": last_updated},
            "fresh": {"last_updated": last_updated},
        },
        now=last_updated + timedelta(minutes=121),
    )

    assert summary["stale_datasets_count"] == 2
    assert summary["stale_dataset_names"] == ["stale", "fresh"]


def test_get_catalog_health_summary_counts_dashboards_with_stale_linked_datasets():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    summary = get_catalog_health_summary(
        datasets={
            "stale": {
                "name": "stale",
                "display_name": "Stale Dataset",
                "description": "Stale dataset",
                "refresh_interval_minutes": 60,
            }
        },
        registry={
            "dashboards": [
                {
                    "name": "example_dashboard",
                    "title": "Example",
                    "datasets": ["stale"],
                }
            ]
        },
        freshness_registry={"stale": {"last_updated": last_updated}},
        now=last_updated + timedelta(minutes=121),
    )

    assert summary["dashboards_with_stale_linked_datasets_count"] == 1
    assert summary["dashboards_with_stale_linked_datasets"] == ["example_dashboard"]


def test_get_catalog_health_summary_handles_empty_freshness_registry():
    summary = get_catalog_health_summary(
        datasets={
            "example": {
                "name": "example",
                "display_name": "Example Dataset",
                "description": "Example dataset",
                "refresh_interval_minutes": 60,
            }
        },
        registry={"dashboards": [{"name": "example_dashboard", "title": "Example"}]},
        freshness_registry={},
    )

    assert summary["datasets_with_freshness_snapshots"] == 0
    assert summary["stale_datasets_count"] == 0
    assert summary["dashboards_with_stale_linked_datasets_count"] == 0


def test_get_assets_under_management_balances_returns_structured_response_with_sql():
    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_etherfi_assets_under_management"
    assert "suggested_sql" in result
    assert "SELECT" in result["suggested_sql"]
    assert "address = 0x1111111111111111111111111111111111111111" in result["suggested_sql"]
    assert "address = '0x1111111111111111111111111111111111111111'" not in result["suggested_sql"]


def test_get_assets_under_management_balances_execute_live_false_preserves_planning_behavior():
    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=False,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert "suggested_sql" in result
    assert "rows" not in result
    assert result["classification_context"]["address_registry_dataset"] == "dune.ether_fi.result_etherfi_addresses"


def test_get_assets_under_management_balances_execute_live_without_api_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("DUNE_API_KEY", raising=False)

    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert "error" in result
    assert "DUNE_API_KEY" in result["error"]


def test_get_assets_under_management_balances_execute_live_returns_mocked_rows(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-01-01",
                "blockchain": "ethereum",
                "address": "0x1111111111111111111111111111111111111111",
                "address_name": "CASH",
                "token_symbol": "eETH",
                "token_underlying_symbol": "ETH",
                "token_balance": 2.0,
                "token_balance_underlying": 2.1,
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            }
        ],
    )

    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 1
    assert result["rows"][0]["token_symbol"] == "eETH"
    assert result["classification_context"]["observed_address_names"] == ["CASH"]
    assert result["summary"]["total_token_balance_usd"] == 5000.0


def test_get_assets_under_management_balances_includes_freshness_when_available():
    last_updated = datetime(2026, 1, 1, 0, 0, 0)
    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "last_updated": last_updated
            }
        },
        now=last_updated + timedelta(minutes=121),
    )

    assert result["freshness_status"]["warning"]
    assert result["freshness_status"]["recommended_action"]


def test_get_assets_under_management_balances_returns_clear_error_when_not_query_ready():
    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": False,
            }
        },
        freshness_registry={},
    )

    assert result["query_ready"] is False
    assert "error" in result


def test_get_assets_under_management_balances_live_zero_rows_returns_empty_rows(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", lambda sql: [])

    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 0
    assert result["rows"] == []
    assert result["summary"]["balances_by_token"] == []


def test_get_assets_under_management_balances_summary_groups_balances_by_token(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-01-01",
                "blockchain": "ethereum",
                "address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "eETH",
                "token_underlying_symbol": "ETH",
                "token_balance": 2.0,
                "token_balance_underlying": 2.1,
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            },
            {
                "day": "2026-01-01",
                "blockchain": "ethereum",
                "address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "eETH",
                "token_underlying_symbol": "ETH",
                "token_balance": 1.0,
                "token_balance_underlying": 1.1,
                "token_balance_usd": 2500.0,
                "token_balance_eth": 1.0,
            },
        ],
    )

    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["summary"]["balances_by_token"][0]["token_symbol"] == "eETH"
    assert result["summary"]["balances_by_token"][0]["token_balance_usd"] == 7500.0


def test_get_assets_under_management_balances_summary_groups_balances_by_blockchain(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-01-01",
                "blockchain": "ethereum",
                "address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "eETH",
                "token_underlying_symbol": "ETH",
                "token_balance": 2.0,
                "token_balance_underlying": 2.1,
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            },
            {
                "day": "2026-01-01",
                "blockchain": "base",
                "address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "weETH",
                "token_underlying_symbol": "ETH",
                "token_balance": 1.0,
                "token_balance_underlying": 1.0,
                "token_balance_usd": 2500.0,
                "token_balance_eth": 1.0,
            },
        ],
    )

    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["summary"]["balances_by_blockchain"][0]["blockchain"] == "ethereum"
    assert result["summary"]["balances_by_blockchain"][0]["token_balance_usd"] == 5000.0


def test_get_assets_under_management_balances_live_execution_failures_return_execution_error(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: (_ for _ in ()).throw(RuntimeError("Dune query execution failed: boom")),
    )

    result = get_assets_under_management_balances(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "address_column": "address",
                "date_column": "day",
                "balance_columns": ["token_balance"],
                "token_columns": ["token_symbol"],
                "query_patterns": ["latest balances by address"],
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert "execution_error" in result
    assert result["row_count"] == 0
    assert result["rows"] == []


def test_get_top_cash_users_returns_structured_planning_response():
    result = get_top_cash_users(
        as_of_date="2026-04-13",
        limit=5,
        min_total_usd=100.0,
        token_symbol="liquidUSD",
        blockchain="optimism",
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "date_column": "day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_etherfi_assets_under_management"
    assert result["as_of_date"] == "2026-04-13"
    assert result["limit"] == 5
    assert result["min_total_usd"] == 100.0
    assert result["token_symbol"] == "liquidUSD"
    assert result["blockchain"] == "optimism"
    assert result["ranking_scope"] == "filtered-token holdings"
    assert "address_name = 'CASH'" in result["suggested_sql"]
    assert "token_symbol = 'liquidUSD'" in result["suggested_sql"]
    assert "blockchain = 'optimism'" in result["suggested_sql"]
    assert "HAVING SUM(token_balance_usd) >= 100.0" in result["suggested_sql"]
    assert "LIMIT 5" in result["suggested_sql"]
    assert "rerank the Cash population itself" in result["tool_gap_note"]
    assert "rows" not in result
    assert result["summary"]["user_count_returned"] == 0


def test_get_top_cash_users_defaults_to_latest_cash_day():
    result = get_top_cash_users(
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "date_column": "day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert (
        "day = (SELECT MAX(day) FROM dune.ether_fi.result_etherfi_assets_under_management\n"
        "WHERE address_name = 'CASH'\n)"
    ) in result["suggested_sql"]
    assert result["latest_day_logic"]


def test_get_top_cash_users_validates_inputs():
    dataset = {
        "dune.ether_fi.result_etherfi_assets_under_management": {
            "name": "dune.ether_fi.result_etherfi_assets_under_management",
            "display_name": "Ether.fi Assets Under Management",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
            "query_ready": True,
        }
    }

    bad_limit = get_top_cash_users(limit=0, datasets=dataset, freshness_registry={})
    bad_minimum = get_top_cash_users(min_total_usd=-1, datasets=dataset, freshness_registry={})
    bad_date = get_top_cash_users(as_of_date="04-13-2026", datasets=dataset, freshness_registry={})
    bad_both_tokens = get_top_cash_users(
        token_symbol="liquidUSD",
        token_address="0x1111111111111111111111111111111111111111",
        datasets=dataset,
        freshness_registry={},
    )
    bad_token_symbol = get_top_cash_users(token_symbol="liquid-usd", datasets=dataset, freshness_registry={})
    bad_token_address = get_top_cash_users(token_address="not-an-address", datasets=dataset, freshness_registry={})
    bad_blockchain = get_top_cash_users(blockchain="optimism-mainnet", datasets=dataset, freshness_registry={})

    assert "limit must be a positive integer" in bad_limit["error"]
    assert "min_total_usd must be a non-negative number" in bad_minimum["error"]
    assert "as_of_date must be a YYYY-MM-DD string" in bad_date["error"]
    assert "Provide only one of token_symbol or token_address." in bad_both_tokens["error"]
    assert "token_symbol must contain only letters, numbers, and underscores." in bad_token_symbol["error"]
    assert "Address must be a 42-character 0x-prefixed hex string." in bad_token_address["error"]
    assert "blockchain must contain only letters, numbers, and underscores." in bad_blockchain["error"]


def test_get_top_cash_users_execute_live_groups_tokens_and_chains(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "address_name = 'CASH'" in sql
        assert "token_symbol = 'liquidUSD'" in sql
        assert "blockchain = 'optimism'" in sql
        return [
            {
                "rank": 1,
                "day": "2026-04-13",
                "address": "0x1111111111111111111111111111111111111111",
                "total_token_balance_usd": 7500.0,
                "total_token_balance_eth": 3.0,
                "blockchain": "ethereum",
                "token_address": "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                "token_symbol": "weETH",
                "token_type": "peg-to-underlying",
                "token_project": "ether.fi",
                "token_balance": 2.0,
                "token_balance_underlying": 2.1,
                "token_underlying_symbol": "WETH",
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            },
            {
                "rank": 1,
                "day": "2026-04-13",
                "address": "0x1111111111111111111111111111111111111111",
                "total_token_balance_usd": 7500.0,
                "total_token_balance_eth": 3.0,
                "blockchain": "base",
                "token_address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "token_symbol": "USDC",
                "token_type": "stablecoin",
                "token_project": "circle",
                "token_balance": 2500.0,
                "token_balance_underlying": 2500.0,
                "token_underlying_symbol": "USDC",
                "token_balance_usd": 2500.0,
                "token_balance_eth": 1.0,
            },
            {
                "rank": 2,
                "day": "2026-04-13",
                "address": "0x2222222222222222222222222222222222222222",
                "total_token_balance_usd": 1000.0,
                "total_token_balance_eth": 0.4,
                "blockchain": "ethereum",
                "token_address": "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                "token_symbol": "weETH",
                "token_type": "peg-to-underlying",
                "token_project": "ether.fi",
                "token_balance": 0.4,
                "token_balance_underlying": 0.42,
                "token_underlying_symbol": "WETH",
                "token_balance_usd": 1000.0,
                "token_balance_eth": 0.4,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_top_cash_users(
        token_symbol="liquidUSD",
        blockchain="optimism",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "date_column": "day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 2
    assert result["raw_row_count"] == 3
    assert result["summary"]["latest_day"] == "2026-04-13"
    assert result["summary"]["user_count_returned"] == 2
    assert result["summary"]["total_usd_of_returned_users"] == 8500.0
    assert result["summary"]["total_eth_of_returned_users"] == 3.4
    assert result["rows"][0]["rank"] == 1
    assert result["rows"][0]["token_breakdown"][0]["token_symbol"] == "weETH"
    assert result["rows"][0]["chain_breakdown"][0]["blockchain"] == "ethereum"


def test_get_top_cash_users_token_symbol_filter_reranks_cash_population(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    captured_sql = {}

    def fake_execute(sql):
        captured_sql["sql"] = sql
        return [
            {
                "rank": 1,
                "day": "2026-04-13",
                "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "total_token_balance_usd": 900.0,
                "total_token_balance_eth": 0.3,
                "blockchain": "optimism",
                "token_address": "0x9999999999999999999999999999999999999999",
                "token_symbol": "liquidUSD",
                "token_type": "one-to-one",
                "token_project": "ether.fi",
                "token_balance": 900.0,
                "token_balance_underlying": 900.0,
                "token_underlying_symbol": "USDT",
                "token_balance_usd": 900.0,
                "token_balance_eth": 0.3,
            },
            {
                "rank": 2,
                "day": "2026-04-13",
                "address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "total_token_balance_usd": 600.0,
                "total_token_balance_eth": 0.2,
                "blockchain": "optimism",
                "token_address": "0x9999999999999999999999999999999999999999",
                "token_symbol": "liquidUSD",
                "token_type": "one-to-one",
                "token_project": "ether.fi",
                "token_balance": 600.0,
                "token_balance_underlying": 600.0,
                "token_underlying_symbol": "USDT",
                "token_balance_usd": 600.0,
                "token_balance_eth": 0.2,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_top_cash_users(
        token_symbol="liquidUSD",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "date_column": "day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert "token_symbol = 'liquidUSD'" in captured_sql["sql"]
    assert "FROM cash_balances" in captured_sql["sql"]
    assert result["ranking_scope"] == "filtered-token holdings"
    assert [row["address"] for row in result["rows"]] == [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    ]
    assert result["rows"][0]["total_token_balance_usd"] == 900.0
    assert result["rows"][1]["total_token_balance_usd"] == 600.0
    assert result["rows"][0]["token_breakdown"][0]["token_symbol"] == "liquidUSD"


def test_get_top_cash_users_token_address_filter_reranks_cash_population(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    token_address = "0x1234567890abcdef1234567890abcdef12345678"
    captured_sql = {}

    def fake_execute(sql):
        captured_sql["sql"] = sql
        return [
            {
                "rank": 1,
                "day": "2026-04-13",
                "address": "0xcccccccccccccccccccccccccccccccccccccccc",
                "total_token_balance_usd": 1200.0,
                "total_token_balance_eth": 0.4,
                "blockchain": "optimism",
                "token_address": token_address,
                "token_symbol": "liquidUSD",
                "token_type": "one-to-one",
                "token_project": "ether.fi",
                "token_balance": 1200.0,
                "token_balance_underlying": 1200.0,
                "token_underlying_symbol": "USDT",
                "token_balance_usd": 1200.0,
                "token_balance_eth": 0.4,
            }
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_top_cash_users(
        token_address=token_address,
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "date_column": "day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert f"token_address = {token_address}" in captured_sql["sql"]
    assert result["token_address"] == token_address
    assert result["rows"][0]["address"] == "0xcccccccccccccccccccccccccccccccccccccccc"
    assert result["rows"][0]["total_token_balance_usd"] == 1200.0


def test_get_top_cash_users_blockchain_and_token_symbol_filters_apply_before_ranking(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    captured_sql = {}

    def fake_execute(sql):
        captured_sql["sql"] = sql
        return [
            {
                "rank": 1,
                "day": "2026-04-13",
                "address": "0xdddddddddddddddddddddddddddddddddddddddd",
                "total_token_balance_usd": 700.0,
                "total_token_balance_eth": 0.25,
                "blockchain": "optimism",
                "token_address": "0x9999999999999999999999999999999999999999",
                "token_symbol": "liquidUSD",
                "token_type": "one-to-one",
                "token_project": "ether.fi",
                "token_balance": 700.0,
                "token_balance_underlying": 700.0,
                "token_underlying_symbol": "USDT",
                "token_balance_usd": 700.0,
                "token_balance_eth": 0.25,
            }
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_top_cash_users(
        token_symbol="liquidUSD",
        blockchain="optimism",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "date_column": "day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert "token_symbol = 'liquidUSD'" in captured_sql["sql"]
    assert "blockchain = 'optimism'" in captured_sql["sql"]
    assert "WHERE address_name = 'CASH'" in captured_sql["sql"]
    assert result["blockchain"] == "optimism"
    assert result["rows"][0]["chain_breakdown"][0]["blockchain"] == "optimism"


def test_get_top_cash_users_live_execution_failures_return_execution_error(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: (_ for _ in ()).throw(RuntimeError("Dune query execution failed: boom")),
    )

    result = get_top_cash_users(
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "date_column": "day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert "execution_error" in result
    assert result["row_count"] == 0
    assert result["rows"] == []


def _cash_aum_dataset():
    return {
        "dune.ether_fi.result_etherfi_assets_under_management": {
            "name": "dune.ether_fi.result_etherfi_assets_under_management",
            "display_name": "Ether.fi Assets Under Management",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
            "query_ready": True,
            "grain": "one row per day, address, and token",
            "date_column": "day",
            "refresh_interval_minutes": 60,
        }
    }


def test_get_cash_token_totals_returns_unfiltered_planning_response():
    result = get_cash_token_totals(
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_etherfi_assets_under_management"
    assert result["aggregate_scope"] == "all Cash balances"
    assert "address_name = 'CASH'" in result["suggested_sql"]
    assert "COUNT(DISTINCT address) AS holder_count" in result["suggested_sql"]
    assert "get_top_cash_users" in result["wrong_alternative_note"]
    assert result["summary"]["holder_count"] == 0
    assert result["summary"]["balances_by_blockchain"] == []


def test_get_cash_token_totals_returns_token_filtered_planning_response():
    result = get_cash_token_totals(
        as_of_date="2026-04-13",
        token_symbol="liquidUSD",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert result["as_of_date"] == "2026-04-13"
    assert result["token_symbol"] == "liquidUSD"
    assert result["aggregate_scope"] == "token-filtered Cash balances"
    assert "token_symbol = 'liquidUSD'" in result["suggested_sql"]
    assert "CAST(day AS DATE) = CAST('2026-04-13' AS DATE)" in result["suggested_sql"]
    assert "balances_by_blockchain" in result["expected_output_fields"]


def test_get_cash_token_totals_live_execution_for_token_symbol(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "address_name = 'CASH'" in sql
        assert "token_symbol = 'liquidUSD'" in sql
        return [
            {
                "row_type": "overview",
                "latest_day": "2026-04-13",
                "blockchain": None,
                "holder_count": 3,
                "total_token_balance_usd": 3500.0,
                "total_token_balance_eth": 1.25,
                "total_token_balance": 3500.0,
                "token_symbol": "liquidUSD",
                "token_underlying_symbol": "USDT",
            },
            {
                "row_type": "blockchain",
                "latest_day": "2026-04-13",
                "blockchain": "optimism",
                "holder_count": 2,
                "total_token_balance_usd": 3000.0,
                "total_token_balance_eth": 1.05,
                "total_token_balance": 3000.0,
                "token_symbol": "liquidUSD",
                "token_underlying_symbol": "USDT",
            },
            {
                "row_type": "blockchain",
                "latest_day": "2026-04-13",
                "blockchain": "base",
                "holder_count": 1,
                "total_token_balance_usd": 500.0,
                "total_token_balance_eth": 0.2,
                "total_token_balance": 500.0,
                "token_symbol": "liquidUSD",
                "token_underlying_symbol": "USDT",
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_token_totals(
        token_symbol="liquidUSD",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 3
    assert result["summary"]["latest_day"] == "2026-04-13"
    assert result["summary"]["holder_count"] == 3
    assert result["summary"]["total_token_balance_usd"] == 3500.0
    assert result["summary"]["total_token_balance"] == 3500.0
    assert result["summary"]["token_symbol"] == "liquidUSD"
    assert result["summary"]["token_underlying_symbol"] == "USDT"
    assert result["summary"]["balances_by_blockchain"][0]["blockchain"] == "optimism"


def test_get_cash_token_totals_live_execution_for_token_symbol_and_blockchain(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured_sql = {}

    def fake_execute(sql):
        captured_sql["sql"] = sql
        return [
            {
                "row_type": "overview",
                "latest_day": "2026-04-13",
                "blockchain": None,
                "holder_count": 2,
                "total_token_balance_usd": 900.0,
                "total_token_balance_eth": 0.3,
                "total_token_balance": 900.0,
                "token_symbol": "liquidUSD",
                "token_underlying_symbol": "USDT",
            },
            {
                "row_type": "blockchain",
                "latest_day": "2026-04-13",
                "blockchain": "optimism",
                "holder_count": 2,
                "total_token_balance_usd": 900.0,
                "total_token_balance_eth": 0.3,
                "total_token_balance": 900.0,
                "token_symbol": "liquidUSD",
                "token_underlying_symbol": "USDT",
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_token_totals(
        token_symbol="liquidUSD",
        blockchain="optimism",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert "token_symbol = 'liquidUSD'" in captured_sql["sql"]
    assert "blockchain = 'optimism'" in captured_sql["sql"]
    assert result["aggregate_scope"] == "token + blockchain filtered Cash balances"
    assert result["summary"]["balances_by_blockchain"][0]["blockchain"] == "optimism"


def test_get_cash_token_totals_validates_token_symbol_and_token_address_together():
    result = get_cash_token_totals(
        token_symbol="liquidUSD",
        token_address="0x1111111111111111111111111111111111111111",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert "Provide only one of token_symbol or token_address." in result["error"]


def test_get_cash_token_totals_empty_result_behavior(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "row_type": "overview",
                "latest_day": None,
                "blockchain": None,
                "holder_count": 0,
                "total_token_balance_usd": 0.0,
                "total_token_balance_eth": 0.0,
                "total_token_balance": None,
                "token_symbol": "liquidUSD",
                "token_underlying_symbol": "USDT",
            }
        ],
    )

    result = get_cash_token_totals(
        token_symbol="liquidUSD",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert result["row_count"] == 0
    assert result["rows"] == []
    assert result["summary"]["holder_count"] == 0
    assert result["summary"]["total_token_balance_usd"] == 0.0
    assert "No Cash balances matched" in result["warning"]


def test_get_cash_token_totals_prompt_equivalent_liquidusd_total(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "row_type": "overview",
                "latest_day": "2026-04-13",
                "blockchain": None,
                "holder_count": 4,
                "total_token_balance_usd": 4200.0,
                "total_token_balance_eth": 1.5,
                "total_token_balance": 4200.0,
                "token_symbol": "liquidUSD",
                "token_underlying_symbol": "USDT",
            },
            {
                "row_type": "blockchain",
                "latest_day": "2026-04-13",
                "blockchain": "optimism",
                "holder_count": 4,
                "total_token_balance_usd": 4200.0,
                "total_token_balance_eth": 1.5,
                "total_token_balance": 4200.0,
                "token_symbol": "liquidUSD",
                "token_underlying_symbol": "USDT",
            },
        ],
    )

    result = get_cash_token_totals(
        token_symbol="liquidUSD",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert result["summary"]["token_symbol"] == "liquidUSD"
    assert result["summary"]["holder_count"] == 4
    assert result["summary"]["total_token_balance_usd"] == 4200.0
    assert "top-N cohorts" in result["important_caveats"][2]


def test_get_cash_holdings_timeseries_returns_period_planning_response():
    result = get_cash_holdings_timeseries(
        period="last_30_days",
        token_symbol="liquidUSD",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert result["dataset_name"] == "dune.ether_fi.result_etherfi_assets_under_management"
    assert result["start_date"] == "2026-03-24"
    assert result["end_date"] == "2026-04-22"
    assert result["granularity"] == "day"
    assert result["question_class"] == "time-series summary"
    assert result["aggregate_scope"] == "token-filtered Cash balances"
    assert "GROUP BY 1, 2" in result["suggested_sql"]
    assert "AVG(total_usd) AS avg_balance_usd" in result["suggested_sql"]
    assert "one aggregate Dune query" in result["wrong_alternative_note"]
    assert result["summary"]["day_count"] == 0
    assert result["timeseries"] == []


def test_get_cash_holdings_timeseries_validates_ranges_and_filters():
    missing_range = get_cash_holdings_timeseries(
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    both_token_filters = get_cash_holdings_timeseries(
        period="last_30_days",
        token_symbol="liquidUSD",
        token_address="0x1111111111111111111111111111111111111111",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    symbol_and_symbols = get_cash_holdings_timeseries(
        period="last_30_days",
        token_symbol="liquidUSD",
        token_symbols=["liquidETH"],
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    empty_token_symbols = get_cash_holdings_timeseries(
        period="last_30_days",
        token_symbols=[],
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    bad_granularity = get_cash_holdings_timeseries(
        period="last_30_days",
        granularity="week",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    bad_date_range = get_cash_holdings_timeseries(
        start_date="2026-04-22",
        end_date="2026-04-01",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert "Provide either start_date + end_date or a supported period." in missing_range["error"]
    assert "Provide only one of token_symbol, token_symbols, or token_address." in both_token_filters["error"]
    assert "Provide only one of token_symbol, token_symbols, or token_address." in symbol_and_symbols["error"]
    assert "token_symbols must be a non-empty list." in empty_token_symbols["error"]
    assert "granularity must be 'day' or 'month'." in bad_granularity["error"]
    assert "start_date must be on or before end_date." in bad_date_range["error"]


def test_get_cash_holdings_timeseries_validates_group_by_and_category_preset():
    bad_group_by = get_cash_holdings_timeseries(
        period="last_30_days",
        group_by="blockchain",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    bad_preset = get_cash_holdings_timeseries(
        period="last_30_days",
        group_by="category",
        category_preset="custom",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    missing_preset = get_cash_holdings_timeseries(
        period="last_30_days",
        group_by="category",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    preset_with_token_filter = get_cash_holdings_timeseries(
        period="last_30_days",
        group_by="category",
        category_preset="cash_balance_buckets",
        token_symbol="liquidUSD",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    categories_without_category_grouping = get_cash_holdings_timeseries(
        period="last_30_days",
        group_by="token_symbol",
        category_preset="cash_balance_buckets",
        categories=["liquidUSD"],
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )
    bad_category = get_cash_holdings_timeseries(
        period="last_30_days",
        group_by="category",
        category_preset="cash_balance_buckets",
        categories=["other"],
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert "group_by must be one of: category, token_symbol." in bad_group_by["error"]
    assert "category_preset must be one of: cash_balance_buckets." in bad_preset["error"]
    assert "group_by='category' requires category_preset='cash_balance_buckets'." in missing_preset["error"]
    assert "category_preset cannot be combined with token_symbol, token_symbols, or token_address filters." in preset_with_token_filter["error"]
    assert "category_preset requires group_by='category'." in categories_without_category_grouping["error"]
    assert "categories must contain only: liquidBTC, liquidETH, liquidUSD, stables." in bad_category["error"]


def test_get_cash_holdings_timeseries_returns_monthly_token_symbol_planning_response():
    result = get_cash_holdings_timeseries(
        period="last_2_years",
        granularity="month",
        group_by="token_symbol",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 24),
    )

    assert result["start_date"] == "2024-04-24"
    assert result["end_date"] == "2026-04-24"
    assert result["granularity"] == "month"
    assert result["group_by"] == "token_symbol"
    assert result["expected_output_fields"] == ["month", "month_end_day", "token_symbol", "holder_count", "total_usd", "total_eth"]
    assert "DATE_TRUNC('month', day)" in result["suggested_sql"]
    assert "MAX(day) AS month_end_day" in result["suggested_sql"]
    assert "token_symbol" in result["suggested_sql"]
    assert "one aggregate Dune query" in result["wrong_alternative_note"]


def test_get_cash_holdings_timeseries_plans_batched_token_symbols_in_one_query():
    result = get_cash_holdings_timeseries(
        period="last_2_years",
        granularity="month",
        group_by="token_symbol",
        token_symbols=["liquidUSD", "liquidETH", "liquidBTC", "liquidUSD"],
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 24),
    )

    assert result["token_symbol"] is None
    assert result["token_symbols"] == ["liquidUSD", "liquidETH", "liquidBTC"]
    assert result["summary"]["token_symbols"] == ["liquidUSD", "liquidETH", "liquidBTC"]
    assert result["aggregate_scope"] == "multi-symbol Cash balances batched in one query grouped by token_symbol"
    assert "token_symbol IN ('liquidUSD', 'liquidETH', 'liquidBTC')" in result["suggested_sql"]
    assert "token_symbol = 'liquidUSD'" not in result["suggested_sql"]
    assert "uses one token_symbol IN (...) filter and one Dune query" in result["batching_note"]


def test_get_cash_holdings_timeseries_returns_monthly_category_planning_response():
    result = get_cash_holdings_timeseries(
        period="last_2_years",
        granularity="month",
        group_by="category",
        category_preset="cash_balance_buckets",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 24),
    )

    assert result["category_preset"] == "cash_balance_buckets"
    assert {"token_symbol": "USDC", "category": "stables"} in result["category_mapping"]
    assert {"token_symbol": "liquidBTC", "category": "liquidBTC"} in result["category_mapping"]
    assert "WHEN token_symbol = 'USDC' THEN 'stables'" in result["suggested_sql"]
    assert "token_symbol IN ('liquidUSD', 'liquidETH', 'liquidBTC', 'USDC', 'USDC.e')" in result["suggested_sql"]
    assert "latest available daily snapshot in each calendar month" in result["monthly_snapshot_rule"]
    assert "category preset is intentionally narrow" in result["important_caveats"][3]


def test_get_cash_holdings_timeseries_plans_filtered_categories():
    result = get_cash_holdings_timeseries(
        period="last_2_years",
        granularity="month",
        group_by="category",
        category_preset="cash_balance_buckets",
        categories=["liquidUSD", "liquidETH", "liquidBTC", "stables", "stables"],
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 24),
    )

    assert result["categories"] == ["liquidUSD", "liquidETH", "liquidBTC", "stables"]
    assert result["summary"]["categories"] == ["liquidUSD", "liquidETH", "liquidBTC", "stables"]
    assert result["category_mapping"] == [
        {"token_symbol": "liquidUSD", "category": "liquidUSD"},
        {"token_symbol": "liquidETH", "category": "liquidETH"},
        {"token_symbol": "liquidBTC", "category": "liquidBTC"},
        {"token_symbol": "USDC", "category": "stables"},
        {"token_symbol": "USDC.e", "category": "stables"},
    ]
    assert "token_symbol IN ('liquidUSD', 'liquidETH', 'liquidBTC', 'USDC', 'USDC.e')" in result["suggested_sql"]


def test_get_cash_holdings_timeseries_rejects_period_and_explicit_dates_together():
    result = get_cash_holdings_timeseries(
        start_date="2026-04-01",
        end_date="2026-04-22",
        period="last_30_days",
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert "Provide either start_date + end_date or period, not both." in result["error"]


def test_get_cash_holdings_timeseries_live_execution_returns_chart_friendly_series(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured = {"calls": 0, "sql": None}

    def fake_execute(sql):
        captured["calls"] += 1
        captured["sql"] = sql
        return [
            {
                "day": "2026-04-20",
                "holder_count": 10,
                "total_usd": 1000.0,
                "avg_balance_usd": 100.0,
                "total_eth": 0.5,
                "avg_balance_eth": 0.05,
            },
            {
                "day": "2026-04-21",
                "holder_count": 20,
                "total_usd": 2600.0,
                "avg_balance_usd": 130.0,
                "total_eth": 1.0,
                "avg_balance_eth": 0.05,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_holdings_timeseries(
        start_date="2026-04-20",
        end_date="2026-04-21",
        blockchain="optimism",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert captured["calls"] == 1
    assert "CAST(day AS DATE) BETWEEN CAST('2026-04-20' AS DATE) AND CAST('2026-04-21' AS DATE)" in captured["sql"]
    assert "blockchain = 'optimism'" in captured["sql"]
    assert "GROUP BY 1, 2" in captured["sql"]
    assert result["executed_live"] is True
    assert result["row_count"] == 2
    assert result["rows"] == result["timeseries"]
    assert result["summary"]["day_count"] == 2
    assert result["summary"]["latest_day"] == "2026-04-21"
    assert result["summary"]["latest_avg_balance_usd"] == 130.0
    assert result["summary"]["average_of_daily_avg_balance_usd"] == 115.0


def test_get_cash_holdings_timeseries_live_execution_returns_monthly_category_series(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured = {"calls": 0, "sql": None}

    def fake_execute(sql):
        captured["calls"] += 1
        captured["sql"] = sql
        return [
            {
                "month": "2026-03-01",
                "month_end_day": "2026-03-31",
                "category": "liquidETH",
                "holder_count": 5,
                "total_usd": 3000.0,
                "total_eth": 1.2,
            },
            {
                "month": "2026-03-01",
                "month_end_day": "2026-03-31",
                "category": "stables",
                "holder_count": 8,
                "total_usd": 900.0,
                "total_eth": 0.4,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-22",
                "category": "liquidETH",
                "holder_count": 7,
                "total_usd": 4200.0,
                "total_eth": 1.7,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-22",
                "category": "stables",
                "holder_count": 9,
                "total_usd": 1200.0,
                "total_eth": 0.5,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_holdings_timeseries(
        start_date="2026-03-01",
        end_date="2026-04-22",
        granularity="month",
        group_by="category",
        category_preset="cash_balance_buckets",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
    )

    assert captured["calls"] == 1
    assert "DATE_TRUNC('month', day)" in captured["sql"]
    assert "WHEN token_symbol = 'USDC.e' THEN 'stables'" in captured["sql"]
    assert result["executed_live"] is True
    assert result["row_count"] == 4
    assert result["timeseries"][0] == {
        "month": "2026-03-01",
        "month_end_day": "2026-03-31",
        "category": "liquidETH",
        "holder_count": 5,
        "total_usd": 3000.0,
        "total_eth": 1.2,
    }
    assert result["summary"]["month_count"] == 2
    assert result["summary"]["latest_month"] == "2026-04-01"
    assert result["summary"]["latest_day"] == "2026-04-22"
    assert result["summary"]["latest_total_usd"] == 5400.0
    assert result["summary"]["latest_totals_by_group"][0] == {
        "category": "liquidETH",
        "total_usd": 4200.0,
        "total_eth": 1.7,
        "holder_count": 7,
    }


def test_get_cash_holdings_timeseries_live_execution_batches_multiple_symbols(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured = {"calls": 0, "sql": None}

    def fake_execute(sql):
        captured["calls"] += 1
        captured["sql"] = sql
        return [
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-24",
                "token_symbol": "liquidUSD",
                "holder_count": 10,
                "total_usd": 10000.0,
                "total_eth": 4.0,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-24",
                "token_symbol": "liquidETH",
                "holder_count": 6,
                "total_usd": 20000.0,
                "total_eth": 8.0,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-24",
                "token_symbol": "liquidBTC",
                "holder_count": 2,
                "total_usd": 3000.0,
                "total_eth": 1.2,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_holdings_timeseries(
        period="last_2_years",
        granularity="month",
        group_by="token_symbol",
        token_symbols=["liquidUSD", "liquidETH", "liquidBTC"],
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 24),
    )

    assert captured["calls"] == 1
    assert "token_symbol IN ('liquidUSD', 'liquidETH', 'liquidBTC')" in captured["sql"]
    assert result["row_count"] == 3
    assert result["summary"]["token_symbols"] == ["liquidUSD", "liquidETH", "liquidBTC"]
    assert result["summary"]["latest_total_usd"] == 33000.0
    assert result["summary"]["latest_totals_by_group"][0] == {
        "token_symbol": "liquidETH",
        "total_usd": 20000.0,
        "total_eth": 8.0,
        "holder_count": 6,
    }


def test_get_cash_holdings_timeseries_empty_result_behavior(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", lambda sql: [])

    result = get_cash_holdings_timeseries(
        period="last_90_days",
        token_symbol="liquidUSD",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert result["row_count"] == 0
    assert result["timeseries"] == []
    assert result["summary"]["day_count"] == 0
    assert "No Cash balances matched" in result["warning"]


def test_get_cash_holdings_timeseries_prompt_equivalent_last_month_chart(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured_sql = {}

    def fake_execute(sql):
        captured_sql["sql"] = sql
        return [
            {
                "day": "2026-03-01",
                "holder_count": 4,
                "total_usd": 2000.0,
                "avg_balance_usd": 500.0,
                "total_eth": 0.8,
                "avg_balance_eth": 0.2,
            },
            {
                "day": "2026-03-31",
                "holder_count": 5,
                "total_usd": 3000.0,
                "avg_balance_usd": 600.0,
                "total_eth": 1.1,
                "avg_balance_eth": 0.22,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_holdings_timeseries(
        period="last_month",
        token_symbol="liquidUSD",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert result["start_date"] == "2026-03-01"
    assert result["end_date"] == "2026-03-31"
    assert "token_symbol = 'liquidUSD'" in captured_sql["sql"]
    assert result["summary"]["token_symbol"] == "liquidUSD"
    assert result["summary"]["latest_avg_balance_usd"] == 600.0


def test_get_cash_holdings_timeseries_prompt_equivalent_monthly_cash_categories(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured_sql = {}

    def fake_execute(sql):
        captured_sql["sql"] = sql
        return [
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-24",
                "category": "liquidUSD",
                "holder_count": 10,
                "total_usd": 10000.0,
                "total_eth": 4.0,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-24",
                "category": "liquidETH",
                "holder_count": 6,
                "total_usd": 20000.0,
                "total_eth": 8.0,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-24",
                "category": "liquidBTC",
                "holder_count": 2,
                "total_usd": 3000.0,
                "total_eth": 1.2,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-24",
                "category": "stables",
                "holder_count": 20,
                "total_usd": 5000.0,
                "total_eth": 2.0,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_holdings_timeseries(
        period="last_2_years",
        granularity="month",
        group_by="category",
        category_preset="cash_balance_buckets",
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 24),
    )

    assert result["start_date"] == "2024-04-24"
    assert result["end_date"] == "2026-04-24"
    assert "GROUP BY 1, 2" in captured_sql["sql"]
    assert "ORDER BY month_end_days.month ASC, month_end_days.category ASC" in captured_sql["sql"]
    assert result["summary"]["latest_totals_by_group"][0]["category"] == "liquidETH"
    assert result["summary"]["latest_total_usd"] == 38000.0


def test_get_cash_holdings_timeseries_prompt_equivalent_multiple_symbols_one_query(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured = {"calls": 0, "sql": None}

    def fake_execute(sql):
        captured["calls"] += 1
        captured["sql"] = sql
        return []

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_holdings_timeseries(
        period="last_2_years",
        granularity="month",
        group_by="token_symbol",
        token_symbols=["liquidUSD", "liquidETH", "liquidBTC"],
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 24),
    )

    assert captured["calls"] == 1
    assert "token_symbol IN ('liquidUSD', 'liquidETH', 'liquidBTC')" in captured["sql"]
    assert "GROUP BY 1, 2" in captured["sql"]
    assert result["summary"]["token_symbols"] == ["liquidUSD", "liquidETH", "liquidBTC"]


def test_get_cash_holdings_timeseries_prompt_equivalent_filtered_categories_one_query(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured = {"calls": 0, "sql": None}

    def fake_execute(sql):
        captured["calls"] += 1
        captured["sql"] = sql
        return []

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_holdings_timeseries(
        period="last_2_years",
        granularity="month",
        group_by="category",
        category_preset="cash_balance_buckets",
        categories=["liquidUSD", "liquidETH", "liquidBTC", "stables"],
        execute_live=True,
        datasets=_cash_aum_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 24),
    )

    assert captured["calls"] == 1
    assert "WHEN token_symbol = 'liquidUSD' THEN 'liquidUSD'" in captured["sql"]
    assert "WHEN token_symbol = 'USDC.e' THEN 'stables'" in captured["sql"]
    assert "token_symbol IN ('liquidUSD', 'liquidETH', 'liquidBTC', 'USDC', 'USDC.e')" in captured["sql"]
    assert result["summary"]["categories"] == ["liquidUSD", "liquidETH", "liquidBTC", "stables"]


def _cash_safe_profile_datasets():
    return {
        "dune.ether_fi.result_etherfi_assets_under_management": {
            "name": "dune.ether_fi.result_etherfi_assets_under_management",
            "display_name": "Ether.fi Assets Under Management",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
            "query_ready": True,
            "grain": "one row per day, address, and token",
            "date_column": "day",
            "refresh_interval_minutes": 60,
        },
        "dune.ether_fi.result_etherfi_cash_events": {
            "name": "dune.ether_fi.result_etherfi_cash_events",
            "display_name": "Ether.fi Cash Events",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_etherfi_cash_events",
            "query_ready": True,
            "grain": "one row per Cash event",
            "refresh_interval_minutes": 720,
        },
        "dune.ether_fi.result_etherfi_addresses": {
            "name": "dune.ether_fi.result_etherfi_addresses",
            "display_name": "Ether.fi Addresses",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_etherfi_addresses",
            "query_ready": True,
            "grain": "one row per blockchain address classification record",
            "refresh_interval_minutes": 2880,
        },
    }


def test_get_cash_safe_profile_planning_mode_omits_identity_lookup_by_default():
    result = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        datasets=_cash_safe_profile_datasets(),
        freshness_registry={},
    )

    assert result["address"] == "0x1111111111111111111111111111111111111111"
    assert result["validate_cash_identity"] is False
    assert result["dataset_names"]["balances"] == "dune.ether_fi.result_etherfi_assets_under_management"
    assert result["dataset_names"]["events"] == "dune.ether_fi.result_etherfi_cash_events"
    assert result["dataset_names"]["identity"] is None
    assert "result_etherfi_addresses" not in result["suggested_sql"]
    assert "user_safe = 0x1111111111111111111111111111111111111111" in result["suggested_sql"]
    assert "address_name = 'CASH'" in result["suggested_sql"]
    assert "profile_mode" in result["mode_notes"]
    assert "is_classified_cash" not in result
    assert result["summary"]["identity"].startswith("identity validation was not requested")


def test_get_cash_safe_profile_planning_mode_can_include_identity_validation():
    result = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        as_of_date="2026-04-13",
        recent_days=14,
        validate_cash_identity=True,
        datasets=_cash_safe_profile_datasets(),
        freshness_registry={},
    )

    assert result["as_of_date"] == "2026-04-13"
    assert result["recent_days"] == 14
    assert result["validate_cash_identity"] is True
    assert result["dataset_names"]["identity"] == "dune.ether_fi.result_etherfi_addresses"
    assert "FROM dune.ether_fi.result_etherfi_addresses" in result["suggested_sql"]
    assert "COUNT_IF(name = 'CASH') > 0 AS is_classified_cash" in result["suggested_sql"]
    assert result["classification_source"] == "dune.ether_fi.result_etherfi_addresses"


def test_get_cash_safe_profile_validates_inputs():
    datasets = _cash_safe_profile_datasets()

    missing_address = get_cash_safe_profile("", datasets=datasets, freshness_registry={})
    bad_date = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        as_of_date="04-13-2026",
        datasets=datasets,
        freshness_registry={},
    )
    bad_recent_days = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        recent_days=0,
        datasets=datasets,
        freshness_registry={},
    )

    assert "Address must be a 42-character 0x-prefixed hex string" in missing_address["error"]
    assert "as_of_date must be a YYYY-MM-DD string" in bad_date["error"]
    assert "recent_days must be a positive integer no greater than 365" in bad_recent_days["error"]


def test_get_cash_safe_profile_execute_live_profiles_balances_and_activity(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "result_etherfi_addresses" not in sql
        return [
            {
                "row_type": "balance_token",
                "latest_balance_day": "2026-04-13",
                "token_symbol": "weETH",
                "token_underlying_symbol": "WETH",
                "token_balance": 2.0,
                "token_balance_underlying": 2.1,
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            },
            {
                "row_type": "balance_token",
                "latest_balance_day": "2026-04-13",
                "token_symbol": "USDC",
                "token_underlying_symbol": "USDC",
                "token_balance": 2500.0,
                "token_balance_underlying": 2500.0,
                "token_balance_usd": 2500.0,
                "token_balance_eth": 1.0,
            },
            {
                "row_type": "balance_blockchain",
                "latest_balance_day": "2026-04-13",
                "blockchain": "ethereum",
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            },
            {
                "row_type": "balance_blockchain",
                "latest_balance_day": "2026-04-13",
                "blockchain": "base",
                "token_balance_usd": 2500.0,
                "token_balance_eth": 1.0,
            },
            {
                "row_type": "events_overview",
                "event_count": 3,
                "token_amount_usd": 120.0,
                "latest_event_time": "2026-04-12 10:00:00 UTC",
            },
            {
                "row_type": "event_type",
                "event_type": "spend",
                "event_count": 2,
                "token_amount_usd": 100.0,
            },
            {
                "row_type": "event_type",
                "event_type": "cashback",
                "event_count": 1,
                "token_amount_usd": 20.0,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets=_cash_safe_profile_datasets(),
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["latest_balance_day"] == "2026-04-13"
    assert result["total_token_balance_usd"] == 7500.0
    assert result["total_token_balance_eth"] == 3.0
    assert result["balances_by_token"][0]["token_symbol"] == "weETH"
    assert result["balances_by_blockchain"][0]["blockchain"] == "ethereum"
    assert result["recent_event_count"] == 3
    assert result["recent_event_types"][0]["event_type"] == "spend"
    assert result["latest_event_time"] == "2026-04-12 10:00:00 UTC"
    assert result["has_cash_activity_evidence"] is True
    assert "is_classified_cash" not in result
    assert result["summary"]["identity"].startswith("identity validation was not requested")


def test_get_cash_safe_profile_execute_live_can_validate_identity(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "FROM dune.ether_fi.result_etherfi_addresses" in sql
        return [
            {
                "row_type": "events_overview",
                "event_count": 0,
                "latest_event_time": None,
            },
            {
                "row_type": "identity",
                "is_classified_cash": True,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        validate_cash_identity=True,
        execute_live=True,
        datasets=_cash_safe_profile_datasets(),
        freshness_registry={},
    )

    assert result["is_classified_cash"] is True
    assert result["classification_source"] == "dune.ether_fi.result_etherfi_addresses"
    assert result["summary"]["identity"] == "classified as CASH in the canonical address registry"


def test_get_cash_safe_profile_live_execution_failures_return_execution_error(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: (_ for _ in ()).throw(RuntimeError("Dune query execution failed: boom")),
    )

    result = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets=_cash_safe_profile_datasets(),
        freshness_registry={},
    )

    assert "execution_error" in result
    assert result["executed_live"] is False
    assert result["total_token_balance_usd"] == 0.0


def test_cash_workflow_summarize_safe_uses_evidence_profile_without_identity_claim(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "row_type": "balance_token",
                "latest_balance_day": "2026-04-13",
                "token_symbol": "weETH",
                "token_underlying_symbol": "WETH",
                "token_balance": 2.0,
                "token_balance_underlying": 2.1,
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            },
            {
                "row_type": "balance_blockchain",
                "latest_balance_day": "2026-04-13",
                "blockchain": "ethereum",
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            },
            {
                "row_type": "events_overview",
                "event_count": 2,
                "latest_event_time": "2026-04-12 10:00:00 UTC",
            },
            {
                "row_type": "event_type",
                "event_type": "spend",
                "event_count": 2,
                "token_amount_usd": 100.0,
            },
        ],
    )

    result = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets=_cash_safe_profile_datasets(),
        freshness_registry={},
    )

    assert result["total_token_balance_usd"] == 5000.0
    assert result["balances_by_token"][0]["token_symbol"] == "weETH"
    assert result["recent_event_count"] == 2
    assert result["has_cash_activity_evidence"] is True
    assert "is_classified_cash" not in result
    assert result["summary"]["identity"].startswith("identity validation was not requested")


def test_cash_workflow_validate_safe_identity_distinguishes_canonical_classification(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "row_type": "events_overview",
                "event_count": 0,
                "latest_event_time": None,
            },
            {
                "row_type": "identity",
                "is_classified_cash": False,
            },
        ],
    )

    result = get_cash_safe_profile(
        "0x1111111111111111111111111111111111111111",
        validate_cash_identity=True,
        execute_live=True,
        datasets=_cash_safe_profile_datasets(),
        freshness_registry={},
    )

    assert result["validate_cash_identity"] is True
    assert result["is_classified_cash"] is False
    assert result["classification_source"] == "dune.ether_fi.result_etherfi_addresses"
    assert result["summary"]["identity"] == "not classified as CASH in the canonical address registry"


def test_cash_workflow_top_users_returns_ranked_all_users_with_breakdowns(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "rank": 1,
                "day": "2026-04-13",
                "address": "0x1111111111111111111111111111111111111111",
                "total_token_balance_usd": 7500.0,
                "total_token_balance_eth": 3.0,
                "blockchain": "ethereum",
                "token_address": "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
                "token_symbol": "weETH",
                "token_type": "peg-to-underlying",
                "token_project": "ether.fi",
                "token_balance": 2.0,
                "token_balance_underlying": 2.1,
                "token_underlying_symbol": "WETH",
                "token_balance_usd": 5000.0,
                "token_balance_eth": 2.0,
            },
            {
                "rank": 1,
                "day": "2026-04-13",
                "address": "0x1111111111111111111111111111111111111111",
                "total_token_balance_usd": 7500.0,
                "total_token_balance_eth": 3.0,
                "blockchain": "base",
                "token_address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "token_symbol": "USDC",
                "token_type": "stablecoin",
                "token_project": "circle",
                "token_balance": 2500.0,
                "token_balance_underlying": 2500.0,
                "token_underlying_symbol": "USDC",
                "token_balance_usd": 2500.0,
                "token_balance_eth": 1.0,
            },
        ],
    )

    result = get_top_cash_users(
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_assets_under_management": {
                "name": "dune.ether_fi.result_etherfi_assets_under_management",
                "display_name": "Ether.fi Assets Under Management",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_assets_under_management",
                "query_ready": True,
                "grain": "one row per day, address, and token",
                "date_column": "day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["rows"][0]["rank"] == 1
    assert result["summary"]["user_count_returned"] == 1
    assert result["summary"]["total_usd_of_returned_users"] == 7500.0
    assert result["rows"][0]["token_breakdown"][0]["token_symbol"] == "weETH"
    assert result["rows"][0]["chain_breakdown"][0]["blockchain"] == "ethereum"
    assert "single-address AUM balance tool" in result["tool_gap_note"]


def test_cash_workflow_recent_spend_activity_uses_summary_path(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "event_type = 'spend'" in sql
        if "token_symbol" in sql:
            return [{"token_symbol": "USDC", "event_count": 4, "total_token_amount": 240.0, "total_token_amount_usd": 240.0}]
        if "blockchain" in sql:
            return [{"blockchain": "base", "event_count": 4, "total_token_amount_usd": 240.0}]
        if "COUNT(*) AS event_count" in sql:
            return [{
                "event_count": 4,
                "latest_event_time": "2026-04-13 12:00:00 UTC",
                "total_token_amount_usd": 240.0,
                "single_token_symbol": "USDC",
                "total_token_amount": 240.0,
            }]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_events(
        event_type="spend",
        start_date="2026-04-01",
        end_date="2026-04-13",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_cash_events": {
                "name": "dune.ether_fi.result_etherfi_cash_events",
                "display_name": "Ether.fi Cash Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_cash_events",
                "query_ready": True,
                "grain": "one row per Cash event",
                "refresh_interval_minutes": 720,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert result["rows"] == []
    assert result["summary"]["event_type"] == "spend"
    assert result["summary"]["event_count"] == 4
    assert result["summary"]["totals_by_token"][0]["token_symbol"] == "USDC"
    assert result["summary"]["totals_by_blockchain"][0]["blockchain"] == "base"


def test_cash_events_planner_defaults_recent_prompts_to_live_query():
    plan = plan_etherfi_query(
        "Show recent ether.fi Cash spend activity.",
        freshness_registry={},
    )

    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_etherfi_cash_events"
    assert plan["data_access"]["selected_data_access"] == "live_query"
    assert plan["data_access"]["live_query"]["defaults_to_mat_view"] is True
    assert any(
        "currently defaults to the same materialized-view" in note
        for note in plan["data_access"]["data_access_notes"]
    )


def test_cash_events_planner_prefers_mat_view_for_historical_prompts():
    plan = plan_etherfi_query(
        "Show weekly Cash spend volume over time.",
        freshness_registry={},
    )

    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_etherfi_cash_events"
    assert plan["data_access"]["selected_data_access"] == "mat_view"
    assert any("baseline materialized view" in note for note in plan["data_access"]["data_access_notes"])


def test_cash_workflow_borrow_and_repay_for_safe_preserve_event_type_semantics(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        event_type = "borrow" if "event_type = 'borrow'" in sql else "repay"
        assert "user_safe = 0x1111111111111111111111111111111111111111" in sql
        if "token_symbol" in sql:
            total = 500.0 if event_type == "borrow" else 125.0
            return [{"token_symbol": "USDC", "event_count": 2 if event_type == "borrow" else 1, "total_token_amount": total, "total_token_amount_usd": total}]
        if "blockchain" in sql:
            total = 500.0 if event_type == "borrow" else 125.0
            return [{"blockchain": "base", "event_count": 2 if event_type == "borrow" else 1, "total_token_amount_usd": total}]
        if "COUNT(*) AS event_count" in sql:
            total = 500.0 if event_type == "borrow" else 125.0
            return [{
                "event_count": 2 if event_type == "borrow" else 1,
                "latest_event_time": "2026-04-13 12:00:00 UTC",
                "total_token_amount_usd": total,
                "single_token_symbol": "USDC",
                "total_token_amount": total,
            }]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    common_kwargs = {
        "user_safe": "0x1111111111111111111111111111111111111111",
        "execute_live": True,
        "datasets": {
            "dune.ether_fi.result_etherfi_cash_events": {
                "name": "dune.ether_fi.result_etherfi_cash_events",
                "display_name": "Ether.fi Cash Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_cash_events",
                "query_ready": True,
                "grain": "one row per Cash event",
                "refresh_interval_minutes": 720,
            }
        },
        "freshness_registry": {},
    }
    borrow = get_cash_events(event_type="borrow", **common_kwargs)
    repay = get_cash_events(event_type="repay", **common_kwargs)

    assert borrow["summary"]["user_safe"] == "0x1111111111111111111111111111111111111111"
    assert repay["summary"]["user_safe"] == "0x1111111111111111111111111111111111111111"
    assert borrow["summary"]["event_type"] == "borrow"
    assert repay["summary"]["event_type"] == "repay"
    assert borrow["summary"]["total_token_amount_usd"] == 500.0
    assert repay["summary"]["total_token_amount_usd"] == 125.0


def test_cash_workflow_user_safe_meaning_is_discoverable_from_natural_prompt():
    results = search_datasets("What does user_safe mean in ether.fi Cash events?")

    assert results[0]["name"] == "dune.ether_fi.result_etherfi_cash_events"
    assert any("`user_safe` is the Cash safe" in note for note in results[0]["semantic_notes"])


def test_cash_workflow_borrow_index_is_discoverable_from_debt_prompts():
    borrow_index_results = search_datasets("cash borrow index")
    debt_index_results = search_datasets("ether.fi cash debt index")

    assert borrow_index_results[0]["name"] == "dune.ether_fi.result_etherfi_cash_borrow_index"
    assert debt_index_results[0]["name"] == "dune.ether_fi.result_etherfi_cash_borrow_index"


def test_get_cash_events_returns_structured_response_with_sql():
    result = get_cash_events(
        event_type="spend",
        user_safe="0x1111111111111111111111111111111111111111",
        start_date="2026-01-01",
        end_date="2026-01-31",
        mode="rows",
        datasets={
            "dune.ether_fi.result_etherfi_cash_events": {
                "name": "dune.ether_fi.result_etherfi_cash_events",
                "display_name": "Ether.fi Cash Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_cash_events",
                "query_ready": True,
                "grain": "one row per Cash event",
                "refresh_interval_minutes": 720,
            }
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_etherfi_cash_events"
    assert "event_type = 'spend'" in result["suggested_sql"]
    assert "user_safe = 0x1111111111111111111111111111111111111111" in result["suggested_sql"]
    assert "block_date >=" in result["suggested_sql"]


def test_get_cash_events_rejects_unknown_event_type():
    result = get_cash_events(
        event_type="mint",
        datasets={
            "dune.ether_fi.result_etherfi_cash_events": {
                "name": "dune.ether_fi.result_etherfi_cash_events",
                "display_name": "Ether.fi Cash Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_cash_events",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "error" in result
    assert "event_type must be one of" in result["error"]


def test_get_cash_events_execute_live_returns_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "block_date": "2026-01-02",
                "block_time": "2026-01-02 10:00:00",
                "blockchain": "optimism",
                "event_type": "spend",
                "user_safe": "0x1111111111111111111111111111111111111111",
                "token_symbol": "USDC",
                "token_amount": 20.0,
                "token_amount_usd": 20.0,
            },
            {
                "block_date": "2026-01-03",
                "block_time": "2026-01-03 10:00:00",
                "blockchain": "optimism",
                "event_type": "cashback",
                "user_safe": "0x1111111111111111111111111111111111111111",
                "token_symbol": "USDC",
                "token_amount": 2.0,
                "token_amount_usd": 2.0,
            },
        ],
    )

    result = get_cash_events(
        user_safe="0x1111111111111111111111111111111111111111",
        mode="rows",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_cash_events": {
                "name": "dune.ether_fi.result_etherfi_cash_events",
                "display_name": "Ether.fi Cash Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_cash_events",
                "query_ready": True,
                "grain": "one row per Cash event",
                "refresh_interval_minutes": 720,
            }
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 2
    assert result["summary"]["total_token_amount_usd"] == 22.0
    assert result["summary"]["totals_by_event_type"][0]["event_type"] in {"spend", "cashback"}


def test_get_cash_events_summary_mode_uses_aggregate_queries(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        if "COUNT(*) AS event_count" in sql:
            return [{
                "event_count": 12,
                "latest_event_time": "2026-04-08 12:13:57.000 UTC",
                "total_token_amount_usd": 345.67,
                "single_token_symbol": None,
                "total_token_amount": None,
            }]
        if "GROUP BY 1" in sql and "token_symbol" in sql:
            return [{"token_symbol": "USDC", "event_count": 12, "total_token_amount": 345.67, "total_token_amount_usd": 345.67}]
        if "GROUP BY 1" in sql and "blockchain" in sql:
            return [{"blockchain": "optimism", "event_count": 12, "total_token_amount_usd": 345.67}]
        if "GROUP BY 1" in sql and "event_type" in sql:
            return [{"event_type": "spend", "event_count": 12, "total_token_amount_usd": 345.67}]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_cash_events(
        start_date="2026-04-01",
        end_date="2026-04-08",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_cash_events": {
                "name": "dune.ether_fi.result_etherfi_cash_events",
                "display_name": "Ether.fi Cash Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_cash_events",
                "query_ready": True,
                "grain": "one row per Cash event",
                "refresh_interval_minutes": 720,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert result["rows"] == []
    assert result["row_count"] == 12
    assert result["summary"]["event_count"] == 12
    assert result["summary"]["total_token_amount_usd"] == 345.67


def test_get_cash_events_rows_mode_rejects_broad_high_limit_requests():
    result = get_cash_events(
        mode="rows",
        start_date="2026-01-01",
        end_date="2026-01-31",
        limit=1000,
        datasets={
            "dune.ether_fi.result_etherfi_cash_events": {
                "name": "dune.ether_fi.result_etherfi_cash_events",
                "display_name": "Ether.fi Cash Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_cash_events",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "Broad rows mode requests are expensive" in result["error"]


def test_get_protocol_token_holders_requires_token_filter():
    result = get_protocol_token_holders(
        datasets={
            "etherfi_protocol_token_holders": {
                "name": "etherfi_protocol_token_holders",
                "display_name": "Protocol Token Holders",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_holders",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert result["error"] == "Provide token_symbol or token_address."


def test_get_protocol_token_holders_rejects_excluding_defi_without_include_defi():
    result = get_protocol_token_holders(
        token_symbol="liquidETH",
        exclude_identified_defi=True,
        datasets={
            "etherfi_protocol_token_holders": {
                "name": "etherfi_protocol_token_holders",
                "display_name": "Protocol Token Holders",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_holders",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "include_defi=True" in result["error"]


def test_get_protocol_token_holders_uses_with_defi_dataset_when_requested():
    result = get_protocol_token_holders(
        token_symbol="liquidETH",
        include_defi=True,
        exclude_identified_defi=True,
        mode="rows",
        datasets={
            "etherfi_protocol_token_holders_with_defi": {
                "name": "etherfi_protocol_token_holders_with_defi",
                "display_name": "Protocol Token Holders With Defi",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_holders_with_defi",
                "query_ready": True,
                "grain": "one row per address per token per snapshot date",
                "refresh_interval_minutes": 240,
                "completeness label": "partial",
            }
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "etherfi_protocol_token_holders_with_defi"
    assert "identified_defi_contract IS NULL" in result["suggested_sql"]
    assert "completeness_note" in result


def test_get_protocol_token_holders_execute_live_returns_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-01",
                "blockchain": "ethereum",
                "address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "liquidETH",
                "token_balance": 10.0,
                "token_balance_usd": 25000.0,
                "token_balance_eth": 10.0,
                "identified_defi_contract": None,
            },
            {
                "day": "2026-04-01",
                "blockchain": "base",
                "address": "0x2222222222222222222222222222222222222222",
                "token_symbol": "liquidETH",
                "token_balance": 8.0,
                "token_balance_usd": 20000.0,
                "token_balance_eth": 8.0,
                "identified_defi_contract": "Aave",
            },
        ],
    )

    result = get_protocol_token_holders(
        token_symbol="liquidETH",
        include_defi=True,
        mode="rows",
        execute_live=True,
        datasets={
            "etherfi_protocol_token_holders_with_defi": {
                "name": "etherfi_protocol_token_holders_with_defi",
                "display_name": "Protocol Token Holders With Defi",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_holders_with_defi",
                "query_ready": True,
                "grain": "one row per address per token per snapshot date",
                "refresh_interval_minutes": 240,
                "completeness label": "partial",
            }
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 2
    assert result["summary"]["holder_count"] == 2
    assert result["summary"]["defi_contract_breakdown"][0]["identified_defi_contract"] in {
        "Aave",
        "unidentified_or_non_defi",
    }


def test_get_protocol_token_holders_summary_mode_uses_aggregate_queries(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        if "COUNT(*) AS holder_count" in sql and "SUM(token_balance) AS total_token_balance" in sql:
            return [{"latest_day": "2026-04-01", "holder_count": 2, "token_symbol": "liquidETH", "total_token_balance": 18.0}]
        if "SUM(COALESCE(token_balance_usd, 0)) AS token_balance_usd" in sql:
            return [{"blockchain": "ethereum", "holder_count": 2, "total_token_balance": 18.0, "token_balance_usd": 45000.0, "token_balance_eth": 18.0}]
        if "LIMIT 5;" in sql:
            return [{"address": "0x1111111111111111111111111111111111111111", "blockchain": "ethereum", "token_balance": 10.0, "token_balance_usd": 25000.0, "identified_defi_contract": None}]
        if "unidentified_or_non_defi" in sql:
            return [{"identified_defi_contract": "unidentified_or_non_defi", "holder_count": 1, "total_token_balance": 10.0, "token_balance_usd": 25000.0}]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_token_holders(
        token_symbol="liquidETH",
        include_defi=True,
        execute_live=True,
        datasets={
            "etherfi_protocol_token_holders_with_defi": {
                "name": "etherfi_protocol_token_holders_with_defi",
                "display_name": "Protocol Token Holders With Defi",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_holders_with_defi",
                "query_ready": True,
                "grain": "one row per address per token per snapshot date",
                "refresh_interval_minutes": 240,
                "completeness label": "partial",
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert result["rows"] == []
    assert result["summary"]["holder_count"] == 2
    assert result["summary"]["top_holders_preview"][0]["token_balance"] == 10.0


def _protocol_holder_datasets():
    return {
        "etherfi_protocol_token_holders": {
            "name": "etherfi_protocol_token_holders",
            "display_name": "Protocol Token Holders",
            "description": "Direct holders of ether.fi protocol tokens by address",
            "table_name": "dune.ether_fi.result_etherfi_protocol_token_holders",
            "query_ready": True,
            "grain": "one row per address per token per snapshot date",
            "refresh_interval_minutes": 240,
            "completeness label": "complete",
        },
        "etherfi_protocol_token_holders_with_defi": {
            "name": "etherfi_protocol_token_holders_with_defi",
            "display_name": "Protocol Token Holders With Defi",
            "description": "Holder exposure table that includes direct balances plus balances attributable to tracked defi deposits",
            "table_name": "dune.ether_fi.result_etherfi_protocol_token_holders_with_defi",
            "query_ready": True,
            "grain": "one row per address per token per snapshot date",
            "refresh_interval_minutes": 240,
            "completeness label": "partial",
        },
    }


def test_holder_workflow_direct_holders_are_discoverable_from_natural_prompts():
    top_holder_results = search_datasets("top eETH holders")
    direct_holder_results = search_datasets("direct protocol token holders")

    assert top_holder_results[0]["name"] == "etherfi_protocol_token_holders"
    assert direct_holder_results[0]["name"] == "etherfi_protocol_token_holders"
    assert "direct holder balances only" in " ".join(top_holder_results[0]["semantic_notes"])


def test_holder_workflow_defi_aware_holders_are_discoverable_from_natural_prompts():
    including_defi_results = search_datasets("top eETH holders including defi")
    exposure_results = search_datasets("holders with defi exposure")

    assert including_defi_results[0]["name"] == "etherfi_protocol_token_holders_with_defi"
    assert exposure_results[0]["name"] == "etherfi_protocol_token_holders_with_defi"
    assert including_defi_results[0]["completeness label"] == "partial"


def test_holder_workflow_completeness_caveat_surfaces_direct_vs_defi_distinction():
    results = search_datasets("direct holders clean with defi broader incomplete")
    result_names = [result["name"] for result in results]

    assert "etherfi_protocol_token_holders" in result_names
    assert "etherfi_protocol_token_holders_with_defi" in result_names
    direct = next(result for result in results if result["name"] == "etherfi_protocol_token_holders")
    with_defi = next(result for result in results if result["name"] == "etherfi_protocol_token_holders_with_defi")
    assert "cleaner default" in " ".join(direct["comparison_notes"])
    assert "broader but incomplete" in " ".join(with_defi["comparison_notes"])


def test_holder_workflow_identified_defi_contract_semantics_are_discoverable():
    meaning_results = search_datasets("what does identified_defi_contract mean?")
    exclude_results = search_datasets("exclude known defi contracts")

    assert meaning_results[0]["name"] == "etherfi_protocol_token_holders_with_defi"
    assert exclude_results[0]["name"] == "etherfi_protocol_token_holders_with_defi"
    assert any("identified_defi_contract" in note for note in meaning_results[0]["semantic_notes"])


def test_holder_workflow_direct_holders_summary_uses_latest_day_for_selected_token(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "FROM dune.ether_fi.result_etherfi_protocol_token_holders" in sql
        assert "token_symbol = 'eETH'" in sql
        assert "SELECT MAX(day) FROM dune.ether_fi.result_etherfi_protocol_token_holders" in sql
        assert "SUM(COALESCE(token_balance_usd, 0))" not in sql
        assert "SUM(COALESCE(token_balance_eth, 0))" not in sql
        if "COUNT(*) AS holder_count" in sql and "CASE WHEN COUNT(DISTINCT token_symbol)" in sql:
            return [{"latest_day": "2026-04-13", "holder_count": 2, "token_symbol": "eETH", "total_token_balance": 18.0}]
        if "CAST(0 AS DOUBLE) AS token_balance_usd" in sql:
            return [{"blockchain": "ethereum", "holder_count": 2, "total_token_balance": 18.0, "token_balance_usd": 0.0, "token_balance_eth": 0.0}]
        if "LIMIT 5;" in sql:
            return [{"address": "0x1111111111111111111111111111111111111111", "blockchain": "ethereum", "token_balance": 10.0}]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_token_holders(
        token_symbol="eETH",
        execute_live=True,
        datasets=_protocol_holder_datasets(),
        freshness_registry={},
    )

    assert result["dataset_name"] == "etherfi_protocol_token_holders"
    assert result["mode"] == "summary"
    assert result["summary"]["latest_day"] == "2026-04-13"
    assert result["summary"]["token_symbol"] == "eETH"
    assert result["summary"]["holder_count"] == 2
    assert result["summary"]["top_holders_preview"][0]["address"] == "0x1111111111111111111111111111111111111111"


def test_holder_workflow_with_defi_summary_preserves_partial_coverage_caveat(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "FROM dune.ether_fi.result_etherfi_protocol_token_holders_with_defi" in sql
        assert "token_symbol = 'eETH'" in sql
        if "COUNT(*) AS holder_count" in sql and "CASE WHEN COUNT(DISTINCT token_symbol)" in sql:
            return [{"latest_day": "2026-04-13", "holder_count": 3, "token_symbol": "eETH", "total_token_balance": 25.0}]
        if "SUM(COALESCE(token_balance_usd, 0)) AS token_balance_usd" in sql and "blockchain" in sql:
            return [{"blockchain": "ethereum", "holder_count": 3, "total_token_balance": 25.0, "token_balance_usd": 60000.0, "token_balance_eth": 25.0}]
        if "LIMIT 5;" in sql:
            return [{"address": "0x2222222222222222222222222222222222222222", "blockchain": "ethereum", "token_balance": 15.0, "token_balance_usd": 36000.0, "identified_defi_contract": "Aave"}]
        if "unidentified_or_non_defi" in sql:
            return [{"identified_defi_contract": "Aave", "holder_count": 1, "total_token_balance": 15.0, "token_balance_usd": 36000.0}]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_token_holders(
        token_symbol="eETH",
        include_defi=True,
        execute_live=True,
        datasets=_protocol_holder_datasets(),
        freshness_registry={},
    )

    assert result["dataset_name"] == "etherfi_protocol_token_holders_with_defi"
    assert result["summary"]["include_defi"] is True
    assert result["summary"]["defi_contract_breakdown"][0]["identified_defi_contract"] == "Aave"
    assert result["summary"]["top_holders_preview"][0]["identified_defi_contract"] == "Aave"
    assert "broader than direct holders" in result["completeness_note"]


def test_holder_workflow_exclude_identified_defi_adds_filter_and_preserves_summary_flag(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "identified_defi_contract IS NULL" in sql
        if "COUNT(*) AS holder_count" in sql and "CASE WHEN COUNT(DISTINCT token_symbol)" in sql:
            return [{"latest_day": "2026-04-13", "holder_count": 2, "token_symbol": "eETH", "total_token_balance": 10.0}]
        if "SUM(COALESCE(token_balance_usd, 0)) AS token_balance_usd" in sql and "blockchain" in sql:
            return [{"blockchain": "ethereum", "holder_count": 2, "total_token_balance": 10.0, "token_balance_usd": 24000.0, "token_balance_eth": 10.0}]
        if "LIMIT 5;" in sql:
            return [{"address": "0x3333333333333333333333333333333333333333", "blockchain": "ethereum", "token_balance": 10.0, "token_balance_usd": 24000.0, "identified_defi_contract": None}]
        if "unidentified_or_non_defi" in sql:
            return [{"identified_defi_contract": "unidentified_or_non_defi", "holder_count": 2, "total_token_balance": 10.0, "token_balance_usd": 24000.0}]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_token_holders(
        token_symbol="eETH",
        include_defi=True,
        exclude_identified_defi=True,
        execute_live=True,
        datasets=_protocol_holder_datasets(),
        freshness_registry={},
    )

    assert result["exclude_identified_defi"] is True
    assert result["summary"]["exclude_identified_defi"] is True
    assert result["summary"]["top_holders_preview"][0]["identified_defi_contract"] is None
    assert result["summary_queries"]["overview_sql"].count("identified_defi_contract IS NULL") >= 1


def test_get_protocol_events_summary_planning_mode_returns_sql():
    result = get_protocol_events(
        strategy_symbol="liquidETH",
        event_type="deposit",
        start_date="2026-03-01",
        end_date="2026-03-31",
        mode="summary",
        datasets={
            "dune.ether_fi.result_etherfi_protocol_events": {
                "name": "dune.ether_fi.result_etherfi_protocol_events",
                "display_name": "Ether.fi Protocol Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_events",
                "query_ready": True,
                "grain": "one row per protocol event",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert "strategy_symbol = 'liquidETH'" in result["suggested_sql"]
    assert "event_type = 'deposit'" in result["suggested_sql"]
    assert result["filter_preference_note"]


def test_get_protocol_events_rows_planning_mode_returns_sql():
    result = get_protocol_events(
        strategy_symbol="liquidUSD",
        mode="rows",
        limit=50,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_events": {
                "name": "dune.ether_fi.result_etherfi_protocol_events",
                "display_name": "Ether.fi Protocol Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_events",
                "query_ready": True,
                "grain": "one row per protocol event",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "rows"
    assert "ORDER BY block_time DESC NULLS LAST, evt_index DESC NULLS LAST" in result["suggested_sql"]
    assert "LIMIT 50" in result["suggested_sql"]


def test_get_protocol_events_validates_strategy_address():
    result = get_protocol_events(
        strategy_address="not-an-address",
        datasets={
            "dune.ether_fi.result_etherfi_protocol_events": {
                "name": "dune.ether_fi.result_etherfi_protocol_events",
                "display_name": "Ether.fi Protocol Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_events",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "Address must be" in result["error"]


def test_get_protocol_events_rejects_broad_rows_mode_request():
    result = get_protocol_events(
        mode="rows",
        start_date="2026-03-01",
        end_date="2026-03-31",
        limit=1000,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_events": {
                "name": "dune.ether_fi.result_etherfi_protocol_events",
                "display_name": "Ether.fi Protocol Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_events",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "Broad rows mode requests are expensive" in result["error"]


def test_get_protocol_events_summary_mode_uses_aggregate_queries(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        if "COUNT(*) AS event_count" in sql and "SUM(amount_usd) AS total_amount_usd" in sql:
            return [{
                "event_count": 5,
                "latest_block_time": "2026-03-31 23:00:00 UTC",
                "total_amount_usd": 1000.0,
                "total_amount_eth": 0.4,
                "single_token_symbol": "liquidETH",
                "total_token_amount": 100.0,
                "single_strategy_symbol": "liquidETH",
                "single_strategy_address": "0x111",
                "single_underlying_symbol": "ETH",
                "total_amount_underlying": 99.0,
                "total_strategy_amount": 100.0,
            }]
        if "GROUP BY 1" in sql and "event_type" in sql:
            return [{"event_type": "deposit", "event_count": 5, "total_amount_usd": 1000.0, "total_amount_eth": 0.4}]
        if "GROUP BY 1" in sql and "blockchain" in sql:
            return [{"blockchain": "ethereum", "event_count": 5, "total_amount_usd": 1000.0, "total_amount_eth": 0.4}]
        if "GROUP BY 1, 2" in sql:
            return [{"strategy_symbol": "liquidETH", "strategy_address": "0x111", "event_count": 5, "total_amount_usd": 1000.0, "total_amount_eth": 0.4}]
        if "SUM(token_amount) AS total_token_amount" in sql:
            return [{"token_symbol": "liquidETH", "event_count": 5, "total_token_amount": 100.0, "total_amount_usd": 1000.0}]
        if "SUM(amount_underlying) AS total_amount_underlying" in sql:
            return [{"amount_underlying_symbol": "ETH", "event_count": 5, "total_amount_underlying": 99.0, "total_amount_usd": 1000.0}]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_events(
        strategy_symbol="liquidETH",
        event_type="deposit",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_events": {
                "name": "dune.ether_fi.result_etherfi_protocol_events",
                "display_name": "Ether.fi Protocol Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_events",
                "query_ready": True,
                "grain": "one row per protocol event",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert result["rows"] == []
    assert result["summary"]["event_count"] == 5
    assert result["summary"]["total_amount_usd"] == 1000.0


def test_get_protocol_events_rows_mode_returns_row_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "block_time": "2026-03-15 10:00:00 UTC",
                "blockchain": "ethereum",
                "event_type": "deposit",
                "strategy_symbol": "liquidUSD",
                "strategy_address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "liquidUSD",
                "token_amount": 10.0,
                "strategy_amount": 10.0,
                "amount_underlying": 10.0,
                "amount_underlying_symbol": "USDT",
                "amount_usd": 10.0,
                "amount_eth": 0.01,
            },
            {
                "block_time": "2026-03-14 10:00:00 UTC",
                "blockchain": "ethereum",
                "event_type": "withdrawal_processed",
                "strategy_symbol": "liquidUSD",
                "strategy_address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "liquidUSD",
                "token_amount": 5.0,
                "strategy_amount": 5.0,
                "amount_underlying": 5.0,
                "amount_underlying_symbol": "USDT",
                "amount_usd": 5.0,
                "amount_eth": 0.005,
            },
        ],
    )

    result = get_protocol_events(
        strategy_symbol="liquidUSD",
        mode="rows",
        limit=50,
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_events": {
                "name": "dune.ether_fi.result_etherfi_protocol_events",
                "display_name": "Ether.fi Protocol Events",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_events",
                "query_ready": True,
                "grain": "one row per protocol event",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "rows"
    assert result["row_count"] == 2
    assert result["summary"]["event_count"] == 2
    assert result["summary"]["total_amount_usd"] == 15.0


def _protocol_events_dataset():
    return {
        "dune.ether_fi.result_etherfi_protocol_events": {
            "name": "dune.ether_fi.result_etherfi_protocol_events",
            "display_name": "Ether.fi Protocol Events",
            "description": "Dataset used by ether.fi overview analytics for protocol events",
            "table_name": "dune.ether_fi.result_etherfi_protocol_events",
            "query_ready": True,
            "grain": "one row per protocol event",
            "refresh_interval_minutes": 60,
        }
    }


def test_protocol_events_workflow_dataset_is_discoverable_from_natural_prompts():
    recent_results = search_datasets("recent protocol events")
    activity_results = search_datasets("ether.fi protocol activity")

    assert recent_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"
    assert activity_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"


def test_protocol_events_workflow_filter_guidance_prefers_strategy_filters():
    guidance_results = search_datasets("best filter for protocol events")
    comparison_results = search_datasets("strategy filter for protocol events")

    assert guidance_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"
    assert "dune.ether_fi.result_etherfi_protocol_events" in [
        result["name"] for result in comparison_results
    ]
    notes = " ".join(guidance_results[0]["query_notes"])
    comparison_notes = " ".join(
        next(
            result for result in comparison_results
            if result["name"] == "dune.ether_fi.result_etherfi_protocol_events"
        )["query_notes"]
    )
    caveats = " ".join(guidance_results[0]["caveats"])
    assert "strategy_symbol" in notes
    assert "strategy_symbol" in comparison_notes
    assert "project" in notes
    assert "prefer strategy filters" in caveats


def test_protocol_events_planner_defaults_latest_prompts_to_live_query():
    plan = plan_etherfi_query(
        "Show latest protocol deposit events for eETH.",
        freshness_registry={},
    )

    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"
    assert plan["data_access"]["selected_data_access"] == "live_query"
    assert plan["data_access"]["live_query"]["query_id"] == 6232670
    assert any(
        "currently defaults to the same materialized-view" in note
        for note in plan["data_access"]["data_access_notes"]
    )
    assert "event_type = 'deposit'" in plan["suggested_sql_skeleton"]


def test_protocol_events_planner_prefers_mat_view_for_historical_prompts():
    plan = plan_etherfi_query(
        "Show weekly protocol deposits over time for liquidETH.",
        freshness_registry={},
    )

    assert plan["recommended_datasets"][0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"
    assert plan["data_access"]["selected_data_access"] == "mat_view"
    assert any("baseline materialized view" in note for note in plan["data_access"]["data_access_notes"])
    assert "DATE_TRUNC('week', block_date)" in plan["suggested_sql_skeleton"]


def test_protocol_events_workflow_deposit_prompt_maps_to_summary_semantics(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        assert "event_type = 'deposit'" in sql
        assert "strategy_symbol = 'eETH'" in sql
        if "GROUP BY 1" in sql and "blockchain" in sql:
            return [{"blockchain": "ethereum", "event_count": 4, "total_amount_usd": 4000.0, "total_amount_eth": 1.6}]
        if "GROUP BY 1, 2" in sql:
            return [{"strategy_symbol": "eETH", "strategy_address": "0x1111111111111111111111111111111111111111", "event_count": 4, "total_amount_usd": 4000.0, "total_amount_eth": 1.6}]
        if "SUM(token_amount) AS total_token_amount" in sql:
            return [{"token_symbol": "eETH", "event_count": 4, "total_token_amount": 4.0, "total_amount_usd": 4000.0}]
        if "SUM(amount_underlying) AS total_amount_underlying" in sql:
            return [{"amount_underlying_symbol": "ETH", "event_count": 4, "total_amount_underlying": 4.0, "total_amount_usd": 4000.0}]
        if "COUNT(*) AS event_count" in sql and "SUM(amount_usd) AS total_amount_usd" in sql:
            return [{
                "event_count": 4,
                "latest_block_time": "2026-04-13 12:00:00 UTC",
                "total_amount_usd": 4000.0,
                "total_amount_eth": 1.6,
                "single_token_symbol": "eETH",
                "total_token_amount": 4.0,
                "single_strategy_symbol": "eETH",
                "single_strategy_address": "0x1111111111111111111111111111111111111111",
                "single_underlying_symbol": "ETH",
                "total_amount_underlying": 4.0,
                "total_strategy_amount": 4.0,
            }]
        raise AssertionError(sql)

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_events(
        strategy_symbol="eETH",
        event_type="deposit",
        execute_live=True,
        datasets=_protocol_events_dataset(),
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert result["rows"] == []
    assert result["summary"]["event_type"] == "deposit"
    assert result["summary"]["totals_by_strategy"][0]["strategy_symbol"] == "eETH"
    assert result["summary"]["totals_by_token_symbol"][0]["token_symbol"] == "eETH"


def test_protocol_events_workflow_withdrawal_semantics_are_discoverable_and_distinct():
    request_results = search_datasets("withdrawal requests")
    processed_results = search_datasets("withdrawal processed")
    difference_results = search_datasets("difference between withdrawal_request and withdrawal_processed")

    assert request_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"
    assert processed_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"
    assert difference_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"
    notes = " ".join(difference_results[0]["query_notes"])
    assert "withdrawal_request" in notes
    assert "withdrawal_processed" in notes


def test_protocol_events_workflow_summary_default_and_rows_newest_first():
    summary_result = get_protocol_events(
        strategy_symbol="liquidETH",
        datasets=_protocol_events_dataset(),
        freshness_registry={},
    )
    rows_result = get_protocol_events(
        strategy_symbol="liquidETH",
        mode="rows",
        limit=25,
        datasets=_protocol_events_dataset(),
        freshness_registry={},
    )

    assert summary_result["mode"] == "summary"
    assert "ORDER BY" not in summary_result["suggested_sql"]
    assert rows_result["mode"] == "rows"
    assert "ORDER BY block_time DESC NULLS LAST, evt_index DESC NULLS LAST" in rows_result["suggested_sql"]
    assert "LIMIT 25" in rows_result["suggested_sql"]


def test_protocol_events_workflow_strategy_address_filter_is_discoverable_and_usable(monkeypatch):
    strategy_address_results = search_datasets("strategy address protocol events")
    strategy_activity_results = search_datasets("show recent protocol activity for this strategy")

    assert strategy_address_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"
    assert strategy_activity_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_events"

    planning_result = get_protocol_events(
        strategy_address="0x1111111111111111111111111111111111111111",
        mode="summary",
        datasets=_protocol_events_dataset(),
        freshness_registry={},
    )

    assert "strategy_address = 0x1111111111111111111111111111111111111111" in planning_result["suggested_sql"]
    assert planning_result["filter_preference_note"]


def _protocol_tvl_dataset():
    return {
        "dune.ether_fi.result_etherfi_protocol_token_tvl": {
            "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
            "display_name": "Ether.fi Protocol Token TVL",
            "description": "Dataset used by the main ether.fi overview dashboard for protocol token TVL",
            "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
            "query_ready": True,
            "grain": "one row per day per strategy",
            "refresh_interval_minutes": 60,
        }
    }


def test_protocol_tvl_workflow_dataset_is_discoverable_from_natural_prompts():
    latest_results = search_datasets("latest protocol TVL")
    token_tvl_results = search_datasets("ether.fi token TVL")

    assert latest_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"
    assert token_tvl_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"


def test_protocol_tvl_workflow_filter_guidance_prefers_strategy_filters():
    best_filter_results = search_datasets("best filter for protocol TVL")
    comparison_results = search_datasets("should I use project or strategy_symbol?")

    assert best_filter_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"
    assert comparison_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"
    notes = " ".join(best_filter_results[0]["query_notes"])
    assert "strategy_symbol" in notes
    assert "strategy_address" in notes


def test_protocol_tvl_workflow_single_strategy_tvl_prompt_maps_to_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-13 00:00:00 UTC",
                "strategy_symbol": "eETH",
                "strategy_address": "0x1111111111111111111111111111111111111111",
                "strategy_blockchains": ["ethereum"],
                "underlying_asset_symbol": "ETH",
                "token_supply": 200.0,
                "token_supply_underlying": 198.0,
                "token_supply_usd": 500000.0,
                "token_supply_eth": 200.0,
                "token_supply_btc": 6.0,
                "token_supply_eigen": 1000.0,
                "token_supply_hype": 2000.0,
                "usd_rate": 2500.0,
                "eth_rate": 1.0,
                "btc_rate": 0.03,
                "eigen_rate": 5.0,
                "hype_rate": 10.0,
            }
        ],
    )

    result = get_protocol_token_tvl(
        strategy_symbol="eETH",
        execute_live=True,
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert result["rows"] == []
    assert result["summary"]["strategy_symbol"] == "eETH"
    assert result["summary"]["latest_day"] == "2026-04-13 00:00:00 UTC"
    assert result["summary"]["token_supply_usd"] == 500000.0


def test_protocol_tvl_workflow_multi_strategy_comparison_preserves_comparison_semantics(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-13 00:00:00 UTC",
                "strategy_symbol": "eETH",
                "strategy_address": "0x1111111111111111111111111111111111111111",
                "strategy_blockchains": ["ethereum"],
                "underlying_asset_symbol": "ETH",
                "token_supply": 200.0,
                "token_supply_underlying": 198.0,
                "token_supply_usd": 500000.0,
                "token_supply_eth": 200.0,
                "token_supply_btc": 6.0,
                "token_supply_eigen": 1000.0,
                "token_supply_hype": 2000.0,
                "usd_rate": 2500.0,
                "eth_rate": 1.0,
                "btc_rate": 0.03,
                "eigen_rate": 5.0,
                "hype_rate": 10.0,
            },
            {
                "day": "2026-04-12 00:00:00 UTC",
                "strategy_symbol": "liquidETH",
                "strategy_address": "0x2222222222222222222222222222222222222222",
                "strategy_blockchains": ["ethereum", "scroll"],
                "underlying_asset_symbol": "ETH",
                "token_supply": 100.0,
                "token_supply_underlying": 110.0,
                "token_supply_usd": 260000.0,
                "token_supply_eth": 110.0,
                "token_supply_btc": 3.3,
                "token_supply_eigen": 550.0,
                "token_supply_hype": 1100.0,
                "usd_rate": 2363.64,
                "eth_rate": 1.1,
                "btc_rate": 0.033,
                "eigen_rate": 5.5,
                "hype_rate": 11.0,
            },
            {
                "day": "2026-04-11 00:00:00 UTC",
                "strategy_symbol": "liquidUSD",
                "strategy_address": "0x3333333333333333333333333333333333333333",
                "strategy_blockchains": ["ethereum"],
                "underlying_asset_symbol": "USDT",
                "token_supply": 50.0,
                "token_supply_underlying": 50.0,
                "token_supply_usd": 50.0,
                "token_supply_eth": 0.02,
                "token_supply_btc": 0.001,
                "token_supply_eigen": 0.5,
                "token_supply_hype": 1.0,
                "usd_rate": 1.0,
                "eth_rate": 0.0004,
                "btc_rate": 0.00001,
                "eigen_rate": 0.01,
                "hype_rate": 0.02,
            },
        ],
    )

    result = get_protocol_token_tvl(
        strategy_symbols=["eETH", "liquidETH", "liquidUSD"],
        execute_live=True,
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )

    assert result["summary"]["strategy_symbols"] == ["eETH", "liquidETH", "liquidUSD"]
    assert result["summary"]["strategy_count"] == 3
    assert result["summary"]["underlying_asset_symbol"] is None
    assert result["summary"]["strategies"][0]["latest_day"] == "2026-04-13 00:00:00 UTC"
    assert result["summary"]["strategies"][1]["latest_day"] == "2026-04-12 00:00:00 UTC"
    assert result["summary"]["strategies"][2]["latest_day"] == "2026-04-11 00:00:00 UTC"


def test_protocol_tvl_workflow_backing_semantics_are_discoverable():
    backs_results = search_datasets("what backs eETH?")
    backing_amount_results = search_datasets("how much ETH backs liquidETH?")
    underlying_results = search_datasets("what is the underlying asset for liquidUSD?")

    assert backs_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"
    assert backing_amount_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"
    assert underlying_results[0]["name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"
    notes = " ".join(backs_results[0]["query_notes"])
    assert "token_supply_underlying" in notes
    assert "underlying_asset_symbol" in notes


def test_protocol_tvl_workflow_summary_default_and_rows_are_inspection_oriented():
    summary_result = get_protocol_token_tvl(
        strategy_symbol="eETH",
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )
    rows_result = get_protocol_token_tvl(
        strategy_symbol="eETH",
        mode="rows",
        limit=25,
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )

    assert summary_result["mode"] == "summary"
    assert "ORDER BY day DESC" not in summary_result["suggested_sql"]
    assert rows_result["mode"] == "rows"
    assert "ORDER BY day DESC NULLS LAST, strategy_symbol ASC, strategy_address ASC" in rows_result["suggested_sql"]
    assert "LIMIT 25" in rows_result["suggested_sql"]


def test_get_protocol_token_tvl_summary_planning_mode_returns_sql():
    result = get_protocol_token_tvl(
        strategy_symbol="liquidETH",
        mode="summary",
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
                "grain": "one row per day per strategy",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert "strategy_symbol = 'liquidETH'" in result["suggested_sql"]
    assert "SELECT MAX(day) FROM dune.ether_fi.result_etherfi_protocol_token_tvl" in result["suggested_sql"]
    assert result["backing_asset_note"]


def test_get_protocol_token_tvl_summary_planning_mode_supports_multi_strategy_sql():
    result = get_protocol_token_tvl(
        strategy_symbols=["eETH", "liquidETH"],
        mode="summary",
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
                "grain": "one row per day per strategy",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert "strategy_symbol IN ('eETH', 'liquidETH')" in result["suggested_sql"]
    assert "SELECT strategy_symbol, MAX(day) AS latest_day" in result["suggested_sql"]
    assert result["strategy_symbols"] == ["eETH", "liquidETH"]


def test_get_protocol_token_tvl_summary_planning_mode_with_date_uses_requested_day():
    result = get_protocol_token_tvl(
        strategy_symbol="eBTC",
        as_of_date="2026-04-01",
        mode="summary",
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "CAST(day AS DATE) = CAST('2026-04-01' AS DATE)" in result["suggested_sql"]
    assert "SELECT MAX(day)" not in result["suggested_sql"]


def test_get_protocol_token_tvl_rows_planning_mode_returns_sql():
    result = get_protocol_token_tvl(
        strategy_symbol="liquidUSD",
        mode="rows",
        limit=50,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "rows"
    assert "ORDER BY day DESC NULLS LAST, strategy_symbol ASC, strategy_address ASC" in result["suggested_sql"]
    assert "LIMIT 50" in result["suggested_sql"]


def test_get_protocol_token_tvl_requires_strategy_filter():
    result = get_protocol_token_tvl(
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "Provide strategy_symbol, strategy_symbols, or strategy_address" in result["error"]


def test_get_protocol_token_tvl_rejects_conflicting_strategy_symbol_inputs():
    result = get_protocol_token_tvl(
        strategy_symbol="eETH",
        strategy_symbols=["liquidETH"],
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "Provide either strategy_symbol or strategy_symbols" in result["error"]


def test_get_protocol_token_tvl_validates_strategy_address():
    result = get_protocol_token_tvl(
        strategy_address="not-an-address",
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "Address must be" in result["error"]


def test_get_protocol_token_tvl_rows_mode_rejects_broad_high_limit_requests():
    result = get_protocol_token_tvl(
        strategy_symbol="eETH",
        mode="rows",
        limit=501,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "Rows mode across many days can be expensive" in result["error"]


def test_get_protocol_token_tvl_execute_live_summary_returns_grouped_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-08 00:00:00 UTC",
                "strategy_symbol": "liquidETH",
                "strategy_address": "0x1111111111111111111111111111111111111111",
                "strategy_blockchains": ["ethereum"],
                "underlying_asset_symbol": "ETH",
                "token_supply": 100.0,
                "token_supply_underlying": 99.5,
                "token_supply_usd": 250000.0,
                "token_supply_eth": 100.0,
                "token_supply_btc": 3.0,
                "token_supply_eigen": 500.0,
                "token_supply_hype": 1000.0,
                "usd_rate": 2500.0,
                "eth_rate": 1.0,
                "btc_rate": 0.03,
                "eigen_rate": 5.0,
                "hype_rate": 10.0,
            }
        ],
    )

    result = get_protocol_token_tvl(
        strategy_symbol="liquidETH",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
                "grain": "one row per day per strategy",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert result["rows"] == []
    assert result["summary"]["latest_day"] == "2026-04-08 00:00:00 UTC"
    assert result["summary"]["underlying_asset_symbol"] == "ETH"
    assert result["summary"]["token_supply_usd"] == 250000.0
    assert result["summary"]["strategy_count"] == 1


def test_get_protocol_token_tvl_execute_live_summary_supports_multi_strategy(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-08 00:00:00 UTC",
                "strategy_symbol": "eETH",
                "strategy_address": "0x1111111111111111111111111111111111111111",
                "strategy_blockchains": ["ethereum"],
                "underlying_asset_symbol": "WETH",
                "token_supply": 200.0,
                "token_supply_underlying": 200.0,
                "token_supply_usd": 500000.0,
                "token_supply_eth": 200.0,
                "token_supply_btc": 6.0,
                "token_supply_eigen": 1000.0,
                "token_supply_hype": 2000.0,
                "usd_rate": 2500.0,
                "eth_rate": 1.0,
                "btc_rate": 0.03,
                "eigen_rate": 5.0,
                "hype_rate": 10.0,
            },
            {
                "day": "2026-04-07 00:00:00 UTC",
                "strategy_symbol": "liquidETH",
                "strategy_address": "0x2222222222222222222222222222222222222222",
                "strategy_blockchains": ["ethereum", "scroll"],
                "underlying_asset_symbol": "WETH",
                "token_supply": 100.0,
                "token_supply_underlying": 110.0,
                "token_supply_usd": 260000.0,
                "token_supply_eth": 110.0,
                "token_supply_btc": 3.3,
                "token_supply_eigen": 550.0,
                "token_supply_hype": 1100.0,
                "usd_rate": 2363.64,
                "eth_rate": 1.1,
                "btc_rate": 0.033,
                "eigen_rate": 5.5,
                "hype_rate": 11.0,
            },
        ],
    )

    result = get_protocol_token_tvl(
        strategy_symbols=["eETH", "liquidETH"],
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
                "grain": "one row per day per strategy",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "summary"
    assert result["summary"]["strategy_symbols"] == ["eETH", "liquidETH"]
    assert result["summary"]["strategy_count"] == 2
    assert result["summary"]["underlying_asset_symbol"] is None
    assert result["summary"]["token_supply_usd"] == 760000.0
    assert result["summary"]["strategies"][0]["latest_day"] == "2026-04-08 00:00:00 UTC"
    assert result["summary"]["strategies"][1]["latest_day"] == "2026-04-07 00:00:00 UTC"


def test_get_protocol_token_tvl_rows_mode_returns_row_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-08 00:00:00 UTC",
                "strategy_symbol": "liquidUSD",
                "strategy_address": "0x1111111111111111111111111111111111111111",
                "strategy_blockchains": ["ethereum"],
                "underlying_asset_symbol": "USDT",
                "token_supply": 100.0,
                "token_supply_underlying": 100.0,
                "token_supply_usd": 100.0,
                "token_supply_eth": 0.04,
                "token_supply_btc": 0.001,
                "token_supply_eigen": 1.0,
                "token_supply_hype": 2.0,
                "usd_rate": 1.0,
                "eth_rate": 0.0004,
                "btc_rate": 0.00001,
                "eigen_rate": 0.01,
                "hype_rate": 0.02,
            },
            {
                "day": "2026-04-07 00:00:00 UTC",
                "strategy_symbol": "liquidUSD",
                "strategy_address": "0x1111111111111111111111111111111111111111",
                "strategy_blockchains": ["ethereum"],
                "underlying_asset_symbol": "USDT",
                "token_supply": 90.0,
                "token_supply_underlying": 90.0,
                "token_supply_usd": 90.0,
                "token_supply_eth": 0.036,
                "token_supply_btc": 0.0009,
                "token_supply_eigen": 0.9,
                "token_supply_hype": 1.8,
                "usd_rate": 1.0,
                "eth_rate": 0.0004,
                "btc_rate": 0.00001,
                "eigen_rate": 0.01,
                "hype_rate": 0.02,
            },
        ],
    )

    result = get_protocol_token_tvl(
        strategy_symbol="liquidUSD",
        mode="rows",
        limit=50,
        execute_live=True,
        datasets={
            "dune.ether_fi.result_etherfi_protocol_token_tvl": {
                "name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "display_name": "Ether.fi Protocol Token TVL",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
                "query_ready": True,
                "grain": "one row per day per strategy",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["mode"] == "rows"
    assert result["row_count"] == 2
    assert result["summary"]["row_count"] == 2
    assert result["summary"]["token_supply_usd"] == 190.0
    assert result["summary"]["underlying_asset_symbol"] == "USDT"


def test_get_protocol_token_tvl_timeseries_returns_period_planning_response():
    result = get_protocol_token_tvl_timeseries(
        period="last_1_year",
        strategy_symbols=["liquideth", "liquidusd", "liquidbtc", "ebtc", "eeth"],
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert result["dataset_name"] == "dune.ether_fi.result_etherfi_protocol_token_tvl"
    assert result["start_date"] == "2025-04-23"
    assert result["end_date"] == "2026-04-22"
    assert result["granularity"] == "day"
    assert result["strategy_symbols"] == ["liquidETH", "liquidUSD", "liquidBTC", "eBTC", "eETH"]
    assert result["question_class"] == "time-series summary"
    assert "different question class" in result["why_chosen"]
    assert "one aggregate Dune query" in result["wrong_alternative_note"]
    assert "GROUP BY 1, 2" in result["suggested_sql"]
    assert "SUM(token_supply_usd) AS tvl_usd" in result["suggested_sql"]
    assert result["timeseries"] == []


def test_get_protocol_token_tvl_timeseries_returns_monthly_planning_response():
    result = get_protocol_token_tvl_timeseries(
        period="last_1_year",
        strategy_symbols=["liquidusd", "ebtc"],
        granularity="month",
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert result["granularity"] == "month"
    assert result["strategy_symbols"] == ["liquidUSD", "eBTC"]
    assert "DATE_TRUNC('month', day)" in result["suggested_sql"]
    assert "MAX(day) AS month_end_day" in result["suggested_sql"]
    assert result["expected_output_fields"] == ["month", "strategy_symbol", "month_end_day", "tvl_usd"]
    assert "latest available daily snapshot in each calendar month" in result["monthly_snapshot_rule"]


def test_get_protocol_token_tvl_timeseries_validates_ranges_and_filters():
    missing_range = get_protocol_token_tvl_timeseries(
        strategy_symbol="eETH",
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )
    bad_granularity = get_protocol_token_tvl_timeseries(
        strategy_symbol="eETH",
        period="last_30_days",
        granularity="week",
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )
    conflicting_symbols = get_protocol_token_tvl_timeseries(
        strategy_symbol="eETH",
        strategy_symbols=["liquidETH"],
        period="last_30_days",
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )
    conflicting_address = get_protocol_token_tvl_timeseries(
        strategy_symbol="eETH",
        strategy_address="0x1111111111111111111111111111111111111111",
        period="last_30_days",
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )
    bad_date_range = get_protocol_token_tvl_timeseries(
        strategy_symbol="eETH",
        start_date="2026-04-22",
        end_date="2026-04-01",
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )

    assert "Provide either start_date + end_date or a supported period." in missing_range["error"]
    assert "granularity must be 'day' or 'month'." in bad_granularity["error"]
    assert "Provide either strategy_symbol or strategy_symbols" in conflicting_symbols["error"]
    assert "Provide either strategy_address or strategy_symbol/strategy_symbols" in conflicting_address["error"]
    assert "start_date must be on or before end_date." in bad_date_range["error"]


def test_get_protocol_token_tvl_timeseries_live_execution_returns_chart_friendly_series(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured = {"calls": 0, "sql": None}

    def fake_execute(sql):
        captured["calls"] += 1
        captured["sql"] = sql
        return [
            {"day": "2026-04-20", "strategy_symbol": "eETH", "tvl_usd": 5000000.0},
            {"day": "2026-04-20", "strategy_symbol": "liquidETH", "tvl_usd": 250000.0},
            {"day": "2026-04-21", "strategy_symbol": "eETH", "tvl_usd": 5100000.0},
            {"day": "2026-04-21", "strategy_symbol": "liquidETH", "tvl_usd": 255000.0},
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_token_tvl_timeseries(
        start_date="2026-04-20",
        end_date="2026-04-21",
        strategy_symbols=["eeth", "liquideth"],
        execute_live=True,
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
    )

    assert captured["calls"] == 1
    assert "CAST(day AS DATE) BETWEEN CAST('2026-04-20' AS DATE) AND CAST('2026-04-21' AS DATE)" in captured["sql"]
    assert "strategy_symbol IN ('eETH', 'liquidETH')" in captured["sql"]
    assert "GROUP BY 1, 2" in captured["sql"]
    assert result["executed_live"] is True
    assert result["row_count"] == 4
    assert result["rows"] == result["timeseries"]
    assert result["summary"]["day_count"] == 2
    assert result["summary"]["strategy_count"] == 2
    assert result["summary"]["latest_day"] == "2026-04-21"
    assert result["summary"]["latest_tvl_usd_total"] == 5355000.0
    assert result["summary"]["latest_tvl_usd_by_symbol"][0]["strategy_symbol"] == "eETH"


def test_get_protocol_token_tvl_timeseries_live_execution_returns_month_end_series(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured = {"calls": 0, "sql": None}

    def fake_execute(sql):
        captured["calls"] += 1
        captured["sql"] = sql
        return [
            {
                "month": "2026-03-01",
                "month_end_day": "2026-03-31",
                "strategy_symbol": "eETH",
                "tvl_usd": 6174184759.285492,
            },
            {
                "month": "2026-03-01",
                "month_end_day": "2026-03-31",
                "strategy_symbol": "liquidETH",
                "tvl_usd": 390752666.0419608,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-22",
                "strategy_symbol": "eETH",
                "tvl_usd": 6501298417.298669,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-22",
                "strategy_symbol": "liquidETH",
                "tvl_usd": 426430968.8708626,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_token_tvl_timeseries(
        period="last_90_days",
        strategy_symbols=["eeth", "liquideth"],
        granularity="month",
        execute_live=True,
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert captured["calls"] == 1
    assert "DATE_TRUNC('month', day)" in captured["sql"]
    assert "MAX(day) AS month_end_day" in captured["sql"]
    assert "month_end_days.month AS month" in captured["sql"]
    assert result["executed_live"] is True
    assert result["row_count"] == 4
    assert result["rows"] == result["timeseries"]
    assert result["timeseries"][0]["month"] == "2026-03-01"
    assert result["timeseries"][0]["month_end_day"] == "2026-03-31"
    assert result["summary"]["month_count"] == 2
    assert result["summary"]["latest_month"] == "2026-04-01"
    assert result["summary"]["latest_day"] == "2026-04-22"
    assert result["summary"]["latest_tvl_usd_total"] == pytest.approx(6927729386.169531)
    assert result["summary"]["latest_tvl_usd_by_symbol"][0]["strategy_symbol"] == "eETH"


def test_get_protocol_token_tvl_timeseries_empty_result_behavior(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", lambda sql: [])

    result = get_protocol_token_tvl_timeseries(
        period="last_90_days",
        strategy_symbol="liquidETH",
        execute_live=True,
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert result["row_count"] == 0
    assert result["timeseries"] == []
    assert result["summary"]["day_count"] == 0
    assert "No protocol token TVL rows matched" in result["warning"]


def test_get_protocol_token_tvl_timeseries_prompt_equivalent_last_year_multi_token_chart(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured_sql = {}

    def fake_execute(sql):
        captured_sql["sql"] = sql
        return [
            {"day": "2025-04-23", "strategy_symbol": "eETH", "tvl_usd": 4000000000.0},
            {"day": "2025-04-23", "strategy_symbol": "liquidETH", "tvl_usd": 300000000.0},
            {"day": "2025-04-23", "strategy_symbol": "liquidUSD", "tvl_usd": 30000000.0},
            {"day": "2025-04-23", "strategy_symbol": "eBTC", "tvl_usd": 500000000.0},
            {"day": "2025-04-23", "strategy_symbol": "liquidBTC", "tvl_usd": 60000000.0},
            {"day": "2026-04-22", "strategy_symbol": "eETH", "tvl_usd": 6500000000.0},
            {"day": "2026-04-22", "strategy_symbol": "liquidETH", "tvl_usd": 426000000.0},
            {"day": "2026-04-22", "strategy_symbol": "liquidUSD", "tvl_usd": 100000000.0},
            {"day": "2026-04-22", "strategy_symbol": "eBTC", "tvl_usd": 84000000.0},
            {"day": "2026-04-22", "strategy_symbol": "liquidBTC", "tvl_usd": 17000000.0},
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_token_tvl_timeseries(
        period="last_1_year",
        strategy_symbols=["liquideth", "liquidusd", "liquidbtc", "ebtc", "eeth"],
        execute_live=True,
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert "strategy_symbol IN ('liquidETH', 'liquidUSD', 'liquidBTC', 'eBTC', 'eETH')" in captured_sql["sql"]
    assert result["summary"]["strategy_symbols"] == ["liquidETH", "liquidUSD", "liquidBTC", "eBTC", "eETH"]
    assert result["summary"]["latest_day"] == "2026-04-22"
    assert result["summary"]["latest_tvl_usd_by_symbol"][0] == {
        "strategy_symbol": "eETH",
        "tvl_usd": 6500000000.0,
    }


def test_get_protocol_token_tvl_timeseries_prompt_equivalent_month_over_month_bar_chart(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    captured_sql = {}

    def fake_execute(sql):
        captured_sql["sql"] = sql
        return [
            {
                "month": "2026-03-01",
                "month_end_day": "2026-03-31",
                "strategy_symbol": "liquidUSD",
                "tvl_usd": 137043344.09579223,
            },
            {
                "month": "2026-03-01",
                "month_end_day": "2026-03-31",
                "strategy_symbol": "eBTC",
                "tvl_usd": 71850744.44978067,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-22",
                "strategy_symbol": "liquidUSD",
                "tvl_usd": 100405571.49493246,
            },
            {
                "month": "2026-04-01",
                "month_end_day": "2026-04-22",
                "strategy_symbol": "eBTC",
                "tvl_usd": 84280020.39234395,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_protocol_token_tvl_timeseries(
        period="last_1_year",
        strategy_symbols=["liquidusd", "ebtc"],
        granularity="month",
        execute_live=True,
        datasets=_protocol_tvl_dataset(),
        freshness_registry={},
        now=datetime(2026, 4, 22),
    )

    assert "strategy_symbol IN ('liquidUSD', 'eBTC')" in captured_sql["sql"]
    assert "month_end_day" in captured_sql["sql"]
    assert result["summary"]["strategy_symbols"] == ["liquidUSD", "eBTC"]
    assert result["summary"]["month_count"] == 2
    assert result["summary"]["latest_month"] == "2026-04-01"
    assert result["timeseries"][0] == {
        "month": "2026-03-01",
        "month_end_day": "2026-03-31",
        "strategy_symbol": "liquidUSD",
        "tvl_usd": 137043344.09579223,
    }


def test_get_token_price_minute_planning_mode_returns_semantic_sql():
    result = get_token_price(
        token_address="0x1111111111111111111111111111111111111111",
        blockchain="base",
        as_of_timestamp="2026-04-12T10:30:00Z",
        granularity="minute",
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_minute": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "display_name": "Tokens Prices Enriched (Minute)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "query_ready": True,
                "grain": "one row per token, blockchain, and minute",
                "refresh_interval_minutes": 120,
            }
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_tokens_prices_enriched_minute"
    assert result["granularity"] == "minute"
    assert "token_address = 0x1111111111111111111111111111111111111111" in result["suggested_sql"]
    assert "blockchain = 'base'" in result["suggested_sql"]
    assert "minute <= CAST('2026-04-12 10:30:00+00:00' AS timestamp)" in result["suggested_sql"]
    assert "COALESCE(token_usd, token_usd_rate) AS effective_price_usd" in result["suggested_sql"]
    assert "price_source" in result["expected_output_fields"]
    assert any("incomplete by design" in caveat for caveat in result["caveats"])
    assert result["summary"]["effective_price_usd"] is None


def test_get_token_price_daily_planning_mode_uses_daily_enriched_dataset():
    result = get_token_price(
        token_address="0x1111111111111111111111111111111111111111",
        granularity="daily",
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_daily": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "display_name": "Tokens Prices Enriched (Daily)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "query_ready": True,
                "grain": "one row per token, blockchain, and day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_tokens_prices_enriched_daily"
    assert result["granularity"] == "daily"
    assert "FROM dune.ether_fi.result_tokens_prices_enriched_daily" in result["suggested_sql"]
    assert "ORDER BY day DESC NULLS LAST" in result["suggested_sql"]
    assert "safer default" in result["why_chosen"]


def test_get_token_price_execute_live_returns_effective_price_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-12 00:00:00 UTC",
                "blockchain": "base",
                "token_address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "weETH",
                "token_usd": None,
                "token_usd_rate": 2500.0,
                "effective_price_usd": 2500.0,
                "price_source": "enriched_fallback",
                "token_underlying_rate": 1.02,
                "token_underlying_symbol": "ETH",
                "token_weth_rate": 1.02,
                "last_updated": "2026-04-12 01:00:00 UTC",
            }
        ],
    )

    result = get_token_price(
        token_address="0x1111111111111111111111111111111111111111",
        blockchain="base",
        granularity="daily",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_daily": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "display_name": "Tokens Prices Enriched (Daily)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "query_ready": True,
                "grain": "one row per token, blockchain, and day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 1
    assert result["summary"]["effective_price_usd"] == 2500.0
    assert result["summary"]["price_source"] == "enriched_fallback"
    assert result["summary"]["token_underlying_rate"] == 1.02
    assert result["summary"]["token_underlying_symbol"] == "ETH"


def test_get_token_price_minute_live_zero_rows_suggests_daily_and_token_list(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", lambda sql: [])

    result = get_token_price(
        token_address="0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_minute": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "display_name": "Tokens Prices Enriched (Minute)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "query_ready": True,
                "grain": "one row per token, blockchain, and minute",
                "refresh_interval_minutes": 120,
            }
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 0
    assert "granularity='daily'" in result["warning"]
    assert "result_tokens_prices_tokens_list" in result["summary"]["missing_result_note"]


def test_get_token_price_validates_inputs():
    missing_address = get_token_price(
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_minute": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "display_name": "Tokens Prices Enriched (Minute)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )
    invalid_granularity = get_token_price(
        token_address="0x1111111111111111111111111111111111111111",
        granularity="hourly",
        datasets={},
        freshness_registry={},
    )
    invalid_timestamp = get_token_price(
        token_address="0x1111111111111111111111111111111111111111",
        as_of_timestamp="yesterday",
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_minute": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "display_name": "Tokens Prices Enriched (Minute)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert missing_address["error"] == "Provide token_address."
    assert "granularity must be" in invalid_granularity["error"]
    assert "as_of_timestamp must be" in invalid_timestamp["error"]


def test_get_token_prices_batch_daily_planning_mode_returns_narrow_sql():
    result = get_token_prices_batch(
        token_addresses=[
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
        ],
        blockchain="base",
        as_of_timestamp="2026-04-12",
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_daily": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "display_name": "Tokens Prices Enriched (Daily)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "query_ready": True,
                "grain": "one row per token, blockchain, and day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_tokens_prices_enriched_daily"
    assert result["granularity"] == "daily"
    assert "token_address IN (0x1111111111111111111111111111111111111111, 0x2222222222222222222222222222222222222222)" in result["suggested_sql"]
    assert "blockchain = 'base'" in result["suggested_sql"]
    assert "day <= CAST('2026-04-12' AS timestamp)" in result["suggested_sql"]
    assert "COALESCE(token_usd, token_usd_rate) AS effective_price_usd" in result["suggested_sql"]
    assert "price_source" in result["expected_output_fields"]
    assert result["summary"]["requested_token_count"] == 2


def test_get_token_prices_batch_execute_live_returns_partial_coverage_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-12 00:00:00 UTC",
                "blockchain": "base",
                "token_address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "weETH",
                "token_usd": None,
                "token_usd_rate": 2500.0,
                "effective_price_usd": 2500.0,
                "price_source": "enriched_fallback",
                "token_underlying_rate": 1.02,
                "token_underlying_symbol": "ETH",
                "token_weth_rate": 1.02,
                "last_updated": "2026-04-12 01:00:00 UTC",
            }
        ],
    )

    result = get_token_prices_batch(
        token_addresses=[
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
        ],
        execute_live=True,
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_daily": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "display_name": "Tokens Prices Enriched (Daily)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "query_ready": True,
                "grain": "one row per token, blockchain, and day",
                "refresh_interval_minutes": 60,
            }
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 1
    assert result["summary"]["requested_token_count"] == 2
    assert result["summary"]["matched_token_count"] == 1
    assert result["summary"]["missing_token_count"] == 1
    assert result["summary"]["missing_tokens"] == ["0x2222222222222222222222222222222222222222"]
    assert result["summary"]["price_source_breakdown"] == {"enriched_fallback": 1}
    assert "result_tokens_prices_tokens_list" in result["summary"]["missing_result_note"]


def test_get_token_prices_batch_minute_planning_mode_includes_completeness_caveat():
    result = get_token_prices_batch(
        token_addresses=["0x1111111111111111111111111111111111111111"],
        granularity="minute",
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_minute": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "display_name": "Tokens Prices Enriched (Minute)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_minute",
                "query_ready": True,
                "grain": "one row per token, blockchain, and minute",
                "refresh_interval_minutes": 120,
            }
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_tokens_prices_enriched_minute"
    assert any("incomplete by design" in caveat for caveat in result["caveats"])
    assert "ROW_NUMBER() OVER" in result["suggested_sql"]


def test_get_token_prices_batch_validates_inputs():
    empty_addresses = get_token_prices_batch(
        token_addresses=[],
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_daily": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "display_name": "Tokens Prices Enriched (Daily)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )
    invalid_address = get_token_prices_batch(
        token_addresses=["not-an-address"],
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_daily": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "display_name": "Tokens Prices Enriched (Daily)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )
    invalid_granularity = get_token_prices_batch(
        token_addresses=["0x1111111111111111111111111111111111111111"],
        granularity="hourly",
        datasets={},
        freshness_registry={},
    )
    too_many_addresses = get_token_prices_batch(
        token_addresses=[
            f"0x{index:040x}"
            for index in range(51)
        ],
        datasets={
            "dune.ether_fi.result_tokens_prices_enriched_daily": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "display_name": "Tokens Prices Enriched (Daily)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "query_ready": True,
            }
        },
        freshness_registry={},
    )

    assert "non-empty list" in empty_addresses["error"]
    assert "Address must be" in invalid_address["error"]
    assert "granularity must be" in invalid_granularity["error"]
    assert "cannot contain more than 50" in too_many_addresses["error"]


def _price_coverage_test_datasets():
    return {
        "dune.ether_fi.result_tokens_prices_tokens_list": {
            "name": "dune.ether_fi.result_tokens_prices_tokens_list",
            "display_name": "Tokens Prices Token List",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
            "query_ready": True,
        },
        "dune.ether_fi.result_tokens_traits": {
            "name": "dune.ether_fi.result_tokens_traits",
            "display_name": "Tokens Traits",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_tokens_traits",
            "query_ready": True,
        },
        "dune.ether_fi.result_tokens_prices_usd": {
            "name": "dune.ether_fi.result_tokens_prices_usd",
            "display_name": "Tokens Prices USD (Minute)",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_tokens_prices_usd",
            "query_ready": True,
        },
        "dune.ether_fi.result_tokens_prices_usd_daily": {
            "name": "dune.ether_fi.result_tokens_prices_usd_daily",
            "display_name": "Tokens Prices USD (Daily)",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_tokens_prices_usd_daily",
            "query_ready": True,
        },
        "dune.ether_fi.result_tokens_prices_enriched_minute": {
            "name": "dune.ether_fi.result_tokens_prices_enriched_minute",
            "display_name": "Tokens Prices Enriched (Minute)",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_tokens_prices_enriched_minute",
            "query_ready": True,
        },
        "dune.ether_fi.result_tokens_prices_enriched_daily": {
            "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
            "display_name": "Tokens Prices Enriched (Daily)",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
            "query_ready": True,
        },
        "dune.ether_fi.result_tokens_rates_oracle_pegs": {
            "name": "dune.ether_fi.result_tokens_rates_oracle_pegs",
            "display_name": "Tokens Exchange Rates",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_tokens_rates_oracle_pegs",
            "query_ready": True,
        },
        "dune.ether_fi.result_tokens_exchange_rates_daily": {
            "name": "dune.ether_fi.result_tokens_exchange_rates_daily",
            "display_name": "Tokens Exchange Rates (Daily)",
            "description": "Example dataset",
            "table_name": "dune.ether_fi.result_tokens_exchange_rates_daily",
            "query_ready": True,
        },
    }


def test_diagnose_token_price_coverage_planning_mode_returns_checks_sql():
    result = diagnose_token_price_coverage(
        token_address="0x1111111111111111111111111111111111111111",
        blockchain="base",
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["query_ready"] is True
    assert len(result["datasets_checked"]) == 8
    assert "price_token_universe AS" in result["suggested_sql"]
    assert "raw_usd_minute AS" in result["suggested_sql"]
    assert "exchange_rates_raw AS" in result["suggested_sql"]
    assert "token_blockchain = 'base'" in result["suggested_sql"]
    assert "checks" in result["expected_output_fields"]
    assert any("incomplete by design" in caveat for caveat in result["caveats"])
    assert "not a USD price table" in result["check_meanings"]["has_exchange_rates_raw"]


def test_diagnose_token_price_coverage_live_explains_daily_fallback(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "in_price_token_universe": True,
                "in_tokens_traits": True,
                "has_raw_usd_minute": True,
                "has_raw_usd_daily": True,
                "has_enriched_minute": False,
                "has_enriched_daily": True,
                "has_exchange_rates_raw": False,
                "has_exchange_rates_daily": False,
                "enriched_daily_latest_observed_timestamp": "2026-04-12 00:00:00 UTC",
            }
        ],
    )

    result = diagnose_token_price_coverage(
        token_address="0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["checks"]["has_enriched_daily"] is True
    assert result["checks"]["has_enriched_minute"] is False
    assert result["summary"]["minute_enriched_missing_but_daily_exists"] is True
    assert "minute table is incomplete by design" in result["likely_explanation"]
    assert any("Use daily granularity" in step for step in result["suggested_next_steps"])
    assert result["latest_observed_timestamps"]["enriched_daily"] == "2026-04-12 00:00:00 UTC"


def test_diagnose_token_price_coverage_live_explains_missing_universe(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "in_price_token_universe": False,
                "in_tokens_traits": False,
                "has_raw_usd_minute": False,
                "has_raw_usd_daily": False,
                "has_enriched_minute": False,
                "has_enriched_daily": False,
                "has_exchange_rates_raw": False,
                "has_exchange_rates_daily": False,
            }
        ],
    )

    result = diagnose_token_price_coverage(
        token_address="0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["summary"]["in_price_token_universe"] is False
    assert "may not yet be included" in result["likely_explanation"]
    assert any("result_tokens_prices_tokens_list" in step for step in result["suggested_next_steps"])


def test_diagnose_token_price_coverage_live_explains_exchange_rates_without_usd(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "in_price_token_universe": True,
                "in_tokens_traits": True,
                "has_raw_usd_minute": False,
                "has_raw_usd_daily": False,
                "has_enriched_minute": False,
                "has_enriched_daily": False,
                "has_exchange_rates_raw": True,
                "has_exchange_rates_daily": True,
            }
        ],
    )

    result = diagnose_token_price_coverage(
        token_address="0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["summary"]["has_any_exchange_rate"] is True
    assert result["summary"]["has_any_raw_usd_price"] is False
    assert "Exchange-rate coverage exists" in result["likely_explanation"]
    assert any("not a USD price table" in step for step in result["suggested_next_steps"])


def test_diagnose_token_price_coverage_validates_inputs():
    missing_address = diagnose_token_price_coverage(
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )
    invalid_address = diagnose_token_price_coverage(
        token_address="not-an-address",
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )
    invalid_blockchain = diagnose_token_price_coverage(
        token_address="0x1111111111111111111111111111111111111111",
        blockchain="base;drop",
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert missing_address["error"] == "Provide token_address."
    assert "Address must be" in invalid_address["error"]
    assert "blockchain must contain" in invalid_blockchain["error"]


def test_price_workflow_unique_symbol_resolution_to_price(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        if "WITH token_candidates" in sql:
            return [
                {
                    "token_address": "0x1111111111111111111111111111111111111111",
                    "blockchain": "bnb",
                    "token_symbol": "weETH",
                    "token_project": "ether.fi",
                    "token_type": "lrt",
                    "in_price_token_universe": True,
                }
            ]
        return [
            {
                "day": "2026-04-12 00:00:00 UTC",
                "blockchain": "bnb",
                "token_address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "weETH",
                "token_usd": None,
                "token_usd_rate": 2500.0,
                "effective_price_usd": 2500.0,
                "price_source": "enriched_fallback",
                "token_underlying_rate": 1.02,
                "token_underlying_symbol": "ETH",
                "token_weth_rate": 1.02,
            }
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_token_price_by_symbol(
        token_symbol="weETH",
        blockchain="bnb",
        granularity="daily",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["outcome"] == "resolved_and_priced"
    assert result["resolved_token"]["blockchain"] == "bnb"
    assert result["price_summary"]["effective_price_usd"] == 2500.0
    assert result["price_summary"]["price_source"] == "enriched_fallback"


def test_price_workflow_ambiguous_symbol_returns_candidates_without_guessing(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    executed_sql: list[str] = []

    def fake_execute(sql):
        executed_sql.append(sql)
        return [
            {
                "token_address": "0x1111111111111111111111111111111111111111",
                "blockchain": "ethereum",
                "token_symbol": "weETH",
                "token_project": "ether.fi",
                "token_type": "lrt",
                "in_price_token_universe": True,
            },
            {
                "token_address": "0x2222222222222222222222222222222222222222",
                "blockchain": "bnb",
                "token_symbol": "weETH",
                "token_project": "ether.fi",
                "token_type": "lrt",
                "in_price_token_universe": True,
            },
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_token_price_by_symbol(
        token_symbol="weETH",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["outcome"] == "needs_disambiguation"
    assert len(result["candidates"]) == 2
    assert any(candidate["blockchain"] == "bnb" for candidate in result["candidates"])
    assert all("result_tokens_prices_enriched" not in sql for sql in executed_sql)


def test_price_workflow_no_match_returns_suggestions(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", lambda sql: [])

    result = get_token_price_by_symbol(
        token_symbol="NOT_A_TOKEN",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["outcome"] == "no_match"
    assert result["candidates"] == []
    assert "Try a different token_symbol spelling." in result["summary"]["suggestions"]


def test_price_workflow_batch_partial_coverage_does_not_fail(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "day": "2026-04-12 00:00:00 UTC",
                "blockchain": "ethereum",
                "token_address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "weETH",
                "token_usd": 2500.0,
                "token_usd_rate": 2500.0,
                "effective_price_usd": 2500.0,
                "price_source": "direct_and_enriched_available",
                "token_underlying_rate": 1.02,
                "token_underlying_symbol": "ETH",
                "token_weth_rate": 1.02,
            }
        ],
    )

    result = get_token_prices_batch(
        token_addresses=[
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
        ],
        granularity="daily",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["summary"]["matched_token_count"] == 1
    assert result["summary"]["missing_token_count"] == 1
    assert result["summary"]["missing_tokens"] == ["0x2222222222222222222222222222222222222222"]
    assert result["summary"]["price_source_breakdown"] == {"direct_and_enriched_available": 1}


def test_price_workflow_minute_missing_diagnostic_suggests_daily_fallback(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "in_price_token_universe": True,
                "in_tokens_traits": True,
                "has_raw_usd_minute": True,
                "has_raw_usd_daily": True,
                "has_enriched_minute": False,
                "has_enriched_daily": True,
                "has_exchange_rates_raw": False,
                "has_exchange_rates_daily": False,
            }
        ],
    )

    result = diagnose_token_price_coverage(
        token_address="0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["summary"]["minute_enriched_missing_but_daily_exists"] is True
    assert "incomplete by design" in result["likely_explanation"]
    assert any("Use daily granularity" in step for step in result["suggested_next_steps"])


def test_price_workflow_exchange_rate_without_usd_diagnostic(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "in_price_token_universe": True,
                "in_tokens_traits": True,
                "has_raw_usd_minute": False,
                "has_raw_usd_daily": False,
                "has_enriched_minute": False,
                "has_enriched_daily": False,
                "has_exchange_rates_raw": True,
                "has_exchange_rates_daily": True,
            }
        ],
    )

    result = diagnose_token_price_coverage(
        token_address="0x1111111111111111111111111111111111111111",
        execute_live=True,
        datasets=_price_coverage_test_datasets(),
        freshness_registry={},
    )

    assert result["summary"]["has_any_exchange_rate"] is True
    assert result["summary"]["has_any_raw_usd_price"] is False
    assert "not the same as a USD price feed" in result["likely_explanation"]


def test_find_price_tokens_planning_mode_returns_candidate_sql():
    result = find_price_tokens(
        token_symbol="weETH",
        blockchain="bnb",
        limit=10,
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
                "grain": "one row per token address and blockchain metadata record",
                "refresh_interval_minutes": 2880,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
                "refresh_interval_minutes": 60,
            },
        },
        freshness_registry={},
    )

    assert result["dataset_name"] == "dune.ether_fi.result_tokens_traits"
    assert result["coverage_dataset_name"] == "dune.ether_fi.result_tokens_prices_tokens_list"
    assert "LOWER(token_symbol) LIKE LOWER('%weETH%')" in result["suggested_sql"]
    assert "blockchain = 'bnb'" in result["suggested_sql"]
    assert "LEFT JOIN price_universe" in result["suggested_sql"]
    assert "in_price_token_universe" in result["expected_output_fields"]
    assert "get_token_price" in result["next_step"]
    assert result["summary"]["candidate_count"] == 0


def test_find_price_tokens_execute_live_returns_summary(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "token_address": "0x1111111111111111111111111111111111111111",
                "blockchain": "ethereum",
                "token_symbol": "weETH",
                "token_project": "ether.fi",
                "token_type": "lrt",
                "in_price_token_universe": True,
                "last_updated": "2026-04-12 00:00:00 UTC",
            },
            {
                "token_address": "0x2222222222222222222222222222222222222222",
                "blockchain": "bnb",
                "token_symbol": "weETH",
                "token_project": "ether.fi",
                "token_type": "lrt",
                "in_price_token_universe": True,
                "last_updated": "2026-04-12 00:00:00 UTC",
            },
        ],
    )

    result = find_price_tokens(
        token_symbol="weETH",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
                "grain": "one row per token address and blockchain metadata record",
                "refresh_interval_minutes": 2880,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
                "refresh_interval_minutes": 60,
            },
        },
        freshness_registry={},
    )

    assert result["executed_live"] is True
    assert result["row_count"] == 2
    assert result["summary"]["candidate_count"] == 2
    assert result["summary"]["blockchains"] == ["bnb", "ethereum"]
    assert result["summary"]["in_price_token_universe_count"] == 2
    assert "get_token_price" in result["summary"]["next_step"]


def test_find_price_tokens_validates_inputs():
    missing_filters = find_price_tokens(
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
            },
        },
        freshness_registry={},
    )
    invalid_blockchain = find_price_tokens(
        token_symbol="weETH",
        blockchain="bnb;drop",
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
            },
        },
        freshness_registry={},
    )
    invalid_limit = find_price_tokens(
        token_symbol="weETH",
        limit=0,
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
            },
        },
        freshness_registry={},
    )

    assert missing_filters["error"] == "Provide token_symbol, token_project, or blockchain."
    assert "blockchain must contain" in invalid_blockchain["error"]
    assert "limit must be" in invalid_limit["error"]


def test_get_token_price_by_symbol_planning_mode_describes_orchestration():
    result = get_token_price_by_symbol(
        token_symbol="weETH",
        blockchain="bnb",
        granularity="daily",
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
            },
        },
        freshness_registry={},
    )

    assert result["outcome"] == "planning"
    assert result["executed_live"] is False
    assert "discover token candidates" in result["summary"]["steps"][0]
    assert "resolved_and_priced" in result["summary"]["possible_outcomes"]
    assert "suggested_sql" in result["discovery_plan"]
    assert "price_summary" in result["expected_output_fields"]


def test_get_token_price_by_symbol_live_resolves_unique_candidate_and_prices(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")

    def fake_execute(sql):
        if "WITH token_candidates" in sql:
            return [
                {
                    "token_address": "0x1111111111111111111111111111111111111111",
                    "blockchain": "bnb",
                    "token_symbol": "weETH",
                    "token_project": "ether.fi",
                    "token_type": "lrt",
                    "in_price_token_universe": True,
                    "last_updated": "2026-04-12 00:00:00 UTC",
                }
            ]
        return [
            {
                "day": "2026-04-12 00:00:00 UTC",
                "blockchain": "bnb",
                "token_address": "0x1111111111111111111111111111111111111111",
                "token_symbol": "weETH",
                "token_usd": None,
                "token_usd_rate": 2500.0,
                "effective_price_usd": 2500.0,
                "price_source": "enriched_fallback",
                "token_underlying_rate": 1.02,
                "token_underlying_symbol": "ETH",
                "token_weth_rate": 1.02,
                "last_updated": "2026-04-12 01:00:00 UTC",
            }
        ]

    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", fake_execute)

    result = get_token_price_by_symbol(
        token_symbol="weETH",
        blockchain="bnb",
        granularity="daily",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
            },
            "dune.ether_fi.result_tokens_prices_enriched_daily": {
                "name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "display_name": "Tokens Prices Enriched (Daily)",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_enriched_daily",
                "query_ready": True,
            },
        },
        freshness_registry={},
    )

    assert result["outcome"] == "resolved_and_priced"
    assert result["resolved_token"]["token_address"] == "0x1111111111111111111111111111111111111111"
    assert result["price_summary"]["effective_price_usd"] == 2500.0
    assert result["price_summary"]["price_source"] == "enriched_fallback"
    assert result["price_result"]["dataset_name"] == "dune.ether_fi.result_tokens_prices_enriched_daily"


def test_get_token_price_by_symbol_live_returns_disambiguation_for_multiple_matches(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr(
        "etherfi_catalog.catalog._execute_dune_sql",
        lambda sql: [
            {
                "token_address": "0x1111111111111111111111111111111111111111",
                "blockchain": "ethereum",
                "token_symbol": "weETH",
                "token_project": "ether.fi",
                "token_type": "lrt",
                "in_price_token_universe": True,
            },
            {
                "token_address": "0x2222222222222222222222222222222222222222",
                "blockchain": "bnb",
                "token_symbol": "weETH",
                "token_project": "ether.fi",
                "token_type": "lrt",
                "in_price_token_universe": True,
            },
        ],
    )

    result = get_token_price_by_symbol(
        token_symbol="weETH",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
            },
        },
        freshness_registry={},
    )

    assert result["outcome"] == "needs_disambiguation"
    assert len(result["candidates"]) == 2
    assert result["summary"]["exact_candidate_count"] == 2
    assert any("Specify blockchain" in suggestion for suggestion in result["summary"]["suggestions"])


def test_get_token_price_by_symbol_live_returns_no_match(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "test-key")
    monkeypatch.setattr("etherfi_catalog.catalog._execute_dune_sql", lambda sql: [])

    result = get_token_price_by_symbol(
        token_symbol="NOPE",
        execute_live=True,
        datasets={
            "dune.ether_fi.result_tokens_traits": {
                "name": "dune.ether_fi.result_tokens_traits",
                "display_name": "Tokens Traits",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_traits",
                "query_ready": True,
            },
            "dune.ether_fi.result_tokens_prices_tokens_list": {
                "name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "display_name": "Tokens Prices Token List",
                "description": "Example dataset",
                "table_name": "dune.ether_fi.result_tokens_prices_tokens_list",
                "query_ready": True,
            },
        },
        freshness_registry={},
    )

    assert result["outcome"] == "no_match"
    assert result["summary"]["candidate_count"] == 0
    assert "Try a different token_symbol spelling." in result["summary"]["suggestions"]


def test_get_token_price_by_symbol_validates_inputs():
    missing_symbol = get_token_price_by_symbol()
    invalid_granularity = get_token_price_by_symbol(token_symbol="weETH", granularity="hourly")
    invalid_timestamp = get_token_price_by_symbol(token_symbol="weETH", as_of_timestamp="todayish")

    assert missing_symbol["error"] == "Provide token_symbol."
    assert "granularity must be" in invalid_granularity["error"]
    assert "as_of_timestamp must be" in invalid_timestamp["error"]


def test_search_datasets_finds_both_holder_datasets():
    results = search_datasets("holder")
    names = {dataset["name"] for dataset in results}

    assert "etherfi_protocol_token_holders" in names
    assert "etherfi_protocol_token_holders_with_defi" in names


def test_search_datasets_finds_protocol_token_holders_by_alias():
    results = search_datasets("dune.ether_fi.result_etherfi_protocol_token_holders")

    assert [dataset["name"] for dataset in results] == ["etherfi_protocol_token_holders"]


def test_search_datasets_finds_protocol_token_holders_with_defi_by_alias():
    results = search_datasets("dune.ether_fi.result_etherfi_protocol_token_holders_with_defi")

    assert [dataset["name"] for dataset in results] == ["etherfi_protocol_token_holders_with_defi"]


def test_search_datasets_finds_etherfi_addresses_by_cash_safe_intent():
    results = search_datasets("cash safe")

    assert any(
        dataset["name"] == "dune.ether_fi.result_etherfi_addresses"
        for dataset in results
    )


def test_search_datasets_distinguishes_minute_enriched_prices_from_raw_usd_feed():
    results = search_datasets("minute-level token prices")
    names = {dataset["name"] for dataset in results}

    assert "dune.ether_fi.result_tokens_prices_enriched_minute" in names
    assert "dune.ether_fi.result_tokens_prices_usd" in names

    enriched_minute = next(
        dataset
        for dataset in results
        if dataset["name"] == "dune.ether_fi.result_tokens_prices_enriched_minute"
    )
    raw_usd = next(
        dataset
        for dataset in results
        if dataset["name"] == "dune.ether_fi.result_tokens_prices_usd"
    )

    assert enriched_minute["completeness label"] == "partial"
    assert any("incomplete by design" in note for note in enriched_minute["semantic_notes"])
    assert any("coalesce(token_usd, token_usd_rate)" in note for note in enriched_minute["query_notes"])
    assert "raw/direct USD token price feed" in raw_usd["description"]


def test_search_datasets_finds_enriched_daily_prices_for_dashboarding_default():
    results = search_datasets("daily token prices for dashboards")
    names = {dataset["name"] for dataset in results}

    assert "dune.ether_fi.result_tokens_prices_enriched_daily" in names

    enriched_daily = next(
        dataset
        for dataset in results
        if dataset["name"] == "dune.ether_fi.result_tokens_prices_enriched_daily"
    )

    assert any("safer than incomplete minute coverage" in use for use in enriched_daily["use_when"])
    assert any("better default" in note for note in enriched_daily["semantic_notes"])
    assert any("coalesce(token_usd, token_usd_rate)" in note for note in enriched_daily["query_notes"])


def test_search_datasets_finds_raw_usd_price_feed_and_token_list_diagnostic():
    raw_results = search_datasets("direct raw USD price feed")
    raw_names = {dataset["name"] for dataset in raw_results}

    assert "dune.ether_fi.result_tokens_prices_usd" in raw_names

    raw_usd = next(
        dataset
        for dataset in raw_results
        if dataset["name"] == "dune.ether_fi.result_tokens_prices_usd"
    )

    assert "raw/direct USD token price feed" in raw_usd["description"]
    assert any("raw/direct USD price feed value" in note for note in raw_usd["query_notes"])

    missing_results = search_datasets("why is a token missing from price tables?")
    missing_names = {dataset["name"] for dataset in missing_results}

    assert "dune.ether_fi.result_tokens_prices_tokens_list" in missing_names

    token_list = next(
        dataset
        for dataset in missing_results
        if dataset["name"] == "dune.ether_fi.result_tokens_prices_tokens_list"
    )

    assert "Token universe" in token_list["description"]
    assert any("does not guarantee a direct USD feed" in note for note in token_list["query_notes"])


def test_search_datasets_finds_exchange_rates_without_confusing_them_for_usd_prices():
    exchange_results = search_datasets("token exchange rates")
    exchange_names = {dataset["name"] for dataset in exchange_results}

    assert "dune.ether_fi.result_tokens_rates_oracle_pegs" in exchange_names

    oracle_rates = next(
        dataset
        for dataset in exchange_results
        if dataset["name"] == "dune.ether_fi.result_tokens_rates_oracle_pegs"
    )

    assert "not a USD price table" in oracle_rates["description"]
    assert any("Do not describe this dataset as a USD price table" in note for note in oracle_rates["query_notes"])

    daily_results = search_datasets("daily exchange rates with forward fill semantics")
    daily_names = {dataset["name"] for dataset in daily_results}

    assert "dune.ether_fi.result_tokens_exchange_rates_daily" in daily_names

    daily_rates = next(
        dataset
        for dataset in daily_results
        if dataset["name"] == "dune.ether_fi.result_tokens_exchange_rates_daily"
    )

    assert any("forward-fill behavior" in note for note in daily_rates["query_notes"])
    assert any("not a USD price table" in note for note in daily_rates["semantic_notes"])


def test_compare_datasets_reflects_holder_completeness_difference():
    comparison = compare_datasets(
        "etherfi_protocol_token_holders",
        "etherfi_protocol_token_holders_with_defi",
    )

    assert comparison["name_a"] == "etherfi_protocol_token_holders"
    assert comparison["name_b"] == "etherfi_protocol_token_holders_with_defi"
    assert comparison["completeness_a"] == "complete"
    assert comparison["completeness_b"] == "partial"


def test_compare_datasets_accepts_legacy_holder_names():
    comparison = compare_datasets(
        "protocol_token_holders",
        "protocol_token_holders_with_defi",
    )

    assert comparison["name_a"] == "etherfi_protocol_token_holders"
    assert comparison["name_b"] == "etherfi_protocol_token_holders_with_defi"
