from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Iterable, Mapping, Sequence


METHODOLOGY_ID = "kyberswap_attributed_holdings_v1"
METHODOLOGY_VERSION = "2.0.0"
SOURCE_QUERY_ID = 8199058

SOURCE_REQUIRED_COLUMNS = (
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
)

ENRICHED_COLUMNS = (
    "day",
    "address",
    "strategy_symbol",
    "base_asset",
    "depositor_type",
    "referral_balance",
    "previous_balance",
    "total_current_balance",
    "campaign_supported_balance",
    "final_attributable_balance",
    "exited_balance",
    "current_token",
    "current_token_category",
    "current_balance",
    "attributed_balance",
    "unattributed_balance",
    "destination_status",
    "allocation_rank",
    "allocation_rule",
    "methodology_id",
    "source_query_id",
    "source_execution_id",
    "source_last_updated",
    "generated_at",
)

DEPOSITOR_TYPES = {"New Depositor", "Existing Depositor", "Past Depositor"}
EVM_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")


class KyberSwapAttributionError(ValueError):
    """A source row or attribution group cannot satisfy methodology v1."""


@dataclass(frozen=True)
class EnrichmentResult:
    rows: list[dict]
    summary: dict
    warnings: list[dict]
    source_last_updated: str


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _parse_decimal(
    value: object,
    *,
    field: str,
    row_index: int,
    non_negative: bool = False,
    positive: bool = False,
) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or value is None:
        raise KyberSwapAttributionError(
            f"row {row_index} field {field} must be an exact decimal value"
        )
    if not isinstance(value, (str, int, Decimal)):
        raise KyberSwapAttributionError(
            f"row {row_index} field {field} must be an exact decimal value"
        )
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise KyberSwapAttributionError(
            f"row {row_index} field {field} must be an exact decimal value"
        ) from exc
    if not parsed.is_finite():
        raise KyberSwapAttributionError(
            f"row {row_index} field {field} must be finite"
        )
    if positive and parsed <= 0:
        raise KyberSwapAttributionError(
            f"row {row_index} field {field} must be greater than zero"
        )
    if non_negative and parsed < 0:
        raise KyberSwapAttributionError(
            f"row {row_index} field {field} must not be negative"
        )
    return parsed


