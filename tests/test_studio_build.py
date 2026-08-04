from copy import deepcopy
from datetime import datetime, timezone
from html import unescape
import json
from pathlib import Path
import re
import shutil

import pytest
import yaml

from scripts.build_website import build_site
from scripts.studio_ingestion import (
    DuneLatestResultClient,
    FixtureDuneClient,
    StudioIngestionError,
    load_query_requests,
    refresh_studio_data,
)
from scripts.studio import (
    DEFAULT_STUDIO_DIR,
    STUDIO_RANGE_OPTIONS,
    load_studio_registry,
    validate_studio_registry,
)

@pytest.fixture(scope="module")
def studio_registry():
    dashboards, metrics = load_studio_registry(validate_generated_data=False)
    return dashboards, metrics


@pytest.fixture(scope="module")
def built_site(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("studio-site")
    build_site(output_dir=output_dir)
    return output_dir


def registry_values() -> tuple[list[dict], list[dict]]:
    dashboards_payload = yaml.safe_load(
        (DEFAULT_STUDIO_DIR / "dashboards.yaml").read_text(encoding="utf-8")
    )
    metrics_payload = yaml.safe_load(
        (DEFAULT_STUDIO_DIR / "metrics.yaml").read_text(encoding="utf-8")
    )
    return dashboards_payload["dashboards"], metrics_payload["metrics"]


def test_studio_registry_has_unique_ordered_dashboards_and_metrics(studio_registry):
    dashboards, metrics = studio_registry

    dashboard_ids = [dashboard.id for dashboard in dashboards]
    dashboard_slugs = [dashboard.slug for dashboard in dashboards]
    metric_ids = [metric.id for metric in metrics]

    assert dashboard_ids == ["kyberswap_campaign"]
    assert dashboard_slugs == ["kyberswap"]
    assert next(
        dashboard.data["status"]
        for dashboard in dashboards
        if dashboard.id == "kyberswap_campaign"
    ) == "live"
    assert [dashboard.data["display_order"] for dashboard in dashboards] == sorted(
        dashboard.data["display_order"] for dashboard in dashboards
    )
    assert len(dashboard_ids) == len(set(dashboard_ids))
    assert len(dashboard_slugs) == len(set(dashboard_slugs))
    assert len(metric_ids) == len(set(metric_ids))
    assert metrics


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda dashboards, metrics: dashboards.append(deepcopy(dashboards[0])),
            "Duplicate Studio dashboard ids",
        ),
        (
            lambda dashboards, metrics: dashboards.append(
                {
                    **deepcopy(dashboards[0]),
                    "id": "duplicate_slug_dashboard",
                }
            ),
            "Duplicate Studio dashboard slugs",
        ),
        (
            lambda dashboards, metrics: metrics.append(deepcopy(metrics[0])),
            "Duplicate Studio metric ids",
        ),
        (
            lambda dashboards, metrics: metrics[1].update(
                {"display_order": metrics[0]["display_order"]}
            ),
            "Duplicate Studio metric display orders",
        ),
    ],
)
def test_studio_registry_rejects_duplicate_identifiers_and_orders(mutation, message):
    dashboards, metrics = deepcopy(registry_values())
    mutation(dashboards, metrics)

    with pytest.raises(ValueError, match=message):
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
        )


def test_duplicate_metric_id_error_identifies_field_and_correction():
    dashboards, metrics = deepcopy(registry_values())
    metrics.append(deepcopy(metrics[0]))

    with pytest.raises(ValueError) as exc_info:
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
            validate_generated_data=False,
        )

    message = str(exc_info.value)
    assert "Duplicate Studio metric ids" in message
    assert "field id" in message
    assert "expected correction: assign every metric a unique id" in message


@pytest.mark.parametrize(
    ("metric_id", "field", "invalid_value", "message"),
    [
        (
            "kyber_referral_deposits_growth",
            "date_column",
            "missing_day",
            "date_column must be declared in columns",
        ),
        (
            "kyber_attributed_tvl_by_location",
            "category_column",
            "missing_destination",
            "category_column must be declared in columns",
        ),
        (
            "kyber_attributed_tvl_by_location",
            "value_column",
            "missing_value",
            "value_column must be declared in columns",
        ),
        (
            "kyber_capital_journey",
            "source_column",
            "missing_source",
            "source_column must be declared in columns",
        ),
        (
            "kyber_capital_journey",
            "target_column",
            "missing_target",
            "target_column must be declared in columns",
        ),
        (
            "kyber_capital_journey",
            "value_column",
            "missing_value",
            "value_column must be declared in columns",
        ),
    ],
)
def test_studio_registry_validates_visualization_query_column_mappings(
    metric_id,
    field,
    invalid_value,
    message,
):
    dashboards, metrics = deepcopy(registry_values())
    metric = next(item for item in metrics if item["id"] == metric_id)
    metric[field] = invalid_value

    with pytest.raises(ValueError, match=message):
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
        )


@pytest.mark.parametrize(
    ("metric_id", "mutation", "message"),
    [
        (
            "kyber_referral_deposits_growth",
            lambda metric: metric.update(
                {"allowed_visualizations": ["line", "pie"]}
            ),
            "invalid allowed_visualizations",
        ),
        (
            "kyber_referral_deposits_growth",
            lambda metric: metric.update(
                {
                    "allowed_visualizations": ["line", "area"],
                    "default_visualization": "column",
                }
            ),
            "default_visualization must be allowed",
        ),
        (
            "kyber_recent_referral_deposits",
            lambda metric: metric.update({"transaction_columns": ["missing_tx"]}),
            "transaction_column missing_tx must be declared",
        ),
        (
            "kyber_recent_referral_deposits",
            lambda metric: metric.update(
                {
                    "address_columns": ["address", "tx_hash"],
                    "transaction_columns": ["tx_hash"],
                }
            ),
            "identifier columns must be unambiguous",
        ),
        (
            "kyber_recent_referral_deposits",
            lambda metric: metric.update({"default_chain": "solana"}),
            "unsupported default_chain",
        ),
        (
            "kyber_recent_referral_deposits",
            lambda metric: metric["column_formats"].update(
                {"amount_usd": "abbreviated-money"}
            ),
            "unsupported column formats",
        ),
    ],
)
def test_studio_registry_validates_chart_and_table_interaction_config(
    metric_id,
    mutation,
    message,
):
    dashboards, metrics = deepcopy(registry_values())
    metric = next(item for item in metrics if item["id"] == metric_id)
    mutation(metric)

    with pytest.raises(ValueError, match=message):
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
        )


