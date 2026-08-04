from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import scripts.fetch_studio_data as fetch_studio_data
import scripts.studio_ingestion as studio_ingestion
from scripts.studio import publish_studio_generated_data
from scripts.studio_ingestion import (
    DuneLatestResultClient,
    FailureCategory,
    FixtureDuneClient,
    RetryPolicy,
    RoutedStudioLatestResultClient,
    SequenceStudioLatestResultClient,
    SnapshotStore,
    StudioIngestionError,
    StudioProviderResult,
    StudioQueryRequest,
    build_query_requests,
    classify_freshness,
    fetch_latest_result_with_retry,
    generated_query_ids,
    load_query_requests,
    normalize_provider_result,
    prepare_provider_result,
    prepare_raw_provider_result,
    refresh_studio_data,
    sha256_bytes,
    sha256_json,
    strict_json_loads,
    validate_current_snapshot,
    validate_snapshot_directory,
)


NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def fixed_clock() -> datetime:
    return NOW


def registry_fixture(scenario: str = "success"):
    dashboards, _, requests = load_query_requests()
    return requests, FixtureDuneClient(
        requests,
        dashboards,
        scenario=scenario,
        clock=fixed_clock,
    )


def generated_registry_fixture(scenario: str = "success"):
    dashboards, _, requests = load_query_requests()
    selected = generated_query_ids(dashboards, requests)
    return requests, selected, FixtureDuneClient(
        requests,
        dashboards,
        scenario=scenario,
        clock=fixed_clock,
    )


def minimal_request(**overrides) -> StudioQueryRequest:
    values = {
        "query_id": 123,
        "query_url": "https://dune.com/queries/123",
        "result_file": "query_123.json",
        "data_source": "values",
        "source_label": "Values",
        "dashboard_ids": ("dashboard",),
        "metric_ids": ("metric",),
        "required_columns": ("value",),
        "optional_columns": (),
        "date_columns": (),
        "address_columns": (),
        "transaction_columns": (),
        "dimension_columns": (),
        "value_columns": ("value",),
        "allow_empty": False,
        "is_exportable": True,
        "freshness_policy": {
            "expected_refresh_hours": 12,
            "warning_after_hours": 24,
            "stale_after_hours": 48,
        },
    }
    values.update(overrides)
    return StudioQueryRequest(**values)


def provider_result(**overrides) -> StudioProviderResult:
    values = {
        "query_id": 123,
        "status": "success",
        "columns": ["value"],
        "rows": [{"value": 42}],
        "fetched_at": "2026-07-31T12:00:00Z",
        "execution_started_at": "2026-07-31T11:58:00Z",
        "execution_finished_at": "2026-07-31T11:59:00Z",
        "data_updated_at": "2026-07-31T11:59:00Z",
        "execution_id": "fixture-123",
        "total_row_count": 1,
    }
    values.update(overrides)
    return StudioProviderResult(**values)


def normalize(result: StudioProviderResult, request: StudioQueryRequest | None = None):
    return normalize_provider_result(
        result,
        request or minimal_request(),
        checked_at=NOW,
        mode="fixture",
        fetch_attempts=1,
    )


def test_query_requests_deduplicate_queries_and_union_metric_contracts():
    dashboards, metrics, requests = load_query_requests()

    assert len(dashboards) == 1
    assert len(metrics) == 24
    assert set(requests) == {
        8180894,
        8191379,
        8191704,
        8193003,
        8193040,
        8199058,
        8202133,
        8204345,
        8204373,
    }
    shared = requests[8180894]
    assert shared.metric_ids == (
        "kyber_total_referral_deposits",
        "kyber_attributed_tvl",
        "kyber_new_depositor_deposits",
        "kyber_new_depositor_deposit_rate",
        "kyber_total_depositors",
        "kyber_new_depositors",
        "kyber_retention_rate",
        "kyber_revenue_generated",
    )
    assert "key_" in shared.required_columns
    assert "revenue_generated" in shared.required_columns
    assert shared.result_file == "query_8180894.json"
    assert shared.query_url == "https://dune.com/queries/8180894"
    assert shared.provider_mode == "latest_result"
    assert shared.source_required_columns == ("rank_", "key_")
    assert shared.transformation["id"] == "kyberswap_campaign_summary"
    assert shared.transformation["methodology_id"] == (
        "kyberswap_campaign_summary_v1"
    )
    assert shared.transformation["raw_data_file"] == "raw_query_8180894.json"
    attribution = requests[8199058]
    assert attribution.metric_ids == (
        "kyber_attributed_tvl_by_location",
        "kyber_capital_journey",
        "kyber_product_adoption",
        "kyber_top_referred_depositors",
        "kyber_referral_deposit_concentration",
        "kyber_top_depositors",
        "kyber_wallet_investigation",
    )
    assert attribution.provider_mode == "latest_result"
    assert "current_token_category" in attribution.source_required_columns
    assert "depositor_type" in attribution.source_required_columns
    assert "base_asset_price" not in attribution.source_required_columns
    assert attribution.transformation["raw_data_file"] == (
        "raw_query_8199058.json"
    )
    growth_metrics = {
        8191379: ("kyber_referral_deposits_growth",),
        8191704: ("kyber_attributed_tvl_over_time",),
        8193003: (
            "kyber_referral_deposits_breakdown",
            "kyber_total_referral_deposits_breakdown",
        ),
        8193040: (
            "kyber_deposit_depositor_count_by_product",
            "kyber_deposit_depositor_count_by_depositor_type",
        ),
    }
    for query_id, metric_ids in growth_metrics.items():
        request = requests[query_id]
        assert request.metric_ids == metric_ids
        assert request.provider_mode == "latest_result"
        assert request.transformation["id"].startswith("kyberswap_growth_")
        assert request.transformation["raw_data_file"] == (
            f"raw_query_{query_id}.json"
        )
    activity = requests[8202133]
    assert activity.metric_ids == ("kyber_post_referral_activity",)
    assert activity.provider_mode == "latest_result"
    assert activity.transformation["id"] == "kyberswap_post_referral_activity"
    assert activity.transformation["raw_data_file"] == "raw_query_8202133.json"
    deposits = requests[8204345]
    assert deposits.metric_ids == ("kyber_recent_referral_deposits",)
    assert deposits.transformation["id"] == "kyberswap_referral_deposits"
    assert deposits.transformation["raw_data_file"] == "raw_query_8204345.json"
    activity_events = requests[8204373]
    assert activity_events.metric_ids == ("kyber_recent_etherfi_activity",)
    assert activity_events.transformation["id"] == "kyberswap_etherfi_activity"
    assert activity_events.transformation["raw_data_file"] == "raw_query_8204373.json"
    assert 8182330 not in requests


def test_fixture_client_reuses_realistic_query_fixtures_and_tracks_calls():
    requests, client = registry_fixture()

    summary = client.fetch_latest_result(8204345, timeout_seconds=1)
    client.fetch_latest_result(8204345, timeout_seconds=1)

    assert len(summary.rows) == 4
    assert "address" in summary.columns
    assert "amount_usd" in summary.columns
    assert summary.provider_metadata["source_bundle"] == "kyberswap.json"
    assert client.calls == {8204345: 2}
    assert requests[8204345].metric_ids == ("kyber_recent_referral_deposits",)


@pytest.mark.parametrize(
    ("scenario", "category"),
    [
        ("missing_required_column", FailureCategory.TRANSFORMATION_FAILURE),
        ("malformed_row", FailureCategory.TRANSFORMATION_FAILURE),
        ("invalid_date", FailureCategory.TRANSFORMATION_FAILURE),
        ("partial_refresh", FailureCategory.PARTIAL_RESULT),
        ("row_count_mismatch", FailureCategory.PARTIAL_RESULT),
        ("empty_result", FailureCategory.TRANSFORMATION_FAILURE),
    ],
)
def test_fixture_schema_failures_are_deterministic(scenario, category):
    requests, client = registry_fixture(scenario)
    query_id = int(client.scenario["query_id"])
    result = client.fetch_latest_result(query_id, timeout_seconds=1)

    with pytest.raises(StudioIngestionError, match=f"Query {query_id}") as exc_info:
        raw_metadata, raw_files = prepare_raw_provider_result(
            result,
            requests[query_id],
        )
        prepared = prepare_provider_result(
            result,
            requests[query_id],
            checked_at=NOW,
            raw_metadata=raw_metadata,
            raw_supporting_files=raw_files,
        )
        normalize_provider_result(
            prepared.result,
            requests[query_id],
            checked_at=NOW,
            mode="fixture",
            fetch_attempts=1,
            transformation_metadata=prepared.metadata,
            supporting_files=prepared.supporting_files,
        )

    assert exc_info.value.category is category
    assert client.calls[query_id] == 1


def test_normalization_preserves_unexpected_columns_nulls_duplicates_and_numeric_strings():
    extra_result = normalize(
        provider_result(
            columns=["value", "fixture_note"],
            rows=[{"value": 42, "fixture_note": "deterministic-extra-column"}],
        )
    )
    assert "fixture_note" in extra_result.artifact["unexpected_columns"]
    assert all(row["fixture_note"] == "deterministic-extra-column" for row in extra_result.artifact["rows"])

    duplicate_result = normalize(
        provider_result(
            rows=[{"value": 42}, {"value": 42}],
            total_row_count=2,
        )
    )
    assert duplicate_result.artifact["duplicate_row_count"] == 1

    null_result = normalize(
        provider_result(
            columns=["value", "nullable"],
            rows=[{"value": 42, "nullable": None}],
        ),
        minimal_request(optional_columns=("nullable",)),
    )
    assert null_result.artifact["rows"][0]["nullable"] is None

    large_result = normalize(
        provider_result(rows=[{"value": "12345678901234567890.123456789"}])
    )
    assert large_result.artifact["rows"][0]["value"] == "12345678901234567890.123456789"

    chain_result = normalize(
        provider_result(
            columns=["value", "chain"],
            rows=[
                {"value": 1, "chain": "ethereum"},
                {"value": 2, "chain": "arbitrum"},
                {"value": 3, "chain": "base"},
            ],
            total_row_count=3,
        )
    )
    assert [
        row["chain"] for row in chain_result.artifact["rows"][:3]
    ] == ["ethereum", "arbitrum", "base"]
    assert "chain" in chain_result.artifact["unexpected_columns"]


