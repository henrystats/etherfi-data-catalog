from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from scripts.build_website import (
    DEFAULT_OUTPUT_DIR,
    NOT_DOCUMENTED,
    build_site,
    category_description,
    dataset_card_status_label,
    dataset_freshness_interval_summary,
    format_compact_duration,
    format_relative_age,
    freshness_meter_for_row,
    load_dashboard_entries,
    load_dataset_entries,
    load_pages,
    normalize_schema_search_text,
    render_compact_dataset_card,
    serialize_catalog_index,
    site_output_path,
    validate_page_output_path,
)


def test_website_pages_include_expected_navigation_entries():
    pages = load_pages()
    nav_labels = [page.nav_label for page in pages]

    assert nav_labels == [
        "Home",
        "MCP",
        "Datasets",
        "Dashboards",
        "Studio",
        "Freshness",
    ]


@pytest.mark.parametrize(
    "output_path",
    ["../escape.html", "/tmp/escape.html", "studio\\..\\escape.html", "studio/data.json"],
)
def test_page_output_paths_reject_traversal_and_non_html_targets(output_path):
    with pytest.raises(ValueError, match="Unsafe website page output_path"):
        validate_page_output_path(output_path)


def test_site_output_path_cannot_escape_the_build_directory(tmp_path):
    with pytest.raises(ValueError, match="escapes the build directory"):
        site_output_path(tmp_path, "../escape.html")


def test_dataset_category_description_uses_dynamic_singular_and_plural_grammar():
    assert category_description("metadata", 1) == (
        "1 dataset in the Metadata catalog group."
    )
    assert category_description("prices", 7) == (
        "7 datasets in the Prices catalog group."
    )


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
    assert 'href="assets/styles.css?v=' in index_html
    assert "<title>ether.fi Data Catalog</title>" in index_html
    assert "ether.fi Data Catalog | ether.fi Data Catalog" not in index_html
    assert 'class="nav-link active" href="index.html" aria-current="page"' in index_html
    assert 'data-home-page' in index_html
    assert '<span class="brand-mark">ether.fi</span>' in index_html
    assert '<span class="brand-mark">e.fi</span>' not in index_html
    assert "ether.fi Data Catalog" in index_html
    assert (
        "A polished, repo-backed catalog for finding ether.fi datasets, checking "
        "freshness, discovering dashboards, and giving AI agents the right context "
        "before Dune execution."
        in index_html
    )
    assert "ind the right ether.fi dataset" not in index_html
    assert 'href="datasets.html">Explore datasets</a>' in index_html
    assert '<a class="home-preview-card" href="dashboards.html">' in index_html
    assert '<span class="dataset-detail-action">View dashboards</span>' in index_html
    assert 'href="freshness.html">Check freshness</a>' in index_html
    assert '<a class="home-preview-card" href="mcp.html">' in index_html
    assert '<span class="dataset-detail-action">Learn about MCP</span>' in index_html
    assert index_html.count('<a class="home-preview-card" href=') == 4
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
    assert "Data discovery &amp; operations" not in hero_html.group(1)
    assert "ether.fi data command center" not in hero_html.group(1).lower()
    assert "home-command-preview" not in hero_html.group(1)
    assert "Which table backs Cash activity and is it fresh enough?" not in hero_html.group(1)
    assert 'href="datasets.html">Explore datasets</a>' in hero_html.group(1)
    assert 'href="dashboards.html">Find dashboards</a>' in hero_html.group(1)
    assert 'href="freshness.html">Check freshness</a>' in hero_html.group(1)
    assert 'href="mcp.html">Connect MCP</a>' in hero_html.group(1)
    assert "catalog-summary-card" not in hero_html.group(1)
    assert "Total datasets" not in index_html
    assert "Total dashboards" not in index_html
    assert "Fresh datasets" not in index_html
    assert "MCP tools" not in index_html
    assert "Choose a workflow" in index_html
    assert "Start from the surface that matches the question in front of you." not in index_html
    assert "Jump straight into the page that matches the question in front of you." not in index_html
    assert "Find cataloged tables, inspect caveats, and review schemas." in index_html
    assert "Find existing Dune dashboards before building new views." in index_html
    assert "Verify freshness, cadence, and source-query context." in index_html
    assert "Set up the catalog MCP alongside Dune MCP." in index_html
    assert "How this fits together" not in index_html
    assert "A short path through the catalog without duplicating the full MCP guide." not in index_html
    assert "Discover the right dataset or dashboard" not in index_html
    assert "Start with <strong>Datasets</strong>" not in index_html
    assert "Start with <strong>MCP</strong>" not in index_html
    assert "Monday demo path" not in index_html
    assert "Built for three audiences" not in index_html
    assert "Questions this makes safer" not in index_html
    core_css = (tmp_path / "assets" / "styles.css").read_text(encoding="utf-8")
    assert ".home-command-preview" not in core_css
    assert ".command-preview-" not in core_css
    assert ".home-stat-grid" not in core_css

    dataset_entries = load_dataset_entries()
    dataset_pages = list((tmp_path / "datasets").glob("*.html"))
    assert len(dataset_pages) == len(dataset_entries)
    assert (tmp_path / "dashboards" / "etherfi_overview.html").exists()
    assert (tmp_path / "dashboards" / "etherfi_cash.html").exists()
    assert (tmp_path / "dashboards" / "etherfi_cash_swaps.html").exists()
    assert (tmp_path / "dashboards" / "etherfi_users.html").exists()
    assert (tmp_path / "dashboards" / "eeth_staking.html").exists()
    assert (tmp_path / "dashboards" / "weeth_l2s.html").exists()
    assert (tmp_path / "dashboards" / "weeth_utilization.html").exists()
    assert (tmp_path / "dashboards" / "liquid_vaults.html").exists()

    freshness_html = (tmp_path / "freshness.html").read_text(encoding="utf-8")
    assert "<title>Freshness | ether.fi Data Catalog</title>" in freshness_html
    assert '<span class="brand-mark">ether.fi</span>' in freshness_html
    assert '<span class="brand-mark">e.fi</span>' not in freshness_html
    assert (
        '<h1 id="freshness-page-title" class="visually-hidden">Freshness</h1>'
        in freshness_html
    )
    assert (
        '<h2 id="freshness-source-title" class="freshness-source-title">'
        "Source &amp; automation</h2>"
        in freshness_html
    )
    assert "<h1>Freshness</h1>" not in freshness_html
    assert "Static site" not in freshness_html
    assert "Runtime snapshot aware" not in freshness_html
    assert "No live Dune call in the browser" not in freshness_html


def test_generated_pages_include_global_theme_contract(tmp_path):
    build_site(output_dir=tmp_path)

    html_files = sorted(tmp_path.glob("**/*.html"))
    assert html_files
    assert (tmp_path / "assets" / "theme.js").exists()

    for html_file in html_files:
        html = html_file.read_text(encoding="utf-8")
        relative_path = html_file.relative_to(tmp_path)
        asset_prefix = "../" * (len(relative_path.parts) - 1)
        head = re.search(r"<head>(.*?)</head>", html, re.S)

        assert head
        assert len(re.findall(r"<h1(?:\s|>)", html)) == 1
        assert html.count("data-theme-init") == 1
        assert html.count("data-theme-toggle") == 1
        assert html.count("assets/theme.js?v=") == 1
        assert html.count("assets/catalog-ui.js?v=") == 1
        assert head.group(1).find("data-theme-init") < head.group(1).find('rel="stylesheet"')
        assert 'type="button" data-theme-toggle aria-pressed="false"' in html
        assert 'aria-label="Dark theme"' in html
        assert f'src="{asset_prefix}assets/theme.js?v=' in html
        assert f'src="{asset_prefix}assets/catalog-ui.js?v=' in html
        assert "assets/catalog-ui.js?v=" in head.group(1)
        assert '<main id="main-content" tabindex="-1">' in html

    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    init_script = re.search(r"<script data-theme-init>(.*?)</script>", index_html, re.S)
    assert init_script
    assert "etherfi-data-catalog-theme" in init_script.group(1)
    assert '(prefers-color-scheme: dark)' in init_script.group(1)
    assert 'root.setAttribute("data-theme", theme)' in init_script.group(1)
    assert 'root.setAttribute("data-js", "")' in init_script.group(1)
    assert 'root.setAttribute("data-theme-ready", "")' not in init_script.group(1)
    theme_js = (tmp_path / "assets" / "theme.js").read_text(encoding="utf-8")
    assert 'root.setAttribute("data-theme-ready", "")' in theme_js

    css = (tmp_path / "assets" / "styles.css").read_text(encoding="utf-8")
    dark_tokens = re.search(r'html\[data-theme="dark"\] \{(.*?)\n\}', css, re.S)
    assert dark_tokens
    assert "--focus-ring: #147a4c;" in css
    assert ".dataset-glance-card .inline-info-hint:focus-visible {" in css
    assert css.count("outline: 3px solid var(--focus-ring);") >= 3
    for token in [
        "bg",
        "surface",
        "surface-muted",
        "border",
        "text",
        "muted",
        "accent",
        "accent-deep",
        "accent-soft",
        "ink-soft",
        "canvas",
        "surface-raised",
        "surface-glass",
        "border-subtle",
        "border-strong",
        "green-wash",
        "blue-wash",
        "amber-wash",
        "danger-wash",
        "shadow-xs",
        "shadow-sm",
        "shadow-md",
    ]:
        assert f"--{token}:" in dark_tokens.group(1)
    assert "color-scheme: dark;" in dark_tokens.group(1)
    assert 'html[data-theme="dark"] .site-header' in css
    assert 'html[data-theme="dark"] .catalog-search input' in css
    assert 'html[data-theme="dark"] .schema-table-toolbar' in css
    assert 'html[data-theme="dark"] .code-snippet' in css
    assert 'html[data-theme="dark"] .site-footer' in css
    assert ".freshness-summary" not in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_theme_scripts_handle_preferences_persistence_and_storage_failures(tmp_path):
    node = shutil.which("node")
    if node is None:
        return

    build_site(output_dir=tmp_path)
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    init_source = re.search(r"<script data-theme-init>(.*?)</script>", index_html, re.S)
    assert init_source
    theme_source = (tmp_path / "assets" / "theme.js").read_text(encoding="utf-8")

    script = """
const vm = require("vm");
const initSource = __INIT_SOURCE__;
const themeSource = __THEME_SOURCE__;

function fakeElement(initial) {
  return {
    attrs: Object.assign({}, initial || {}),
    listeners: {},
    setAttribute(name, value) { this.attrs[name] = String(value); },
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; },
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
}

function runInit(options) {
  const root = fakeElement();
  const browserWindow = {
    matchMedia() {
      if (options.mediaThrows) throw new Error("media unavailable");
      return { matches: options.systemDark };
    },
  };
  Object.defineProperty(browserWindow, "localStorage", {
    get() {
      if (options.storageThrows) throw new Error("storage unavailable");
      return { getItem() { return options.saved; } };
    },
  });
  vm.runInNewContext(initSource, { document: { documentElement: root }, window: browserWindow });
  return root.attrs["data-theme"];
}

const root = fakeElement({ "data-theme": "light" });
const toggle = fakeElement({ "aria-pressed": "false", "aria-label": "Dark theme" });
const themeColor = fakeElement({ content: "#f2f0e8" });
const windowListeners = {};
let attemptedStoredTheme = null;
const browserWindow = {
  localStorage: {
    getItem() { return null; },
    setItem(key, value) {
      attemptedStoredTheme = value;
      throw new Error("storage write blocked");
    },
  },
  matchMedia() { return { matches: false, addEventListener() {} }; },
  addEventListener(name, callback) { windowListeners[name] = callback; },
};
const documentObject = {
  documentElement: root,
  querySelector(selector) {
    if (selector === "[data-theme-toggle]") return toggle;
    if (selector === "[data-theme-color]") return themeColor;
    return null;
  },
};
vm.runInNewContext(themeSource, { document: documentObject, window: browserWindow });
const initialControl = {
  theme: root.attrs["data-theme"],
  pressed: toggle.attrs["aria-pressed"],
  label: toggle.attrs["aria-label"],
};
toggle.listeners.click();
const clickedControl = {
  theme: root.attrs["data-theme"],
  pressed: toggle.attrs["aria-pressed"],
  label: toggle.attrs["aria-label"],
  title: toggle.attrs.title,
  themeColor: themeColor.attrs.content,
  attemptedStoredTheme,
};
windowListeners.storage({ key: "etherfi-data-catalog-theme", newValue: "light" });

console.log(JSON.stringify({
  init: {
    savedDark: runInit({ saved: "dark", systemDark: false }),
    savedLight: runInit({ saved: "light", systemDark: true }),
    systemDark: runInit({ saved: null, systemDark: true }),
    storageFailure: runInit({ saved: null, systemDark: true, storageThrows: true }),
    mediaFailure: runInit({ saved: null, systemDark: false, mediaThrows: true }),
  },
  initialControl,
  clickedControl,
  storageTheme: root.attrs["data-theme"],
}));
""".replace("__INIT_SOURCE__", json.dumps(init_source.group(1))).replace(
        "__THEME_SOURCE__", json.dumps(theme_source)
    )
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior["init"] == {
        "savedDark": "dark",
        "savedLight": "light",
        "systemDark": "dark",
        "storageFailure": "dark",
        "mediaFailure": "light",
    }
    assert behavior["initialControl"] == {
        "theme": "light",
        "pressed": "false",
        "label": "Dark theme",
    }
    assert behavior["clickedControl"] == {
        "theme": "dark",
        "pressed": "true",
        "label": "Dark theme",
        "title": "Switch to light theme",
        "themeColor": "#0b110d",
        "attemptedStoredTheme": "dark",
    }
    assert behavior["storageTheme"] == "light"


def test_studio_rehomes_single_theme_control_and_skips_catalog_search():
    node = shutil.which("node")
    if node is None:
        return

    root_dir = Path(__file__).resolve().parents[1]
    theme_source = (root_dir / "website" / "assets" / "theme.js").read_text(
        encoding="utf-8"
    )
    script = r"""
const vm = require("vm");
const globalSearch = require("./website/assets/global-search.js");
const themeSource = __THEME_SOURCE__;

function fakeElement(initial) {
  return {
    attrs: Object.assign({}, initial || {}),
    listeners: {},
    setAttribute(name, value) { this.attrs[name] = String(value); },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attrs, name)
        ? this.attrs[name]
        : null;
    },
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
}

const root = fakeElement({ "data-theme": "light" });
const toggle = fakeElement({ "aria-pressed": "false" });
const themeColor = fakeElement({ content: "#f2f0e8" });
const slot = {
  children: [],
  appendChild(child) { this.children.push(child); },
};
const documentObject = {
  documentElement: root,
  querySelector(selector) {
    if (selector === "[data-theme-toggle]") return toggle;
    if (selector === "[data-studio-theme-slot]") return slot;
    if (selector === "[data-theme-color]") return themeColor;
    return null;
  },
};
const browserWindow = {
  localStorage: { getItem() { return null; }, setItem() {} },
  matchMedia() { return { matches: false, addEventListener() {} }; },
  addEventListener() {},
};
vm.runInNewContext(themeSource, {
  document: documentObject,
  window: browserWindow,
});

let catalogQueries = 0;
const studioScope = {
  body: {
    classList: {
      contains(name) { return name === "studio-page"; },
    },
  },
  querySelector() {
    catalogQueries += 1;
    return null;
  },
};
const searchMount = globalSearch.mount(studioScope, {
  ETHERFI_CATALOG_INDEX: [],
});

console.log(JSON.stringify({
  movedCount: slot.children.length,
  movedOriginal: slot.children[0] === toggle,
  pressed: toggle.attrs["aria-pressed"],
  searchMount,
  catalogQueries,
}));
""".replace("__THEME_SOURCE__", json.dumps(theme_source))
    result = subprocess.run(
        [node, "-e", script],
        cwd=root_dir,
        check=True,
        capture_output=True,
        text=True,
    )

    behavior = json.loads(result.stdout)
    assert behavior == {
        "movedCount": 1,
        "movedOriginal": True,
        "pressed": "false",
        "searchMount": None,
        "catalogQueries": 0,
    }


