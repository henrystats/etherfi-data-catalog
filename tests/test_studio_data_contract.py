from copy import deepcopy
from html import unescape
import json
from pathlib import Path
import re

import pytest

from scripts.studio import (
    STUDIO_DATA_SCHEMA_VERSION,
    StudioDashboard,
    StudioMetric,
    build_studio_query_contracts,
    load_studio_generated_manifest,
    load_studio_query_result,
    load_studio_registry,
    load_studio_data,
    normalize_studio_registry,
    publish_studio_generated_data,
    render_studio_dashboard,
    resolve_studio_generated_data_dir,
    validate_studio_generated_manifest,
    validate_studio_query_result,
    validate_studio_registry,
)


GENERATED_AT = "2026-07-30T12:00:00Z"
FINISHED_AT = "2026-07-30T11:58:41Z"


def dashboard(
    *,
    data_mode: str = "demo",
    stale_after_hours: int | float | None = None,
) -> dict:
    value = {
        "id": "contract_dashboard",
        "slug": "contract",
        "name": "Contract Dashboard",
        "description": "A focused data-contract fixture.",
        "eyebrow": "Contract",
        "audience": "Engineering",
        "status": "demo" if data_mode == "demo" else "live",
        "freshness_status": "current",
        "freshness_note": "Fixture metadata.",
        "data_mode": data_mode,
        "data_file": "contract.json",
        "default_date_range": "ALL",
        "display_order": 1,
        "sections": [
            {
                "id": "summary",
                "label": "Summary",
                "description": "Contract metrics.",
            }
        ],
    }
    if stale_after_hours is not None:
        value["stale_after_hours"] = stale_after_hours
    return value


def metric(
    metric_id: str,
    column: str,
    *,
    query_id: int = 42,
    data_source: str = "shared_result",
    display_order: int = 1,
    exportable: bool = True,
) -> dict:
    return {
        "id": metric_id,
        "dashboard_id": "contract_dashboard",
        "name": metric_id.replace("_", " ").title(),
        "description": f"Value from {column}.",
        "section": "summary",
        "visualization_type": "counter",
        "query_id": query_id,
        "columns": [column],
        "data_source": data_source,
        "last_updated": "generated",
        "is_exportable": exportable,
        "default_visible": True,
        "display_order": display_order,
        "value_format": "integer",
        "size": "small",
    }


def compact_counter_registry() -> tuple[list[dict], list[dict]]:
    dashboard_value = dashboard(data_mode="generated")
    dashboard_value["show_hero"] = False
    dashboard_value["sections"][0].update(
        {
            "show_heading": False,
            "grid_columns": 2,
            "shared_methodology_metric_id": "campaign_summary",
            "shared_export_metric_id": "campaign_summary",
        }
    )
    metric_value = metric("campaign_summary", "total")
    metric_value.update(
        {
            "columns": ["key_", "total", "source_last_updated"],
            "value_column": "total",
            "compact_counter": True,
            "period_key_column": "key_",
            "period_key_map": {
                "30D": "30d_data",
                "ALL": "all_time_data",
            },
            "export_name": "Campaign Summary",
            "export_slug": "campaign-summary",
            "export_columns": ["key_", "total", "source_last_updated"],
            "export_column_aliases": {"key_": "period"},
            "methodology": {
                "title": "Campaign Summary",
                "description": "Selected-period campaign counters.",
                "metric_definitions": ["Total is the selected-period value."],
                "selected_period_logic": ["The active range selects one key row."],
                "notes": ["Missing development values display zero."],
            },
        }
    )
    return [dashboard_value], [metric_value]


def growth_metric(kind: str = "timeseries") -> dict:
    default_style, allowed_styles = {
        "combo": ("line", ["line"]),
        "timeseries": ("area", ["area", "line"]),
        "ranking": (None, None),
    }[kind]
    value = metric(
        f"growth_{kind}",
        "value_usd",
        query_id=8191379,
        data_source="kyberswap_growth",
    )
    value.update(
        {
            "columns": [
                "record_type",
                "period",
                "observation_day",
                "category",
                "value_usd",
            ],
            "size": "medium",
        }
    )
    growth_chart = {
        "kind": kind,
        "period_column": "period",
        "available_granularities": [] if kind == "ranking" else ["daily", "weekly"],
        "default_view": "all",
        "views": [
            {
                "id": "all",
                "label": "All",
                "record_types": (
                    {"total": "daily_total"}
                    if kind == "ranking"
                    else {"daily": "daily", "weekly": "weekly"}
                ),
                "dimension_column": "category",
                "value_column": "value_usd",
            }
        ],
        "measures": [
            {
                "column": "value_usd",
                "label": "Value",
                "format": "currency_compact",
                "series_type": "bar" if kind == "ranking" else "line",
            }
        ],
        "export_columns": ["period", "category", "value_usd"],
        "export_aliases": {
            "period": "period",
            "category": "dimension",
            "value_usd": "primary_value",
        },
    }
    if kind == "ranking":
        value.update(
            {
                "visualization_type": "bar",
                "orientation": "horizontal",
                "category_column": "category",
                "value_column": "value_usd",
            }
        )
    else:
        value.update(
            {
                "visualization_type": "line",
                "date_column": "period",
                "series": [{"column": "value_usd", "label": "Value"}],
                "default_visualization": default_style,
                "allowed_visualizations": allowed_styles,
            }
        )
        growth_chart["default_granularity"] = "weekly"
        growth_chart["range_date_column"] = "observation_day"
        growth_chart["rebuild_weekly_from_daily"] = True
    value["growth_chart"] = growth_chart
    return value


def manifest_entry(
    *,
    query_id: int = 42,
    columns: list[str] | None = None,
    status: str = "success",
    freshness_status: str = "current",
    row_count: int = 1,
    data_file: str | None = None,
    error: str | None = None,
) -> dict:
    entry = {
        "schema_version": STUDIO_DATA_SCHEMA_VERSION,
        "query_id": query_id,
        "query_url": f"https://dune.com/queries/{query_id}",
        "data_file": data_file or f"query_{query_id}.json",
        "generated_at": GENERATED_AT,
        "execution_id": f"fixture-{query_id}",
        "execution_finished_at": FINISHED_AT,
        "status": status,
        "freshness_status": freshness_status,
        "row_count": row_count,
        "columns": columns or ["value_a", "value_b"],
    }
    if error is not None:
        entry["error"] = error
    return entry


def query_result(entry: dict, rows: list[dict]) -> dict:
    return {
        key: deepcopy(value)
        for key, value in entry.items()
        if key != "data_file"
    } | {"rows": rows}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_generated_contract(
    directory: Path,
    entries_and_rows: list[tuple[dict, list[dict]]],
) -> None:
    directory.mkdir(parents=True)
    entries = [entry for entry, _ in entries_and_rows]
    write_json(
        directory / "manifest.json",
        {
            "schema_version": STUDIO_DATA_SCHEMA_VERSION,
            "generated_at": GENERATED_AT,
            "queries": entries,
        },
    )
    for entry, rows in entries_and_rows:
        write_json(
            directory / entry["data_file"],
            query_result(entry, rows),
        )


