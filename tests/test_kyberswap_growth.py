from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.enrich_kyberswap_growth import (
    ACTIVITY_OUTPUT_COLUMNS,
    ACTIVITY_QUERY_ID,
    ACTIVITY_SOURCE_COLUMNS,
    ACTIVITY_TRANSFORMATION_ID,
    BREAKDOWN_OUTPUT_COLUMNS,
    BREAKDOWN_QUERY_ID,
    BREAKDOWN_SOURCE_COLUMNS,
    BREAKDOWN_TRANSFORMATION_ID,
    DEPOSITOR_TYPES,
    DEPOSITS_OUTPUT_COLUMNS,
    DEPOSITS_QUERY_ID,
    DEPOSITS_SOURCE_COLUMNS,
    DEPOSITS_TRANSFORMATION_ID,
    EXPECTED_PRODUCT_ORDER,
    KyberSwapGrowthError,
    POST_REFERRAL_ACTIVITY_GROUPING_TYPES,
    POST_REFERRAL_ACTIVITY_OUTPUT_COLUMNS,
    POST_REFERRAL_ACTIVITY_QUERY_ID,
    POST_REFERRAL_ACTIVITY_RECORD_TYPES,
    POST_REFERRAL_ACTIVITY_SOURCE_COLUMNS,
    POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID,
    TVL_OUTPUT_COLUMNS,
    TVL_QUERY_ID,
    TVL_SOURCE_COLUMNS,
    TVL_TRANSFORMATION_ID,
    prepare_kyberswap_growth_activity,
    prepare_kyberswap_growth_attributed_tvl,
    prepare_kyberswap_growth_breakdown,
    prepare_kyberswap_growth_deposits,
    prepare_kyberswap_post_referral_activity,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "studio" / "fixtures"
SOURCE_UPDATED = "2026-08-02T09:00:00+01:00"
GENERATED_AT = "2026-08-02T08:01:00Z"


def post_referral_activity_rows() -> list[dict[str, object]]:
    return [
        {
            "day": "2026-07-04",
            "week": "2026-06-29",
            "project": "spark",
            "event": "lending deposit",
            "label": "Deposit weETH into Spark",
            "amount_usd": "438.98411887431797",
        },
        {
            "day": "2026-07-05",
            "week": "2026-06-29",
            "project": "spark",
            "event": "lending withdraw",
            "label": "Withdraw weETH from Spark",
            "amount_usd": "-38.98411887431797",
        },
        {
            "day": "2026-07-06",
            "week": "2026-07-06",
            "project": "aave",
            "event": "lending withdraw",
            "label": "Withdraw weETH from Aave",
            "amount_usd": "-410.4062395041133",
        },
        {
            "day": "2026-07-06",
            "week": "2026-07-06",
            "project": "spark",
            "event": "lending deposit",
            "label": "Deposit weETH into Spark",
            "amount_usd": "10.4062395041133",
        },
    ]


def prepare_post_referral_activity(rows=None):
    return prepare_kyberswap_post_referral_activity(
        post_referral_activity_rows() if rows is None else rows,
        source_query_id=POST_REFERRAL_ACTIVITY_QUERY_ID,
        source_execution_id=" execution-8202133-test ",
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=POST_REFERRAL_ACTIVITY_SOURCE_COLUMNS,
    )


def fixture(query_id: int) -> dict:
    return json.loads(
        (FIXTURE_DIR / f"query_{query_id}.json").read_text(encoding="utf-8")
    )


def prepare_fixture(query_id: int):
    payload = fixture(query_id)
    functions = {
        DEPOSITS_QUERY_ID: prepare_kyberswap_growth_deposits,
        TVL_QUERY_ID: prepare_kyberswap_growth_attributed_tvl,
        BREAKDOWN_QUERY_ID: prepare_kyberswap_growth_breakdown,
        ACTIVITY_QUERY_ID: prepare_kyberswap_growth_activity,
    }
    return functions[query_id](
        payload["rows"],
        source_query_id=query_id,
        source_execution_id=payload["execution_id"],
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=payload["columns"],
    )


def records(result, record_type: str) -> list[dict]:
    return [row for row in result.rows if row["record_type"] == record_type]


def test_query_transform_and_schema_contracts_are_explicit() -> None:
    assert {
        DEPOSITS_QUERY_ID: DEPOSITS_TRANSFORMATION_ID,
        TVL_QUERY_ID: TVL_TRANSFORMATION_ID,
        BREAKDOWN_QUERY_ID: BREAKDOWN_TRANSFORMATION_ID,
        ACTIVITY_QUERY_ID: ACTIVITY_TRANSFORMATION_ID,
        POST_REFERRAL_ACTIVITY_QUERY_ID: POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID,
    } == {
        8191379: "kyberswap_growth_deposits",
        8191704: "kyberswap_growth_attributed_tvl",
        8193003: "kyberswap_growth_breakdown",
        8193040: "kyberswap_growth_activity",
        8202133: "kyberswap_post_referral_activity",
    }
    assert DEPOSITOR_TYPES == (
        "New Depositor",
        "Existing Depositor",
        "Past Depositor",
    )
    assert EXPECTED_PRODUCT_ORDER == (
        "eETH",
        "liquidETH",
        "liquidUSD",
        "liquidBTC",
    )
    assert DEPOSITS_SOURCE_COLUMNS == (
        "day",
        "week",
        "daily_deposits_usd",
        "weekly_deposits_usd",
        "cum_deposits_usd",
        "last_updated",
    )
    assert TVL_SOURCE_COLUMNS == (
        "day",
        "week",
        "depositor_type",
        "daily_attributed_tvl_usd",
        "cum_attributed_tvl_usd",
    )
    assert BREAKDOWN_SOURCE_COLUMNS == (
        "day",
        "week",
        "product_symbol",
        "depositor_type",
        "daily_deposits",
    )
    assert ACTIVITY_SOURCE_COLUMNS == (
        "timestamp_type",
        "timestamp",
        "category_type",
        "category",
        "metric_type",
        "metric_value",
    )
    assert POST_REFERRAL_ACTIVITY_SOURCE_COLUMNS == (
        "day",
        "week",
        "project",
        "event",
        "label",
        "amount_usd",
    )
    assert POST_REFERRAL_ACTIVITY_GROUPING_TYPES == ("label", "project", "event")
    assert POST_REFERRAL_ACTIVITY_RECORD_TYPES == (
        "daily_label",
        "weekly_label",
        "daily_project",
        "weekly_project",
        "daily_event",
        "weekly_event",
    )


@pytest.mark.parametrize(
    ("query_id", "expected_columns"),
    [
        (DEPOSITS_QUERY_ID, DEPOSITS_SOURCE_COLUMNS),
        (TVL_QUERY_ID, TVL_SOURCE_COLUMNS),
        (BREAKDOWN_QUERY_ID, BREAKDOWN_SOURCE_COLUMNS),
        (ACTIVITY_QUERY_ID, ACTIVITY_SOURCE_COLUMNS),
    ],
)
def test_fixtures_have_exact_latest_result_schemas(query_id, expected_columns) -> None:
    payload = fixture(query_id)
    assert payload["schema_version"] == 1
    assert payload["query_id"] == query_id
    assert payload["execution_id"] == f"fixture-{query_id}-latest"
    assert payload["columns"] == list(expected_columns)
    assert payload["rows"]
    assert all(set(row) == set(expected_columns) for row in payload["rows"])


def test_deposits_daily_and_weekly_latest_rows_never_sum_weekly_value() -> None:
    result = prepare_fixture(DEPOSITS_QUERY_ID)

    assert result.columns == list(DEPOSITS_OUTPUT_COLUMNS)
    assert all(tuple(row) == DEPOSITS_OUTPUT_COLUMNS for row in result.rows)
    assert [
        (row["period"], row["daily_deposits_usd"], row["cum_deposits_usd"])
        for row in records(result, "daily")
    ] == [
        ("2026-07-20", "100.1", "100.1"),
        ("2026-07-21", "200.2", "300.3"),
        ("2026-07-27", "50", "350.3"),
        ("2026-07-28", "25", "375.3"),
    ]
    assert [
        (
            row["period"],
            row["day"],
            row["weekly_deposits_usd"],
            row["cum_deposits_usd"],
        )
        for row in records(result, "weekly")
    ] == [
        ("2026-07-20", "2026-07-21", "300.3", "300.3"),
        ("2026-07-27", "2026-07-28", "75", "375.3"),
    ]
    assert result.summary["weekly_selection"] == "latest_day"
    assert result.summary["weekly_deposits_usd_summed"] is False


def test_deposits_preserve_decimal_precision_and_normalize_provenance() -> None:
    payload = fixture(DEPOSITS_QUERY_ID)
    payload["rows"] = [
        {
            **payload["rows"][0],
            "daily_deposits_usd": "0.123456789012345678901234567890",
            "weekly_deposits_usd": "0.123456789012345678901234567890",
            "cum_deposits_usd": "0.123456789012345678901234567890",
            "last_updated": "2026-08-01 00:05:00 UTC",
        }
    ]
    result = prepare_kyberswap_growth_deposits(
        payload["rows"],
        source_query_id=DEPOSITS_QUERY_ID,
        source_execution_id=" execution-growth ",
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=payload["columns"],
    )

    assert result.rows[0]["daily_deposits_usd"] == (
        "0.12345678901234567890123456789"
    )
    assert result.rows[0]["source_execution_id"] == "execution-growth"
    assert result.rows[0]["source_last_updated"] == "2026-08-02T08:00:00Z"
    assert result.rows[0]["generated_at"] == GENERATED_AT
    assert result.rows[0]["last_updated"] == "2026-08-01T00:05:00Z"


def test_deposits_reject_decreasing_cumulative_values() -> None:
    rows = deepcopy(fixture(DEPOSITS_QUERY_ID)["rows"][:2])
    rows[0]["cum_deposits_usd"] = "10"
    rows[1]["cum_deposits_usd"] = "9"

    with pytest.raises(
        KyberSwapGrowthError,
        match="cum_deposits_usd must be nondecreasing",
    ):
        prepare_kyberswap_growth_deposits(
            rows,
            source_query_id=DEPOSITS_QUERY_ID,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=DEPOSITS_SOURCE_COLUMNS,
        )


def test_deposits_accept_out_of_order_valid_row_last_updated_values() -> None:
    rows = deepcopy(fixture(DEPOSITS_QUERY_ID)["rows"][:2])
    rows[0]["last_updated"] = "2026-07-22T00:00:00Z"
    rows[1]["last_updated"] = "2026-07-21T00:00:00Z"

    result = prepare_kyberswap_growth_deposits(
        rows,
        source_query_id=DEPOSITS_QUERY_ID,
        source_execution_id="execution",
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=DEPOSITS_SOURCE_COLUMNS,
    )

    assert [row["last_updated"] for row in records(result, "daily")] == [
        "2026-07-22T00:00:00Z",
        "2026-07-21T00:00:00Z",
    ]
    assert result.summary["last_updated_validated"] is True
    assert "last_updated_nondecreasing" not in result.summary


def test_deposits_reject_duplicate_days_and_incorrect_week_boundaries() -> None:
    rows = deepcopy(fixture(DEPOSITS_QUERY_ID)["rows"][:2])
    rows[1]["day"] = rows[0]["day"]
    with pytest.raises(KyberSwapGrowthError, match="duplicate source day"):
        prepare_kyberswap_growth_deposits(
            rows,
            source_query_id=DEPOSITS_QUERY_ID,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=DEPOSITS_SOURCE_COLUMNS,
        )

    row = deepcopy(fixture(DEPOSITS_QUERY_ID)["rows"][0])
    row["week"] = "2026-07-21"
    with pytest.raises(KyberSwapGrowthError, match="field week must be Monday"):
        prepare_kyberswap_growth_deposits(
            [row],
            source_query_id=DEPOSITS_QUERY_ID,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=DEPOSITS_SOURCE_COLUMNS,
        )


def test_attributed_tvl_builds_daily_all_and_weekly_latest_observations() -> None:
    result = prepare_fixture(TVL_QUERY_ID)

    assert result.columns == list(TVL_OUTPUT_COLUMNS)
    assert all(tuple(row) == TVL_OUTPUT_COLUMNS for row in result.rows)
    assert [
        (
            row["period"],
            row["daily_attributed_tvl_usd"],
            row["cum_attributed_tvl_usd"],
        )
        for row in records(result, "daily_all")
    ] == [
        ("2026-07-20", "175.25", "175.25"),
        ("2026-07-21", "35", "210.25"),
        ("2026-07-27", "70", "280.25"),
    ]
    assert [
        (row["period"], row["day"], row["cum_attributed_tvl_usd"])
        for row in records(result, "weekly_all")
    ] == [
        ("2026-07-20", "2026-07-21", "210.25"),
        ("2026-07-27", "2026-07-27", "280.25"),
    ]
    assert len(records(result, "daily_depositor_type")) == 9
    assert len(records(result, "weekly_depositor_type")) == 6
    assert all(result.summary["reconciliations"].values())


def test_attributed_tvl_rejects_disagreeing_repeated_cumulative_totals() -> None:
    rows = deepcopy(fixture(TVL_QUERY_ID)["rows"])
    rows[1]["cum_attributed_tvl_usd"] = "999"

    with pytest.raises(KyberSwapGrowthError, match="repeated totals disagree"):
        prepare_kyberswap_growth_attributed_tvl(
            rows,
            source_query_id=TVL_QUERY_ID,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=TVL_SOURCE_COLUMNS,
        )


def test_attributed_tvl_allows_capital_still_held_to_decline_between_days() -> None:
    rows = deepcopy(fixture(TVL_QUERY_ID)["rows"][:6])
    for row in rows[3:]:
        row["cum_attributed_tvl_usd"] = "150.125"

    result = prepare_kyberswap_growth_attributed_tvl(
        rows,
        source_query_id=TVL_QUERY_ID,
        source_execution_id="execution",
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=TVL_SOURCE_COLUMNS,
    )

    assert [
        row["cum_attributed_tvl_usd"] for row in records(result, "daily_all")
    ] == ["175.25", "150.125"]
    assert result.summary["reconciliations"][
        "repeated_cumulative_totals_agree"
    ] is True


@pytest.mark.parametrize(
    ("query_id", "function", "columns"),
    [
        (TVL_QUERY_ID, prepare_kyberswap_growth_attributed_tvl, TVL_SOURCE_COLUMNS),
        (
            BREAKDOWN_QUERY_ID,
            prepare_kyberswap_growth_breakdown,
            BREAKDOWN_SOURCE_COLUMNS,
        ),
    ],
)
def test_growth_sources_retain_and_warn_on_dynamic_depositor_classifications(
    query_id, function, columns
) -> None:
    rows = deepcopy(fixture(query_id)["rows"])
    rows[0]["depositor_type"] = "Zeta Depositor"
    rows[1]["depositor_type"] = "Alpha Depositor"

    result = function(
        rows,
        source_query_id=query_id,
        source_execution_id="execution",
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=columns,
    )

    assert result.summary["depositor_types"] == [
        "New Depositor",
        "Existing Depositor",
        "Past Depositor",
        "Alpha Depositor",
        "Zeta Depositor",
    ]
    assert result.warnings[-2:] == [
        {
            "code": "unexpected_depositor_type",
            "depositor_type": "Alpha Depositor",
            "message": "Unexpected depositor type Alpha Depositor was retained",
        },
        {
            "code": "unexpected_depositor_type",
            "depositor_type": "Zeta Depositor",
            "message": "Unexpected depositor type Zeta Depositor was retained",
        },
    ]
    assert result.summary["warning_count"] >= 2
    assert all(result.summary["reconciliations"].values())


def test_breakdown_daily_weekly_product_and_depositor_sums_reconcile() -> None:
    result = prepare_fixture(BREAKDOWN_QUERY_ID)

    assert result.columns == list(BREAKDOWN_OUTPUT_COLUMNS)
    assert all(tuple(row) == BREAKDOWN_OUTPUT_COLUMNS for row in result.rows)
    assert result.summary["totals"] == {
        "source": "206.5",
        "daily_product": "206.5",
        "weekly_product": "206.5",
        "daily_depositor_type": "206.5",
        "weekly_depositor_type": "206.5",
    }
    assert all(result.summary["reconciliations"].values())
    assert result.summary["products"] == list(EXPECTED_PRODUCT_ORDER)
    assert result.warnings == []
    first_product = records(result, "daily_product")[0]
    assert first_product["product_symbol"] == "eETH"
    assert first_product["depositor_type"] is None
    first_depositor = records(result, "daily_depositor_type")[0]
    assert first_depositor["product_symbol"] is None


def test_breakdown_retains_and_warns_on_unexpected_products() -> None:
    rows = deepcopy(fixture(BREAKDOWN_QUERY_ID)["rows"])
    rows[0]["product_symbol"] = "futureETH"
    result = prepare_kyberswap_growth_breakdown(
        rows,
        source_query_id=BREAKDOWN_QUERY_ID,
        source_execution_id="execution",
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=BREAKDOWN_SOURCE_COLUMNS,
    )

    assert result.summary["products"] == [
        "eETH",
        "liquidETH",
        "liquidUSD",
        "liquidBTC",
        "futureETH",
    ]
    assert result.warnings == [
        {
            "code": "unexpected_product",
            "product_symbol": "futureETH",
            "message": "Unexpected product futureETH was retained",
        }
    ]
    assert any(row["product_symbol"] == "futureETH" for row in result.rows)


def test_activity_preserves_distinct_integer_rows_and_all_eight_grains() -> None:
    payload = fixture(ACTIVITY_QUERY_ID)
    original_rows = deepcopy(payload["rows"])
    result = prepare_fixture(ACTIVITY_QUERY_ID)

    assert payload["rows"] == original_rows
    assert result.columns == list(ACTIVITY_OUTPUT_COLUMNS)
    assert all(tuple(row) == ACTIVITY_OUTPUT_COLUMNS for row in result.rows)
    assert len(result.rows) == len(original_rows)
    assert set(result.summary["row_counts"]) == {
        "day_product_deposits",
        "day_product_depositors",
        "day_depositor_type_deposits",
        "day_depositor_type_depositors",
        "week_product_deposits",
        "week_product_depositors",
        "week_depositor_type_deposits",
        "week_depositor_type_depositors",
    }
    assert all(type(row["metric_value"]) is int for row in result.rows)
    assert result.summary["distinct_grains"] is True
    assert result.summary["integer_values"] is True


def test_activity_retains_unexpected_product_with_warning() -> None:
    row = deepcopy(fixture(ACTIVITY_QUERY_ID)["rows"][0])
    row["category"] = "futureETH"
    result = prepare_kyberswap_growth_activity(
        [row],
        source_query_id=ACTIVITY_QUERY_ID,
        source_execution_id="execution",
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=ACTIVITY_SOURCE_COLUMNS,
    )

    assert result.rows[0]["category"] == "futureETH"
    assert result.summary["products"] == ["futureETH"]
    assert result.warnings[0]["code"] == "unexpected_product"


def test_activity_retains_dynamic_depositor_types_in_preferred_order() -> None:
    rows = deepcopy(fixture(ACTIVITY_QUERY_ID)["rows"])
    rows[2]["category"] = "Zeta Depositor"
    rows[6]["category"] = "Alpha Depositor"
    result = prepare_kyberswap_growth_activity(
        rows,
        source_query_id=ACTIVITY_QUERY_ID,
        source_execution_id="execution",
        source_last_updated=SOURCE_UPDATED,
        generated_at=GENERATED_AT,
        source_columns=ACTIVITY_SOURCE_COLUMNS,
    )

    assert result.summary["depositor_types"] == [
        "New Depositor",
        "Alpha Depositor",
        "Zeta Depositor",
    ]
    assert result.warnings == [
        {
            "code": "unexpected_depositor_type",
            "depositor_type": "Alpha Depositor",
            "message": "Unexpected depositor type Alpha Depositor was retained",
        },
        {
            "code": "unexpected_depositor_type",
            "depositor_type": "Zeta Depositor",
            "message": "Unexpected depositor type Zeta Depositor was retained",
        },
    ]
    assert {
        row["category"]
        for row in result.rows
        if row["category_type"] == "depositor_type"
    } == {"New Depositor", "Alpha Depositor", "Zeta Depositor"}


@pytest.mark.parametrize(
    ("query_id", "function", "columns", "field"),
    [
        (TVL_QUERY_ID, prepare_kyberswap_growth_attributed_tvl, TVL_SOURCE_COLUMNS, "depositor_type"),
        (
            BREAKDOWN_QUERY_ID,
            prepare_kyberswap_growth_breakdown,
            BREAKDOWN_SOURCE_COLUMNS,
            "depositor_type",
        ),
        (
            ACTIVITY_QUERY_ID,
            prepare_kyberswap_growth_activity,
            ACTIVITY_SOURCE_COLUMNS,
            "category",
        ),
    ],
)
def test_dynamic_depositor_classifications_must_still_be_trimmed(
    query_id, function, columns, field
) -> None:
    row = deepcopy(fixture(query_id)["rows"][0])
    if query_id == ACTIVITY_QUERY_ID:
        row["category_type"] = "depositor_type"
    row[field] = " Untrimmed Depositor "

    with pytest.raises(KyberSwapGrowthError, match="non-empty trimmed string"):
        function(
            [row],
            source_query_id=query_id,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=columns,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("timestamp_type", "month", "timestamp_type must be day or week"),
        ("category_type", "asset", "category_type must be product or depositor_type"),
        ("metric_type", "volume", "metric_type must be deposits or depositors"),
        ("metric_value", "1.5", "metric_value must be an integer"),
        ("metric_value", -1, "metric_value must not be negative"),
    ],
)
def test_activity_rejects_invalid_dimensions_and_values(field, value, message) -> None:
    row = deepcopy(fixture(ACTIVITY_QUERY_ID)["rows"][0])
    row[field] = value

    with pytest.raises(KyberSwapGrowthError, match=message):
        prepare_kyberswap_growth_activity(
            [row],
            source_query_id=ACTIVITY_QUERY_ID,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=ACTIVITY_SOURCE_COLUMNS,
        )


