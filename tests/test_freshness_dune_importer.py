import importlib.util
import json
from pathlib import Path
import urllib.request

import yaml


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "update_freshness_from_dune.py"
)
SPEC = importlib.util.spec_from_file_location("update_freshness_from_dune", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_dune_freshness_importer_matches_rows_by_source_query_id(tmp_path):
    output_path = tmp_path / "dataset_freshness.yaml"
    datasets = {
        "dune.ether_fi.result_etherfi_protocol_token_tvl": {
            "source_query_id": 6216803,
        },
        "protocol_token_holders": {
            "source_query_id": 6213381,
        },
    }
    rows = [
        {"query_id": 6216803, "last_updated": "2026-06-01T08:00:00Z"},
        {"query_id": "6213381", "last_updated": "2026-06-01T07:30:00Z"},
    ]

    MODULE.write_dataset_freshness_registry(
        MODULE.build_dataset_freshness_registry_from_rows(rows, datasets=datasets),
        output_path,
    )

    registry = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    assert registry == {
        "dune.ether_fi.result_etherfi_protocol_token_tvl": {
            "last_updated": "2026-06-01T08:00:00Z",
            "query_id": 6216803,
        },
        "protocol_token_holders": {
            "last_updated": "2026-06-01T07:30:00Z",
            "query_id": 6213381,
        },
    }


def test_dune_freshness_importer_ignores_unknown_or_empty_rows():
    datasets = {
        "protocol_token_holders": {
            "source_query_id": 6213381,
        },
    }
    rows = [
        {"query_id": 9999999, "last_updated": "2026-06-01T08:00:00Z"},
        {"query_id": 6213381, "last_updated": ""},
        {"query_id": None, "last_updated": "2026-06-01T08:00:00Z"},
    ]

    registry = MODULE.build_dataset_freshness_registry_from_rows(rows, datasets=datasets)

    assert registry == {}


def test_dune_freshness_importer_accepts_alternate_timestamp_field():
    datasets = {
        "protocol_token_holders": {
            "source_query_id": 6213381,
        },
    }
    rows = [{"source_query_id": 6213381, "latest_freshness_at": "2026-06-01 08:00:00"}]

    registry = MODULE.build_dataset_freshness_registry_from_rows(rows, datasets=datasets)

    assert registry == {
        "protocol_token_holders": {
            "last_updated": "2026-06-01 08:00:00",
            "query_id": 6213381,
        }
    }


def test_dune_freshness_importer_loads_api_key_from_env_or_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("api_key: config-key\n", encoding="utf-8")

    monkeypatch.delenv("DUNE_API_KEY", raising=False)
    assert MODULE.load_dune_api_key(config_path) == "config-key"

    monkeypatch.setenv("DUNE_API_KEY", "env-key")
    assert MODULE.load_dune_api_key(config_path) == "env-key"


def test_dune_freshness_importer_reads_latest_result_endpoint_without_execution(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse(
            {
                "execution_id": "01ABC",
                "result": {
                    "rows": [
                        {
                            "query_id": 6213381,
                            "last_updated": "2026-06-01T08:00:00Z",
                        }
                    ]
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    rows = MODULE.fetch_latest_freshness_rows(
        query_id=7625551,
        api_key="read-only-key",
        base_url="https://api.dune.com/api/v1",
        limit=1000,
        timeout=12,
    )

    assert captured["url"] == "https://api.dune.com/api/v1/query/7625551/results?limit=1000&offset=0"
    assert "execute" not in captured["url"]
    assert captured["headers"]["X-dune-api-key"] == "read-only-key"
    assert captured["timeout"] == 12
    assert rows == [{"query_id": 6213381, "last_updated": "2026-06-01T08:00:00Z"}]
