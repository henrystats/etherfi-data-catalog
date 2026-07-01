from datetime import datetime, timedelta
from importlib import resources
import os
from pathlib import Path
import re

import yaml


_SEARCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "of",
    "on",
    "or",
    "semantic",
    "semantics",
    "table",
    "tables",
    "the",
    "to",
    "with",
    "why",
}

_DASHBOARD_CATEGORY_ORDER = {
    "stake": 0,
    "cash": 1,
    "liquid": 2,
    "others": 3,
}

_DEFAULT_DATASETS_DIR = "datasets"
_DEFAULT_DASHBOARDS_DIR = "dashboards"
_DEFAULT_FRESHNESS_REGISTRY_PATH = "status/dataset_freshness.yaml"
_PACKAGE_DATA_ROOT = resources.files("etherfi_catalog").joinpath("data")


def _catalog_data_root() -> Path | resources.abc.Traversable:
    override = os.getenv("ETHERFI_CATALOG_DATA_DIR")
    if override:
        return Path(override)
    return _PACKAGE_DATA_ROOT


def _resolve_catalog_dir(
    value: str | Path,
    *,
    default_value: str,
    env_var: str,
    package_subdir: str,
) -> Path | resources.abc.Traversable:
    override = os.getenv(env_var)
    if override:
        return Path(override)

    path = Path(value)
    if str(value) != default_value or path.exists():
        return path

    data_root = _catalog_data_root()
    return data_root.joinpath(package_subdir)


def _resolve_freshness_registry_path(
    value: str | Path,
) -> Path | resources.abc.Traversable:
    freshness_override = os.getenv("ETHERFI_FRESHNESS_PATH")
    if freshness_override:
        return Path(freshness_override)

    status_override = os.getenv("ETHERFI_STATUS_DIR")
    if status_override:
        return Path(status_override) / Path(value).name

    path = Path(value)
    if str(value) != _DEFAULT_FRESHNESS_REGISTRY_PATH or path.exists():
        return path

    data_root = _catalog_data_root()
    return data_root.joinpath("status", Path(value).name)


def _iter_yaml_files(path: Path | resources.abc.Traversable):
    if isinstance(path, Path):
        yield from sorted(path.glob("**/*.yaml"))
        return

    for child in sorted(path.iterdir(), key=lambda item: str(item)):
        if child.is_dir():
            yield from _iter_yaml_files(child)
        elif child.name.endswith(".yaml"):
            yield child


def _iter_child_dirs(path: Path | resources.abc.Traversable):
    if not _is_dir(path):
        return
    yield from sorted(
        (child for child in path.iterdir() if child.is_dir()),
        key=lambda item: str(item),
    )


def _is_file(path: Path | resources.abc.Traversable) -> bool:
    return path.is_file() if hasattr(path, "is_file") else False


def _is_dir(path: Path | resources.abc.Traversable) -> bool:
    return path.is_dir() if hasattr(path, "is_dir") else False


def _open_text(path: Path | resources.abc.Traversable):
    return path.open("r", encoding="utf-8")


def _search_terms(text: str) -> list[str]:
    terms: list[str] = []
    for term in re.findall(r"[a-z0-9_]+", text.lower()):
        if term in _SEARCH_STOPWORDS:
            continue
        if len(term) > 3 and term.endswith("ing"):
            term = term[:-3]
        elif len(term) > 3 and term.endswith("s"):
            term = term[:-1]
        terms.append(term)
    return terms


def load_datasets(datasets_dir: str | Path = _DEFAULT_DATASETS_DIR) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    path = _resolve_catalog_dir(
        datasets_dir,
        default_value=_DEFAULT_DATASETS_DIR,
        env_var="ETHERFI_DATASETS_DIR",
        package_subdir="datasets",
    )

    for dataset_path in _iter_yaml_files(path):
        with _open_text(dataset_path) as f:
            dataset = yaml.safe_load(f) or {}

        name = dataset.get("name")
        if not name:
            # Skip files that do not declare a dataset name.
            continue

        catalog[name] = dataset

    return catalog


def _normalize_dashboard_category(value) -> str:
    category = str(value or "others").strip().lower().replace("-", "_")
    return category if category in _DASHBOARD_CATEGORY_ORDER else "others"


def _normalize_dashboard_metadata(dashboard: dict, *, source_path, category: str | None = None) -> dict:
    normalized = dict(dashboard)
    normalized["category"] = _normalize_dashboard_category(normalized.get("category") or category)
    normalized["tags"] = list(normalized.get("tags") or [])
    normalized["datasets"] = list(normalized.get("datasets") or [])
    normalized["source_path"] = str(source_path)
    normalized["show_in_core"] = bool(
        normalized.get("show_in_core")
        or normalized.get("featured")
        or normalized.get("core")
    )
    return normalized


def _dashboard_sort_key(dashboard: dict) -> tuple[int, str]:
    category = _normalize_dashboard_category(dashboard.get("category"))
    return (
        _DASHBOARD_CATEGORY_ORDER.get(category, len(_DASHBOARD_CATEGORY_ORDER)),
        str(dashboard.get("title") or dashboard.get("name") or "").lower(),
    )


def _load_dashboard_yaml_file(path, *, category: str | None = None) -> list[dict]:
    with _open_text(path) as f:
        raw = yaml.safe_load(f) or {}

    dashboards = raw.get("dashboards") if isinstance(raw, dict) else None
    if isinstance(dashboards, list):
        return [
            _normalize_dashboard_metadata(dashboard, source_path=path, category=category)
            for dashboard in dashboards
            if isinstance(dashboard, dict) and dashboard.get("name")
        ]
    if isinstance(raw, dict) and raw.get("name"):
        return [_normalize_dashboard_metadata(raw, source_path=path, category=category)]
    return []


def load_dashboard_registry(
    registry_path: str | Path = _DEFAULT_DASHBOARDS_DIR,
) -> dict:
    path = _resolve_catalog_dir(
        registry_path,
        default_value=_DEFAULT_DASHBOARDS_DIR,
        env_var="ETHERFI_DASHBOARDS_DIR",
        package_subdir="dashboards",
    )
    dashboards_by_name: dict[str, dict] = {}

    def add_dashboard(dashboard: dict) -> None:
        name = dashboard.get("name")
        if name and name not in dashboards_by_name:
            dashboards_by_name[str(name)] = dashboard

    if _is_dir(path):
        for category_dir in _iter_child_dirs(path):
            category = category_dir.name
            for dashboard_path in _iter_yaml_files(category_dir):
                for dashboard in _load_dashboard_yaml_file(dashboard_path, category=category):
                    add_dashboard(dashboard)

        legacy_registry_path = path.joinpath("registry.yaml")
        if _is_file(legacy_registry_path):
            for dashboard in _load_dashboard_yaml_file(legacy_registry_path):
                add_dashboard(dashboard)
    elif _is_file(path):
        for dashboard in _load_dashboard_yaml_file(path):
            add_dashboard(dashboard)

    return {"dashboards": sorted(dashboards_by_name.values(), key=_dashboard_sort_key)}


def load_dataset_freshness_registry(
    registry_path: str | Path = _DEFAULT_FRESHNESS_REGISTRY_PATH,
) -> dict:
    path = _resolve_freshness_registry_path(registry_path)
    if not _is_file(path):
        return {}

    with _open_text(path) as f:
        registry = yaml.safe_load(f) or {}

    return registry


def dataset_reference_values(dataset: dict, catalog_name: str | None = None) -> list:
    return [
        catalog_name,
        dataset.get("name"),
        dataset.get("table_name"),
        *(dataset.get("aliases") or []),
    ]


def resolve_dataset_name(name, datasets: dict) -> str | None:
    if name in datasets:
        return name

    query = str(name).lower()
    for catalog_name, dataset in datasets.items():
        for value in dataset_reference_values(dataset, catalog_name):
            if value and str(value).lower() == query:
                return catalog_name

    return None


def freshness_snapshot_for_dataset(
    dataset: dict,
    freshness_registry: dict,
    catalog_name: str | None = None,
) -> dict:
    for value in dataset_reference_values(dataset, catalog_name):
        if value and value in freshness_registry:
            return freshness_registry[value] or {}

    source_query_id = dataset.get("source_query_id")
    if source_query_id is not None:
        source_query_id_text = str(source_query_id)
        for snapshot in freshness_registry.values():
            if str((snapshot or {}).get("query_id")) == source_query_id_text:
                return snapshot or {}

    return {}


ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
ADDRESS_IN_TEXT_PATTERN = re.compile(r"(?<![a-fA-F0-9])0x[a-fA-F0-9]{40}(?![a-fA-F0-9])")
CASH_SAFE_ADDRESSES_DATASET_NAME = "etherfi_cash_addresses"
CASH_EVENT_TYPES = {"spend", "borrow", "repay", "cashback", "liquidation"}
QUERY_MODES = {"summary", "rows"}
PROTOCOL_EVENT_TYPES = {"deposit", "withdrawal_request", "withdrawal_processed"}
_PROTOCOL_TVL_TIMESERIES_PERIODS = {
    "last_30_days",
    "last_90_days",
    "last_1_year",
    "last_month",
}
_CASH_HOLDINGS_TIMESERIES_PERIODS = {
    "last_30_days",
    "last_90_days",
    "last_1_year",
    "last_2_years",
    "last_month",
}
_TIMESERIES_GRANULARITIES = {"day", "month"}
_CASH_HOLDINGS_GROUP_BYS = {"token_symbol", "category"}
_CASH_HOLDINGS_CATEGORY_PRESETS = {
    "cash_balance_buckets": {
        "liquidUSD": "liquidUSD",
        "liquidETH": "liquidETH",
        "liquidBTC": "liquidBTC",
        "USDC": "stables",
        "USDC.e": "stables",
    }
}
_KNOWN_PROTOCOL_TVL_STRATEGY_SYMBOLS = {
    "eeth": "eETH",
    "liquideth": "liquidETH",
    "liquidusd": "liquidUSD",
    "ebtc": "eBTC",
    "liquidbtc": "liquidBTC",
}
_KNOWN_ANALYSIS_TOKEN_SYMBOLS = {
    "usdc": "USDC",
    "usdc.e": "USDC.e",
    "eeth": "eETH",
    "liquideth": "liquidETH",
    "liquidusd": "liquidUSD",
    "ebtc": "eBTC",
    "liquidbtc": "liquidBTC",
}
_PLANNER_VISUALIZATION_GUIDE = {
    "cash_events_time_volume": {
        "type": "bar_chart",
        "alternatives": ["line_chart"],
        "rationale": "Time-bucketed event volume is easy to compare as bars; use a line chart when the trend matters more than period-to-period comparison.",
    },
    "protocol_events_time_volume": {
        "type": "bar_chart",
        "alternatives": ["line_chart", "table"],
        "rationale": "Time-bucketed protocol event volume and counts are easy to compare as bars; use a table when contract-level reconciliation fields matter most.",
    },
    "cash_balances_category_timeseries": {
        "type": "grouped_bar_chart",
        "alternatives": ["stacked_bar_chart", "line_chart"],
        "rationale": "Monthly category snapshots compare well as grouped bars; stacked bars are useful for total composition over time.",
    },
    "protocol_tvl_timeseries": {
        "type": "line_chart",
        "alternatives": ["grouped_bar_chart"],
        "rationale": "Protocol TVL is a time-series level metric, so a line chart best preserves trend shape.",
    },
    "protocol_tvl_month_end": {
        "type": "line_chart",
        "alternatives": ["grouped_bar_chart", "month_over_month_bar_chart"],
        "rationale": "Month-end TVL snapshots usually read best as trend lines; use grouped bars for month-by-month comparison.",
    },
    "holder_ranking": {
        "type": "table",
        "alternatives": ["horizontal_bar_chart"],
        "rationale": "Top-N holder outputs need addresses and balances, so a table is the safest default; use horizontal bars for a presentation view.",
    },
    "price_timeseries": {
        "type": "line_chart",
        "alternatives": ["table"],
        "rationale": "Token price history is a time-series metric, so a line chart is the clearest default; use a table for coverage diagnostics.",
    },
    "product_protocol_deployment": {
        "type": "table",
        "alternatives": ["horizontal_bar_chart"],
        "rationale": "Protocol deployment exposure should show protocol, chain, token, and net-vs-raw metrics; a bar chart can summarize top protocols.",
    },
}

_KNOWN_AUM_PROTOCOL_PROJECTS = {
    "aave": "Aave",
    "morpho": "Morpho",
}


def _normalize_address_literal(address: str) -> str:
    if not isinstance(address, str) or not ADDRESS_PATTERN.fullmatch(address):
        raise ValueError("Address must be a 42-character 0x-prefixed hex string.")
    return address.lower()


def _extract_address_literals(text: str) -> list[str]:
    found: list[str] = []
    for match in ADDRESS_IN_TEXT_PATTERN.findall(text):
        normalized = match.lower()
        if normalized not in found:
            found.append(normalized)
    return found


def _validate_date_literal(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a YYYY-MM-DD string.")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a YYYY-MM-DD string.") from exc


def _validate_timestamp_literal(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO timestamp or YYYY-MM-DD string.")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).isoformat(sep=" ")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp or YYYY-MM-DD string.") from exc