def _required_text(value: object, *, field: str, row_index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KyberSwapAttributionError(
            f"row {row_index} field {field} must be a non-empty string"
        )
    return value.strip()


def _parse_day(value: object, *, row_index: int) -> str:
    day = _required_text(value, field="day", row_index=row_index)
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            return datetime.strptime(day, "%Y-%m-%d").date().isoformat()
        else:
            parsed = datetime.fromisoformat(_normalized_datetime_text(day))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
    except ValueError as exc:
        raise KyberSwapAttributionError(
            f"row {row_index} field day must be an ISO date or timestamp"
        ) from exc
    return parsed.astimezone(timezone.utc).date().isoformat()


def _normalized_datetime_text(value: str) -> str:
    """Normalize Dune's explicit `` UTC`` timestamps for fromisoformat."""
    stripped = value.strip()
    if stripped.endswith(" UTC"):
        return stripped[:-4] + "+00:00"
    if stripped.endswith("Z"):
        return stripped[:-1] + "+00:00"
    return stripped


def _parse_timestamp(
    value: object,
    *,
    field: str,
    row_index: int,
    allow_naive_utc: bool = False,
) -> datetime:
    raw = _required_text(value, field=field, row_index=row_index)
    try:
        parsed = datetime.fromisoformat(_normalized_datetime_text(raw))
    except ValueError as exc:
        raise KyberSwapAttributionError(
            f"row {row_index} field {field} must be an ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if allow_naive_utc:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            raise KyberSwapAttributionError(
                f"row {row_index} field {field} must include a timezone"
            )
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validated_source_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    source_columns: Sequence[str] = (),
) -> list[dict]:
    if source_columns:
        if any(not isinstance(column, str) or not column for column in source_columns):
            raise KyberSwapAttributionError(
                "source_columns must contain non-empty strings"
            )
        if len(set(source_columns)) != len(source_columns):
            raise KyberSwapAttributionError("source_columns must not contain duplicates")
        missing = sorted(set(SOURCE_REQUIRED_COLUMNS) - set(source_columns))
        unexpected = sorted(set(source_columns) - set(SOURCE_REQUIRED_COLUMNS))
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise KyberSwapAttributionError(
                f"query {SOURCE_QUERY_ID} latest-result schema mismatch: "
                + "; ".join(details)
            )

    parsed_rows: list[dict] = []
    seen_grain: set[tuple[str, str, str, str]] = set()
    for row_index, source_row in enumerate(rows):
        if not isinstance(source_row, Mapping):
            raise KyberSwapAttributionError(f"row {row_index} must be an object")
        missing = sorted(set(SOURCE_REQUIRED_COLUMNS) - set(source_row))
        unexpected = sorted(set(source_row) - set(SOURCE_REQUIRED_COLUMNS))
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise KyberSwapAttributionError(
                f"row {row_index} schema mismatch: {'; '.join(details)}"
            )
        day = _parse_day(source_row["day"], row_index=row_index)
        address = _required_text(source_row["address"], field="address", row_index=row_index)
        if not EVM_ADDRESS_PATTERN.fullmatch(address):
            raise KyberSwapAttributionError(
                f"row {row_index} field address must be an EVM address"
            )
        strategy_symbol = _required_text(
            source_row["strategy_symbol"],
            field="strategy_symbol",
            row_index=row_index,
        )
        current_token = _required_text(
            source_row["current_token"],
            field="current_token",
            row_index=row_index,
        )
        grain = (day, address.lower(), strategy_symbol, current_token)
        if grain in seen_grain:
            raise KyberSwapAttributionError(
                "duplicate source grain for "
                f"day={day}, address={address}, strategy_symbol={strategy_symbol}, "
                f"current_token={current_token}"
            )
        seen_grain.add(grain)
        depositor_type = _required_text(
            source_row["depositor_type"],
            field="depositor_type",
            row_index=row_index,
        )
        category_value = source_row["current_token_category"]
        category = (
            category_value.strip()
            if isinstance(category_value, str) and category_value.strip()
            else None
        )
        parsed_rows.append(
            {
                "row_index": row_index,
                "day": day,
                "address": address,
                "strategy_symbol": strategy_symbol,
                "base_asset": _required_text(
                    source_row["base_asset"],
                    field="base_asset",
                    row_index=row_index,
                ),
                "referral_balance": _parse_decimal(
                    source_row["referral_balance"],
                    field="referral_balance",
                    row_index=row_index,
                    non_negative=True,
                ),
                "current_token": current_token,
                "current_balance": _parse_decimal(
                    source_row["current_balance"],
                    field="current_balance",
                    row_index=row_index,
                ),
                "current_token_category": category,
                "depositor_type": depositor_type,
                "previous_balance": _parse_decimal(
                    source_row["previous_balance"],
                    field="previous_balance",
                    row_index=row_index,
                    non_negative=True,
                ),
            }
        )
    if not parsed_rows:
        raise KyberSwapAttributionError(
            f"query {SOURCE_QUERY_ID} returned no source rows"
        )
    days = {row["day"] for row in parsed_rows}
    if len(days) != 1:
        raise KyberSwapAttributionError(
            f"query {SOURCE_QUERY_ID} must contain exactly one latest snapshot day"
        )
    depositor_types: dict[str, str] = {}
    for row in parsed_rows:
        address_key = row["address"].lower()
        previous_type = depositor_types.setdefault(address_key, row["depositor_type"])
        if previous_type != row["depositor_type"]:
            raise KyberSwapAttributionError(
                f"address {row['address']} has conflicting depositor_type values"
            )
    return parsed_rows


