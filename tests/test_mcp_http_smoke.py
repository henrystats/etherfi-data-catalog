from scripts import smoke_mcp_http


def test_http_smoke_config_defaults_to_local_ephemeral_port():
    config = smoke_mcp_http.parse_args([])

    assert config.url is None
    assert config.host == "127.0.0.1"
    assert config.port == 0
    assert config.query == "cash events"
    assert config.timeout_seconds == 10.0
    assert config.bearer_token is None
    assert config.auth_header_name == "Authorization"


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
    assert config.bearer_token is None


def test_http_smoke_config_accepts_bearer_token():
    config = smoke_mcp_http.parse_args(
        [
            "--url",
            "https://example.run.app/mcp",
            "--bearer-token",
            "not-a-real-token",
        ]
    )

    assert config.url == "https://example.run.app/mcp"
    assert config.bearer_token == "not-a-real-token"
    assert config.auth_header_name == "Authorization"


def test_http_smoke_config_accepts_custom_auth_header_name():
    config = smoke_mcp_http.parse_args(
        [
            "--url",
            "https://example.run.app/mcp",
            "--bearer-token",
            "not-a-real-token",
            "--auth-header-name",
            "X-Serverless-Authorization",
        ]
    )

    assert config.auth_header_name == "X-Serverless-Authorization"


def test_http_smoke_config_rejects_invalid_auth_header_name():
    try:
        smoke_mcp_http.parse_args(
            [
                "--url",
                "https://example.run.app/mcp",
                "--bearer-token",
                "not-a-real-token",
                "--auth-header-name",
                "Bad Header",
            ]
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Invalid auth header name should exit through argparse.")


def test_http_smoke_builds_default_authorization_header():
    headers = smoke_mcp_http.build_auth_headers("not-a-real-token", "Authorization")

    assert headers == {"Authorization": "Bearer not-a-real-token"}


def test_http_smoke_builds_custom_auth_header():
    headers = smoke_mcp_http.build_auth_headers(
        "not-a-real-token",
        "X-Serverless-Authorization",
    )

    assert headers == {"X-Serverless-Authorization": "Bearer not-a-real-token"}


def test_http_smoke_omits_auth_headers_without_token():
    assert smoke_mcp_http.build_auth_headers(None, "Authorization") == {}


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


def test_http_smoke_main_does_not_print_bearer_token(monkeypatch, capsys):
    async def fake_wait_for_mcp_endpoint(url, query, timeout_seconds, auth_headers=None):
        assert url == "https://example.run.app/mcp"
        assert query == "cash events"
        assert timeout_seconds == 10.0
        assert auth_headers == {"Authorization": "Bearer not-a-real-token"}
        return 12, 1

    monkeypatch.setattr(
        smoke_mcp_http,
        "wait_for_mcp_endpoint",
        fake_wait_for_mcp_endpoint,
    )

    smoke_mcp_http.main(
        [
            "--url",
            "https://example.run.app/mcp",
            "--bearer-token",
            "not-a-real-token",
        ]
    )

    output = capsys.readouterr().out
    assert "Streamable HTTP MCP smoke test passed" in output
    assert "not-a-real-token" not in output
    assert "Authorization" not in output