def test_normalization_is_deterministic_but_preserves_row_order():
    request = minimal_request(
        required_columns=("value",),
        optional_columns=("label",),
    )
    result = provider_result(
        columns=["extra", "label", "value"],
        rows=[
            {"label": "second", "value": 2, "extra": True},
            {"extra": False, "value": 1, "label": "first"},
        ],
        total_row_count=2,
    )

    normalized = normalize(result, request)

    assert normalized.artifact["columns"] == ["value", "label", "extra"]
    assert [row["value"] for row in normalized.artifact["rows"]] == [2, 1]
    assert list(normalized.artifact["rows"][0]) == ["value", "label", "extra"]


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), {"nested": True}, [1]])
def test_normalization_rejects_unsafe_or_ambiguous_values(bad_value):
    with pytest.raises(StudioIngestionError) as exc_info:
        normalize(provider_result(rows=[{"value": bad_value}]))

    assert exc_info.value.category is FailureCategory.INVALID_VALUE


def test_normalization_rejects_invalid_date_values():
    request = minimal_request(
        required_columns=("day", "value"),
        date_columns=("day",),
    )
    result = provider_result(
        columns=["day", "value"],
        rows=[{"day": "not-a-date", "value": 42}],
    )

    with pytest.raises(StudioIngestionError) as exc_info:
        normalize(result, request)

    assert exc_info.value.category is FailureCategory.INVALID_DATE


def test_normalization_rejects_non_string_row_keys_as_invalid_rows():
    with pytest.raises(StudioIngestionError) as exc_info:
        normalize(provider_result(rows=[{1: 42}], columns=["value"]))

    assert exc_info.value.category is FailureCategory.INVALID_ROW
    assert "non-string column key" in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    ['{"value": 1, "value": 2}', '{"value": NaN}', '{"value": Infinity}'],
)
def test_strict_json_loader_rejects_duplicate_keys_and_non_finite_numbers(payload):
    with pytest.raises(ValueError):
        strict_json_loads(payload)


def test_live_json_decode_and_normalization_preserve_unsafe_numeric_lexemes():
    decoded = strict_json_loads(
        '{"rows":[{"value":12345678901234567890.123456789,'
        '"whole":9007199254740993}]}',
        preserve_decimal_lexemes=True,
    )

    assert decoded["rows"][0]["value"] == "12345678901234567890.123456789"
    assert decoded["rows"][0]["whole"] == "9007199254740993"
    result = provider_result(
        columns=["value", "whole"],
        rows=decoded["rows"],
        total_row_count=1,
    )
    request = minimal_request(
        required_columns=("value", "whole"),
        value_columns=("value", "whole"),
    )

    normalized = normalize(result, request)

    assert normalized.artifact["rows"] == [
        {
            "value": "12345678901234567890.123456789",
            "whole": "9007199254740993",
        }
    ]
    serialized = normalized.file_bytes.decode("utf-8")
    assert '"value": "12345678901234567890.123456789"' in serialized
    assert '"whole": "9007199254740993"' in serialized


def test_custom_clients_serialize_unsafe_integer_scalars_as_exact_strings():
    normalized = normalize(
        provider_result(rows=[{"value": 9007199254740993}])
    )

    assert normalized.artifact["rows"][0]["value"] == "9007199254740993"


def test_identifier_columns_validate_non_null_values_and_allow_nulls():
    address = "0x" + "12" * 20
    transaction = "0x" + "ab" * 32
    request = minimal_request(
        required_columns=("wallet", "tx_hash", "value"),
        address_columns=("wallet",),
        transaction_columns=("tx_hash",),
    )
    valid = provider_result(
        columns=["wallet", "tx_hash", "value"],
        rows=[{"wallet": address, "tx_hash": transaction, "value": 1}],
    )
    assert normalize(valid, request).artifact["rows"][0]["wallet"] == address

    nullable = provider_result(
        columns=["wallet", "tx_hash", "value"],
        rows=[{"wallet": None, "tx_hash": None, "value": 1}],
    )
    assert normalize(nullable, request).artifact["rows"][0]["tx_hash"] is None

    invalid = provider_result(
        columns=["wallet", "tx_hash", "value"],
        rows=[{"wallet": "0x1234", "tx_hash": transaction, "value": 1}],
    )
    with pytest.raises(StudioIngestionError, match="EVM address"):
        normalize(invalid, request)


@pytest.mark.parametrize("bad_value", [True, "not-a-number", "NaN", "Infinity", ""])
def test_value_columns_require_finite_numeric_shape_without_coercion(bad_value):
    with pytest.raises(StudioIngestionError) as exc_info:
        normalize(provider_result(rows=[{"value": bad_value}]))

    assert exc_info.value.category is FailureCategory.INVALID_VALUE


@pytest.mark.parametrize(
    "timestamp_overrides",
    [
        {
            "execution_started_at": "2026-07-31T12:00:00Z",
            "execution_finished_at": "2026-07-31T11:59:00Z",
        },
        {"fetched_at": "2026-07-31T12:06:00Z"},
        {"data_updated_at": "2026-07-31T12:06:00Z"},
    ],
)
def test_normalization_rejects_inconsistent_or_future_provider_timestamps(
    timestamp_overrides,
):
    with pytest.raises(StudioIngestionError) as exc_info:
        normalize(provider_result(**timestamp_overrides))

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE


def test_reordered_provider_columns_normalize_to_contract_order():
    request = minimal_request(
        required_columns=(
            "day",
            "total_value_usd",
            "deposits_usd",
            "withdrawals_usd",
            "fees_usd",
        ),
        value_columns=(
            "total_value_usd",
            "deposits_usd",
            "withdrawals_usd",
            "fees_usd",
        ),
        date_columns=("day",),
    )
    normalized = normalize(
        provider_result(
            columns=[
                "fees_usd",
                "withdrawals_usd",
                "deposits_usd",
                "total_value_usd",
                "day",
            ],
            rows=[{
                "day": "2026-07-31",
                "total_value_usd": 100,
                "deposits_usd": 20,
                "withdrawals_usd": 5,
                "fees_usd": 1,
            }],
        ),
        request,
    )

    assert normalized.artifact["columns"][:5] == [
        "day",
        "total_value_usd",
        "deposits_usd",
        "withdrawals_usd",
        "fees_usd",
    ]
    assert normalized.artifact["row_count"] == 1


def test_freshness_classifier_has_current_delayed_and_stale_boundaries():
    policy = {
        "warning_after_hours": 24,
        "stale_after_hours": 48,
    }
    assert classify_freshness("2026-07-30T12:00:00Z", policy, NOW) == "current"
    assert classify_freshness("2026-07-30T11:59:59Z", policy, NOW) == "delayed"
    assert classify_freshness("2026-07-29T11:59:59Z", policy, NOW) == "stale"


def test_normalization_uses_execution_completion_for_freshness():
    normalized = normalize(
        provider_result(
            execution_started_at="2026-07-28T11:58:00Z",
            execution_finished_at="2026-07-28T11:59:00Z",
            data_updated_at="2026-07-31T11:59:00Z",
        )
    )

    assert normalized.artifact["freshness_status"] == "stale"
    assert normalized.artifact["execution_finished_at"] == (
        "2026-07-28T11:59:00Z"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_attempts": True},
        {"max_attempts": 0},
        {"base_delay_seconds": True},
        {"base_delay_seconds": -1},
        {"base_delay_seconds": float("nan")},
        {"max_delay_seconds": float("inf")},
    ],
)
def test_retry_policy_rejects_invalid_direct_construction(overrides):
    with pytest.raises(ValueError):
        RetryPolicy(**overrides)


@pytest.mark.parametrize(
    ("scenario", "expected_calls", "expected_delays"),
    [
        ("rate_limited_once", 2, [0.0]),
        ("timeout_once", 2, [0.25]),
    ],
)
def test_retryable_fixture_failures_use_bounded_backoff(
    scenario,
    expected_calls,
    expected_delays,
):
    requests, client = registry_fixture(scenario)
    query_id = int(client.scenario["query_id"])
    delays: list[float] = []

    result, attempts = fetch_latest_result_with_retry(
        client,
        requests[query_id],
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.25),
        timeout_seconds=1,
        sleeper=delays.append,
    )

    assert result.query_id == query_id
    assert attempts == expected_calls
    assert client.calls[query_id] == expected_calls
    assert delays == expected_delays


def test_observed_failed_latest_execution_is_not_retried():
    requests, client = registry_fixture("query_execution_failed")
    query_id = int(client.scenario["query_id"])

    with pytest.raises(StudioIngestionError) as exc_info:
        fetch_latest_result_with_retry(
            client,
            requests[query_id],
            retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0),
            timeout_seconds=1,
            sleeper=lambda _: None,
        )

    assert exc_info.value.category is FailureCategory.QUERY_EXECUTION_FAILED
    assert client.calls[query_id] == 1


def test_dune_latest_result_client_supports_read_only_result_pagination():
    seen_urls: list[str] = []

    def transport(url, headers, timeout):
        seen_urls.append(url)
        assert headers["X-Dune-API-Key"] == "test-key"
        assert timeout == 5
        if len(seen_urls) == 1:
            return 200, {}, {
                "query_id": 123,
                "execution_id": "exec-1",
                "state": "QUERY_STATE_COMPLETED",
                "execution_started_at": "2026-07-31T11:58:00Z",
                "execution_ended_at": "2026-07-31T11:59:00Z",
                "next_uri": (
                    "https://api.dune.com/api/v1/execution/exec-1/results"
                    "?offset=1&limit=1000"
                ),
                "result": {
                    "rows": [{"value": 1}],
                    "metadata": {
                        "column_names": ["value"],
                        "total_row_count": 2,
                    },
                },
            }
        return 200, {}, {
            "query_id": 123,
            "execution_id": "exec-1",
            "state": "QUERY_STATE_COMPLETED",
            "execution_ended_at": "2026-07-31T11:59:00Z",
            "result": {
                "rows": [{"value": 2}],
                "metadata": {"column_names": ["value"]},
            },
        }

    client = DuneLatestResultClient("test-key", transport=transport, clock=fixed_clock)
    result = client.fetch_latest_result(123, timeout_seconds=5)

    assert result.rows == [{"value": 1}, {"value": 2}]
    assert result.execution_id == "exec-1"
    assert result.execution_finished_at == "2026-07-31T11:59:00Z"
    assert seen_urls == [
        "https://api.dune.com/api/v1/query/123/results?limit=1000",
        (
            "https://api.dune.com/api/v1/execution/exec-1/results"
            "?offset=1&limit=1000"
        ),
    ]
    assert all("/execute" not in url for url in seen_urls)
    assert all("max_age_hours" not in url for url in seen_urls)
    assert "test-key" not in json.dumps(result.provider_metadata)


