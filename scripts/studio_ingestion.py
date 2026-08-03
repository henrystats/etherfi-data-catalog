from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from enum import Enum
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Callable, Iterator, Mapping, Protocol
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from uuid import uuid4

import yaml

try:
    from scripts.studio import (
        ROOT,
        STUDIO_DASHBOARDS_PATH,
        STUDIO_DATA_DIR,
        STUDIO_METRICS_PATH,
        build_studio_query_contracts,
        normalize_studio_registry,
        validate_studio_generated_manifest,
        validate_studio_query_result,
        validate_studio_registry,
    )
    from scripts.enrich_kyberswap_attributed_holdings import (
        ENRICHED_COLUMNS as KYBERSWAP_ENRICHED_COLUMNS,
        KyberSwapAttributionError,
        enrich_kyberswap_attributed_holdings,
    )
    from scripts.prepare_kyberswap_campaign_summary import (
        TRANSFORMATION_ID as KYBERSWAP_SUMMARY_TRANSFORMATION_ID,
        KyberSwapCampaignSummaryError,
        prepare_kyberswap_campaign_summary,
    )
    from scripts.prepare_kyberswap_depositor_intelligence import (
        ATTRIBUTED_HOLDINGS_QUERY_ID as KYBERSWAP_INTELLIGENCE_HOLDINGS_QUERY_ID,
        DERIVED_ARTIFACT_FILE as KYBERSWAP_INTELLIGENCE_FILE,
        DERIVED_ARTIFACT_ID as KYBERSWAP_INTELLIGENCE_ID,
        ETHERFI_ACTIVITY_OUTPUT_COLUMNS as KYBERSWAP_ACTIVITY_COLUMNS,
        ETHERFI_ACTIVITY_QUERY_ID as KYBERSWAP_ACTIVITY_QUERY_ID,
        ETHERFI_ACTIVITY_TRANSFORMATION_ID as KYBERSWAP_ACTIVITY_TRANSFORMATION_ID,
        METHODOLOGY_ID as KYBERSWAP_INTELLIGENCE_METHODOLOGY_ID,
        METHODOLOGY_VERSION as KYBERSWAP_INTELLIGENCE_METHODOLOGY_VERSION,
        REFERRAL_DEPOSITS_OUTPUT_COLUMNS as KYBERSWAP_DEPOSITS_COLUMNS,
        REFERRAL_DEPOSITS_QUERY_ID as KYBERSWAP_DEPOSITS_QUERY_ID,
        REFERRAL_DEPOSITS_TRANSFORMATION_ID as KYBERSWAP_DEPOSITS_TRANSFORMATION_ID,
        KyberSwapDepositorIntelligenceError,
        build_kyberswap_depositor_intelligence,
        prepare_kyberswap_etherfi_activity,
        prepare_kyberswap_referral_deposits,
        validate_kyberswap_depositor_intelligence,
    )
    from scripts.enrich_kyberswap_growth import (
        ACTIVITY_OUTPUT_COLUMNS as KYBERSWAP_GROWTH_ACTIVITY_COLUMNS,
        ACTIVITY_TRANSFORMATION_ID as KYBERSWAP_GROWTH_ACTIVITY_TRANSFORMATION_ID,
        BREAKDOWN_OUTPUT_COLUMNS as KYBERSWAP_GROWTH_BREAKDOWN_COLUMNS,
        BREAKDOWN_TRANSFORMATION_ID as KYBERSWAP_GROWTH_BREAKDOWN_TRANSFORMATION_ID,
        DEPOSITS_OUTPUT_COLUMNS as KYBERSWAP_GROWTH_DEPOSITS_COLUMNS,
        DEPOSITS_TRANSFORMATION_ID as KYBERSWAP_GROWTH_DEPOSITS_TRANSFORMATION_ID,
        POST_REFERRAL_ACTIVITY_OUTPUT_COLUMNS as KYBERSWAP_POST_REFERRAL_ACTIVITY_COLUMNS,
        POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID as KYBERSWAP_POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID,
        TVL_OUTPUT_COLUMNS as KYBERSWAP_GROWTH_TVL_COLUMNS,
        TVL_TRANSFORMATION_ID as KYBERSWAP_GROWTH_TVL_TRANSFORMATION_ID,
        KyberSwapGrowthError,
        prepare_kyberswap_growth_activity,
        prepare_kyberswap_growth_attributed_tvl,
        prepare_kyberswap_growth_breakdown,
        prepare_kyberswap_growth_deposits,
        prepare_kyberswap_post_referral_activity,
    )
except ModuleNotFoundError:  # Supports direct script execution.
    from studio import (  # type: ignore
        ROOT,
        STUDIO_DASHBOARDS_PATH,
        STUDIO_DATA_DIR,
        STUDIO_METRICS_PATH,
        build_studio_query_contracts,
        normalize_studio_registry,
        validate_studio_generated_manifest,
        validate_studio_query_result,
        validate_studio_registry,
    )
    from enrich_kyberswap_attributed_holdings import (  # type: ignore
        ENRICHED_COLUMNS as KYBERSWAP_ENRICHED_COLUMNS,
        KyberSwapAttributionError,
        enrich_kyberswap_attributed_holdings,
    )
    from prepare_kyberswap_campaign_summary import (  # type: ignore
        TRANSFORMATION_ID as KYBERSWAP_SUMMARY_TRANSFORMATION_ID,
        KyberSwapCampaignSummaryError,
        prepare_kyberswap_campaign_summary,
    )
    from prepare_kyberswap_depositor_intelligence import (  # type: ignore
        ATTRIBUTED_HOLDINGS_QUERY_ID as KYBERSWAP_INTELLIGENCE_HOLDINGS_QUERY_ID,
        DERIVED_ARTIFACT_FILE as KYBERSWAP_INTELLIGENCE_FILE,
        DERIVED_ARTIFACT_ID as KYBERSWAP_INTELLIGENCE_ID,
        ETHERFI_ACTIVITY_OUTPUT_COLUMNS as KYBERSWAP_ACTIVITY_COLUMNS,
        ETHERFI_ACTIVITY_QUERY_ID as KYBERSWAP_ACTIVITY_QUERY_ID,
        ETHERFI_ACTIVITY_TRANSFORMATION_ID as KYBERSWAP_ACTIVITY_TRANSFORMATION_ID,
        METHODOLOGY_ID as KYBERSWAP_INTELLIGENCE_METHODOLOGY_ID,
        METHODOLOGY_VERSION as KYBERSWAP_INTELLIGENCE_METHODOLOGY_VERSION,
        REFERRAL_DEPOSITS_OUTPUT_COLUMNS as KYBERSWAP_DEPOSITS_COLUMNS,
        REFERRAL_DEPOSITS_QUERY_ID as KYBERSWAP_DEPOSITS_QUERY_ID,
        REFERRAL_DEPOSITS_TRANSFORMATION_ID as KYBERSWAP_DEPOSITS_TRANSFORMATION_ID,
        KyberSwapDepositorIntelligenceError,
        build_kyberswap_depositor_intelligence,
        prepare_kyberswap_etherfi_activity,
        prepare_kyberswap_referral_deposits,
        validate_kyberswap_depositor_intelligence,
    )
    from enrich_kyberswap_growth import (  # type: ignore
        ACTIVITY_OUTPUT_COLUMNS as KYBERSWAP_GROWTH_ACTIVITY_COLUMNS,
        ACTIVITY_TRANSFORMATION_ID as KYBERSWAP_GROWTH_ACTIVITY_TRANSFORMATION_ID,
        BREAKDOWN_OUTPUT_COLUMNS as KYBERSWAP_GROWTH_BREAKDOWN_COLUMNS,
        BREAKDOWN_TRANSFORMATION_ID as KYBERSWAP_GROWTH_BREAKDOWN_TRANSFORMATION_ID,
        DEPOSITS_OUTPUT_COLUMNS as KYBERSWAP_GROWTH_DEPOSITS_COLUMNS,
        DEPOSITS_TRANSFORMATION_ID as KYBERSWAP_GROWTH_DEPOSITS_TRANSFORMATION_ID,
        POST_REFERRAL_ACTIVITY_OUTPUT_COLUMNS as KYBERSWAP_POST_REFERRAL_ACTIVITY_COLUMNS,
        POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID as KYBERSWAP_POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID,
        TVL_OUTPUT_COLUMNS as KYBERSWAP_GROWTH_TVL_COLUMNS,
        TVL_TRANSFORMATION_ID as KYBERSWAP_GROWTH_TVL_TRANSFORMATION_ID,
        KyberSwapGrowthError,
        prepare_kyberswap_growth_activity,
        prepare_kyberswap_growth_attributed_tvl,
        prepare_kyberswap_growth_breakdown,
        prepare_kyberswap_growth_deposits,
        prepare_kyberswap_post_referral_activity,
    )


INGESTION_SCHEMA_VERSION = 2
SNAPSHOT_STATE_SCHEMA_VERSION = 2
INGESTION_TOOL_VERSION = "1.0.0"
DEFAULT_STUDIO_OUTPUT_ROOT = ROOT / "website" / "data" / "studio" / "generated"
DEFAULT_FIXTURE_SCENARIOS_PATH = ROOT / "studio" / "fixtures" / "scenarios.yaml"
SNAPSHOT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
EVM_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")
EVM_TRANSACTION_PATTERN = re.compile(r"^0x[0-9a-fA-F]{64}$")
DUNE_EXECUTION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_PROVIDER_CLOCK_SKEW_SECONDS = 300
MAX_SAFE_JSON_INTEGER = (2**53) - 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Studio timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: object, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_data_date(value: object, *, field_name: str) -> None:
    """Accept an ISO calendar date or a timezone-aware ISO timestamp."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO date or timestamp")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a valid calendar date") from exc
        return
    parse_timestamp(value, field_name=field_name)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def pretty_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def strict_json_loads(
    value: str | bytes,
    *,
    preserve_decimal_lexemes: bool = False,
) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = item
        return result

    def reject_constant(constant: str) -> object:
        raise ValueError(f"Non-finite JSON number: {constant}")

    def preserve_large_integer(lexeme: str) -> int | str:
        parsed = int(lexeme)
        return lexeme if abs(parsed) > MAX_SAFE_JSON_INTEGER else parsed

    return json.loads(
        value,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_constant,
        parse_float=str if preserve_decimal_lexemes else float,
        parse_int=preserve_large_integer if preserve_decimal_lexemes else int,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_write_bytes(path: Path, payload: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


class FailureCategory(str, Enum):
    AUTHENTICATION = "authentication_failure"
    RATE_LIMITED = "rate_limited"
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_ERROR = "network_error"
    QUERY_UNAVAILABLE = "query_unavailable"
    LATEST_RESULT_REQUEST_FAILED = "latest_result_request_failed"
    QUERY_EXECUTION_FAILED = "query_execution_failed"
    MALFORMED_RESPONSE = "malformed_response"
    MISSING_REQUIRED_COLUMNS = "missing_required_columns"
    EMPTY_RESULT = "empty_result"
    PARTIAL_RESULT = "partial_result"
    WRITE_FAILURE = "write_failure"
    MANIFEST_FAILURE = "manifest_failure"
    INVALID_ROW = "invalid_row"
    INVALID_VALUE = "invalid_value"
    INVALID_DATE = "invalid_date"
    TRANSFORMATION_FAILURE = "transformation_failure"


RETRYABLE_FAILURES = {
    FailureCategory.RATE_LIMITED,
    FailureCategory.NETWORK_TIMEOUT,
    FailureCategory.NETWORK_ERROR,
}


class StudioIngestionError(RuntimeError):
    def __init__(
        self,
        category: FailureCategory,
        message: str,
        *,
        query_id: int | None = None,
        retryable: bool | None = None,
        retry_after_seconds: float | None = None,
        affected_metrics: list[str] | None = None,
        provider_execution_id: str | None = None,
        provider_execution_finished_at: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.query_id = query_id
        self.retryable = (
            category in RETRYABLE_FAILURES if retryable is None else retryable
        )
        self.retry_after_seconds = retry_after_seconds
        self.affected_metrics = list(affected_metrics or [])
        self.provider_execution_id = provider_execution_id
        self.provider_execution_finished_at = provider_execution_finished_at

    def as_dict(self) -> dict:
        return {
            "category": self.category.value,
            "message": str(self),
            "query_id": self.query_id,
            "retryable": self.retryable,
            "retry_after_seconds": self.retry_after_seconds,
            "affected_metrics": self.affected_metrics,
            "provider_execution_id": self.provider_execution_id,
            "provider_execution_finished_at": (
                self.provider_execution_finished_at
            ),
        }


@dataclass(frozen=True)
class StudioQueryRequest:
    query_id: int
    query_url: str
    result_file: str
    data_source: str
    source_label: str
    dashboard_ids: tuple[str, ...]
    metric_ids: tuple[str, ...]
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...]
    date_columns: tuple[str, ...]
    address_columns: tuple[str, ...]
    transaction_columns: tuple[str, ...]
    dimension_columns: tuple[str, ...]
    value_columns: tuple[str, ...]
    allow_empty: bool
    is_exportable: bool
    freshness_policy: Mapping[str, float]
    provider_mode: str = "fixture"
    source_required_columns: tuple[str, ...] = ()
    transformation: Mapping[str, object] | None = None


@dataclass
class StudioProviderResult:
    query_id: int
    status: str
    columns: list[str]
    rows: list[object]
    fetched_at: str
    execution_started_at: str
    execution_finished_at: str
    data_updated_at: str
    execution_id: str | None = None
    total_row_count: int | None = None
    partial: bool = False
    error: str | None = None
    provider_metadata: dict = field(default_factory=dict)


class StudioLatestResultClient(Protocol):
    """Read a query's latest already-executed stored result without executing it."""

    def fetch_latest_result(
        self,
        query_id: int,
        *,
        timeout_seconds: float,
    ) -> StudioProviderResult:
        ...


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 4.0

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or self.max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer")
        for field_name, value in (
            ("base_delay_seconds", self.base_delay_seconds),
            ("max_delay_seconds", self.max_delay_seconds),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"{field_name} must be finite and non-negative")


@dataclass
class NormalizedQuery:
    artifact: dict
    manifest_entry: dict
    content_checksum: str
    file_bytes: bytes
    supporting_files: dict[str, bytes] = field(default_factory=dict)


@dataclass
class NormalizedDerivedArtifact:
    payload: dict
    manifest_entry: dict
    content_checksum: str
    file_bytes: bytes


@dataclass
class PreparedProviderResult:
    result: StudioProviderResult
    metadata: dict = field(default_factory=dict)
    supporting_files: dict[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class RefreshSummary:
    status: str
    snapshot_id: str | None
    attempt_id: str
    fetched_query_ids: tuple[int, ...]
    reused_query_ids: tuple[int, ...]
    failed_query_ids: tuple[int, ...]
    unchanged: bool
    output_root: Path

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "snapshot_id": self.snapshot_id,
            "attempt_id": self.attempt_id,
            "fetched_query_ids": list(self.fetched_query_ids),
            "reused_query_ids": list(self.reused_query_ids),
            "failed_query_ids": list(self.failed_query_ids),
            "unchanged": self.unchanged,
            "output_root": str(self.output_root),
        }