@pytest.mark.parametrize(
    ("metric_id", "mutation", "expected_field", "expected_query"),
    [
        (
            "kyber_referral_deposits_growth",
            lambda metric: metric.update({"visualization_type": "radar"}),
            "field visualization_type",
            "query 8191379",
        ),
        (
            "kyber_referral_deposits_growth",
            lambda metric: metric.update(
                {"allowed_visualizations": ["line", "radar"]}
            ),
            "field allowed_visualizations",
            "query 8191379",
        ),
        (
            "kyber_referral_deposits_growth",
            lambda metric: metric.update({"format": "approximate"}),
            "field format",
            "query 8191379",
        ),
        (
            "kyber_referral_deposits_growth",
            lambda metric: metric.update({"date_column": "missing_day"}),
            "field date_column",
            "query 8191379",
        ),
        (
            "kyber_referral_deposits_growth",
            lambda metric: metric["series"][0].update(
                {"column": "missing_value"}
            ),
            "field series[0].column",
            "query 8191379",
        ),
        (
            "kyber_recent_referral_deposits",
            lambda metric: metric.update({"address_columns": ["missing_wallet"]}),
            "field address_columns",
            "query 8204345",
        ),
        (
            "kyber_recent_referral_deposits",
            lambda metric: metric.update({"transaction_columns": ["missing_tx"]}),
            "field transaction_columns",
            "query 8204345",
        ),
        (
            "kyber_recent_referral_deposits",
            lambda metric: metric["column_formats"].update(
                {"amount_usd": "approximate"}
            ),
            "field column_formats",
            "query 8204345",
        ),
    ],
)
def test_registry_metric_errors_name_dashboard_metric_query_field_and_correction(
    metric_id,
    mutation,
    expected_field,
    expected_query,
):
    dashboards, metrics = deepcopy(registry_values())
    metric = next(item for item in metrics if item["id"] == metric_id)
    mutation(metric)

    with pytest.raises(ValueError) as exc_info:
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
            validate_generated_data=False,
        )

    message = str(exc_info.value)
    assert "dashboard kyberswap_campaign" in message
    assert f"metric {metric_id}" in message
    assert expected_query in message
    assert expected_field in message
    assert "expected correction:" in message


def test_registry_missing_query_error_names_known_context_and_correction():
    dashboards, metrics = deepcopy(registry_values())
    metric = next(
        item
        for item in metrics
        if item["id"] == "kyber_referral_deposits_growth"
    )
    del metric["query_id"]

    with pytest.raises(ValueError) as exc_info:
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
            validate_generated_data=False,
        )

    message = str(exc_info.value)
    assert "dashboard kyberswap_campaign" in message
    assert "metric kyber_referral_deposits_growth" in message
    assert "query <unknown>" in message
    assert "field query_id" in message
    assert "expected correction:" in message


def test_studio_registry_validates_dashboard_dune_url():
    dashboards, metrics = deepcopy(registry_values())
    dashboards[0]["dune_url"] = "https://example.com/not-dune"

    with pytest.raises(ValueError, match="invalid Dune URL"):
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
        )


def test_studio_registry_validates_query_urls():
    dashboards, metrics = deepcopy(registry_values())
    metric = next(
        item
        for item in metrics
        if item["id"] == "kyber_referral_deposits_growth"
    )
    metric["query_url"] = "https://dune.com/queries/123"

    with pytest.raises(ValueError, match="query_url does not match query_id"):
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
        )


def test_one_query_result_can_power_all_eight_counters_through_value_columns(
    studio_registry,
):
    _, metrics = studio_registry
    shared_metrics = [
        metric.data for metric in metrics if metric.data["query_id"] == 8180894
    ]

    shared_by_id = {metric["id"]: metric for metric in shared_metrics}
    expected_ids = {
        "kyber_total_referral_deposits",
        "kyber_attributed_tvl",
        "kyber_new_depositor_deposits",
        "kyber_new_depositor_deposit_rate",
        "kyber_total_depositors",
        "kyber_new_depositors",
        "kyber_retention_rate",
        "kyber_revenue_generated",
    }
    assert expected_ids == set(shared_by_id)
    assert {metric["data_source"] for metric in shared_metrics} == {
        "kyberswap_campaign_summary"
    }
    assert {
        metric_id: shared_by_id[metric_id]["value_column"]
        for metric_id in expected_ids
    } == {
        "kyber_total_referral_deposits": "total_deposits_usd",
        "kyber_attributed_tvl": "outstanding_balance_usd",
        "kyber_new_depositor_deposits": "deposits_by_new_depositors",
        "kyber_new_depositor_deposit_rate": "depositors_new_users_rate",
        "kyber_total_depositors": "num_depositors",
        "kyber_new_depositors": "new_depositors",
        "kyber_retention_rate": "retention_rate",
        "kyber_revenue_generated": "revenue_generated",
    }
    assert all(metric["compact_counter"] for metric in shared_metrics)
    assert {tuple(metric["period_key_map"].items()) for metric in shared_metrics} == {
        (
            ("7D", "7d_data"),
            ("30D", "30d_data"),
            ("90D", "90d_data"),
            ("YTD", "ytd_data"),
            ("1Y", "1y_data"),
            ("ALL", "all_time_data"),
        )
    }


