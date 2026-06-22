from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess

from scripts.build_website import (
    DEFAULT_OUTPUT_DIR,
    NOT_DOCUMENTED,
    build_site,
    dataset_freshness_interval_summary,
    extract_mcp_tools,
    format_relative_age,
    freshness_meter_for_row,
    load_dashboard_entries,
    load_dataset_entries,
    load_pages,
)


def test_website_pages_include_expected_navigation_entries():
    pages = load_pages()
    nav_labels = [page.nav_label for page in pages]

    assert nav_labels == [
        "Home",
        "MCP",
        "Datasets",
        "Dashboards",
        "Freshness",
    ]


def test_build_website_outputs_core_pages(tmp_path):
    (tmp_path / "agent-workflow.html").write_text("stale page", encoding="utf-8")

    written_paths = build_site(output_dir=tmp_path)
    written_names = {path.name for path in written_paths}

    assert {
        "index.html",
        "mcp.html",
        "datasets.html",
        "dashboards.html",
        "freshness.html",
    }.issubset(written_names)
    assert "agent-workflow.html" not in written_names
    assert not (tmp_path / "agent-workflow.html").exists()
    assert (tmp_path / "assets" / "styles.css").exists()

    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'data-home-page' in index_html
    assert '<span class="brand-mark">ether.fi</span>' in index_html
    assert '<span class="brand-mark">e.fi</span>' not in index_html
    assert "ether.fi Data Catalog" in index_html
    assert "A repo-backed catalog for ether.fi datasets, dashboards, freshness status, and MCP-powered AI workflows." in index_html
    assert 'href="datasets.html">Explore datasets</a>' in index_html
    assert 'href="dashboards.html">View dashboards</a>' in index_html
    assert 'href="freshness.html">Check freshness</a>' in index_html
    assert 'href="mcp.html">Learn about MCP</a>' in index_html
    assert 'href="mcp.html">MCP</a>' in index_html
    assert 'href="agent-workflow.html"' not in index_html
    assert "Agent Workflow" not in index_html
    hero_html = re.search(
        r'<section class="home-hub-hero detail-panel">(.*?)</section>',
        index_html,
        re.S,
    )
    assert hero_html
    assert "ether.fi Data Catalog" in hero_html.group(1)
    assert "A repo-backed catalog" in hero_html.group(1)
    assert "button" not in hero_html.group(1)
    assert "catalog-summary-card" not in hero_html.group(1)
    assert "Total datasets" not in index_html
    assert "Total dashboards" not in index_html
    assert "Fresh datasets" not in index_html
    assert "MCP tools" not in index_html
    assert "Explore the data catalog" in index_html
    assert "Jump straight into the page that matches the question in front of you." not in index_html
    assert "Browse ether.fi materialized views" in index_html
    assert "Find Dune dashboards by product area" in index_html
    assert "How this fits together" in index_html
    assert "A short path through the catalog without duplicating the full MCP guide." not in index_html
    assert "Discover the right dataset or dashboard" in index_html
    assert "Start with <strong>Datasets</strong>" in index_html
    assert "Start with <strong>MCP</strong>" in index_html
    assert "Monday demo path" not in index_html
    assert "Built for three audiences" not in index_html
    assert "Questions this makes safer" not in index_html

    dataset_entries = load_dataset_entries()
    dataset_pages = list((tmp_path / "datasets").glob("*.html"))
    assert len(dataset_pages) == len(dataset_entries)
    assert (tmp_path / "dashboards" / "etherfi_overview.html").exists()
    assert (tmp_path / "dashboards" / "etherfi_cash.html").exists()

    freshness_html = (tmp_path / "freshness.html").read_text(encoding="utf-8")
    assert '<span class="brand-mark">ether.fi</span>' in freshness_html
    assert '<span class="brand-mark">e.fi</span>' not in freshness_html


def test_build_website_generates_polished_mcp_page_from_current_tools(tmp_path):
    build_site(output_dir=tmp_path)

    mcp_page = (tmp_path / "mcp.html").read_text(encoding="utf-8")
    assert 'data-mcp-page' in mcp_page
    assert "<h1>ether.fi Catalog MCP</h1>" in mcp_page
    assert "Install a local stdio MCP" in mcp_page
    assert 'href="datasets.html">Explore datasets</a>' in mcp_page
    assert 'href="dashboards.html">View dashboards</a>' in mcp_page
    assert 'href="freshness.html">Check freshness</a>' in mcp_page

    assert "What this MCP does" in mcp_page
    assert "Dataset discovery" in mcp_page
    assert "Dashboard discovery" in mcp_page
    assert "Freshness checks" in mcp_page
    assert "Query planning" in mcp_page
    assert "Live answers" in mcp_page

    assert "How it fits together" in mcp_page
    assert "etherfi-catalog is the semantic layer" in mcp_page
    assert "Dune / Dune MCP" in mcp_page
    assert "Tool groups" in mcp_page
    assert "Catalog discovery" in mcp_page
    assert "Freshness and status" in mcp_page
    assert "Cash live tools" in mcp_page
    assert "Protocol live tools" in mcp_page
    assert "Price coverage tools" in mcp_page

    registered_tools = set(extract_mcp_tools())
    rendered_tools = set(re.findall(r'data-mcp-tool="([^"]+)"', mcp_page))
    assert rendered_tools == registered_tools
    assert "create_dashboard" not in rendered_tools
    assert "run_arbitrary_sql" not in rendered_tools

    cash_events_card = re.search(
        r'<article class="mcp-tool-card" data-mcp-tool="get_cash_events">(.*?)</article>',
        mcp_page,
        re.S,
    )
    assert cash_events_card
    assert "Live-capable" in cash_events_card.group(1)
    assert "DUNE_API_KEY" in cash_events_card.group(1)

    plan_card = re.search(
        r'<article class="mcp-tool-card" data-mcp-tool="plan_etherfi_query">(.*?)</article>',
        mcp_page,
        re.S,
    )
    assert plan_card
    assert "Planning" in plan_card.group(1)
    assert "DUNE_API_KEY" not in plan_card.group(1)

    search_card = re.search(
        r'<article class="mcp-tool-card" data-mcp-tool="search_datasets">(.*?)</article>',
        mcp_page,
        re.S,
    )
    assert search_card
    assert "Metadata" in search_card.group(1)
    assert "DUNE_API_KEY" not in search_card.group(1)

    assert "Example prompts" in mcp_page
    assert "Which ether.fi dataset should I use to analyze protocol token TVL?" in mcp_page
    assert "Plan a Dune query for weekly USDC spend volume on ether.fi Cash." in mcp_page
    assert "Planning mode" in mcp_page
    assert "Live mode" in mcp_page
    assert "Setup" in mcp_page
    assert "Recommended setup is local stdio via <code>uvx</code>" in mcp_page
    assert "uvx --from git+https://github.com/henrystats/etherfi-data-catalog.git etherfi-catalog-mcp" in mcp_page
    assert "Cloud Run and Docker are optional/private staging paths" in mcp_page
    assert "Claude Desktop" in mcp_page
    assert "Codex" in mcp_page
    assert "Dune MCP" in mcp_page
    assert ".venv/bin/python -m etherfi_catalog.server" not in mcp_page
    assert "DUNE_API_KEY" in mcp_page
    assert "Best practices" in mcp_page

    assert (tmp_path / "datasets.html").exists()
    assert (tmp_path / "dashboards.html").exists()
    assert (tmp_path / "freshness.html").exists()


