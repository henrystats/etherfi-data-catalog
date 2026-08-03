from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
from string import Template
from typing import Callable

import yaml

try:
    from scripts.prepare_kyberswap_depositor_intelligence import (
        DERIVED_ARTIFACT_FILE as KYBERSWAP_INTELLIGENCE_FILE,
        DERIVED_ARTIFACT_ID as KYBERSWAP_INTELLIGENCE_ID,
        KyberSwapDepositorIntelligenceError,
        validate_kyberswap_depositor_intelligence,
    )
except ModuleNotFoundError:  # Supports direct script execution.
    from prepare_kyberswap_depositor_intelligence import (  # type: ignore
        DERIVED_ARTIFACT_FILE as KYBERSWAP_INTELLIGENCE_FILE,
        DERIVED_ARTIFACT_ID as KYBERSWAP_INTELLIGENCE_ID,
        KyberSwapDepositorIntelligenceError,
        validate_kyberswap_depositor_intelligence,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDIO_DIR = ROOT / "studio"
STUDIO_DASHBOARDS_PATH = DEFAULT_STUDIO_DIR / "dashboards.yaml"
STUDIO_METRICS_PATH = DEFAULT_STUDIO_DIR / "metrics.yaml"
STUDIO_DATA_DIR = DEFAULT_STUDIO_DIR / "data"
STUDIO_GENERATED_DATA_DIR = ROOT / "website" / "data" / "studio" / "generated"
STUDIO_GENERATED_MANIFEST_PATH = STUDIO_GENERATED_DATA_DIR / "manifest.json"
STUDIO_DATA_SCHEMA_VERSION = 1
STUDIO_QUERY_STATUSES = {"success", "empty", "failed"}
STUDIO_QUERY_FRESHNESS_STATUSES = {"current", "delayed", "stale"}
STUDIO_VISUALIZATION_TYPES = {"counter", "line", "bar", "sankey", "table"}
STUDIO_LINE_VISUALIZATIONS = {"line", "area", "column", "scatter"}
STUDIO_FORMATS = {
    "currency",
    "currency_compact",
    "integer",
    "integer_compact",
    "percent",
    "percentage_points",
    "table",
    "token",
}
STUDIO_TABLE_FORMATS = {
    "boolean",
    "currency",
    "currency_compact",
    "date",
    "datetime",
    "integer",
    "integer_compact",
    "percent",
    "percentage_points",
    "text",
    "token",
}
STUDIO_NUMERIC_TABLE_FORMATS = {
    "currency",
    "currency_compact",
    "integer",
    "integer_compact",
    "percent",
    "percentage_points",
    "token",
}
STUDIO_EXPLORER_CHAINS = {
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
STUDIO_SIZES = {"small", "medium", "wide", "full"}
STUDIO_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
STUDIO_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STUDIO_QUERY_FILE_PATTERN = re.compile(r"^query_([1-9][0-9]*)\.json$")
STUDIO_RAW_QUERY_FILE_PATTERN = re.compile(r"^raw_query_([1-9][0-9]*)\.json$")
STUDIO_COLUMN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
STUDIO_METHOD_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
STUDIO_EXPORT_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STUDIO_PERIOD_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
STUDIO_SNAPSHOT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
STUDIO_EXECUTION_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)
STUDIO_GENERATED_STATE_SCHEMA_VERSION = 2
STUDIO_FRESHNESS_POLICY_FIELDS = (
    "expected_refresh_hours",
    "warning_after_hours",
    "stale_after_hours",
)
STUDIO_RANGE_OPTIONS = ("7D", "30D", "90D", "YTD", "1Y", "ALL")
STUDIO_PROVIDER_MODES = {"fixture", "latest_result"}
STUDIO_INTELLIGENCE_COMPONENTS = {
    "top_referred_depositors",
    "referral_concentration",
    "top_depositors",
    "recent_referral_deposits",
    "recent_etherfi_activity",
    "wallet_investigation",
}


@dataclass(frozen=True)
class StudioDashboard:
    data: dict

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def slug(self) -> str:
        return str(self.data["slug"])

    @property
    def name(self) -> str:
        return str(self.data["name"])

    @property
    def data_file(self) -> str:
        return str(self.data["data_file"])


@dataclass(frozen=True)
class StudioMetric:
    data: dict

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def dashboard_id(self) -> str:
        return str(self.data["dashboard_id"])

    @property
    def section(self) -> str:
        return str(self.data["section"])

    @property
    def visualization_type(self) -> str:
        return str(self.data["visualization_type"])


def _read_yaml_list(path: Path, key: str) -> list[dict]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    values = payload.get(key)
    if not isinstance(values, list):
        raise ValueError(f"{path} must contain a '{key}' list")
    if not all(isinstance(value, dict) for value in values):
        raise ValueError(f"Every item in {path} '{key}' must be a mapping")
    return values


def _require_fields(kind: str, value: dict, required: set[str]) -> None:
    missing = sorted(field for field in required if value.get(field) in (None, ""))
    if missing:
        item_id = value.get("id") or "<unknown>"
        raise ValueError(f"{kind} {item_id} is missing required fields: {', '.join(missing)}")


def _require_unique(
    kind: str,
    values: list[object],
    *,
    field: str | None = None,
    correction: str | None = None,
) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        guidance = ""
        if field and correction:
            guidance = (
                f"; field {field}; expected correction: {correction}"
            )
        raise ValueError(
            f"Duplicate Studio {kind}: {', '.join(str(value) for value in duplicates)}"
            f"{guidance}"
        )


def _studio_metric_context(metric: dict) -> str:
    dashboard_id = str(metric.get("dashboard_id") or "<unknown>")
    metric_id = str(metric.get("id") or "<unknown>")
    query_id = metric.get("query_id")
    query_label = str(query_id) if query_id not in (None, "") else "<unknown>"
    return (
        f"Studio dashboard {dashboard_id} metric {metric_id} "
        f"query {query_label}"
    )


def _metric_registry_error(
    metric: dict,
    *,
    field: str,
    problem: str,
    correction: str,
) -> ValueError:
    return ValueError(
        f"{_studio_metric_context(metric)} field {field}: {problem}; "
        f"expected correction: {correction}"
    )


def studio_query_url(query_id: int) -> str:
    if type(query_id) is not int or query_id <= 0:
        raise ValueError("Studio query_id must be a positive integer")
    return f"https://dune.com/queries/{query_id}"


def studio_query_data_file(query_id: int) -> str:
    if type(query_id) is not int or query_id <= 0:
        raise ValueError("Studio query_id must be a positive integer")
    return f"query_{query_id}.json"


def _normalize_freshness_policy(value: object, *, context: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{context} freshness_policy must be a mapping")
    unknown_fields = sorted(set(value) - set(STUDIO_FRESHNESS_POLICY_FIELDS))
    if unknown_fields:
        raise ValueError(
            f"{context} freshness_policy has unsupported fields: "
            f"{', '.join(unknown_fields)}"
        )

    normalized = {}
    for field in STUDIO_FRESHNESS_POLICY_FIELDS:
        if field not in value:
            continue
        threshold = value[field]
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
            or threshold <= 0
        ):
            raise ValueError(
                f"{context} freshness_policy {field} must be a positive number"
            )
        normalized[field] = threshold

    ordered_values = [
        (field, normalized[field])
        for field in STUDIO_FRESHNESS_POLICY_FIELDS
        if field in normalized
    ]
    for (earlier_field, earlier), (later_field, later) in zip(
        ordered_values,
        ordered_values[1:],
    ):
        if earlier > later:
            raise ValueError(
                f"{context} freshness_policy requires {earlier_field} "
                f"to be no greater than {later_field}"
            )
    return normalized


def _merge_freshness_policies(*policies: dict) -> dict:
    merged = {}
    for policy in policies:
        for field, value in policy.items():
            merged[field] = value
    return merged


def normalize_studio_dashboard(dashboard: dict) -> dict:
    normalized = dict(dashboard)
    normalized["data_mode"] = str(normalized.get("data_mode") or "demo")
    dashboard_id = str(normalized.get("id") or "<unknown>")
    context = f"Studio dashboard {dashboard_id}"
    freshness_policy = _normalize_freshness_policy(
        normalized.get("freshness_policy"),
        context=context,
    )
    legacy_stale_after = normalized.get("stale_after_hours")
    if legacy_stale_after is not None:
        legacy_policy = _normalize_freshness_policy(
            {"stale_after_hours": legacy_stale_after},
            context=context,
        )
        configured_stale_after = freshness_policy.get("stale_after_hours")
        if (
            configured_stale_after is not None
            and configured_stale_after != legacy_stale_after
        ):
            raise ValueError(
                f"{context} stale_after_hours conflicts with "
                "freshness_policy stale_after_hours"
            )
        freshness_policy.update(legacy_policy)
    if freshness_policy:
        normalized["freshness_policy"] = freshness_policy
        if "stale_after_hours" in freshness_policy:
            normalized["stale_after_hours"] = freshness_policy[
                "stale_after_hours"
            ]
    return normalized


def normalize_studio_metric(metric: dict) -> dict:
    normalized = dict(metric)
    normalized["provider_mode"] = str(
        normalized.get("provider_mode") or "fixture"
    )
    metric_id = str(normalized.get("id") or "<unknown>")
    query_id = normalized.get("query_id")
    if type(query_id) is int and query_id > 0:
        normalized["query_url"] = str(
            normalized.get("query_url") or studio_query_url(query_id)
        ).rstrip("/")
        normalized["data_file"] = str(
            normalized.get("data_file") or studio_query_data_file(query_id)
        )

    value_format = normalized.get("value_format")
    existing_format = normalized.get("format")
    if (
        value_format not in (None, "")
        and existing_format not in (None, "")
        and value_format != existing_format
    ):
        raise _metric_registry_error(
            normalized,
            field="format",
            problem="value_format conflicts with format",
            correction="set format and value_format to the same supported value",
        )
    if existing_format in (None, "") and value_format not in (None, ""):
        normalized["format"] = value_format
    if normalized.get("format") not in (None, ""):
        normalized["value_format"] = normalized["format"]

    for field in ("optional_columns", "dimension_columns", "value_columns"):
        if normalized.get(field) is None:
            normalized[field] = []
    source_label = normalized.get("source_label")
    if isinstance(source_label, str):
        normalized["source_label"] = source_label.strip()
    source_mode = normalized.get("source_mode")
    if source_mode is not None and source_mode not in {"fixture", "live"}:
        raise ValueError(f"{context} source_mode must be fixture or live")
    methodology_id = normalized.get("methodology_id")
    if methodology_id is not None:
        required_provenance = {
            "source_query_id",
            "source_execution_id",
            "source_last_updated",
            "raw_data_file",
            "raw_row_count",
            "raw_columns",
            "raw_checksum",
            "raw_file_checksum",
            "raw_file_size_bytes",
            "methodology_version",
            "script_path",
            "script_checksum",
            "tests_path",
            "transformation_summary",
            "data_quality_warnings",
        }
        missing_provenance = sorted(
            field for field in required_provenance if field not in normalized
        )
        if missing_provenance:
            raise ValueError(
                f"{context} transformed result is missing provenance: "
                + ", ".join(missing_provenance)
            )
        if (
            not isinstance(methodology_id, str)
            or not STUDIO_METHOD_ID_PATTERN.fullmatch(methodology_id)
        ):
            raise ValueError(f"{context} methodology_id is unsafe")
        if normalized["source_query_id"] != query_id:
            raise ValueError(f"{context} source_query_id does not match query_id")
        if normalized["source_execution_id"] != execution_id:
            raise ValueError(
                f"{context} source_execution_id does not match execution_id"
            )
        _parse_timezone_timestamp(
            normalized["source_last_updated"],
            context=context,
            field="source_last_updated",
        )
        expected_raw_file = f"raw_query_{query_id}.json"
        if normalized["raw_data_file"] != expected_raw_file:
            raise ValueError(f"{context} raw_data_file must be {expected_raw_file}")
        if type(normalized["raw_row_count"]) is not int or normalized["raw_row_count"] < 0:
            raise ValueError(f"{context} raw_row_count must be non-negative")
        normalized["raw_columns"] = _validated_columns(
            normalized["raw_columns"],
            context=f"{context} raw result",
        )
        for field in ("raw_checksum", "raw_file_checksum", "script_checksum"):
            if (
                not isinstance(normalized[field], str)
                or not re.fullmatch(r"[0-9a-f]{64}", normalized[field])
            ):
                raise ValueError(f"{context} {field} must be a SHA-256 digest")
        if (
            type(normalized["raw_file_size_bytes"]) is not int
            or normalized["raw_file_size_bytes"] <= 0
        ):
            raise ValueError(f"{context} raw_file_size_bytes must be positive")
        if (
            not isinstance(normalized["methodology_version"], str)
            or not re.fullmatch(
                r"[0-9]+\.[0-9]+\.[0-9]+",
                normalized["methodology_version"],
            )
        ):
            raise ValueError(f"{context} methodology_version must use semantic versioning")
        for field in ("script_path", "tests_path"):
            path_value = normalized[field]
            if (
                not isinstance(path_value, str)
                or Path(path_value).is_absolute()
                or ".." in Path(path_value).parts
            ):
                raise ValueError(f"{context} {field} must be repository-relative")
        if not isinstance(normalized["transformation_summary"], dict):
            raise ValueError(f"{context} transformation_summary must be a mapping")
        if not isinstance(normalized["data_quality_warnings"], list) or any(
            not isinstance(item, dict) for item in normalized["data_quality_warnings"]
        ):
            raise ValueError(f"{context} data_quality_warnings must be mappings")
    for field in ("data_source", "sparkline_data_source"):
        if isinstance(normalized.get(field), str):
            normalized[field] = normalized[field].strip()
    if "allow_empty" not in normalized and isinstance(
        normalized.get("is_exportable"),
        bool,
    ):
        normalized["allow_empty"] = not normalized["is_exportable"]
    normalized["freshness_policy"] = _normalize_freshness_policy(
        normalized.get("freshness_policy"),
        context=f"Studio metric {metric_id}",
    )
    return normalized


def normalize_studio_registry(
    dashboard_values: list[dict],
    metric_values: list[dict],
) -> tuple[list[dict], list[dict]]:
    normalized_dashboards = [
        normalize_studio_dashboard(value) for value in dashboard_values
    ]
    dashboards_by_id = {
        str(value.get("id")): value for value in normalized_dashboards
    }
    normalized_metrics = []
    for value in metric_values:
        metric = normalize_studio_metric(value)
        dashboard = dashboards_by_id.get(str(metric.get("dashboard_id"))) or {}
        effective_policy = _merge_freshness_policies(
            dashboard.get("freshness_policy") or {},
            metric.get("freshness_policy") or {},
        )
        metric["effective_freshness_policy"] = _normalize_freshness_policy(
            effective_policy,
            context=f"Studio metric {metric.get('id') or '<unknown>'} effective",
        )
        normalized_metrics.append(metric)
    return normalized_dashboards, normalized_metrics


def _parse_timezone_timestamp(value: object, *, context: str, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} needs {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context} has invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{context} {field} must include a timezone")
    return parsed


def _validated_columns(value: object, *, context: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(column, str) and column for column in value)
    ):
        raise ValueError(f"{context} columns must be a non-empty string list")
    _require_unique(f"columns in {context}", value)
    return list(value)


def _validated_registry_columns(
    value: object,
    *,
    context: str,
    field: str,
    allow_empty: bool = True,
) -> list[str]:
    if not isinstance(value, list) or (
        not allow_empty and not value
    ):
        qualifier = "a string list" if allow_empty else "a non-empty string list"
        raise ValueError(f"{context} {field} must be {qualifier}")
    invalid_columns = [
        column
        for column in value
        if not isinstance(column, str)
        or not STUDIO_COLUMN_PATTERN.fullmatch(column)
    ]
    if invalid_columns:
        raise ValueError(
            f"{context} {field} contains unsafe column references: "
            f"{', '.join(str(column) for column in invalid_columns)}"
        )
    _require_unique(f"{field} in {context}", value)
    return list(value)


def _validated_repo_path(value: object, *, context: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} {field} must be a repository-relative path")
    normalized = value.strip()
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != normalized:
        raise ValueError(f"{context} {field} must be a safe repository-relative path")
    if not (ROOT / path).is_file():
        raise ValueError(f"{context} {field} does not exist: {normalized}")
    return normalized