def test_registry_normalization_derives_query_fields_and_preserves_runtime_format():
    raw_dashboard = dashboard()
    del raw_dashboard["data_mode"]
    raw_metric = metric("value_a", "value_a")

    normalized_dashboards, normalized_metrics = normalize_studio_registry(
        [raw_dashboard],
        [raw_metric],
    )

    assert normalized_dashboards[0]["data_mode"] == "demo"
    assert normalized_metrics[0]["query_url"] == "https://dune.com/queries/42"
    assert normalized_metrics[0]["data_file"] == "query_42.json"
    assert normalized_metrics[0]["format"] == "integer"
    assert normalized_metrics[0]["value_format"] == "integer"

    conflicting = deepcopy(raw_metric)
    conflicting["format"] = "currency"
    with pytest.raises(ValueError, match="value_format conflicts with format"):
        normalize_studio_registry([raw_dashboard], [conflicting])


def test_depositor_recent_table_contracts_keep_raw_age_sort_and_export_fields():
    _, metrics = load_studio_registry(validate_generated_data=False)
    metrics_by_id = {metric.id: metric.data for metric in metrics}
    recent_metrics = [
        metrics_by_id["kyber_recent_referral_deposits"],
        metrics_by_id["kyber_recent_etherfi_activity"],
    ]
    contracts = build_studio_query_contracts(recent_metrics)

    assert set(contracts) == {8204345, 8204373}
    for metric_value in recent_metrics:
        assert metric_value["section"] == "tables"
        assert "derived_data_source" not in metric_value
        assert metric_value["size"] == "medium"
        assert metric_value["page_size"] == 10
        assert metric_value["column_labels"]["block_time"] == "Age"
        assert metric_value["column_labels"]["tx_hash"] == "Tx Hash"
        assert metric_value["date_column"] == "block_time"
        assert metric_value["default_sort_column"] == "block_time"
        assert metric_value["default_sort_direction"] == "descending"
        assert metric_value["table_columns"][0] == "block_time"
        assert metric_value["table_columns"][-1] == "tx_hash"
        assert metric_value["export_columns"][0] == "block_time"
        assert metric_value["export_columns"][-1] == "tx_hash"
        contract = contracts[metric_value["query_id"]]
        assert "block_time" in contract["required_columns"]
        assert "tx_hash" in contract["required_columns"]

    wallet_metric = metrics_by_id["kyber_wallet_investigation"]
    wallet_contract = build_studio_query_contracts([wallet_metric])[8199058]
    assert "allocation_rule" in wallet_metric["columns"]
    assert "allocation_rule" in wallet_contract["required_columns"]


def test_registry_accepts_compact_period_counter_section_and_export_contract():
    dashboards, metrics = compact_counter_registry()

    normalized_dashboards, normalized_metrics = validate_studio_registry(
        dashboards,
        metrics,
        validate_generated_data=False,
    )

    section = normalized_dashboards[0]["sections"][0]
    configured_metric = normalized_metrics[0]
    assert normalized_dashboards[0]["show_hero"] is False
    assert section == {
        "id": "summary",
        "label": "Summary",
        "description": "Contract metrics.",
        "show_heading": False,
        "grid_columns": 2,
        "shared_methodology_metric_id": "campaign_summary",
        "shared_export_metric_id": "campaign_summary",
    }
    assert configured_metric["value_column"] == "total"
    assert configured_metric["period_key_map"]["ALL"] == "all_time_data"
    assert configured_metric["export_column_aliases"] == {"key_": "period"}


def test_registry_accepts_generic_growth_chart_contracts():
    dashboard_value = dashboard(data_mode="generated")
    dashboard_value["sections"][0].update(
        {
            "label": "Campaign Growth & Activity",
            "description": "Referral deposits and activity over time.",
            "grid_columns": 2,
        }
    )
    metrics = [
        growth_metric("combo"),
        growth_metric("timeseries"),
        growth_metric("ranking"),
    ]
    for display_order, value in enumerate(metrics, start=1):
        value["display_order"] = display_order

    normalized_dashboards, normalized_metrics = validate_studio_registry(
        [dashboard_value],
        metrics,
        validate_generated_data=False,
    )

    assert normalized_dashboards[0]["sections"][0]["grid_columns"] == 2
    assert [value["growth_chart"]["kind"] for value in normalized_metrics] == [
        "combo",
        "timeseries",
        "ranking",
    ]
    assert {value["query_id"] for value in normalized_metrics} == {8191379}
    assert {value["data_source"] for value in normalized_metrics} == {
        "kyberswap_growth"
    }
    assert normalized_metrics[0]["growth_chart"]["range_date_column"] == (
        "observation_day"
    )
    assert normalized_metrics[1]["growth_chart"]["rebuild_weekly_from_daily"] is True
    assert normalized_metrics[2]["growth_chart"]["export_aliases"]["category"] == (
        "dimension"
    )


@pytest.mark.parametrize(
    ("kind", "mutation", "message"),
    [
        (
            "timeseries",
            lambda value: value["growth_chart"].update({"kind": "unsupported"}),
            "growth_chart kind is invalid",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"].update(
                {"default_granularity": "monthly"}
            ),
            "default_granularity must be daily or weekly",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"].update(
                {"available_granularities": ["daily", "monthly"]}
            ),
            "available_granularities must contain only daily or weekly",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"].update(
                {"period_column": "missing"}
            ),
            "period_column must be declared in columns",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"].update(
                {"range_date_column": "missing"}
            ),
            "range_date_column must be declared in columns",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"].update(
                {"rebuild_weekly_from_daily": "yes"}
            ),
            "rebuild_weekly_from_daily must be a boolean",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"]["views"].append(
                deepcopy(value["growth_chart"]["views"][0])
            ),
            "Duplicate Studio growth view ids",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"]["measures"][0].update(
                {"series_type": "pie"}
            ),
            "measure series_type is invalid",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"]["views"][0].update(
                {"dimension_column": "missing"}
            ),
            "dimension_column must be declared in columns",
        ),
        (
            "ranking",
            lambda value: value["growth_chart"].update(
                {"default_granularity": "weekly"}
            ),
            "ranking growth_chart must not configure granularity",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"].update({"unknown": True}),
            "growth_chart has unsupported fields: unknown",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"].update({"default_view": "missing"}),
            "default_view must reference a configured view",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"]["export_aliases"].update(
                {"value_usd": "raw_column"}
            ),
            "export_aliases must map export columns to supported semantic values",
        ),
        (
            "timeseries",
            lambda value: value["growth_chart"]["export_aliases"].pop("category"),
            "export_aliases and export_constants must cover every export column",
        ),
    ],
)
def test_registry_rejects_invalid_growth_chart_config(kind, mutation, message):
    dashboard_value = dashboard(data_mode="generated")
    value = growth_metric(kind)
    mutation(value)

    with pytest.raises(ValueError, match=message):
        validate_studio_registry(
            [dashboard_value],
            [value],
            validate_generated_data=False,
        )