def test_build_website_generates_polished_mcp_page_from_current_tools(tmp_path):
    build_site(output_dir=tmp_path)

    mcp_page = (tmp_path / "mcp.html").read_text(encoding="utf-8")
    mcp_js = (tmp_path / "assets" / "mcp.js").read_text(encoding="utf-8")
    assert 'data-mcp-page' in mcp_page
    assert "<h1>ether.fi Catalog MCP</h1>" in mcp_page
    assert "Connect AI agents to ether.fi dataset metadata, dashboards, freshness context, and query-planning guidance." in mcp_page

    assert "What it does" in mcp_page
    assert "mcp-plain-list" in mcp_page
    assert (
        'Find the right ether.fi <a href="datasets.html">dataset</a> or '
        '<a href="dashboards.html">dashboard</a>.'
        in mcp_page
    )
    assert (
        'Check <a href="freshness.html">freshness context</a> and caveats before '
        "reporting or querying."
        in mcp_page
    )
    assert "Plan safer DuneSQL with documented caveats and table semantics." in mcp_page
    assert "Use Dune MCP for execution, saved queries, charts, and dashboards." in mcp_page
    assert "Search the catalog and understand what each table represents." not in mcp_page
    assert "See whether datasets are fresh, stale, or missing freshness data." not in mcp_page

    assert "Recommended setup" in mcp_page
    assert (
        '<strong>Before you install:</strong> <code>uvx</code> is required. '
        '<code>DUNE_API_KEY</code> is needed only for live Dune-backed tools.'
        in mcp_page
    )
    assert "mcp-preview-panel" not in mcp_page
    assert "mcp-capability-grid" not in mcp_page
    assert "mcp-capability-card" not in mcp_page
    assert "Client configs" in mcp_page
    assert "uvx --from git+https://github.com/henrystats/etherfi-data-catalog.git etherfi-catalog-mcp" in mcp_page
    assert 'data-snippet-copy' in mcp_page
    assert mcp_page.count('data-copy-announcer role="status" aria-live="polite" aria-atomic="true"') == 6
    assert '<pre tabindex="0" role="region" aria-label="Install command code snippet">' in mcp_page
    assert '<pre tabindex="0" role="region" aria-label="Codex TOML code snippet">' in mcp_page
    assert '<pre tabindex="0" role="region" aria-label="Claude JSON code snippet">' in mcp_page
    assert "Install Dune MCP separately using Dune&rsquo;s official instructions." in mcp_page
    assert "Use ether.fi Catalog MCP for dataset semantics" in mcp_page
    assert "Use Dune MCP for execution, saved queries, charts, and dashboards." in mcp_page
    assert "<li>Use local stdio via <code>uvx</code>. Keep real credentials in private local config.</li>" in mcp_page
    assert "Each user should use their own Dune API key locally." not in mcp_page
    assert "Do not put a shared team key in the repo." in mcp_page

    assert "Codex config" in mcp_page
    assert "Claude Desktop config" in mcp_page
    assert "[mcp_servers.etherfi-catalog]" in mcp_page
    assert "&quot;mcpServers&quot;" in mcp_page
    assert 'command = &quot;uvx&quot;' in mcp_page
    assert "enabled = true" in mcp_page
    assert "startup_timeout_sec = 60" in mcp_page
    assert "tool_timeout_sec = 120" in mcp_page
    assert "<li>Use placeholders in examples. Put real credentials only in private local config.</li>" in mcp_page
    assert "/Users/&lt;user&gt;/.codex/config.toml" in mcp_page
    assert "After editing MCP config, fully restart or reload the client." in mcp_page

    assert "How to use with Dune MCP" in mcp_page
    assert "Ask ether.fi Catalog MCP which dataset, dashboard, or freshness context applies." in mcp_page
    assert "Keep caveats and freshness notes in query descriptions." in mcp_page

    assert "Test it works" in mcp_page
    assert "Metadata-only test" in mcp_page
    assert "Search datasets for &quot;cash events&quot;" in mcp_page
    assert "Dashboard test" in mcp_page
    assert "Search dashboards for &quot;cash&quot;" in mcp_page
    assert "Planning test" in mcp_page
    assert "weekly USDC cashback volume" in mcp_page
    assert "Live Dune-backed tools" in mcp_page
    assert "may consume Dune credits" in mcp_page

    assert "Troubleshooting" in mcp_page
    assert "confirm <code>uvx</code> works" in mcp_page
    assert "restart Codex" in mcp_page
    assert "the key may not be reaching the MCP runtime" in mcp_page
    assert "Bad CPU type in executable" in mcp_page
    assert "Advanced deployment" not in mcp_page
    assert "local <code>uvx</code> setup is the recommended teammate install path" not in mcp_page

    assert "Tool groups" not in mcp_page
    assert "Available tools are read from the current MCP server" not in mcp_page
    assert "Catalog discovery" not in mcp_page
    assert "Cash live tools" not in mcp_page
    assert "Protocol live tools" not in mcp_page
    assert "Price coverage tools" not in mcp_page
    assert 'data-mcp-tool="' not in mcp_page
    assert ".venv/bin/python -m etherfi_catalog.server" not in mcp_page
    assert 'src="assets/mcp.js?v=' in mcp_page
    assert "data-copy-announcer" in mcp_js
    assert 'dataset.mcpMounted = "true"' in mcp_js
    assert 'button.dataset.copyDefaultLabel || "Copy"' in mcp_js
    assert 'announcer.textContent = announce ? label : "";' in mcp_js
    assert "DUNE_API_KEY" in mcp_page
    assert "Best practices" not in mcp_page

    mcp_nav = re.search(
        r'<nav class="detail-section-nav" aria-label="MCP guide sections">(.*?)</nav>',
        mcp_page,
        re.S,
    )
    assert mcp_nav
    nav_positions = [
        mcp_nav.group(1).find('href="#what-it-does"'),
        mcp_nav.group(1).find('href="#recommended-setup"'),
        mcp_nav.group(1).find('href="#client-configs"'),
        mcp_nav.group(1).find('href="#test-it-works"'),
        mcp_nav.group(1).find('href="#dune-workflow"'),
        mcp_nav.group(1).find('href="#live-dune-tools"'),
        mcp_nav.group(1).find('href="#troubleshooting"'),
    ]
    section_positions = [
        mcp_page.find('id="what-it-does"'),
        mcp_page.find('id="recommended-setup"'),
        mcp_page.find('id="client-configs"'),
        mcp_page.find('id="test-it-works"'),
        mcp_page.find('id="dune-workflow"'),
        mcp_page.find('id="live-dune-tools"'),
        mcp_page.find('id="troubleshooting"'),
    ]
    assert all(position >= 0 for position in nav_positions)
    assert nav_positions == sorted(nav_positions)
    assert section_positions == sorted(section_positions)

    assert (tmp_path / "datasets.html").exists()
    assert (tmp_path / "dashboards.html").exists()
    assert (tmp_path / "freshness.html").exists()
    assert (tmp_path / "assets" / "mcp.js").exists()


def test_mcp_test_prompts_are_copyable_without_hiding_the_prompt_text(tmp_path):
    build_site(output_dir=tmp_path)

    mcp_page = (tmp_path / "mcp.html").read_text(encoding="utf-8")
    prompt_cards = re.findall(
        r'<article class="mcp-prompt-card">(.*?)</article>',
        mcp_page,
        re.S,
    )

    assert len(prompt_cards) == 3
    for card in prompt_cards:
        group_match = re.match(r"<span>(.*?)</span>", card, re.S)
        prompt_match = re.search(r"<p>(.*?)</p>", card, re.S)
        copy_text_match = re.search(r'data-copy-text="(.*?)"', card, re.S)
        assert group_match
        assert prompt_match
        assert copy_text_match
        assert copy_text_match.group(1) == prompt_match.group(1)
        assert " hidden" not in prompt_match.group(0)
        assert card.count("data-snippet-copy") == 1
        assert 'data-copy-default-label="Copy prompt"' in card
        assert (
            f'aria-label="Copy {group_match.group(1)} prompt"'
            in card
        )
        assert '<span class="copy-value-label" data-copy-feedback>Copy prompt</span>' in card
        assert (
            'data-copy-announcer role="status" aria-live="polite" '
            'aria-atomic="true"'
            in card
        )