def _validated_query_transformation(metric: dict) -> dict | None:
    value = metric.get("transformation")
    if value is None:
        return None
    context = _studio_metric_context(metric)
    if not isinstance(value, dict):
        raise ValueError(f"{context} transformation must be a mapping")
    expected_fields = {
        "id",
        "version",
        "methodology_id",
        "script_path",
        "tests_path",
        "fixture_path",
        "raw_data_file",
        "source_required_columns",
    }
    unknown_fields = sorted(set(value) - expected_fields)
    if unknown_fields:
        raise ValueError(
            f"{context} transformation has unsupported fields: "
            + ", ".join(unknown_fields)
        )
    missing_fields = sorted(
        field for field in expected_fields if value.get(field) in (None, "")
    )
    if missing_fields:
        raise ValueError(
            f"{context} transformation is missing: {', '.join(missing_fields)}"
        )
    transformation_id = str(value["id"])
    methodology_id = str(value["methodology_id"])
    if not STUDIO_METHOD_ID_PATTERN.fullmatch(transformation_id):
        raise ValueError(f"{context} transformation id is unsafe")
    if not STUDIO_METHOD_ID_PATTERN.fullmatch(methodology_id):
        raise ValueError(f"{context} transformation methodology_id is unsafe")
    version = value["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError(f"{context} transformation version must use semantic versioning")
    query_id = metric.get("query_id")
    raw_data_file = str(value["raw_data_file"])
    raw_match = STUDIO_RAW_QUERY_FILE_PATTERN.fullmatch(raw_data_file)
    if raw_match is None or int(raw_match.group(1)) != query_id:
        raise ValueError(
            f"{context} transformation raw_data_file must be raw_query_{query_id}.json"
        )
    return {
        "id": transformation_id,
        "version": version,
        "methodology_id": methodology_id,
        "script_path": _validated_repo_path(
            value["script_path"],
            context=context,
            field="transformation script_path",
        ),
        "tests_path": _validated_repo_path(
            value["tests_path"],
            context=context,
            field="transformation tests_path",
        ),
        "fixture_path": _validated_repo_path(
            value["fixture_path"],
            context=context,
            field="transformation fixture_path",
        ),
        "raw_data_file": raw_data_file,
        "source_required_columns": _validated_registry_columns(
            value["source_required_columns"],
            context=context,
            field="transformation source_required_columns",
            allow_empty=False,
        ),
    }


def _validate_methodology_content(metric: dict) -> None:
    value = metric.get("methodology")
    if value is None:
        return
    context = _studio_metric_context(metric)
    visualization_type = metric.get("visualization_type")
    if visualization_type not in {"counter", "line", "bar", "sankey"}:
        raise ValueError(
            f"{context} methodology is supported for counter, line, bar, and Sankey metrics"
        )
    if not isinstance(value, dict):
        raise ValueError(f"{context} methodology must be a mapping")
    allowed_fields = {
        "description",
        "title",
        "definitions",
        "metric_definitions",
        "selected_period_logic",
        "business_rules",
        "allocation_rules",
        "validation",
        "notes",
    }
    unknown_fields = sorted(set(value) - allowed_fields)
    if unknown_fields:
        raise ValueError(
            f"{context} methodology has unsupported fields: {', '.join(unknown_fields)}"
        )
    if not isinstance(value.get("description"), str) or not value["description"].strip():
        raise ValueError(f"{context} methodology needs a description")
    if visualization_type == "counter":
        if not isinstance(value.get("title"), str) or not value["title"].strip():
            raise ValueError(f"{context} counter methodology needs a title")
        for field in ("metric_definitions", "selected_period_logic"):
            items = value.get(field)
            if not isinstance(items, list) or not items or any(
                not isinstance(item, str) or not item.strip() for item in items
            ):
                raise ValueError(
                    f"{context} methodology {field} must be a non-empty string list"
                )
    elif value.get("title") is not None and (
        not isinstance(value["title"], str) or not value["title"].strip()
    ):
        raise ValueError(f"{context} methodology title must be a non-empty string")
    for field in (
        "definitions",
        "metric_definitions",
        "selected_period_logic",
        "business_rules",
        "allocation_rules",
        "validation",
        "notes",
    ):
        items = value.get(field) or []
        if not isinstance(items, list) or any(
            not isinstance(item, str) or not item.strip() for item in items
        ):
            raise ValueError(f"{context} methodology {field} must be a string list")


def _validate_growth_chart(metric: dict, columns: list[str]) -> None:
    value = metric.get("growth_chart")
    if value is None:
        return
    context = _studio_metric_context(metric)
    if metric.get("visualization_type") not in {"line", "bar"}:
        raise ValueError(
            f"{context} growth_chart is supported only for line and bar metrics"
        )
    if not isinstance(value, dict):
        raise ValueError(f"{context} growth_chart must be a mapping")
    allowed_fields = {
        "kind",
        "default_granularity",
        "granularity_column",
        "period_column",
        "range_date_column",
        "rebuild_weekly_from_daily",
        "latest_period_only",
        "available_granularities",
        "default_view",
        "views",
        "measures",
        "export_columns",
        "export_aliases",
        "export_constants",
        "visible_category_limit",
        "visible_others_label",
        "preserve_categories",
        "preserve_uncategorized_when_material",
        "rank_by_activity_magnitude",
    }
    unknown_fields = sorted(set(value) - allowed_fields)
    if unknown_fields:
        raise ValueError(
            f"{context} growth_chart has unsupported fields: "
            + ", ".join(unknown_fields)
        )
    visible_category_limit = value.get("visible_category_limit")
    if visible_category_limit is not None and (
        type(visible_category_limit) is not int
        or visible_category_limit < 1
        or visible_category_limit > 100
    ):
        raise ValueError(
            f"{context} growth_chart visible_category_limit must be an "
            "integer from 1 through 100"
        )
    visible_others_label = value.get("visible_others_label")
    if visible_others_label is not None and (
        not isinstance(visible_others_label, str)
        or not visible_others_label.strip()
    ):
        raise ValueError(
            f"{context} growth_chart visible_others_label must be a "
            "non-empty string"
        )
    preserve_categories = value.get("preserve_categories")
    if preserve_categories is not None:
        if not isinstance(preserve_categories, list) or any(
            not isinstance(category, str) or not category.strip()
            for category in preserve_categories
        ):
            raise ValueError(
                f"{context} growth_chart preserve_categories must be a string list"
            )
        _require_unique(
            f"preserved growth categories in metric {metric.get('id')}",
            preserve_categories,
        )
        if visible_others_label in preserve_categories:
            raise ValueError(
                f"{context} growth_chart visible_others_label cannot be preserved"
            )
    for boolean_field in (
        "preserve_uncategorized_when_material",
        "rank_by_activity_magnitude",
    ):
        if boolean_field in value and not isinstance(value[boolean_field], bool):
            raise ValueError(
                f"{context} growth_chart {boolean_field} must be a boolean"
            )
    kind = value.get("kind")
    if kind not in {"combo", "timeseries", "ranking"}:
        raise ValueError(f"{context} growth_chart kind is invalid")

    period_column = value.get("period_column")
    if not isinstance(period_column, str) or period_column not in columns:
        raise ValueError(
            f"{context} growth_chart period_column must be declared in columns"
        )
    range_date_column = value.get("range_date_column")
    if range_date_column is not None and (
        not isinstance(range_date_column, str) or range_date_column not in columns
    ):
        raise ValueError(
            f"{context} growth_chart range_date_column must be declared in columns"
        )
    rebuild_weekly_from_daily = value.get("rebuild_weekly_from_daily")
    if rebuild_weekly_from_daily is not None and not isinstance(
        rebuild_weekly_from_daily, bool
    ):
        raise ValueError(
            f"{context} growth_chart rebuild_weekly_from_daily must be a boolean"
        )
    latest_period_only = value.get("latest_period_only")
    if latest_period_only is not None and not isinstance(latest_period_only, bool):
        raise ValueError(
            f"{context} growth_chart latest_period_only must be a boolean"
        )
    if latest_period_only and value.get("kind") != "ranking":
        raise ValueError(
            f"{context} growth_chart latest_period_only is supported only for ranking"
        )
    granularities = value.get("available_granularities")
    if not isinstance(granularities, list) or any(
        item not in {"daily", "weekly"} for item in granularities
    ):
        raise ValueError(
            f"{context} growth_chart available_granularities must contain only daily or weekly"
        )
    _require_unique(
        f"growth granularities in metric {metric.get('id')}", granularities
    )
    if kind == "ranking":
        if granularities or value.get("default_granularity") is not None:
            raise ValueError(
                f"{context} ranking growth_chart must not configure granularity"
            )
    else:
        if granularities != ["daily", "weekly"]:
            raise ValueError(
                f"{context} growth_chart available_granularities must be daily and weekly"
            )
        if value.get("default_granularity") not in granularities:
            raise ValueError(
                f"{context} growth_chart default_granularity must be daily or weekly"
            )
        granularity_column = value.get("granularity_column")
        if granularity_column is not None and (
            not isinstance(granularity_column, str)
            or granularity_column not in columns
        ):
            raise ValueError(
                f"{context} growth_chart granularity_column must be declared in columns"
            )

    views = value.get("views")
    if not isinstance(views, list) or not views:
        raise ValueError(f"{context} growth_chart views must be a non-empty list")
    view_ids = []
    for view in views:
        if not isinstance(view, dict):
            raise ValueError(f"{context} growth_chart views must be mappings")
        unknown_view_fields = sorted(
            set(view)
            - {
                "id",
                "label",
                "record_types",
                "dimension_column",
                "dimension_order",
                "series_label",
                "value_column",
                "value_column_by_granularity",
                "measures",
            }
        )
        if unknown_view_fields:
            raise ValueError(
                f"{context} growth_chart view has unsupported fields: "
                + ", ".join(unknown_view_fields)
            )
        view_id = view.get("id")
        label = view.get("label")
        if not isinstance(view_id, str) or not view_id.strip():
            raise ValueError(f"{context} growth_chart view id is required")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{context} growth_chart view label is required")
        view_ids.append(view_id)
        record_types = view.get("record_types")
        expected_grains = granularities or ["total"]
        if not isinstance(record_types, dict) or sorted(record_types) != sorted(
            expected_grains
        ) or any(
            not isinstance(record_type, str) or not record_type.strip()
            for record_type in record_types.values()
        ):
            raise ValueError(
                f"{context} growth_chart view record_types must map every configured grain"
            )
        dimension_column = view.get("dimension_column")
        if dimension_column is not None and dimension_column not in columns:
            raise ValueError(
                f"{context} growth_chart view dimension_column must be declared in columns"
            )
        dimension_order = view.get("dimension_order") or []
        if not isinstance(dimension_order, list) or any(
            not isinstance(item, str) or not item.strip() for item in dimension_order
        ):
            raise ValueError(
                f"{context} growth_chart view dimension_order must be a string list"
            )
        _require_unique(
            f"growth dimension order in metric {metric.get('id')}", dimension_order
        )
        if view.get("series_label") is not None and (
            not isinstance(view["series_label"], str)
            or not view["series_label"].strip()
        ):
            raise ValueError(
                f"{context} growth_chart view series_label must be a non-empty string"
            )
        value_column = view.get("value_column")
        if value_column is not None and value_column not in columns:
            raise ValueError(
                f"{context} growth_chart view value_column must be declared in columns"
            )
        value_by_granularity = view.get("value_column_by_granularity")
        if value_by_granularity is not None and (
            not isinstance(value_by_granularity, dict)
            or sorted(value_by_granularity) != sorted(granularities)
            or any(column not in columns for column in value_by_granularity.values())
        ):
            raise ValueError(
                f"{context} growth_chart view value_column_by_granularity must map every configured grain to a declared column"
            )
        if view.get("measures") is not None and not isinstance(view["measures"], list):
            raise ValueError(f"{context} growth_chart view measures must be a list")
    _require_unique(f"growth view ids in metric {metric.get('id')}", view_ids)
    if value.get("default_view") not in view_ids:
        raise ValueError(
            f"{context} growth_chart default_view must reference a configured view"
        )

    measures = value.get("measures")
    if not isinstance(measures, list) or not measures:
        raise ValueError(f"{context} growth_chart measures must be a non-empty list")
    measure_columns = []
    for measure in measures:
        if not isinstance(measure, dict):
            raise ValueError(f"{context} growth_chart measures must be mappings")
        unknown_measure_fields = sorted(
            set(measure)
            - {
                "column",
                "column_by_granularity",
                "label",
                "format",
                "series_type",
                "axis",
                "color",
                "stack",
            }
        )
        if unknown_measure_fields:
            raise ValueError(
                f"{context} growth_chart measure has unsupported fields: "
                + ", ".join(unknown_measure_fields)
            )
        column = measure.get("column")
        columns_by_granularity = measure.get("column_by_granularity")
        if column is None and columns_by_granularity is None:
            raise ValueError(f"{context} growth_chart measure needs a column")
        if column is not None and (
            not isinstance(column, str) or column not in columns
        ):
            raise ValueError(
                f"{context} growth_chart measure column must be declared in columns"
            )
        if columns_by_granularity is not None and (
            not isinstance(columns_by_granularity, dict)
            or sorted(columns_by_granularity) != sorted(granularities)
            or any(
                item not in columns for item in columns_by_granularity.values()
            )
        ):
            raise ValueError(
                f"{context} growth_chart measure column_by_granularity must map every configured grain to a declared column"
            )
        measure_columns.append(
            column or "|".join(columns_by_granularity[grain] for grain in granularities)
        )
        if not isinstance(measure.get("label"), str) or not measure["label"].strip():
            raise ValueError(f"{context} growth_chart measure label is required")
        if measure.get("format") not in STUDIO_FORMATS:
            raise ValueError(f"{context} growth_chart measure format is invalid")
        if measure.get("series_type") not in {"area", "bar", "column", "line"}:
            raise ValueError(f"{context} growth_chart measure series_type is invalid")
        if measure.get("axis") is not None and measure["axis"] not in {"left", "right"}:
            raise ValueError(f"{context} growth_chart measure axis is invalid")
        if measure.get("stack") is not None and not isinstance(measure["stack"], bool):
            raise ValueError(f"{context} growth_chart measure stack must be boolean")
    _require_unique(
        f"growth measure columns in metric {metric.get('id')}", measure_columns
    )
    export_columns = value.get("export_columns")
    if not isinstance(export_columns, list) or not export_columns or any(
        not isinstance(item, str) or not item.strip() for item in export_columns
    ):
        raise ValueError(
            f"{context} growth_chart export_columns must be a non-empty string list"
        )
    _require_unique(
        f"growth export columns in metric {metric.get('id')}", export_columns
    )
    export_aliases = value.get("export_aliases")
    export_constants = value.get("export_constants") or {}
    allowed_export_aliases = {
        "period",
        "granularity",
        "source_granularity",
        "selected_view",
        "dashboard_period",
        "dimension",
        "primary_value",
        "secondary_value",
        "source_last_updated",
    }
    if not isinstance(export_aliases, dict) or any(
        key not in export_columns
        or not isinstance(alias, str)
        or alias not in allowed_export_aliases
        for key, alias in export_aliases.items()
    ):
        raise ValueError(
            f"{context} growth_chart export_aliases must map export columns to supported semantic values"
        )
    if not isinstance(export_constants, dict) or any(
        key not in export_columns
        or not isinstance(constant, (str, int, float, bool))
        for key, constant in export_constants.items()
    ):
        raise ValueError(
            f"{context} growth_chart export_constants must map export columns to scalar values"
        )
    if set(export_aliases) & set(export_constants):
        raise ValueError(
            f"{context} growth_chart export columns cannot be both aliases and constants"
        )
    if set(export_aliases) | set(export_constants) != set(export_columns):
        raise ValueError(
            f"{context} growth_chart export_aliases and export_constants must cover every export column"
        )


def _validated_metric_column_groups(
    metric: dict,
    *,
    metric_id: str,
    context: str | None = None,
) -> dict:
    context = context or f"Studio metric {metric_id}"
    columns = _validated_registry_columns(
        metric.get("columns"),
        context=context,
        field="columns",
        allow_empty=False,
    )
    optional_columns = _validated_registry_columns(
        metric.get("optional_columns") or [],
        context=context,
        field="optional_columns",
    )
    dimension_columns = _validated_registry_columns(
        metric.get("dimension_columns") or [],
        context=context,
        field="dimension_columns",
    )
    value_columns = _validated_registry_columns(
        metric.get("value_columns") or [],
        context=context,
        field="value_columns",
    )

    required_optional_overlap = sorted(set(columns) & set(optional_columns))
    if required_optional_overlap:
        raise ValueError(
            f"{context} columns cannot also be optional_columns: "
            f"{', '.join(required_optional_overlap)}"
        )
    declared_columns = set(columns) | set(optional_columns)
    for field, values in (
        ("dimension_columns", dimension_columns),
        ("value_columns", value_columns),
    ):
        undeclared = [column for column in values if column not in declared_columns]
        if undeclared:
            raise ValueError(
                f"{context} {field} references undeclared columns: "
                f"{', '.join(undeclared)}"
            )
    role_overlap = sorted(set(dimension_columns) & set(value_columns))
    if role_overlap:
        raise ValueError(
            f"{context} columns cannot be both dimensions and values: "
            f"{', '.join(role_overlap)}"
        )
    return {
        "columns": columns,
        "optional_columns": optional_columns,
        "dimension_columns": dimension_columns,
        "value_columns": value_columns,
    }


def _validated_column_reference(
    value: object,
    *,
    context: str,
    field: str,
) -> str:
    if not isinstance(value, str) or not STUDIO_COLUMN_PATTERN.fullmatch(value):
        raise ValueError(f"{context} {field} must be a safe column reference")
    return value


def _validate_safe_metric_column_references(
    metric: dict,
    *,
    metric_id: str,
    context: str | None = None,
) -> None:
    context = context or f"Studio metric {metric_id}"
    for field in (
        "comparison_column",
        "date_column",
        "category_column",
        "value_column",
        "source_column",
        "target_column",
        "exit_value_column",
        "chain_column",
        "sparkline_column",
        "sparkline_date_column",
        "period_key_column",
    ):
        value = metric.get(field)
        if value in (None, ""):
            continue
        try:
            _validated_column_reference(value, context=context, field=field)
        except ValueError as exc:
            raise _metric_registry_error(
                metric,
                field=field,
                problem=str(exc).removeprefix(f"{context} "),
                correction="use a safe declared column name",
            ) from exc
    if metric.get("stage_columns") is not None:
        try:
            _validated_registry_columns(
                metric["stage_columns"],
                context=context,
                field="stage_columns",
                allow_empty=False,
            )
        except ValueError as exc:
            raise _metric_registry_error(
                metric,
                field="stage_columns",
                problem=str(exc).removeprefix(f"{context} "),
                correction="provide two or three safe declared stage columns",
            ) from exc
    for field in ("address_columns", "transaction_columns"):
        if field not in metric:
            continue
        try:
            _validated_registry_columns(
                metric[field],
                context=context,
                field=field,
            )
        except ValueError as exc:
            raise _metric_registry_error(
                metric,
                field=field,
                problem=str(exc).removeprefix(f"{context} "),
                correction="provide a unique list of safe column names declared in columns",
            ) from exc
    series = metric.get("series")
    if series is not None:
        if not isinstance(series, list):
            raise _metric_registry_error(
                metric,
                field="series",
                problem="series must be a list",
                correction="provide a list of series mappings with column and label values",
            )
        for index, item in enumerate(series):
            if not isinstance(item, dict) or "column" not in item:
                raise _metric_registry_error(
                    metric,
                    field=f"series[{index}].column",
                    problem=f"series {index} needs a column",
                    correction="provide a safe column name declared in columns",
                )
            try:
                _validated_column_reference(
                    item["column"],
                    context=context,
                    field=f"series {index} column",
                )
            except ValueError as exc:
                raise _metric_registry_error(
                    metric,
                    field=f"series[{index}].column",
                    problem=str(exc).removeprefix(f"{context} "),
                    correction="use a safe column name declared in columns",
                ) from exc
    for field in ("column_labels", "column_formats"):
        mapping = metric.get(field)
        if mapping is None:
            continue
        if not isinstance(mapping, dict):
            raise ValueError(f"{context} {field} must be a mapping")
        for column in mapping:
            _validated_column_reference(
                column,
                context=context,
                field=f"{field} key",
            )


def _metric_semantic_column_groups(
    metric: dict,
    *,
    metric_id: str,
    column_groups: dict,
    required_columns: list[str],
) -> tuple[list[str], list[str]]:
    dimension_columns = list(column_groups["dimension_columns"])
    value_columns = list(column_groups["value_columns"])
    inferred_dimensions: list[str] = []
    inferred_values: list[str] = []
    visualization_type = str(metric.get("visualization_type") or "")

    if visualization_type == "counter":
        value_column = metric.get("value_column")
        if value_column:
            inferred_values.append(str(value_column))
        elif column_groups["columns"]:
            inferred_values.append(column_groups["columns"][0])
        if metric.get("period_key_column"):
            inferred_dimensions.append(str(metric["period_key_column"]))
        if metric.get("comparison_column"):
            inferred_values.append(str(metric["comparison_column"]))
    elif visualization_type == "line":
        if metric.get("date_column"):
            inferred_dimensions.append(str(metric["date_column"]))
        for series in metric.get("series") or []:
            if isinstance(series, dict) and series.get("column"):
                inferred_values.append(str(series["column"]))
    elif visualization_type == "bar":
        if metric.get("category_column"):
            inferred_dimensions.append(str(metric["category_column"]))
        if metric.get("value_column"):
            inferred_values.append(str(metric["value_column"]))
    elif visualization_type == "sankey":
        stage_columns = metric.get("stage_columns") or [
            metric.get("source_column"),
            metric.get("target_column"),
        ]
        inferred_dimensions.extend(
            str(column) for column in stage_columns if column
        )
        if metric.get("value_column"):
            inferred_values.append(str(metric["value_column"]))
        if metric.get("exit_value_column"):
            inferred_values.append(str(metric["exit_value_column"]))
    elif visualization_type == "table":
        if metric.get("date_column"):
            inferred_dimensions.append(str(metric["date_column"]))
        inferred_dimensions.extend(metric.get("address_columns") or [])
        inferred_dimensions.extend(metric.get("transaction_columns") or [])
        if metric.get("chain_column"):
            inferred_dimensions.append(str(metric["chain_column"]))
        inferred_values.extend(
            str(column)
            for column, value_format in (metric.get("column_formats") or {}).items()
            if value_format in STUDIO_NUMERIC_TABLE_FORMATS
        )

    for field, inferred in (
        ("dimension_columns", inferred_dimensions),
        ("value_columns", inferred_values),
    ):
        undeclared = [
            column for column in inferred if column not in required_columns
        ]
        if undeclared:
            raise ValueError(
                f"Studio metric {metric_id} inferred {field} references "
                f"undeclared columns: {', '.join(undeclared)}"
            )
    _append_unique(dimension_columns, inferred_dimensions)
    _append_unique(value_columns, inferred_values)
    return dimension_columns, value_columns


def _append_unique(values: list[str], additions: list[str]) -> None:
    for addition in additions:
        if addition not in values:
            values.append(addition)


def _validate_dashboard(dashboard: dict) -> None:
    _require_fields(
        "Dashboard",
        dashboard,
        {
            "id",
            "slug",
            "name",
            "description",
            "eyebrow",
            "audience",
            "status",
            "freshness_status",
            "freshness_note",
            "data_file",
            "default_date_range",
            "display_order",
            "sections",
        },
    )
    if not STUDIO_ID_PATTERN.fullmatch(str(dashboard["id"])):
        raise ValueError(f"Invalid Studio dashboard id: {dashboard['id']}")
    if not STUDIO_SLUG_PATTERN.fullmatch(str(dashboard["slug"])):
        raise ValueError(f"Invalid Studio dashboard slug: {dashboard['slug']}")
    data_file = str(dashboard["data_file"])
    if Path(data_file).name != data_file or not data_file.endswith(".json"):
        raise ValueError(f"Unsafe Studio data file: {data_file}")
    if dashboard["default_date_range"] not in STUDIO_RANGE_OPTIONS:
        raise ValueError(
            f"Unsupported default date range for {dashboard['id']}: "
            f"{dashboard['default_date_range']}"
        )
    if dashboard["status"] not in {"demo", "live"}:
        raise ValueError(f"Studio dashboard {dashboard['id']} has invalid status")
    if dashboard["data_mode"] not in {"demo", "generated"}:
        raise ValueError(
            f"Studio dashboard {dashboard['id']} has invalid data_mode"
        )
    if "show_hero" in dashboard and not isinstance(dashboard["show_hero"], bool):
        raise ValueError(
            f"Studio dashboard {dashboard['id']} show_hero must be boolean"
        )
    _normalize_freshness_policy(
        dashboard.get("freshness_policy"),
        context=f"Studio dashboard {dashboard['id']}",
    )
    stale_after_hours = dashboard.get("stale_after_hours")
    if stale_after_hours is not None and (
        isinstance(stale_after_hours, bool)
        or not isinstance(stale_after_hours, (int, float))
        or stale_after_hours <= 0
    ):
        raise ValueError(
            f"Studio dashboard {dashboard['id']} stale_after_hours "
            "must be a positive number"
        )
    dune_url = dashboard.get("dune_url")
    if dune_url and not re.fullmatch(
        r"https://dune\.com/[A-Za-z0-9][A-Za-z0-9_./-]*",
        str(dune_url),
    ):
        raise ValueError(
            f"Studio dashboard {dashboard['id']} has an invalid Dune URL"
        )
    sections = dashboard["sections"]
    if not isinstance(sections, list) or not sections:
        raise ValueError(f"Studio dashboard {dashboard['id']} needs sections")
    section_ids = []
    for section in sections:
        if (
            not isinstance(section, dict)
            or not section.get("id")
            or not section.get("label")
            or not section.get("description")
        ):
            raise ValueError(f"Studio dashboard {dashboard['id']} has an invalid section")
        section_id = str(section["id"])
        if not STUDIO_ID_PATTERN.fullmatch(section_id):
            raise ValueError(
                f"Studio dashboard {dashboard['id']} has an invalid section id"
            )
        if "show_heading" in section and not isinstance(
            section["show_heading"], bool
        ):
            raise ValueError(
                f"Studio dashboard {dashboard['id']} section {section_id} "
                "show_heading must be boolean"
            )
        if "show_description" in section and not isinstance(
            section["show_description"], bool
        ):
            raise ValueError(
                f"Studio dashboard {dashboard['id']} section {section_id} "
                "show_description must be boolean"
            )
        grid_columns = section.get("grid_columns")
        if grid_columns is not None and (
            type(grid_columns) is not int or grid_columns < 1 or grid_columns > 4
        ):
            raise ValueError(
                f"Studio dashboard {dashboard['id']} section {section_id} "
                "grid_columns must be an integer from 1 through 4"
            )
        for field in (
            "shared_methodology_metric_id",
            "shared_export_metric_id",
        ):
            metric_id = section.get(field)
            if metric_id is not None and (
                not isinstance(metric_id, str)
                or not STUDIO_ID_PATTERN.fullmatch(metric_id)
            ):
                raise ValueError(
                    f"Studio dashboard {dashboard['id']} section {section_id} "
                    f"{field} must be a safe metric id"
                )
        section_ids.append(section_id)
    _require_unique(f"section ids in {dashboard['id']}", section_ids)


def _validate_dashboard_section_metric_references(
    dashboard_values: list[dict],
    metric_values: list[dict],
) -> None:
    metrics_by_id = {str(metric["id"]): metric for metric in metric_values}
    for dashboard in dashboard_values:
        dashboard_id = str(dashboard["id"])
        for section in dashboard["sections"]:
            section_id = str(section["id"])
            for field in (
                "shared_methodology_metric_id",
                "shared_export_metric_id",
            ):
                metric_id = section.get(field)
                if metric_id is None:
                    continue
                metric = metrics_by_id.get(str(metric_id))
                if metric is None:
                    raise ValueError(
                        f"Studio dashboard {dashboard_id} section {section_id} "
                        f"{field} references unknown metric {metric_id}"
                    )
                if (
                    str(metric["dashboard_id"]) != dashboard_id
                    or str(metric["section"]) != section_id
                ):
                    raise ValueError(
                        f"Studio dashboard {dashboard_id} section {section_id} "
                        f"{field} must reference a metric in the same section"
                    )
                if field == "shared_methodology_metric_id" and not metric.get(
                    "methodology"
                ):
                    raise ValueError(
                        f"Studio dashboard {dashboard_id} section {section_id} "
                        f"{field} must reference a metric with methodology"
                    )
                if field == "shared_export_metric_id" and not metric.get(
                    "is_exportable"
                ):
                    raise ValueError(
                        f"Studio dashboard {dashboard_id} section {section_id} "
                        f"{field} must reference an exportable metric"
                    )
                if field == "shared_export_metric_id" and (
                    not metric.get("export_name")
                    or not metric.get("export_columns")
                ):
                    raise ValueError(
                        f"Studio dashboard {dashboard_id} section {section_id} "
                        f"{field} must reference a metric with export_name and "
                        "export_columns"
                    )


def _validate_metric_export_config(metric: dict, columns: list[str]) -> None:
    metric_id = str(metric["id"])
    export_name = metric.get("export_name")
    if export_name is not None and (
        not isinstance(export_name, str)
        or not export_name.strip()
        or len(export_name.strip()) > 120
    ):
        raise ValueError(
            f"Studio metric {metric_id} export_name must be a non-empty string "
            "of at most 120 characters"
        )

    export_columns = metric.get("export_columns")
    aliases = metric.get("export_column_aliases")
    if export_columns is None:
        if aliases is not None:
            raise ValueError(
                f"Studio metric {metric_id} export_column_aliases requires "
                "export_columns"
            )
        return
    validated_export_columns = _validated_registry_columns(
        export_columns,
        context=f"Studio metric {metric_id}",
        field="export_columns",
        allow_empty=False,
    )
    undeclared = [
        column for column in validated_export_columns if column not in columns
    ]
    if undeclared:
        raise ValueError(
            f"Studio metric {metric_id} export_columns references undeclared "
            f"columns: {', '.join(undeclared)}"
        )
    if not metric.get("is_exportable"):
        raise ValueError(
            f"Studio metric {metric_id} export_columns requires is_exportable true"
        )
    if aliases is None:
        return
    if not isinstance(aliases, dict):
        raise ValueError(
            f"Studio metric {metric_id} export_column_aliases must be a mapping"
        )
    unknown_aliases = [
        str(column) for column in aliases if column not in validated_export_columns
    ]
    if unknown_aliases:
        raise ValueError(
            f"Studio metric {metric_id} export_column_aliases references columns "
            f"outside export_columns: {', '.join(unknown_aliases)}"
        )
    output_columns = []
    for source_column in validated_export_columns:
        output_column = aliases.get(source_column, source_column)
        output_columns.append(
            _validated_column_reference(
                output_column,
                context=f"Studio metric {metric_id}",
                field=f"export alias for {source_column}",
            )
        )
    _require_unique(
        f"export output columns in metric {metric_id}",
        output_columns,
    )


def _validate_metric(metric: dict, dashboards_by_id: dict[str, dict]) -> None:
    required_fields = {
        "id",
        "dashboard_id",
        "name",
        "description",
        "section",
        "visualization_type",
        "query_id",
        "query_url",
        "data_file",
        "columns",
        "data_source",
        "last_updated",
        "is_exportable",
        "default_visible",
        "display_order",
        "format",
    }
    missing = sorted(
        field for field in required_fields if metric.get(field) in (None, "")
    )
    if missing:
        raise _metric_registry_error(
            metric,
            field=", ".join(missing),
            problem=f"missing required fields: {', '.join(missing)}",
            correction="configure every listed field; query_id must identify a registered positive Dune query",
        )
    metric_id = str(metric["id"])
    context = _studio_metric_context(metric)
    if not STUDIO_ID_PATTERN.fullmatch(metric_id):
        raise ValueError(f"Invalid Studio metric id: {metric_id}")
    dashboard_id = str(metric["dashboard_id"])
    dashboard = dashboards_by_id.get(dashboard_id)
    if dashboard is None:
        raise _metric_registry_error(
            metric,
            field="dashboard_id",
            problem=f"references unknown dashboard {dashboard_id}",
            correction="use the id of a configured Studio dashboard",
        )
    dashboard_sections = {str(section["id"]) for section in dashboard["sections"]}
    if str(metric["section"]) not in dashboard_sections:
        raise _metric_registry_error(
            metric,
            field="section",
            problem=f"references unknown section {metric['section']}",
            correction="use a section id configured on this dashboard",
        )
    visualization_type = str(metric["visualization_type"])
    if visualization_type not in STUDIO_VISUALIZATION_TYPES:
        raise _metric_registry_error(
            metric,
            field="visualization_type",
            problem=f"unsupported visualization type {visualization_type}",
            correction=(
                "choose one of "
                + ", ".join(sorted(STUDIO_VISUALIZATION_TYPES))
            ),
        )
    if str(metric["format"]) not in STUDIO_FORMATS:
        raise _metric_registry_error(
            metric,
            field="format",
            problem=f"unsupported format {metric['format']}",
            correction="choose one of " + ", ".join(sorted(STUDIO_FORMATS)),
        )
    source_label = metric.get("source_label")
    if source_label is not None and (
        not isinstance(source_label, str) or not source_label.strip()
    ):
        raise ValueError(
            f"Studio metric {metric_id} source_label must be a non-empty string"
        )
    provider_mode = str(metric.get("provider_mode") or "fixture")
    if provider_mode not in STUDIO_PROVIDER_MODES:
        raise ValueError(
            f"Studio metric {metric_id} provider_mode must be fixture or latest_result"
        )
    export_slug = metric.get("export_slug")
    if export_slug is not None and (
        not isinstance(export_slug, str)
        or not STUDIO_EXPORT_SLUG_PATTERN.fullmatch(export_slug)
    ):
        raise ValueError(f"Studio metric {metric_id} export_slug is unsafe")
    _validated_query_transformation(metric)
    _validate_methodology_content(metric)
    if str(metric.get("size") or "medium") not in STUDIO_SIZES:
        raise ValueError(f"Studio metric {metric_id} has unsupported size {metric.get('size')}")
    query_id = metric["query_id"]
    if type(query_id) is not int or query_id <= 0:
        raise _metric_registry_error(
            metric,
            field="query_id",
            problem="query_id must be a positive integer",
            correction="set query_id to the positive integer ID of the intended Dune query",
        )
    expected_query_url = studio_query_url(query_id)
    if str(metric["query_url"]).rstrip("/") != expected_query_url:
        raise _metric_registry_error(
            metric,
            field="query_url",
            problem=f"query_url does not match query_id {query_id}",
            correction=f"set query_url to {expected_query_url}",
        )
    expected_data_file = studio_query_data_file(query_id)
    data_file = str(metric["data_file"])
    if (
        Path(data_file).name != data_file
        or not STUDIO_QUERY_FILE_PATTERN.fullmatch(data_file)
        or data_file != expected_data_file
    ):
        raise _metric_registry_error(
            metric,
            field="data_file",
            problem=f"data_file must be {expected_data_file}",
            correction=f"set data_file to {expected_data_file}",
        )
    column_groups = _validated_metric_column_groups(
        metric,
        metric_id=metric_id,
        context=context,
    )
    _validate_safe_metric_column_references(
        metric,
        metric_id=metric_id,
        context=context,
    )
    columns = column_groups["columns"]
    intelligence_component = metric.get("intelligence_component")
    derived_data_source = metric.get("derived_data_source")
    if intelligence_component is not None:
        if intelligence_component not in STUDIO_INTELLIGENCE_COMPONENTS:
            raise ValueError(
                f"Studio metric {metric_id} has unsupported "
                "intelligence_component"
            )
        direct_source_components = {
            "recent_referral_deposits",
            "recent_etherfi_activity",
        }
        if (
            derived_data_source is None
            and intelligence_component not in direct_source_components
        ):
            raise ValueError(
                f"Studio metric {metric_id} intelligence_component needs a "
                "safe derived_data_source"
            )
        if derived_data_source is not None and (
            not isinstance(derived_data_source, str)
            or not STUDIO_ID_PATTERN.fullmatch(derived_data_source)
        ):
            raise ValueError(
                f"Studio metric {metric_id} intelligence_component needs a "
                "safe derived_data_source"
            )
    elif derived_data_source is not None:
        raise ValueError(
            f"Studio metric {metric_id} derived_data_source requires "
            "intelligence_component"
        )
    for field in (
        "intelligence_category_column",
        "intelligence_value_column",
    ):
        value = metric.get(field)
        if value is not None and (
            not isinstance(value, str)
            or not STUDIO_COLUMN_PATTERN.fullmatch(value)
        ):
            raise ValueError(
                f"Studio metric {metric_id} {field} must be a safe column"
            )

    related_query_urls = metric.get("related_query_urls")
    if related_query_urls is not None:
        if not isinstance(related_query_urls, list) or not related_query_urls:
            raise ValueError(
                f"Studio metric {metric_id} related_query_urls must be a "
                "non-empty list"
            )
        invalid_query_urls = [
            str(url)
            for url in related_query_urls
            if not isinstance(url, str)
            or not re.fullmatch(r"https://dune\.com/queries/[1-9][0-9]*", url)
        ]
        if invalid_query_urls:
            raise ValueError(
                f"Studio metric {metric_id} has invalid related_query_urls"
            )
        _require_unique(
            f"related query URLs in metric {metric_id}",
            related_query_urls,
        )

    top_n_options = metric.get("top_n_options")
    if top_n_options is not None:
        if (
            visualization_type != "bar"
            or not isinstance(top_n_options, list)
            or not top_n_options
            or any(
                type(option) is not int or option < 1 or option > 1000
                for option in top_n_options
            )
        ):
            raise ValueError(
                f"Studio metric {metric_id} top_n_options must be positive "
                "integers for a bar metric"
            )
        _require_unique(f"top N options in metric {metric_id}", top_n_options)
        default_top_n = metric.get("default_top_n")
        if default_top_n not in top_n_options:
            raise ValueError(
                f"Studio metric {metric_id} default_top_n must be in "
                "top_n_options"
            )

    intelligence_columns = _validated_registry_columns(
        metric.get("intelligence_columns") or [],
        context=context,
        field="intelligence_columns",
    )
    _validated_registry_columns(
        metric.get("intelligence_export_columns") or [],
        context=context,
        field="intelligence_export_columns",
    )
    intelligence_column_set = set(intelligence_columns)
    available_presentation_columns = set(columns) | intelligence_column_set
    for field in ("table_columns", "table_search_columns"):
        configured_columns = metric.get(field)
        if configured_columns is None:
            continue
        validated_columns = _validated_registry_columns(
            configured_columns,
            context=context,
            field=field,
            allow_empty=False,
        )
        undeclared = [
            column
            for column in validated_columns
            if column not in available_presentation_columns
        ]
        if undeclared:
            raise ValueError(
                f"Studio metric {metric_id} {field} references undeclared "
                f"columns: {', '.join(undeclared)}"
            )
    for mapping_name in (
        "intelligence_column_labels",
        "intelligence_column_formats",
    ):
        mapping = metric.get(mapping_name)
        if mapping is None:
            continue
        if (
            not isinstance(mapping, dict)
            or any(column not in intelligence_column_set for column in mapping)
        ):
            raise ValueError(
                f"Studio metric {metric_id} has invalid {mapping_name}"
            )
    invalid_intelligence_formats = sorted(
        {
            str(value)
            for value in (metric.get("intelligence_column_formats") or {}).values()
            if not isinstance(value, str) or value not in STUDIO_TABLE_FORMATS
        }
    )
    if invalid_intelligence_formats:
        raise ValueError(
            f"Studio metric {metric_id} has unsupported intelligence table "
            "formats: " + ", ".join(invalid_intelligence_formats)
        )

    concentration_tiers = metric.get("concentration_tiers")
    if concentration_tiers is not None:
        if (
            intelligence_component != "referral_concentration"
            or not isinstance(concentration_tiers, list)
            or not concentration_tiers
            or any(type(tier) is not int or tier < 1 for tier in concentration_tiers)
        ):
            raise ValueError(
                f"Studio metric {metric_id} has invalid concentration_tiers"
            )
        _require_unique(
            f"concentration tiers in metric {metric_id}", concentration_tiers
        )
    concentration_measures = metric.get("concentration_measures")
    if concentration_measures is not None:
        if (
            intelligence_component != "referral_concentration"
            or not isinstance(concentration_measures, list)
            or not concentration_measures
            or any(
                not isinstance(measure, dict)
                or set(measure) != {"id", "label", "column"}
                or not isinstance(measure["id"], str)
                or not STUDIO_ID_PATTERN.fullmatch(measure["id"])
                or not isinstance(measure["label"], str)
                or not measure["label"].strip()
                or not isinstance(measure["column"], str)
                or not STUDIO_COLUMN_PATTERN.fullmatch(measure["column"])
                for measure in concentration_measures
            )
        ):
            raise ValueError(
                f"Studio metric {metric_id} has invalid concentration_measures"
            )
        measure_ids = [measure["id"] for measure in concentration_measures]
        _require_unique(
            f"concentration measures in metric {metric_id}", measure_ids
        )
        if metric.get("default_concentration_measure") not in measure_ids:
            raise ValueError(
                f"Studio metric {metric_id} default_concentration_measure "
                "must reference a configured measure"
            )

    _validate_growth_chart(metric, columns)
    for boolean_field in ("is_exportable", "default_visible"):
        if not isinstance(metric[boolean_field], bool):
            raise ValueError(f"Studio metric {metric_id} {boolean_field} must be boolean")
    if not isinstance(metric.get("allow_empty"), bool):
        raise ValueError(f"Studio metric {metric_id} allow_empty must be boolean")
    _normalize_freshness_policy(
        metric.get("freshness_policy"),
        context=f"Studio metric {metric_id}",
    )
    _normalize_freshness_policy(
        metric.get("effective_freshness_policy"),
        context=f"Studio metric {metric_id} effective",
    )
    if not isinstance(metric["display_order"], int):
        raise ValueError(f"Studio metric {metric_id} display_order must be an integer")
    _validate_metric_export_config(metric, columns)
    comparison_column = metric.get("comparison_column")
    if comparison_column:
        _validated_column_reference(
            comparison_column,
            context=f"Studio metric {metric_id}",
            field="comparison_column",
        )
        if comparison_column in column_groups["optional_columns"]:
            raise ValueError(
                f"Studio metric {metric_id} comparison_column cannot be optional"
            )
    sparkline_source = metric.get("sparkline_data_source")
    if sparkline_source:
        if not metric.get("sparkline_column"):
            raise ValueError(f"Studio metric {metric_id} needs sparkline_column")
        if not metric.get("sparkline_date_column"):
            raise ValueError(
                f"Studio metric {metric_id} needs sparkline_date_column"
            )
        _validated_column_reference(
            metric["sparkline_column"],
            context=f"Studio metric {metric_id}",
            field="sparkline_column",
        )
        _validated_column_reference(
            metric["sparkline_date_column"],
            context=f"Studio metric {metric_id}",
            field="sparkline_date_column",
        )

    counter_only_fields = (
        "compact_counter",
        "period_key_column",
        "period_key_map",
    )
    if visualization_type != "counter":
        configured_counter_fields = [
            field for field in counter_only_fields if field in metric
        ]
        if configured_counter_fields:
            raise ValueError(
                f"Studio metric {metric_id} fields "
                f"{', '.join(configured_counter_fields)} are supported only for counters"
            )

    if visualization_type == "counter":
        compact_counter = metric.get("compact_counter")
        if compact_counter is not None and not isinstance(compact_counter, bool):
            raise ValueError(
                f"Studio counter metric {metric_id} compact_counter must be boolean"
            )
        value_column = metric.get("value_column")
        if compact_counter and not value_column:
            raise ValueError(
                f"Studio counter metric {metric_id} compact_counter needs value_column"
            )
        if value_column and value_column not in columns:
            raise ValueError(
                f"Studio counter metric {metric_id} value_column must be declared in columns"
            )
        period_key_column = metric.get("period_key_column")
        period_key_map = metric.get("period_key_map")
        if (period_key_column is None) != (period_key_map is None):
            raise ValueError(
                f"Studio counter metric {metric_id} period_key_column and "
                "period_key_map must be configured together"
            )
        if period_key_column is not None:
            if period_key_column not in columns:
                raise ValueError(
                    f"Studio counter metric {metric_id} period_key_column must "
                    "be declared in columns"
                )
            if not isinstance(period_key_map, dict) or not period_key_map:
                raise ValueError(
                    f"Studio counter metric {metric_id} period_key_map must be "
                    "a non-empty mapping"
                )
            invalid_ranges = [
                str(value) for value in period_key_map if value not in STUDIO_RANGE_OPTIONS
            ]
            if invalid_ranges:
                raise ValueError(
                    f"Studio counter metric {metric_id} period_key_map has "
                    f"unsupported ranges: {', '.join(invalid_ranges)}"
                )
            invalid_period_keys = [
                str(value)
                for value in period_key_map.values()
                if not isinstance(value, str)
                or not STUDIO_PERIOD_KEY_PATTERN.fullmatch(value)
            ]
            if invalid_period_keys:
                raise ValueError(
                    f"Studio counter metric {metric_id} period_key_map has "
                    f"invalid period keys: {', '.join(invalid_period_keys)}"
                )
            _require_unique(
                f"period keys in metric {metric_id}",
                list(period_key_map.values()),
            )
    elif visualization_type == "line":
        if not metric.get("date_column"):
            raise _metric_registry_error(
                metric,
                field="date_column",
                problem="line visualization needs date_column",
                correction="reference a date column declared in columns",
            )
        if not metric.get("series"):
            raise _metric_registry_error(
                metric,
                field="series",
                problem="line visualization needs at least one series",
                correction="add a series list with declared column and non-empty label values",
            )
        if metric["date_column"] not in columns:
            raise _metric_registry_error(
                metric,
                field="date_column",
                problem="date_column must be declared in columns",
                correction="add the referenced date column to columns or correct date_column",
            )
        for series_index, series in enumerate(metric["series"]):
            if not isinstance(series, dict) or not series.get("column") or not series.get("label"):
                raise _metric_registry_error(
                    metric,
                    field=f"series[{series_index}]",
                    problem="invalid series; column and label are required",
                    correction="provide a declared column and a non-empty label",
                )
            if series["column"] not in columns:
                raise _metric_registry_error(
                    metric,
                    field=f"series[{series_index}].column",
                    problem=f"series column {series['column']} is not declared",
                    correction="add the referenced series column to columns or correct the reference",
                )
        allowed_visualizations = metric.get("allowed_visualizations")
        default_visualization = metric.get("default_visualization")
        if (
            not isinstance(allowed_visualizations, list)
            or not allowed_visualizations
            or not all(
                isinstance(visualization, str)
                and visualization in STUDIO_LINE_VISUALIZATIONS
                for visualization in allowed_visualizations
            )
        ):
            raise _metric_registry_error(
                metric,
                field="allowed_visualizations",
                problem="invalid allowed_visualizations",
                correction=(
                    "provide a non-empty list containing only area, column, line, or scatter"
                ),
            )
        duplicate_visualizations = sorted(
            {
                visualization
                for visualization in allowed_visualizations
                if allowed_visualizations.count(visualization) > 1
            }
        )
        if duplicate_visualizations:
            raise _metric_registry_error(
                metric,
                field="allowed_visualizations",
                problem=(
                    "duplicate allowed line visualizations: "
                    + ", ".join(duplicate_visualizations)
                ),
                correction="list each allowed visualization once",
            )
        if default_visualization not in allowed_visualizations:
            raise _metric_registry_error(
                metric,
                field="default_visualization",
                problem="default_visualization must be allowed",
                correction="choose a value present in allowed_visualizations",
            )
    elif visualization_type == "bar":
        for field in ("orientation", "category_column", "value_column"):
            if not metric.get(field):
                raise ValueError(f"Studio bar metric {metric_id} needs {field}")
        if metric["orientation"] not in {"horizontal", "vertical"}:
            raise ValueError(f"Studio bar metric {metric_id} has invalid orientation")
        for field in ("category_column", "value_column"):
            if metric[field] not in columns:
                raise ValueError(
                    f"Studio bar metric {metric_id} {field} must be declared in columns"
                )
    elif visualization_type == "sankey":
        for field in ("source_column", "target_column", "value_column"):
            if not metric.get(field):
                raise ValueError(f"Studio Sankey metric {metric_id} needs {field}")
            if metric[field] not in columns:
                raise ValueError(
                    f"Studio Sankey metric {metric_id} {field} must be declared in columns"
                )
        stage_columns = metric.get("stage_columns") or [
            metric["source_column"],
            metric["target_column"],
        ]
        if not isinstance(stage_columns, list) or len(stage_columns) not in {2, 3}:
            raise ValueError(
                f"Studio Sankey metric {metric_id} stage_columns must contain two or three columns"
            )
        if len(stage_columns) != len(set(stage_columns)):
            raise ValueError(
                f"Studio Sankey metric {metric_id} stage_columns must be unique"
            )
        undeclared_stages = [column for column in stage_columns if column not in columns]
        if undeclared_stages:
            raise ValueError(
                f"Studio Sankey metric {metric_id} stage_columns must be declared in columns"
            )
        exit_value_column = metric.get("exit_value_column")
        if exit_value_column and exit_value_column not in columns:
            raise ValueError(
                f"Studio Sankey metric {metric_id} exit_value_column must be declared in columns"
            )
        destination_top_n = metric.get("destination_top_n")
        destination_others_label = metric.get("destination_others_label")
        preserve_destinations = metric.get("preserve_destinations")
        aggregation_configured = any(
            value is not None
            for value in (
                destination_top_n,
                destination_others_label,
                preserve_destinations,
            )
        )
        if aggregation_configured:
            if (
                type(destination_top_n) is not int
                or destination_top_n < 1
                or destination_top_n > 100
            ):
                raise ValueError(
                    f"Studio Sankey metric {metric_id} destination_top_n must "
                    "be an integer from 1 through 100"
                )
            if (
                not isinstance(destination_others_label, str)
                or not destination_others_label.strip()
            ):
                raise ValueError(
                    f"Studio Sankey metric {metric_id} "
                    "destination_others_label must be a non-empty string"
                )
            if preserve_destinations is None:
                preserve_destinations = []
            if not isinstance(preserve_destinations, list) or any(
                not isinstance(value, str) or not value.strip()
                for value in preserve_destinations
            ):
                raise ValueError(
                    f"Studio Sankey metric {metric_id} preserve_destinations "
                    "must be a string list"
                )
            _require_unique(
                f"preserved destinations in metric {metric_id}",
                preserve_destinations,
            )
            if destination_others_label in preserve_destinations:
                raise ValueError(
                    f"Studio Sankey metric {metric_id} destination_others_label "
                    "cannot also be preserved"
                )
    elif visualization_type == "table":
        if not isinstance(metric.get("page_size"), int) or metric["page_size"] <= 0:
            raise ValueError(f"Studio table metric {metric_id} needs a positive page_size")
        page_size_options = metric.get("page_size_options")
        if page_size_options is not None:
            if (
                not isinstance(page_size_options, list)
                or not page_size_options
                or any(
                    type(option) is not int or option <= 0
                    for option in page_size_options
                )
            ):
                raise ValueError(
                    f"Studio table metric {metric_id} page_size_options must "
                    "be positive integers"
                )
            _require_unique(
                f"page size options in metric {metric_id}",
                page_size_options,
            )
            if metric["page_size"] not in page_size_options:
                raise ValueError(
                    f"Studio table metric {metric_id} page_size must be in "
                    "page_size_options"
                )
        default_sort_column = metric.get("default_sort_column")
        if default_sort_column is not None and (
            not isinstance(default_sort_column, str)
            or default_sort_column not in available_presentation_columns
        ):
            raise ValueError(
                f"Studio table metric {metric_id} default_sort_column must be "
                "declared"
            )
        default_sort_direction = metric.get("default_sort_direction")
        if default_sort_direction is not None and default_sort_direction not in {
            "ascending",
            "descending",
        }:
            raise ValueError(
                f"Studio table metric {metric_id} default_sort_direction must "
                "be ascending or descending"
            )
        investigate_address_column = metric.get("investigate_address_column")
        if investigate_address_column is not None and (
            not isinstance(investigate_address_column, str)
            or investigate_address_column not in available_presentation_columns
        ):
            raise ValueError(
                f"Studio table metric {metric_id} investigate_address_column "
                "must be declared"
            )
        signed_value_columns = metric.get("signed_value_columns")
        if signed_value_columns is not None:
            validated_signed_columns = _validated_registry_columns(
                signed_value_columns,
                context=context,
                field="signed_value_columns",
                allow_empty=False,
            )
            undeclared_signed_columns = [
                column
                for column in validated_signed_columns
                if column not in available_presentation_columns
            ]
            if undeclared_signed_columns:
                raise ValueError(
                    f"Studio table metric {metric_id} signed_value_columns "
                    "must be declared"
                )
        if "export_respects_period" in metric and not isinstance(
            metric["export_respects_period"], bool
        ):
            raise ValueError(
                f"Studio table metric {metric_id} export_respects_period must "
                "be boolean"
            )
        for identifier_mapping in ("address_columns", "transaction_columns"):
            identifier_columns = metric.get(identifier_mapping) or []
            if not isinstance(identifier_columns, list):
                raise _metric_registry_error(
                    metric,
                    field=identifier_mapping,
                    problem=f"invalid {identifier_mapping}",
                    correction="provide a list of column names declared in columns",
                )
            for identifier_column in identifier_columns:
                if identifier_column in columns:
                    continue
                raise _metric_registry_error(
                    metric,
                    field=identifier_mapping,
                    problem=(
                        f"{identifier_mapping[:-1]} {identifier_column} "
                        "must be declared"
                    ),
                    correction="add the referenced identifier column to columns or remove the reference",
                )
        if set(metric.get("address_columns") or []) & set(
            metric.get("transaction_columns") or []
        ):
            raise _metric_registry_error(
                metric,
                field="address_columns, transaction_columns",
                problem="identifier columns must be unambiguous",
                correction="declare each identifier column as either an address or a transaction, not both",
            )
        default_chain = metric.get("default_chain")
        if default_chain and (
            not isinstance(default_chain, str)
            or default_chain not in STUDIO_EXPLORER_CHAINS
        ):
            raise ValueError(
                f"Studio table metric {metric_id} has unsupported default_chain"
            )
        chain_column = metric.get("chain_column")
        if chain_column and chain_column not in columns:
            raise ValueError(
                f"Studio table metric {metric_id} chain_column must be declared in columns"
            )
        if metric.get("date_column") and metric["date_column"] not in columns:
            raise ValueError(
                f"Studio table metric {metric_id} date_column must be declared in columns"
            )
        for mapping_name in ("column_labels", "column_formats"):
            mapping = metric.get(mapping_name) or {}
            if not isinstance(mapping, dict) or any(key not in columns for key in mapping):
                raise _metric_registry_error(
                    metric,
                    field=mapping_name,
                    problem=f"invalid {mapping_name}",
                    correction="map only column names declared in columns",
                )
        invalid_table_formats = sorted(
            {
                str(value)
                for value in (metric.get("column_formats") or {}).values()
                if not isinstance(value, str) or value not in STUDIO_TABLE_FORMATS
            }
        )
        if invalid_table_formats:
            raise _metric_registry_error(
                metric,
                field="column_formats",
                problem=(
                    "unsupported column formats: "
                    + ", ".join(invalid_table_formats)
                ),
                correction="choose supported Studio table formats",
            )


def _tighten_freshness_policy(target: dict, policy: dict) -> None:
    for field, value in policy.items():
        current = target.get(field)
        if current is None or value < current:
            target[field] = value


def build_studio_query_contracts(metric_values: list[dict]) -> dict[int, dict]:
    contracts: dict[int, dict] = {}
    source_to_query: dict[str, int] = {}
    source_origins: dict[str, str] = {}
    output_file_owners: dict[str, tuple[int, str]] = {}
    metric_ids: list[str] = []
    metrics = [normalize_studio_metric(value) for value in metric_values]

    prechecked_metric_ids: list[str] = []
    prechecked_output_files: dict[str, tuple[int, str]] = {}
    for metric in metrics:
        metric_id = str(metric.get("id") or "<unknown>")
        if metric_id in prechecked_metric_ids:
            raise ValueError(f"Duplicate Studio metric ids: {metric_id}")
        prechecked_metric_ids.append(metric_id)
        query_id = metric.get("query_id")
        if type(query_id) is not int or query_id <= 0:
            raise ValueError(
                f"Studio metric {metric_id} query_id must be a positive integer"
            )
        data_file = metric.get("data_file")
        if (
            not isinstance(data_file, str)
            or Path(data_file).name != data_file
            or not STUDIO_QUERY_FILE_PATTERN.fullmatch(data_file)
        ):
            raise ValueError(
                f"Studio metric {metric_id} has unsafe output data_file {data_file}"
            )
        output_owner = prechecked_output_files.get(data_file)
        if output_owner is not None and output_owner[0] != query_id:
            raise ValueError(
                f"Duplicate Studio query output filename {data_file}: query "
                f"{output_owner[0]} from metric {output_owner[1]} and query "
                f"{query_id} from metric {metric_id}"
            )
        prechecked_output_files[data_file] = (query_id, metric_id)

    for metric in metrics:
        metric_id = str(metric.get("id") or "<unknown>")
        if metric_id in metric_ids:
            raise ValueError(f"Duplicate Studio metric ids: {metric_id}")
        metric_ids.append(metric_id)

        query_id = metric.get("query_id")
        if type(query_id) is not int or query_id <= 0:
            raise ValueError(
                f"Studio metric {metric_id} query_id must be a positive integer"
            )
        query_url_value = metric.get("query_url")
        if not isinstance(query_url_value, str) or not query_url_value.strip():
            raise ValueError(f"Studio metric {metric_id} needs query_url")
        query_url = query_url_value.rstrip("/")
        expected_query_url = studio_query_url(query_id)
        if query_url != expected_query_url:
            raise ValueError(
                f"Studio metric {metric_id} query_url does not match query_id "
                f"{query_id}"
            )

        data_file_value = metric.get("data_file")
        if not isinstance(data_file_value, str):
            raise ValueError(f"Studio metric {metric_id} needs data_file")
        data_file = data_file_value
        if (
            Path(data_file).name != data_file
            or not STUDIO_QUERY_FILE_PATTERN.fullmatch(data_file)
        ):
            raise ValueError(
                f"Studio metric {metric_id} has unsafe output data_file {data_file}"
            )
        output_owner = output_file_owners.get(data_file)
        if output_owner is not None and output_owner[0] != query_id:
            raise ValueError(
                f"Duplicate Studio query output filename {data_file}: query "
                f"{output_owner[0]} from metric {output_owner[1]} and query "
                f"{query_id} from metric {metric_id}"
            )
        output_file_owners[data_file] = (query_id, metric_id)
        expected_data_file = studio_query_data_file(query_id)
        if data_file != expected_data_file:
            raise ValueError(
                f"Studio metric {metric_id} data_file must be {expected_data_file}"
            )

        data_source_value = metric.get("data_source")
        if not isinstance(data_source_value, str) or not data_source_value.strip():
            raise ValueError(f"Studio metric {metric_id} needs data_source")
        data_source = data_source_value.strip()
        column_groups = _validated_metric_column_groups(
            metric,
            metric_id=metric_id,
        )
        _validate_safe_metric_column_references(metric, metric_id=metric_id)
        required_columns = list(column_groups["columns"])
        comparison_column = metric.get("comparison_column")
        if comparison_column:
            comparison_column = _validated_column_reference(
                comparison_column,
                context=f"Studio metric {metric_id}",
                field="comparison_column",
            )
            if comparison_column in column_groups["optional_columns"]:
                raise ValueError(
                    f"Studio metric {metric_id} comparison_column cannot be optional"
                )
            _append_unique(required_columns, [comparison_column])
        dimension_columns, value_columns = _metric_semantic_column_groups(
            metric,
            metric_id=metric_id,
            column_groups=column_groups,
            required_columns=required_columns,
        )

        source_label = metric.get("source_label")
        if source_label is not None and (
            not isinstance(source_label, str) or not source_label.strip()
        ):
            raise ValueError(
                f"Studio metric {metric_id} source_label must be a non-empty string"
            )
        if isinstance(source_label, str):
            source_label = source_label.strip()
        is_exportable = metric.get("is_exportable")
        if not isinstance(is_exportable, bool):
            raise ValueError(
                f"Studio metric {metric_id} is_exportable must be boolean"
            )
        allow_empty = metric.get("allow_empty")
        if not isinstance(allow_empty, bool):
            raise ValueError(f"Studio metric {metric_id} allow_empty must be boolean")
        freshness_policy = _normalize_freshness_policy(
            metric.get("effective_freshness_policy")
            if "effective_freshness_policy" in metric
            else metric.get("freshness_policy"),
            context=f"Studio metric {metric_id} effective",
        )
        provider_mode = str(metric.get("provider_mode") or "fixture")
        transformation = _validated_query_transformation(metric)

        contract = contracts.get(query_id)
        if contract is None:
            contract = {
                "query_id": query_id,
                "query_url": query_url,
                "data_file": data_file,
                "data_source": data_source,
                "source_label": source_label,
                "provider_mode": provider_mode,
                "transformation": transformation,
                "source_required_columns": list(
                    (transformation or {}).get("source_required_columns") or []
                ),
                "source_labels": [],
                "required_columns": [],
                "optional_columns": [],
                "date_columns": [],
                "address_columns": [],
                "transaction_columns": [],
                "dimension_columns": [],
                "value_columns": [],
                "metric_ids": [],
                "supporting_metric_ids": [],
                "metric_metadata": [],
                "dashboard_ids": [],
                "is_exportable": False,
                "allow_empty": True,
                "freshness_policy": {},
                "_field_origins": {
                    "query_url": metric_id,
                    "data_file": metric_id,
                    "data_source": metric_id,
                    "provider_mode": metric_id,
                    "transformation": metric_id,
                },
            }
            contracts[query_id] = contract
        else:
            for field, value in (
                ("query_url", query_url),
                ("data_file", data_file),
                ("data_source", data_source),
                ("provider_mode", provider_mode),
                ("transformation", transformation),
            ):
                if contract[field] != value:
                    origin = contract["_field_origins"][field]
                    raise ValueError(
                        f"Studio query {query_id} maps to inconsistent {field}: "
                        f"metric {origin} uses {contract[field]!r}; metric "
                        f"{metric_id} uses {value!r}"
                    )

        mapped_query_id = source_to_query.get(data_source)
        if mapped_query_id is not None and mapped_query_id != query_id:
            raise ValueError(
                f"Studio data source {data_source} maps to multiple query IDs: "
                f"{mapped_query_id} from metric {source_origins[data_source]} "
                f"and {query_id} from metric {metric_id}"
            )
        source_to_query[data_source] = query_id
        source_origins[data_source] = metric_id

        _append_unique(contract["required_columns"], required_columns)
        _append_unique(
            contract["optional_columns"],
            column_groups["optional_columns"],
        )
        date_columns = (
            [str(metric["date_column"])] if metric.get("date_column") else []
        )
        address_columns = list(metric.get("address_columns") or [])
        transaction_columns = list(metric.get("transaction_columns") or [])
        for field, values in (
            ("date_columns", date_columns),
            ("address_columns", address_columns),
            ("transaction_columns", transaction_columns),
        ):
            undeclared = [
                column
                for column in values
                if column not in column_groups["columns"]
            ]
            if undeclared:
                raise ValueError(
                    f"Studio metric {metric_id} {field} references undeclared "
                    f"columns: {', '.join(undeclared)}"
                )
        _append_unique(contract["date_columns"], date_columns)
        _append_unique(contract["address_columns"], address_columns)
        _append_unique(contract["transaction_columns"], transaction_columns)
        _append_unique(
            contract["dimension_columns"],
            dimension_columns,
        )
        _append_unique(
            contract["value_columns"],
            value_columns,
        )
        contract["metric_ids"].append(metric_id)
        dashboard_id = str(metric.get("dashboard_id") or "")
        if dashboard_id and dashboard_id not in contract["dashboard_ids"]:
            contract["dashboard_ids"].append(dashboard_id)
        contract["is_exportable"] = bool(
            contract["is_exportable"] or is_exportable
        )
        contract["allow_empty"] = bool(contract["allow_empty"] and allow_empty)
        _tighten_freshness_policy(contract["freshness_policy"], freshness_policy)
        if source_label:
            _append_unique(contract["source_labels"], [source_label])
            contract["source_label"] = (
                contract["source_labels"][0]
                if len(contract["source_labels"]) == 1
                else None
            )
        contract["metric_metadata"].append(
            {
                "metric_id": metric_id,
                "dashboard_id": dashboard_id,
                "visualization_type": str(metric.get("visualization_type") or ""),
                "source_label": source_label,
                "provider_mode": provider_mode,
                "transformation": transformation,
                "required_columns": required_columns,
                "optional_columns": list(column_groups["optional_columns"]),
                "date_columns": date_columns,
                "address_columns": address_columns,
                "transaction_columns": transaction_columns,
                "dimension_columns": dimension_columns,
                "value_columns": value_columns,
                "is_exportable": is_exportable,
                "allow_empty": allow_empty,
                "freshness_policy": freshness_policy,
            }
        )

    for metric in metrics:
        sparkline_source = metric.get("sparkline_data_source")
        if not sparkline_source:
            continue
        metric_id = str(metric.get("id") or "<unknown>")
        sparkline_query_id = source_to_query.get(str(sparkline_source))
        if sparkline_query_id is None:
            raise ValueError(
                f"Studio metric {metric_id} sparkline source {sparkline_source} "
                "does not map to a configured query"
            )
        sparkline_column = metric.get("sparkline_column")
        if not sparkline_column:
            raise ValueError(f"Studio metric {metric_id} needs sparkline_column")
        sparkline_column = _validated_column_reference(
            sparkline_column,
            context=f"Studio metric {metric_id}",
            field="sparkline_column",
        )
        sparkline_date_column = metric.get("sparkline_date_column")
        if not sparkline_date_column:
            raise ValueError(
                f"Studio metric {metric_id} needs sparkline_date_column"
            )
        sparkline_date_column = _validated_column_reference(
            sparkline_date_column,
            context=f"Studio metric {metric_id}",
            field="sparkline_date_column",
        )
        supporting_contract = contracts[sparkline_query_id]
        _append_unique(
            supporting_contract["required_columns"],
            [sparkline_column, sparkline_date_column],
        )
        _append_unique(
            supporting_contract["dimension_columns"],
            [sparkline_date_column],
        )
        _append_unique(
            supporting_contract["date_columns"],
            [sparkline_date_column],
        )
        _append_unique(
            supporting_contract["value_columns"],
            [sparkline_column],
        )
        _append_unique(supporting_contract["supporting_metric_ids"], [metric_id])
        dashboard_id = str(metric.get("dashboard_id") or "")
        if dashboard_id and dashboard_id not in supporting_contract["dashboard_ids"]:
            supporting_contract["dashboard_ids"].append(dashboard_id)
        freshness_policy = _normalize_freshness_policy(
            metric.get("effective_freshness_policy")
            if "effective_freshness_policy" in metric
            else metric.get("freshness_policy"),
            context=f"Studio metric {metric_id} effective",
        )
        _tighten_freshness_policy(
            supporting_contract["freshness_policy"],
            freshness_policy,
        )

    for contract in contracts.values():
        contract["optional_columns"] = [
            column
            for column in contract["optional_columns"]
            if column not in contract["required_columns"]
        ]
        contract.pop("_field_origins", None)
    return contracts


def _normalize_generated_query_metadata(
    value: dict,
    *,
    context: str,
    require_data_file: bool,
) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a mapping")
    normalized = dict(value)
    if normalized.get("schema_version") != STUDIO_DATA_SCHEMA_VERSION:
        raise ValueError(
            f"{context} schema_version must be {STUDIO_DATA_SCHEMA_VERSION}"
        )
    query_id = normalized.get("query_id")
    if type(query_id) is not int or query_id <= 0:
        raise ValueError(f"{context} query_id must be a positive integer")

    expected_url = studio_query_url(query_id)
    query_url_value = normalized.get("query_url")
    if not isinstance(query_url_value, str) or not query_url_value.strip():
        raise ValueError(f"{context} needs query_url")
    query_url = query_url_value.rstrip("/")
    if query_url != expected_url:
        raise ValueError(f"{context} query_url does not match query_id {query_id}")
    normalized["query_url"] = query_url

    execution_id = normalized.get("execution_id")
    if (
        not isinstance(execution_id, str)
        or not STUDIO_EXECUTION_ID_PATTERN.fullmatch(execution_id)
    ):
        raise ValueError(f"{context} needs a valid execution_id")

    expected_file = studio_query_data_file(query_id)
    if require_data_file:
        data_file = normalized.get("data_file")
        if not isinstance(data_file, str) or data_file != expected_file:
            raise ValueError(f"{context} data_file must be {expected_file}")
        if Path(data_file).name != data_file:
            raise ValueError(f"{context} has unsafe data_file")

    _parse_timezone_timestamp(
        normalized.get("generated_at"),
        context=context,
        field="generated_at",
    )
    _parse_timezone_timestamp(
        normalized.get("execution_finished_at"),
        context=context,
        field="execution_finished_at",
    )
    if normalized.get("data_updated_at") is not None:
        _parse_timezone_timestamp(
            normalized["data_updated_at"],
            context=context,
            field="data_updated_at",
        )

    status = normalized.get("status")
    if status not in STUDIO_QUERY_STATUSES:
        raise ValueError(f"{context} has unsupported status {status}")
    freshness_status = normalized.get("freshness_status")
    if freshness_status not in STUDIO_QUERY_FRESHNESS_STATUSES:
        raise ValueError(
            f"{context} has unsupported freshness_status {freshness_status}"
        )

    row_count = normalized.get("row_count")
    if type(row_count) is not int or row_count < 0:
        raise ValueError(f"{context} row_count must be a non-negative integer")
    if status == "success" and row_count == 0:
        raise ValueError(f"{context} success status requires at least one row")
    if status in {"empty", "failed"} and row_count != 0:
        raise ValueError(f"{context} {status} status requires row_count 0")

    normalized["columns"] = _validated_columns(
        normalized.get("columns"),
        context=context,
    )
    for field in ("optional_columns", "dimension_columns", "value_columns"):
        if field in normalized:
            normalized[field] = _validated_registry_columns(
                normalized[field],
                context=context,
                field=field,
            )
    declared_contract_columns = set(normalized["columns"]) | set(
        normalized.get("optional_columns") or []
    )
    for field in ("dimension_columns", "value_columns"):
        undeclared = [
            column
            for column in normalized.get(field) or []
            if column not in declared_contract_columns
        ]
        if undeclared:
            raise ValueError(
                f"{context} {field} references undeclared columns: "
                f"{', '.join(undeclared)}"
            )
    source_label = normalized.get("source_label")
    if source_label is not None:
        if not isinstance(source_label, str) or not source_label.strip():
            raise ValueError(f"{context} source_label must be a non-empty string")
        normalized["source_label"] = source_label.strip()
    if "allow_empty" in normalized and not isinstance(
        normalized["allow_empty"],
        bool,
    ):
        raise ValueError(f"{context} allow_empty must be boolean")
    if status == "empty" and normalized.get("allow_empty") is False:
        raise ValueError(f"{context} does not allow an empty result")
    if "freshness_policy" in normalized:
        normalized["freshness_policy"] = _normalize_freshness_policy(
            normalized["freshness_policy"],
            context=context,
        )
    error = normalized.get("error")
    if error is not None and (not isinstance(error, str) or not error.strip()):
        raise ValueError(f"{context} error must be a non-empty string")
    return normalized


def validate_studio_generated_manifest(
    payload: dict,
    *,
    query_contracts: dict[int, dict] | None = None,
    required_query_ids: set[int] | None = None,
) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Studio generated manifest must be a mapping")
    if payload.get("schema_version") != STUDIO_DATA_SCHEMA_VERSION:
        raise ValueError(
            "Studio generated manifest schema_version must be "
            f"{STUDIO_DATA_SCHEMA_VERSION}"
        )
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list):
        raise ValueError("Studio generated manifest needs a queries list")

    generated_at = payload.get("generated_at")
    if raw_queries:
        _parse_timezone_timestamp(
            generated_at,
            context="Studio generated manifest",
            field="generated_at",
        )
    elif generated_at is not None:
        _parse_timezone_timestamp(
            generated_at,
            context="Studio generated manifest",
            field="generated_at",
        )

    normalized_queries = []
    query_ids: list[int] = []
    data_files: list[str] = []
    contracts = query_contracts or {}
    for index, raw_entry in enumerate(raw_queries):
        context = f"Studio generated manifest query {index}"
        entry = _normalize_generated_query_metadata(
            raw_entry,
            context=context,
            require_data_file=True,
        )
        query_id = entry["query_id"]
        query_ids.append(query_id)
        data_files.append(entry["data_file"])

        contract = contracts.get(query_id)
        if query_contracts is not None and contract is None:
            raise ValueError(
                f"Studio generated query {query_id} is not mapped in the metric registry"
            )
        if contract is not None:
            for field in ("query_url", "data_file"):
                if entry[field] != contract[field]:
                    raise ValueError(
                        f"Studio generated query {query_id} {field} does not "
                        "match the metric registry"
                    )
            missing_columns = [
                column
                for column in contract["required_columns"]
                if column not in entry["columns"]
            ]
            if missing_columns:
                raise ValueError(
                    f"Studio generated query {query_id} is missing required "
                    f"columns: {', '.join(missing_columns)}"
                )
            if entry["status"] == "failed" and contract["is_exportable"]:
                raise ValueError(
                    f"Studio generated query {query_id} failed but powers "
                    "exportable metrics"
                )
            if entry["status"] == "empty" and not contract.get(
                "allow_empty",
                True,
            ):
                disallowing_metrics = [
                    metadata["metric_id"]
                    for metadata in contract.get("metric_metadata") or []
                    if not metadata.get("allow_empty", True)
                ]
                detail = (
                    f": {', '.join(disallowing_metrics)}"
                    if disallowing_metrics
                    else ""
                )
                raise ValueError(
                    f"Studio generated query {query_id} is empty but powers "
                    f"metrics that do not allow empty results{detail}"
                )
            if "optional_columns" in entry:
                allowed_optional_columns = set(contract["required_columns"]) | set(
                    contract.get("optional_columns") or []
                )
                unexpected_optional_columns = [
                    column
                    for column in entry["optional_columns"]
                    if column not in allowed_optional_columns
                ]
                if unexpected_optional_columns:
                    raise ValueError(
                        f"Studio generated query {query_id} optional_columns are "
                        "not declared by the metric registry: "
                        f"{', '.join(unexpected_optional_columns)}"
                    )
            for field in ("dimension_columns", "value_columns"):
                if field not in entry:
                    continue
                unexpected_semantic_columns = [
                    column
                    for column in entry[field]
                    if column not in (contract.get(field) or [])
                ]
                if unexpected_semantic_columns:
                    raise ValueError(
                        f"Studio generated query {query_id} {field} are not "
                        "declared by the metric registry: "
                        f"{', '.join(unexpected_semantic_columns)}"
                    )
            if "allow_empty" in entry and entry["allow_empty"] != contract.get(
                "allow_empty"
            ):
                raise ValueError(
                    f"Studio generated query {query_id} allow_empty does not "
                    "match the metric registry"
                )
            if "freshness_policy" in entry:
                contract_policy = contract.get("freshness_policy") or {}
                mismatched_policy_fields = [
                    field
                    for field, value in contract_policy.items()
                    if entry["freshness_policy"].get(field) != value
                ]
                if mismatched_policy_fields:
                    raise ValueError(
                        f"Studio generated query {query_id} freshness_policy "
                        "does not match the metric registry for: "
                        f"{', '.join(mismatched_policy_fields)}"
                    )
            if "source_label" in entry:
                source_labels = contract.get("source_labels") or []
                if entry["source_label"] not in source_labels:
                    raise ValueError(
                        f"Studio generated query {query_id} source_label does "
                        "not match the metric registry"
                    )
            transformation = contract.get("transformation") or {}
            if transformation:
                for entry_field, transformation_field in (
                    ("methodology_id", "methodology_id"),
                    ("methodology_version", "version"),
                    ("script_path", "script_path"),
                    ("tests_path", "tests_path"),
                    ("raw_data_file", "raw_data_file"),
                ):
                    if entry.get(entry_field) != transformation.get(
                        transformation_field
                    ):
                        raise ValueError(
                            f"Studio generated query {query_id} {entry_field} "
                            "does not match its transformation registry"
                        )
                missing_source_columns = [
                    column
                    for column in transformation.get("source_required_columns", [])
                    if column not in (entry.get("raw_columns") or [])
                ]
                if missing_source_columns:
                    raise ValueError(
                        f"Studio generated query {query_id} raw result is missing "
                        f"source columns: {', '.join(missing_source_columns)}"
                    )
            elif entry.get("methodology_id") is not None:
                raise ValueError(
                    f"Studio generated query {query_id} has unregistered transformation metadata"
                )
        normalized_queries.append(entry)

    _require_unique("generated query IDs", query_ids)
    _require_unique("generated query data files", data_files)
    if required_query_ids:
        missing_query_ids = sorted(set(required_query_ids) - set(query_ids))
        if missing_query_ids:
            affected = []
            for query_id in missing_query_ids:
                contract = contracts.get(query_id) or {}
                dashboards = ", ".join(contract.get("dashboard_ids") or [])
                metrics = ", ".join(contract.get("metric_ids") or [])
                context_parts = []
                if dashboards:
                    context_parts.append(f"dashboard {dashboards}")
                if metrics:
                    context_parts.append(f"metric {metrics}")
                context = f" ({'; '.join(context_parts)})" if context_parts else ""
                affected.append(f"{query_id}{context}")
            raise ValueError(
                "Studio generated manifest is missing query IDs: "
                + ", ".join(affected)
                + "; field query_id; expected correction: refresh and publish each "
                "required query result before validating the dashboard"
            )

    normalized = dict(payload)
    normalized["queries"] = normalized_queries
    return normalized