def _read_registry_values(
    dashboard_path: Path = STUDIO_DASHBOARDS_PATH,
    metric_path: Path = STUDIO_METRICS_PATH,
) -> tuple[list[dict], list[dict]]:
    dashboard_payload = yaml.safe_load(Path(dashboard_path).read_text(encoding="utf-8")) or {}
    metric_payload = yaml.safe_load(Path(metric_path).read_text(encoding="utf-8")) or {}
    dashboards = dashboard_payload.get("dashboards")
    metrics = metric_payload.get("metrics")
    if not isinstance(dashboards, list) or not all(isinstance(item, dict) for item in dashboards):
        raise ValueError("Studio dashboards registry must contain a dashboards list")
    if not isinstance(metrics, list) or not all(isinstance(item, dict) for item in metrics):
        raise ValueError("Studio metrics registry must contain a metrics list")
    dashboards, metrics = normalize_studio_registry(dashboards, metrics)
    try:
        return validate_studio_registry(
            dashboards,
            metrics,
            validate_generated_data=False,
        )
    except TypeError:
        # Compatibility while older callers use the pre-ingestion validator.
        bootstrap = Path(tempfile.mkdtemp(prefix="studio-registry-bootstrap-"))
        try:
            (bootstrap / "manifest.json").write_bytes(
                pretty_json_bytes(
                    {"schema_version": 1, "generated_at": None, "queries": []}
                )
            )
            return validate_studio_registry(
                dashboards,
                metrics,
                generated_data_dir=bootstrap,
            )
        finally:
            shutil.rmtree(bootstrap)


def _freshness_policy_for_request(
    contract: dict,
    dashboards_by_id: dict[str, dict],
) -> dict[str, float]:
    policies: list[dict] = []
    contract_policy = contract.get("freshness_policy")
    if isinstance(contract_policy, dict):
        policies.append(contract_policy)
    for dashboard_id in contract.get("dashboard_ids", []):
        dashboard = dashboards_by_id.get(str(dashboard_id), {})
        policy = dashboard.get("freshness_policy")
        if isinstance(policy, dict):
            policies.append(policy)
    if not policies:
        return {
            "expected_refresh_hours": 24.0,
            "warning_after_hours": 36.0,
            "stale_after_hours": 72.0,
        }
    result: dict[str, float] = {}
    for field_name in (
        "expected_refresh_hours",
        "warning_after_hours",
        "stale_after_hours",
    ):
        values = [
            float(policy[field_name])
            for policy in policies
            if isinstance(policy.get(field_name), (int, float))
            and not isinstance(policy.get(field_name), bool)
        ]
        if values:
            result[field_name] = min(values)
    expected = result.get("expected_refresh_hours", 24.0)
    warning = result.get("warning_after_hours", max(expected, expected * 1.5))
    stale = result.get("stale_after_hours", max(warning, expected * 3))
    return {
        "expected_refresh_hours": expected,
        "warning_after_hours": warning,
        "stale_after_hours": stale,
    }


def build_query_requests(
    dashboard_values: list[dict],
    metric_values: list[dict],
) -> dict[int, StudioQueryRequest]:
    contracts = build_studio_query_contracts(metric_values)
    dashboards_by_id = {
        str(dashboard["id"]): dashboard for dashboard in dashboard_values
    }
    requests: dict[int, StudioQueryRequest] = {}
    for query_id, contract in sorted(contracts.items()):
        requests[query_id] = StudioQueryRequest(
            query_id=query_id,
            query_url=str(contract["query_url"]),
            result_file=str(contract["data_file"]),
            data_source=str(contract["data_source"]),
            source_label=str(contract.get("source_label") or ""),
            dashboard_ids=tuple(str(value) for value in contract["dashboard_ids"]),
            metric_ids=tuple(str(value) for value in contract["metric_ids"]),
            required_columns=tuple(str(value) for value in contract["required_columns"]),
            optional_columns=tuple(str(value) for value in contract.get("optional_columns", [])),
            date_columns=tuple(str(value) for value in contract.get("date_columns", [])),
            address_columns=tuple(str(value) for value in contract.get("address_columns", [])),
            transaction_columns=tuple(
                str(value) for value in contract.get("transaction_columns", [])
            ),
            dimension_columns=tuple(
                str(value) for value in contract.get("dimension_columns", [])
            ),
            value_columns=tuple(str(value) for value in contract.get("value_columns", [])),
            allow_empty=bool(contract.get("allow_empty", not contract["is_exportable"])),
            is_exportable=bool(contract["is_exportable"]),
            freshness_policy=_freshness_policy_for_request(
                contract,
                dashboards_by_id,
            ),
            provider_mode=str(contract.get("provider_mode") or "fixture"),
            source_required_columns=tuple(
                str(value)
                for value in contract.get("source_required_columns", [])
            ),
            transformation=(
                dict(contract["transformation"])
                if isinstance(contract.get("transformation"), dict)
                else None
            ),
        )
    return requests


def load_query_requests() -> tuple[list[dict], list[dict], dict[int, StudioQueryRequest]]:
    dashboards, metrics = _read_registry_values()
    return dashboards, metrics, build_query_requests(dashboards, metrics)


def generated_query_ids(
    dashboards: list[dict],
    query_requests: Mapping[int, StudioQueryRequest],
) -> set[int]:
    generated_dashboard_ids = {
        str(dashboard["id"])
        for dashboard in dashboards
        if dashboard.get("data_mode") == "generated"
    }
    return {
        query_id
        for query_id, request in query_requests.items()
        if generated_dashboard_ids.intersection(request.dashboard_ids)
    }


def query_contract_checksum(
    query_requests: Mapping[int, StudioQueryRequest],
) -> str:
    """Fingerprint the validated registry fields that shape generated artifacts."""
    return sha256_json(
        [
            {
                "query_id": request.query_id,
                "query_url": request.query_url,
                "result_file": request.result_file,
                "data_source": request.data_source,
                "source_label": request.source_label,
                "dashboard_ids": list(request.dashboard_ids),
                "metric_ids": list(request.metric_ids),
                "required_columns": list(request.required_columns),
                "optional_columns": list(request.optional_columns),
                "date_columns": list(request.date_columns),
                "address_columns": list(request.address_columns),
                "transaction_columns": list(request.transaction_columns),
                "dimension_columns": list(request.dimension_columns),
                "value_columns": list(request.value_columns),
                "allow_empty": request.allow_empty,
                "is_exportable": request.is_exportable,
                "freshness_policy": dict(request.freshness_policy),
                "provider_mode": request.provider_mode,
                "source_required_columns": list(request.source_required_columns),
                "transformation": dict(request.transformation or {}),
            }
            for _, request in sorted(query_requests.items())
        ]
    )


class FixtureDuneClient:
    """Simulate read-only latest-result responses from deterministic demo bundles."""

    def __init__(
        self,
        requests: Mapping[int, StudioQueryRequest],
        dashboards: list[dict],
        *,
        scenario: str = "success",
        scenarios_path: Path = DEFAULT_FIXTURE_SCENARIOS_PATH,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.requests = dict(requests)
        self.dashboards = {str(item["id"]): item for item in dashboards}
        self.clock = clock
        payload = yaml.safe_load(Path(scenarios_path).read_text(encoding="utf-8")) or {}
        if payload.get("schema_version") != 1:
            raise ValueError("Studio fixture scenarios schema_version must be 1")
        scenarios = payload.get("scenarios")
        if not isinstance(scenarios, dict) or scenario not in scenarios:
            raise ValueError(f"Unknown Studio fixture scenario: {scenario}")
        self.defaults = payload.get("default_query_overrides") or {}
        self.scenario_name = scenario
        self.scenario = scenarios[scenario] or {}
        self.calls: Counter[int] = Counter()
        self._bundles: dict[str, dict] = {}

    def _bundle(self, dashboard_id: str) -> dict:
        dashboard = self.dashboards[dashboard_id]
        data_file = str(dashboard["data_file"])
        if data_file not in self._bundles:
            self._bundles[data_file] = strict_json_loads(
                (STUDIO_DATA_DIR / data_file).read_text(encoding="utf-8")
            )
        return self._bundles[data_file]

    @staticmethod
    def _columns(rows: list[object], fallback: list[str]) -> list[str]:
        columns: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            for column in row:
                if column not in columns:
                    columns.append(str(column))
        return columns or list(fallback)

    @staticmethod
    def _failure_category(value: str) -> FailureCategory:
        try:
            return FailureCategory(value)
        except ValueError as exc:
            raise ValueError(f"Unsupported fixture failure category: {value}") from exc

    def fetch_latest_result(
        self,
        query_id: int,
        *,
        timeout_seconds: float,
    ) -> StudioProviderResult:
        del timeout_seconds
        self.calls[query_id] += 1
        studio_request = self.requests.get(query_id)
        if studio_request is None:
            raise StudioIngestionError(
                FailureCategory.QUERY_UNAVAILABLE,
                f"Fixture query {query_id} is not in the Studio registry",
                query_id=query_id,
            )
        effect = self.scenario if int(self.scenario.get("query_id", query_id)) == query_id else {}
        failure = effect.get("failure") if isinstance(effect, dict) else None
        if isinstance(failure, dict):
            fail_attempts = int(failure.get("fail_attempts", 999999))
            if self.calls[query_id] <= fail_attempts:
                category = self._failure_category(str(failure["category"]))
                raise StudioIngestionError(
                    category,
                    str(failure.get("message") or f"Fixture {category.value}"),
                    query_id=query_id,
                    retry_after_seconds=(
                        float(failure["retry_after_seconds"])
                        if failure.get("retry_after_seconds") is not None
                        else None
                    ),
                    provider_execution_id=(
                        str(failure["provider_execution_id"])
                        if failure.get("provider_execution_id") is not None
                        else None
                    ),
                    provider_execution_finished_at=(
                        str(failure["provider_execution_finished_at"])
                        if failure.get("provider_execution_finished_at") is not None
                        else None
                    ),
                )

        dashboard_id = studio_request.dashboard_ids[0]
        fixture_payload: dict | None = None
        explicit_columns: list[str] | None = None
        transformation = studio_request.transformation or {}
        fixture_path = transformation.get("fixture_path")
        if isinstance(fixture_path, str):
            fixture_value = strict_json_loads((ROOT / fixture_path).read_bytes())
            if not isinstance(fixture_value, dict):
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Fixture query {query_id} file must be a mapping",
                    query_id=query_id,
                )
            if fixture_value.get("query_id") != query_id:
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Fixture query {query_id} file identifies another query",
                    query_id=query_id,
                )
            fixture_payload = fixture_value
            raw_rows = fixture_payload.get("rows")
            raw_columns = fixture_payload.get("columns")
            if isinstance(raw_columns, list) and all(
                isinstance(column, str) for column in raw_columns
            ):
                explicit_columns = list(raw_columns)
            bundle_meta = {
                "last_refreshed": fixture_payload.get("execution_finished_at")
            }
        else:
            bundle = self._bundle(dashboard_id)
            bundle_meta = bundle.get("meta") or {}
            raw_rows = (bundle.get("datasets") or {}).get(studio_request.data_source)
        default_override = self.defaults.get(str(query_id)) or {}
        if "replace_rows" in default_override:
            raw_rows = default_override["replace_rows"]
        if isinstance(raw_rows, dict) and raw_rows.get("error"):
            raise StudioIngestionError(
                FailureCategory.QUERY_EXECUTION_FAILED,
                str(raw_rows["error"]),
                query_id=query_id,
            )
        if not isinstance(raw_rows, list):
            raise StudioIngestionError(
                FailureCategory.MALFORMED_RESPONSE,
                f"Fixture query {query_id} did not return a rows list",
                query_id=query_id,
            )
        rows: list[object] = [dict(row) if isinstance(row, dict) else row for row in raw_rows]

        if isinstance(effect, dict):
            if "replace_rows" in effect:
                replacement = effect["replace_rows"]
                rows = [dict(row) if isinstance(row, dict) else row for row in replacement]
            dropped = [str(value) for value in effect.get("drop_columns", [])]
            if dropped:
                rows = [
                    {key: value for key, value in row.items() if key not in dropped}
                    if isinstance(row, dict)
                    else row
                    for row in rows
                ]
            extra_columns = effect.get("extra_columns") or {}
            if isinstance(extra_columns, dict):
                for row_index, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    for column, values in extra_columns.items():
                        if isinstance(values, list):
                            row[str(column)] = values[row_index % len(values)] if values else None
                        else:
                            row[str(column)] = values
            set_values = effect.get("set_values") or {}
            if rows and isinstance(rows[0], dict) and isinstance(set_values, dict):
                for column, value in set_values.items():
                    rows[0][str(column)] = value
            malformed_index = effect.get("malformed_row_index")
            if malformed_index is not None and rows:
                rows[int(malformed_index) % len(rows)] = ["malformed", "row"]
            if effect.get("duplicate_first_row") and rows:
                first = rows[0]
                rows.append(dict(first) if isinstance(first, dict) else first)

        fallback_columns = list(studio_request.required_columns) + list(
            studio_request.optional_columns
        )
        columns = explicit_columns or self._columns(rows, fallback_columns)
        reordered = effect.get("column_order") if isinstance(effect, dict) else None
        if isinstance(reordered, list):
            ordered = [str(value) for value in reordered if str(value) in columns]
            columns = ordered + [column for column in columns if column not in ordered]

        refreshed_at = str(bundle_meta.get("last_refreshed") or iso_utc(self.clock()))
        checked_at = iso_utc(self.clock())
        status = str(effect.get("status") or ("success" if rows else "empty"))
        execution_started_at = str(
            (fixture_payload or {}).get("execution_started_at") or refreshed_at
        )
        execution_finished_at = str(
            (fixture_payload or {}).get("execution_finished_at") or refreshed_at
        )
        execution_id = (
            str(fixture_payload["execution_id"])
            if fixture_payload and fixture_payload.get("execution_id") is not None
            else (
                f"fixture-{query_id}-"
                f"{sha256_bytes(refreshed_at.encode('utf-8'))[:12]}"
            )
        )
        return StudioProviderResult(
            query_id=query_id,
            status=status,
            columns=columns,
            rows=rows,
            fetched_at=checked_at,
            execution_started_at=execution_started_at,
            execution_finished_at=execution_finished_at,
            data_updated_at=execution_finished_at,
            execution_id=execution_id,
            total_row_count=(
                int(effect["reported_row_count"])
                if isinstance(effect, dict) and effect.get("reported_row_count") is not None
                else len(rows)
            ),
            partial=bool(effect.get("partial")) if isinstance(effect, dict) else False,
            provider_metadata={
                "fixture": True,
                "scenario": self.scenario_name,
                "source_bundle": str(self.dashboards[dashboard_id]["data_file"]),
                "data_source": studio_request.data_source,
                "source_mode": "fixture",
                "fixture_path": fixture_path,
            },
        )


