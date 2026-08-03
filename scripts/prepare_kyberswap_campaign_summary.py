from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Iterable, Mapping, Sequence


TRANSFORMATION_ID = "kyberswap_campaign_summary"
METHODOLOGY_ID = "kyberswap_campaign_summary_v1"
METHODOLOGY_VERSION = "1.0.0"
SOURCE_QUERY_ID = 8180894

SOURCE_REQUIRED_COLUMNS = (
    "rank_",
    "key_",
)

EXPECTED_NUMERIC_COLUMNS = (
    "total_deposits_usd",
    "outstanding_balance_usd",
    "num_depositors",
    "new_depositors",
    "deposits_by_new_depositors",
    "retention_rate",
    "depositors_new_users_rate",
    "revenue_generated",
)

PROVENANCE_COLUMNS = (
    "source_query_id",
    "source_execution_id",
    "source_last_updated",
    "generated_at",
)

OUTPUT_COLUMNS = SOURCE_REQUIRED_COLUMNS + EXPECTED_NUMERIC_COLUMNS + PROVENANCE_COLUMNS

METRIC_NAMES = {
    "total_deposits_usd": "Total Referral Deposits",
    "outstanding_balance_usd": "Attributed TVL",
    "deposits_by_new_depositors": "Referred Deposits by New Depositors",
    "depositors_new_users_rate": "% Deposits by New Depositors",
    "num_depositors": "Total Depositors",
    "new_depositors": "New Depositors",
    "retention_rate": "Retention Rate",
    "revenue_generated": "Revenue Generated",
}

NON_NEGATIVE_COLUMNS = {
    "total_deposits_usd",
    "outstanding_balance_usd",
    "num_depositors",
    "new_depositors",
    "deposits_by_new_depositors",
}
COUNT_COLUMNS = {"num_depositors", "new_depositors"}
RATE_COLUMNS = {"retention_rate", "depositors_new_users_rate"}
INTERVAL_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class KyberSwapCampaignSummaryError(ValueError):
    """The latest q8180894 result cannot satisfy the summary contract."""


@dataclass(frozen=True)
class CampaignSummaryResult:
    rows: list[dict]
    columns: list[str]
    summary: dict
    warnings: list[dict]
    source_last_updated: str


