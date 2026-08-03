from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy-website.yml"
STUDIO_FIXTURE_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "studio-fixture-refresh.yml"
)
STUDIO_REFRESH_TEMPLATE_PATH = (
    ROOT / "docs" / "examples" / "studio_dune_refresh.yml.example"
)


def test_deploy_website_workflow_builds_and_publishes_pages_artifact():
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)

    assert workflow["name"] == "Deploy website"
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["workflow_dispatch"] == ""
    assert workflow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }

    job = workflow["jobs"]["build-and-deploy"]
    step_names = [step["name"] for step in job["steps"]]

    assert "Install project" in step_names
    assert "Run website tests" in step_names
    assert "Build website" in step_names
    assert "Configure GitHub Pages" in step_names
    assert "Upload website artifact" in step_names
    assert "Deploy to GitHub Pages" in step_names

    assert "python -m pip install -e '.[dev]'" in workflow_text
    assert "python -m pytest tests/test_website_build.py" in workflow_text
    assert "tests/test_studio_build.py" in workflow_text
    assert "tests/test_studio_data_contract.py" in workflow_text
    assert "tests/test_studio_inventory.py" in workflow_text
    assert "tests/test_studio_js.py" in workflow_text
    assert "python scripts/generate_studio_inventory.py --check" in workflow_text
    assert "python scripts/build_website.py" in workflow_text
    assert "actions/configure-pages@v5" in workflow_text
    assert "actions/upload-pages-artifact@v3" in workflow_text
    assert "path: output/website" in workflow_text
    assert "actions/deploy-pages@v4" in workflow_text
    assert "DUNE_API_KEY" not in workflow_text


def test_deploy_website_runs_studio_tests_before_the_static_build():
    workflow = yaml.load(
        WORKFLOW_PATH.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["build-and-deploy"]["steps"]
    step_names = [step["name"] for step in steps]

    test_step = steps[step_names.index("Run website tests")]
    build_step = steps[step_names.index("Build website")]

    assert step_names.index("Run website tests") < step_names.index("Build website")
    assert "python scripts/generate_studio_inventory.py --check" in test_step["run"]
    assert "tests/test_studio_build.py" in test_step["run"]
    assert "tests/test_studio_data_contract.py" in test_step["run"]
    assert "tests/test_studio_inventory.py" in test_step["run"]
    assert "tests/test_studio_js.py" in test_step["run"]
    assert build_step["run"] == "python scripts/build_website.py"


def test_studio_refresh_example_is_a_disabled_manual_template():
    template_text = STUDIO_REFRESH_TEMPLATE_PATH.read_text(encoding="utf-8")
    template = yaml.load(template_text, Loader=yaml.BaseLoader)

    assert "TEMPLATE ONLY" in template_text
    assert STUDIO_REFRESH_TEMPLATE_PATH.parent != ROOT / ".github" / "workflows"
    assert STUDIO_REFRESH_TEMPLATE_PATH.suffix == ".example"
    assert set(template["on"]) == {"workflow_dispatch"}
    dispatch = template["on"]["workflow_dispatch"]
    assert dispatch["inputs"]["confirm_read_only_import"] == {
        "description": "Import reviewed stored Dune results (read only)",
        "required": "true",
        "type": "boolean",
        "default": "false",
    }

    jobs = template["jobs"]
    assert list(jobs) == ["import-build-deploy-template"]
    job = jobs["import-build-deploy-template"]
    assert job["if"] == "${{ false && inputs.confirm_read_only_import == true }}"


def test_studio_refresh_template_scopes_secret_and_preserves_failure_boundary():
    template = yaml.load(
        STUDIO_REFRESH_TEMPLATE_PATH.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    steps = template["jobs"]["import-build-deploy-template"]["steps"]
    step_names = [step["name"] for step in steps]

    expected_order = [
        "Check unique query inventory",
        "Fetch latest stored results, validate, and promote snapshot",
        "Validate promoted snapshot",
        "Run complete tests",
        "Build website",
        "Upload website artifact",
        "Deploy to GitHub Pages",
    ]
    assert [step_names.index(name) for name in expected_order] == sorted(
        step_names.index(name) for name in expected_order
    )

    secret_steps = [
        step for step in steps if "DUNE_API_KEY" in str(step.get("env") or {})
    ]
    assert len(secret_steps) == 1
    assert secret_steps[0]["name"] == (
        "Fetch latest stored results, validate, and promote snapshot"
    )
    assert secret_steps[0]["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
        "STUDIO_ENABLE_LIVE_DUNE": "1",
    }

    refresh_step = steps[
        step_names.index("Fetch latest stored results, validate, and promote snapshot")
    ]
    validate_step = steps[step_names.index("Validate promoted snapshot")]
    assert "scripts/fetch_studio_data.py" in refresh_step["run"]
    assert "--keep-previous 1" in refresh_step["run"]
    assert "--fixture-mode" not in refresh_step["run"]
    assert "--mixed-source-mode" not in refresh_step["run"]
    assert "scripts/fetch_studio_data.py" in validate_step["run"]
    assert "--validate-only" in validate_step["run"]
    assert "refresh_studio_from_dune.py" not in STUDIO_REFRESH_TEMPLATE_PATH.read_text(
        encoding="utf-8"
    )

    active_workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "DUNE_API_KEY" not in active_workflow_text


def test_studio_refresh_template_documents_read_only_latest_result_contract():
    template_text = STUDIO_REFRESH_TEMPLATE_PATH.read_text(encoding="utf-8")
    template = yaml.load(template_text, Loader=yaml.BaseLoader)
    steps = template["jobs"]["import-build-deploy-template"]["steps"]
    step_names = [step["name"] for step in steps]
    import_step = steps[
        step_names.index("Fetch latest stored results, validate, and promote snapshot")
    ]

    assert "READ-ONLY DUNE CONTRACT" in template_text
    assert "GET /api/v1/query/{query_id}/results" in template_text
    assert "get_latest_result" in template_text
    assert "read-only DUNE_API_KEY" in template_text
    assert "max_age_hours" in template_text
    assert "scripts/fetch_studio_data.py" in import_step["run"]
    assert "--fixture-mode" not in import_step["run"]
    assert "--max-age" not in import_step["run"]


def test_studio_fixture_workflow_is_manual_offline_and_runs_on_dispatch():
    workflow_text = STUDIO_FIXTURE_WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)

    assert workflow["name"] == "Validate Studio fixture refresh"
    assert workflow["on"] == {"workflow_dispatch": ""}
    assert "schedule" not in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"

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
    workflow = yaml.load(
        STUDIO_FIXTURE_WORKFLOW_PATH.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
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
        'python scripts/build_website.py '
        '--studio-generated-data "$RUNNER_TEMP/studio-fixture-generated"'
    )
    artifact = steps[step_names.index("Upload fixture diagnostics")]
    assert artifact["if"] == "${{ always() }}"
    assert artifact["uses"] == "actions/upload-artifact@v4"
    assert artifact["with"]["retention-days"] == "7"
    assert "${{ runner.temp }}/studio-fixture-generated/state.json" in artifact["with"][
        "path"
    ]
    assert "${{ runner.temp }}/studio-fixture-generated/attempts/" in artifact["with"][
        "path"
    ]
