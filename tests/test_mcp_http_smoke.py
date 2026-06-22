from scripts import smoke_mcp_http


def test_http_smoke_config_defaults_to_local_ephemeral_port():
    config = smoke_mcp_http.parse_args([])

    assert config.url is None
    assert config.host == "127.0.0.1"
    assert config.port == 0
    assert config.query == "cash events"
    assert config.timeout_seconds == 10.0


def test_http_smoke_config_accepts_existing_url():
    config = smoke_mcp_http.parse_args(
        [
            "--url",
            "http://127.0.0.1:8001/mcp",
            "--query",
            "protocol token tvl",
            "--timeout",
            "3",
        ]
    )

    assert config.url == "http://127.0.0.1:8001/mcp"
    assert config.query == "protocol token tvl"
    assert config.timeout_seconds == 3.0


def test_http_smoke_expected_tools_cover_metadata_handshake_tools():
    assert {
        "search_datasets",
        "get_dataset_details",
        "search_dashboards",
        "get_dataset_status",
        "plan_etherfi_query",
    } <= smoke_mcp_http.EXPECTED_HTTP_SMOKE_TOOLS


def test_http_smoke_server_subprocess_does_not_receive_dune_key(monkeypatch):
    captured = {}

    class FakeProcess:
        stdout = None
        stderr = None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setenv("DUNE_API_KEY", "test-key-value-not-real")
    monkeypatch.setattr(smoke_mcp_http.subprocess, "Popen", fake_popen)

    smoke_mcp_http.start_local_server("127.0.0.1", 8001)

    assert "DUNE_API_KEY" not in captured["env"]
    assert captured["command"][-4:] == [
        "--host",
        "127.0.0.1",
        "--port",
        "8001",
    ]
