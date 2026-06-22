from __future__ import annotations

import argparse
import asyncio
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


EXPECTED_HTTP_SMOKE_TOOLS = {
    "search_datasets",
    "get_dataset_details",
    "search_dashboards",
    "get_dataset_status",
    "plan_etherfi_query",
}

AUTH_HEADER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


@dataclass(frozen=True)
class SmokeConfig:
    url: str | None
    host: str
    port: int
    query: str
    timeout_seconds: float
    bearer_token: str | None
    auth_header_name: str


def normalize_auth_header_name(name: str) -> str:
    normalized = name.strip()
    if not normalized or not AUTH_HEADER_NAME_PATTERN.fullmatch(normalized):
        raise ValueError("Auth header name must contain only letters, numbers, and hyphens.")
    return normalized


def build_auth_headers(bearer_token: str | None, auth_header_name: str) -> dict[str, str]:
    if not bearer_token:
        return {}
    return {normalize_auth_header_name(auth_header_name): f"Bearer {bearer_token}"}


def find_free_port(host: str) -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def parse_args(argv: Sequence[str] | None = None) -> SmokeConfig:
    parser = argparse.ArgumentParser(
        description="Smoke test the ether.fi catalog MCP Streamable HTTP endpoint.",
    )
    parser.add_argument(
        "--url",
        help="Existing MCP Streamable HTTP URL to test. If omitted, this script starts a local server.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Local host to use when starting the server. Defaults to 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Local port to use when starting the server. Defaults to a free ephemeral port.",
    )
    parser.add_argument(
        "--query",
        default="cash events",
        help="Safe metadata-only search query to call through the MCP tool.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for the server/client handshake.",
    )
    parser.add_argument(
        "--bearer-token",
        help="Bearer token for authenticated MCP endpoints. The token is never printed.",
    )
    parser.add_argument(
        "--auth-header-name",
        default="Authorization",
        help="Header name for bearer auth. Defaults to Authorization.",
    )
    args = parser.parse_args(argv)
    try:
        auth_header_name = normalize_auth_header_name(args.auth_header_name)
    except ValueError as exc:
        parser.error(str(exc))

    return SmokeConfig(
        url=args.url,
        host=args.host,
        port=args.port,
        query=args.query,
        timeout_seconds=args.timeout,
        bearer_token=args.bearer_token,
        auth_header_name=auth_header_name,
    )


async def verify_mcp_endpoint(
    url: str,
    query: str,
    timeout_seconds: float,
    auth_headers: dict[str, str] | None = None,
) -> tuple[int, int]:
    timeout = httpx.Timeout(timeout_seconds, read=timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, headers=auth_headers or {}) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = {tool.name for tool in tools.tools}
                missing_tools = sorted(EXPECTED_HTTP_SMOKE_TOOLS - tool_names)
                if missing_tools:
                    raise RuntimeError(f"Missing expected MCP tools: {', '.join(missing_tools)}")

                result = await session.call_tool("search_datasets", {"query": query})
                if result.isError:
                    raise RuntimeError("search_datasets returned an MCP tool error.")
                if not result.content:
                    raise RuntimeError("search_datasets returned no content.")

                return len(tool_names), len(result.content)


async def wait_for_mcp_endpoint(
    url: str,
    query: str,
    timeout_seconds: float,
    auth_headers: dict[str, str] | None = None,
) -> tuple[int, int]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return await verify_mcp_endpoint(
                url,
                query,
                timeout_seconds=min(3.0, timeout_seconds),
                auth_headers=auth_headers,
            )
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.25)
    raise RuntimeError(f"MCP Streamable HTTP smoke test failed: {last_error}") from last_error


def start_local_server(host: str, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env.pop("DUNE_API_KEY", None)
    command = [
        sys.executable,
        "-m",
        "etherfi_catalog.server",
        "--transport",
        "streamable-http",
        "--host",
        host,
        "--port",
        str(port),
    ]
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main(argv: Sequence[str] | None = None) -> None:
    config = parse_args(argv)
    process: subprocess.Popen | None = None
    url = config.url

    if url is None:
        port = config.port or find_free_port(config.host)
        url = f"http://{config.host}:{port}/mcp"
        process = start_local_server(config.host, port)

    auth_headers = build_auth_headers(config.bearer_token, config.auth_header_name)

    try:
        if process is not None and process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise SystemExit(
                f"MCP server exited before smoke test. code={process.returncode}\n"
                f"stdout={stdout}\nstderr={stderr}"
            )

        tool_count, content_count = asyncio.run(
            wait_for_mcp_endpoint(
                url,
                config.query,
                config.timeout_seconds,
                auth_headers=auth_headers,
            )
        )
    finally:
        if process is not None:
            stop_server(process)

    print(
        "Streamable HTTP MCP smoke test passed: "
        f"{tool_count} tools listed; search_datasets returned {content_count} content item(s). "
        f"Endpoint: {url}"
    )


if __name__ == "__main__":
    main()
