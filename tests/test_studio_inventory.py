import json
from pathlib import Path
import re

import scripts.generate_studio_inventory as inventory_module

from scripts.generate_studio_inventory import (
    DEFAULT_JSON_PATH,
    DEFAULT_MARKDOWN_PATH,
    build_inventory,
    check_outputs,
    generated_outputs,
    render_markdown,
)


def test_inventory_has_metric_rows_and_a_deduplicated_query_plan():
    inventory = build_inventory()

    assert inventory["schema_version"] == 2
    assert inventory["dashboard_count"] == 2
    assert inventory["metric_count"] == 37
    assert inventory["unique_query_count"] == 17
    assert re.fullmatch(r"[0-9a-f]{64}", inventory["registry_checksum"])
    assert len(inventory["metrics"]) == 37
    assert len(inventory["queries"]) == 17
    assert len({query["query_id"] for query in inventory["queries"]}) == 17


def test_inventory_deduplicates_the_shared_live_kyberswap_attribution_source():
    inventory = build_inventory()
    metrics = {metric["metric_id"]: metric for metric in inventory["metrics"]}
    query = next(
        query for query in inventory["queries"] if query["query_id"] == 8199058
    )

    assert query["provider_mode"] == "latest_result"
    assert query["metric_ids"] == [
        "kyber_attributed_tvl_by_location",
        "kyber_capital_journey",
        "kyber_product_adoption",
        "kyber_referral_deposit_concentration",
        "kyber_top_depositors",
        "kyber_top_referred_depositors",
        "kyber_wallet_investigation",
    ]
    assert query["source_required_columns"] == [
        "day",
        "address",
        "strategy_symbol",
        "base_asset",
        "depositor_type",
        "current_token",
        "current_token_category",
        "referral_balance",
        "current_balance",
        "previous_balance",
    ]
    assert query["transformation"]["raw_data_file"] == "raw_query_8199058.json"
    assert query["transformation"]["script_path"] == (
        "scripts/enrich_kyberswap_attributed_holdings.py"
    )
    assert query["transformation"]["version"] == "2.0.0"
    for metric_id in query["metric_ids"]:
        assert metrics[metric_id]["query_id"] == 8199058
        assert metrics[metric_id]["transformation"] == query["transformation"]
    assert 8178495 not in {
        query_record["query_id"] for query_record in inventory["queries"]
    }


def test_inventory_registers_post_referral_activity_as_one_read_only_source():
    inventory = build_inventory()
    metrics = {metric["metric_id"]: metric for metric in inventory["metrics"]}
    query = next(
        query for query in inventory["queries"] if query["query_id"] == 8202133
    )

    assert query["provider_mode"] == "latest_result"
    assert query["metric_ids"] == ["kyber_post_referral_activity"]
    assert query["source_required_columns"] == [
        "day",
        "week",
        "project",
        "event",
        "label",
        "amount_usd",
    ]
    assert query["transformation"]["id"] == "kyberswap_post_referral_activity"
    assert query["transformation"]["raw_data_file"] == "raw_query_8202133.json"
    assert query["transformation"]["script_path"] == (
        "scripts/enrich_kyberswap_growth.py"
    )
    assert {
        "record_type",
        "granularity",
        "period",
        "day",
        "week",
        "grouping_type",
        "category",
        "amount_usd",
        "source_query_id",
        "source_execution_id",
        "source_last_updated",
        "generated_at",
    } == set(query["required_columns"])
    assert metrics["kyber_post_referral_activity"]["query_id"] == 8202133


def test_inventory_registers_depositor_event_sources_as_read_only_transforms():
    inventory = build_inventory()
    queries = {query["query_id"]: query for query in inventory["queries"]}
    expected = {
        8204345: (
            "kyber_recent_referral_deposits",
            "kyberswap_referral_deposits",
            [
                "tx_hash",
                "address",
                "blockchain",
                "block_time",
                "strategy_symbol",
                "amount_usd",
            ],
        ),
        8204373: (
            "kyber_recent_etherfi_activity",
            "kyberswap_etherfi_activity",
            [
                "event",
                "address",
                "project",
                "blockchain",
                "tx_hash",
                "block_time",
                "amount_usd",
                "token_symbol",
                "label",
            ],
        ),
    }
    for query_id, (metric_id, transformation_id, source_columns) in expected.items():
        query = queries[query_id]
        assert query["provider_mode"] == "latest_result"
        assert query["metric_ids"] == [metric_id]
        assert query["source_required_columns"] == source_columns
        assert query["transformation"]["id"] == transformation_id
        assert query["transformation"]["script_path"] == (
            "scripts/prepare_kyberswap_depositor_intelligence.py"
        )
        assert query["transformation"]["raw_data_file"] == (
            f"raw_query_{query_id}.json"
        )