def resolve_studio_generated_data_dir(
    generated_data_dir: Path = STUDIO_GENERATED_DATA_DIR,
) -> Path:
    generated_data_dir = Path(generated_data_dir)
    state_path = generated_data_dir / "state.json"
    if not state_path.exists() and not state_path.is_symlink():
        return generated_data_dir
    if state_path.is_symlink():
        raise ValueError(f"Studio generated state must not be a symlink: {state_path}")
    if not state_path.is_file():
        raise ValueError(f"Studio generated state is not a file: {state_path}")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed Studio generated state: {state_path}") from exc
    if not isinstance(state, dict):
        raise ValueError("Studio generated state must be a mapping")
    if state.get("schema_version") != STUDIO_GENERATED_STATE_SCHEMA_VERSION:
        raise ValueError(
            "Studio generated state schema_version must be "
            f"{STUDIO_GENERATED_STATE_SCHEMA_VERSION}"
        )
    snapshot_id = state.get("current_snapshot_id")
    if not isinstance(snapshot_id, str) or not STUDIO_SNAPSHOT_ID_PATTERN.fullmatch(
        snapshot_id
    ):
        raise ValueError(
            "Studio generated state current_snapshot_id must be a safe snapshot ID"
        )

    snapshots_dir = generated_data_dir / "snapshots"
    snapshot_dir = snapshots_dir / snapshot_id
    if snapshots_dir.is_symlink():
        raise ValueError(
            f"Studio generated snapshots directory must not be a symlink: "
            f"{snapshots_dir}"
        )
    if snapshot_dir.is_symlink():
        raise ValueError(
            f"Studio generated snapshot must not be a symlink: {snapshot_dir}"
        )
    resolved_snapshots_dir = snapshots_dir.resolve()
    resolved_snapshot_dir = snapshot_dir.resolve()
    if resolved_snapshot_dir.parent != resolved_snapshots_dir:
        raise ValueError(
            f"Studio generated snapshot escapes the snapshots directory: {snapshot_id}"
        )
    if not snapshot_dir.is_dir():
        raise ValueError(
            f"Missing active Studio generated snapshot: {snapshot_dir}"
        )
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            f"Missing active Studio generated manifest: {manifest_path}"
        )
    return snapshot_dir