def test_build_website_generates_dataset_index_and_detail_pages(tmp_path):
    build_site(output_dir=tmp_path)

    dataset_index = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    assert 'class="dataset-category-panel"' in dataset_index
    assert 'data-datasets-page' in dataset_index
    assert 'data-dataset-nav="overview"' in dataset_index
    assert 'data-dataset-nav="activity"' in dataset_index
    assert 'data-dataset-nav="etherfi_protocol"' in dataset_index
    assert 'data-dataset-nav="prices"' in dataset_index
    assert 'data-dataset-nav="metadata"' in dataset_index
    assert 'data-dataset-nav="lrt_restaking"' in dataset_index
    assert dataset_index.find("<span>Overview</span>") < dataset_index.find("<span>Activity</span>")
    assert dataset_index.find("<span>Activity</span>") < dataset_index.find("<span>Ether.fi Protocol</span>")
    assert dataset_index.find("<span>Ether.fi Protocol</span>") < dataset_index.find("<span>Prices</span>")
    assert dataset_index.find("<span>Prices</span>") < dataset_index.find("<span>Metadata</span>")
    assert dataset_index.find("<span>Metadata</span>") < dataset_index.find("<span>LRT / Restaking</span>")
    assert "<h1>Dataset catalog</h1>" in dataset_index
    assert "This page documents ether.fi materialized views and supporting datasets." in dataset_index
    assert "dataset-summary-grid" not in dataset_index
    assert "Total datasets" not in dataset_index
    assert "Categories" not in dataset_index
    assert "Query ready" not in dataset_index
    assert "Source queries documented" not in dataset_index
    assert "Featured datasets" in dataset_index
    assert "Ether.fi Assets Under Management" in dataset_index
    assert "Ether.fi Protocol Token TVL" in dataset_index
    assert "Ether.fi Cash Events" in dataset_index
    assert "Browse categories on the left to explore the full catalog." in dataset_index
    assert 'id="dataset-search"' in dataset_index
    assert 'id="dataset-count"' in dataset_index
    assert 'id="dataset-empty-state"' in dataset_index
    assert 'data-dataset-category-section data-category="activity"' in dataset_index
    assert 'data-dataset-card' in dataset_index
    assert 'data-search=' in dataset_index
    assert 'data-status=' in dataset_index
    assert 'href="datasets/protocol_token_holders.html"' in dataset_index
    assert "Protocol Token Holders" in dataset_index
    assert 'href="https://dune.com/queries/6213381"' in dataset_index
    assert 'data-source-query-id="6213381"' in dataset_index
    assert 'src="assets/datasets.js?v=' in dataset_index
    assert 'src="assets/dataset-detail.js?v=' not in dataset_index
    holder_card = re.search(
        r'<article class="dataset-browser-card"[^>]*data-source-query-id="6213381"[^>]*>(.*?)</article>',
        dataset_index,
        re.S,
    )
    assert holder_card
    holder_card_html = holder_card.group(1)
    assert "Protocol Token Holders" in holder_card_html
    assert "Direct holders of ether.fi protocol tokens by address" in holder_card_html
    assert '<span>Refresh</span>' in holder_card_html
    assert '<strong>4h</strong>' in holder_card_html
    assert '<span>Last refreshed</span>' in holder_card_html
    assert '<span>Status</span>' in holder_card_html
    assert 'href="https://dune.com/queries/6213381"' in holder_card_html
    assert 'href="datasets/protocol_token_holders.html"' in holder_card_html
    assert "Details" in holder_card_html
    assert "dataset-card-kicker" not in dataset_index
    assert "dataset-table-inline" not in dataset_index
    assert 'class="meta-chip subtle"' not in dataset_index
    assert "<span>Related</span>" not in dataset_index
    assert "<span>Category</span>" not in holder_card_html
    assert "dune.ether_fi.result_etherfi_protocol_token_holders" not in holder_card_html
    assert "related datasets</strong>" not in holder_card_html
    assert "dashboards</strong>" not in holder_card_html
    assert "dune.ether_fi.result_etherfi_protocol_token_holders" in dataset_index
    assert "etherfi_protocol_token_holders" in dataset_index

    holder_page = (tmp_path / "datasets" / "protocol_token_holders.html").read_text(encoding="utf-8")
    css = (tmp_path / "assets" / "styles.css").read_text(encoding="utf-8")
    assert "../assets/styles.css" in holder_page
    assert "Back to datasets" in holder_page
    assert "At a glance" in holder_page
    assert "Full table name" in holder_page
    assert 'class="dataset-glance-card full-table-name copyable-table-name"' in holder_page
    assert 'class="dataset-glance-card glance-grain"' in holder_page
    assert 'class="table-pill table-pill-block"' in holder_page
    assert "dune.ether_fi.result_etherfi_protocol_token_holders" in holder_page
    assert 'data-copy-text="dune.ether_fi.result_etherfi_protocol_token_holders"' in holder_page
    assert 'aria-label="Copy full table name"' in holder_page
    assert 'src="../assets/dataset-detail.js?v=' in holder_page
    assert "<span>Live query</span>" not in holder_page
    assert "Live query table" not in holder_page
    assert "Live query ID" not in holder_page
    assert ".dataset-glance-grid:not(:has(.live-query-card)) .dataset-glance-card.full-table-name" in css
    holder_glance = re.search(
        r"<h2>At a glance</h2><div class=\"dataset-glance-grid\">(.*?)</div></section>",
        holder_page,
        re.S,
    )
    assert holder_glance
    holder_glance_html = holder_glance.group(1)
    assert "<span>Category</span>" not in holder_glance_html
    assert "<span>Query ready</span>" not in holder_glance_html
    assert "<span>Freshness column</span>" not in holder_glance_html
    assert "<span>Source query ID</span>" not in holder_glance_html
    assert "<span>Refresh interval</span>" not in holder_glance_html
    assert "<span>Freshness</span>" not in holder_glance_html
    assert "<span>Grain</span>" in holder_glance_html
    assert '<div class="glance-label">Freshness &amp; Refresh Interval</div>' in holder_glance_html
    assert "<span>Freshness &amp; Interval</span>" not in holder_glance_html
    assert 'class="dataset-glance-card glance-compact freshness-refresh-item"' in holder_glance_html
    assert 'class="glance-value freshness-refresh-value"' in holder_glance_html
    assert 'class="freshness-status-pill status-' in holder_glance_html
    assert 'class="freshness-refresh-text"' in holder_glance_html
    assert 'class="freshness-interval-summary' not in holder_glance_html
    assert 'class="status-badge freshness-badge' not in holder_glance_html
    assert "Every 4h" in holder_glance_html
    assert any(status in holder_glance_html for status in ["Fresh", "Delayed", "Stale", "Unknown"])
    assert "daily" not in holder_page
    assert "About this table" in holder_page
    assert "Direct holders of ether.fi protocol tokens by address" in holder_page
    assert "one row per address per token per snapshot date" in holder_page
    assert "Schema" in holder_page
    assert "<th>Description</th>" in holder_page
    assert "<td><code>address</code></td><td>varbinary</td>" in holder_page
    assert '<td class="schema-description">holder wallet or contract address</td>' in holder_page
    assert "Related datasets and dashboards" in holder_page
    assert 'class="related-resource-list"' in holder_page
    assert 'class="related-resource"' in holder_page

    holder_with_defi_page = (
        tmp_path / "datasets" / "protocol_token_holders_with_defi.html"
    ).read_text(encoding="utf-8")
    assert "Protocol Token Holders With Defi" in holder_with_defi_page
    assert "Freshness &amp; Refresh Interval" in holder_with_defi_page
    assert "Freshness &amp; Interval" not in holder_with_defi_page
    assert "Every 4h" in holder_with_defi_page
    assert "daily" not in holder_with_defi_page
    assert 'href="../dashboards/etherfi_overview.html"' in holder_page
    assert "What this table contains" not in holder_page
    assert "Important columns" not in holder_page
    assert "Query notes" not in holder_page
    assert "Query notes / caveats" not in holder_page
    assert "Caveats" not in holder_page
    assert "This table does not include broader routed exposure" not in holder_page
    assert "Use when" not in holder_page
    assert "Do not use when" not in holder_page
    assert "Example prompts" not in holder_page
    assert "Who are the top direct holders of eETH?" not in holder_page

    transfers_page = (tmp_path / "datasets" / "addresses_transfers.html").read_text(
        encoding="utf-8"
    )
    transfers_glance = re.search(
        r"<h2>At a glance</h2><div class=\"dataset-glance-grid\">(.*?)</div></section>",
        transfers_page,
        re.S,
    )
    assert transfers_glance
    transfers_glance_html = transfers_glance.group(1)
    assert "<span>Category</span>" not in transfers_glance_html
    assert "<span>Query ready</span>" not in transfers_glance_html
    assert "<span>Freshness column</span>" not in transfers_glance_html
    assert "<span>Source query ID</span>" not in transfers_glance_html
    assert "<span>Refresh interval</span>" not in transfers_glance_html
    assert "<span>Freshness</span>" not in transfers_glance_html
    assert '<div class="glance-label">Freshness &amp; Refresh Interval</div>' in transfers_glance_html
    assert "<span>Freshness &amp; Interval</span>" not in transfers_glance_html
    assert 'class="dataset-glance-card glance-compact freshness-refresh-item"' in transfers_glance_html
    assert 'class="glance-value freshness-refresh-value"' in transfers_glance_html
    assert 'class="freshness-status-pill status-' in transfers_glance_html
    assert 'class="freshness-refresh-text"' in transfers_glance_html
    assert 'class="freshness-interval-summary' not in transfers_glance_html
    assert 'class="status-badge freshness-badge' not in transfers_glance_html
    assert "Every 1h" in transfers_glance_html
    assert transfers_page.count("<span>Live query</span>") == 1
    assert 'class="dataset-glance-card full-table-name copyable-table-name"' in transfers_page
    assert 'class="dataset-glance-card copyable-table-name live-query-card"' in transfers_page
    assert "Live query table" not in transfers_page
    assert "Live query ID" not in transfers_page
    assert "live-query-status" not in transfers_page
    assert ">Available<" not in transfers_page
    assert "query_7576959" in transfers_page
    assert 'data-copy-text="query_7576959"' in transfers_page
    assert 'aria-label="Copy live query table name"' in transfers_page
    assert "Live queries are saved-query outputs used for fresher recent data." in transfers_page
    assert "query_&lt;query_id&gt;" in transfers_page
    assert 'src="../assets/dataset-detail.js?v=' in transfers_page
    assert ".dataset-glance-grid:has(.live-query-card) .dataset-glance-card.full-table-name" in css
    assert ".dataset-glance-grid:has(.live-query-card) .dataset-glance-card.live-query-card" in css


