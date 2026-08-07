import json
import os
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
DEPLOY_WRAPPER_PATH = WORKFLOWS_DIR / "deploy-website.yml"
STUDIO_LIVE_WORKFLOW_PATH = WORKFLOWS_DIR / "studio-live-refresh.yml"
STUDIO_PRODUCTION_WORKFLOW_PATH = WORKFLOWS_DIR / "studio-production-deploy.yml"
STUDIO_FIXTURE_WORKFLOW_PATH = WORKFLOWS_DIR / "studio-fixture-refresh.yml"
SHARED_WORKFLOW_REFERENCE = "./.github/workflows/studio-production-deploy.yml"
STUDIO_LIVE_OUTPUT = '"$RUNNER_TEMP/studio-live-generated"'
STUDIO_ARTIFACT_PREFIX = "studio-live-snapshot-"


def load_workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def only_job(workflow: dict) -> dict:
    assert len(workflow["jobs"]) == 1
    return next(iter(workflow["jobs"].values()))


def step_with_run(steps: list[dict], text: str) -> dict:
    matches = [step for step in steps if text in str(step.get("run") or "")]
    assert len(matches) == 1, text
    return matches[0]


def step_with_action(steps: list[dict], action: str) -> dict:
    matches = [step for step in steps if step.get("uses") == action]
    assert len(matches) == 1, action
    return matches[0]


