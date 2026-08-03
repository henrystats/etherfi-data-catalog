from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
import re
from typing import Iterable, Mapping, Sequence


REFERRAL_DEPOSITS_QUERY_ID = 8204345
ETHERFI_ACTIVITY_QUERY_ID = 8204373
ATTRIBUTED_HOLDINGS_QUERY_ID = 8199058

REFERRAL_DEPOSITS_TRANSFORMATION_ID = "kyberswap_referral_deposits"
ETHERFI_ACTIVITY_TRANSFORMATION_ID = "kyberswap_etherfi_activity"
DERIVED_ARTIFACT_ID = "kyberswap_depositor_intelligence"
DERIVED_ARTIFACT_FILE = "kyberswap_depositor_intelligence.json"
METHODOLOGY_ID = "kyberswap_depositor_intelligence_v1"
METHODOLOGY_VERSION = "1.0.0"

REFERRAL_DEPOSITS_SOURCE_COLUMNS = (
    "tx_hash",
    "address",
    "blockchain",
    "block_time",
    "strategy_symbol",
    "amount_usd",
)
ETHERFI_ACTIVITY_SOURCE_COLUMNS = (
    "event",
    "address",
    "project",
    "blockchain",
    "tx_hash",
    "block_time",
    "amount_usd",
    "token_symbol",
    "label",
)
PROVENANCE_COLUMNS = (
    "source_query_id",
    "source_execution_id",
    "source_last_updated",
    "generated_at",
)
REFERRAL_DEPOSITS_OUTPUT_COLUMNS = (
    *REFERRAL_DEPOSITS_SOURCE_COLUMNS,
    *PROVENANCE_COLUMNS,
)
ETHERFI_ACTIVITY_OUTPUT_COLUMNS = (
    *ETHERFI_ACTIVITY_SOURCE_COLUMNS,
    *PROVENANCE_COLUMNS,
)

ATTRIBUTED_HOLDINGS_REQUIRED_COLUMNS = (
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

WALLET_COLUMNS = (
    "address",
    "depositor_type",
    "source_day",
    "total_referral_deposits_usd",
    "attributed_tvl_usd",
    "exited_balance_usd",
    "retention_rate",
    "products_deposited",
    "num_products_deposited",
    "current_tokens",
    "current_token_categories",
    "num_current_locations",
    "latest_referral_deposit_time",
    "latest_referral_deposit_product",
    "latest_referral_deposit_usd",
    "latest_activity_time",
    "latest_activity_event",
    "latest_activity_project",
    "latest_activity_label",
    "latest_activity_amount_usd",
    "positions",
    "referral_deposits",
    "activity",
)

SUPPORTED_BLOCKCHAINS = frozenset(
    {
        "arbitrum",
        "avalanche",
        "base",
        "bnb",
        "ethereum",
        "linea",
        "optimism",
        "polygon",
        "scroll",
    }
)
DEPOSITOR_TYPES = frozenset(
    {"New Depositor", "Existing Depositor", "Past Depositor"}
)
IMMATERIAL_ORPHAN_DEPOSIT_USD = Decimal("0.005")
EVM_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")
EVM_TRANSACTION_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")
SAFE_TEXT_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")


class KyberSwapDepositorIntelligenceError(ValueError):
    """A depositor-intelligence source or derived result is inconsistent."""


@dataclass(frozen=True)
class SourcePreparationResult:
    rows: list[dict]
    columns: list[str]
    summary: dict
    warnings: list[dict]
    source_last_updated: str


@dataclass(frozen=True)
class DepositorIntelligenceResult:
    payload: dict
    summary: dict
    warnings: list[dict]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


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
    row_index: int | None = None,
    allow_naive_utc: bool = False,
) -> datetime:
    context = f"row {row_index} field {field}" if row_index is not None else field
    if not isinstance(value, str) or not value.strip():
        raise KyberSwapDepositorIntelligenceError(
            f"{context} must be a non-empty timestamp"
        )
    try:
        parsed = datetime.fromisoformat(_normalized_datetime_text(value))
    except ValueError as exc:
        raise KyberSwapDepositorIntelligenceError(
            f"{context} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if not allow_naive_utc:
            raise KyberSwapDepositorIntelligenceError(
                f"{context} must include a timezone"
            )
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_text(value: object, *, field: str, row_index: int) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or not SAFE_TEXT_PATTERN.fullmatch(value)
    ):
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be a non-empty trimmed string"
        )
    return value


def _address(value: object, *, field: str, row_index: int) -> str:
    text = _required_text(value, field=field, row_index=row_index)
    if not EVM_ADDRESS_PATTERN.fullmatch(text):
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be an EVM address"
        )
    return text.lower()


