from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import math
import re
from typing import Iterable, Mapping, Sequence


METHODOLOGY_VERSION = "1.0.0"
DEPOSITS_TRANSFORMATION_ID = "kyberswap_growth_deposits"
TVL_TRANSFORMATION_ID = "kyberswap_growth_attributed_tvl"
BREAKDOWN_TRANSFORMATION_ID = "kyberswap_growth_breakdown"
ACTIVITY_TRANSFORMATION_ID = "kyberswap_growth_activity"
POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID = "kyberswap_post_referral_activity"

DEPOSITS_QUERY_ID = 8191379
TVL_QUERY_ID = 8191704
BREAKDOWN_QUERY_ID = 8193003
ACTIVITY_QUERY_ID = 8193040
POST_REFERRAL_ACTIVITY_QUERY_ID = 8202133

DEPOSITS_SOURCE_COLUMNS = (
    "day",
    "week",
    "daily_deposits_usd",
    "weekly_deposits_usd",
    "cum_deposits_usd",
    "last_updated",
)
TVL_SOURCE_COLUMNS = (
    "day",
    "week",
    "depositor_type",
    "daily_attributed_tvl_usd",
    "cum_attributed_tvl_usd",
)
BREAKDOWN_SOURCE_COLUMNS = (
    "day",
    "week",
    "product_symbol",
    "depositor_type",
    "daily_deposits",
)
ACTIVITY_SOURCE_COLUMNS = (
    "timestamp_type",
    "timestamp",
    "category_type",
    "category",
    "metric_type",
    "metric_value",
)
POST_REFERRAL_ACTIVITY_SOURCE_COLUMNS = (
    "day",
    "week",
    "project",
    "event",
    "label",
    "amount_usd",
)

PROVENANCE_COLUMNS = (
    "source_query_id",
    "source_execution_id",
    "source_last_updated",
    "generated_at",
)
DEPOSITS_OUTPUT_COLUMNS = (
    "record_type",
    "period",
    "day",
    "observation_day",
    "week",
    "daily_deposits_usd",
    "weekly_deposits_usd",
    "cum_deposits_usd",
    "last_updated",
    *PROVENANCE_COLUMNS,
)
TVL_OUTPUT_COLUMNS = (
    "record_type",
    "period",
    "day",
    "observation_day",
    "week",
    "depositor_type",
    "daily_attributed_tvl_usd",
    "cum_attributed_tvl_usd",
    *PROVENANCE_COLUMNS,
)
BREAKDOWN_OUTPUT_COLUMNS = (
    "record_type",
    "period",
    "day",
    "week",
    "product_symbol",
    "depositor_type",
    "daily_deposits",
    *PROVENANCE_COLUMNS,
)
ACTIVITY_OUTPUT_COLUMNS = (
    "record_type",
    "period",
    "timestamp_type",
    "timestamp",
    "category_type",
    "category",
    "metric_type",
    "metric_value",
    *PROVENANCE_COLUMNS,
)
POST_REFERRAL_ACTIVITY_OUTPUT_COLUMNS = (
    "record_type",
    "granularity",
    "period",
    "day",
    "week",
    "grouping_type",
    "category",
    "amount_usd",
    *PROVENANCE_COLUMNS,
)

DEPOSITOR_TYPES = (
    "New Depositor",
    "Existing Depositor",
    "Past Depositor",
)
EXPECTED_PRODUCT_ORDER = ("eETH", "liquidETH", "liquidUSD", "liquidBTC")
TIMESTAMP_TYPES = ("day", "week")
CATEGORY_TYPES = ("product", "depositor_type")
METRIC_TYPES = ("deposits", "depositors")
POST_REFERRAL_ACTIVITY_GROUPING_TYPES = ("label", "project", "event")
POST_REFERRAL_ACTIVITY_RECORD_TYPES = tuple(
    f"{granularity}_{grouping_type}"
    for grouping_type in POST_REFERRAL_ACTIVITY_GROUPING_TYPES
    for granularity in ("daily", "weekly")
)
TEXT_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,120}$")


class KyberSwapGrowthError(ValueError):
    """A latest stored Campaign Growth result violates its data contract."""


@dataclass(frozen=True)
class GrowthResult:
    rows: list[dict]
    columns: list[str]
    summary: dict
    warnings: list[dict]
    source_last_updated: str


def _normalized_datetime_text(value: str) -> str:
    text = value.strip()
    if text.endswith(" UTC"):
        return text[:-4] + "+00:00"
    if text.endswith("Z"):
        return text[:-1] + "+00:00"
    return text