def run_studio_resolver(
    script: str,
    *,
    runs: list[dict],
    artifacts: list[dict],
    requested_run_id: str = "",
) -> dict:
    node_source = f"""
const context = {{ repo: {{ owner: "henrystats", repo: "etherfi-data-catalog" }} }};
const runs = {json.dumps(runs)};
const artifacts = {json.dumps(artifacts)};
const outputs = {{}};
const github = {{ rest: {{ actions: {{
  async listWorkflowRuns() {{ return {{ data: {{ workflow_runs: runs }} }}; }},
  async getWorkflowRun({{ run_id }}) {{
    return {{ data: runs.find((run) => run.id === run_id) }};
  }},
  async listWorkflowRunArtifacts() {{ return {{ data: {{ artifacts }} }}; }},
}} }} }};
const core = {{ setOutput(name, value) {{ outputs[name] = value; }} }};
(async () => {{
{script}
}})().then(
  (result) => console.log(JSON.stringify({{ result, outputs }})),
  (error) => console.log(JSON.stringify({{ error: error.message, outputs }})),
);
"""
    env = {
        **os.environ,
        "REQUESTED_RUN_ID": requested_run_id,
        "STUDIO_WORKFLOW_PATH": "studio-live-refresh.yml",
        "REQUIRED_BRANCH": "main",
    }
    completed = subprocess.run(
        ["node", "-e", node_source],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(completed.stdout)


def trusted_studio_run(
    run_id: int,
    *,
    event: str = "schedule",
    path: str = ".github/workflows/studio-live-refresh.yml@main",
) -> dict:
    return {
        "id": run_id,
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "path": path,
        "head_repository": {"full_name": "henrystats/etherfi-data-catalog"},
        "event": event,
        "run_attempt": 1,
    }


def assert_shared_deployment_caller(
    path: Path,
    *,
    expected_trigger: dict,
    expected_inputs: dict | None = None,
) -> dict:
    workflow = load_workflow(path)

    assert workflow["on"] == expected_trigger
    assert workflow["permissions"] == {}
    job = only_job(workflow)
    assert job["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert job["uses"] == SHARED_WORKFLOW_REFERENCE
    assert job["secrets"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    assert job.get("with", {}) == (expected_inputs or {})
    assert "steps" not in job
    return job


def test_push_deploy_uses_the_same_snapshot_consumer_as_freshness_deploys():
    job = assert_shared_deployment_caller(
        DEPLOY_WRAPPER_PATH,
        expected_trigger={"push": {"branches": ["main"]}},
    )

    assert "if" not in job
    workflow_text = DEPLOY_WRAPPER_PATH.read_text(encoding="utf-8")
    assert "scripts/fetch_studio_data.py" not in workflow_text
    assert "scripts/update_freshness_from_dune.py" not in workflow_text
    assert "actions/deploy-pages" not in workflow_text


def test_live_studio_refresh_is_a_manual_four_hour_snapshot_producer_only():
    workflow_text = STUDIO_LIVE_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = load_workflow(STUDIO_LIVE_WORKFLOW_PATH)

    assert workflow["name"] == "Refresh live Studio data snapshot"
    assert workflow["on"] == {
        "workflow_dispatch": "",
        "schedule": [{"cron": "25 */4 * * *"}],
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "studio-live-snapshot",
        "cancel-in-progress": "true",
    }

    cron_fields = workflow["on"]["schedule"][0]["cron"].split()
    assert cron_fields == ["25", "*/4", "*", "*", "*"]
    job = only_job(workflow)
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert "permissions" not in job
    assert "uses" not in job
    assert "pages" not in workflow_text
    assert "id-token" not in workflow_text
    assert "actions/configure-pages" not in workflow_text
    assert "actions/upload-pages-artifact" not in workflow_text
    assert "actions/deploy-pages" not in workflow_text
    assert SHARED_WORKFLOW_REFERENCE not in workflow_text
    assert "scripts/update_freshness_from_dune.py" not in workflow_text
    assert "actions/download-artifact" not in workflow_text


def test_live_studio_refresh_fetches_validates_and_uploads_one_temporary_snapshot():
    workflow = load_workflow(STUDIO_LIVE_WORKFLOW_PATH)
    job = workflow["jobs"]["refresh-snapshot"]
    steps = job["steps"]

    preflight = step_with_run(steps, 'if [ -z "${DUNE_API_KEY:-}" ]')
    inventory = step_with_run(steps, "scripts/generate_studio_inventory.py --check")
    seed = step_with_run(steps, "website/data/studio/generated")
    refresh_candidates = [
        step
        for step in steps
        if "scripts/fetch_studio_data.py" in str(step.get("run") or "")
        and "--validate-only" not in str(step.get("run") or "")
    ]
    validation_candidates = [
        step
        for step in steps
        if "scripts/fetch_studio_data.py" in str(step.get("run") or "")
        and "--validate-only" in str(step.get("run") or "")
    ]
    assert len(refresh_candidates) == 1
    assert len(validation_candidates) == 1
    refresh = refresh_candidates[0]
    validation = validation_candidates[0]
    tests = step_with_run(steps, "python -m pytest")
    build = step_with_run(steps, "scripts/build_website.py")
    uploads = [
        step for step in steps if step.get("uses") == "actions/upload-artifact@v4"
    ]
    assert len(uploads) == 2
    success_upload = next(
        step
        for step in uploads
        if step["with"].get("name", "").startswith(STUDIO_ARTIFACT_PREFIX)
    )

    ordered = [
        preflight,
        inventory,
        seed,
        refresh,
        validation,
        tests,
        build,
        success_upload,
    ]
    assert [steps.index(step) for step in ordered] == sorted(
        steps.index(step) for step in ordered
    )

    assert preflight["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    assert refresh["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
        "STUDIO_ENABLE_LIVE_DUNE": "1",
    }
    secret_steps = [
        step for step in steps if "DUNE_API_KEY" in (step.get("env") or {})
    ]
    assert secret_steps == [preflight, refresh]

    seed_command = str(seed["run"])
    assert "website/data/studio/generated" in seed_command
    assert STUDIO_LIVE_OUTPUT in seed_command

    refresh_command = str(refresh["run"])
    assert f"--output-dir {STUDIO_LIVE_OUTPUT}" in refresh_command
    assert "--keep-previous 1" in refresh_command
    assert "--force" in refresh_command
    for forbidden in (
        "--fixture-mode",
        "--mixed-source-mode",
        "--allow-partial",
        "--query-id",
        "--dashboard",
        "run_query",
        "run_query_dataframe",
        "execute_query",
        "refresh_query",
        "max_age_hours",
        "/execute",
    ):
        assert forbidden not in refresh_command

    validation_command = str(validation["run"])
    assert "--validate-only" in validation_command
    assert f"--output-dir {STUDIO_LIVE_OUTPUT}" in validation_command
    assert f"--studio-generated-data {STUDIO_LIVE_OUTPUT}" in str(build["run"])

    assert success_upload.get("if") is None
    assert success_upload["with"] == {
        "name": (
            "studio-live-snapshot-${{ github.run_id }}-"
            "${{ github.run_attempt }}"
        ),
        "path": (
            "${{ runner.temp }}/studio-live-generated/state.json\n"
            "${{ runner.temp }}/studio-live-generated/snapshots/\n"
        ),
        "if-no-files-found": "error",
        "retention-days": "2",
    }
    assert "attempts/" not in success_upload["with"]["path"]
    failure_upload = next(step for step in uploads if step is not success_upload)
    assert failure_upload["if"] == "${{ failure() }}"
    assert failure_upload["with"]["name"].startswith(
        "studio-live-refresh-failure-"
    )
    assert not failure_upload["with"]["name"].startswith(STUDIO_ARTIFACT_PREFIX)


def test_shared_deployment_requires_only_freshness_dune_access_and_artifact_read_access():
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)

    assert set(workflow["on"]) == {"workflow_call"}
    workflow_call = workflow["on"]["workflow_call"]
    assert workflow_call["inputs"] == {
        "studio_run_id": {
            "description": "Optional successful Studio snapshot workflow run to consume",
            "required": "false",
            "type": "string",
            "default": "",
        }
    }
    declared_secrets = workflow_call["secrets"]
    assert set(declared_secrets) == {"DUNE_API_KEY"}
    assert declared_secrets["DUNE_API_KEY"]["required"] == "true"
    assert workflow["permissions"] == {}
    assert "env" not in workflow

    assert set(workflow["jobs"]) == {"build", "deploy"}
    build_job = workflow["jobs"]["build"]
    deploy_job = workflow["jobs"]["deploy"]
    assert build_job["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert deploy_job["permissions"] == {
        "pages": "write",
        "id-token": "write",
    }
    assert "env" not in build_job
    assert "env" not in deploy_job

    secret_steps = [
        step
        for step in build_job["steps"]
        if "DUNE_API_KEY" in (step.get("env") or {})
    ]
    assert len(secret_steps) == 2
    preflight = step_with_run(secret_steps, 'if [ -z "${DUNE_API_KEY:-}" ]')
    catalog_refresh = step_with_run(
        secret_steps,
        "scripts/update_freshness_from_dune.py --query-id 7625551",
    )
    assert preflight["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    assert catalog_refresh["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    assert "STUDIO_ENABLE_LIVE_DUNE" not in STUDIO_PRODUCTION_WORKFLOW_PATH.read_text(
        encoding="utf-8"
    )


def test_shared_deployment_resolves_only_a_successful_trusted_main_studio_run():
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)
    steps = workflow["jobs"]["build"]["steps"]
    resolver = step_with_action(steps, "actions/github-script@v9")
    downloader = step_with_action(steps, "actions/download-artifact@v4")

    assert resolver["id"] == "studio-run"
    assert resolver["env"] == {
        "REQUESTED_RUN_ID": "${{ inputs.studio_run_id }}",
        "STUDIO_WORKFLOW_PATH": "studio-live-refresh.yml",
        "REQUIRED_BRANCH": "main",
    }
    assert resolver["with"]["github-token"] == "${{ github.token }}"
    assert resolver["with"]["result-encoding"] == "string"
    assert int(resolver["with"]["retries"]) >= 1
    script = str(resolver["with"]["script"])
    for required in (
        "github.rest.actions.getWorkflowRun",
        "github.rest.actions.listWorkflowRuns",
        "github.rest.actions.listWorkflowRunArtifacts",
        "workflow_id: workflowPath",
        "branch: requiredBranch",
        'status: "success"',
        'candidate.status === "completed"',
        'candidate.conclusion === "success"',
        "candidate.head_branch === requiredBranch",
        "candidate.path",
        "candidate.head_repository?.full_name === expectedRepository",
        'trustedEvents.has(candidate.event)',
        "No successful Studio snapshot workflow run is available.",
        "is not a successful trusted",
        "run.id !== newestRun.id",
        "older than newest eligible run",
        "artifact.expired === false",
        'core.setOutput("run_id"',
        'core.setOutput("artifact_id"',
    ):
        assert required in script
    assert "/^\\d+$/.test(requestedRunId)" in script

    assert downloader["with"] == {
        "artifact-ids": "${{ steps.studio-run.outputs.artifact_id }}",
        "path": "${{ runner.temp }}/studio-live-generated",
        "github-token": "${{ github.token }}",
        "repository": "${{ github.repository }}",
        "run-id": "${{ steps.studio-run.outputs.run_id }}",
        "merge-multiple": "true",
    }
    assert steps.index(resolver) < steps.index(downloader)
    assert "env" not in resolver or "DUNE_API_KEY" not in resolver["env"]
    assert "env" not in downloader or "DUNE_API_KEY" not in downloader["env"]


def test_studio_resolver_selects_newest_trusted_run_and_immutable_artifact():
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)
    resolver = step_with_action(
        workflow["jobs"]["build"]["steps"],
        "actions/github-script@v9",
    )
    runs = [trusted_studio_run(100), trusted_studio_run(101)]
    artifacts = [
        {
            "id": 501,
            "name": "studio-live-snapshot-101-1",
            "expired": False,
        }
    ]

    result = run_studio_resolver(
        resolver["with"]["script"],
        runs=runs,
        artifacts=artifacts,
    )

    assert result == {
        "result": "101",
        "outputs": {
            "run_id": "101",
            "artifact_id": "501",
            "artifact_name": "studio-live-snapshot-101-1",
        },
    }


def test_studio_resolver_rejects_an_older_triggered_run():
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)
    resolver = step_with_action(
        workflow["jobs"]["build"]["steps"],
        "actions/github-script@v9",
    )
    runs = [trusted_studio_run(100), trusted_studio_run(101)]

    result = run_studio_resolver(
        resolver["with"]["script"],
        runs=runs,
        artifacts=[],
        requested_run_id="100",
    )

    assert "older than newest eligible run 101" in result["error"]
    assert result["outputs"] == {}