class SequenceStudioLatestResultClient:
    """Inject a sequence of latest-result responses for deterministic tests."""

    def __init__(self, responses: Mapping[int, list[object]]) -> None:
        self.responses = {query_id: list(values) for query_id, values in responses.items()}
        self.calls: Counter[int] = Counter()

    def fetch_latest_result(
        self,
        query_id: int,
        *,
        timeout_seconds: float,
    ) -> StudioProviderResult:
        del timeout_seconds
        self.calls[query_id] += 1
        values = self.responses.get(query_id)
        if not values:
            raise StudioIngestionError(
                FailureCategory.QUERY_UNAVAILABLE,
                f"No mocked response remains for query {query_id}",
                query_id=query_id,
            )
        value = values.pop(0)
        if isinstance(value, BaseException):
            raise value
        if not isinstance(value, StudioProviderResult):
            raise StudioIngestionError(
                FailureCategory.MALFORMED_RESPONSE,
                f"Mocked query {query_id} returned an unsupported value",
                query_id=query_id,
            )
        return value


class RoutedStudioLatestResultClient:
    """Route each query to one explicit latest-result provider."""

    def __init__(self, routes: Mapping[int, StudioLatestResultClient]) -> None:
        self.routes = dict(routes)
        self.calls: Counter[int] = Counter()

    def fetch_latest_result(
        self,
        query_id: int,
        *,
        timeout_seconds: float,
    ) -> StudioProviderResult:
        self.calls[query_id] += 1
        client = self.routes.get(query_id)
        if client is None:
            raise StudioIngestionError(
                FailureCategory.QUERY_UNAVAILABLE,
                f"No latest-result provider is configured for query {query_id}",
                query_id=query_id,
            )
        return client.fetch_latest_result(
            query_id,
            timeout_seconds=timeout_seconds,
        )


HttpTransport = Callable[[str, Mapping[str, str], float], tuple[int, Mapping[str, str], object]]


class _NoRedirectHandler(urllib_request.HTTPRedirectHandler):
    """Never forward the Dune API key through an HTTP redirect."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        del request, file_pointer, code, message, headers, new_url
        return None


_NO_REDIRECT_OPENER = urllib_request.build_opener(_NoRedirectHandler())


def _urllib_transport(
    url: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> tuple[int, Mapping[str, str], object]:
    request = urllib_request.Request(url, headers=dict(headers), method="GET")
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=timeout_seconds) as response:
            payload = strict_json_loads(
                response.read().decode("utf-8"),
                preserve_decimal_lexemes=True,
            )
            return int(response.status), dict(response.headers.items()), payload
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload: object = strict_json_loads(
                body,
                preserve_decimal_lexemes=True,
            )
        except (json.JSONDecodeError, ValueError):
            payload = {"error": "Dune returned a non-JSON error response"}
        return int(exc.code), dict(exc.headers.items()), payload


class DuneLatestResultClient:
    """Read Dune's latest stored result; never execute or refresh a query."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: HttpTransport = _urllib_transport,
        base_url: str = "https://api.dune.com/api/v1",
        page_size: int = 1000,
        max_pages: int = 100,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not api_key:
            raise ValueError("DUNE_API_KEY is required for live Studio fetching")
        if type(page_size) is not int or page_size <= 0:
            raise ValueError("Dune page_size must be a positive integer")
        if type(max_pages) is not int or max_pages <= 0:
            raise ValueError("Dune max_pages must be a positive integer")
        self._api_key = api_key
        self.transport = transport
        self.base_url = base_url.rstrip("/")
        self._base_parts = urllib_parse.urlsplit(self.base_url)
        if self._base_parts.scheme != "https" or not self._base_parts.netloc:
            raise ValueError("Dune base_url must be an absolute HTTPS URL")
        try:
            self._base_origin = (
                self._base_parts.scheme.lower(),
                self._base_parts.hostname,
                self._base_parts.port,
            )
        except ValueError as exc:
            raise ValueError("Dune base_url has an invalid port") from exc
        self.page_size = page_size
        self.max_pages = max_pages
        self.clock = clock

    @staticmethod
    def _error_message(payload: object, fallback: str) -> str:
        if isinstance(payload, dict):
            for field_name in ("error", "message"):
                value = payload.get(field_name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return fallback

    def _redact(self, message: str) -> str:
        return message.replace(self._api_key, "[redacted]")

    def _retry_after_seconds(self, raw_value: object) -> float | None:
        if not isinstance(raw_value, str) or not raw_value.strip():
            return None
        value = raw_value.strip()
        try:
            seconds = float(value)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if retry_at.tzinfo is None or retry_at.utcoffset() is None:
                return None
            seconds = (
                retry_at.astimezone(timezone.utc)
                - self.clock().astimezone(timezone.utc)
            ).total_seconds()
        if not math.isfinite(seconds) or seconds < 0:
            return None
        return seconds

    def _safe_next_url(
        self,
        query_id: int,
        execution_id: str,
        current_url: str,
        next_uri: str,
    ) -> str:
        try:
            candidate = urllib_parse.urljoin(current_url, next_uri)
            parsed = urllib_parse.urlsplit(candidate)
            candidate_origin = (
                parsed.scheme.lower(),
                parsed.hostname,
                parsed.port,
            )
            query_params = urllib_parse.parse_qsl(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=True,
            )
        except ValueError as exc:
            raise StudioIngestionError(
                FailureCategory.MALFORMED_RESPONSE,
                f"Dune query {query_id} returned a malformed pagination URL",
                query_id=query_id,
            ) from exc
        base_path = self._base_parts.path.rstrip("/")
        allowed_paths = {
            f"{base_path}/query/{query_id}/results",
            f"{base_path}/execution/{execution_id}/results",
        }
        param_names = [name for name, _ in query_params]
        pagination_params_are_safe = (
            not parsed.fragment
            and parsed.username is None
            and parsed.password is None
            and len(param_names) == len(set(param_names))
            and set(param_names).issubset({"limit", "offset"})
        )
        if pagination_params_are_safe:
            for name, value in query_params:
                if not value.isascii() or not value.isdecimal():
                    pagination_params_are_safe = False
                    break
                numeric_value = int(value)
                if name == "limit" and not 0 < numeric_value <= self.page_size:
                    pagination_params_are_safe = False
                    break
        if (
            candidate_origin != self._base_origin
            or parsed.path.rstrip("/") not in allowed_paths
            or not pagination_params_are_safe
        ):
            raise StudioIngestionError(
                FailureCategory.MALFORMED_RESPONSE,
                f"Dune query {query_id} returned an unsafe pagination URL",
                query_id=query_id,
            )
        return candidate

    def _raise_http_error(
        self,
        query_id: int,
        status: int,
        headers: Mapping[str, str],
        payload: object,
    ) -> None:
        message = self._redact(
            self._error_message(payload, f"Dune HTTP {status}")
        )
        if status in {401, 403}:
            category = FailureCategory.AUTHENTICATION
        elif status == 429:
            category = FailureCategory.RATE_LIMITED
        elif status == 404:
            category = FailureCategory.QUERY_UNAVAILABLE
        elif status in {408, 500, 502, 503, 504}:
            category = FailureCategory.NETWORK_ERROR
        else:
            category = FailureCategory.LATEST_RESULT_REQUEST_FAILED
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        raise StudioIngestionError(
            category,
            message,
            query_id=query_id,
            retry_after_seconds=self._retry_after_seconds(retry_after),
        )

    def fetch_latest_result(
        self,
        query_id: int,
        *,
        timeout_seconds: float,
    ) -> StudioProviderResult:
        """GET the latest already-executed result, following read-only pagination."""
        headers = {"X-Dune-API-Key": self._api_key, "Accept": "application/json"}
        url = f"{self.base_url}/query/{query_id}/results?limit={self.page_size}"
        rows: list[object] = []
        columns: list[str] = []
        first_payload: dict | None = None
        expected_execution_id: str | None = None
        expected_execution_started_at: str | None = None
        expected_execution_finished_at: str | None = None
        expected_total_row_count: int | None = None
        visited_urls: set[str] = set()
        page_count = 0
        while url:
            if url in visited_urls:
                raise StudioIngestionError(
                    FailureCategory.PARTIAL_RESULT,
                    f"Dune query {query_id} returned a pagination loop",
                    query_id=query_id,
                )
            visited_urls.add(url)
            page_count += 1
            if page_count > self.max_pages:
                raise StudioIngestionError(
                    FailureCategory.PARTIAL_RESULT,
                    f"Query {query_id} exceeded the configured pagination limit",
                    query_id=query_id,
                )
            try:
                status, response_headers, payload = self.transport(
                    url,
                    headers,
                    timeout_seconds,
                )
            except (TimeoutError, urllib_error.URLError) as exc:
                category = (
                    FailureCategory.NETWORK_TIMEOUT
                    if isinstance(exc, TimeoutError)
                    else FailureCategory.NETWORK_ERROR
                )
                raise StudioIngestionError(
                    category,
                    f"Dune result request failed for query {query_id}",
                    query_id=query_id,
                ) from exc
            except (UnicodeError, ValueError) as exc:
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} returned malformed response data",
                    query_id=query_id,
                ) from exc
            if status < 200 or status >= 300:
                self._raise_http_error(query_id, status, response_headers, payload)
            if not isinstance(payload, dict):
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} returned a non-object response",
                    query_id=query_id,
                )
            state = payload.get("state")
            if not isinstance(state, str) or not state.strip():
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} response has no execution state",
                    query_id=query_id,
                )
            response_query_id = payload.get("query_id")
            if type(response_query_id) is not int:
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} response has no valid query ID",
                    query_id=query_id,
                )
            if response_query_id != query_id:
                raise StudioIngestionError(
                    FailureCategory.PARTIAL_RESULT,
                    f"Dune query {query_id} response identified query {response_query_id}",
                    query_id=query_id,
                )
            if state not in {"QUERY_STATE_COMPLETED", "COMPLETED"}:
                provider_execution_id = payload.get("execution_id")
                if (
                    not isinstance(provider_execution_id, str)
                    or not DUNE_EXECUTION_ID_PATTERN.fullmatch(provider_execution_id)
                ):
                    provider_execution_id = None
                provider_execution_finished_at = payload.get(
                    "execution_ended_at"
                )
                try:
                    parse_timestamp(
                        provider_execution_finished_at,
                        field_name="execution_ended_at",
                    )
                except ValueError:
                    provider_execution_finished_at = None
                raise StudioIngestionError(
                    FailureCategory.QUERY_EXECUTION_FAILED,
                    self._redact(
                        self._error_message(
                            payload,
                            f"Dune query {query_id} finished with state {state}",
                        )
                    ),
                    query_id=query_id,
                    provider_execution_id=provider_execution_id,
                    provider_execution_finished_at=(
                        provider_execution_finished_at
                    ),
                )
            execution_id_value = payload.get("execution_id")
            if (
                not isinstance(execution_id_value, str)
                or not DUNE_EXECUTION_ID_PATTERN.fullmatch(execution_id_value)
            ):
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} response has no valid execution ID",
                    query_id=query_id,
                )
            execution_id = execution_id_value
            if first_payload is None:
                first_payload = payload
                expected_execution_id = execution_id
                started_value = payload.get("execution_started_at")
                finished_value = payload.get("execution_ended_at")
                if not isinstance(started_value, str) or not isinstance(
                    finished_value,
                    str,
                ):
                    raise StudioIngestionError(
                        FailureCategory.MALFORMED_RESPONSE,
                        f"Dune query {query_id} response is missing execution timestamps",
                        query_id=query_id,
                    )
                expected_execution_started_at = started_value
                expected_execution_finished_at = finished_value
            elif execution_id != expected_execution_id:
                raise StudioIngestionError(
                    FailureCategory.PARTIAL_RESULT,
                    f"Dune query {query_id} pagination mixed execution IDs",
                    query_id=query_id,
                )
            else:
                for field_name, expected_value in (
                    ("execution_started_at", expected_execution_started_at),
                    ("execution_ended_at", expected_execution_finished_at),
                ):
                    page_value = payload.get(field_name)
                    if page_value is not None and page_value != expected_value:
                        raise StudioIngestionError(
                            FailureCategory.PARTIAL_RESULT,
                            f"Dune query {query_id} pagination changed {field_name}",
                            query_id=query_id,
                        )
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("rows"), list):
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} response has no result rows",
                    query_id=query_id,
                )
            rows.extend(result["rows"])
            metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
            raw_total_row_count = (
                metadata.get("total_row_count")
                if metadata.get("total_row_count") is not None
                else result.get("total_row_count")
            )
            if raw_total_row_count is None:
                raw_total_row_count = payload.get("total_row_count")
            if page_count == 1 and raw_total_row_count is None:
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} response has no total row count",
                    query_id=query_id,
                )
            if raw_total_row_count is not None:
                if (
                    type(raw_total_row_count) is not int
                    or raw_total_row_count < 0
                ):
                    raise StudioIngestionError(
                        FailureCategory.MALFORMED_RESPONSE,
                        f"Dune query {query_id} returned an invalid total row count",
                        query_id=query_id,
                    )
                if expected_total_row_count is None:
                    expected_total_row_count = raw_total_row_count
                elif raw_total_row_count != expected_total_row_count:
                    raise StudioIngestionError(
                        FailureCategory.PARTIAL_RESULT,
                        f"Dune query {query_id} pagination changed total row count",
                        query_id=query_id,
                    )
            raw_columns = metadata.get("column_names") or result.get("column_names")
            if isinstance(raw_columns, list):
                for column in raw_columns:
                    if isinstance(column, str) and column not in columns:
                        columns.append(column)
            next_uri = payload.get("next_uri")
            if next_uri is None:
                next_uri = metadata.get("next_uri")
            if isinstance(next_uri, str) and next_uri:
                url = self._safe_next_url(
                    query_id,
                    execution_id,
                    url,
                    next_uri,
                )
                continue
            if next_uri is not None and not isinstance(next_uri, str):
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} returned an invalid next URI",
                    query_id=query_id,
                )
            next_offset = payload.get("next_offset")
            if next_offset is None:
                next_offset = metadata.get("next_offset")
            if type(next_offset) is int and next_offset >= 0:
                url = (
                    f"{self.base_url}/execution/{execution_id}/results"
                    f"?limit={self.page_size}&offset={next_offset}"
                )
                continue
            if next_offset is not None:
                raise StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Dune query {query_id} returned an invalid next offset",
                    query_id=query_id,
                )
            url = ""

        assert first_payload is not None
        assert expected_total_row_count is not None
        if len(rows) != expected_total_row_count:
            raise StudioIngestionError(
                FailureCategory.PARTIAL_RESULT,
                f"Dune query {query_id} returned {len(rows)} of "
                f"{expected_total_row_count} rows",
                query_id=query_id,
            )
        if not columns:
            columns = FixtureDuneClient._columns(rows, [])
        now_value = iso_utc(self.clock())
        assert expected_execution_started_at is not None
        assert expected_execution_finished_at is not None
        started_at = expected_execution_started_at
        finished_at = expected_execution_finished_at
        data_updated_at = finished_at
        return StudioProviderResult(
            query_id=query_id,
            status="success" if rows else "empty",
            columns=columns,
            rows=rows,
            fetched_at=now_value,
            execution_started_at=started_at,
            execution_finished_at=finished_at,
            data_updated_at=data_updated_at,
            execution_id=(
                str(first_payload["execution_id"])
                if first_payload.get("execution_id") is not None
                else None
            ),
            total_row_count=expected_total_row_count,
            partial=False,
            provider_metadata={"page_count": page_count, "source_mode": "live"},
        )


