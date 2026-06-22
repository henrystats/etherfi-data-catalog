from pathlib import Path

import yaml

from etherfi_catalog.catalog import plan_etherfi_query


FIXTURE_PATH = Path("tests/fixtures/orchestration_prompt_regressions.yaml")
README_PATH = Path("README.md")
ETHERFI_SKILL_PATH = Path("skills/etherfi/SKILL.md")
DASHBOARD_FLOW_PATH = Path("skills/etherfi/flows/dashboard_build.md")
QUERY_FLOW_PATH = Path("skills/etherfi/flows/query_authoring.md")


def _load_cases() -> list[dict]:
    return yaml.safe_load(FIXTURE_PATH.read_text())["cases"]


def _case(case_id: str) -> dict:
    for case in _load_cases():
        if case["id"] == case_id:
            return case
    raise AssertionError(f"Missing orchestration regression case: {case_id}")


def _read_orchestration_docs() -> str:
    return "\n".join(
        path.read_text()
        for path in [
            README_PATH,
            ETHERFI_SKILL_PATH,
            DASHBOARD_FLOW_PATH,
            QUERY_FLOW_PATH,
        ]
    )


def test_orchestration_regression_fixture_covers_expected_flows():
    case_ids = {case["id"] for case in _load_cases()}

    assert case_ids == {
        "shareable_query_flow",
        "create_shareable_query_flow",
        "visualization_flow",
        "dashboard_flow",
        "optimization_flow",
        "holder_ambiguity_flow",
    }


def test_shareable_query_flow_routes_through_catalog_plan_then_dune_mcp():
    case = _case("shareable_query_flow")
    plan = plan_etherfi_query(case["prompt"])

    assert case["route"] == ["etherfi-catalog", "Dune MCP"]
    assert plan["recommended_datasets"][0]["name"] == case["expected"]["dataset"]
    assert {"field": "event_type", "operator": "=", "value": case["expected"]["filters"]["event_type"]} in plan["preferred_filters"]
    assert {"field": "token_symbol", "operator": "=", "value": case["expected"]["filters"]["token_symbol"]} in plan["preferred_filters"]
    assert plan["suggested_grain"] == case["expected"]["grain"]
    assert case["expected"]["metric"] in plan["suggested_metrics"]
    assert "Use Dune MCP" in plan["suggested_next_step"]
    assert "create, run, and save" in plan["suggested_next_step"]
    assert "local chart" not in plan["suggested_next_step"].lower()


def test_create_shareable_query_flow_preserves_team_owned_dune_context_note():
    case = _case("create_shareable_query_flow")
    plan = plan_etherfi_query(case["prompt"])

    assert case["route"] == ["etherfi-catalog", "Dune MCP", "Dune Skills"]
    assert plan["recommended_datasets"][0]["name"] == case["expected"]["dataset"]
    assert "Use Dune MCP" in plan["suggested_next_step"]
    assert "team-owned Dune context" in plan["suggested_next_step"]
    assert "DuneSQL" in QUERY_FLOW_PATH.read_text()


def test_visualization_flow_assigns_shareable_chart_artifacts_to_dune_mcp():
    case = _case("visualization_flow")
    docs = _read_orchestration_docs()

    assert case["route"] == ["Dune MCP"]
    assert case["expected"]["dune_mcp_owner"] == "visualization"
    assert "use Dune MCP visualization/dashboard tools" in docs
    assert "Avoid local chart files when the user wants a shareable Dune artifact." in Path(
        "skills/etherfi/examples/chart_for_query.md"
    ).read_text()
    assert "Avoid ad hoc local chart building when the user asked for a shareable Dune chart or dashboard." in docs


def test_dashboard_flow_assigns_dashboard_artifacts_to_dune_mcp():
    case = _case("dashboard_flow")
    docs = _read_orchestration_docs()

    assert case["route"] == ["Dune MCP"]
    assert case["expected"]["dune_mcp_owner"] == "dashboard"
    assert "Use Dune MCP to run, save, retrieve, visualize, and dashboard the Dune query." in docs
    assert "Dune MCP has created or updated the requested chart/dashboard artifact." in docs


def test_optimization_flow_routes_to_dune_skills_not_catalog_optimizer():
    case = _case("optimization_flow")
    docs = _read_orchestration_docs()

    assert case["route"] == ["Dune Skills"]
    assert case["expected"]["optimization_owner"] == "Dune Skills"
    assert case["expected"]["catalog_is_optimizer"] is False
    assert "Dune Skills: Dune CLI, query-writing, optimization, and Dune-side workflow guidance for agents." in docs
    assert "Dune Skills for DuneSQL style, optimization, and Dune CLI guidance" in docs


def test_holder_ambiguity_flow_surfaces_direct_vs_defi_before_dune_mcp():
    case = _case("holder_ambiguity_flow")
    plan = plan_etherfi_query(case["prompt"])

    dataset_names = {dataset["name"] for dataset in plan["recommended_datasets"]}
    assert set(case["expected"]["datasets"]).issubset(dataset_names)
    assert any("direct holders" in note for note in plan["ambiguity_notes"])
    assert "Should indirect DeFi exposure be included?" in plan["clarifying_questions"]
    assert "Should rows attributed to known tracked DeFi contracts be included?" in plan["clarifying_questions"]
    assert any("identified_defi_contract" in caveat for caveat in plan["important_caveats"])
    assert any("tracked DeFi contract name" in caveat for caveat in plan["important_caveats"])
    assert "identified_defi_contract = true" not in " ".join(
        str(value)
        for value in [
            plan["clarifying_questions"],
            plan["important_caveats"],
            plan["suggested_query_description"],
        ]
    )
    assert "Resolve the holder semantics first" in plan["suggested_next_step"]
    assert "Dune MCP" in plan["suggested_next_step"]