def test_dune_latest_result_client_rejects_malformed_response_without_retrying():
    calls = 0

    def transport(url, headers, timeout):
        nonlocal calls
        del url, headers, timeout
        calls += 1
        return 200, {}, {"state": "QUERY_STATE_COMPLETED", "result": {}}

    client = DuneLatestResultClient("test-key", transport=transport)
    request = minimal_request()
    with pytest.raises(StudioIngestionError) as exc_info:
        fetch_latest_result_with_retry(
            client,
            request,
            retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0),
            timeout_seconds=1,
            sleeper=lambda _: None,
        )

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE
    assert calls == 1


def test_dune_latest_result_client_rejects_cross_origin_pagination_without_leaking_key():
    calls = 0

    def transport(url, headers, timeout):
        nonlocal calls
        del url, headers, timeout
        calls += 1
        return 200, {}, {
            "query_id": 123,
            "execution_id": "exec-1",
            "state": "QUERY_STATE_COMPLETED",
            "execution_started_at": "2026-07-31T11:58:00Z",
            "execution_ended_at": "2026-07-31T11:59:00Z",
            "next_uri": "https://attacker.example/steal",
            "result": {
                "rows": [{"value": 1}],
                "metadata": {
                    "column_names": ["value"],
                    "total_row_count": 1,
                },
            },
        }

    client = DuneLatestResultClient("secret-test-key", transport=transport, clock=fixed_clock)
    with pytest.raises(StudioIngestionError) as exc_info:
        client.fetch_latest_result(123, timeout_seconds=1)

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE
    assert "secret-test-key" not in str(exc_info.value)
    assert calls == 1


@pytest.mark.parametrize(
    "next_uri",
    [
        "https://api.dune.com/api/v1/query/123/execute",
        "https://api.dune.com/api/v1/query/999/results?offset=1&limit=1000",
        "https://api.dune.com/api/v1/execution/other-exec/results?offset=1",
        "https://api.dune.com/api/v1/sql/execute",
        "https://api.dune.com/api/v1/query/123/results?max_age_hours=1",
        "https://api.dune.com/api/v1/query/123/results?offset=1&offset=2",
        "https://api.dune.com/api/v1/query/123/results?offset=1#fragment",
        "https://api.dune.com/api/v1/query/123/results?limit=1001&offset=1",
    ],
)
def test_dune_latest_result_client_rejects_unsafe_pagination_options(next_uri):
    calls = 0

    def transport(url, headers, timeout):
        nonlocal calls
        del url, headers, timeout
        calls += 1
        return 200, {}, {
            "query_id": 123,
            "execution_id": "exec-1",
            "state": "QUERY_STATE_COMPLETED",
            "execution_started_at": "2026-07-31T11:58:00Z",
            "execution_ended_at": "2026-07-31T11:59:00Z",
            "next_uri": next_uri,
            "result": {
                "rows": [{"value": 1}],
                "metadata": {
                    "column_names": ["value"],
                    "total_row_count": 1,
                },
            },
        }

    with pytest.raises(StudioIngestionError) as exc_info:
        DuneLatestResultClient(
            "test-key",
            transport=transport,
            clock=fixed_clock,
        ).fetch_latest_result(123, timeout_seconds=1)

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE
    assert calls == 1


def test_dune_latest_result_client_requires_execution_id():
    payload = {
        "query_id": 123,
        "state": "QUERY_STATE_COMPLETED",
        "execution_started_at": "2026-07-31T11:58:00Z",
        "execution_ended_at": "2026-07-31T11:59:00Z",
        "result": {
            "rows": [{"value": 1}],
            "metadata": {
                "column_names": ["value"],
                "total_row_count": 1,
            },
        },
    }
    client = DuneLatestResultClient(
        "test-key",
        transport=lambda url, headers, timeout: (200, {}, payload),
        clock=fixed_clock,
    )

    with pytest.raises(StudioIngestionError) as exc_info:
        client.fetch_latest_result(123, timeout_seconds=1)

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE
    assert "execution ID" in str(exc_info.value)


def test_dune_latest_result_client_requires_total_row_count():
    payload = {
        "query_id": 123,
        "execution_id": "exec-1",
        "state": "QUERY_STATE_COMPLETED",
        "execution_started_at": "2026-07-31T11:58:00Z",
        "execution_ended_at": "2026-07-31T11:59:00Z",
        "result": {
            "rows": [{"value": 1}],
            "metadata": {"column_names": ["value"]},
        },
    }
    client = DuneLatestResultClient(
        "test-key",
        transport=lambda url, headers, timeout: (200, {}, payload),
        clock=fixed_clock,
    )

    with pytest.raises(StudioIngestionError) as exc_info:
        client.fetch_latest_result(123, timeout_seconds=1)

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE
    assert "total row count" in str(exc_info.value)


def test_dune_latest_result_client_records_observed_failed_execution_metadata():
    payload = {
        "query_id": 123,
        "execution_id": "failed-exec-1",
        "state": "QUERY_STATE_FAILED",
        "execution_started_at": "2026-07-31T11:58:00Z",
        "execution_ended_at": "2026-07-31T11:59:00Z",
        "error": "scheduled query failed on Dune",
    }
    client = DuneLatestResultClient(
        "test-key",
        transport=lambda url, headers, timeout: (200, {}, payload),
        clock=fixed_clock,
    )

    with pytest.raises(StudioIngestionError) as exc_info:
        client.fetch_latest_result(123, timeout_seconds=1)

    failure = exc_info.value.as_dict()
    assert failure["category"] == "query_execution_failed"
    assert failure["provider_execution_id"] == "failed-exec-1"
    assert failure["provider_execution_finished_at"] == (
        "2026-07-31T11:59:00Z"
    )


def test_dune_latest_result_client_exposes_no_execution_operation():
    client = DuneLatestResultClient("test-key", transport=lambda *args: None)

    assert callable(client.fetch_latest_result)
    assert not hasattr(client, "execute_query")
    assert not hasattr(client, "run_query")


def test_default_dune_transport_refuses_http_redirects_before_header_forwarding():
    handler = studio_ingestion._NoRedirectHandler()

    assert handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere") is None


def test_default_dune_transport_uses_get_without_a_request_body(monkeypatch):
    captured = {}

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b'{"state":"QUERY_STATE_COMPLETED"}'

    class Opener:
        def open(self, request, *, timeout):
            captured.update(
                {
                    "method": request.get_method(),
                    "body": request.data,
                    "url": request.full_url,
                    "timeout": timeout,
                }
            )
            return Response()

    monkeypatch.setattr(studio_ingestion, "_NO_REDIRECT_OPENER", Opener())

    status, _, payload = studio_ingestion._urllib_transport(
        "https://api.dune.com/api/v1/query/123/results",
        {"X-Dune-API-Key": "test-key"},
        4.5,
    )

    assert status == 200
    assert payload == {"state": "QUERY_STATE_COMPLETED"}
    assert captured == {
        "method": "GET",
        "body": None,
        "url": "https://api.dune.com/api/v1/query/123/results",
        "timeout": 4.5,
    }


def test_dune_latest_result_client_requires_https_and_rejects_malformed_pagination_ports():
    with pytest.raises(ValueError, match="absolute HTTPS URL"):
        DuneLatestResultClient("test-key", base_url="http://api.dune.com/api/v1")

    def transport(url, headers, timeout):
        del url, headers, timeout
        return 200, {}, {
            "query_id": 123,
            "execution_id": "exec-1",
            "state": "QUERY_STATE_COMPLETED",
            "execution_started_at": "2026-07-31T11:58:00Z",
            "execution_ended_at": "2026-07-31T11:59:00Z",
            "next_uri": "https://api.dune.com:not-a-port/api/v1/query/123/results",
            "result": {
                "rows": [{"value": 1}],
                "metadata": {
                    "column_names": ["value"],
                    "total_row_count": 1,
                },
            },
        }

    with pytest.raises(StudioIngestionError) as exc_info:
        DuneLatestResultClient("test-key", transport=transport, clock=fixed_clock).fetch_latest_result(
            123,
            timeout_seconds=1,
        )

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE
    assert "malformed pagination URL" in str(exc_info.value)


def test_dune_api_client_detects_truncated_and_mixed_pagination():
    def truncated_transport(url, headers, timeout):
        del url, headers, timeout
        return 200, {}, {
            "query_id": 123,
            "execution_id": "exec-1",
            "state": "QUERY_STATE_COMPLETED",
            "execution_started_at": "2026-07-31T11:58:00Z",
            "execution_ended_at": "2026-07-31T11:59:00Z",
            "result": {
                "rows": [{"value": 1}],
                "metadata": {
                    "column_names": ["value"],
                    "total_row_count": 2,
                },
            },
        }

    with pytest.raises(StudioIngestionError) as truncated:
        DuneLatestResultClient(
            "test-key",
            transport=truncated_transport,
            clock=fixed_clock,
        ).fetch_latest_result(123, timeout_seconds=1)
    assert truncated.value.category is FailureCategory.PARTIAL_RESULT

    calls = 0

    def mixed_transport(url, headers, timeout):
        nonlocal calls
        del url, headers, timeout
        calls += 1
        return 200, {}, {
            "query_id": 123,
            "execution_id": f"exec-{calls}",
            "state": "QUERY_STATE_COMPLETED",
            "execution_started_at": "2026-07-31T11:58:00Z",
            "execution_ended_at": "2026-07-31T11:59:00Z",
            "result": {
                "rows": [{"value": calls}],
                "metadata": {
                    "column_names": ["value"],
                    "total_row_count": 2,
                    **({"next_offset": 1} if calls == 1 else {}),
                },
            },
        }

    with pytest.raises(StudioIngestionError) as mixed:
        DuneLatestResultClient(
            "test-key",
            transport=mixed_transport,
            clock=fixed_clock,
        ).fetch_latest_result(123, timeout_seconds=1)
    assert mixed.value.category is FailureCategory.PARTIAL_RESULT
    assert calls == 2