def fetch_latest_result_with_retry(
    client: StudioLatestResultClient,
    request: StudioQueryRequest,
    *,
    retry_policy: RetryPolicy,
    timeout_seconds: float,
    sleeper: Callable[[float], None] = time.sleep,
    logger: Callable[[str], None] | None = None,
) -> tuple[StudioProviderResult, int]:
    for attempt in range(1, retry_policy.max_attempts + 1):
        try:
            return (
                client.fetch_latest_result(
                    request.query_id,
                    timeout_seconds=timeout_seconds,
                ),
                attempt,
            )
        except TimeoutError as exc:
            error = StudioIngestionError(
                FailureCategory.NETWORK_TIMEOUT,
                f"Query {request.query_id} timed out",
                query_id=request.query_id,
            )
            error.__cause__ = exc
        except StudioIngestionError as exc:
            error = exc
        if not error.retryable or attempt >= retry_policy.max_attempts:
            error.affected_metrics = list(request.metric_ids)
            raise error
        requested_delay = (
            error.retry_after_seconds
            if error.retry_after_seconds is not None
            else min(
                retry_policy.max_delay_seconds,
                retry_policy.base_delay_seconds * (2 ** (attempt - 1)),
            )
        )
        delay = min(retry_policy.max_delay_seconds, max(0.0, requested_delay))
        if logger:
            logger(
                f"query {request.query_id}: {error.category.value}; "
                f"retrying in {delay:g}s ({attempt + 1}/{retry_policy.max_attempts})"
            )
        sleeper(delay)
    raise AssertionError("retry loop exited unexpectedly")


def classify_freshness(
    execution_finished_at: str,
    policy: Mapping[str, float],
    checked_at: datetime,
) -> str:
    completed_at = parse_timestamp(
        execution_finished_at,
        field_name="execution_finished_at",
    )
    age_hours = max(0.0, (checked_at - completed_at).total_seconds() / 3600)
    stale_after = float(policy.get("stale_after_hours", math.inf))
    warning_after = float(policy.get("warning_after_hours", stale_after))
    if age_hours > stale_after:
        return "stale"
    if age_hours > warning_after:
        return "delayed"
    return "current"


def _ensure_json_scalar(value: object, *, query_id: int, row_index: int, column: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise StudioIngestionError(
            FailureCategory.INVALID_VALUE,
            f"Query {query_id} row {row_index} column {column} contains NaN or infinity",
            query_id=query_id,
        )
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise StudioIngestionError(
        FailureCategory.INVALID_VALUE,
        f"Query {query_id} row {row_index} column {column} must be a JSON scalar",
        query_id=query_id,
    )


def _ensure_numeric_value(
    value: object,
    *,
    query_id: int,
    row_index: int,
    column: str,
) -> None:
    """Validate numeric shape without coercing or rounding financial values."""
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise StudioIngestionError(
            FailureCategory.INVALID_VALUE,
            f"Query {query_id} row {row_index} value column {column} must be numeric",
            query_id=query_id,
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise StudioIngestionError(
            FailureCategory.INVALID_VALUE,
            f"Query {query_id} row {row_index} value column {column} must be finite",
            query_id=query_id,
        )
    if isinstance(value, str):
        if not value.strip():
            raise StudioIngestionError(
                FailureCategory.INVALID_VALUE,
                f"Query {query_id} row {row_index} value column {column} must be numeric",
                query_id=query_id,
            )
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise StudioIngestionError(
                FailureCategory.INVALID_VALUE,
                f"Query {query_id} row {row_index} value column {column} must be numeric",
                query_id=query_id,
            ) from exc
        if not parsed.is_finite():
            raise StudioIngestionError(
                FailureCategory.INVALID_VALUE,
                f"Query {query_id} row {row_index} value column {column} must be finite",
                query_id=query_id,
            )


def _raw_result_bytes(value: dict) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        )
        + "\n"
    ).encode("utf-8")


def prepare_raw_provider_result(
    result: StudioProviderResult,
    request: StudioQueryRequest,
) -> tuple[dict, dict[str, bytes]]:
    """Serialize the fetched provider rows before any transformation runs."""
    transformation = dict(request.transformation or {})
    if not transformation:
        return {}, {}
    raw_checksum = sha256_json(
        {"columns": list(result.columns), "rows": result.rows}
    )
    raw_artifact = {
        "schema_version": 1,
        "query_id": request.query_id,
        "query_url": request.query_url,
        "execution_id": result.execution_id,
        "execution_started_at": result.execution_started_at,
        "execution_finished_at": result.execution_finished_at,
        "fetched_at": result.fetched_at,
        "data_updated_at": result.data_updated_at,
        "row_count": len(result.rows),
        "columns": list(result.columns),
        "rows": result.rows,
        "checksum": raw_checksum,
    }
    raw_file_bytes = _raw_result_bytes(raw_artifact)
    raw_data_file = str(transformation["raw_data_file"])
    return (
        {
            "raw_data_file": raw_data_file,
            "raw_row_count": len(result.rows),
            "raw_columns": list(result.columns),
            "raw_checksum": raw_checksum,
            "raw_file_checksum": sha256_bytes(raw_file_bytes),
            "raw_file_size_bytes": len(raw_file_bytes),
        },
        {raw_data_file: raw_file_bytes},
    )


def prepare_provider_result(
    result: StudioProviderResult,
    request: StudioQueryRequest,
    *,
    checked_at: datetime,
    raw_metadata: Mapping[str, object] | None = None,
    raw_supporting_files: Mapping[str, bytes] | None = None,
) -> PreparedProviderResult:
    transformation = dict(request.transformation or {})
    if not transformation:
        return PreparedProviderResult(result=result)
    if not isinstance(result.rows, list):
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {request.query_id} source rows must be a list",
            query_id=request.query_id,
            affected_metrics=list(request.metric_ids),
        )
    if result.partial:
        raise StudioIngestionError(
            FailureCategory.PARTIAL_RESULT,
            f"Query {request.query_id} returned a partial source result",
            query_id=request.query_id,
            affected_metrics=list(request.metric_ids),
        )
    if (
        type(result.total_row_count) is not int
        or result.total_row_count < 0
        or result.total_row_count != len(result.rows)
    ):
        raise StudioIngestionError(
            FailureCategory.PARTIAL_RESULT,
            f"Query {request.query_id} source row count does not match",
            query_id=request.query_id,
            affected_metrics=list(request.metric_ids),
        )
    if result.status not in {"success", "empty"}:
        raise StudioIngestionError(
            FailureCategory.QUERY_EXECUTION_FAILED,
            result.error
            or f"Query {request.query_id} returned source status {result.status}",
            query_id=request.query_id,
            affected_metrics=list(request.metric_ids),
        )
    missing_source_columns = [
        column
        for column in request.source_required_columns
        if column not in result.columns
    ]
    if missing_source_columns:
        raise StudioIngestionError(
            FailureCategory.MISSING_REQUIRED_COLUMNS,
            f"Query {request.query_id} source result is missing "
            f"{', '.join(missing_source_columns)} required by "
            f"{transformation.get('methodology_id')}",
            query_id=request.query_id,
            affected_metrics=list(request.metric_ids),
        )
    transformation_id = transformation.get("id")
    growth_transformers = {
        KYBERSWAP_GROWTH_DEPOSITS_TRANSFORMATION_ID: (
            prepare_kyberswap_growth_deposits,
            KYBERSWAP_GROWTH_DEPOSITS_COLUMNS,
            "referral deposits",
        ),
        KYBERSWAP_GROWTH_TVL_TRANSFORMATION_ID: (
            prepare_kyberswap_growth_attributed_tvl,
            KYBERSWAP_GROWTH_TVL_COLUMNS,
            "attributed TVL",
        ),
        KYBERSWAP_GROWTH_BREAKDOWN_TRANSFORMATION_ID: (
            prepare_kyberswap_growth_breakdown,
            KYBERSWAP_GROWTH_BREAKDOWN_COLUMNS,
            "referral deposit breakdown",
        ),
        KYBERSWAP_GROWTH_ACTIVITY_TRANSFORMATION_ID: (
            prepare_kyberswap_growth_activity,
            KYBERSWAP_GROWTH_ACTIVITY_COLUMNS,
            "deposit and depositor counts",
        ),
        KYBERSWAP_POST_REFERRAL_ACTIVITY_TRANSFORMATION_ID: (
            prepare_kyberswap_post_referral_activity,
            KYBERSWAP_POST_REFERRAL_ACTIVITY_COLUMNS,
            "post-referral activity",
        ),
    }
    depositor_intelligence_transformers = {
        KYBERSWAP_DEPOSITS_TRANSFORMATION_ID: (
            prepare_kyberswap_referral_deposits,
            KYBERSWAP_DEPOSITS_COLUMNS,
            "referral-deposit events",
        ),
        KYBERSWAP_ACTIVITY_TRANSFORMATION_ID: (
            prepare_kyberswap_etherfi_activity,
            KYBERSWAP_ACTIVITY_COLUMNS,
            "ether.fi activity events",
        ),
    }
    if transformation_id not in {
        "kyberswap_attributed_holdings",
        KYBERSWAP_SUMMARY_TRANSFORMATION_ID,
        *growth_transformers,
        *depositor_intelligence_transformers,
    }:
        raise StudioIngestionError(
            FailureCategory.TRANSFORMATION_FAILURE,
            f"Query {request.query_id} has an unsupported transformation",
            query_id=request.query_id,
        )
    if not isinstance(result.execution_id, str) or not result.execution_id:
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {request.query_id} transformation requires an execution ID",
            query_id=request.query_id,
        )
    if raw_metadata is None or raw_supporting_files is None:
        raw_metadata, raw_supporting_files = prepare_raw_provider_result(
            result,
            request,
        )
    script_path = str(transformation["script_path"])
    if transformation_id == "kyberswap_attributed_holdings":
        try:
            enrichment = enrich_kyberswap_attributed_holdings(
                result.rows,
                source_query_id=request.query_id,
                source_execution_id=result.execution_id,
                source_last_updated=result.execution_finished_at,
                # Keep row-level provenance stable when the same stored Dune
                # execution is fetched again. The artifact itself records the
                # current ingestion time separately as generated_at.
                generated_at=result.execution_finished_at,
                source_columns=result.columns,
            )
        except KyberSwapAttributionError as exc:
            raise StudioIngestionError(
                FailureCategory.TRANSFORMATION_FAILURE,
                f"Query {request.query_id} attribution failed: {exc}",
                query_id=request.query_id,
                affected_metrics=list(request.metric_ids),
                provider_execution_id=result.execution_id,
                provider_execution_finished_at=result.execution_finished_at,
            ) from exc
        transformed_columns = list(KYBERSWAP_ENRICHED_COLUMNS)
    elif transformation_id == KYBERSWAP_SUMMARY_TRANSFORMATION_ID:
        try:
            enrichment = prepare_kyberswap_campaign_summary(
                result.rows,
                source_query_id=request.query_id,
                source_execution_id=result.execution_id,
                # The stored execution's completion time is the authoritative
                # freshness timestamp for this aggregate source.
                source_last_updated=result.execution_finished_at,
                generated_at=result.execution_finished_at,
                source_columns=result.columns,
            )
        except KyberSwapCampaignSummaryError as exc:
            raise StudioIngestionError(
                FailureCategory.TRANSFORMATION_FAILURE,
                f"Query {request.query_id} campaign summary validation failed: {exc}",
                query_id=request.query_id,
                affected_metrics=list(request.metric_ids),
                provider_execution_id=result.execution_id,
                provider_execution_finished_at=result.execution_finished_at,
            ) from exc
        transformed_columns = list(enrichment.columns)
    elif transformation_id in growth_transformers:
        transformer, output_columns, transformation_label = growth_transformers[
            transformation_id
        ]
        try:
            enrichment = transformer(
                result.rows,
                source_query_id=request.query_id,
                source_execution_id=result.execution_id,
                source_last_updated=result.execution_finished_at,
                generated_at=result.execution_finished_at,
                source_columns=result.columns,
            )
        except KyberSwapGrowthError as exc:
            raise StudioIngestionError(
                FailureCategory.TRANSFORMATION_FAILURE,
                f"Query {request.query_id} {transformation_label} validation failed: {exc}",
                query_id=request.query_id,
                affected_metrics=list(request.metric_ids),
                provider_execution_id=result.execution_id,
                provider_execution_finished_at=result.execution_finished_at,
            ) from exc
        transformed_columns = list(output_columns)
    else:
        transformer, output_columns, transformation_label = (
            depositor_intelligence_transformers[transformation_id]
        )
        try:
            enrichment = transformer(
                result.rows,
                source_query_id=request.query_id,
                source_execution_id=result.execution_id,
                source_last_updated=result.execution_finished_at,
                generated_at=result.execution_finished_at,
                source_columns=result.columns,
            )
        except KyberSwapDepositorIntelligenceError as exc:
            raise StudioIngestionError(
                FailureCategory.TRANSFORMATION_FAILURE,
                f"Query {request.query_id} {transformation_label} validation failed: {exc}",
                query_id=request.query_id,
                affected_metrics=list(request.metric_ids),
                provider_execution_id=result.execution_id,
                provider_execution_finished_at=result.execution_finished_at,
            ) from exc
        transformed_columns = list(output_columns)
    transformed_result = StudioProviderResult(
        query_id=result.query_id,
        status="success" if enrichment.rows else "empty",
        columns=transformed_columns,
        rows=enrichment.rows,
        fetched_at=result.fetched_at,
        execution_started_at=result.execution_started_at,
        execution_finished_at=result.execution_finished_at,
        data_updated_at=result.data_updated_at,
        execution_id=result.execution_id,
        total_row_count=len(enrichment.rows),
        partial=False,
        provider_metadata={
            **result.provider_metadata,
            "source_row_count": len(result.rows),
            "transformation_id": transformation["id"],
        },
    )
    metadata = {
        "source_query_id": request.query_id,
        "source_execution_id": result.execution_id,
        "source_last_updated": enrichment.source_last_updated,
        **dict(raw_metadata),
        "methodology_id": transformation["methodology_id"],
        "methodology_version": transformation["version"],
        "script_path": script_path,
        "script_checksum": sha256_bytes((ROOT / script_path).read_bytes()),
        "tests_path": transformation["tests_path"],
        "transformation_summary": enrichment.summary,
        "data_quality_warnings": enrichment.warnings,
    }
    return PreparedProviderResult(
        result=transformed_result,
        metadata=metadata,
        supporting_files=dict(raw_supporting_files),
    )