def _parse_timestamp(
    value: object,
    *,
    field: str,
    allow_naive_utc: bool = False,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise KyberSwapGrowthError(f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(_normalized_datetime_text(value))
    except ValueError as exc:
        raise KyberSwapGrowthError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if not allow_naive_utc:
            raise KyberSwapGrowthError(f"{field} must include a timezone")
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_date(value: object, *, field: str, row_index: int) -> date:
    if not isinstance(value, str) or not value.strip():
        raise KyberSwapGrowthError(
            f"row {row_index} field {field} must be an ISO date"
        )
    text = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
        parsed = datetime.fromisoformat(_normalized_datetime_text(text))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
    except ValueError as exc:
        raise KyberSwapGrowthError(
            f"row {row_index} field {field} must be an ISO date or timezone-aware timestamp"
        ) from exc
    return parsed.astimezone(timezone.utc).date()


def _week_start(value: date) -> str:
    return (value - timedelta(days=value.weekday())).isoformat()


def _required_text(value: object, *, field: str, row_index: int) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise KyberSwapGrowthError(
            f"row {row_index} field {field} must be a non-empty trimmed string"
        )
    if not TEXT_PATTERN.fullmatch(value):
        raise KyberSwapGrowthError(f"row {row_index} field {field} is malformed")
    return value


def _decimal(
    value: object,
    *,
    field: str,
    row_index: int,
    integer: bool = False,
    non_negative: bool = True,
) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise KyberSwapGrowthError(f"row {row_index} field {field} must be numeric")
    if isinstance(value, float) and not math.isfinite(value):
        raise KyberSwapGrowthError(f"row {row_index} field {field} must be finite")
    if not isinstance(value, (str, int, float, Decimal)):
        raise KyberSwapGrowthError(f"row {row_index} field {field} must be numeric")
    if isinstance(value, str) and not value.strip():
        raise KyberSwapGrowthError(f"row {row_index} field {field} must be numeric")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise KyberSwapGrowthError(
            f"row {row_index} field {field} must be numeric"
        ) from exc
    if not parsed.is_finite():
        raise KyberSwapGrowthError(f"row {row_index} field {field} must be finite")
    if non_negative and parsed < 0:
        raise KyberSwapGrowthError(
            f"row {row_index} field {field} must not be negative"
        )
    if integer and parsed != parsed.to_integral_value():
        raise KyberSwapGrowthError(
            f"row {row_index} field {field} must be an integer"
        )
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _sum(values: Iterable[Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = 78
        return sum(values, Decimal(0))


def _validate_exact_schema(
    rows: Iterable[Mapping[str, object]],
    *,
    expected_columns: Sequence[str],
    source_columns: Sequence[str],
    query_id: int,
) -> list[Mapping[str, object]]:
    expected = tuple(expected_columns)
    if source_columns:
        if any(not isinstance(column, str) or not column for column in source_columns):
            raise KyberSwapGrowthError(
                "source_columns must contain non-empty strings"
            )
        if len(set(source_columns)) != len(source_columns):
            raise KyberSwapGrowthError("source_columns must not contain duplicates")
        missing = sorted(set(expected) - set(source_columns))
        unexpected = sorted(set(source_columns) - set(expected))
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise KyberSwapGrowthError(
                f"query {query_id} latest-result schema mismatch: {'; '.join(details)}"
            )

    materialized = list(rows)
    if not materialized:
        raise KyberSwapGrowthError(f"query {query_id} returned no source rows")
    for row_index, row in enumerate(materialized):
        if not isinstance(row, Mapping):
            raise KyberSwapGrowthError(f"row {row_index} must be an object")
        missing = sorted(set(expected) - set(row))
        unexpected = sorted(set(row) - set(expected))
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise KyberSwapGrowthError(
                f"row {row_index} schema mismatch: {'; '.join(details)}"
            )
    return materialized


def _provenance(
    *,
    source_query_id: int,
    expected_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
) -> tuple[dict, str]:
    if source_query_id != expected_query_id:
        raise KyberSwapGrowthError(
            f"transformation requires source query {expected_query_id}"
        )
    if not isinstance(source_execution_id, str) or not source_execution_id.strip():
        raise KyberSwapGrowthError("source_execution_id must be a non-empty string")
    updated = _iso_utc(
        _parse_timestamp(source_last_updated, field="source_last_updated")
    )
    generated = _iso_utc(_parse_timestamp(generated_at, field="generated_at"))
    return (
        {
            "source_query_id": expected_query_id,
            "source_execution_id": source_execution_id.strip(),
            "source_last_updated": updated,
            "generated_at": generated,
        },
        updated,
    )


def _validated_day_week(
    row: Mapping[str, object], *, row_index: int
) -> tuple[str, str]:
    day = _parse_date(row["day"], field="day", row_index=row_index)
    week = _parse_date(row["week"], field="week", row_index=row_index)
    expected_week = _week_start(day)
    if week.isoformat() != expected_week:
        raise KyberSwapGrowthError(
            f"row {row_index} field week must be Monday {expected_week} for day {day}"
        )
    return day.isoformat(), week.isoformat()


def _ordered_products(products: set[str]) -> list[str]:
    expected = [product for product in EXPECTED_PRODUCT_ORDER if product in products]
    unexpected = sorted(
        products.difference(EXPECTED_PRODUCT_ORDER),
        key=lambda product: (product.casefold(), product),
    )
    return [*expected, *unexpected]


def _product_warnings(products: set[str]) -> tuple[list[str], list[dict]]:
    ordered = _ordered_products(products)
    unexpected = [product for product in ordered if product not in EXPECTED_PRODUCT_ORDER]
    return ordered, [
        {
            "code": "unexpected_product",
            "product_symbol": product,
            "message": f"Unexpected product {product} was retained",
        }
        for product in unexpected
    ]


def _depositor_type_warnings(
    depositor_types: set[str],
) -> tuple[list[str], list[dict]]:
    expected = [
        depositor_type
        for depositor_type in DEPOSITOR_TYPES
        if depositor_type in depositor_types
    ]
    unexpected = sorted(
        depositor_types.difference(DEPOSITOR_TYPES),
        key=lambda depositor_type: (depositor_type.casefold(), depositor_type),
    )
    ordered = [*expected, *unexpected]
    return ordered, [
        {
            "code": "unexpected_depositor_type",
            "depositor_type": depositor_type,
            "message": f"Unexpected depositor type {depositor_type} was retained",
        }
        for depositor_type in unexpected
    ]


def prepare_kyberswap_growth_deposits(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> GrowthResult:
    """Prepare q8191379 daily rows and one latest observation per week."""
    source_rows = _validate_exact_schema(
        rows,
        expected_columns=DEPOSITS_SOURCE_COLUMNS,
        source_columns=source_columns,
        query_id=DEPOSITS_QUERY_ID,
    )
    provenance, updated = _provenance(
        source_query_id=source_query_id,
        expected_query_id=DEPOSITS_QUERY_ID,
        source_execution_id=source_execution_id,
        source_last_updated=source_last_updated,
        generated_at=generated_at,
    )
    normalized: list[dict] = []
    seen_days: set[str] = set()
    for row_index, row in enumerate(source_rows):
        day, week = _validated_day_week(row, row_index=row_index)
        if day in seen_days:
            raise KyberSwapGrowthError(f"duplicate source day {day}")
        seen_days.add(day)
        normalized.append(
            {
                "day": day,
                "week": week,
                "daily_deposits_usd": _decimal(
                    row["daily_deposits_usd"],
                    field="daily_deposits_usd",
                    row_index=row_index,
                ),
                "weekly_deposits_usd": _decimal(
                    row["weekly_deposits_usd"],
                    field="weekly_deposits_usd",
                    row_index=row_index,
                ),
                "cum_deposits_usd": _decimal(
                    row["cum_deposits_usd"],
                    field="cum_deposits_usd",
                    row_index=row_index,
                ),
                "last_updated_dt": _parse_timestamp(
                    row["last_updated"],
                    field=f"row {row_index} field last_updated",
                    allow_naive_utc=True,
                ),
            }
        )
    normalized.sort(key=lambda row: row["day"])
    for previous, current in zip(normalized, normalized[1:]):
        if current["cum_deposits_usd"] < previous["cum_deposits_usd"]:
            raise KyberSwapGrowthError("cum_deposits_usd must be nondecreasing by day")

    def output(record_type: str, row: Mapping[str, object]) -> dict:
        return {
            "record_type": record_type,
            "period": row["day"] if record_type == "daily" else row["week"],
            "day": row["day"],
            "observation_day": row["day"],
            "week": row["week"],
            "daily_deposits_usd": _decimal_text(row["daily_deposits_usd"]),
            "weekly_deposits_usd": _decimal_text(row["weekly_deposits_usd"]),
            "cum_deposits_usd": _decimal_text(row["cum_deposits_usd"]),
            "last_updated": _iso_utc(row["last_updated_dt"]),
            **provenance,
        }

    weekly_latest: dict[str, dict] = {}
    for row in normalized:
        weekly_latest[row["week"]] = row
    output_rows = [output("daily", row) for row in normalized]
    output_rows.extend(
        output("weekly", weekly_latest[week]) for week in sorted(weekly_latest)
    )
    summary = {
        "source_rows": len(normalized),
        "generated_rows": len(output_rows),
        "row_counts": {"daily": len(normalized), "weekly": len(weekly_latest)},
        "weekly_selection": "latest_day",
        "weekly_deposits_usd_summed": False,
        "cumulative_nondecreasing": True,
        "last_updated_validated": True,
        "source_last_updated": updated,
        "warning_count": 0,
    }
    return GrowthResult(
        rows=output_rows,
        columns=list(DEPOSITS_OUTPUT_COLUMNS),
        summary=summary,
        warnings=[],
        source_last_updated=updated,
    )


def prepare_kyberswap_growth_attributed_tvl(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> GrowthResult:
    """Prepare q8191704 type series, derived All series, and weekly snapshots."""
    source_rows = _validate_exact_schema(
        rows,
        expected_columns=TVL_SOURCE_COLUMNS,
        source_columns=source_columns,
        query_id=TVL_QUERY_ID,
    )
    provenance, updated = _provenance(
        source_query_id=source_query_id,
        expected_query_id=TVL_QUERY_ID,
        source_execution_id=source_execution_id,
        source_last_updated=source_last_updated,
        generated_at=generated_at,
    )
    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row_index, row in enumerate(source_rows):
        day, week = _validated_day_week(row, row_index=row_index)
        depositor_type = _required_text(
            row["depositor_type"], field="depositor_type", row_index=row_index
        )
        grain = (day, depositor_type)
        if grain in seen:
            raise KyberSwapGrowthError(
                f"duplicate source grain day={day}, depositor_type={depositor_type}"
            )
        seen.add(grain)
        normalized.append(
            {
                "day": day,
                "week": week,
                "depositor_type": depositor_type,
                "daily_attributed_tvl_usd": _decimal(
                    row["daily_attributed_tvl_usd"],
                    field="daily_attributed_tvl_usd",
                    row_index=row_index,
                ),
                "cum_attributed_tvl_usd": _decimal(
                    row["cum_attributed_tvl_usd"],
                    field="cum_attributed_tvl_usd",
                    row_index=row_index,
                ),
            }
        )
    depositor_types, warnings = _depositor_type_warnings(
        {row["depositor_type"] for row in normalized}
    )
    depositor_order = {
        depositor_type: index
        for index, depositor_type in enumerate(depositor_types)
    }
    normalized.sort(
        key=lambda row: (row["day"], depositor_order[row["depositor_type"]])
    )
    by_day: dict[str, list[dict]] = {}
    for row in normalized:
        by_day.setdefault(row["day"], []).append(row)
    day_cumulative: dict[str, Decimal] = {}
    for day, day_rows in sorted(by_day.items()):
        cumulative_values = {row["cum_attributed_tvl_usd"] for row in day_rows}
        if len(cumulative_values) != 1:
            raise KyberSwapGrowthError(
                f"cum_attributed_tvl_usd repeated totals disagree for day {day}"
            )
        day_cumulative[day] = next(iter(cumulative_values))
    def output(record_type: str, row: Mapping[str, object]) -> dict:
        return {
            "record_type": record_type,
            "period": row["day"] if record_type.startswith("daily") else row["week"],
            "day": row["day"],
            "observation_day": row["day"],
            "week": row["week"],
            "depositor_type": row["depositor_type"],
            "daily_attributed_tvl_usd": _decimal_text(
                row["daily_attributed_tvl_usd"]
            ),
            "cum_attributed_tvl_usd": _decimal_text(
                row["cum_attributed_tvl_usd"]
            ),
            **provenance,
        }

    daily_all: list[dict] = []
    for day, day_rows in sorted(by_day.items()):
        daily_all.append(
            {
                "day": day,
                "week": day_rows[0]["week"],
                "depositor_type": "All",
                "daily_attributed_tvl_usd": _sum(
                    row["daily_attributed_tvl_usd"] for row in day_rows
                ),
                "cum_attributed_tvl_usd": day_cumulative[day],
            }
        )
    weekly_all: dict[str, dict] = {}
    for row in daily_all:
        weekly_all[row["week"]] = row
    weekly_type: dict[tuple[str, str], dict] = {}
    for row in normalized:
        weekly_type[(row["week"], row["depositor_type"])] = row

    output_rows = [output("daily_all", row) for row in daily_all]
    output_rows.extend(output("daily_depositor_type", row) for row in normalized)
    output_rows.extend(
        output("weekly_all", weekly_all[week]) for week in sorted(weekly_all)
    )
    output_rows.extend(
        output("weekly_depositor_type", row)
        for _, row in sorted(
            weekly_type.items(),
            key=lambda item: (
                item[0][0],
                depositor_order[item[0][1]],
            ),
        )
    )
    row_counts = {
        record_type: sum(row["record_type"] == record_type for row in output_rows)
        for record_type in (
            "daily_all",
            "weekly_all",
            "daily_depositor_type",
            "weekly_depositor_type",
        )
    }
    summary = {
        "source_rows": len(normalized),
        "generated_rows": len(output_rows),
        "row_counts": row_counts,
        "depositor_types": depositor_types,
        "reconciliations": {
            "daily_all_equals_type_sum": all(
                _sum(row["daily_attributed_tvl_usd"] for row in by_day[item["day"]])
                == item["daily_attributed_tvl_usd"]
                for item in daily_all
            ),
            "repeated_cumulative_totals_agree": True,
            "weekly_uses_latest_observation": True,
        },
        "source_last_updated": updated,
        "warning_count": len(warnings),
    }
    return GrowthResult(
        rows=output_rows,
        columns=list(TVL_OUTPUT_COLUMNS),
        summary=summary,
        warnings=warnings,
        source_last_updated=updated,
    )


def prepare_kyberswap_growth_breakdown(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> GrowthResult:
    """Prepare q8193003 daily/weekly product and depositor-type sums."""
    source_rows = _validate_exact_schema(
        rows,
        expected_columns=BREAKDOWN_SOURCE_COLUMNS,
        source_columns=source_columns,
        query_id=BREAKDOWN_QUERY_ID,
    )
    provenance, updated = _provenance(
        source_query_id=source_query_id,
        expected_query_id=BREAKDOWN_QUERY_ID,
        source_execution_id=source_execution_id,
        source_last_updated=source_last_updated,
        generated_at=generated_at,
    )
    normalized: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row_index, row in enumerate(source_rows):
        day, week = _validated_day_week(row, row_index=row_index)
        product = _required_text(
            row["product_symbol"], field="product_symbol", row_index=row_index
        )
        depositor_type = _required_text(
            row["depositor_type"], field="depositor_type", row_index=row_index
        )
        grain = (day, product, depositor_type)
        if grain in seen:
            raise KyberSwapGrowthError(
                f"duplicate source grain day={day}, product_symbol={product}, "
                f"depositor_type={depositor_type}"
            )
        seen.add(grain)
        normalized.append(
            {
                "day": day,
                "week": week,
                "product_symbol": product,
                "depositor_type": depositor_type,
                "daily_deposits": _decimal(
                    row["daily_deposits"],
                    field="daily_deposits",
                    row_index=row_index,
                ),
            }
        )

    products, product_warnings = _product_warnings(
        {row["product_symbol"] for row in normalized}
    )
    depositor_types, depositor_warnings = _depositor_type_warnings(
        {row["depositor_type"] for row in normalized}
    )
    warnings = [*product_warnings, *depositor_warnings]
    product_order = {product: index for index, product in enumerate(products)}
    depositor_order = {
        depositor_type: index
        for index, depositor_type in enumerate(depositor_types)
    }

    aggregates: dict[str, dict[tuple[str, str], Decimal]] = {
        "daily_product": {},
        "weekly_product": {},
        "daily_depositor_type": {},
        "weekly_depositor_type": {},
    }
    with localcontext() as context:
        context.prec = 78
        for row in normalized:
            keys = {
                "daily_product": (row["day"], row["product_symbol"]),
                "weekly_product": (row["week"], row["product_symbol"]),
                "daily_depositor_type": (row["day"], row["depositor_type"]),
                "weekly_depositor_type": (row["week"], row["depositor_type"]),
            }
            for record_type, key in keys.items():
                aggregates[record_type][key] = (
                    aggregates[record_type].get(key, Decimal(0))
                    + row["daily_deposits"]
                )

    output_rows: list[dict] = []
    for record_type, values in aggregates.items():
        weekly = record_type.startswith("weekly")
        by_product = record_type.endswith("product")
        category_order = product_order if by_product else depositor_order
        for (period, category), amount in sorted(
            values.items(),
            key=lambda item: (item[0][0], category_order[item[0][1]]),
        ):
            output_rows.append(
                {
                    "record_type": record_type,
                    "period": period,
                    "day": None if weekly else period,
                    "week": period if weekly else _week_start(date.fromisoformat(period)),
                    "product_symbol": category if by_product else None,
                    "depositor_type": None if by_product else category,
                    "daily_deposits": _decimal_text(amount),
                    **provenance,
                }
            )
    source_total = _sum(row["daily_deposits"] for row in normalized)
    aggregate_totals = {
        record_type: _sum(values.values())
        for record_type, values in aggregates.items()
    }
    reconciliations = {
        record_type: total == source_total
        for record_type, total in aggregate_totals.items()
    }
    summary = {
        "source_rows": len(normalized),
        "generated_rows": len(output_rows),
        "row_counts": {
            record_type: len(values) for record_type, values in aggregates.items()
        },
        "products": products,
        "depositor_types": depositor_types,
        "totals": {
            "source": _decimal_text(source_total),
            **{
                record_type: _decimal_text(total)
                for record_type, total in aggregate_totals.items()
            },
        },
        "reconciliations": reconciliations,
        "source_last_updated": updated,
        "warning_count": len(warnings),
    }
    return GrowthResult(
        rows=output_rows,
        columns=list(BREAKDOWN_OUTPUT_COLUMNS),
        summary=summary,
        warnings=warnings,
        source_last_updated=updated,
    )


def prepare_kyberswap_growth_activity(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> GrowthResult:
    """Validate and preserve q8193040's already-aggregated integer rows."""
    source_rows = _validate_exact_schema(
        rows,
        expected_columns=ACTIVITY_SOURCE_COLUMNS,
        source_columns=source_columns,
        query_id=ACTIVITY_QUERY_ID,
    )
    provenance, updated = _provenance(
        source_query_id=source_query_id,
        expected_query_id=ACTIVITY_QUERY_ID,
        source_execution_id=source_execution_id,
        source_last_updated=source_last_updated,
        generated_at=generated_at,
    )
    output_rows: list[dict] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    products: set[str] = set()
    depositor_types: set[str] = set()
    for row_index, row in enumerate(source_rows):
        timestamp_type = _required_text(
            row["timestamp_type"], field="timestamp_type", row_index=row_index
        )
        if timestamp_type not in TIMESTAMP_TYPES:
            raise KyberSwapGrowthError(
                f"row {row_index} field timestamp_type must be day or week"
            )
        timestamp = _parse_date(
            row["timestamp"], field="timestamp", row_index=row_index
        )
        if timestamp_type == "week" and timestamp.weekday() != 0:
            raise KyberSwapGrowthError(
                f"row {row_index} weekly timestamp must be a Monday"
            )
        category_type = _required_text(
            row["category_type"], field="category_type", row_index=row_index
        )
        if category_type not in CATEGORY_TYPES:
            raise KyberSwapGrowthError(
                f"row {row_index} field category_type must be product or depositor_type"
            )
        category = _required_text(
            row["category"], field="category", row_index=row_index
        )
        if category_type == "product":
            products.add(category)
        else:
            depositor_types.add(category)
        metric_type = _required_text(
            row["metric_type"], field="metric_type", row_index=row_index
        )
        if metric_type not in METRIC_TYPES:
            raise KyberSwapGrowthError(
                f"row {row_index} field metric_type must be deposits or depositors"
            )
        metric_value = _decimal(
            row["metric_value"],
            field="metric_value",
            row_index=row_index,
            integer=True,
        )
        timestamp_text = timestamp.isoformat()
        grain = (
            timestamp_type,
            timestamp_text,
            category_type,
            category,
            metric_type,
        )
        if grain in seen:
            raise KyberSwapGrowthError(
                "duplicate activity grain "
                + "/".join(grain)
            )
        seen.add(grain)
        output_rows.append(
            {
                "record_type": f"{timestamp_type}_{category_type}_{metric_type}",
                "period": timestamp_text,
                "timestamp_type": timestamp_type,
                "timestamp": timestamp_text,
                "category_type": category_type,
                "category": category,
                "metric_type": metric_type,
                "metric_value": int(metric_value),
                **provenance,
            }
        )
    ordered_products, product_warnings = _product_warnings(products)
    ordered_depositor_types, depositor_warnings = _depositor_type_warnings(
        depositor_types
    )
    warnings = [*product_warnings, *depositor_warnings]
    product_order = {
        product: index for index, product in enumerate(ordered_products)
    }
    depositor_order = {
        depositor_type: index
        for index, depositor_type in enumerate(ordered_depositor_types)
    }
    output_rows.sort(
        key=lambda row: (
            TIMESTAMP_TYPES.index(row["timestamp_type"]),
            row["timestamp"],
            CATEGORY_TYPES.index(row["category_type"]),
            (
                product_order[row["category"]]
                if row["category_type"] == "product"
                else depositor_order[row["category"]]
            ),
            METRIC_TYPES.index(row["metric_type"]),
        )
    )
    row_counts: dict[str, int] = {}
    for row in output_rows:
        row_counts[row["record_type"]] = row_counts.get(row["record_type"], 0) + 1
    summary = {
        "source_rows": len(output_rows),
        "generated_rows": len(output_rows),
        "row_counts": row_counts,
        "products": ordered_products,
        "depositor_types": ordered_depositor_types,
        "timestamp_types": list(TIMESTAMP_TYPES),
        "category_types": list(CATEGORY_TYPES),
        "metric_types": list(METRIC_TYPES),
        "distinct_grains": True,
        "integer_values": True,
        "source_last_updated": updated,
        "warning_count": len(warnings),
    }
    return GrowthResult(
        rows=output_rows,
        columns=list(ACTIVITY_OUTPUT_COLUMNS),
        summary=summary,
        warnings=warnings,
        source_last_updated=updated,
    )


def prepare_kyberswap_post_referral_activity(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> GrowthResult:
    """Prepare q8202133 signed daily/weekly label, project, and event sums."""
    source_rows = _validate_exact_schema(
        rows,
        expected_columns=POST_REFERRAL_ACTIVITY_SOURCE_COLUMNS,
        source_columns=source_columns,
        query_id=POST_REFERRAL_ACTIVITY_QUERY_ID,
    )
    provenance, updated = _provenance(
        source_query_id=source_query_id,
        expected_query_id=POST_REFERRAL_ACTIVITY_QUERY_ID,
        source_execution_id=source_execution_id,
        source_last_updated=source_last_updated,
        generated_at=generated_at,
    )

    normalized: list[dict] = []
    for row_index, row in enumerate(source_rows):
        day, week = _validated_day_week(row, row_index=row_index)
        normalized.append(
            {
                "day": day,
                "week": week,
                "label": _required_text(
                    row["label"], field="label", row_index=row_index
                ),
                "project": _required_text(
                    row["project"], field="project", row_index=row_index
                ),
                "event": _required_text(
                    row["event"], field="event", row_index=row_index
                ),
                "amount_usd": _decimal(
                    row["amount_usd"],
                    field="amount_usd",
                    row_index=row_index,
                    non_negative=False,
                ),
            }
        )

    aggregates: dict[str, dict[tuple[str, str], Decimal]] = {
        record_type: {} for record_type in POST_REFERRAL_ACTIVITY_RECORD_TYPES
    }
    with localcontext() as context:
        context.prec = 78
        for row in normalized:
            for grouping_type in POST_REFERRAL_ACTIVITY_GROUPING_TYPES:
                category = row[grouping_type]
                for granularity, period in (
                    ("daily", row["day"]),
                    ("weekly", row["week"]),
                ):
                    record_type = f"{granularity}_{grouping_type}"
                    key = (period, category)
                    aggregates[record_type][key] = (
                        aggregates[record_type].get(key, Decimal(0))
                        + row["amount_usd"]
                    )

    output_rows: list[dict] = []
    for record_type in POST_REFERRAL_ACTIVITY_RECORD_TYPES:
        granularity, grouping_type = record_type.split("_", 1)
        weekly = granularity == "weekly"
        for (period, category), amount_usd in sorted(
            aggregates[record_type].items(),
            key=lambda item: (
                item[0][0],
                item[0][1].casefold(),
                item[0][1],
            ),
        ):
            output_rows.append(
                {
                    "record_type": record_type,
                    "granularity": granularity,
                    "period": period,
                    "day": None if weekly else period,
                    "week": (
                        period
                        if weekly
                        else _week_start(date.fromisoformat(period))
                    ),
                    "grouping_type": grouping_type,
                    "category": category,
                    "amount_usd": _decimal_text(amount_usd),
                    **provenance,
                }
            )

    source_total = _sum(row["amount_usd"] for row in normalized)
    aggregate_totals = {
        record_type: _sum(values.values())
        for record_type, values in aggregates.items()
    }
    reconciliations: dict[str, bool] = {}
    for grouping_type in POST_REFERRAL_ACTIVITY_GROUPING_TYPES:
        daily_record_type = f"daily_{grouping_type}"
        weekly_record_type = f"weekly_{grouping_type}"
        reconciliations[f"{daily_record_type}_equals_source"] = (
            aggregate_totals[daily_record_type] == source_total
        )
        reconciliations[f"{weekly_record_type}_equals_source"] = (
            aggregate_totals[weekly_record_type] == source_total
        )

        daily_rollup: dict[tuple[str, str], Decimal] = {}
        with localcontext() as context:
            context.prec = 78
            for (day, category), amount_usd in aggregates[
                daily_record_type
            ].items():
                key = (_week_start(date.fromisoformat(day)), category)
                daily_rollup[key] = daily_rollup.get(key, Decimal(0)) + amount_usd
        reconciliations[f"{weekly_record_type}_equals_daily_rollup"] = (
            aggregates[weekly_record_type] == daily_rollup
        )

    if not all(reconciliations.values()):
        raise KyberSwapGrowthError(
            "post-referral activity aggregate views do not reconcile"
        )

    categories = {
        grouping_type: sorted(
            {row[grouping_type] for row in normalized},
            key=lambda value: (value.casefold(), value),
        )
        for grouping_type in POST_REFERRAL_ACTIVITY_GROUPING_TYPES
    }
    summary = {
        "source_rows": len(normalized),
        "generated_rows": len(output_rows),
        "row_counts": {
            record_type: len(aggregates[record_type])
            for record_type in POST_REFERRAL_ACTIVITY_RECORD_TYPES
        },
        "record_types": list(POST_REFERRAL_ACTIVITY_RECORD_TYPES),
        "grouping_types": list(POST_REFERRAL_ACTIVITY_GROUPING_TYPES),
        "categories": categories,
        "totals": {
            "source": _decimal_text(source_total),
            **{
                record_type: _decimal_text(aggregate_totals[record_type])
                for record_type in POST_REFERRAL_ACTIVITY_RECORD_TYPES
            },
        },
        "reconciliations": reconciliations,
        "signed_values_preserved": True,
        "source_last_updated": updated,
        "warning_count": 0,
    }
    return GrowthResult(
        rows=output_rows,
        columns=list(POST_REFERRAL_ACTIVITY_OUTPUT_COLUMNS),
        summary=summary,
        warnings=[],
        source_last_updated=updated,
    )


__all__ = [
    "ACTIVITY_OUTPUT_COLUMNS",
    "ACTIVITY_QUERY_ID",
    "ACTIVITY_SOURCE_COLUMNS",
    "ACTIVITY_TRANSFORMATION_ID",
    "BREAKDOWN_OUTPUT_COLUMNS",
    "BREAKDOWN_QUERY_ID",
    "BREAKDOWN_SOURCE_COLUMNS",
    "BREAKDOWN_TRANSFORMATION_ID",
    "CATEGORY_TYPES",
    "DEPOSITOR_TYPES",
    "DEPOSITS_OUTPUT_COLUMNS",
    "DEPOSITS_QUERY_ID",
    "DEPOSITS_SOURCE_COLUMNS",
    "DEPOSITS_TRANSFORMATION_ID",
    "EXPECTED_PRODUCT_ORDER",
    "GrowthResult",
    "KyberSwapGrowthError",
    "METRIC_TYPES",
    "METHODOLOGY_VERSION",
    "PROVENANCE_COLUMNS",
    "POST_REFERRAL_ACTIVITY_GROUPING_TYPES",
    "POST_REFERRAL_ACTIVITY_OUTPUT_COLUMNS",
    "POST_REFERRAL_ACTIVITY_QUERY_ID",
    "POST_REFERRAL_ACTIVITY_RECORD_TYPES",
    "POST_REFERRAL_ACTIVITY_SOURCE_COLUMNS",
    "POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID",
    "TIMESTAMP_TYPES",
    "TVL_OUTPUT_COLUMNS",
    "TVL_QUERY_ID",
    "TVL_SOURCE_COLUMNS",
    "TVL_TRANSFORMATION_ID",
    "prepare_kyberswap_growth_activity",
    "prepare_kyberswap_growth_attributed_tvl",
    "prepare_kyberswap_growth_breakdown",
    "prepare_kyberswap_growth_deposits",
    "prepare_kyberswap_post_referral_activity",
]