def _load_sanitized_studio_refresh_status(state_path: Path) -> dict:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed Studio generated state: {state_path}") from exc
    if not isinstance(state, dict):
        raise ValueError("Studio generated state must be a mapping")

    sanitized = {}
    for field in (
        "schema_version",
        "current_snapshot_id",
        "previous_snapshot_id",
        "current_manifest_checksum",
        "updated_at",
        "last_checked_at",
        "last_successful_fetch_at",
        "latest_attempt_status",
        "using_previous",
    ):
        if field in state:
            sanitized[field] = state[field]

    previous_snapshot_id = sanitized.get("previous_snapshot_id")
    if previous_snapshot_id is not None and (
        not isinstance(previous_snapshot_id, str)
        or not STUDIO_SNAPSHOT_ID_PATTERN.fullmatch(previous_snapshot_id)
    ):
        raise ValueError(
            "Studio generated state previous_snapshot_id must be a safe snapshot ID"
        )
    for field in (
        "current_manifest_checksum",
        "updated_at",
        "last_checked_at",
        "last_successful_fetch_at",
        "latest_attempt_status",
    ):
        if field in sanitized and sanitized[field] is not None and not isinstance(
            sanitized[field],
            str,
        ):
            raise ValueError(f"Studio generated state {field} must be a string")
    if "using_previous" in sanitized and not isinstance(
        sanitized["using_previous"],
        bool,
    ):
        raise ValueError("Studio generated state using_previous must be boolean")

    latest_failure = state.get("latest_failure")
    if latest_failure is None:
        if "latest_failure" in state:
            sanitized["latest_failure"] = None
    else:
        if not isinstance(latest_failure, dict):
            raise ValueError("Studio generated state latest_failure must be a mapping")
        failure = {}
        failed_query_ids = latest_failure.get("failed_query_ids")
        if failed_query_ids is not None:
            if not isinstance(failed_query_ids, list) or any(
                type(query_id) is not int or query_id <= 0
                for query_id in failed_query_ids
            ):
                raise ValueError(
                    "Studio generated state failed_query_ids must be positive integers"
                )
            failure["failed_query_ids"] = list(failed_query_ids)
        categories = latest_failure.get("categories")
        if categories is not None:
            if not isinstance(categories, list) or any(
                not isinstance(category, str) or not category.strip()
                for category in categories
            ):
                raise ValueError(
                    "Studio generated state failure categories must be strings"
                )
            failure["categories"] = [category.strip() for category in categories]
        summary = latest_failure.get("summary")
        if summary is not None:
            if not isinstance(summary, str) or not summary.strip():
                raise ValueError(
                    "Studio generated state failure summary must be a string"
                )
            failure["summary"] = summary.strip()
        sanitized["latest_failure"] = failure
    return sanitized


