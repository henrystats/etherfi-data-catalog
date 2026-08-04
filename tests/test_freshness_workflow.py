from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "refresh-freshness.yml"


def test_refresh_freshness_workflow_is_scheduled_read_only_and_non_deploying():
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)

    assert workflow["on"]["workflow_dispatch"] == ""
    assert workflow["on"]["schedule"] == [{"cron": "7 * * * *"}]
    assert workflow["permissions"] == {"contents": "read"}
    assert "pages" not in workflow["permissions"]
    assert "id-token" not in workflow["permissions"]
    assert "actions/configure-pages" not in workflow_text
    assert "actions/upload-pages-artifact" not in workflow_text
    assert "actions/deploy-pages" not in workflow_text
    assert "scripts/build_website.py" not in workflow_text
    if "concurrency" in workflow:
        assert workflow["concurrency"]["group"] != "studio-production-pages"


def test_refresh_freshness_workflow_scopes_secret_and_uploads_short_lived_diagnostics():
    workflow = yaml.load(
        WORKFLOW_PATH.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert len(workflow["jobs"]) == 1
    job = next(iter(workflow["jobs"].values()))
    assert "environment" not in job
    assert "env" not in job
    steps = job["steps"]

    fetch_steps = [
        step
        for step in steps
        if "scripts/update_freshness_from_dune.py" in str(step.get("run") or "")
        and "--query-id 7625551" in str(step.get("run") or "")
    ]
    assert len(fetch_steps) == 1
    fetch = fetch_steps[0]
    assert fetch["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    secret_steps = [
        step for step in steps if "DUNE_API_KEY" in (step.get("env") or {})
    ]
    assert secret_steps == [fetch]

    artifact_steps = [
        step for step in steps if step.get("uses") == "actions/upload-artifact@v4"
    ]
    assert len(artifact_steps) == 1
    artifact = artifact_steps[0]
    assert steps.index(fetch) < steps.index(artifact)
    assert '--output "$RUNNER_TEMP/dataset_freshness.yaml"' in fetch["run"]
    assert artifact["with"]["path"] == (
        "${{ runner.temp }}/dataset_freshness.yaml"
    )
    assert 1 <= int(artifact["with"]["retention-days"]) <= 7
    assert artifact["with"].get("if-no-files-found") in {None, "error"}