@pytest.mark.parametrize(
    ("payload", "category"),
    [
        (
            {
                "query_id": 123,
                "state": "QUERY_STATE_FAILED",
                "error": "controlled execution failure",
            },
            FailureCategory.QUERY_EXECUTION_FAILED,
        ),
        (
            {"result": {"rows": [], "metadata": {"column_names": ["value"]}}},
            FailureCategory.MALFORMED_RESPONSE,
        ),
    ],
)
def test_dune_api_client_classifies_2xx_execution_states(payload, category):
    client = DuneLatestResultClient(
        "test-key",
        transport=lambda url, headers, timeout: (200, {}, payload),
        clock=fixed_clock,
    )

    with pytest.raises(StudioIngestionError) as exc_info:
        client.fetch_latest_result(123, timeout_seconds=1)

    assert exc_info.value.category is category


def test_dune_api_client_wraps_transport_decode_failures():
    def transport(url, headers, timeout):
        del url, headers, timeout
        raise ValueError("invalid JSON")

    with pytest.raises(StudioIngestionError) as exc_info:
        DuneLatestResultClient("test-key", transport=transport).fetch_latest_result(
            123,
            timeout_seconds=1,
        )

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE


@pytest.mark.parametrize(
    ("retry_after", "max_delay", "expected_delay"),
    [
        ("999999", 2.0, 2.0),
        ("Fri, 31 Jul 2026 12:00:05 GMT", 10.0, 5.0),
        ("not-a-delay", 10.0, 0.25),
    ],
)
def test_retry_after_is_parsed_and_bounded(
    retry_after,
    max_delay,
    expected_delay,
):
    calls = 0

    def transport(url, headers, timeout):
        nonlocal calls
        del url, headers, timeout
        calls += 1
        if calls == 1:
            return 429, {"Retry-After": retry_after}, {"error": "wait"}
        return 200, {}, {
            "query_id": 123,
            "execution_id": "exec-1",
            "state": "QUERY_STATE_COMPLETED",
            "execution_started_at": "2026-07-31T11:58:00Z",
            "execution_ended_at": "2026-07-31T11:59:00Z",
            "result": {
                "rows": [{"value": 1}],
                "metadata": {
                    "column_names": ["value"],
                    "total_row_count": 1,
                },
            },
        }

    delays = []
    result, attempts = fetch_latest_result_with_retry(
        DuneLatestResultClient("test-key", transport=transport, clock=fixed_clock),
        minimal_request(),
        retry_policy=RetryPolicy(
            max_attempts=2,
            base_delay_seconds=0.25,
            max_delay_seconds=max_delay,
        ),
        timeout_seconds=1,
        sleeper=delays.append,
    )

    assert result.rows == [{"value": 1}]
    assert attempts == 2
    assert delays == [expected_delay]


@pytest.mark.parametrize(
    ("status", "category", "retryable"),
    [
        (302, FailureCategory.LATEST_RESULT_REQUEST_FAILED, False),
        (400, FailureCategory.LATEST_RESULT_REQUEST_FAILED, False),
        (401, FailureCategory.AUTHENTICATION, False),
        (404, FailureCategory.QUERY_UNAVAILABLE, False),
        (429, FailureCategory.RATE_LIMITED, True),
        (503, FailureCategory.NETWORK_ERROR, True),
    ],
)
def test_dune_latest_result_client_classifies_http_failures(
    status,
    category,
    retryable,
):
    def transport(url, headers, timeout):
        del url, headers, timeout
        return status, {"Retry-After": "2"}, {"error": "controlled"}

    client = DuneLatestResultClient("test-key", transport=transport)
    with pytest.raises(StudioIngestionError) as exc_info:
        client.fetch_latest_result(123, timeout_seconds=1)

    assert exc_info.value.category is category
    assert exc_info.value.retryable is retryable
    assert "test-key" not in str(exc_info.value)


def test_successful_refresh_promotes_complete_valid_snapshot_once_per_query(tmp_path):
    requests, selected, client = generated_registry_fixture()

    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )

    assert summary.status == "success"
    assert summary.fetched_query_ids == tuple(sorted(selected))
    assert client.calls == {query_id: 1 for query_id in selected}
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == summary.snapshot_id
    assert state["previous_snapshot_id"] is None
    manifest = validate_current_snapshot(tmp_path)
    assert manifest["snapshot_id"] == summary.snapshot_id
    assert manifest["dashboard_count"] == 1
    assert manifest["metric_count"] == 24
    assert manifest["unique_query_count"] == 9
    assert [entry["artifact_id"] for entry in manifest["artifacts"]] == [
        "kyberswap_depositor_intelligence"
    ]
    assert manifest["validation_status"] == "valid"
    assert manifest["mode"] == "fixture"
    assert manifest["dashboard_refreshed_at"] == "2026-07-31T12:00:00Z"
    refreshed_at = datetime.fromisoformat(
        manifest["dashboard_refreshed_at"].replace("Z", "+00:00")
    )
    assert refreshed_at.tzinfo is not None
    assert refreshed_at.utcoffset() == timedelta(0)
    assert len(manifest["contract_checksum"]) == 64


def test_live_dashboard_timestamp_is_sampled_at_validated_acceptance(tmp_path):
    _, _, client = generated_registry_fixture()
    acceptance_time = NOW + timedelta(minutes=7)
    clock_values = iter((NOW, acceptance_time))

    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="live",
        force=True,
        clock=lambda: next(clock_values),
        sleeper=lambda _: None,
    )

    manifest = validate_current_snapshot(tmp_path)
    assert summary.status == "success"
    assert manifest["generated_at"] == "2026-07-31T12:00:00Z"
    assert manifest["dashboard_refreshed_at"] == "2026-07-31T12:07:00Z"


def test_shared_transformed_queries_are_fetched_once_and_keep_raw_results(
    tmp_path,
    monkeypatch,
):
    requests, selected, client = generated_registry_fixture()
    transform_calls = 0
    summary_transform_calls = 0
    growth_transform_calls = {
        8191379: 0,
        8191704: 0,
        8193003: 0,
        8193040: 0,
        8202133: 0,
        8204345: 0,
        8204373: 0,
    }
    intelligence_builder_calls = 0
    real_transform = studio_ingestion.enrich_kyberswap_attributed_holdings
    real_summary_transform = studio_ingestion.prepare_kyberswap_campaign_summary
    real_intelligence_builder = (
        studio_ingestion.build_kyberswap_depositor_intelligence
    )

    def tracked_transform(*args, **kwargs):
        nonlocal transform_calls
        transform_calls += 1
        return real_transform(*args, **kwargs)

    def tracked_summary_transform(*args, **kwargs):
        nonlocal summary_transform_calls
        summary_transform_calls += 1
        return real_summary_transform(*args, **kwargs)

    def tracked_growth_transform(query_id, real_transformer):
        def tracked(*args, **kwargs):
            growth_transform_calls[query_id] += 1
            return real_transformer(*args, **kwargs)

        return tracked

    def tracked_intelligence_builder(*args, **kwargs):
        nonlocal intelligence_builder_calls
        intelligence_builder_calls += 1
        return real_intelligence_builder(*args, **kwargs)

    monkeypatch.setattr(
        studio_ingestion,
        "enrich_kyberswap_attributed_holdings",
        tracked_transform,
    )
    monkeypatch.setattr(
        studio_ingestion,
        "prepare_kyberswap_campaign_summary",
        tracked_summary_transform,
    )
    for query_id, function_name in {
        8191379: "prepare_kyberswap_growth_deposits",
        8191704: "prepare_kyberswap_growth_attributed_tvl",
        8193003: "prepare_kyberswap_growth_breakdown",
        8193040: "prepare_kyberswap_growth_activity",
        8202133: "prepare_kyberswap_post_referral_activity",
    }.items():
        monkeypatch.setattr(
            studio_ingestion,
            function_name,
            tracked_growth_transform(
                query_id,
                getattr(studio_ingestion, function_name),
            ),
        )
    for query_id, function_name in {
        8204345: "prepare_kyberswap_referral_deposits",
        8204373: "prepare_kyberswap_etherfi_activity",
    }.items():
        monkeypatch.setattr(
            studio_ingestion,
            function_name,
            tracked_growth_transform(
                query_id,
                getattr(studio_ingestion, function_name),
            ),
        )
    monkeypatch.setattr(
        studio_ingestion,
        "build_kyberswap_depositor_intelligence",
        tracked_intelligence_builder,
    )

    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )

    assert selected == {
        8199058,
        8180894,
        8191379,
        8191704,
        8193003,
        8193040,
        8202133,
        8204345,
        8204373,
    }
    assert requests[8199058].metric_ids == (
        "kyber_attributed_tvl_by_location",
        "kyber_capital_journey",
        "kyber_product_adoption",
        "kyber_top_referred_depositors",
        "kyber_referral_deposit_concentration",
        "kyber_top_depositors",
        "kyber_wallet_investigation",
    )
    assert client.calls[8199058] == 1
    assert client.calls[8180894] == 1
    assert all(client.calls[query_id] == 1 for query_id in growth_transform_calls)
    assert transform_calls == 1
    assert summary_transform_calls == 1
    assert growth_transform_calls == {
        8191379: 1,
        8191704: 1,
        8193003: 1,
        8193040: 1,
        8202133: 1,
        8204345: 1,
        8204373: 1,
    }
    assert intelligence_builder_calls == 1

    snapshot_dir = tmp_path / "snapshots" / summary.snapshot_id
    manifest = validate_current_snapshot(tmp_path)
    entry = next(
        value for value in manifest["queries"] if value["query_id"] == 8199058
    )
    assert entry["metrics_using_query"] == [
        "kyber_attributed_tvl_by_location",
        "kyber_capital_journey",
        "kyber_product_adoption",
        "kyber_top_referred_depositors",
        "kyber_referral_deposit_concentration",
        "kyber_top_depositors",
        "kyber_wallet_investigation",
    ]
    assert entry["raw_data_file"] == "raw_query_8199058.json"
    assert entry["source_execution_id"] == "fixture-8199058-latest"
    assert entry["source_last_updated"] == "2026-07-31T12:00:00Z"

    raw = json.loads((snapshot_dir / entry["raw_data_file"]).read_text())
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "studio"
            / "fixtures"
            / "query_8199058.json"
        ).read_text()
    )
    assert raw["columns"] == fixture["columns"]
    assert raw["rows"] == fixture["rows"]
    assert "current_token_category" in raw["columns"]
    assert "base_asset_price" not in raw["columns"]

    enriched = json.loads((snapshot_dir / "query_8199058.json").read_text())
    assert "attributed_balance" in enriched["columns"]
    assert "attributed_balance_usd" not in enriched["columns"]
    assert enriched["rows"] != raw["rows"]

    summary_entry = next(
        value for value in manifest["queries"] if value["query_id"] == 8180894
    )
    assert summary_entry["metrics_using_query"] == [
        "kyber_total_referral_deposits",
        "kyber_attributed_tvl",
        "kyber_new_depositor_deposits",
        "kyber_new_depositor_deposit_rate",
        "kyber_total_depositors",
        "kyber_new_depositors",
        "kyber_retention_rate",
        "kyber_revenue_generated",
    ]
    assert summary_entry["raw_data_file"] == "raw_query_8180894.json"
    assert summary_entry["source_execution_id"] == "fixture-8180894-latest"
    assert summary_entry["source_last_updated"] == "2026-07-31T12:00:00Z"
    summary_raw = json.loads(
        (snapshot_dir / summary_entry["raw_data_file"]).read_text()
    )
    summary_fixture = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "studio"
            / "fixtures"
            / "query_8180894.json"
        ).read_text()
    )
    assert summary_raw["columns"] == summary_fixture["columns"]
    assert summary_raw["rows"] == summary_fixture["rows"]
    prepared_summary = json.loads(
        (snapshot_dir / "query_8180894.json").read_text()
    )
    assert prepared_summary["rows"][0]["source_query_id"] == 8180894
    assert prepared_summary["rows"][0]["source_execution_id"] == (
        "fixture-8180894-latest"
    )
    assert prepared_summary["rows"][0]["source_last_updated"] == (
        "2026-07-31T12:00:00Z"
    )

    growth_metric_ids = {
        8191379: ["kyber_referral_deposits_growth"],
        8191704: ["kyber_attributed_tvl_over_time"],
        8193003: [
            "kyber_referral_deposits_breakdown",
            "kyber_total_referral_deposits_breakdown",
        ],
        8193040: [
            "kyber_deposit_depositor_count_by_product",
            "kyber_deposit_depositor_count_by_depositor_type",
        ],
        8202133: ["kyber_post_referral_activity"],
        8204345: ["kyber_recent_referral_deposits"],
        8204373: ["kyber_recent_etherfi_activity"],
    }
    for query_id, metric_ids in growth_metric_ids.items():
        growth_entry = next(
            value for value in manifest["queries"] if value["query_id"] == query_id
        )
        assert growth_entry["metrics_using_query"] == metric_ids
        assert growth_entry["raw_data_file"] == f"raw_query_{query_id}.json"
        assert growth_entry["source_execution_id"] == f"fixture-{query_id}-latest"
        growth_raw = json.loads(
            (snapshot_dir / growth_entry["raw_data_file"]).read_text()
        )
        growth_fixture = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "studio"
                / "fixtures"
                / f"query_{query_id}.json"
            ).read_text()
        )
        assert growth_entry["source_last_updated"] == growth_fixture[
            "execution_finished_at"
        ]
        assert growth_raw["columns"] == growth_fixture["columns"]
        assert growth_raw["rows"] == growth_fixture["rows"]
        prepared_growth = json.loads(
            (snapshot_dir / f"query_{query_id}.json").read_text()
        )
        assert prepared_growth["rows"] != growth_raw["rows"]
        assert all(
            row["source_query_id"] == query_id
            for row in prepared_growth["rows"]
        )

    published_dir = tmp_path / "published"
    published = publish_studio_generated_data(tmp_path, published_dir)
    assert "raw_query_8199058.json" not in {path.name for path in published}
    assert "raw_query_8180894.json" not in {path.name for path in published}
    for query_id in growth_metric_ids:
        assert f"raw_query_{query_id}.json" not in {
            path.name for path in published
        }
    assert not (published_dir / "raw_query_8199058.json").exists()
    assert not (published_dir / "raw_query_8180894.json").exists()
    for query_id in growth_metric_ids:
        assert not (published_dir / f"raw_query_{query_id}.json").exists()
    assert (published_dir / "kyberswap_depositor_intelligence.json").is_file()