def normalize_provider_result(
    result: StudioProviderResult,
    request: StudioQueryRequest,
    *,
    checked_at: datetime,
    mode: str,
    fetch_attempts: int,
    previous_entry: Mapping[str, object] | None = None,
    transformation_metadata: Mapping[str, object] | None = None,
    supporting_files: Mapping[str, bytes] | None = None,
) -> NormalizedQuery:
    query_id = request.query_id
    if result.query_id != query_id:
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} received result for query {result.query_id}",
            query_id=query_id,
        )
    if result.partial:
        raise StudioIngestionError(
            FailureCategory.PARTIAL_RESULT,
            f"Query {query_id} returned a partial result",
            query_id=query_id,
        )
    if result.status not in {"success", "empty"}:
        raise StudioIngestionError(
            FailureCategory.QUERY_EXECUTION_FAILED,
            result.error or f"Query {query_id} returned status {result.status}",
            query_id=query_id,
        )
    if (
        not isinstance(result.execution_id, str)
        or not DUNE_EXECUTION_ID_PATTERN.fullmatch(result.execution_id)
    ):
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} result has no valid execution ID",
            query_id=query_id,
        )
    if not isinstance(result.rows, list):
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} rows must be a list",
            query_id=query_id,
        )
    if (
        not isinstance(result.columns, list)
        or not result.columns
        or not all(isinstance(column, str) and column for column in result.columns)
        or len(result.columns) != len(set(result.columns))
    ):
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} columns must be a unique non-empty string list",
            query_id=query_id,
        )
    if type(result.total_row_count) is not int or result.total_row_count < 0:
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} result has no valid total row count",
            query_id=query_id,
        )
    if result.total_row_count != len(result.rows):
        raise StudioIngestionError(
            FailureCategory.PARTIAL_RESULT,
            f"Query {query_id} returned {len(result.rows)} of {result.total_row_count} rows",
            query_id=query_id,
        )

    returned_columns = list(result.columns)
    for row_index, row in enumerate(result.rows):
        if isinstance(row, dict):
            for column in row:
                if not isinstance(column, str) or not column:
                    raise StudioIngestionError(
                        FailureCategory.INVALID_ROW,
                        f"Query {query_id} row {row_index} has a non-string column key",
                        query_id=query_id,
                    )
                if column not in returned_columns:
                    returned_columns.append(column)
    missing_columns = [
        column for column in request.required_columns if column not in returned_columns
    ]
    if missing_columns:
        raise StudioIngestionError(
            FailureCategory.MISSING_REQUIRED_COLUMNS,
            f"Query {query_id} field required_columns is missing "
            f"{', '.join(missing_columns)}; update the query output or registry mapping",
            query_id=query_id,
            affected_metrics=list(request.metric_ids),
        )
    if not result.rows and not request.allow_empty:
        raise StudioIngestionError(
            FailureCategory.EMPTY_RESULT,
            f"Query {query_id} returned no rows but its metrics do not allow empty results",
            query_id=query_id,
            affected_metrics=list(request.metric_ids),
        )

    ordered_columns = list(request.required_columns)
    ordered_columns.extend(
        column
        for column in request.optional_columns
        if column in returned_columns and column not in ordered_columns
    )
    ordered_columns.extend(
        sorted(column for column in returned_columns if column not in ordered_columns)
    )
    normalized_rows: list[dict] = []
    for row_index, raw_row in enumerate(result.rows):
        if not isinstance(raw_row, dict):
            raise StudioIngestionError(
                FailureCategory.INVALID_ROW,
                f"Query {query_id} row {row_index} must be an object",
                query_id=query_id,
            )
        absent = [column for column in ordered_columns if column not in raw_row]
        if absent:
            raise StudioIngestionError(
                FailureCategory.INVALID_ROW,
                f"Query {query_id} row {row_index} is missing declared columns: "
                f"{', '.join(absent)}",
                query_id=query_id,
            )
        normalized_row: dict = {}
        for column in ordered_columns:
            value = raw_row[column]
            _ensure_json_scalar(
                value,
                query_id=query_id,
                row_index=row_index,
                column=column,
            )
            if column in request.value_columns:
                _ensure_numeric_value(
                    value,
                    query_id=query_id,
                    row_index=row_index,
                    column=column,
                )
            if value is not None and column in request.date_columns:
                try:
                    validate_data_date(value, field_name=f"query {query_id} {column}")
                except ValueError as exc:
                    raise StudioIngestionError(
                        FailureCategory.INVALID_DATE,
                        f"Query {query_id} row {row_index} column {column} has an invalid date",
                        query_id=query_id,
                    ) from exc
            if value is not None and column in request.address_columns:
                if not isinstance(value, str) or not EVM_ADDRESS_PATTERN.fullmatch(value):
                    raise StudioIngestionError(
                        FailureCategory.INVALID_VALUE,
                        f"Query {query_id} row {row_index} column {column} is not an EVM address",
                        query_id=query_id,
                    )
            if value is not None and column in request.transaction_columns:
                if not isinstance(value, str) or not EVM_TRANSACTION_PATTERN.fullmatch(value):
                    raise StudioIngestionError(
                        FailureCategory.INVALID_VALUE,
                        f"Query {query_id} row {row_index} column {column} is not an EVM transaction hash",
                        query_id=query_id,
                    )
            normalized_row[column] = (
                str(value)
                if type(value) is int and abs(value) > MAX_SAFE_JSON_INTEGER
                else value
            )
        normalized_rows.append(normalized_row)

    row_keys = [canonical_json_bytes(row) for row in normalized_rows]
    duplicate_row_count = len(row_keys) - len(set(row_keys))
    content_checksum = sha256_json(
        {"columns": ordered_columns, "rows": normalized_rows}
    )
    previous_checksum = str((previous_entry or {}).get("checksum") or "")
    checked_at_text = iso_utc(checked_at)
    data_changed_at = (
        str(previous_entry.get("data_changed_at"))
        if previous_entry
        and previous_checksum == content_checksum
        and previous_entry.get("data_changed_at")
        else str(result.data_updated_at)
    )
    parsed_timestamps: dict[str, datetime] = {}
    for field_name, timestamp_value in (
        ("fetched_at", result.fetched_at),
        ("execution_started_at", result.execution_started_at),
        ("execution_finished_at", result.execution_finished_at),
        ("data_updated_at", result.data_updated_at),
    ):
        try:
            parsed_timestamps[field_name] = parse_timestamp(
                timestamp_value,
                field_name=field_name,
            )
        except ValueError as exc:
            raise StudioIngestionError(
                FailureCategory.MALFORMED_RESPONSE,
                f"Query {query_id} has invalid {field_name}",
                query_id=query_id,
            ) from exc
    skew = MAX_PROVIDER_CLOCK_SKEW_SECONDS
    if (
        parsed_timestamps["execution_started_at"]
        > parsed_timestamps["execution_finished_at"]
    ):
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} execution timestamps are out of order",
            query_id=query_id,
        )
    if (
        parsed_timestamps["execution_finished_at"]
        - parsed_timestamps["fetched_at"]
    ).total_seconds() > skew:
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} execution_finished_at is implausibly in the future",
            query_id=query_id,
        )
    if (
        parsed_timestamps["data_updated_at"]
        - parsed_timestamps["fetched_at"]
    ).total_seconds() > skew:
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} data_updated_at is implausibly in the future",
            query_id=query_id,
        )
    if (
        parsed_timestamps["fetched_at"] - checked_at
    ).total_seconds() > skew:
        raise StudioIngestionError(
            FailureCategory.MALFORMED_RESPONSE,
            f"Query {query_id} fetched_at is implausibly in the future",
            query_id=query_id,
        )
    freshness_status = classify_freshness(
        result.execution_finished_at,
        request.freshness_policy,
        checked_at,
    )
    artifact = {
        "schema_version": 1,
        "ingestion_schema_version": INGESTION_SCHEMA_VERSION,
        "query_id": query_id,
        "query_url": request.query_url,
        "generated_at": checked_at_text,
        "fetched_at": result.fetched_at,
        "execution_id": result.execution_id,
        "execution_started_at": result.execution_started_at,
        "execution_finished_at": result.execution_finished_at,
        "data_updated_at": result.data_updated_at,
        "data_changed_at": data_changed_at,
        "status": "success" if normalized_rows else "empty",
        "freshness_status": freshness_status,
        "row_count": len(normalized_rows),
        "columns": ordered_columns,
        "rows": normalized_rows,
        "optional_columns": list(request.optional_columns),
        "dimension_columns": list(request.dimension_columns),
        "value_columns": list(request.value_columns),
        "allow_empty": request.allow_empty,
        "freshness_policy": dict(request.freshness_policy),
        "checksum": content_checksum,
        "duplicate_row_count": duplicate_row_count,
        "unexpected_columns": [
            column
            for column in ordered_columns
            if column not in request.required_columns
            and column not in request.optional_columns
        ],
        "validation_status": "valid",
        "mode": mode,
    }
    if request.source_label:
        artifact["source_label"] = request.source_label
    if transformation_metadata:
        artifact.update(dict(transformation_metadata))
    artifact["source_mode"] = str(
        result.provider_metadata.get("source_mode")
        or ("fixture" if mode == "fixture" else "live")
    )
    file_bytes = pretty_json_bytes(artifact)
    manifest_entry = {
        key: value for key, value in artifact.items() if key != "rows"
    }
    manifest_entry.update(
        {
            "data_file": request.result_file,
            "result_file": request.result_file,
            "file_checksum": sha256_bytes(file_bytes),
            "file_size_bytes": len(file_bytes),
            "metrics_using_query": list(request.metric_ids),
            "dashboard_ids": list(request.dashboard_ids),
            "required_columns": list(request.required_columns),
            "optional_columns": list(request.optional_columns),
            "dimension_columns": list(request.dimension_columns),
            "value_columns": list(request.value_columns),
            "fetch_attempts": fetch_attempts,
            "freshness_policy": dict(request.freshness_policy),
            "provider_mode": request.provider_mode,
            "source_required_columns": list(request.source_required_columns),
            "transformation": dict(request.transformation or {}),
        }
    )
    return NormalizedQuery(
        artifact=artifact,
        manifest_entry=manifest_entry,
        content_checksum=content_checksum,
        file_bytes=file_bytes,
        supporting_files=dict(supporting_files or {}),
    )


def _safe_snapshot_id(value: object) -> str:
    if not isinstance(value, str) or not SNAPSHOT_ID_PATTERN.fullmatch(value):
        raise ValueError("Studio snapshot ID is unsafe")
    return value


def _validate_snapshot_derived_artifacts(
    snapshot_dir: Path,
    manifest: Mapping[str, object],
) -> list[dict]:
    raw_entries = manifest.get("artifacts", [])
    if not isinstance(raw_entries, list) or not all(
        isinstance(entry, dict) for entry in raw_entries
    ):
        raise ValueError("Studio snapshot artifacts must be a list of mappings")
    query_entries = {
        int(entry["query_id"]): entry
        for entry in manifest["queries"]
        if isinstance(entry, dict) and isinstance(entry.get("query_id"), int)
    }
    required_sources = {
        KYBERSWAP_INTELLIGENCE_HOLDINGS_QUERY_ID,
        KYBERSWAP_DEPOSITS_QUERY_ID,
        KYBERSWAP_ACTIVITY_QUERY_ID,
    }
    expected_artifact_ids = (
        {KYBERSWAP_INTELLIGENCE_ID}
        if required_sources.issubset(query_entries)
        else set()
    )
    artifact_ids = [entry.get("artifact_id") for entry in raw_entries]
    if any(not isinstance(value, str) or not value for value in artifact_ids):
        raise ValueError("Studio snapshot artifact IDs must be non-empty strings")
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("Studio snapshot artifact IDs must be unique")
    if set(artifact_ids) != expected_artifact_ids:
        raise ValueError(
            "Studio snapshot derived artifacts do not match its query inventory"
        )

    validated: list[dict] = []
    for entry in raw_entries:
        artifact_id = str(entry["artifact_id"])
        if artifact_id != KYBERSWAP_INTELLIGENCE_ID:
            raise ValueError(f"Unsupported Studio derived artifact: {artifact_id}")
        if entry.get("id") != artifact_id or entry.get("data_source") != artifact_id:
            raise ValueError(
                f"Studio derived artifact {artifact_id} identifiers do not match"
            )
        if entry.get("data_file") != KYBERSWAP_INTELLIGENCE_FILE:
            raise ValueError(
                f"Studio derived artifact {artifact_id} data_file does not match"
            )
        data_path = snapshot_dir / KYBERSWAP_INTELLIGENCE_FILE
        file_bytes = data_path.read_bytes()
        payload_value = strict_json_loads(file_bytes)
        try:
            payload = validate_kyberswap_depositor_intelligence(payload_value)
        except KyberSwapDepositorIntelligenceError as exc:
            raise ValueError(
                f"Studio derived artifact {artifact_id} is invalid: {exc}"
            ) from exc
        for field_name in (
            "schema_version",
            "generated_at",
            "row_count",
            "columns",
            "source_query_ids",
            "source_executions",
            "checksum",
        ):
            if entry.get(field_name) != payload.get(field_name):
                raise ValueError(
                    f"Studio derived artifact {artifact_id} {field_name} does not match"
                )
        if entry.get("file_checksum") != sha256_bytes(file_bytes):
            raise ValueError(
                f"Studio derived artifact {artifact_id} file checksum does not match"
            )
        if entry.get("file_size_bytes") != len(file_bytes):
            raise ValueError(
                f"Studio derived artifact {artifact_id} file size does not match"
            )
        script_path = entry.get("script_path")
        if (
            script_path != "scripts/prepare_kyberswap_depositor_intelligence.py"
            or entry.get("script_checksum")
            != sha256_bytes((ROOT / str(script_path)).read_bytes())
        ):
            raise ValueError(
                f"Studio derived artifact {artifact_id} script checksum does not match"
            )
        if entry.get("tests_path") != "tests/test_kyberswap_depositor_intelligence.py":
            raise ValueError(
                f"Studio derived artifact {artifact_id} tests_path does not match"
            )
        source_executions = payload["source_executions"]
        for query_id in sorted(required_sources):
            query_entry = query_entries[query_id]
            source = source_executions.get(str(query_id))
            if not isinstance(source, dict) or source != {
                "execution_id": query_entry.get("execution_id"),
                "execution_finished_at": query_entry.get("execution_finished_at"),
            }:
                raise ValueError(
                    f"Studio derived artifact {artifact_id} query {query_id} provenance does not match"
                )
        validated.append(dict(entry))
    return validated


