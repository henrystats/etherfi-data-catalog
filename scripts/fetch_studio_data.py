from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

import yaml

try:
    from scripts.studio_ingestion import (
        DEFAULT_FIXTURE_SCENARIOS_PATH,
        DEFAULT_STUDIO_OUTPUT_ROOT,
        DuneLatestResultClient,
        FixtureDuneClient,
        RoutedStudioLatestResultClient,
        RetryPolicy,
        SnapshotStore,
        StudioIngestionError,
        generated_query_ids,
        iso_utc,
        load_query_requests,
        refresh_studio_data,
        validate_current_snapshot,
    )
except ModuleNotFoundError:  # Supports direct `python scripts/fetch_studio_data.py`.
    from studio_ingestion import (  # type: ignore
        DEFAULT_FIXTURE_SCENARIOS_PATH,
        DEFAULT_STUDIO_OUTPUT_ROOT,
        DuneLatestResultClient,
        FixtureDuneClient,
        RoutedStudioLatestResultClient,
        RetryPolicy,
        SnapshotStore,
        StudioIngestionError,
        generated_query_ids,
        iso_utc,
        load_query_requests,
        refresh_studio_data,
        validate_current_snapshot,
    )


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return parsed


def _nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and atomically promote validated Studio query snapshots."
    )
    parser.add_argument(
        "--fixture-mode",
        action="store_true",
        help="Use deterministic local fixtures instead of the Dune API.",
    )
    parser.add_argument(
        "--mixed-source-mode",
        action="store_true",
        help=(
            "Use Dune latest stored results only for registry entries marked "
            "latest_result, while retaining explicit fixture-backed entries."
        ),
    )
    parser.add_argument(
        "--fixture-scenario",
        default="success",
        help="Named scenario from studio/fixtures/scenarios.yaml.",
    )
    parser.add_argument(
        "--fixture-scenarios",
        type=Path,
        default=DEFAULT_FIXTURE_SCENARIOS_PATH,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--fixture-now",
        type=_parse_timestamp,
        help="Override the fixture clock for deterministic tests.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the registry and active snapshot without fetching or writing.",
    )
    parser.add_argument(
        "--query-id",
        action="append",
        type=_positive_int,
        help="Refresh one query ID; repeat to select several.",
    )
    parser.add_argument(
        "--dashboard",
        action="append",
        help="Refresh queries used by a dashboard ID; repeat to select several.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_STUDIO_OUTPUT_ROOT,
        help="Snapshot root containing state.json, snapshots/, and attempts/.",
    )
    parser.add_argument(
        "--keep-previous",
        nargs="?",
        type=_nonnegative_int,
        const=1,
        default=1,
        metavar="COUNT",
        help="Retain COUNT prior valid snapshots (default: 1).",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Explicitly reuse current files for failed queries; fail closed by default.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Promote even when the same execution and content are already active.",
    )
    parser.add_argument("--timeout", type=_positive_float, default=30.0)
    parser.add_argument("--max-attempts", type=_positive_int, default=3)
    parser.add_argument("--backoff", type=_nonnegative_float, default=0.25)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dashboards, _, requests = load_query_requests()
        if args.validate_only:
            store = SnapshotStore(args.output_dir)
            current_dir = store.current_snapshot_dir()
            manifest = (
                validate_current_snapshot(args.output_dir)
                if current_dir is not None
                else None
            )
            print(
                json.dumps(
                    {
                        "status": "valid",
                        "registry_valid": True,
                        "active_snapshot": manifest is not None,
                        "snapshot_id": manifest.get("snapshot_id") if manifest else None,
                        "unique_query_count": (
                            manifest.get("unique_query_count")
                            if manifest
                            else len(generated_query_ids(dashboards, requests))
                        ),
                        "output_root": str(args.output_dir),
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.fixture_mode and args.mixed_source_mode:
            raise ValueError("Choose either --fixture-mode or --mixed-source-mode")

        if args.fixture_mode:
            clock = (
                (lambda: args.fixture_now)
                if args.fixture_now is not None
                else (lambda: datetime.now(timezone.utc))
            )
            client = FixtureDuneClient(
                requests,
                dashboards,
                scenario=args.fixture_scenario,
                scenarios_path=args.fixture_scenarios,
                clock=clock,
            )
            mode = "fixture"
        else:
            if args.fixture_now is not None or args.fixture_scenario != "success":
                raise ValueError(
                    "Fixture-only options require --fixture-mode"
                )
            clock = lambda: datetime.now(timezone.utc)
            if os.environ.get("STUDIO_ENABLE_LIVE_DUNE") != "1":
                raise ValueError(
                    "Live Dune fetching is disabled. Use --fixture-mode, or set "
                    "STUDIO_ENABLE_LIVE_DUNE=1 only after production query review."
                )
            api_key = os.environ.get("DUNE_API_KEY")
            if not api_key:
                raise ValueError("DUNE_API_KEY is required for explicitly enabled live mode")
            dune_client = DuneLatestResultClient(api_key)
            if args.mixed_source_mode:
                fixture_client = FixtureDuneClient(
                    requests,
                    dashboards,
                    scenario="success",
                    scenarios_path=args.fixture_scenarios,
                    clock=clock,
                )
                routes = {
                    query_id: (
                        dune_client
                        if request.provider_mode == "latest_result"
                        else fixture_client
                    )
                    for query_id, request in requests.items()
                }
                client = RoutedStudioLatestResultClient(routes)
                mode = "mixed"
            else:
                generated_ids = generated_query_ids(dashboards, requests)
                fixture_backed = sorted(
                    query_id
                    for query_id in generated_ids
                    if requests[query_id].provider_mode != "latest_result"
                )
                if fixture_backed:
                    raise ValueError(
                        "Live mode requires every generated query to use the "
                        "latest_result provider; use --mixed-source-mode during "
                        "the explicit transitional fixture rollout"
                    )
                client = dune_client
                mode = "live"

        logger = (
            (lambda message: print(message, file=sys.stderr))
            if args.verbose
            else None
        )
        summary = refresh_studio_data(
            client,
            output_root=args.output_dir,
            mode=mode,
            query_ids=set(args.query_id or []),
            dashboard_ids=set(args.dashboard or []),
            keep_previous=args.keep_previous,
            force=args.force,
            allow_partial=args.allow_partial,
            timeout_seconds=args.timeout,
            retry_policy=RetryPolicy(
                max_attempts=args.max_attempts,
                base_delay_seconds=args.backoff,
            ),
            clock=clock,
            logger=logger,
        )
        print(json.dumps(summary.as_dict(), sort_keys=True))
        return 0
    except (StudioIngestionError, ValueError, OSError, yaml.YAMLError) as exc:
        payload = {
            "status": "failed",
            "error": str(exc),
        }
        if isinstance(exc, StudioIngestionError):
            payload.update(exc.as_dict())
            payload["status"] = "failed"
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