def test_dataset_index_hides_subtables_and_parent_page_links_them_compactly(tmp_path):
    build_site(output_dir=tmp_path)

    dataset_index = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    assert "Addresses Transfers" in dataset_index
    assert 'href="datasets/addresses_transfers.html"' in dataset_index
    assert 'data-source-query-id="6901789"' in dataset_index
    assert "Addresses Transfers Daily" not in dataset_index
    assert "Addresses Transfers Hourly" not in dataset_index
    assert "Addresses Transfers Intermediate" not in dataset_index
    assert 'data-source-query-id="6119694"' not in dataset_index
    assert 'data-source-query-id="6901762"' not in dataset_index
    assert 'data-source-query-id="7576331"' not in dataset_index
    assert 'href="datasets/addresses_transfers_daily.html"' not in dataset_index
    assert 'href="datasets/addresses_transfers_hourly.html"' not in dataset_index
    assert 'href="datasets/addresses_transfers_intermediate.html"' not in dataset_index

    assert "Addresses List" in dataset_index
    assert 'href="datasets/addresses_list.html"' in dataset_index
    assert 'data-source-query-id="6118315"' in dataset_index

    parent_page = (tmp_path / "datasets" / "addresses_transfers.html").read_text(encoding="utf-8")
    assert "Supporting sub-tables" in parent_page
    assert "Supporting layers used for lineage, debugging, and freshness/cost-aware dataset construction." in parent_page
    assert 'href="../datasets/addresses_transfers_daily.html"' in parent_page
    assert 'href="../datasets/addresses_transfers_hourly.html"' in parent_page
    assert 'href="../datasets/addresses_transfers_intermediate.html"' in parent_page
    assert "Addresses Transfers Daily" in parent_page
    assert "Addresses Transfers Hourly" in parent_page
    assert "Addresses Transfers Intermediate" in parent_page
    assert 'class="dataset-browser-card"' not in parent_page
    assert "query_6901789" in parent_page
    assert parent_page.count("<span>Live query</span>") == 1
    assert "Live query table" not in parent_page
    assert "query_7576959" in parent_page

    assert (tmp_path / "datasets" / "addresses_transfers_daily.html").exists()
    assert (tmp_path / "datasets" / "addresses_transfers_hourly.html").exists()
    assert (tmp_path / "datasets" / "addresses_transfers_intermediate.html").exists()

    addresses_list_page = (tmp_path / "datasets" / "addresses_list.html").read_text(encoding="utf-8")
    assert 'href="../datasets/etherfi_assets_under_management.html"' in addresses_list_page
    assert 'href="../datasets/etherfi_addresses.html"' in addresses_list_page
    assert 'href="../datasets/addresses_transfers_daily.html"' not in addresses_list_page
    assert "Schema" in addresses_list_page
    assert "Tracked address used for AUM analysis." in addresses_list_page
    assert "Freshness timestamp column for this dataset." in addresses_list_page


def test_dataset_index_hides_token_transfer_subtables_and_parent_page_links_them_compactly(tmp_path):
    build_site(output_dir=tmp_path)

    dataset_index = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    assert "Tokens Transfers" in dataset_index
    assert 'href="datasets/tokens_transfers.html"' in dataset_index
    assert 'data-source-query-id="6901790"' in dataset_index
    assert "Tokens Transfers Daily" not in dataset_index
    assert "Tokens Transfers Hourly" not in dataset_index
    assert "Tokens Transfers Intermediate" not in dataset_index
    assert "Tokens WETH Transfers" not in dataset_index
    assert 'data-source-query-id="6102580"' not in dataset_index
    assert 'data-source-query-id="6901763"' not in dataset_index
    assert 'data-source-query-id="7570243"' not in dataset_index
    assert 'data-source-query-id="6226918"' not in dataset_index
    assert 'href="datasets/tokens_transfers_daily.html"' not in dataset_index
    assert 'href="datasets/tokens_transfers_hourly.html"' not in dataset_index
    assert 'href="datasets/tokens_transfers_intermediate.html"' not in dataset_index
    assert 'href="datasets/tokens_weth_transfers.html"' not in dataset_index
    assert 'href="datasets/tokens_weth_tfers.html"' not in dataset_index

    assert "Tokens List" in dataset_index
    assert 'href="datasets/tokens_list.html"' in dataset_index
    assert 'data-source-query-id="6101189"' in dataset_index

    parent_page = (tmp_path / "datasets" / "tokens_transfers.html").read_text(encoding="utf-8")
    assert "Supporting sub-tables" in parent_page
    assert 'href="../datasets/tokens_transfers_daily.html"' in parent_page
    assert 'href="../datasets/tokens_transfers_hourly.html"' in parent_page
    assert 'href="../datasets/tokens_transfers_intermediate.html"' in parent_page
    assert 'href="../datasets/tokens_weth_transfers.html"' in parent_page
    assert "Tokens Transfers Daily" in parent_page
    assert "Tokens Transfers Hourly" in parent_page
    assert "Tokens Transfers Intermediate" in parent_page
    assert "Tokens WETH Transfers" in parent_page
    assert 'class="dataset-browser-card"' not in parent_page
    assert "query_6901790" in parent_page
    assert parent_page.count("<span>Live query</span>") == 1
    assert "Live query table" not in parent_page
    assert "query_7576181" in parent_page

    assert (tmp_path / "datasets" / "tokens_transfers_daily.html").exists()
    assert (tmp_path / "datasets" / "tokens_transfers_hourly.html").exists()
    assert (tmp_path / "datasets" / "tokens_transfers_intermediate.html").exists()
    assert (tmp_path / "datasets" / "tokens_weth_transfers.html").exists()
    assert not (tmp_path / "datasets" / "tokens_weth_tfers.html").exists()

    tokens_list_page = (tmp_path / "datasets" / "tokens_list.html").read_text(encoding="utf-8")
    assert 'href="../datasets/tokens_transfers.html"' in tokens_list_page
    assert 'href="../datasets/tokens_transfers_daily.html"' not in tokens_list_page
    assert "Token decimals used to normalize raw token amounts." in tokens_list_page
    assert "True when the token is a rebasing token" in tokens_list_page


def test_contract_activity_dataset_pages_render_registry_relationships(tmp_path):
    build_site(output_dir=tmp_path)

    dataset_index = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    assert "Contracts Logs" in dataset_index
    assert 'href="datasets/contracts_logs.html"' in dataset_index
    assert 'data-source-query-id="6090018"' in dataset_index
    assert "Contracts Traces" in dataset_index
    assert 'href="datasets/contracts_traces.html"' in dataset_index
    assert 'data-source-query-id="6090651"' in dataset_index
    assert "Contracts Addresses List" in dataset_index
    assert 'href="datasets/contracts_addresses_list.html"' in dataset_index
    assert 'data-source-query-id="6089538"' in dataset_index

    logs_page = (tmp_path / "datasets" / "contracts_logs.html").read_text(encoding="utf-8")
    assert "Contracts Logs" in logs_page
    assert "https://dune.com/queries/6090018" in logs_page
    assert "Event signature topic for the log." in logs_page
    assert "Freshness timestamp column for this dataset." in logs_page
    assert "Related datasets and dashboards" in logs_page
    assert 'class="related-resource-list"' in logs_page
    assert 'href="../datasets/contracts_addresses_list.html"' in logs_page
    assert 'href="../datasets/contracts_traces.html"' in logs_page
    assert 'href="../datasets/tokens_rates_oracle_pegs.html"' in logs_page
    assert 'href="../datasets/tokens_exchange_rates_daily.html"' in logs_page

    traces_page = (tmp_path / "datasets" / "contracts_traces.html").read_text(encoding="utf-8")
    assert "Contracts Traces" in traces_page
    assert "https://dune.com/queries/6090651" in traces_page
    assert "Raw input calldata for the trace/call." in traces_page
    assert "Freshness timestamp column for this dataset." in traces_page
    assert 'href="../datasets/contracts_addresses_list.html"' in traces_page
    assert 'href="../datasets/contracts_logs.html"' in traces_page
    assert 'href="../datasets/tokens_rates_oracle_pegs.html"' in traces_page
    assert 'href="../datasets/tokens_exchange_rates_daily.html"' in traces_page

    registry_page = (tmp_path / "datasets" / "contracts_addresses_list.html").read_text(
        encoding="utf-8"
    )
    assert "Contracts Addresses List" in registry_page
    assert "https://dune.com/queries/6089538" in registry_page
    assert "Event signature topic to track for this contract" in registry_page
    assert "Freshness timestamp column for this dataset." in registry_page
    assert 'href="../datasets/contracts_logs.html"' in registry_page
    assert 'href="../datasets/contracts_traces.html"' in registry_page