def validate_snapshot_directory(
    snapshot_dir: Path,
    *,
    query_requests: Mapping[int, StudioQueryRequest],
    required_query_ids: set[int] | None = None,
    expected_snapshot_id: str | None = None,
) -> dict:
    snapshot_dir = Path(snapshot_dir)
    contracts = {
        query_id: {
            "query_id": request.query_id,
            "query_url": request.query_url,
            "data_file": request.result_file,
            "data_source": request.data_source,
            "source_label": request.source_label or None,
            "source_labels": (
                [request.source_label] if request.source_label else []
            ),
            "provider_mode": request.provider_mode,
            "transformation": dict(request.transformation or {}),
            "source_required_columns": list(request.source_required_columns),
            "required_columns": list(request.required_columns),
            "optional_columns": list(request.optional_columns),
            "dimension_columns": list(request.dimension_columns),
            "value_columns": list(request.value_columns),
            "date_columns": list(request.date_columns),
            "address_columns": list(request.address_columns),
            "transaction_columns": list(request.transaction_columns),
            "metric_ids": list(request.metric_ids),
            "dashboard_ids": list(request.dashboard_ids),
            "is_exportable": request.is_exportable,
            "allow_empty": request.allow_empty,
            "freshness_policy": dict(request.freshness_policy),
        }
        for query_id, request in query_requests.items()
    }
    manifest_payload = strict_json_loads(
        (snapshot_dir / "manifest.json").read_bytes()
    )
    if not isinstance(manifest_payload, dict):
        raise ValueError("Studio snapshot manifest must be a mapping")
    manifest = validate_studio_generated_manifest(
        manifest_payload,
        query_contracts=contracts,
        required_query_ids=required_query_ids,
    )
    if (
        expected_snapshot_id is not None
        and manifest.get("snapshot_id") != expected_snapshot_id
    ):
        raise ValueError(
            "Studio snapshot manifest snapshot_id does not match its directory"
        )
    if manifest.get("ingestion_schema_version") != INGESTION_SCHEMA_VERSION:
        raise ValueError(
            f"Studio snapshot ingestion_schema_version must be {INGESTION_SCHEMA_VERSION}"
        )
    manifest_query_ids = {
        int(entry["query_id"])
        for entry in manifest["queries"]
    }
    scoped_query_requests = {
        query_id: query_requests[query_id]
        for query_id in manifest_query_ids
    }
    expected_contract_checksum = query_contract_checksum(scoped_query_requests)
    if manifest.get("contract_checksum") != expected_contract_checksum:
        raise ValueError("Studio snapshot registry-contract checksum does not match")
    expected_manifest_checksum = manifest.get("manifest_checksum")
    manifest_without_checksum = dict(manifest)
    manifest_without_checksum.pop("manifest_checksum", None)
    if expected_manifest_checksum != sha256_json(manifest_without_checksum):
        raise ValueError("Studio snapshot manifest checksum does not match")
    for entry in manifest["queries"]:
        path = snapshot_dir / entry["data_file"]
        payload_value = strict_json_loads(path.read_bytes())
        if not isinstance(payload_value, dict):
            raise ValueError(f"Studio query {entry['query_id']} file must be a mapping")
        payload = validate_studio_query_result(payload_value, entry)
        if entry.get("checksum") != sha256_json(
            {"columns": payload["columns"], "rows": payload["rows"]}
        ):
            raise ValueError(
                f"Studio query {entry['query_id']} content checksum does not match"
            )
        if entry.get("file_checksum") != sha256_bytes(path.read_bytes()):
            raise ValueError(
                f"Studio query {entry['query_id']} file checksum does not match"
            )
        if entry.get("file_size_bytes") != path.stat().st_size:
            raise ValueError(
                f"Studio query {entry['query_id']} file size does not match"
            )
        raw_data_file = entry.get("raw_data_file")
        if raw_data_file is not None:
            if (
                not isinstance(raw_data_file, str)
                or Path(raw_data_file).name != raw_data_file
                or raw_data_file != f"raw_query_{entry['query_id']}.json"
            ):
                raise ValueError(
                    f"Studio query {entry['query_id']} raw_data_file is unsafe"
                )
            raw_path = snapshot_dir / raw_data_file
            raw_bytes = raw_path.read_bytes()
            raw_value = strict_json_loads(raw_bytes)
            if not isinstance(raw_value, dict):
                raise ValueError(
                    f"Studio query {entry['query_id']} raw result must be a mapping"
                )
            for field_name, expected_value in (
                ("query_id", entry["query_id"]),
                ("query_url", entry["query_url"]),
                ("execution_id", entry["execution_id"]),
                ("row_count", entry.get("raw_row_count")),
                ("columns", entry.get("raw_columns")),
                ("checksum", entry.get("raw_checksum")),
            ):
                if raw_value.get(field_name) != expected_value:
                    raise ValueError(
                        f"Studio query {entry['query_id']} raw {field_name} does not match"
                    )
            raw_rows = raw_value.get("rows")
            if not isinstance(raw_rows, list) or len(raw_rows) != raw_value["row_count"]:
                raise ValueError(
                    f"Studio query {entry['query_id']} raw row count does not match"
                )
            if entry.get("raw_checksum") != sha256_json(
                {"columns": raw_value["columns"], "rows": raw_rows}
            ):
                raise ValueError(
                    f"Studio query {entry['query_id']} raw checksum does not match"
                )
            if entry.get("raw_file_checksum") != sha256_bytes(raw_bytes):
                raise ValueError(
                    f"Studio query {entry['query_id']} raw file checksum does not match"
                )
            if entry.get("raw_file_size_bytes") != raw_path.stat().st_size:
                raise ValueError(
                    f"Studio query {entry['query_id']} raw file size does not match"
                )
            script_path = entry.get("script_path")
            if (
                not isinstance(script_path, str)
                or entry.get("script_checksum")
                != sha256_bytes((ROOT / script_path).read_bytes())
            ):
                raise ValueError(
                    f"Studio query {entry['query_id']} transformation script checksum does not match"
                )
    artifacts = _validate_snapshot_derived_artifacts(snapshot_dir, manifest)
    source_checksum = _source_data_checksum(manifest["queries"], artifacts)
    if manifest.get("source_data_checksum") != source_checksum:
        raise ValueError("Studio snapshot source-data checksum does not match")
    return manifest