def test_kyberswap_growth_is_six_ordered_two_column_charts_from_four_queries(
    built_site,
    studio_registry,
):
    dashboards, metrics = studio_registry
    dashboard = next(
        item for item in dashboards if item.id == "kyberswap_campaign"
    )
    growth_section = next(
        section for section in dashboard.data["sections"] if section["id"] == "trends"
    )
    growth_metrics = [
        metric.data
        for metric in metrics
        if metric.dashboard_id == dashboard.id and metric.data["section"] == "trends"
    ]
    expected = [
        (
            "kyber_referral_deposits_growth",
            "Referral Deposits",
            "line",
            ["line"],
            "combo",
            8191379,
            "weekly",
            "deposits",
        ),
        (
            "kyber_attributed_tvl_over_time",
            "Attributed TVL Over Time",
            "area",
            ["area", "line"],
            "timeseries",
            8191704,
            "weekly",
            "all",
        ),
        (
            "kyber_referral_deposits_breakdown",
            "Referral Deposits Breakdown",
            "column",
            ["column"],
            "timeseries",
            8193003,
            "weekly",
            "product",
        ),
        (
            "kyber_total_referral_deposits_breakdown",
            "Total Referral Deposits Breakdown",
            None,
            None,
            "ranking",
            8193003,
            None,
            "product",
        ),
        (
            "kyber_deposit_depositor_count_by_product",
            "Deposit & Depositor Count by Product",
            "column",
            ["column", "line"],
            "timeseries",
            8193040,
            "weekly",
            "deposits",
        ),
        (
            "kyber_deposit_depositor_count_by_depositor_type",
            "Deposit & Depositor Count by Depositor Type",
            "column",
            ["column", "line"],
            "timeseries",
            8193040,
            "weekly",
            "deposits",
        ),
    ]

    assert growth_section["label"] == "Campaign Growth & Activity"
    assert growth_section["description"] == (
        "Referral deposits, attributed TVL, product mix, and depositor activity "
        "over time."
    )
    assert growth_section["show_description"] is False
    assert growth_section["grid_columns"] == 2
    assert [
        (
            metric["id"],
            metric["name"],
            metric.get("default_visualization"),
            metric.get("allowed_visualizations"),
            metric["growth_chart"]["kind"],
            metric["query_id"],
            metric["growth_chart"].get("default_granularity"),
            metric["growth_chart"]["default_view"],
        )
        for metric in growth_metrics
    ] == expected
    assert {metric["query_id"] for metric in growth_metrics} == {
        8191379,
        8191704,
        8193003,
        8193040,
    }
    assert all(metric["size"] == "medium" for metric in growth_metrics)
    assert all(metric["methodology"] for metric in growth_metrics)
    assert all(metric["source_label"] == "Methodology" for metric in growth_metrics)
    assert {metric["transformation"]["id"] for metric in growth_metrics} == {
        "kyberswap_growth_deposits",
        "kyberswap_growth_attributed_tvl",
        "kyberswap_growth_breakdown",
        "kyberswap_growth_activity",
    }
    assert growth_metrics[0]["growth_chart"]["range_date_column"] == "observation_day"
    assert growth_metrics[1]["growth_chart"]["range_date_column"] == "observation_day"
    assert growth_metrics[2]["growth_chart"]["rebuild_weekly_from_daily"] is True
    assert growth_metrics[4]["growth_chart"]["views"][0]["record_types"] == {
        "daily": "day_product_deposits",
        "weekly": "week_product_deposits",
    }
    assert growth_metrics[5]["growth_chart"]["views"][0]["record_types"] == {
        "daily": "day_depositor_type_deposits",
        "weekly": "week_depositor_type_deposits",
    }

    html = (built_site / "studio" / "kyberswap" / "index.html").read_text(
        encoding="utf-8"
    )
    section_match = re.search(
        r'(<section class="[^"]*studio-section-trends[^"]*"[^>]*'
        r'data-studio-section="trends".*?</section>)',
        html,
        re.DOTALL,
    )
    assert section_match
    section_html = section_match.group(1)
    assert "studio-metric-grid studio-metric-grid-columns-2" in section_html
    assert 'data-grid-columns="2"' in section_html
    readable_section_html = unescape(section_html)
    assert '<h2 id="studio-section-trends">Campaign Growth & Activity</h2>' in (
        readable_section_html
    )
    assert (
        "Referral deposits, attributed TVL, product mix, and depositor activity "
        "over time."
    ) not in readable_section_html
    title_positions = [
        readable_section_html.index(f"<h3>{title}</h3>") for _, title, *_ in expected
    ]
    assert title_positions == sorted(title_positions)

    for metric_id, title, default_style, allowed_styles, kind, *_ in expected:
        card_match = re.search(
            rf'(<article[^>]+data-studio-metric-id="{metric_id}".*?</article>)',
            section_html,
            re.DOTALL,
        )
        assert card_match
        card = card_match.group(1)
        assert "studio-size-medium" in card
        assert card.index("studio-growth-data-controls") < card.index(
            "studio-metric-actions"
        )
        assert card.count(f'data-methodology-open="{metric_id}"') == 1
        assert "data-growth-context" not in card
        assert "studio-growth-context" not in card
        assert f'data-metric-render="{metric_id}"' in card
        assert 'role="region"' in card
        assert f'aria-label="{title} visualization"' in unescape(card)
        if kind == "ranking":
            assert f'data-growth-granularity-for="{metric_id}"' not in card
        else:
            assert f'data-growth-granularity-for="{metric_id}"' in card
            assert "Daily" in card and "Weekly" in card
        if allowed_styles and len(allowed_styles) > 1:
            assert f'data-chart-style="{default_style}"' in card
            for style in allowed_styles:
                assert (
                    f'data-chart-style="{style}" '
                    f'data-chart-style-for="{metric_id}"'
                ) in card
        elif allowed_styles:
            assert "studio-chart-style-switcher" not in card
        assert ">PNG<" not in card
        assert "data-metric-png" not in card

    for metric_id in (
        "kyber_deposit_depositor_count_by_product",
        "kyber_deposit_depositor_count_by_depositor_type",
    ):
        card = re.search(
            rf'(<article[^>]+data-studio-metric-id="{metric_id}".*?</article>)',
            section_html,
            re.DOTALL,
        ).group(1)
        assert f'aria-label="Metric type for ' in card

    visible_text = unescape(
        re.sub(
            r"<[^>]+>",
            " ",
            re.sub(r"<script\b.*?</script>", " ", section_html, flags=re.DOTALL),
        )
    )
    for query_id in (8191379, 8191704, 8193003, 8193040):
        assert str(query_id) not in visible_text