def test_studio_resolver_rejects_untrusted_or_expired_handoffs():
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)
    resolver = step_with_action(
        workflow["jobs"]["build"]["steps"],
        "actions/github-script@v9",
    )
    untrusted = run_studio_resolver(
        resolver["with"]["script"],
        runs=[trusted_studio_run(101, event="pull_request")],
        artifacts=[],
    )
    wrong_workflow_ref = run_studio_resolver(
        resolver["with"]["script"],
        runs=[
            trusted_studio_run(
                101,
                path=".github/workflows/studio-live-refresh.yml@feature",
            )
        ],
        artifacts=[],
    )
    expired = run_studio_resolver(
        resolver["with"]["script"],
        runs=[trusted_studio_run(101)],
        artifacts=[
            {
                "id": 501,
                "name": "studio-live-snapshot-101-1",
                "expired": True,
            }
        ],
    )

    assert "No successful Studio snapshot workflow run" in untrusted["error"]
    assert "No successful Studio snapshot workflow run" in wrong_workflow_ref["error"]
    assert "Expected one active studio-live-snapshot-101-1" in expired["error"]


def test_shared_deployment_validates_downloaded_snapshot_without_refetching_studio():
    workflow_text = STUDIO_PRODUCTION_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)
    build_job = workflow["jobs"]["build"]
    deploy_job = workflow["jobs"]["deploy"]
    steps = build_job["steps"]

    download = step_with_action(steps, "actions/download-artifact@v4")
    inventory = step_with_run(steps, "scripts/generate_studio_inventory.py --check")
    studio_commands = [
        step
        for step in steps
        if "scripts/fetch_studio_data.py" in str(step.get("run") or "")
    ]
    assert len(studio_commands) == 1
    validation = studio_commands[0]
    validation_command = str(validation["run"])
    assert "--validate-only" in validation_command
    assert "--require-active-snapshot" in validation_command
    assert f"--output-dir {STUDIO_LIVE_OUTPUT}" in validation_command

    catalog_refresh = step_with_run(
        steps,
        "scripts/update_freshness_from_dune.py --query-id 7625551",
    )
    tests = step_with_run(steps, "python -m pytest")
    build = step_with_run(steps, "scripts/build_website.py")
    upload = step_with_action(steps, "actions/upload-pages-artifact@v3")
    ordered = [
        download,
        inventory,
        validation,
        catalog_refresh,
        tests,
        build,
        upload,
    ]
    assert [steps.index(step) for step in ordered] == sorted(
        steps.index(step) for step in ordered
    )

    assert f"--studio-generated-data {STUDIO_LIVE_OUTPUT}" in str(build["run"])
    assert upload["with"]["path"] == "output/website"
    assert "website/data/studio/generated" not in workflow_text
    assert "--force" not in workflow_text
    assert "--allow-partial" not in workflow_text
    assert "--mixed-source-mode" not in workflow_text
    assert "STUDIO_ENABLE_LIVE_DUNE" not in workflow_text
    for forbidden in (
        "run_query",
        "run_query_dataframe",
        "execute_query",
        "refresh_query",
        "max_age_hours",
        "/execute",
    ):
        assert forbidden not in workflow_text

    assert upload.get("if") != "${{ always() }}"
    assert deploy_job["needs"] == "build"
    deploy_steps = deploy_job["steps"]
    configure = step_with_action(deploy_steps, "actions/configure-pages@v5")
    deploy = step_with_action(deploy_steps, "actions/deploy-pages@v4")
    assert deploy_steps.index(configure) < deploy_steps.index(deploy)
    assert deploy.get("if") != "${{ always() }}"