def test_compact_counter_section_renders_shared_controls_and_hidden_heading():
    dashboards, metrics = compact_counter_registry()
    normalized_dashboards, normalized_metrics = validate_studio_registry(
        dashboards,
        metrics,
        validate_generated_data=False,
    )
    dashboard_model = StudioDashboard(normalized_dashboards[0])
    metric_models = [StudioMetric(value) for value in normalized_metrics]

    html = render_studio_dashboard(
        dashboard_model,
        [dashboard_model],
        metric_models,
        {
            "meta": {
                "status": "live",
                "last_refreshed": "2026-07-30T12:00:00Z",
            },
            "sources": {},
        },
        studio_js_version="test",
        echarts_js_version="test",
    )

    assert '<section class="studio-dashboard-hero">' not in html
    assert 'class="studio-dashboard-section studio-section-summary"' in html
    assert "studio-section-heading-hidden" not in html
    assert '<h2 class="visually-hidden" id="studio-section-summary">Summary</h2>' in html
    assert 'data-studio-section-utility="summary"' in html
    assert html.count('data-methodology-open="campaign_summary"') == 1
    assert 'aria-label="Inspect methodology for Campaign Summary"' in html
    assert html.count('data-metric-export="campaign_summary"') == 1
    assert "studio-metric-grid studio-metric-grid-columns-2" in html
    assert 'data-grid-columns="2"' in html
    card = re.search(
        r'(<article[^>]+data-studio-metric-id="campaign_summary".*?</article>)',
        html,
    )
    assert card
    assert "studio-counter-compact" in card.group(1)
    assert "studio-metric-actions" not in card.group(1)
    assert "data-methodology-open" not in card.group(1)
    assert "data-metric-export" not in card.group(1)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda dashboards, metrics: dashboards[0]["sections"][0].update(
                {"grid_columns": 0}
            ),
            "grid_columns must be an integer from 1 through 4",
        ),
        (
            lambda dashboards, metrics: metrics[0]["period_key_map"].update(
                {"INVALID": "invalid_data"}
            ),
            "period_key_map has unsupported ranges",
        ),
        (
            lambda dashboards, metrics: metrics[0]["export_column_aliases"].update(
                {"missing": "renamed"}
            ),
            "export_column_aliases references columns outside export_columns",
        ),
        (
            lambda dashboards, metrics: metrics[0]["methodology"].update(
                {"metric_definitions": []}
            ),
            "metric_definitions must be a non-empty string list",
        ),
    ],
)
def test_registry_rejects_invalid_compact_counter_section_contract(
    mutation,
    message,
):
    dashboards, metrics = compact_counter_registry()
    mutation(dashboards, metrics)

    with pytest.raises(ValueError, match=message):
        validate_studio_registry(
            dashboards,
            metrics,
            validate_generated_data=False,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("destination_top_n", 0, "destination_top_n must be an integer"),
        ("destination_others_label", "", "destination_others_label must be"),
        ("preserve_destinations", ["Exited", "Exited"], "preserved destinations"),
    ],
)
def test_registry_validates_configurable_sankey_destination_aggregation(
    field,
    value,
    message,
):
    dashboard_value = dashboard(data_mode="generated")
    flow = metric("flow", "source")
    flow.update(
        {
            "visualization_type": "sankey",
            "columns": ["source", "destination", "amount"],
            "source_column": "source",
            "target_column": "destination",
            "value_column": "amount",
            "destination_top_n": 5,
            "destination_others_label": "Others",
            "preserve_destinations": ["Exited"],
        }
    )
    flow[field] = value

    with pytest.raises(ValueError, match=message):
        validate_studio_registry(
            [dashboard_value],
            [flow],
            validate_generated_data=False,
        )


def test_query_contract_unions_shared_metric_and_supporting_columns():
    metrics = [
        metric("value_a", "value_a", display_order=1),
        metric("value_b", "value_b", display_order=2),
        metric(
            "trend_value",
            "trend_value",
            query_id=43,
            data_source="trend_result",
            display_order=3,
        ),
    ]
    metrics[0]["comparison_column"] = "change_pct"
    metrics[0]["sparkline_data_source"] = "trend_result"
    metrics[0]["sparkline_column"] = "spark_value"
    metrics[0]["sparkline_date_column"] = "day"

    contracts = build_studio_query_contracts(metrics)

    assert contracts[42]["metric_ids"] == ["value_a", "value_b"]
    assert contracts[42]["required_columns"] == [
        "value_a",
        "change_pct",
        "value_b",
    ]
    assert contracts[43]["required_columns"] == [
        "trend_value",
        "spark_value",
        "day",
    ]
    assert contracts[43]["date_columns"] == ["day"]

    inconsistent = deepcopy(metrics)
    inconsistent[1]["data_source"] = "another_source"
    with pytest.raises(ValueError, match="inconsistent data_source"):
        build_studio_query_contracts(inconsistent)


def test_registry_normalizes_richer_column_and_freshness_metadata():
    dashboard_value = dashboard()
    dashboard_value["freshness_policy"] = {
        "expected_refresh_hours": 6,
        "warning_after_hours": 12,
        "stale_after_hours": 24,
    }
    metric_value = metric("value_a", "value_a")
    metric_value.update(
        {
            "source_label": "  Query methodology  ",
            "optional_columns": ["cohort"],
            "dimension_columns": ["cohort"],
            "value_columns": ["value_a"],
            "freshness_policy": {"warning_after_hours": 10},
        }
    )

    normalized_dashboards, normalized_metrics = normalize_studio_registry(
        [dashboard_value],
        [metric_value],
    )

    assert normalized_dashboards[0]["freshness_policy"] == {
        "expected_refresh_hours": 6,
        "warning_after_hours": 12,
        "stale_after_hours": 24,
    }
    assert normalized_dashboards[0]["stale_after_hours"] == 24
    assert normalized_metrics[0]["source_label"] == "Query methodology"
    assert normalized_metrics[0]["optional_columns"] == ["cohort"]
    assert normalized_metrics[0]["dimension_columns"] == ["cohort"]
    assert normalized_metrics[0]["value_columns"] == ["value_a"]
    assert normalized_metrics[0]["allow_empty"] is False
    assert normalized_metrics[0]["effective_freshness_policy"] == {
        "expected_refresh_hours": 6,
        "warning_after_hours": 10,
        "stale_after_hours": 24,
    }


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (
            {"expected_refresh_hours": 24, "warning_after_hours": 12},
            "expected_refresh_hours to be no greater",
        ),
        (
            {"stale_after_hours": True},
            "stale_after_hours must be a positive number",
        ),
        (
            {"refresh_every": 6},
            "unsupported fields: refresh_every",
        ),
    ],
)
def test_registry_rejects_invalid_freshness_policies(policy, message):
    dashboard_value = dashboard()
    dashboard_value["freshness_policy"] = policy

    with pytest.raises(ValueError, match=message):
        normalize_studio_registry(
            [dashboard_value],
            [metric("value_a", "value_a")],
        )