def test_build_website_generates_dataset_index_and_detail_pages(tmp_path):
    freshness_path = tmp_path / "dataset_freshness.fixture.yaml"
    freshness_path.write_text(
        "etherfi_protocol_token_holders:\n"
        "  last_updated: '2026-06-22T20:00:00Z'\n"
        "  query_id: 6213381\n",
        encoding="utf-8",
    )
    build_site(
        output_dir=tmp_path,
        freshness_registry_path=freshness_path,
        now=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )

    dataset_index = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    css = (tmp_path / "assets" / "styles.css").read_text(encoding="utf-8")
    assert (
        'class="dataset-category-panel" aria-labelledby="dataset-categories-title"'
        in dataset_index
    )
    assert 'data-datasets-page' in dataset_index
    assert '<header class="catalog-index-header' not in dataset_index
    assert '<p class="eyebrow">Dataset registry</p>' not in dataset_index
    assert '<h1 id="datasets-page-title" class="visually-hidden">Datasets</h1>' in dataset_index
    assert "Find trusted ether.fi tables by product area" not in dataset_index
    assert "browsable datasets across" not in dataset_index
    assert (
        '<h2 id="dataset-categories-title" class="dataset-category-panel-header">'
        "Dataset categories</h2>"
        in dataset_index
    )
    assert "<strong>Catalog</strong>" not in dataset_index
    assert 'aria-labelledby="datasets-page-title"' in dataset_index
    assert 'data-dataset-nav="overview"' in dataset_index
    assert 'data-dataset-nav="activity"' in dataset_index
    assert 'data-dataset-nav="etherfi_protocol"' in dataset_index
    assert 'data-dataset-nav="prices"' in dataset_index
    assert 'data-dataset-nav="metadata"' in dataset_index
    assert 'data-dataset-nav="lrt_restaking"' in dataset_index
    overview_nav = re.search(
        r'<button[^>]*data-dataset-nav="overview"[^>]*>(.*?)</button>',
        dataset_index,
        re.S,
    )
    assert overview_nav
    assert "<strong>4</strong>" in overview_nav.group(1)
    for category, section_id in [
        ("overview", "overview"),
        ("activity", "activity"),
        ("etherfi_protocol", "etherfi-protocol"),
        ("prices", "prices"),
        ("metadata", "metadata"),
        ("lrt_restaking", "lrt-restaking"),
    ]:
        nav_button = re.search(
            rf'<button[^>]*data-dataset-nav="{category}"[^>]*>',
            dataset_index,
        )
        assert nav_button
        assert f'aria-controls="dataset-view-{section_id}"' in nav_button.group(0)
        assert f'id="dataset-view-{section_id}"' in dataset_index
        if category != "overview":
            section = re.search(
                rf'<section id="dataset-view-{section_id}".*?</section>',
                dataset_index,
                re.S,
            )
            assert section
            count_match = re.search(
                r'<span class="dataset-view-count">(\d+) datasets?</span>',
                section.group(0),
            )
            assert count_match
            count = int(count_match.group(1))
            assert (
                f"<p>{category_description(category, count)}</p>"
                in section.group(0)
            )
    assert dataset_index.find("<span>Overview</span>") < dataset_index.find("<span>Activity</span>")
    assert dataset_index.find("<span>Activity</span>") < dataset_index.find("<span>Ether.fi Protocol</span>")
    assert dataset_index.find("<span>Ether.fi Protocol</span>") < dataset_index.find("<span>Prices</span>")
    assert dataset_index.find("<span>Prices</span>") < dataset_index.find("<span>Metadata</span>")
    assert dataset_index.find("<span>Metadata</span>") < dataset_index.find("<span>LRT / Restaking</span>")
    assert '<h1 id="dataset-heading-overview">Dataset catalog</h1>' not in dataset_index
    assert "Search or browse ether.fi materialized views, then open a detail page" not in dataset_index
    assert "This page documents ether.fi materialized views and supporting datasets." not in dataset_index
    assert "dataset-overview-routes" not in dataset_index
    assert "Search spans schema fields, table names, source query IDs, and related catalog metadata." not in dataset_index
    assert "dataset-summary-grid" not in dataset_index
    assert "Total datasets" not in dataset_index
    assert "Categories" not in dataset_index
    assert "Query ready" not in dataset_index
    assert "Source queries documented" not in dataset_index
    assert 'class="dataset-overview-view dataset-featured-view"' in dataset_index
    assert '<h2 id="dataset-heading-overview">Featured datasets</h2>' in dataset_index
    assert "Our most used datasets." in dataset_index
    assert "dataset-featured-section" not in dataset_index
    assert "Ether.fi Assets Under Management" in dataset_index
    assert "Ether.fi Protocol Token TVL" in dataset_index
    assert "Ether.fi Cash Events" in dataset_index
    assert "Tokens Traits" in dataset_index
    overview_end = dataset_index.find('<section id="dataset-view-activity"')
    assert overview_end > 0
    overview_html = dataset_index[:overview_end]
    assert overview_html.count('class="dataset-browser-card featured"') == 4
    assert 'href="datasets/tokens_traits.html"' in overview_html
    assert dataset_index.find('class="catalog-toolbar dataset-browser-toolbar"') < dataset_index.find('id="dataset-view-overview"')
    assert dataset_index.find('id="dataset-view-overview"') < overview_end
    assert ".dataset-featured-view::before" in css
    assert "background: linear-gradient(90deg, var(--lime), var(--accent), var(--cobalt));" in css
    assert ".dataset-featured-view .dataset-view-heading" in css
    assert 'html[data-theme="dark"] .dataset-overview-view.dataset-featured-view' in css
    assert "Browse categories on the left to explore the full catalog." not in dataset_index
    assert 'id="dataset-search"' in dataset_index
    assert 'data-catalog-search aria-keyshortcuts="/"' in dataset_index
    assert 'aria-describedby="dataset-count"' in dataset_index
    assert 'data-search-clear aria-label="Clear dataset search"' in dataset_index
    assert 'id="dataset-count"' in dataset_index
    assert (
        'id="dataset-count" class="visually-hidden" role="status" '
        'aria-live="polite" aria-atomic="true"'
        in dataset_index
    )
    assert ">Featured datasets shown</span>" in dataset_index
    assert "featured &middot;" not in dataset_index
    assert " total</span>" not in dataset_index
    assert 'id="dataset-empty-state"' in dataset_index
    assert 'data-dataset-category-section data-category="activity"' in dataset_index
    assert 'data-category="activity" aria-labelledby="dataset-heading-activity" data-default-hidden' in dataset_index
    assert '<noscript><p class="no-js-note">' in dataset_index
    assert 'data-dataset-card' in dataset_index
    assert 'data-search=' in dataset_index
    assert 'data-status=' in dataset_index
    assert 'href="datasets/protocol_token_holders.html"' in dataset_index
    assert "Ether.fi Protocol Token Holders" in dataset_index
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
    assert "Ether.fi Protocol Token Holders" in holder_card_html
    assert "Direct user/wallet holders of ether.fi protocol tokens by address" in holder_card_html
    assert re.search(
        r'<span class="dataset-card-status stale">Stale \d+(?:m|hr|d)</span>',
        holder_card_html,
    )
    assert '<dl class="dataset-card-meta"' not in holder_card_html
    assert '<dt>Refresh interval</dt>' not in holder_card_html
    assert '<dt>Last refreshed</dt>' not in holder_card_html
    assert "registry-meta-row" not in holder_card_html
    assert 'href="https://dune.com/queries/6213381"' in holder_card_html
    assert (
        'aria-label="Open source Dune query for Ether.fi Protocol Token Holders"'
        in holder_card_html
    )
    assert 'href="datasets/protocol_token_holders.html"' in holder_card_html
    assert (
        'aria-label="View Ether.fi Protocol Token Holders dataset details"'
        in holder_card_html
    )
    assert '<span class="dataset-category-chip etherfi-protocol">Ether.fi Protocol</span>' in holder_card_html
    assert '<code class="dataset-card-table"' not in holder_card_html
    assert "dune.ether_fi.result_etherfi_protocol_token_holders" not in holder_card_html
    assert '<h3 class="dataset-card-heading">' in holder_card_html
    assert '<p class="dataset-card-description">' in holder_card_html
    assert '<div class="dataset-card-side">' in holder_card_html
    assert "dataset-card-relationships" not in holder_card_html
    assert "related dataset" not in holder_card_html
    assert "linked dataset" not in holder_card_html
    assert "linked dashboard" not in holder_card_html
    assert 'title="Completeness: complete">Full coverage</span>' in holder_card_html
    assert '<div class="dataset-card-actions">' in holder_card_html
    assert holder_card_html.find('class="dataset-category-chip etherfi-protocol"') < holder_card_html.find('class="dataset-card-status stale"')
    assert holder_card_html.find('class="dataset-card-status stale"') < holder_card_html.find('class="dataset-card-heading"')
    assert re.search(
        r"\.dataset-browser-list\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\);",
        css,
        re.S,
    )
    for status in ["fresh", "delayed", "stale", "unknown"]:
        assert f".dataset-card-status.{status}" in css
        assert f'html[data-theme="dark"] .dataset-card-status.{status}' in css
    assert re.search(
        r"\.dataset-card-description\s*\{[^}]*-webkit-line-clamp:\s*2;",
        css,
        re.S,
    )
    assert ".dataset-card-meta" not in css
    assert ".dataset-browser-card::before" in css
    assert '.dataset-browser-card[data-category="activity"]::before' in css
    assert '.dataset-browser-card[data-category="prices"]::before' in css
    assert '.dataset-browser-card[data-category="metadata"]::before' in css
    assert '.dataset-browser-card[data-category="lrt_restaking"]::before' in css
    assert ".dashboard-browser-card::before" in css
    assert ".dataset-featured-view::before," in css
    assert ".dataset-category-view::before" in css
    for category in ["activity", "prices", "metadata", "lrt_restaking"]:
        assert f'.dataset-category-view[data-category="{category}"]' in css
    assert "Details" in holder_card_html
    assert "dataset-card-kicker" not in dataset_index
    assert "dataset-table-inline" not in dataset_index
    assert 'class="meta-chip subtle"' not in dataset_index
    assert "<span>Related</span>" not in dataset_index
    assert "<span>Category</span>" not in holder_card_html
    assert "related datasets</strong>" not in holder_card_html
    assert "dashboards</strong>" not in holder_card_html
    assert "dune.ether_fi.result_etherfi_protocol_token_holders" in dataset_index
    assert "etherfi_protocol_token_holders" in dataset_index
    assert "dataset-card-relationships" not in dataset_index
    assert "High coverage" in dataset_index
    defi_holder_card = re.search(
        r'<article class="dataset-browser-card"[^>]*data-source-query-id="6221932"[^>]*>(.*?)</article>',
        dataset_index,
        re.S,
    )
    assert defi_holder_card
    assert "Partial coverage" in defi_holder_card.group(1)
    assert 'title="Completeness: partial"' in defi_holder_card.group(1)

    holder_page = (tmp_path / "datasets" / "protocol_token_holders.html").read_text(encoding="utf-8")
    assert "../assets/styles.css" in holder_page
    assert '../assets/styles.css?v=' in holder_page
    assert 'class="nav-link active" href="../datasets.html" aria-current="page"' in holder_page
    assert "Back to datasets" in holder_page
    assert (
        '<a class="dataset-back-link" '
        'href="../datasets.html#dataset-view-etherfi-protocol" '
        'aria-label="Back to Ether.fi Protocol datasets">Back to datasets</a>'
        in holder_page
    )
    assert "At a glance" not in holder_page
    assert "dataset-detail-hero-meta" in holder_page
    holder_hero = re.search(
        r'<header class="dataset-detail-header">(.*?)</header>',
        holder_page,
        re.S,
    )
    assert holder_hero
    holder_hero_html = holder_hero.group(1)
    assert (
        '<div class="dataset-detail-hero-glance" role="group" '
        'aria-label="Dataset metadata">'
        in holder_hero_html
    )
    assert "Ether.fi Protocol Token Holders" in holder_hero_html
    assert (
        '<a class="dune-action detail-dune-action" href="https://dune.com/queries/6213381" '
        'aria-label="Open the source query for Ether.fi Protocol Token Holders on Dune">'
        "Open in Dune</a>"
        in holder_hero_html
    )
    holder_glance = re.search(
        r'<div class="dataset-detail-hero-glance" role="group" '
        r'aria-label="Dataset metadata">(.*)</div>$',
        holder_hero_html,
        re.S,
    )
    assert holder_glance
    holder_glance_html = holder_glance.group(1)
    assert "Full table name" in holder_glance_html
    assert 'class="dataset-glance-card full-table-name copyable-table-name"' in holder_glance_html
    assert 'class="dataset-glance-card glance-grain"' in holder_glance_html
    assert 'class="table-pill table-pill-block"' in holder_glance_html
    assert "dune.ether_fi.result_etherfi_protocol_token_holders" in holder_glance_html
    assert (
        'data-copy-text="dune.ether_fi.result_etherfi_protocol_token_holders"'
        in holder_glance_html
    )
    assert 'aria-label="Copy full table name"' in holder_glance_html
    assert (
        'data-copy-announcer role="status" aria-live="polite" aria-atomic="true"'
        in holder_glance_html
    )
    assert 'src="../assets/dataset-detail.js?v=' in holder_page
    assert "schema-table-toolbar" in holder_page
    assert '<span class="schema-scroll-hint" aria-hidden="true">Scroll for type + description &rarr;</span>' in holder_page
    assert (
        'class="schema-table-wrap" data-schema-table role="region" '
        'aria-label="Dataset schema" tabindex="0"'
        in holder_page
    )
    assert "<h3>Caveats</h3>" not in holder_page
    assert holder_glance_html.count("<span>Live query</span>") == 1
    assert 'class="dataset-glance-card copyable-table-name live-query-card"' in holder_glance_html
    assert "query_6815122" in holder_glance_html
    assert 'data-copy-text="query_6815122"' in holder_glance_html
    assert 'aria-label="Copy live query table name"' in holder_glance_html
    assert (
        '<button class="inline-info-hint" type="button" aria-expanded="false" '
        in holder_glance_html
    )
    assert 'aria-label="About live queries"' in holder_glance_html
    assert 'aria-describedby="live-query-hint-description"' in holder_glance_html
    assert (
        '<span class="inline-info-tooltip" id="live-query-hint-description" '
        'role="tooltip">Live queries are saved-query outputs'
        in holder_glance_html
    )
    assert 'class="inline-info-hint" type="button" title=' not in holder_glance_html
    assert "Live query table" not in holder_page
    assert "Live query ID" not in holder_page
    assert ".dataset-glance-grid:not(:has(.live-query-card)) .dataset-glance-card.full-table-name" in css
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
    assert "What this dataset represents" not in holder_page
    assert "Use this dataset when" not in holder_page
    assert "Choose another dataset when" not in holder_page
    assert "Direct user/wallet holders of ether.fi protocol tokens by address" in holder_page
    assert "one row per address per token per snapshot date" in holder_page
    assert "Schema" in holder_page
    assert 'class="detail-section-nav" aria-label="On this page"' not in holder_page
    assert (
        'class="detail-tab-interface" data-detail-tabs data-default-tab="schema" '
        'data-detail-tabs-label="Dataset detail sections"'
        in holder_page
    )
    assert (
        'class="detail-tab-list" data-detail-tab-list hidden'
        in holder_page
    )
    assert (
        'data-detail-tab="schema" data-detail-tab-controls="schema"'
        in holder_page
    )
    assert (
        'data-detail-tab="about" data-detail-tab-controls="about"'
        in holder_page
    )
    assert (
        'data-detail-tab="about" data-detail-tab-controls="about">'
        "Methodology and Notes</button>"
        in holder_page
    )
    assert 'data-detail-tab-controls="about">About</button>' not in holder_page
    assert (
        'data-detail-tab="related-resources" '
        'data-detail-tab-controls="related-resources"'
        in holder_page
    )
    assert 'id="about" class="detail-tab-panel detail-panel"' in holder_page
    assert 'id="schema" class="detail-tab-panel detail-panel"' in holder_page
    methodology_panel = re.search(
        r'<section id="about" class="detail-tab-panel detail-panel" '
        r'data-detail-tab-panel="about" '
        r'data-detail-tab-labelledby="dataset-detail-tab-about" '
        r'data-empty-tab-panel="true"></section>',
        holder_page,
    )
    assert methodology_panel
    assert 'id="about-table"' not in holder_page
    assert 'id="dataset-schema"' in holder_page
    assert 'id="dataset-caveats"' not in holder_page
    assert 'id="related-resources"' in holder_page
    for panel_id in ["about", "schema", "related-resources"]:
        panel_tag = re.search(rf'<section id="{panel_id}"[^>]*>', holder_page)
        assert panel_tag
        assert " hidden" not in panel_tag.group(0)
    assert holder_page.find('id="about"') < holder_page.find('id="dataset-schema"')
    assert holder_page.find('id="dataset-schema"') < holder_page.find('id="related-resources"')
    assert '<th scope="col">Column</th><th scope="col">Type</th><th scope="col">Description</th>' in holder_page

    addresses_page = (tmp_path / "datasets" / "etherfi_addresses.html").read_text(
        encoding="utf-8"
    )
    assert 'data-empty-tab-panel="true"></section>' in addresses_page
    assert 'id="dataset-caveats"' not in addresses_page
    assert '<th scope="row"><code>address</code></th><td>varbinary</td>' in holder_page
    assert '<td class="schema-description">holder wallet or contract address</td>' in holder_page
    assert "Related resources" in holder_page
    assert "<h2>Related resources</h2>" not in holder_page
    assert 'class="related-resource-list"' in holder_page
    assert 'class="related-resource"' in holder_page

    holder_with_defi_page = (
        tmp_path / "datasets" / "protocol_token_holders_with_defi.html"
    ).read_text(encoding="utf-8")
    assert "Protocol Token Holders with DeFi" in holder_with_defi_page
    assert '<span class="dataset-coverage-chip partial" title="Completeness: partial">Partial coverage</span>' in holder_with_defi_page
    assert "Freshness &amp; Refresh Interval" in holder_with_defi_page
    assert "Freshness &amp; Interval" not in holder_with_defi_page
    assert "Every 4h" in holder_with_defi_page
    assert "daily" not in holder_with_defi_page
    assert 'href="../dashboards/etherfi_overview.html"' in holder_page
    assert "What this table contains" not in holder_page
    assert "Important columns" not in holder_page
    assert "Query notes" not in holder_page
    assert "Query notes / caveats" not in holder_page
    assert "<h3>Caveats</h3>" not in holder_page
    assert "This table does not include broader routed exposure" not in holder_page
    assert "Use when" not in holder_page
    assert "Do not use when" not in holder_page
    assert "Example prompts" not in holder_page
    assert "Who are the top direct holders of eETH?" not in holder_page

    transfers_page = (tmp_path / "datasets" / "addresses_transfers.html").read_text(
        encoding="utf-8"
    )
    assert "At a glance" not in transfers_page
    transfers_hero = re.search(
        r'<header class="dataset-detail-header">(.*?)</header>',
        transfers_page,
        re.S,
    )
    assert transfers_hero
    transfers_glance = re.search(
        r'<div class="dataset-detail-hero-glance" role="group" '
        r'aria-label="Dataset metadata">(.*)</div>$',
        transfers_hero.group(1),
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
    assert "<h2>Related resources</h2>" not in parent_page
    assert "<h2>Supporting sub-tables</h2>" in parent_page
    assert parent_page.find("<h2>Related datasets</h2>") < parent_page.find(
        "<h2>Supporting sub-tables</h2>"
    )
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
    assert "Related resources" in logs_page
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


def test_cash_addresses_dataset_page_renders_public_registry_metadata(tmp_path):
    build_site(output_dir=tmp_path)

    dataset_index = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    assert "Ether.fi Cash Addresses" in dataset_index
    assert 'href="datasets/etherfi_cash_addresses.html"' in dataset_index
    assert 'data-source-query-id="7854862"' in dataset_index

    page = (tmp_path / "datasets" / "etherfi_cash_addresses.html").read_text(
        encoding="utf-8"
    )
    assert "Ether.fi Cash Addresses" in page
    assert "dune.ether_fi.result_etherfi_cash_addresses" in page
    assert "https://dune.com/queries/7854862" in page
    assert "one row per blockchain and Cash safe address" in page
    assert "Every 4h" in page
    assert "last_updated" in page
    assert '<th scope="row"><code>blockchain</code></th><td>varchar</td>' in page
    assert '<td class="schema-description">Chain where the Cash safe exists.</td>' in page
    assert '<th scope="row"><code>address</code></th><td>varbinary</td>' in page
    assert '<td class="schema-description">Cash safe address.</td>' in page
    assert 'href="../datasets/etherfi_cash_events.html"' in page
    assert 'href="../datasets/etherfi_assets_under_management.html"' in page
    assert 'href="../dashboards/etherfi_cash.html"' in page


def test_schema_search_text_normalizes_only_case_and_whitespace():
    assert normalize_schema_search_text(
        "  User_Safe ",
        "VARBINARY",
        "Owner's\n wallet   or contract address",
    ) == "user_safe varbinary owner's wallet or contract address"
    assert normalize_schema_search_text("", None, "Already-normalized") == "already-normalized"


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
    assert '<div class="schema-filter-controls" data-schema-filter hidden>' in mapping_page
    assert (
        '<label class="schema-filter-label" for="schema-column-filter">Filter columns</label>'
        in mapping_page
    )
    assert (
        '<input class="schema-filter-input" id="schema-column-filter" type="search" '
        'data-schema-filter-input placeholder="Name, type, or description"'
        in mapping_page
    )
    assert (
        '<button class="schema-filter-clear" type="button" '
        'data-schema-filter-clear hidden>Clear</button>'
        in mapping_page
    )
    assert (
        'class="schema-filter-count" data-schema-filter-count role="status" '
        'aria-live="polite" aria-atomic="true">5 columns</strong>'
        in mapping_page
    )
    assert '<p class="schema-filter-empty" data-schema-filter-empty hidden>' in mapping_page
    assert (
        'data-schema-search="user_safe varbinary schema safe address description"'
        in mapping_page
    )
    assert (
        'data-schema-search="token_balance_usd double usd value of the token balance"'
        in mapping_page
    )
    assert '<th scope="col">Column</th><th scope="col">Type</th><th scope="col">Description</th>' in mapping_page
    assert '<th scope="row"><code>user_safe</code></th><td>varbinary</td>' in mapping_page
    assert (
        '<th scope="row"><code>this_is_a_very_long_schema_column_name_that_should_wrap_inside_the_column_cell_without_breaking_layout</code></th><td>varchar</td>'
        in mapping_page
    )
    assert '<td class="schema-description">Schema safe address description</td>' in mapping_page
    assert "Important fallback should not win" not in mapping_page
    assert '<td class="schema-description">USD value of the token balance</td>' in mapping_page
    assert '<td class="schema-description">Blockchain fallback from nested important map</td>' in mapping_page
    assert '<span class="schema-description-empty">&mdash;</span>' in mapping_page
    assert "Important columns" not in mapping_page
    schema_rows = re.findall(r"<tr data-schema-row[^>]*>", mapping_page)
    assert len(schema_rows) == 5
    assert all(" hidden" not in row for row in schema_rows)
    assert "table-layout: fixed;" in css
    assert ".schema-table tbody th:first-child code" in css
    assert re.search(
        r"\.schema-table-toolbar\s*\{[^}]*min-width:\s*680px;",
        css,
        re.S,
    )
    assert "overflow-wrap: anywhere;" in css
    assert "word-break: break-word;" in css

    list_page = (tmp_path / "site" / "datasets" / "list_schema.html").read_text(
        encoding="utf-8"
    )
    assert '<th scope="col">Column</th><th scope="col">Type</th><th scope="col">Description</th>' in list_page
    assert '<td class="schema-description">Cash safe address</td>' in list_page
    assert '<td class="schema-description">Schema balance description</td>' in list_page
    assert "Important balance fallback should not win" not in list_page
    assert '<td class="schema-description">Block number fallback</td>' in list_page
    assert '<th scope="row"><code>no_description_column</code></th><td>varchar</td>' in list_page
    assert '<span class="schema-description-empty">&mdash;</span>' in list_page
    assert "Important columns" not in list_page


def test_dataset_detail_schema_filter_matches_name_type_and_description_terms():
    node = shutil.which("node")
    if node is None:
        return

    script = r"""
const detail = require("./website/assets/dataset-detail.js");
const rows = [
  {
    id: "safe",
    search: "user_safe varbinary owner's wallet or contract address",
  },
  {
    id: "balance",
    search: "token_balance_usd double usd value of the token balance",
  },
  {
    id: "chain",
    search: "blockchain varchar blockchain network for this row",
  },
];
const matches = (query) => detail
  .filterSchemaRows(rows, query)
  .filter((result) => result.visible)
  .map((result) => result.row.id);

console.log(JSON.stringify({
  nameAndType: matches("USER_SAFE varbinary"),
  descriptionInAnyOrder: matches("wallet owner's"),
  naturalColumnLookup: matches("USD token balance"),
  typeAndDescription: matches("network VARCHAR"),
  allTermsRequired: matches("wallet double"),
  partialTerm: matches("blockch varch"),
  whitespaceOnly: matches("   \n  "),
  normalized: detail.normalizeSchemaSearch("  Owner's\n WALLET  "),
  counts: [
    detail.formatSchemaCount(3, 3, false),
    detail.formatSchemaCount(1, 3, true),
    detail.formatSchemaCount(0, 3, true),
    detail.formatSchemaCount(1, 1, false),
  ],
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior == {
        "nameAndType": ["safe"],
        "descriptionInAnyOrder": ["safe"],
        "naturalColumnLookup": ["balance"],
        "typeAndDescription": ["chain"],
        "allTermsRequired": [],
        "partialTerm": ["chain"],
        "whitespaceOnly": ["safe", "balance", "chain"],
        "normalized": "owner's wallet",
        "counts": [
            "3 columns",
            "1 of 3 columns",
            "0 of 3 columns",
            "1 column",
        ],
    }


def test_dataset_detail_schema_filter_mounts_and_handles_clear_escape_and_empty_state():
    node = shutil.which("node")
    if node is None:
        return

    script = r"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync("./website/assets/dataset-detail.js", "utf8");

function control(initial = {}) {
  return {
    ...initial,
    dataset: { ...(initial.dataset || {}) },
    hidden: Boolean(initial.hidden),
    listeners: {},
    value: initial.value || "",
    focusCount: 0,
    blurCount: 0,
    addEventListener(type, listener) {
      (this.listeners[type] ||= []).push(listener);
    },
    focus() {
      this.focusCount += 1;
    },
    blur() {
      this.blurCount += 1;
    },
  };
}

const rows = [
  control({ dataset: { schemaSearch: "user_safe varbinary owner wallet address" } }),
  control({ dataset: { schemaSearch: "token_balance_usd double usd token balance" } }),
  control({ dataset: { schemaSearch: "blockchain varchar blockchain network" } }),
];
const input = control();
const clearButton = control({ hidden: true });
const count = control({ textContent: "3 columns" });
const emptyState = control({ hidden: true });
const table = {
  querySelector(selector) {
    if (selector === "[data-schema-filter-count]") return count;
    if (selector === "[data-schema-filter-empty]") return emptyState;
    return null;
  },
  querySelectorAll(selector) {
    return selector === "[data-schema-row]" ? rows : [];
  },
};
const filter = control({ hidden: true });
filter.closest = (selector) => selector === "[data-schema-table]" ? table : null;
filter.querySelector = (selector) => {
  if (selector === "[data-schema-filter-input]") return input;
  if (selector === "[data-schema-filter-clear]") return clearButton;
  return null;
};

const documentObject = {
  documentElement: { dataset: {} },
  listeners: {},
  querySelectorAll(selector) {
    return selector === "[data-schema-filter]" ? [filter] : [];
  },
  addEventListener(type, listener) {
    (this.listeners[type] ||= []).push(listener);
  },
};
const browserWindow = {
  clearTimeout() {},
  setTimeout() {
    return 1;
  },
};
vm.runInNewContext(source, {
  console,
  document: documentObject,
  window: browserWindow,
});

function dispatch(element, type, event = {}) {
  for (const listener of element.listeners[type] || []) {
    listener.call(element, event);
  }
}
function snapshot() {
  return {
    visible: rows.map((row) => !row.hidden),
    count: count.textContent,
    emptyHidden: emptyState.hidden,
    clearHidden: clearButton.hidden,
  };
}

const mounted = {
  ...snapshot(),
  filterHidden: filter.hidden,
  filterMounted: filter.dataset.schemaFilterMounted,
  detailMounted: documentObject.documentElement.dataset.datasetDetailMounted,
};

input.value = "wallet VARBINARY";
dispatch(input, "input");
const filtered = snapshot();

input.value = "not a real column";
dispatch(input, "input");
const noMatch = snapshot();

dispatch(clearButton, "click");
const cleared = {
  ...snapshot(),
  value: input.value,
  focusCount: input.focusCount,
};

input.value = "USD DOUBLE";
dispatch(input, "input");
let escapePrevented = false;
dispatch(input, "keydown", {
  key: "Escape",
  preventDefault() {
    escapePrevented = true;
  },
});
const escaped = {
  ...snapshot(),
  value: input.value,
  prevented: escapePrevented,
  focusCount: input.focusCount,
};

dispatch(input, "keydown", {
  key: "Escape",
  preventDefault() {
    throw new Error("Blank Escape should not be prevented");
  },
});

console.log(JSON.stringify({
  mounted,
  filtered,
  noMatch,
  cleared,
  escaped,
  blankEscapeBlurCount: input.blurCount,
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior["mounted"] == {
        "visible": [True, True, True],
        "count": "3 columns",
        "emptyHidden": True,
        "clearHidden": True,
        "filterHidden": False,
        "filterMounted": "true",
        "detailMounted": "true",
    }
    assert behavior["filtered"] == {
        "visible": [True, False, False],
        "count": "1 of 3 columns",
        "emptyHidden": True,
        "clearHidden": False,
    }
    assert behavior["noMatch"] == {
        "visible": [False, False, False],
        "count": "0 of 3 columns",
        "emptyHidden": False,
        "clearHidden": False,
    }
    assert behavior["cleared"] == {
        "visible": [True, True, True],
        "count": "3 columns",
        "emptyHidden": True,
        "clearHidden": True,
        "value": "",
        "focusCount": 1,
    }
    assert behavior["escaped"] == {
        "visible": [True, True, True],
        "count": "3 columns",
        "emptyHidden": True,
        "clearHidden": True,
        "value": "",
        "prevented": True,
        "focusCount": 2,
    }
    assert behavior["blankEscapeBlurCount"] == 1


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
    css = (tmp_path / "assets" / "styles.css").read_text(encoding="utf-8")
    assert 'data-dashboards-page' in dashboard_index
    assert (
        'class="dataset-category-panel" aria-labelledby="dashboard-categories-title"'
        in dashboard_index
    )
    assert '<section class="dashboard-browser-header">' not in dashboard_index
    assert '<header class="catalog-index-header' not in dashboard_index
    assert '<p class="eyebrow">Dashboard registry</p>' not in dashboard_index
    assert (
        '<h1 id="dashboards-page-title" class="visually-hidden">Dashboards</h1>'
        in dashboard_index
    )
    assert 'aria-labelledby="dashboards-page-title"' in dashboard_index
    assert "Search curated Dune dashboards by product area" not in dashboard_index
    assert "dashboards across <strong>" not in dashboard_index
    assert (
        '<h2 id="dashboard-categories-title" class="dataset-category-panel-header">'
        "Dashboard categories</h2>"
        in dashboard_index
    )
    assert "Dashboard groups" not in dashboard_index
    assert "<strong>Registry</strong>" not in dashboard_index
    assert "Find existing ether.fi Dune dashboards by product area, tag, or linked catalog dataset." not in dashboard_index
    assert "Browse ether.fi Dune dashboards by product area and linked datasets." not in dashboard_index
    assert "Total dashboards" not in dashboard_index
    assert "Categories" not in dashboard_index
    assert "Linked datasets" not in dashboard_index
    assert 'data-dashboard-nav="core"' in dashboard_index
    assert 'data-dashboard-nav="stake"' in dashboard_index
    assert 'data-dashboard-nav="cash"' in dashboard_index
    assert 'data-dashboard-nav="liquid"' in dashboard_index
    assert 'data-dashboard-nav="others"' in dashboard_index
    for group in ["core", "stake", "cash", "liquid", "others"]:
        nav_button = re.search(
            rf'<button[^>]*data-dashboard-nav="{group}"[^>]*>',
            dashboard_index,
        )
        assert nav_button
        assert f'aria-controls="dashboard-group-{group}"' in nav_button.group(0)
        assert f'id="dashboard-group-{group}"' in dashboard_index
        assert f'aria-labelledby="dashboard-heading-{group}"' in dashboard_index
        assert f'id="dashboard-heading-{group}"' in dashboard_index
    for group, expected_count in {
        "core": 4,
        "stake": 5,
        "cash": 2,
        "liquid": 13,
        "others": 1,
    }.items():
        nav = re.search(
            rf'<button[^>]*data-dashboard-nav="{group}"[^>]*>(.*?)</button>',
            dashboard_index,
            re.S,
        )
        assert nav
        assert f"<strong>{expected_count}</strong>" in nav.group(1)
    assert dashboard_index.find("<span>Core</span>") < dashboard_index.find("<span>Stake</span>")
    assert dashboard_index.find("<span>Stake</span>") < dashboard_index.find("<span>Cash</span>")
    assert dashboard_index.find("<span>Cash</span>") < dashboard_index.find("<span>Liquid</span>")
    assert dashboard_index.find("<span>Liquid</span>") < dashboard_index.find("<span>Others</span>")
    assert 'data-dashboard-section data-dashboard-group="core"' in dashboard_index
    assert 'data-dashboard-section data-dashboard-group="stake"' in dashboard_index
    assert 'data-dashboard-section data-dashboard-group="cash"' in dashboard_index
    core_section = re.search(
        r'<section id="dashboard-group-core".*?</section>',
        dashboard_index,
        re.S,
    )
    assert core_section
    cash_section = re.search(
        r'<section id="dashboard-group-cash".*?</section>',
        dashboard_index,
        re.S,
    )
    assert cash_section
    assert "2 dashboards in the Cash product area." in cash_section.group(0)
    assert 'href="dashboards/etherfi_cash_swaps.html"' in cash_section.group(0)
    assert 'href="dashboards/etherfi_cash_swaps.html"' not in core_section.group(0)
    others_section = re.search(
        r'<section id="dashboard-group-others".*?</section>',
        dashboard_index,
        re.S,
    )
    assert others_section
    assert "1 dashboard in the Others product area." in others_section.group(0)
    assert "No dashboards documented in this group yet." not in others_section.group(0)
    assert (
        "Most used, most updated, and most informative ether.fi dashboards."
        in core_section.group(0)
    )
    assert "Core contains the top dashboards teammates should check first." not in dashboard_index
    assert "teammates" not in core_section.group(0)
    assert "ether.fi" in dashboard_index
    assert "ether.fi Users" in dashboard_index
    assert "ether.fi Cash" in dashboard_index
    assert "ether.fi Cash Swaps" in dashboard_index
    assert "eETH Staking" in dashboard_index
    assert "weETH on L2s + BNB" in dashboard_index
    assert "weETH Utilization" in dashboard_index
    assert "Liquid Vaults" in dashboard_index
    assert "Lido vs ether.fi Stakers" in dashboard_index
    assert dashboard_index.count('href="dashboards/etherfi_overview.html"') >= 2
    assert dashboard_index.count('href="dashboards/etherfi_users.html"') >= 2
    assert dashboard_index.count('href="dashboards/etherfi_cash.html"') >= 2
    assert 'href="dashboards/etherfi_overview.html"' in dashboard_index
    assert 'href="dashboards/etherfi_users.html"' in dashboard_index
    assert 'href="dashboards/etherfi_cash.html"' in dashboard_index
    assert 'href="dashboards/etherfi_cash_swaps.html"' in dashboard_index
    assert 'href="dashboards/eeth_staking.html"' in dashboard_index
    assert 'href="dashboards/weeth_l2s.html"' in dashboard_index
    assert 'href="dashboards/weeth_utilization.html"' in dashboard_index
    assert 'href="dashboards/liquid_vaults.html"' in dashboard_index
    assert 'href="dashboards/lido_vs_etherfi_stakers.html"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/etherfi"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/etherfi-users"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/etherfi-cash"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/cash-swaps-data"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/eeth-staking"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/weeth-l2s"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/weeth-utilization"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/liquid-vaults"' in dashboard_index
    assert 'href="https://dune.com/ether_fi/lido-vs-etherfi-stakers"' in dashboard_index
    assert 'data-dashboard-card' in dashboard_index
    assert 'data-dashboard-core-card' in dashboard_index
    assert 'data-search=' in dashboard_index
    assert 'data-dashboard-category="stake"' in dashboard_index
    assert 'data-dashboard-category="cash"' in dashboard_index
    assert 'data-dashboard-category="others"' in dashboard_index
    assert "cashback" in dashboard_index
    assert "spend" in dashboard_index
    assert "lending" in dashboard_index
    assert "user_safe" in dashboard_index
    assert 'id="dashboard-search"' in dashboard_index
    assert 'data-catalog-search aria-keyshortcuts="/"' in dashboard_index
    assert 'aria-describedby="dashboard-count"' in dashboard_index
    assert 'data-search-clear aria-label="Clear dashboard search"' in dashboard_index
    assert 'id="dashboard-count"' in dashboard_index
    assert (
        'id="dashboard-count" class="visually-hidden" role="status" '
        'aria-live="polite" aria-atomic="true">Core dashboards shown</span>'
        in dashboard_index
    )
    assert "core &middot;" not in dashboard_index
    assert " total</span>" not in dashboard_index
    assert 'id="dashboard-empty-state"' in dashboard_index
    assert 'src="assets/dashboards.js?v=' in dashboard_index
    assert 'data-dashboard-group="stake" aria-labelledby="dashboard-heading-stake" data-default-hidden' in dashboard_index
    assert '<noscript><p class="no-js-note">' in dashboard_index
    assert dashboard_index.find('class="catalog-toolbar dataset-browser-toolbar"') < dashboard_index.find('id="dashboard-group-core"')
    assert "No dashboards documented in this group yet." not in dashboard_index
    assert "No dashboards match your search." in dashboard_index
    assert "generated from dashboards/registry.yaml" not in dashboard_index

    core_cards = re.findall(
        r'<article class="dashboard-browser-card featured" data-dashboard-core-card>(.*?)</article>',
        core_section.group(0),
        re.S,
    )
    assert len(core_cards) == 4
    overview_card = next(card for card in core_cards if ">ether.fi</a>" in card)
    assert '<span class="dashboard-category-chip stake">Stake</span>' in overview_card
    assert "dashboard-linked-count" not in overview_card
    assert '<h3 class="dashboard-card-heading"><a class="dashboard-card-title"' in overview_card
    assert '<div class="dashboard-tag-row">' in overview_card
    assert '<span class="dashboard-tag">overview</span>' in overview_card
    assert 'href="https://dune.com/ether_fi/etherfi" aria-label="Open ether.fi on Dune">Dune</a>' in overview_card
    assert (
        'href="dashboards/etherfi_overview.html" '
        'aria-label="View ether.fi dashboard details">Details</a>'
        in overview_card
    )
    users_core_card = next(
        card
        for card in core_cards
        if 'href="dashboards/etherfi_users.html"' in card
    )
    assert '<span class="dashboard-category-chip stake">Stake</span>' in users_core_card
    assert "dashboard-linked-count" not in users_core_card
    assert (
        'href="dashboards/etherfi_users.html" '
        'aria-label="View ether.fi Users dashboard details">Details</a>'
        in users_core_card
    )
    liquid_vaults_core_card = next(
        card
        for card in core_cards
        if 'href="dashboards/liquid_vaults.html"' in card
    )
    assert (
        '<span class="dashboard-category-chip liquid">Liquid</span>'
        in liquid_vaults_core_card
    )

    dashboard_cards = re.findall(
        r'<article class="dashboard-browser-card"[^>]*>(.*?)</article>',
        dashboard_index,
        re.S,
    )
    dashboard_search_cards = re.findall(
        r'(<article class="dashboard-browser-card" data-dashboard-card[^>]*>.*?</article>)',
        dashboard_index,
        re.S,
    )
    overview_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/etherfi_overview.html"' in card
    )
    for metric_search_text in [
        "protocol revenue",
        "ethfi buybacks",
        "weeth trading volume",
        "daily deposits across stake and liquid products",
    ]:
        assert metric_search_text in overview_search_card.lower()
    users_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/etherfi_users.html"' in card
    )
    assert 'data-dashboard-category="stake"' in users_search_card
    for search_text in [
        "unique depositors",
        "active holders",
        "new vs old",
        "retention rates",
        "top onboarding products",
    ]:
        assert search_text in users_search_card.lower()
    eeth_staking_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/eeth_staking.html"' in card
    )
    for metric_search_text in [
        "staking apr",
        "weeth peg",
        "withdrawal processing wait time",
        "weeth dex trading volume",
        "weeth defi utilization",
    ]:
        assert metric_search_text in eeth_staking_search_card.lower()
    weeth_utilization_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/weeth_utilization.html"' in card
    )
    for metric_search_text in [
        "weeth supply in defi",
        "percentage of eeth wrapped as weeth",
        "weeth netflows by protocol",
        "weeth top holders with labels",
        "weeth integrations on aave and pendle",
    ]:
        assert metric_search_text in weeth_utilization_search_card.lower()
    weeth_l2s_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/weeth_l2s.html"' in card
    )
    for metric_search_text in [
        "arbitrum weeth metrics",
        "bnb chain weeth metrics",
        "weeth dex volumes on l2s",
        "weeth/eth ratio on l2s",
        "top sectors holding weeth on l2s",
    ]:
        assert metric_search_text in weeth_l2s_search_card.lower()
    cash_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/etherfi_cash.html"' in card
    )
    for metric_search_text in [
        "cash spend volume",
        "cashbacks",
        "active cards",
        "onramp volume",
        "outstanding cash borrows",
    ]:
        assert metric_search_text in cash_search_card.lower()
    cash_swaps_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/etherfi_cash_swaps.html"' in card
    )
    assert 'data-dashboard-category="cash"' in cash_swaps_search_card
    assert "dashboard-linked-count" not in cash_swaps_search_card
    for search_text in [
        "cash swaps",
        "swap volume",
        "top dexes",
        "token pairs",
        "cash safe",
    ]:
        assert search_text in cash_swaps_search_card.lower()
    lido_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/lido_vs_etherfi_stakers.html"' in card
    )
    for search_text in [
        "lido vs ether.fi stakers",
        "compare lido and ether.fi",
        "new depositors",
        "7-day moving deposit sum",
        "deposit and withdrawal size buckets",
        "deposits and withdrawals by size bucket",
        "market-comparison",
    ]:
        assert search_text in lido_search_card.lower()
    liquid_vaults_search_card = next(
        card
        for card in dashboard_search_cards
        if 'href="dashboards/liquid_vaults.html"' in card
    )
    assert 'data-dashboard-category="liquid"' in liquid_vaults_search_card
    lido_card = next(
        card
        for card in dashboard_cards
        if 'href="dashboards/lido_vs_etherfi_stakers.html"' in card
    )
    assert '<span class="dashboard-category-chip others">Others</span>' in lido_card
    assert "dashboard-linked-count" not in lido_card
    ebtc_card = next(card for card in dashboard_cards if 'href="dashboards/ebtc.html"' in card)
    assert '<span class="dashboard-tag">liquid</span>' in ebtc_card
    assert '<span class="dashboard-tag">vaults</span>' in ebtc_card
    assert '<span class="dashboard-tag">ebtc</span>' in ebtc_card
    assert '<span class="dashboard-tag">btc</span>' in ebtc_card
    assert '<span class="dashboard-tag">deposits</span>' not in ebtc_card
    assert '<span class="dashboard-tag muted">+7</span>' in ebtc_card

    assert re.search(
        r"\.button\.primary::after,\s*\.dataset-detail-action::after\s*\{[^}]*content:\s*\"\\2192\";",
        css,
        re.S,
    )
    assert re.search(
        r"\.dune-action:not\(\.disabled\)::after\s*\{[^}]*content:\s*\"\\2197\";",
        css,
        re.S,
    )
    related_resource_arrow = re.search(
        r"a\.related-resource::after\s*\{([^}]*)\}",
        css,
        re.S,
    )
    assert related_resource_arrow
    assert 'content: ""' in related_resource_arrow.group(1)
    assert "border-top: 1.5px solid currentColor" in related_resource_arrow.group(1)
    assert "border-right: 1.5px solid currentColor" in related_resource_arrow.group(1)
    assert "rotate(45deg)" in related_resource_arrow.group(1)
    assert r'content: "\2192"' not in related_resource_arrow.group(1)
    assert re.search(
        r"\.dashboard-card-title\s*\{[^}]*overflow-wrap:\s*anywhere;",
        css,
        re.S,
    )
    assert "outline: 3px solid var(--focus-ring);" in css
    assert "scroll-snap-type: inline proximity;" in css
    assert re.search(
        r"\.code-snippet code\s*\{[^}]*background:\s*transparent;[^}]*color:\s*inherit;",
        css,
        re.S,
    )

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
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in overview_page
    assert 'class="detail-section-nav" aria-label="On this page"' not in overview_page
    assert (
        'class="detail-tab-interface" data-detail-tabs data-default-tab="metrics" '
        'data-detail-tabs-label="Dashboard detail sections"'
        in overview_page
    )
    assert (
        'class="detail-tab-list" data-detail-tab-list hidden'
        in overview_page
    )
    assert (
        'data-detail-tab="metrics" data-detail-tab-controls="metrics"'
        in overview_page
    )
    assert (
        'data-detail-tab="linked-datasets" '
        'data-detail-tab-controls="linked-datasets"'
        in overview_page
    )
    assert (
        'data-detail-tab="tags" data-detail-tab-controls="tags"'
        in overview_page
    )
    for panel_id in ["metrics", "linked-datasets", "tags"]:
        panel_tag = re.search(rf'<section id="{panel_id}"[^>]*>', overview_page)
        assert panel_tag
        assert " hidden" not in panel_tag.group(0)
    assert "<h2>Metrics displayed</h2>" in overview_page
    assert "Dashboard coverage" not in overview_page
    assert '<span class="dashboard-metrics-count">18 documented metrics</span>' in overview_page
    assert '<ul class="dashboard-metrics-grid">' in overview_page
    assert "Latest ether.fi TVL" in overview_page
    assert "weETH in DeFi Protocols" in overview_page
    assert "Daily Withdrawal Requests Across Stake and Liquid Products" in overview_page
    assert "weETH Liquidity in DEXes" in overview_page
    assert "weETH/ETH Ratio" in overview_page
    assert "ETHFI Buybacks" in overview_page
    assert "ether.fi Protocol Revenue" in overview_page
    assert "<h2>Notes</h2>" not in overview_page
    assert overview_page.find('id="metrics"') < overview_page.find('id="linked-datasets"')
    assert overview_page.find('id="linked-datasets"') < overview_page.find('id="tags"')
    assert "<h2>Linked datasets</h2>" not in overview_page
    assert '<h2 class="detail-tab-source-heading">Linked datasets</h2>' in overview_page
    assert "<h3>Catalog datasets</h3>" not in overview_page
    assert "Linked datasets" in overview_page
    assert "Linked datasets and references" not in overview_page
    assert 'class="related-resource-list"' in overview_page
    assert 'class="related-resource"' in overview_page
    assert "dashboard-linked-dataset-card" not in overview_page
    assert "dashboard-linked-dataset-grid" not in overview_page
    assert (
        '[data-detail-tabs-mounted="true"] .detail-tab-source-heading'
        in css
    )
    assert 'href="../datasets/protocol_token_holders.html"' in overview_page
    assert 'href="../datasets/etherfi_protocol_token_tvl.html"' in overview_page
    assert "Ether.fi Protocol Token TVL" in overview_page
    linked_dataset_section = re.search(
        r'<section id="linked-datasets"[^>]*>(.*?)</section>',
        overview_page,
        re.S,
    )
    assert linked_dataset_section
    linked_dataset_hrefs = re.findall(
        r'<a class="related-resource" href="([^"]+)">',
        linked_dataset_section.group(1),
    )
    assert linked_dataset_hrefs
    assert len(linked_dataset_hrefs) == len(set(linked_dataset_hrefs))
    assert (
        '<a class="related-resource" href="../datasets/protocol_token_holders.html">'
        "Ether.fi Protocol Token Holders</a>"
        in linked_dataset_section.group(1)
    )
    assert 'target="_blank"' not in linked_dataset_section.group(1)
    assert "Dataset used by the main ether.fi overview dashboard for protocol token TVL" not in overview_page
    assert "<span>Refresh</span>" not in overview_page
    assert "utils.days" not in overview_page
    assert "labels.ens" not in overview_page
    assert "dex_aggregator.trades" not in overview_page
    assert "<h2>Source</h2>" not in overview_page
    assert "dashboards/stake/etherfi_overview.yaml" not in overview_page
    assert "Use this dashboard if" not in overview_page
    assert "dashboards/registry.yaml" not in overview_page

    users_page = (tmp_path / "dashboards" / "etherfi_users.html").read_text(
        encoding="utf-8"
    )
    assert "ether.fi Users" in users_page
    assert "https://dune.com/ether_fi/etherfi-users" in users_page
    assert "Protocol-wide ether.fi user dashboard" in users_page
    assert 'aria-label="Open ether.fi Users on Dune"' in users_page
    assert '<span class="dashboard-category-chip stake">Stake</span>' in users_page
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in users_page
    assert "<h2>Metrics displayed</h2>" in users_page
    assert '<span class="dashboard-metrics-count">16 documented metrics</span>' in users_page
    assert '<ul class="dashboard-metrics-grid">' in users_page
    assert "Total Protocol Unique Depositors" in users_page
    assert "Protocol Active Holders" in users_page
    assert "Daily Deposits by Depositor Type" in users_page
    assert "Protocol Retention Rates" in users_page
    assert "Deposits by New Depositors Across All ether.fi Products" in users_page
    assert "Top Onboarding Products" in users_page
    assert users_page.find("<h2>Metrics displayed</h2>") < users_page.find('id="tags"')
    assert "<h2>Notes</h2>" not in users_page
    assert "new vs old" not in users_page
    assert "at least $10 worth" not in users_page
    for dataset_slug in [
        "etherfi_protocol_events",
        "protocol_token_holders",
        "protocol_token_holders_with_defi",
        "etherfi_protocol_token_tvl",
        "etherfi_assets_under_management",
        "etherfi_addresses",
        "addresses_traits",
    ]:
        assert f'href="../datasets/{dataset_slug}.html"' in users_page

    eeth_staking_page = (tmp_path / "dashboards" / "eeth_staking.html").read_text(
        encoding="utf-8"
    )
    assert "eETH Staking" in eeth_staking_page
    assert "Core eETH and weETH staking dashboard" in eeth_staking_page
    assert 'href="../datasets/protocol_token_holders.html"' in eeth_staking_page
    assert 'href="../datasets/protocol_token_holders_with_defi.html"' in eeth_staking_page
    assert 'href="../datasets/tokens_transfers.html"' in eeth_staking_page
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in eeth_staking_page
    assert "<h2>Metrics displayed</h2>" in eeth_staking_page
    assert '<span class="dashboard-metrics-count">18 documented metrics</span>' in eeth_staking_page
    assert '<ul class="dashboard-metrics-grid">' in eeth_staking_page
    assert "eETH TVL" in eeth_staking_page
    assert "eETH User Staking APR" in eeth_staking_page
    assert "weETH Peg" in eeth_staking_page
    assert "7-Day Moving Average Withdrawal Processing Time" in eeth_staking_page
    assert "Instant Withdrawal Fees" in eeth_staking_page
    assert "eETH and weETH Holder Distribution" in eeth_staking_page
    assert "eETH and weETH Retention Rates" in eeth_staking_page
    assert "weETH DEX Trading Volume" in eeth_staking_page
    assert "weETH DeFi Utilization" in eeth_staking_page
    assert eeth_staking_page.find("<h2>Metrics displayed</h2>") < eeth_staking_page.find(
        'id="tags"'
    )
    assert '<section class="detail-panel dataset-detail-section dashboard-notes-panel">' not in eeth_staking_page
    assert "<h2>Notes</h2>" not in eeth_staking_page
    assert "decoded contract calls and events" not in eeth_staking_page

    weeth_l2s_page = (tmp_path / "dashboards" / "weeth_l2s.html").read_text(
        encoding="utf-8"
    )
    assert "weETH on L2s + BNB" in weeth_l2s_page
    assert "Overview of weETH across L2 chains and BNB Chain" in weeth_l2s_page
    assert 'class="dashboard-category-chip stake"' in weeth_l2s_page
    assert 'href="../datasets/protocol_token_holders.html"' in weeth_l2s_page
    assert 'href="../datasets/lrts_restaking_dex_pools_balances.html"' in weeth_l2s_page
    assert 'href="../datasets/lrts_restaking_trades.html"' in weeth_l2s_page
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in weeth_l2s_page
    assert "<h2>Metrics displayed</h2>" in weeth_l2s_page
    assert '<span class="dashboard-metrics-count">24 documented metrics</span>' in weeth_l2s_page
    assert '<ul class="dashboard-metrics-grid">' in weeth_l2s_page
    for chain_metric in [
        "Arbitrum weETH Metrics",
        "Avalanche weETH Metrics",
        "Base weETH Metrics",
        "Berachain weETH Metrics",
        "Blast weETH Metrics",
        "BNB Chain weETH Metrics",
        "Katana weETH Metrics",
        "Linea weETH Metrics",
        "Mode weETH Metrics",
        "Optimism weETH Metrics",
        "Scroll weETH Metrics",
        "Unichain weETH Metrics",
    ]:
        assert chain_metric in weeth_l2s_page
    assert weeth_l2s_page.find("Arbitrum weETH Metrics") < weeth_l2s_page.find(
        "Unichain weETH Metrics"
    ) < weeth_l2s_page.find("weETH Supply on L2s")
    assert "weETH DEX Volumes on L2s" in weeth_l2s_page
    assert "weETH/ETH Ratio on L2s" in weeth_l2s_page
    assert "Percentage of weETH Supply in DeFi on L2s" in weeth_l2s_page
    assert "Top Sectors Holding weETH on L2s" in weeth_l2s_page
    assert weeth_l2s_page.find("<h2>Metrics displayed</h2>") < weeth_l2s_page.find(
        'id="tags"'
    )
    assert "prices.usd" not in weeth_l2s_page
    assert "<h2>Notes</h2>" not in weeth_l2s_page

    weeth_utilization_page = (
        tmp_path / "dashboards" / "weeth_utilization.html"
    ).read_text(encoding="utf-8")
    assert "weETH Utilization" in weeth_utilization_page
    assert "Overview of weETH utilization across DeFi protocols" in weeth_utilization_page
    assert 'class="dashboard-category-chip stake"' in weeth_utilization_page
    assert 'href="../datasets/protocol_token_holders.html"' in weeth_utilization_page
    assert 'href="../datasets/tokens_prices_tokens_list.html"' in weeth_utilization_page
    assert 'href="../datasets/tokens_transfers.html"' in weeth_utilization_page
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in weeth_utilization_page
    assert "<h2>Metrics displayed</h2>" in weeth_utilization_page
    assert '<span class="dashboard-metrics-count">11 documented metrics</span>' in weeth_utilization_page
    assert '<ul class="dashboard-metrics-grid">' in weeth_utilization_page
    assert "weETH Supply in DeFi" in weeth_utilization_page
    assert "Percentage of eETH Wrapped as weETH" in weeth_utilization_page
    assert "weETH Netflows by Protocol" in weeth_utilization_page
    assert "weETH Top Holders with Labels" in weeth_utilization_page
    assert "weETH Integrations on Aave and Pendle" in weeth_utilization_page
    assert weeth_utilization_page.find(
        "<h2>Metrics displayed</h2>"
    ) < weeth_utilization_page.find('id="tags"')
    assert "bridge contracts" not in weeth_utilization_page
    assert "prices.usd" not in weeth_utilization_page
    assert "<h2>Notes</h2>" not in weeth_utilization_page

    liquid_vaults_page = (tmp_path / "dashboards" / "liquid_vaults.html").read_text(
        encoding="utf-8"
    )
    assert "Liquid Vaults" in liquid_vaults_page
    assert "Overview of ether.fi Liquid Vaults" in liquid_vaults_page
    assert 'href="../datasets/etherfi_protocol_token_tvl.html"' in liquid_vaults_page
    assert 'href="../datasets/protocol_token_holders_with_defi.html"' in liquid_vaults_page
    assert 'href="../datasets/tokens_rates_oracle_pegs.html"' in liquid_vaults_page
    assert "boringonchainqueue" not in liquid_vaults_page.lower()
    assert "<h2>Notes</h2>" not in liquid_vaults_page
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in liquid_vaults_page
    assert "<h2>Metrics displayed</h2>" in liquid_vaults_page
    assert '<span class="dashboard-metrics-count">18 documented metrics</span>' in liquid_vaults_page
    assert '<ul class="dashboard-metrics-grid">' in liquid_vaults_page
    assert "Use these metrics to confirm the dashboard covers the analysis you need before opening Dune." not in liquid_vaults_page
    assert "dashboard-metrics-intro" not in liquid_vaults_page
    assert "Current All-Time Unique Depositors" in liquid_vaults_page
    assert "Daily Withdrawal Requests" in liquid_vaults_page
    assert "Daily Liquid Vaults Deposits grouped by Liquid Vault" in liquid_vaults_page
    assert "Daily Protocol Deposits Breakdown" in liquid_vaults_page
    assert "LiquidETH, LiquidUSD, and LiquidBTC TVL, withdrawal times, and APR" in liquid_vaults_page
    assert liquid_vaults_page.find("<h2>Metrics displayed</h2>") < liquid_vaults_page.find('id="tags"')

    related_liquid_vaults = [
        "ebtc",
        "weeths",
        "weethk",
        "liquidberabtc",
        "liquidberaeth",
        "liquidusd",
        "liquidbtc",
        "ultrausd",
        "liquidmoveeth",
        "liquidkatanaeth",
        "liquideth",
        "liquidrwa",
    ]
    for dashboard_name in related_liquid_vaults:
        assert f'href="dashboards/{dashboard_name}.html"' in dashboard_index
        dashboard_page = (tmp_path / "dashboards" / f"{dashboard_name}.html").read_text(
            encoding="utf-8"
        )
        assert 'class="dashboard-category-chip liquid"' in dashboard_page
        assert 'href="../datasets/etherfi_protocol_token_tvl.html"' in dashboard_page
        assert 'href="../datasets/protocol_token_holders_with_defi.html"' in dashboard_page
        assert "BoringOnChainQueue" not in dashboard_page
        assert "<h2>Notes</h2>" not in dashboard_page

    cash_page = (tmp_path / "dashboards" / "etherfi_cash.html").read_text(
        encoding="utf-8"
    )
    assert "../assets/styles.css" in cash_page
    assert "ether.fi Cash" in cash_page
    assert "https://dune.com/ether_fi/etherfi-cash" in cash_page
    assert "Operational dashboard for ether.fi Cash activity" in cash_page
    assert "cashback" in cash_page
    assert "user_safe" in cash_page
    assert 'href="../dashboards.html#dashboard-group-core"' in cash_page
    assert 'aria-label="Back to Core dashboards"' in cash_page
    assert "At a glance" not in cash_page
    assert "Core display" not in cash_page
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in cash_page
    assert "<h2>Metrics displayed</h2>" in cash_page
    assert '<span class="dashboard-metrics-count">20 documented metrics</span>' in cash_page
    assert '<ul class="dashboard-metrics-grid">' in cash_page
    assert "Total Cash Spend Volume" in cash_page
    assert "Total Cashbacks" in cash_page
    assert "Daily Cashback Volume" in cash_page
    assert "Daily New Cards" in cash_page
    assert "Total Cash User Safe Balances" in cash_page
    assert "Outstanding Cash Borrows" in cash_page
    assert "Cash Transaction Profiles" in cash_page
    assert "Most Active Cash Spend Hours" in cash_page
    assert "<h2>Notes</h2>" not in cash_page
    assert "Linked datasets" in cash_page
    assert (
        "Linked datasets show catalog pages only; this dashboard also references "
        "source dependencies outside the catalog."
        in cash_page
    )
    assert "Linked datasets and references" not in cash_page
    assert 'class="related-resource-list"' in cash_page
    assert 'class="related-resource"' in cash_page
    assert "dashboard-linked-dataset-card" not in cash_page
    assert "dashboard-linked-dataset-grid" not in cash_page
    assert "etherfi_optimism.casheventemitter_evt_cashback" not in cash_page
    assert "etherfi_optimism.casheventemitter_evt_spend" not in cash_page
    assert "dune.ether_fi.result_backup_etherfi_cash_scroll_events" not in cash_page
    assert 'href="../datasets/etherfi_cash_events.html"' in cash_page
    assert 'href="../datasets/etherfi_cash_addresses.html"' in cash_page
    assert 'href="../datasets/etherfi_assets_under_management.html"' in cash_page
    assert 'href="../datasets/etherfi_cash_borrow_index.html"' in cash_page
    assert 'href="../datasets/tokens_prices_usd.html"' in cash_page
    assert "Minute-level raw/direct USD token price feed" not in cash_page
    assert "<span>Refresh</span>" not in cash_page
    assert "<h2>Source</h2>" not in cash_page
    assert "utils.days" not in cash_page

    cash_swaps_page = (
        tmp_path / "dashboards" / "etherfi_cash_swaps.html"
    ).read_text(encoding="utf-8")
    assert "ether.fi Cash Swaps" in cash_swaps_page
    assert "https://dune.com/ether_fi/cash-swaps-data" in cash_swaps_page
    assert "Dashboard tracking swap activity by ether.fi Cash safes" in cash_swaps_page
    assert 'aria-label="Open ether.fi Cash Swaps on Dune"' in cash_swaps_page
    assert '<span class="dashboard-category-chip cash">Cash</span>' in cash_swaps_page
    assert 'href="../dashboards.html#dashboard-group-cash"' in cash_swaps_page
    assert "dashboard-linked-summary" not in cash_swaps_page
    assert "catalog datasets linked" not in cash_swaps_page
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in cash_swaps_page
    assert "<h2>Metrics displayed</h2>" in cash_swaps_page
    assert '<span class="dashboard-metrics-count">5 documented metrics</span>' in cash_swaps_page
    assert '<ul class="dashboard-metrics-grid">' in cash_swaps_page
    assert "Total Cash Swap Volume" in cash_swaps_page
    assert "Total Cash Swaps" in cash_swaps_page
    assert "Daily Cash Swap Volume" in cash_swaps_page
    assert "Top DEXes for Cash Swaps" in cash_swaps_page
    assert "Top Cash Swap Token Pairs" in cash_swaps_page
    assert cash_swaps_page.find('id="metrics"') < cash_swaps_page.find('id="linked-datasets"')
    assert cash_swaps_page.find('id="linked-datasets"') < cash_swaps_page.find('id="tags"')
    assert "<h2>Notes</h2>" not in cash_swaps_page
    assert 'href="../datasets/etherfi_cash_addresses.html"' in cash_swaps_page
    assert 'href="../datasets/etherfi_assets_under_management.html"' in cash_swaps_page
    assert 'href="../datasets/etherfi_cash_events.html"' in cash_swaps_page
    assert 'href="../datasets/tokens_prices_usd.html"' in cash_swaps_page

    lido_page = (
        tmp_path / "dashboards" / "lido_vs_etherfi_stakers.html"
    ).read_text(encoding="utf-8")
    assert "Lido vs ether.fi Stakers" in lido_page
    assert "https://dune.com/ether_fi/lido-vs-etherfi-stakers" in lido_page
    assert "Compare Lido and ether.fi staking performance" in lido_page
    assert 'aria-label="Open Lido vs ether.fi Stakers on Dune"' in lido_page
    assert '<span class="dashboard-category-chip others">Others</span>' in lido_page
    assert '<div id="dashboard-metrics" class="dashboard-metrics-panel">' in lido_page
    assert "<h2>Metrics displayed</h2>" in lido_page
    assert '<span class="dashboard-metrics-count">16 documented metrics</span>' in lido_page
    assert '<ul class="dashboard-metrics-grid">' in lido_page
    assert "Daily ether.fi TVL and Lido TVL" in lido_page
    assert "Total Deposits by New Users" in lido_page
    assert "7-Day Moving Median Deposit Amount" in lido_page
    assert "Deposits and Withdrawals by Size Bucket" in lido_page
    assert lido_page.find("<h2>Metrics displayed</h2>") < lido_page.find('id="tags"')
    assert '<h2>Notes</h2>' not in lido_page
    assert "outside the ether.fi catalog" not in lido_page
    assert "lido_ethereum.steth_evt_submitted" not in lido_page
    assert 'href="../datasets/etherfi_protocol_events.html"' in lido_page
    assert 'href="../datasets/etherfi_protocol_token_tvl.html"' in lido_page
    assert 'href="../datasets/protocol_token_holders.html"' in lido_page
    assert 'href="../datasets/etherfi_assets_under_management.html"' in lido_page
    assert 'href="../datasets/etherfi_addresses.html"' in lido_page
    assert 'href="../datasets/tokens_prices_tokens_list.html"' in lido_page
    assert 'href="../datasets/tokens_prices_usd.html"' in lido_page


def test_dashboard_detail_keeps_stable_tabs_without_internal_dataset_matches(tmp_path):
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
    assert "Linked datasets" in detail_page
    assert 'data-detail-tabs data-default-tab="metrics"' in detail_page
    assert 'data-detail-tab="linked-datasets"' in detail_page
    assert "dashboard-linked-summary" not in detail_page
    assert "catalog datasets linked" not in detail_page
    assert "No linked catalog datasets are documented." in detail_page
    assert (
        "Linked datasets show catalog pages only; this dashboard also references "
        "source dependencies outside the catalog."
        in detail_page
    )
    assert '<span class="dashboard-metrics-count">0 documented metrics</span>' in detail_page
    assert "Metrics are not documented in the catalog." in detail_page
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
    assert "catalog-summary-card" not in freshness_page
    assert "freshness-status-legend" not in freshness_page
    assert "Total datasets" not in freshness_page
    assert "Fresh datasets" not in freshness_page
    assert "Stale datasets" not in freshness_page
    assert "Unknown datasets" not in freshness_page
    assert '<section class="freshness-hero detail-panel">' not in freshness_page
    assert "<h1>Freshness</h1>" not in freshness_page
    source_panel = re.search(
        r'<section class="freshness-source-panel detail-panel"[^>]*>(.*?)</section>',
        freshness_page,
        re.S,
    )
    assert source_panel
    assert (
        '<h2 id="freshness-source-title" class="freshness-source-title">'
        "Source &amp; automation</h2>"
        in source_panel.group(1)
    )
    assert (
        "Catalog freshness is read from a Dune tracker query; each website "
        "deployment reuses the latest validated four-hour Studio snapshot."
        in source_panel.group(1)
    )
    assert re.search(
        r'<a class="freshness-source-link dune" href="https://dune\.com/queries/7625551"[^>]*>'
        r'.*?<strong>View freshness query</strong>.*?</a>',
        source_panel.group(1),
        re.S,
    )
    assert re.search(
        r'<a class="freshness-source-link workflow" '
        r'href="https://github\.com/henrystats/etherfi-data-catalog/actions/workflows/refresh-freshness\.yml"[^>]*>'
        r'.*?<strong>Refresh freshness &amp; deploy</strong>.*?</a>',
        source_panel.group(1),
        re.S,
    )
    assert "freshness-summary" not in source_panel.group(1)
    assert "freshness-summary-item" not in freshness_page
    assert "Search datasets" in freshness_page
    assert "Search datasets, tables, status, or query IDs..." in freshness_page
    assert 'data-catalog-search aria-keyshortcuts="/"' in freshness_page
    assert 'data-search-clear aria-label="Clear dataset search"' in freshness_page
    assert "Dataset category filters" not in freshness_page
    assert "data-category-filter" not in freshness_page
    assert 'data-status-filter="all"' in freshness_page
    assert 'data-status-filter="fresh"' in freshness_page
    assert 'data-status-filter="delayed"' in freshness_page
    assert 'data-status-filter="stale"' in freshness_page
    assert 'data-status-filter="unknown"' in freshness_page
    assert (
        '<button class="filter-chip active" type="button" '
        'data-status-filter="all" aria-pressed="true">All</button>'
        in freshness_page
    )
    for status, label in [
        ("fresh", "Fresh"),
        ("delayed", "Delayed"),
        ("stale", "Stale"),
        ("unknown", "Unknown"),
    ]:
        assert (
            f'<button class="filter-chip" type="button" data-status-filter="{status}" '
            f'aria-pressed="false">{label}</button>'
            in freshness_page
        )
    card_statuses = re.findall(
        r'<article class="registry-card freshness-dataset-card [^"]+" '
        r'[^>]*data-status="([^"]+)"',
        freshness_page,
    )
    assert card_statuses
    filter_group = re.search(
        r'<div class="filter-chip-row"[^>]*>(.*?)</div>',
        freshness_page,
        re.S,
    )
    assert filter_group
    assert "<strong>" not in filter_group.group(1)
    assert not re.search(r">\s*\d+\s*<", filter_group.group(1))
    assert (
        'class="filter-chip-row" role="group" '
        'aria-labelledby="freshness-status-label"'
        in freshness_page
    )
    assert "<noscript><p class=\"no-js-note\">" in freshness_page
    assert 'aria-describedby="dataset-count"' in freshness_page
    assert 'aria-describedby="dataset-count freshness-status-note"' not in freshness_page
    assert 'aria-describedby="freshness-status-note"' not in freshness_page
    assert 'id="freshness-status-note"' not in freshness_page
    assert "<table" not in freshness_page
    assert "catalog-table" not in freshness_page
    assert "Dataset registry" not in freshness_page
    assert "One card per freshness-tracked catalog entry." not in freshness_page
    assert (
        '<section class="registry-section" '
        'aria-labelledby="freshness-registry-title">'
        in freshness_page
    )
    assert (
        '<h2 id="freshness-registry-title" class="visually-hidden">'
        "Freshness datasets</h2>"
        in freshness_page
    )
    assert 'class="registry-list"' in freshness_page
    assert 'class="registry-card freshness-dataset-card stale"' in freshness_page
    assert 'class="registry-card freshness-dataset-card fresh"' in freshness_page
    assert 'class="registry-card freshness-dataset-card unknown"' in freshness_page
    assert 'class="freshness-card-heading"' in freshness_page
    assert freshness_page.count('class="freshness-card-heading"') == len(card_statuses)
    assert "data-dataset-card" in freshness_page
    assert "data-search=" in freshness_page
    assert 'data-status="fresh"' in freshness_page
    assert 'data-status="stale"' in freshness_page
    assert 'id="dataset-search"' in freshness_page
    assert 'id="dataset-count"' in freshness_page
    assert 'data-freshness-count' in freshness_page
    assert 'data-freshness-count role="status" aria-live="polite" aria-atomic="true"' in freshness_page
    assert 'id="dataset-empty-state"' in freshness_page
    assert "Source queries" not in freshness_page
    assert "Fresh" in freshness_page
    assert "Stale" in freshness_page
    assert "Unknown" in freshness_page
    assert 'href="datasets/protocol_token_holders.html"' in freshness_page
    assert 'href="datasets/etherfi_protocol_token_tvl.html"' in freshness_page
    assert "Ether.fi Protocol Token Holders" in freshness_page
    assert "Ether.fi Protocol Token TVL" in freshness_page
    assert "table-pill" not in freshness_page
    assert "<span>Category</span>" not in freshness_page
    assert '<span class="meta-chip protocol"><span>Category</span>' not in freshness_page
    assert (
        '<span class="meta-chip interval"><span>Refresh</span>'
        "<strong>1h</strong></span>"
        in freshness_page
    )
    assert "<code>dune.ether_fi.result_" not in freshness_page
    assert "dune.ether_fi.result_etherfi_protocol_token_tvl" in freshness_page
    assert "Dataset used by the main ether.fi overview dashboard for protocol token TVL" not in freshness_page
    assert "Ether.fi Protocol Token TVLdune.ether_fi.result_etherfi_protocol_token_tvl" not in freshness_page
    assert "https://dune.com/queries/6213381" in freshness_page
    assert (
        'data-search="etherfi_protocol_token_holders ether.fi protocol token holders ether.fi protocol fresh protocol 6213381 '
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
    assert "Freshness status fresh; refreshed 1h ago; documented cadence 4h" in freshness_page
    assert "Freshness status stale; refreshed 2h 30m ago; documented cadence 1h" in freshness_page
    assert 'class="freshness-meter-marker"' not in freshness_page
    assert 'class="freshness-meter-caption"' not in freshness_page
    assert 'class="freshness-meter-track"' not in freshness_page
    assert 'class="freshness-meter-segment filled"' in freshness_page
    assert 'class="freshness-meter-label"' not in freshness_page
    freshness_card = re.search(
        r'<article class="registry-card freshness-dataset-card fresh".*?</article>',
        freshness_page,
        re.S,
    )
    assert freshness_card
    assert freshness_card.group(0).find('class="freshness-meter fresh"') < freshness_card.group(0).find(
        'class="status-badge freshness-badge fresh"'
    )
    assert freshness_card.group(0).find('class="status-badge freshness-badge fresh"') < freshness_card.group(0).find(
        'class="dune-action"'
    )
    assert (
        'class="status-badge freshness-badge fresh" '
        'aria-label="Fresh: Within the expected refresh interval."'
        in freshness_page
    )
    assert (
        'class="status-badge freshness-badge stale" '
        'aria-label="Stale: More than twice the expected refresh interval."'
        in freshness_page
    )
    assert (
        'class="status-badge freshness-badge unknown" '
        'aria-label="Unknown: No latest Dune snapshot has been imported yet."'
        in freshness_page
    )
    assert re.search(r'data-freshness-count[^>]*>\d+ of \d+ shown</span>', freshness_page)
    assert "Not documented yetNot documented yet" not in freshness_page
    assert '<span class="meta-chip updated" title="Not documented"><span>Last refreshed</span><strong>Not documented</strong></span>' in freshness_page
    assert "Next expected" not in freshness_page
    assert "No datasets match these filters." in freshness_page
    assert 'src="assets/freshness.js?v=' in freshness_page
    assert 'src="assets/freshness.js" defer' not in freshness_page
    assert freshness_page.find("Ether.fi Protocol Token TVL") < freshness_page.find(
        "Ether.fi Protocol Token Holders"
    )
    assert (tmp_path / "site" / "assets" / "freshness.js").exists()
    freshness_css = (tmp_path / "site" / "assets" / "styles.css").read_text(encoding="utf-8")
    assert ".freshness-summary" not in freshness_css
    assert ".freshness-meter-segment" in freshness_css


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
    catalog_ui_js = (tmp_path / "assets" / "catalog-ui.js").read_text(encoding="utf-8")

    assert 'src="assets/datasets.js?v=' in datasets_page
    assert 'src="assets/catalog-ui.js?v=' in datasets_page
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
    assert "activeNavForState" in datasets_js
    assert "selectCategory" in datasets_js
    assert "__etherfiDatasetBrowserDebug" in datasets_js
    assert "data-copy-text" in dataset_detail_js
    assert "data-copy-announcer" in dataset_detail_js
    assert 'dataset.datasetDetailMounted = "true"' in dataset_detail_js
    assert "window.CatalogUI.copyText" in dataset_detail_js
    assert "Copy failed" in dataset_detail_js
    assert "browserNavigator.clipboard.writeText" in catalog_ui_js
    assert "execCommand" in catalog_ui_js
    assert "data-catalog-search" in catalog_ui_js
    assert "data-search-clear" in catalog_ui_js


def test_catalog_indexes_keep_content_available_without_javascript(tmp_path):
    build_site(output_dir=tmp_path)

    datasets_page = (tmp_path / "datasets.html").read_text(encoding="utf-8")
    dashboards_page = (tmp_path / "dashboards.html").read_text(encoding="utf-8")
    dataset_detail = (tmp_path / "datasets" / "protocol_token_holders.html").read_text(
        encoding="utf-8"
    )
    dashboard_detail = (tmp_path / "dashboards" / "etherfi_overview.html").read_text(
        encoding="utf-8"
    )
    css = (tmp_path / "assets" / "styles.css").read_text(encoding="utf-8")

    dataset_sections = re.findall(
        r"<section\b[^>]*\bdata-dataset-category-section\b[^>]*>",
        datasets_page,
    )
    dashboard_sections = re.findall(
        r"<section\b[^>]*\bdata-dashboard-section\b[^>]*>",
        dashboards_page,
    )

    assert dataset_sections
    assert dashboard_sections
    assert any("data-default-hidden" in section for section in dataset_sections)
    assert any("data-default-hidden" in section for section in dashboard_sections)
    assert all(" hidden" not in section for section in dataset_sections)
    assert all(" hidden" not in section for section in dashboard_sections)
    assert "html[data-js] [data-default-hidden]" not in css
    assert (
        '[data-datasets-page]:not([data-datasets-mounted="true"]) '
        ".dataset-category-panel"
        in css
    )
    assert (
        '[data-dashboards-page]:not([data-dashboards-mounted="true"]) '
        ".dataset-browser-toolbar"
        in css
    )
    assert (
        '[data-freshness-page]:not([data-freshness-mounted="true"]) '
        ".catalog-toolbar"
        in css
    )
    assert 'html[data-catalog-ui-mounted="true"] .search-clear-button' in css
    assert re.search(
        r"\.copy-value-button\s*\{[^}]*display:\s*none;",
        css,
        re.S,
    )
    assert (
        'html[data-dataset-detail-mounted="true"] .copy-value-button' in css
    )
    assert 'html[data-mcp-mounted="true"] .snippet-copy-button' in css
    assert "<noscript>" in datasets_page
    assert "<noscript>" in dashboards_page
    for detail_html, panel_ids in [
        (dataset_detail, ["about", "schema", "related-resources"]),
        (dashboard_detail, ["metrics", "linked-datasets", "tags"]),
    ]:
        tab_list = re.search(r'<div class="detail-tab-list"[^>]*>', detail_html)
        assert tab_list
        assert " data-detail-tab-list hidden" in tab_list.group(0)
        assert 'role="tablist"' not in tab_list.group(0)
        for panel_id in panel_ids:
            panel = re.search(rf'<section id="{panel_id}"[^>]*>', detail_html)
            assert panel
            assert " hidden" not in panel.group(0)
            assert 'role="tabpanel"' not in panel.group(0)
            assert 'tabindex="' not in panel.group(0)


def test_generated_pages_have_single_h1_and_valid_detail_navigation_targets(tmp_path):
    build_site(output_dir=tmp_path)

    for relative_path in [
        "index.html",
        "datasets.html",
        "dashboards.html",
        "freshness.html",
        "mcp.html",
        "datasets/protocol_token_holders.html",
        "datasets/etherfi_addresses.html",
        "dashboards/etherfi_overview.html",
        "dashboards/liquid_vaults.html",
    ]:
        html = (tmp_path / relative_path).read_text(encoding="utf-8")
        assert len(re.findall(r"<h1(?:\s|>)", html)) == 1, relative_path

        section_nav = re.search(
            r'<nav class="detail-section-nav"[^>]*>(.*?)</nav>',
            html,
            re.S,
        )
        if not section_nav:
            continue
        fragment_ids = re.findall(r'href="#([^"]+)"', section_nav.group(1))
        assert len(fragment_ids) >= 2, relative_path
        for fragment_id in fragment_ids:
            assert html.count(f'id="{fragment_id}"') == 1, (
                relative_path,
                fragment_id,
            )


def test_catalog_ui_shortcuts_and_copy_fallback():
    node = shutil.which("node")
    if node is None:
        return

    script = """
let clipboardAttempted = false;
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: {
    clipboard: {
      writeText() {
        clipboardAttempted = true;
        return Promise.reject(new Error("clipboard unavailable"));
      },
    },
  },
});
Object.defineProperty(globalThis, "isSecureContext", {
  configurable: true,
  value: true,
});
const ui = require("./website/assets/catalog-ui.js");
let appended = false;
let removed = false;
let selected = false;
let copiedCommand = "";
let fallbackFocusRestored = false;
const textarea = {
  value: "",
  style: {},
  setAttribute() {},
  select() { selected = true; },
};
const scope = {
  activeElement: {
    focus() { fallbackFocusRestored = true; },
  },
  body: {
    appendChild(node) { appended = node === textarea; },
    removeChild(node) { removed = node === textarea; },
  },
  createElement(name) { return name === "textarea" ? textarea : null; },
  execCommand(command) {
    copiedCommand = command;
    return command === "copy";
  },
};