def test_addresses_traits_dataset_page_renders_schema_and_related_links(tmp_path):
    build_site(output_dir=tmp_path)

    dataset_index = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    assert "Addresses Traits" in dataset_index
    assert 'href="datasets/addresses_traits.html"' in dataset_index
    assert 'data-source-query-id="6127413"' in dataset_index

    page = (tmp_path / "datasets" / "addresses_traits.html").read_text(encoding="utf-8")
    assert "Addresses Traits" in page
    assert "https://dune.com/queries/6127413" in page
    assert "one row per labeled address and blockchain/project context" in page
    assert "Human-readable name of the address." in page
    assert "Category/classification label for the address." in page
    assert "Legacy or helper trait field" in page
    assert "Freshness timestamp column for this dataset." in page
    assert 'href="../datasets/addresses_list.html"' in page
    assert 'href="../datasets/etherfi_addresses.html"' in page
    assert 'href="../datasets/addresses_transfers.html"' in page
    assert 'href="../datasets/etherfi_assets_under_management.html"' in page
    assert 'href="../dashboards/etherfi_overview.html"' in page


def test_dataset_schema_descriptions_render_from_schema_and_important_columns(tmp_path):
    datasets_dir = tmp_path / "datasets"
    category_dir = datasets_dir / "demo_category"
    category_dir.mkdir(parents=True)
    (category_dir / "mapping_schema.yaml").write_text(
        "name: demo.mapping_schema\n"
        "display_name: Mapping Schema Dataset\n"
        "description: Dataset for schema description rendering.\n"
        "important_columns:\n"
        "  user_safe: Important fallback should not win\n"
        "  token_balance_usd: USD value of the token balance\n"
        "  chain:\n"
        "    description: Blockchain fallback from nested important map\n"
        "schema:\n"
        "  user_safe:\n"
        "    type: varbinary\n"
        "    description: Schema safe address description\n"
        "  token_balance_usd: double\n"
        "  chain:\n"
        "    type: varchar\n"
        "  no_description: varchar\n"
        "  this_is_a_very_long_schema_column_name_that_should_wrap_inside_the_column_cell_without_breaking_layout: varchar\n",
        encoding="utf-8",
    )
    (category_dir / "list_schema.yaml").write_text(
        "name: demo.list_schema\n"
        "display_name: List Schema Dataset\n"
        "description: Dataset for list-shaped schema metadata.\n"
        "important_columns:\n"
        "  - name: cash_safe\n"
        "    description: Cash safe address\n"
        "  - column: token_balance\n"
        "    description: Important balance fallback should not win\n"
        "  - block_number: Block number fallback\n"
        "  - no_description_column\n"
        "schema:\n"
        "  - name: cash_safe\n"
        "    type: varbinary\n"
        "  - column: token_balance\n"
        "    type: double\n"
        "    description: Schema balance description\n"
        "  - block_number: bigint\n"
        "  - name: no_description_column\n"
        "    type: varchar\n",
        encoding="utf-8",
    )

    build_site(output_dir=tmp_path / "site", datasets_dir=datasets_dir, dashboard_registry_path=None)

    mapping_page = (tmp_path / "site" / "datasets" / "mapping_schema.html").read_text(
        encoding="utf-8"
    )
    css = (tmp_path / "site" / "assets" / "styles.css").read_text(encoding="utf-8")
    assert "<th>Column</th><th>Type</th><th>Description</th>" in mapping_page
    assert "<td><code>user_safe</code></td><td>varbinary</td>" in mapping_page
    assert (
        "<td><code>this_is_a_very_long_schema_column_name_that_should_wrap_inside_the_column_cell_without_breaking_layout</code></td><td>varchar</td>"
        in mapping_page
    )
    assert '<td class="schema-description">Schema safe address description</td>' in mapping_page
    assert "Important fallback should not win" not in mapping_page
    assert '<td class="schema-description">USD value of the token balance</td>' in mapping_page
    assert '<td class="schema-description">Blockchain fallback from nested important map</td>' in mapping_page
    assert '<span class="schema-description-empty">&mdash;</span>' in mapping_page
    assert "Important columns" not in mapping_page
    assert "table-layout: fixed;" in css
    assert ".schema-table td:first-child code" in css
    assert "overflow-wrap: anywhere;" in css
    assert "word-break: break-word;" in css

    list_page = (tmp_path / "site" / "datasets" / "list_schema.html").read_text(
        encoding="utf-8"
    )
    assert "<th>Column</th><th>Type</th><th>Description</th>" in list_page
    assert '<td class="schema-description">Cash safe address</td>' in list_page
    assert '<td class="schema-description">Schema balance description</td>' in list_page
    assert "Important balance fallback should not win" not in list_page
    assert '<td class="schema-description">Block number fallback</td>' in list_page
    assert '<td><code>no_description_column</code></td><td>varchar</td>' in list_page
    assert '<span class="schema-description-empty">&mdash;</span>' in list_page
    assert "Important columns" not in list_page


def test_load_dashboard_entries_reads_categorized_files_and_dedupes_legacy(tmp_path):
    dashboards_dir = tmp_path / "dashboards"
    stake_dir = dashboards_dir / "stake"
    stake_dir.mkdir(parents=True)
    (stake_dir / "etherfi_overview.yaml").write_text(
        "name: etherfi_overview\n"
        "title: ether.fi\n"
        "url: https://dune.com/ether_fi/etherfi\n"
        "show_in_core: true\n"
        "description: Main dashboard.\n"
        "tags:\n"
        "  - overview\n"
        "datasets:\n"
        "  - dune.ether_fi.result_etherfi_protocol_token_tvl\n",
        encoding="utf-8",
    )
    (dashboards_dir / "registry.yaml").write_text(
        "dashboards:\n"
        "  - name: etherfi_overview\n"
        "    title: Duplicate legacy dashboard\n"
        "  - name: legacy_cash\n"
        "    title: Legacy Cash\n"
        "    category: cash\n"
        "    featured: true\n",
        encoding="utf-8",
    )

    entries = load_dashboard_entries(dashboards_dir)
    by_name = {entry.data["name"]: entry for entry in entries}

    assert sorted(by_name) == ["etherfi_overview", "legacy_cash"]
    assert by_name["etherfi_overview"].category == "stake"
    assert by_name["etherfi_overview"].data["category"] == "stake"
    assert by_name["etherfi_overview"].data["show_in_core"] is True
    assert by_name["etherfi_overview"].data["title"] == "ether.fi"
    assert by_name["etherfi_overview"].source_path == stake_dir / "etherfi_overview.yaml"
    assert by_name["legacy_cash"].category == "cash"
    assert by_name["legacy_cash"].data["show_in_core"] is True