def _consistent(group: list[dict], field: str, group_label: str) -> object:
    values = {row[field] for row in group}
    if len(values) != 1:
        raise KyberSwapAttributionError(
            f"group {group_label} has conflicting repeated {field} values"
        )
    return next(iter(values))


def _allocation_plan(destinations: list[dict], attributable: Decimal) -> tuple[str, dict[str, Decimal], list[dict]]:
    ordered_desc = sorted(
        destinations,
        key=lambda item: (-item["balance"], item["current_token"]),
    )
    allocations = {item["current_token"]: Decimal(0) for item in destinations}
    total = sum((item["balance"] for item in destinations), Decimal(0))
    if attributable == 0:
        return "rule_a_no_current_attributable_balance", allocations, ordered_desc
    if total <= attributable:
        for item in destinations:
            allocations[item["current_token"]] = item["balance"]
        return "rule_b_current_positions_fit", allocations, ordered_desc

    reaches_cap = [item for item in ordered_desc if item["balance"] >= attributable]
    if len(reaches_cap) >= 2:
        winner = reaches_cap[0]
        allocations[winner["current_token"]] = attributable
        return "rule_e_multiple_destinations_reach_cap", allocations, ordered_desc

    if len(reaches_cap) == 1:
        oversized = reaches_cap[0]
        smaller = sorted(
            [item for item in destinations if item is not oversized],
            key=lambda item: (-item["balance"], item["current_token"]),
        )
        remaining = attributable
        for item in smaller:
            allocated = min(item["balance"], remaining)
            allocations[item["current_token"]] = allocated
            remaining -= allocated
            if remaining == 0:
                break
        allocations[oversized["current_token"]] = remaining
        return (
            "rule_d_preserve_smaller_then_oversized",
            allocations,
            smaller + [oversized],
        )

    remaining = attributable
    for item in ordered_desc:
        allocated = min(item["balance"], remaining)
        allocations[item["current_token"]] = allocated
        remaining -= allocated
        if remaining == 0:
            break
    return "rule_c_largest_balance_first", allocations, ordered_desc


