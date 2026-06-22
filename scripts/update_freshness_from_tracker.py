import argparse
import csv
from html import unescape
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etherfi_catalog.catalog import load_datasets


QUERY_ID_PATTERN = re.compile(r"queries/(\d+)")
ANCHOR_TEXT_PATTERN = re.compile(r">([^<]+)<")


def normalize_display_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def parse_matview_name(value: str | None) -> tuple[str | None, str]:
    value = value or ""
    query_id_match = QUERY_ID_PATTERN.search(value)
    text_match = ANCHOR_TEXT_PATTERN.search(value)
    display_text = unescape(text_match.group(1) if text_match else value)

    return (
        query_id_match.group(1) if query_id_match else None,
        normalize_display_text(display_text),
    )


def build_dataset_freshness_registry(csv_path, datasets=None) -> dict:
    datasets = datasets or load_datasets()
    dataset_names_by_query_id = {
        str(dataset.get("source_query_id")): dataset_name
        for dataset_name, dataset in datasets.items()
        if dataset.get("source_query_id") is not None
    }
    dataset_names_by_source = {
        normalize_display_text(dataset.get("freshness_source_name")): dataset_name
        for dataset_name, dataset in datasets.items()
        if dataset.get("freshness_source_name")
    }
    registry: dict[str, dict] = {}

    with Path(csv_path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            query_id, display_text = parse_matview_name(row.get("matview_name"))
            dataset_name = dataset_names_by_query_id.get(query_id) if query_id else None
            if dataset_name is None:
                dataset_name = dataset_names_by_source.get(display_text)
            last_updated = row.get("last_updated")

            if dataset_name and last_updated:
                registry[dataset_name] = {"last_updated": last_updated}

    return registry


def write_dataset_freshness_registry(registry, output_path="status/dataset_freshness.yaml") -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(registry, f, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument(
        "--output",
        default="status/dataset_freshness.yaml",
    )
    args = parser.parse_args()

    registry = build_dataset_freshness_registry(args.csv_path)
    write_dataset_freshness_registry(registry, args.output)


if __name__ == "__main__":
    main()