def test_only_the_shared_consumer_can_deploy_pages_and_serializes_deployments():
    deployers = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        workflow = load_workflow(path)
        for job in (workflow.get("jobs") or {}).values():
            if any(
                step.get("uses") == "actions/deploy-pages@v4"
                for step in job.get("steps", [])
            ):
                deployers.append((path, job))

    assert [path for path, _ in deployers] == [STUDIO_PRODUCTION_WORKFLOW_PATH]
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)
    assert workflow["concurrency"] == {
        "group": "studio-production-pages",
        "cancel-in-progress": "true",
    }
    assert load_workflow(STUDIO_LIVE_WORKFLOW_PATH)["concurrency"]["group"] != (
        "studio-production-pages"
    )


def test_studio_fixture_workflow_is_manual_offline_and_isolated_from_production():
    workflow_text = STUDIO_FIXTURE_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = load_workflow(STUDIO_FIXTURE_WORKFLOW_PATH)

    assert workflow["name"] == "Validate Studio fixture refresh"
    assert workflow["on"] == {"workflow_dispatch": ""}
    assert "schedule" not in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "studio-fixture-refresh-${{ github.ref }}",
        "cancel-in-progress": "false",
    }

    job = workflow["jobs"]["fixture-refresh"]
    assert "if" not in job
    assert job["timeout-minutes"] == "20"
    assert "env" not in job
    for forbidden in (
        "DUNE_API_KEY",
        "STUDIO_ENABLE_LIVE_DUNE",
        "actions/configure-pages",
        "actions/deploy-pages",
        "upload-pages-artifact",
        "actions/download-artifact",
        SHARED_WORKFLOW_REFERENCE,
        STUDIO_ARTIFACT_PREFIX,
    ):
        assert forbidden not in workflow_text