def test_activity_rejects_duplicate_grain_and_non_monday_week() -> None:
    row = deepcopy(fixture(ACTIVITY_QUERY_ID)["rows"][4])
    with pytest.raises(KyberSwapGrowthError, match="duplicate activity grain"):
        prepare_kyberswap_growth_activity(
            [row, deepcopy(row)],
            source_query_id=ACTIVITY_QUERY_ID,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=ACTIVITY_SOURCE_COLUMNS,
        )

    row["timestamp"] = "2026-07-28"
    with pytest.raises(KyberSwapGrowthError, match="weekly timestamp must be a Monday"):
        prepare_kyberswap_growth_activity(
            [row],
            source_query_id=ACTIVITY_QUERY_ID,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=ACTIVITY_SOURCE_COLUMNS,
        )


def test_post_referral_activity_builds_six_signed_daily_and_weekly_views() -> None:
    source_rows = post_referral_activity_rows()
    original_rows = deepcopy(source_rows)
    result = prepare_post_referral_activity(source_rows)

    assert source_rows == original_rows
    assert result.columns == list(POST_REFERRAL_ACTIVITY_OUTPUT_COLUMNS)
    assert all(
        tuple(row) == POST_REFERRAL_ACTIVITY_OUTPUT_COLUMNS for row in result.rows
    )
    assert set(result.summary["row_counts"]) == set(
        POST_REFERRAL_ACTIVITY_RECORD_TYPES
    )
    assert result.summary["record_types"] == list(
        POST_REFERRAL_ACTIVITY_RECORD_TYPES
    )
    assert result.summary["grouping_types"] == list(
        POST_REFERRAL_ACTIVITY_GROUPING_TYPES
    )
    assert result.summary["signed_values_preserved"] is True
    assert result.warnings == []

    weekly_projects = [
        (
            row["period"],
            row["category"],
            row["amount_usd"],
            row["granularity"],
            row["day"],
            row["week"],
        )
        for row in records(result, "weekly_project")
    ]
    assert weekly_projects == [
        ("2026-06-29", "spark", "400", "weekly", None, "2026-06-29"),
        (
            "2026-07-06",
            "aave",
            "-410.4062395041133",
            "weekly",
            None,
            "2026-07-06",
        ),
        (
            "2026-07-06",
            "spark",
            "10.4062395041133",
            "weekly",
            None,
            "2026-07-06",
        ),
    ]
    daily_projects = records(result, "daily_project")
    assert all(row["granularity"] == "daily" for row in daily_projects)
    assert any(
        row["period"] == "2026-07-05"
        and row["category"] == "spark"
        and row["amount_usd"] == "-38.98411887431797"
        for row in daily_projects
    )
    assert all(
        row["source_query_id"] == POST_REFERRAL_ACTIVITY_QUERY_ID
        and row["source_execution_id"] == "execution-8202133-test"
        and row["source_last_updated"] == "2026-08-02T08:00:00Z"
        and row["generated_at"] == GENERATED_AT
        for row in result.rows
    )