let inputEvent = null;
let inputFocused = false;
class FakeEvent {
  constructor(type, options) {
    this.type = type;
    this.bubbles = Boolean(options && options.bubbles);
  }
}
const input = {
  value: "oracle",
  ownerDocument: { defaultView: { Event: FakeEvent } },
  dispatchEvent(event) { inputEvent = event; },
  focus() { inputFocused = true; },
};
ui.clearSearch(input, true);

const hint = {
  attrs: {},
  open: false,
  classList: {
    toggle(name, enabled) {
      if (name === "is-open") hint.open = enabled;
    },
  },
  setAttribute(name, value) { this.attrs[name] = String(value); },
};
ui.setHintExpanded(hint, true);
const expandedHint = { open: hint.open, expanded: hint.attrs["aria-expanded"] };
ui.setHintExpanded(hint, false);
const otherHint = {
  attrs: {},
  open: true,
  classList: {
    toggle(name, enabled) {
      if (name === "is-open") otherHint.open = enabled;
    },
  },
  setAttribute(name, value) { this.attrs[name] = String(value); },
};
ui.setHintExpanded(hint, true);
ui.closeUnfocusedHints([hint, otherHint], {
  closest(selector) { return selector === "[data-info-hint]" ? hint : null; },
});
const focusMovedBetweenHints = {
  focusedOpen: hint.open,
  otherOpen: otherHint.open,
};
ui.closeUnfocusedHints([hint, otherHint], { closest() { return null; } });
const focusLeftHints = {
  focusedOpen: hint.open,
  otherOpen: otherHint.open,
};