def test_query_contract_unions_richer_metadata_and_keeps_metric_provenance():
    first = metric("value_a", "value_a", display_order=1)
    first.update(
        {
            "source_label": "Summary calculation",
            "optional_columns": ["label", "note"],
            "dimension_columns": ["label"],
            "value_columns": ["value_a"],
            "freshness_policy": {
                "expected_refresh_hours": 12,
                "warning_after_hours": 24,
                "stale_after_hours": 48,
            },
        }
    )
    second = metric("value_b", "value_b", display_order=2)
    second.update(
        {
            "columns": ["value_b", "label"],
            "source_label": "Ranking methodology",
            "dimension_columns": ["label"],
            "value_columns": ["value_b"],
            "allow_empty": True,
            "freshness_policy": {
                "expected_refresh_hours": 6,
                "warning_after_hours": 12,
                "stale_after_hours": 24,
            },
        }
    )

    contract = build_studio_query_contracts([first, second])[42]

    assert contract["required_columns"] == ["value_a", "value_b", "label"]
    assert contract["optional_columns"] == ["note"]
    assert contract["dimension_columns"] == ["label"]
    assert contract["value_columns"] == ["value_a", "value_b"]
    assert contract["source_label"] is None
    assert contract["source_labels"] == [
        "Summary calculation",
        "Ranking methodology",
    ]
    assert contract["allow_empty"] is False
    assert contract["freshness_policy"] == {
        "expected_refresh_hours": 6,
        "warning_after_hours": 12,
        "stale_after_hours": 24,
    }
    assert contract["metric_metadata"][0] == {
        "metric_id": "value_a",
        "dashboard_id": "contract_dashboard",
        "visualization_type": "counter",
        "source_label": "Summary calculation",
        "required_columns": ["value_a"],
        "optional_columns": ["label", "note"],
        "date_columns": [],
        "address_columns": [],
        "transaction_columns": [],
        "dimension_columns": ["label"],
        "value_columns": ["value_a"],
        "is_exportable": True,
        "allow_empty": False,
        "provider_mode": "fixture",
        "transformation": None,
        "freshness_policy": {
            "expected_refresh_hours": 12,
            "warning_after_hours": 24,
            "stale_after_hours": 48,
        },
    }


def test_query_contract_reports_detailed_conflicts_and_unsafe_references():
    first = metric("value_a", "value_a", display_order=1)
    second = metric("value_b", "value_b", display_order=2)
    second["data_source"] = "another_source"
    with pytest.raises(
        ValueError,
        match=(
            "inconsistent data_source: metric value_a uses 'shared_result'; "
            "metric value_b uses 'another_source'"
        ),
    ):
        build_studio_query_contracts([first, second])

    duplicate_file = metric(
        "other_query",
        "value_b",
        query_id=43,
        data_source="other_result",
        display_order=2,
    )
    duplicate_file["data_file"] = "query_42.json"
    with pytest.raises(ValueError, match="Duplicate Studio query output filename"):
        build_studio_query_contracts([first, duplicate_file])

    unsafe = deepcopy(first)
    unsafe["optional_columns"] = ["../secret"]
    with pytest.raises(ValueError, match="unsafe column references"):
        build_studio_query_contracts([unsafe])

    undeclared = deepcopy(first)
    undeclared["dimension_columns"] = ["cohort"]
    with pytest.raises(ValueError, match="references undeclared columns: cohort"):
        build_studio_query_contracts([undeclared])


def test_query_contract_unions_date_and_identifier_columns():
    records = metric("records", "value", exportable=True)
    records.update(
        {
            "columns": ["day", "wallet", "tx_hash", "value"],
            "date_column": "day",
            "address_columns": ["wallet"],
            "transaction_columns": ["tx_hash"],
        }
    )

    contract = build_studio_query_contracts([records])[42]

    assert contract["date_columns"] == ["day"]
    assert contract["address_columns"] == ["wallet"]
    assert contract["transaction_columns"] == ["tx_hash"]


def test_query_contract_infers_visualization_semantic_roles_additively():
    counter = metric("counter", "total", query_id=41, data_source="counter_data")
    counter["columns"] = ["key_", "total", "change_pct"]
    counter["value_column"] = "total"
    counter["period_key_column"] = "key_"
    counter["period_key_map"] = {"ALL": "all_time_data"}
    counter["comparison_column"] = "change_pct"

    line = metric("line", "day", query_id=42, data_source="line_data")
    line.update(
        {
            "visualization_type": "line",
            "columns": ["day", "cohort", "deposits", "withdrawals", "fees"],
            "date_column": "day",
            "series": [
                {"column": "deposits", "label": "Deposits"},
                {"column": "withdrawals", "label": "Withdrawals"},
            ],
            "dimension_columns": ["cohort"],
            "value_columns": ["fees"],
        }
    )

    bar = metric("bar", "category", query_id=43, data_source="bar_data")
    bar.update(
        {
            "visualization_type": "bar",
            "columns": ["category", "amount"],
            "category_column": "category",
            "value_column": "amount",
        }
    )

    sankey = metric("flow", "source", query_id=44, data_source="flow_data")
    sankey.update(
        {
            "visualization_type": "sankey",
            "columns": ["source", "target", "amount"],
            "source_column": "source",
            "target_column": "target",
            "value_column": "amount",
        }
    )

    table = metric("table", "day", query_id=45, data_source="table_data")
    table.update(
        {
            "visualization_type": "table",
            "columns": [
                "day",
                "wallet",
                "tx_hash",
                "chain",
                "rank",
                "amount",
                "label",
            ],
            "date_column": "day",
            "address_columns": ["wallet"],
            "transaction_columns": ["tx_hash"],
            "chain_column": "chain",
            "column_formats": {
                "rank": "integer",
                "amount": "currency",
                "label": "text",
            },
        }
    )

    contracts = build_studio_query_contracts([counter, line, bar, sankey, table])

    assert contracts[41]["dimension_columns"] == ["key_"]
    assert contracts[41]["value_columns"] == ["total", "change_pct"]
    assert contracts[42]["dimension_columns"] == ["cohort", "day"]
    assert contracts[42]["value_columns"] == [
        "fees",
        "deposits",
        "withdrawals",
    ]
    assert contracts[43]["dimension_columns"] == ["category"]
    assert contracts[43]["value_columns"] == ["amount"]
    assert contracts[44]["dimension_columns"] == ["source", "target"]
    assert contracts[44]["value_columns"] == ["amount"]
    assert contracts[45]["dimension_columns"] == [
        "day",
        "wallet",
        "tx_hash",
        "chain",
    ]
    assert contracts[45]["value_columns"] == ["rank", "amount"]