def test_post_referral_activity_view_totals_and_weekly_rollups_reconcile() -> None:
    result = prepare_post_referral_activity()

    assert result.summary["totals"] == {
        "source": "0",
        **{record_type: "0" for record_type in POST_REFERRAL_ACTIVITY_RECORD_TYPES},
    }
    assert result.summary["reconciliations"] == {
        "daily_label_equals_source": True,
        "weekly_label_equals_source": True,
        "weekly_label_equals_daily_rollup": True,
        "daily_project_equals_source": True,
        "weekly_project_equals_source": True,
        "weekly_project_equals_daily_rollup": True,
        "daily_event_equals_source": True,
        "weekly_event_equals_source": True,
        "weekly_event_equals_daily_rollup": True,
    }
    assert result.summary["categories"] == {
        "label": [
            "Deposit weETH into Spark",
            "Withdraw weETH from Aave",
            "Withdraw weETH from Spark",
        ],
        "project": ["aave", "spark"],
        "event": ["lending deposit", "lending withdraw"],
    }


def test_post_referral_activity_is_deterministic_and_preserves_decimal_precision() -> None:
    rows = post_referral_activity_rows()
    rows.append(
        {
            "day": "2026-07-06",
            "week": "2026-07-06",
            "project": "spark",
            "event": "lending deposit",
            "label": "Deposit weETH into Spark",
            "amount_usd": "0.000000000000000000000000000001",
        }
    )

    forward = prepare_post_referral_activity(rows)
    reverse = prepare_post_referral_activity(list(reversed(rows)))

    assert forward.rows == reverse.rows
    spark_week = next(
        row
        for row in records(forward, "weekly_project")
        if row["period"] == "2026-07-06" and row["category"] == "spark"
    )
    assert spark_week["amount_usd"] == "10.406239504113300000000000000001"
    assert all(forward.summary["reconciliations"].values())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("day", "not-a-day", "field day must be an ISO date"),
        ("week", "2026-07-01", "field week must be Monday"),
        ("project", "", "field project must be a non-empty trimmed string"),
        ("event", " lending deposit", "field event must be a non-empty trimmed string"),
        ("label", "Bad\nlabel", "field label is malformed"),
        ("amount_usd", "NaN", "field amount_usd must be finite"),
        ("amount_usd", float("inf"), "field amount_usd must be finite"),
        ("amount_usd", None, "field amount_usd must be numeric"),
    ],
)
def test_post_referral_activity_rejects_invalid_dates_text_and_amounts(
    field, value, message
) -> None:
    row = post_referral_activity_rows()[0]
    row[field] = value

    with pytest.raises(KyberSwapGrowthError, match=message):
        prepare_post_referral_activity([row])