def load_studio_generated_manifest(
    path: Path = STUDIO_GENERATED_MANIFEST_PATH,
    *,
    query_contracts: dict[int, dict] | None = None,
    required_query_ids: set[int] | None = None,
) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Missing Studio generated manifest: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed Studio generated manifest: {path}") from exc
    return validate_studio_generated_manifest(
        payload,
        query_contracts=query_contracts,
        required_query_ids=required_query_ids,
    )


def validate_studio_query_result(payload: dict, manifest_entry: dict) -> dict:
    if not isinstance(manifest_entry, dict):
        raise ValueError("Studio generated manifest query must be a mapping")
    entry = _normalize_generated_query_metadata(
        manifest_entry,
        context=f"Studio generated manifest query {manifest_entry.get('query_id')}",
        require_data_file=True,
    )
    query_id = entry["query_id"]
    context = f"Studio query result {query_id}"
    normalized = _normalize_generated_query_metadata(
        payload,
        context=context,
        require_data_file=False,
    )
    for field in (
        "query_id",
        "query_url",
        "generated_at",
        "execution_id",
        "execution_finished_at",
        "status",
        "freshness_status",
        "row_count",
        "columns",
    ):
        if normalized[field] != entry[field]:
            raise ValueError(
                f"{context} {field} does not match the generated manifest"
            )
    for field in (
        "optional_columns",
        "dimension_columns",
        "value_columns",
        "source_label",
        "allow_empty",
        "freshness_policy",
        "source_mode",
        "source_query_id",
        "source_execution_id",
        "source_last_updated",
        "raw_data_file",
        "raw_row_count",
        "raw_columns",
        "raw_checksum",
        "raw_file_checksum",
        "raw_file_size_bytes",
        "methodology_id",
        "methodology_version",
        "script_path",
        "script_checksum",
        "tests_path",
        "transformation_summary",
        "data_quality_warnings",
    ):
        if field in normalized:
            if normalized.get(field) != entry.get(field):
                raise ValueError(
                    f"{context} {field} does not match the generated manifest"
                )
    if normalized.get("error") != entry.get("error"):
        raise ValueError(f"{context} error does not match the generated manifest")

    rows = normalized.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{context} rows must be a list")
    if len(rows) != normalized["row_count"]:
        raise ValueError(
            f"{context} row_count does not match its rows"
        )
    declared_columns = normalized["columns"]
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{context} row {row_index} must be a mapping")
        missing_columns = [
            column for column in declared_columns if column not in row
        ]
        undeclared_columns = [
            column for column in row if column not in declared_columns
        ]
        if missing_columns:
            raise ValueError(
                f"{context} row {row_index} is missing declared columns: "
                f"{', '.join(missing_columns)}"
            )
        if undeclared_columns:
            raise ValueError(
                f"{context} row {row_index} has undeclared columns: "
                f"{', '.join(undeclared_columns)}"
            )
    return normalized


