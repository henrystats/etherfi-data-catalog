from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts.studio import ROOT, load_studio_registry
except ModuleNotFoundError:  # Supports direct `python scripts/generate_studio_inventory.py`.
    from studio import ROOT, load_studio_registry


DEFAULT_JSON_PATH = ROOT / "studio" / "query_inventory.json"
DEFAULT_MARKDOWN_PATH = ROOT / "docs" / "studio-query-inventory.md"


def _ordered_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _primary_required_columns(metric: dict) -> list[str]:
    columns = [str(column) for column in metric["columns"]]
    if metric.get("comparison_column"):
        columns.append(str(metric["comparison_column"]))
    return _ordered_unique(columns)


def _registry_checksum(dashboards: list, metrics: list) -> str:
    payload = {
        "dashboards": [dashboard.data for dashboard in dashboards],
        "metrics": [metric.data for metric in metrics],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_contracts(metrics: list) -> dict[str, dict]:
    contracts: dict[str, dict] = {}
    for metric in metrics:
        value = metric.data
        source_name = str(value["data_source"])
        contract = {
            "query_id": int(value["query_id"]),
            "query_url": str(value["query_url"]),
            "data_file": str(value["data_file"]),
            "data_source": source_name,
            "provider_mode": str(value.get("provider_mode") or "fixture"),
            "source_required_columns": [
                str(column)
                for column in (
                    (value.get("transformation") or {}).get(
                        "source_required_columns", []
                    )
                )
            ],
            "transformation": dict(value.get("transformation") or {}),
        }
        existing = contracts.get(source_name)
        if existing is not None and existing != contract:
            raise ValueError(
                f"Studio data source {source_name} has conflicting query mappings"
            )
        contracts[source_name] = contract
    return contracts


def build_inventory() -> dict:
    # Inventory generation is an input to ingestion. It must remain possible to
    # add a new query mapping before a matching generated snapshot exists.
    dashboards, metrics = load_studio_registry(validate_generated_data=False)
    dashboards_by_id = {dashboard.id: dashboard for dashboard in dashboards}
    dashboard_order = {
        dashboard.id: int(dashboard.data["display_order"])
        for dashboard in dashboards
    }
    section_labels = {
        dashboard.id: {
            str(section["id"]): str(section["label"])
            for section in dashboard.data["sections"]
        }
        for dashboard in dashboards
    }
    metrics = sorted(
        metrics,
        key=lambda metric: (
            dashboard_order[metric.dashboard_id],
            int(metric.data["display_order"]),
            metric.id,
        ),
    )
    source_contracts = _source_contracts(metrics)
    metric_records = []
    query_records: dict[int, dict] = {}

    def register_mapping(
        *,
        dashboard_id: str,
        metric_id: str,
        contract: dict,
        columns: list[str],
    ) -> None:
        query_id = int(contract["query_id"])
        record = query_records.setdefault(
            query_id,
            {
                "query_id": query_id,
                "query_url": str(contract["query_url"]),
                "data_file": str(contract["data_file"]),
                "dashboard_ids": set(),
                "metric_ids": set(),
                "data_sources": set(),
                "source_roles": set(),
                "provider_mode": str(contract.get("provider_mode") or "fixture"),
                "source_required_columns": [],
                "transformation": dict(contract.get("transformation") or {}),
                "required_columns": [],
                "optional_columns": [],
            },
        )
        record["dashboard_ids"].add(dashboard_id)
        record["metric_ids"].add(metric_id)
        record["data_sources"].add(str(contract["data_source"]))
        record["source_roles"].add(str(contract["role"]))
        if record["provider_mode"] != str(
            contract.get("provider_mode") or "fixture"
        ):
            raise ValueError(f"Studio query {query_id} has conflicting provider modes")
        if record["transformation"] != dict(contract.get("transformation") or {}):
            raise ValueError(f"Studio query {query_id} has conflicting transformations")
        record["source_required_columns"] = _ordered_unique(
            [
                *record["source_required_columns"],
                *contract.get("source_required_columns", []),
            ]
        )
        record["required_columns"] = _ordered_unique(
            [*record["required_columns"], *columns]
        )
        record["optional_columns"] = _ordered_unique(
            [*record["optional_columns"], *contract.get("optional_columns", [])]
        )

    for metric in metrics:
        value = metric.data
        dashboard = dashboards_by_id[metric.dashboard_id]
        primary_columns = _primary_required_columns(value)
        primary_contract = source_contracts[str(value["data_source"])]
        mappings = [
            {
                "role": "primary",
                **primary_contract,
                "required_columns": primary_columns,
                "optional_columns": [
                    str(column) for column in value.get("optional_columns", [])
                ],
            }
        ]
        register_mapping(
            dashboard_id=dashboard.id,
            metric_id=metric.id,
            contract=mappings[0],
            columns=primary_columns,
        )

        sparkline_source = value.get("sparkline_data_source")
        if sparkline_source:
            sparkline_contract = source_contracts.get(str(sparkline_source))
            if sparkline_contract is None:
                raise ValueError(
                    f"Studio metric {metric.id} has no query mapping for "
                    f"sparkline source {sparkline_source}"
                )
            sparkline_columns = _ordered_unique(
                [
                    str(value.get("sparkline_date_column") or ""),
                    str(value.get("sparkline_column") or ""),
                ]
            )
            mappings.append(
                {
                    "role": "sparkline",
                    **sparkline_contract,
                    "required_columns": sparkline_columns,
                    "optional_columns": [],
                }
            )
            register_mapping(
                dashboard_id=dashboard.id,
                metric_id=metric.id,
                contract=mappings[-1],
                columns=sparkline_columns,
            )

        metric_records.append(
            {
                "dashboard_id": dashboard.id,
                "dashboard": dashboard.name,
                "dashboard_display_order": int(dashboard.data["display_order"]),
                "section_id": str(value["section"]),
                "section": section_labels[dashboard.id][str(value["section"])],
                "metric_id": metric.id,
                "metric": str(value["name"]),
                "display_order": int(value["display_order"]),
                "query_id": int(value["query_id"]),
                "query_url": str(value["query_url"]),
                "data_file": str(value["data_file"]),
                "data_source": str(value["data_source"]),
                "provider_mode": str(value.get("provider_mode") or "fixture"),
                "source_required_columns": [
                    str(column)
                    for column in (
                        (value.get("transformation") or {}).get(
                            "source_required_columns", []
                        )
                    )
                ],
                "transformation": dict(value.get("transformation") or {}),
                "columns": [str(column) for column in value["columns"]],
                "required_columns": primary_columns,
                "optional_columns": [
                    str(column) for column in value.get("optional_columns", [])
                ],
                "dimension_columns": [
                    str(column) for column in value.get("dimension_columns", [])
                ],
                "value_columns": [
                    str(column) for column in value.get("value_columns", [])
                ],
                # Retain the original inventory field for downstream readers
                # while exposing the registry's explicit name in schema v2.
                "visualization": str(value["visualization_type"]),
                "visualization_type": str(value["visualization_type"]),
                "default_visualization": str(
                    value.get("default_visualization")
                    or value["visualization_type"]
                ),
                "allowed_visualizations": [
                    str(item)
                    for item in (
                        value.get("allowed_visualizations")
                        or [value["visualization_type"]]
                    )
                ],
                "value_format": str(
                    value.get("value_format") or value.get("format") or ""
                ),
                "exportable": bool(value["is_exportable"]),
                "allow_empty": bool(value["allow_empty"]),
                "source_label": str(value.get("source_label") or ""),
                "freshness_policy": dict(
                    value.get("effective_freshness_policy")
                    or value.get("freshness_policy")
                    or {}
                ),
                "source_mappings": mappings,
            }
        )

    unique_queries = []
    for query_id in sorted(query_records):
        record = query_records[query_id]
        unique_queries.append(
            {
                "query_id": query_id,
                "query_url": record["query_url"],
                "data_file": record["data_file"],
                "dashboard_ids": sorted(record["dashboard_ids"]),
                "metric_ids": sorted(record["metric_ids"]),
                "data_sources": sorted(record["data_sources"]),
                "source_roles": sorted(record["source_roles"]),
                "provider_mode": record["provider_mode"],
                "source_required_columns": record["source_required_columns"],
                "transformation": record["transformation"],
                "required_columns": record["required_columns"],
                "optional_columns": record["optional_columns"],
            }
        )

    return {
        "schema_version": 2,
        "generated_from": [
            "studio/dashboards.yaml",
            "studio/metrics.yaml",
        ],
        "registry_checksum": _registry_checksum(dashboards, metrics),
        "dashboard_count": len(dashboards),
        "metric_count": len(metric_records),
        "unique_query_count": len(unique_queries),
        "metrics": metric_records,
        "queries": unique_queries,
    }


def render_markdown(inventory: dict) -> str:
    lines = [
        "# Studio query-to-metric inventory",
        "",
        "> Generated by `scripts/generate_studio_inventory.py`; do not edit by hand.",
        "> All listed query IDs are reviewed read-only production sources.",
        f"> Registry checksum: `{inventory['registry_checksum']}`.",
        "",
        "## Metric mappings",
        "",
        "Each row is one source dependency. A metric with a sparkline therefore has a primary row and an auxiliary row; the metric's CSV export still uses only its configured metric columns.",
        "",
        "| Dashboard | Section | Metric | Source role | Query ID | Query URL | Required columns | Default visualization | Allowed visualizations | Value format | Exportable | Data file |",
        "|---|---|---|---|---:|---|---|---|---|---|---|---|",
    ]
    for metric in inventory["metrics"]:
        allowed = ", ".join(
            visualization.title()
            for visualization in metric["allowed_visualizations"]
        )
        for mapping in metric["source_mappings"]:
            columns = ", ".join(
                f"`{column}`" for column in mapping["required_columns"]
            )
            lines.append(
                "| "
                f"{metric['dashboard']} | {metric['section']} | "
                f"{metric['metric']} | {mapping['role'].title()} | "
                f"{mapping['query_id']} | [Open query]({mapping['query_url']}) | "
                f"{columns} | {metric['default_visualization'].title()} | "
                f"{allowed} | `{metric['value_format']}` | "
                f"{'Yes' if metric['exportable'] else 'No'} | "
                f"`{mapping['data_file']}` |"
            )

    lines.extend(
        [
            "",
            "## Unique query fetch plan",
            "",
            "Each query below is fetched once. Multiple metrics may consume different column subsets from the same result.",
            "",
            "| Query ID | Query URL | Provider | Data file | Raw source columns | Published-column union | Optional-column union | Source roles | Consuming metrics |",
            "|---:|---|---|---|---|---|---|---|---|",
        ]
    )
    for query in inventory["queries"]:
        columns = ", ".join(f"`{column}`" for column in query["required_columns"])
        optional_columns = ", ".join(
            f"`{column}`" for column in query["optional_columns"]
        ) or "—"
        source_columns = ", ".join(
            f"`{column}`" for column in query["source_required_columns"]
        ) or "Same as published contract"
        roles = ", ".join(query["source_roles"])
        metrics = ", ".join(f"`{metric_id}`" for metric_id in query["metric_ids"])
        lines.append(
            f"| {query['query_id']} | [Open query]({query['query_url']}) | "
            f"`{query['provider_mode']}` | `{query['data_file']}` | "
            f"{source_columns} | {columns} | {optional_columns} | "
            f"{roles} | {metrics} |"
        )
    return "\n".join(lines) + "\n"


def generated_outputs() -> tuple[str, str]:
    inventory = build_inventory()
    return (
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        render_markdown(inventory),
    )


def write_outputs(
    json_path: Path = DEFAULT_JSON_PATH,
    markdown_path: Path = DEFAULT_MARKDOWN_PATH,
) -> None:
    json_text, markdown_text = generated_outputs()
    Path(json_path).write_text(json_text, encoding="utf-8")
    Path(markdown_path).write_text(markdown_text, encoding="utf-8")


def check_outputs(
    json_path: Path = DEFAULT_JSON_PATH,
    markdown_path: Path = DEFAULT_MARKDOWN_PATH,
) -> list[Path]:
    json_text, markdown_text = generated_outputs()
    expected = {
        Path(json_path): json_text,
        Path(markdown_path): markdown_text,
    }
    return [
        path
        for path, content in expected.items()
        if not path.exists() or path.read_text(encoding="utf-8") != content
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic Studio query-to-metric inventory."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when checked-in inventory files do not match the registry.",
    )
    args = parser.parse_args()
    if args.check:
        mismatches = check_outputs()
        if mismatches:
            for path in mismatches:
                print(f"Studio inventory is out of date: {path.relative_to(ROOT)}")
            return 1
        print("Studio inventory is up to date.")
        return 0
    write_outputs()
    print(
        "Wrote "
        f"{DEFAULT_JSON_PATH.relative_to(ROOT)} and "
        f"{DEFAULT_MARKDOWN_PATH.relative_to(ROOT)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