def test_post_referral_activity_rejects_wrong_query_and_exact_schema_mismatches() -> None:
    rows = post_referral_activity_rows()
    kwargs = {
        "source_query_id": POST_REFERRAL_ACTIVITY_QUERY_ID,
        "source_execution_id": "execution",
        "source_last_updated": SOURCE_UPDATED,
        "generated_at": GENERATED_AT,
        "source_columns": POST_REFERRAL_ACTIVITY_SOURCE_COLUMNS,
    }
    with pytest.raises(KyberSwapGrowthError, match="returned no source rows"):
        prepare_kyberswap_post_referral_activity([], **kwargs)
    with pytest.raises(KyberSwapGrowthError, match="requires source query 8202133"):
        prepare_kyberswap_post_referral_activity(
            rows, **{**kwargs, "source_query_id": 1}
        )

    missing = deepcopy(rows[0])
    del missing["label"]
    with pytest.raises(KyberSwapGrowthError, match="missing label"):
        prepare_kyberswap_post_referral_activity([missing], **kwargs)

    unexpected = deepcopy(rows[0])
    unexpected["unexpected"] = True
    with pytest.raises(KyberSwapGrowthError, match="unexpected unexpected"):
        prepare_kyberswap_post_referral_activity([unexpected], **kwargs)

    with pytest.raises(
        KyberSwapGrowthError,
        match="latest-result schema mismatch",
    ):
        prepare_kyberswap_post_referral_activity(
            rows,
            **{
                **kwargs,
                "source_columns": (
                    *POST_REFERRAL_ACTIVITY_SOURCE_COLUMNS[:-1],
                    "unexpected",
                ),
            },
        )


