from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "refresh-freshness.yml"
SHARED_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "studio-production-deploy.yml"
)
SHARED_WORKFLOW_REFERENCE = "./.github/workflows/studio-production-deploy.yml"


def load_workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_refresh_freshness_is_hourly_manual_and_runs_after_a_studio_snapshot():
    workflow = load_workflow(WORKFLOW_PATH)

    assert workflow["name"] == "Refresh catalog freshness and deploy website"
    assert workflow["on"] == {
        "workflow_dispatch": "",
        "schedule": [{"cron": "7 * * * *"}],
        "workflow_run": {
            "workflows": ["Refresh live Studio data snapshot"],
            "types": ["completed"],
            "branches": ["main"],
        },
    }
    cron_fields = workflow["on"]["schedule"][0]["cron"].split()
    assert cron_fields == ["7", "*", "*", "*", "*"]
    assert workflow["permissions"] == {}

    assert len(workflow["jobs"]) == 1
    job = workflow["jobs"]["production-deploy"]
    assert job["permissions"] == {
        "actions": "read",
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert job["uses"] == SHARED_WORKFLOW_REFERENCE
    assert job["with"] == {
        "studio_run_id": "${{ format('{0}', github.event.workflow_run.id || '') }}",
    }
    assert job["secrets"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }
    assert "steps" not in job

    condition = str(job["if"])
    assert "github.ref == 'refs/heads/main'" in condition
    assert "github.event_name != 'workflow_run'" in condition
    assert "github.event.workflow_run.conclusion == 'success'" in condition


def test_freshness_deploy_uses_one_latest_result_read_and_never_refetches_studio():
    wrapper_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    shared_text = SHARED_WORKFLOW_PATH.read_text(encoding="utf-8")
    shared = load_workflow(SHARED_WORKFLOW_PATH)
    steps = shared["jobs"]["build"]["steps"]

    assert "scripts/update_freshness_from_dune.py" not in wrapper_text
    assert "scripts/fetch_studio_data.py" not in wrapper_text
    freshness_steps = [
        step
        for step in steps
        if "scripts/update_freshness_from_dune.py" in str(step.get("run") or "")
    ]
    assert len(freshness_steps) == 1
    freshness = freshness_steps[0]
    assert "--query-id 7625551" in freshness["run"]
    assert freshness["env"] == {
        "DUNE_API_KEY": "${{ secrets.DUNE_API_KEY }}",
    }

    studio_steps = [
        step
        for step in steps
        if "scripts/fetch_studio_data.py" in str(step.get("run") or "")
    ]
    assert len(studio_steps) == 1
    assert "--validate-only" in studio_steps[0]["run"]
    assert "STUDIO_ENABLE_LIVE_DUNE" not in shared_text
    for forbidden in (
        "run_query",
        "run_query_dataframe",
        "execute_query",
        "refresh_query",
        "max_age_hours",
        "/execute",
    ):
        assert forbidden not in shared_text

    build = next(
        step
        for step in steps
        if "scripts/build_website.py" in str(step.get("run") or "")
    )
    upload = next(
        step for step in steps if step.get("uses") == "actions/upload-pages-artifact@v3"
    )
    assert steps.index(freshness) < steps.index(build) < steps.index(upload)
    assert upload.get("if") != "${{ always() }}"
