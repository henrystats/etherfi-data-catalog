import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.catalog import load_datasets


DEFAULT_FRESHNESS_QUERY_ID = 7625551
DEFAULT_DUNE_API_BASE_URL = "https://api.dune.com/api/v1"
DEFAULT_DUNE_CONFIG_PATH = Path.home() / ".config" / "dune" / "config.yaml"


def _rows_from_result(result) -> list[dict]:
    rows = getattr(result, "rows", None)
    if rows is None and hasattr(result, "result"):
        rows = getattr(result.result, "rows", None)
    if rows is None:
        if isinstance(result, dict):
            nested_result = result.get("result")
            if isinstance(nested_result, dict):
                rows = nested_result.get("rows")
            rows = rows or result.get("rows")
    if rows is None:
        return []
    return list(rows)


def _normalize_query_id(value) -> str | None:
    if value is None or value == "":
        return None
    return str(value).strip()


def _last_updated_from_row(row: dict):
    return (
        row.get("last_updated")
        or row.get("latest_freshness_at")
        or row.get("latest_updated_at")
    )


def load_dune_api_key(config_path=DEFAULT_DUNE_CONFIG_PATH) -> str | None:
    env_key = os.getenv("DUNE_API_KEY")
    if env_key:
        return env_key

    config_path = Path(config_path)
    if not config_path.exists():
        return None

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    api_key = config.get("api_key")
    if api_key:
        return str(api_key)
    return None


def build_dataset_freshness_registry_from_rows(rows, datasets=None) -> dict:
    datasets = datasets or load_datasets()
    dataset_names_by_query_id = {
        str(dataset.get("source_query_id")): dataset_name
        for dataset_name, dataset in datasets.items()
        if dataset.get("source_query_id") is not None
    }

    registry: dict[str, dict] = {}
    for row in rows:
        query_id = _normalize_query_id(row.get("query_id") or row.get("source_query_id"))
        dataset_name = dataset_names_by_query_id.get(query_id)
        last_updated = _last_updated_from_row(row)

        if dataset_name and last_updated:
            snapshot = {"last_updated": str(last_updated)}
            if query_id:
                snapshot["query_id"] = int(query_id) if query_id.isdigit() else query_id
            registry[dataset_name] = snapshot

    return registry


def latest_results_url(
    query_id=DEFAULT_FRESHNESS_QUERY_ID,
    *,
    base_url=DEFAULT_DUNE_API_BASE_URL,
    limit=1000,
    offset=0,
) -> str:
    params = urllib.parse.urlencode({"limit": int(limit), "offset": int(offset)})
    return f"{base_url.rstrip('/')}/query/{int(query_id)}/results?{params}"


def fetch_latest_freshness_rows(
    query_id=DEFAULT_FRESHNESS_QUERY_ID,
    api_key=None,
    *,
    base_url=DEFAULT_DUNE_API_BASE_URL,
    limit=1000,
    offset=0,
    timeout=30,
):
    api_key = api_key or load_dune_api_key()
    if not api_key:
        raise RuntimeError(
            "A Dune API key is required to fetch freshness from Dune. Set DUNE_API_KEY "
            "or run `dune auth` to save a read-only key in ~/.config/dune/config.yaml."
        )

    url = latest_results_url(query_id, base_url=base_url, limit=limit, offset=offset)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-DUNE-API-KEY": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Failed to fetch latest Dune result for query {query_id}: "
            f"HTTP {exc.code} {body}"
        ) from exc

    return _rows_from_result(payload)


def write_dataset_freshness_registry(registry, output_path="status/dataset_freshness.yaml") -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(registry, f, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch latest ether.fi catalog freshness rows from a saved Dune query."
    )
    parser.add_argument(
        "--query-id",
        type=int,
        default=DEFAULT_FRESHNESS_QUERY_ID,
        help="Saved Dune query that returns query_id and last_updated rows.",
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=24,
        help=(
            "Deprecated compatibility flag. The importer now only reads the latest "
            "stored result and never triggers query execution."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum rows to read from the latest stored Dune query result.",
    )
    parser.add_argument(
        "--output",
        default="status/dataset_freshness.yaml",
        help="Output YAML snapshot consumed by the website builder.",
    )
    args = parser.parse_args()

    rows = fetch_latest_freshness_rows(
        query_id=args.query_id,
        limit=args.limit,
    )
    registry = build_dataset_freshness_registry_from_rows(rows)
    write_dataset_freshness_registry(registry, args.output)
    print(f"Wrote {len(registry)} freshness rows to {args.output}")


if __name__ == "__main__":
    main()