ui.copyText("dune.ether_fi.result_example", scope).then((copied) => {
  console.log(JSON.stringify({
    copied,
    clipboardAttempted,
    copiedCommand,
    appended,
    removed,
    selected,
    fallbackFocusRestored,
    textareaValue: textarea.value,
    clearedValue: input.value,
    inputEvent: inputEvent && inputEvent.type,
    inputEventBubbles: inputEvent && inputEvent.bubbles,
    inputFocused,
    expandedHint,
    collapsedHint: { open: hint.open, expanded: hint.attrs["aria-expanded"] },
    focusMovedBetweenHints,
    focusLeftHints,
    slash: ui.shortcutAction({ key: "/" }, { hasSearch: true, editableTarget: false }),
    slashInInput: ui.shortcutAction({ key: "/" }, { hasSearch: true, editableTarget: true }),
    modifiedSlash: ui.shortcutAction(
      { key: "/", metaKey: true },
      { hasSearch: true, editableTarget: false }
    ),
    clear: ui.shortcutAction(
      { key: "Escape" },
      { activeSearch: true, searchHasValue: true }
    ),
    blur: ui.shortcutAction(
      { key: "Escape" },
      { activeSearch: true, searchHasValue: false }
    ),
    dismissHint: ui.shortcutAction(
      { key: "Escape" },
      { hintFocused: true, activeSearch: false }
    ),
    unrelated: ui.shortcutAction({ key: "Enter" }, { hasSearch: true }),
    inputEditable: ui.isEditableTarget({
      matches(selector) { return selector.includes("input"); },
    }),
    plainEditable: ui.isEditableTarget({ matches() { return false; } }),
  }));
});
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior == {
        "copied": True,
        "clipboardAttempted": True,
        "copiedCommand": "copy",
        "appended": True,
        "removed": True,
        "selected": True,
        "fallbackFocusRestored": True,
        "textareaValue": "dune.ether_fi.result_example",
        "clearedValue": "",
        "inputEvent": "input",
        "inputEventBubbles": True,
        "inputFocused": True,
        "expandedHint": {"open": True, "expanded": "true"},
        "collapsedHint": {"open": False, "expanded": "false"},
        "focusMovedBetweenHints": {"focusedOpen": True, "otherOpen": False},
        "focusLeftHints": {"focusedOpen": False, "otherOpen": False},
        "slash": "focus-search",
        "slashInInput": "none",
        "modifiedSlash": "none",
        "clear": "clear-search",
        "blur": "blur-search",
        "dismissHint": "dismiss-hint",
        "unrelated": "none",
        "inputEditable": True,
        "plainEditable": False,
    }