def enrich_kyberswap_attributed_holdings(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> EnrichmentResult:
    if source_query_id != SOURCE_QUERY_ID:
        raise KyberSwapAttributionError(
            f"methodology {METHODOLOGY_ID} requires source query {SOURCE_QUERY_ID}"
        )
    if not isinstance(source_execution_id, str) or not source_execution_id.strip():
        raise KyberSwapAttributionError("source_execution_id must be a non-empty string")
    source_updated_timestamp = _parse_timestamp(
        source_last_updated,
        field="source_last_updated",
        row_index=0,
    )
    source_last_updated_text = _iso_utc(source_updated_timestamp)
    generated_timestamp = _parse_timestamp(
        generated_at,
        field="generated_at",
        row_index=0,
    )
    generated_at_text = _iso_utc(generated_timestamp)
    parsed_rows = _validated_source_rows(rows, source_columns=source_columns)
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in parsed_rows:
        key = (row["day"], row["address"].lower(), row["strategy_symbol"])
        groups.setdefault(key, []).append(row)

    enriched_rows: list[dict] = []
    observed_depositor_types = sorted(
        {row["depositor_type"] for row in parsed_rows},
        key=lambda value: (value.casefold(), value),
    )
    warnings: list[dict] = [
        {
            "code": "unexpected_depositor_type",
            "depositor_type": depositor_type,
            "message": f"Unexpected depositor type {depositor_type} was retained",
        }
        for depositor_type in observed_depositor_types
        if depositor_type not in DEPOSITOR_TYPES
    ]
    total_referral_usd = Decimal(0)
    total_active_attributed_usd = Decimal(0)
    total_exited_usd = Decimal(0)
    uncategorized_count = 0
    with localcontext() as decimal_context:
        decimal_context.prec = 256
        for key in sorted(groups):
            group = groups[key]
            day, _, strategy_symbol = key
            address = group[0]["address"]
            group_label = f"day={day}, address={address}, strategy_symbol={strategy_symbol}"
            referral_cap = _consistent(group, "referral_balance", group_label)
            previous_balance = _consistent(group, "previous_balance", group_label)
            base_asset = _consistent(group, "base_asset", group_label)
            depositor_type = _consistent(group, "depositor_type", group_label)
            assert isinstance(referral_cap, Decimal)
            assert isinstance(previous_balance, Decimal)

            destinations: list[dict] = []
            for source_row in group:
                raw_balance = source_row["current_balance"]
                if source_row["current_token"] == "Empty":
                    if raw_balance > 0:
                        raise KyberSwapAttributionError(
                            f"group {group_label} has Empty with a positive current_balance"
                        )
                    if raw_balance < 0:
                        warnings.append(
                            {
                                "code": "negative_current_balance_normalized",
                                "group": group_label,
                                "current_token": "Empty",
                            }
                        )
                    continue
                balance = max(raw_balance, Decimal(0))
                if raw_balance < 0:
                    warnings.append(
                        {
                            "code": "negative_current_balance_normalized",
                            "group": group_label,
                            "current_token": source_row["current_token"],
                        }
                    )
                category = source_row["current_token_category"]
                if category is None:
                    category = "Uncategorized"
                    uncategorized_count += 1
                    warnings.append(
                        {
                            "code": "uncategorized_destination",
                            "group": group_label,
                            "current_token": source_row["current_token"],
                        }
                    )
                destinations.append(
                    {
                        "current_token": source_row["current_token"],
                        "category": category,
                        "balance": balance,
                    }
                )

            total_current = sum(
                (destination["balance"] for destination in destinations),
                Decimal(0),
            )
            campaign_supported = max(total_current - previous_balance, Decimal(0))
            final_attributable = min(referral_cap, campaign_supported)
            exited_balance = max(referral_cap - final_attributable, Decimal(0))
            rule, allocations, ranked_destinations = _allocation_plan(
                destinations,
                final_attributable,
            )
            if sum(allocations.values(), Decimal(0)) != final_attributable:
                raise KyberSwapAttributionError(
                    f"group {group_label} allocation does not reconcile"
                )
            total_referral_usd += referral_cap
            total_exited_usd += exited_balance

            for allocation_rank, destination in enumerate(ranked_destinations, start=1):
                current_balance = destination["balance"]
                attributed_balance = allocations[destination["current_token"]]
                if attributed_balance < 0 or attributed_balance > current_balance:
                    raise KyberSwapAttributionError(
                        f"group {group_label} active destination allocation is out of bounds"
                    )
                unattributed_balance = max(
                    current_balance - attributed_balance,
                    Decimal(0),
                )
                total_active_attributed_usd += attributed_balance
                enriched_rows.append(
                    {
                        "day": day,
                        "address": address,
                        "strategy_symbol": strategy_symbol,
                        "base_asset": base_asset,
                        "depositor_type": depositor_type,
                        "referral_balance": _decimal_text(referral_cap),
                        "previous_balance": _decimal_text(previous_balance),
                        "total_current_balance": _decimal_text(total_current),
                        "campaign_supported_balance": _decimal_text(campaign_supported),
                        "final_attributable_balance": _decimal_text(final_attributable),
                        "exited_balance": _decimal_text(exited_balance),
                        "current_token": destination["current_token"],
                        "current_token_category": destination["category"],
                        "current_balance": _decimal_text(current_balance),
                        "attributed_balance": _decimal_text(attributed_balance),
                        "unattributed_balance": _decimal_text(unattributed_balance),
                        "destination_status": "active",
                        "allocation_rank": allocation_rank,
                        "allocation_rule": rule,
                        "methodology_id": METHODOLOGY_ID,
                        "source_query_id": source_query_id,
                        "source_execution_id": source_execution_id,
                        "source_last_updated": source_last_updated_text,
                        "generated_at": generated_at_text,
                    }
                )

            if exited_balance > 0:
                enriched_rows.append(
                    {
                        "day": day,
                        "address": address,
                        "strategy_symbol": strategy_symbol,
                        "base_asset": base_asset,
                        "depositor_type": depositor_type,
                        "referral_balance": _decimal_text(referral_cap),
                        "previous_balance": _decimal_text(previous_balance),
                        "total_current_balance": _decimal_text(total_current),
                        "campaign_supported_balance": _decimal_text(campaign_supported),
                        "final_attributable_balance": _decimal_text(final_attributable),
                        "exited_balance": _decimal_text(exited_balance),
                        "current_token": "Exited",
                        "current_token_category": "Exited",
                        "current_balance": "0",
                        "attributed_balance": _decimal_text(exited_balance),
                        "unattributed_balance": "0",
                        "destination_status": "exited",
                        "allocation_rank": len(ranked_destinations) + 1,
                        "allocation_rule": rule,
                        "methodology_id": METHODOLOGY_ID,
                        "source_query_id": source_query_id,
                        "source_execution_id": source_execution_id,
                        "source_last_updated": source_last_updated_text,
                        "generated_at": generated_at_text,
                    }
                )

            active_total = sum(allocations.values(), Decimal(0))
            if active_total + exited_balance != referral_cap:
                raise KyberSwapAttributionError(
                    f"group {group_label} active plus exited balance does not equal referral cap"
                )

    # Preserve exact reconciliation even for values far beyond Decimal's default
    # 28-digit context.  The allocations above are evaluated at the same high
    # precision, so the final conservation check must be as well.
    with localcontext() as reconciliation_context:
        reconciliation_context.prec = 256
        if total_referral_usd != total_active_attributed_usd + total_exited_usd:
            raise KyberSwapAttributionError("USD attribution totals do not reconcile")
    unique_addresses = {row["address"].lower() for row in parsed_rows}
    new_addresses = {
        row["address"].lower()
        for row in parsed_rows
        if row["depositor_type"] == "New Depositor"
    }
    existing_addresses = {
        row["address"].lower()
        for row in parsed_rows
        if row["depositor_type"] == "Existing Depositor"
    }
    past_addresses = {
        row["address"].lower()
        for row in parsed_rows
        if row["depositor_type"] == "Past Depositor"
    }
    unclassified_addresses = (
        unique_addresses - new_addresses - existing_addresses - past_addresses
    )
    summary = {
        "source_rows": len(parsed_rows),
        "unique_addresses": len(unique_addresses),
        "unique_address_product_groups": len(groups),
        "new_depositors": len(new_addresses),
        "existing_depositors": len(existing_addresses),
        "past_depositors": len(past_addresses),
        "unclassified_depositors": len(unclassified_addresses),
        "depositor_types": observed_depositor_types,
        "total_referral_value_usd": _decimal_text(total_referral_usd),
        "total_attributed_value_usd": _decimal_text(total_active_attributed_usd),
        "total_exited_value_usd": _decimal_text(total_exited_usd),
        "uncategorized_destination_count": uncategorized_count,
        "invalid_group_count": 0,
        "source_last_updated": source_last_updated_text,
        "reconciliation_delta_usd": "0",
        "reconciliation_tolerance_usd": "0",
    }
    enriched_rows.sort(
        key=lambda row: (
            row["day"],
            row["address"].lower(),
            row["strategy_symbol"],
            int(row["allocation_rank"]),
            row["current_token"],
        )
    )
    return EnrichmentResult(
        rows=enriched_rows,
        summary=summary,
        warnings=warnings,
        source_last_updated=source_last_updated_text,
    )


__all__ = [
    "ENRICHED_COLUMNS",
    "EnrichmentResult",
    "KyberSwapAttributionError",
    "METHODOLOGY_ID",
    "METHODOLOGY_VERSION",
    "SOURCE_QUERY_ID",
    "SOURCE_REQUIRED_COLUMNS",
    "enrich_kyberswap_attributed_holdings",
]