def test_inventory_renames_depositor_section_without_changing_source_contracts():
    inventory = build_inventory()
    metrics = {metric["metric_id"]: metric for metric in inventory["metrics"]}
    depositor_metric_ids = [
        "kyber_top_referred_depositors",
        "kyber_referral_deposit_concentration",
        "kyber_top_depositors",
        "kyber_recent_referral_deposits",
        "kyber_recent_etherfi_activity",
        "kyber_wallet_investigation",
    ]

    assert {
        metrics[metric_id]["section"] for metric_id in depositor_metric_ids
    } == {"Depositor Analysis"}
    assert {
        metrics[metric_id]["section_id"] for metric_id in depositor_metric_ids
    } == {"tables"}
    for metric_id in (
        "kyber_recent_referral_deposits",
        "kyber_recent_etherfi_activity",
    ):
        assert "block_time" in metrics[metric_id]["required_columns"]
        assert "tx_hash" in metrics[metric_id]["required_columns"]
    assert "allocation_rule" in metrics["kyber_wallet_investigation"][
        "required_columns"
    ]


def test_inventory_fetches_the_campaign_summary_once_for_all_eight_counters():
    inventory = build_inventory()
    metrics = {metric["metric_id"]: metric for metric in inventory["metrics"]}
    query = next(
        query for query in inventory["queries"] if query["query_id"] == 8180894
    )

    counter_ids = [
        "kyber_total_referral_deposits",
        "kyber_attributed_tvl",
        "kyber_new_depositor_deposits",
        "kyber_new_depositor_deposit_rate",
        "kyber_total_depositors",
        "kyber_new_depositors",
        "kyber_retention_rate",
        "kyber_revenue_generated",
    ]
    assert query["provider_mode"] == "latest_result"
    assert query["metric_ids"] == sorted(counter_ids)
    assert query["source_required_columns"] == ["rank_", "key_"]
    assert query["transformation"]["raw_data_file"] == "raw_query_8180894.json"
    assert query["transformation"]["script_path"] == (
        "scripts/prepare_kyberswap_campaign_summary.py"
    )
    assert {metrics[metric_id]["query_id"] for metric_id in counter_ids} == {8180894}
    assert {
        "total_deposits_usd",
        "outstanding_balance_usd",
        "num_depositors",
        "new_depositors",
        "deposits_by_new_depositors",
        "retention_rate",
        "depositors_new_users_rate",
        "revenue_generated",
    } <= set(query["required_columns"])


def test_inventory_deduplicates_four_growth_sources_for_six_charts():
    inventory = build_inventory()
    metrics = {metric["metric_id"]: metric for metric in inventory["metrics"]}
    queries = {query["query_id"]: query for query in inventory["queries"]}
    growth_contracts = {
        8191379: (
            ["kyber_referral_deposits_growth"],
            "kyberswap_growth_deposits",
        ),
        8191704: (
            ["kyber_attributed_tvl_over_time"],
            "kyberswap_growth_attributed_tvl",
        ),
        8193003: (
            [
                "kyber_referral_deposits_breakdown",
                "kyber_total_referral_deposits_breakdown",
            ],
            "kyberswap_growth_breakdown",
        ),
        8193040: (
            [
                "kyber_deposit_depositor_count_by_product",
                "kyber_deposit_depositor_count_by_depositor_type",
            ],
            "kyberswap_growth_activity",
        ),
    }
    for query_id, (metric_ids, transformation_id) in growth_contracts.items():
        query = queries[query_id]
        assert query["provider_mode"] == "latest_result"
        assert query["metric_ids"] == sorted(metric_ids)
        assert query["transformation"]["id"] == transformation_id
        assert query["transformation"]["raw_data_file"] == (
            f"raw_query_{query_id}.json"
        )
        assert query["transformation"]["script_path"] == (
            "scripts/enrich_kyberswap_growth.py"
        )
        assert {metrics[metric_id]["query_id"] for metric_id in metric_ids} == {
            query_id
        }