def test_catalog_ui_ignores_already_handled_keyboard_events():
    node = shutil.which("node")
    if node is None:
        return

    script = r"""
const ui = require("./website/assets/catalog-ui.js");
const listeners = {};
let blurred = false;
let preventedAgain = false;
const input = {
  disabled: false,
  hidden: false,
  value: "",
  matches(selector) {
    return (
      selector === "[data-catalog-search]" ||
      selector.includes("input")
    );
  },
  getClientRects() { return [{}]; },
  blur() {
    blurred = true;
    scope.activeElement = null;
  },
};
const scope = {
  activeElement: input,
  documentElement: { dataset: {} },
  querySelectorAll(selector) {
    return selector === "[data-catalog-search]" ? [input] : [];
  },
  addEventListener(type, listener) {
    (listeners[type] ||= []).push(listener);
  },
};

ui.mount(scope);
listeners.keydown[0]({
  key: "Escape",
  defaultPrevented: true,
  target: input,
  preventDefault() { preventedAgain = true; },
});

console.log(JSON.stringify({
  blurred,
  focused: scope.activeElement === input,
  preventedAgain,
  value: input.value,
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "blurred": False,
        "focused": True,
        "preventedAgain": False,
        "value": "",
    }


def test_catalog_ui_copy_text_covers_clipboard_and_fallback_paths():
    node = shutil.which("node")
    if node is None:
        return

    script = """
const ui = require("./website/assets/catalog-ui.js");

function installNavigator(value, secure = true) {
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value,
  });
  Object.defineProperty(globalThis, "isSecureContext", {
    configurable: true,
    value: secure,
  });
}

function makeScope(execResult) {
  const state = {
    appended: false,
    execCalls: 0,
    removed: false,
    selected: false,
  };
  const textarea = {
    value: "",
    style: {},
    setAttribute() {},
    select() { state.selected = true; },
  };
  return {
    state,
    scope: {
      body: {
        appendChild(node) { state.appended = node === textarea; },
        removeChild(node) { state.removed = node === textarea; },
      },
      createElement(name) { return name === "textarea" ? textarea : null; },
      execCommand(command) {
        state.execCalls += 1;
        return command === "copy" && execResult;
      },
    },
  };
}