def load_studio_query_result(path: Path, manifest_entry: dict) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Missing Studio query result file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed Studio query result file: {path}") from exc
    return validate_studio_query_result(payload, manifest_entry)


def load_studio_derived_artifact(path: Path, manifest_entry: dict) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Missing Studio derived artifact file: {path}")
    if (
        manifest_entry.get("artifact_id") != KYBERSWAP_INTELLIGENCE_ID
        or manifest_entry.get("id") != KYBERSWAP_INTELLIGENCE_ID
        or manifest_entry.get("data_source") != KYBERSWAP_INTELLIGENCE_ID
        or manifest_entry.get("data_file") != KYBERSWAP_INTELLIGENCE_FILE
    ):
        raise ValueError("Studio derived artifact metadata does not match")
    file_bytes = path.read_bytes()
    try:
        payload = json.loads(file_bytes)
        normalized = validate_kyberswap_depositor_intelligence(payload)
    except (json.JSONDecodeError, KyberSwapDepositorIntelligenceError) as exc:
        raise ValueError(f"Malformed Studio derived artifact file: {path}") from exc
    for field_name in (
        "schema_version",
        "generated_at",
        "row_count",
        "columns",
        "source_query_ids",
        "source_executions",
        "checksum",
    ):
        if normalized.get(field_name) != manifest_entry.get(field_name):
            raise ValueError(
                f"Studio derived artifact {field_name} does not match its manifest"
            )
    if manifest_entry.get("file_size_bytes") != len(file_bytes):
        raise ValueError("Studio derived artifact file size does not match its manifest")
    if manifest_entry.get("file_checksum") != hashlib.sha256(file_bytes).hexdigest():
        raise ValueError("Studio derived artifact checksum does not match its manifest")
    return normalized