def test_kyberswap_merges_capital_position_and_activity_into_four_chart_grid(
    built_site,
    studio_registry,
):
    dashboards, metrics = studio_registry
    dashboard = next(item for item in dashboards if item.id == "kyberswap_campaign")
    section = next(
        item for item in dashboard.data["sections"]
        if item["id"] == "capital_activity"
    )
    section_metrics = [
        metric.data for metric in metrics
        if metric.dashboard_id == dashboard.id and metric.section == "capital_activity"
    ]
    expected = [
        "kyber_attributed_tvl_by_location",
        "kyber_post_referral_activity",
        "kyber_capital_journey",
        "kyber_product_adoption",
    ]

    assert section["label"] == "Capital Position & Activity"
    assert section["show_description"] is False
    assert section["grid_columns"] == 2
    assert [metric["id"] for metric in section_metrics] == expected
    assert [metric["display_order"] for metric in section_metrics] == [15, 16, 17, 18]
    assert all(metric["size"] == "medium" for metric in section_metrics)
    assert {metric["query_id"] for metric in section_metrics[:1] + section_metrics[2:]} == {
        8199058
    }
    assert {
        metric["data_source"] for metric in section_metrics[:1] + section_metrics[2:]
    } == {"kyberswap_attributed_holdings"}
    assert {
        metric["transformation"]["id"]
        for metric in section_metrics[:1] + section_metrics[2:]
    } == {"kyberswap_attributed_holdings"}
    assert section_metrics[0]["growth_chart"]["default_view"] == "protocol"
    assert section_metrics[0]["growth_chart"]["latest_period_only"] is True
    assert section_metrics[0]["growth_chart"]["visible_category_limit"] == 6
    assert section_metrics[0]["growth_chart"]["visible_others_label"] == "Others"
    assert section_metrics[0]["growth_chart"]["preserve_categories"] == ["Exited"]
    assert (
        section_metrics[0]["growth_chart"]["preserve_uncategorized_when_material"]
        is True
    )
    assert [
        view["label"] for view in section_metrics[0]["growth_chart"]["views"]
    ] == ["Protocol", "Category"]
    assert section_metrics[0]["value_column"] == "attributed_balance"
    assert section_metrics[1]["query_id"] == 8202133
    assert section_metrics[1]["growth_chart"]["default_granularity"] == "weekly"
    assert section_metrics[1]["growth_chart"]["default_view"] == "project"
    assert section_metrics[1]["growth_chart"]["visible_category_limit"] == 6
    assert section_metrics[1]["growth_chart"]["visible_others_label"] == "Others"
    assert section_metrics[1]["growth_chart"]["rank_by_activity_magnitude"] is True
    assert [
        view["label"] for view in section_metrics[1]["growth_chart"]["views"]
    ] == ["Label", "Project", "Event"]
    assert section_metrics[1]["tooltip_signed"] is True
    assert section_metrics[2]["stage_columns"] == ["strategy_symbol", "current_token"]
    assert section_metrics[3]["stage_columns"] == [
        "depositor_type",
        "strategy_symbol",
        "current_token_category",
    ]
    assert section_metrics[2]["value_column"] == "attributed_balance"
    assert section_metrics[3]["value_column"] == "attributed_balance"

    html = (built_site / "studio" / "kyberswap" / "index.html").read_text(
        encoding="utf-8"
    )
    section_match = re.search(
        r'(<section class="[^"]*studio-section-capital_activity[^"]*"[^>]*'
        r'data-studio-section="capital_activity".*?</section>)',
        html,
        re.DOTALL,
    )
    assert section_match
    section_html = unescape(section_match.group(1))
    assert '<h2 id="studio-section-capital_activity">Capital Position & Activity</h2>' in section_html
    assert section["description"] not in section_html
    assert "studio-metric-grid studio-metric-grid-columns-2" in section_html
    assert 'data-grid-columns="2"' in section_html
    assert "Composition" not in html
    assert "Capital flows" not in html
    for removed in ("Product Breakdown", "Top Users", "Eligible Balance by Location"):
        assert f"<h3>{removed}</h3>" not in html
    positions = [section_html.index(f'data-studio-metric-id="{metric_id}"') for metric_id in expected]
    assert positions == sorted(positions)
    assert section_html.count("studio-size-medium") == 4