def test_inventory_uses_display_order_and_includes_stage_14_fields():
    inventory = build_inventory()
    first = inventory["metrics"][0]

    assert first["dashboard_id"] == "kyberswap_campaign"
    assert first["metric_id"] == "kyber_total_referral_deposits"
    assert first["section_id"] == "counters"
    assert first["section"] == "Campaign summary"
    assert first["visualization"] == "counter"
    assert first["visualization_type"] == first["visualization"]
    assert first["default_visualization"] == "counter"
    assert first["allowed_visualizations"] == ["counter"]
    assert first["value_format"] == "currency_compact"
    assert first["exportable"] is True
    assert first["optional_columns"] == []
    assert first["source_mappings"][0]["role"] == "primary"


def test_inventory_does_not_require_an_already_matching_generated_snapshot(
    monkeypatch,
):
    original = inventory_module.load_studio_registry
    calls = []

    def tracked_load(*args, **kwargs):
        calls.append(kwargs.get("validate_generated_data"))
        return original(*args, **kwargs)

    monkeypatch.setattr(inventory_module, "load_studio_registry", tracked_load)

    inventory_module.build_inventory()

    assert calls == [False]


def test_inventory_assigns_sparkline_dependencies_to_their_source_query():
    inventory = build_inventory()
    metric = next(
        metric
        for metric in inventory["metrics"]
        if metric["metric_id"] == "lab_total_value"
    )
    timeseries_query = next(
        query for query in inventory["queries"] if query["query_id"] == 9102002
    )

    assert metric["source_mappings"][1] == {
        "role": "sparkline",
        "query_id": 9102002,
        "query_url": "https://dune.com/queries/9102002",
        "data_file": "query_9102002.json",
        "data_source": "lab_timeseries",
        "provider_mode": "fixture",
        "source_required_columns": [],
        "transformation": {},
        "required_columns": ["day", "total_value_usd"],
        "optional_columns": [],
    }
    assert {
        "day",
        "total_value_usd",
        "deposits_usd",
        "withdrawals_usd",
        "fees_usd",
    } <= set(
        timeseries_query["required_columns"]
    )
    assert "lab_total_value" in timeseries_query["metric_ids"]


def test_inventory_json_and_markdown_are_deterministic():
    first = generated_outputs()
    second = generated_outputs()

    assert first == second
    assert json.loads(first[0]) == build_inventory()
    assert first[1] == render_markdown(build_inventory())
    assert "Unique query fetch plan" in first[1]
    assert "demo placeholders" in first[1]
    assert "`8199058`" in first[1]
    assert "`8202133`" in first[1]
    assert "`8204345`" in first[1]
    assert "`8204373`" in first[1]
    assert "8178495" not in first[1]
    assert "| Dashboard | Section | Metric | Source role |" in first[1]
    assert "Default visualization | Allowed visualizations | Value format" in first[1]
    assert (
        "KyberSwap Campaign | Campaign summary | Total Referral Deposits | Primary"
        in first[1]
    )
    assert "KyberSwap Campaign | Depositor Analysis | Recent Referral Deposits" in first[1]
    assert "Depositor Intelligence" not in first[1]


def test_checked_in_inventory_matches_registry():
    assert check_outputs() == []


def test_inventory_check_detects_missing_or_drifted_files(tmp_path: Path):
    json_path = tmp_path / "query_inventory.json"
    markdown_path = tmp_path / "studio-query-inventory.md"
    json_text, markdown_text = generated_outputs()
    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown_text + "\nchanged\n", encoding="utf-8")

    assert check_outputs(json_path, markdown_path) == [markdown_path]


def test_inventory_default_paths_are_the_documented_artifacts():
    assert DEFAULT_JSON_PATH.name == "query_inventory.json"
    assert DEFAULT_MARKDOWN_PATH.name == "studio-query-inventory.md"