def test_studio_fixture_workflow_validates_builds_and_uploads_short_lived_artifacts():
    workflow = load_workflow(STUDIO_FIXTURE_WORKFLOW_PATH)
    steps = workflow["jobs"]["fixture-refresh"]["steps"]
    step_names = [step["name"] for step in steps]
    setup = steps[step_names.index("Set up Python")]
    install = steps[step_names.index("Install project")]
    assert setup["with"] == {
        "python-version": "3.12",
        "cache": "pip",
        "cache-dependency-path": "pyproject.toml",
    }
    assert "python -m pip install -e '.[dev]'" in install["run"]
    expected_order = [
        "Check Studio query inventory",
        "Build deterministic fixture snapshot",
        "Validate active fixture snapshot",
        "Run complete tests",
        "Build website",
        "Upload fixture diagnostics",
    ]
    assert [step_names.index(name) for name in expected_order] == sorted(
        step_names.index(name) for name in expected_order
    )

    refresh = steps[step_names.index("Build deterministic fixture snapshot")]["run"]
    assert "scripts/fetch_studio_data.py" in refresh
    assert "--fixture-mode" in refresh
    assert "--fixture-scenario success" in refresh
    assert "--fixture-now 2026-07-31T12:00:00Z" in refresh
    assert '--output-dir "$RUNNER_TEMP/studio-fixture-generated"' in refresh
    assert "--keep-previous 1" in refresh

    validation = steps[step_names.index("Validate active fixture snapshot")]["run"]
    assert "--validate-only" in validation
    assert '--output-dir "$RUNNER_TEMP/studio-fixture-generated"' in validation
    assert steps[step_names.index("Run complete tests")]["run"] == (
        "python -m pytest -q"
    )
    assert steps[step_names.index("Build website")]["run"] == (
        "python scripts/build_website.py "
        '--studio-generated-data "$RUNNER_TEMP/studio-fixture-generated"'
    )
    artifact = steps[step_names.index("Upload fixture diagnostics")]
    assert artifact["if"] == "${{ always() }}"
    assert artifact["uses"] == "actions/upload-artifact@v4"
    assert artifact["with"]["retention-days"] == "7"
    assert "${{ runner.temp }}/studio-fixture-generated/state.json" in artifact[
        "with"
    ]["path"]
    assert "${{ runner.temp }}/studio-fixture-generated/attempts/" in artifact[
        "with"
    ]["path"]