def test_sparkline_source_requires_and_validates_its_date_column(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_json(
        data_dir / "contract.json",
        {
            "meta": {
                "dashboard_id": "contract_dashboard",
                "status": "demo",
                "last_refreshed": GENERATED_AT,
            },
            "datasets": {
                "shared_result": [{"value_a": 1}],
                "trend_result": [{"spark_value": 2}],
            },
        },
    )
    summary_metric = metric("value_a", "value_a", display_order=1)
    summary_metric.update(
        {
            "sparkline_data_source": "trend_result",
            "sparkline_column": "spark_value",
            "sparkline_date_column": "day",
        }
    )
    trend_metric = metric(
        "trend_source",
        "spark_value",
        query_id=43,
        data_source="trend_result",
        display_order=2,
    )

    with pytest.raises(ValueError, match="sparkline source trend_result is missing"):
        validate_studio_registry(
            [dashboard()],
            [summary_metric, trend_metric],
            data_dir=data_dir,
        )

    missing_date_mapping = deepcopy(summary_metric)
    del missing_date_mapping["sparkline_date_column"]
    with pytest.raises(ValueError, match="needs sparkline_date_column"):
        validate_studio_registry(
            [dashboard()],
            [missing_date_mapping, trend_metric],
            data_dir=data_dir,
        )


def test_manifest_accepts_empty_bootstrap_and_validates_registry_requirements():
    bootstrap = validate_studio_generated_manifest(
        {
            "schema_version": STUDIO_DATA_SCHEMA_VERSION,
            "generated_at": None,
            "queries": [],
        }
    )
    assert bootstrap["queries"] == []

    metrics = [
        metric("value_a", "value_a", display_order=1),
        metric("value_b", "value_b", display_order=2),
    ]
    contracts = build_studio_query_contracts(metrics)
    entry = manifest_entry(columns=["value_a", "value_b"])
    validated = validate_studio_generated_manifest(
        {
            "schema_version": STUDIO_DATA_SCHEMA_VERSION,
            "generated_at": GENERATED_AT,
            "queries": [entry],
        },
        query_contracts=contracts,
        required_query_ids={42},
    )
    assert validated["queries"][0]["query_id"] == 42

    missing_column = deepcopy(entry)
    missing_column["columns"] = ["value_a"]
    with pytest.raises(ValueError, match="missing required columns: value_b"):
        validate_studio_generated_manifest(
            {
                "schema_version": STUDIO_DATA_SCHEMA_VERSION,
                "generated_at": GENERATED_AT,
                "queries": [missing_column],
            },
            query_contracts=contracts,
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload.update({"schema_version": 2}),
            "schema_version must be 1",
        ),
        (
            lambda payload: payload.update({"generated_at": "2026-07-30T12:00:00"}),
            "generated_at must include a timezone",
        ),
        (
            lambda payload: payload["queries"][0].update(
                {"data_file": "../query_42.json"}
            ),
            "data_file must be query_42.json",
        ),
        (
            lambda payload: payload["queries"][0].update(
                {"query_url": "https://example.com/42"}
            ),
            "query_url does not match query_id",
        ),
        (
            lambda payload: payload["queries"][0].pop("query_url"),
            "needs query_url",
        ),
        (
            lambda payload: payload["queries"][0].update(
                {"columns": ["value_a", "value_a"]}
            ),
            "Duplicate Studio columns",
        ),
        (
            lambda payload: payload["queries"][0].update(
                {"status": "empty", "row_count": 1}
            ),
            "empty status requires row_count 0",
        ),
        (
            lambda payload: payload["queries"].append(
                manifest_entry(data_file="query_42.json")
            ),
            "Duplicate Studio generated query IDs",
        ),
    ],
)
def test_manifest_rejects_invalid_metadata(mutate, message):
    payload = {
        "schema_version": STUDIO_DATA_SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "queries": [manifest_entry()],
    }
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        validate_studio_generated_manifest(payload)


def test_failed_query_cannot_power_exportable_metrics():
    contracts = build_studio_query_contracts(
        [metric("value_a", "value_a", exportable=True)]
    )
    failed = manifest_entry(
        columns=["value_a"],
        status="failed",
        row_count=0,
        error="Dune execution failed.",
    )
    with pytest.raises(ValueError, match="failed but powers exportable metrics"):
        validate_studio_generated_manifest(
            {
                "schema_version": STUDIO_DATA_SCHEMA_VERSION,
                "generated_at": GENERATED_AT,
                "queries": [failed],
            },
            query_contracts=contracts,
        )


