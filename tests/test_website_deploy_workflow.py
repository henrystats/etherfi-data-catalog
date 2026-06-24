from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "deploy-website.yml"


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
    assert "python scripts/build_website.py" in workflow_text
    assert "actions/configure-pages@v5" in workflow_text
    assert "actions/upload-pages-artifact@v3" in workflow_text
    assert "path: output/website" in workflow_text
    assert "actions/deploy-pages@v4" in workflow_text
    assert "DUNE_API_KEY" not in workflow_text
