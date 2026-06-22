import importlib.util
from pathlib import Path

import yaml


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "update_freshness_from_tracker.py"
)
SPEC = importlib.util.spec_from_file_location("update_freshness_from_tracker", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_tracker_importer_matches_html_matview_name_by_extracted_query_id(tmp_path):
    csv_path = tmp_path / "tracker.csv"
    output_path = tmp_path / "dataset_freshness.yaml"
    csv_path.write_text(
        "matview_name,last_updated\n"
        "\"<a href='https://dune.com/queries/6213381' target='_blank'>Wrong Display Name</a>\",2026-04-08T10:00:00Z\n",
        encoding="utf-8",
    )

    MODULE.write_dataset_freshness_registry(
        MODULE.build_dataset_freshness_registry(csv_path),
        output_path,
    )

    registry = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    assert registry == {
        "etherfi_protocol_token_holders": {"last_updated": "2026-04-08T10:00:00Z"}
    }


def test_tracker_importer_matches_by_normalized_display_text_without_usable_query_id(tmp_path):
    csv_path = tmp_path / "tracker.csv"
    output_path = tmp_path / "dataset_freshness.yaml"
    csv_path.write_text(
        "matview_name,last_updated\n"
        "\"  tokens   prices usd (minute)  \",2026-04-08T10:00:00Z\n",
        encoding="utf-8",
    )

    MODULE.write_dataset_freshness_registry(
        MODULE.build_dataset_freshness_registry(csv_path),
        output_path,
    )

    registry = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    assert registry == {
        "dune.ether_fi.result_tokens_prices_usd": {"last_updated": "2026-04-08T10:00:00Z"}
    }


def test_tracker_importer_ignores_unknown_rows(tmp_path):
    csv_path = tmp_path / "tracker.csv"
    output_path = tmp_path / "dataset_freshness.yaml"
    csv_path.write_text(
        "matview_name,last_updated\n"
        "\"<a href='https://dune.com/queries/9999999' target='_blank'>Unknown Matview</a>\",2026-04-08T10:00:00Z\n",
        encoding="utf-8",
    )

    MODULE.write_dataset_freshness_registry(
        MODULE.build_dataset_freshness_registry(csv_path),
        output_path,
    )

    registry = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    assert registry == {}