def test_demo_error_source_cannot_power_an_exportable_metric(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_json(
        data_dir / "contract.json",
        {
            "meta": {
                "dashboard_id": "contract_dashboard",
                "status": "demo",
                "last_refreshed": GENERATED_AT,
            },
            "datasets": {
                "shared_result": {
                    "error": "The configured demo source failed."
                }
            },
        },
    )

    with pytest.raises(ValueError, match="exportable metric value_a has no row data"):
        validate_studio_registry(
            [dashboard()],
            [metric("value_a", "value_a", exportable=True)],
            data_dir=data_dir,
        )


def test_query_result_is_self_describing_and_agrees_with_manifest():
    entry = manifest_entry(columns=["value_a", "value_b"])
    result = query_result(entry, [{"value_a": 1, "value_b": 2}])

    assert validate_studio_query_result(result, entry)["rows"] == [
        {"value_a": 1, "value_b": 2}
    ]

    mismatched_time = deepcopy(result)
    mismatched_time["generated_at"] = "2026-07-30T13:00:00Z"
    with pytest.raises(ValueError, match="generated_at does not match"):
        validate_studio_query_result(mismatched_time, entry)

    mismatched_execution = deepcopy(result)
    mismatched_execution["execution_id"] = "different-execution"
    with pytest.raises(ValueError, match="execution_id does not match"):
        validate_studio_query_result(mismatched_execution, entry)

    missing_execution = deepcopy(result)
    del missing_execution["execution_id"]
    with pytest.raises(ValueError, match="valid execution_id"):
        validate_studio_query_result(missing_execution, entry)

    manifest_without_execution = deepcopy(entry)
    del manifest_without_execution["execution_id"]
    with pytest.raises(ValueError, match="valid execution_id"):
        validate_studio_generated_manifest(
            {
                "schema_version": STUDIO_DATA_SCHEMA_VERSION,
                "generated_at": GENERATED_AT,
                "queries": [manifest_without_execution],
            }
        )

    missing = query_result(entry, [{"value_a": 1}])
    with pytest.raises(ValueError, match="missing declared columns: value_b"):
        validate_studio_query_result(missing, entry)

    undeclared = query_result(
        entry,
        [{"value_a": 1, "value_b": 2, "extra": 3}],
    )
    with pytest.raises(ValueError, match="undeclared columns: extra"):
        validate_studio_query_result(undeclared, entry)


def test_empty_query_result_is_valid_and_keeps_declared_columns():
    entry = manifest_entry(
        columns=["day", "value"],
        status="empty",
        row_count=0,
    )
    result = query_result(entry, [])

    validated_manifest = validate_studio_generated_manifest(
        {
            "schema_version": STUDIO_DATA_SCHEMA_VERSION,
            "generated_at": GENERATED_AT,
            "queries": [entry],
        }
    )
    validated_result = validate_studio_query_result(result, entry)

    assert validated_manifest["queries"][0]["columns"] == ["day", "value"]
    assert validated_result["rows"] == []


def test_delayed_query_freshness_is_valid_and_propagates_to_dashboard(tmp_path):
    generated_dir = tmp_path / "generated"
    entry = manifest_entry(
        columns=["value_a"],
        freshness_status="delayed",
    )
    write_generated_contract(generated_dir, [(entry, [{"value_a": 1}])])
    normalized_dashboards, normalized_metrics = validate_studio_registry(
        [dashboard(data_mode="generated")],
        [metric("value_a", "value_a")],
        data_dir=tmp_path / "unused-demo-data",
        generated_data_dir=generated_dir,
    )

    payload = load_studio_data(
        StudioDashboard(normalized_dashboards[0]),
        metrics=[StudioMetric(normalized_metrics[0])],
        generated_data_dir=generated_dir,
    )

    assert payload["sources"]["shared_result"]["freshness_status"] == "delayed"
    assert payload["meta"]["freshness_status"] == "delayed"


def test_contract_allow_empty_policy_protects_exportable_metrics():
    exportable_metric = metric("value_a", "value_a", exportable=True)
    contracts = build_studio_query_contracts([exportable_metric])
    empty = manifest_entry(
        columns=["value_a"],
        status="empty",
        row_count=0,
    )

    with pytest.raises(
        ValueError,
        match="empty but powers metrics that do not allow empty results: value_a",
    ):
        validate_studio_generated_manifest(
            {
                "schema_version": STUDIO_DATA_SCHEMA_VERSION,
                "generated_at": GENERATED_AT,
                "queries": [empty],
            },
            query_contracts=contracts,
        )

    explicitly_allowed = deepcopy(exportable_metric)
    explicitly_allowed["allow_empty"] = True
    allowed_contracts = build_studio_query_contracts([explicitly_allowed])
    validated = validate_studio_generated_manifest(
        {
            "schema_version": STUDIO_DATA_SCHEMA_VERSION,
            "generated_at": GENERATED_AT,
            "queries": [empty],
        },
        query_contracts=allowed_contracts,
    )
    assert validated["queries"][0]["status"] == "empty"


def test_schema_v1_accepts_and_validates_optional_richer_query_metadata():
    metric_value = metric("value_a", "value_a")
    metric_value.update(
        {
            "source_label": "Query methodology",
            "optional_columns": ["cohort"],
            "dimension_columns": ["cohort"],
            "value_columns": ["value_a"],
            "freshness_policy": {
                "expected_refresh_hours": 6,
                "warning_after_hours": 12,
                "stale_after_hours": 24,
            },
        }
    )
    contracts = build_studio_query_contracts([metric_value])
    entry = manifest_entry(columns=["value_a"])
    entry.update(
        {
            "source_label": "Query methodology",
            "optional_columns": ["cohort"],
            "dimension_columns": ["cohort"],
            "value_columns": ["value_a"],
            "allow_empty": False,
            "freshness_policy": {
                "expected_refresh_hours": 6,
                "warning_after_hours": 12,
                "stale_after_hours": 24,
            },
        }
    )
    result = query_result(entry, [{"value_a": 1}])

    validated_manifest = validate_studio_generated_manifest(
        {
            "schema_version": STUDIO_DATA_SCHEMA_VERSION,
            "generated_at": GENERATED_AT,
            "queries": [entry],
        },
        query_contracts=contracts,
    )
    assert validated_manifest["queries"][0]["optional_columns"] == ["cohort"]
    assert validate_studio_query_result(result, entry)["rows"] == [
        {"value_a": 1}
    ]

    lean_result = deepcopy(result)
    for field in (
        "source_label",
        "optional_columns",
        "dimension_columns",
        "value_columns",
        "allow_empty",
        "freshness_policy",
    ):
        del lean_result[field]
    assert validate_studio_query_result(lean_result, entry)["rows"] == [
        {"value_a": 1}
    ]

    result_with_mismatched_policy = deepcopy(result)
    result_with_mismatched_policy["freshness_policy"]["stale_after_hours"] = 25
    with pytest.raises(ValueError, match="freshness_policy does not match"):
        validate_studio_query_result(result_with_mismatched_policy, entry)


def test_file_loaders_report_missing_and_malformed_generated_files(tmp_path):
    missing_manifest = tmp_path / "missing-manifest.json"
    with pytest.raises(ValueError, match="Missing Studio generated manifest"):
        load_studio_generated_manifest(missing_manifest)

    malformed_manifest = tmp_path / "manifest.json"
    malformed_manifest.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed Studio generated manifest"):
        load_studio_generated_manifest(malformed_manifest)

    entry = manifest_entry(columns=["value_a"])
    missing_result = tmp_path / "query_42.json"
    with pytest.raises(ValueError, match="Missing Studio query result file"):
        load_studio_query_result(missing_result, entry)

    missing_result.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed Studio query result file"):
        load_studio_query_result(missing_result, entry)


def test_generated_mode_loads_one_shared_query_for_multiple_metrics(tmp_path):
    generated_dir = tmp_path / "generated"
    entry = manifest_entry(
        columns=["value_a", "value_b"],
        freshness_status="stale",
    )
    write_generated_contract(
        generated_dir,
        [(entry, [{"value_a": 10, "value_b": 20}])],
    )
    manifest_payload = json.loads(
        (generated_dir / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_payload.update(
        {
            "mode": "fixture",
            "source": "local_fixture",
            "data_updated_at": FINISHED_AT,
            "display_updated_at": FINISHED_AT,
            "last_checked_at": GENERATED_AT,
            "last_successful_fetch_at": GENERATED_AT,
        }
    )
    write_json(generated_dir / "manifest.json", manifest_payload)
    dashboard_value = dashboard(data_mode="generated")
    metric_values = [
        metric("value_a", "value_a", display_order=1),
        metric("value_b", "value_b", display_order=2),
    ]

    normalized_dashboards, normalized_metrics = validate_studio_registry(
        [dashboard_value],
        metric_values,
        data_dir=tmp_path / "unused-demo-data",
        generated_data_dir=generated_dir,
    )
    dashboard_model = StudioDashboard(normalized_dashboards[0])
    metric_models = [StudioMetric(value) for value in normalized_metrics]
    payload = load_studio_data(
        dashboard_model,
        metrics=metric_models,
        generated_data_dir=generated_dir,
    )

    assert payload["datasets"] == {
        "shared_result": [{"value_a": 10, "value_b": 20}]
    }
    assert payload["sources"]["shared_result"]["query_id"] == 42
    assert payload["meta"]["last_refreshed"] == FINISHED_AT
    assert payload["meta"]["generated_at"] == GENERATED_AT
    assert payload["meta"]["data_updated_at"] == FINISHED_AT
    assert payload["meta"]["display_updated_at"] == FINISHED_AT
    assert payload["meta"]["sample_data"] is True
    assert payload["meta"]["mode"] == "fixture"
    assert payload["meta"]["freshness_status"] == "stale"


def test_generated_dashboard_uses_oldest_required_source_update_timestamp(
    tmp_path,
):
    generated_dir = tmp_path / "generated"
    first_entry = manifest_entry(query_id=42, columns=["value_a"])
    first_entry.update(
        {
            "execution_finished_at": "2026-07-30T11:40:00Z",
            "data_updated_at": "2026-07-30T09:15:00Z",
        }
    )
    second_entry = manifest_entry(query_id=43, columns=["value_b"])
    second_entry["execution_finished_at"] = "2026-07-30T10:30:00Z"
    write_generated_contract(
        generated_dir,
        [
            (first_entry, [{"value_a": 1}]),
            (second_entry, [{"value_b": 2}]),
        ],
    )
    manifest_payload = json.loads(
        (generated_dir / "manifest.json").read_text(encoding="utf-8")
    )
    manifest_payload.update(
        {
            "data_updated_at": "2026-07-29T01:00:00Z",
            "display_updated_at": "2026-07-30T11:59:00Z",
        }
    )
    write_json(generated_dir / "manifest.json", manifest_payload)

    metric_values = [
        metric("value_a", "value_a", display_order=1),
        metric(
            "value_b",
            "value_b",
            query_id=43,
            data_source="other_result",
            display_order=2,
        ),
    ]
    normalized_dashboards, normalized_metrics = validate_studio_registry(
        [dashboard(data_mode="generated")],
        metric_values,
        data_dir=tmp_path / "unused-demo-data",
        generated_data_dir=generated_dir,
    )

    payload = load_studio_data(
        StudioDashboard(normalized_dashboards[0]),
        metrics=[StudioMetric(value) for value in normalized_metrics],
        generated_data_dir=generated_dir,
    )

    expected = "2026-07-30T09:15:00Z"
    assert payload["meta"]["last_refreshed"] == expected
    assert payload["meta"]["data_updated_at"] == expected
    assert payload["meta"]["display_updated_at"] == expected


def test_global_generated_manifest_allows_registered_queries_for_other_dashboards(
    tmp_path,
):
    generated_dir = tmp_path / "generated"
    first_entry = manifest_entry(query_id=42, columns=["value_a"])
    second_entry = manifest_entry(query_id=43, columns=["value_b"])
    write_generated_contract(
        generated_dir,
        [
            (first_entry, [{"value_a": 1}]),
            (second_entry, [{"value_b": 2}]),
        ],
    )
    first_dashboard = dashboard(data_mode="generated")
    second_dashboard = deepcopy(first_dashboard)
    second_dashboard.update(
        {
            "id": "other_dashboard",
            "slug": "other",
            "name": "Other Dashboard",
            "data_file": "other.json",
            "display_order": 2,
        }
    )
    first_metric = metric("value_a", "value_a")
    second_metric = metric(
        "value_b",
        "value_b",
        query_id=43,
        data_source="other_result",
    )
    second_metric["dashboard_id"] = "other_dashboard"

    normalized_dashboards, normalized_metrics = validate_studio_registry(
        [first_dashboard, second_dashboard],
        [first_metric, second_metric],
        data_dir=tmp_path / "unused-demo-data",
        generated_data_dir=generated_dir,
    )
    first_payload = load_studio_data(
        StudioDashboard(normalized_dashboards[0]),
        metrics=[StudioMetric(normalized_metrics[0])],
        generated_data_dir=generated_dir,
    )

    assert first_payload["datasets"] == {
        "shared_result": [{"value_a": 1}]
    }
    assert set(first_payload["sources"]) == {"shared_result"}


def test_generated_state_resolves_active_immutable_snapshot_for_registry_and_build(
    tmp_path,
):
    generated_dir = tmp_path / "generated"
    snapshot_dir = generated_dir / "snapshots" / "snapshot_20260730"
    entry = manifest_entry(columns=["value_a"])
    write_generated_contract(snapshot_dir, [(entry, [{"value_a": 10}])])
    write_json(
        snapshot_dir / "raw_query_42.json",
        {
            "query_id": 42,
            "execution_id": "fixture-42",
            "columns": ["value_a"],
            "rows": [{"value_a": 10}],
        },
    )
    write_json(
        generated_dir / "state.json",
        {
            "schema_version": 2,
            "current_snapshot_id": "snapshot_20260730",
            "previous_snapshot_id": "snapshot_20260729",
            "current_manifest_checksum": "abc123",
            "last_checked_at": GENERATED_AT,
            "latest_attempt_id": "attempt-internal-only",
            "latest_attempt_status": "failed",
            "using_previous": True,
            "latest_failure": {
                "failed_query_ids": [43],
                "categories": ["provider_failure"],
                "summary": "One query failed.",
                "private_detail": "do not publish",
            },
            "private_state": "do not publish",
        },
    )

    assert resolve_studio_generated_data_dir(generated_dir) == snapshot_dir
    normalized_dashboards, normalized_metrics = validate_studio_registry(
        [dashboard(data_mode="generated")],
        [metric("value_a", "value_a")],
        data_dir=tmp_path / "unused-demo-data",
        generated_data_dir=generated_dir,
    )
    payload = load_studio_data(
        StudioDashboard(normalized_dashboards[0]),
        metrics=[StudioMetric(normalized_metrics[0])],
        generated_data_dir=generated_dir,
    )
    assert payload["datasets"] == {"shared_result": [{"value_a": 10}]}

    output_dir = tmp_path / "published"
    written = publish_studio_generated_data(generated_dir, output_dir)
    assert {path.name for path in written} == {
        "manifest.json",
        "query_42.json",
        "refresh_status.json",
    }
    assert not (output_dir / "raw_query_42.json").exists()
    refresh_status = json.loads(
        (output_dir / "refresh_status.json").read_text(encoding="utf-8")
    )
    assert refresh_status["latest_attempt_status"] == "failed"
    assert refresh_status["latest_failure"] == {
        "failed_query_ids": [43],
        "categories": ["provider_failure"],
        "summary": "One query failed.",
    }
    assert "latest_attempt_id" not in refresh_status
    assert "private_state" not in refresh_status


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (
            {"schema_version": 1, "current_snapshot_id": "snapshot_1"},
            "state schema_version must be 2",
        ),
        (
            {"schema_version": 2, "current_snapshot_id": "../snapshot_1"},
            "current_snapshot_id must be a safe snapshot ID",
        ),
        (
            {"schema_version": 2, "current_snapshot_id": "missing_snapshot"},
            "Missing active Studio generated snapshot",
        ),
    ],
)
def test_generated_state_rejects_invalid_or_missing_snapshot(tmp_path, state, message):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    write_json(generated_dir / "state.json", state)

    with pytest.raises(ValueError, match=message):
        resolve_studio_generated_data_dir(generated_dir)


def test_registry_can_validate_generated_configuration_without_active_snapshot(
    tmp_path,
):
    dashboard_value = dashboard(data_mode="generated")
    metric_value = metric("value_a", "value_a")
    normalized_dashboards, normalized_metrics = validate_studio_registry(
        [dashboard_value],
        [metric_value],
        data_dir=tmp_path / "unused-demo-data",
        generated_data_dir=tmp_path / "missing-generated-data",
        validate_generated_data=False,
    )
    assert normalized_dashboards[0]["data_mode"] == "generated"
    assert normalized_metrics[0]["query_id"] == 42

    studio_dir = tmp_path / "studio"
    studio_dir.mkdir()
    write_json(studio_dir / "dashboards.yaml", {"dashboards": [dashboard_value]})
    write_json(studio_dir / "metrics.yaml", {"metrics": [metric_value]})
    dashboards, metrics = load_studio_registry(
        studio_dir,
        generated_data_dir=tmp_path / "missing-generated-data",
        validate_generated_data=False,
    )
    assert dashboards[0].id == "contract_dashboard"
    assert metrics[0].id == "value_a"

    with pytest.raises(ValueError, match="Missing Studio generated manifest"):
        load_studio_registry(
            studio_dir,
            generated_data_dir=tmp_path / "missing-generated-data",
        )


@pytest.mark.parametrize("data_mode", ["demo", "generated"])
def test_rendered_config_contains_mode_specific_source_descriptors(data_mode):
    dashboard_value = dashboard(
        data_mode=data_mode,
        stale_after_hours=36,
    )
    metric_value = metric("value_a", "value_a")
    normalized_dashboards, normalized_metrics = normalize_studio_registry(
        [dashboard_value],
        [metric_value],
    )
    dashboard_model = StudioDashboard(normalized_dashboards[0])
    metric_model = StudioMetric(normalized_metrics[0])
    data_payload = {
        "meta": {
            "dashboard_id": "contract_dashboard",
            "status": dashboard_value["status"],
            "last_refreshed": GENERATED_AT,
            "freshness_status": "current",
        },
        "datasets": {"shared_result": [{"value_a": 1}]},
        "sources": {
            "shared_result": manifest_entry(columns=["value_a"])
        },
    }
    html = render_studio_dashboard(
        dashboard_model,
        [dashboard_model],
        [metric_model],
        data_payload,
        studio_js_version="test",
        echarts_js_version="test",
    )
    match = re.search(
        r'<script type="application/json" data-studio-config>(.*?)</script>',
        html,
    )
    assert match
    config = json.loads(unescape(match.group(1)))
    source = config["dataSources"]["shared_result"]

    assert config["dataMode"] == data_mode
    assert config["dataUrl"] == (
        None if data_mode == "generated" else "../data/contract.json"
    )
    assert source["queryId"] == 42
    assert source["expectedColumns"] == ["value_a"]
    assert source["staleAfterHours"] == 36
    assert f'data-studio-last-updated="{GENERATED_AT}"' in html
    if data_mode == "generated":
        assert source["kind"] == "generated_query"
        assert config["manifestUrl"] == (
            "../../data/studio/generated/manifest.json"
        )
        assert source["url"] == (
            "../../data/studio/generated/query_42.json"
        )
        assert "dataset" not in source
    else:
        assert source["kind"] == "demo_bundle"
        assert config["manifestUrl"] is None
        assert source["url"] == "../data/contract.json"
        assert source["dataset"] == "shared_result"


def test_generated_config_deduplicates_registry_driven_derived_source_descriptor():
    dashboard_value = dashboard(data_mode="generated", stale_after_hours=36)
    source_specs = [
        (8199058, "attributed_holdings", "balance"),
        (8204345, "referral_deposit_events", "deposit_amount"),
        (8204373, "etherfi_activity_events", "activity_amount"),
    ]
    metric_values = []
    source_metadata = {}
    for display_order, (query_id, source_name, column) in enumerate(
        source_specs,
        start=1,
    ):
        metric_value = metric(
            f"derived_input_{display_order}",
            column,
            query_id=query_id,
            data_source=source_name,
            display_order=display_order,
        )
        metric_value["derived_data_source"] = "kyberswap_depositor_intelligence"
        metric_values.append(metric_value)
        source_metadata[source_name] = manifest_entry(
            query_id=query_id,
            columns=[column],
        )

    normalized_dashboards, normalized_metrics = normalize_studio_registry(
        [dashboard_value],
        metric_values,
    )
    dashboard_model = StudioDashboard(normalized_dashboards[0])
    html = render_studio_dashboard(
        dashboard_model,
        [dashboard_model],
        [StudioMetric(value) for value in normalized_metrics],
        {
            "meta": {
                "dashboard_id": "contract_dashboard",
                "status": "live",
                "last_refreshed": GENERATED_AT,
                "freshness_status": "current",
            },
            "datasets": {},
            "sources": source_metadata,
        },
        studio_js_version="test",
        echarts_js_version="test",
    )
    match = re.search(
        r'<script type="application/json" data-studio-config>(.*?)</script>',
        html,
    )
    assert match
    config = json.loads(unescape(match.group(1)))
    descriptor = config["dataSources"]["kyberswap_depositor_intelligence"]

    assert descriptor["mode"] == "generated"
    assert descriptor["kind"] == "generated_derived"
    assert descriptor["dataSource"] == "kyberswap_depositor_intelligence"
    assert descriptor["artifactId"] == "kyberswap_depositor_intelligence"
    assert descriptor["dataFile"] == "kyberswap_depositor_intelligence.json"
    assert descriptor["url"] == (
        "../../data/studio/generated/kyberswap_depositor_intelligence.json"
    )
    assert descriptor["sourceQueryIds"] == [8199058, 8204345, 8204373]
    assert descriptor["staleAfterHours"] == 36
    assert list(config["dataSources"]).count(
        "kyberswap_depositor_intelligence"
    ) == 1


@pytest.mark.parametrize("stale_after_hours", [0, -1, True, "24"])
def test_dashboard_rejects_invalid_stale_threshold(
    tmp_path,
    stale_after_hours,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    write_json(
        data_dir / "contract.json",
        {
            "meta": {
                "dashboard_id": "contract_dashboard",
                "status": "demo",
                "last_refreshed": GENERATED_AT,
            },
            "datasets": {"shared_result": [{"value_a": 1}]},
        },
    )
    invalid_dashboard = dashboard()
    invalid_dashboard["stale_after_hours"] = stale_after_hours

    with pytest.raises(ValueError, match="stale_after_hours must be a positive"):
        validate_studio_registry(
            [invalid_dashboard],
            [metric("value_a", "value_a")],
            data_dir=data_dir,
        )


def test_generated_publish_copies_only_validated_allow_list(tmp_path):
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    entry = manifest_entry(columns=["value_a", "value_b"])
    write_generated_contract(
        source_dir,
        [(entry, [{"value_a": 1, "value_b": 2}])],
    )
    (source_dir / "notes.txt").write_text("do not publish", encoding="utf-8")
    write_json(
        source_dir / "query_999.json",
        {"unconfigured": True},
    )
    stale = output_dir / "stale.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    written = publish_studio_generated_data(source_dir, output_dir)

    assert {path.name for path in written} == {
        "manifest.json",
        "query_42.json",
    }
    assert {path.name for path in output_dir.iterdir()} == {
        "manifest.json",
        "query_42.json",
    }


def test_partial_populated_manifest_does_not_replace_previous_output(tmp_path):
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    entry = manifest_entry(columns=["value_a"])
    write_generated_contract(
        source_dir,
        [(entry, [{"value_a": 1}])],
    )
    output_dir.mkdir()
    previous = output_dir / "previous-snapshot.json"
    previous.write_text("preserve me", encoding="utf-8")
    contracts = build_studio_query_contracts(
        [
            metric("value_a", "value_a", display_order=1),
            metric(
                "value_c",
                "value_c",
                query_id=43,
                data_source="another_result",
                display_order=2,
            ),
        ]
    )

    with pytest.raises(ValueError, match="missing query IDs: 43"):
        publish_studio_generated_data(
            source_dir,
            output_dir,
            query_contracts=contracts,
        )

    assert previous.read_text(encoding="utf-8") == "preserve me"
    assert {path.name for path in output_dir.iterdir()} == {
        "previous-snapshot.json"
    }


def test_publish_requires_only_the_explicit_generated_dashboard_query_set(tmp_path):
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    entry = manifest_entry(columns=["value_a"])
    write_generated_contract(
        source_dir,
        [(entry, [{"value_a": 1}])],
    )
    contracts = build_studio_query_contracts(
        [
            metric("value_a", "value_a", display_order=1),
            metric(
                "value_c",
                "value_c",
                query_id=43,
                data_source="another_result",
                display_order=2,
            ),
        ]
    )

    written = publish_studio_generated_data(
        source_dir,
        output_dir,
        query_contracts=contracts,
        required_query_ids={42},
    )

    assert {path.name for path in written} == {
        "manifest.json",
        "query_42.json",
    }


def test_publish_rejects_manifest_queries_absent_from_the_registry(tmp_path):
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    unknown_entry = manifest_entry(query_id=44, columns=["value_a"])
    write_generated_contract(
        source_dir,
        [(unknown_entry, [{"value_a": 1}])],
    )
    output_dir.mkdir()
    previous = output_dir / "previous-snapshot.json"
    previous.write_text("preserve me", encoding="utf-8")
    contracts = build_studio_query_contracts(
        [metric("value_a", "value_a")]
    )

    with pytest.raises(ValueError, match="not mapped in the metric registry"):
        publish_studio_generated_data(
            source_dir,
            output_dir,
            query_contracts=contracts,
            required_query_ids=set(),
        )

    assert previous.read_text(encoding="utf-8") == "preserve me"