def _transaction(value: object, *, field: str, row_index: int) -> str:
    text = _required_text(value, field=field, row_index=row_index)
    if not EVM_TRANSACTION_PATTERN.fullmatch(text):
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be an EVM transaction hash"
        )
    return text.lower()


def _blockchain(value: object, *, row_index: int) -> str:
    text = _required_text(value, field="blockchain", row_index=row_index).lower()
    if text not in SUPPORTED_BLOCKCHAINS:
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field blockchain has unsupported value {text}"
        )
    return text


def _decimal(
    value: object,
    *,
    field: str,
    row_index: int,
    non_negative: bool,
) -> Decimal:
    if value is None or isinstance(value, bool):
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be numeric"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be finite"
        )
    if not isinstance(value, (str, int, float, Decimal)):
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be numeric"
        )
    if isinstance(value, str) and not value.strip():
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be numeric"
        )
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be numeric"
        ) from exc
    if not parsed.is_finite():
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must be finite"
        )
    if non_negative and parsed < 0:
        raise KyberSwapDepositorIntelligenceError(
            f"row {row_index} field {field} must not be negative"
        )
    return parsed


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _sum(values: Iterable[Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = 256
        return sum(values, Decimal(0))


def _validate_source_schema(
    rows: Iterable[Mapping[str, object]],
    *,
    expected_columns: Sequence[str],
    source_columns: Sequence[str],
    query_id: int,
) -> list[Mapping[str, object]]:
    expected = tuple(expected_columns)
    if source_columns:
        if any(not isinstance(column, str) or not column for column in source_columns):
            raise KyberSwapDepositorIntelligenceError(
                "source_columns must contain non-empty strings"
            )
        if len(source_columns) != len(set(source_columns)):
            raise KyberSwapDepositorIntelligenceError(
                "source_columns must not contain duplicates"
            )
        missing = sorted(set(expected) - set(source_columns))
        unexpected = sorted(set(source_columns) - set(expected))
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise KyberSwapDepositorIntelligenceError(
                f"query {query_id} latest-result schema mismatch: "
                + "; ".join(details)
            )

    validated: list[Mapping[str, object]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise KyberSwapDepositorIntelligenceError(
                f"row {row_index} must be an object"
            )
        missing = sorted(set(expected) - set(row))
        unexpected = sorted(set(row) - set(expected))
        if missing or unexpected:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise KyberSwapDepositorIntelligenceError(
                f"row {row_index} schema mismatch: {'; '.join(details)}"
            )
        validated.append(row)
    if not validated:
        raise KyberSwapDepositorIntelligenceError(
            f"query {query_id} returned no source rows"
        )
    return validated


def _validated_provenance(
    *,
    source_query_id: int,
    expected_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
) -> tuple[str, str]:
    if source_query_id != expected_query_id:
        raise KyberSwapDepositorIntelligenceError(
            f"transformation requires source query {expected_query_id}"
        )
    if not isinstance(source_execution_id, str) or not source_execution_id.strip():
        raise KyberSwapDepositorIntelligenceError(
            "source_execution_id must be a non-empty string"
        )
    source_updated = _iso_utc(
        _parse_timestamp(source_last_updated, field="source_last_updated")
    )
    generated = _iso_utc(_parse_timestamp(generated_at, field="generated_at"))
    return source_updated, generated


def prepare_kyberswap_referral_deposits(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> SourcePreparationResult:
    source_updated, generated = _validated_provenance(
        source_query_id=source_query_id,
        expected_query_id=REFERRAL_DEPOSITS_QUERY_ID,
        source_execution_id=source_execution_id,
        source_last_updated=source_last_updated,
        generated_at=generated_at,
    )
    source_rows = _validate_source_schema(
        rows,
        expected_columns=REFERRAL_DEPOSITS_SOURCE_COLUMNS,
        source_columns=source_columns,
        query_id=REFERRAL_DEPOSITS_QUERY_ID,
    )
    prepared_rows: list[dict] = []
    total = Decimal(0)
    for row_index, row in enumerate(source_rows):
        tx_hash = _transaction(row["tx_hash"], field="tx_hash", row_index=row_index)
        address = _address(row["address"], field="address", row_index=row_index)
        strategy = _required_text(
            row["strategy_symbol"], field="strategy_symbol", row_index=row_index
        )
        amount = _decimal(
            row["amount_usd"],
            field="amount_usd",
            row_index=row_index,
            non_negative=True,
        )
        total += amount
        prepared_rows.append(
            {
                "tx_hash": tx_hash,
                "address": address,
                "blockchain": _blockchain(row["blockchain"], row_index=row_index),
                "block_time": _iso_utc(
                    _parse_timestamp(
                        row["block_time"],
                        field="block_time",
                        row_index=row_index,
                        allow_naive_utc=True,
                    )
                ),
                "strategy_symbol": strategy,
                "amount_usd": _decimal_text(amount),
                "source_query_id": source_query_id,
                "source_execution_id": source_execution_id,
                "source_last_updated": source_updated,
                "generated_at": generated,
            }
        )
    prepared_rows.sort(
        key=lambda row: (
            _parse_timestamp(row["block_time"], field="block_time"),
            row["tx_hash"],
            row["address"],
            row["strategy_symbol"],
        ),
        reverse=True,
    )
    return SourcePreparationResult(
        rows=prepared_rows,
        columns=list(REFERRAL_DEPOSITS_OUTPUT_COLUMNS),
        summary={
            "source_rows": len(source_rows),
            "prepared_rows": len(prepared_rows),
            "unique_addresses": len({row["address"] for row in prepared_rows}),
            "total_amount_usd": _decimal_text(total),
            "source_last_updated": source_updated,
        },
        warnings=[],
        source_last_updated=source_updated,
    )


def prepare_kyberswap_etherfi_activity(
    rows: Iterable[Mapping[str, object]],
    *,
    source_query_id: int,
    source_execution_id: str,
    source_last_updated: str,
    generated_at: str,
    source_columns: Sequence[str] = (),
) -> SourcePreparationResult:
    source_updated, generated = _validated_provenance(
        source_query_id=source_query_id,
        expected_query_id=ETHERFI_ACTIVITY_QUERY_ID,
        source_execution_id=source_execution_id,
        source_last_updated=source_last_updated,
        generated_at=generated_at,
    )
    source_rows = _validate_source_schema(
        rows,
        expected_columns=ETHERFI_ACTIVITY_SOURCE_COLUMNS,
        source_columns=source_columns,
        query_id=ETHERFI_ACTIVITY_QUERY_ID,
    )
    prepared_rows: list[dict] = []
    net_amount = Decimal(0)
    negative_amount_count = 0
    for row_index, row in enumerate(source_rows):
        amount = _decimal(
            row["amount_usd"],
            field="amount_usd",
            row_index=row_index,
            non_negative=False,
        )
        negative_amount_count += int(amount < 0)
        net_amount += amount
        prepared_row = {
            "event": _required_text(row["event"], field="event", row_index=row_index),
            "address": _address(row["address"], field="address", row_index=row_index),
            "project": _required_text(
                row["project"], field="project", row_index=row_index
            ),
            "blockchain": _blockchain(row["blockchain"], row_index=row_index),
            "tx_hash": _transaction(
                row["tx_hash"], field="tx_hash", row_index=row_index
            ),
            "block_time": _iso_utc(
                _parse_timestamp(
                    row["block_time"],
                    field="block_time",
                    row_index=row_index,
                    allow_naive_utc=True,
                )
            ),
            "amount_usd": _decimal_text(amount),
            "token_symbol": _required_text(
                row["token_symbol"], field="token_symbol", row_index=row_index
            ),
            "label": _required_text(row["label"], field="label", row_index=row_index),
            "source_query_id": source_query_id,
            "source_execution_id": source_execution_id,
            "source_last_updated": source_updated,
            "generated_at": generated,
        }
        prepared_rows.append(prepared_row)
    prepared_rows.sort(
        key=lambda row: (
            _parse_timestamp(row["block_time"], field="block_time"),
            row["tx_hash"],
            row["address"],
            row["event"],
            row["project"],
            row["token_symbol"],
        ),
        reverse=True,
    )
    return SourcePreparationResult(
        rows=prepared_rows,
        columns=list(ETHERFI_ACTIVITY_OUTPUT_COLUMNS),
        summary={
            "source_rows": len(source_rows),
            "prepared_rows": len(prepared_rows),
            "unique_addresses": len({row["address"] for row in prepared_rows}),
            "negative_amount_rows": negative_amount_count,
            "net_amount_usd": _decimal_text(net_amount),
            "source_last_updated": source_updated,
        },
        warnings=[],
        source_last_updated=source_updated,
    )


def _validated_day(value: object, *, row_index: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KyberSwapDepositorIntelligenceError(
            f"holdings row {row_index} field day must be an ISO date"
        )
    text = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text).isoformat()
        parsed = _parse_timestamp(text, field="day", row_index=row_index)
    except (ValueError, KyberSwapDepositorIntelligenceError) as exc:
        raise KyberSwapDepositorIntelligenceError(
            f"holdings row {row_index} field day must be an ISO date"
        ) from exc
    return parsed.date().isoformat()


def _parsed_holdings_rows(
    rows: Iterable[Mapping[str, object]],
) -> tuple[list[dict], str]:
    parsed_rows: list[dict] = []
    source_execution_ids: set[str] = set()
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise KyberSwapDepositorIntelligenceError(
                f"holdings row {row_index} must be an object"
            )
        missing = sorted(set(ATTRIBUTED_HOLDINGS_REQUIRED_COLUMNS) - set(row))
        if missing:
            raise KyberSwapDepositorIntelligenceError(
                f"holdings row {row_index} is missing: {', '.join(missing)}"
            )
        query_id = row["source_query_id"]
        if query_id != ATTRIBUTED_HOLDINGS_QUERY_ID:
            raise KyberSwapDepositorIntelligenceError(
                f"holdings row {row_index} has unexpected source_query_id"
            )
        execution_id = _required_text(
            row["source_execution_id"],
            field="source_execution_id",
            row_index=row_index,
        )
        source_execution_ids.add(execution_id)
        destination_status = _required_text(
            row["destination_status"],
            field="destination_status",
            row_index=row_index,
        )
        if destination_status not in {"active", "exited"}:
            raise KyberSwapDepositorIntelligenceError(
                f"holdings row {row_index} has unsupported destination_status"
            )
        depositor_type = _required_text(
            row["depositor_type"],
            field="depositor_type",
            row_index=row_index,
        )
        parsed_rows.append(
            {
                "row_index": row_index,
                "row": dict(row),
                "day": _validated_day(row["day"], row_index=row_index),
                "address": _address(
                    row["address"], field="address", row_index=row_index
                ),
                "strategy_symbol": _required_text(
                    row["strategy_symbol"],
                    field="strategy_symbol",
                    row_index=row_index,
                ),
                "depositor_type": depositor_type,
                "referral_balance": _decimal(
                    row["referral_balance"],
                    field="referral_balance",
                    row_index=row_index,
                    non_negative=True,
                ),
                "exited_balance": _decimal(
                    row["exited_balance"],
                    field="exited_balance",
                    row_index=row_index,
                    non_negative=True,
                ),
                "attributed_balance": _decimal(
                    row["attributed_balance"],
                    field="attributed_balance",
                    row_index=row_index,
                    non_negative=True,
                ),
                "current_balance": _decimal(
                    row["current_balance"],
                    field="current_balance",
                    row_index=row_index,
                    non_negative=True,
                ),
                "current_token": _required_text(
                    row["current_token"],
                    field="current_token",
                    row_index=row_index,
                ),
                "current_token_category": _required_text(
                    row["current_token_category"],
                    field="current_token_category",
                    row_index=row_index,
                ),
                "destination_status": destination_status,
                "source_last_updated": _iso_utc(
                    _parse_timestamp(
                        row["source_last_updated"],
                        field="source_last_updated",
                        row_index=row_index,
                    )
                ),
            }
        )
    if not parsed_rows:
        raise KyberSwapDepositorIntelligenceError(
            "attributed holdings contains no rows"
        )
    if len(source_execution_ids) != 1:
        raise KyberSwapDepositorIntelligenceError(
            "attributed holdings mixes source execution IDs"
        )
    days = {row["day"] for row in parsed_rows}
    if len(days) != 1:
        raise KyberSwapDepositorIntelligenceError(
            "attributed holdings must contain one source snapshot day"
        )
    return parsed_rows, next(iter(source_execution_ids))


def _source_execution_metadata(
    *,
    query_id: int,
    rows: Sequence[Mapping[str, object]],
    expected_execution_id: str | None = None,
) -> dict:
    execution_ids = {str(row.get("source_execution_id") or "") for row in rows}
    updated_values = {str(row.get("source_last_updated") or "") for row in rows}
    if len(execution_ids) != 1 or "" in execution_ids:
        raise KyberSwapDepositorIntelligenceError(
            f"query {query_id} rows mix source execution IDs"
        )
    execution_id = next(iter(execution_ids))
    if expected_execution_id is not None and execution_id != expected_execution_id:
        raise KyberSwapDepositorIntelligenceError(
            f"query {query_id} execution metadata does not match its rows"
        )
    if len(updated_values) != 1 or "" in updated_values:
        raise KyberSwapDepositorIntelligenceError(
            f"query {query_id} rows mix source completion timestamps"
        )
    completed_at = _iso_utc(
        _parse_timestamp(
            next(iter(updated_values)),
            field=f"query {query_id} source_last_updated",
        )
    )
    return {
        "execution_id": execution_id,
        "execution_finished_at": completed_at,
    }


def _latest_row(rows: Sequence[dict]) -> dict | None:
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            _parse_timestamp(row["block_time"], field="block_time"),
            row["tx_hash"],
            str(row.get("event") or ""),
            str(row.get("project") or ""),
            str(row.get("strategy_symbol") or ""),
        ),
    )


def _concentration(wallets: Sequence[dict], *, field: str) -> dict:
    ranked = sorted(
        (
            (wallet["address"], Decimal(str(wallet[field])))
            for wallet in wallets
        ),
        key=lambda item: (-item[1], item[0]),
    )
    total = _sum(value for _, value in ranked)
    tiers = []
    for top_n in (1, 5, 10, 25):
        value = _sum(item[1] for item in ranked[:top_n])
        with localcontext() as context:
            context.prec = 78
            share = Decimal(0) if total == 0 else value / total
        tiers.append(
            {
                "top_n": top_n,
                "value_usd": _decimal_text(value),
                "share": _decimal_text(share),
            }
        )
    return {
        "total_usd": _decimal_text(total),
        "tiers": tiers,
        "ranked_addresses": [address for address, _ in ranked],
    }


def build_kyberswap_depositor_intelligence(
    attributed_holdings_rows: Iterable[Mapping[str, object]],
    referral_deposit_rows: Iterable[Mapping[str, object]],
    activity_rows: Iterable[Mapping[str, object]],
    *,
    source_execution_ids: Mapping[int, str] | None = None,
) -> DepositorIntelligenceResult:
    """Build one deterministic wallet index from the three validated sources."""
    parsed_holdings, holdings_execution_id = _parsed_holdings_rows(
        attributed_holdings_rows
    )
    deposits = [dict(row) for row in referral_deposit_rows]
    activities = [dict(row) for row in activity_rows]
    if not deposits:
        raise KyberSwapDepositorIntelligenceError(
            "referral deposits contains no rows"
        )
    if not activities:
        raise KyberSwapDepositorIntelligenceError("activity contains no rows")

    expected_executions = dict(source_execution_ids or {})
    source_executions = {
        ATTRIBUTED_HOLDINGS_QUERY_ID: _source_execution_metadata(
            query_id=ATTRIBUTED_HOLDINGS_QUERY_ID,
            rows=[item["row"] for item in parsed_holdings],
            expected_execution_id=expected_executions.get(
                ATTRIBUTED_HOLDINGS_QUERY_ID,
                holdings_execution_id,
            ),
        ),
        REFERRAL_DEPOSITS_QUERY_ID: _source_execution_metadata(
            query_id=REFERRAL_DEPOSITS_QUERY_ID,
            rows=deposits,
            expected_execution_id=expected_executions.get(
                REFERRAL_DEPOSITS_QUERY_ID
            ),
        ),
        ETHERFI_ACTIVITY_QUERY_ID: _source_execution_metadata(
            query_id=ETHERFI_ACTIVITY_QUERY_ID,
            rows=activities,
            expected_execution_id=expected_executions.get(ETHERFI_ACTIVITY_QUERY_ID),
        ),
    }

    holdings_by_address: dict[str, list[dict]] = {}
    deposits_by_address: dict[str, list[dict]] = {}
    activity_by_address: dict[str, list[dict]] = {}
    for row in parsed_holdings:
        holdings_by_address.setdefault(row["address"], []).append(row)
    for row_index, row in enumerate(deposits):
        address = _address(row.get("address"), field="address", row_index=row_index)
        if row.get("source_query_id") != REFERRAL_DEPOSITS_QUERY_ID:
            raise KyberSwapDepositorIntelligenceError(
                f"referral deposit row {row_index} has unexpected source_query_id"
            )
        _decimal(
            row.get("amount_usd"),
            field="amount_usd",
            row_index=row_index,
            non_negative=True,
        )
        _parse_timestamp(
            row.get("block_time"), field="block_time", row_index=row_index
        )
        deposits_by_address.setdefault(address, []).append(row)
    for row_index, row in enumerate(activities):
        address = _address(row.get("address"), field="address", row_index=row_index)
        if row.get("source_query_id") != ETHERFI_ACTIVITY_QUERY_ID:
            raise KyberSwapDepositorIntelligenceError(
                f"activity row {row_index} has unexpected source_query_id"
            )
        _decimal(
            row.get("amount_usd"),
            field="amount_usd",
            row_index=row_index,
            non_negative=False,
        )
        _parse_timestamp(
            row.get("block_time"), field="block_time", row_index=row_index
        )
        activity_by_address.setdefault(address, []).append(row)

    holdings_addresses = set(holdings_by_address)
    orphan_deposit_addresses = sorted(set(deposits_by_address) - holdings_addresses)
    orphan_activity_addresses = sorted(set(activity_by_address) - holdings_addresses)
    orphan_deposit_rows = [
        row
        for address in orphan_deposit_addresses
        for row in deposits_by_address[address]
    ]
    orphan_deposit_total = _sum(
        _decimal(
            row["amount_usd"],
            field="amount_usd",
            row_index=row_index,
            non_negative=True,
        )
        for row_index, row in enumerate(orphan_deposit_rows)
    )
    material_orphan_deposits = (
        orphan_deposit_total >= IMMATERIAL_ORPHAN_DEPOSIT_USD
    )
    if material_orphan_deposits or orphan_activity_addresses:
        details = []
        if material_orphan_deposits:
            details.append(
                f"{len(orphan_deposit_addresses)} referral-deposit wallet(s)"
            )
        if orphan_activity_addresses:
            details.append(f"{len(orphan_activity_addresses)} activity wallet(s)")
        raise KyberSwapDepositorIntelligenceError(
            "cross-source wallet coverage does not reconcile: " + ", ".join(details)
        )

    wallets: list[dict] = []
    global_group_count = 0
    global_referral = Decimal(0)
    global_active = Decimal(0)
    global_exited = Decimal(0)
    for address in sorted(holdings_by_address):
        wallet_rows = holdings_by_address[address]
        depositor_types = {row["depositor_type"] for row in wallet_rows}
        days = {row["day"] for row in wallet_rows}
        if len(depositor_types) != 1 or len(days) != 1:
            raise KyberSwapDepositorIntelligenceError(
                f"wallet {address} has conflicting holdings metadata"
            )

        groups: dict[tuple[str, str], list[dict]] = {}
        for row in wallet_rows:
            groups.setdefault((row["day"], row["strategy_symbol"]), []).append(row)
        wallet_referral = Decimal(0)
        wallet_active = Decimal(0)
        wallet_exited = Decimal(0)
        products: set[str] = set()
        current_tokens: set[str] = set()
        current_categories: set[str] = set()
        positions: list[dict] = []
        for (day, strategy), group in sorted(groups.items()):
            global_group_count += 1
            products.add(strategy)
            referral_values = {row["referral_balance"] for row in group}
            exited_values = {row["exited_balance"] for row in group}
            if len(referral_values) != 1 or len(exited_values) != 1:
                raise KyberSwapDepositorIntelligenceError(
                    f"wallet {address} product {strategy} repeats conflicting balances"
                )
            referral = next(iter(referral_values))
            exited = next(iter(exited_values))
            active = _sum(
                row["attributed_balance"]
                for row in group
                if row["destination_status"] == "active"
            )
            exited_rows = [
                row for row in group if row["destination_status"] == "exited"
            ]
            if len(exited_rows) != int(exited > 0):
                raise KyberSwapDepositorIntelligenceError(
                    f"wallet {address} product {strategy} has invalid Exited rows"
                )
            if exited_rows and exited_rows[0]["attributed_balance"] != exited:
                raise KyberSwapDepositorIntelligenceError(
                    f"wallet {address} product {strategy} Exited value does not reconcile"
                )
            if active + exited != referral:
                raise KyberSwapDepositorIntelligenceError(
                    f"wallet {address} product {strategy} attribution does not reconcile"
                )
            wallet_referral += referral
            wallet_active += active
            wallet_exited += exited
            for row in group:
                if (
                    row["destination_status"] == "active"
                    and row["attributed_balance"] > 0
                ):
                    current_tokens.add(row["current_token"])
                    current_categories.add(row["current_token_category"])
                position = dict(row["row"])
                position["address"] = address
                position["exited_balance"] = (
                    _decimal_text(exited)
                    if row["destination_status"] == "exited"
                    else "0"
                )
                position["exited_balance_usd"] = position["exited_balance"]
                positions.append(position)
        if wallet_referral != wallet_active + wallet_exited:
            raise KyberSwapDepositorIntelligenceError(
                f"wallet {address} totals do not reconcile"
            )
        global_referral += wallet_referral
        global_active += wallet_active
        global_exited += wallet_exited

        positions.sort(
            key=lambda row: (
                row["day"],
                row["strategy_symbol"],
                int(row["allocation_rank"]),
                row["current_token"],
            )
        )
        wallet_deposits = sorted(
            deposits_by_address.get(address, []),
            key=lambda row: (
                _parse_timestamp(row["block_time"], field="block_time"),
                row["tx_hash"],
                row["strategy_symbol"],
            ),
            reverse=True,
        )
        wallet_activity = sorted(
            activity_by_address.get(address, []),
            key=lambda row: (
                _parse_timestamp(row["block_time"], field="block_time"),
                row["tx_hash"],
                row["event"],
                row["project"],
            ),
            reverse=True,
        )
        latest_deposit = _latest_row(wallet_deposits)
        latest_activity = _latest_row(wallet_activity)
        with localcontext() as context:
            context.prec = 78
            retention = (
                Decimal(0)
                if wallet_referral == 0
                else wallet_active / wallet_referral
            )
        wallets.append(
            {
                "address": address,
                "depositor_type": next(iter(depositor_types)),
                "source_day": next(iter(days)),
                "total_referral_deposits_usd": _decimal_text(wallet_referral),
                "attributed_tvl_usd": _decimal_text(wallet_active),
                "exited_balance_usd": _decimal_text(wallet_exited),
                "retention_rate": _decimal_text(retention),
                "products_deposited": sorted(products, key=str.casefold),
                "num_products_deposited": len(products),
                "current_tokens": sorted(current_tokens, key=str.casefold),
                "current_token_categories": sorted(
                    current_categories, key=str.casefold
                ),
                "num_current_locations": len(current_tokens),
                "latest_referral_deposit_time": (
                    latest_deposit["block_time"] if latest_deposit else None
                ),
                "latest_referral_deposit_product": (
                    latest_deposit["strategy_symbol"] if latest_deposit else None
                ),
                "latest_referral_deposit_usd": (
                    latest_deposit["amount_usd"] if latest_deposit else None
                ),
                "latest_activity_time": (
                    latest_activity["block_time"] if latest_activity else None
                ),
                "latest_activity_event": (
                    latest_activity["event"] if latest_activity else None
                ),
                "latest_activity_project": (
                    latest_activity["project"] if latest_activity else None
                ),
                "latest_activity_label": (
                    latest_activity["label"] if latest_activity else None
                ),
                "latest_activity_amount_usd": (
                    latest_activity["amount_usd"] if latest_activity else None
                ),
                "positions": positions,
                "referral_deposits": wallet_deposits,
                "activity": wallet_activity,
            }
        )

    if global_referral != global_active + global_exited:
        raise KyberSwapDepositorIntelligenceError(
            "global wallet totals do not reconcile"
        )
    completion_times = [
        _parse_timestamp(
            item["execution_finished_at"],
            field=f"query {query_id} execution_finished_at",
        )
        for query_id, item in source_executions.items()
    ]
    generated_at = _iso_utc(max(completion_times))
    source_execution_payload = {
        str(query_id): value
        for query_id, value in sorted(source_executions.items())
    }
    payload = {
        "schema_version": 1,
        "artifact_id": DERIVED_ARTIFACT_ID,
        "data_source": DERIVED_ARTIFACT_ID,
        "generated_at": generated_at,
        "source_query_ids": sorted(source_executions),
        "source_executions": source_execution_payload,
        "row_count": len(wallets),
        "columns": list(WALLET_COLUMNS),
        "wallets": wallets,
        "wallet_index": {
            wallet["address"]: index for index, wallet in enumerate(wallets)
        },
        "concentration": {
            "referral_deposits": _concentration(
                wallets, field="total_referral_deposits_usd"
            ),
            "attributed_tvl": _concentration(wallets, field="attributed_tvl_usd"),
        },
    }
    payload["checksum"] = _sha256_json(payload)
    unexpected_depositor_types = sorted(
        {
            row["depositor_type"]
            for row in parsed_holdings
            if row["depositor_type"] not in DEPOSITOR_TYPES
        },
        key=str.casefold,
    )
    return DepositorIntelligenceResult(
        payload=payload,
        summary={
            "wallet_count": len(wallets),
            "wallet_product_groups": global_group_count,
            "referral_deposit_event_count": len(deposits),
            "activity_event_count": len(activities),
            "total_referral_deposits_usd": _decimal_text(global_referral),
            "attributed_tvl_usd": _decimal_text(global_active),
            "exited_balance_usd": _decimal_text(global_exited),
            "reconciliation_delta_usd": "0",
        },
        warnings=[
            *(
                [
                    {
                        "code": "immaterial_orphan_referral_deposit",
                        "wallet_count": len(orphan_deposit_addresses),
                        "event_count": len(orphan_deposit_rows),
                        "amount_usd": _decimal_text(orphan_deposit_total),
                        "threshold_usd": _decimal_text(
                            IMMATERIAL_ORPHAN_DEPOSIT_USD
                        ),
                        "message": (
                            "Sub-cent referral-deposit events without a matching "
                            "attributed-holdings wallet were excluded from wallet "
                            "summaries and retained in the validated source artifact"
                        ),
                    }
                ]
                if orphan_deposit_addresses
                else []
            ),
            *[
                {
                    "code": "unexpected_depositor_type",
                    "depositor_type": depositor_type,
                    "message": (
                        f"Unexpected depositor type {depositor_type} was retained "
                        "from the validated attribution source"
                    ),
                }
                for depositor_type in unexpected_depositor_types
            ],
        ],
    )


def validate_kyberswap_depositor_intelligence(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence must be an object"
        )
    if payload.get("schema_version") != 1:
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence schema_version must be 1"
        )
    if payload.get("artifact_id") != DERIVED_ARTIFACT_ID:
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence artifact_id does not match"
        )
    if payload.get("data_source") != DERIVED_ARTIFACT_ID:
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence data_source does not match"
        )
    if payload.get("source_query_ids") != sorted(
        {
            ATTRIBUTED_HOLDINGS_QUERY_ID,
            REFERRAL_DEPOSITS_QUERY_ID,
            ETHERFI_ACTIVITY_QUERY_ID,
        }
    ):
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence source query IDs do not match"
        )
    source_executions = payload.get("source_executions")
    expected_execution_keys = {
        str(ATTRIBUTED_HOLDINGS_QUERY_ID),
        str(REFERRAL_DEPOSITS_QUERY_ID),
        str(ETHERFI_ACTIVITY_QUERY_ID),
    }
    if not isinstance(source_executions, dict) or set(source_executions) != (
        expected_execution_keys
    ):
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence source_executions do not match"
        )
    for query_id, source in source_executions.items():
        if (
            not isinstance(source, dict)
            or set(source) != {"execution_id", "execution_finished_at"}
            or not isinstance(source.get("execution_id"), str)
            or not source["execution_id"]
        ):
            raise KyberSwapDepositorIntelligenceError(
                f"derived query {query_id} execution metadata is malformed"
            )
        _parse_timestamp(
            source["execution_finished_at"],
            field=f"query {query_id} execution_finished_at",
        )
    if payload.get("columns") != list(WALLET_COLUMNS):
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence columns do not match"
        )
    wallets = payload.get("wallets")
    wallet_index = payload.get("wallet_index")
    if not isinstance(wallets, list) or not isinstance(wallet_index, dict):
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence wallet collections are malformed"
        )
    if payload.get("row_count") != len(wallets):
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence row_count does not match"
        )
    addresses: list[str] = []
    for row_index, wallet in enumerate(wallets):
        if not isinstance(wallet, dict):
            raise KyberSwapDepositorIntelligenceError(
                f"derived wallet {row_index} must be an object"
            )
        missing = sorted(set(WALLET_COLUMNS) - set(wallet))
        unexpected = sorted(set(wallet) - set(WALLET_COLUMNS))
        if missing or unexpected:
            raise KyberSwapDepositorIntelligenceError(
                f"derived wallet {row_index} columns do not match"
            )
        address = _address(
            wallet["address"], field="address", row_index=row_index
        )
        if address != wallet["address"]:
            raise KyberSwapDepositorIntelligenceError(
                f"derived wallet {row_index} address must be lowercase"
            )
        addresses.append(address)
    if addresses != sorted(addresses) or len(addresses) != len(set(addresses)):
        raise KyberSwapDepositorIntelligenceError(
            "derived wallet addresses must be unique and sorted"
        )
    expected_index = {address: index for index, address in enumerate(addresses)}
    if wallet_index != expected_index:
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence wallet_index does not match wallets"
        )
    concentration = payload.get("concentration")
    if not isinstance(concentration, dict) or set(concentration) != {
        "referral_deposits",
        "attributed_tvl",
    }:
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence concentration is malformed"
        )
    for name, field in (
        ("referral_deposits", "total_referral_deposits_usd"),
        ("attributed_tvl", "attributed_tvl_usd"),
    ):
        expected = _concentration(wallets, field=field)
        if concentration.get(name) != expected:
            raise KyberSwapDepositorIntelligenceError(
                f"derived depositor intelligence {name} concentration does not reconcile"
            )
    expected_checksum = payload.get("checksum")
    core = dict(payload)
    core.pop("checksum", None)
    if expected_checksum != _sha256_json(core):
        raise KyberSwapDepositorIntelligenceError(
            "derived depositor intelligence checksum does not match"
        )
    _parse_timestamp(payload.get("generated_at"), field="generated_at")
    return dict(payload)