def test_build_website_generates_dashboard_registry_pages(tmp_path):
    build_site(output_dir=tmp_path)

    dashboard_index = (tmp_path / "dashboards.html").read_text(encoding="utf-8")
    assert 'data-dashboards-page' in dashboard_index
    assert '<h1>Dashboards</h1>' in dashboard_index
    assert "Browse ether.fi Dune dashboards by product area and linked datasets." in dashboard_index
    assert "Total dashboards" in dashboard_index
    assert "Core dashboards" in dashboard_index
    assert "Categories" in dashboard_index
    assert "Linked datasets" in dashboard_index
    assert 'data-dashboard-nav="core"' in dashboard_index
    assert 'data-dashboard-nav="stake"' in dashboard_index
    assert 'data-dashboard-nav="cash"' in dashboard_index
    assert 'data-dashboard-nav="liquid"' in dashboard_index
    assert 'data-dashboard-nav="others"' in dashboard_index
    assert dashboard_index.find("<span>Core</span>") < dashboard_index.find("<span>Stake</span>")
    assert dashboard_index.find("<span>Stake</span>") < dashboard_index.find("<span>Cash</span>")
    assert dashboard_index.find("<span>Cash</span>") < dashboard_index.find("<span>Liquid</span>")
    assert dashboard_index.find("<span>Liquid</span>") < dashboard_index.find("<span>Others</span>")
    assert 'data-dashboard-section data-dashboard-group="core"' in dashboard_index
    assert 'data-dashboard-section data-dashboard-group="stake"' in dashboard_index
    assert 'data-dashboard-section data-dashboard-group="cash"' in dashboard_index
    assert "Core contains the top dashboards" in dashboard_index
    assert "ether.fi" in dashboard_index
    assert "ether.fi Cash" in dashboard_index
    assert dashboard_index.count('href="dashboards/etherfi_overview.html"') >= 2
    assert dashboard_index.count('href="dashboards/etherfi_cash.html"') >= 2
    assert 'href="dashboards/etherfi_overview.html"' in dashboard_index
    assert 'href="dashboards/etherfi_cash.html"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/etherfi"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/etherfi-cash"' in dashboard_index
    assert 'data-dashboard-card' in dashboard_index
    assert 'data-dashboard-core-card' in dashboard_index
    assert 'data-search=' in dashboard_index
    assert 'data-dashboard-category="stake"' in dashboard_index
    assert 'data-dashboard-category="cash"' in dashboard_index
    assert "cashback" in dashboard_index
    assert "spend" in dashboard_index
    assert "lending" in dashboard_index
    assert "user_safe" in dashboard_index
    assert 'id="dashboard-search"' in dashboard_index
    assert 'id="dashboard-count"' in dashboard_index
    assert 'id="dashboard-empty-state"' in dashboard_index
    assert 'src="assets/dashboards.js?v=' in dashboard_index
    assert "No dashboards documented in this group yet." in dashboard_index
    assert "No dashboards match your search." in dashboard_index
    assert "generated from dashboards/registry.yaml" not in dashboard_index

    overview_page = (tmp_path / "dashboards" / "etherfi_overview.html").read_text(
        encoding="utf-8"
    )
    assert "../assets/styles.css" in overview_page
    assert "https://dune.com/ether_fi/etherfi" in overview_page
    assert "Main ether.fi protocol overview dashboard" in overview_page
    assert "overview" in overview_page
    assert "protocol" in overview_page
    assert "At a glance" not in overview_page
    assert "Core display" not in overview_page
    assert "Linked datasets" in overview_page
    assert "Linked datasets and references" not in overview_page
    assert 'class="related-resource-list"' in overview_page
    assert 'class="related-resource"' in overview_page
    assert "dashboard-linked-dataset-card" not in overview_page
    assert "dashboard-linked-dataset-grid" not in overview_page
    assert 'href="../datasets/protocol_token_holders.html"' in overview_page
    assert 'href="../datasets/etherfi_protocol_token_tvl.html"' in overview_page
    assert "Ether.fi Protocol Token TVL" in overview_page
    assert "Dataset used by the main ether.fi overview dashboard for protocol token TVL" not in overview_page
    assert "<span>Refresh</span>" not in overview_page
    assert "utils.days" not in overview_page
    assert "labels.ens" not in overview_page
    assert "dex_aggregator.trades" not in overview_page
    assert "<h2>Source</h2>" not in overview_page
    assert "dashboards/stake/etherfi_overview.yaml" not in overview_page
    assert "Use this dashboard if" not in overview_page
    assert "dashboards/registry.yaml" not in overview_page

    cash_page = (tmp_path / "dashboards" / "etherfi_cash.html").read_text(
        encoding="utf-8"
    )
    assert "../assets/styles.css" in cash_page
    assert "ether.fi Cash" in cash_page
    assert "https://dune.com/ether_fi/etherfi-cash" in cash_page
    assert "Operational dashboard for ether.fi Cash activity" in cash_page
    assert "cashback" in cash_page
    assert "user_safe" in cash_page
    assert "At a glance" not in cash_page
    assert "Core display" not in cash_page
    assert "Linked datasets" in cash_page
    assert "Linked datasets and references" not in cash_page
    assert 'class="related-resource-list"' in cash_page
    assert 'class="related-resource"' in cash_page
    assert "dashboard-linked-dataset-card" not in cash_page
    assert "dashboard-linked-dataset-grid" not in cash_page
    assert "etherfi_optimism.casheventemitter_evt_cashback" not in cash_page
    assert "etherfi_optimism.casheventemitter_evt_spend" not in cash_page
    assert "dune.ether_fi.result_backup_etherfi_cash_scroll_events" not in cash_page
    assert 'href="../datasets/etherfi_cash_events.html"' in cash_page
    assert 'href="../datasets/etherfi_assets_under_management.html"' in cash_page
    assert 'href="../datasets/etherfi_cash_borrow_index.html"' in cash_page
    assert 'href="../datasets/tokens_prices_usd.html"' in cash_page
    assert "Minute-level raw/direct USD token price feed" not in cash_page
    assert "<span>Refresh</span>" not in cash_page
    assert "<h2>Source</h2>" not in cash_page
    assert "utils.days" not in cash_page


def test_dashboard_detail_omits_linked_dataset_section_without_internal_matches(tmp_path):
    dashboards_dir = tmp_path / "dashboards"
    others_dir = dashboards_dir / "others"
    others_dir.mkdir(parents=True)
    (others_dir / "external_only.yaml").write_text(
        "name: external_only\n"
        "title: External Only\n"
        "url: https://dune.com/example/external-only\n"
        "category: others\n"
        "description: Dashboard that only references raw external tables.\n"
        "tags:\n"
        "  - external\n"
        "datasets:\n"
        "  - raw.external_table\n"
        "  - utils.days\n",
        encoding="utf-8",
    )

    build_site(output_dir=tmp_path / "site", dashboard_registry_path=dashboards_dir)

    detail_page = (tmp_path / "site" / "dashboards" / "external_only.html").read_text(
        encoding="utf-8"
    )
    assert "External Only" in detail_page
    assert "Dashboard that only references raw external tables." in detail_page
    assert "https://dune.com/example/external-only" in detail_page
    assert "external" in detail_page
    assert "At a glance" not in detail_page
    assert "Linked datasets" not in detail_page
    assert "Linked datasets and references" not in detail_page
    assert "dashboard-linked-dataset-card" not in detail_page
    assert "dashboard-linked-dataset-grid" not in detail_page
    assert "raw.external_table" not in detail_page
    assert "utils.days" not in detail_page
    assert "<h2>Source</h2>" not in detail_page


def test_build_website_generates_freshness_status_page(tmp_path):
    freshness_path = tmp_path / "dataset_freshness.yaml"
    freshness_path.write_text(
        "protocol_token_holders:\n"
        "  query_id: 6213381\n"
        "  last_updated: '2026-06-01T11:00:00Z'\n"
        "dune.ether_fi.result_etherfi_protocol_token_tvl:\n"
        "  query_id: 6216803\n"
        "  last_updated: '2026-06-01T09:30:00Z'\n",
        encoding="utf-8",
    )

    build_site(
        output_dir=tmp_path / "site",
        freshness_registry_path=freshness_path,
        now=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
    )

    freshness_page = (tmp_path / "site" / "freshness.html").read_text(encoding="utf-8")
    assert '<section class="catalog-hero">' not in freshness_page
    assert '<p class="eyebrow">ether.fi Data Catalog</p>' not in freshness_page
    assert "<h1>Data Freshness</h1>" not in freshness_page
    assert (
        "Track refresh intervals, latest updates, and freshness status across the ether.fi materialized view catalog."
        not in freshness_page
    )
    assert "Stale datasets need attention" not in freshness_page
    assert "Latest snapshot" not in freshness_page
    assert "Freshness query" not in freshness_page
    assert "Latest imported row" not in freshness_page
    assert "Observed freshness comes from saved Dune query" not in freshness_page
    assert "generated from repo metadata" not in freshness_page
    assert "within documented interval" not in freshness_page
    assert "past expected refresh" not in freshness_page
    assert "missing freshness coverage" not in freshness_page
    assert "Search datasets" in freshness_page
    assert "Search by dataset, table name, category, status, or query ID..." in freshness_page
    assert "Dataset category filters" not in freshness_page
    assert "data-category-filter" not in freshness_page
    assert 'data-status-filter="all"' in freshness_page
    assert 'data-status-filter="fresh"' in freshness_page
    assert 'data-status-filter="delayed"' in freshness_page
    assert 'data-status-filter="stale"' in freshness_page
    assert 'data-status-filter="unknown"' in freshness_page
    assert "<table" not in freshness_page
    assert "catalog-table" not in freshness_page
    assert "Dataset registry" in freshness_page
    assert 'class="registry-list"' in freshness_page
    assert 'class="registry-card freshness-dataset-card stale"' in freshness_page
    assert 'class="registry-card freshness-dataset-card fresh"' in freshness_page
    assert 'class="registry-card freshness-dataset-card unknown"' in freshness_page
    assert "data-dataset-card" in freshness_page
    assert "data-search=" in freshness_page
    assert 'data-status="fresh"' in freshness_page
    assert 'data-status="stale"' in freshness_page
    assert 'id="dataset-search"' in freshness_page
    assert 'id="dataset-count"' in freshness_page
    assert 'data-freshness-count' in freshness_page
    assert 'id="dataset-empty-state"' in freshness_page
    assert "Source queries" not in freshness_page
    assert "Fresh" in freshness_page
    assert "Stale" in freshness_page
    assert "Unknown" in freshness_page
    assert 'href="datasets/protocol_token_holders.html"' in freshness_page
    assert 'href="datasets/etherfi_protocol_token_tvl.html"' in freshness_page
    assert "Protocol Token Holders" in freshness_page
    assert "Ether.fi Protocol Token TVL" in freshness_page
    assert "table-pill" not in freshness_page
    assert "<span>Category</span>" not in freshness_page
    assert '<span class="meta-chip protocol"><span>Category</span>' not in freshness_page
    assert '<span class="meta-chip interval"><span>Refresh</span><strong>1h</strong></span>' in freshness_page
    assert "<code>dune.ether_fi.result_" not in freshness_page
    assert "dune.ether_fi.result_etherfi_protocol_token_tvl" in freshness_page
    assert "Dataset used by the main ether.fi overview dashboard for protocol token TVL" not in freshness_page
    assert "Ether.fi Protocol Token TVLdune.ether_fi.result_etherfi_protocol_token_tvl" not in freshness_page
    assert "https://dune.com/queries/6213381" in freshness_page
    assert (
        'data-search="etherfi_protocol_token_holders protocol token holders ether.fi protocol fresh protocol 6213381 '
        "https://dune.com/queries/6213381 4h dune.ether_fi.result_etherfi_protocol_token_holders"
        in freshness_page
    )
    assert "View dataset" not in freshness_page
    assert 'class="dune-action"' in freshness_page
    assert 'href="https://dune.com/queries/6213381"' in freshness_page
    assert 'title="Source query on Dune">Dune</a>' in freshness_page
    assert "6213381" in freshness_page
    assert "2026-06-01 11:00 UTC" in freshness_page
    assert "2026-06-01 09:30 UTC" in freshness_page
    assert '<span class="meta-chip updated" title="2026-06-01 11:00 UTC"><span>Last refreshed</span><strong>1h ago</strong></span>' in freshness_page
    assert '<span class="meta-chip updated" title="2026-06-01 09:30 UTC"><span>Last refreshed</span><strong>2h 30m ago</strong></span>' in freshness_page
    assert 'class="freshness-meter fresh"' in freshness_page
    assert 'class="freshness-meter stale"' in freshness_page
    assert "Freshness: 8/10 green bars, refreshed 1h ago, expected every 4h" in freshness_page
    assert "Freshness: 10/10 red bars, refreshed 2h 30m ago, expected every 1h" in freshness_page
    assert '<span class="status-badge freshness-badge fresh">Fresh</span>' in freshness_page
    assert '<span class="status-badge freshness-badge stale">Stale</span>' in freshness_page
    assert '<span class="status-badge freshness-badge unknown">Unknown</span>' in freshness_page
    assert "Not documented yetNot documented yet" not in freshness_page
    assert '<span class="meta-chip updated" title="Not documented"><span>Last refreshed</span><strong>Not documented</strong></span>' in freshness_page
    assert "Next expected" not in freshness_page
    assert "No datasets match your search." in freshness_page
    assert 'src="assets/freshness.js?v=' in freshness_page
    assert 'src="assets/freshness.js" defer' not in freshness_page
    assert freshness_page.find("Ether.fi Protocol Token TVL") < freshness_page.find("Protocol Token Holders")
    assert (tmp_path / "site" / "assets" / "freshness.js").exists()


