from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_exposes_local_stdio_console_script():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "etherfi-catalog-mcp"
    assert (
        pyproject["project"]["scripts"]["etherfi-catalog-mcp"]
        == "etherfi_catalog.server:main"
    )


def test_pyproject_includes_catalog_metadata_package_data():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["etherfi_catalog"]

    assert "data/datasets/**/*.yaml" in package_data
    assert "data/dashboards/**/*.yaml" in package_data
    assert "data/status/*.yaml" in package_data


def test_pyproject_keeps_fastmcp_v1_and_smoke_client_dependencies_explicit():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "mcp>=1.28,<2" in pyproject["project"]["dependencies"]
    assert "httpx>=0.27.1,<1.0.0" in pyproject["project"]["optional-dependencies"]["dev"]