__all__ = [
    "ATTRIBUTED_HOLDINGS_QUERY_ID",
    "DERIVED_ARTIFACT_FILE",
    "DERIVED_ARTIFACT_ID",
    "DepositorIntelligenceResult",
    "ETHERFI_ACTIVITY_OUTPUT_COLUMNS",
    "ETHERFI_ACTIVITY_QUERY_ID",
    "ETHERFI_ACTIVITY_SOURCE_COLUMNS",
    "ETHERFI_ACTIVITY_TRANSFORMATION_ID",
    "KyberSwapDepositorIntelligenceError",
    "METHODOLOGY_ID",
    "METHODOLOGY_VERSION",
    "REFERRAL_DEPOSITS_OUTPUT_COLUMNS",
    "REFERRAL_DEPOSITS_QUERY_ID",
    "REFERRAL_DEPOSITS_SOURCE_COLUMNS",
    "REFERRAL_DEPOSITS_TRANSFORMATION_ID",
    "SUPPORTED_BLOCKCHAINS",
    "SourcePreparationResult",
    "WALLET_COLUMNS",
    "build_kyberswap_depositor_intelligence",
    "prepare_kyberswap_etherfi_activity",
    "prepare_kyberswap_referral_deposits",
    "validate_kyberswap_depositor_intelligence",
]