@pytest.mark.parametrize(
    ("query_id", "field"),
    [
        (DEPOSITS_QUERY_ID, "weekly_deposits_usd"),
        (TVL_QUERY_ID, "cum_attributed_tvl_usd"),
        (BREAKDOWN_QUERY_ID, "product_symbol"),
        (ACTIVITY_QUERY_ID, "category_type"),
    ],
)
def test_every_transform_rejects_missing_or_unexpected_schema(query_id, field) -> None:
    payload = fixture(query_id)
    functions = {
        DEPOSITS_QUERY_ID: prepare_kyberswap_growth_deposits,
        TVL_QUERY_ID: prepare_kyberswap_growth_attributed_tvl,
        BREAKDOWN_QUERY_ID: prepare_kyberswap_growth_breakdown,
        ACTIVITY_QUERY_ID: prepare_kyberswap_growth_activity,
    }
    row = deepcopy(payload["rows"][0])
    del row[field]
    with pytest.raises(KyberSwapGrowthError, match=f"missing {field}"):
        functions[query_id](
            [row],
            source_query_id=query_id,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=payload["columns"],
        )

    row = deepcopy(payload["rows"][0])
    row["unexpected"] = 1
    with pytest.raises(KyberSwapGrowthError, match="unexpected unexpected"):
        functions[query_id](
            [row],
            source_query_id=query_id,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=payload["columns"],
        )