def test_default_built_freshness_output_uses_current_search_asset():
    build_site(output_dir=DEFAULT_OUTPUT_DIR)

    freshness_page = (DEFAULT_OUTPUT_DIR / "freshness.html").read_text(encoding="utf-8")
    freshness_js = (DEFAULT_OUTPUT_DIR / "assets" / "freshness.js").read_text(encoding="utf-8")

    assert 'src="assets/freshness.js?v=' in freshness_page
    assert 'src="assets/freshness.js" defer' not in freshness_page
    assert 'id="dataset-search"' in freshness_page
    assert "data-dataset-card" in freshness_page
    assert "data-search=" in freshness_page
    assert "data-status=" in freshness_page
    assert "dataset-search" in freshness_js
    assert "data-dataset-card" in freshness_js
    assert "dataset.status" in freshness_js
    assert "applyFilters" in freshness_js
    assert "__etherfiFreshnessSearchDebug" in freshness_js


def test_dataset_browser_output_uses_search_asset_and_stable_selectors(tmp_path):
    build_site(output_dir=tmp_path)

    datasets_page = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    datasets_js = (tmp_path / "assets" / "datasets.js").read_text(encoding="utf-8")
    dataset_detail_js = (tmp_path / "assets" / "dataset-detail.js").read_text(encoding="utf-8")

    assert 'src="assets/datasets.js?v=' in datasets_page
    assert 'src="assets/datasets.js" defer' not in datasets_page
    assert 'id="dataset-search"' in datasets_page
    assert "data-dataset-card" in datasets_page
    assert "data-search=" in datasets_page
    assert "data-status=" in datasets_page
    assert "data-dataset-nav" in datasets_page
    assert "data-dataset-category-section" in datasets_page
    assert "dataset-search" in datasets_js
    assert "data-dataset-card" in datasets_js
    assert "data-dataset-nav" in datasets_js
    assert "data-dataset-category-section" in datasets_js
    assert "applyFilters" in datasets_js
    assert "__etherfiDatasetBrowserDebug" in datasets_js
    assert "data-copy-text" in dataset_detail_js
    assert "navigator.clipboard.writeText" in dataset_detail_js
    assert "execCommand" in dataset_detail_js
    assert "Copy failed" in dataset_detail_js


def test_dataset_browser_filter_script_matches_search_terms():
    node = shutil.which("node")
    if node is None:
        return

    script = """
const browser = require("./website/assets/datasets.js");
const cards = [
  {
    category: "etherfi_protocol",
    search: "ether.fi protocol token tvl ether.fi protocol stale 1h 6216803 https://dune.com/queries/6216803 dune.ether_fi.result_etherfi_protocol_token_tvl token_supply_usd strategy_symbol",
  },
  {
    category: "prices",
    search: "tokens rates oracle pegs prices fresh 4h 5849669 https://dune.com/queries/5849669 dune.ether_fi.result_tokens_rates_oracle_pegs token_address usd_rate",
  },
  {
    category: "metadata",
    search: "tokens traits metadata unknown 2d 5711782 https://dune.com/queries/5711782 dune.ether_fi.result_tokens_traits decimals token_symbol",
  },
];
const names = (state) => browser.filterCards(cards, state).map((result) => result.visible);
console.log(JSON.stringify({
  title: names({ activeCategory: "all", query: "protocol tvl" }).filter(Boolean).length,
  category: names({ activeCategory: "all", query: "prices" }).filter(Boolean).length,
  queryId: names({ activeCategory: "all", query: "6216803" }).filter(Boolean).length,
  queryUrl: names({ activeCategory: "all", query: "https://dune.com/queries/5849669" }).filter(Boolean).length,
  tableName: names({ activeCategory: "all", query: "result_tokens_traits" }).filter(Boolean).length,
  column: names({ activeCategory: "all", query: "token_supply_usd" }).filter(Boolean).length,
  partial: names({ activeCategory: "all", query: "orac" }).filter(Boolean).length,
  categoryFilter: names({ activeCategory: "prices", query: "" }).filter(Boolean).length,
  categoryAndSearch: names({ activeCategory: "prices", query: "oracle" }).filter(Boolean).length,
  categoryMiss: names({ activeCategory: "metadata", query: "oracle" }).filter(Boolean).length,
  noMatch: names({ activeCategory: "all", query: "zzzz-no-match" }).filter(Boolean).length,
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    counts = json.loads(result.stdout)

    assert counts == {
        "title": 1,
        "category": 1,
        "queryId": 1,
        "queryUrl": 1,
        "tableName": 1,
        "column": 1,
        "partial": 1,
        "categoryFilter": 1,
        "categoryAndSearch": 1,
        "categoryMiss": 0,
        "noMatch": 0,
    }


def test_dashboard_browser_filter_script_matches_search_terms():
    node = shutil.which("node")
    if node is None:
        return

    script = """