def test_derived_wallet_artifact_tampering_is_rejected(tmp_path):
    requests, _, client = generated_registry_fixture()
    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    snapshot_dir = tmp_path / "snapshots" / summary.snapshot_id
    artifact_path = snapshot_dir / "kyberswap_depositor_intelligence.json"
    payload = json.loads(artifact_path.read_text())
    payload["wallets"][0]["attributed_tvl_usd"] = "1"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="derived artifact"):
        validate_snapshot_directory(snapshot_dir, query_requests=requests)


def test_derived_wallet_failure_preserves_active_snapshot(tmp_path, monkeypatch):
    _, initial_client = registry_fixture()
    first = refresh_studio_data(
        initial_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    _, failing_client = registry_fixture()

    def fail_builder(*args, **kwargs):
        del args, kwargs
        raise studio_ingestion.KyberSwapDepositorIntelligenceError(
            "controlled cross-source reconciliation failure"
        )

    monkeypatch.setattr(
        studio_ingestion,
        "build_kyberswap_depositor_intelligence",
        fail_builder,
    )
    with pytest.raises(StudioIngestionError, match="active snapshot preserved") as exc:
        refresh_studio_data(
            failing_client,
            output_root=tmp_path,
            mode="fixture",
            clock=lambda: NOW + timedelta(hours=1),
            sleeper=lambda _: None,
        )

    assert exc.value.category is FailureCategory.TRANSFORMATION_FAILURE
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == first.snapshot_id
    assert state["latest_failure"]["failed_query_ids"] == []
    attempt = json.loads(
        sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text()
    )
    assert attempt["failures"][0]["query_id"] is None
    assert attempt["failures"][0]["category"] == "transformation_failure"


def test_stale_latest_results_are_promoted_without_any_execution_operation(tmp_path):
    dashboards, _, requests = load_query_requests()
    selected = generated_query_ids(dashboards, requests)

    class StaleLatestResultFixture(FixtureDuneClient):
        def fetch_latest_result(self, query_id, *, timeout_seconds):
            result = super().fetch_latest_result(
                query_id,
                timeout_seconds=timeout_seconds,
            )
            result.execution_started_at = "2026-07-28T11:58:00Z"
            result.execution_finished_at = "2026-07-28T11:59:00Z"
            result.data_updated_at = "2026-07-28T11:59:00Z"
            result.execution_id = f"scheduled-stale-{query_id}"
            return result

    client = StaleLatestResultFixture(requests, dashboards, clock=fixed_clock)
    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )

    manifest = json.loads(
        (tmp_path / "snapshots" / summary.snapshot_id / "manifest.json").read_text()
    )
    assert summary.status == "success"
    assert client.calls == {query_id: 1 for query_id in selected}
    assert {
        entry["freshness_status"] for entry in manifest["queries"]
    } == {"stale"}
    assert all(
        entry["execution_id"].startswith("scheduled-stale-")
        for entry in manifest["queries"]
    )
    assert not hasattr(client, "execute_query")


def test_named_previous_valid_snapshot_fixture_seeds_a_valid_snapshot(tmp_path):
    _, selected, client = generated_registry_fixture("previous_valid_snapshot")

    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )

    assert summary.status == "success"
    assert client.calls == {query_id: 1 for query_id in selected}
    assert validate_current_snapshot(tmp_path)["snapshot_id"] == summary.snapshot_id