def test_kyberswap_depositor_analysis_registry_layout_and_sources(
    built_site,
    studio_registry,
):
    dashboards, metrics = studio_registry
    dashboard = next(item for item in dashboards if item.id == "kyberswap_campaign")
    section = next(
        item for item in dashboard.data["sections"] if item["id"] == "tables"
    )
    section_metrics = [
        metric.data
        for metric in metrics
        if metric.dashboard_id == dashboard.id and metric.section == "tables"
    ]
    expected_ids = [
        "kyber_top_referred_depositors",
        "kyber_referral_deposit_concentration",
        "kyber_top_depositors",
        "kyber_recent_referral_deposits",
        "kyber_recent_etherfi_activity",
        "kyber_wallet_investigation",
    ]

    assert dashboard.data["default_date_range"] == "ALL"
    assert section == {
        "id": "tables",
        "label": "Depositor Analysis",
        "description": (
            "Wallet-level referral, retention, position, and activity intelligence."
        ),
        "show_description": False,
        "grid_columns": 2,
    }
    assert [metric["id"] for metric in section_metrics] == expected_ids
    assert [metric["display_order"] for metric in section_metrics] == list(
        range(20, 26)
    )
    assert [metric["size"] for metric in section_metrics] == [
        "medium",
        "medium",
        "full",
        "medium",
        "medium",
        "full",
    ]
    assert [metric["query_id"] for metric in section_metrics] == [
        8199058,
        8199058,
        8199058,
        8204345,
        8204373,
        8199058,
    ]
    assert {
        metric["id"]
        for metric in section_metrics
        if metric.get("derived_data_source") == "kyberswap_depositor_intelligence"
    } == {
        "kyber_top_referred_depositors",
        "kyber_referral_deposit_concentration",
        "kyber_top_depositors",
        "kyber_wallet_investigation",
    }
    assert [metric["intelligence_component"] for metric in section_metrics] == [
        "top_referred_depositors",
        "referral_concentration",
        "top_depositors",
        "recent_referral_deposits",
        "recent_etherfi_activity",
        "wallet_investigation",
    ]

    ranking, concentration, top_table, deposits, activity, wallet = section_metrics
    assert ranking["top_n_options"] == [10, 25, 50, 100]
    assert ranking["default_top_n"] == 10
    assert concentration["concentration_tiers"] == [1, 5, 10, 25]
    assert [item["id"] for item in concentration["concentration_measures"]] == [
        "referral_deposits",
        "attributed_tvl",
    ]
    assert top_table["page_size_options"] == [10, 25, 50, 100]
    assert top_table["default_sort_column"] == "total_referral_deposits_usd"
    assert top_table["default_sort_direction"] == "descending"
    assert top_table["investigate_address_column"] == "address"
    for table_metric, query_id in ((deposits, 8204345), (activity, 8204373)):
        assert table_metric["query_id"] == query_id
        assert "derived_data_source" not in table_metric
        assert table_metric["address_columns"] == ["address"]
        assert table_metric["transaction_columns"] == ["tx_hash"]
        assert table_metric["chain_column"] == "blockchain"
        assert table_metric["default_chain"] == "ethereum"
        assert table_metric["date_column"] == "block_time"
        assert table_metric["size"] == "medium"
        assert table_metric["page_size"] == 10
        assert table_metric["page_size_options"] == [10, 16, 32]
        assert table_metric["default_sort_column"] == "block_time"
        assert table_metric["default_sort_direction"] == "descending"
        assert table_metric["investigate_address_column"] == "address"
        assert table_metric["export_respects_period"] is True
        assert table_metric["source_label"] == "View Dune Query"
        assert table_metric["column_labels"]["block_time"] == "Age"
        assert table_metric["column_labels"]["tx_hash"] == "Tx Hash"
        assert table_metric["table_columns"][0] == "block_time"
        assert table_metric["table_columns"][-1] == "tx_hash"
        assert table_metric["export_columns"][0] == "block_time"
        assert table_metric["export_columns"][-1] == "tx_hash"
    assert activity["signed_value_columns"] == ["amount_usd"]
    assert wallet["is_exportable"] is False
    assert wallet["related_query_urls"] == [
        "https://dune.com/queries/8199058",
        "https://dune.com/queries/8204345",
        "https://dune.com/queries/8204373",
    ]

    _, _, requests = load_query_requests()
    kyberswap_request_ids = [
        query_id
        for query_id, request in requests.items()
        if dashboard.id in request.dashboard_ids
    ]
    assert kyberswap_request_ids == [
        8180894,
        8191379,
        8191704,
        8193003,
        8193040,
        8199058,
        8202133,
        8204345,
        8204373,
    ]

    html = (built_site / "studio" / "kyberswap" / "index.html").read_text(
        encoding="utf-8"
    )
    section_match = re.search(
        r'(<section class="[^"]*studio-section-tables[^"]*"[^>]*'
        r'data-studio-section="tables".*?</section>)',
        html,
        re.DOTALL,
    )
    assert section_match
    section_html = unescape(section_match.group(1))
    assert '<h2 id="studio-section-tables">Depositor Analysis</h2>' in section_html
    assert section["description"] not in section_html
    assert "Depositor Intelligence" not in html
    assert "Depositor Analysis" in section_html
    assert "User Detail" not in section_html
    assert 'id="studio-dashboard-section-tables"' in section_html
    assert 'data-studio-section="tables"' in section_html
    assert 'aria-labelledby="studio-section-tables"' in section_html
    assert (
        'href="#studio-dashboard-section-tables" '
        'data-section-nav-target="tables">Depositor Analysis</a>'
    ) in html
    assert 'aria-label="Expand Depositor Analysis metrics"' in html
    assert '<strong>Depositor Analysis</strong>' in html
    assert "studio-metric-grid studio-metric-grid-columns-2" in section_html
    assert 'data-grid-columns="2"' in section_html
    positions = [
        section_html.index(f'data-studio-metric-id="{metric_id}"')
        for metric_id in expected_ids
    ]
    assert positions == sorted(positions)
    assert 'data-top-n-for="kyber_top_referred_depositors"' in section_html

    assert 'data-studio-range="ALL" aria-pressed="true" class="active"' in html
    config_match = re.search(
        r'<script type="application/json" data-studio-config>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert config_match
    config = json.loads(config_match.group(1))
    configured_section = next(
        item for item in config["dashboard"]["sections"] if item["id"] == "tables"
    )
    assert configured_section["id"] == "tables"
    assert configured_section["label"] == "Depositor Analysis"
    descriptor = config["dataSources"]["kyberswap_depositor_intelligence"]
    assert descriptor["kind"] == "generated_derived"
    assert descriptor["dataSource"] == "kyberswap_depositor_intelligence"
    assert descriptor["artifactId"] == "kyberswap_depositor_intelligence"
    assert descriptor["dataFile"] == "kyberswap_depositor_intelligence.json"
    assert descriptor["url"].endswith(
        "/data/studio/generated/kyberswap_depositor_intelligence.json"
    )
    assert descriptor["sourceQueryIds"] == [8199058, 8204345, 8204373]


def test_studio_registry_requires_rendered_dashboard_metadata():
    dashboards, metrics = deepcopy(registry_values())
    del dashboards[0]["audience"]
    with pytest.raises(ValueError, match="missing required fields: audience"):
        validate_studio_registry(
            dashboards,
            metrics,
            data_dir=DEFAULT_STUDIO_DIR / "data",
        )


def test_build_generates_studio_routes_and_preserves_existing_pages(built_site):
    expected_pages = [
        "index.html",
        "mcp.html",
        "datasets.html",
        "dashboards.html",
        "freshness.html",
        "studio/index.html",
        "studio/kyberswap/index.html",
    ]

    for relative_path in expected_pages:
        assert (built_site / relative_path).is_file(), relative_path

    assert not (built_site / "studio" / "demo").exists()
    assert not (built_site / "studio" / "data" / "demo.json").exists()
    assert not (built_site / "studio" / "data" / "kyberswap.json").exists()
    assert (built_site / "assets" / "studio.css").is_file()
    assert (built_site / "assets" / "studio.js").is_file()
    assert (built_site / "assets" / "studio-landing.js").is_file()
    assert (built_site / "assets" / "vendor" / "echarts.min.js").is_file()
    assert (built_site / "assets" / "vendor" / "ECHARTS-LICENSE.txt").is_file()


def test_studio_build_prunes_stale_routes_and_data(tmp_path):
    stale_routes = [
        tmp_path / "studio" / "retired-dashboard" / "index.html",
        tmp_path / "studio" / "demo" / "index.html",
    ]
    for stale_route in stale_routes:
        stale_route.parent.mkdir(parents=True, exist_ok=True)
        stale_route.write_text("retired", encoding="utf-8")
    stale_files = [
        tmp_path / "studio" / "data" / "retired.json",
        tmp_path / "studio" / "data" / "demo.json",
    ]
    for stale_file in stale_files:
        stale_file.parent.mkdir(parents=True, exist_ok=True)
        stale_file.write_text("{}", encoding="utf-8")

    build_site(output_dir=tmp_path)

    assert all(not path.exists() for path in stale_routes + stale_files)
    assert (tmp_path / "studio" / "kyberswap" / "index.html").is_file()


def test_disabling_studio_prunes_stale_generated_routes_and_navigation(tmp_path):
    stale_route = tmp_path / "studio" / "retired-dashboard" / "index.html"
    stale_route.parent.mkdir(parents=True)
    stale_route.write_text("retired", encoding="utf-8")

    build_site(output_dir=tmp_path, studio_dir=None)

    assert not (tmp_path / "studio").exists()
    root_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert ">Studio</a>" not in root_html


def test_studio_build_publishes_only_configured_generated_data_files(tmp_path):
    studio_dir = tmp_path / "studio-source"
    shutil.copytree(DEFAULT_STUDIO_DIR, studio_dir)
    (studio_dir / "data" / "raw-query-notes.txt").write_text(
        "must not be deployed",
        encoding="utf-8",
    )

    output_dir = tmp_path / "site"
    build_site(output_dir=output_dir, studio_dir=studio_dir)

    published_names = {
        path.name for path in (output_dir / "studio" / "data").iterdir()
    }
    assert published_names == set()


def test_snapshot_and_site_build_never_publish_a_sentinel_api_secret(tmp_path):
    sentinel = "SUPER_SECRET_STUDIO_API_KEY_SENTINEL"
    generated_dir = tmp_path / "generated"

    def denied_transport(url, headers, timeout):
        del url, timeout
        assert headers["X-Dune-API-Key"] == sentinel
        return 401, {}, {"error": f"credential {sentinel} was rejected"}

    with pytest.raises(StudioIngestionError):
        refresh_studio_data(
            DuneLatestResultClient(sentinel, transport=denied_transport),
            output_root=generated_dir,
            mode="live",
            sleeper=lambda _: None,
        )

    dashboards, _, requests = load_query_requests()
    fixture_clock = lambda: datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
    refresh_studio_data(
        FixtureDuneClient(
            requests,
            dashboards,
            scenario="success",
            clock=fixture_clock,
        ),
        output_root=generated_dir,
        mode="fixture",
        clock=fixture_clock,
        sleeper=lambda _: None,
    )

    site_dir = tmp_path / "site"
    build_site(
        output_dir=site_dir,
        studio_generated_data_dir=generated_dir,
    )

    secret_bytes = sentinel.encode("utf-8")
    for root in (generated_dir, site_dir):
        for path in root.rglob("*"):
            if path.is_file():
                assert secret_bytes not in path.read_bytes(), path
    assert not (site_dir / "data" / "studio" / "generated" / "attempts").exists()


def test_live_snapshot_labels_and_timezone_render_without_template_changes(tmp_path):
    studio_dir = tmp_path / "studio-source"
    shutil.copytree(DEFAULT_STUDIO_DIR, studio_dir)
    dashboards_path = studio_dir / "dashboards.yaml"
    dashboards_payload = yaml.safe_load(dashboards_path.read_text(encoding="utf-8"))
    kyber_dashboard = next(
        dashboard
        for dashboard in dashboards_payload["dashboards"]
        if dashboard["id"] == "kyberswap_campaign"
    )
    kyber_dashboard["status"] = "live"
    dashboards_path.write_text(
        yaml.safe_dump(dashboards_payload, sort_keys=False),
        encoding="utf-8",
    )
    kyber_data_path = studio_dir / "data" / "kyberswap.json"
    kyber_payload = json.loads(kyber_data_path.read_text(encoding="utf-8"))
    kyber_payload["meta"]["status"] = "live"
    kyber_payload["meta"]["last_refreshed"] = "2026-07-29T20:40:00+02:00"
    kyber_data_path.write_text(json.dumps(kyber_payload), encoding="utf-8")

    generated_dir = tmp_path / "generated"
    dashboards, _, requests = load_query_requests()
    fixture_clock = lambda: datetime(2026, 8, 3, 12, tzinfo=timezone.utc)
    refresh_studio_data(
        FixtureDuneClient(
            requests,
            dashboards,
            scenario="success",
            clock=fixture_clock,
        ),
        output_root=generated_dir,
        mode="fixture",
        clock=fixture_clock,
        sleeper=lambda _: None,
    )
    failed_clock = lambda: datetime(2026, 8, 3, 14, tzinfo=timezone.utc)
    with pytest.raises(StudioIngestionError, match="active snapshot preserved"):
        refresh_studio_data(
            FixtureDuneClient(
                requests,
                dashboards,
                scenario="query_execution_failed",
                clock=failed_clock,
            ),
            output_root=generated_dir,
            mode="fixture",
            clock=failed_clock,
            sleeper=lambda _: None,
        )

    output_dir = tmp_path / "site"
    build_site(
        output_dir=output_dir,
        studio_dir=studio_dir,
        studio_generated_data_dir=generated_dir,
    )
    html = (output_dir / "studio" / "kyberswap" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "03 Aug 2026 · 12:00 UTC" in html
    assert "Last Updated:" in html
    assert '"sourceLastUpdated":"2026-07-31T11:45:00Z"' in html
    assert '"executionFinishedAt":"2026-07-31T11:45:00Z"' in html
    assert "Live generated snapshot" not in html
    assert "Dune-backed analytics, rendered statically." not in html
    assert "Query 8180894 · source" not in html
    assert "Query 8180894 · placeholder" not in html
    assert ">View calculation <" not in html
    assert ">Methodology</button>" in html
    assert 'data-methodology-open="kyber_total_referral_deposits"' not in html
    assert "kyberswap_campaign_summary_v1" in html
    assert '"queryId":8180894' in html

    replacement_clock = lambda: datetime(2026, 8, 3, 16, tzinfo=timezone.utc)
    refresh_studio_data(
        FixtureDuneClient(
            requests,
            dashboards,
            scenario="success",
            clock=replacement_clock,
        ),
        output_root=generated_dir,
        mode="fixture",
        force=True,
        clock=replacement_clock,
        sleeper=lambda _: None,
    )
    replacement_output = tmp_path / "replacement-site"
    build_site(
        output_dir=replacement_output,
        studio_dir=studio_dir,
        studio_generated_data_dir=generated_dir,
    )
    replacement_html = (
        replacement_output / "studio" / "kyberswap" / "index.html"
    ).read_text(encoding="utf-8")
    assert "03 Aug 2026 · 16:00 UTC" in replacement_html
    assert '"sourceLastUpdated":"2026-07-31T11:45:00Z"' in replacement_html


def test_every_dashboard_appears_in_landing_and_dashboard_selectors(
    built_site,
    studio_registry,
):
    dashboards, _ = studio_registry
    pages = [
        (built_site / "studio" / "index.html").read_text(encoding="utf-8"),
        (built_site / "studio" / "kyberswap" / "index.html").read_text(
            encoding="utf-8"
        ),
    ]

    for html in pages:
        assert "data-studio-dashboard-select" in html
        assert "data-studio-theme-slot" in html
        assert "Back to Data Catalog" in html
        for dashboard in dashboards:
            assert f'data-dashboard-id="{dashboard.id}"' in html
            assert dashboard.name in html

    for dashboard in dashboards:
        html = (
            built_site / "studio" / dashboard.slug / "index.html"
        ).read_text(encoding="utf-8")
        assert (
            f'data-dashboard-id="{dashboard.id}" selected'
            in html
        )

    landing_html = pages[0]
    assert "Validated static snapshots" in landing_html
    assert "Validated campaign data from reviewed read-only query snapshots." in landing_html
    assert "Component Test Lab" not in landing_html
    assert 'href="demo/"' not in landing_html
    assert "Generated demo data" not in landing_html
    assert "Dune-backed refreshes next" not in landing_html


def test_line_metrics_render_valid_config_driven_chart_style_switchers(
    built_site,
    studio_registry,
):
    dashboards, metrics = studio_registry
    for dashboard in dashboards:
        html = (
            built_site / "studio" / dashboard.slug / "index.html"
        ).read_text(encoding="utf-8")
        line_metrics = [
            metric
            for metric in metrics
            if metric.dashboard_id == dashboard.id
            and metric.visualization_type == "line"
        ]
        for metric in line_metrics:
            assert metric.data["default_visualization"] in {
                "line",
                "area",
                "column",
                "scatter",
            }
            assert set(metric.data["allowed_visualizations"]) <= {
                "line",
                "area",
                "column",
                "scatter",
            }
            for style in metric.data["allowed_visualizations"]:
                if metric.data.get("growth_chart") and len(
                    metric.data["allowed_visualizations"]
                ) == 1:
                    continue
                assert (
                    f'data-chart-style="{style}" '
                    f'data-chart-style-for="{metric.id}"'
                ) in html


def test_kyberswap_sample_and_query_fixtures_cover_required_states():
    kyberswap = json.loads(
        (DEFAULT_STUDIO_DIR / "data" / "kyberswap.json").read_text(
            encoding="utf-8"
        )
    )
    growth_fixtures = {
        query_id: json.loads(
            (DEFAULT_STUDIO_DIR / "fixtures" / f"query_{query_id}.json").read_text(
                encoding="utf-8"
            )
        )
        for query_id in (8191379, 8191704, 8193003, 8193040)
    }
    depositor_fixtures = {
        query_id: json.loads(
            (DEFAULT_STUDIO_DIR / "fixtures" / f"query_{query_id}.json").read_text(
                encoding="utf-8"
            )
        )
        for query_id in (8204345, 8204373)
    }

    assert kyberswap["meta"]["sample_data"] is True
    assert all(
        fixture["query_id"] == query_id and fixture["rows"]
        for query_id, fixture in growth_fixtures.items()
    )
    assert {row["depositor_type"] for row in growth_fixtures[8191704]["rows"]} == {
        "New Depositor",
        "Existing Depositor",
        "Past Depositor",
    }
    assert {row["category_type"] for row in growth_fixtures[8193040]["rows"]} == {
        "product",
        "depositor_type",
    }
    assert {
        "tx_hash",
        "address",
        "blockchain",
        "block_time",
        "strategy_symbol",
        "amount_usd",
    } <= set(depositor_fixtures[8204345]["rows"][0])
    assert {
        "event",
        "address",
        "project",
        "blockchain",
        "tx_hash",
        "block_time",
        "amount_usd",
        "token_symbol",
        "label",
    } <= set(depositor_fixtures[8204373]["rows"][0])
    assert all(
        row["amount_usd"] >= 0 for row in depositor_fixtures[8204345]["rows"]
    )
    assert any(
        row["amount_usd"] < 0 for row in depositor_fixtures[8204373]["rows"]
    )
    assert kyberswap["datasets"]["capital_journey"]


def test_dashboard_has_connected_visibility_export_and_range_controls(
    built_site,
    studio_registry,
):
    dashboards, metrics = studio_registry
    dashboard = next(item for item in dashboards if item.id == "kyberswap_campaign")
    dashboard_metrics = [
        metric for metric in metrics if metric.dashboard_id == dashboard.id
    ]
    html = (built_site / "studio" / dashboard.slug / "index.html").read_text(
        encoding="utf-8"
    )

    workspace_tag = re.search(r'<div class="studio-workspace"[^>]+>', html)
    left_panel = re.search(
        r'(<aside class="[^"]*studio-side-left[^"]*".*?</aside>)',
        html,
        re.DOTALL,
    )
    right_panel = re.search(
        r'(<aside class="[^"]*studio-side-right[^"]*".*?</aside>)',
        html,
        re.DOTALL,
    )

    assert workspace_tag
    assert 'data-left-collapsed="true"' in workspace_tag.group(0)
    assert 'data-right-collapsed="true"' in workspace_tag.group(0)
    assert "data-unified-panel" not in workspace_tag.group(0)
    assert left_panel
    assert right_panel
    left_html = left_panel.group(1)
    right_html = right_panel.group(1)

    assert 'data-studio-panel="left"' in left_html
    assert 'data-panel-toggle="left"' in left_html
    assert 'data-panel-toggle="left" aria-expanded="false"' in left_html
    assert "data-studio-section-nav" in left_html
    assert "data-section-nav-target" in left_html
    assert "data-visibility-metric" not in left_html
    assert "data-visibility-action" not in left_html
    assert "data-visible-count" not in left_html
    assert "data-export-download" not in left_html

    assert 'data-studio-panel="right"' in html
    assert 'data-panel-toggle="right"' in right_html
    assert 'data-panel-toggle="right" aria-expanded="false"' in right_html
    assert '<h2 id="studio-metrics-panel-title">Metric controls</h2>' in right_html
    assert "Workspace" not in right_html
    assert "Metrics &amp; Downloads" not in right_html
    assert "data-studio-section-nav" not in right_html
    assert "data-visible-count" not in right_html
    assert "data-export-count" not in right_html
    assert "studio-panel-counts" not in right_html
    assert 'data-visibility-action="show-all"' in right_html
    assert 'data-visibility-action="hide-all"' in right_html
    assert 'data-visibility-action="reset"' in right_html
    assert "data-export-action" not in html
    assert "data-export-metric" not in html
    assert "data-export-group" not in html
    assert "data-export-download" in right_html
    assert right_html.count("data-export-download") == 1
    assert "Selected metrics · ZIP" in right_html
    assert right_html.index("studio-panel-bulk") > right_html.index(
        "studio-panel-actions"
    )
    assert right_html.index("studio-panel-bulk") > right_html.rindex(
        "studio-control-group"
    )
    assert right_html.count("data-visibility-disclosure") == len(
        dashboard.data["sections"]
    )
    assert right_html.count("data-visibility-list") == len(
        dashboard.data["sections"]
    )

    section_ids = {
        section["id"]
        for section in dashboard.data["sections"]
        if any(metric.section == section["id"] for metric in dashboard_metrics)
    }
    assert {
        match.group(1)
        for match in re.finditer(r'data-section-nav-target="([^"]+)"', left_html)
    } == section_ids
    for range_name in STUDIO_RANGE_OPTIONS:
        assert f'data-studio-range="{range_name}"' in html

    for metric in dashboard_metrics:
        opening_tag = re.search(
            rf'<article[^>]+data-studio-metric-id="{re.escape(metric.id)}"[^>]*>',
            html,
        )
        assert opening_tag
        assert (
            f'data-studio-visible="{str(metric.data["default_visible"]).lower()}"'
            in opening_tag.group(0)
        )
        assert (" hidden" in opening_tag.group(0)) == (
            not metric.data["default_visible"]
        )
        visibility_markup = f'data-visibility-metric="{metric.id}"'
        assert visibility_markup in html
        if metric.data["default_visible"]:
            start = html.index(visibility_markup)
            assert "checked" in html[start : start + 100]
        assert metric.data["query_url"] in html
        if metric.visualization_type != "counter":
            assert f'data-query-id="{metric.data["query_id"]}"' in html
        assert f"Query {metric.data['query_id']} · placeholder" not in html
        if metric.data["is_exportable"] and metric.visualization_type != "counter":
            assert f'data-metric-export="{metric.id}"' in html


def test_kyberswap_header_stays_intact_while_configured_hero_is_omitted(built_site):
    html = (built_site / "studio" / "kyberswap" / "index.html").read_text(
        encoding="utf-8"
    )
    assert (
        'href="https://dune.com/ether_fi/kyberswap-campaign"'
        in html
    )
    assert "View on Dune" in html
    assert 'data-dashboard-id="kyberswap_campaign" selected' in html
    assert '<h1 class="visually-hidden">KyberSwap Campaign</h1>' in html
    assert '<section class="studio-dashboard-hero">' not in html


def test_kyberswap_renders_exact_compact_eight_counter_section_without_inline_actions(
    built_site,
):
    html = (built_site / "studio" / "kyberswap" / "index.html").read_text(
        encoding="utf-8"
    )
    section_match = re.search(
        r'(<section class="[^"]*studio-section-counters[^"]*"[^>]*'
        r'data-studio-section="counters".*?</section>)',
        html,
        re.DOTALL,
    )
    assert section_match
    section = section_match.group(1)
    expected_names = [
        "Total Referral Deposits",
        "Attributed TVL",
        "Referred Deposits by New Depositors",
        "% Deposits by New Depositors",
        "Total Depositors",
        "New Depositors",
        "Retention Rate",
        "Revenue Generated",
    ]

    assert "studio-section-heading-hidden" not in section
    assert (
        '<h2 class="visually-hidden" id="studio-section-counters">'
        "Campaign summary</h2>"
    ) in section
    assert "studio-dashboard-section-heading" not in section
    assert "Campaign pulse" not in section
    assert "The current attributed campaign position." not in section
    assert 'data-studio-section-utility="counters"' not in section
    assert 'data-methodology-open="kyber_total_referral_deposits"' not in section
    assert 'data-metric-export="kyber_total_referral_deposits"' not in section
    assert "Inspect Methodology" not in section
    assert "studio-metric-grid studio-metric-grid-columns-2" in section
    assert 'data-grid-columns="2"' in section

    positions = [section.index(f"<h3>{name}</h3>") for name in expected_names]
    assert positions == sorted(positions)
    cards = re.findall(
        r'(<article[^>]+data-studio-metric-type="counter".*?</article>)',
        section,
        re.DOTALL,
    )
    assert len(cards) == 8
    for card in cards:
        assert "studio-counter-compact" in card
        assert "studio-metric-actions" not in card
        assert "data-methodology-open" not in card
        assert "data-metric-export" not in card

    config_match = re.search(
        r'<script type="application/json" data-studio-config>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert config_match
    config = json.loads(config_match.group(1))
    counter_section = next(
        value for value in config["dashboard"]["sections"]
        if value["id"] == "counters"
    )
    summary_metric = next(
        value for value in config["metrics"]
        if value["id"] == "kyber_total_referral_deposits"
    )
    assert config["dashboard"]["show_hero"] is False
    assert counter_section["show_heading"] is False
    assert counter_section["grid_columns"] == 2
    assert "shared_methodology_metric_id" not in counter_section
    assert "shared_export_metric_id" not in counter_section
    assert summary_metric["compact_counter"] is True
    assert summary_metric["value_column"] == "total_deposits_usd"
    assert summary_metric["period_key_column"] == "key_"
    assert summary_metric["methodology"]["title"] == "KyberSwap Campaign Summary"
    assert len(summary_metric["methodology"]["metric_definitions"]) == 8
    assert summary_metric["methodology"]["selected_period_logic"]
    assert 'data-visibility-metric="kyber_total_referral_deposits"' in html
    assert html.count("data-export-download") == 1
    assert summary_metric["export_column_aliases"] == {
        "key_": "period",
        "depositors_new_users_rate": "deposits_by_new_depositors_rate",
    }


def test_kyberswap_counter_styles_keep_scorecard_scoped_and_responsive():
    css = (Path("website") / "assets" / "studio.css").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", css)
    card_selector = (
        '[data-studio-dashboard="kyberswap_campaign"] '
        ".studio-section-counters .studio-metric-grid-columns-2 "
        "> .studio-counter-compact"
    )
    desktop_block = re.search(
        rf"{re.escape(card_selector)} \{{([^}}]+)\}}",
        normalized,
    )

    assert desktop_block
    assert "grid-column: span 3" in desktop_block.group(1)
    assert "@media (min-width: 641px) and (max-width: 1199px)" in normalized
    assert "grid-column: span 6" in normalized
    assert "@media (min-width: 1200px) and (max-width: 1399px)" in normalized
    assert "-webkit-line-clamp: 3" in normalized
    assert "@media (max-width: 640px)" in normalized
    assert "grid-column: 1 / -1" in normalized
    assert '--studio-counter-accent: var(--studio-green-strong)' in normalized
    assert '--studio-counter-accent: var(--studio-blue)' in normalized
    assert '--studio-counter-accent: var(--studio-amber)' in normalized
    assert 'data-studio-metric-id="kyber_total_depositors"' in normalized
    assert 'data-studio-metric-id="kyber_retention_rate"' in normalized


def test_depositor_analysis_paired_tables_share_equal_height_row_rhythm():
    css = (Path("website") / "assets" / "studio.css").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", css)

    for component in (
        "recent_referral_deposits",
        "recent_etherfi_activity",
    ):
        assert f'[data-intelligence-component="{component}"]' in normalized
    assert "display: flex; height: 100%; align-self: stretch; flex-direction: column" in normalized
    assert "height: 112px; min-height: 112px" in normalized
    assert "grid-template-rows: auto minmax(0, 1fr) auto" in normalized
    assert "height: 62px; min-height: 62px" in normalized
    assert "height: 52px" in normalized
    assert ".studio-table-compact-text" in normalized
    assert "text-overflow: ellipsis" in normalized
    assert ".studio-relative-age[data-full-timestamp]:is(:hover, :focus-visible)" in normalized
    assert ".studio-copy-address.studio-copy-icon" in normalized
    assert "@media (max-width: 720px)" in normalized
    assert '.studio-wallet-summary-grid { display: grid; margin: 0; grid-template-columns: repeat(5, minmax(0, 1fr))' in normalized
    assert "@container studio-main (max-width: 860px)" in normalized


def test_studio_layout_styles_keep_panels_sections_and_chart_headers_compact():
    css = (Path("website") / "assets" / "studio.css").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", css)

    assert "clamp(50px, 6vw, 78px)" not in normalized
    assert "clamp(38px, 4vw, 56px)" not in normalized
    assert ".studio-dashboard-section + .studio-dashboard-section { border-top:" in (
        normalized
    )
    assert "grid-template-columns: 54px minmax(0, 1fr) 54px" in normalized
    assert "data-unified-panel" not in normalized
    assert "@media (max-width: 900px)" in normalized
    assert "grid-template-columns: minmax(0, 1fr)" in normalized

    chart_header = re.search(
        r"\.studio-metric-card:is\(\.studio-metric-line, \.studio-metric-bar, "
        r"\.studio-metric-sankey\) \.studio-metric-header \{([^}]+)\}",
        normalized,
    )
    assert chart_header
    assert "border-bottom: 0" in chart_header.group(1)
    assert "min-height: 174px" not in normalized
    assert "min-height: 136px" in normalized
    assert "[data-growth-context]" not in normalized
    assert ".studio-growth-context" not in normalized