def _parse_timestamp(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise KyberSwapCampaignSummaryError(
            f"{field} must be a non-empty timezone-aware timestamp"
        )
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise KyberSwapCampaignSummaryError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KyberSwapCampaignSummaryError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_decimal(
    value: object,
    *,
    field: str,
    row_index: int,
    key: str,
) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KyberSwapCampaignSummaryError(
            f"row {row_index} key_={key} field {field} must be numeric"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise KyberSwapCampaignSummaryError(
            f"row {row_index} key_={key} field {field} must be finite"
        )
    if not isinstance(value, (str, int, float, Decimal)):
        raise KyberSwapCampaignSummaryError(
            f"row {row_index} key_={key} field {field} must be numeric"
        )
    if isinstance(value, str) and not value.strip():
        raise KyberSwapCampaignSummaryError(
            f"row {row_index} key_={key} field {field} must be numeric"
        )
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise KyberSwapCampaignSummaryError(
            f"row {row_index} key_={key} field {field} must be numeric"
        ) from exc
    if not parsed.is_finite():
        raise KyberSwapCampaignSummaryError(
            f"row {row_index} key_={key} field {field} must be finite"
        )
    return parsed


def _normalized_source_value(value: object) -> object:
    # Decimal is useful to callers of this pure function but is not a JSON
    # scalar. Dune result values arrive as strings/integers, which pass through
    # unchanged; normalize only an explicitly supplied Decimal test value.
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _validated_interval_key(value: object, *, row_index: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not INTERVAL_KEY_PATTERN.fullmatch(value)
    ):
        raise KyberSwapCampaignSummaryError(
            f"row {row_index} field key_ must be a lowercase interval key"
        )
    return value


def _validated_rank(value: object, *, row_index: int, key: str) -> int:
    rank = _parse_decimal(value, field="rank_", row_index=row_index, key=key)
    if rank <= 0 or rank != rank.to_integral_value():
        raise KyberSwapCampaignSummaryError(
            f"row {row_index} key_={key} field rank_ must be a positive integer"
        )
    return int(rank)


def _raise_contradiction(
    *,
    row_index: int,
    key: str,
    left_column: str,
    right_column: str,
) -> None:
    raise KyberSwapCampaignSummaryError(
        f"row {row_index} key_={key} has contradictory values: "
        f"{left_column} exceeds {right_column}"
    )


def prepare_kyberswap_campaign_summary(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> CampaignSummaryResult:
    """Validate q8180894 and add stable latest-result provenance.

    Missing or null expected counter values are defaulted only in the prepared
    rows. The caller retains the untouched provider response as a raw sidecar.
    """
    if source_query_id != SOURCE_QUERY_ID:
        raise KyberSwapCampaignSummaryError(
            f"methodology {METHODOLOGY_ID} requires source query {SOURCE_QUERY_ID}"
        )
    if not isinstance(source_execution_id, str) or not source_execution_id.strip():
        raise KyberSwapCampaignSummaryError(
            "source_execution_id must be a non-empty string"
        )
    source_last_updated_text = _iso_utc(
        _parse_timestamp(source_last_updated, field="source_last_updated")
    )
    generated_at_text = _iso_utc(
        _parse_timestamp(generated_at, field="generated_at")
    )

    declared_columns: list[str] = []
    for column in source_columns:
        if not isinstance(column, str) or not column:
            raise KyberSwapCampaignSummaryError(
                "source_columns must contain non-empty strings"
            )
        if column not in declared_columns:
            declared_columns.append(column)

    prepared_rows: list[dict] = []
    warnings: list[dict] = []
    seen_keys: set[str] = set()
    fallback_value_count = 0

    for row_index, source_row in enumerate(rows):
        if not isinstance(source_row, Mapping):
            raise KyberSwapCampaignSummaryError(f"row {row_index} must be an object")
        missing_keys = [
            column for column in SOURCE_REQUIRED_COLUMNS if column not in source_row
        ]
        if missing_keys:
            raise KyberSwapCampaignSummaryError(
                f"row {row_index} is missing source columns: {', '.join(missing_keys)}"
            )

        key = _validated_interval_key(source_row["key_"], row_index=row_index)
        if key in seen_keys:
            raise KyberSwapCampaignSummaryError(
                f"duplicate interval key_={key} in q{SOURCE_QUERY_ID} result"
            )
        seen_keys.add(key)
        _validated_rank(source_row["rank_"], row_index=row_index, key=key)

        prepared_row = {
            column: _normalized_source_value(value)
            for column, value in source_row.items()
        }
        supplied: dict[str, bool] = {}
        parsed_values: dict[str, Decimal] = {}
        for column in EXPECTED_NUMERIC_COLUMNS:
            value_is_supplied = column in source_row and source_row[column] is not None
            supplied[column] = value_is_supplied
            if not value_is_supplied:
                prepared_row[column] = 0
                fallback_value_count += 1
                warnings.append(
                    {
                        "code": "missing_numeric_value_defaulted",
                        "key_": key,
                        "column": column,
                        "affected_metric": METRIC_NAMES[column],
                    }
                )
                parsed_values[column] = Decimal(0)
                continue
            parsed_values[column] = _parse_decimal(
                source_row[column],
                field=column,
                row_index=row_index,
                key=key,
            )

        for column in NON_NEGATIVE_COLUMNS:
            if parsed_values[column] < 0:
                raise KyberSwapCampaignSummaryError(
                    f"row {row_index} key_={key} field {column} must not be negative"
                )
        for column in COUNT_COLUMNS:
            if parsed_values[column] != parsed_values[column].to_integral_value():
                raise KyberSwapCampaignSummaryError(
                    f"row {row_index} key_={key} field {column} must be an integer"
                )
        for column in RATE_COLUMNS:
            if parsed_values[column] < 0 or parsed_values[column] > 1:
                raise KyberSwapCampaignSummaryError(
                    f"row {row_index} key_={key} field {column} must be between 0 and 1"
                )

        if (
            supplied["outstanding_balance_usd"]
            and supplied["total_deposits_usd"]
            and parsed_values["outstanding_balance_usd"]
            > parsed_values["total_deposits_usd"]
        ):
            _raise_contradiction(
                row_index=row_index,
                key=key,
                left_column="outstanding_balance_usd",
                right_column="total_deposits_usd",
            )
        if (
            supplied["new_depositors"]
            and supplied["num_depositors"]
            and parsed_values["new_depositors"] > parsed_values["num_depositors"]
        ):
            _raise_contradiction(
                row_index=row_index,
                key=key,
                left_column="new_depositors",
                right_column="num_depositors",
            )
        if (
            supplied["deposits_by_new_depositors"]
            and supplied["total_deposits_usd"]
            and parsed_values["deposits_by_new_depositors"]
            > parsed_values["total_deposits_usd"]
        ):
            _raise_contradiction(
                row_index=row_index,
                key=key,
                left_column="deposits_by_new_depositors",
                right_column="total_deposits_usd",
            )

        prepared_row.update(
            {
                "source_query_id": source_query_id,
                "source_execution_id": source_execution_id,
                "source_last_updated": source_last_updated_text,
                "generated_at": generated_at_text,
            }
        )
        prepared_rows.append(prepared_row)
        for column in source_row:
            if column not in declared_columns:
                declared_columns.append(column)

    if not prepared_rows:
        raise KyberSwapCampaignSummaryError(
            f"query {SOURCE_QUERY_ID} returned no source rows"
        )

    columns = list(declared_columns)
    for column in EXPECTED_NUMERIC_COLUMNS + PROVENANCE_COLUMNS:
        if column not in columns:
            columns.append(column)
    summary = {
        "source_rows": len(prepared_rows),
        "interval_keys": [row["key_"] for row in prepared_rows],
        "fallback_value_count": fallback_value_count,
        "warning_count": len(warnings),
        "source_last_updated": source_last_updated_text,
    }
    return CampaignSummaryResult(
        rows=prepared_rows,
        columns=columns,
        summary=summary,
        warnings=warnings,
        source_last_updated=source_last_updated_text,
    )


__all__ = [
    "CampaignSummaryResult",
    "EXPECTED_NUMERIC_COLUMNS",
    "KyberSwapCampaignSummaryError",
    "METHODOLOGY_ID",
    "METHODOLOGY_VERSION",
    "OUTPUT_COLUMNS",
    "PROVENANCE_COLUMNS",
    "SOURCE_QUERY_ID",
    "SOURCE_REQUIRED_COLUMNS",
    "TRANSFORMATION_ID",
    "prepare_kyberswap_campaign_summary",
]