def publish_studio_generated_data(
    source_dir: Path,
    output_dir: Path,
    *,
    query_contracts: dict[int, dict] | None = None,
    required_query_ids: set[int] | None = None,
) -> list[Path]:
    source_root = Path(source_dir)
    state_path = source_root / "state.json"
    refresh_status = None
    if state_path.exists() or state_path.is_symlink():
        source_dir = resolve_studio_generated_data_dir(source_root)
        refresh_status = _load_sanitized_studio_refresh_status(state_path)
    else:
        source_dir = source_root
    output_dir = Path(output_dir)
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.is_file():
        return []

    bootstrap_manifest = load_studio_generated_manifest(manifest_path)
    effective_required_query_ids = required_query_ids
    if (
        bootstrap_manifest["queries"]
        and query_contracts is not None
        and effective_required_query_ids is None
    ):
        effective_required_query_ids = set(query_contracts)
    manifest = validate_studio_generated_manifest(
        bootstrap_manifest,
        query_contracts=query_contracts,
        required_query_ids=effective_required_query_ids,
    )
    validated_files: list[tuple[Path, str]] = []
    for entry in manifest["queries"]:
        source_path = source_dir / entry["data_file"]
        load_studio_query_result(source_path, entry)
        validated_files.append((source_path, entry["data_file"]))
    for entry in manifest.get("artifacts") or []:
        if not isinstance(entry, dict):
            raise ValueError("Studio generated manifest artifacts must be mappings")
        source_path = source_dir / str(entry.get("data_file") or "")
        load_studio_derived_artifact(source_path, entry)
        validated_files.append((source_path, str(entry["data_file"])))

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = [output_dir / "manifest.json"]
    shutil.copy2(manifest_path, written[0])
    for source_path, data_file in validated_files:
        target_path = output_dir / data_file
        shutil.copy2(source_path, target_path)
        written.append(target_path)
    if refresh_status is not None:
        refresh_status_path = output_dir / "refresh_status.json"
        refresh_status_path.write_text(
            json.dumps(refresh_status, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(refresh_status_path)
    return written


def validate_studio_registry(
    dashboard_values: list[dict],
    metric_values: list[dict],
    *,
    data_dir: Path = STUDIO_DATA_DIR,
    generated_data_dir: Path = STUDIO_GENERATED_DATA_DIR,
    validate_generated_data: bool = True,
) -> tuple[list[dict], list[dict]]:
    dashboard_values, metric_values = normalize_studio_registry(
        dashboard_values,
        metric_values,
    )
    if not dashboard_values:
        raise ValueError("Studio needs at least one configured dashboard")
    for dashboard in dashboard_values:
        _validate_dashboard(dashboard)
    dashboard_ids = [str(dashboard["id"]) for dashboard in dashboard_values]
    dashboard_slugs = [str(dashboard["slug"]) for dashboard in dashboard_values]
    _require_unique(
        "dashboard ids",
        dashboard_ids,
        field="id",
        correction="assign every dashboard a unique id",
    )
    _require_unique(
        "dashboard slugs",
        dashboard_slugs,
        field="slug",
        correction="assign every dashboard a unique URL slug",
    )
    dashboards_by_id = {str(dashboard["id"]): dashboard for dashboard in dashboard_values}

    if not metric_values:
        raise ValueError("Studio needs at least one configured metric")
    for metric in metric_values:
        _validate_metric(metric, dashboards_by_id)
    metric_ids = [str(metric["id"]) for metric in metric_values]
    _require_unique(
        "metric ids",
        metric_ids,
        field="id",
        correction="assign every metric a unique id",
    )
    _validate_dashboard_section_metric_references(
        dashboard_values,
        metric_values,
    )
    query_contracts = build_studio_query_contracts(metric_values)

    metric_orders: dict[str, list[int]] = {}
    for metric in metric_values:
        metric_orders.setdefault(str(metric["dashboard_id"]), []).append(metric["display_order"])
    for dashboard_id, display_orders in metric_orders.items():
        _require_unique(
            f"metric display orders in {dashboard_id}",
            display_orders,
            field="display_order",
            correction=f"assign unique metric display_order values within dashboard {dashboard_id}",
        )

    data_dir = Path(data_dir)
    active_generated_data_dir: Path | None = None
    generated_dashboard_ids = {
        str(dashboard["id"])
        for dashboard in dashboard_values
        if dashboard["data_mode"] == "generated"
    }
    if validate_generated_data and generated_dashboard_ids:
        active_generated_data_dir = resolve_studio_generated_data_dir(
            generated_data_dir
        )
        required_generated_query_ids = {
            query_id
            for query_id, contract in query_contracts.items()
            if generated_dashboard_ids.intersection(contract["dashboard_ids"])
        }
        manifest = load_studio_generated_manifest(
            active_generated_data_dir / "manifest.json",
            query_contracts=query_contracts,
            required_query_ids=required_generated_query_ids,
        )
        manifest_by_query = {
            entry["query_id"]: entry for entry in manifest["queries"]
        }
        for query_id in sorted(required_generated_query_ids):
            contract = query_contracts[query_id]
            load_studio_query_result(
                active_generated_data_dir / contract["data_file"],
                manifest_by_query[query_id],
            )

    for dashboard in dashboard_values:
        if dashboard["data_mode"] == "generated":
            continue

        data_path = data_dir / str(dashboard["data_file"])
        if not data_path.exists():
            raise ValueError(f"Missing Studio generated data file: {data_path}")
        payload = json.loads(data_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("datasets"), dict):
            raise ValueError(f"Studio data file {data_path} needs a datasets mapping")
        meta = payload.get("meta") or {}
        if meta.get("dashboard_id") != dashboard["id"]:
            raise ValueError(
                f"Studio data file {data_path} dashboard_id does not match {dashboard['id']}"
            )
        if not meta.get("last_refreshed"):
            raise ValueError(f"Studio data file {data_path} needs meta.last_refreshed")
        if meta.get("status") != dashboard["status"]:
            raise ValueError(
                f"Studio data file {data_path} status does not match {dashboard['status']}"
            )
        try:
            refreshed_at = datetime.fromisoformat(
                str(meta["last_refreshed"]).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError(
                f"Studio data file {data_path} has invalid last_refreshed"
            ) from exc
        if refreshed_at.tzinfo is None or refreshed_at.utcoffset() is None:
            raise ValueError(
                f"Studio data file {data_path} last_refreshed must include a timezone"
            )
        datasets = payload["datasets"]
        dashboard_metrics = [
            metric
            for metric in metric_values
            if metric["dashboard_id"] == dashboard["id"]
        ]
        for metric in dashboard_metrics:
            metric_id = str(metric["id"])
            source_name = str(metric["data_source"])
            if source_name not in datasets:
                raise ValueError(
                    f"Studio metric {metric_id} references missing data source {source_name}"
                )
            source = datasets[source_name]
            if isinstance(source, dict) and source.get("error"):
                if metric["is_exportable"]:
                    raise ValueError(
                        f"Studio exportable metric {metric_id} has no row data"
                    )
                continue
            if not isinstance(source, list):
                raise ValueError(
                    f"Studio data source {source_name} for {metric_id} must be rows or an error"
                )
            if not source and not metric["allow_empty"]:
                if metric["is_exportable"]:
                    raise ValueError(
                        f"Studio exportable metric {metric_id} has no row data"
                    )
                raise ValueError(
                    f"Studio metric {metric_id} does not allow empty row data"
                )
            required_source_columns = list(metric["columns"])
            comparison_column = metric.get("comparison_column")
            if comparison_column:
                required_source_columns.append(str(comparison_column))
            for row_index, row in enumerate(source):
                if not isinstance(row, dict):
                    raise ValueError(
                        f"Studio metric {metric_id} source {source_name} row "
                        f"{row_index} must be a mapping"
                    )
                missing_columns = [
                    column for column in required_source_columns if column not in row
                ]
                if missing_columns:
                    raise ValueError(
                        f"Studio metric {metric_id} source {source_name} row {row_index} "
                        f"is missing columns: {', '.join(missing_columns)}"
                    )
            sparkline_source = metric.get("sparkline_data_source")
            if sparkline_source and sparkline_source not in datasets:
                raise ValueError(
                    f"Studio metric {metric_id} references missing sparkline source "
                    f"{sparkline_source}"
                )
            if sparkline_source:
                sparkline_rows = datasets[sparkline_source]
                sparkline_column = metric.get("sparkline_column")
                sparkline_date_column = metric.get("sparkline_date_column")
                required_sparkline_columns = [
                    str(sparkline_column),
                    str(sparkline_date_column),
                ]
                if not isinstance(sparkline_rows, list) or any(
                    not isinstance(row, dict)
                    or any(
                        column not in row
                        for column in required_sparkline_columns
                    )
                    for row in sparkline_rows
                ):
                    missing = ", ".join(required_sparkline_columns)
                    raise ValueError(
                        f"Studio metric {metric_id} sparkline source "
                        f"{sparkline_source} is missing {missing}"
                    )
    return dashboard_values, metric_values


def load_studio_registry(
    studio_dir: Path = DEFAULT_STUDIO_DIR,
    *,
    generated_data_dir: Path = STUDIO_GENERATED_DATA_DIR,
    validate_generated_data: bool = True,
) -> tuple[list[StudioDashboard], list[StudioMetric]]:
    studio_dir = Path(studio_dir)
    dashboard_values = _read_yaml_list(studio_dir / "dashboards.yaml", "dashboards")
    metric_values = _read_yaml_list(studio_dir / "metrics.yaml", "metrics")
    dashboard_values, metric_values = validate_studio_registry(
        dashboard_values,
        metric_values,
        data_dir=studio_dir / "data",
        generated_data_dir=generated_data_dir,
        validate_generated_data=validate_generated_data,
    )
    dashboards = [
        StudioDashboard(value)
        for value in sorted(
            dashboard_values,
            key=lambda item: (int(item["display_order"]), str(item["name"])),
        )
    ]
    metrics = [
        StudioMetric(value)
        for value in sorted(
            metric_values,
            key=lambda item: (
                str(item["dashboard_id"]),
                int(item["display_order"]),
                str(item["name"]),
            ),
        )
    ]
    return dashboards, metrics


def load_studio_data(
    dashboard: StudioDashboard,
    *,
    metrics: list[StudioMetric] | None = None,
    studio_dir: Path = DEFAULT_STUDIO_DIR,
    generated_data_dir: Path = STUDIO_GENERATED_DATA_DIR,
) -> dict:
    dashboard_metrics = list(metrics or [])
    if dashboard.data.get("data_mode") != "generated":
        payload = json.loads(
            (Path(studio_dir) / "data" / dashboard.data_file).read_text(
                encoding="utf-8"
            )
        )
        if not dashboard_metrics:
            return payload
        contracts = build_studio_query_contracts(
            [metric.data for metric in dashboard_metrics]
        )
        meta = payload.get("meta") or {}
        generated_at = meta.get("last_refreshed")
        freshness_status = meta.get("freshness_status") or "current"
        sources = {}
        for contract in contracts.values():
            source = (payload.get("datasets") or {}).get(contract["data_source"])
            if isinstance(source, list):
                status = "empty" if not source else "success"
                row_count = len(source)
                error = None
            else:
                status = "failed"
                row_count = 0
                error = (
                    source.get("error")
                    if isinstance(source, dict)
                    else "Demo data source unavailable."
                )
            descriptor = {
                "schema_version": STUDIO_DATA_SCHEMA_VERSION,
                "query_id": contract["query_id"],
                "query_url": contract["query_url"],
                "data_file": contract["data_file"],
                "generated_at": generated_at,
                "execution_finished_at": generated_at,
                "status": status,
                "freshness_status": freshness_status,
                "row_count": row_count,
                "columns": list(contract["required_columns"]),
                "optional_columns": list(contract["optional_columns"]),
                "dimension_columns": list(contract["dimension_columns"]),
                "value_columns": list(contract["value_columns"]),
                "allow_empty": contract["allow_empty"],
                "freshness_policy": dict(contract["freshness_policy"]),
            }
            if contract.get("source_label"):
                descriptor["source_label"] = contract["source_label"]
            if error:
                descriptor["error"] = str(error)
            sources[contract["data_source"]] = descriptor
        normalized = dict(payload)
        normalized["sources"] = sources
        return normalized

    if not dashboard_metrics:
        raise ValueError(
            f"Generated Studio dashboard {dashboard.id} needs configured metrics"
        )
    contracts = build_studio_query_contracts(
        [metric.data for metric in dashboard_metrics]
    )
    active_generated_data_dir = resolve_studio_generated_data_dir(
        generated_data_dir
    )
    global_manifest = load_studio_generated_manifest(
        active_generated_data_dir / "manifest.json"
    )
    manifest = validate_studio_generated_manifest(
        {
            **global_manifest,
            "queries": [
                entry
                for entry in global_manifest["queries"]
                if entry["query_id"] in contracts
            ],
        },
        query_contracts=contracts,
        required_query_ids=set(contracts),
    )
    manifest_by_query = {
        entry["query_id"]: entry for entry in manifest["queries"]
    }
    datasets = {}
    sources = {}
    for query_id, contract in contracts.items():
        entry = manifest_by_query[query_id]
        result = load_studio_query_result(
            active_generated_data_dir / contract["data_file"],
            entry,
        )
        source_name = contract["data_source"]
        sources[source_name] = dict(entry)
        if entry["status"] == "failed":
            datasets[source_name] = {
                "error": entry.get("error") or f"Dune query {query_id} failed.",
                "hint": "The previous successful snapshot was not replaced.",
                "state": "query_failed",
                "query_id": query_id,
            }
        else:
            datasets[source_name] = result["rows"]
    requested_derived_sources = sorted(
        {
            str(metric.data["derived_data_source"])
            for metric in dashboard_metrics
            if metric.data.get("derived_data_source")
        }
    )
    artifact_entries = {
        str(entry.get("data_source")): entry
        for entry in manifest.get("artifacts", [])
        if isinstance(entry, dict) and isinstance(entry.get("data_source"), str)
    }
    for source_name in requested_derived_sources:
        entry = artifact_entries.get(source_name)
        if entry is None:
            raise ValueError(
                f"Generated Studio dashboard {dashboard.id} is missing derived source "
                f"{source_name}"
            )
        payload = load_studio_derived_artifact(
            active_generated_data_dir / str(entry["data_file"]),
            entry,
        )
        datasets[source_name] = payload
        sources[source_name] = dict(entry)
    source_freshness_statuses = {
        source["freshness_status"]
        for source in sources.values()
        if source.get("freshness_status")
    }
    freshness_status = (
        "stale"
        if "stale" in source_freshness_statuses
        else "delayed"
        if "delayed" in source_freshness_statuses
        else "current"
    )
    source_update_candidates = []
    for source in sources.values():
        if source.get("query_id") is None:
            continue
        timestamp_field = (
            "data_updated_at"
            if source.get("data_updated_at")
            else "execution_finished_at"
        )
        timestamp = source.get(timestamp_field)
        if timestamp:
            source_update_candidates.append(
                (
                    _parse_timezone_timestamp(
                        timestamp,
                        context=(
                            f"Studio dashboard {dashboard.id} query "
                            f"{source['query_id']}"
                        ),
                        field=timestamp_field,
                    ),
                    timestamp,
                )
            )
    source_updated_at = (
        min(source_update_candidates, key=lambda candidate: candidate[0])[1]
        if source_update_candidates
        else manifest["generated_at"]
    )
    data_updated_at = source_updated_at
    display_updated_at = source_updated_at
    is_fixture_snapshot = manifest.get("mode") == "fixture"
    return {
        "meta": {
            "dashboard_id": dashboard.id,
            "status": dashboard.data["status"],
            "last_refreshed": display_updated_at,
            "generated_at": manifest["generated_at"],
            "data_updated_at": data_updated_at,
            "display_updated_at": display_updated_at,
            "last_checked_at": manifest.get("last_checked_at")
            or manifest["generated_at"],
            "last_successful_fetch_at": manifest.get("last_successful_fetch_at")
            or manifest["generated_at"],
            "freshness_status": freshness_status,
            "sample_data": is_fixture_snapshot,
            "mode": manifest.get("mode") or "generated",
            "source": manifest.get("source") or "generated_query_manifest",
            "generator": (
                "Studio fixture query manifest"
                if is_fixture_snapshot
                else "Studio generated query manifest"
            ),
        },
        "datasets": datasets,
        "sources": sources,
    }


def metrics_for_dashboard(
    dashboard: StudioDashboard,
    metrics: list[StudioMetric],
) -> list[StudioMetric]:
    return [metric for metric in metrics if metric.dashboard_id == dashboard.id]


def _json_script(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace(
        "</",
        "<\\/",
    )


def _dashboard_select(
    dashboards: list[StudioDashboard],
    *,
    active_dashboard: StudioDashboard | None,
    landing: bool,
) -> str:
    options = []
    if landing:
        options.append('<option value="" selected>Choose a dashboard</option>')
    for dashboard in dashboards:
        selected = (
            " selected"
            if active_dashboard is not None and dashboard.id == active_dashboard.id
            else ""
        )
        href = (
            f"{escape(dashboard.slug)}/"
            if landing
            else f"../{escape(dashboard.slug)}/"
        )
        options.append(
            f'<option value="{href}" data-dashboard-id="{escape(dashboard.id)}"{selected}>'
            f"{escape(dashboard.name)}</option>"
        )
    return (
        '<label class="studio-dashboard-select">'
        '<span>Dashboard</span>'
        '<select data-studio-dashboard-select aria-label="Choose a Studio dashboard">'
        f'{"".join(options)}'
        "</select>"
        "</label>"
    )


def render_studio_landing(
    dashboards: list[StudioDashboard],
    metrics: list[StudioMetric],
    *,
    landing_js_version: str,
) -> str:
    dashboard_cards = []
    for dashboard in dashboards:
        dashboard_metrics = metrics_for_dashboard(dashboard, metrics)
        dashboard_cards.append(
            '<article class="studio-directory-card">'
            '<div class="studio-directory-card-topline">'
            f'<span class="studio-status-badge">{escape(str(dashboard.data["status"]))} data</span>'
            f'<span>{len(dashboard_metrics)} metrics</span>'
            "</div>"
            f"<h2>{escape(dashboard.name)}</h2>"
            f"<p>{escape(str(dashboard.data['description']))}</p>"
            f'<a class="studio-card-link" href="{escape(dashboard.slug)}/">'
            f"Open {escape(str(dashboard.data.get('short_name') or dashboard.name))}"
            '<span aria-hidden="true">↗</span></a>'
            "</article>"
        )

    selector = _dashboard_select(
        dashboards,
        active_dashboard=None,
        landing=True,
    )
    return (
        '<section class="studio-landing" data-studio-landing>'
        '<header class="studio-landing-toolbar">'
        '<div class="studio-toolbar-leading">'
        '<a class="studio-back-link" href="../index.html">Back to Data Catalog</a>'
        '<a class="studio-wordmark" href="./"><span>Studio</span>'
        '<small>Analytics workspace</small></a>'
        "</div>"
        '<div class="studio-toolbar-trailing" data-studio-theme-slot></div>'
        "</header>"
        '<div class="studio-landing-glow" aria-hidden="true"></div>'
        '<div class="wrap studio-landing-shell">'
        '<header class="studio-landing-hero">'
        '<div class="studio-landing-copy">'
        '<p class="studio-kicker">ether.fi Studio</p>'
        '<h1>Analytics shaped for decisions.</h1>'
        "<p>Studio is an independent workspace for reusable, partner-ready "
        "analytics dashboards. It is intentionally separate from the catalog, "
        "MCP, and existing dashboard registry.</p>"
        '<div class="studio-landing-actions">'
        f"{selector}"
        "</div>"
        "</div>"
        '<aside class="studio-landing-note" aria-label="Studio data status">'
        '<span class="studio-note-index">01</span>'
        '<p class="studio-note-label">Current phase</p>'
        "<strong>Validated static snapshots</strong>"
        "<p>Validated campaign data from reviewed read-only query snapshots.</p>"
        "</aside>"
        "</header>"
        '<section class="studio-directory" aria-labelledby="studio-directory-title">'
        '<div class="studio-section-heading">'
        "<div><p>Configured dashboards</p>"
        '<h2 id="studio-directory-title">Choose a workspace</h2></div>'
        f"<span>{len(dashboards):02d} available</span>"
        "</div>"
        f'<div class="studio-directory-grid">{"".join(dashboard_cards)}</div>'
        "</section>"
        '<section class="studio-pipeline" aria-labelledby="studio-pipeline-title">'
        '<div class="studio-section-heading"><div><p>Refresh architecture</p>'
        '<h2 id="studio-pipeline-title">One stable path from query to review</h2>'
        "</div></div>"
        '<ol class="studio-pipeline-list">'
        '<li><span>01</span><strong>Dune queries</strong><p>One result may power several configured metrics.</p></li>'
        '<li><span>02</span><strong>Generated JSON</strong><p>An Action replaces data files and refresh metadata.</p></li>'
        '<li><span>03</span><strong>Studio build</strong><p>Shared components render every configured dashboard.</p></li>'
        '<li><span>04</span><strong>Review &amp; export</strong><p>Users filter, inspect, and download the same rows.</p></li>'
        "</ol>"
        "</section>"
        "</div>"
        f'<script src="../assets/studio-landing.js?v={escape(landing_js_version)}" defer></script>'
        "</section>"
    )


def _control_group(
    dashboard: StudioDashboard,
    dashboard_metrics: list[StudioMetric],
    *,
    control_type: str,
) -> str:
    is_visibility = control_type == "visibility"
    parts = []
    for section in dashboard.data["sections"]:
        section_metrics = [
            metric
            for metric in dashboard_metrics
            if metric.section == section["id"]
            and (is_visibility or metric.data["is_exportable"])
        ]
        if not section_metrics:
            continue
        checked_count = sum(
            metric.data["default_visible"] if is_visibility else True
            for metric in section_metrics
        )
        metric_rows = []
        for metric in section_metrics:
            checked = (
                " checked"
                if (metric.data["default_visible"] if is_visibility else True)
                else ""
            )
            data_attribute = (
                f'data-visibility-metric="{escape(metric.id)}"'
                if is_visibility
                else f'data-export-metric="{escape(metric.id)}"'
            )
            metric_rows.append(
                '<label class="studio-check-row">'
                f'<input type="checkbox" {data_attribute}{checked}>'
                '<span class="studio-custom-check" aria-hidden="true"></span>'
                f"<span>{escape(str(metric.data['name']))}</span>"
                "</label>"
            )
        group_attribute = (
            f'data-visibility-group="{escape(str(section["id"]))}"'
            if is_visibility
            else f'data-export-group="{escape(str(section["id"]))}"'
        )
        section_id = str(section["id"])
        list_id = f"studio-visibility-list-{section_id}"
        is_expanded = len(parts) == 0
        disclosure = (
            '<button class="studio-visibility-disclosure" type="button" '
            f'data-visibility-disclosure="{escape(section_id)}" '
            f'aria-controls="{escape(list_id)}" '
            f'aria-expanded="{str(is_expanded).lower()}" '
            f'aria-label="{("Collapse" if is_expanded else "Expand")} '
            f'{escape(str(section["label"]))} metrics">'
            '<span aria-hidden="true">⌄</span></button>'
            if is_visibility
            else ""
        )
        list_attributes = (
            f' id="{escape(list_id)}" '
            f'data-visibility-list="{escape(section_id)}"'
            f'{"" if is_expanded else " hidden"}'
            if is_visibility
            else ""
        )
        parts.append(
            '<fieldset class="studio-control-group">'
            '<legend>'
            f'<label><input type="checkbox" {group_attribute}'
            f' data-group-size="{len(section_metrics)}" checked>'
            '<span class="studio-custom-check" aria-hidden="true"></span>'
            f"<strong>{escape(str(section['label']))}</strong></label>"
            f"<small>{checked_count}/{len(section_metrics)}</small>"
            f"{disclosure}"
            "</legend>"
            f'<div class="studio-check-list"{list_attributes}>{"".join(metric_rows)}</div>'
            "</fieldset>"
        )
    return "".join(parts)


def _render_metric_card(metric: StudioMetric, *, source_status: str) -> str:
    data = metric.data
    visualization_type = metric.visualization_type
    source_label = str(
        data.get("source_label")
        or {
            "counter": "View calculation",
            "line": "View methodology",
            "bar": "View methodology",
            "sankey": "View methodology",
            "table": "Inspect records",
        }[visualization_type]
    )
    query_id = int(data["query_id"])
    growth_config = data.get("growth_chart")
    is_intelligence = bool(data.get("intelligence_component"))
    source_aria = (
        f"{source_label} for {data['name']}"
        if growth_config or is_intelligence
        else f"{source_label} for {data['name']} in Dune query {query_id}"
    )
    if data.get("methodology"):
        methodology_title = (
            "Metric methodology" if growth_config else "Attribution methodology"
        )
        source_control = (
            '<button class="studio-source-link studio-methodology-trigger" '
            'type="button" '
            f'data-methodology-open="{escape(metric.id)}" '
            'aria-haspopup="dialog" '
            'aria-controls="studio-methodology-dialog" '
            f'data-query-id="{query_id}" title="{methodology_title}" '
            f'aria-label="{escape(source_aria)}">'
            f"{escape(source_label)}</button>"
        )
    else:
        source_control = (
            f'<a class="studio-source-link" href="{escape(str(data["query_url"]))}" '
            'target="_blank" rel="noopener noreferrer" '
            f'data-query-id="{query_id}" title="'
            f'{"Open source on Dune" if is_intelligence else f"Dune query {query_id}"}" '
            f'aria-label="{escape(source_aria)}">'
            f'{escape(source_label)} <span aria-hidden="true">↗</span></a>'
        )
    export_button = (
        f'<button class="studio-metric-export" type="button" '
        f'data-metric-export="{escape(metric.id)}">CSV</button>'
        if data["is_exportable"]
        else ""
    )
    top_n = ""
    if visualization_type == "bar" and data.get("top_n_options"):
        options = "".join(
            f'<option value="{int(value)}"'
            f'{" selected" if int(value) == int(data.get("default_top_n", value)) else ""}>'
            f"Top {int(value)}</option>"
            for value in data["top_n_options"]
        )
        top_n = (
            '<label class="studio-top-n-control">'
            '<span class="visually-hidden">Ranking depth</span>'
            f'<select data-top-n-for="{escape(metric.id)}">{options}</select>'
            "</label>"
        )
    chart_style_switcher = ""
    if visualization_type == "line":
        default_visualization = str(data["default_visualization"])
        style_labels = {
            "column": "Bar",
        } if growth_config else {}
        style_buttons = "".join(
            f'<button type="button" data-chart-style="{escape(str(style))}" '
            f'data-chart-style-for="{escape(metric.id)}" '
            f'aria-pressed="{str(style == default_visualization).lower()}" '
            f'{"class=\"active\" " if style == default_visualization else ""}'
            f'title="Show as {escape(str(style_labels.get(style) or style))} chart">'
            f"{escape(str(style_labels.get(style) or str(style).title()))}</button>"
            for style in data["allowed_visualizations"]
        )
        if len(data["allowed_visualizations"]) > 1 or not growth_config:
            chart_style_switcher = (
                '<div class="studio-chart-style-switcher" role="group" '
                f'aria-label="Chart style for {escape(str(data["name"]))}">'
                f"{style_buttons}</div>"
            )
    growth_controls = ""
    if isinstance(growth_config, dict):
        default_granularity = growth_config.get("default_granularity")
        granularity_control = ""
        if default_granularity:
            granularity_buttons = "".join(
                f'<button type="button" data-growth-granularity="{escape(str(granularity))}" '
                f'data-growth-granularity-for="{escape(metric.id)}" '
                f'aria-pressed="{str(granularity == default_granularity).lower()}" '
                f'{"class=\"is-active\" " if granularity == default_granularity else ""}>'
                f"{escape(str(granularity).title())}</button>"
                for granularity in growth_config["available_granularities"]
            )
            granularity_control = (
                '<div class="studio-growth-granularity" role="group" '
                f'aria-label="Time granularity for {escape(str(data["name"]))}">'
                f"{granularity_buttons}</div>"
            )
        views = growth_config["views"]
        default_view = str(growth_config["default_view"])
        view_control = ""
        if len(views) > 1:
            view_control_name = (
                "Metric type"
                if {str(view["id"]) for view in views} == {"deposits", "depositors"}
                else "Data grouping"
            )
            view_buttons = "".join(
                f'<button type="button" data-growth-view="{escape(str(view["id"]))}" '
                f'data-growth-view-for="{escape(metric.id)}" '
                f'aria-pressed="{str(str(view["id"]) == default_view).lower()}" '
                f'{"class=\"is-active\" " if str(view["id"]) == default_view else ""}>'
                f'{escape(str(view["label"]))}</button>'
                for view in views
            )
            view_control = (
                '<div class="studio-growth-view" role="group" '
                f'aria-label="{view_control_name} for {escape(str(data["name"]))}">'
                f"{view_buttons}</div>"
            )
        growth_controls = (
            '<div class="studio-growth-data-controls" '
            f'data-growth-controls="{escape(metric.id)}">'
            f'<div class="studio-growth-control-row">{granularity_control}{view_control}</div>'
            "</div>"
        )
    visible = bool(data["default_visible"])
    hidden = "" if visible else " hidden"
    compact_counter = bool(
        visualization_type == "counter" and data.get("compact_counter")
    )
    compact_class = " studio-counter-compact" if compact_counter else ""
    growth_class = " studio-growth-card" if isinstance(growth_config, dict) else ""
    actions = (
        ""
        if compact_counter
        else (
            '<div class="studio-metric-actions">'
            f"{chart_style_switcher}{top_n}{export_button}{source_control}"
            "</div>"
        )
    )
    if isinstance(growth_config, dict):
        card_header = (
            '<header class="studio-metric-header studio-growth-metric-header">'
            '<div class="studio-growth-heading">'
            f'<h3>{escape(str(data["name"]))}</h3>'
            f'<p class="studio-metric-description">{escape(str(data["description"]))}</p>'
            "</div>"
            '<div class="studio-growth-header-controls">'
            f"{growth_controls}{actions}"
            "</div>"
            "</header>"
        )
    else:
        card_header = (
            '<header class="studio-metric-header">'
            "<div>"
            f'<h3>{escape(str(data["name"]))}</h3>'
            f'<p class="studio-metric-description">{escape(str(data["description"]))}</p>'
            "</div>"
            f"{actions}"
            "</header>"
        )
    return (
        f'<article class="studio-metric-card studio-metric-{escape(visualization_type)} '
        f'studio-size-{escape(str(data.get("size") or "medium"))}{compact_class}{growth_class}" '
        f'data-studio-metric-id="{escape(metric.id)}" '
        f'data-studio-metric-type="{escape(visualization_type)}" '
        f'data-studio-visible="{str(visible).lower()}"{hidden}>'
        f"{card_header}"
        f'<div class="studio-metric-body" data-metric-render="{escape(metric.id)}" '
        'role="region" '
        f'aria-label="{escape(str(data["name"]))} visualization">'
        '<div class="studio-loading-state"><span></span><span></span><span></span>'
        "<p>Preparing metric…</p></div>"
        "</div>"
        "</article>"
    )


def _render_section_utility(
    section: dict,
    metrics_by_id: dict[str, StudioMetric],
) -> str:
    controls = []
    methodology_metric_id = section.get("shared_methodology_metric_id")
    if methodology_metric_id:
        metric = metrics_by_id[str(methodology_metric_id)]
        methodology = metric.data.get("methodology") or {}
        methodology_name = str(
            methodology.get("title")
            or metric.data.get("export_name")
            or metric.data["name"]
        )
        controls.append(
            '<button class="studio-source-link studio-methodology-trigger" '
            'type="button" '
            f'data-methodology-open="{escape(metric.id)}" '
            'aria-haspopup="dialog" '
            'aria-controls="studio-methodology-dialog" '
            f'aria-label="Inspect methodology for {escape(methodology_name)}">'
            "Inspect Methodology</button>"
        )
    export_metric_id = section.get("shared_export_metric_id")
    if export_metric_id:
        metric = metrics_by_id[str(export_metric_id)]
        controls.append(
            '<button class="studio-metric-export studio-section-export" '
            'type="button" '
            f'data-metric-export="{escape(metric.id)}" '
            f'aria-label="Export {escape(str(metric.data.get("export_name") or metric.data["name"]))} as CSV">'
            "CSV</button>"
        )
    if not controls:
        return ""
    return (
        '<div class="studio-section-utility" '
        f'data-studio-section-utility="{escape(str(section["id"]))}">'
        f'{"".join(controls)}</div>'
    )


def _render_dashboard_sections(
    dashboard: StudioDashboard,
    dashboard_metrics: list[StudioMetric],
    *,
    source_status: str,
) -> str:
    sections = []
    metrics_by_id = {metric.id: metric for metric in dashboard_metrics}
    for section in dashboard.data["sections"]:
        section_metrics = [
            metric
            for metric in dashboard_metrics
            if metric.section == section["id"]
        ]
        if not section_metrics:
            continue
        cards = "".join(
            _render_metric_card(metric, source_status=source_status)
            for metric in section_metrics
        )
        section_id = str(section["id"])
        heading_id = f"studio-section-{section_id}"
        show_heading = section.get("show_heading", True)
        if show_heading:
            if section.get("show_description", True):
                heading_content = (
                    f'<p>{escape(str(section["label"]))}</p>'
                    f'<h2 id="{escape(heading_id)}">'
                    f'{escape(str(section["description"]))}</h2>'
                )
                heading_class = "studio-dashboard-section-heading"
            else:
                heading_content = (
                    f'<h2 id="{escape(heading_id)}">'
                    f'{escape(str(section["label"]))}</h2>'
                )
                heading_class = (
                    "studio-dashboard-section-heading "
                    "studio-dashboard-section-heading-title-only"
                )
            heading = (
                f'<header class="{heading_class}">'
                f"<div>{heading_content}</div>"
                f"<span>{len(section_metrics):02d}</span>"
                "</header>"
            )
        else:
            heading = (
                f'<h2 class="visually-hidden" id="{escape(heading_id)}">'
                f'{escape(str(section["label"]))}</h2>'
            )
        utility = _render_section_utility(section, metrics_by_id)
        grid_columns = section.get("grid_columns")
        grid_class = (
            f" studio-metric-grid-columns-{int(grid_columns)}"
            if grid_columns is not None
            else ""
        )
        grid_attribute = (
            f' data-grid-columns="{int(grid_columns)}"'
            if grid_columns is not None
            else ""
        )
        initially_hidden = not any(
            bool(metric.data["default_visible"]) for metric in section_metrics
        )
        sections.append(
            f'<section class="studio-dashboard-section studio-section-{escape(section_id)}'
            '" '
            f'id="studio-dashboard-section-{escape(section_id)}" '
            f'data-studio-section="{escape(section_id)}" '
            f'aria-labelledby="{escape(heading_id)}"'
            f'{" hidden" if initially_hidden else ""}>'
            f"{heading}{utility}"
            f'<div class="studio-metric-grid{grid_class}"{grid_attribute}>{cards}</div>'
            "</section>"
        )
    return "".join(sections)


def _studio_data_source_descriptors(
    dashboard: StudioDashboard,
    dashboard_metrics: list[StudioMetric],
    data_payload: dict,
) -> dict[str, dict]:
    data_mode = str(dashboard.data.get("data_mode") or "demo")
    contracts = build_studio_query_contracts(
        [metric.data for metric in dashboard_metrics]
    )
    source_metadata = data_payload.get("sources") or {}
    descriptors = {}
    for contract in contracts.values():
        source_name = contract["data_source"]
        metadata = source_metadata.get(source_name) or {}
        if data_mode == "generated":
            source_url = (
                "../../data/studio/generated/"
                f"{contract['data_file']}"
            )
            dataset = None
        else:
            source_url = f"../data/{dashboard.data_file}"
            dataset = source_name
        descriptor = {
            "mode": data_mode,
            "kind": (
                "generated_query"
                if data_mode == "generated"
                else "demo_bundle"
            ),
            "dataSource": source_name,
            "queryId": contract["query_id"],
            "queryUrl": contract["query_url"],
            "dataFile": contract["data_file"],
            "url": source_url,
            "requiredColumns": list(contract["required_columns"]),
            "expectedColumns": list(contract["required_columns"]),
        }
        if dashboard.data.get("stale_after_hours") is not None:
            descriptor["staleAfterHours"] = dashboard.data["stale_after_hours"]
        if dataset is not None:
            descriptor["dataset"] = dataset
        for source_field, config_field in (
            ("generated_at", "generatedAt"),
            ("execution_finished_at", "executionFinishedAt"),
            ("execution_id", "executionId"),
            ("source_execution_id", "sourceExecutionId"),
            ("source_last_updated", "sourceLastUpdated"),
            ("methodology_id", "methodologyId"),
            ("methodology_version", "methodologyVersion"),
            ("script_path", "scriptPath"),
            ("tests_path", "testsPath"),
            ("transformation_summary", "transformationSummary"),
            ("data_quality_warnings", "dataQualityWarnings"),
            ("status", "status"),
            ("freshness_status", "freshnessStatus"),
            ("row_count", "rowCount"),
        ):
            if metadata.get(source_field) is not None:
                descriptor[config_field] = metadata[source_field]
        descriptors[source_name] = descriptor
    if data_mode == "generated":
        derived_source_names = sorted(
            {
                str(metric.data["derived_data_source"])
                for metric in dashboard_metrics
                if metric.data.get("derived_data_source")
            }
        )
        for source_name in derived_source_names:
            metadata = source_metadata.get(source_name) or {}
            source_metrics = [
                metric
                for metric in dashboard_metrics
                if str(metric.data.get("derived_data_source") or "")
                == source_name
            ]
            data_file = str(
                metadata.get("data_file")
                or (
                    KYBERSWAP_INTELLIGENCE_FILE
                    if source_name == KYBERSWAP_INTELLIGENCE_ID
                    else ""
                )
            )
            if not data_file:
                raise ValueError(
                    f"Studio derived source {source_name} has no generated data file"
                )
            columns = list(metadata.get("columns") or [])
            descriptor = {
                "mode": data_mode,
                "kind": "generated_derived",
                "artifactId": str(metadata.get("artifact_id") or source_name),
                "dataSource": source_name,
                "dataFile": data_file,
                "url": f"../../data/studio/generated/{data_file}",
                "requiredColumns": columns,
                "expectedColumns": columns,
            }
            source_query_ids = metadata.get("source_query_ids") or sorted(
                {
                    int(metric.data["query_id"])
                    for metric in source_metrics
                }
            )
            descriptor["sourceQueryIds"] = list(source_query_ids)
            if dashboard.data.get("stale_after_hours") is not None:
                descriptor["staleAfterHours"] = dashboard.data[
                    "stale_after_hours"
                ]
            for source_field, config_field in (
                ("generated_at", "generatedAt"),
                ("source_executions", "sourceExecutions"),
                ("methodology_id", "methodologyId"),
                ("methodology_version", "methodologyVersion"),
                ("script_path", "scriptPath"),
                ("tests_path", "testsPath"),
                ("transformation_summary", "transformationSummary"),
                ("data_quality_warnings", "dataQualityWarnings"),
                ("row_count", "rowCount"),
            ):
                if metadata.get(source_field) is not None:
                    descriptor[config_field] = metadata[source_field]
            descriptors[source_name] = descriptor
    return descriptors


def render_studio_dashboard(
    dashboard: StudioDashboard,
    dashboards: list[StudioDashboard],
    metrics: list[StudioMetric],
    data_payload: dict,
    *,
    studio_js_version: str,
    echarts_js_version: str,
) -> str:
    dashboard_metrics = metrics_for_dashboard(dashboard, metrics)
    available_section_ids = {
        metric.section for metric in dashboard_metrics
    }
    default_visible_section_ids = {
        metric.section
        for metric in dashboard_metrics
        if bool(metric.data["default_visible"])
    }
    section_navigation = "".join(
        '<a class="studio-section-nav-link" '
        f'href="#studio-dashboard-section-{escape(str(section["id"]))}" '
        f'data-section-nav-target="{escape(str(section["id"]))}"'
        f'{"" if section["id"] in default_visible_section_ids else " hidden"}>'
        f'{escape(str(section["label"]))}</a>'
        for section in dashboard.data["sections"]
        if section["id"] in available_section_ids
    )
    meta = data_payload["meta"]
    source_status = str(meta["status"])
    refreshed_at = str(meta["last_refreshed"])
    try:
        refreshed_datetime = datetime.fromisoformat(
            refreshed_at.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        refreshed_display = refreshed_datetime.strftime("%d %b %Y · %H:%M UTC")
    except ValueError:
        refreshed_display = refreshed_at
    selector = _dashboard_select(
        dashboards,
        active_dashboard=dashboard,
        landing=False,
    )
    range_buttons = "".join(
        f'<button type="button" data-studio-range="{value}" '
        f'aria-pressed="{str(value == dashboard.data["default_date_range"]).lower()}"'
        f'{" class=\"active\"" if value == dashboard.data["default_date_range"] else ""}>'
        f"{value}</button>"
        for value in STUDIO_RANGE_OPTIONS
    )
    config_payload = {
        "dashboard": dashboard.data,
        "dashboards": [
            {
                "id": candidate.id,
                "slug": candidate.slug,
                "name": candidate.name,
                "href": f"../{candidate.slug}/",
            }
            for candidate in dashboards
        ],
        "metrics": [metric.data for metric in dashboard_metrics],
        "dataUrl": (
            f"../data/{dashboard.data_file}"
            if dashboard.data.get("data_mode") != "generated"
            else None
        ),
        "dataMode": str(dashboard.data.get("data_mode") or "demo"),
        "dataSources": _studio_data_source_descriptors(
            dashboard,
            dashboard_metrics,
            data_payload,
        ),
        "manifestUrl": (
            "../../data/studio/generated/manifest.json"
            if dashboard.data.get("data_mode") == "generated"
            else None
        ),
        "repositoryBlobBase": (
            "https://github.com/henrystats/etherfi-data-catalog/blob/main"
        ),
    }
    dune_link = (
        '<a class="studio-dune-link" '
        f'href="{escape(str(dashboard.data["dune_url"]))}" '
        'target="_blank" rel="noopener noreferrer">View on Dune '
        '<span aria-hidden="true">↗</span></a>'
        if dashboard.data.get("dune_url")
        else ""
    )
    hero = (
        ""
        if dashboard.data.get("show_hero") is False
        else (
            '<section class="studio-dashboard-hero">'
            f"<h1>{escape(dashboard.name)}</h1>"
            f'<p class="studio-dashboard-description">'
            f"{escape(str(dashboard.data['description']))}</p>"
            "</section>"
        )
    )
    toolbar_heading = (
        f'<h1 class="visually-hidden">{escape(dashboard.name)}</h1>'
        if dashboard.data.get("show_hero") is False
        else ""
    )
    return (
        f'<section class="studio-dashboard" data-studio-dashboard="{escape(dashboard.id)}">'
        '<header class="studio-dashboard-toolbar">'
        f"{toolbar_heading}"
        '<div class="studio-toolbar-leading">'
        '<a class="studio-back-link" href="../../index.html">Back to Data Catalog</a>'
        '<a class="studio-wordmark" href="../"><span>Studio</span>'
        '<small>Analytics workspace</small></a>'
        "</div>"
        f"{selector}"
        '<div class="studio-toolbar-trailing">'
        f"{dune_link}"
        '<span class="studio-last-updated">Last Updated: '
        f'<time data-studio-last-updated="{escape(refreshed_at)}" '
        f'datetime="{escape(refreshed_at)}">{escape(refreshed_display)}</time>'
        "</span>"
        '<div data-studio-theme-slot></div>'
        "</div>"
        "</header>"
        f"{hero}"
        '<div class="studio-timebar" role="group" aria-label="Dashboard date range">'
        '<div><span>View</span>'
        f'<div class="studio-range-group">{range_buttons}</div></div>'
        '<p data-range-summary>Showing the configured date range</p>'
        "</div>"
        '<div class="studio-workspace" data-studio-workspace '
        'data-left-collapsed="true" data-right-collapsed="true">'
        '<aside class="studio-side-panel studio-side-left is-collapsed" '
        'data-studio-panel="left" aria-labelledby="studio-navigation-panel-title">'
        '<header><div><p>Navigate</p>'
        '<h2 id="studio-navigation-panel-title">Dashboard sections</h2></div>'
        '<button type="button" data-panel-toggle="left" aria-expanded="false" '
        'aria-label="Expand dashboard navigation panel"><span aria-hidden="true">→</span>'
        "</button></header>"
        '<div class="studio-panel-content">'
        '<section class="studio-panel-section studio-panel-navigation" '
        'aria-labelledby="studio-navigate-title">'
        '<h3 id="studio-navigate-title">Navigate</h3>'
        '<nav class="studio-section-navigation" data-studio-section-nav '
        'aria-label="Dashboard sections">'
        f"{section_navigation}</nav></section></div>"
        '<span class="studio-panel-collapsed-label" aria-hidden="true">Navigation</span>'
        "</aside>"
        '<div class="studio-dashboard-main" data-studio-dashboard-main>'
        '<noscript><p class="studio-state-card">Studio interactions and charts require JavaScript. '
        "The generated dashboard structure remains available.</p></noscript>"
        f"{_render_dashboard_sections(dashboard, dashboard_metrics, source_status=source_status)}"
        '<div class="studio-no-metrics" data-no-visible-metrics hidden>'
        "<strong>No metrics are displayed.</strong>"
        "<p>Use Metric controls in the right panel to restore the default view or choose individual metrics.</p>"
        '<button type="button" data-visibility-action="reset">Restore Metrics</button>'
        "</div>"
        "</div>"
        '<aside class="studio-side-panel studio-side-right is-collapsed" '
        'data-studio-panel="right" aria-labelledby="studio-metrics-panel-title">'
        '<header><button type="button" data-panel-toggle="right" aria-expanded="false" '
        'aria-label="Expand metric controls panel"><span aria-hidden="true">←</span>'
        '</button><div>'
        '<h2 id="studio-metrics-panel-title">Metric controls</h2></div></header>'
        '<div class="studio-panel-content">'
        '<section class="studio-panel-section studio-panel-metrics-downloads" '
        'aria-labelledby="studio-metrics-panel-title">'
        '<div class="studio-panel-actions">'
        '<button type="button" data-visibility-action="show-all">Select all</button>'
        '<button type="button" data-visibility-action="hide-all">Clear all</button>'
        '<button type="button" data-visibility-action="reset">Restore defaults</button>'
        "</div>"
        f'{_control_group(dashboard, dashboard_metrics, control_type="visibility")}'
        '<div class="studio-panel-bulk studio-export-footer">'
        '<button class="studio-download-button" type="button" data-export-download>'
        '<span>Download CSV</span><small>Selected metrics · ZIP</small></button>'
        '<p data-export-feedback aria-live="polite"></p>'
        "</div>"
        "</section></div>"
        '<span class="studio-panel-collapsed-label" aria-hidden="true">Metrics</span>'
        "</aside>"
        "</div>"
        '<dialog class="studio-methodology-dialog" '
        'id="studio-methodology-dialog" data-studio-methodology-dialog '
        'aria-labelledby="studio-methodology-title">'
        '<div class="studio-methodology-shell">'
        '<header class="studio-methodology-header">'
        '<div><p>Attribution methodology</p>'
        '<h2 id="studio-methodology-title" data-methodology-title>'
        'Methodology</h2></div>'
        '<button type="button" data-methodology-close '
        'aria-label="Close methodology">×</button>'
        '</header>'
        '<div class="studio-methodology-content" data-methodology-content></div>'
        '</div>'
        '</dialog>'
        f'<script type="application/json" data-studio-config>{_json_script(config_payload)}</script>'
        f'<script src="../../assets/vendor/echarts.min.js?v={escape(echarts_js_version)}" defer></script>'
        f'<script src="../../assets/studio.js?v={escape(studio_js_version)}" defer></script>'
        "</section>"
    )


def write_studio_pages(
    *,
    pages: list,
    template: Template,
    output_dir: Path,
    render_generated_page: Callable,
    studio_dir: Path = DEFAULT_STUDIO_DIR,
    generated_data_dir: Path = STUDIO_GENERATED_DATA_DIR,
    studio_css_version: str = "local",
    studio_js_version: str = "local",
    landing_js_version: str = "local",
    echarts_js_version: str = "local",
) -> list[Path]:
    dashboards, metrics = load_studio_registry(
        studio_dir,
        generated_data_dir=generated_data_dir,
    )
    query_contracts = build_studio_query_contracts(
        [metric.data for metric in metrics]
    )
    generated_dashboard_ids = {
        dashboard.id
        for dashboard in dashboards
        if dashboard.data.get("data_mode") == "generated"
    }
    required_generated_query_ids = {
        query_id
        for query_id, contract in query_contracts.items()
        if generated_dashboard_ids.intersection(contract["dashboard_ids"])
    }
    studio_output_dir = Path(output_dir) / "studio"
    if studio_output_dir.exists():
        shutil.rmtree(studio_output_dir)
    studio_output_dir.mkdir(parents=True, exist_ok=True)
    studio_data_output_dir = studio_output_dir / "data"
    studio_data_output_dir.mkdir(parents=True, exist_ok=True)
    for dashboard in dashboards:
        if dashboard.data.get("data_mode") == "generated":
            continue
        shutil.copy2(
            Path(studio_dir) / "data" / dashboard.data_file,
            studio_data_output_dir / dashboard.data_file,
        )

    written_paths = publish_studio_generated_data(
        generated_data_dir,
        Path(output_dir) / "data" / "studio" / "generated",
        query_contracts=query_contracts,
        required_query_ids=required_generated_query_ids,
    )
    landing_path = studio_output_dir / "index.html"
    landing_path.write_text(
        render_generated_page(
            title="Studio",
            description=(
                "Independent, reusable analytics dashboards for ether.fi teams "
                "and partners."
            ),
            content=render_studio_landing(
                dashboards,
                metrics,
                landing_js_version=landing_js_version,
            ),
            pages=pages,
            template=template,
            active_slug="studio",
            link_prefix="../",
            asset_prefix="../",
            body_class="studio-page studio-landing-page",
            extra_head=(
                f'<link rel="stylesheet" href="../assets/studio.css?'
                f'v={escape(studio_css_version)}">'
            ),
        ),
        encoding="utf-8",
    )
    written_paths.append(landing_path)

    for dashboard in dashboards:
        dashboard_dir = studio_output_dir / dashboard.slug
        dashboard_dir.mkdir(parents=True, exist_ok=True)
        dashboard_metrics = metrics_for_dashboard(dashboard, metrics)
        data_payload = load_studio_data(
            dashboard,
            metrics=dashboard_metrics,
            studio_dir=studio_dir,
            generated_data_dir=generated_data_dir,
        )
        output_path = dashboard_dir / "index.html"
        output_path.write_text(
            render_generated_page(
                title=f"{dashboard.name} · Studio",
                description=str(dashboard.data["description"]),
                content=render_studio_dashboard(
                    dashboard,
                    dashboards,
                    metrics,
                    data_payload,
                    studio_js_version=studio_js_version,
                    echarts_js_version=echarts_js_version,
                ),
                pages=pages,
                template=template,
                active_slug="studio",
                link_prefix="../../",
                asset_prefix="../../",
                body_class=f"studio-page studio-dashboard-page studio-{dashboard.slug}",
                extra_head=(
                    f'<link rel="stylesheet" href="../../assets/studio.css?'
                    f'v={escape(studio_css_version)}">'
                ),
            ),
            encoding="utf-8",
        )
        written_paths.append(output_path)
    return written_paths