const browser = require("./website/assets/dashboards.js");
const cards = [
  {
    category: "stake",
    search: "etherfi_overview ether.fi stake main protocol overview dashboard overview protocol tvl https://dune.com/ether_fi/etherfi dune.ether_fi.result_etherfi_protocol_token_tvl core",
  },
  {
    category: "cash",
    search: "etherfi_cash ether.fi cash cash operational dashboard cashback spend lending user_safe borrow repay liquidations https://dune.com/ether_fi/etherfi-cash dune.ether_fi.result_etherfi_cash_events",
  },
  {
    category: "liquid",
    search: "liquid_dashboard liquid liquid dashboard liquideth vaults",
  },
];
const shown = (query) => browser.filterCards(cards, query).filter((result) => result.visible).length;
console.log(JSON.stringify({
  title: shown("ether.fi cash"),
  category: shown("cash"),
  cashback: shown("cashback"),
  spend: shown("spend"),
  lending: shown("lending"),
  userSafe: shown("user_safe"),
  nonContiguousWords: shown("protocol tvl"),
  url: shown("etherfi-cash"),
  dataset: shown("cash events"),
  tag: shown("borrow"),
  partial: shown("liquideth"),
  noMatch: shown("zzzz-no-match"),
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    counts = json.loads(result.stdout)

    assert counts == {
        "title": 1,
        "category": 1,
        "cashback": 1,
        "spend": 1,
        "lending": 1,
        "userSafe": 1,
        "nonContiguousWords": 1,
        "url": 1,
        "dataset": 1,
        "tag": 1,
        "partial": 1,
        "noMatch": 0,
    }


def test_freshness_filter_script_combines_search_and_status():
    node = shutil.which("node")
    if node is None:
        return

    script = """
const filters = require("./website/assets/freshness.js");
const rows = [
  {
    status: "stale",
    search: "ether.fi protocol token tvl ether.fi protocol stale protocol 6216803 https://dune.com/queries/6216803 1h dune.ether_fi.result_etherfi_protocol_token_tvl",
  },
  {
    status: "delayed",
    search: "tokens rates oracle pegs prices delayed prices 5849669 https://dune.com/queries/5849669 4h dune.ether_fi.result_tokens_rates_oracle_pegs",
  },
  {
    status: "fresh",
    search: "tokens traits metadata fresh metadata 5711782 https://dune.com/queries/5711782 2d dune.ether_fi.result_tokens_traits",
  },
  {
    status: "unknown",
    search: "addresses traits metadata unknown metadata 6127413 https://dune.com/queries/6127413 2d dune.ether_fi.result_addresses_traits",
  },
];
const shown = (state) => filters.filterRows(rows, state).filter((result) => result.visible).length;
console.log(JSON.stringify({
  datasetName: shown({ status: "all", query: "TOKEN tvl" }),
  nonContiguousWords: shown({ status: "all", query: "protocol tvl" }),
  category: shown({ status: "all", query: "prices" }),
  status: shown({ status: "delayed", query: "" }),
  queryId: shown({ status: "all", query: "5849669" }),
  queryUrl: shown({ status: "all", query: "https://dune.com/queries/5849669" }),
  tableName: shown({ status: "all", query: "result_tokens_traits" }),
  partialWord: shown({ status: "all", query: "orac" }),
  allWithSearch: shown({ status: "all", query: "oracle" }),
  combined: shown({ status: "delayed", query: "oracle" }),
  combinedMiss: shown({ status: "fresh", query: "oracle" }),
  noMatch: shown({ status: "all", query: "not real" }),
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    counts = json.loads(result.stdout)

    assert counts == {
        "datasetName": 1,
        "nonContiguousWords": 1,
        "category": 1,
        "status": 1,
        "queryId": 1,
        "queryUrl": 1,
        "tableName": 1,
        "partialWord": 1,
        "allWithSearch": 1,
        "combined": 1,
        "combinedMiss": 0,
        "noMatch": 0,
    }


def test_generated_freshness_page_search_behavior_executes_in_dom(tmp_path):
    node = shutil.which("node")
    if node is None:
        return

    freshness_path = tmp_path / "dataset_freshness.yaml"
    freshness_path.write_text(
        "protocol_token_holders:\n"
        "  query_id: 6213381\n"
        "  last_updated: '2026-06-01T11:00:00Z'\n"
        "dune.ether_fi.result_etherfi_protocol_token_tvl:\n"
        "  query_id: 6216803\n"
        "  last_updated: '2026-06-01T09:30:00Z'\n",
        encoding="utf-8",
    )
    build_site(
        output_dir=tmp_path / "site",
        freshness_registry_path=freshness_path,
        now=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
    )

    script = r"""
const fs = require("fs");
const vm = require("vm");
const [htmlPath, jsPath] = process.argv.slice(1);
const html = fs.readFileSync(htmlPath, "utf8");
const source = fs.readFileSync(jsPath, "utf8");

function decodeHtml(value) {
  return String(value || "")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function datasetKey(name) {
  return name
    .slice(5)
    .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

function parseAttrs(rawAttrs) {
  const attrs = {};
  const attrPattern = /([\w:-]+)(?:="([^"]*)")?/g;
  let match;
  while ((match = attrPattern.exec(rawAttrs))) {
    attrs[match[1]] = decodeHtml(match[2] || "");
  }
  return attrs;
}

class ClassList {
  constructor(value) {
    this.classes = new Set(String(value || "").split(/\s+/).filter(Boolean));
  }
  toggle(name, force) {
    const shouldHaveClass = force === undefined ? !this.classes.has(name) : Boolean(force);
    if (shouldHaveClass) {
      this.classes.add(name);
    } else {
      this.classes.delete(name);
    }
    return shouldHaveClass;
  }
}

class FakeElement {
  constructor(attrs = {}, text = "") {
    this.attrs = { ...attrs };
    this.dataset = {};
    Object.entries(this.attrs).forEach(([name, value]) => {
      if (name.startsWith("data-")) {
        this.dataset[datasetKey(name)] = value;
      }
    });
    this.hidden = Object.prototype.hasOwnProperty.call(this.attrs, "hidden");
    this.value = this.attrs.value || "";
    this.textContent = text;
    this.style = { display: "" };
    this.listeners = {};
    this.classList = new ClassList(this.attrs.class || "");
    this.ownerDocument = null;
  }
  addEventListener(type, listener) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(listener);
  }
  dispatchEvent(event) {
    const normalized = typeof event === "string" ? { type: event } : event;
    for (const listener of this.listeners[normalized.type] || []) {
      listener.call(this, normalized);
    }
  }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
    if (name.startsWith("data-")) {
      this.dataset[datasetKey(name)] = String(value);
    }
  }
  getAttribute(name) {
    return this.attrs[name] || null;
  }
  querySelector(selector) {
    return this.ownerDocument.querySelector(selector);
  }
  querySelectorAll(selector) {
    return this.ownerDocument.querySelectorAll(selector);
  }
}

class FakeDocument {
  constructor() {
    this.readyState = "loading";
    this.listeners = {};
    this.page = new FakeElement({ "data-freshness-page": "" });
    this.search = null;
    this.count = null;
    this.empty = null;
    this.statusButtons = [];
    this.cards = [];
  }
  attach(element) {
    element.ownerDocument = this;
    return element;
  }
  addEventListener(type, listener) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(listener);
  }
  dispatchEvent(event) {
    const normalized = typeof event === "string" ? { type: event } : event;
    if (normalized.type === "DOMContentLoaded") {
      this.readyState = "complete";
    }
    for (const listener of this.listeners[normalized.type] || []) {
      listener.call(this, normalized);
    }
  }
  querySelector(selector) {
    if (selector === "[data-freshness-page]") return this.page;
    if (selector === "#dataset-search") return this.search;
    if (selector === "#dataset-count") return this.count;
    if (selector === "#dataset-empty-state") return this.empty;
    return null;
  }
  querySelectorAll(selector) {
    if (selector === "[data-status-filter]") return this.statusButtons;
    if (selector === "[data-dataset-card]") return this.cards;
    return [];
  }
}

function stripTags(text) {
  return decodeHtml(String(text || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim());
}

const doc = new FakeDocument();
doc.attach(doc.page);

const inputMatch = html.match(/<input\b([^>]*\bid="dataset-search"[^>]*)>/);
if (!inputMatch) throw new Error("dataset search input was not generated");
doc.search = doc.attach(new FakeElement(parseAttrs(inputMatch[1])));

const countMatch = html.match(/<span\b([^>]*\bid="dataset-count"[^>]*)>(.*?)<\/span>/);
if (!countMatch) throw new Error("dataset count was not generated");
doc.count = doc.attach(new FakeElement(parseAttrs(countMatch[1]), stripTags(countMatch[2])));

const emptyMatch = html.match(/<div\b([^>]*\bid="dataset-empty-state"[^>]*)>(.*?)<\/div>/);
if (!emptyMatch) throw new Error("dataset empty state was not generated");
doc.empty = doc.attach(new FakeElement(parseAttrs(emptyMatch[1]), stripTags(emptyMatch[2])));

for (const match of html.matchAll(/<button\b([^>]*\bdata-status-filter="[^"]+"[^>]*)>(.*?)<\/button>/g)) {
  doc.statusButtons.push(doc.attach(new FakeElement(parseAttrs(match[1]), stripTags(match[2]))));
}

for (const match of html.matchAll(/<article\b([^>]*\bdata-dataset-card\b[^>]*)>([\s\S]*?)<\/article>/g)) {
  const attrs = parseAttrs(match[1]);
  const name = (match[2].match(/<a\b[^>]*class="freshness-dataset-link"[^>]*>(.*?)<\/a>/) || [null, ""])[1];
  doc.cards.push(doc.attach(new FakeElement(attrs, stripTags(name))));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const context = {
  document: doc,
  window: {},
  console,
};
context.globalThis = context.window;
vm.runInNewContext(source, context, { filename: jsPath });
doc.dispatchEvent({ type: "DOMContentLoaded" });

function visibleCards() {
  return doc.cards.filter((card) => !card.hidden && card.style.display !== "none");
}

function clickStatus(status) {
  const button = doc.statusButtons.find((candidate) => candidate.dataset.statusFilter === status);
  assert(button, `Missing ${status} status button`);
  button.dispatchEvent({ type: "click" });
}

function search(value) {
  doc.search.value = value;
  doc.search.dispatchEvent({ type: "input" });
}

const total = doc.cards.length;
assert(total > 5, "Expected generated dataset cards");
assert(doc.count.textContent === `${total} shown`, "Initial count did not match generated cards");
assert(doc.empty.hidden === true, "Empty state should start hidden");
assert(typeof context.window.__etherfiFreshnessSearchDebug === "function", "Debug hook was not exposed");
let debug = context.window.__etherfiFreshnessSearchDebug();
assert(debug.inputFound === true, "Debug hook should report search input");
assert(debug.cardCount === total, "Debug hook card count did not match");
assert(debug.visibleCount === total, "Debug hook visible count did not match initial cards");
assert(debug.selectedStatus === "all", "Debug hook should start with all status");

search("protocol tvl");
assert(visibleCards().length > 0 && visibleCards().length < total, "Non-contiguous dataset search should narrow cards");
assert(visibleCards().some((card) => card.textContent.includes("Ether.fi Protocol Token TVL")), "Non-contiguous dataset search should include Protocol Token TVL");
assert(!visibleCards().some((card) => card.textContent.includes("Protocol Token Holders")), "Non-contiguous dataset search should hide unrelated holders card");
assert(doc.count.textContent === `${visibleCards().length} shown`, "Non-contiguous search count did not update");

search("protocol token tvl");
assert(visibleCards().length === 1, "Dataset search should show one card");
assert(visibleCards()[0].textContent.includes("Ether.fi Protocol Token TVL"), "Dataset search showed the wrong card");
assert(doc.count.textContent === "1 shown", "Dataset search count did not update");

search("6216803");
assert(visibleCards().length === 1, "Query ID search should show one card");
assert(visibleCards()[0].textContent.includes("Ether.fi Protocol Token TVL"), "Query ID search showed the wrong card");

search("https://dune.com/queries/6216803");
assert(visibleCards().length === 1, "Query URL search should show one card");

clickStatus("stale");
assert(visibleCards().length === 1, "Stale status + query search should show one card");

clickStatus("fresh");
assert(visibleCards().length === 0, "Fresh status + stale query search should show no cards");
assert(doc.count.textContent === "0 shown", "No-match count did not update");
assert(doc.empty.hidden === false, "Empty state should be visible when no cards match");

clickStatus("all");
assert(visibleCards().length === 1, "All status should restore current search results");

search("zzzz-no-match");
assert(visibleCards().length === 0, "Nonsense search should show no cards");
assert(doc.empty.hidden === false, "Nonsense search should show empty state");

search("");
assert(visibleCards().length === total, "Clearing search should restore all cards for All status");
assert(doc.count.textContent === `${total} shown`, "Clearing search should restore count");
assert(doc.empty.hidden === true, "Empty state should hide after clearing search");
debug = context.window.__etherfiFreshnessSearchDebug();
assert(debug.visibleCount === total, "Debug hook visible count should update after clearing search");

console.log(JSON.stringify({ total, finalCount: doc.count.textContent }));
"""
    result = subprocess.run(
        [
            node,
            "-e",
            script,
            str(tmp_path / "site" / "freshness.html"),
            str(tmp_path / "site" / "assets" / "freshness.js"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior["total"] > 5
    assert behavior["finalCount"] == f'{behavior["total"]} shown'


def test_freshness_relative_age_and_meter_buckets():
    assert format_relative_age(10) == "10 min ago"
    assert format_relative_age(108) == "1h 48m ago"
    assert format_relative_age(2880) == "2d ago"
    assert format_relative_age(None) == "Not documented"

    base_row = {"refresh_interval_minutes": 120}

    assert freshness_meter_for_row({**base_row, "ratio": 0.05, "lag_minutes": 6})["filled"] == 10
    assert freshness_meter_for_row({**base_row, "ratio": 0.2, "lag_minutes": 24})["filled"] == 9
    assert freshness_meter_for_row({**base_row, "ratio": 0.5, "lag_minutes": 60})["filled"] == 5
    assert freshness_meter_for_row({**base_row, "ratio": 0.9, "lag_minutes": 108})["filled"] == 1
    delayed_meter = freshness_meter_for_row({**base_row, "ratio": 1.5, "lag_minutes": 180})
    assert delayed_meter["phase"] == "delayed"
    assert delayed_meter["filled"] == 5
    stale_meter = freshness_meter_for_row({**base_row, "ratio": 2.1, "lag_minutes": 252})
    assert stale_meter["phase"] == "stale"
    assert stale_meter["filled"] == 10
    unknown_meter = freshness_meter_for_row({"refresh_interval_minutes": None, "ratio": None, "lag_minutes": None})
    assert unknown_meter["phase"] == "unknown"
    assert unknown_meter["filled"] == 0


def test_dataset_freshness_interval_summary_uses_dedicated_status_pills():
    data = {"refresh_interval_minutes": 60}
    cases = [
        ("fresh", "Fresh", 18, "fresh", "18m ago · Every 1h"),
        ("delayed", "Delayed", 130, "delayed", "2h 10m ago · Every 1h"),
        ("stale", "Stale", 540, "stale", "9h ago · Every 1h"),
        ("not-documented", "Not documented", None, "unknown", "Not documented · Every 1h"),
    ]

    for status, label, lag_minutes, badge_class, text in cases:
        html = dataset_freshness_interval_summary(
            data,
            {"status": status, "label": label, "lag_minutes": lag_minutes},
        )
        assert f'class="freshness-status-pill status-{badge_class}">{label if status != "not-documented" else "Unknown"}</span>' in html
        assert 'class="status-badge freshness-badge' not in html
        assert 'class="freshness-refresh-text"' in html
        assert text in html


def test_build_website_dataset_pages_show_missing_fields_without_breaking(tmp_path):
    datasets_dir = tmp_path / "datasets"
    category_dir = datasets_dir / "demo_category"
    category_dir.mkdir(parents=True)
    (category_dir / "minimal_dataset.yaml").write_text(
        "name: demo.minimal_dataset\n"
        "display_name: Minimal Dataset\n"
        "description: A deliberately sparse dataset for docs generation.\n",
        encoding="utf-8",
    )
    (category_dir / "missing_description.yaml").write_text(
        "name: demo.missing_description\n"
        "display_name: Missing Description Dataset\n",
        encoding="utf-8",
    )

    build_site(output_dir=tmp_path / "site", datasets_dir=datasets_dir, dashboard_registry_path=None)

    dataset_index = (tmp_path / "site" / "datasets.html").read_text(encoding="utf-8")
    assert "Demo Category" in dataset_index
    assert "Minimal Dataset" in dataset_index
    assert "Missing Description Dataset" in dataset_index
    assert 'data-dataset-nav="demo_category"' in dataset_index
    assert 'data-dataset-card' in dataset_index
    assert 'data-search=' in dataset_index

    detail_page = (tmp_path / "site" / "datasets" / "minimal_dataset.html").read_text(
        encoding="utf-8"
    )
    assert "Minimal Dataset" in detail_page
    assert NOT_DOCUMENTED in detail_page
    assert "A deliberately sparse dataset for docs generation." in detail_page
    assert "At a glance" in detail_page
    assert "Freshness &amp; Refresh Interval" in detail_page
    assert "Freshness &amp; Interval" not in detail_page
    assert '<div class="glance-value freshness-refresh-value">' in detail_page
    assert '<span class="freshness-status-pill status-unknown">Unknown</span>' in detail_page
    assert '<span class="freshness-refresh-text">Not documented · Interval not documented</span>' in detail_page
    assert "Not documented · Interval not documented" in detail_page
    assert "<span>Category</span>" not in detail_page
    assert "<span>Query ready</span>" not in detail_page
    assert "<span>Freshness column</span>" not in detail_page
    assert "<span>Source query ID</span>" not in detail_page
    assert "<span>Refresh interval</span>" not in detail_page
    assert "About this table" in detail_page
    assert 'class="dataset-glance-card full-table-name copyable-table-name"' in detail_page
    assert 'class="table-pill table-pill-block"' in detail_page
    assert "Schema" in detail_page
    assert "Related datasets and dashboards" in detail_page
    assert "What this table contains" not in detail_page
    assert "Important columns" not in detail_page
    assert "Query notes" not in detail_page
    assert "Query notes / caveats" not in detail_page
    assert "Use when" not in detail_page
    assert "Do not use when" not in detail_page

    fallback_page = (tmp_path / "site" / "datasets" / "missing_description.html").read_text(
        encoding="utf-8"
    )
    assert "Missing Description Dataset" in fallback_page
    assert "About this table" in fallback_page
    assert "This dataset documents Demo Category data for Missing Description Dataset." in fallback_page


def test_build_website_can_use_custom_source_and_output(tmp_path):
    source_dir = tmp_path / "source"
    pages_dir = source_dir / "pages"
    templates_dir = source_dir / "templates"
    assets_dir = source_dir / "assets"
    pages_dir.mkdir(parents=True)
    templates_dir.mkdir()
    assets_dir.mkdir()

    (pages_dir / "index.md").write_text(
        "---\n"
        "title: Test Site\n"
        "nav_label: Home\n"
        "order: 1\n"
        "---\n"
        "# Hello\n"
        "\n"
        "This is **markdown**.",
        encoding="utf-8",
    )
    (templates_dir / "base.html.tpl").write_text(
        "<html><head><title>$title</title></head><body>$nav<main>$content</main></body></html>",
        encoding="utf-8",
    )
    (assets_dir / "styles.css").write_text("body { color: black; }", encoding="utf-8")

    output_dir = tmp_path / "output"
    build_site(
        source_dir=source_dir,
        output_dir=output_dir,
        datasets_dir=None,
        dashboard_registry_path=None,
    )

    html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "<h2>Hello</h2>" in html
    assert "<strong>markdown</strong>" in html
    assert Path(output_dir / "assets" / "styles.css").exists()


def test_generated_website_local_links_resolve(tmp_path):
    build_site(output_dir=tmp_path)
    html_files = list(tmp_path.glob("**/*.html"))
    assert html_files

    for html_file in html_files:
        html = html_file.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"]+)"', html):
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = (html_file.parent / href.split("#", 1)[0]).resolve()
            assert target.exists(), f"{html_file.relative_to(tmp_path)} links to missing {href}"
