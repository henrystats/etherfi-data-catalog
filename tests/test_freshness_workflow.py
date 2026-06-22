from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "refresh-freshness.yml"


def test_refresh_freshness_workflow_fetches_dune_snapshot_and_deploys_site():
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)

    assert workflow["name"] == "Refresh freshness website"
    assert workflow["on"]["workflow_dispatch"] == ""
    assert workflow["on"]["schedule"][0]["cron"] == "7 * * * *"
    assert workflow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }

    job = workflow["jobs"]["refresh-and-deploy"]

    step_names = [step["name"] for step in job["steps"]]
    assert "Fetch latest Dune freshness snapshot" in step_names
    assert "Build website" in step_names
    assert "Upload website artifact" in step_names
    assert "Deploy to GitHub Pages" in step_names

    assert "DUNE_API_KEY: ${{ secrets.DUNE_API_KEY }}" in workflow_text
    assert "scripts/update_freshness_from_dune.py --query-id 7625551" in workflow_text
    assert "python scripts/build_website.py" in workflow_text
    assert "actions/upload-pages-artifact@v3" in workflow_text
    assert "path: output/website" in workflow_text
    assert "actions/deploy-pages@v4" in workflow_text