def _validate_simple_string_literal(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError(f"{field_name} must contain only letters, numbers, and underscores.")
    return value


def _quote_sql_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _validate_limit(limit, default: int = 100) -> int:
    if limit is None:
        return default
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer.")
    return limit


def _validate_min_total_usd(min_total_usd) -> float | None:
    if min_total_usd is None:
        return None
    if not isinstance(min_total_usd, (int, float)) or isinstance(min_total_usd, bool) or min_total_usd < 0:
        raise ValueError("min_total_usd must be a non-negative number.")
    return float(min_total_usd)


def _validate_recent_days(recent_days, default: int = 30) -> int:
    if recent_days is None:
        return default
    if not isinstance(recent_days, int) or isinstance(recent_days, bool) or recent_days <= 0 or recent_days > 365:
        raise ValueError("recent_days must be a positive integer no greater than 365.")
    return recent_days


def _validate_mode(mode: str | None) -> str:
    if mode is None:
        return "summary"
    if mode not in QUERY_MODES:
        raise ValueError("mode must be 'summary' or 'rows'.")
    return mode


def _normalize_string_list(values, field_name: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field_name} must be a non-empty list of strings.")

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must contain only non-empty strings.")
        normalized_value = value.strip()
        if normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized.append(normalized_value)
    return normalized


def _validate_protocol_tvl_timeseries_granularity(granularity: str | None) -> str:
    return _validate_timeseries_granularity(granularity, allowed=_TIMESERIES_GRANULARITIES)


def _validate_timeseries_granularity(granularity: str | None, allowed: set[str]) -> str:
    if granularity is None:
        return "day"
    if granularity not in allowed:
        allowed_values = " or ".join(f"'{value}'" for value in sorted(allowed))
        raise ValueError(f"granularity must be {allowed_values}.")
    return granularity


def _resolve_timeseries_date_range(
    start_date=None,
    end_date=None,
    period=None,
    supported_periods=None,
    now=None,
) -> tuple[str, str]:
    supported_periods = supported_periods or set()
    if period and (start_date or end_date):
        raise ValueError("Provide either start_date + end_date or period, not both.")
    if start_date and not end_date:
        raise ValueError("end_date is required when start_date is provided.")
    if end_date and not start_date:
        raise ValueError("start_date is required when end_date is provided.")

    if start_date and end_date:
        start_date_value = _validate_date_literal(start_date, "start_date")
        end_date_value = _validate_date_literal(end_date, "end_date")
        if start_date_value > end_date_value:
            raise ValueError("start_date must be on or before end_date.")
        return start_date_value, end_date_value

    if not period:
        raise ValueError("Provide either start_date + end_date or a supported period.")
    if period not in supported_periods:
        supported_values = ", ".join(sorted(supported_periods))
        raise ValueError(f"period must be one of: {supported_values}.")

    anchor = now or datetime.utcnow()
    anchor_date = anchor.date() if isinstance(anchor, datetime) else anchor
    if period == "last_30_days":
        return (anchor_date - timedelta(days=29)).isoformat(), anchor_date.isoformat()
    if period == "last_90_days":
        return (anchor_date - timedelta(days=89)).isoformat(), anchor_date.isoformat()
    if period == "last_1_year":
        return (anchor_date - timedelta(days=364)).isoformat(), anchor_date.isoformat()
    if period == "last_2_years":
        return (anchor_date - timedelta(days=730)).isoformat(), anchor_date.isoformat()

    first_day_this_month = anchor_date.replace(day=1)
    last_day_previous_month = first_day_this_month - timedelta(days=1)
    first_day_previous_month = last_day_previous_month.replace(day=1)
    return first_day_previous_month.isoformat(), last_day_previous_month.isoformat()


def _build_month_end_snapshot_sql(
    *,
    daily_cte_sql: str,
    group_columns: list[tuple[str, str]],
    metric_selects: list[str],
    order_columns: list[str],
    output_group_aliases: list[str] | None = None,
    include_month_end_day: bool = True,
) -> str:
    group_aliases = [alias for alias, _ in group_columns]
    output_group_aliases = output_group_aliases if output_group_aliases is not None else group_aliases
    group_select = "".join(f"    {expression} AS {alias},\n" for alias, expression in group_columns)
    group_by = ", ".join(str(index) for index in range(1, len(group_aliases) + 2))
    join_conditions = "\n".join(
        f" AND daily_totals.{alias} = month_end_days.{alias}"
        for alias in group_aliases
    )
    grouped_column_count = 1 + len(output_group_aliases) + (1 if include_month_end_day else 0)
    outer_group_by = ", ".join(str(index) for index in range(1, grouped_column_count + 1))
    order_by = ", ".join(order_columns)

    return (
        "WITH daily_totals AS (\n"
        + daily_cte_sql
        + "),\n"
        + "month_end_days AS (\n"
        + "  SELECT\n"
        + "    CAST(DATE_TRUNC('month', day) AS DATE) AS month,\n"
        + group_select
        + "    MAX(day) AS month_end_day\n"
        + "  FROM daily_totals\n"
        f"  GROUP BY {group_by}\n"
        + ")\n"
        + "SELECT\n"
        + "  month_end_days.month AS month,\n"
        + ("  month_end_days.month_end_day AS month_end_day,\n" if include_month_end_day else "")
        + "".join(f"  month_end_days.{alias} AS {alias},\n" for alias in output_group_aliases)
        + "".join(f"  {select_expr},\n" for select_expr in metric_selects)[:-2]
        + "\nFROM month_end_days\n"
        + "JOIN daily_totals\n"
        + "  ON daily_totals.day = month_end_days.month_end_day\n"
        + join_conditions
        + f"\nGROUP BY {outer_group_by}\n"
        + f"ORDER BY {order_by};"
    )


def _normalize_protocol_tvl_strategy_symbol(value: str, field_name: str) -> str:
    normalized_value = _validate_simple_string_literal(value, field_name)
    return _KNOWN_PROTOCOL_TVL_STRATEGY_SYMBOLS.get(normalized_value.lower(), normalized_value)


def _normalize_protocol_tvl_strategy_symbol_list(values, field_name: str) -> list[str]:
    normalized_values = _normalize_string_list(values, field_name)
    canonical_values: list[str] = []
    seen: set[str] = set()
    for value in normalized_values:
        canonical_value = _normalize_protocol_tvl_strategy_symbol(value, field_name)
        if canonical_value in seen:
            continue
        seen.add(canonical_value)
        canonical_values.append(canonical_value)
    return canonical_values


def _resolve_protocol_tvl_timeseries_date_range(
    start_date=None,
    end_date=None,
    period=None,
    now=None,
) -> tuple[str, str]:
    return _resolve_timeseries_date_range(
        start_date=start_date,
        end_date=end_date,
        period=period,
        supported_periods=_PROTOCOL_TVL_TIMESERIES_PERIODS,
        now=now,
    )


def _get_query_ready_dataset(
    dataset_name: str,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> tuple[dict, dict | None] | tuple[None, dict]:
    datasets = datasets or load_datasets()
    dataset = datasets.get(dataset_name)
    if dataset is None:
        return None, {
            "error": f"Dataset metadata not found for {dataset_name}.",
            "dataset_name": dataset_name,
        }

    if not dataset.get("query_ready"):
        return None, {
            "error": f"Dataset {dataset_name} is not query_ready.",
            "dataset_name": dataset_name,
            "query_ready": False,
        }

    freshness_status = get_dataset_status(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    return dataset, freshness_status


def search_dashboards(query, registry=None, datasets=None, freshness_registry=None, now=None) -> list[dict]:
    registry = registry or load_dashboard_registry()
    datasets = datasets or load_datasets()
    dashboards = registry.get("dashboards", [])
    query_text = query.lower()
    matches: list[dict] = []

    for dashboard in dashboards:
        searchable_values = [
            dashboard.get("name", ""),
            dashboard.get("title", ""),
            dashboard.get("category", ""),
            dashboard.get("description", ""),
            dashboard.get("url", ""),
        ]
        searchable_values.extend(dashboard.get("tags", []))
        searchable_values.extend(dashboard.get("datasets", []))

        if any(query_text in str(value).lower() for value in searchable_values):
            details = dict(dashboard)
            linked_dataset_warnings: list[dict] = []

            for dataset_name in details.get("datasets", []):
                dataset = get_dataset_details(
                    dataset_name,
                    datasets=datasets,
                    freshness_registry=freshness_registry,
                    now=now,
                )
                if dataset and dataset.get("warning"):
                    linked_dataset_warnings.append(
                        {
                            "name": dataset["name"],
                            "display_name": dataset["display_name"],
                            "warning": dataset["warning"],
                            "recommended_action": dataset["recommended_action"],
                        }
                    )

            if linked_dataset_warnings:
                details["linked_dataset_warnings"] = linked_dataset_warnings

            matches.append(details)

    return matches


def get_dashboard_details(name, registry=None) -> dict | None:
    registry = registry or load_dashboard_registry()

    for dashboard in registry.get("dashboards", []):
        if dashboard.get("name") == name:
            return dashboard

    return None


def get_dashboard_status(name, registry=None, datasets=None, freshness_registry=None, now=None) -> dict | None:
    registry = registry or load_dashboard_registry()
    datasets = datasets or load_datasets()

    for dashboard in registry.get("dashboards", []):
        if dashboard.get("name") != name:
            continue

        status = {
            "name": dashboard.get("name"),
            "title": dashboard.get("title"),
            "url": dashboard.get("url"),
            "category": dashboard.get("category"),
            "show_in_core": dashboard.get("show_in_core"),
            "datasets": dashboard.get("datasets", []),
        }
        linked_dataset_warnings: list[dict] = []

        for dataset_name in status["datasets"]:
            dataset = get_dataset_details(
                dataset_name,
                datasets=datasets,
                freshness_registry=freshness_registry,
                now=now,
            )
            if dataset and dataset.get("warning"):
                linked_dataset_warnings.append(
                    {
                        "name": dataset["name"],
                        "display_name": dataset["display_name"],
                        "warning": dataset["warning"],
                        "recommended_action": dataset["recommended_action"],
                    }
                )

        if linked_dataset_warnings:
            status["linked_dataset_warnings"] = linked_dataset_warnings

        return status

    return None


def get_dataset_details(name, datasets=None, freshness_registry=None, now=None) -> dict | None:
    datasets = datasets or load_datasets()
    resolved_name = resolve_dataset_name(name, datasets)
    if resolved_name is None:
        return None
    dataset = datasets.get(resolved_name)
    if dataset is None:
        return None

    details = dict(dataset)
    freshness_registry = (
        load_dataset_freshness_registry()
        if freshness_registry is None
        else freshness_registry
    )
    freshness_snapshot = freshness_snapshot_for_dataset(
        details,
        freshness_registry,
        catalog_name=resolved_name,
    )
    if freshness_snapshot.get("last_updated") is not None:
        details["last_updated"] = freshness_snapshot["last_updated"]

    last_updated = details.get("last_updated")
    refresh_interval_minutes = details.get("refresh_interval_minutes")

    if last_updated is not None and refresh_interval_minutes is not None:
        if isinstance(last_updated, str):
            try:
                last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            except ValueError:
                last_updated = None

        if isinstance(last_updated, datetime):
            details["freshness"] = evaluate_freshness(
                last_updated,
                refresh_interval_minutes,
                now=now,
            )
            if details["freshness"]["is_stale"]:
                details["warning"] = (
                    "This dataset may be outdated based on the latest imported "
                    f"freshness snapshot. Expected refresh interval: {refresh_interval_minutes} minutes."
                )
                details["recommended_action"] = (
                    "Refresh the tracker CSV snapshot, verify the Dune query/source query "
                    "status, and treat downstream dashboard numbers cautiously until freshness is updated."
                )

    return details


def get_dataset_status(name, datasets=None, freshness_registry=None, now=None) -> dict | None:
    details = get_dataset_details(
        name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if details is None:
        return None

    status = {
        "name": details["name"],
        "display_name": details["display_name"],
        "refresh_interval_minutes": details.get("refresh_interval_minutes"),
    }
    if "last_updated" in details:
        status["last_updated"] = details["last_updated"]
    if "freshness" in details:
        status["freshness"] = details["freshness"]
    if "warning" in details:
        status["warning"] = details["warning"]
    if "recommended_action" in details:
        status["recommended_action"] = details["recommended_action"]

    return status


def _dataset_plan_summary(dataset: dict) -> dict:
    return {
        "name": dataset.get("name"),
        "table_name": dataset.get("table_name"),
        "display_name": dataset.get("display_name"),
        "grain": dataset.get("grain"),
        "query_ready": dataset.get("query_ready", False),
    }


def _dataset_notes(dataset: dict, field_name: str, limit: int = 3) -> list[str]:
    values = dataset.get(field_name, [])
    if isinstance(values, str):
        return [values]
    return list(values[:limit])


def _question_prefers_live_query(question: str) -> bool:
    question_lower = question.lower()
    return bool(
        re.search(
            r"\b(current|latest|now|right now|today|yesterday|recent|fresh|live)\b",
            question_lower,
        )
    )


def _question_prefers_historical_matview(question: str) -> bool:
    question_lower = question.lower()
    return bool(
        re.search(
            r"\b(historical|history|over time|trend|daily|weekly|monthly|quarterly|yearly|last year|last month|last quarter|between|since|from)\b",
            question_lower,
        )
        or re.search(r"\b20\d{2}\b", question_lower)
    )


def _live_query_guidance(question: str, dataset: dict) -> dict:
    live_query = dataset.get("live_query") or {}
    use_live_query = _question_prefers_live_query(question) and not _question_prefers_historical_matview(question)
    selected_source = "live_query" if use_live_query else "mat_view"
    table_name = live_query.get("table_name") if use_live_query else None
    table_name = table_name or dataset.get("table_name")
    guidance_notes = []

    if use_live_query:
        guidance_notes.append(
            "Current/recent prompts should default to the dataset live_query reference when present."
        )
        if live_query.get("defaults_to_mat_view"):
            guidance_notes.append(
                "This live_query currently defaults to the same materialized-view query/table; future implementations can add fresher recent data."
            )
        refresh_interval = dataset.get("refresh_interval_minutes")
        if refresh_interval:
            guidance_notes.append(
                f"Because the current live_query still uses the mat view baseline, its {refresh_interval}-minute refresh cadence may affect freshness."
            )
    else:
        guidance_notes.append(
            "Historical/range prompts should prefer the baseline materialized view; there is usually little practical difference for settled historical analysis."
        )
        refresh_interval = dataset.get("refresh_interval_minutes")
        if refresh_interval:
            guidance_notes.append(
                f"Mat view freshness is still relevant near the edge of the data; expected refresh interval is {refresh_interval} minutes."
            )

    return {
        "selected_data_access": selected_source,
        "selected_table_name": table_name,
        "live_query": live_query,
        "mat_view": {
            "table_name": dataset.get("table_name"),
            "source_query_id": dataset.get("source_query_id"),
            "source_query_url": dataset.get("source_query_url"),
            "refresh_interval_minutes": dataset.get("refresh_interval_minutes"),
        },
        "data_access_notes": guidance_notes,
    }


def _planner_visualization(
    guide_key: str,
    *,
    title: str,
    x: str | None = None,
    y: str | None = None,
    series: str | None = None,
    sort: str | None = None,
) -> dict:
    guide = _PLANNER_VISUALIZATION_GUIDE[guide_key]
    recommendation = {
        "type": guide["type"],
        "title": title,
        "rationale": guide["rationale"],
        "alternatives": guide["alternatives"],
    }
    if x:
        recommendation["x"] = x
    if y:
        recommendation["y"] = y
    if series:
        recommendation["series"] = series
    if sort:
        recommendation["sort"] = sort
    return recommendation


def _compact_joined(values: list[str]) -> str:
    return ", ".join(value for value in values if value)


def _extract_known_token_symbols(question_text: str) -> list[str]:
    found: list[str] = []
    normalized = question_text.lower().replace("-", "")
    for raw_symbol, canonical_symbol in _KNOWN_ANALYSIS_TOKEN_SYMBOLS.items():
        if re.search(rf"\b{re.escape(raw_symbol)}\b", normalized) and canonical_symbol not in found:
            found.append(canonical_symbol)
    return found


def _question_has_cash_context(question_lower: str) -> bool:
    return re.search(
        r"\b(cash|card|cards|user_safe|safe|safes|spend|spends|spending|spent|cashback|borrow|borrowed|borrowing|debt|repay|repaid|repayment|liquidation)\b",
        question_lower,
    ) is not None


def _question_mentions_cash_safe_validation(question_lower: str) -> bool:
    has_cash_safe_lens = re.search(
        r"\b(cash[-\s]?safe|cash\s+safes|cash\s+address|user_safe|card\s+account)\b",
        question_lower,
    ) is not None or ("cash" in question_lower and "safe" in question_lower)
    if not has_cash_safe_lens:
        return False

    has_validation_lens = re.search(
        r"\b(is|whether|check|confirm|validate|validation|identity|registry|registered|listed|actually)\b",
        question_lower,
    ) is not None
    if has_validation_lens:
        return True

    has_activity_or_balance_lens = re.search(
        r"\b(activity|event|events|spend|spends|spending|spent|cashback|borrow|repay|repaid|liquidation|balance|balances|holding|holdings|profile|summarize|summary|top|rank|users?)\b",
        question_lower,
    ) is not None
    return not has_activity_or_balance_lens


def _question_is_cash_safe_validation(question_lower: str) -> bool:
    if not ADDRESS_IN_TEXT_PATTERN.search(question_lower):
        return False
    return _question_mentions_cash_safe_validation(question_lower)


def _question_has_explicit_aum_context(question_lower: str) -> bool:
    return re.search(
        r"\b(aum|assets\s+under\s+management|managed\s+address|ether\.?fi[-\s]?managed|ether\.?fi[-\s]?owned|protocol[-\s]?owned|internal\s+(?:ether\.?fi\s+)?address|treasury|address\s+registry|address_name|address\s+traits|protocol[-\s]?controlled\s+assets?)\b",
        question_lower,
    ) is not None


def _question_mentions_generic_protocol_wallet_holdings(question_lower: str) -> bool:
    if _question_has_cash_context(question_lower):
        return False
    if _question_has_explicit_aum_context(question_lower):
        return False
    if re.search(r"\b(deposit|deposits|deposited|depositing)\b", question_lower):
        return False
    has_address_or_wallet_lens = (
        ADDRESS_IN_TEXT_PATTERN.search(question_lower) is not None
        or re.search(r"\b(address|wallet)\b", question_lower) is not None
    )
    has_holdings_lens = re.search(
        r"\b(have|has|hold|holds|holding|holdings|balance|balances|invested|tokens?)\b",
        question_lower,
    ) is not None
    return has_address_or_wallet_lens and has_holdings_lens


def _question_is_generic_protocol_address_holdings(question_lower: str) -> bool:
    if _question_is_explicit_aum_managed_address(question_lower):
        return False
    if not ADDRESS_IN_TEXT_PATTERN.search(question_lower):
        return False
    return _question_mentions_generic_protocol_wallet_holdings(question_lower)


def _question_is_explicit_aum_managed_address(question_lower: str) -> bool:
    if not ADDRESS_IN_TEXT_PATTERN.search(question_lower):
        return False
    return _question_has_explicit_aum_context(question_lower)


def _question_is_cash_safe_address_balance(question_lower: str) -> bool:
    if not ADDRESS_IN_TEXT_PATTERN.search(question_lower):
        return False
    if not re.search(r"\b(cash|card|safe|user_safe)\b", question_lower):
        return False
    if re.search(r"\b(event|events|activity|spend|spends|spending|spent|cashback|borrow|repay|repaid|liquidation)\b", question_lower):
        return False
    return re.search(r"\b(balance|balances|holding|holdings|have|has)\b", question_lower) is not None


def _question_is_historical_protocol_deposit(question_lower: str) -> bool:
    if _question_has_cash_context(question_lower):
        return False
    if not ADDRESS_IN_TEXT_PATTERN.search(question_lower):
        return False
    if re.search(r"\bhave\s+(?:this\s+)?(?:wallet|address)?\s*deposited\s+in\b", question_lower):
        return False
    return re.search(
        r"\b(deposited\s+into|deposit\s+into|deposits?\s+from|show\s+deposits?|did\s+.*\bdeposit|has\s+.*\bdeposited\s+into|historical\s+deposits?)\b",
        question_lower,
    ) is not None


def _question_is_ambiguous_protocol_deposited_balance(question_lower: str) -> bool:
    if _question_has_cash_context(question_lower):
        return False
    if not ADDRESS_IN_TEXT_PATTERN.search(question_lower):
        return False
    return re.search(
        r"\b(have|has)\b.*\bdeposited\s+in\s+ether\.?fi\b|\bdeposited\s+in\s+ether\.?fi\b",
        question_lower,
    ) is not None


def _extract_protocol_strategy_symbols(question_text: str) -> list[str]:
    found: list[str] = []
    normalized = question_text.lower().replace("-", "")
    for raw_symbol, canonical_symbol in _KNOWN_PROTOCOL_TVL_STRATEGY_SYMBOLS.items():
        if re.search(rf"\b{re.escape(raw_symbol)}\b", normalized) and canonical_symbol not in found:
            found.append(canonical_symbol)
    return found


def _plan_error(question, execute_live=False) -> dict:
    return {
        "tool_name": "plan_etherfi_query",
        "question_class": "planning / query authoring",
        "execute_live": execute_live,
        "executed_live": False,
        "interpreted_question": None,
        "recommended_datasets": [],
        "why_these_datasets": [],
        "important_caveats": [],
        "preferred_filters": [],
        "suggested_grain": None,
        "suggested_metrics": [],
        "join_notes": [],
        "suggested_sql_skeleton": None,
        "suggested_visualization": None,
        "suggested_chart_title": None,
        "suggested_query_description": None,
        "suggested_dashboard_description": None,
        "suggested_next_step": None,
        "error": "question must be a non-empty string.",
        "input_question": question,
    }


def _finalize_etherfi_query_plan(plan: dict, execute_live: bool) -> dict:
    plan.setdefault("tool_name", "plan_etherfi_query")
    plan.setdefault("question_class", "planning / query authoring")
    plan.setdefault("execute_live", execute_live)
    plan.setdefault("executed_live", False)
    plan.setdefault(
        "live_mode_note",
        (
            "This tool is planning-oriented. It does not create, execute, save, "
            "or visualize Dune queries; use Dune MCP for that next step."
        ),
    )
    if execute_live:
        plan["live_mode_note"] = (
            "execute_live=True was requested, but plan_etherfi_query remains a planning tool. "
            "No Dune query was created or executed."
        )
    return plan


def _plan_cash_safe_validation_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    dataset, freshness_status = _get_query_ready_dataset(
        CASH_SAFE_ADDRESSES_DATASET_NAME,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    address_literals = _extract_address_literals(question)
    address_literal = address_literals[0] if address_literals else "<cash_safe_address>"
    table_name = dataset["table_name"]
    suggested_sql = (
        "SELECT\n"
        "  blockchain,\n"
        "  address,\n"
        "  last_updated\n"
        f"FROM {table_name}\n"
        f"WHERE address = {address_literal}\n"
        "ORDER BY blockchain;"
    )

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan a public Cash-safe registry lookup for one address.",
            "question_class": "single-entity lookup",
            "recommended_tool": "check_cash_safe_address",
            "recommended_tool_parameters": {
                "address": address_literal if address_literals else None,
                "blockchain": None,
                "execute_live": False,
            },
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                "Cash-safe validation should use the public Cash-safe registry, not private/internal protocol address registries.",
            ],
            "important_caveats": _dataset_notes(dataset, "caveats", limit=4),
            "preferred_filters": [
                {"field": "address", "operator": "=", "value": address_literal},
            ],
            "suggested_grain": "one row per blockchain and Cash safe address",
            "suggested_metrics": ["registry_row_count", "matching_blockchains"],
            "join_notes": [
                "No join is needed to answer whether the address appears in the public Cash-safe registry.",
                "Use Cash events or AUM balances separately for activity or balance questions after identity is established.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": None,
            "suggested_chart_title": None,
            "suggested_query_description": (
                f"Checks whether {address_literal} appears in the public ether.fi Cash-safe registry."
            ),
            "suggested_dashboard_description": None,
            "suggested_next_step": (
                "Use check_cash_safe_address with execute_live=false to review SQL, or execute_live=true only when a live registry check is approved."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def _plan_cash_events_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_cash_events"
    dataset, freshness_status = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    question_lower = question.lower()
    token_symbols = _extract_known_token_symbols(question)
    event_type = "spend" if re.search(r"\b(spend|spends|spending)\b", question_lower) else None
    granularity = "week" if re.search(r"\b(week|weekly)\b", question_lower) else "day"
    metric = "weekly_spend_volume_usd" if granularity == "week" else "daily_event_volume_usd"
    token_filter = token_symbols[0] if token_symbols else None
    data_access = _live_query_guidance(question, dataset)
    table_name = data_access["selected_table_name"]

    where_lines = []
    filters = []
    if event_type:
        where_lines.append(f"event_type = {_quote_sql_string(event_type)}")
        filters.append({"field": "event_type", "operator": "=", "value": event_type})
    if token_filter:
        where_lines.append(f"token_symbol = {_quote_sql_string(token_filter)}")
        filters.append({"field": "token_symbol", "operator": "=", "value": token_filter})
    where_lines.append("block_date >= DATE_ADD('month', -3, CURRENT_DATE)")
    filters.append({"field": "block_date", "operator": "range", "value": "choose_report_window"})
    where_sql = "\n  AND ".join(where_lines)
    date_expr = "DATE_TRUNC('week', block_date)" if granularity == "week" else "block_date"
    title_token = token_filter or "token"
    title_event = event_type or "Cash event"
    period_label = "Weekly" if granularity == "week" else "Daily"
    chart_title = f"{period_label} {title_token} {title_event} volume"
    event_scope = f"event_type='{event_type}'" if event_type else "all Cash event types"
    token_scope = f"token_symbol='{token_filter}'" if token_filter else "selected token scope"
    suggested_sql = (
        "SELECT\n"
        f"  {date_expr} AS period,\n"
        "  token_symbol,\n"
        "  SUM(token_amount_usd) AS volume_usd,\n"
        "  COUNT(*) AS event_count\n"
        f"FROM {table_name}\n"
        f"WHERE {where_sql}\n"
        "GROUP BY 1, 2\n"
        "ORDER BY 1;"
    )

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan a chart-ready Cash events volume query.",
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                "Cash spend volume is an activity/event question, so the Cash events table is narrower and more semantically correct than Cash balance snapshots.",
            ],
            "important_caveats": _dataset_notes(dataset, "caveats", limit=4),
            "data_access": data_access,
            "preferred_filters": filters,
            "suggested_grain": granularity,
            "suggested_metrics": [metric, "event_count"],
            "join_notes": [
                "No join is needed for basic spend volume by token and week.",
                "Use token_address instead of token_symbol if symbol ambiguity matters.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                "cash_events_time_volume",
                title=chart_title,
                x="period",
                y="volume_usd",
                series="token_symbol",
            ),
            "suggested_chart_title": chart_title,
            "suggested_query_description": (
                f"Aggregates ether.fi Cash events by {granularity}, filtered to {event_scope} and {token_scope}. "
                "Cash event volume and Cash balances answer different questions. "
                f"Uses {data_access['selected_data_access']}; see data_access notes for freshness."
            ),
            "suggested_dashboard_description": (
                f"Cash activity view for {chart_title.lower()}; review event_type and token filters before sharing."
            ),
            "suggested_next_step": (
                "Use Dune MCP to create, run, and save the shareable query; prefer a team-owned Dune context for shared team artifacts. "
                "Then use Dune MCP visualization tools for a bar chart or dashboard widget."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def _plan_protocol_events_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_protocol_events"
    dataset, freshness_status = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    question_lower = question.lower()
    token_symbols = _extract_known_token_symbols(question)
    address_literals = _extract_address_literals(question)
    address_literal = address_literals[0] if address_literals else None
    event_type = None
    if re.search(r"\b(deposit|deposits|deposited|depositing)\b", question_lower):
        event_type = "deposit"
    elif "withdrawal_request" in question_lower or re.search(r"\bwithdrawal requests?\b", question_lower):
        event_type = "withdrawal_request"
    elif "withdrawal_processed" in question_lower or re.search(r"\bprocessed withdrawals?\b", question_lower):
        event_type = "withdrawal_processed"

    data_access = _live_query_guidance(question, dataset)
    table_name = data_access["selected_table_name"]
    granularity = "week" if re.search(r"\b(week|weekly)\b", question_lower) else "day"
    is_address_deposit_lookup = address_literal is not None and event_type == "deposit"
    date_expr = "DATE_TRUNC('week', block_date)" if granularity == "week" else "block_date"
    token_filter = token_symbols[0] if token_symbols else None
    where_lines = []
    filters = []
    if not is_address_deposit_lookup:
        where_lines.append("block_date >= DATE_ADD('month', -3, CURRENT_DATE)")
        filters.append({"field": "block_date", "operator": "range", "value": "choose_report_window"})

    if event_type:
        where_lines.append(f"event_type = {_quote_sql_string(event_type)}")
        filters.append({"field": "event_type", "operator": "=", "value": event_type})
    if address_literal:
        where_lines.append(f"address = {address_literal}")
        filters.append({"field": "address", "operator": "=", "value": address_literal})
    if token_filter:
        where_lines.append(f"strategy_symbol = {_quote_sql_string(token_filter)}")
        filters.append({"field": "strategy_symbol", "operator": "=", "value": token_filter})

    where_sql = "\n  AND ".join(where_lines) if where_lines else "1 = 1"
    if is_address_deposit_lookup:
        suggested_sql = (
            "SELECT\n"
            "  project,\n"
            "  strategy_symbol,\n"
            "  strategy_address,\n"
            "  token_symbol,\n"
            "  amount_underlying_symbol,\n"
            "  COUNT(*) AS deposit_event_count,\n"
            "  SUM(token_amount) AS deposited_token_amount,\n"
            "  SUM(amount_underlying) AS deposited_underlying_amount,\n"
            "  SUM(amount_usd) AS deposited_usd,\n"
            "  MAX(block_time) AS latest_deposit_time,\n"
            "  MAX(last_updated) AS data_updated_at\n"
            f"FROM {table_name}\n"
            f"WHERE {where_sql}\n"
            "GROUP BY 1, 2, 3, 4, 5\n"
            "ORDER BY deposited_usd DESC NULLS LAST;"
        )
    else:
        suggested_sql = (
            "SELECT\n"
            f"  {date_expr} AS period,\n"
            "  blockchain,\n"
            "  event_type,\n"
            "  strategy_address,\n"
            "  COUNT(*) AS event_count,\n"
            "  SUM(amount_usd) AS volume_usd\n"
            f"FROM {table_name}\n"
            f"WHERE {where_sql}\n"
            "GROUP BY 1, 2, 3, 4\n"
            "ORDER BY 1, 2, 3, 4;"
        )
    event_scope = f"event_type='{event_type}'" if event_type else "all protocol event types"
    strategy_scope = f"strategy_symbol='{token_filter}'" if token_filter else "selected strategy scope"
    interpreted_question = (
        "Plan a historical protocol deposit lookup for one address."
        if is_address_deposit_lookup
        else "Plan a protocol events volume/count query."
    )
    suggested_grain = (
        "historical address/project/strategy/token aggregate"
        if is_address_deposit_lookup
        else granularity
    )
    suggested_metrics = (
        ["deposit_event_count", "deposited_usd", "deposited_token_amount", "deposited_underlying_amount"]
        if is_address_deposit_lookup
        else ["event_count", "volume_usd"]
    )
    chart_title = "Protocol deposits by address" if is_address_deposit_lookup else "Protocol event volume"

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": interpreted_question,
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                (
                    "Historical deposit questions should use protocol events with event_type='deposit', not latest holder snapshots."
                    if is_address_deposit_lookup
                    else "Protocol event questions should use the protocol events table, not TVL or holder snapshots."
                ),
            ],
            "important_caveats": _dataset_notes(dataset, "caveats", limit=4),
            "data_access": data_access,
            "preferred_filters": filters,
            "suggested_grain": suggested_grain,
            "suggested_metrics": suggested_metrics,
            "join_notes": [
                (
                    "No join is needed to aggregate documented deposit amounts by address, project, strategy, and token."
                    if is_address_deposit_lookup
                    else "No join is needed for event counts or USD volume by event_type, blockchain, and strategy_address."
                ),
                "Use strategy_address for precise contract-level analysis and raw-log reconciliation.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                "protocol_events_time_volume",
                title=chart_title,
                x=None if is_address_deposit_lookup else "period",
                y="deposited_usd" if is_address_deposit_lookup else "volume_usd",
                series="strategy_symbol" if is_address_deposit_lookup else "event_type",
            ),
            "suggested_chart_title": chart_title,
            "suggested_query_description": (
                f"Aggregates ether.fi protocol events by {suggested_grain}, filtered to {event_scope} and {strategy_scope}. "
                + (f" Address filter: {address_literal}. " if address_literal else "")
                + f"Uses {data_access['selected_data_access']}; see data_access notes for freshness."
            ),
            "suggested_dashboard_description": (
                "Protocol activity view; label selected event_type, strategy filters, and whether the plan uses live_query or the baseline mat view."
            ),
            "suggested_next_step": (
                "Use Dune MCP to create, run, and save the shareable query only after confirming event_type and strategy filters."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def _plan_protocol_holders_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    direct_name = "etherfi_protocol_token_holders"
    defi_name = "etherfi_protocol_token_holders_with_defi"
    direct_dataset, direct_status = _get_query_ready_dataset(
        direct_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    defi_dataset, defi_status = _get_query_ready_dataset(
        defi_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    question_lower = question.lower()
    token_symbols = _extract_known_token_symbols(question)
    address_literals = _extract_address_literals(question)
    holder_address = address_literals[0] if address_literals else None
    token_filter = token_symbols[0] if token_symbols else None
    limit_match = re.search(r"\btop\s+(\d{1,4})\b", question_lower)
    limit_value = int(limit_match.group(1)) if limit_match else 100
    wants_defi = "with_defi" in question_lower or "including defi" in question_lower or "defi exposure" in question_lower
    wants_direct = "direct" in question_lower and not wants_defi
    chosen_dataset = defi_dataset if wants_defi else direct_dataset
    chosen_name = defi_name if wants_defi else direct_name
    table_name = chosen_dataset["table_name"] if chosen_dataset else "<holder_table>"
    balance_column = "token_balance_usd" if wants_defi else "token_balance"
    is_address_lookup = holder_address is not None
    recommended = []
    if wants_defi:
        if defi_dataset:
            recommended.append(_dataset_plan_summary(defi_dataset))
    elif is_address_lookup:
        if direct_dataset:
            recommended.append(_dataset_plan_summary(direct_dataset))
    else:
        if direct_dataset:
            recommended.append(_dataset_plan_summary(direct_dataset))
        if defi_dataset:
            recommended.append(_dataset_plan_summary(defi_dataset))
    ambiguity_notes = []
    clarifying_questions = []
    if not wants_defi and not wants_direct and not is_address_lookup:
        ambiguity_notes.append("Holder prompts are ambiguous between direct holders and holders with tracked DeFi exposure.")
        clarifying_questions.extend(
            [
                "Should indirect DeFi exposure be included?",
                "Should rows attributed to known tracked DeFi contracts be included?",
            ]
        )
    if not token_filter and not is_address_lookup:
        ambiguity_notes.append("No protocol token symbol was detected; choose a token_symbol such as eETH or liquidETH before running.")
    if is_address_lookup and not wants_defi:
        ambiguity_notes.append(
            "This address lookup defaults to direct protocol token holders; ask for DeFi exposure explicitly to use the with_defi table."
        )
        ambiguity_notes.append(
            "The direct holder table does not include USD value fields; return token balances or join pricing separately if USD totals are required."
        )

    where_lines = ["day = (SELECT MAX(day) FROM " + table_name + ")"]
    filters = [{"field": "day", "operator": "=", "value": "latest_snapshot"}]
    if holder_address:
        where_lines.append(f"address = {holder_address}")
        filters.append({"field": "address", "operator": "=", "value": holder_address})
    if token_filter:
        where_lines.append(f"token_symbol = {_quote_sql_string(token_filter)}")
        filters.append({"field": "token_symbol", "operator": "=", "value": token_filter})
    if wants_defi:
        filters.append({"field": "identified_defi_contract", "operator": "review", "value": "decide include/exclude"})
    if is_address_lookup:
        select_lines = [
            "  address,",
            "  blockchain,",
            "  token_symbol,",
            "  token_address,",
            "  SUM(token_balance) AS token_balance,",
            "  SUM(token_balance_raw) AS token_balance_raw,",
        ]
        if wants_defi:
            select_lines.extend(
                [
                    "  token_underlying_symbol,",
                    "  SUM(token_balance_underlying) AS token_balance_underlying,",
                    "  SUM(token_balance_usd) AS token_balance_usd,",
                    "  SUM(token_balance_eth) AS token_balance_eth,",
                    "  identified_defi_contract,",
                ]
            )
            group_by = "GROUP BY 1, 2, 3, 4, 7, 11"
        else:
            group_by = "GROUP BY 1, 2, 3, 4"
        select_lines.extend(
            [
                "  MAX(day) AS snapshot_day,",
                "  MAX(last_updated) AS data_updated_at",
            ]
        )
        suggested_sql = (
            "SELECT\n"
            + "\n".join(select_lines)
            + f"\nFROM {table_name}\n"
            + "WHERE "
            + "\n  AND ".join(where_lines)
            + "\n"
            + group_by
            + "\nORDER BY token_balance DESC NULLS LAST, token_symbol;"
        )
    else:
        suggested_sql = (
            "SELECT\n"
            "  address,\n"
            "  token_symbol,\n"
            f"  SUM({balance_column}) AS holder_balance,\n"
            "  MAX(day) AS snapshot_day\n"
            f"FROM {table_name}\n"
            "WHERE " + "\n  AND ".join(where_lines) + "\n"
            "GROUP BY 1, 2\n"
            "ORDER BY holder_balance DESC\n"
            f"LIMIT {limit_value};"
        )

    caveats = []
    if direct_dataset:
        caveats.extend(_dataset_notes(direct_dataset, "caveats", limit=2))
    if defi_dataset:
        caveats.extend(_dataset_notes(defi_dataset, "caveats", limit=2))
    caveats.append(
        "For DeFi-aware holder plans, identified_defi_contract is a tracked DeFi contract name; "
        "identified_defi_contract IS NOT NULL marks rows attributed to known tracked DeFi contracts, "
        "while null means non-DeFi exposure or untracked routing."
    )
    chart_title = (
        "Ether.fi protocol token balances for address"
        if is_address_lookup
        else f"Top {limit_value} ether.fi protocol token holders"
    )
    holder_scope = (
        "tracked DeFi-aware holder exposure"
        if wants_defi
        else "direct holder balances; resolve direct vs with_defi before sharing"
    )

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": (
                "Plan a latest protocol token holdings lookup for one address."
                if is_address_lookup
                else "Plan a top protocol token holders query."
            ),
            "recommended_datasets": recommended,
            "why_these_datasets": [
                (
                    "Generic ether.fi address balance, wallet holdings, and invested-balance questions should use etherfi_protocol_token_holders as the clean direct-holder snapshot."
                    if is_address_lookup and not wants_defi
                    else "Use etherfi_protocol_token_holders for the clean direct holders view."
                ),
                "Use etherfi_protocol_token_holders_with_defi only when the user wants tracked DeFi-routed exposure and accepts incomplete DeFi coverage.",
            ],
            "ambiguity_notes": ambiguity_notes,
            "clarifying_questions": clarifying_questions,
            "important_caveats": caveats,
            "preferred_filters": filters,
            "suggested_grain": "latest holder snapshot",
            "suggested_metrics": (
                ["token_balance", "token_balance_raw", "token_balance_usd"]
                if is_address_lookup and wants_defi
                else ["token_balance", "token_balance_raw"]
                if is_address_lookup
                else ["holder_balance", "rank"]
            ),
            "join_notes": [
                (
                    "No join is needed for direct token balances by address; join a price source only if a USD value is required."
                    if is_address_lookup and not wants_defi
                    else "Do not join the direct and with-DeFi holder datasets unless the analysis explicitly requires reconciling those two semantics."
                ),
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                "holder_ranking",
                title=chart_title,
                sort=("token_balance descending" if is_address_lookup else "holder_balance descending"),
            ),
            "suggested_chart_title": chart_title,
            "suggested_query_description": (
                (
                    f"Latest current protocol token holdings for address {holder_address} using direct holder balances. "
                    "This is a current snapshot, not historical deposits."
                    if is_address_lookup and not wants_defi
                    else f"Ranks ether.fi protocol token holders using {holder_scope}. "
                    "For the with_defi dataset, identified_defi_contract is a tracked DeFi contract name, not a boolean."
                )
            ),
            "suggested_dashboard_description": (
                "Holder ranking view; label whether results are direct holders only or include tracked DeFi exposure."
            ),
            "suggested_next_step": (
                (
                    f"Use get_protocol_token_holders(address={_quote_sql_string(holder_address)}, execute_live=True) "
                    "for a live catalog answer; add token_symbol or token_address only if the user wants one token."
                )
                if is_address_lookup
                else "Resolve the holder semantics first, then use Dune MCP to create, run, and save the shareable query."
            ),
            "freshness_status": {
                direct_name: direct_status,
                defi_name: defi_status,
            },
            "selected_default_dataset": chosen_name,
            "recommended_tool": "get_protocol_token_holders",
            "recommended_tool_parameters": {
                "address": holder_address,
                "token_symbol": token_filter,
                "include_defi": wants_defi,
                "execute_live": True,
            }
            if is_address_lookup
            else {
                "token_symbol": token_filter,
                "include_defi": wants_defi,
                "execute_live": True,
                "limit": limit_value,
            },
        },
        execute_live,
    )


def _plan_protocol_deposited_balance_ambiguity(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    direct_name = "etherfi_protocol_token_holders"
    events_name = "dune.ether_fi.result_etherfi_protocol_events"
    direct_dataset, direct_status = _get_query_ready_dataset(
        direct_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    events_dataset, events_status = _get_query_ready_dataset(
        events_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    recommended = []
    if direct_dataset:
        recommended.append(_dataset_plan_summary(direct_dataset))
    if events_dataset:
        recommended.append(_dataset_plan_summary(events_dataset))

    address_literals = _extract_address_literals(question)
    address_literal = address_literals[0] if address_literals else "<address>"
    current_holdings_plan = _plan_protocol_holders_query(
        question,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
        execute_live=False,
    )
    historical_deposits_plan = _plan_protocol_events_query(
        question,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
        execute_live=False,
    )
    current_holdings_sql = current_holdings_plan.get("suggested_sql_skeleton")
    historical_deposits_sql = historical_deposits_plan.get("suggested_sql_skeleton")
    suggested_sql_parts = [
        f"-- Current/latest protocol token holdings for this address\n{current_holdings_sql}",
        f"-- Historical deposit flow by this address\n{historical_deposits_sql}",
    ]

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Ambiguous deposited-in wording: current holdings or historical deposits.",
            "recommended_datasets": recommended,
            "why_these_datasets": [
                "Use etherfi_protocol_token_holders for current/latest protocol token holdings by address.",
                "Use etherfi_protocol_events with event_type='deposit' for historical deposit flow by address.",
            ],
            "ambiguity_notes": [
                "The phrase 'have deposited in ether.fi' can mean current balances or historical deposit flow.",
                "Do not route this wording to Cash unless the user explicitly says Cash, card, safe, spend, cashback, borrow, repay, or similar Cash context.",
            ],
            "clarifying_questions": [
                "Do you want current/latest holdings, historical deposits, or both?",
            ],
            "important_caveats": [
                "Current holder snapshots and historical deposits answer different questions.",
                "The direct holder table does not include USD value fields; use token balances or join pricing if USD totals are required.",
                *_dataset_notes(events_dataset or {}, "caveats", limit=2),
            ],
            "preferred_filters": [
                {"field": "address", "operator": "=", "value": address_literal},
                {"field": "day", "operator": "=", "value": "latest_snapshot"},
                {"field": "event_type", "operator": "=", "value": "deposit"},
            ],
            "suggested_grain": "ambiguous: latest holder snapshot or historical deposit aggregate",
            "suggested_metrics": [
                "token_balance",
                "token_balance_raw",
                "deposit_event_count",
                "deposited_usd",
                "deposited_token_amount",
            ],
            "join_notes": [
                "No join is needed for the holder snapshot or protocol deposit aggregate.",
                "Add a price join only if current direct-holder balances need USD valuation.",
            ],
            "suggested_sql_skeleton": "\n\n".join(suggested_sql_parts),
            "suggested_visualization": None,
            "suggested_chart_title": None,
            "suggested_query_description": (
                "Ambiguous address question: current holdings use protocol token holders; historical deposits use protocol events with event_type='deposit'."
            ),
            "suggested_dashboard_description": (
                "Keep current holdings and historical deposit flow as separate views if both are shown."
            ),
            "suggested_next_step": (
                "Ask whether the user wants current holdings or historical deposits; if both are useful, run the two narrow queries separately."
            ),
            "freshness_status": {
                direct_name: direct_status,
                events_name: events_status,
            },
        },
        execute_live,
    )


def _plan_protocol_tvl_timeseries_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_protocol_token_tvl"
    dataset, freshness_status = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    question_lower = question.lower()
    strategy_symbols = _extract_protocol_strategy_symbols(question)
    granularity = "month" if re.search(r"\b(month|monthly)\b", question_lower) else "day"
    if "last year" in question_lower or "last 1 year" in question_lower:
        date_filter = "day >= DATE_ADD('year', -1, CURRENT_DATE)"
        date_value = "last_1_year"
    else:
        date_filter = "-- add a day range before running"
        date_value = "choose_date_range"
    filters = [{"field": "day", "operator": "range", "value": date_value}]
    if strategy_symbols:
        filters.append({"field": "strategy_symbol", "operator": "IN", "value": strategy_symbols})
    symbol_filter = (
        "strategy_symbol IN (" + ", ".join(_quote_sql_string(symbol) for symbol in strategy_symbols) + ")"
        if strategy_symbols
        else "-- add strategy_symbol filter"
    )
    if granularity == "month":
        suggested_sql = (
            "WITH daily_tvl AS (\n"
            "  SELECT\n"
            "    CAST(day AS DATE) AS day,\n"
            "    DATE_TRUNC('month', day) AS month,\n"
            "    strategy_symbol,\n"
            "    SUM(token_supply_usd) AS tvl_usd\n"
            f"  FROM {dataset['table_name']}\n"
            f"  WHERE {date_filter}\n"
            f"    AND {symbol_filter}\n"
            "  GROUP BY 1, 2, 3\n"
            "), ranked_months AS (\n"
            "  SELECT\n"
            "    *,\n"
            "    ROW_NUMBER() OVER (PARTITION BY month, strategy_symbol ORDER BY day DESC) AS rn\n"
            "  FROM daily_tvl\n"
            ")\n"
            "SELECT\n"
            "  month,\n"
            "  day AS month_end_day,\n"
            "  strategy_symbol,\n"
            "  tvl_usd\n"
            "FROM ranked_months\n"
            "WHERE rn = 1\n"
            "ORDER BY month, strategy_symbol;"
        )
    else:
        suggested_sql = (
            "SELECT\n"
            "  CAST(day AS DATE) AS period,\n"
            "  strategy_symbol,\n"
            "  SUM(token_supply_usd) AS tvl_usd\n"
            f"FROM {dataset['table_name']}\n"
            f"WHERE {date_filter}\n"
            f"  AND {symbol_filter}\n"
            "GROUP BY 1, 2\n"
            "ORDER BY 1, 2;"
        )
    symbol_label = _compact_joined(strategy_symbols) if strategy_symbols else "selected strategies"
    chart_title = (
        f"Monthly protocol TVL for {symbol_label}"
        if granularity == "month"
        else f"Daily protocol TVL for {symbol_label}"
    )
    visualization_key = "protocol_tvl_month_end" if granularity == "month" else "protocol_tvl_timeseries"

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan a protocol token TVL time-series query.",
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                "Protocol TVL history should use the protocol token TVL time-series path, not repeated snapshot lookups.",
            ],
            "important_caveats": [
                *_dataset_notes(dataset, "caveats", limit=4),
                "Monthly TVL rows should use the latest available daily snapshot in each month, not summed daily TVL.",
            ],
            "preferred_filters": filters,
            "suggested_grain": granularity,
            "suggested_metrics": ["tvl_usd"],
            "join_notes": [
                "No join is needed for basic protocol token TVL over time.",
                "Use strategy_address when a precise strategy identity is needed instead of symbol matching.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                visualization_key,
                title=chart_title,
                x="month" if granularity == "month" else "period",
                y="tvl_usd",
                series="strategy_symbol",
            ),
            "suggested_chart_title": chart_title,
            "suggested_query_description": (
                f"Shows {granularity} ether.fi protocol token TVL for {symbol_label}. "
                "Monthly rows use the latest available daily snapshot in each month."
                if granularity == "month"
                else f"Shows daily ether.fi protocol token TVL for {symbol_label}."
            ),
            "suggested_dashboard_description": (
                f"Protocol TVL trend for {symbol_label}; label strategy filters and month-end snapshot behavior where applicable."
            ),
            "suggested_next_step": (
                "Use Dune MCP to create, run, and save the query; use Dune MCP visualization tools for the chart or dashboard."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def _plan_cash_balances_category_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    dataset, freshness_status = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    category_mapping = _CASH_HOLDINGS_CATEGORY_PRESETS["cash_balance_buckets"]
    case_lines = [
        f"      WHEN token_symbol = {_quote_sql_string(symbol)} THEN {_quote_sql_string(label)}"
        for symbol, label in category_mapping.items()
    ]
    suggested_sql = (
        "WITH daily_balances AS (\n"
        "  SELECT\n"
        "    CAST(day AS DATE) AS day,\n"
        "    DATE_TRUNC('month', day) AS month,\n"
        "    CASE\n"
        + "\n".join(case_lines)
        + "\n"
        "    END AS category,\n"
        "    address,\n"
        "    SUM(COALESCE(token_balance_usd, 0)) AS balance_usd\n"
        f"  FROM {dataset['table_name']}\n"
        "  WHERE address_name = 'CASH'\n"
        "    AND day >= DATE_ADD('year', -1, CURRENT_DATE)\n"
        "    AND token_symbol IN ('liquidUSD', 'liquidETH', 'liquidBTC', 'USDC', 'USDC.e')\n"
        "  GROUP BY 1, 2, 3, 4\n"
        "), category_totals AS (\n"
        "  SELECT\n"
        "    day,\n"
        "    month,\n"
        "    category,\n"
        "    COUNT(DISTINCT address) AS holder_count,\n"
        "    SUM(balance_usd) AS total_usd\n"
        "  FROM daily_balances\n"
        "  WHERE category IS NOT NULL\n"
        "  GROUP BY 1, 2, 3\n"
        "), ranked_months AS (\n"
        "  SELECT\n"
        "    *,\n"
        "    ROW_NUMBER() OVER (PARTITION BY month, category ORDER BY day DESC) AS rn\n"
        "  FROM category_totals\n"
        ")\n"
        "SELECT\n"
        "  month,\n"
        "  day AS month_end_day,\n"
        "  category,\n"
        "  holder_count,\n"
        "  total_usd\n"
        "FROM ranked_months\n"
        "WHERE rn = 1\n"
        "ORDER BY month, category;"
    )
    chart_title = "Monthly Cash balances by category"

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan a dashboard-ready Cash balance category time-series query.",
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                "Cash balance category history should use the AUM balance table filtered to address_name='CASH', not Cash event activity rows.",
            ],
            "important_caveats": [
                "This is based on AUM balances classified with `address_name = 'CASH'`.",
                "Monthly rows use the latest available daily snapshot in each calendar month.",
                "The category mapping is intentionally narrow: liquidUSD, liquidETH, liquidBTC, and stables from USDC/USDC.e.",
            ],
            "preferred_filters": [
                {"field": "address_name", "operator": "=", "value": "CASH"},
                {"field": "day", "operator": "range", "value": "last_1_year"},
                {"field": "category_preset", "operator": "=", "value": "cash_balance_buckets"},
            ],
            "suggested_grain": "month",
            "suggested_metrics": ["total_usd", "holder_count"],
            "join_notes": [
                "No join is needed for the standard Cash balance category dashboard view.",
                "Keep the category mapping explicit so teammates can review which token symbols are included.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                "cash_balances_category_timeseries",
                title=chart_title,
                x="month",
                y="total_usd",
                series="category",
            ),
            "suggested_chart_title": chart_title,
            "suggested_query_description": (
                "Month-end ether.fi Cash balances grouped into the cash_balance_buckets category preset. "
                "Monthly values use the latest available daily Cash balance snapshot."
            ),
            "suggested_dashboard_description": (
                "Cash balance composition over time by category; categories are liquidUSD, liquidETH, liquidBTC, and stables."
            ),
            "suggested_next_step": (
                "Use Dune MCP to create, run, and save the query; use Dune MCP dashboard tools for the shareable dashboard widget."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def _plan_cash_safe_balance_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    dataset, freshness_status = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    address_literals = _extract_address_literals(question)
    address_literal = address_literals[0] if address_literals else "<cash_safe_address>"
    table_name = dataset["table_name"]
    suggested_sql = (
        "SELECT\n"
        "  address,\n"
        "  blockchain,\n"
        "  token_symbol,\n"
        "  token_underlying_symbol,\n"
        "  SUM(token_balance) AS token_balance,\n"
        "  SUM(token_balance_underlying) AS token_balance_underlying,\n"
        "  SUM(token_balance_usd) AS token_balance_usd,\n"
        "  SUM(token_balance_eth) AS token_balance_eth,\n"
        "  MAX(day) AS latest_balance_day,\n"
        "  MAX(last_updated) AS data_updated_at\n"
        f"FROM {table_name}\n"
        f"WHERE address = {address_literal}\n"
        "  AND address_name = 'CASH'\n"
        f"  AND day = (SELECT MAX(day) FROM {table_name} WHERE address = {address_literal} AND address_name = 'CASH')\n"
        "GROUP BY 1, 2, 3, 4\n"
        "ORDER BY token_balance_usd DESC NULLS LAST, token_symbol;"
    )

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan a latest ether.fi Cash safe balance lookup for one address.",
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                "Explicit Cash safe/card balance questions should use the AUM balance table filtered to address_name='CASH'.",
            ],
            "important_caveats": [
                "This route is only for explicit ether.fi Cash safe/card balance wording.",
                "The AUM balance table provides balance-state snapshots, not historical Cash spend or cashback activity.",
                "If public Cash-safe identity validation is required, use check_cash_safe_address or the Cash-safe profile tool with validation enabled.",
                *_dataset_notes(dataset, "caveats", limit=2),
            ],
            "preferred_filters": [
                {"field": "address", "operator": "=", "value": address_literal},
                {"field": "address_name", "operator": "=", "value": "CASH"},
                {"field": "day", "operator": "=", "value": "latest_snapshot"},
            ],
            "suggested_grain": "latest Cash safe/token/blockchain snapshot",
            "suggested_metrics": [
                "token_balance",
                "token_balance_underlying",
                "token_balance_usd",
                "token_balance_eth",
            ],
            "join_notes": [
                "No join is needed for latest Cash safe balances by token and chain.",
                "Use Cash events separately when the question is about spend, cashback, borrow, repay, or liquidation activity.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                "holder_ranking",
                title="Cash safe balance by token",
                sort="token_balance_usd descending",
            ),
            "suggested_chart_title": "Cash safe balance by token",
            "suggested_query_description": (
                f"Latest ether.fi Cash balance snapshot for safe/address {address_literal}, filtered to address_name='CASH'."
            ),
            "suggested_dashboard_description": (
                "Single Cash safe balance view by token and chain; label the address_name='CASH' filter clearly."
            ),
            "suggested_next_step": (
                "Use the Cash-safe profile tool for a live profile, or Dune MCP to create this shareable query."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def _plan_token_price_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    question_lower = question.lower()
    wants_minute = re.search(r"\b(minute|minute-level|intraday)\b", question_lower) is not None
    dataset_name = (
        "dune.ether_fi.result_tokens_prices_enriched_minute"
        if wants_minute
        else "dune.ether_fi.result_tokens_prices_enriched_daily"
    )
    dataset, freshness_status = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    token_symbols = _extract_known_token_symbols(question)
    token_filter = token_symbols[0] if token_symbols else None
    time_column = "minute" if wants_minute else "day"
    grain = "minute" if wants_minute else "day"
    filters = [{"field": time_column, "operator": "range", "value": "choose_price_window"}]
    if token_filter:
        filters.append({"field": "token_symbol", "operator": "=", "value": token_filter})
    where_lines = [f"{time_column} >= DATE_ADD('month', -3, CURRENT_TIMESTAMP)"]
    if token_filter:
        where_lines.append(f"token_symbol = {_quote_sql_string(token_filter)}")
    else:
        where_lines.append("-- add token_symbol or token_address before running")
    suggested_sql = (
        "SELECT\n"
        f"  {time_column} AS period,\n"
        "  blockchain,\n"
        "  token_symbol,\n"
        "  token_address,\n"
        "  COALESCE(token_usd, token_usd_rate) AS price_usd,\n"
        "  token_usd,\n"
        "  token_usd_rate,\n"
        "  last_updated\n"
        f"FROM {dataset['table_name']}\n"
        "WHERE " + "\n  AND ".join(where_lines) + "\n"
        "ORDER BY period, blockchain, token_symbol;"
    )
    title_symbol = token_filter or "selected token"
    chart_title = f"{'Minute' if wants_minute else 'Daily'} enriched price for {title_symbol}"
    caveats = _dataset_notes(dataset, "caveats", limit=3)
    if not wants_minute:
        caveats.append("Daily enriched prices are the safer default for broad historical and shareable dashboarding.")

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan an ether.fi enriched token price query.",
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                (
                    "Minute enriched prices are selected only because minute-level resolution was requested; coverage is intentionally partial."
                    if wants_minute
                    else "Daily enriched prices are the safer default for shareable historical price analysis and avoid overclaiming minute coverage."
                )
            ],
            "important_caveats": caveats,
            "preferred_filters": filters,
            "suggested_grain": grain,
            "suggested_metrics": ["price_usd", "token_usd", "token_usd_rate"],
            "join_notes": [
                "Prefer COALESCE(token_usd, token_usd_rate) for usable USD price, while preserving direct-vs-enriched semantics.",
                "Use token_address when symbol ambiguity matters.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                "price_timeseries",
                title=chart_title,
                x="period",
                y="price_usd",
                series="token_symbol",
            ),
            "suggested_chart_title": chart_title,
            "suggested_query_description": (
                f"{grain.capitalize()} enriched token price plan using COALESCE(token_usd, token_usd_rate). "
                "Do not describe token_usd_rate as a direct raw USD price feed."
            ),
            "suggested_dashboard_description": (
                "Enriched token price view; label direct price vs derived/enriched price semantics and coverage caveats."
            ),
            "suggested_next_step": (
                "Use Dune MCP to create, run, and save the query; use Dune Skills if the DuneSQL needs price-coverage optimization."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def _extract_known_aum_protocol_project(question: str) -> str | None:
    question_lower = question.lower()
    for protocol_lower, protocol in _KNOWN_AUM_PROTOCOL_PROJECTS.items():
        if re.search(rf"\b{re.escape(protocol_lower)}\b", question_lower):
            return protocol
    return None


def _plan_product_protocol_deployment_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    dataset, freshness_status = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    parent_symbols = _extract_known_token_symbols(question)
    parent_symbol = parent_symbols[0] if parent_symbols else None
    token_project = _extract_known_aum_protocol_project(question)
    product_filter = (
        f"parent_symbol = {_quote_sql_string(parent_symbol)}"
        if parent_symbol
        else "-- add parent_symbol, for example 'liquidUSD'"
    )
    protocol_filter_line = (
        f"    AND LOWER(token_project) = LOWER({_quote_sql_string(token_project)})\n"
        if token_project
        else ""
    )
    filters = [{"field": "day", "operator": "=", "value": "latest_available"}]
    if parent_symbol:
        filters.append({"field": "parent_symbol", "operator": "=", "value": parent_symbol})
    if token_project:
        filters.append({"field": "token_project", "operator": "=", "value": token_project})

    suggested_sql = (
        "WITH latest_day AS (\n"
        "  SELECT MAX(day) AS day\n"
        f"  FROM {dataset['table_name']}\n"
        f"  WHERE {product_filter}\n"
        "), scoped_balances AS (\n"
        "  SELECT\n"
        "    day,\n"
        "    parent_symbol,\n"
        "    token_project,\n"
        "    secondary_trait,\n"
        "    blockchain,\n"
        "    token_symbol,\n"
        "    token_underlying_symbol,\n"
        "    token_balance_usd,\n"
        "    token_balance_eth,\n"
        "    token_balance_underlying,\n"
        "    CASE\n"
        "      WHEN LOWER(token_project) IN ('aave', 'morpho')\n"
        "       AND LOWER(secondary_trait) = 'borrow'\n"
        "        THEN -COALESCE(token_balance_usd, 0)\n"
        "      ELSE COALESCE(token_balance_usd, 0)\n"
        "    END AS net_token_balance_usd,\n"
        "    CASE\n"
        "      WHEN LOWER(token_project) IN ('aave', 'morpho')\n"
        "       AND LOWER(secondary_trait) = 'borrow'\n"
        "        THEN -COALESCE(token_balance_underlying, 0)\n"
        "      ELSE COALESCE(token_balance_underlying, 0)\n"
        "    END AS net_token_balance_underlying,\n"
        "    CASE\n"
        "      WHEN LOWER(token_project) IN ('aave', 'morpho')\n"
        "       AND LOWER(secondary_trait) = 'borrow'\n"
        "        THEN -COALESCE(token_balance_eth, 0)\n"
        "      ELSE COALESCE(token_balance_eth, 0)\n"
        "    END AS net_token_balance_eth\n"
        f"  FROM {dataset['table_name']}\n"
        "  WHERE day = (SELECT day FROM latest_day)\n"
        f"    AND {product_filter}\n"
        f"{protocol_filter_line}"
        "    AND COALESCE(token_balance_usd, 0) > 0\n"
        ")\n"
        "SELECT\n"
        "  MAX(day) AS latest_day,\n"
        "  parent_symbol,\n"
        "  token_project,\n"
        "  blockchain,\n"
        "  token_symbol,\n"
        "  token_underlying_symbol,\n"
        "  SUM(COALESCE(token_balance_usd, 0)) AS raw_token_balance_usd,\n"
        "  SUM(net_token_balance_usd) AS net_token_balance_usd,\n"
        "  SUM(net_token_balance_underlying) AS net_token_balance_underlying,\n"
        "  SUM(net_token_balance_eth) AS net_token_balance_eth\n"
        "FROM scoped_balances\n"
        "GROUP BY 2, 3, 4, 5, 6\n"
        "ORDER BY ABS(SUM(net_token_balance_usd)) DESC NULLS LAST;"
    )
    title_parts = [parent_symbol or "selected product"]
    if token_project:
        title_parts.append(f"in {token_project}")
    chart_title = f"Tracked net deployment for {' '.join(title_parts)}"

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan a product protocol-deployment footprint query.",
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                "Product deployment questions should use the AUM balance-state table filtered by parent_symbol and token_project, not canonical protocol TVL.",
            ],
            "important_caveats": [
                *_dataset_notes(dataset, "caveats", limit=3),
                "token_project identifies the deployed protocol for protocol-deployment questions such as Aave or Morpho.",
                "For Aave and Morpho, borrow rows are stored as positive raw balances and must be negated for net deployment exposure.",
                "AUM deployment coverage is tracked and partial, so do not describe this as canonical product TVL.",
            ],
            "preferred_filters": filters,
            "suggested_grain": "latest product/protocol/token/chain snapshot",
            "suggested_metrics": [
                "net_token_balance_usd",
                "raw_token_balance_usd",
                "net_token_balance_underlying",
                "net_token_balance_eth",
            ],
            "join_notes": [
                "No join is needed for protocol-deployment footprint analysis.",
                "Use token_project for protocol filters; address_name is balance-side classification context and can be too coarse for protocol filtering.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                "product_protocol_deployment",
                title=chart_title,
                x="token_project",
                y="net_token_balance_usd",
                series="blockchain",
            ),
            "suggested_chart_title": chart_title,
            "suggested_query_description": (
                "Latest tracked product deployment footprint filtered by parent_symbol and token_project. "
                "Aave and Morpho rows use net lending exposure by negating borrow-side secondary_trait rows."
            ),
            "suggested_dashboard_description": (
                "Tracked product deployment by protocol; label net lending treatment for Aave/Morpho and partial AUM coverage."
            ),
            "suggested_next_step": (
                "Use Dune MCP to create and run the SQL, then summarize net_token_balance_usd for the requested protocol."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def _plan_explicit_aum_managed_address_query(question: str, datasets, freshness_registry=None, now=None, execute_live=False) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    dataset, freshness_status = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return _finalize_etherfi_query_plan(
            {
                **freshness_status,
                "interpreted_question": question,
                "recommended_datasets": [],
            },
            execute_live,
        )

    address_literals = _extract_address_literals(question)
    address_literal = address_literals[0] if address_literals else "<managed_address>"
    table_name = dataset["table_name"]
    date_column = dataset.get("date_column", "day")
    address_column = dataset.get("address_column", "address")
    suggested_sql = (
        "SELECT\n"
        f"  {date_column},\n"
        "  blockchain,\n"
        f"  {address_column},\n"
        "  address_name,\n"
        "  token_address,\n"
        "  token_symbol,\n"
        "  token_type,\n"
        "  token_project,\n"
        "  token_balance,\n"
        "  token_balance_underlying,\n"
        "  token_underlying_symbol,\n"
        "  token_balance_usd,\n"
        "  token_balance_eth,\n"
        "  last_updated\n"
        f"FROM {table_name}\n"
        f"WHERE {address_column} = {address_literal}\n"
        f"  AND {date_column} = (SELECT MAX({date_column}) FROM {table_name} WHERE {address_column} = {address_literal})\n"
        "ORDER BY token_balance_usd DESC NULLS LAST, token_symbol;"
    )

    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan an explicit AUM/managed-address balance lookup.",
            "recommended_datasets": [_dataset_plan_summary(dataset)],
            "why_these_datasets": [
                "The prompt explicitly uses AUM, managed, internal, treasury, address registry, or protocol-controlled wording.",
                "AUM is for ether.fi-managed/internal/protocol-controlled addresses and tracked product deployment balances, not generic user wallet holdings.",
            ],
            "important_caveats": [
                "Do not use this AUM route for generic user wallet prompts such as 'how much does this address have in ether.fi?'; use etherfi_protocol_token_holders instead.",
                "AUM sums from this table are tracked deployment balances and are not canonical protocol token TVL.",
                *_dataset_notes(dataset, "caveats", limit=2),
            ],
            "preferred_filters": [
                {"field": address_column, "operator": "=", "value": address_literal},
                {"field": date_column, "operator": "=", "value": "latest_snapshot"},
            ],
            "suggested_grain": "latest managed-address/token/blockchain snapshot",
            "suggested_metrics": [
                "token_balance",
                "token_balance_underlying",
                "token_balance_usd",
                "token_balance_eth",
            ],
            "join_notes": [
                "No join is needed for an explicit managed-address AUM balance lookup.",
                "Use the address registry only if the task is to classify why the address belongs in AUM scope.",
            ],
            "suggested_sql_skeleton": suggested_sql,
            "suggested_visualization": _planner_visualization(
                "holder_ranking",
                title="Managed address AUM balances by token",
                sort="token_balance_usd descending",
            ),
            "suggested_chart_title": "Managed address AUM balances by token",
            "suggested_query_description": (
                f"Latest tracked AUM balances for explicit managed/internal address {address_literal}. "
                "This is not the default route for generic user wallet holdings."
            ),
            "suggested_dashboard_description": (
                "Managed/internal address AUM view; label that the address must be in ether.fi-managed or protocol-controlled scope."
            ),
            "suggested_next_step": (
                "Confirm the address is intended as ether.fi-managed/internal scope before creating or running a Dune query."
            ),
            "freshness_status": freshness_status,
        },
        execute_live,
    )


def plan_etherfi_query(
    question: str,
    execute_live: bool = False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    if not isinstance(question, str) or not question.strip():
        return _plan_error(question, execute_live=execute_live)

    datasets = datasets or load_datasets()
    question_value = question.strip()
    question_lower = question_value.lower()

    if "price" in question_lower or "prices" in question_lower:
        return _plan_token_price_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if (
        "cash" in question_lower
        and re.search(r"\b(balance|balances|holding|holdings)\b", question_lower)
        and re.search(r"\b(category|categories|bucket|buckets)\b", question_lower)
    ):
        return _plan_cash_balances_category_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if _question_is_cash_safe_validation(question_lower):
        return _plan_cash_safe_validation_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if _question_is_cash_safe_address_balance(question_lower):
        return _plan_cash_safe_balance_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if _question_is_explicit_aum_managed_address(question_lower):
        return _plan_explicit_aum_managed_address_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if _question_is_ambiguous_protocol_deposited_balance(question_lower):
        return _plan_protocol_deposited_balance_ambiguity(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if _question_is_historical_protocol_deposit(question_lower):
        return _plan_protocol_events_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if _question_is_generic_protocol_address_holdings(question_lower):
        return _plan_protocol_holders_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if (
        _extract_known_token_symbols(question_value)
        and (
            _extract_known_aum_protocol_project(question_value)
            or "token_project" in question_lower
            or re.search(r"\b(in|into|deployed|deployment|held|hold|holds)\b", question_lower)
        )
    ):
        return _plan_product_protocol_deployment_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if (
        "cash" in question_lower
        and re.search(r"\b(event|events|spend|spends|spending|volume|borrow|repay|cashback|liquidation)\b", question_lower)
        and not re.search(r"\b(balance|balances|holding|holdings)\b", question_lower)
    ):
        return _plan_cash_events_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if (
        re.search(r"\b(protocol|strategy|deposit|deposits|withdrawal|withdrawals)\b", question_lower)
        and re.search(r"\b(event|events|activity|deposit|deposits|withdrawal|withdrawals|volume)\b", question_lower)
        and "cash" not in question_lower
    ):
        return _plan_protocol_events_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if "holder" in question_lower or "holders" in question_lower:
        return _plan_protocol_holders_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    if "tvl" in question_lower and re.search(r"\b(month|monthly|day|daily|history|over time|last year|last 1 year)\b", question_lower):
        return _plan_protocol_tvl_timeseries_query(
            question_value,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
            execute_live=execute_live,
        )

    matches = search_datasets(
        question_value,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )[:3]
    return _finalize_etherfi_query_plan(
        {
            "interpreted_question": "Plan an ether.fi analysis, but the route is ambiguous.",
            "recommended_datasets": [
                _dataset_plan_summary(match)
                for match in matches
                if match.get("query_ready")
            ],
            "why_these_datasets": [
                "The question did not match one of the narrow planner routes; these are metadata search candidates only."
            ],
            "ambiguity_notes": [
                "Clarify whether this is a live answer, shareable query, chart/dashboard, snapshot, time series, ranking, or population aggregate."
            ],
            "important_caveats": [],
            "preferred_filters": [],
            "suggested_grain": None,
            "suggested_metrics": [],
            "join_notes": [],
            "suggested_sql_skeleton": None,
            "suggested_visualization": None,
            "suggested_chart_title": None,
            "suggested_query_description": None,
            "suggested_dashboard_description": None,
            "suggested_next_step": (
                "Use etherfi-catalog dataset/tool discovery to resolve semantics first; then use Dune MCP only if a shareable query, chart, or dashboard is needed."
            ),
        },
        execute_live,
    )


def _get_assets_under_management_balances_plan(
    address,
    as_of_date=None,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "address": address,
            "as_of_date": as_of_date,
        }
    freshness_status = dataset_error
    try:
        address_literal = _normalize_address_literal(address)
    except ValueError:
        address_literal = str(address)
    table_name = dataset["table_name"]
    date_column = dataset["date_column"]
    address_column = dataset["address_column"]
    where_lines = [f"{address_column} = {address_literal}"]

    if as_of_date:
        where_lines.append(f"CAST({date_column} AS DATE) = CAST('{as_of_date}' AS DATE)")
    else:
        where_lines.append(
            f"{date_column} = ("
            f"SELECT MAX({date_column}) FROM {table_name} WHERE {address_column} = {address_literal}"
            f")"
        )

    suggested_sql = (
        "SELECT\n"
        "  day,\n"
        "  blockchain,\n"
        "  address,\n"
        "  address_name,\n"
        "  token_address,\n"
        "  token_symbol,\n"
        "  token_type,\n"
        "  token_project,\n"
        "  token_balance,\n"
        "  token_balance_underlying,\n"
        "  token_underlying_symbol,\n"
        "  token_balance_usd,\n"
        "  token_balance_eth,\n"
        "  last_updated\n"
        f"FROM {table_name}\n"
        "WHERE " + "\n  AND ".join(where_lines) + "\n"
        "ORDER BY token_balance_usd DESC NULLS LAST, token_symbol;"
    )

    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "address": address,
        "as_of_date": as_of_date,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "address_column": address_column,
        "date_column": date_column,
        "balance_columns": dataset.get("balance_columns", []),
        "token_columns": dataset.get("token_columns", []),
        "query_patterns": dataset.get("query_patterns", []),
        "freshness_status": freshness_status,
        "suggested_sql": suggested_sql,
    }


def _build_cash_safe_address_check_summary(rows: list[dict], address: str, blockchain: str | None = None) -> dict:
    data_rows = [
        row
        for row in rows
        if row.get("address") not in (None, "") or row.get("blockchain") not in (None, "")
    ]
    blockchains = sorted(
        {
            str(row.get("blockchain"))
            for row in data_rows
            if row.get("blockchain") not in (None, "")
        }
    )
    last_updated_values = [
        row.get("last_updated")
        for row in data_rows
        if row.get("last_updated") not in (None, "")
    ]
    return {
        "address": address,
        "blockchain": blockchain,
        "is_cash_safe": bool(data_rows),
        "matching_row_count": len(data_rows),
        "matching_blockchains": blockchains,
        "last_updated": max(last_updated_values) if last_updated_values else None,
        "message": (
            "Address is listed in the public ether.fi Cash-safe registry."
            if data_rows
            else "Address was not found in the public ether.fi Cash-safe registry for the applied filters."
        ),
    }


def _build_cash_safe_address_not_executed_summary(address: str, blockchain: str | None = None) -> dict:
    return {
        "address": address,
        "blockchain": blockchain,
        "is_cash_safe": None,
        "check_status": "unknown_not_executed",
        "matching_row_count": None,
        "matching_blockchains": [],
        "last_updated": None,
        "message": (
            "Live execution is disabled, so this response only shows how to check the address. "
            "Run with `execute_live=true` to verify whether the address is an ether.fi Cash safe."
        ),
    }


def _compact_cash_safe_address_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "blockchain": row.get("blockchain"),
            "address": row.get("address"),
            "last_updated": row.get("last_updated"),
        }
        for row in rows
        if row.get("address") not in (None, "") or row.get("blockchain") not in (None, "")
    ]


def _get_cash_safe_address_check_plan(
    address,
    blockchain=None,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = CASH_SAFE_ADDRESSES_DATASET_NAME
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "address": address,
            "blockchain": blockchain,
        }
    freshness_status = dataset_error

    try:
        address_literal = _normalize_address_literal(address)
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain").lower()
            if blockchain
            else None
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "address": address,
            "blockchain": blockchain,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    where_lines = [f"address = {address_literal}"]
    filters_applied = [{"field": "address", "operator": "=", "value": address_literal}]
    if blockchain_value:
        where_lines.append(f"blockchain = {_quote_sql_string(blockchain_value)}")
        filters_applied.append({"field": "blockchain", "operator": "=", "value": blockchain_value})

    suggested_sql = (
        "SELECT\n"
        "  blockchain,\n"
        "  address,\n"
        "  last_updated\n"
        f"FROM {table_name}\n"
        "WHERE "
        + "\n  AND ".join(where_lines)
        + "\n"
        "ORDER BY blockchain;"
    )

    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "address": address_literal,
        "blockchain": blockchain_value,
        "query_ready": True,
        "question_class": "single-entity lookup",
        "freshness_status": freshness_status,
        "chosen_dataset": {
            "name": dataset_name,
            "table_name": table_name,
            "why_chosen": (
                "This public registry is the canonical source for Cash-safe validation and avoids private/internal protocol address tables."
            ),
        },
        "filters_applied": filters_applied,
        "aggregate_scope": (
            "one address on one blockchain"
            if blockchain_value
            else "one address across all blockchains in the public Cash-safe registry"
        ),
        "expected_output_fields": ["blockchain", "address", "last_updated"],
        "caveats": [
            "This confirms public Cash-safe registry membership only; it does not return balances or activity.",
            "Use Cash events for activity and AUM Cash filters for balance snapshots.",
        ],
        "suggested_sql": suggested_sql,
    }


def check_cash_safe_address(
    address,
    blockchain=None,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_cash_safe_address_check_plan(
        address=address,
        blockchain=blockchain,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        summary = _build_cash_safe_address_not_executed_summary(
            address=plan.get("address", address),
            blockchain=plan.get("blockchain", blockchain),
        )
        return {
            **plan,
            "execute_live": False,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": summary,
        }
    summary = _build_cash_safe_address_check_summary(
        [],
        address=plan.get("address", address),
        blockchain=plan.get("blockchain", blockchain),
    )
    if plan.get("error"):
        return {
            **plan,
            "execute_live": True,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": summary,
        }

    try:
        raw_rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "execute_live": True,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "raw_rows": [],
            "summary": summary,
        }

    rows = _compact_cash_safe_address_rows(raw_rows)
    summary = _build_cash_safe_address_check_summary(
        rows,
        address=plan["address"],
        blockchain=plan.get("blockchain"),
    )
    return {
        **plan,
        "execute_live": True,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "raw_row_count": len(raw_rows),
        "raw_rows": raw_rows,
        "summary": summary,
    }


def _build_cash_events_summary(rows: list[dict], event_type=None, user_safe=None, start_date=None, end_date=None) -> dict:
    if not rows:
        return {
            "row_count": 0,
            "event_type": event_type,
            "user_safe": user_safe,
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "latest_block_time": None,
            "total_token_amount": 0.0,
            "total_token_amount_usd": 0.0,
            "totals_by_token": [],
            "totals_by_blockchain": [],
            "totals_by_event_type": [],
        }

    block_dates = [row.get("block_date") for row in rows if row.get("block_date") is not None]
    latest_block_time = max(row.get("block_time") for row in rows if row.get("block_time") is not None)
    total_token_amount_usd = sum(_to_number(row.get("token_amount_usd")) for row in rows)
    token_symbols = {row.get("token_symbol") for row in rows if row.get("token_symbol") not in (None, "")}
    total_token_amount = sum(_to_number(row.get("token_amount")) for row in rows) if len(token_symbols) <= 1 else None

    totals_by_token: dict[str, dict] = {}
    totals_by_blockchain: dict[str, dict] = {}
    totals_by_event_type: dict[str, dict] = {}

    for row in rows:
        token_symbol = row.get("token_symbol")
        token_group = totals_by_token.setdefault(
            token_symbol,
            {
                "token_symbol": token_symbol,
                "total_token_amount": 0.0,
                "total_token_amount_usd": 0.0,
                "row_count": 0,
            },
        )
        token_group["total_token_amount"] += _to_number(row.get("token_amount"))
        token_group["total_token_amount_usd"] += _to_number(row.get("token_amount_usd"))
        token_group["row_count"] += 1

        blockchain = row.get("blockchain")
        chain_group = totals_by_blockchain.setdefault(
            blockchain,
            {
                "blockchain": blockchain,
                "total_token_amount_usd": 0.0,
                "row_count": 0,
            },
        )
        chain_group["total_token_amount_usd"] += _to_number(row.get("token_amount_usd"))
        chain_group["row_count"] += 1

        row_event_type = row.get("event_type")
        event_group = totals_by_event_type.setdefault(
            row_event_type,
            {
                "event_type": row_event_type,
                "total_token_amount_usd": 0.0,
                "row_count": 0,
            },
        )
        event_group["total_token_amount_usd"] += _to_number(row.get("token_amount_usd"))
        event_group["row_count"] += 1

    return {
        "row_count": len(rows),
        "event_type": event_type,
        "user_safe": user_safe,
        "date_range": {
            "start_date": start_date or (min(block_dates) if block_dates else None),
            "end_date": end_date or (max(block_dates) if block_dates else None),
        },
        "latest_block_time": latest_block_time,
        "total_token_amount": total_token_amount,
        "total_token_amount_usd": total_token_amount_usd,
        "totals_by_token": sorted(
            totals_by_token.values(),
            key=lambda row: row["total_token_amount_usd"],
            reverse=True,
        ),
        "totals_by_blockchain": sorted(
            totals_by_blockchain.values(),
            key=lambda row: row["total_token_amount_usd"],
            reverse=True,
        ),
        "totals_by_event_type": sorted(
            totals_by_event_type.values(),
            key=lambda row: row["total_token_amount_usd"],
            reverse=True,
        ),
    }


def _build_cash_events_summary_from_queries(
    overview_rows: list[dict],
    totals_by_token_rows: list[dict],
    totals_by_blockchain_rows: list[dict],
    totals_by_event_type_rows: list[dict],
    event_type=None,
    user_safe=None,
    start_date=None,
    end_date=None,
) -> dict:
    overview = overview_rows[0] if overview_rows else {}
    return {
        "row_count": int(_to_number(overview.get("event_count"))),
        "event_count": int(_to_number(overview.get("event_count"))),
        "event_type": event_type,
        "user_safe": user_safe,
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "latest_block_time": overview.get("latest_event_time"),
        "latest_event_time": overview.get("latest_event_time"),
        "total_token_amount": _to_number(overview.get("total_token_amount")) if overview.get("single_token_symbol") else None,
        "total_token_amount_usd": _to_number(overview.get("total_token_amount_usd")),
        "totals_by_token": [
            {
                "token_symbol": row.get("token_symbol"),
                "total_token_amount": _to_number(row.get("total_token_amount")),
                "total_token_amount_usd": _to_number(row.get("total_token_amount_usd")),
                "row_count": int(_to_number(row.get("event_count"))),
            }
            for row in totals_by_token_rows
        ],
        "totals_by_blockchain": [
            {
                "blockchain": row.get("blockchain"),
                "total_token_amount_usd": _to_number(row.get("total_token_amount_usd")),
                "row_count": int(_to_number(row.get("event_count"))),
            }
            for row in totals_by_blockchain_rows
        ],
        "totals_by_event_type": [
            {
                "event_type": row.get("event_type"),
                "total_token_amount_usd": _to_number(row.get("total_token_amount_usd")),
                "row_count": int(_to_number(row.get("event_count"))),
            }
            for row in totals_by_event_type_rows
        ],
    }


def _build_cash_events_where_lines(event_type=None, user_safe_literal=None, start_date=None, end_date=None) -> list[str]:
    where_lines: list[str] = []
    if event_type:
        where_lines.append(f"event_type = '{event_type}'")
    if user_safe_literal:
        where_lines.append(f"user_safe = {user_safe_literal}")
    if start_date:
        where_lines.append(f"block_date >= CAST('{start_date}' AS DATE)")
    if end_date:
        where_lines.append(f"block_date <= CAST('{end_date}' AS DATE)")
    return where_lines


def _format_where_clause(where_lines: list[str]) -> str:
    return (("WHERE " + "\n  AND ".join(where_lines) + "\n") if where_lines else "")


def _execute_cash_events_summary_queries(table_name: str, where_lines: list[str], include_event_type_breakdown: bool) -> dict:
    where_clause = _format_where_clause(where_lines)
    overview_sql = (
        "SELECT\n"
        "  COUNT(*) AS event_count,\n"
        "  MAX(block_time) AS latest_event_time,\n"
        "  SUM(token_amount_usd) AS total_token_amount_usd,\n"
        "  CASE WHEN COUNT(DISTINCT token_symbol) = 1 THEN MAX(token_symbol) ELSE NULL END AS single_token_symbol,\n"
        "  CASE WHEN COUNT(DISTINCT token_symbol) = 1 THEN SUM(token_amount) ELSE NULL END AS total_token_amount\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
    )
    totals_by_token_sql = (
        "SELECT\n"
        "  token_symbol,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(token_amount) AS total_token_amount,\n"
        "  SUM(token_amount_usd) AS total_token_amount_usd\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
        "GROUP BY 1\n"
        "ORDER BY total_token_amount_usd DESC NULLS LAST, token_symbol\n"
        "LIMIT 20;"
    )
    totals_by_blockchain_sql = (
        "SELECT\n"
        "  blockchain,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(token_amount_usd) AS total_token_amount_usd\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
        "GROUP BY 1\n"
        "ORDER BY total_token_amount_usd DESC NULLS LAST, blockchain\n"
        "LIMIT 20;"
    )
    totals_by_event_type_sql = (
        "SELECT\n"
        "  event_type,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(token_amount_usd) AS total_token_amount_usd\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
        "GROUP BY 1\n"
        "ORDER BY total_token_amount_usd DESC NULLS LAST, event_type\n"
        "LIMIT 20;"
    )
    return {
        "overview_rows": _execute_dune_sql(overview_sql),
        "totals_by_token_rows": _execute_dune_sql(totals_by_token_sql),
        "totals_by_blockchain_rows": _execute_dune_sql(totals_by_blockchain_sql),
        "totals_by_event_type_rows": _execute_dune_sql(totals_by_event_type_sql) if include_event_type_breakdown else [],
        "overview_sql": overview_sql,
        "totals_by_token_sql": totals_by_token_sql,
        "totals_by_blockchain_sql": totals_by_blockchain_sql,
        "totals_by_event_type_sql": totals_by_event_type_sql if include_event_type_breakdown else None,
    }


def _get_cash_events_plan(
    event_type=None,
    user_safe=None,
    start_date=None,
    end_date=None,
    mode="summary",
    limit=100,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_cash_events"
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "event_type": event_type,
            "user_safe": user_safe,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
    freshness_status = dataset_error

    if event_type is not None and event_type not in CASH_EVENT_TYPES:
        return {
            "error": (
                "event_type must be one of: "
                + ", ".join(sorted(CASH_EVENT_TYPES))
                + "."
            ),
            "dataset_name": dataset_name,
            "event_type": event_type,
            "user_safe": user_safe,
            "start_date": start_date,
            "end_date": end_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    try:
        mode_value = _validate_mode(mode)
        limit_value = _validate_limit(limit)
        user_safe_literal = _normalize_address_literal(user_safe) if user_safe else None
        start_date_value = _validate_date_literal(start_date, "start_date") if start_date else None
        end_date_value = _validate_date_literal(end_date, "end_date") if end_date else None
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "event_type": event_type,
            "user_safe": user_safe,
            "start_date": start_date,
            "end_date": end_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    if start_date_value and end_date_value and start_date_value > end_date_value:
        return {
            "error": "start_date must be on or before end_date.",
            "dataset_name": dataset_name,
            "event_type": event_type,
            "user_safe": user_safe,
            "start_date": start_date,
            "end_date": end_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    where_lines = _build_cash_events_where_lines(
        event_type=event_type,
        user_safe_literal=user_safe_literal,
        start_date=start_date_value,
        end_date=end_date_value,
    )
    broad_rows_request = (
        mode_value == "rows"
        and user_safe_literal is None
        and (start_date_value is None or end_date_value is None)
    ) or (
        mode_value == "rows"
        and user_safe_literal is None
        and start_date_value is not None
        and end_date_value is not None
        and (datetime.strptime(end_date_value, "%Y-%m-%d").date() - datetime.strptime(start_date_value, "%Y-%m-%d").date()).days > 7
        and limit_value > 500
    )
    if broad_rows_request:
        return {
            "error": (
                "Broad rows mode requests are expensive. Add user_safe, narrow the "
                "date range, or keep limit at 500 or less."
            ),
            "dataset_name": dataset_name,
            "event_type": event_type,
            "user_safe": user_safe,
            "start_date": start_date_value,
            "end_date": end_date_value,
            "mode": mode_value,
            "limit": limit_value,
            "query_ready": True,
        }

    if mode_value == "rows":
        suggested_sql = (
            "SELECT\n"
            "  blockchain,\n"
            "  contract_address,\n"
            "  block_date,\n"
            "  block_time,\n"
            "  block_minute,\n"
            "  block_number,\n"
            "  tx_index,\n"
            "  tx_hash,\n"
            "  event_type,\n"
            "  user_safe,\n"
            "  token_address,\n"
            "  token_symbol,\n"
            "  token_amount_raw,\n"
            "  token_amount,\n"
            "  token_amount_usd,\n"
            "  event_class,\n"
            "  last_updated\n"
            f"FROM {table_name}\n"
            + _format_where_clause(where_lines)
            + "ORDER BY block_time DESC NULLS LAST, tx_index DESC NULLS LAST\n"
            + f"LIMIT {limit_value};"
        )
    else:
        suggested_sql = (
            "SELECT\n"
            "  COUNT(*) AS event_count,\n"
            "  MAX(block_time) AS latest_event_time,\n"
            "  SUM(token_amount_usd) AS total_token_amount_usd\n"
            f"FROM {table_name}\n"
            + _format_where_clause(where_lines)
        )

    plan = {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "event_type": event_type,
        "user_safe": user_safe,
        "start_date": start_date_value,
        "end_date": end_date_value,
        "mode": mode_value,
        "limit": limit_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "suggested_sql": suggested_sql,
    }
    if not where_lines:
        plan["warning"] = (
            "No filters were provided. Cash events can be large; add event_type, "
            "user_safe, or a date range for a more focused query."
        )
    if mode_value == "rows":
        plan["rows_mode_note"] = "Summary values in rows mode apply only to the returned rows."
    return plan


def get_cash_events(
    event_type=None,
    user_safe=None,
    start_date=None,
    end_date=None,
    mode="summary",
    execute_live=False,
    limit=100,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_cash_events_plan(
        event_type=event_type,
        user_safe=user_safe,
        start_date=start_date,
        end_date=end_date,
        mode=mode,
        limit=limit,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        return {
            **plan,
            "summary": _build_cash_events_summary(
                [],
                event_type=event_type,
                user_safe=user_safe,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_cash_events_summary(
                [],
                event_type=event_type,
                user_safe=user_safe,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    try:
        if plan["mode"] == "summary":
            summary_queries = _execute_cash_events_summary_queries(
                plan["table_name"],
                _build_cash_events_where_lines(
                    event_type=event_type,
                    user_safe_literal=_normalize_address_literal(user_safe) if user_safe else None,
                    start_date=plan["start_date"],
                    end_date=plan["end_date"],
                ),
                include_event_type_breakdown=event_type is None,
            )
            summary = _build_cash_events_summary_from_queries(
                summary_queries["overview_rows"],
                summary_queries["totals_by_token_rows"],
                summary_queries["totals_by_blockchain_rows"],
                summary_queries["totals_by_event_type_rows"],
                event_type=event_type,
                user_safe=user_safe,
                start_date=start_date,
                end_date=end_date,
            )
            return {
                **plan,
                "executed_live": True,
                "row_count": summary["event_count"],
                "rows": [],
                "summary": summary,
                "summary_queries": {
                    "overview_sql": summary_queries["overview_sql"],
                    "totals_by_token_sql": summary_queries["totals_by_token_sql"],
                    "totals_by_blockchain_sql": summary_queries["totals_by_blockchain_sql"],
                    "totals_by_event_type_sql": summary_queries["totals_by_event_type_sql"],
                },
            }
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_cash_events_summary(
                [],
                event_type=event_type,
                user_safe=user_safe,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    return {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "summary": _build_cash_events_summary(
            rows,
            event_type=event_type,
            user_safe=user_safe,
            start_date=start_date,
            end_date=end_date,
        ),
    }


def _build_protocol_token_holders_summary(
    rows: list[dict],
    dataset_name: str,
    include_defi: bool,
    exclude_identified_defi: bool,
    address=None,
    token_symbol=None,
    token_address=None,
) -> dict:
    if not rows:
        return {
            "dataset_used": dataset_name,
            "address": address,
            "include_defi": include_defi,
            "exclude_identified_defi": exclude_identified_defi,
            "latest_day": None,
            "row_count": 0,
            "holder_count": 0,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "total_token_balance": 0.0,
            "balances_by_blockchain": [],
            "top_holders_preview": [],
            "defi_contract_breakdown": [],
        }

    latest_day = max(row.get("day") for row in rows if row.get("day") is not None)
    total_token_balance = sum(_to_number(row.get("token_balance")) for row in rows)
    holder_count = len({row.get("address") for row in rows if row.get("address") is not None})
    observed_symbols = {row.get("token_symbol") for row in rows if row.get("token_symbol") not in (None, "")}

    chain_groups: dict[str, dict] = {}
    for row in rows:
        blockchain = row.get("blockchain")
        group = chain_groups.setdefault(
            blockchain,
            {
                "blockchain": blockchain,
                "total_token_balance": 0.0,
                "token_balance_usd": 0.0,
                "token_balance_eth": 0.0,
                "holder_count": 0,
            },
        )
        group["total_token_balance"] += _to_number(row.get("token_balance"))
        group["token_balance_usd"] += _to_number(row.get("token_balance_usd"))
        group["token_balance_eth"] += _to_number(row.get("token_balance_eth"))

    holders_seen_by_chain: dict[str, set] = {}
    for row in rows:
        holders_seen_by_chain.setdefault(row.get("blockchain"), set()).add(row.get("address"))
    for blockchain, holders in holders_seen_by_chain.items():
        chain_groups[blockchain]["holder_count"] = len(holders)

    top_holders_preview = []
    for row in rows[: min(len(rows), 5)]:
        preview = {
            "address": row.get("address"),
            "blockchain": row.get("blockchain"),
            "token_balance": row.get("token_balance"),
        }
        if include_defi:
            preview["token_balance_usd"] = row.get("token_balance_usd")
            preview["identified_defi_contract"] = row.get("identified_defi_contract")
        top_holders_preview.append(preview)

    defi_contract_breakdown = []
    if include_defi:
        contract_groups: dict[str, dict] = {}
        for row in rows:
            bucket = row.get("identified_defi_contract") or "unidentified_or_non_defi"
            group = contract_groups.setdefault(
                bucket,
                {
                    "identified_defi_contract": bucket,
                    "holder_count": 0,
                    "total_token_balance": 0.0,
                    "token_balance_usd": 0.0,
                },
            )
            group["total_token_balance"] += _to_number(row.get("token_balance"))
            group["token_balance_usd"] += _to_number(row.get("token_balance_usd"))
        holders_by_bucket: dict[str, set] = {}
        for row in rows:
            bucket = row.get("identified_defi_contract") or "unidentified_or_non_defi"
            holders_by_bucket.setdefault(bucket, set()).add(row.get("address"))
        for bucket, holders in holders_by_bucket.items():
            contract_groups[bucket]["holder_count"] = len(holders)
        defi_contract_breakdown = sorted(
            contract_groups.values(),
            key=lambda row: row["token_balance_usd"],
            reverse=True,
        )

    return {
        "dataset_used": dataset_name,
        "address": address,
        "include_defi": include_defi,
        "exclude_identified_defi": exclude_identified_defi,
        "latest_day": latest_day,
        "row_count": len(rows),
        "holder_count": holder_count,
        "token_symbol": token_symbol if token_symbol is not None else (next(iter(observed_symbols)) if len(observed_symbols) == 1 else None),
        "token_address": token_address,
        "total_token_balance": total_token_balance,
        "balances_by_blockchain": sorted(
            chain_groups.values(),
            key=lambda row: row["total_token_balance"],
            reverse=True,
        ),
        "top_holders_preview": top_holders_preview,
        "defi_contract_breakdown": defi_contract_breakdown,
    }


def _is_protocol_address_placeholder_row(row: dict) -> bool:
    return (
        row.get("address") is None
        and row.get("token_symbol") is None
        and row.get("token_address") is None
    )


def _protocol_address_holding_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if not _is_protocol_address_placeholder_row(row)]


def _build_protocol_address_holdings_summary(
    rows: list[dict],
    dataset_name: str,
    address: str | None,
    include_defi: bool,
    exclude_identified_defi: bool,
    token_symbol=None,
    token_address=None,
) -> dict:
    data_rows = _protocol_address_holding_rows(rows)
    latest_values = [row.get("day") for row in rows if row.get("day") is not None]
    latest_day = max(latest_values) if latest_values else None
    usd_value_available = include_defi

    base_summary = {
        "dataset_used": dataset_name,
        "address": address,
        "include_defi": include_defi,
        "exclude_identified_defi": exclude_identified_defi,
        "latest_day": latest_day,
        "row_count": len(data_rows),
        "holder_count": 1 if data_rows else 0,
        "token_symbol": token_symbol,
        "token_address": token_address,
        "usd_value_available": usd_value_available,
        "total_token_balance": None,
        "total_token_balance_usd": None,
        "token_breakdown": [],
        "balances_by_blockchain": [],
        "defi_contract_breakdown": [],
        "no_holdings_found": not data_rows,
    }
    if not data_rows:
        snapshot_label = latest_day or "the selected snapshot"
        base_summary["message"] = (
            "No current tracked ether.fi protocol token holdings were found for this address "
            f"in {dataset_name} as of {snapshot_label}."
        )
        if not usd_value_available:
            base_summary["valuation_note"] = (
                "The direct protocol holder table has token balances but no USD value column; "
                "join pricing separately if USD totals are required."
            )
        return base_summary

    observed_symbols = {row.get("token_symbol") for row in data_rows if row.get("token_symbol") not in (None, "")}
    total_token_balance = sum(_to_number(row.get("token_balance")) for row in data_rows)
    total_token_balance_usd = (
        sum(_to_number(row.get("token_balance_usd")) for row in data_rows)
        if usd_value_available
        else None
    )

    token_breakdown = []
    for row in data_rows:
        item = {
            "blockchain": row.get("blockchain"),
            "token_symbol": row.get("token_symbol"),
            "token_address": row.get("token_address"),
            "token_balance": _to_number(row.get("token_balance")),
            "token_balance_raw": _to_number(row.get("token_balance_raw")),
            "last_updated": row.get("last_updated"),
        }
        if include_defi:
            item.update(
                {
                    "token_underlying_symbol": row.get("token_underlying_symbol"),
                    "token_balance_underlying": _to_number(row.get("token_balance_underlying")),
                    "token_balance_usd": _to_number(row.get("token_balance_usd")),
                    "token_balance_eth": _to_number(row.get("token_balance_eth")),
                    "identified_defi_contract": row.get("identified_defi_contract"),
                }
            )
        token_breakdown.append(item)

    chain_groups: dict[str, dict] = {}
    for row in data_rows:
        blockchain = row.get("blockchain")
        group = chain_groups.setdefault(
            blockchain,
            {
                "blockchain": blockchain,
                "row_count": 0,
                "total_token_balance": 0.0 if len(observed_symbols) <= 1 else None,
                "token_balance_usd": 0.0 if usd_value_available else None,
                "token_balance_eth": 0.0 if include_defi else None,
            },
        )
        group["row_count"] += 1
        if group["total_token_balance"] is not None:
            group["total_token_balance"] += _to_number(row.get("token_balance"))
        if usd_value_available:
            group["token_balance_usd"] += _to_number(row.get("token_balance_usd"))
        if include_defi:
            group["token_balance_eth"] += _to_number(row.get("token_balance_eth"))

    defi_contract_breakdown = []
    if include_defi:
        contract_groups: dict[str, dict] = {}
        for row in data_rows:
            bucket = row.get("identified_defi_contract") or "unidentified_or_non_defi"
            group = contract_groups.setdefault(
                bucket,
                {
                    "identified_defi_contract": bucket,
                    "row_count": 0,
                    "total_token_balance": 0.0,
                    "token_balance_usd": 0.0,
                },
            )
            group["row_count"] += 1
            group["total_token_balance"] += _to_number(row.get("token_balance"))
            group["token_balance_usd"] += _to_number(row.get("token_balance_usd"))
        defi_contract_breakdown = sorted(
            contract_groups.values(),
            key=lambda row: row["token_balance_usd"],
            reverse=True,
        )

    base_summary.update(
        {
            "latest_day": latest_day,
            "row_count": len(data_rows),
            "holder_count": 1,
            "token_symbol": token_symbol if token_symbol is not None else (next(iter(observed_symbols)) if len(observed_symbols) == 1 else None),
            "total_token_balance": total_token_balance if len(observed_symbols) <= 1 else None,
            "total_token_balance_usd": total_token_balance_usd,
            "token_breakdown": token_breakdown,
            "balances_by_blockchain": sorted(
                chain_groups.values(),
                key=lambda row: (
                    _to_number(row.get("token_balance_usd"))
                    if usd_value_available
                    else _to_number(row.get("total_token_balance"))
                ),
                reverse=True,
            ),
            "defi_contract_breakdown": defi_contract_breakdown,
            "message": (
                f"Current tracked ether.fi protocol holdings were found for this address in {dataset_name}."
            ),
        }
    )
    if len(observed_symbols) > 1 and not usd_value_available:
        base_summary["total_token_balance_note"] = (
            "Token balances are not summed across symbols because the direct holder table has no USD value column."
        )
    if not usd_value_available:
        base_summary["valuation_note"] = (
            "The direct protocol holder table has token balances but no USD value column; "
            "join pricing separately if USD totals are required."
        )
    return base_summary


def _build_protocol_token_holders_summary_from_queries(
    overview_rows: list[dict],
    balances_by_blockchain_rows: list[dict],
    top_holders_rows: list[dict],
    defi_contract_breakdown_rows: list[dict],
    dataset_name: str,
    include_defi: bool,
    exclude_identified_defi: bool,
    token_symbol=None,
    token_address=None,
) -> dict:
    overview = overview_rows[0] if overview_rows else {}
    return {
        "dataset_used": dataset_name,
        "include_defi": include_defi,
        "exclude_identified_defi": exclude_identified_defi,
        "latest_day": overview.get("latest_day"),
        "row_count": int(_to_number(overview.get("holder_count"))),
        "holder_count": int(_to_number(overview.get("holder_count"))),
        "token_symbol": token_symbol or overview.get("token_symbol"),
        "token_address": token_address,
        "total_token_balance": _to_number(overview.get("total_token_balance")),
        "balances_by_blockchain": [
            {
                "blockchain": row.get("blockchain"),
                "total_token_balance": _to_number(row.get("total_token_balance")),
                "token_balance_usd": _to_number(row.get("token_balance_usd")),
                "token_balance_eth": _to_number(row.get("token_balance_eth")),
                "holder_count": int(_to_number(row.get("holder_count"))),
            }
            for row in balances_by_blockchain_rows
        ],
        "top_holders_preview": [
            {
                "address": row.get("address"),
                "blockchain": row.get("blockchain"),
                "token_balance": _to_number(row.get("token_balance")),
                **(
                    {
                        "token_balance_usd": _to_number(row.get("token_balance_usd")),
                        "identified_defi_contract": row.get("identified_defi_contract"),
                    }
                    if include_defi
                    else {}
                ),
            }
            for row in top_holders_rows
        ],
        "defi_contract_breakdown": [
            {
                "identified_defi_contract": row.get("identified_defi_contract"),
                "holder_count": int(_to_number(row.get("holder_count"))),
                "total_token_balance": _to_number(row.get("total_token_balance")),
                "token_balance_usd": _to_number(row.get("token_balance_usd")),
            }
            for row in defi_contract_breakdown_rows
        ],
    }


def _build_protocol_token_holders_base_filter_lines(
    token_symbol=None,
    token_address_literal=None,
    address_literal=None,
    include_defi=False,
    exclude_identified_defi=False,
) -> list[str]:
    filter_lines: list[str] = []
    if token_symbol:
        filter_lines.append(f"token_symbol = {_quote_sql_string(token_symbol)}")
    if token_address_literal:
        filter_lines.append(f"token_address = {token_address_literal}")
    if address_literal:
        filter_lines.append(f"address = {address_literal}")
    if include_defi and exclude_identified_defi:
        filter_lines.append("identified_defi_contract IS NULL")
    return filter_lines


def _build_top_cash_users_filter_lines(
    token_symbol=None,
    token_address_literal=None,
    blockchain=None,
) -> list[str]:
    filter_lines = ["address_name = 'CASH'"]
    if token_symbol:
        filter_lines.append(f"token_symbol = {_quote_sql_string(token_symbol)}")
    if token_address_literal:
        filter_lines.append(f"token_address = {token_address_literal}")
    if blockchain:
        filter_lines.append(f"blockchain = {_quote_sql_string(blockchain)}")
    return filter_lines


def _build_cash_token_totals_summary(rows: list[dict]) -> dict:
    summary = {
        "latest_day": None,
        "holder_count": 0,
        "total_token_balance_usd": 0.0,
        "total_token_balance_eth": 0.0,
        "total_token_balance": 0.0,
        "token_symbol": None,
        "token_underlying_symbol": None,
        "balances_by_blockchain": [],
    }
    if not rows:
        return summary

    overview_row = next((row for row in rows if row.get("row_type") == "overview"), None)
    if overview_row is None:
        return summary

    summary.update(
        {
            "latest_day": overview_row.get("latest_day"),
            "holder_count": int(_to_number(overview_row.get("holder_count"))),
            "total_token_balance_usd": _to_number(overview_row.get("total_token_balance_usd")),
            "total_token_balance_eth": _to_number(overview_row.get("total_token_balance_eth")),
            "total_token_balance": (
                None
                if overview_row.get("total_token_balance") is None
                else _to_number(overview_row.get("total_token_balance"))
            ),
            "token_symbol": overview_row.get("token_symbol"),
            "token_underlying_symbol": overview_row.get("token_underlying_symbol"),
            "balances_by_blockchain": [
                {
                    "blockchain": row.get("blockchain"),
                    "holder_count": int(_to_number(row.get("holder_count"))),
                    "total_token_balance_usd": _to_number(row.get("total_token_balance_usd")),
                    "total_token_balance_eth": _to_number(row.get("total_token_balance_eth")),
                    "total_token_balance": (
                        None
                        if row.get("total_token_balance") is None
                        else _to_number(row.get("total_token_balance"))
                    ),
                    "token_symbol": row.get("token_symbol"),
                    "token_underlying_symbol": row.get("token_underlying_symbol"),
                }
                for row in rows
                if row.get("row_type") == "blockchain"
            ],
        }
    )
    return summary


def _validate_cash_holdings_timeseries_granularity(granularity: str | None) -> str:
    return _validate_timeseries_granularity(granularity, allowed=_TIMESERIES_GRANULARITIES)


def _validate_cash_holdings_group_by(group_by: str | None) -> str | None:
    if group_by is None:
        return None
    if group_by not in _CASH_HOLDINGS_GROUP_BYS:
        allowed_values = ", ".join(sorted(_CASH_HOLDINGS_GROUP_BYS))
        raise ValueError(f"group_by must be one of: {allowed_values}.")
    return group_by


def _validate_cash_holdings_category_preset(category_preset: str | None) -> str | None:
    if category_preset is None:
        return None
    if category_preset not in _CASH_HOLDINGS_CATEGORY_PRESETS:
        allowed_values = ", ".join(sorted(_CASH_HOLDINGS_CATEGORY_PRESETS))
        raise ValueError(f"category_preset must be one of: {allowed_values}.")
    return category_preset


def _validate_cash_holdings_token_symbols(token_symbols) -> list[str] | None:
    if token_symbols is None:
        return None
    if not isinstance(token_symbols, list) or not token_symbols:
        raise ValueError("token_symbols must be a non-empty list.")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in token_symbols:
        symbol = _validate_simple_string_literal(value, "token_symbols")
        if symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    return normalized


def _validate_cash_holdings_categories(categories, category_preset: str | None) -> list[str] | None:
    if categories is None:
        return None
    if category_preset is None:
        raise ValueError("categories requires category_preset='cash_balance_buckets'.")
    if not isinstance(categories, list) or not categories:
        raise ValueError("categories must be a non-empty list.")
    allowed_categories = sorted(set(_CASH_HOLDINGS_CATEGORY_PRESETS[category_preset].values()))
    normalized: list[str] = []
    seen: set[str] = set()
    for value in categories:
        category = _validate_simple_string_literal(value, "categories")
        if category not in allowed_categories:
            allowed_values = ", ".join(allowed_categories)
            raise ValueError(f"categories must contain only: {allowed_values}.")
        if category not in seen:
            normalized.append(category)
            seen.add(category)
    return normalized


def _resolve_cash_holdings_timeseries_date_range(
    start_date=None,
    end_date=None,
    period=None,
    now=None,
) -> tuple[str, str]:
    return _resolve_timeseries_date_range(
        start_date=start_date,
        end_date=end_date,
        period=period,
        supported_periods=_CASH_HOLDINGS_TIMESERIES_PERIODS,
        now=now,
    )


def _build_cash_holdings_timeseries_summary(
    rows: list[dict],
    start_date: str,
    end_date: str,
    period=None,
    token_symbol=None,
    token_symbols=None,
    token_address=None,
    blockchain=None,
    granularity="day",
    group_by=None,
    category_preset=None,
    categories=None,
) -> dict:
    summary = {
        "start_date": start_date,
        "end_date": end_date,
        "period": period,
        "granularity": granularity,
        "group_by": group_by,
        "category_preset": category_preset,
        "categories": categories,
        "token_symbol": token_symbol,
        "token_symbols": token_symbols,
        "token_address": token_address,
        "blockchain": blockchain,
        "period_count": 0,
        "day_count": 0,
        "month_count": 0,
        "latest_day": None,
        "latest_month": None,
        "latest_holder_count": 0,
        "latest_total_usd": 0.0,
        "latest_avg_balance_usd": 0.0,
        "latest_total_eth": 0.0,
        "latest_avg_balance_eth": 0.0,
        "latest_totals_by_group": [],
        "max_avg_balance_usd": 0.0,
        "min_avg_balance_usd": 0.0,
        "average_of_daily_avg_balance_usd": 0.0,
    }
    if not rows:
        return summary

    period_key = "month" if granularity == "month" else "day"
    latest_period = max(row.get(period_key) for row in rows if row.get(period_key) is not None)
    latest_rows = [row for row in rows if row.get(period_key) == latest_period]
    latest_day = max(
        row.get("month_end_day") or row.get("day")
        for row in latest_rows
        if row.get("month_end_day") or row.get("day")
    )
    latest_totals_by_group = []
    if group_by:
        latest_totals_by_group = [
            {
                group_by: row.get(group_by),
                "total_usd": _to_number(row.get("total_usd")),
                "total_eth": _to_number(row.get("total_eth")),
                "holder_count": int(_to_number(row.get("holder_count"))),
            }
            for row in sorted(latest_rows, key=lambda item: _to_number(item.get("total_usd")), reverse=True)
        ]
    avg_usd_values = [
        _to_number(row.get("avg_balance_usd"))
        for row in rows
        if row.get("avg_balance_usd") is not None
    ]
    summary.update(
        {
            "period_count": len({row.get(period_key) for row in rows if row.get(period_key) is not None}),
            "latest_day": latest_day,
            "latest_holder_count": sum(int(_to_number(row.get("holder_count"))) for row in latest_rows),
            "latest_total_usd": sum(_to_number(row.get("total_usd")) for row in latest_rows),
            "latest_total_eth": sum(_to_number(row.get("total_eth")) for row in latest_rows),
            "latest_totals_by_group": latest_totals_by_group,
        }
    )
    if granularity == "month":
        summary["month_count"] = summary["period_count"]
        summary["latest_month"] = latest_period
    else:
        summary["day_count"] = summary["period_count"]
    if not group_by and latest_rows:
        latest_row = latest_rows[-1]
        summary["latest_avg_balance_usd"] = _to_number(latest_row.get("avg_balance_usd"))
        summary["latest_avg_balance_eth"] = _to_number(latest_row.get("avg_balance_eth"))
    if avg_usd_values:
        summary["max_avg_balance_usd"] = max(avg_usd_values)
        summary["min_avg_balance_usd"] = min(avg_usd_values)
        summary["average_of_daily_avg_balance_usd"] = sum(avg_usd_values) / len(avg_usd_values)
    return summary


def _build_protocol_token_holders_summary_queries(
    table_name: str,
    filter_lines: list[str],
    include_defi: bool,
) -> dict:
    latest_day_expr = (
        "CAST(day AS DATE) = CAST('{as_of_date}' AS DATE)"
    )
    filter_clause = _format_where_clause(filter_lines)
    latest_day_subquery = (
        f"SELECT MAX(day) FROM {table_name}\n" + filter_clause
    )
    summary_where_lines = [*filter_lines, f"day = ({latest_day_subquery.rstrip()})"]
    summary_where_clause = _format_where_clause(summary_where_lines)
    overview_sql = (
        "SELECT\n"
        "  MAX(day) AS latest_day,\n"
        "  COUNT(*) AS holder_count,\n"
        "  CASE WHEN COUNT(DISTINCT token_symbol) = 1 THEN MAX(token_symbol) ELSE NULL END AS token_symbol,\n"
        "  SUM(token_balance) AS total_token_balance\n"
        f"FROM {table_name}\n"
        f"{summary_where_clause}"
    )
    balances_by_blockchain_sql = (
        "SELECT\n"
        "  blockchain,\n"
        "  COUNT(*) AS holder_count,\n"
        "  SUM(token_balance) AS total_token_balance,\n"
        + (
            "  SUM(COALESCE(token_balance_usd, 0)) AS token_balance_usd,\n"
            "  SUM(COALESCE(token_balance_eth, 0)) AS token_balance_eth\n"
            if include_defi
            else "  CAST(0 AS DOUBLE) AS token_balance_usd,\n"
            "  CAST(0 AS DOUBLE) AS token_balance_eth\n"
        )
        + f"FROM {table_name}\n"
        + f"{summary_where_clause}"
        + "GROUP BY 1\n"
        + "ORDER BY total_token_balance DESC NULLS LAST, blockchain\n"
        + "LIMIT 20;"
    )
    top_holders_sql = (
        "SELECT\n"
        "  address,\n"
        "  blockchain,\n"
        "  token_balance,\n"
        + ("  token_balance_usd,\n  identified_defi_contract,\n" if include_defi else "")
        + "  last_updated\n"
        f"FROM {table_name}\n"
        f"{summary_where_clause}"
        "ORDER BY token_balance DESC NULLS LAST, address\n"
        "LIMIT 5;"
    )
    defi_contract_breakdown_sql = (
        "SELECT\n"
        "  COALESCE(identified_defi_contract, 'unidentified_or_non_defi') AS identified_defi_contract,\n"
        "  COUNT(*) AS holder_count,\n"
        "  SUM(token_balance) AS total_token_balance,\n"
        "  SUM(COALESCE(token_balance_usd, 0)) AS token_balance_usd\n"
        f"FROM {table_name}\n"
        f"{summary_where_clause}"
        "GROUP BY 1\n"
        "ORDER BY token_balance_usd DESC NULLS LAST, identified_defi_contract\n"
        "LIMIT 20;"
    )
    return {
        "overview_rows": _execute_dune_sql(overview_sql),
        "balances_by_blockchain_rows": _execute_dune_sql(balances_by_blockchain_sql),
        "top_holders_rows": _execute_dune_sql(top_holders_sql),
        "defi_contract_breakdown_rows": _execute_dune_sql(defi_contract_breakdown_sql) if include_defi else [],
        "overview_sql": overview_sql,
        "balances_by_blockchain_sql": balances_by_blockchain_sql,
        "top_holders_sql": top_holders_sql,
        "defi_contract_breakdown_sql": defi_contract_breakdown_sql if include_defi else None,
    }


def _build_protocol_address_holdings_sql(
    table_name: str,
    address_literal: str,
    token_symbol=None,
    token_address_literal=None,
    as_of_date=None,
    include_defi=False,
    exclude_identified_defi=False,
    limit=100,
) -> str:
    snapshot_filter_lines = _build_protocol_token_holders_base_filter_lines(
        token_symbol=token_symbol,
        token_address_literal=token_address_literal,
        include_defi=include_defi,
        exclude_identified_defi=exclude_identified_defi,
    )
    latest_snapshot_where_clause = _format_where_clause(
        [
            *snapshot_filter_lines,
            f"CAST(day AS DATE) = CAST('{as_of_date}' AS DATE)",
        ]
        if as_of_date
        else snapshot_filter_lines
    )
    holding_filter_lines = _build_protocol_token_holders_base_filter_lines(
        token_symbol=token_symbol,
        token_address_literal=token_address_literal,
        address_literal=address_literal,
        include_defi=include_defi,
        exclude_identified_defi=exclude_identified_defi,
    )
    holding_where_clause = _format_where_clause(
        [
            *holding_filter_lines,
            "day = (SELECT day FROM latest_snapshot)",
        ]
    )
    if include_defi:
        aggregate_select = (
            "  day,\n"
            "  address,\n"
            "  blockchain,\n"
            "  token_address,\n"
            "  token_symbol,\n"
            "  underlying_symbol,\n"
            "  underlying_protocol,\n"
            "  token_underlying_symbol,\n"
            "  identified_defi_contract,\n"
            "  SUM(token_balance_raw) AS token_balance_raw,\n"
            "  SUM(token_balance) AS token_balance,\n"
            "  SUM(token_balance_underlying) AS token_balance_underlying,\n"
            "  SUM(COALESCE(token_balance_usd, 0)) AS token_balance_usd,\n"
            "  SUM(COALESCE(token_balance_eth, 0)) AS token_balance_eth,\n"
            "  MAX(last_updated) AS last_updated"
        )
        aggregate_group_by = "GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9"
        final_extra_select = (
            "  aggregated_holdings.underlying_symbol,\n"
            "  aggregated_holdings.underlying_protocol,\n"
            "  aggregated_holdings.token_underlying_symbol,\n"
            "  aggregated_holdings.identified_defi_contract,\n"
            "  aggregated_holdings.token_balance_underlying,\n"
            "  aggregated_holdings.token_balance_usd,\n"
            "  aggregated_holdings.token_balance_eth,\n"
        )
        order_expr = "aggregated_holdings.token_balance_usd DESC NULLS LAST, aggregated_holdings.token_balance DESC NULLS LAST"
    else:
        aggregate_select = (
            "  day,\n"
            "  address,\n"
            "  blockchain,\n"
            "  token_address,\n"
            "  token_symbol,\n"
            "  SUM(token_balance_raw) AS token_balance_raw,\n"
            "  SUM(token_balance) AS token_balance,\n"
            "  MAX(last_updated) AS last_updated"
        )
        aggregate_group_by = "GROUP BY 1, 2, 3, 4, 5"
        final_extra_select = ""
        order_expr = "aggregated_holdings.token_balance DESC NULLS LAST"

    return (
        "WITH latest_snapshot AS (\n"
        "  SELECT MAX(day) AS day\n"
        f"  FROM {table_name}\n"
        f"{latest_snapshot_where_clause}"
        "),\n"
        "filtered_holdings AS (\n"
        "  SELECT *\n"
        f"  FROM {table_name}\n"
        f"{holding_where_clause}"
        "),\n"
        "aggregated_holdings AS (\n"
        "SELECT\n"
        f"{aggregate_select}\n"
        "FROM filtered_holdings\n"
        f"{aggregate_group_by}\n"
        ")\n"
        "SELECT\n"
        "  COALESCE(aggregated_holdings.day, latest_snapshot.day) AS day,\n"
        "  aggregated_holdings.address,\n"
        "  aggregated_holdings.blockchain,\n"
        "  aggregated_holdings.token_address,\n"
        "  aggregated_holdings.token_symbol,\n"
        f"{final_extra_select}"
        "  aggregated_holdings.token_balance_raw,\n"
        "  aggregated_holdings.token_balance,\n"
        "  aggregated_holdings.last_updated\n"
        "FROM latest_snapshot\n"
        "LEFT JOIN aggregated_holdings ON TRUE\n"
        f"ORDER BY {order_expr}, aggregated_holdings.token_symbol, aggregated_holdings.blockchain\n"
        f"LIMIT {limit};"
    )


def _build_protocol_token_tvl_where_lines(
    strategy_symbol=None,
    strategy_symbols=None,
    strategy_address_literal=None,
) -> list[str]:
    where_lines: list[str] = []
    if strategy_symbol:
        where_lines.append(f"strategy_symbol = '{strategy_symbol}'")
    elif strategy_symbols:
        symbol_literals = ", ".join(f"'{symbol}'" for symbol in strategy_symbols)
        where_lines.append(f"strategy_symbol IN ({symbol_literals})")
    if strategy_address_literal:
        where_lines.append(f"strategy_address = {strategy_address_literal}")
    return where_lines


def _build_protocol_token_tvl_day_filter(
    table_name: str,
    filter_lines: list[str],
    latest_day_per_strategy=False,
    as_of_date=None,
) -> str:
    if as_of_date:
        return f"CAST(day AS DATE) = CAST('{as_of_date}' AS DATE)"

    if latest_day_per_strategy:
        latest_day_subquery = (
            f"SELECT strategy_symbol, MAX(day) AS latest_day FROM {table_name}\n"
            + _format_where_clause(filter_lines)
            + "GROUP BY 1"
        )
        return (
            "(strategy_symbol, day) IN (\n"
            f"{latest_day_subquery.rstrip()}\n"
            ")"
        )

    latest_day_subquery = (
        f"SELECT MAX(day) FROM {table_name}\n"
        + _format_where_clause(filter_lines)
    )
    return f"day = ({latest_day_subquery.rstrip()})"


def _build_protocol_token_tvl_summary(
    rows: list[dict],
    strategy_symbol=None,
    strategy_symbols=None,
    strategy_address=None,
    as_of_date=None,
    mode="summary",
) -> dict:
    if not rows:
        return {
            "dataset_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
            "mode": mode,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "requested_as_of_date": as_of_date,
            "latest_day": None,
            "row_count": 0,
            "strategy_count": 0,
            "underlying_asset_symbol": None,
            "strategy_blockchains": [],
            "token_supply": 0.0,
            "token_supply_underlying": 0.0,
            "token_supply_usd": 0.0,
            "token_supply_eth": 0.0,
            "token_supply_btc": 0.0,
            "token_supply_eigen": 0.0,
            "token_supply_hype": 0.0,
            "usd_rate": None,
            "eth_rate": None,
            "btc_rate": None,
            "eigen_rate": None,
            "hype_rate": None,
            "strategies": [],
        }

    latest_day = max(row.get("day") for row in rows if row.get("day") is not None)
    grouped_rows = [
        {
            "latest_day": row.get("day"),
            "strategy_symbol": row.get("strategy_symbol"),
            "strategy_address": row.get("strategy_address"),
            "underlying_asset_symbol": row.get("underlying_asset_symbol"),
            "strategy_blockchains": row.get("strategy_blockchains") or [],
            "token_supply": _to_number(row.get("token_supply")),
            "token_supply_underlying": _to_number(row.get("token_supply_underlying")),
            "token_supply_usd": _to_number(row.get("token_supply_usd")),
            "token_supply_eth": _to_number(row.get("token_supply_eth")),
            "token_supply_btc": _to_number(row.get("token_supply_btc")),
            "token_supply_eigen": _to_number(row.get("token_supply_eigen")),
            "token_supply_hype": _to_number(row.get("token_supply_hype")),
            "usd_rate": row.get("usd_rate"),
            "eth_rate": row.get("eth_rate"),
            "btc_rate": row.get("btc_rate"),
            "eigen_rate": row.get("eigen_rate"),
            "hype_rate": row.get("hype_rate"),
        }
        for row in rows
    ]
    unique_strategy_keys = {
        (row["strategy_symbol"], row["strategy_address"])
        for row in grouped_rows
    }
    strategy_count = len(unique_strategy_keys)

    summary = {
        "dataset_name": "dune.ether_fi.result_etherfi_protocol_token_tvl",
        "mode": mode,
        "strategy_symbol": strategy_symbol,
        "strategy_symbols": strategy_symbols or [],
        "strategy_address": strategy_address,
        "requested_as_of_date": as_of_date,
        "latest_day": latest_day,
        "row_count": len(rows),
        "strategy_count": strategy_count,
        "underlying_asset_symbol": None,
        "strategy_blockchains": [],
        "token_supply": sum(row["token_supply"] for row in grouped_rows),
        "token_supply_underlying": sum(row["token_supply_underlying"] for row in grouped_rows),
        "token_supply_usd": sum(row["token_supply_usd"] for row in grouped_rows),
        "token_supply_eth": sum(row["token_supply_eth"] for row in grouped_rows),
        "token_supply_btc": sum(row["token_supply_btc"] for row in grouped_rows),
        "token_supply_eigen": sum(row["token_supply_eigen"] for row in grouped_rows),
        "token_supply_hype": sum(row["token_supply_hype"] for row in grouped_rows),
        "usd_rate": None,
        "eth_rate": None,
        "btc_rate": None,
        "eigen_rate": None,
        "hype_rate": None,
        "strategies": grouped_rows,
    }
    if strategy_count == 1:
        strategy = grouped_rows[0]
        summary["underlying_asset_symbol"] = strategy["underlying_asset_symbol"]
        summary["strategy_blockchains"] = strategy["strategy_blockchains"]
        summary["usd_rate"] = strategy["usd_rate"]
        summary["eth_rate"] = strategy["eth_rate"]
        summary["btc_rate"] = strategy["btc_rate"]
        summary["eigen_rate"] = strategy["eigen_rate"]
        summary["hype_rate"] = strategy["hype_rate"]
    return summary


def _build_protocol_token_tvl_timeseries_summary(
    rows: list[dict],
    start_date=None,
    end_date=None,
    period=None,
    strategy_symbol=None,
    strategy_symbols=None,
    strategy_address=None,
    granularity="day",
) -> dict:
    summary = {
        "start_date": start_date,
        "end_date": end_date,
        "period": period,
        "granularity": granularity,
        "strategy_symbol": strategy_symbol,
        "strategy_symbols": strategy_symbols or [],
        "strategy_address": strategy_address,
        "period_count": 0,
        "day_count": 0,
        "month_count": 0,
        "row_count": 0,
        "strategy_count": 0,
        "latest_day": None,
        "latest_month": None,
        "latest_tvl_usd_total": 0.0,
        "latest_tvl_usd_by_symbol": [],
        "max_tvl_usd": 0.0,
        "min_tvl_usd": 0.0,
    }
    if not rows:
        return summary

    if granularity == "month":
        normalized_rows = [
            {
                "period_key": row.get("month"),
                "latest_day": row.get("month_end_day") or row.get("month"),
                "strategy_symbol": row.get("strategy_symbol"),
                "tvl_usd": _to_number(row.get("tvl_usd")),
            }
            for row in rows
        ]
    else:
        normalized_rows = [
            {
                "period_key": row.get("day"),
                "latest_day": row.get("day"),
                "strategy_symbol": row.get("strategy_symbol"),
                "tvl_usd": _to_number(row.get("tvl_usd")),
            }
            for row in rows
        ]

    latest_period = max(row["period_key"] for row in normalized_rows if row["period_key"] is not None)
    latest_rows = [row for row in normalized_rows if row["period_key"] == latest_period]
    summary.update(
        {
            "period_count": len({row["period_key"] for row in normalized_rows if row["period_key"] is not None}),
            "row_count": len(normalized_rows),
            "strategy_count": len({row["strategy_symbol"] for row in normalized_rows if row["strategy_symbol"]}),
            "latest_day": max(row["latest_day"] for row in latest_rows if row["latest_day"] is not None),
            "latest_tvl_usd_total": sum(row["tvl_usd"] for row in latest_rows),
            "latest_tvl_usd_by_symbol": [
                {
                    "strategy_symbol": row["strategy_symbol"],
                    "tvl_usd": row["tvl_usd"],
                }
                for row in sorted(latest_rows, key=lambda item: item["tvl_usd"], reverse=True)
            ],
            "max_tvl_usd": max(row["tvl_usd"] for row in normalized_rows),
            "min_tvl_usd": min(row["tvl_usd"] for row in normalized_rows),
        }
    )
    if granularity == "month":
        summary["month_count"] = summary["period_count"]
        summary["latest_month"] = latest_period
    else:
        summary["day_count"] = summary["period_count"]
    return summary


def _build_protocol_events_where_lines(
    project=None,
    strategy_symbol=None,
    strategy_address_literal=None,
    event_type=None,
    start_date=None,
    end_date=None,
) -> list[str]:
    where_lines: list[str] = []
    if project:
        where_lines.append(f"project = '{project}'")
    if strategy_symbol:
        where_lines.append(f"strategy_symbol = '{strategy_symbol}'")
    if strategy_address_literal:
        where_lines.append(f"strategy_address = {strategy_address_literal}")
    if event_type:
        where_lines.append(f"event_type = '{event_type}'")
    if start_date:
        where_lines.append(f"block_date >= CAST('{start_date}' AS DATE)")
    if end_date:
        where_lines.append(f"block_date <= CAST('{end_date}' AS DATE)")
    return where_lines


def _build_protocol_events_rows_summary(
    rows: list[dict],
    project=None,
    strategy_symbol=None,
    strategy_address=None,
    event_type=None,
    start_date=None,
    end_date=None,
) -> dict:
    if not rows:
        return {
            "dataset_name": "dune.ether_fi.result_etherfi_protocol_events",
            "mode": "rows",
            "project": project,
            "strategy_symbol": strategy_symbol,
            "strategy_address": strategy_address,
            "event_type": event_type,
            "date_range": {"start_date": start_date, "end_date": end_date},
            "event_count": 0,
            "latest_block_time": None,
            "total_amount_usd": 0.0,
            "total_amount_eth": 0.0,
            "total_token_amount": None,
            "total_strategy_amount": 0.0,
            "total_amount_underlying": None,
            "totals_by_event_type": [],
            "totals_by_blockchain": [],
            "totals_by_strategy": [],
            "totals_by_token_symbol": [],
            "totals_by_underlying_symbol": [],
        }

    latest_block_time = max(row.get("block_time") for row in rows if row.get("block_time") is not None)
    token_symbols = {row.get("token_symbol") for row in rows if row.get("token_symbol") not in (None, "")}
    underlying_symbols = {
        row.get("amount_underlying_symbol")
        for row in rows
        if row.get("amount_underlying_symbol") not in (None, "")
    }
    totals_by_event_type: dict[str, dict] = {}
    totals_by_blockchain: dict[str, dict] = {}
    totals_by_strategy: dict[str, dict] = {}
    totals_by_token_symbol: dict[str, dict] = {}
    totals_by_underlying_symbol: dict[str, dict] = {}

    for row in rows:
        event_key = row.get("event_type")
        event_group = totals_by_event_type.setdefault(
            event_key,
            {"event_type": event_key, "event_count": 0, "total_amount_usd": 0.0},
        )
        event_group["event_count"] += 1
        event_group["total_amount_usd"] += _to_number(row.get("amount_usd"))

        blockchain = row.get("blockchain")
        chain_group = totals_by_blockchain.setdefault(
            blockchain,
            {"blockchain": blockchain, "event_count": 0, "total_amount_usd": 0.0, "total_amount_eth": 0.0},
        )
        chain_group["event_count"] += 1
        chain_group["total_amount_usd"] += _to_number(row.get("amount_usd"))
        chain_group["total_amount_eth"] += _to_number(row.get("amount_eth"))

        strategy_key = row.get("strategy_symbol") or str(row.get("strategy_address"))
        strategy_group = totals_by_strategy.setdefault(
            strategy_key,
            {"strategy_symbol": row.get("strategy_symbol"), "strategy_address": row.get("strategy_address"), "event_count": 0, "total_amount_usd": 0.0},
        )
        strategy_group["event_count"] += 1
        strategy_group["total_amount_usd"] += _to_number(row.get("amount_usd"))

        token_symbol = row.get("token_symbol")
        token_group = totals_by_token_symbol.setdefault(
            token_symbol,
            {"token_symbol": token_symbol, "event_count": 0, "total_token_amount": 0.0, "total_amount_usd": 0.0},
        )
        token_group["event_count"] += 1
        token_group["total_token_amount"] += _to_number(row.get("token_amount"))
        token_group["total_amount_usd"] += _to_number(row.get("amount_usd"))

        underlying_symbol = row.get("amount_underlying_symbol")
        underlying_group = totals_by_underlying_symbol.setdefault(
            underlying_symbol,
            {"amount_underlying_symbol": underlying_symbol, "event_count": 0, "total_amount_underlying": 0.0, "total_amount_usd": 0.0},
        )
        underlying_group["event_count"] += 1
        underlying_group["total_amount_underlying"] += _to_number(row.get("amount_underlying"))
        underlying_group["total_amount_usd"] += _to_number(row.get("amount_usd"))

    return {
        "dataset_name": "dune.ether_fi.result_etherfi_protocol_events",
        "mode": "rows",
        "project": project,
        "strategy_symbol": strategy_symbol,
        "strategy_address": strategy_address,
        "event_type": event_type,
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "event_count": len(rows),
        "latest_block_time": latest_block_time,
        "total_amount_usd": sum(_to_number(row.get("amount_usd")) for row in rows),
        "total_amount_eth": sum(_to_number(row.get("amount_eth")) for row in rows),
        "total_token_amount": sum(_to_number(row.get("token_amount")) for row in rows) if len(token_symbols) <= 1 else None,
        "total_strategy_amount": sum(_to_number(row.get("strategy_amount")) for row in rows),
        "total_amount_underlying": sum(_to_number(row.get("amount_underlying")) for row in rows) if len(underlying_symbols) <= 1 else None,
        "totals_by_event_type": sorted(totals_by_event_type.values(), key=lambda row: row["total_amount_usd"], reverse=True),
        "totals_by_blockchain": sorted(totals_by_blockchain.values(), key=lambda row: row["total_amount_usd"], reverse=True),
        "totals_by_strategy": sorted(totals_by_strategy.values(), key=lambda row: row["total_amount_usd"], reverse=True),
        "totals_by_token_symbol": sorted(totals_by_token_symbol.values(), key=lambda row: row["total_amount_usd"], reverse=True),
        "totals_by_underlying_symbol": sorted(
            totals_by_underlying_symbol.values(),
            key=lambda row: row["total_amount_usd"],
            reverse=True,
        ),
    }


def _build_protocol_events_summary_from_queries(
    overview_rows: list[dict],
    totals_by_event_type_rows: list[dict],
    totals_by_blockchain_rows: list[dict],
    totals_by_strategy_rows: list[dict],
    totals_by_token_symbol_rows: list[dict],
    totals_by_underlying_symbol_rows: list[dict],
    project=None,
    strategy_symbol=None,
    strategy_address=None,
    event_type=None,
    start_date=None,
    end_date=None,
) -> dict:
    overview = overview_rows[0] if overview_rows else {}
    return {
        "dataset_name": "dune.ether_fi.result_etherfi_protocol_events",
        "mode": "summary",
        "project": project,
        "strategy_symbol": strategy_symbol,
        "strategy_address": strategy_address,
        "event_type": event_type,
        "date_range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "event_count": int(_to_number(overview.get("event_count"))),
        "latest_block_time": overview.get("latest_block_time"),
        "total_amount_usd": _to_number(overview.get("total_amount_usd")),
        "total_amount_eth": _to_number(overview.get("total_amount_eth")),
        "total_token_amount": _to_number(overview.get("total_token_amount")) if overview.get("single_token_symbol") else None,
        "total_strategy_amount": _to_number(overview.get("total_strategy_amount")) if overview.get("single_strategy_symbol") or overview.get("single_strategy_address") else None,
        "total_amount_underlying": _to_number(overview.get("total_amount_underlying")) if overview.get("single_underlying_symbol") else None,
        "totals_by_event_type": [
            {
                "event_type": row.get("event_type"),
                "event_count": int(_to_number(row.get("event_count"))),
                "total_amount_usd": _to_number(row.get("total_amount_usd")),
                "total_amount_eth": _to_number(row.get("total_amount_eth")),
            }
            for row in totals_by_event_type_rows
        ],
        "totals_by_blockchain": [
            {
                "blockchain": row.get("blockchain"),
                "event_count": int(_to_number(row.get("event_count"))),
                "total_amount_usd": _to_number(row.get("total_amount_usd")),
                "total_amount_eth": _to_number(row.get("total_amount_eth")),
            }
            for row in totals_by_blockchain_rows
        ],
        "totals_by_strategy": [
            {
                "strategy_symbol": row.get("strategy_symbol"),
                "strategy_address": row.get("strategy_address"),
                "event_count": int(_to_number(row.get("event_count"))),
                "total_amount_usd": _to_number(row.get("total_amount_usd")),
                "total_amount_eth": _to_number(row.get("total_amount_eth")),
            }
            for row in totals_by_strategy_rows
        ],
        "totals_by_token_symbol": [
            {
                "token_symbol": row.get("token_symbol"),
                "event_count": int(_to_number(row.get("event_count"))),
                "total_token_amount": _to_number(row.get("total_token_amount")),
                "total_amount_usd": _to_number(row.get("total_amount_usd")),
            }
            for row in totals_by_token_symbol_rows
        ],
        "totals_by_underlying_symbol": [
            {
                "amount_underlying_symbol": row.get("amount_underlying_symbol"),
                "event_count": int(_to_number(row.get("event_count"))),
                "total_amount_underlying": _to_number(row.get("total_amount_underlying")),
                "total_amount_usd": _to_number(row.get("total_amount_usd")),
            }
            for row in totals_by_underlying_symbol_rows
        ],
    }


def _execute_protocol_events_summary_queries(
    table_name: str,
    where_lines: list[str],
    include_event_type_breakdown: bool,
) -> dict:
    where_clause = _format_where_clause(where_lines)
    overview_sql = (
        "SELECT\n"
        "  COUNT(*) AS event_count,\n"
        "  MAX(block_time) AS latest_block_time,\n"
        "  SUM(amount_usd) AS total_amount_usd,\n"
        "  SUM(amount_eth) AS total_amount_eth,\n"
        "  CASE WHEN COUNT(DISTINCT token_symbol) = 1 THEN MAX(token_symbol) ELSE NULL END AS single_token_symbol,\n"
        "  CASE WHEN COUNT(DISTINCT token_symbol) = 1 THEN SUM(token_amount) ELSE NULL END AS total_token_amount,\n"
        "  CASE WHEN COUNT(DISTINCT strategy_symbol) = 1 THEN MAX(strategy_symbol) ELSE NULL END AS single_strategy_symbol,\n"
        "  CASE WHEN COUNT(DISTINCT strategy_address) = 1 THEN MAX(CAST(strategy_address AS varchar)) ELSE NULL END AS single_strategy_address,\n"
        "  CASE WHEN COUNT(DISTINCT amount_underlying_symbol) = 1 THEN MAX(amount_underlying_symbol) ELSE NULL END AS single_underlying_symbol,\n"
        "  CASE WHEN COUNT(DISTINCT amount_underlying_symbol) = 1 THEN SUM(amount_underlying) ELSE NULL END AS total_amount_underlying,\n"
        "  CASE WHEN COUNT(DISTINCT strategy_symbol) = 1 OR COUNT(DISTINCT strategy_address) = 1 THEN SUM(strategy_amount) ELSE NULL END AS total_strategy_amount\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
    )
    totals_by_event_type_sql = (
        "SELECT\n"
        "  event_type,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(amount_usd) AS total_amount_usd,\n"
        "  SUM(amount_eth) AS total_amount_eth\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
        "GROUP BY 1\n"
        "ORDER BY total_amount_usd DESC NULLS LAST, event_type\n"
        "LIMIT 20;"
    )
    totals_by_blockchain_sql = (
        "SELECT\n"
        "  blockchain,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(amount_usd) AS total_amount_usd,\n"
        "  SUM(amount_eth) AS total_amount_eth\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
        "GROUP BY 1\n"
        "ORDER BY total_amount_usd DESC NULLS LAST, blockchain\n"
        "LIMIT 20;"
    )
    totals_by_strategy_sql = (
        "SELECT\n"
        "  strategy_symbol,\n"
        "  strategy_address,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(amount_usd) AS total_amount_usd,\n"
        "  SUM(amount_eth) AS total_amount_eth\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
        "GROUP BY 1, 2\n"
        "ORDER BY total_amount_usd DESC NULLS LAST, strategy_symbol\n"
        "LIMIT 20;"
    )
    totals_by_token_symbol_sql = (
        "SELECT\n"
        "  token_symbol,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(token_amount) AS total_token_amount,\n"
        "  SUM(amount_usd) AS total_amount_usd\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
        "GROUP BY 1\n"
        "ORDER BY total_amount_usd DESC NULLS LAST, token_symbol\n"
        "LIMIT 20;"
    )
    totals_by_underlying_symbol_sql = (
        "SELECT\n"
        "  amount_underlying_symbol,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(amount_underlying) AS total_amount_underlying,\n"
        "  SUM(amount_usd) AS total_amount_usd\n"
        f"FROM {table_name}\n"
        f"{where_clause}"
        "GROUP BY 1\n"
        "ORDER BY total_amount_usd DESC NULLS LAST, amount_underlying_symbol\n"
        "LIMIT 20;"
    )
    return {
        "overview_rows": _execute_dune_sql(overview_sql),
        "totals_by_event_type_rows": _execute_dune_sql(totals_by_event_type_sql) if include_event_type_breakdown else [],
        "totals_by_blockchain_rows": _execute_dune_sql(totals_by_blockchain_sql),
        "totals_by_strategy_rows": _execute_dune_sql(totals_by_strategy_sql),
        "totals_by_token_symbol_rows": _execute_dune_sql(totals_by_token_symbol_sql),
        "totals_by_underlying_symbol_rows": _execute_dune_sql(totals_by_underlying_symbol_sql),
        "overview_sql": overview_sql,
        "totals_by_event_type_sql": totals_by_event_type_sql if include_event_type_breakdown else None,
        "totals_by_blockchain_sql": totals_by_blockchain_sql,
        "totals_by_strategy_sql": totals_by_strategy_sql,
        "totals_by_token_symbol_sql": totals_by_token_symbol_sql,
        "totals_by_underlying_symbol_sql": totals_by_underlying_symbol_sql,
    }


def _get_protocol_events_plan(
    project=None,
    strategy_symbol=None,
    strategy_address=None,
    event_type=None,
    start_date=None,
    end_date=None,
    mode="summary",
    limit=100,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_protocol_events"
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "project": project,
            "strategy_symbol": strategy_symbol,
            "strategy_address": strategy_address,
            "event_type": event_type,
            "start_date": start_date,
            "end_date": end_date,
            "mode": mode,
            "limit": limit,
        }
    freshness_status = dataset_error

    if event_type is not None and event_type not in PROTOCOL_EVENT_TYPES:
        return {
            "error": (
                "event_type must be one of: "
                + ", ".join(sorted(PROTOCOL_EVENT_TYPES))
                + "."
            ),
            "dataset_name": dataset_name,
            "project": project,
            "strategy_symbol": strategy_symbol,
            "strategy_address": strategy_address,
            "event_type": event_type,
            "start_date": start_date,
            "end_date": end_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    try:
        mode_value = _validate_mode(mode)
        limit_value = _validate_limit(limit)
        strategy_address_literal = _normalize_address_literal(strategy_address) if strategy_address else None
        start_date_value = _validate_date_literal(start_date, "start_date") if start_date else None
        end_date_value = _validate_date_literal(end_date, "end_date") if end_date else None
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "project": project,
            "strategy_symbol": strategy_symbol,
            "strategy_address": strategy_address,
            "event_type": event_type,
            "start_date": start_date,
            "end_date": end_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    if start_date_value and end_date_value and start_date_value > end_date_value:
        return {
            "error": "start_date must be on or before end_date.",
            "dataset_name": dataset_name,
            "project": project,
            "strategy_symbol": strategy_symbol,
            "strategy_address": strategy_address,
            "event_type": event_type,
            "start_date": start_date,
            "end_date": end_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    where_lines = _build_protocol_events_where_lines(
        project=project,
        strategy_symbol=strategy_symbol,
        strategy_address_literal=strategy_address_literal,
        event_type=event_type,
        start_date=start_date_value,
        end_date=end_date_value,
    )

    broad_rows_request = (
        mode_value == "rows"
        and strategy_symbol is None
        and strategy_address_literal is None
        and project is None
        and (start_date_value is None or end_date_value is None)
    ) or (
        mode_value == "rows"
        and strategy_symbol is None
        and strategy_address_literal is None
        and start_date_value is not None
        and end_date_value is not None
        and (datetime.strptime(end_date_value, "%Y-%m-%d").date() - datetime.strptime(start_date_value, "%Y-%m-%d").date()).days > 7
        and limit_value > 500
    )
    if broad_rows_request:
        return {
            "error": (
                "Broad rows mode requests are expensive. Prefer strategy_symbol or "
                "strategy_address filters, narrow the date range, or keep limit at 500 or less."
            ),
            "dataset_name": dataset_name,
            "project": project,
            "strategy_symbol": strategy_symbol,
            "strategy_address": strategy_address,
            "event_type": event_type,
            "start_date": start_date_value,
            "end_date": end_date_value,
            "mode": mode_value,
            "limit": limit_value,
            "query_ready": True,
        }

    if mode_value == "rows":
        suggested_sql = (
            "SELECT\n"
            "  blockchain,\n"
            "  project,\n"
            "  block_time,\n"
            "  block_date,\n"
            "  block_number,\n"
            "  tx_hash,\n"
            "  tx_from,\n"
            "  tx_to,\n"
            "  evt_index,\n"
            "  event_type,\n"
            "  event_id,\n"
            "  address,\n"
            "  token_address,\n"
            "  token_symbol,\n"
            "  token_amount,\n"
            "  strategy_address,\n"
            "  strategy_symbol,\n"
            "  strategy_amount,\n"
            "  amount_underlying,\n"
            "  amount_underlying_symbol,\n"
            "  amount_usd,\n"
            "  amount_eth,\n"
            "  last_updated\n"
            f"FROM {table_name}\n"
            + _format_where_clause(where_lines)
            + "ORDER BY block_time DESC NULLS LAST, evt_index DESC NULLS LAST\n"
            + f"LIMIT {limit_value};"
        )
    else:
        suggested_sql = (
            "SELECT\n"
            "  COUNT(*) AS event_count,\n"
            "  MAX(block_time) AS latest_block_time,\n"
            "  SUM(amount_usd) AS total_amount_usd,\n"
            "  SUM(amount_eth) AS total_amount_eth\n"
            f"FROM {table_name}\n"
            + _format_where_clause(where_lines)
        )

    plan = {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "project": project,
        "strategy_symbol": strategy_symbol,
        "strategy_address": strategy_address,
        "event_type": event_type,
        "start_date": start_date_value,
        "end_date": end_date_value,
        "mode": mode_value,
        "limit": limit_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "suggested_sql": suggested_sql,
        "filter_preference_note": (
            "strategy_symbol and strategy_address are usually the best filters for precise protocol event analysis; "
            "project is broader and should usually be secondary."
        ),
        "event_type_semantics": {
            "deposit": "inflow into an ether.fi protocol strategy/product",
            "withdrawal_request": "withdrawal requested but not yet necessarily completed",
            "withdrawal_processed": "withdrawal has been processed/completed",
        },
    }
    if mode_value == "rows":
        plan["rows_mode_note"] = "Summary values in rows mode apply only to the returned rows."
    if not where_lines:
        plan["warning"] = (
            "No filters were provided. Protocol events can be large; prefer strategy_symbol "
            "or strategy_address and add a date range for more focused queries."
        )
    return plan


def _get_protocol_token_tvl_plan(
    strategy_symbol=None,
    strategy_symbols=None,
    strategy_address=None,
    as_of_date=None,
    mode="summary",
    limit=100,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_protocol_token_tvl"
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "as_of_date": as_of_date,
            "mode": mode,
            "limit": limit,
        }
    freshness_status = dataset_error

    if strategy_symbol and strategy_symbols:
        return {
            "error": "Provide either strategy_symbol or strategy_symbols, not both.",
            "dataset_name": dataset_name,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "as_of_date": as_of_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    if not strategy_symbol and not strategy_symbols and not strategy_address:
        return {
            "error": "Provide strategy_symbol, strategy_symbols, or strategy_address.",
            "dataset_name": dataset_name,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "as_of_date": as_of_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    try:
        mode_value = _validate_mode(mode)
        limit_value = _validate_limit(limit)
        strategy_symbols_value = _normalize_string_list(strategy_symbols, "strategy_symbols")
        strategy_address_literal = _normalize_address_literal(strategy_address) if strategy_address else None
        as_of_date_value = _validate_date_literal(as_of_date, "as_of_date") if as_of_date else None
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "as_of_date": as_of_date,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    if mode_value == "rows" and as_of_date_value is None and limit_value > 500:
        return {
            "error": (
                "Rows mode across many days can be expensive. Provide as_of_date or keep limit at 500 or less."
            ),
            "dataset_name": dataset_name,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols_value,
            "strategy_address": strategy_address,
            "as_of_date": as_of_date_value,
            "mode": mode_value,
            "limit": limit_value,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    filter_lines = _build_protocol_token_tvl_where_lines(
        strategy_symbol=strategy_symbol,
        strategy_symbols=strategy_symbols_value,
        strategy_address_literal=strategy_address_literal,
    )
    day_filter = _build_protocol_token_tvl_day_filter(
        table_name,
        filter_lines,
        latest_day_per_strategy=bool(strategy_symbols_value) and as_of_date_value is None,
        as_of_date=as_of_date_value,
    )
    summary_where_lines = [*filter_lines, day_filter]

    if mode_value == "summary":
        suggested_sql = (
            "SELECT\n"
            "  day,\n"
            "  strategy_symbol,\n"
            "  CAST(strategy_address AS varchar) AS strategy_address,\n"
            "  strategy_blockchains,\n"
            "  underlying_asset_symbol,\n"
            "  SUM(token_supply) AS token_supply,\n"
            "  SUM(token_supply_underlying) AS token_supply_underlying,\n"
            "  SUM(token_supply_usd) AS token_supply_usd,\n"
            "  SUM(token_supply_eth) AS token_supply_eth,\n"
            "  SUM(token_supply_btc) AS token_supply_btc,\n"
            "  SUM(token_supply_eigen) AS token_supply_eigen,\n"
            "  SUM(token_supply_hype) AS token_supply_hype,\n"
            "  MAX(usd_rate) AS usd_rate,\n"
            "  MAX(eth_rate) AS eth_rate,\n"
            "  MAX(btc_rate) AS btc_rate,\n"
            "  MAX(eigen_rate) AS eigen_rate,\n"
            "  MAX(hype_rate) AS hype_rate,\n"
            "  MAX(last_updated) AS last_updated\n"
            f"FROM {table_name}\n"
            + _format_where_clause(summary_where_lines)
            + "GROUP BY 1, 2, 3, 4, 5\n"
            + "ORDER BY token_supply_usd DESC NULLS LAST, strategy_symbol, strategy_address\n"
            + f"LIMIT {limit_value};"
        )
    else:
        suggested_sql = (
            "SELECT\n"
            "  day,\n"
            "  strategy_blockchains,\n"
            "  strategy_symbol,\n"
            "  strategy_address,\n"
            "  token_supply,\n"
            "  token_supply_underlying,\n"
            "  underlying_asset_symbol,\n"
            "  eth_rate,\n"
            "  token_supply_eth,\n"
            "  usd_rate,\n"
            "  token_supply_usd,\n"
            "  btc_rate,\n"
            "  token_supply_btc,\n"
            "  eigen_rate,\n"
            "  token_supply_eigen,\n"
            "  hype_rate,\n"
            "  token_supply_hype,\n"
            "  last_updated\n"
            f"FROM {table_name}\n"
            + _format_where_clause(filter_lines)
            + "ORDER BY day DESC NULLS LAST, strategy_symbol ASC, strategy_address ASC\n"
            + f"LIMIT {limit_value};"
        )

    plan = {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "strategy_symbol": strategy_symbol,
        "strategy_symbols": strategy_symbols_value,
        "strategy_address": strategy_address,
        "as_of_date": as_of_date_value,
        "mode": mode_value,
        "limit": limit_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "suggested_sql": suggested_sql,
        "filter_preference_note": (
            "strategy_symbol and strategy_address are usually the best filters for precise protocol TVL analysis."
        ),
        "backing_asset_note": (
            "token_supply_underlying together with underlying_asset_symbol represents the asset backing or peg "
            "for the ether.fi protocol token, for example eETH -> ETH, liquidETH -> ETH, liquidUSD -> USDT, and eBTC -> BTC."
        ),
    }
    if mode_value == "rows":
        plan["rows_mode_note"] = "Summary values in rows mode apply only to the returned rows."
    else:
        plan["summary_mode_note"] = (
            "Summary mode uses SQL to return the latest available day for the selected strategy filter, "
            "or the requested as_of_date when provided."
        )
    return plan


def _get_protocol_token_tvl_timeseries_plan(
    strategy_symbol=None,
    strategy_symbols=None,
    strategy_address=None,
    start_date=None,
    end_date=None,
    period=None,
    granularity="day",
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_protocol_token_tvl"
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "granularity": granularity,
        }
    freshness_status = dataset_error

    if strategy_symbol and strategy_symbols:
        return {
            "error": "Provide either strategy_symbol or strategy_symbols, not both.",
            "dataset_name": dataset_name,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "granularity": granularity,
            "query_ready": True,
        }
    if strategy_address and (strategy_symbol or strategy_symbols):
        return {
            "error": "Provide either strategy_address or strategy_symbol/strategy_symbols, not both.",
            "dataset_name": dataset_name,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "granularity": granularity,
            "query_ready": True,
        }
    if not strategy_symbol and not strategy_symbols and not strategy_address:
        return {
            "error": "Provide strategy_symbol, strategy_symbols, or strategy_address.",
            "dataset_name": dataset_name,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "granularity": granularity,
            "query_ready": True,
        }

    try:
        granularity_value = _validate_protocol_tvl_timeseries_granularity(granularity)
        start_date_value, end_date_value = _resolve_protocol_tvl_timeseries_date_range(
            start_date=start_date,
            end_date=end_date,
            period=period,
            now=now,
        )
        strategy_symbol_value = (
            _normalize_protocol_tvl_strategy_symbol(strategy_symbol, "strategy_symbol")
            if strategy_symbol
            else None
        )
        strategy_symbols_value = _normalize_protocol_tvl_strategy_symbol_list(
            strategy_symbols,
            "strategy_symbols",
        )
        strategy_address_literal = _normalize_address_literal(strategy_address) if strategy_address else None
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "strategy_symbol": strategy_symbol,
            "strategy_symbols": strategy_symbols or [],
            "strategy_address": strategy_address,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "granularity": granularity,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    filter_lines = _build_protocol_token_tvl_where_lines(
        strategy_symbol=strategy_symbol_value,
        strategy_symbols=strategy_symbols_value,
        strategy_address_literal=strategy_address_literal,
    )
    range_filter = (
        f"CAST(day AS DATE) BETWEEN CAST('{start_date_value}' AS DATE) "
        f"AND CAST('{end_date_value}' AS DATE)"
    )
    where_lines = [*filter_lines, range_filter]
    aggregate_scope = "strategy-filtered protocol token TVL history"
    if strategy_address_literal:
        aggregate_scope = "strategy-address filtered protocol token TVL history"
    elif strategy_symbols_value:
        aggregate_scope = "multi-strategy protocol token TVL history"

    if granularity_value == "month":
        daily_sql = (
            "  SELECT\n"
            "    CAST(day AS DATE) AS day,\n"
            "    strategy_symbol,\n"
            "    CAST(strategy_address AS varchar) AS strategy_address,\n"
            "    SUM(token_supply_usd) AS tvl_usd\n"
            f"  FROM {table_name}\n"
            + _format_where_clause(where_lines)
            + "  GROUP BY 1, 2, 3\n"
        )
        suggested_sql = _build_month_end_snapshot_sql(
            daily_cte_sql=daily_sql,
            group_columns=[
                ("strategy_symbol", "strategy_symbol"),
                ("strategy_address", "strategy_address"),
            ],
            output_group_aliases=["strategy_symbol"],
            metric_selects=[
                "CAST(MAX(month_end_days.month_end_day) AS DATE) AS month_end_day",
                "SUM(daily_totals.tvl_usd) AS tvl_usd",
            ],
            order_columns=["month_end_days.month ASC", "month_end_days.strategy_symbol ASC"],
            include_month_end_day=False,
        )
    else:
        suggested_sql = (
            "SELECT\n"
            "  CAST(day AS DATE) AS day,\n"
            "  strategy_symbol,\n"
            "  SUM(token_supply_usd) AS tvl_usd\n"
            f"FROM {table_name}\n"
            + _format_where_clause(where_lines)
            + "GROUP BY 1, 2\n"
            + "ORDER BY day ASC, strategy_symbol ASC;"
        )

    aggregation_logic = (
        "Run one date-range query, filter to the requested strategy symbols or address, and "
        "group by day and strategy_symbol to produce chart-ready USD TVL rows."
    )
    important_caveats = [
        "This uses the same token_supply_usd TVL definition as get_protocol_token_tvl(...).",
        "Daily values depend on the available day-level snapshots in dune.ether_fi.result_etherfi_protocol_token_tvl.",
        "Strategy-level TVL history is different from holder distribution or protocol event flow.",
    ]
    expected_output_fields = ["day", "strategy_symbol", "tvl_usd"]
    if granularity_value == "month":
        aggregation_logic = (
            "Run one date-range query, filter to the requested strategy symbols or address, "
            "then select the latest available daily snapshot in each calendar month per strategy "
            "to return month-end TVL rows."
        )
        important_caveats[1] = (
            "Monthly rows use the latest available daily snapshot in each calendar month per strategy; "
            "month_end_day shows the exact day that supplied the month-end point."
        )
        expected_output_fields = ["month", "strategy_symbol", "month_end_day", "tvl_usd"]

    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "strategy_symbol": strategy_symbol_value,
        "strategy_symbols": strategy_symbols_value,
        "strategy_address": strategy_address_literal,
        "start_date": start_date_value,
        "end_date": end_date_value,
        "period": period,
        "granularity": granularity_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "question_class": "time-series summary",
        "why_chosen": (
            "Uses the main protocol token TVL table because this is a historical range query "
            "about daily USD TVL by strategy, which is a different question class from the "
            "point-in-time backing and snapshot lookup handled by get_protocol_token_tvl(...)."
        ),
        "dataset_choice_note": (
            "This reuses dune.ether_fi.result_etherfi_protocol_token_tvl so the timeseries tool "
            "returns the same token_supply_usd TVL semantics as the snapshot tool."
        ),
        "wrong_alternative_note": (
            "Do not answer historical protocol TVL prompts by looping through dates or stitching "
            "together repeated snapshot calls; this tool is designed to answer the full range with "
            "one aggregate Dune query."
        ),
        "aggregate_scope": aggregate_scope,
        "aggregation_logic": aggregation_logic,
        "monthly_snapshot_rule": (
            "When granularity='month', each row uses the latest available daily snapshot in each "
            "calendar month for the filtered strategy."
        ),
        "important_caveats": important_caveats,
        "expected_output_fields": expected_output_fields,
        "suggested_sql": suggested_sql,
    }


def get_protocol_token_tvl(
    strategy_symbol=None,
    strategy_symbols=None,
    strategy_address=None,
    as_of_date=None,
    mode="summary",
    execute_live=False,
    limit=100,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_protocol_token_tvl_plan(
        strategy_symbol=strategy_symbol,
        strategy_symbols=strategy_symbols,
        strategy_address=strategy_address,
        as_of_date=as_of_date,
        mode=mode,
        limit=limit,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    empty_summary = _build_protocol_token_tvl_summary(
        [],
        strategy_symbol=strategy_symbol,
        strategy_symbols=plan.get("strategy_symbols", strategy_symbols or []),
        strategy_address=strategy_address,
        as_of_date=as_of_date,
        mode=plan.get("mode", mode),
    )
    if not execute_live:
        return {**plan, "summary": empty_summary}
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": empty_summary,
        }
    try:
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": empty_summary,
        }

    if plan["mode"] == "summary":
        return {
            **plan,
            "executed_live": True,
            "row_count": len(rows),
            "rows": [],
            "summary": _build_protocol_token_tvl_summary(
                rows,
                strategy_symbol=strategy_symbol,
                strategy_symbols=plan.get("strategy_symbols", []),
                strategy_address=strategy_address,
                as_of_date=plan["as_of_date"],
                mode="summary",
            ),
            "summary_queries": {"overview_sql": plan["suggested_sql"]},
        }

    return {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "summary": _build_protocol_token_tvl_summary(
            rows,
            strategy_symbol=strategy_symbol,
            strategy_symbols=plan.get("strategy_symbols", []),
            strategy_address=strategy_address,
            as_of_date=plan["as_of_date"],
            mode="rows",
        ),
    }


def get_protocol_token_tvl_timeseries(
    strategy_symbol=None,
    strategy_symbols=None,
    strategy_address=None,
    start_date=None,
    end_date=None,
    period=None,
    granularity="day",
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_protocol_token_tvl_timeseries_plan(
        strategy_symbol=strategy_symbol,
        strategy_symbols=strategy_symbols,
        strategy_address=strategy_address,
        start_date=start_date,
        end_date=end_date,
        period=period,
        granularity=granularity,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    summary = _build_protocol_token_tvl_timeseries_summary(
        [],
        start_date=plan.get("start_date"),
        end_date=plan.get("end_date"),
        period=plan.get("period"),
        strategy_symbol=plan.get("strategy_symbol"),
        strategy_symbols=plan.get("strategy_symbols"),
        strategy_address=plan.get("strategy_address"),
        granularity=plan.get("granularity", granularity),
    )
    if not execute_live:
        return {
            **plan,
            "summary": summary,
            "timeseries": [],
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "timeseries": [],
            "summary": summary,
        }

    try:
        raw_rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "timeseries": [],
            "summary": summary,
        }

    if plan.get("granularity") == "month":
        timeseries = [
            {
                "month": row.get("month"),
                "month_end_day": row.get("month_end_day"),
                "strategy_symbol": row.get("strategy_symbol"),
                "tvl_usd": _to_number(row.get("tvl_usd")),
            }
            for row in raw_rows
        ]
    else:
        timeseries = [
            {
                "day": row.get("day"),
                "strategy_symbol": row.get("strategy_symbol"),
                "tvl_usd": _to_number(row.get("tvl_usd")),
            }
            for row in raw_rows
        ]
    result = {
        **plan,
        "executed_live": True,
        "row_count": len(timeseries),
        "rows": timeseries,
        "timeseries": timeseries,
        "summary": _build_protocol_token_tvl_timeseries_summary(
            timeseries,
            start_date=plan.get("start_date"),
            end_date=plan.get("end_date"),
            period=plan.get("period"),
            strategy_symbol=plan.get("strategy_symbol"),
            strategy_symbols=plan.get("strategy_symbols"),
            strategy_address=plan.get("strategy_address"),
            granularity=plan.get("granularity", granularity),
        ),
    }
    if not timeseries:
        result["warning"] = (
            "No protocol token TVL rows matched the requested range and strategy filters."
        )
    return result


def _validate_price_granularity(granularity: str | None) -> str:
    if granularity is None:
        return "minute"
    if granularity not in {"minute", "daily"}:
        raise ValueError("granularity must be 'minute' or 'daily'.")
    return granularity


def _get_token_price_dataset_name(granularity: str) -> str:
    return (
        "dune.ether_fi.result_tokens_prices_enriched_daily"
        if granularity == "daily"
        else "dune.ether_fi.result_tokens_prices_enriched_minute"
    )


def _get_token_price_time_column(granularity: str) -> str:
    return "day" if granularity == "daily" else "minute"


def _get_token_price_caveats(granularity: str) -> list[str]:
    base_caveats = [
        "`token_usd` is the direct raw USD price.",
        "`token_usd_rate` is the enriched or derived USD fallback price.",
        "The effective USD price should usually be read as `coalesce(token_usd, token_usd_rate)`.",
        "`token_underlying_rate` and `token_underlying_symbol` matter for underlying-value calculations.",
    ]
    if granularity == "minute":
        return [
            "The enriched minute table is incomplete by design and only includes selected active token-minute combinations.",
            "If no minute row is returned, try daily granularity or check `dune.ether_fi.result_tokens_prices_tokens_list` for token coverage.",
            *base_caveats,
        ]
    return [
        "The enriched daily table is usually the safer default for broader historical price lookups.",
        *base_caveats,
    ]


def _build_token_price_summary(row: dict | None, granularity: str) -> dict:
    if not row:
        return {
            "row_count": 0,
            "granularity": granularity,
            "timestamp": None,
            "blockchain": None,
            "token_address": None,
            "token_symbol": None,
            "token_usd": None,
            "token_usd_rate": None,
            "effective_price_usd": None,
            "price_source": None,
            "token_underlying_rate": None,
            "token_underlying_symbol": None,
            "token_weth_rate": None,
            "last_updated": None,
            "missing_result_note": (
                "No price row was returned. For minute lookups, try granularity='daily' "
                "or check `dune.ether_fi.result_tokens_prices_tokens_list` for coverage."
            ) if granularity == "minute" else (
                "No daily enriched price row was returned. Check token coverage in "
                "`dune.ether_fi.result_tokens_prices_tokens_list` and direct feed coverage."
            ),
        }

    token_usd = row.get("token_usd")
    token_usd_rate = row.get("token_usd_rate")
    effective_price = row.get("effective_price_usd")
    if effective_price is None:
        effective_price = token_usd if token_usd is not None else token_usd_rate

    price_source = row.get("price_source")
    if price_source is None:
        if token_usd is not None and token_usd_rate is not None:
            price_source = "direct_and_enriched_available"
        elif token_usd is not None:
            price_source = "direct"
        elif token_usd_rate is not None:
            price_source = "enriched_fallback"

    timestamp_column = _get_token_price_time_column(granularity)
    return {
        "row_count": 1,
        "granularity": granularity,
        "timestamp": row.get(timestamp_column),
        "blockchain": row.get("blockchain"),
        "token_address": row.get("token_address"),
        "token_symbol": row.get("token_symbol"),
        "token_usd": token_usd,
        "token_usd_rate": token_usd_rate,
        "effective_price_usd": effective_price,
        "price_source": price_source,
        "token_underlying_rate": row.get("token_underlying_rate"),
        "token_underlying_symbol": row.get("token_underlying_symbol"),
        "token_weth_rate": row.get("token_weth_rate"),
        "last_updated": row.get("last_updated"),
    }


MAX_TOKEN_PRICE_BATCH_SIZE = 50


def _normalize_token_address_list(token_addresses) -> list[str]:
    if not isinstance(token_addresses, list) or not token_addresses:
        raise ValueError("token_addresses must be a non-empty list of token addresses.")
    if len(token_addresses) > MAX_TOKEN_PRICE_BATCH_SIZE:
        raise ValueError(f"token_addresses cannot contain more than {MAX_TOKEN_PRICE_BATCH_SIZE} addresses.")

    normalized: list[str] = []
    seen: set[str] = set()
    for token_address in token_addresses:
        normalized_address = _normalize_address_literal(token_address)
        if normalized_address not in seen:
            normalized.append(normalized_address)
            seen.add(normalized_address)
    return normalized


def _build_token_prices_batch_summary(rows: list[dict], token_addresses: list[str], granularity: str) -> dict:
    requested_addresses = [address.lower() for address in token_addresses]
    matched_addresses = {
        str(row.get("token_address")).lower()
        for row in rows
        if row.get("token_address") is not None
    }
    missing_tokens = [
        token_address
        for token_address in requested_addresses
        if token_address not in matched_addresses
    ]
    price_source_breakdown: dict[str, int] = {}
    for row in rows:
        price_source = row.get("price_source")
        if price_source is None:
            if row.get("token_usd") is not None and row.get("token_usd_rate") is not None:
                price_source = "direct_and_enriched_available"
            elif row.get("token_usd") is not None:
                price_source = "direct"
            elif row.get("token_usd_rate") is not None:
                price_source = "enriched_fallback"
            else:
                price_source = "missing_price"
        price_source_breakdown[price_source] = price_source_breakdown.get(price_source, 0) + 1

    return {
        "requested_token_count": len(requested_addresses),
        "matched_token_count": len(matched_addresses),
        "missing_token_count": len(missing_tokens),
        "missing_tokens": missing_tokens,
        "price_source_breakdown": price_source_breakdown,
        "granularity": granularity,
        "missing_result_note": (
            "Some requested tokens were not found. Check `dune.ether_fi.result_tokens_prices_tokens_list` "
            "for price-universe coverage."
        ) if missing_tokens else None,
    }


def _get_token_price_plan(
    token_address=None,
    blockchain=None,
    as_of_timestamp=None,
    granularity="minute",
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    try:
        granularity_value = _validate_price_granularity(granularity)
    except ValueError as exc:
        return {
            "error": str(exc),
            "token_address": token_address,
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity,
            "query_ready": False,
        }

    dataset_name = _get_token_price_dataset_name(granularity_value)
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "token_address": token_address,
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity_value,
        }
    freshness_status = dataset_error

    if not token_address:
        return {
            "error": "Provide token_address.",
            "dataset_name": dataset_name,
            "token_address": token_address,
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity_value,
            "query_ready": True,
        }

    try:
        token_address_literal = _normalize_address_literal(token_address)
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain")
            if blockchain
            else None
        )
        as_of_timestamp_value = (
            _validate_timestamp_literal(as_of_timestamp, "as_of_timestamp")
            if as_of_timestamp
            else None
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "token_address": token_address,
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity_value,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    time_column = _get_token_price_time_column(granularity_value)
    where_lines = [f"token_address = {token_address_literal}"]
    if blockchain_value:
        where_lines.append(f"blockchain = '{blockchain_value}'")
    if as_of_timestamp_value:
        where_lines.append(f"{time_column} <= CAST('{as_of_timestamp_value}' AS timestamp)")

    suggested_sql = (
        "SELECT\n"
        f"  {time_column},\n"
        "  blockchain,\n"
        "  token_address,\n"
        "  token_symbol,\n"
        "  token_type,\n"
        "  token_project,\n"
        "  token_usd,\n"
        "  token_usd_rate,\n"
        "  COALESCE(token_usd, token_usd_rate) AS effective_price_usd,\n"
        "  CASE\n"
        "    WHEN token_usd IS NOT NULL AND token_usd_rate IS NOT NULL THEN 'direct_and_enriched_available'\n"
        "    WHEN token_usd IS NOT NULL THEN 'direct'\n"
        "    WHEN token_usd_rate IS NOT NULL THEN 'enriched_fallback'\n"
        "    ELSE NULL\n"
        "  END AS price_source,\n"
        "  token_underlying_rate,\n"
        "  token_underlying_symbol,\n"
        "  token_weth_rate,\n"
        "  last_updated\n"
        f"FROM {table_name}\n"
        + _format_where_clause(where_lines)
        + f"ORDER BY {time_column} DESC NULLS LAST\n"
        + "LIMIT 1;"
    )

    why_chosen = (
        "Minute granularity uses the enriched minute table for recent high-resolution pricing."
        if granularity_value == "minute"
        else "Daily granularity uses the enriched daily table, the safer default for broader historical lookups."
    )
    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "token_address": token_address,
        "blockchain": blockchain_value,
        "as_of_timestamp": as_of_timestamp_value,
        "granularity": granularity_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "why_chosen": why_chosen,
        "caveats": _get_token_price_caveats(granularity_value),
        "expected_output_fields": [
            time_column,
            "blockchain",
            "token_address",
            "token_symbol",
            "token_usd",
            "token_usd_rate",
            "effective_price_usd",
            "price_source",
            "token_underlying_rate",
            "token_underlying_symbol",
            "token_weth_rate",
            "last_updated",
        ],
        "suggested_sql": suggested_sql,
    }


def get_token_price(
    token_address=None,
    blockchain=None,
    as_of_timestamp=None,
    granularity="minute",
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_token_price_plan(
        token_address=token_address,
        blockchain=blockchain,
        as_of_timestamp=as_of_timestamp,
        granularity=granularity,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    empty_summary = _build_token_price_summary(None, plan.get("granularity", granularity))
    if not execute_live:
        return {**plan, "summary": empty_summary}
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": empty_summary,
        }
    try:
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": empty_summary,
        }

    row = rows[0] if rows else None
    summary = _build_token_price_summary(row, plan["granularity"])
    result = {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "summary": summary,
    }
    if plan["granularity"] == "minute":
        result["warning"] = (
            "The enriched minute price table is incomplete by design. If this lookup returned no row, "
            "try granularity='daily' or check `dune.ether_fi.result_tokens_prices_tokens_list`."
        )
    return result


def _get_token_prices_batch_plan(
    token_addresses=None,
    blockchain=None,
    as_of_timestamp=None,
    granularity="daily",
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    try:
        granularity_value = _validate_price_granularity(granularity)
    except ValueError as exc:
        return {
            "error": str(exc),
            "token_addresses": token_addresses or [],
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity,
            "query_ready": False,
        }

    dataset_name = _get_token_price_dataset_name(granularity_value)
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "token_addresses": token_addresses or [],
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity_value,
        }
    freshness_status = dataset_error

    try:
        token_address_values = _normalize_token_address_list(token_addresses)
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain")
            if blockchain
            else None
        )
        as_of_timestamp_value = (
            _validate_timestamp_literal(as_of_timestamp, "as_of_timestamp")
            if as_of_timestamp
            else None
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "token_addresses": token_addresses or [],
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity_value,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    time_column = _get_token_price_time_column(granularity_value)
    token_address_sql = ", ".join(token_address_values)
    where_lines = [f"token_address IN ({token_address_sql})"]
    if blockchain_value:
        where_lines.append(f"blockchain = '{blockchain_value}'")
    if as_of_timestamp_value:
        where_lines.append(f"{time_column} <= CAST('{as_of_timestamp_value}' AS timestamp)")

    suggested_sql = (
        "WITH ranked_prices AS (\n"
        "  SELECT\n"
        f"    {time_column},\n"
        "    blockchain,\n"
        "    token_address,\n"
        "    token_symbol,\n"
        "    token_type,\n"
        "    token_project,\n"
        "    token_usd,\n"
        "    token_usd_rate,\n"
        "    COALESCE(token_usd, token_usd_rate) AS effective_price_usd,\n"
        "    CASE\n"
        "      WHEN token_usd IS NOT NULL AND token_usd_rate IS NOT NULL THEN 'direct_and_enriched_available'\n"
        "      WHEN token_usd IS NOT NULL THEN 'direct'\n"
        "      WHEN token_usd_rate IS NOT NULL THEN 'enriched_fallback'\n"
        "      ELSE NULL\n"
        "    END AS price_source,\n"
        "    token_underlying_rate,\n"
        "    token_underlying_symbol,\n"
        "    token_weth_rate,\n"
        "    last_updated,\n"
        f"    ROW_NUMBER() OVER (PARTITION BY token_address, blockchain ORDER BY {time_column} DESC NULLS LAST) AS price_rank\n"
        f"  FROM {table_name}\n"
        + "  WHERE "
        + "\n    AND ".join(where_lines)
        + "\n)\n"
        "SELECT\n"
        f"  {time_column},\n"
        "  blockchain,\n"
        "  token_address,\n"
        "  token_symbol,\n"
        "  token_type,\n"
        "  token_project,\n"
        "  token_usd,\n"
        "  token_usd_rate,\n"
        "  effective_price_usd,\n"
        "  price_source,\n"
        "  token_underlying_rate,\n"
        "  token_underlying_symbol,\n"
        "  token_weth_rate,\n"
        "  last_updated\n"
        "FROM ranked_prices\n"
        "WHERE price_rank = 1\n"
        "ORDER BY token_symbol, blockchain, token_address;"
    )

    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "token_addresses": token_address_values,
        "blockchain": blockchain_value,
        "as_of_timestamp": as_of_timestamp_value,
        "granularity": granularity_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "why_chosen": (
            "Daily granularity uses the enriched daily table, the safer default for dashboard and batch analysis workflows."
            if granularity_value == "daily"
            else "Minute granularity uses the enriched minute table for recent high-resolution batch pricing."
        ),
        "caveats": _get_token_price_caveats(granularity_value),
        "expected_output_fields": [
            time_column,
            "blockchain",
            "token_address",
            "token_symbol",
            "token_usd",
            "token_usd_rate",
            "effective_price_usd",
            "price_source",
            "token_underlying_rate",
            "token_underlying_symbol",
            "token_weth_rate",
            "last_updated",
        ],
        "suggested_sql": suggested_sql,
    }


def get_token_prices_batch(
    token_addresses=None,
    blockchain=None,
    as_of_timestamp=None,
    granularity="daily",
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_token_prices_batch_plan(
        token_addresses=token_addresses,
        blockchain=blockchain,
        as_of_timestamp=as_of_timestamp,
        granularity=granularity,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    empty_summary = _build_token_prices_batch_summary(
        [],
        plan.get("token_addresses", []),
        plan.get("granularity", granularity),
    )
    if not execute_live:
        return {**plan, "summary": empty_summary}
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": empty_summary,
        }
    try:
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": empty_summary,
        }

    result = {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "summary": _build_token_prices_batch_summary(
            rows,
            plan["token_addresses"],
            plan["granularity"],
        ),
    }
    if plan["granularity"] == "minute":
        result["warning"] = (
            "The enriched minute price table is incomplete by design. Missing batch rows may reflect "
            "the minute exposure filter; try granularity='daily' or check `dune.ether_fi.result_tokens_prices_tokens_list`."
        )
    return result


TOKEN_PRICE_COVERAGE_DATASETS = {
    "price_token_universe": "dune.ether_fi.result_tokens_prices_tokens_list",
    "tokens_traits": "dune.ether_fi.result_tokens_traits",
    "raw_usd_minute": "dune.ether_fi.result_tokens_prices_usd",
    "raw_usd_daily": "dune.ether_fi.result_tokens_prices_usd_daily",
    "enriched_minute": "dune.ether_fi.result_tokens_prices_enriched_minute",
    "enriched_daily": "dune.ether_fi.result_tokens_prices_enriched_daily",
    "exchange_rates_raw": "dune.ether_fi.result_tokens_rates_oracle_pegs",
    "exchange_rates_daily": "dune.ether_fi.result_tokens_exchange_rates_daily",
}


def _truthy(value) -> bool:
    return value in (True, 1, "true", "True")


def _build_price_coverage_where(
    address_column: str,
    token_address_literal: str,
    blockchain_column: str,
    blockchain_value: str | None,
) -> str:
    where_lines = [f"{address_column} = {token_address_literal}"]
    if blockchain_value:
        where_lines.append(f"{blockchain_column} = '{blockchain_value}'")
    return "WHERE " + "\n    AND ".join(where_lines)


def _build_price_coverage_aggregate_cte(
    cte_name: str,
    table_name: str,
    timestamp_column: str,
    address_column: str,
    token_address_literal: str,
    blockchain_column: str,
    blockchain_value: str | None,
) -> str:
    return (
        f"{cte_name} AS (\n"
        "  SELECT\n"
        "    COUNT(*) AS row_count,\n"
        f"    MAX({timestamp_column}) AS latest_observed_timestamp\n"
        f"  FROM {table_name}\n"
        "  "
        + _build_price_coverage_where(
            address_column,
            token_address_literal,
            blockchain_column,
            blockchain_value,
        )
        + "\n)"
    )


def _build_token_price_coverage_sql(
    tables: dict[str, str],
    token_address_literal: str,
    blockchain_value: str | None,
) -> str:
    ctes = [
        _build_price_coverage_aggregate_cte(
            "price_token_universe",
            tables["price_token_universe"],
            "last_updated",
            "token_address",
            token_address_literal,
            "blockchain",
            blockchain_value,
        ),
        _build_price_coverage_aggregate_cte(
            "tokens_traits",
            tables["tokens_traits"],
            "last_updated",
            "token_address",
            token_address_literal,
            "blockchain",
            blockchain_value,
        ),
        _build_price_coverage_aggregate_cte(
            "raw_usd_minute",
            tables["raw_usd_minute"],
            "minute",
            "contract_address",
            token_address_literal,
            "blockchain",
            blockchain_value,
        ),
        _build_price_coverage_aggregate_cte(
            "raw_usd_daily",
            tables["raw_usd_daily"],
            "day",
            "contract_address",
            token_address_literal,
            "blockchain",
            blockchain_value,
        ),
        _build_price_coverage_aggregate_cte(
            "enriched_minute",
            tables["enriched_minute"],
            "minute",
            "token_address",
            token_address_literal,
            "blockchain",
            blockchain_value,
        ),
        _build_price_coverage_aggregate_cte(
            "enriched_daily",
            tables["enriched_daily"],
            "day",
            "token_address",
            token_address_literal,
            "blockchain",
            blockchain_value,
        ),
        _build_price_coverage_aggregate_cte(
            "exchange_rates_raw",
            tables["exchange_rates_raw"],
            "block_time",
            "token_address",
            token_address_literal,
            "token_blockchain",
            blockchain_value,
        ),
        _build_price_coverage_aggregate_cte(
            "exchange_rates_daily",
            tables["exchange_rates_daily"],
            "day",
            "token_address",
            token_address_literal,
            "token_blockchain",
            blockchain_value,
        ),
    ]
    return (
        "WITH\n"
        + ",\n".join(ctes)
        + "\nSELECT\n"
        "  price_token_universe.row_count > 0 AS in_price_token_universe,\n"
        "  tokens_traits.row_count > 0 AS in_tokens_traits,\n"
        "  raw_usd_minute.row_count > 0 AS has_raw_usd_minute,\n"
        "  raw_usd_daily.row_count > 0 AS has_raw_usd_daily,\n"
        "  enriched_minute.row_count > 0 AS has_enriched_minute,\n"
        "  enriched_daily.row_count > 0 AS has_enriched_daily,\n"
        "  exchange_rates_raw.row_count > 0 AS has_exchange_rates_raw,\n"
        "  exchange_rates_daily.row_count > 0 AS has_exchange_rates_daily,\n"
        "  price_token_universe.latest_observed_timestamp AS price_token_universe_latest_observed_timestamp,\n"
        "  tokens_traits.latest_observed_timestamp AS tokens_traits_latest_observed_timestamp,\n"
        "  raw_usd_minute.latest_observed_timestamp AS raw_usd_minute_latest_observed_timestamp,\n"
        "  raw_usd_daily.latest_observed_timestamp AS raw_usd_daily_latest_observed_timestamp,\n"
        "  enriched_minute.latest_observed_timestamp AS enriched_minute_latest_observed_timestamp,\n"
        "  enriched_daily.latest_observed_timestamp AS enriched_daily_latest_observed_timestamp,\n"
        "  exchange_rates_raw.latest_observed_timestamp AS exchange_rates_raw_latest_observed_timestamp,\n"
        "  exchange_rates_daily.latest_observed_timestamp AS exchange_rates_daily_latest_observed_timestamp\n"
        "FROM price_token_universe\n"
        "CROSS JOIN tokens_traits\n"
        "CROSS JOIN raw_usd_minute\n"
        "CROSS JOIN raw_usd_daily\n"
        "CROSS JOIN enriched_minute\n"
        "CROSS JOIN enriched_daily\n"
        "CROSS JOIN exchange_rates_raw\n"
        "CROSS JOIN exchange_rates_daily;"
    )


def _build_price_coverage_checks(row: dict) -> dict:
    return {
        "in_price_token_universe": _truthy(row.get("in_price_token_universe")),
        "in_tokens_traits": _truthy(row.get("in_tokens_traits")),
        "has_raw_usd_minute": _truthy(row.get("has_raw_usd_minute")),
        "has_raw_usd_daily": _truthy(row.get("has_raw_usd_daily")),
        "has_enriched_minute": _truthy(row.get("has_enriched_minute")),
        "has_enriched_daily": _truthy(row.get("has_enriched_daily")),
        "has_exchange_rates_raw": _truthy(row.get("has_exchange_rates_raw")),
        "has_exchange_rates_daily": _truthy(row.get("has_exchange_rates_daily")),
    }


def _build_price_coverage_latest_timestamps(row: dict) -> dict:
    return {
        "price_token_universe": row.get("price_token_universe_latest_observed_timestamp"),
        "tokens_traits": row.get("tokens_traits_latest_observed_timestamp"),
        "raw_usd_minute": row.get("raw_usd_minute_latest_observed_timestamp"),
        "raw_usd_daily": row.get("raw_usd_daily_latest_observed_timestamp"),
        "enriched_minute": row.get("enriched_minute_latest_observed_timestamp"),
        "enriched_daily": row.get("enriched_daily_latest_observed_timestamp"),
        "exchange_rates_raw": row.get("exchange_rates_raw_latest_observed_timestamp"),
        "exchange_rates_daily": row.get("exchange_rates_daily_latest_observed_timestamp"),
    }


def _build_price_coverage_explanation(checks: dict) -> str:
    has_raw_usd = checks["has_raw_usd_minute"] or checks["has_raw_usd_daily"]
    has_enriched = checks["has_enriched_minute"] or checks["has_enriched_daily"]
    has_exchange_rates = checks["has_exchange_rates_raw"] or checks["has_exchange_rates_daily"]

    if not checks["in_price_token_universe"]:
        return "This token may not yet be included in the ether.fi price-token universe."
    if not has_raw_usd and not has_enriched and not has_exchange_rates:
        return "The token is in the price-token universe, but currently lacks usable downstream raw, enriched, or exchange-rate coverage."
    if checks["has_enriched_daily"] and not checks["has_enriched_minute"]:
        return "Daily enriched price coverage exists, but minute enriched coverage is missing; this can happen because the minute table is incomplete by design."
    if has_exchange_rates and not has_raw_usd:
        return "Exchange-rate coverage exists, but direct USD price coverage appears unavailable; underlying-rate coverage is not the same as a USD price feed."
    if has_enriched and not has_raw_usd:
        return "Enriched price coverage exists, but direct raw USD price coverage appears unavailable."
    return "The token has at least one usable price coverage path in the checked ether.fi price datasets."


def _build_price_coverage_next_steps(checks: dict) -> list[str]:
    next_steps = []
    if not checks["in_price_token_universe"]:
        next_steps.append("Check whether the token should be added to `dune.ether_fi.result_tokens_prices_tokens_list` source inputs.")
    if checks["has_enriched_daily"] and not checks["has_enriched_minute"]:
        next_steps.append("Use daily granularity with `get_token_price` or `get_token_prices_batch` when minute coverage is missing.")
    if not (checks["has_raw_usd_minute"] or checks["has_raw_usd_daily"]):
        next_steps.append("Check direct USD price feed coverage in `result_tokens_prices_usd` and `result_tokens_prices_usd_daily`.")
    if checks["has_exchange_rates_raw"] or checks["has_exchange_rates_daily"]:
        next_steps.append("Remember that `result_tokens_rates_oracle_pegs` is an exchange-rate table, not a USD price table.")
    if not next_steps:
        next_steps.append("Use `get_token_price` for a single-token lookup or `get_token_prices_batch` for a small token basket.")
    next_steps.append("If coverage is missing unexpectedly, inspect token metadata with `find_price_tokens`.")
    return next_steps


def _build_price_coverage_summary(checks: dict) -> dict:
    return {
        "in_price_token_universe": checks["in_price_token_universe"],
        "has_any_raw_usd_price": checks["has_raw_usd_minute"] or checks["has_raw_usd_daily"],
        "has_any_enriched_price": checks["has_enriched_minute"] or checks["has_enriched_daily"],
        "has_any_exchange_rate": checks["has_exchange_rates_raw"] or checks["has_exchange_rates_daily"],
        "minute_enriched_missing_but_daily_exists": checks["has_enriched_daily"] and not checks["has_enriched_minute"],
    }


def _get_token_price_coverage_plan(
    token_address=None,
    blockchain=None,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    if not token_address:
        return {
            "error": "Provide token_address.",
            "token_address": token_address,
            "blockchain": blockchain,
            "query_ready": True,
        }

    catalog = datasets or load_datasets()
    freshness_data = freshness_registry
    dataset_details: dict[str, dict] = {}
    tables: dict[str, str] = {}
    for key, dataset_name in TOKEN_PRICE_COVERAGE_DATASETS.items():
        dataset, dataset_error = _get_query_ready_dataset(
            dataset_name,
            datasets=catalog,
            freshness_registry=freshness_data,
            now=now,
        )
        if dataset is None:
            return {
                **dataset_error,
                "token_address": token_address,
                "blockchain": blockchain,
                "dataset_key": key,
            }
        dataset_details[key] = {
            "dataset_name": dataset_name,
            "table_name": dataset["table_name"],
            "freshness_status": dataset_error,
        }
        tables[key] = dataset["table_name"]

    try:
        token_address_literal = _normalize_address_literal(token_address)
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain")
            if blockchain
            else None
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "token_address": token_address,
            "blockchain": blockchain,
            "query_ready": True,
        }

    suggested_sql = _build_token_price_coverage_sql(
        tables,
        token_address_literal,
        blockchain_value,
    )
    return {
        "token_address": token_address_literal,
        "blockchain": blockchain_value,
        "query_ready": True,
        "datasets_checked": dataset_details,
        "check_meanings": {
            "in_price_token_universe": "`result_tokens_prices_tokens_list` includes the token in the intended ether.fi price universe, but this does not guarantee a usable price.",
            "has_raw_usd_minute": "`result_tokens_prices_usd` has direct/raw minute USD price rows.",
            "has_raw_usd_daily": "`result_tokens_prices_usd_daily` has direct/raw daily USD price rows.",
            "has_enriched_minute": "`result_tokens_prices_enriched_minute` has enriched minute rows; this table is incomplete by design.",
            "has_enriched_daily": "`result_tokens_prices_enriched_daily` has enriched daily rows and is often the better fallback when minute rows are missing.",
            "has_exchange_rates_raw": "`result_tokens_rates_oracle_pegs` has token-to-underlying exchange rates; it is not a USD price table.",
            "has_exchange_rates_daily": "`result_tokens_exchange_rates_daily` has daily token-to-underlying exchange rates.",
        },
        "caveats": [
            "`result_tokens_prices_tokens_list` defines the intended price-token universe, but inclusion there does not guarantee a usable price.",
            "`result_tokens_prices_enriched_minute` is incomplete by design because minute rows are filtered to recent protocol/Veda token-minute activity.",
            "`result_tokens_rates_oracle_pegs` is an exchange-rate table, not a USD price table.",
            "A token may have exchange-rate coverage without direct USD price coverage.",
            "Daily enriched prices are often a better fallback when minute enriched coverage is missing.",
        ],
        "expected_output_fields": [
            "checks",
            "latest_observed_timestamps",
            "summary",
            "likely_explanation",
            "suggested_next_steps",
        ],
        "suggested_sql": suggested_sql,
    }


def diagnose_token_price_coverage(
    token_address=None,
    blockchain=None,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_token_price_coverage_plan(
        token_address=token_address,
        blockchain=blockchain,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        return {
            **plan,
            "summary": {
                "mode": "planning",
                "message": "Live mode will run narrow coverage checks across the ether.fi token universe, raw USD, enriched price, and exchange-rate datasets.",
            },
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "checks": {},
            "latest_observed_timestamps": {},
            "summary": {},
            "suggested_next_steps": [],
        }
    try:
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "checks": {},
            "latest_observed_timestamps": {},
            "summary": {},
            "suggested_next_steps": [],
        }
    row = rows[0] if rows else {}
    checks = _build_price_coverage_checks(row)
    return {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "checks": checks,
        "latest_observed_timestamps": _build_price_coverage_latest_timestamps(row),
        "summary": _build_price_coverage_summary(checks),
        "likely_explanation": _build_price_coverage_explanation(checks),
        "suggested_next_steps": _build_price_coverage_next_steps(checks),
    }


def _build_find_price_tokens_summary(rows: list[dict], token_symbol=None, token_project=None, blockchain=None) -> dict:
    candidate_count = len(rows)
    blockchains = sorted(
        {row.get("blockchain") for row in rows if row.get("blockchain") not in (None, "")}
    )
    token_symbols = sorted(
        {row.get("token_symbol") for row in rows if row.get("token_symbol") not in (None, "")}
    )
    in_price_universe_count = sum(
        1
        for row in rows
        if row.get("in_price_token_universe") in (True, 1, "true", "True")
    )
    return {
        "candidate_count": candidate_count,
        "token_symbol": token_symbol,
        "token_project": token_project,
        "blockchain": blockchain,
        "token_symbols": token_symbols,
        "blockchains": blockchains,
        "in_price_token_universe_count": in_price_universe_count,
        "candidate_note": (
            f"Found {candidate_count} likely token candidate"
            + ("" if candidate_count == 1 else "s")
            + (
                f" across {', '.join(blockchains)}."
                if blockchains
                else "."
            )
        ),
        "next_step": (
            "Use a returned token_address and blockchain with "
            "`get_token_price(token_address=..., blockchain=...)`."
        ),
    }


def _get_find_price_tokens_plan(
    token_symbol=None,
    token_project=None,
    blockchain=None,
    limit=20,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    traits_dataset_name = "dune.ether_fi.result_tokens_traits"
    price_list_dataset_name = "dune.ether_fi.result_tokens_prices_tokens_list"
    traits_dataset, traits_error = _get_query_ready_dataset(
        traits_dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    price_list_dataset, price_list_error = _get_query_ready_dataset(
        price_list_dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if traits_dataset is None:
        return {
            **traits_error,
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain,
            "limit": limit,
        }
    if price_list_dataset is None:
        return {
            **price_list_error,
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain,
            "limit": limit,
        }

    if not token_symbol and not token_project and not blockchain:
        return {
            "error": "Provide token_symbol, token_project, or blockchain.",
            "dataset_name": traits_dataset_name,
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain,
            "limit": limit,
            "query_ready": True,
        }

    try:
        limit_value = _validate_limit(limit, default=20)
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain")
            if blockchain
            else None
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": traits_dataset_name,
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain,
            "limit": limit,
            "query_ready": True,
        }

    where_lines: list[str] = []
    exact_symbol_order = "1"
    if token_symbol:
        token_symbol_literal = _quote_sql_string(token_symbol)
        token_symbol_like_literal = _quote_sql_string(f"%{token_symbol}%")
        where_lines.append(f"LOWER(token_symbol) LIKE LOWER({token_symbol_like_literal})")
        exact_symbol_order = f"CASE WHEN LOWER(token_symbol) = LOWER({token_symbol_literal}) THEN 0 ELSE 1 END"
    if token_project:
        token_project_like_literal = _quote_sql_string(f"%{token_project}%")
        where_lines.append(f"LOWER(token_project) LIKE LOWER({token_project_like_literal})")
    if blockchain_value:
        where_lines.append(f"blockchain = '{blockchain_value}'")

    traits_table_name = traits_dataset["table_name"]
    price_list_table_name = price_list_dataset["table_name"]
    suggested_sql = (
        "WITH token_candidates AS (\n"
        "  SELECT DISTINCT\n"
        "    token_address,\n"
        "    blockchain,\n"
        "    token_symbol,\n"
        "    token_project,\n"
        "    token_type,\n"
        "    last_updated\n"
        f"  FROM {traits_table_name}\n"
        + ("  WHERE " + "\n    AND ".join(where_lines) + "\n" if where_lines else "")
        + "),\n"
        + "price_universe AS (\n"
        "  SELECT DISTINCT\n"
        "    token_address,\n"
        "    blockchain\n"
        f"  FROM {price_list_table_name}\n"
        ")\n"
        "SELECT\n"
        "  t.token_address,\n"
        "  t.blockchain,\n"
        "  t.token_symbol,\n"
        "  t.token_project,\n"
        "  t.token_type,\n"
        "  p.token_address IS NOT NULL AS in_price_token_universe,\n"
        "  t.last_updated\n"
        "FROM token_candidates t\n"
        "LEFT JOIN price_universe p\n"
        "  ON t.token_address = p.token_address\n"
        "  AND t.blockchain = p.blockchain\n"
        f"ORDER BY {exact_symbol_order}, CASE WHEN p.token_address IS NOT NULL THEN 0 ELSE 1 END, t.blockchain, t.token_symbol\n"
        f"LIMIT {limit_value};"
    )

    return {
        "dataset_name": traits_dataset_name,
        "table_name": traits_table_name,
        "coverage_dataset_name": price_list_dataset_name,
        "coverage_table_name": price_list_table_name,
        "token_symbol": token_symbol,
        "token_project": token_project,
        "blockchain": blockchain_value,
        "limit": limit_value,
        "query_ready": True,
        "grain": traits_dataset.get("grain"),
        "freshness_status": traits_error,
        "coverage_freshness_status": price_list_error,
        "why_chosen": (
            "Uses token traits to resolve likely token metadata candidates and "
            "left joins the ether.fi price token universe to flag price coverage."
        ),
        "expected_output_fields": [
            "token_address",
            "blockchain",
            "token_symbol",
            "token_project",
            "token_type",
            "in_price_token_universe",
            "last_updated",
        ],
        "next_step": (
            "Use a candidate token_address and blockchain with "
            "`get_token_price(token_address=..., blockchain=...)`."
        ),
        "suggested_sql": suggested_sql,
    }


def find_price_tokens(
    token_symbol=None,
    token_project=None,
    blockchain=None,
    limit=20,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_find_price_tokens_plan(
        token_symbol=token_symbol,
        token_project=token_project,
        blockchain=blockchain,
        limit=limit,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    empty_summary = _build_find_price_tokens_summary(
        [],
        token_symbol=token_symbol,
        token_project=token_project,
        blockchain=plan.get("blockchain", blockchain),
    )
    if not execute_live:
        return {**plan, "summary": empty_summary}
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": empty_summary,
        }
    try:
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": empty_summary,
        }
    return {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "summary": _build_find_price_tokens_summary(
            rows,
            token_symbol=token_symbol,
            token_project=token_project,
            blockchain=plan.get("blockchain"),
        ),
    }


def _normalize_match_value(value) -> str:
    return str(value).strip().lower() if value is not None else ""


def _build_token_price_by_symbol_planning_summary(token_symbol, token_project=None, blockchain=None, granularity="minute") -> dict:
    return {
        "outcome": "planning",
        "token_symbol": token_symbol,
        "token_project": token_project,
        "blockchain": blockchain,
        "granularity": granularity,
        "steps": [
            "discover token candidates with `find_price_tokens`",
            "keep only exact normalized token_symbol matches when available",
            "fetch price with `get_token_price` only when exactly one strong candidate remains",
            "return candidate rows for disambiguation instead of guessing when multiple candidates remain",
        ],
        "possible_outcomes": [
            "resolved_and_priced",
            "needs_disambiguation",
            "no_match",
        ],
    }


def _candidate_summary_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "token_address": row.get("token_address"),
            "blockchain": row.get("blockchain"),
            "token_symbol": row.get("token_symbol"),
            "token_project": row.get("token_project"),
            "token_type": row.get("token_type"),
            "in_price_token_universe": row.get("in_price_token_universe"),
        }
        for row in rows
    ]


def _get_exact_symbol_candidates(rows: list[dict], token_symbol: str) -> list[dict]:
    normalized_symbol = _normalize_match_value(token_symbol)
    return [
        row
        for row in rows
        if _normalize_match_value(row.get("token_symbol")) == normalized_symbol
    ]


def get_token_price_by_symbol(
    token_symbol=None,
    blockchain=None,
    token_project=None,
    as_of_timestamp=None,
    granularity="minute",
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    if not token_symbol:
        return {
            "error": "Provide token_symbol.",
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity,
            "query_ready": True,
        }
    try:
        granularity_value = _validate_price_granularity(granularity)
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain")
            if blockchain
            else None
        )
        as_of_timestamp_value = (
            _validate_timestamp_literal(as_of_timestamp, "as_of_timestamp")
            if as_of_timestamp
            else None
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain,
            "as_of_timestamp": as_of_timestamp,
            "granularity": granularity,
            "query_ready": True,
        }

    discovery_plan = find_price_tokens(
        token_symbol=token_symbol,
        token_project=token_project,
        blockchain=blockchain_value,
        limit=20,
        execute_live=False,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        return {
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain_value,
            "as_of_timestamp": as_of_timestamp_value,
            "granularity": granularity_value,
            "query_ready": not bool(discovery_plan.get("error")),
            "executed_live": False,
            "outcome": "planning",
            "summary": _build_token_price_by_symbol_planning_summary(
                token_symbol,
                token_project=token_project,
                blockchain=blockchain_value,
                granularity=granularity_value,
            ),
            "discovery_plan": discovery_plan,
            "expected_output_fields": [
                "outcome",
                "resolved_token",
                "candidates",
                "price_rows",
                "price_summary",
            ],
            "caveats": [
                "This helper does not guess when multiple plausible token candidates remain.",
                "Minute price lookups inherit the enriched minute table completeness caveat.",
                "Effective USD price follows `coalesce(token_usd, token_usd_rate)` from `get_token_price`.",
            ],
        }

    discovery_result = find_price_tokens(
        token_symbol=token_symbol,
        token_project=token_project,
        blockchain=blockchain_value,
        limit=20,
        execute_live=True,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if discovery_result.get("error"):
        return {
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain_value,
            "as_of_timestamp": as_of_timestamp_value,
            "granularity": granularity_value,
            "query_ready": discovery_result.get("query_ready", False),
            "executed_live": False,
            "outcome": "error",
            "error": discovery_result["error"],
            "discovery_result": discovery_result,
        }

    candidates = discovery_result.get("rows", [])
    if not candidates:
        return {
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain_value,
            "as_of_timestamp": as_of_timestamp_value,
            "granularity": granularity_value,
            "query_ready": True,
            "executed_live": True,
            "outcome": "no_match",
            "candidates": [],
            "summary": {
                "candidate_count": 0,
                "message": "No token candidates were found for the provided filters.",
                "suggestions": [
                    "Try a different token_symbol spelling.",
                    "Add or adjust blockchain.",
                    "Add or adjust token_project.",
                ],
            },
            "discovery_result": discovery_result,
        }

    exact_candidates = _get_exact_symbol_candidates(candidates, token_symbol)
    if len(exact_candidates) != 1:
        disambiguation_candidates = exact_candidates if exact_candidates else candidates
        return {
            "token_symbol": token_symbol,
            "token_project": token_project,
            "blockchain": blockchain_value,
            "as_of_timestamp": as_of_timestamp_value,
            "granularity": granularity_value,
            "query_ready": True,
            "executed_live": True,
            "outcome": "needs_disambiguation",
            "candidates": _candidate_summary_rows(disambiguation_candidates),
            "summary": {
                "candidate_count": len(disambiguation_candidates),
                "exact_candidate_count": len(exact_candidates),
                "message": (
                    "Multiple exact token candidates were found; specify blockchain or token_project."
                    if exact_candidates
                    else "Token candidates were found, but none exactly matched token_symbol; specify a more exact token_symbol, blockchain, or token_project."
                ),
                "suggestions": [
                    "Specify blockchain.",
                    "Specify token_project.",
                    "Use `find_price_tokens` to inspect candidates before pricing.",
                ],
            },
            "discovery_result": discovery_result,
        }

    resolved_token = exact_candidates[0]
    price_result = get_token_price(
        token_address=resolved_token.get("token_address"),
        blockchain=resolved_token.get("blockchain"),
        as_of_timestamp=as_of_timestamp_value,
        granularity=granularity_value,
        execute_live=True,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    return {
        "token_symbol": token_symbol,
        "token_project": token_project,
        "blockchain": blockchain_value,
        "as_of_timestamp": as_of_timestamp_value,
        "granularity": granularity_value,
        "query_ready": True,
        "executed_live": True,
        "outcome": "resolved_and_priced",
        "resolved_token": _candidate_summary_rows([resolved_token])[0],
        "price_rows": price_result.get("rows", []),
        "price_summary": price_result.get("summary", {}),
        "price_result": price_result,
        "discovery_result": discovery_result,
    }


def get_protocol_events(
    project=None,
    strategy_symbol=None,
    strategy_address=None,
    event_type=None,
    start_date=None,
    end_date=None,
    mode="summary",
    execute_live=False,
    limit=100,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_protocol_events_plan(
        project=project,
        strategy_symbol=strategy_symbol,
        strategy_address=strategy_address,
        event_type=event_type,
        start_date=start_date,
        end_date=end_date,
        mode=mode,
        limit=limit,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        return {
            **plan,
            "summary": _build_protocol_events_rows_summary(
                [],
                project=project,
                strategy_symbol=strategy_symbol,
                strategy_address=strategy_address,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
            ) if mode == "rows" else _build_protocol_events_summary_from_queries(
                [],
                [],
                [],
                [],
                [],
                [],
                project=project,
                strategy_symbol=strategy_symbol,
                strategy_address=strategy_address,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_protocol_events_rows_summary(
                [],
                project=project,
                strategy_symbol=strategy_symbol,
                strategy_address=strategy_address,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
            ) if plan.get("mode") == "rows" else _build_protocol_events_summary_from_queries(
                [],
                [],
                [],
                [],
                [],
                [],
                project=project,
                strategy_symbol=strategy_symbol,
                strategy_address=strategy_address,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    try:
        strategy_address_literal = _normalize_address_literal(strategy_address) if strategy_address else None
        where_lines = _build_protocol_events_where_lines(
            project=project,
            strategy_symbol=strategy_symbol,
            strategy_address_literal=strategy_address_literal,
            event_type=event_type,
            start_date=plan["start_date"],
            end_date=plan["end_date"],
        )
        if plan["mode"] == "summary":
            summary_queries = _execute_protocol_events_summary_queries(
                plan["table_name"],
                where_lines,
                include_event_type_breakdown=event_type is None,
            )
            summary = _build_protocol_events_summary_from_queries(
                summary_queries["overview_rows"],
                summary_queries["totals_by_event_type_rows"],
                summary_queries["totals_by_blockchain_rows"],
                summary_queries["totals_by_strategy_rows"],
                summary_queries["totals_by_token_symbol_rows"],
                summary_queries["totals_by_underlying_symbol_rows"],
                project=project,
                strategy_symbol=strategy_symbol,
                strategy_address=strategy_address,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
            )
            return {
                **plan,
                "executed_live": True,
                "row_count": summary["event_count"],
                "rows": [],
                "summary": summary,
                "summary_queries": {
                    "overview_sql": summary_queries["overview_sql"],
                    "totals_by_event_type_sql": summary_queries["totals_by_event_type_sql"],
                    "totals_by_blockchain_sql": summary_queries["totals_by_blockchain_sql"],
                    "totals_by_strategy_sql": summary_queries["totals_by_strategy_sql"],
                    "totals_by_token_symbol_sql": summary_queries["totals_by_token_symbol_sql"],
                    "totals_by_underlying_symbol_sql": summary_queries["totals_by_underlying_symbol_sql"],
                },
            }
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_protocol_events_rows_summary(
                [],
                project=project,
                strategy_symbol=strategy_symbol,
                strategy_address=strategy_address,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
            ) if plan["mode"] == "rows" else _build_protocol_events_summary_from_queries(
                [],
                [],
                [],
                [],
                [],
                [],
                project=project,
                strategy_symbol=strategy_symbol,
                strategy_address=strategy_address,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
            ),
        }
    return {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "summary": _build_protocol_events_rows_summary(
            rows,
            project=project,
            strategy_symbol=strategy_symbol,
            strategy_address=strategy_address,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
        ),
    }


def _get_protocol_token_holders_plan(
    address=None,
    token_symbol=None,
    token_address=None,
    as_of_date=None,
    include_defi=False,
    exclude_identified_defi=False,
    mode="summary",
    limit=100,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = (
        "etherfi_protocol_token_holders_with_defi"
        if include_defi
        else "etherfi_protocol_token_holders"
    )
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "address": address,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "as_of_date": as_of_date,
            "include_defi": include_defi,
            "exclude_identified_defi": exclude_identified_defi,
            "limit": limit,
        }
    freshness_status = dataset_error

    if not address and not token_symbol and not token_address:
        return {
            "error": "Provide address, token_symbol, or token_address.",
            "dataset_name": dataset_name,
            "address": address,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "as_of_date": as_of_date,
            "include_defi": include_defi,
            "exclude_identified_defi": exclude_identified_defi,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }
    if exclude_identified_defi and not include_defi:
        return {
            "error": "exclude_identified_defi can only be used when include_defi=True.",
            "dataset_name": dataset_name,
            "address": address,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "as_of_date": as_of_date,
            "include_defi": include_defi,
            "exclude_identified_defi": exclude_identified_defi,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    try:
        mode_value = _validate_mode(mode)
        limit_value = _validate_limit(limit)
        address_literal = _normalize_address_literal(address) if address else None
        token_symbol_value = _validate_simple_string_literal(token_symbol, "token_symbol") if token_symbol else None
        token_address_literal = _normalize_address_literal(token_address) if token_address else None
        as_of_date_value = _validate_date_literal(as_of_date, "as_of_date") if as_of_date else None
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "address": address,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "as_of_date": as_of_date,
            "include_defi": include_defi,
            "exclude_identified_defi": exclude_identified_defi,
            "mode": mode,
            "limit": limit,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    filter_lines = _build_protocol_token_holders_base_filter_lines(
        token_symbol=token_symbol_value,
        token_address_literal=token_address_literal,
        include_defi=include_defi,
        exclude_identified_defi=exclude_identified_defi,
    )

    day_filter = (
        f"CAST(day AS DATE) = CAST('{as_of_date_value}' AS DATE)"
        if as_of_date_value
        else (
            "day = ("
            f"SELECT MAX(day) FROM {table_name}"
            + ("\nWHERE " + "\n  AND ".join(filter_lines) if filter_lines else "")
            + "\n)"
        )
    )
    where_lines = [*filter_lines, day_filter]
    if address_literal:
        suggested_sql = _build_protocol_address_holdings_sql(
            table_name,
            address_literal,
            token_symbol=token_symbol_value,
            token_address_literal=token_address_literal,
            as_of_date=as_of_date_value,
            include_defi=include_defi,
            exclude_identified_defi=exclude_identified_defi,
            limit=limit_value,
        )
    elif mode_value == "rows":
        suggested_sql = None
    else:
        suggested_sql = (
            "SELECT\n"
            "  COUNT(*) AS holder_count,\n"
            "  SUM(token_balance) AS total_token_balance\n"
            f"FROM {table_name}\n"
            + "WHERE "
            + "\n  AND ".join(where_lines)
        )

    if mode_value == "rows" and not address_literal:
        select_lines = [
            "  day,",
            "  blockchain,",
            "  address,",
            "  token_address,",
            "  token_symbol,",
            "  token_balance_raw,",
            "  token_balance,",
        ]
        if include_defi:
            select_lines.extend(
                [
                    "  underlying_symbol,",
                    "  underlying_protocol,",
                    "  token_balance_underlying,",
                    "  token_underlying_symbol,",
                    "  token_balance_usd,",
                    "  token_balance_eth,",
                    "  identified_defi_contract,",
                ]
            )
        select_lines.append("  last_updated")
        suggested_sql = (
            "SELECT\n"
            + "\n".join(select_lines)
            + f"\nFROM {table_name}\n"
            + "WHERE "
            + "\n  AND ".join(where_lines)
            + "\nORDER BY token_balance DESC NULLS LAST, address\n"
            + f"LIMIT {limit_value};"
        )

    plan = {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "address": address_literal,
        "token_symbol": token_symbol,
        "token_address": token_address,
        "as_of_date": as_of_date_value,
        "include_defi": include_defi,
        "exclude_identified_defi": exclude_identified_defi,
        "mode": mode_value,
        "limit": limit_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "suggested_sql": suggested_sql,
    }
    if include_defi and dataset.get("completeness label") == "partial":
        plan["completeness_note"] = (
            "This DeFi-aware holder view is broader than direct holders, but "
            "coverage is partial because not all DeFi protocols are tracked."
        )
    if mode_value == "rows" and limit_value > 500:
        plan["warning"] = (
            "Rows mode can be expensive for large holder sets. Prefer mode='summary' "
            "for aggregate questions or keep limit modest."
        )
    return plan


def get_protocol_token_holders(
    address=None,
    token_symbol=None,
    token_address=None,
    as_of_date=None,
    include_defi=False,
    exclude_identified_defi=False,
    mode="summary",
    limit=100,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_protocol_token_holders_plan(
        address=address,
        token_symbol=token_symbol,
        token_address=token_address,
        as_of_date=as_of_date,
        include_defi=include_defi,
        exclude_identified_defi=exclude_identified_defi,
        mode=mode,
        limit=limit,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        if plan.get("address"):
            return {
                **plan,
                "summary": _build_protocol_address_holdings_summary(
                    [],
                    dataset_name=plan["dataset_name"],
                    address=plan["address"],
                    include_defi=include_defi,
                    exclude_identified_defi=exclude_identified_defi,
                    token_symbol=token_symbol,
                    token_address=token_address,
                ),
            }
        return {
            **plan,
            "summary": _build_protocol_token_holders_summary(
                [],
                dataset_name=plan["dataset_name"],
                include_defi=include_defi,
                exclude_identified_defi=exclude_identified_defi,
                address=plan.get("address"),
                token_symbol=token_symbol,
                token_address=token_address,
            ),
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_protocol_token_holders_summary(
                [],
                dataset_name=plan["dataset_name"],
                include_defi=include_defi,
                exclude_identified_defi=exclude_identified_defi,
                address=plan.get("address"),
                token_symbol=token_symbol,
                token_address=token_address,
            ),
        }
    try:
        if plan.get("address"):
            raw_rows = _execute_dune_sql(plan["suggested_sql"])
            rows = _protocol_address_holding_rows(raw_rows)
            summary = _build_protocol_address_holdings_summary(
                raw_rows,
                dataset_name=plan["dataset_name"],
                address=plan["address"],
                include_defi=include_defi,
                exclude_identified_defi=exclude_identified_defi,
                token_symbol=token_symbol,
                token_address=token_address,
            )
            return {
                **plan,
                "executed_live": True,
                "row_count": summary["row_count"],
                "rows": rows if plan["mode"] == "rows" else [],
                "summary": summary,
                "summary_queries": {
                    "address_holdings_sql": plan["suggested_sql"],
                },
            }
        if plan["mode"] == "summary":
            token_address_literal = _normalize_address_literal(token_address) if token_address else None
            filter_lines = _build_protocol_token_holders_base_filter_lines(
                token_symbol=token_symbol,
                token_address_literal=token_address_literal,
                include_defi=include_defi,
                exclude_identified_defi=exclude_identified_defi,
            )
            if as_of_date:
                filter_lines.append(f"CAST(day AS DATE) = CAST('{plan['as_of_date']}' AS DATE)")
            summary_queries = _build_protocol_token_holders_summary_queries(
                plan["table_name"],
                filter_lines,
                include_defi=include_defi,
            )
            summary = _build_protocol_token_holders_summary_from_queries(
                summary_queries["overview_rows"],
                summary_queries["balances_by_blockchain_rows"],
                summary_queries["top_holders_rows"],
                summary_queries["defi_contract_breakdown_rows"],
                dataset_name=plan["dataset_name"],
                include_defi=include_defi,
                exclude_identified_defi=exclude_identified_defi,
                token_symbol=token_symbol,
                token_address=token_address,
            )
            return {
                **plan,
                "executed_live": True,
                "row_count": summary["holder_count"],
                "rows": [],
                "summary": summary,
                "summary_queries": {
                    "overview_sql": summary_queries["overview_sql"],
                    "balances_by_blockchain_sql": summary_queries["balances_by_blockchain_sql"],
                    "top_holders_sql": summary_queries["top_holders_sql"],
                    "defi_contract_breakdown_sql": summary_queries["defi_contract_breakdown_sql"],
                },
            }
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_protocol_token_holders_summary(
                [],
                dataset_name=plan["dataset_name"],
                include_defi=include_defi,
                exclude_identified_defi=exclude_identified_defi,
                address=plan.get("address"),
                token_symbol=token_symbol,
                token_address=token_address,
            ),
        }
    return {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "summary": _build_protocol_token_holders_summary(
            rows,
            dataset_name=plan["dataset_name"],
            include_defi=include_defi,
            exclude_identified_defi=exclude_identified_defi,
            address=plan.get("address"),
            token_symbol=token_symbol,
            token_address=token_address,
        ),
    }


def _execute_dune_sql(sql: str) -> list[dict]:
    api_key = os.getenv("DUNE_API_KEY")
    if not api_key:
        raise RuntimeError("DUNE_API_KEY is required when execute_live=true.")

    try:
        from dune_client.client import DuneClient

        result = DuneClient(api_key=api_key).run_sql(query_sql=sql)
        rows = getattr(result, "rows", None)
        if rows is None and hasattr(result, "result"):
            rows = getattr(result.result, "rows", None)
        if rows is None:
            raise RuntimeError("Dune query returned no rows payload.")
        return rows
    except Exception as exc:
        raise RuntimeError(f"Dune query execution failed: {exc}") from exc


def _to_number(value) -> float:
    if value is None:
        return 0.0
    return float(value)


def _build_aum_summary(rows: list[dict]) -> dict:
    if not rows:
        return {
            "latest_day": None,
            "total_token_balance_usd": 0.0,
            "total_token_balance_eth": 0.0,
            "balances_by_token": [],
            "balances_by_blockchain": [],
        }

    latest_day = max(row.get("day") for row in rows if row.get("day") is not None)
    total_token_balance_usd = sum(_to_number(row.get("token_balance_usd")) for row in rows)
    total_token_balance_eth = sum(_to_number(row.get("token_balance_eth")) for row in rows)

    token_groups: dict[str, dict] = {}
    for row in rows:
        token_symbol = row.get("token_symbol")
        group = token_groups.setdefault(
            token_symbol,
            {
                "token_symbol": token_symbol,
                "token_underlying_symbol": row.get("token_underlying_symbol"),
                "token_balance": 0.0,
                "token_balance_underlying": 0.0,
                "token_balance_usd": 0.0,
                "token_balance_eth": 0.0,
            },
        )
        group["token_balance"] += _to_number(row.get("token_balance"))
        group["token_balance_underlying"] += _to_number(row.get("token_balance_underlying"))
        group["token_balance_usd"] += _to_number(row.get("token_balance_usd"))
        group["token_balance_eth"] += _to_number(row.get("token_balance_eth"))

    blockchain_groups: dict[str, dict] = {}
    for row in rows:
        blockchain = row.get("blockchain")
        group = blockchain_groups.setdefault(
            blockchain,
            {
                "blockchain": blockchain,
                "token_balance_usd": 0.0,
                "token_balance_eth": 0.0,
            },
        )
        group["token_balance_usd"] += _to_number(row.get("token_balance_usd"))
        group["token_balance_eth"] += _to_number(row.get("token_balance_eth"))

    return {
        "latest_day": latest_day,
        "total_token_balance_usd": total_token_balance_usd,
        "total_token_balance_eth": total_token_balance_eth,
        "balances_by_token": sorted(
            token_groups.values(),
            key=lambda row: row["token_balance_usd"],
            reverse=True,
        ),
        "balances_by_blockchain": sorted(
            blockchain_groups.values(),
            key=lambda row: row["token_balance_usd"],
            reverse=True,
        ),
    }


def _build_aum_classification_context(rows: list[dict], dataset_name: str) -> dict:
    observed_names = sorted(
        {
            row.get("address_name")
            for row in rows
            if row.get("address_name") not in (None, "")
        }
    )
    return {
        "address_registry_dataset": "dune.ether_fi.result_etherfi_addresses",
        "cash_safe_registry_dataset": "dune.ether_fi.result_etherfi_cash_addresses",
        "address_registry_classification_column": "name",
        "balance_dataset": dataset_name,
        "balance_classification_column": "address_name",
        "relationship_note": (
            "The ether.fi address registry uses `name` as the canonical address "
            "classification field, while the AUM balance table exposes the related "
            "classification context in `address_name`."
        ),
        "cash_semantics_note": (
            "For public Cash-safe validation, use `dune.ether_fi.result_etherfi_cash_addresses`. "
            "AUM balances can still be filtered with `address_name = 'CASH'` when the question is about Cash balances."
        ),
        "observed_address_names": observed_names,
    }


def _build_top_cash_users_summary(users: list[dict], latest_day=None) -> dict:
    if not users:
        return {
            "latest_day": latest_day,
            "user_count_returned": 0,
            "total_usd_of_returned_users": 0.0,
            "total_eth_of_returned_users": 0.0,
        }
    return {
        "latest_day": latest_day or next(
            (user.get("latest_day") for user in users if user.get("latest_day") is not None),
            None,
        ),
        "user_count_returned": len(users),
        "total_usd_of_returned_users": sum(
            _to_number(user.get("total_token_balance_usd")) for user in users
        ),
        "total_eth_of_returned_users": sum(
            _to_number(user.get("total_token_balance_eth")) for user in users
        ),
    }


def _compact_top_cash_user_rows(rows: list[dict]) -> list[dict]:
    users: dict[str, dict] = {}
    for row in rows:
        address = row.get("address")
        user = users.setdefault(
            address,
            {
                "rank": row.get("rank"),
                "address": address,
                "latest_day": row.get("day"),
                "total_token_balance_usd": _to_number(row.get("total_token_balance_usd")),
                "total_token_balance_eth": _to_number(row.get("total_token_balance_eth")),
                "token_breakdown": {},
                "chain_breakdown": {},
            },
        )

        token_key = (row.get("blockchain"), row.get("token_address"), row.get("token_symbol"))
        token_group = user["token_breakdown"].setdefault(
            token_key,
            {
                "blockchain": row.get("blockchain"),
                "token_address": row.get("token_address"),
                "token_symbol": row.get("token_symbol"),
                "token_type": row.get("token_type"),
                "token_project": row.get("token_project"),
                "token_underlying_symbol": row.get("token_underlying_symbol"),
                "token_balance": 0.0,
                "token_balance_underlying": 0.0,
                "token_balance_usd": 0.0,
                "token_balance_eth": 0.0,
            },
        )
        token_group["token_balance"] += _to_number(row.get("token_balance"))
        token_group["token_balance_underlying"] += _to_number(row.get("token_balance_underlying"))
        token_group["token_balance_usd"] += _to_number(row.get("token_balance_usd"))
        token_group["token_balance_eth"] += _to_number(row.get("token_balance_eth"))

        chain_key = row.get("blockchain")
        chain_group = user["chain_breakdown"].setdefault(
            chain_key,
            {
                "blockchain": row.get("blockchain"),
                "token_balance_usd": 0.0,
                "token_balance_eth": 0.0,
            },
        )
        chain_group["token_balance_usd"] += _to_number(row.get("token_balance_usd"))
        chain_group["token_balance_eth"] += _to_number(row.get("token_balance_eth"))

    compact_rows = []
    for user in users.values():
        compact_rows.append(
            {
                **user,
                "token_breakdown": sorted(
                    user["token_breakdown"].values(),
                    key=lambda token: token["token_balance_usd"],
                    reverse=True,
                ),
                "chain_breakdown": sorted(
                    user["chain_breakdown"].values(),
                    key=lambda chain: chain["token_balance_usd"],
                    reverse=True,
                ),
            }
        )
    return sorted(compact_rows, key=lambda user: user["rank"])


def _get_top_cash_users_plan(
    as_of_date=None,
    limit=10,
    min_total_usd=None,
    token_symbol=None,
    token_address=None,
    blockchain=None,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "as_of_date": as_of_date,
            "limit": limit,
            "min_total_usd": min_total_usd,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "blockchain": blockchain,
        }
    freshness_status = dataset_error

    if token_symbol and token_address:
        return {
            "error": "Provide only one of token_symbol or token_address.",
            "dataset_name": dataset_name,
            "as_of_date": as_of_date,
            "limit": limit,
            "min_total_usd": min_total_usd,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "blockchain": blockchain,
            "query_ready": True,
        }

    try:
        limit_value = _validate_limit(limit, default=10)
        min_total_usd_value = _validate_min_total_usd(min_total_usd)
        as_of_date_value = _validate_date_literal(as_of_date, "as_of_date") if as_of_date else None
        token_symbol_value = (
            _validate_simple_string_literal(token_symbol, "token_symbol")
            if token_symbol
            else None
        )
        token_address_literal = _normalize_address_literal(token_address) if token_address else None
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain")
            if blockchain
            else None
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "as_of_date": as_of_date,
            "limit": limit,
            "min_total_usd": min_total_usd,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "blockchain": blockchain,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    filter_lines = _build_top_cash_users_filter_lines(
        token_symbol=token_symbol_value,
        token_address_literal=token_address_literal,
        blockchain=blockchain_value,
    )
    date_column = dataset.get("date_column", "day")
    day_filter = (
        f"CAST({date_column} AS DATE) = CAST('{as_of_date_value}' AS DATE)"
        if as_of_date_value
        else (
            f"{date_column} = (SELECT MAX({date_column}) FROM {table_name}\n"
            + "WHERE "
            + "\n  AND ".join(filter_lines)
            + "\n)"
        )
    )
    min_total_usd_filter = (
        f"HAVING SUM(token_balance_usd) >= {min_total_usd_value}"
        if min_total_usd_value is not None
        else ""
    )
    suggested_sql = (
        "WITH cash_balances AS (\n"
        "  SELECT\n"
        "    day,\n"
        "    blockchain,\n"
        "    address,\n"
        "    token_address,\n"
        "    token_symbol,\n"
        "    token_type,\n"
        "    token_project,\n"
        "    token_balance,\n"
        "    token_balance_underlying,\n"
        "    token_underlying_symbol,\n"
        "    token_balance_usd,\n"
        "    token_balance_eth,\n"
        "    last_updated\n"
        f"  FROM {table_name}\n"
        "  WHERE "
        + "\n    AND ".join(filter_lines)
        + "\n"
        f"    AND {day_filter}\n"
        "    AND COALESCE(token_balance_usd, 0) > 0\n"
        "), user_totals AS (\n"
        "  SELECT\n"
        "    address,\n"
        "    SUM(token_balance_usd) AS total_token_balance_usd,\n"
        "    SUM(token_balance_eth) AS total_token_balance_eth\n"
        "  FROM cash_balances\n"
        "  GROUP BY 1\n"
        f"  {min_total_usd_filter}\n"
        "), top_users AS (\n"
        "  SELECT\n"
        "    address,\n"
        "    total_token_balance_usd,\n"
        "    total_token_balance_eth,\n"
        "    ROW_NUMBER() OVER (ORDER BY total_token_balance_usd DESC) AS rank\n"
        "  FROM user_totals\n"
        "  ORDER BY total_token_balance_usd DESC\n"
        f"  LIMIT {limit_value}\n"
        ")\n"
        "SELECT\n"
        "  t.rank,\n"
        "  b.day,\n"
        "  b.address,\n"
        "  t.total_token_balance_usd,\n"
        "  t.total_token_balance_eth,\n"
        "  b.blockchain,\n"
        "  b.token_address,\n"
        "  b.token_symbol,\n"
        "  b.token_type,\n"
        "  b.token_project,\n"
        "  b.token_balance,\n"
        "  b.token_balance_underlying,\n"
        "  b.token_underlying_symbol,\n"
        "  b.token_balance_usd,\n"
        "  b.token_balance_eth,\n"
        "  b.last_updated\n"
        "FROM cash_balances b\n"
        "JOIN top_users t ON b.address = t.address\n"
        "ORDER BY t.rank, b.token_balance_usd DESC NULLS LAST, b.blockchain, b.token_symbol;"
    )

    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "as_of_date": as_of_date_value,
        "limit": limit_value,
        "min_total_usd": min_total_usd_value,
        "token_symbol": token_symbol_value,
        "token_address": token_address_literal,
        "blockchain": blockchain_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "why_chosen": (
            "Uses the AUM balance table filtered to `address_name = 'CASH'`, which is "
            "the balance-side classification for ether.fi Cash safes."
        ),
        "ranking_scope": (
            "filtered-token holdings"
            if token_symbol_value or token_address_literal or blockchain_value
            else "all-token total holdings"
        ),
        "latest_day_logic": (
            "When `as_of_date` is omitted, the query uses the latest available AUM day "
            "among rows that match the Cash and optional token/blockchain filters."
        ),
        "tool_gap_note": (
            "Token and blockchain filters are applied before aggregation, so filtered "
            "queries rerank the Cash population itself rather than only trimming the "
            "displayed token breakdown."
            if token_symbol_value or token_address_literal or blockchain_value
            else (
                "This answers ranked all-Cash-user holding questions that the single-address "
                "AUM balance tool cannot execute directly."
            )
        ),
        "expected_output_fields": [
            "rank",
            "address",
            "total_token_balance_usd",
            "total_token_balance_eth",
            "token_breakdown",
            "chain_breakdown",
        ],
        "suggested_sql": suggested_sql,
    }


def _get_cash_token_totals_plan(
    as_of_date=None,
    token_symbol=None,
    token_address=None,
    blockchain=None,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "as_of_date": as_of_date,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "blockchain": blockchain,
        }
    freshness_status = dataset_error

    if token_symbol and token_address:
        return {
            "error": "Provide only one of token_symbol or token_address.",
            "dataset_name": dataset_name,
            "as_of_date": as_of_date,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "blockchain": blockchain,
            "query_ready": True,
        }

    try:
        as_of_date_value = _validate_date_literal(as_of_date, "as_of_date") if as_of_date else None
        token_symbol_value = (
            _validate_simple_string_literal(token_symbol, "token_symbol")
            if token_symbol
            else None
        )
        token_address_literal = _normalize_address_literal(token_address) if token_address else None
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain")
            if blockchain
            else None
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "dataset_name": dataset_name,
            "as_of_date": as_of_date,
            "token_symbol": token_symbol,
            "token_address": token_address,
            "blockchain": blockchain,
            "query_ready": True,
        }

    table_name = dataset["table_name"]
    filter_lines = _build_top_cash_users_filter_lines(
        token_symbol=token_symbol_value,
        token_address_literal=token_address_literal,
        blockchain=blockchain_value,
    )
    date_column = dataset.get("date_column", "day")
    day_filter = (
        f"CAST({date_column} AS DATE) = CAST('{as_of_date_value}' AS DATE)"
        if as_of_date_value
        else (
            f"{date_column} = (SELECT MAX({date_column}) FROM {table_name}\n"
            + "WHERE "
            + "\n  AND ".join(filter_lines)
            + "\n)"
        )
    )
    scope = "all Cash balances"
    if token_symbol_value or token_address_literal:
        scope = "token-filtered Cash balances"
    if (token_symbol_value or token_address_literal) and blockchain_value:
        scope = "token + blockchain filtered Cash balances"
    elif blockchain_value:
        scope = "blockchain-filtered Cash balances"

    suggested_sql = (
        "WITH cash_balances AS (\n"
        "  SELECT\n"
        "    day,\n"
        "    blockchain,\n"
        "    address,\n"
        "    token_address,\n"
        "    token_symbol,\n"
        "    token_underlying_symbol,\n"
        "    token_balance,\n"
        "    token_balance_usd,\n"
        "    token_balance_eth\n"
        f"  FROM {table_name}\n"
        "  WHERE "
        + "\n    AND ".join(filter_lines)
        + "\n"
        f"    AND {day_filter}\n"
        "    AND (\n"
        "      COALESCE(token_balance_usd, 0) > 0\n"
        "      OR COALESCE(token_balance_eth, 0) > 0\n"
        "      OR COALESCE(token_balance, 0) > 0\n"
        "    )\n"
        "), overview AS (\n"
        "  SELECT\n"
        "    'overview' AS row_type,\n"
        "    MAX(day) AS latest_day,\n"
        "    NULL AS blockchain,\n"
        "    COUNT(DISTINCT address) AS holder_count,\n"
        "    COALESCE(SUM(token_balance_usd), 0) AS total_token_balance_usd,\n"
        "    COALESCE(SUM(token_balance_eth), 0) AS total_token_balance_eth,\n"
        "    CASE\n"
        "      WHEN COUNT(DISTINCT token_address) = 1 THEN COALESCE(SUM(token_balance), 0)\n"
        "      ELSE NULL\n"
        "    END AS total_token_balance,\n"
        "    CASE WHEN COUNT(DISTINCT token_address) = 1 THEN MAX(token_symbol) ELSE NULL END AS token_symbol,\n"
        "    CASE WHEN COUNT(DISTINCT token_address) = 1 THEN MAX(token_underlying_symbol) ELSE NULL END AS token_underlying_symbol\n"
        "  FROM cash_balances\n"
        "), blockchain_totals AS (\n"
        "  SELECT\n"
        "    'blockchain' AS row_type,\n"
        "    MAX(day) AS latest_day,\n"
        "    blockchain,\n"
        "    COUNT(DISTINCT address) AS holder_count,\n"
        "    COALESCE(SUM(token_balance_usd), 0) AS total_token_balance_usd,\n"
        "    COALESCE(SUM(token_balance_eth), 0) AS total_token_balance_eth,\n"
        "    CASE\n"
        "      WHEN COUNT(DISTINCT token_address) = 1 THEN COALESCE(SUM(token_balance), 0)\n"
        "      ELSE NULL\n"
        "    END AS total_token_balance,\n"
        "    CASE WHEN COUNT(DISTINCT token_address) = 1 THEN MAX(token_symbol) ELSE NULL END AS token_symbol,\n"
        "    CASE WHEN COUNT(DISTINCT token_address) = 1 THEN MAX(token_underlying_symbol) ELSE NULL END AS token_underlying_symbol\n"
        "  FROM cash_balances\n"
        "  GROUP BY 1, 3\n"
        ")\n"
        "SELECT *\n"
        "FROM overview\n"
        "UNION ALL\n"
        "SELECT *\n"
        "FROM blockchain_totals\n"
        "ORDER BY CASE WHEN row_type = 'overview' THEN 0 ELSE 1 END, total_token_balance_usd DESC NULLS LAST, blockchain;"
    )

    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "as_of_date": as_of_date_value,
        "token_symbol": token_symbol_value,
        "token_address": token_address_literal,
        "blockchain": blockchain_value,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "why_chosen": (
            "Uses the AUM balance table filtered to `address_name = 'CASH'`, which is "
            "the balance-side classification for ether.fi Cash safes and the narrowest "
            "query-ready dataset for full-population balance totals."
        ),
        "wrong_alternative_note": (
            "Do not use `get_top_cash_users` or any ranked subset to answer this question; "
            "population totals must be aggregated directly across all matching Cash rows."
        ),
        "aggregate_scope": scope,
        "latest_day_logic": (
            "When `as_of_date` is omitted, the query uses the latest available AUM day "
            "among rows that match the Cash and optional token/blockchain filters."
        ),
        "important_caveats": [
            "Filtering happens before aggregation, so token and blockchain totals represent the full matching Cash population.",
            "When no token filter is provided, `total_token_balance` is only meaningful if the matching population resolves to one token; otherwise it is null by design.",
            "This tool answers full-population aggregate questions and must not approximate totals from top-N cohorts.",
        ],
        "expected_output_fields": [
            "latest_day",
            "holder_count",
            "total_token_balance_usd",
            "total_token_balance_eth",
            "total_token_balance",
            "token_symbol",
            "token_underlying_symbol",
            "balances_by_blockchain",
        ],
        "suggested_sql": suggested_sql,
    }


def get_top_cash_users(
    as_of_date=None,
    limit=10,
    min_total_usd=None,
    token_symbol=None,
    token_address=None,
    blockchain=None,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_top_cash_users_plan(
        as_of_date=as_of_date,
        limit=limit,
        min_total_usd=min_total_usd,
        token_symbol=token_symbol,
        token_address=token_address,
        blockchain=blockchain,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        return {
            **plan,
            "summary": _build_top_cash_users_summary([]),
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_top_cash_users_summary([]),
        }

    try:
        raw_rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "raw_rows": [],
            "summary": _build_top_cash_users_summary([]),
        }

    rows = _compact_top_cash_user_rows(raw_rows)
    latest_day = rows[0].get("latest_day") if rows else None
    return {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "raw_row_count": len(raw_rows),
        "raw_rows": raw_rows,
        "summary": _build_top_cash_users_summary(rows, latest_day=latest_day),
    }


def get_cash_token_totals(
    as_of_date=None,
    token_symbol=None,
    token_address=None,
    blockchain=None,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_cash_token_totals_plan(
        as_of_date=as_of_date,
        token_symbol=token_symbol,
        token_address=token_address,
        blockchain=blockchain,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        return {
            **plan,
            "summary": _build_cash_token_totals_summary([]),
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_cash_token_totals_summary([]),
        }

    try:
        raw_rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "raw_rows": [],
            "summary": _build_cash_token_totals_summary([]),
        }

    summary = _build_cash_token_totals_summary(raw_rows)
    has_results = summary["holder_count"] > 0
    rows = raw_rows if has_results else []
    return {
        **plan,
        "executed_live": True,
        "row_count": len(rows),
        "rows": rows,
        "raw_row_count": len(raw_rows),
        "raw_rows": raw_rows,
        "summary": summary,
        "warning": (
            None
            if has_results
            else "No Cash balances matched the requested date/token/blockchain filters."
        ),
    }


def _get_cash_holdings_timeseries_plan(
    start_date=None,
    end_date=None,
    period=None,
    granularity="day",
    token_symbol=None,
    token_symbols=None,
    token_address=None,
    blockchain=None,
    group_by=None,
    category_preset=None,
    categories=None,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    dataset, dataset_error = _get_query_ready_dataset(
        dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if dataset is None:
        return {
            **dataset_error,
            "start_date": start_date,
            "end_date": end_date,
            "period": period,
            "granularity": granularity,
            "token_symbol": token_symbol,
            "token_symbols": token_symbols,
            "token_address": token_address,
            "blockchain": blockchain,
            "group_by": group_by,
            "category_preset": category_preset,
            "categories": categories,
        }
    freshness_status = dataset_error

    base_error = {
        "dataset_name": dataset_name,
        "start_date": start_date,
        "end_date": end_date,
        "period": period,
        "granularity": granularity,
        "token_symbol": token_symbol,
        "token_symbols": token_symbols,
        "token_address": token_address,
        "blockchain": blockchain,
        "group_by": group_by,
        "category_preset": category_preset,
        "categories": categories,
        "query_ready": True,
    }
    requested_token_filter_count = sum(
        1
        for value in (token_symbol, token_symbols, token_address)
        if value is not None
    )
    if requested_token_filter_count > 1:
        return {
            **base_error,
            "error": "Provide only one of token_symbol, token_symbols, or token_address.",
        }

    try:
        granularity_value = _validate_cash_holdings_timeseries_granularity(granularity)
        group_by_value = _validate_cash_holdings_group_by(group_by)
        category_preset_value = _validate_cash_holdings_category_preset(category_preset)
        if category_preset_value and group_by_value != "category":
            raise ValueError("category_preset requires group_by='category'.")
        if group_by_value == "category" and not category_preset_value:
            raise ValueError("group_by='category' requires category_preset='cash_balance_buckets'.")
        if category_preset_value and (token_symbol or token_symbols or token_address):
            raise ValueError("category_preset cannot be combined with token_symbol, token_symbols, or token_address filters.")
        if categories is not None and group_by_value != "category":
            raise ValueError("categories can only be used when group_by='category'.")
        start_date_value, end_date_value = _resolve_cash_holdings_timeseries_date_range(
            start_date=start_date,
            end_date=end_date,
            period=period,
            now=now,
        )
        token_symbol_value = (
            _validate_simple_string_literal(token_symbol, "token_symbol")
            if token_symbol
            else None
        )
        token_symbols_value = _validate_cash_holdings_token_symbols(token_symbols)
        token_address_literal = _normalize_address_literal(token_address) if token_address else None
        blockchain_value = (
            _validate_simple_string_literal(blockchain, "blockchain")
            if blockchain
            else None
        )
        categories_value = _validate_cash_holdings_categories(categories, category_preset_value)
    except ValueError as exc:
        return {
            **base_error,
            "error": str(exc),
        }

    table_name = dataset["table_name"]
    filter_lines = _build_top_cash_users_filter_lines(
        token_symbol=None if category_preset_value else token_symbol_value,
        token_address_literal=token_address_literal,
        blockchain=blockchain_value,
    )
    if token_symbols_value:
        symbols = ", ".join(_quote_sql_string(symbol) for symbol in token_symbols_value)
        filter_lines.append(f"token_symbol IN ({symbols})")
    category_mapping = (
        _CASH_HOLDINGS_CATEGORY_PRESETS[category_preset_value]
        if category_preset_value
        else {}
    )
    if categories_value:
        category_mapping = {
            symbol: label
            for symbol, label in category_mapping.items()
            if label in categories_value
        }
    if category_mapping:
        symbols = ", ".join(_quote_sql_string(symbol) for symbol in category_mapping)
        filter_lines.append(f"token_symbol IN ({symbols})")
    date_column = dataset.get("date_column", "day")
    range_filter = (
        f"CAST({date_column} AS DATE) BETWEEN CAST('{start_date_value}' AS DATE) "
        f"AND CAST('{end_date_value}' AS DATE)"
    )
    query_scope = "all Cash balances"
    if token_symbol_value or token_symbols_value or token_address_literal:
        query_scope = "token-filtered Cash balances"
    if token_symbols_value:
        query_scope = "multi-symbol Cash balances batched in one query"
    if (token_symbol_value or token_symbols_value or token_address_literal) and blockchain_value:
        query_scope = "token + blockchain filtered Cash balances"
    elif blockchain_value:
        query_scope = "blockchain-filtered Cash balances"
    if group_by_value == "token_symbol":
        query_scope = f"{query_scope} grouped by token_symbol"
    if group_by_value == "category":
        query_scope = "Cash balance bucket history grouped by category"
        if categories_value:
            query_scope = "filtered Cash balance bucket history grouped by category"

    balance_filter = (
        "    AND (\n"
        "      COALESCE(token_balance_usd, 0) > 0\n"
        "      OR COALESCE(token_balance_eth, 0) > 0\n"
        "      OR COALESCE(token_balance, 0) > 0\n"
        "    )\n"
    )
    where_sql = (
        "  WHERE "
        + "\n    AND ".join(filter_lines)
        + "\n"
        f"    AND {range_filter}\n"
        + balance_filter
    )
    if group_by_value == "category":
        case_lines = [
            f"      WHEN token_symbol = {_quote_sql_string(symbol)} THEN {_quote_sql_string(label)}"
            for symbol, label in category_mapping.items()
        ]
        group_expression = "category"
        source_sql = (
            "  SELECT\n"
            f"    CAST({date_column} AS DATE) AS day,\n"
            "    CASE\n"
            + "\n".join(case_lines)
            + "\n"
            "    END AS category,\n"
            "    address,\n"
            "    COALESCE(token_balance_usd, 0) AS token_balance_usd,\n"
            "    COALESCE(token_balance_eth, 0) AS token_balance_eth\n"
            f"  FROM {table_name}\n"
            + where_sql
        )
        daily_sql = (
            "  SELECT\n"
            "    day,\n"
            "    category,\n"
            "    COUNT(DISTINCT address) AS holder_count,\n"
            "    SUM(token_balance_usd) AS total_usd,\n"
            "    SUM(token_balance_eth) AS total_eth\n"
            "  FROM (\n"
            + source_sql
            + "  ) source_balances\n"
            "  WHERE category IS NOT NULL\n"
            "  GROUP BY 1, 2\n"
        )
        group_columns = [("category", group_expression)]
    elif group_by_value == "token_symbol":
        daily_sql = (
            "  SELECT\n"
            f"    CAST({date_column} AS DATE) AS day,\n"
            "    token_symbol,\n"
            "    COUNT(DISTINCT address) AS holder_count,\n"
            "    SUM(COALESCE(token_balance_usd, 0)) AS total_usd,\n"
            "    SUM(COALESCE(token_balance_eth, 0)) AS total_eth\n"
            f"  FROM {table_name}\n"
            + where_sql
            + "  GROUP BY 1, 2\n"
        )
        group_columns = [("token_symbol", "token_symbol")]
    else:
        daily_sql = (
            "  SELECT\n"
            "    day,\n"
            "    COUNT(DISTINCT address) AS holder_count,\n"
            "    SUM(total_usd) AS total_usd,\n"
            "    AVG(total_usd) AS avg_balance_usd,\n"
            "    SUM(total_eth) AS total_eth,\n"
            "    AVG(total_eth) AS avg_balance_eth\n"
            "  FROM (\n"
            "    SELECT\n"
            f"      CAST({date_column} AS DATE) AS day,\n"
            "      address,\n"
            "      SUM(COALESCE(token_balance_usd, 0)) AS total_usd,\n"
            "      SUM(COALESCE(token_balance_eth, 0)) AS total_eth\n"
            f"    FROM {table_name}\n"
            + where_sql
            + "    GROUP BY 1, 2\n"
            "  ) address_day_balances\n"
            "  GROUP BY 1\n"
        )
        group_columns = []

    if granularity_value == "month":
        metric_selects = [
            "SUM(daily_totals.holder_count) AS holder_count",
            "SUM(daily_totals.total_usd) AS total_usd",
            "SUM(daily_totals.total_eth) AS total_eth",
        ]
        if not group_by_value:
            metric_selects.extend(
                [
                    "SUM(daily_totals.avg_balance_usd) AS avg_balance_usd",
                    "SUM(daily_totals.avg_balance_eth) AS avg_balance_eth",
                ]
            )
        order_columns = ["month_end_days.month ASC"]
        if group_by_value:
            order_columns.append(f"month_end_days.{group_by_value} ASC")
        suggested_sql = _build_month_end_snapshot_sql(
            daily_cte_sql=daily_sql,
            group_columns=group_columns,
            metric_selects=metric_selects,
            order_columns=order_columns,
        )
    else:
        select_columns = ["day"]
        if group_by_value:
            select_columns.append(group_by_value)
        select_columns.extend(["holder_count", "total_usd", "total_eth"])
        if not group_by_value:
            select_columns.extend(["avg_balance_usd", "avg_balance_eth"])
        suggested_sql = (
            "WITH daily_totals AS (\n"
            + daily_sql
            + ")\n"
            "SELECT\n"
            + ",\n".join(f"  {column}" for column in select_columns)
            + "\nFROM daily_totals\n"
            + "ORDER BY day"
            + (f", {group_by_value}" if group_by_value else "")
            + ";"
        )

    category_mapping_output = [
        {"token_symbol": symbol, "category": label}
        for symbol, label in category_mapping.items()
    ]
    expected_output_fields = ["day", "holder_count", "total_usd", "total_eth"]
    if granularity_value == "month":
        expected_output_fields = ["month", "month_end_day", "holder_count", "total_usd", "total_eth"]
    if group_by_value:
        expected_output_fields.insert(2 if granularity_value == "month" else 1, group_by_value)
    elif granularity_value == "day":
        expected_output_fields.extend(["avg_balance_usd", "avg_balance_eth"])

    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "start_date": start_date_value,
        "end_date": end_date_value,
        "period": period,
        "granularity": granularity_value,
        "token_symbol": token_symbol_value,
        "token_symbols": token_symbols_value,
        "token_address": token_address_literal,
        "blockchain": blockchain_value,
        "group_by": group_by_value,
        "category_preset": category_preset_value,
        "categories": categories_value,
        "category_mapping": category_mapping_output,
        "query_ready": True,
        "grain": dataset.get("grain"),
        "freshness_status": freshness_status,
        "question_class": "time-series summary",
        "why_chosen": (
            "Uses the AUM balance table filtered to `address_name = 'CASH'`, which is "
            "the balance-side classification for ether.fi Cash safes and the narrowest "
            "query-ready dataset for chart-friendly Cash holdings history."
        ),
        "question_class_note": (
            "This remains the Cash holdings time-series question class: it summarizes "
            "Cash balance snapshots over a date range rather than ranking users, "
            "inspecting individual rows, or executing arbitrary SQL."
        ),
        "wrong_alternative_note": (
            "Do not answer historical average-holdings questions by making repeated "
            "single-date calls; this tool is designed to answer the full range with "
            "one aggregate Dune query."
        ),
        "batching_note": (
            "When multiple token symbols are requested, pass token_symbols so the tool "
            "uses one token_symbol IN (...) filter and one Dune query rather than "
            "multiple per-symbol calls."
        ),
        "aggregate_scope": query_scope,
        "aggregation_logic": (
            "Daily mode returns one aggregate row per day"
            + (f" and {group_by_value}" if group_by_value else "")
            + ". Monthly mode first computes daily aggregates, then returns the latest "
            "available daily snapshot in each calendar month."
        ),
        "monthly_snapshot_rule": (
            "When granularity='month', each row uses the latest available daily snapshot "
            "in each calendar month for the selected group."
        ),
        "category_preset_note": (
            "category_preset='cash_balance_buckets' maps exact token symbols to labels: "
            "liquidUSD->liquidUSD, liquidETH->liquidETH, liquidBTC->liquidBTC, "
            "USDC/USDC.e->stables."
            if category_preset_value
            else None
        ),
        "range_logic": (
            "The query scans one explicit date range and groups by day, instead of "
            "looping over point-in-time snapshots."
        ),
        "important_caveats": [
            "This is based on AUM balances classified with `address_name = 'CASH'`.",
            "Daily values depend on the available daily snapshots in the materialized view.",
            "Monthly rows use the latest available daily snapshot in each calendar month; month_end_day shows the exact source day.",
            "The Cash balance category preset is intentionally narrow and only maps exact configured token_symbol values.",
            "Average holdings are returned only for ungrouped daily rows; grouped/monthly rows are intended for total-balance charting.",
        ],
        "expected_output_fields": expected_output_fields,
        "suggested_sql": suggested_sql,
    }


def get_cash_holdings_timeseries(
    start_date=None,
    end_date=None,
    period=None,
    granularity="day",
    token_symbol=None,
    token_symbols=None,
    token_address=None,
    blockchain=None,
    group_by=None,
    category_preset=None,
    categories=None,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_cash_holdings_timeseries_plan(
        start_date=start_date,
        end_date=end_date,
        period=period,
        granularity=granularity,
        token_symbol=token_symbol,
        token_symbols=token_symbols,
        token_address=token_address,
        blockchain=blockchain,
        group_by=group_by,
        category_preset=category_preset,
        categories=categories,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    summary = _build_cash_holdings_timeseries_summary(
        [],
        start_date=plan.get("start_date"),
        end_date=plan.get("end_date"),
        period=plan.get("period"),
        token_symbol=plan.get("token_symbol"),
        token_symbols=plan.get("token_symbols"),
        token_address=plan.get("token_address"),
        blockchain=plan.get("blockchain"),
        granularity=plan.get("granularity", granularity),
        group_by=plan.get("group_by"),
        category_preset=plan.get("category_preset"),
        categories=plan.get("categories"),
    )
    if not execute_live:
        return {
            **plan,
            "summary": summary,
            "timeseries": [],
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "timeseries": [],
            "summary": summary,
        }

    try:
        raw_rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "timeseries": [],
            "raw_rows": [],
            "summary": summary,
        }

    timeseries = []
    for row in raw_rows:
        normalized = {}
        if plan["granularity"] == "month":
            normalized["month"] = row.get("month")
            normalized["month_end_day"] = row.get("month_end_day")
        else:
            normalized["day"] = row.get("day")
        if plan.get("group_by"):
            normalized[plan["group_by"]] = row.get(plan["group_by"])
        normalized.update(
            {
                "holder_count": int(_to_number(row.get("holder_count"))),
                "total_usd": _to_number(row.get("total_usd")),
                "total_eth": _to_number(row.get("total_eth")),
            }
        )
        if row.get("avg_balance_usd") is not None:
            normalized["avg_balance_usd"] = _to_number(row.get("avg_balance_usd"))
        if row.get("avg_balance_eth") is not None:
            normalized["avg_balance_eth"] = _to_number(row.get("avg_balance_eth"))
        timeseries.append(normalized)
    summary = _build_cash_holdings_timeseries_summary(
        timeseries,
        start_date=plan["start_date"],
        end_date=plan["end_date"],
        period=plan.get("period"),
        token_symbol=plan.get("token_symbol"),
        token_symbols=plan.get("token_symbols"),
        token_address=plan.get("token_address"),
        blockchain=plan.get("blockchain"),
        granularity=plan["granularity"],
        group_by=plan.get("group_by"),
        category_preset=plan.get("category_preset"),
        categories=plan.get("categories"),
    )
    return {
        **plan,
        "executed_live": True,
        "row_count": len(timeseries),
        "rows": timeseries,
        "timeseries": timeseries,
        "raw_row_count": len(raw_rows),
        "raw_rows": raw_rows,
        "summary": summary,
        "warning": (
            None
            if timeseries
            else "No Cash balances matched the requested date range/token/blockchain filters."
        ),
    }


def _build_cash_safe_profile_summary(profile: dict) -> dict:
    if profile.get("validate_cash_identity"):
        identity_phrase = (
            "listed in the public Cash-safe registry"
            if profile.get("is_classified_cash")
            else "not listed in the public Cash-safe registry"
        )
    else:
        identity_phrase = (
            "identity validation was not requested; this is a Cash-profile view derived "
            "from AUM and Cash activity evidence for the provided address"
        )
    return {
        "address": profile["address"],
        "identity": identity_phrase,
        "latest_balance_day": profile.get("latest_balance_day"),
        "total_token_balance_usd": profile.get("total_token_balance_usd", 0.0),
        "recent_event_count": profile.get("recent_event_count", 0),
        "has_cash_activity_evidence": profile.get("has_cash_activity_evidence", False),
    }


def _empty_cash_safe_profile(
    address,
    validate_cash_identity=False,
    recent_days=30,
    is_classified_cash=None,
    classification_source=None,
) -> dict:
    profile = {
        "address": address,
        "validate_cash_identity": validate_cash_identity,
        "latest_balance_day": None,
        "total_token_balance_usd": 0.0,
        "total_token_balance_eth": 0.0,
        "balances_by_token": [],
        "balances_by_blockchain": [],
        "recent_days": recent_days,
        "recent_event_count": 0,
        "recent_event_types": [],
        "latest_event_time": None,
        "has_cash_activity_evidence": False,
    }
    if validate_cash_identity:
        profile["is_classified_cash"] = is_classified_cash
        profile["classification_source"] = classification_source
    profile["summary"] = _build_cash_safe_profile_summary(profile)
    return profile


def _build_cash_safe_profile_from_rows(
    address,
    rows: list[dict],
    recent_days=30,
    validate_cash_identity=False,
) -> dict:
    profile = _empty_cash_safe_profile(
        address,
        validate_cash_identity=validate_cash_identity,
        recent_days=recent_days,
        is_classified_cash=False if validate_cash_identity else None,
        classification_source="dune.ether_fi.result_etherfi_cash_addresses" if validate_cash_identity else None,
    )
    token_rows = []
    blockchain_rows = []
    event_type_rows = []
    for row in rows:
        row_type = row.get("row_type")
        if row_type == "balance_token":
            token_rows.append(
                {
                    "token_symbol": row.get("token_symbol"),
                    "token_underlying_symbol": row.get("token_underlying_symbol"),
                    "token_balance": _to_number(row.get("token_balance")),
                    "token_balance_underlying": _to_number(row.get("token_balance_underlying")),
                    "token_balance_usd": _to_number(row.get("token_balance_usd")),
                    "token_balance_eth": _to_number(row.get("token_balance_eth")),
                }
            )
            profile["latest_balance_day"] = profile["latest_balance_day"] or row.get("latest_balance_day")
        elif row_type == "balance_blockchain":
            blockchain_rows.append(
                {
                    "blockchain": row.get("blockchain"),
                    "token_balance_usd": _to_number(row.get("token_balance_usd")),
                    "token_balance_eth": _to_number(row.get("token_balance_eth")),
                }
            )
            profile["latest_balance_day"] = profile["latest_balance_day"] or row.get("latest_balance_day")
        elif row_type == "events_overview":
            profile["recent_event_count"] = int(_to_number(row.get("event_count")))
            profile["latest_event_time"] = row.get("latest_event_time")
        elif row_type == "event_type":
            event_type_rows.append(
                {
                    "event_type": row.get("event_type"),
                    "event_count": int(_to_number(row.get("event_count"))),
                    "token_amount_usd": _to_number(row.get("token_amount_usd")),
                }
            )
        elif row_type == "identity" and validate_cash_identity:
            profile["is_classified_cash"] = bool(row.get("is_classified_cash"))
            profile["classification_source"] = "dune.ether_fi.result_etherfi_cash_addresses"

    profile["balances_by_token"] = sorted(
        token_rows,
        key=lambda row: row["token_balance_usd"],
        reverse=True,
    )
    profile["balances_by_blockchain"] = sorted(
        blockchain_rows,
        key=lambda row: row["token_balance_usd"],
        reverse=True,
    )
    profile["total_token_balance_usd"] = sum(
        row["token_balance_usd"] for row in profile["balances_by_token"]
    )
    profile["total_token_balance_eth"] = sum(
        row["token_balance_eth"] for row in profile["balances_by_token"]
    )
    profile["recent_event_types"] = sorted(
        event_type_rows,
        key=lambda row: row["token_amount_usd"],
        reverse=True,
    )
    profile["has_cash_activity_evidence"] = (
        bool(profile["balances_by_token"]) or profile["recent_event_count"] > 0
    )
    profile["summary"] = _build_cash_safe_profile_summary(profile)
    return profile


def _get_cash_safe_profile_plan(
    address,
    as_of_date=None,
    recent_days=30,
    validate_cash_identity=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    aum_dataset_name = "dune.ether_fi.result_etherfi_assets_under_management"
    events_dataset_name = "dune.ether_fi.result_etherfi_cash_events"
    identity_dataset_name = CASH_SAFE_ADDRESSES_DATASET_NAME
    aum_dataset, aum_error = _get_query_ready_dataset(
        aum_dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    events_dataset, events_error = _get_query_ready_dataset(
        events_dataset_name,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    identity_dataset = None
    identity_error = None
    if validate_cash_identity:
        identity_dataset, identity_error = _get_query_ready_dataset(
            identity_dataset_name,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
        )
    if aum_dataset is None or events_dataset is None or (validate_cash_identity and identity_dataset is None):
        return {
            "error": "Required dataset is not query_ready.",
            "address": address,
            "as_of_date": as_of_date,
            "recent_days": recent_days,
            "validate_cash_identity": validate_cash_identity,
            "query_ready": False,
            "dataset_errors": [error for error in (aum_error, events_error, identity_error) if error],
        }

    try:
        address_literal = _normalize_address_literal(address)
        as_of_date_value = _validate_date_literal(as_of_date, "as_of_date") if as_of_date else None
        recent_days_value = _validate_recent_days(recent_days)
    except ValueError as exc:
        return {
            "error": str(exc),
            "address": address,
            "as_of_date": as_of_date,
            "recent_days": recent_days,
            "validate_cash_identity": validate_cash_identity,
            "query_ready": True,
        }

    aum_table_name = aum_dataset["table_name"]
    events_table_name = events_dataset["table_name"]
    identity_table_name = identity_dataset["table_name"] if identity_dataset else None
    date_column = aum_dataset.get("date_column", "day")
    balance_day_filter = (
        f"CAST({date_column} AS DATE) = CAST('{as_of_date_value}' AS DATE)"
        if as_of_date_value
        else f"{date_column} = (SELECT MAX({date_column}) FROM {aum_table_name} WHERE address = {address_literal} AND address_name = 'CASH')"
    )
    event_end_date = f"CAST('{as_of_date_value}' AS DATE)" if as_of_date_value else "CURRENT_DATE"
    event_start_filter = f"block_date >= {event_end_date} - INTERVAL '{recent_days_value}' day"
    event_end_filter = f"block_date <= {event_end_date}"
    identity_sql = (
        "UNION ALL\n"
        "SELECT\n"
        "  'identity' AS row_type,\n"
        "  CAST(NULL AS timestamp) AS latest_balance_day,\n"
        "  CAST(NULL AS varchar) AS blockchain,\n"
        "  CAST(NULL AS varchar) AS token_symbol,\n"
        "  CAST(NULL AS varchar) AS token_underlying_symbol,\n"
        "  CAST(NULL AS double) AS token_balance,\n"
        "  CAST(NULL AS double) AS token_balance_underlying,\n"
        "  CAST(NULL AS double) AS token_balance_usd,\n"
        "  CAST(NULL AS double) AS token_balance_eth,\n"
        "  CAST(NULL AS varchar) AS event_type,\n"
        "  CAST(NULL AS bigint) AS event_count,\n"
        "  CAST(NULL AS double) AS token_amount_usd,\n"
        "  CAST(NULL AS timestamp) AS latest_event_time,\n"
        "  COUNT(*) > 0 AS is_classified_cash\n"
        f"FROM {identity_table_name}\n"
        f"WHERE address = {address_literal}\n"
    ) if validate_cash_identity else ""

    suggested_sql = (
        "WITH latest_balances AS (\n"
        "  SELECT\n"
        "    day,\n"
        "    blockchain,\n"
        "    token_symbol,\n"
        "    token_underlying_symbol,\n"
        "    token_balance,\n"
        "    token_balance_underlying,\n"
        "    token_balance_usd,\n"
        "    token_balance_eth\n"
        f"  FROM {aum_table_name}\n"
        f"  WHERE address = {address_literal}\n"
        "    AND address_name = 'CASH'\n"
        f"    AND {balance_day_filter}\n"
        "), recent_events AS (\n"
        "  SELECT\n"
        "    event_type,\n"
        "    block_time,\n"
        "    token_amount_usd\n"
        f"  FROM {events_table_name}\n"
        f"  WHERE user_safe = {address_literal}\n"
        f"    AND {event_start_filter}\n"
        f"    AND {event_end_filter}\n"
        ")\n"
        "SELECT\n"
        "  'balance_token' AS row_type,\n"
        "  MAX(day) AS latest_balance_day,\n"
        "  CAST(NULL AS varchar) AS blockchain,\n"
        "  token_symbol,\n"
        "  token_underlying_symbol,\n"
        "  SUM(token_balance) AS token_balance,\n"
        "  SUM(token_balance_underlying) AS token_balance_underlying,\n"
        "  SUM(token_balance_usd) AS token_balance_usd,\n"
        "  SUM(token_balance_eth) AS token_balance_eth,\n"
        "  CAST(NULL AS varchar) AS event_type,\n"
        "  CAST(NULL AS bigint) AS event_count,\n"
        "  CAST(NULL AS double) AS token_amount_usd,\n"
        "  CAST(NULL AS timestamp) AS latest_event_time,\n"
        "  CAST(NULL AS boolean) AS is_classified_cash\n"
        "FROM latest_balances\n"
        "GROUP BY token_symbol, token_underlying_symbol\n"
        "UNION ALL\n"
        "SELECT\n"
        "  'balance_blockchain' AS row_type,\n"
        "  MAX(day) AS latest_balance_day,\n"
        "  blockchain,\n"
        "  CAST(NULL AS varchar) AS token_symbol,\n"
        "  CAST(NULL AS varchar) AS token_underlying_symbol,\n"
        "  CAST(NULL AS double) AS token_balance,\n"
        "  CAST(NULL AS double) AS token_balance_underlying,\n"
        "  SUM(token_balance_usd) AS token_balance_usd,\n"
        "  SUM(token_balance_eth) AS token_balance_eth,\n"
        "  CAST(NULL AS varchar) AS event_type,\n"
        "  CAST(NULL AS bigint) AS event_count,\n"
        "  CAST(NULL AS double) AS token_amount_usd,\n"
        "  CAST(NULL AS timestamp) AS latest_event_time,\n"
        "  CAST(NULL AS boolean) AS is_classified_cash\n"
        "FROM latest_balances\n"
        "GROUP BY blockchain\n"
        "UNION ALL\n"
        "SELECT\n"
        "  'events_overview' AS row_type,\n"
        "  CAST(NULL AS timestamp) AS latest_balance_day,\n"
        "  CAST(NULL AS varchar) AS blockchain,\n"
        "  CAST(NULL AS varchar) AS token_symbol,\n"
        "  CAST(NULL AS varchar) AS token_underlying_symbol,\n"
        "  CAST(NULL AS double) AS token_balance,\n"
        "  CAST(NULL AS double) AS token_balance_underlying,\n"
        "  CAST(NULL AS double) AS token_balance_usd,\n"
        "  CAST(NULL AS double) AS token_balance_eth,\n"
        "  CAST(NULL AS varchar) AS event_type,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(token_amount_usd) AS token_amount_usd,\n"
        "  MAX(block_time) AS latest_event_time,\n"
        "  CAST(NULL AS boolean) AS is_classified_cash\n"
        "FROM recent_events\n"
        "UNION ALL\n"
        "SELECT\n"
        "  'event_type' AS row_type,\n"
        "  CAST(NULL AS timestamp) AS latest_balance_day,\n"
        "  CAST(NULL AS varchar) AS blockchain,\n"
        "  CAST(NULL AS varchar) AS token_symbol,\n"
        "  CAST(NULL AS varchar) AS token_underlying_symbol,\n"
        "  CAST(NULL AS double) AS token_balance,\n"
        "  CAST(NULL AS double) AS token_balance_underlying,\n"
        "  CAST(NULL AS double) AS token_balance_usd,\n"
        "  CAST(NULL AS double) AS token_balance_eth,\n"
        "  event_type,\n"
        "  COUNT(*) AS event_count,\n"
        "  SUM(token_amount_usd) AS token_amount_usd,\n"
        "  MAX(block_time) AS latest_event_time,\n"
        "  CAST(NULL AS boolean) AS is_classified_cash\n"
        "FROM recent_events\n"
        "GROUP BY event_type\n"
        f"{identity_sql}"
    )

    return {
        "dataset_names": {
            "balances": aum_dataset_name,
            "events": events_dataset_name,
            "identity": identity_dataset_name if validate_cash_identity else None,
        },
        "table_names": {
            "balances": aum_table_name,
            "events": events_table_name,
            "identity": identity_table_name,
        },
        "address": address_literal,
        "as_of_date": as_of_date_value,
        "recent_days": recent_days_value,
        "validate_cash_identity": validate_cash_identity,
        "query_ready": True,
        "freshness_status": {
            "balances": aum_error,
            "events": events_error,
            "identity": identity_error if validate_cash_identity else None,
        },
        "datasets_used": [
            "AUM balances from `dune.ether_fi.result_etherfi_assets_under_management` filtered to `address_name = 'CASH'`.",
            "Recent Cash activity from `dune.ether_fi.result_etherfi_cash_events` filtered to `user_safe`.",
            "Public Cash-safe identity from `dune.ether_fi.result_etherfi_cash_addresses` only when `validate_cash_identity=True`.",
        ],
        "mode_notes": {
            "profile_mode": (
                "`validate_cash_identity=False` assumes the caller may already know the address is a Cash safe; "
                "the response is framed as balances/activity evidence, not canonical identity proof."
            ),
            "validation_mode": (
                "`validate_cash_identity=True` adds a public Cash-safe registry check against "
                "`dune.ether_fi.result_etherfi_cash_addresses`."
            ),
        },
        "expected_output_fields": [
            "address",
            "validate_cash_identity",
            "latest_balance_day",
            "total_token_balance_usd",
            "total_token_balance_eth",
            "balances_by_token",
            "balances_by_blockchain",
            "recent_days",
            "recent_event_count",
            "recent_event_types",
            "latest_event_time",
            "has_cash_activity_evidence",
            "summary",
            "is_classified_cash",
            "classification_source",
        ],
        "suggested_sql": suggested_sql,
    }


def get_cash_safe_profile(
    address,
    as_of_date=None,
    recent_days=30,
    validate_cash_identity=False,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_cash_safe_profile_plan(
        address=address,
        as_of_date=as_of_date,
        recent_days=recent_days,
        validate_cash_identity=validate_cash_identity,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        return {
            **plan,
            **_empty_cash_safe_profile(
                plan.get("address", address),
                validate_cash_identity=validate_cash_identity,
                recent_days=plan.get("recent_days", recent_days),
                is_classified_cash=None,
                classification_source=(
                    "dune.ether_fi.result_etherfi_cash_addresses" if validate_cash_identity else None
                ),
            ),
        }
    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            **_empty_cash_safe_profile(
                plan.get("address", address),
                validate_cash_identity=validate_cash_identity,
                recent_days=plan.get("recent_days", recent_days),
                is_classified_cash=None,
                classification_source=(
                    "dune.ether_fi.result_etherfi_cash_addresses" if validate_cash_identity else None
                ),
            ),
        }

    try:
        raw_rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "raw_rows": [],
            **_empty_cash_safe_profile(
                plan["address"],
                validate_cash_identity=validate_cash_identity,
                recent_days=plan["recent_days"],
                is_classified_cash=None,
                classification_source=(
                    "dune.ether_fi.result_etherfi_cash_addresses" if validate_cash_identity else None
                ),
            ),
        }

    profile = _build_cash_safe_profile_from_rows(
        plan["address"],
        raw_rows,
        recent_days=plan["recent_days"],
        validate_cash_identity=validate_cash_identity,
    )
    return {
        **plan,
        "executed_live": True,
        "raw_row_count": len(raw_rows),
        "raw_rows": raw_rows,
        **profile,
    }


def get_assets_under_management_balances(
    address,
    as_of_date=None,
    execute_live=False,
    datasets=None,
    freshness_registry=None,
    now=None,
) -> dict:
    plan = _get_assets_under_management_balances_plan(
        address,
        as_of_date=as_of_date,
        datasets=datasets,
        freshness_registry=freshness_registry,
        now=now,
    )
    if not execute_live:
        return {
            **plan,
            "classification_context": _build_aum_classification_context([], plan["dataset_name"]),
            "summary": _build_aum_summary([]),
        }

    if plan.get("error"):
        return {
            **plan,
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_aum_summary([]),
        }

    try:
        _normalize_address_literal(address)
        rows = _execute_dune_sql(plan["suggested_sql"])
    except RuntimeError as exc:
        return {
            "error": str(exc),
            "execution_error": str(exc),
            "dataset_name": plan["dataset_name"],
            "table_name": plan["table_name"],
            "address": address,
            "as_of_date": as_of_date,
            "query_ready": plan["query_ready"],
            "grain": plan["grain"],
            "freshness_status": plan["freshness_status"],
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "summary": _build_aum_summary([]),
            "suggested_sql": plan["suggested_sql"],
        }
    except ValueError as exc:
        return {
            **plan,
            "error": str(exc),
            "execution_error": str(exc),
            "executed_live": False,
            "row_count": 0,
            "rows": [],
            "classification_context": _build_aum_classification_context([], plan["dataset_name"]),
            "summary": _build_aum_summary([]),
        }

    summary = _build_aum_summary(rows)
    classification_context = _build_aum_classification_context(rows, plan["dataset_name"])

    return {
        "dataset_name": plan["dataset_name"],
        "table_name": plan["table_name"],
        "address": address,
        "as_of_date": as_of_date,
        "query_ready": plan["query_ready"],
        "grain": plan["grain"],
        "freshness_status": plan["freshness_status"],
        "rows": rows,
        "row_count": len(rows),
        "executed_live": True,
        "classification_context": classification_context,
        "summary": summary,
        "suggested_sql": plan["suggested_sql"],
    }


def get_catalog_health_summary(datasets=None, registry=None, freshness_registry=None, now=None) -> dict:
    datasets = datasets or load_datasets()
    registry = registry or load_dashboard_registry()
    freshness_registry = (
        load_dataset_freshness_registry()
        if freshness_registry is None
        else freshness_registry
    )

    stale_dataset_names: list[str] = []
    for dataset_name in datasets:
        status = get_dataset_status(
            dataset_name,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
        )
        if status and status.get("freshness", {}).get("is_stale"):
            stale_dataset_names.append(dataset_name)

    dashboards_with_stale_linked_datasets: list[str] = []
    for dashboard in registry.get("dashboards", []):
        status = get_dashboard_status(
            dashboard.get("name"),
            registry=registry,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
        )
        if status and status.get("linked_dataset_warnings"):
            dashboards_with_stale_linked_datasets.append(status["name"])

    return {
        "total_datasets": len(datasets),
        "datasets_with_refresh_metadata": sum(
            1 for dataset in datasets.values() if dataset.get("refresh_interval_minutes") is not None
        ),
        "datasets_with_freshness_snapshots": sum(
            1
            for dataset_name in datasets
            if freshness_registry.get(dataset_name, {}).get("last_updated") is not None
        ),
        "stale_datasets_count": len(stale_dataset_names),
        "stale_dataset_names": stale_dataset_names,
        "total_dashboards": len(registry.get("dashboards", [])),
        "dashboards_with_stale_linked_datasets_count": len(dashboards_with_stale_linked_datasets),
        "dashboards_with_stale_linked_datasets": dashboards_with_stale_linked_datasets,
    }


def list_stale_datasets(datasets=None, freshness_registry=None, now=None) -> list[dict]:
    datasets = datasets or load_datasets()
    freshness_registry = (
        load_dataset_freshness_registry()
        if freshness_registry is None
        else freshness_registry
    )
    stale_datasets: list[dict] = []

    for name in datasets:
        details = get_dataset_details(
            name,
            datasets=datasets,
            freshness_registry=freshness_registry,
            now=now,
        )
        if details is None or not details.get("freshness", {}).get("is_stale"):
            continue

        stale_datasets.append(
            {
                "name": details["name"],
                "display_name": details["display_name"],
                "refresh_interval_minutes": details["refresh_interval_minutes"],
                "last_updated": details["last_updated"],
                "freshness": details["freshness"],
                "warning": details["warning"],
                "recommended_action": details["recommended_action"],
            }
        )

    return stale_datasets


def evaluate_freshness(last_updated, refresh_interval_minutes, now=None) -> dict:
    now = now or datetime.now(last_updated.tzinfo)
    lag_minutes = (now - last_updated).total_seconds() / 60
    multiplier = 2.0 if refresh_interval_minutes < 720 else 1.5
    stale_threshold_minutes = refresh_interval_minutes * multiplier
    is_stale = lag_minutes > stale_threshold_minutes

    return {
        "refresh_interval_minutes": refresh_interval_minutes,
        "lag_minutes": lag_minutes,
        "stale_threshold_minutes": stale_threshold_minutes,
        "is_stale": is_stale,
        "status": "stale" if is_stale else "fresh",
    }


def search_datasets(query, datasets=None, freshness_registry=None, now=None) -> list[dict]:
    datasets = datasets or load_datasets()
    query_text = query.lower()
    generic_wallet_holdings_query = _question_mentions_generic_protocol_wallet_holdings(query_text)
    cash_safe_validation_query = _question_mentions_cash_safe_validation(query_text)
    matches: list[dict] = []
    exact_alias_matches: list[dict] = []

    for dataset in datasets.values():
        exact_values = [
            dataset.get("name", ""),
            dataset.get("table_name", ""),
            dataset.get("display_name", ""),
            *dataset.get("aliases", []),
        ]
        exact_match = any(query_text == str(value).lower() for value in exact_values if value)
        searchable_values = [
            dataset.get("name", ""),
            dataset.get("display_name", ""),
            dataset.get("description", ""),
        ]
        searchable_values.extend(dataset.get("aliases", []))
        searchable_values.extend(dataset.get("business_meaning", []))
        searchable_values.extend(dataset.get("comparison_notes", []))
        searchable_values.extend(dataset.get("clarifying_questions", []))
        searchable_values.extend(dataset.get("important_columns", []))
        searchable_values.extend(dataset.get("query_notes", []))
        searchable_values.extend(dataset.get("semantic_notes", []))
        searchable_values.extend(dataset.get("use_when", []))
        searchable_values.extend(dataset.get("example_user_intents", []))
        searchable_values.extend(dataset.get("search_keywords", []))

        alias_match = any(
            query_text == str(alias).lower() for alias in dataset.get("aliases", [])
        )
        text_match = any(query_text in str(value).lower() for value in searchable_values)
        if not text_match:
            query_terms = _search_terms(query_text)
            searchable_terms = set(_search_terms(" ".join(str(value) for value in searchable_values)))
            text_match = bool(query_terms) and all(
                term in searchable_terms for term in query_terms
            )
        if generic_wallet_holdings_query:
            if dataset.get("name") == "etherfi_protocol_token_holders":
                text_match = True
            elif dataset.get("name") in {
                "dune.ether_fi.result_etherfi_assets_under_management",
                "dune.ether_fi.result_etherfi_addresses",
                "dune.ether_fi.result_etherfi_cash_events",
                "dune.ether_fi.result_etherfi_cash_borrow_index",
            }:
                text_match = False
        if cash_safe_validation_query:
            if dataset.get("name") == CASH_SAFE_ADDRESSES_DATASET_NAME:
                text_match = True
            elif dataset.get("name") == "dune.ether_fi.result_etherfi_addresses":
                text_match = False

        if exact_match or alias_match:
            details = get_dataset_details(
                dataset["name"],
                datasets=datasets,
                freshness_registry=freshness_registry,
                now=now,
            )
            if details is not None:
                exact_alias_matches.append(details)
            continue

        if dataset.get("hide_from_dataset_search") or dataset.get("is_subtable"):
            continue

        if text_match:
            details = get_dataset_details(
                dataset["name"],
                datasets=datasets,
                freshness_registry=freshness_registry,
                now=now,
            )
            if details is not None:
                matches.append(details)

    if exact_alias_matches:
        return exact_alias_matches

    def priority(match: dict) -> int:
        name = match.get("name")
        if cash_safe_validation_query and name == CASH_SAFE_ADDRESSES_DATASET_NAME:
            return -4
        if generic_wallet_holdings_query and name == "etherfi_protocol_token_holders":
            return -3
        if re.search(r"\bprotocol\s+events?\b", query_text) and name == "dune.ether_fi.result_etherfi_protocol_events":
            return -2
        if (
            re.search(r"\b(back|backs|backing|underlying)\b", query_text)
            and name == "dune.ether_fi.result_etherfi_protocol_token_tvl"
        ):
            return -2
        return 0

    return sorted(matches, key=priority)


def compare_datasets(name_a, name_b, datasets=None) -> dict:
    datasets = datasets or load_datasets()
    resolved_name_a = resolve_dataset_name(name_a, datasets) or name_a
    resolved_name_b = resolve_dataset_name(name_b, datasets) or name_b
    dataset_a = datasets[resolved_name_a]
    dataset_b = datasets[resolved_name_b]

    comparison_summary = (
        f"{resolved_name_a} is the direct holders only view and is "
        f"{dataset_a.get('completeness label')}, while {resolved_name_b} includes broader "
        f"exposure including tracked defi deposits and is "
        f"{dataset_b.get('completeness label')}. "
        f"In {resolved_name_b}, identified_defi_contract is a relevant column."
    )

    return {
        "name_a": resolved_name_a,
        "name_b": resolved_name_b,
        "description_a": dataset_a.get("description"),
        "description_b": dataset_b.get("description"),
        "completeness_a": dataset_a.get("completeness label"),
        "completeness_b": dataset_b.get("completeness label"),
        "use_when_a": dataset_a.get("use_when", []),
        "use_when_b": dataset_b.get("use_when", []),
        "important_columns_a": dataset_a.get("important_columns", []),
        "important_columns_b": dataset_b.get("important_columns", []),
        "comparison_summary": comparison_summary,
    }
