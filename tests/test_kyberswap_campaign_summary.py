from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.prepare_kyberswap_campaign_summary import (
    EXPECTED_NUMERIC_COLUMNS,
    METHODOLOGY_ID,
    OUTPUT_COLUMNS,
    SOURCE_QUERY_ID,
    KyberSwapCampaignSummaryError,
    prepare_kyberswap_campaign_summary,
)


def source_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "rank_": 1,
        "key_": "all_time_data",
        "total_deposits_usd": "481905421.49167466",
        "outstanding_balance_usd": "374476858.39556485",
        "num_depositors": 550,
        "new_depositors": 408,
        "deposits_by_new_depositors": "397690600.9317606",
        "retention_rate": "0.7770754212235694",
        "depositors_new_users_rate": "0.8252461649025691",
        "revenue_generated": 0,
    }
    row.update(overrides)
    return row


def prepare(rows: list[dict[str, object]], *, source_columns=()):
    return prepare_kyberswap_campaign_summary(
        rows,
        source_query_id=SOURCE_QUERY_ID,
        source_execution_id="execution-8180894-test",
        source_last_updated="2026-08-01T02:30:00+01:00",
        generated_at="2026-08-01T01:31:00Z",
        source_columns=source_columns,
    )


def test_prepares_every_source_column_and_stable_execution_provenance() -> None:
    source = source_row(extra_source_dimension="campaign")
    result = prepare([source], source_columns=tuple(source))

    assert result.rows[0] == {
        **source,
        "source_query_id": 8180894,
        "source_execution_id": "execution-8180894-test",
        "source_last_updated": "2026-08-01T01:30:00Z",
        "generated_at": "2026-08-01T01:31:00Z",
    }
    assert result.columns == [
        *source,
        "source_query_id",
        "source_execution_id",
        "source_last_updated",
        "generated_at",
    ]
    assert result.summary == {
        "source_rows": 1,
        "interval_keys": ["all_time_data"],
        "fallback_value_count": 0,
        "warning_count": 0,
        "source_last_updated": "2026-08-01T01:30:00Z",
    }
    assert result.warnings == []


def test_output_contract_contains_all_expected_source_and_provenance_columns() -> None:
    assert OUTPUT_COLUMNS == (
        "rank_",
        "key_",
        *EXPECTED_NUMERIC_COLUMNS,
        "source_query_id",
        "source_execution_id",
        "source_last_updated",
        "generated_at",
    )
    assert METHODOLOGY_ID == "kyberswap_campaign_summary_v1"


def test_missing_and_null_numeric_values_default_only_prepared_rows_to_zero() -> None:
    source = source_row(outstanding_balance_usd=None)
    del source["revenue_generated"]

    result = prepare([source])

    assert source["outstanding_balance_usd"] is None
    assert "revenue_generated" not in source
    assert result.rows[0]["outstanding_balance_usd"] == 0
    assert result.rows[0]["revenue_generated"] == 0
    assert result.summary["fallback_value_count"] == 2
    assert result.warnings == [
        {
            "code": "missing_numeric_value_defaulted",
            "key_": "all_time_data",
            "column": "outstanding_balance_usd",
            "affected_metric": "Attributed TVL",
        },
        {
            "code": "missing_numeric_value_defaulted",
            "key_": "all_time_data",
            "column": "revenue_generated",
            "affected_metric": "Revenue Generated",
        },
    ]


def test_missing_total_does_not_create_a_false_cross_field_contradiction() -> None:
    source = source_row()
    del source["total_deposits_usd"]

    result = prepare([source])

    assert result.rows[0]["total_deposits_usd"] == 0
    assert result.summary["fallback_value_count"] == 1


def test_duplicate_interval_key_fails() -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match="duplicate interval"):
        prepare(
            [
                source_row(),
                source_row(rank_=2, key_="all_time_data"),
            ]
        )


def test_missing_interval_key_fails() -> None:
    source = source_row()
    del source["key_"]

    with pytest.raises(KyberSwapCampaignSummaryError, match="missing source columns: key_"):
        prepare([source])


@pytest.mark.parametrize(
    "key",
    [None, "", " all_time_data", "all_time_data ", "ALL_TIME_DATA", "30d data", 30],
)
def test_malformed_interval_key_fails(key: object) -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match="interval key"):
        prepare([source_row(key_=key)])


@pytest.mark.parametrize("rank", [None, 0, -1, "1.5", True, "not-a-rank"])
def test_rank_must_be_a_positive_integer(rank: object) -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match="rank_"):
        prepare([source_row(rank_=rank)])


@pytest.mark.parametrize("value", ["", "not-a-number", True, float("inf"), object()])
def test_malformed_numeric_value_fails(value: object) -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match="retention_rate"):
        prepare([source_row(retention_rate=value)])


@pytest.mark.parametrize(
    "column",
    [
        "total_deposits_usd",
        "outstanding_balance_usd",
        "deposits_by_new_depositors",
        "num_depositors",
        "new_depositors",
    ],
)
def test_deposit_and_user_count_values_must_not_be_negative(column: str) -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match=column):
        prepare([source_row(**{column: -1})])


@pytest.mark.parametrize("column", ["num_depositors", "new_depositors"])
def test_user_counts_must_be_integral(column: str) -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match="integer"):
        prepare([source_row(**{column: "1.25"})])


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("retention_rate", "-0.01"),
        ("retention_rate", "1.01"),
        ("depositors_new_users_rate", "-0.01"),
        ("depositors_new_users_rate", "1.01"),
    ],
)
def test_rates_must_be_bounded(column: str, value: str) -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match="between 0 and 1"):
        prepare([source_row(**{column: value})])


@pytest.mark.parametrize(
    ("left_column", "right_column", "left_value", "right_value"),
    [
        ("outstanding_balance_usd", "total_deposits_usd", 101, 100),
        ("new_depositors", "num_depositors", 11, 10),
        ("deposits_by_new_depositors", "total_deposits_usd", 101, 100),
    ],
)
def test_serious_cross_field_contradictions_fail(
    left_column: str,
    right_column: str,
    left_value: int,
    right_value: int,
) -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match="contradictory values"):
        prepare(
            [
                source_row(
                    **{
                        left_column: left_value,
                        right_column: right_value,
                    }
                )
            ]
        )


def test_empty_latest_result_fails() -> None:
    with pytest.raises(KyberSwapCampaignSummaryError, match="no source rows"):
        prepare([])


def test_fixture_matches_the_live_all_time_row_shape() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "studio"
        / "fixtures"
        / "query_8180894.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert fixture["query_id"] == 8180894
    assert fixture["execution_id"] == "fixture-8180894-latest"
    assert fixture["columns"] == list(OUTPUT_COLUMNS[:-4])
    assert fixture["rows"] == [source_row()]