class SnapshotStore:
    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.root = Path(root)
        self.snapshots_dir = self.root / "snapshots"
        self.attempts_dir = self.root / "attempts"
        self.state_path = self.root / "state.json"
        self.clock = clock

    def initialize(self) -> None:
        if self.root.is_symlink():
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                "Studio output root must not be a symlink",
            )
        self.root.mkdir(parents=True, exist_ok=True)
        if self.snapshots_dir.is_symlink() or self.attempts_dir.is_symlink():
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                "Studio snapshot and attempt directories must not be symlinks",
            )
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.attempts_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def refresh_lock(self) -> Iterator[None]:
        """Serialize refreshes for this output root across local processes."""
        root_key = sha256_bytes(str(self.root.resolve()).encode("utf-8"))[:20]
        lock_path = Path(tempfile.gettempdir()) / f"studio-refresh-{root_key}.lock"
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                "Could not create the Studio refresh lock",
            ) from exc
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StudioIngestionError(
                    FailureCategory.WRITE_FAILURE,
                    "Another Studio refresh is already running for this output directory",
                ) from exc
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def load_state(self) -> dict | None:
        if self.state_path.is_symlink():
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                "Studio generated state.json must not be a symlink",
            )
        if not self.state_path.is_file():
            return None
        try:
            payload = strict_json_loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError) as exc:
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                "Studio generated state.json is malformed",
            ) from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != SNAPSHOT_STATE_SCHEMA_VERSION:
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                f"Studio generated state schema_version must be {SNAPSHOT_STATE_SCHEMA_VERSION}",
            )
        current_id = payload.get("current_snapshot_id")
        if current_id is not None:
            _safe_snapshot_id(current_id)
        previous_id = payload.get("previous_snapshot_id")
        if previous_id is not None:
            _safe_snapshot_id(previous_id)
        return payload

    def current_snapshot_dir(self) -> Path | None:
        state = self.load_state()
        if not state or not state.get("current_snapshot_id"):
            return None
        if self.snapshots_dir.is_symlink():
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                "Studio generated snapshots directory must not be a symlink",
            )
        directory = self.snapshots_dir / _safe_snapshot_id(
            state["current_snapshot_id"]
        )
        if directory.is_symlink():
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                "Active Studio snapshot must not be a symlink",
            )
        return directory

    def current_manifest(
        self,
        query_requests: Mapping[int, StudioQueryRequest],
        *,
        required_query_ids: set[int] | None = None,
    ) -> dict | None:
        directory = self.current_snapshot_dir()
        if directory is None:
            return None
        try:
            manifest = validate_snapshot_directory(
                directory,
                query_requests=query_requests,
                required_query_ids=required_query_ids,
                expected_snapshot_id=directory.name,
            )
        except (OSError, ValueError) as exc:
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                f"Active Studio snapshot is invalid: {exc}",
            ) from exc
        state = self.load_state() or {}
        if state.get("current_manifest_checksum") != manifest.get(
            "manifest_checksum"
        ):
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                "Studio state checksum does not match the active manifest",
            )
        return manifest

    def _atomic_write(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(pretty_json_bytes(payload))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
            _fsync_directory(path.parent)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                f"Could not atomically write {path.name}",
            ) from exc

    def new_attempt_id(self, checked_at: datetime) -> str:
        stamp = checked_at.astimezone(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
        return f"attempt-{stamp}-{uuid4().hex[:8]}"

    def record_attempt(self, attempt_id: str, payload: dict) -> Path:
        _safe_snapshot_id(attempt_id)
        path = self.attempts_dir / attempt_id / "attempt.json"
        self._atomic_write(path, payload)
        return path

    def record_attempt_file(
        self,
        attempt_id: str,
        file_name: str,
        payload: bytes,
    ) -> Path:
        """Durably retain fetched source bytes even if enrichment rejects them."""
        _safe_snapshot_id(attempt_id)
        if Path(file_name).name != file_name:
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                f"Unsafe Studio attempt filename: {file_name}",
            )
        path = self.attempts_dir / attempt_id / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _durable_write_bytes(path, payload)
            _fsync_directory(path.parent)
        except OSError as exc:
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                f"Could not preserve fetched Studio source {file_name}",
            ) from exc
        return path

    def update_failed_state(
        self,
        *,
        attempt_id: str,
        checked_at: str,
        failures: list[dict],
        active_snapshot_usable: bool = True,
    ) -> None:
        state = self.load_state() or {
            "schema_version": SNAPSHOT_STATE_SCHEMA_VERSION,
            "current_snapshot_id": None,
            "previous_snapshot_id": None,
            "current_manifest_checksum": None,
        }
        state.update(
            {
                "last_checked_at": checked_at,
                "latest_attempt_id": attempt_id,
                "latest_attempt_status": "failed",
                "using_previous": bool(
                    active_snapshot_usable and state.get("current_snapshot_id")
                ),
                "latest_failure": {
                    "failed_query_ids": sorted(
                        failure["query_id"]
                        for failure in failures
                        if failure.get("query_id") is not None
                    ),
                    "categories": sorted(
                        {str(failure["category"]) for failure in failures}
                    ),
                    "summary": f"{len(failures)} query refresh failure(s)",
                },
            }
        )
        self._atomic_write(self.state_path, state)

    def update_unchanged_state(
        self,
        *,
        attempt_id: str,
        checked_at: str,
        partial_failures: list[dict] | None = None,
    ) -> dict:
        state = self.load_state()
        if not state or not state.get("current_snapshot_id"):
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                "Cannot record an unchanged refresh without a current snapshot",
            )
        state.update(
            {
                "last_checked_at": checked_at,
                "latest_attempt_id": attempt_id,
                "latest_attempt_status": "partial" if partial_failures else "unchanged",
                "using_previous": bool(partial_failures),
                "latest_failure": (
                    {
                        "failed_query_ids": sorted(
                            failure["query_id"]
                            for failure in partial_failures
                            if failure.get("query_id") is not None
                        ),
                        "categories": sorted(
                            {str(failure["category"]) for failure in partial_failures}
                        ),
                        "summary": "Some queries reused the previous validated result",
                    }
                    if partial_failures
                    else None
                ),
            }
        )
        if not partial_failures:
            state["last_successful_fetch_at"] = checked_at
        self._atomic_write(self.state_path, state)
        return state

    def promote(
        self,
        *,
        snapshot_id: str,
        manifest: dict,
        query_files: Mapping[str, bytes],
        query_requests: Mapping[int, StudioQueryRequest],
        attempt_id: str,
        checked_at: str,
        keep_previous: int,
        previous_snapshot_id: str | None,
        required_query_ids: set[int],
        partial_failures: list[dict] | None = None,
    ) -> dict:
        snapshot_id = _safe_snapshot_id(snapshot_id)
        self.initialize()
        staging_dir = Path(
            tempfile.mkdtemp(prefix=".studio-snapshot-", dir=self.snapshots_dir)
        )
        try:
            for file_name, file_bytes in query_files.items():
                if Path(file_name).name != file_name:
                    raise StudioIngestionError(
                        FailureCategory.WRITE_FAILURE,
                        f"Unsafe Studio result filename: {file_name}",
                    )
                _durable_write_bytes(staging_dir / file_name, file_bytes)
            _durable_write_bytes(
                staging_dir / "manifest.json",
                pretty_json_bytes(manifest),
            )
            _fsync_directory(staging_dir)
            validate_snapshot_directory(
                staging_dir,
                query_requests=query_requests,
                required_query_ids=required_query_ids,
                expected_snapshot_id=snapshot_id,
            )
            final_dir = self.snapshots_dir / snapshot_id
            if final_dir.exists():
                existing_manifest = validate_snapshot_directory(
                    final_dir,
                    query_requests=query_requests,
                    required_query_ids=required_query_ids,
                    expected_snapshot_id=snapshot_id,
                )
                if existing_manifest.get("manifest_checksum") != manifest.get(
                    "manifest_checksum"
                ):
                    raise StudioIngestionError(
                        FailureCategory.MANIFEST_FAILURE,
                        "Studio snapshot ID collision has different validated content",
                    )
                shutil.rmtree(staging_dir)
                _fsync_directory(self.snapshots_dir)
            else:
                os.replace(staging_dir, final_dir)
                _fsync_directory(self.snapshots_dir)
            old_state = self.load_state() or {}
            previous_candidate = previous_snapshot_id
            if previous_candidate == snapshot_id:
                previous_candidate = old_state.get("previous_snapshot_id")
            if previous_candidate and not (
                self.snapshots_dir / str(previous_candidate)
            ).is_dir():
                previous_candidate = None
            if keep_previous <= 0:
                previous_candidate = None
            new_state = {
                "schema_version": SNAPSHOT_STATE_SCHEMA_VERSION,
                "current_snapshot_id": snapshot_id,
                "previous_snapshot_id": previous_candidate,
                "current_manifest_checksum": manifest["manifest_checksum"],
                "updated_at": checked_at,
                "last_checked_at": checked_at,
                "last_successful_fetch_at": manifest["last_successful_fetch_at"],
                "latest_attempt_id": attempt_id,
                "latest_attempt_status": "partial" if partial_failures else "success",
                "using_previous": bool(partial_failures),
                "latest_failure": (
                    {
                        "failed_query_ids": sorted(
                            failure["query_id"]
                            for failure in partial_failures
                            if failure.get("query_id") is not None
                        ),
                        "categories": sorted(
                            {str(failure["category"]) for failure in partial_failures}
                        ),
                        "summary": "Some queries reused the previous validated result",
                    }
                    if partial_failures
                    else None
                ),
            }
            self._atomic_write(self.state_path, new_state)
            self._prune_snapshots(
                new_state,
                keep_previous=max(0, keep_previous),
                query_requests=query_requests,
                required_query_ids=required_query_ids,
            )
            return new_state
        except StudioIngestionError:
            raise
        except ValueError as exc:
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                f"Could not validate the candidate Studio snapshot: {exc}",
            ) from exc
        except OSError as exc:
            raise StudioIngestionError(
                FailureCategory.WRITE_FAILURE,
                "Could not promote the validated Studio snapshot",
            ) from exc
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def _prune_snapshots(
        self,
        state: dict,
        *,
        keep_previous: int,
        query_requests: Mapping[int, StudioQueryRequest],
        required_query_ids: set[int],
    ) -> None:
        if keep_previous < 0:
            return
        current_id = state.get("current_snapshot_id")
        previous_id = state.get("previous_snapshot_id")
        protected_ids = {
            snapshot_id
            for snapshot_id in (current_id, previous_id)
            if isinstance(snapshot_id, str)
        }
        try:
            raw_candidates = [
                path
                for path in self.snapshots_dir.iterdir()
                if path.is_dir()
                and not path.name.startswith(".")
                and path.name not in protected_ids
            ]
        except OSError:
            return
        valid_candidates: list[Path] = []
        for path in raw_candidates:
            try:
                validate_snapshot_directory(
                    path,
                    query_requests=query_requests,
                    required_query_ids=required_query_ids,
                    expected_snapshot_id=path.name,
                )
            except (OSError, ValueError):
                try:
                    shutil.rmtree(path)
                except OSError:
                    pass
                continue
            valid_candidates.append(path)
        try:
            candidates = sorted(
                valid_candidates,
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        protected_previous_count = 1 if previous_id else 0
        additional_to_keep = max(0, keep_previous - protected_previous_count)
        for path in candidates[additional_to_keep:]:
            try:
                shutil.rmtree(path)
            except OSError:
                # Retention is best-effort after the active pointer is safely written.
                continue
        try:
            _fsync_directory(self.snapshots_dir)
        except OSError:
            pass


def _manifest_query_map(manifest: Mapping[str, object] | None) -> dict[int, dict]:
    if not manifest or not isinstance(manifest.get("queries"), list):
        return {}
    return {
        int(entry["query_id"]): entry
        for entry in manifest["queries"]
        if isinstance(entry, dict) and isinstance(entry.get("query_id"), int)
    }


def _source_checksum_rows(entries: list[dict]) -> list[list[object]]:
    values: list[list[object]] = []
    for entry in sorted(entries, key=lambda item: int(item["query_id"])):
        item: list[object] = [entry["query_id"], entry["checksum"]]
        if entry.get("raw_checksum") is not None:
            item.append(entry["raw_checksum"])
        values.append(item)
    return values


def _source_data_checksum(
    entries: list[dict],
    artifacts: list[dict] | None = None,
) -> str:
    artifact_entries = sorted(
        artifacts or [], key=lambda item: str(item["artifact_id"])
    )
    if not artifact_entries:
        # Preserve the established checksum for snapshots without derived data.
        return sha256_json(_source_checksum_rows(entries))
    return sha256_json(
        {
            "queries": _source_checksum_rows(entries),
            "artifacts": [
                [entry["artifact_id"], entry["checksum"]]
                for entry in artifact_entries
            ],
        }
    )


def _snapshot_id(mode: str, generated_at: datetime, source_checksum: str) -> str:
    stamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    return f"{mode}-{stamp}-{source_checksum[:12]}"


def _build_manifest(
    *,
    checked_at: datetime,
    mode: str,
    dashboard_count: int,
    metric_count: int,
    entries: list[dict],
    snapshot_id: str,
    previous_snapshot_id: str | None,
    changed_query_ids: list[int],
    reused_query_ids: list[int],
    contract_checksum: str,
    last_successful_fetch_at: str,
    artifacts: list[dict] | None = None,
) -> dict:
    entries = sorted(entries, key=lambda entry: int(entry["query_id"]))
    artifacts = sorted(
        artifacts or [], key=lambda entry: str(entry["artifact_id"])
    )
    source_checksum = _source_data_checksum(entries, artifacts)
    data_updated_values = [
        parse_timestamp(entry["data_updated_at"], field_name="data_updated_at")
        for entry in entries
    ]
    display_updated_at = iso_utc(min(data_updated_values))
    parse_timestamp(
        last_successful_fetch_at,
        field_name="last_successful_fetch_at",
    )
    manifest = {
        "schema_version": 1,
        "ingestion_schema_version": INGESTION_SCHEMA_VERSION,
        "ingestion_tool_version": INGESTION_TOOL_VERSION,
        "snapshot_id": snapshot_id,
        "previous_snapshot_id": previous_snapshot_id,
        "generated_at": iso_utc(checked_at),
        "display_updated_at": display_updated_at,
        "data_updated_at": display_updated_at,
        "last_checked_at": iso_utc(checked_at),
        "last_successful_fetch_at": last_successful_fetch_at,
        "source": (
            "local_fixture"
            if mode == "fixture"
            else "mixed_fixture_and_dune_latest_result"
            if mode == "mixed"
            else "dune_api"
        ),
        "mode": mode,
        "validation_status": "valid",
        "dashboard_count": dashboard_count,
        "metric_count": metric_count,
        "unique_query_count": len(entries),
        "changed_query_ids": sorted(changed_query_ids),
        "reused_query_ids": sorted(reused_query_ids),
        "source_data_checksum": source_checksum,
        "contract_checksum": contract_checksum,
        "queries": entries,
        "artifacts": artifacts,
    }
    manifest["manifest_checksum"] = sha256_json(manifest)
    return manifest


def _copy_previous_query(
    snapshot_dir: Path,
    entry: dict,
) -> NormalizedQuery:
    file_name = str(entry["data_file"])
    file_bytes = (snapshot_dir / file_name).read_bytes()
    artifact = strict_json_loads(file_bytes)
    if not isinstance(artifact, dict):
        raise ValueError(f"Studio query artifact {file_name} must be a mapping")
    supporting_files: dict[str, bytes] = {}
    raw_data_file = entry.get("raw_data_file")
    if raw_data_file is not None:
        if not isinstance(raw_data_file, str) or Path(raw_data_file).name != raw_data_file:
            raise ValueError("Studio raw query filename is unsafe")
        supporting_files[raw_data_file] = (snapshot_dir / raw_data_file).read_bytes()
    return NormalizedQuery(
        artifact=artifact,
        manifest_entry=dict(entry),
        content_checksum=str(entry["checksum"]),
        file_bytes=file_bytes,
        supporting_files=supporting_files,
    )


def _prepare_depositor_intelligence_artifact(
    normalized: Mapping[int, NormalizedQuery],
) -> NormalizedDerivedArtifact | None:
    source_query_ids = {
        KYBERSWAP_INTELLIGENCE_HOLDINGS_QUERY_ID,
        KYBERSWAP_DEPOSITS_QUERY_ID,
        KYBERSWAP_ACTIVITY_QUERY_ID,
    }
    if not source_query_ids.issubset(normalized):
        return None
    source_artifacts = {
        query_id: normalized[query_id].artifact for query_id in source_query_ids
    }
    try:
        derived = build_kyberswap_depositor_intelligence(
            source_artifacts[KYBERSWAP_INTELLIGENCE_HOLDINGS_QUERY_ID]["rows"],
            source_artifacts[KYBERSWAP_DEPOSITS_QUERY_ID]["rows"],
            source_artifacts[KYBERSWAP_ACTIVITY_QUERY_ID]["rows"],
            source_execution_ids={
                query_id: str(artifact["execution_id"])
                for query_id, artifact in source_artifacts.items()
            },
        )
        payload = validate_kyberswap_depositor_intelligence(derived.payload)
    except (KeyError, KyberSwapDepositorIntelligenceError) as exc:
        raise StudioIngestionError(
            FailureCategory.TRANSFORMATION_FAILURE,
            f"Derived {KYBERSWAP_INTELLIGENCE_ID} validation failed: {exc}",
            affected_metrics=[
                metric_id
                for query_id in sorted(source_query_ids)
                for metric_id in normalized[query_id].manifest_entry.get(
                    "metrics_using_query", []
                )
            ],
        ) from exc
    file_bytes = pretty_json_bytes(payload)
    script_path = "scripts/prepare_kyberswap_depositor_intelligence.py"
    content_checksum = str(payload["checksum"])
    manifest_entry = {
        "id": KYBERSWAP_INTELLIGENCE_ID,
        "artifact_id": KYBERSWAP_INTELLIGENCE_ID,
        "data_source": KYBERSWAP_INTELLIGENCE_ID,
        "data_file": KYBERSWAP_INTELLIGENCE_FILE,
        "schema_version": payload["schema_version"],
        "generated_at": payload["generated_at"],
        "row_count": payload["row_count"],
        "columns": payload["columns"],
        "source_query_ids": payload["source_query_ids"],
        "source_executions": payload["source_executions"],
        "checksum": content_checksum,
        "file_checksum": sha256_bytes(file_bytes),
        "file_size_bytes": len(file_bytes),
        "methodology_id": KYBERSWAP_INTELLIGENCE_METHODOLOGY_ID,
        "methodology_version": KYBERSWAP_INTELLIGENCE_METHODOLOGY_VERSION,
        "script_path": script_path,
        "script_checksum": sha256_bytes((ROOT / script_path).read_bytes()),
        "tests_path": "tests/test_kyberswap_depositor_intelligence.py",
        "transformation_summary": derived.summary,
        "data_quality_warnings": derived.warnings,
    }
    return NormalizedDerivedArtifact(
        payload=payload,
        manifest_entry=manifest_entry,
        content_checksum=content_checksum,
        file_bytes=file_bytes,
    )


def _abort_refresh(
    *,
    store: SnapshotStore,
    attempt_id: str,
    checked_at: str,
    mode: str,
    selected_query_ids: set[int],
    failures: list[StudioIngestionError],
    state: Mapping[str, object],
    active_snapshot_usable: bool,
) -> None:
    failure_payloads = [failure.as_dict() for failure in failures]
    attempt_payload = {
        "schema_version": INGESTION_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "checked_at": checked_at,
        "mode": mode,
        "status": "failed",
        "selected_query_ids": sorted(selected_query_ids),
        "failures": failure_payloads,
        "active_snapshot_id": state.get("current_snapshot_id"),
        "active_snapshot_preserved": bool(
            active_snapshot_usable and state.get("current_snapshot_id")
        ),
    }
    store.record_attempt(attempt_id, attempt_payload)
    store.update_failed_state(
        attempt_id=attempt_id,
        checked_at=checked_at,
        failures=failure_payloads,
        active_snapshot_usable=active_snapshot_usable,
    )
    summary = "; ".join(
        (
            f"query {failure.query_id}: {failure.category.value}"
            if failure.query_id is not None
            else f"derived artifact: {failure.category.value}"
        )
        for failure in failures
    )
    preservation_message = (
        "active snapshot preserved"
        if active_snapshot_usable and state.get("current_snapshot_id")
        else "no usable active snapshot is available"
    )
    first = failures[0]
    raise StudioIngestionError(
        first.category,
        f"Studio refresh failed; {preservation_message}. {summary}",
        query_id=first.query_id,
        affected_metrics=[
            metric_id
            for failure in failures
            for metric_id in failure.affected_metrics
        ],
        provider_execution_id=first.provider_execution_id,
        provider_execution_finished_at=first.provider_execution_finished_at,
    )


def _refresh_studio_data_unlocked(
    client: StudioLatestResultClient,
    *,
    output_root: Path = DEFAULT_STUDIO_OUTPUT_ROOT,
    mode: str,
    query_ids: set[int] | None = None,
    dashboard_ids: set[str] | None = None,
    keep_previous: int = 1,
    force: bool = False,
    allow_partial: bool = False,
    timeout_seconds: float = 30.0,
    retry_policy: RetryPolicy = RetryPolicy(),
    clock: Callable[[], datetime] = utc_now,
    sleeper: Callable[[float], None] = time.sleep,
    logger: Callable[[str], None] | None = None,
) -> RefreshSummary:
    if mode not in {"fixture", "live", "mixed"}:
        raise ValueError("Studio ingestion mode must be fixture, live, or mixed")
    if type(keep_previous) is not int or keep_previous < 0:
        raise ValueError("keep_previous must be a non-negative integer")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be a finite positive number")
    dashboards, _, requests = load_query_requests()
    available_dashboards = {str(dashboard["id"]) for dashboard in dashboards}
    generated_dashboard_ids = {
        str(dashboard["id"])
        for dashboard in dashboards
        if dashboard.get("data_mode") == "generated"
    }
    default_query_ids = generated_query_ids(dashboards, requests)
    if not default_query_ids:
        raise ValueError("Studio has no generated dashboard queries to refresh")
    if dashboard_ids:
        unknown = sorted(dashboard_ids - available_dashboards)
        if unknown:
            raise ValueError(f"Unknown Studio dashboards: {', '.join(unknown)}")
        if mode in {"live", "mixed"}:
            demo_dashboards = sorted(dashboard_ids - generated_dashboard_ids)
            if demo_dashboards:
                raise ValueError(
                    "Live Studio refresh only supports generated dashboards: "
                    + ", ".join(demo_dashboards)
                )
    explicit_selection = bool(query_ids or dashboard_ids)
    selected_ids = set(requests) if explicit_selection else set(default_query_ids)
    if query_ids:
        unknown_queries = sorted(query_ids - set(requests))
        if unknown_queries:
            raise ValueError(
                "Unknown Studio query IDs: "
                + ", ".join(str(query_id) for query_id in unknown_queries)
            )
        selected_ids &= query_ids
    if dashboard_ids:
        selected_ids &= {
            query_id
            for query_id, request in requests.items()
            if set(request.dashboard_ids) & dashboard_ids
        }
    if not selected_ids:
        raise ValueError("Studio refresh selection contains no queries")
    if mode in {"live", "mixed"}:
        unsupported_live_queries = sorted(
            query_id
            for query_id in selected_ids
            if not generated_dashboard_ids.intersection(
                requests[query_id].dashboard_ids
            )
        )
        if unsupported_live_queries:
            raise ValueError(
                "Live Studio refresh cannot fetch demo-only query IDs: "
                + ", ".join(str(query_id) for query_id in unsupported_live_queries)
            )

    checked_at = clock().astimezone(timezone.utc)
    checked_at_text = iso_utc(checked_at)
    store = SnapshotStore(output_root, clock=clock)
    store.initialize()
    attempt_id = store.new_attempt_id(checked_at)
    state = store.load_state() or {}
    current_dir = store.current_snapshot_dir()
    current_manifest = None
    active_snapshot_usable = False
    if current_dir is not None:
        try:
            current_manifest = store.current_manifest(
                requests,
                required_query_ids=default_query_ids,
            )
        except (StudioIngestionError, ValueError) as exc:
            replacement_scope = default_query_ids | selected_ids
            if selected_ids != replacement_scope:
                raise StudioIngestionError(
                    FailureCategory.MANIFEST_FAILURE,
                    "A filtered Studio refresh cannot merge with an invalid current "
                    f"snapshot: {exc}",
                ) from exc
            if logger:
                logger(
                    "current snapshot is incompatible with the validated registry; "
                    "building a complete replacement"
                )
            current_dir = None
    current_mode_matches = bool(
        current_manifest and current_manifest.get("mode") == mode
    )
    active_snapshot_usable = current_manifest is not None
    if current_manifest is not None and not current_mode_matches and logger:
        logger(
            "active snapshot mode differs from this refresh; its query files "
            "will not be reused"
        )
    reusable_current_dir = current_dir if current_mode_matches else None
    current_entries = (
        _manifest_query_map(current_manifest)
        if current_mode_matches
        else {}
    )
    target_query_ids = set(default_query_ids)
    if explicit_selection:
        target_query_ids.update(selected_ids)
        if current_mode_matches:
            target_query_ids.update(current_entries)
    if selected_ids != target_query_ids and reusable_current_dir is None:
        raise StudioIngestionError(
            FailureCategory.MANIFEST_FAILURE,
            "A filtered Studio refresh needs a same-mode current snapshot to merge with",
        )

    normalized: dict[int, NormalizedQuery] = {}
    failures: list[StudioIngestionError] = []
    for query_id in sorted(selected_ids):
        request = requests[query_id]
        if logger:
            logger(f"query {query_id}: fetching once for {len(request.metric_ids)} metric(s)")
        try:
            result, attempt_count = fetch_latest_result_with_retry(
                client,
                request,
                retry_policy=retry_policy,
                timeout_seconds=timeout_seconds,
                sleeper=sleeper,
                logger=logger,
            )
            raw_metadata, raw_supporting_files = prepare_raw_provider_result(
                result,
                request,
            )
            for raw_file_name, raw_file_bytes in raw_supporting_files.items():
                store.record_attempt_file(
                    attempt_id,
                    raw_file_name,
                    raw_file_bytes,
                )
            prepared = prepare_provider_result(
                result,
                request,
                checked_at=checked_at,
                raw_metadata=raw_metadata,
                raw_supporting_files=raw_supporting_files,
            )
            normalized[query_id] = normalize_provider_result(
                prepared.result,
                request,
                checked_at=checked_at,
                mode=mode,
                fetch_attempts=attempt_count,
                previous_entry=current_entries.get(query_id),
                transformation_metadata=prepared.metadata,
                supporting_files=prepared.supporting_files,
            )
        except StudioIngestionError as exc:
            exc.affected_metrics = list(request.metric_ids)
            failures.append(exc)
        except Exception as exc:
            failures.append(
                StudioIngestionError(
                    FailureCategory.MALFORMED_RESPONSE,
                    f"Query {query_id} client raised an unexpected "
                    f"{type(exc).__name__}",
                    query_id=query_id,
                    affected_metrics=list(request.metric_ids),
                )
            )

    reused_query_ids: list[int] = []
    partial_failure_payloads: list[dict] = []
    if failures and allow_partial and reusable_current_dir is not None:
        unresolved: list[StudioIngestionError] = []
        for failure in failures:
            if failure.query_id in current_entries:
                partial_failure_payloads.append(failure.as_dict())
                normalized[failure.query_id] = _copy_previous_query(
                    reusable_current_dir,
                    current_entries[failure.query_id],
                )
                reused_query_ids.append(int(failure.query_id))
            else:
                unresolved.append(failure)
        failures = unresolved

    if failures:
        _abort_refresh(
            store=store,
            attempt_id=attempt_id,
            checked_at=checked_at_text,
            mode=mode,
            selected_query_ids=selected_ids,
            failures=failures,
            state=state,
            active_snapshot_usable=active_snapshot_usable,
        )

    if reusable_current_dir is not None:
        for query_id in sorted(target_query_ids - selected_ids):
            entry = current_entries.get(query_id)
            if entry is None:
                raise StudioIngestionError(
                    FailureCategory.MANIFEST_FAILURE,
                    f"Current snapshot cannot supply unselected query {query_id}",
                )
            normalized[query_id] = _copy_previous_query(
                reusable_current_dir,
                entry,
            )
            reused_query_ids.append(query_id)

    derived_artifacts: list[NormalizedDerivedArtifact] = []
    depositor_intelligence: NormalizedDerivedArtifact | None = None
    try:
        depositor_intelligence = _prepare_depositor_intelligence_artifact(normalized)
    except StudioIngestionError as exc:
        _abort_refresh(
            store=store,
            attempt_id=attempt_id,
            checked_at=checked_at_text,
            mode=mode,
            selected_query_ids=selected_ids,
            failures=[exc],
            state=state,
            active_snapshot_usable=active_snapshot_usable,
        )
    if depositor_intelligence is not None:
        derived_artifacts.append(depositor_intelligence)

    current_artifact_entries = {
        str(entry.get("artifact_id")): entry
        for entry in (current_manifest or {}).get("artifacts", [])
        if isinstance(entry, dict) and isinstance(entry.get("artifact_id"), str)
    }
    all_same_content = (
        bool(current_entries)
        and set(current_entries) == target_query_ids
        and set(normalized) == target_query_ids
        and all(
            query_id in current_entries
            and current_entries[query_id].get("checksum") == value.content_checksum
            for query_id, value in normalized.items()
        )
    )
    latest_result_metadata_fields = (
        "execution_id",
        "execution_started_at",
        "execution_finished_at",
        "data_updated_at",
        "freshness_status",
        "status",
        "source_mode",
        "source_last_updated",
        "raw_checksum",
        "methodology_id",
        "methodology_version",
        "script_checksum",
    )
    all_same_latest_results = all_same_content and all(
        all(
            current_entries[query_id].get(field_name)
            == value.manifest_entry.get(field_name)
            for field_name in latest_result_metadata_fields
        )
        for query_id, value in normalized.items()
    )
    all_same_latest_results = all_same_latest_results and (
        set(current_artifact_entries)
        == {value.manifest_entry["artifact_id"] for value in derived_artifacts}
        and all(
            current_artifact_entries.get(value.manifest_entry["artifact_id"], {}).get(
                "checksum"
            )
            == value.content_checksum
            and current_artifact_entries.get(
                value.manifest_entry["artifact_id"], {}
            ).get("script_checksum")
            == value.manifest_entry.get("script_checksum")
            and current_artifact_entries.get(
                value.manifest_entry["artifact_id"], {}
            ).get("source_executions")
            == value.manifest_entry.get("source_executions")
            for value in derived_artifacts
        )
    )
    if all_same_latest_results and not force:
        attempt_payload = {
            "schema_version": INGESTION_SCHEMA_VERSION,
            "attempt_id": attempt_id,
            "checked_at": checked_at_text,
            "mode": mode,
            "status": "validated_unchanged",
            "selected_query_ids": sorted(selected_ids),
            "active_snapshot_id": state.get("current_snapshot_id"),
            "source_data_checksum": current_manifest.get("source_data_checksum") if current_manifest else None,
            "failures": partial_failure_payloads,
            "query_checks": [
                {
                    "query_id": query_id,
                    "checksum": value.content_checksum,
                    "execution_id": value.manifest_entry.get("execution_id"),
                    "execution_finished_at": value.manifest_entry.get(
                        "execution_finished_at"
                    ),
                    "data_updated_at": value.manifest_entry.get("data_updated_at"),
                }
                for query_id, value in sorted(normalized.items())
            ],
        }
        store.record_attempt(attempt_id, attempt_payload)
        try:
            new_state = store.update_unchanged_state(
                attempt_id=attempt_id,
                checked_at=checked_at_text,
                partial_failures=partial_failure_payloads,
            )
        except StudioIngestionError as exc:
            failed_attempt = dict(attempt_payload)
            failed_attempt.update(
                {
                    "status": "failed",
                    "failures": [exc.as_dict()],
                    "active_snapshot_preserved": True,
                }
            )
            try:
                store.record_attempt(attempt_id, failed_attempt)
            except StudioIngestionError:
                pass
            raise
        completed_attempt = dict(attempt_payload)
        completed_attempt["status"] = (
            "partial" if partial_failure_payloads else "unchanged"
        )
        try:
            store.record_attempt(attempt_id, completed_attempt)
        except StudioIngestionError as exc:
            if logger:
                logger(
                    "refresh state updated, but final attempt diagnostics could not "
                    f"be updated: {exc}"
                )
        return RefreshSummary(
            status="partial" if partial_failure_payloads else "unchanged",
            snapshot_id=str(new_state["current_snapshot_id"]),
            attempt_id=attempt_id,
            fetched_query_ids=tuple(sorted(selected_ids)),
            reused_query_ids=tuple(sorted(set(reused_query_ids))),
            failed_query_ids=tuple(
                sorted(
                    failure["query_id"]
                    for failure in partial_failure_payloads
                    if failure.get("query_id") is not None
                )
            ),
            unchanged=True,
            output_root=Path(output_root),
        )

    entries = [value.manifest_entry for _, value in sorted(normalized.items())]
    artifact_entries = [
        value.manifest_entry
        for value in sorted(
            derived_artifacts,
            key=lambda value: str(value.manifest_entry["artifact_id"]),
        )
    ]
    if set(normalized) != target_query_ids:
        raise StudioIngestionError(
            FailureCategory.MANIFEST_FAILURE,
            "Studio candidate query scope is incomplete",
        )
    source_checksum = _source_data_checksum(entries, artifact_entries)
    scoped_requests = {
        query_id: requests[query_id]
        for query_id in sorted(target_query_ids)
    }
    contract_checksum = query_contract_checksum(scoped_requests)
    scoped_dashboard_ids = {
        dashboard_id
        for request in scoped_requests.values()
        for dashboard_id in request.dashboard_ids
    }
    scoped_metric_ids = {
        metric_id
        for request in scoped_requests.values()
        for metric_id in request.metric_ids
    }
    snapshot_fingerprint = sha256_json(
        {
            "mode": mode,
            "generated_at": checked_at_text,
            "contract_checksum": contract_checksum,
            "queries": entries,
            "artifacts": artifact_entries,
        }
    )
    snapshot_id = _snapshot_id(mode, checked_at, snapshot_fingerprint)
    changed_query_ids = [
        query_id
        for query_id, value in normalized.items()
        if current_entries.get(query_id, {}).get("checksum") != value.content_checksum
    ]
    last_successful_fetch_at = checked_at_text
    if partial_failure_payloads:
        prior_complete_success = (
            state.get("last_successful_fetch_at")
            or (current_manifest or {}).get("last_successful_fetch_at")
            or (current_manifest or {}).get("generated_at")
        )
        try:
            parse_timestamp(
                prior_complete_success,
                field_name="last_successful_fetch_at",
            )
        except ValueError as exc:
            raise StudioIngestionError(
                FailureCategory.MANIFEST_FAILURE,
                "The active Studio snapshot has no valid complete-success timestamp",
            ) from exc
        last_successful_fetch_at = str(prior_complete_success)
    manifest = _build_manifest(
        checked_at=checked_at,
        mode=mode,
        dashboard_count=len(scoped_dashboard_ids),
        metric_count=len(scoped_metric_ids),
        entries=entries,
        snapshot_id=snapshot_id,
        previous_snapshot_id=(
            str(state["current_snapshot_id"])
            if active_snapshot_usable and state.get("current_snapshot_id")
            else None
        ),
        changed_query_ids=changed_query_ids,
        reused_query_ids=sorted(set(reused_query_ids)),
        contract_checksum=contract_checksum,
        last_successful_fetch_at=last_successful_fetch_at,
        artifacts=artifact_entries,
    )
    attempt_payload = {
        "schema_version": INGESTION_SCHEMA_VERSION,
        "attempt_id": attempt_id,
        "checked_at": checked_at_text,
        "mode": mode,
        "status": "validated_candidate",
        "candidate_snapshot_id": snapshot_id,
        "selected_query_ids": sorted(selected_ids),
        "snapshot_query_ids": sorted(target_query_ids),
        "changed_query_ids": sorted(changed_query_ids),
        "reused_query_ids": sorted(set(reused_query_ids)),
        "failures": partial_failure_payloads,
        "source_data_checksum": manifest["source_data_checksum"],
    }
    store.record_attempt(attempt_id, attempt_payload)
    snapshot_files: dict[str, bytes] = {}
    for value in normalized.values():
        main_file = str(value.manifest_entry["data_file"])
        snapshot_files[main_file] = value.file_bytes
        for supporting_name, supporting_bytes in value.supporting_files.items():
            existing = snapshot_files.get(supporting_name)
            if existing is not None and existing != supporting_bytes:
                raise StudioIngestionError(
                    FailureCategory.MANIFEST_FAILURE,
                    f"Studio supporting file {supporting_name} has conflicting content",
                )
            snapshot_files[supporting_name] = supporting_bytes
    for value in derived_artifacts:
        snapshot_files[str(value.manifest_entry["data_file"])] = value.file_bytes
    try:
        store.promote(
            snapshot_id=snapshot_id,
            manifest=manifest,
            query_files=snapshot_files,
            query_requests=requests,
            attempt_id=attempt_id,
            checked_at=checked_at_text,
            keep_previous=keep_previous,
            previous_snapshot_id=(
                str(state["current_snapshot_id"])
                if active_snapshot_usable and state.get("current_snapshot_id")
                else None
            ),
            required_query_ids=target_query_ids,
            partial_failures=partial_failure_payloads,
        )
    except StudioIngestionError as exc:
        failed_attempt = dict(attempt_payload)
        failed_attempt.update(
            {
                "status": "failed",
                "failures": [exc.as_dict()],
                "active_snapshot_id": state.get("current_snapshot_id"),
                "active_snapshot_preserved": bool(
                    active_snapshot_usable and state.get("current_snapshot_id")
                ),
            }
        )
        try:
            store.record_attempt(attempt_id, failed_attempt)
        except StudioIngestionError:
            pass
        raise
    successful_attempt = dict(attempt_payload)
    successful_attempt["status"] = (
        "partial" if partial_failure_payloads else "success"
    )
    successful_attempt["active_snapshot_id"] = snapshot_id
    try:
        store.record_attempt(attempt_id, successful_attempt)
    except StudioIngestionError as exc:
        if logger:
            logger(
                "snapshot promoted, but final attempt diagnostics could not be "
                f"updated: {exc}"
            )
    return RefreshSummary(
        status="partial" if partial_failure_payloads else "success",
        snapshot_id=snapshot_id,
        attempt_id=attempt_id,
        fetched_query_ids=tuple(sorted(selected_ids)),
        reused_query_ids=tuple(sorted(set(reused_query_ids))),
        failed_query_ids=tuple(
            sorted(
                failure["query_id"]
                for failure in partial_failure_payloads
                if failure.get("query_id") is not None
            )
        ),
        unchanged=all_same_latest_results,
        output_root=Path(output_root),
    )


def refresh_studio_data(
    client: StudioLatestResultClient,
    *,
    output_root: Path = DEFAULT_STUDIO_OUTPUT_ROOT,
    mode: str,
    query_ids: set[int] | None = None,
    dashboard_ids: set[str] | None = None,
    keep_previous: int = 1,
    force: bool = False,
    allow_partial: bool = False,
    timeout_seconds: float = 30.0,
    retry_policy: RetryPolicy = RetryPolicy(),
    clock: Callable[[], datetime] = utc_now,
    sleeper: Callable[[float], None] = time.sleep,
    logger: Callable[[str], None] | None = None,
) -> RefreshSummary:
    store = SnapshotStore(output_root, clock=clock)
    with store.refresh_lock():
        return _refresh_studio_data_unlocked(
            client,
            output_root=output_root,
            mode=mode,
            query_ids=query_ids,
            dashboard_ids=dashboard_ids,
            keep_previous=keep_previous,
            force=force,
            allow_partial=allow_partial,
            timeout_seconds=timeout_seconds,
            retry_policy=retry_policy,
            clock=clock,
            sleeper=sleeper,
            logger=logger,
        )


def validate_current_snapshot(output_root: Path = DEFAULT_STUDIO_OUTPUT_ROOT) -> dict:
    dashboards, _, requests = load_query_requests()
    store = SnapshotStore(output_root)
    manifest = store.current_manifest(
        requests,
        required_query_ids=generated_query_ids(dashboards, requests),
    )
    if manifest is None:
        raise StudioIngestionError(
            FailureCategory.MANIFEST_FAILURE,
            "Studio has no active generated snapshot",
        )
    return manifest
