from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_WRAPPER_PATH = ROOT / ".github" / "workflows" / "deploy-website.yml"
STUDIO_LIVE_WRAPPER_PATH = (
    ROOT / ".github" / "workflows" / "studio-live-refresh.yml"
)
STUDIO_PRODUCTION_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "studio-production-deploy.yml"
)
STUDIO_FIXTURE_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "studio-fixture-refresh.yml"
)
SHARED_WORKFLOW_REFERENCE = "./.github/workflows/studio-production-deploy.yml"
STUDIO_LIVE_OUTPUT = '"$RUNNER_TEMP/studio-live-generated"'


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


def assert_shared_production_caller(path: Path, *, expected_trigger: dict) -> None:
    workflow = load_workflow(path)

    assert workflow["on"] == expected_trigger
    assert workflow["permissions"] == {}
    job = only_job(workflow)
    assert job["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert job["uses"] == SHARED_WORKFLOW_REFERENCE
    assert job["secrets"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    assert "steps" not in job


def test_push_deploy_uses_only_the_shared_live_studio_production_path():
    assert_shared_production_caller(
        DEPLOY_WRAPPER_PATH,
        expected_trigger={"push": {"branches": ["main"]}},
    )


def test_manual_and_scheduled_live_refresh_use_the_shared_production_path():
    assert_shared_production_caller(
        STUDIO_LIVE_WRAPPER_PATH,
        expected_trigger={
            "workflow_dispatch": "",
            "schedule": [{"cron": "25 */4 * * *"}],
        },
    )

    cron = load_workflow(STUDIO_LIVE_WRAPPER_PATH)["on"]["schedule"][0]["cron"]
    assert cron.split()[0] == "25"


def test_shared_production_workflow_requires_only_the_dune_secret():
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)

    assert set(workflow["on"]) == {"workflow_call"}
    declared_secrets = workflow["on"]["workflow_call"]["secrets"]
    assert set(declared_secrets) == {"DUNE_API_KEY"}
    assert declared_secrets["DUNE_API_KEY"]["required"] == "true"
    assert workflow["permissions"] == {}
    assert "env" not in workflow

    assert set(workflow["jobs"]) == {"build", "deploy"}
    build_job = workflow["jobs"]["build"]
    deploy_job = workflow["jobs"]["deploy"]
    assert build_job["permissions"] == {"contents": "read"}
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
    assert len(secret_steps) == 3
    preflight = step_with_run(secret_steps, 'if [ -z "${DUNE_API_KEY:-}" ]')
    studio_refresh = step_with_run(secret_steps, "scripts/fetch_studio_data.py")
    catalog_refresh = step_with_run(
        secret_steps,
        "scripts/update_freshness_from_dune.py",
    )
    assert preflight["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    assert studio_refresh["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
        "STUDIO_ENABLE_LIVE_DUNE": "1",
    }
    assert catalog_refresh["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    assert build_job["steps"].index(preflight) < build_job["steps"].index(
        studio_refresh
    )


def test_shared_production_workflow_fetches_validates_builds_and_deploys_one_snapshot():
    workflow = load_workflow(STUDIO_PRODUCTION_WORKFLOW_PATH)
    build_job = workflow["jobs"]["build"]
    deploy_job = workflow["jobs"]["deploy"]
    steps = build_job["steps"]

    inventory = step_with_run(steps, "scripts/generate_studio_inventory.py --check")
    seed = step_with_run(steps, "website/data/studio/generated")
    validation_candidates = [
        step
        for step in steps
        if "scripts/fetch_studio_data.py" in str(step.get("run") or "")
        and "--validate-only" in str(step.get("run") or "")
    ]
    assert len(validation_candidates) == 1
    validation = validation_candidates[0]
    refresh_candidates = [
        step
        for step in steps
        if "scripts/fetch_studio_data.py" in str(step.get("run") or "")
        and "--validate-only" not in str(step.get("run") or "")
    ]
    assert len(refresh_candidates) == 1
    refresh = refresh_candidates[0]
    catalog_refresh = step_with_run(
        steps,
        "scripts/update_freshness_from_dune.py --query-id 7625551",
    )
    tests = step_with_run(steps, "python -m pytest")
    build = step_with_run(steps, "scripts/build_website.py")
    upload = step_with_action(steps, "actions/upload-pages-artifact@v3")

    assert [
        steps.index(step)
        for step in (
            inventory,
            seed,
            refresh,
            validation,
            catalog_refresh,
            tests,
            build,
            upload,
        )
    ] == sorted(
        steps.index(step)
        for step in (
            inventory,
            seed,
            refresh,
            validation,
            catalog_refresh,
            tests,
            build,
            upload,
        )
    )

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
        "execute_query",
        "refresh_query",
        "max_age_hours",
        "/execute",
    ):
        assert forbidden not in refresh_command

    validation_command = str(validation["run"])
    assert "--validate-only" in validation_command
    assert f"--output-dir {STUDIO_LIVE_OUTPUT}" in validation_command
    assert (
        f"--studio-generated-data {STUDIO_LIVE_OUTPUT}" in str(build["run"])
    )
    assert upload["with"]["path"] == "output/website"

    assert deploy_job["needs"] == "build"
    deploy_steps = deploy_job["steps"]
    configure = step_with_action(deploy_steps, "actions/configure-pages@v5")
    deploy = step_with_action(deploy_steps, "actions/deploy-pages@v4")
    assert deploy_steps.index(configure) < deploy_steps.index(deploy)
    assert deploy.get("if") != "${{ always() }}"


def test_only_the_shared_production_workflow_can_deploy_pages():
    deployers = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
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


def test_studio_fixture_workflow_is_manual_offline_and_runs_on_dispatch():
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
    assert "DUNE_API_KEY" not in workflow_text
    assert "STUDIO_ENABLE_LIVE_DUNE" not in workflow_text
    assert "actions/configure-pages" not in workflow_text
    assert "actions/deploy-pages" not in workflow_text
    assert "upload-pages-artifact" not in workflow_text


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