def test_transforms_reject_wrong_query_empty_rows_and_bad_source_metadata() -> None:
    payload = fixture(DEPOSITS_QUERY_ID)
    kwargs = {
        "source_query_id": DEPOSITS_QUERY_ID,
        "source_execution_id": "execution",
        "source_last_updated": SOURCE_UPDATED,
        "generated_at": GENERATED_AT,
        "source_columns": payload["columns"],
    }
    with pytest.raises(KyberSwapGrowthError, match="returned no source rows"):
        prepare_kyberswap_growth_deposits([], **kwargs)
    with pytest.raises(KyberSwapGrowthError, match="requires source query"):
        prepare_kyberswap_growth_deposits(
            payload["rows"], **{**kwargs, "source_query_id": 1}
        )
    with pytest.raises(KyberSwapGrowthError, match="source_execution_id"):
        prepare_kyberswap_growth_deposits(
            payload["rows"], **{**kwargs, "source_execution_id": ""}
        )
    with pytest.raises(KyberSwapGrowthError, match="must include a timezone"):
        prepare_kyberswap_growth_deposits(
            payload["rows"],
            **{**kwargs, "source_last_updated": "2026-08-02T08:00:00"},
        )


@pytest.mark.parametrize(
    ("function", "query_id", "columns"),
    [
        (prepare_kyberswap_growth_deposits, DEPOSITS_QUERY_ID, DEPOSITS_SOURCE_COLUMNS),
        (prepare_kyberswap_growth_attributed_tvl, TVL_QUERY_ID, TVL_SOURCE_COLUMNS),
        (prepare_kyberswap_growth_breakdown, BREAKDOWN_QUERY_ID, BREAKDOWN_SOURCE_COLUMNS),
        (prepare_kyberswap_growth_activity, ACTIVITY_QUERY_ID, ACTIVITY_SOURCE_COLUMNS),
    ],
)
def test_declared_source_schema_must_be_exact(function, query_id, columns) -> None:
    payload = fixture(query_id)
    with pytest.raises(KyberSwapGrowthError, match="latest-result schema mismatch"):
        function(
            payload["rows"],
            source_query_id=query_id,
            source_execution_id="execution",
            source_last_updated=SOURCE_UPDATED,
            generated_at=GENERATED_AT,
            source_columns=(*columns[:-1], "unexpected"),
        )
