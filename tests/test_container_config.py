from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_runs_streamable_http_without_baked_secret():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in dockerfile
    assert "COPY src ./src" in dockerfile
    assert "COPY datasets ./datasets" in dockerfile
    assert "COPY dashboards ./dashboards" in dockerfile
    assert "COPY status/dataset_freshness.example.yaml ./status/dataset_freshness.example.yaml" in dockerfile
    assert "DUNE_API_KEY" not in dockerfile
    assert "EXPOSE 8001" in dockerfile
    assert '"--transport", "streamable-http"' in dockerfile
    assert '"--host", "0.0.0.0"' in dockerfile
    assert '"--port", "8001"' in dockerfile


def test_dockerignore_excludes_local_secret_and_generated_artifacts():
    dockerignore_lines = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert ".git" in dockerignore_lines
    assert ".venv" in dockerignore_lines
    assert ".env" in dockerignore_lines
    assert ".env.*" in dockerignore_lines
    assert ".codex" in dockerignore_lines
    assert "output/" in dockerignore_lines
    assert "status/dataset_freshness.yaml" in dockerignore_lines


def test_dockerignore_keeps_runtime_metadata_sources_available():
    dockerignore_lines = {
        line.strip().rstrip("/")
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert "datasets" not in dockerignore_lines
    assert "dashboards" not in dockerignore_lines
    assert "status" not in dockerignore_lines
    assert "status/dataset_freshness.example.yaml" not in dockerignore_lines


def test_docker_smoke_workflow_is_manual_and_secret_free():
    workflow = (ROOT / ".github" / "workflows" / "docker-smoke.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "docker build -t etherfi-catalog-mcp:local ." in workflow
    assert "--name etherfi-catalog-mcp-smoke" in workflow
    assert "-p 8001:8001" in workflow
    assert "python scripts/smoke_mcp_http.py --url http://127.0.0.1:8001/mcp --timeout 20" in workflow
    assert "docker push" not in workflow
    assert "docker login" not in workflow
    assert "secrets." not in workflow
    assert "DUNE_API_KEY" not in workflow