def test_refresh_never_reuses_an_active_snapshot_from_another_mode(tmp_path):
    _, fixture_client = registry_fixture()
    fixture_summary = refresh_studio_data(
        fixture_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    _, selected, live_shaped_client = generated_registry_fixture()

    live_summary = refresh_studio_data(
        live_shaped_client,
        output_root=tmp_path,
        mode="live",
        force=True,
        clock=lambda: NOW + timedelta(hours=1),
        sleeper=lambda _: None,
    )

    assert live_shaped_client.calls == {query_id: 1 for query_id in selected}
    assert live_summary.reused_query_ids == ()
    manifest = validate_current_snapshot(tmp_path)
    assert manifest["mode"] == "live"
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == live_summary.snapshot_id
    assert state["previous_snapshot_id"] == fixture_summary.snapshot_id
    assert state["current_snapshot_id"] != fixture_summary.snapshot_id


def test_unexpected_client_exceptions_become_sanitized_attempt_diagnostics(tmp_path):
    class UnexpectedClient:
        def fetch_latest_result(self, query_id, *, timeout_seconds):
            del query_id, timeout_seconds
            raise RuntimeError("private provider detail must not be published")

    with pytest.raises(StudioIngestionError) as exc_info:
        refresh_studio_data(
            UnexpectedClient(),
            output_root=tmp_path,
            mode="fixture",
            clock=fixed_clock,
            sleeper=lambda _: None,
        )

    assert exc_info.value.category is FailureCategory.MALFORMED_RESPONSE
    attempt = json.loads(
        next((tmp_path / "attempts").glob("*/attempt.json")).read_text()
    )
    serialized = json.dumps(attempt)
    assert attempt["status"] == "failed"
    assert "unexpected RuntimeError" in serialized
    assert "private provider detail" not in serialized


def test_refresh_lock_rejects_overlapping_writer(tmp_path):
    _, client = registry_fixture()
    store = SnapshotStore(tmp_path)

    with store.refresh_lock():
        with pytest.raises(StudioIngestionError, match="already running") as exc_info:
            refresh_studio_data(
                client,
                output_root=tmp_path,
                mode="fixture",
                clock=fixed_clock,
                sleeper=lambda _: None,
            )

    assert exc_info.value.category is FailureCategory.WRITE_FAILURE
    assert not (tmp_path / "state.json").exists()


def test_full_refresh_replaces_an_incompatible_active_contract(tmp_path):
    _, first_client = registry_fixture()
    first = refresh_studio_data(
        first_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    old_manifest_path = (
        tmp_path / "snapshots" / first.snapshot_id / "manifest.json"
    )
    old_manifest = json.loads(old_manifest_path.read_text())
    old_manifest["contract_checksum"] = "0" * 64
    old_manifest.pop("manifest_checksum")
    old_manifest["manifest_checksum"] = sha256_json(old_manifest)
    old_manifest_path.write_text(
        json.dumps(old_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    dashboards, _, requests = load_query_requests()
    later = lambda: NOW + timedelta(hours=1)
    second = refresh_studio_data(
        FixtureDuneClient(requests, dashboards, clock=later),
        output_root=tmp_path,
        mode="fixture",
        clock=later,
        sleeper=lambda _: None,
    )

    assert second.status == "success"
    assert second.snapshot_id != first.snapshot_id
    assert validate_current_snapshot(tmp_path)["snapshot_id"] == second.snapshot_id


def test_filtered_refresh_rejects_an_incompatible_active_contract(tmp_path):
    _, first_client = registry_fixture()
    first = refresh_studio_data(
        first_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    manifest_path = tmp_path / "snapshots" / first.snapshot_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["contract_checksum"] = "0" * 64
    manifest.pop("manifest_checksum")
    manifest["manifest_checksum"] = sha256_json(manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    dashboards, _, requests = load_query_requests()

    with pytest.raises(StudioIngestionError, match="filtered Studio refresh"):
        refresh_studio_data(
            FixtureDuneClient(requests, dashboards, clock=fixed_clock),
            output_root=tmp_path,
            mode="fixture",
            query_ids={8204345},
            clock=fixed_clock,
            sleeper=lambda _: None,
        )


def test_unchanged_refresh_records_check_without_rewriting_snapshot_files(tmp_path):
    requests, first_client = registry_fixture()
    first = refresh_studio_data(
        first_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    snapshot_dir = tmp_path / "snapshots" / first.snapshot_id
    query_path = snapshot_dir / requests[8204345].result_file
    before = sha256_bytes(query_path.read_bytes())
    later = lambda: NOW + timedelta(hours=1)
    dashboards, _, later_requests = load_query_requests()
    second_client = FixtureDuneClient(later_requests, dashboards, clock=later)

    second = refresh_studio_data(
        second_client,
        output_root=tmp_path,
        mode="fixture",
        clock=later,
        sleeper=lambda _: None,
    )

    assert second.status == "unchanged"
    assert second.snapshot_id == first.snapshot_id
    assert sha256_bytes(query_path.read_bytes()) == before
    assert len([path for path in (tmp_path / "snapshots").iterdir() if not path.name.startswith(".")]) == 1
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["last_checked_at"] == "2026-07-31T13:00:00Z"
    assert state["latest_attempt_status"] == "unchanged"
    assert validate_current_snapshot(tmp_path)["dashboard_refreshed_at"] == (
        "2026-07-31T12:00:00Z"
    )
    assert len(list((tmp_path / "attempts").glob("*/attempt.json"))) == 2


def test_new_execution_with_identical_content_promotes_latest_result_metadata(
    tmp_path,
):
    _, first_client = registry_fixture()
    first = refresh_studio_data(
        first_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    dashboards, _, requests = load_query_requests()
    later = lambda: NOW + timedelta(hours=1)

    class NewExecutionFixture(FixtureDuneClient):
        def fetch_latest_result(self, query_id, *, timeout_seconds):
            result = super().fetch_latest_result(query_id, timeout_seconds=timeout_seconds)
            result.execution_id = f"new-execution-{query_id}"
            result.execution_started_at = "2026-07-31T12:55:00Z"
            result.execution_finished_at = "2026-07-31T12:59:00Z"
            result.data_updated_at = "2026-07-31T12:59:00Z"
            result.fetched_at = "2026-07-31T13:00:00Z"
            return result

    second = refresh_studio_data(
        NewExecutionFixture(requests, dashboards, clock=later),
        output_root=tmp_path,
        mode="fixture",
        clock=later,
        sleeper=lambda _: None,
    )

    assert second.status == "success"
    assert second.unchanged is False
    assert second.snapshot_id != first.snapshot_id
    assert len(list((tmp_path / "snapshots").iterdir())) == 2
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["last_successful_fetch_at"] == "2026-07-31T13:00:00Z"
    manifest = json.loads(
        (tmp_path / "snapshots" / second.snapshot_id / "manifest.json").read_text()
    )
    # All transformed sources include the source execution ID by design, so
    # their artifacts change even when their business values do not.
    assert manifest["changed_query_ids"] == [
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
    assert all(
        entry["execution_id"].startswith("new-execution-")
        for entry in manifest["queries"]
    )
    assert {
        entry["execution_finished_at"] for entry in manifest["queries"]
    } == {"2026-07-31T12:59:00Z"}
    assert {entry["freshness_status"] for entry in manifest["queries"]} == {
        "current"
    }


def test_failed_refresh_preserves_active_snapshot_and_records_affected_metrics(tmp_path):
    requests, success_client = registry_fixture()
    first = refresh_studio_data(
        success_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    first_dashboard_refreshed_at = validate_current_snapshot(tmp_path)[
        "dashboard_refreshed_at"
    ]
    current_path = tmp_path / "snapshots" / first.snapshot_id / requests[8204345].result_file
    before = current_path.read_bytes()
    _, failed_client = registry_fixture("query_execution_failed")

    with pytest.raises(
        StudioIngestionError,
        match="active snapshot preserved",
    ) as exc_info:
        refresh_studio_data(
            failed_client,
            output_root=tmp_path,
            mode="fixture",
            clock=lambda: NOW + timedelta(hours=1),
            sleeper=lambda _: None,
        )

    assert exc_info.value.provider_execution_id == "fixture-failed-8204345"
    assert exc_info.value.provider_execution_finished_at == (
        "2026-07-31T11:57:00Z"
    )

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == first.snapshot_id
    assert state["using_previous"] is True
    assert state["latest_attempt_status"] == "failed"
    assert state["latest_failure"]["failed_query_ids"] == [8204345]
    assert current_path.read_bytes() == before
    assert validate_current_snapshot(tmp_path)["dashboard_refreshed_at"] == (
        first_dashboard_refreshed_at
    )
    attempt = json.loads(sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text())
    assert attempt["active_snapshot_preserved"] is True
    assert attempt["failures"][0]["affected_metrics"] == [
        "kyber_recent_referral_deposits"
    ]
    assert attempt["failures"][0]["provider_execution_id"] == (
        "fixture-failed-8204345"
    )
    assert attempt["failures"][0]["provider_execution_finished_at"] == (
        "2026-07-31T11:57:00Z"
    )


def test_attribution_failure_retains_previous_valid_snapshot_and_raw_result(tmp_path):
    dashboards, _, requests = load_query_requests()
    first = refresh_studio_data(
        FixtureDuneClient(requests, dashboards, clock=fixed_clock),
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    snapshot_dir = tmp_path / "snapshots" / first.snapshot_id
    raw_path = snapshot_dir / "raw_query_8199058.json"
    raw_before = raw_path.read_bytes()

    class InvalidAttributionFixture(FixtureDuneClient):
        def fetch_latest_result(self, query_id, *, timeout_seconds):
            result = super().fetch_latest_result(
                query_id,
                timeout_seconds=timeout_seconds,
            )
            if query_id == 8199058:
                result.rows[0]["referral_balance"] = "not-a-decimal"
                result.execution_id = "fixture-invalid-attribution"
            return result

    with pytest.raises(StudioIngestionError, match="active snapshot preserved") as exc:
        refresh_studio_data(
            InvalidAttributionFixture(requests, dashboards, clock=fixed_clock),
            output_root=tmp_path,
            mode="fixture",
            clock=lambda: NOW + timedelta(hours=1),
            sleeper=lambda _: None,
        )

    assert exc.value.category is FailureCategory.TRANSFORMATION_FAILURE
    assert exc.value.affected_metrics == [
        "kyber_attributed_tvl_by_location",
        "kyber_capital_journey",
        "kyber_product_adoption",
        "kyber_top_referred_depositors",
        "kyber_referral_deposit_concentration",
        "kyber_top_depositors",
        "kyber_wallet_investigation",
    ]
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == first.snapshot_id
    assert state["using_previous"] is True
    assert raw_path.read_bytes() == raw_before
    latest_attempt = json.loads(
        sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text()
    )
    failure = latest_attempt["failures"][0]
    assert failure["query_id"] == 8199058
    assert failure["category"] == "transformation_failure"
    assert failure["provider_execution_id"] == "fixture-invalid-attribution"
    failed_raw = json.loads(
        (
            tmp_path
            / "attempts"
            / latest_attempt["attempt_id"]
            / "raw_query_8199058.json"
        ).read_text()
    )
    assert failed_raw["execution_id"] == "fixture-invalid-attribution"
    assert failed_raw["rows"][0]["referral_balance"] == "not-a-decimal"


def test_campaign_summary_failure_retains_previous_snapshot_and_raw_result(tmp_path):
    dashboards, _, requests = load_query_requests()
    first = refresh_studio_data(
        FixtureDuneClient(requests, dashboards, clock=fixed_clock),
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    snapshot_dir = tmp_path / "snapshots" / first.snapshot_id
    raw_path = snapshot_dir / "raw_query_8180894.json"
    raw_before = raw_path.read_bytes()

    class InvalidCampaignSummaryFixture(FixtureDuneClient):
        def fetch_latest_result(self, query_id, *, timeout_seconds):
            result = super().fetch_latest_result(
                query_id,
                timeout_seconds=timeout_seconds,
            )
            if query_id == 8180894:
                duplicate = dict(result.rows[0])
                duplicate["rank_"] = 2
                result.rows.append(duplicate)
                result.total_row_count = len(result.rows)
                result.execution_id = "fixture-invalid-campaign-summary"
            return result

    with pytest.raises(StudioIngestionError, match="active snapshot preserved") as exc:
        refresh_studio_data(
            InvalidCampaignSummaryFixture(
                requests,
                dashboards,
                clock=fixed_clock,
            ),
            output_root=tmp_path,
            mode="fixture",
            clock=lambda: NOW + timedelta(hours=1),
            sleeper=lambda _: None,
        )

    assert exc.value.category is FailureCategory.TRANSFORMATION_FAILURE
    assert exc.value.affected_metrics == [
        "kyber_total_referral_deposits",
        "kyber_attributed_tvl",
        "kyber_new_depositor_deposits",
        "kyber_new_depositor_deposit_rate",
        "kyber_total_depositors",
        "kyber_new_depositors",
        "kyber_retention_rate",
        "kyber_revenue_generated",
    ]
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == first.snapshot_id
    assert state["using_previous"] is True
    assert raw_path.read_bytes() == raw_before
    latest_attempt = json.loads(
        sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text()
    )
    failure = latest_attempt["failures"][0]
    assert failure["query_id"] == 8180894
    assert failure["category"] == "transformation_failure"
    assert failure["provider_execution_id"] == "fixture-invalid-campaign-summary"
    failed_raw = json.loads(
        (
            tmp_path
            / "attempts"
            / latest_attempt["attempt_id"]
            / "raw_query_8180894.json"
        ).read_text()
    )
    assert failed_raw["execution_id"] == "fixture-invalid-campaign-summary"
    assert [row["key_"] for row in failed_raw["rows"]] == [
        "all_time_data",
        "all_time_data",
    ]


def test_failed_replacement_does_not_claim_corrupt_snapshot_is_usable(tmp_path):
    requests, success_client = registry_fixture()
    first = refresh_studio_data(
        success_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    corrupt_path = (
        tmp_path
        / "snapshots"
        / first.snapshot_id
        / requests[8204345].result_file
    )
    corrupt_path.write_text("{}", encoding="utf-8")
    _, failed_client = registry_fixture("query_execution_failed")

    with pytest.raises(StudioIngestionError, match="no usable active snapshot"):
        refresh_studio_data(
            failed_client,
            output_root=tmp_path,
            mode="fixture",
            clock=lambda: NOW + timedelta(hours=1),
            sleeper=lambda _: None,
        )

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == first.snapshot_id
    assert state["using_previous"] is False
    attempt = json.loads(
        sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text()
    )
    assert attempt["active_snapshot_preserved"] is False


def test_explicit_partial_policy_reuses_previous_query_and_marks_state(tmp_path):
    _, success_client = registry_fixture()
    first = refresh_studio_data(
        success_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    _, partial_client = registry_fixture("query_execution_failed")

    summary = refresh_studio_data(
        partial_client,
        output_root=tmp_path,
        mode="fixture",
        allow_partial=True,
        clock=lambda: NOW + timedelta(hours=1),
        sleeper=lambda _: None,
    )

    assert summary.status == "partial"
    assert summary.snapshot_id == first.snapshot_id
    assert summary.reused_query_ids == (8204345,)
    assert summary.failed_query_ids == (8204345,)
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["latest_attempt_status"] == "partial"
    assert state["using_previous"] is True
    latest_attempt = json.loads(
        sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text()
    )
    assert latest_attempt["failures"][0]["query_id"] == 8204345


def test_changed_partial_snapshot_preserves_last_complete_success_timestamp(tmp_path):
    _, initial_client = registry_fixture()
    first = refresh_studio_data(
        initial_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    first_dashboard_refreshed_at = validate_current_snapshot(tmp_path)[
        "dashboard_refreshed_at"
    ]
    _, base_client = registry_fixture()

    class ChangedPartialClient:
        def fetch_latest_result(self, query_id, *, timeout_seconds):
            if query_id == 8204345:
                raise StudioIngestionError(
                    FailureCategory.QUERY_EXECUTION_FAILED,
                    "controlled partial query failure",
                    query_id=query_id,
                )
            result = base_client.fetch_latest_result(query_id, timeout_seconds=timeout_seconds)
            if query_id == 8204373:
                result.rows[0]["amount_usd"] = 999999999
            return result

    summary = refresh_studio_data(
        ChangedPartialClient(),
        output_root=tmp_path,
        mode="fixture",
        allow_partial=True,
        clock=lambda: NOW + timedelta(hours=1),
        sleeper=lambda _: None,
    )

    assert summary.status == "partial"
    assert summary.snapshot_id != first.snapshot_id
    assert summary.reused_query_ids == (8204345,)
    manifest = validate_current_snapshot(tmp_path)
    assert manifest["changed_query_ids"] == [8204373]
    assert manifest["last_checked_at"] == "2026-07-31T13:00:00Z"
    assert manifest["last_successful_fetch_at"] == "2026-07-31T12:00:00Z"
    assert manifest["dashboard_refreshed_at"] == first_dashboard_refreshed_at
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["latest_attempt_status"] == "partial"
    assert state["last_checked_at"] == "2026-07-31T13:00:00Z"
    assert state["last_successful_fetch_at"] == "2026-07-31T12:00:00Z"


def test_filtered_refresh_fetches_only_selected_query_and_merges_current(tmp_path):
    _, success_client = registry_fixture()
    first = refresh_studio_data(
        success_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    first_dashboard_refreshed_at = validate_current_snapshot(tmp_path)[
        "dashboard_refreshed_at"
    ]
    _, selected_client = registry_fixture("changed_referral_deposit")

    summary = refresh_studio_data(
        selected_client,
        output_root=tmp_path,
        mode="fixture",
        query_ids={8204345},
        force=True,
        clock=lambda: NOW + timedelta(hours=1),
        sleeper=lambda _: None,
    )

    assert selected_client.calls == {8204345: 1}
    assert summary.fetched_query_ids == (8204345,)
    assert len(summary.reused_query_ids) == 8
    manifest = validate_current_snapshot(tmp_path)
    assert manifest["unique_query_count"] == 9
    assert manifest["changed_query_ids"] == [8204345]
    assert manifest["dashboard_refreshed_at"] == first_dashboard_refreshed_at
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == summary.snapshot_id
    assert state["previous_snapshot_id"] == first.snapshot_id
    assert (tmp_path / "snapshots" / first.snapshot_id).is_dir()


def test_keep_previous_zero_clears_pointer_and_prunes_old_snapshot(tmp_path):
    _, success_client = registry_fixture()
    first = refresh_studio_data(
        success_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    _, changed_client = registry_fixture("changed_referral_deposit")

    second = refresh_studio_data(
        changed_client,
        output_root=tmp_path,
        mode="fixture",
        query_ids={8204345},
        force=True,
        keep_previous=0,
        clock=lambda: NOW + timedelta(hours=1),
        sleeper=lambda _: None,
    )

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == second.snapshot_id
    assert state["previous_snapshot_id"] is None
    assert not (tmp_path / "snapshots" / first.snapshot_id).exists()


def test_retention_preserves_actual_previous_over_newer_orphan(tmp_path):
    _, success_client = registry_fixture()
    first = refresh_studio_data(
        success_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    orphan = tmp_path / "snapshots" / "fixture-orphan-newer"
    orphan.mkdir()
    os.utime(orphan, (NOW.timestamp() + 7200, NOW.timestamp() + 7200))
    _, changed_client = registry_fixture("changed_referral_deposit")

    refresh_studio_data(
        changed_client,
        output_root=tmp_path,
        mode="fixture",
        query_ids={8204345},
        force=True,
        keep_previous=1,
        clock=lambda: NOW + timedelta(hours=1),
        sleeper=lambda _: None,
    )

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["previous_snapshot_id"] == first.snapshot_id
    assert (tmp_path / "snapshots" / first.snapshot_id).is_dir()
    assert not orphan.exists()


def test_corrupted_active_snapshot_is_rejected(tmp_path):
    requests, client = registry_fixture()
    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    snapshot_dir = tmp_path / "snapshots" / summary.snapshot_id
    query_path = snapshot_dir / requests[8204345].result_file
    query_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        validate_snapshot_directory(snapshot_dir, query_requests=requests)


def test_snapshot_validation_binds_state_directory_and_file_size(tmp_path):
    requests, client = registry_fixture()
    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    snapshot_dir = tmp_path / "snapshots" / summary.snapshot_id
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["queries"][0]["file_size_bytes"] += 1
    manifest.pop("manifest_checksum")
    manifest["manifest_checksum"] = sha256_json(manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="file size"):
        validate_snapshot_directory(
            snapshot_dir,
            query_requests=requests,
            expected_snapshot_id=summary.snapshot_id,
        )

    # Restore the immutable manifest, then prove state is also checksum-bound.
    manifest["queries"][0]["file_size_bytes"] -= 1
    manifest.pop("manifest_checksum")
    manifest["manifest_checksum"] = sha256_json(manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    state = json.loads((tmp_path / "state.json").read_text())
    state["current_manifest_checksum"] = "0" * 64
    (tmp_path / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(StudioIngestionError, match="state checksum"):
        validate_current_snapshot(tmp_path)


def test_snapshot_manifest_id_must_match_active_directory(tmp_path):
    _, client = registry_fixture()
    summary = refresh_studio_data(
        client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    manifest_path = tmp_path / "snapshots" / summary.snapshot_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["snapshot_id"] = "fixture-wrong-id"
    manifest.pop("manifest_checksum")
    manifest["manifest_checksum"] = sha256_json(manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(StudioIngestionError, match="snapshot_id"):
        validate_current_snapshot(tmp_path)


def test_state_write_failure_never_repoints_the_active_snapshot(tmp_path, monkeypatch):
    _, success_client = registry_fixture()
    first = refresh_studio_data(
        success_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    _, changed_client = registry_fixture("changed_referral_deposit")
    original_atomic_write = SnapshotStore._atomic_write

    def fail_state_write(store, path, payload):
        if path.name == "state.json":
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                "controlled state write failure",
            )
        return original_atomic_write(store, path, payload)

    monkeypatch.setattr(SnapshotStore, "_atomic_write", fail_state_write)
    with pytest.raises(StudioIngestionError) as exc_info:
        refresh_studio_data(
            changed_client,
            output_root=tmp_path,
            mode="fixture",
            query_ids={8204345},
            force=True,
            clock=lambda: NOW + timedelta(hours=1),
            sleeper=lambda _: None,
        )

    assert exc_info.value.category is FailureCategory.WRITE_FAILURE
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == first.snapshot_id
    assert (
        tmp_path / "snapshots" / first.snapshot_id / "query_8204345.json"
    ).is_file()
    latest_attempt = json.loads(
        sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text()
    )
    assert latest_attempt["status"] == "failed"
    assert latest_attempt["active_snapshot_preserved"] is True


def test_candidate_validation_value_error_cleans_staging_and_records_failure(
    tmp_path,
    monkeypatch,
):
    _, first_client = registry_fixture()
    first = refresh_studio_data(
        first_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    _, changed_client = registry_fixture("changed_referral_deposit")
    original_validate = studio_ingestion.validate_snapshot_directory

    def fail_candidate_validation(snapshot_dir, **kwargs):
        if Path(snapshot_dir).name.startswith(".studio-snapshot-"):
            raise ValueError("controlled candidate validation failure")
        return original_validate(snapshot_dir, **kwargs)

    monkeypatch.setattr(
        studio_ingestion,
        "validate_snapshot_directory",
        fail_candidate_validation,
    )
    with pytest.raises(StudioIngestionError) as exc_info:
        refresh_studio_data(
            changed_client,
            output_root=tmp_path,
            mode="fixture",
            query_ids={8204345},
            force=True,
            clock=lambda: NOW + timedelta(hours=1),
            sleeper=lambda _: None,
        )

    assert exc_info.value.category is FailureCategory.MANIFEST_FAILURE
    assert not list((tmp_path / "snapshots").glob(".studio-snapshot-*"))
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == first.snapshot_id
    latest_attempt = json.loads(
        sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text()
    )
    assert latest_attempt["status"] == "failed"
    assert latest_attempt["active_snapshot_preserved"] is True


def test_unchanged_state_write_failure_records_failed_attempt(tmp_path, monkeypatch):
    _, first_client = registry_fixture()
    first = refresh_studio_data(
        first_client,
        output_root=tmp_path,
        mode="fixture",
        clock=fixed_clock,
        sleeper=lambda _: None,
    )
    original_atomic_write = SnapshotStore._atomic_write

    def fail_state_write(store, path, payload):
        if path.name == "state.json":
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                "controlled unchanged state write failure",
            )
        return original_atomic_write(store, path, payload)

    monkeypatch.setattr(SnapshotStore, "_atomic_write", fail_state_write)
    dashboards, _, requests = load_query_requests()
    later = lambda: NOW + timedelta(hours=1)
    with pytest.raises(StudioIngestionError) as exc_info:
        refresh_studio_data(
            FixtureDuneClient(requests, dashboards, clock=later),
            output_root=tmp_path,
            mode="fixture",
            clock=later,
            sleeper=lambda _: None,
        )

    assert exc_info.value.category is FailureCategory.WRITE_FAILURE
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["current_snapshot_id"] == first.snapshot_id
    assert state["last_checked_at"] == "2026-07-31T12:00:00Z"
    latest_attempt = json.loads(
        sorted((tmp_path / "attempts").glob("*/attempt.json"))[-1].read_text()
    )
    assert latest_attempt["status"] == "failed"


def test_routed_latest_result_client_has_no_execution_path_and_routes_once():
    latest = SequenceStudioLatestResultClient(
        {8199058: [provider_result(query_id=8199058)]}
    )
    fixture = SequenceStudioLatestResultClient(
        {456: [provider_result(query_id=456, execution_id="fixture-456")]}
    )
    routed = RoutedStudioLatestResultClient(
        {8199058: latest, 456: fixture}
    )

    assert routed.fetch_latest_result(8199058, timeout_seconds=1).query_id == 8199058
    assert routed.fetch_latest_result(456, timeout_seconds=1).query_id == 456
    assert routed.calls == {8199058: 1, 456: 1}
    assert latest.calls == {8199058: 1}
    assert fixture.calls == {456: 1}
    assert not hasattr(routed, "execute_query")
    assert not hasattr(routed, "run_query")


def test_mixed_source_cli_fetches_latest_result_queries_once_and_routes_others_to_fixtures(
    tmp_path,
    monkeypatch,
    capsys,
):
    instances = []

    class MockReadOnlyDuneClient:
        def __init__(self, api_key):
            assert api_key == "fake-read-only-key"
            dashboards, _, requests = load_query_requests()
            self.delegate = FixtureDuneClient(
                requests,
                dashboards,
                clock=fixed_clock,
            )
            self.calls = {}
            instances.append(self)

        def fetch_latest_result(self, query_id, *, timeout_seconds):
            self.calls[query_id] = self.calls.get(query_id, 0) + 1
            result = self.delegate.fetch_latest_result(
                query_id,
                timeout_seconds=timeout_seconds,
            )
            result.provider_metadata["source_mode"] = "live"
            return result

    monkeypatch.setattr(
        fetch_studio_data,
        "DuneLatestResultClient",
        MockReadOnlyDuneClient,
    )
    monkeypatch.setenv("STUDIO_ENABLE_LIVE_DUNE", "1")
    monkeypatch.setenv("DUNE_API_KEY", "fake-read-only-key")

    exit_code = fetch_studio_data.main(
        ["--mixed-source-mode", "--output-dir", str(tmp_path)]
    )
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert json.loads(captured.out)["status"] == "success"
    assert len(instances) == 1
    live_query_ids = {
        8180894,
        8191379,
        8191704,
        8193003,
        8193040,
        8199058,
        8202133,
        8204345,
        8204373,
    }
    assert instances[0].calls == {query_id: 1 for query_id in live_query_ids}
    assert instances[0].delegate.calls == {
        query_id: 1 for query_id in live_query_ids
    }
    assert not hasattr(instances[0], "execute_query")
    assert "fake-read-only-key" not in captured.out
    assert "fake-read-only-key" not in captured.err

    manifest = validate_current_snapshot(tmp_path)
    assert manifest["mode"] == "mixed"
    assert manifest["source"] == "mixed_fixture_and_dune_latest_result"
    assert manifest["unique_query_count"] == 9
    entries = {entry["query_id"]: entry for entry in manifest["queries"]}
    assert entries[8199058]["source_mode"] == "live"
    assert entries[8199058]["provider_mode"] == "latest_result"
    assert entries[8180894]["source_mode"] == "live"
    assert entries[8180894]["provider_mode"] == "latest_result"
    for query_id in (
        8191379,
        8191704,
        8193003,
        8193040,
        8202133,
        8204345,
        8204373,
    ):
        assert entries[query_id]["source_mode"] == "live"
        assert entries[query_id]["provider_mode"] == "latest_result"
    assert all(
        entry["source_mode"] == "fixture"
        for query_id, entry in entries.items()
        if query_id not in live_query_ids
    )


def test_plain_live_cli_scopes_provider_guard_to_generated_queries(
    tmp_path,
    monkeypatch,
    capsys,
):
    instances = []

    class MockReadOnlyDuneClient:
        def __init__(self, api_key):
            assert api_key == "fake-read-only-key"
            dashboards, _, requests = load_query_requests()
            self.delegate = FixtureDuneClient(
                requests,
                dashboards,
                clock=fixed_clock,
            )
            self.calls = {}
            instances.append(self)

        def fetch_latest_result(self, query_id, *, timeout_seconds):
            self.calls[query_id] = self.calls.get(query_id, 0) + 1
            result = self.delegate.fetch_latest_result(
                query_id,
                timeout_seconds=timeout_seconds,
            )
            result.provider_metadata["source_mode"] = "live"
            return result

    monkeypatch.setattr(
        fetch_studio_data,
        "DuneLatestResultClient",
        MockReadOnlyDuneClient,
    )
    monkeypatch.setenv("STUDIO_ENABLE_LIVE_DUNE", "1")
    monkeypatch.setenv("DUNE_API_KEY", "fake-read-only-key")

    exit_code = fetch_studio_data.main(["--output-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert json.loads(captured.out)["status"] == "success"
    assert len(instances) == 1
    live_query_ids = {
        8180894,
        8191379,
        8191704,
        8193003,
        8193040,
        8199058,
        8202133,
        8204345,
        8204373,
    }
    assert instances[0].calls == {query_id: 1 for query_id in live_query_ids}
    assert not any(query_id >= 9100000 for query_id in instances[0].calls)
    assert "fake-read-only-key" not in captured.out
    assert "fake-read-only-key" not in captured.err

    manifest = validate_current_snapshot(tmp_path)
    assert manifest["mode"] == "live"
    assert manifest["source"] == "dune_api"
    assert manifest["unique_query_count"] == 9
    assert all(entry["source_mode"] == "live" for entry in manifest["queries"])
    assert all(
        entry["provider_mode"] == "latest_result"
        for entry in manifest["queries"]
    )


def test_cli_refuses_implicit_live_mode_without_touching_dune(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/fetch_studio_data.py",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"DUNE_API_KEY", "STUDIO_ENABLE_LIVE_DUNE"}
        },
    )

    assert completed.returncode == 1
    assert "Live Dune fetching is disabled" in completed.stderr
    assert not (tmp_path / "state.json").exists()


def test_cli_requires_dune_key_before_constructing_live_client(
    tmp_path,
    monkeypatch,
    capsys,
):
    client_constructed = False

    def forbidden_client(api_key):
        nonlocal client_constructed
        del api_key
        client_constructed = True
        raise AssertionError("live client must not be constructed without a secret")

    monkeypatch.setenv("STUDIO_ENABLE_LIVE_DUNE", "1")
    monkeypatch.delenv("DUNE_API_KEY", raising=False)
    monkeypatch.setattr(
        fetch_studio_data,
        "DuneLatestResultClient",
        forbidden_client,
    )

    exit_code = fetch_studio_data.main(["--output-dir", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "DUNE_API_KEY is required for explicitly enabled live mode",
        "status": "failed",
    }
    assert client_constructed is False
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "attempts").exists()


@pytest.mark.parametrize(
    "fixture_only_args",
    [
        ["--fixture-now", "2026-07-31T12:00:00Z"],
        ["--fixture-scenario", "missing_required_column"],
    ],
)
def test_cli_rejects_fixture_only_options_on_live_path(tmp_path, fixture_only_args):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/fetch_studio_data.py",
            "--output-dir",
            str(tmp_path),
            *fixture_only_args,
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "STUDIO_ENABLE_LIVE_DUNE": "1",
            "DUNE_API_KEY": "must-not-be-used",
        },
    )

    assert completed.returncode == 1
    assert "Fixture-only options require --fixture-mode" in completed.stderr
    assert not (tmp_path / "state.json").exists()


def test_cli_validate_only_can_check_registry_before_first_snapshot(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/fetch_studio_data.py",
            "--validate-only",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["registry_valid"] is True
    assert payload["active_snapshot"] is False
    assert payload["unique_query_count"] == 9


def test_cli_fixture_and_validate_only_round_trip(tmp_path):
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "scripts/fetch_studio_data.py",
        "--fixture-mode",
        "--fixture-now",
        "2026-07-31T12:00:00Z",
        "--output-dir",
        str(tmp_path),
    ]
    built = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    assert json.loads(built.stdout)["status"] == "success"

    checked = subprocess.run(
        [
            sys.executable,
            "scripts/fetch_studio_data.py",
            "--validate-only",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["status"] == "valid"


@pytest.mark.parametrize(
    "invalid_args",
    [
        ["--timeout", "0"],
        ["--timeout", "nan"],
        ["--max-attempts", "0"],
        ["--backoff", "-1"],
        ["--keep-previous", "-1"],
    ],
)
def test_cli_rejects_invalid_numeric_options_without_writing(tmp_path, invalid_args):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/fetch_studio_data.py",
            "--fixture-mode",
            "--output-dir",
            str(tmp_path),
            *invalid_args,
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert not (tmp_path / "state.json").exists()


def test_cli_verbose_logs_stay_on_stderr_and_stdout_remains_json(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/fetch_studio_data.py",
            "--fixture-mode",
            "--fixture-now",
            "2026-07-31T12:00:00Z",
            "--output-dir",
            str(tmp_path),
            "--verbose",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "success"
    assert "query 8180894: fetching once for 8 metric(s)" in completed.stderr