(async () => {
  let successAttempts = 0;
  installNavigator({
    clipboard: {
      writeText() {
        successAttempts += 1;
        return Promise.resolve();
      },
    },
  });
  const successFallback = makeScope(true);
  const success = await ui.copyText("success", successFallback.scope);

  let rejectionAttempts = 0;
  installNavigator({
    clipboard: {
      writeText() {
        rejectionAttempts += 1;
        return Promise.reject(new Error("clipboard unavailable"));
      },
    },
  });
  const rejectionFallback = makeScope(true);
  const rejection = await ui.copyText("rejection", rejectionFallback.scope);

  installNavigator({});
  const unavailableFallback = makeScope(true);
  const unavailable = await ui.copyText("unavailable", unavailableFallback.scope);

  installNavigator({});
  const failedFallback = makeScope(false);
  const failed = await ui.copyText("failed", failedFallback.scope);

  console.log(JSON.stringify({
    success: {
      result: success,
      attempts: successAttempts,
      fallback: successFallback.state,
    },
    rejection: {
      result: rejection,
      attempts: rejectionAttempts,
      fallback: rejectionFallback.state,
    },
    unavailable: {
      result: unavailable,
      fallback: unavailableFallback.state,
    },
    failed: {
      result: failed,
      fallback: failedFallback.state,
    },
  }));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior == {
        "success": {
            "result": True,
            "attempts": 1,
            "fallback": {
                "appended": False,
                "execCalls": 0,
                "removed": False,
                "selected": False,
            },
        },
        "rejection": {
            "result": True,
            "attempts": 1,
            "fallback": {
                "appended": True,
                "execCalls": 1,
                "removed": True,
                "selected": True,
            },
        },
        "unavailable": {
            "result": True,
            "fallback": {
                "appended": True,
                "execCalls": 1,
                "removed": True,
                "selected": True,
            },
        },
        "failed": {
            "result": False,
            "fallback": {
                "appended": True,
                "execCalls": 1,
                "removed": True,
                "selected": True,
            },
        },
    }


def test_catalog_ui_detail_tabs_mount_keyboard_hash_and_fallback():
    node = shutil.which("node")
    if node is None:
        return

    script = r"""
globalThis.location = { hash: "" };
const historyCalls = [];
globalThis.history = {
  pushState(_state, _title, hash) {
    historyCalls.push(["push", hash]);
    globalThis.location.hash = hash;
  },
  replaceState(_state, _title, hash) {
    historyCalls.push(["replace", hash]);
    globalThis.location.hash = hash;
  },
};
const windowListeners = {};
globalThis.addEventListener = (type, listener) => {
  (windowListeners[type] ||= []).push(listener);
};

const ui = require("./website/assets/catalog-ui.js");
let focusedValue = "";
let activeNode = null;
const tabScrolls = [];

class FakeNode {
  constructor({ id = "", dataset = {}, hidden = false } = {}) {
    this.id = id;
    this.dataset = { ...dataset };
    this.hidden = hidden;
    this.attrs = {};
    this.listeners = {};
    this.classes = new Set();
    this.classList = {
      toggle: (name, enabled) => {
        if (enabled) this.classes.add(name);
        else this.classes.delete(name);
      },
    };
  }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  removeAttribute(name) { delete this.attrs[name]; }
  addEventListener(type, listener) {
    (this.listeners[type] ||= []).push(listener);
  }
  focus() {
    activeNode = this;
    focusedValue = this.dataset.detailTab || "";
  }
}

function makeGroup() {
  const values = ["about", "schema", "related-resources"];
  const tabs = values.map((value) => new FakeNode({
    id: `dataset-detail-tab-${value}`,
    dataset: {
      detailTab: value,
      detailTabControls: value,
    },
  }));
  const panels = values.map((value, index) => new FakeNode({
    id: value,
    dataset: {
      detailTabPanel: value,
      detailTabLabelledby: tabs[index].id,
      ...(value === "about" ? { emptyTabPanel: "true" } : {}),
    },
  }));
  panels.forEach((panel) => {
    panel.scrollIntoView = (options) => {
      tabScrolls.push({ id: panel.id, block: options.block });
    };
  });
  const tabList = new FakeNode({ hidden: true });
  const group = new FakeNode({
    dataset: {
      defaultTab: "schema",
      detailTabsLabel: "Dataset detail sections",
    },
  });
  group.ownerDocument = {
    get activeElement() { return activeNode; },
  };
  group.contains = (node) => tabs.includes(node) || panels.includes(node);
  group.querySelector = (selector) => selector === "[data-detail-tab-list]" ? tabList : null;
  group.querySelectorAll = (selector) => {
    if (selector === "[data-detail-tab]") return tabs;
    if (selector === "[data-detail-tab-panel]") return panels;
    if (selector === "[id]") return panels;
    return [];
  };
  return { group, panels, tabList, tabs, values };
}

const fixture = makeGroup();
const scope = {
  querySelectorAll(selector) {
    return selector === "[data-detail-tabs]" ? [fixture.group] : [];
  },
};
ui.mountDetailTabs(scope);

const mounted = {
  mounted: fixture.group.dataset.detailTabsMounted,
  active: fixture.group.dataset.activeTab,
  tabListHidden: fixture.tabList.hidden,
  tabListRole: fixture.tabList.attrs.role,
  tabListLabel: fixture.tabList.attrs["aria-label"],
  selected: fixture.tabs.map((tab) => tab.attrs["aria-selected"]),
  tabIndexes: fixture.tabs.map((tab) => tab.attrs.tabindex),
  panelHidden: fixture.panels.map((panel) => panel.hidden),
  panelRoles: fixture.panels.map((panel) => panel.attrs.role),
  panelIndexes: fixture.panels.map((panel) => panel.attrs.tabindex || null),
};

fixture.tabs[0].listeners.click[0]();
const clicked = {
  active: fixture.group.dataset.activeTab,
  activePanelTabIndex: fixture.panels[0].attrs.tabindex || null,
  hash: globalThis.location.hash,
  panelHidden: fixture.panels.map((panel) => panel.hidden),
};

let prevented = false;
fixture.tabs[0].listeners.keydown[0]({
  key: "End",
  preventDefault() { prevented = true; },
});
const keyboard = {
  active: fixture.group.dataset.activeTab,
  focusedValue,
  hash: globalThis.location.hash,
  prevented,
};

globalThis.location.hash = "#main-content";
windowListeners.hashchange[0]();
const ignoredSkipLinkHash = {
  active: fixture.group.dataset.activeTab,
  relatedHidden: fixture.panels[2].hidden,
};
const tabScrollsAfterKeyboard = [...tabScrolls];

globalThis.location.hash = "";
windowListeners.popstate[0]();
const returnedToDefault = {
  active: fixture.group.dataset.activeTab,
  focusedValue,
  schemaHidden: fixture.panels[1].hidden,
};

const invalid = makeGroup();
invalid.tabs[1].dataset.detailTab = "about";
ui.mountDetailTabs({
  querySelectorAll(selector) {
    return selector === "[data-detail-tabs]" ? [invalid.group] : [];
  },
});

let scrolledTo = null;
const scrollTarget = new FakeNode({ id: "related-resources" });
scrollTarget.scrollIntoView = (options) => {
  scrolledTo = { id: scrollTarget.id, block: options.block };
};
ui.scrollToTabHash({
  querySelectorAll(selector) {
    return selector === "[id]" ? [scrollTarget] : [];
  },
}, "#related-resources");

console.log(JSON.stringify({
  mounted,
  clicked,
  keyboard,
  ignoredSkipLinkHash,
  tabScrollsAfterKeyboard,
  returnedToDefault,
  historyCalls,
  aliases: {
    caveat: ui.tabValueForHash("#dataset-caveats", fixture.values),
    metrics: ui.tabValueForHash("#dashboard-metrics", ["metrics", "tags"]),
    invalid: ui.tabValueForHash("#not-a-tab", fixture.values),
  },
  keyIndexes: {
    rightWrap: ui.tabIndexForKey("ArrowRight", 2, 3),
    leftWrap: ui.tabIndexForKey("ArrowLeft", 0, 3),
    home: ui.tabIndexForKey("Home", 2, 3),
    end: ui.tabIndexForKey("End", 0, 3),
    ignored: ui.tabIndexForKey("Enter", 0, 3),
  },
  invalidFallback: {
    tabListHidden: invalid.tabList.hidden,
    mounted: invalid.group.dataset.detailTabsMounted || null,
    panelHidden: invalid.panels.map((panel) => panel.hidden),
    panelRoles: invalid.panels.map((panel) => panel.attrs.role || null),
  },
  scrolledTo,
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior["mounted"] == {
        "mounted": "true",
        "active": "schema",
        "tabListHidden": False,
        "tabListRole": "tablist",
        "tabListLabel": "Dataset detail sections",
        "selected": ["false", "true", "false"],
        "tabIndexes": ["-1", "0", "-1"],
        "panelHidden": [True, False, True],
        "panelRoles": ["tabpanel", "tabpanel", "tabpanel"],
        "panelIndexes": [None, "0", None],
    }
    assert behavior["clicked"] == {
        "active": "about",
        "activePanelTabIndex": None,
        "hash": "#about",
        "panelHidden": [False, True, True],
    }
    assert behavior["keyboard"] == {
        "active": "related-resources",
        "focusedValue": "related-resources",
        "hash": "#related-resources",
        "prevented": True,
    }
    assert behavior["ignoredSkipLinkHash"] == {
        "active": "related-resources",
        "relatedHidden": False,
    }
    assert behavior["tabScrollsAfterKeyboard"] == [
        {"id": "about", "block": "start"},
    ]
    assert behavior["returnedToDefault"] == {
        "active": "schema",
        "focusedValue": "schema",
        "schemaHidden": False,
    }
    assert behavior["historyCalls"] == [
        ["push", "#about"],
        ["replace", "#related-resources"],
    ]
    assert behavior["aliases"] == {
        "caveat": "about",
        "metrics": "metrics",
        "invalid": "",
    }
    assert behavior["keyIndexes"] == {
        "rightWrap": 0,
        "leftWrap": 2,
        "home": 0,
        "end": 2,
        "ignored": -1,
    }
    assert behavior["invalidFallback"] == {
        "tabListHidden": True,
        "mounted": None,
        "panelHidden": [False, False, False],
        "panelRoles": [None, None, None],
    }
    assert behavior["scrolledTo"] == {
        "id": "related-resources",
        "block": "start",
    }


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
const categoryState = { activeCategory: "activity", query: "prices" };
const categoryInput = { value: "prices" };
const activeNavDuringSearch = browser.activeNavForState(categoryState);
browser.selectCategory(categoryState, categoryInput, "prices");
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
  activeNavDuringSearch,
  selectedCategoryAfterClick: categoryState.activeCategory,
  activeNavAfterClick: browser.activeNavForState(categoryState),
  queryAfterClick: categoryState.query,
  inputAfterClick: categoryInput.value,
  fragments: {
    prices: browser.categoryFragment("prices"),
    lrt: browser.categoryFragment("lrt_restaking"),
    valid: browser.categoryForHash(
      "#dataset-view-lrt-restaking",
      ["overview", "prices", "lrt_restaking"],
    ),
    invalid: browser.categoryForHash(
      "#dataset-view-not-real",
      ["overview", "prices", "lrt_restaking"],
    ),
    emptyTarget: browser.categoryTargetForHash(
      "",
      ["overview", "prices", "lrt_restaking"],
    ),
    ownedTarget: browser.categoryTargetForHash(
      "#dataset-view-prices",
      ["overview", "prices", "lrt_restaking"],
    ),
    unrelatedTarget: browser.categoryTargetForHash(
      "#main-content",
      ["overview", "prices", "lrt_restaking"],
    ),
  },
  focusRestore: {
    categoryButton: browser.shouldRestoreCategoryFocus(
      categoryInput,
      [categoryInput],
    ),
    categoryContent: browser.shouldRestoreCategoryFocus(
      { closest(selector) { return selector.includes("dataset-category-section") ? {} : null; } },
      [],
    ),
    outside: browser.shouldRestoreCategoryFocus(
      { closest() { return null; } },
      [],
    ),
  },
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
        "activeNavDuringSearch": "",
        "selectedCategoryAfterClick": "prices",
        "activeNavAfterClick": "prices",
        "queryAfterClick": "",
        "inputAfterClick": "",
        "fragments": {
            "prices": "dataset-view-prices",
            "lrt": "dataset-view-lrt-restaking",
            "valid": "lrt_restaking",
            "invalid": "",
            "emptyTarget": "overview",
            "ownedTarget": "prices",
            "unrelatedTarget": None,
        },
        "focusRestore": {
            "categoryButton": True,
            "categoryContent": True,
            "outside": False,
        },
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
const groupState = { activeGroup: "cash", query: "liquid" };
const groupInput = { value: "liquid" };
const activeNavDuringSearch = browser.activeNavForState(groupState);
browser.selectGroup(groupState, groupInput, "liquid");
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
  activeNavDuringSearch,
  selectedGroupAfterClick: groupState.activeGroup,
  activeNavAfterClick: browser.activeNavForState(groupState),
  queryAfterClick: groupState.query,
  inputAfterClick: groupInput.value,
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
        "activeNavDuringSearch": "",
        "selectedGroupAfterClick": "liquid",
        "activeNavAfterClick": "liquid",
        "queryAfterClick": "",
        "inputAfterClick": "",
    }


def test_dashboard_browser_direct_hash_click_and_history_sync():
    node = shutil.which("node")
    if node is None:
        return

    script = r"""
globalThis.location = { hash: "#dashboard-group-cash" };
const historyCalls = [];
globalThis.history = {
  pushState(_state, _title, hash) {
    historyCalls.push(["push", hash]);
    globalThis.location.hash = hash;
  },
};
const windowListeners = {};
globalThis.addEventListener = (type, listener) => {
  (windowListeners[type] ||= []).push(listener);
};

const browser = require("./website/assets/dashboards.js");
function makeNode(dataset = {}) {
  const classes = new Set();
  return {
    dataset: { ...dataset },
    hidden: false,
    style: {},
    listeners: {},
    classes,
    textContent: "",
    value: "",
    classList: {
      toggle(name, enabled) {
        if (enabled) classes.add(name);
        else classes.delete(name);
      },
    },
    addEventListener(type, listener) {
      (this.listeners[type] ||= []).push(listener);
    },
    setAttribute() {},
    removeAttribute() {},
  };
}

const groups = ["core", "stake", "cash", "liquid", "others"];
const searchInput = makeNode();
const count = makeNode();
const emptyState = makeNode();
const navButtons = groups.map((group) => makeNode({ dashboardNav: group }));
const cards = groups.slice(1).map((group) => makeNode({
    dashboardCategory: group,
    search: {
      stake: "daily active stakers and deposits",
      cash: "daily active borrowers and cashback",
      liquid: "vault deposits and apy",
      others: "validator comparison",
    }[group],
}));
const coreCard = makeNode();
const sections = groups.map((group) => {
  const section = makeNode({ dashboardGroup: group });
  const sectionCount = makeNode();
  const sectionCards = group === "core"
    ? [coreCard]
    : [cards.find((card) => card.dataset.dashboardCategory === group)];
  section.querySelector = (selector) => (
    selector === ".dataset-view-count" ? sectionCount : null
  );
  section.querySelectorAll = () => sectionCards;
  return section;
});
const scrollCalls = [];
navButtons.forEach((button) => {
  button.scrollIntoView = (options) => {
    scrollCalls.push({
      type: "rail",
      group: button.dataset.dashboardNav,
      block: options.block,
      inline: options.inline || "",
    });
  };
});
sections.forEach((section) => {
  section.scrollIntoView = (options) => {
    scrollCalls.push({
      type: "group",
      group: section.dataset.dashboardGroup,
      block: options.block,
      inline: options.inline || "",
    });
  };
});
const page = makeNode();
page.querySelector = (selector) => {
  const controls = {
    "#dashboard-search": searchInput,
    "#dashboard-count": count,
    "#dashboard-empty-state": emptyState,
  };
  if (controls[selector]) return controls[selector];
  return sections.find(
    (section) => selector === `#dashboard-group-${section.dataset.dashboardGroup}`,
  ) || null;
};
page.querySelectorAll = (selector) => ({
  "[data-dashboard-card]": cards,
  "[data-dashboard-core-card]": [coreCard],
  "[data-dashboard-nav]": navButtons,
  "[data-dashboard-section]": sections,
}[selector] || []);
const scope = {
  activeElement: null,
  querySelector(selector) {
    return selector === "[data-dashboards-page]" ? page : null;
  },
};

function snapshot() {
  return {
    selected: globalThis.__etherfiDashboardBrowserDebug().selectedGroup,
    active: navButtons.find((button) => button.classes.has("active"))
      ?.dataset.dashboardNav || "",
    visible: sections
      .filter((section) => !section.hidden && section.style.display !== "none")
      .map((section) => section.dataset.dashboardGroup),
  };
}

browser.mount(scope);
const directHash = snapshot();
scrollCalls.length = 0;

searchInput.value = "daily active borrowers";
searchInput.listeners.input[0]();
const metricSearch = {
  ...snapshot(),
  query: globalThis.__etherfiDashboardBrowserDebug().query,
};

navButtons[3].listeners.click[0]();
const clicked = {
  ...snapshot(),
  input: searchInput.value,
  hash: globalThis.location.hash,
  historyCalls: [...historyCalls],
  scrollCalls: [...scrollCalls],
};
scrollCalls.length = 0;

searchInput.value = "vault deposits";
searchInput.listeners.input[0]();
globalThis.location.hash = "#dashboard-group-cash";
windowListeners.popstate[0]();
const returned = {
  ...snapshot(),
  input: searchInput.value,
};

globalThis.location.hash = "#dashboard-group-others";
windowListeners.hashchange[0]();
const forwarded = snapshot();

globalThis.location.hash = "#main-content";
windowListeners.hashchange[0]();
const unrelatedHash = snapshot();

globalThis.location.hash = "";
windowListeners.popstate[0]();
const emptyHash = snapshot();

console.log(JSON.stringify({
  directHash,
  metricSearch,
  clicked,
  returned,
  forwarded,
  unrelatedHash,
  emptyHash,
  listenerCounts: {
    hashchange: windowListeners.hashchange.length,
    popstate: windowListeners.popstate.length,
  },
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior["directHash"] == {
        "selected": "cash",
        "active": "cash",
        "visible": ["cash"],
    }
    assert behavior["metricSearch"] == {
        "selected": "cash",
        "active": "",
        "visible": ["cash"],
        "query": "daily active borrowers",
    }
    assert behavior["clicked"] == {
        "selected": "liquid",
        "active": "liquid",
        "input": "",
        "hash": "#dashboard-group-liquid",
        "visible": ["liquid"],
        "historyCalls": [["push", "#dashboard-group-liquid"]],
        "scrollCalls": [
            {
                "type": "rail",
                "group": "liquid",
                "block": "nearest",
                "inline": "nearest",
            },
            {
                "type": "group",
                "group": "liquid",
                "block": "start",
                "inline": "",
            },
        ],
    }
    assert behavior["returned"] == {
        "selected": "cash",
        "active": "cash",
        "visible": ["cash"],
        "input": "",
    }
    assert behavior["forwarded"] == {
        "selected": "others",
        "active": "others",
        "visible": ["others"],
    }
    assert behavior["unrelatedHash"] == {
        "selected": "others",
        "active": "others",
        "visible": ["others"],
    }
    assert behavior["emptyHash"] == {
        "selected": "core",
        "active": "core",
        "visible": ["core"],
    }
    assert behavior["listenerCounts"] == {
        "hashchange": 1,
        "popstate": 1,
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
assert(doc.count.textContent === `${total} of ${total} shown`, "Initial count did not match generated cards");
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
assert(!visibleCards().some((card) => card.textContent.includes("Ether.fi Protocol Token Holders")), "Non-contiguous dataset search should hide unrelated holders card");
assert(doc.count.textContent === `${visibleCards().length} of ${total} shown`, "Non-contiguous search count did not update");

search("protocol token tvl");
assert(visibleCards().length === 1, "Dataset search should show one card");
assert(visibleCards()[0].textContent.includes("Ether.fi Protocol Token TVL"), "Dataset search showed the wrong card");
assert(doc.count.textContent === `1 of ${total} shown`, "Dataset search count did not update");

search("6216803");
assert(visibleCards().length === 1, "Query ID search should show one card");
assert(visibleCards()[0].textContent.includes("Ether.fi Protocol Token TVL"), "Query ID search showed the wrong card");

search("https://dune.com/queries/6216803");
assert(visibleCards().length === 1, "Query URL search should show one card");

clickStatus("stale");
assert(visibleCards().length === 1, "Stale status + query search should show one card");

clickStatus("fresh");
assert(visibleCards().length === 0, "Fresh status + stale query search should show no cards");
assert(doc.count.textContent === `0 of ${total} shown`, "No-match count did not update");
assert(doc.empty.hidden === false, "Empty state should be visible when no cards match");

clickStatus("all");
assert(visibleCards().length === 1, "All status should restore current search results");

search("zzzz-no-match");
assert(visibleCards().length === 0, "Nonsense search should show no cards");
assert(doc.empty.hidden === false, "Nonsense search should show empty state");

search("");
assert(visibleCards().length === total, "Clearing search should restore all cards for All status");
assert(doc.count.textContent === `${total} of ${total} shown`, "Clearing search should restore count");
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
    assert behavior["finalCount"] == f'{behavior["total"]} of {behavior["total"]} shown'


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


def test_dataset_card_status_chip_uses_compact_overdue_duration():
    assert format_compact_duration(30) == "30m"
    assert format_compact_duration(50) == "50m"
    assert format_compact_duration(61) == "1hr"
    assert format_compact_duration(119) == "2hr"
    assert format_compact_duration(24 * 60) == "1d"
    assert format_compact_duration(48 * 60) == "2d"
    assert format_compact_duration(None) == ""

    assert dataset_card_status_label({"status": "fresh", "label": "Fresh"}) == "Fresh"
    assert dataset_card_status_label(
        {
            "status": "delayed",
            "label": "Delayed",
            "lag_minutes": 90,
            "refresh_interval_minutes": 60,
        }
    ) == "Delayed 30m"
    assert dataset_card_status_label(
        {
            "status": "stale",
            "label": "Stale",
            "lag_minutes": 3_000,
            "refresh_interval_minutes": 120,
        }
    ) == "Stale 2d"
    assert dataset_card_status_label({"status": "unknown", "label": "Unknown"}) == "Unknown"
    assert dataset_card_status_label({"status": "delayed", "label": "Delayed"}) == "Delayed"
    entry = next(
        entry for entry in load_dataset_entries() if entry.slug == "protocol_token_holders"
    )
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    registry = {
        entry.data["name"]: {
            "last_updated": (now - timedelta(minutes=270)).isoformat(),
            "query_id": entry.data["source_query_id"],
        }
    }
    card_html = render_compact_dataset_card(entry, registry, now=now)

    assert '<span class="dataset-card-status delayed">Delayed 30m</span>' in card_html
    assert "Refresh interval" not in card_html
    assert "Last refreshed" not in card_html


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
    assert "At a glance" not in detail_page
    detail_hero = re.search(
        r'<header class="dataset-detail-header">(.*?)</header>',
        detail_page,
        re.S,
    )
    assert detail_hero
    detail_glance = re.search(
        r'<div class="dataset-detail-hero-glance" role="group" '
        r'aria-label="Dataset metadata">(.*)</div>$',
        detail_hero.group(1),
        re.S,
    )
    assert detail_glance
    detail_glance_html = detail_glance.group(1)
    assert "Freshness &amp; Refresh Interval" in detail_glance_html
    assert "Freshness &amp; Interval" not in detail_glance_html
    assert '<div class="glance-value freshness-refresh-value">' in detail_glance_html
    assert (
        '<span class="freshness-status-pill status-unknown">Unknown</span>'
        in detail_glance_html
    )
    assert (
        '<span class="freshness-refresh-text">Not documented · Interval not documented</span>'
        in detail_glance_html
    )
    assert "Not documented · Interval not documented" in detail_glance_html
    assert "<span>Category</span>" not in detail_glance_html
    assert "<span>Query ready</span>" not in detail_glance_html
    assert "<span>Freshness column</span>" not in detail_glance_html
    assert "<span>Source query ID</span>" not in detail_glance_html
    assert "<span>Refresh interval</span>" not in detail_glance_html
    assert "What this dataset represents" not in detail_page
    assert "Methodology and Notes" in detail_page
    assert 'data-schema-filter' not in detail_page
    assert 'data-schema-row' not in detail_page
    assert (
        'class="dataset-glance-card full-table-name copyable-table-name"'
        in detail_glance_html
    )
    assert 'class="table-pill table-pill-block"' in detail_glance_html
    assert "Schema" in detail_page
    assert "Related resources" in detail_page
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
    assert "What this dataset represents" not in fallback_page
    assert "Methodology and Notes" in fallback_page
    fallback_methodology = re.search(
        r'<section id="about"[^>]*data-empty-tab-panel="true"></section>',
        fallback_page,
    )
    assert fallback_methodology


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
            local_href = href.split("#", 1)[0].split("?", 1)[0]
            target = (html_file.parent / local_href).resolve()
            assert target.exists(), f"{html_file.relative_to(tmp_path)} links to missing {href}"


def test_build_generates_complete_hashed_catalog_index_and_explore_page(tmp_path):
    build_site(output_dir=tmp_path)

    index_path = tmp_path / "assets" / "catalog-index.js"
    index_source = index_path.read_text(encoding="utf-8")
    payload_match = re.search(
        r"^// content-hash: ([a-f0-9]{64})\n"
        r"window\.ETHERFI_CATALOG_INDEX = (.*);\n"
        r'window\.ETHERFI_CATALOG_INDEX_HASH = "\1";\n$',
        index_source,
    )
    assert payload_match
    assert hashlib.sha256(payload_match.group(2).encode("utf-8")).hexdigest() == (
        payload_match.group(1)
    )

    resources = json.loads(payload_match.group(2))
    assert len(resources) == 60
    assert sum(resource["kind"] == "dataset" for resource in resources) == 39
    assert sum(resource["kind"] == "dashboard" for resource in resources) == 21
    assert all(
        set(resource) == {
            "kind",
            "title",
            "href",
            "category",
            "description",
            "searchText",
            "matchHints",
        }
        for resource in resources
    )
    assert all((tmp_path / resource["href"]).exists() for resource in resources)
    assert [resource["title"] for resource in resources[:8]] == [
        "Ether.fi Assets Under Management",
        "Ether.fi Cash Events",
        "Ether.fi Protocol Token TVL",
        "Tokens Traits",
        "ether.fi",
        "ether.fi Users",
        "ether.fi Cash",
        "Liquid Vaults",
    ]

    dataset_resource = next(
        resource
        for resource in resources
        if resource["title"] == "Ether.fi Protocol Token Holders"
    )
    assert "dune.ether_fi.result_etherfi_protocol_token_holders" in (
        dataset_resource["searchText"]
    )
    assert "6213381" in dataset_resource["searchText"]
    assert any(
        "address varbinary holder wallet or contract address" in hint.lower()
        for hint in dataset_resource["matchHints"]
    )
    assert any(
        "token_balance double direct token balance at the snapshot" in hint.lower()
        for hint in dataset_resource["matchHints"]
    )

    dashboard_resource = next(
        resource
        for resource in resources
        if resource["title"] == "ether.fi Cash"
    )
    assert "total cash spend volume" in dashboard_resource["searchText"]
    assert "dune.ether_fi.result_etherfi_cash_events" in (
        dashboard_resource["searchText"]
    )
    assert any(
        hint == "Total Cash Spend Volume"
        for hint in dashboard_resource["matchHints"]
    )

    explore_html = (tmp_path / "explore.html").read_text(encoding="utf-8")
    assert len(re.findall(r"<h1(?:\s|>)", explore_html)) == 1
    assert "<h1 id=\"explore-page-title\">Explore the catalog</h1>" in explore_html
    assert explore_html.count("data-explore-card ") == 60
    assert explore_html.count('data-resource-kind="dataset"') == 39
    assert explore_html.count('data-resource-kind="dashboard"') == 21
    assert (
        "JavaScript, so every catalog resource is shown below."
        in explore_html
    )
    assert all(
        f'href="{resource["href"]}"' in explore_html
        for resource in resources
    )
    card_bodies = re.findall(
        r'<article class="explore-resource-card"[^>]*>(.*?)</article>',
        explore_html,
        re.S,
    )
    assert len(card_bodies) == 60
    assert all(" hidden" not in body for body in card_bodies)
    assert all("dune.ether_fi." not in body for body in card_bodies)
    assert all("Last refreshed" not in body for body in card_bodies)
    assert all("catalog datasets" not in body for body in card_bodies)
    dataset_card = re.search(
        r'<article class="explore-resource-card"[^>]*'
        r'data-search="([^"]*token_balance[^"]*)"[^>]*>.*?'
        r'href="datasets/protocol_token_holders.html"',
        explore_html,
        re.S,
    )
    assert dataset_card
    dashboard_card = re.search(
        r'<article class="explore-resource-card"[^>]*'
        r'data-search="([^"]*total cash spend volume[^"]*)"[^>]*>.*?'
        r'href="dashboards/etherfi_cash.html"',
        explore_html,
        re.S,
    )
    assert dashboard_card
    assert '<script src="assets/explore.js?v=' in explore_html

    asset_version = hashlib.sha256(index_path.read_bytes()).hexdigest()[:12]
    assert f'assets/catalog-index.js?v={asset_version}' in explore_html


def test_catalog_index_serialization_escapes_script_unsafe_content():
    source = serialize_catalog_index(
        [
            {
                "kind": "dataset",
                "title": "</script><script>alert(1)</script>",
                "href": "datasets/example.html",
                "category": "A&B",
                "description": "line\u2028separator\u2029end",
                "searchText": "",
                "matchHints": [],
            }
        ]
    )

    assert "</script>" not in source
    assert "<script>" not in source
    assert "\\u003c/script\\u003e" in source
    assert "\\u0026" in source
    assert "\\u2028" in source
    assert "\\u2029" in source
    assert "\u2028" not in source
    assert "\u2029" not in source


def test_global_search_shell_keeps_primary_nav_and_nested_fallbacks(tmp_path):
    build_site(output_dir=tmp_path)

    root_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    explore_html = (tmp_path / "explore.html").read_text(encoding="utf-8")
    nested_html = (
        tmp_path / "datasets" / "protocol_token_holders.html"
    ).read_text(encoding="utf-8")

    desktop_nav = re.search(
        r'<nav class="site-nav site-nav-desktop"[^>]*>(.*?)</nav>',
        root_html,
        re.S,
    )
    assert desktop_nav
    assert desktop_nav.group(1).count('class="nav-link') == 6
    assert "Explore" not in desktop_nav.group(1)

    for html, prefix in [(root_html, ""), (nested_html, "../")]:
        assert html.count('class="catalog-command-dialog"') == 1
        assert (
            f'<a class="site-search-trigger" href="{prefix}explore.html"'
            in html
        )
        assert 'aria-label="Search catalog"' in html
        assert "data-catalog-search-open" in html
        assert ">Search catalog</span>" in html
        assert 'aria-keyshortcuts="Meta+K Control+K"' in html
        assert f'data-catalog-site-root="{prefix}"' in html
        assert 'data-catalog-command-input' in html
        assert 'data-catalog-command-close' in html
        assert 'data-catalog-command-count role="status"' in html
        assert 'data-catalog-command-results' in html
        assert 'data-catalog-command-empty hidden' in html
        assert "Results include schema columns and dashboard metrics." in html
        index_script = f'src="{prefix}assets/catalog-index.js?v='
        search_script = f'src="{prefix}assets/global-search.js?v='
        assert index_script in html
        assert search_script in html
        assert html.index(index_script) < html.index(search_script)

    explore_trigger = re.search(
        r'<a class="site-search-trigger"[^>]*aria-current="page"[^>]*'
        r'aria-label="Search catalog"',
        explore_html,
    )
    assert explore_trigger


def test_explore_and_global_search_pure_helpers_cover_filter_url_and_prefix_behavior():
    node = shutil.which("node")
    if node is None:
        return

    script = r"""
const explore = require("./website/assets/explore.js");
const globalSearch = require("./website/assets/global-search.js");

const resources = [
  {
    kind: "dataset",
    title: "Holder balances",
    search: "protocol holder wallet contract address varbinary balance",
  },
  {
    kind: "dataset",
    title: "Token prices",
    search: "daily token price usd double",
  },
  {
    kind: "dashboard",
    title: "Cash",
    search: "total cash spend volume cashback active cards",
  },
];

function fakeElement(tagName) {
  return {
    tagName,
    attrs: {},
    children: [],
    className: "",
    textContent: "",
    setAttribute(name, value) {
      this.attrs[name] = String(value);
    },
    appendChild(child) {
      this.children.push(child);
    },
  };
}
const ownerDocument = {
  createElement(tagName) {
    return fakeElement(tagName);
  },
};
const plainResult = globalSearch.createResult(
  ownerDocument,
  { kind: "dataset", title: "A", href: "datasets/a.html" },
  "",
);
const nestedResult = globalSearch.createResult(
  ownerDocument,
  { kind: "dataset", title: "A", href: "datasets/a.html" },
  "",
  "../",
);

console.log(JSON.stringify({
  andMatch: explore.filterResources(resources, {
    kind: "all",
    query: "wallet protocol",
  }).map((resource) => resource.title),
  andMiss: explore.filterResources(resources, {
    kind: "all",
    query: "wallet volume",
  }).map((resource) => resource.title),
  typeMatch: explore.filterResources(resources, {
    kind: "dashboards",
    query: "cash volume",
  }).map((resource) => resource.title),
  parsed: explore.stateFromLocation({
    search: "?q=holder+wallet",
    hash: "#datasets",
  }),
  updatedUrl: explore.urlForState(
    { query: "cash volume", kind: "dashboard" },
    {
      pathname: "/explore.html",
      search: "?view=compact&q=old",
      hash: "#datasets",
    },
  ),
  clearedUrl: explore.urlForState(
    { query: "", kind: "all" },
    {
      pathname: "/explore.html",
      search: "?view=compact&q=old",
      hash: "#dashboards",
    },
  ),
  hashes: [
    explore.hashForKind("dataset"),
    explore.hashForKind("dashboards"),
    explore.kindFromHash("#datasets"),
    explore.kindFromHash("#dashboards"),
  ],
  catalogHashes: [
    explore.isCatalogHash(""),
    explore.isCatalogHash("#datasets"),
    explore.isCatalogHash("#dashboards"),
    explore.isCatalogHash("#main-content"),
  ],
  countLabels: [
    explore.resultCountLabel(60, 60, false),
    explore.resultCountLabel(2, 60, true),
  ],
  shortcuts: [
    explore.isSearchShortcut({ key: "/", target: { tagName: "DIV" } }),
    explore.isSearchShortcut({ key: "/", target: { tagName: "INPUT" } }),
  ],
  emptyHint: globalSearch.bestMatchingHint(
    { matchHints: ["wallet_address varbinary"] },
    "",
  ),
  hrefs: {
    plainHelper: globalSearch.prefixResourceHref("datasets/a.html", ""),
    nestedHelper: globalSearch.prefixResourceHref("datasets/a.html", "../"),
    external: globalSearch.prefixResourceHref("https://dune.com/x", "../"),
    plainResult: plainResult.attrs.href,
    nestedResult: nestedResult.attrs.href,
  },
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    behavior = json.loads(result.stdout)

    assert behavior == {
        "andMatch": ["Holder balances"],
        "andMiss": [],
        "typeMatch": ["Cash"],
        "parsed": {"kind": "dataset", "query": "holder wallet"},
        "updatedUrl": (
            "/explore.html?view=compact&q=cash+volume#dashboards"
        ),
        "clearedUrl": "/explore.html?view=compact",
        "hashes": [
            "#datasets",
            "#dashboards",
            "dataset",
            "dashboard",
        ],
        "catalogHashes": [True, True, True, False],
        "countLabels": [
            "60 resources",
            "2 of 60 resources",
        ],
        "shortcuts": [True, False],
        "emptyHint": "",
        "hrefs": {
            "plainHelper": "datasets/a.html",
            "nestedHelper": "../datasets/a.html",
            "external": "https://dune.com/x",
            "plainResult": "datasets/a.html",
            "nestedResult": "../datasets/a.html",
        },
    }

    explore_source = Path("website/assets/explore.js").read_text(encoding="utf-8")
    assert '"replaceState"' in explore_source
    assert '"pushState"' in explore_source
    assert '"popstate"' in explore_source
    assert '"hashchange"' in explore_source


def test_explore_history_ignores_unrelated_hash_and_restores_hidden_card_focus():
    node = shutil.which("node")
    if node is None:
        return

    script = r"""
const explore = require("./website/assets/explore.js");

function makeNode(attributes = {}) {
  const node = {
    attrs: { ...attributes },
    hidden: false,
    listeners: {},
    textContent: "",
    value: "",
    classes: new Set(),
    classList: {
      toggle(name, enabled) {
        if (enabled) node.classes.add(name);
        else node.classes.delete(name);
      },
    },
    getAttribute(name) { return this.attrs[name] ?? null; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    addEventListener(type, listener) {
      (this.listeners[type] ||= []).push(listener);
    },
  };
  return node;
}

let focused = "";
const datasetCard = makeNode({
  "data-resource-kind": "dataset",
  "data-search": "dataset token prices daily usd",
});
const dashboardCard = makeNode({
  "data-resource-kind": "dashboard",
  "data-search": "dashboard cash volume spend",
});
const cards = [datasetCard, dashboardCard];
const input = makeNode();
input.focus = () => {
  focused = "search";
  scope.activeElement = input;
};
const clear = makeNode();
const count = makeNode();
const empty = makeNode();
const filters = ["all", "dataset", "dashboard"].map((kind) => {
  const button = makeNode({ "data-explore-filter": kind });
  button.focus = () => {
    focused = kind;
    scope.activeElement = button;
  };
  return button;
});
const page = makeNode({ "data-explore-mounted": "" });
page.querySelector = (selector) => ({
  "[data-explore-search]": input,
  "[data-explore-clear]": clear,
  "[data-explore-count]": count,
  "[data-explore-empty]": empty,
}[selector] || null);
page.querySelectorAll = (selector) => ({
  "[data-explore-card]": cards,
  "[data-explore-filter]": filters,
}[selector] || []);

const listeners = {};
const host = {
  location: {
    pathname: "/explore.html",
    search: "",
    hash: "#dashboards",
  },
  history: {
    pushState() {},
    replaceState() {},
  },
  addEventListener(type, listener) {
    (listeners[type] ||= []).push(listener);
  },
};
const scope = {
  activeElement: null,
  querySelector(selector) {
    return selector === "[data-explore-page]" ? page : null;
  },
  addEventListener() {},
};

const controller = explore.mount(scope, host);
const mounted = {
  state: controller.state(),
  hidden: cards.map((card) => card.hidden),
};

const focusedDashboardLink = {
  closest(selector) {
    return selector === "[data-explore-card]" ? dashboardCard : null;
  },
};
scope.activeElement = focusedDashboardLink;
host.location.hash = "#datasets";
listeners.popstate[0]();
const returnedToDatasets = {
  state: controller.state(),
  focused,
  hidden: cards.map((card) => card.hidden),
};

host.location.search = "?q=should-not-apply";
host.location.hash = "#main-content";
listeners.popstate[0]();
const unrelatedHash = {
  state: controller.state(),
  focused,
  hidden: cards.map((card) => card.hidden),
};

console.log(JSON.stringify({
  mounted,
  returnedToDatasets,
  unrelatedHash,
}));
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == {
        "mounted": {
            "state": {"kind": "dashboard", "query": ""},
            "hidden": [True, False],
        },
        "returnedToDatasets": {
            "state": {"kind": "dataset", "query": ""},
            "focused": "dataset",
            "hidden": [False, True],
        },
        "unrelatedHash": {
            "state": {"kind": "dataset", "query": ""},
            "focused": "dataset",
            "hidden": [False, True],
        },
    }
