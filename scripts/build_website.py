from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import math
from pathlib import Path
import re
import shutil
from string import Template

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "website"
DEFAULT_OUTPUT_DIR = ROOT / "output" / "website"
DEFAULT_DATASETS_DIR = ROOT / "datasets"
DEFAULT_DASHBOARD_REGISTRY = ROOT / "dashboards"
DEFAULT_FRESHNESS_REGISTRY = ROOT / "status" / "dataset_freshness.yaml"
OBSOLETE_PAGE_OUTPUT_NAMES = {"agent-workflow.html"}
NOT_DOCUMENTED = "Not documented yet"
FRESHNESS_NOT_DOCUMENTED = "Not documented"
FRESHNESS_DASH = "&mdash;"


@dataclass(frozen=True)
class Page:
    source_path: Path
    slug: str
    title: str
    nav_label: str
    description: str
    order: int
    body: str
    body_format: str
    body_class: str

    @property
    def output_name(self) -> str:
        return "index.html" if self.slug == "index" else f"{self.slug}.html"


@dataclass(frozen=True)
class DatasetEntry:
    source_path: Path
    slug: str
    category: str
    data: dict


@dataclass(frozen=True)
class DashboardEntry:
    source_path: Path
    slug: str
    category: str
    data: dict


@dataclass(frozen=True)
class MCPToolInfo:
    name: str
    description: str
    parameters: tuple[str, ...]

    @property
    def live_capable(self) -> bool:
        return "execute_live" in self.parameters and self.name != "plan_etherfi_query"


def parse_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text

    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter) or {}, body.lstrip()


def slug_from_path(path: Path) -> str:
    return path.stem


def page_output_name_from_metadata(path: Path, metadata: dict) -> str:
    slug = str(metadata.get("slug") or slug_from_path(path))
    return "index.html" if slug == "index" else f"{slug}.html"


def unpublished_page_output_names(source_dir: Path = DEFAULT_SOURCE_DIR) -> set[str]:
    pages_dir = Path(source_dir) / "pages"
    output_names: set[str] = set()
    for path in sorted(pages_dir.glob("*.md")):
        metadata, _ = parse_frontmatter(path)
        if metadata.get("published") is False:
            output_names.add(page_output_name_from_metadata(path, metadata))
    return output_names


def load_pages(source_dir: Path = DEFAULT_SOURCE_DIR) -> list[Page]:
    pages: list[Page] = []
    pages_dir = source_dir / "pages"

    for path in sorted(pages_dir.glob("*.md")):
        metadata, body = parse_frontmatter(path)
        if metadata.get("published") is False:
            continue
        slug = str(metadata.get("slug") or slug_from_path(path))
        title = str(metadata.get("title") or slug.replace("-", " ").title())
        nav_label = str(metadata.get("nav_label") or title)
        pages.append(
            Page(
                source_path=path,
                slug=slug,
                title=title,
                nav_label=nav_label,
                description=str(metadata.get("description") or ""),
                order=int(metadata.get("order") or 100),
                body=body,
                body_format=str(metadata.get("format") or "markdown"),
                body_class=str(metadata.get("body_class") or ""),
            )
        )

    return sorted(pages, key=lambda page: (page.order, page.nav_label))


def render_inline_markdown(text: str) -> str:
    text = escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def flush_paragraph(paragraph_lines: list[str], output: list[str]) -> None:
    if not paragraph_lines:
        return
    paragraph = " ".join(line.strip() for line in paragraph_lines)
    output.append(f"<p>{render_inline_markdown(paragraph)}</p>")
    paragraph_lines.clear()


def render_markdown(markdown: str) -> str:
    output: list[str] = []
    paragraph_lines: list[str] = []
    list_open = False
    in_code = False
    code_lines: list[str] = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            output.append("</ul>")
            list_open = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            flush_paragraph(paragraph_lines, output)
            close_list()
            if in_code:
                output.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            flush_paragraph(paragraph_lines, output)
            close_list()
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            flush_paragraph(paragraph_lines, output)
            close_list()
            level = len(heading_match.group(1)) + 1
            output.append(f"<h{level}>{render_inline_markdown(heading_match.group(2))}</h{level}>")
            continue

        if line.startswith("- "):
            flush_paragraph(paragraph_lines, output)
            if not list_open:
                output.append("<ul>")
                list_open = True
            output.append(f"<li>{render_inline_markdown(line[2:])}</li>")
            continue

        if line.startswith("> "):
            flush_paragraph(paragraph_lines, output)
            close_list()
            output.append(f'<blockquote>{render_inline_markdown(line[2:])}</blockquote>')
            continue

        paragraph_lines.append(line)

    flush_paragraph(paragraph_lines, output)
    close_list()
    if in_code:
        output.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")

    return "\n".join(output)


def render_page_body(page: Page) -> str:
    if page.body_format == "html":
        return page.body
    return render_markdown(page.body)


def render_nav(pages: list[Page], active_slug: str, link_prefix: str = "") -> str:
    links = []
    for page in pages:
        active = " active" if page.slug == active_slug else ""
        href = f"{link_prefix}{page.output_name}"
        links.append(
            f'<a class="nav-link{active}" href="{href}">{escape(page.nav_label)}</a>'
        )
    return "\n".join(links)


def render_page(
    page: Page,
    pages: list[Page],
    template: Template,
    *,
    active_slug: str | None = None,
    link_prefix: str = "",
    asset_prefix: str = "",
) -> str:
    return template.safe_substitute(
        title=escape(page.title),
        description=escape(page.description),
        body_class=escape(page.body_class),
        asset_prefix=asset_prefix,
        nav=render_nav(pages, active_slug or page.slug, link_prefix=link_prefix),
        content=render_page_body(page),
    )


def render_generated_page(
    *,
    title: str,
    description: str,
    content: str,
    pages: list[Page],
    template: Template,
    active_slug: str,
    link_prefix: str = "",
    asset_prefix: str = "",
    body_class: str = "",
) -> str:
    return template.safe_substitute(
        title=escape(title),
        description=escape(description),
        body_class=escape(body_class),
        asset_prefix=asset_prefix,
        nav=render_nav(pages, active_slug, link_prefix=link_prefix),
        content=content,
    )


def copy_assets(source_dir: Path, output_dir: Path) -> None:
    assets_dir = source_dir / "assets"
    if not assets_dir.exists():
        return

    target_dir = output_dir / "assets"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(assets_dir, target_dir)


def asset_cache_version(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def titleize_category(category: str) -> str:
    special = {
        "etherfi_protocol": "Ether.fi Protocol",
        "lrt_restaking": "LRT / Restaking",
    }
    return special.get(category, category.replace("_", " ").title())


CATEGORY_ORDER = [
    "activity",
    "etherfi_protocol",
    "prices",
    "metadata",
    "lrt_restaking",
]

DASHBOARD_CATEGORY_ORDER = [
    "stake",
    "cash",
    "liquid",
    "others",
]

DASHBOARD_DISPLAY_GROUPS = [
    "core",
    *DASHBOARD_CATEGORY_ORDER,
]


MCP_TOOL_GROUPS = [
    {
        "title": "Catalog discovery",
        "description": "Find the right documented dataset or dashboard before anyone writes SQL.",
        "tools": [
            "search_datasets",
            "get_dataset_details",
            "compare_datasets",
            "search_dashboards",
            "get_dashboard_details",
        ],
    },
    {
        "title": "Freshness and status",
        "description": "Inspect freshness, dashboard-linked warnings, and catalog health.",
        "tools": [
            "get_dataset_status",
            "list_stale_datasets",
            "get_dashboard_status",
            "get_catalog_health_summary",
        ],
    },
    {
        "title": "Query planning",
        "description": "Return safe query plans, caveats, filters, and starter DuneSQL without executing.",
        "tools": [
            "plan_etherfi_query",
        ],
    },
    {
        "title": "Cash live tools",
        "description": "Answer narrow ether.fi Cash questions when live execution is enabled.",
        "tools": [
            "get_cash_events",
            "get_cash_holdings_timeseries",
            "get_cash_safe_profile",
            "get_cash_token_totals",
            "get_top_cash_users",
            "get_assets_under_management_balances",
        ],
    },
    {
        "title": "Protocol live tools",
        "description": "Inspect protocol TVL, holders, and protocol events through scoped tools.",
        "tools": [
            "get_protocol_token_holders",
            "get_protocol_events",
            "get_protocol_token_tvl",
            "get_protocol_token_tvl_timeseries",
        ],
    },
    {
        "title": "Price coverage tools",
        "description": "Resolve token price candidates and diagnose enriched price coverage.",
        "tools": [
            "find_price_tokens",
            "get_token_price",
            "get_token_price_by_symbol",
            "get_token_prices_batch",
            "diagnose_token_price_coverage",
        ],
    },
]


def category_sort_key(item: tuple[str, list["DatasetEntry"]] | str) -> tuple[int, str]:
    category = item[0] if isinstance(item, tuple) else item
    if category in CATEGORY_ORDER:
        return (CATEGORY_ORDER.index(category), titleize_category(category).lower())
    return (len(CATEGORY_ORDER), titleize_category(category).lower())


def normalize_dashboard_category(value) -> str:
    category = str(value or "others").strip().lower().replace("-", "_")
    return category if category in DASHBOARD_CATEGORY_ORDER else "others"


def titleize_dashboard_category(category: str) -> str:
    labels = {
        "core": "Core",
        "stake": "Stake",
        "cash": "Cash",
        "liquid": "Liquid",
        "others": "Others",
    }
    return labels.get(category, str(category).replace("_", " ").title())


def dashboard_group_sort_key(category: str) -> tuple[int, str]:
    if category in DASHBOARD_DISPLAY_GROUPS:
        return (DASHBOARD_DISPLAY_GROUPS.index(category), titleize_dashboard_category(category))
    return (len(DASHBOARD_DISPLAY_GROUPS), titleize_dashboard_category(category))


def dataset_slug(path: Path, data: dict) -> str:
    raw_slug = str(data.get("slug") or path.stem or data.get("name") or "dataset")
    return re.sub(r"[^a-z0-9_-]+", "-", raw_slug.lower()).strip("-") or "dataset"


def generic_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-") or "item"


def load_dataset_entries(datasets_dir: Path = DEFAULT_DATASETS_DIR) -> list[DatasetEntry]:
    datasets_dir = Path(datasets_dir)
    raw_entries: list[tuple[Path, str, dict]] = []

    for path in sorted(datasets_dir.glob("**/*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not data.get("name"):
            continue
        category = path.parent.relative_to(datasets_dir).parts[0] if path.parent != datasets_dir else "other"
        raw_entries.append((path, category, data))

    slug_counts: dict[str, int] = {}
    for path, _, data in raw_entries:
        slug = dataset_slug(path, data)
        slug_counts[slug] = slug_counts.get(slug, 0) + 1

    entries: list[DatasetEntry] = []
    for path, category, data in raw_entries:
        slug = dataset_slug(path, data)
        if slug_counts[slug] > 1:
            slug = f"{category}-{slug}"
        entries.append(
            DatasetEntry(
                source_path=path,
                slug=slug,
                category=category,
                data=data,
            )
        )

    return sorted(
        entries,
        key=lambda entry: (
            titleize_category(entry.category),
            str(entry.data.get("display_name") or entry.data.get("name")),
        ),
    )


def is_subtable_entry(entry: DatasetEntry) -> bool:
    return bool(entry.data.get("is_subtable"))


def hide_from_dataset_index(entry: DatasetEntry) -> bool:
    return bool(entry.data.get("hide_from_dataset_index") or is_subtable_entry(entry))


def hide_from_dataset_search(entry: DatasetEntry) -> bool:
    return bool(entry.data.get("hide_from_dataset_search") or is_subtable_entry(entry))


def visible_dataset_entries(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    return [entry for entry in entries if not hide_from_dataset_index(entry)]


def normalize_dashboard_data(data: dict, *, source_path: Path, category: str | None = None) -> dict:
    normalized = dict(data)
    normalized["category"] = normalize_dashboard_category(normalized.get("category") or category)
    normalized["tags"] = list(normalized.get("tags") or [])
    normalized["datasets"] = list(normalized.get("datasets") or [])
    normalized["show_in_core"] = bool(
        normalized.get("show_in_core")
        or normalized.get("featured")
        or normalized.get("core")
    )
    normalized["source_path"] = display_path(source_path)
    return normalized


def dashboard_entry_from_data(data: dict, *, source_path: Path, category: str | None = None) -> DashboardEntry | None:
    name = data.get("name")
    if not name:
        return None
    normalized = normalize_dashboard_data(data, source_path=source_path, category=category)
    return DashboardEntry(
        source_path=source_path,
        slug=generic_slug(str(name)),
        category=normalized["category"],
        data=normalized,
    )


def load_dashboard_yaml_file(path: Path, *, category: str | None = None) -> list[DashboardEntry]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    dashboards = data.get("dashboards") if isinstance(data, dict) else None
    entries: list[DashboardEntry] = []

    if isinstance(dashboards, list):
        for dashboard in dashboards:
            if not isinstance(dashboard, dict):
                continue
            entry = dashboard_entry_from_data(dashboard, source_path=path, category=category)
            if entry:
                entries.append(entry)
        return entries

    if isinstance(data, dict):
        entry = dashboard_entry_from_data(data, source_path=path, category=category)
        if entry:
            entries.append(entry)
    return entries


def dashboard_entry_sort_key(entry: DashboardEntry) -> tuple[int, str]:
    return (
        dashboard_group_sort_key(entry.category)[0],
        dashboard_title(entry).lower(),
    )


def load_dashboard_entries(registry_path: Path = DEFAULT_DASHBOARD_REGISTRY) -> list[DashboardEntry]:
    registry_path = Path(registry_path)
    entries_by_name: dict[str, DashboardEntry] = {}

    def add_entry(entry: DashboardEntry) -> None:
        name = str(entry.data.get("name") or "")
        if name and name not in entries_by_name:
            entries_by_name[name] = entry

    if registry_path.is_dir():
        for path in sorted(registry_path.glob("*/*.yaml")):
            category = path.parent.name
            for entry in load_dashboard_yaml_file(path, category=category):
                add_entry(entry)

        legacy_registry_path = registry_path / "registry.yaml"
        if legacy_registry_path.exists():
            for entry in load_dashboard_yaml_file(legacy_registry_path):
                add_entry(entry)
    elif registry_path.exists():
        for entry in load_dashboard_yaml_file(registry_path):
            add_entry(entry)

    return sorted(entries_by_name.values(), key=dashboard_entry_sort_key)


def load_freshness_registry(registry_path: Path = DEFAULT_FRESHNESS_REGISTRY) -> dict:
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return {}
    return yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}


def count_mcp_tools(server_path: Path = ROOT / "etherfi_catalog" / "server.py") -> int:
    server_path = Path(server_path)
    if not server_path.exists():
        return 0
    return len(re.findall(r"@server\.tool\(", server_path.read_text(encoding="utf-8")))


def mcp_tool_name_from_decorator(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute) or decorator.func.attr != "tool":
        return None
    for keyword in decorator.keywords:
        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return None


def extract_mcp_tools(server_path: Path = ROOT / "etherfi_catalog" / "server.py") -> dict[str, MCPToolInfo]:
    """Read the local MCP server and return the tools currently registered there."""
    server_path = Path(server_path)
    if not server_path.exists():
        return {}
    tree = ast.parse(server_path.read_text(encoding="utf-8"))
    tools: dict[str, MCPToolInfo] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        tool_name = next(
            (
                name
                for decorator in node.decorator_list
                if (name := mcp_tool_name_from_decorator(decorator))
            ),
            None,
        )
        if not tool_name:
            continue
        parameters = tuple(arg.arg for arg in node.args.args)
        tools[tool_name] = MCPToolInfo(
            name=tool_name,
            description=ast.get_docstring(node) or "Available ether.fi catalog MCP tool.",
            parameters=parameters,
        )
    return dict(sorted(tools.items()))


def value_or_missing(value) -> str:
    if value is None or value == "":
        return NOT_DOCUMENTED
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def render_field_value(value) -> str:
    return render_inline_markdown(value_or_missing(value))


COPY_ICON_SVG = (
    '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
    '<rect x="6" y="5" width="7" height="8" rx="1.4"></rect>'
    '<path d="M3 11V3.8C3 3.36 3.36 3 3.8 3H11"></path>'
    "</svg>"
)


def render_copy_button(value: object, label: str) -> str:
    value_text = value_or_missing(value)
    if value_text == NOT_DOCUMENTED:
        return ""
    return (
        f'<button class="copy-value-button" type="button" data-copy-text="{escape(value_text)}" '
        f'aria-label="Copy {escape(label)}">'
        f"{COPY_ICON_SVG}"
        '<span class="copy-value-label" data-copy-feedback>Copy</span>'
        "</button>"
    )


def render_copyable_code_value(value: object, label: str) -> str:
    value_text = value_or_missing(value)
    return (
        '<span class="copyable-value">'
        f'<code class="table-pill table-pill-block">{escape(value_text)}</code>'
        f"{render_copy_button(value_text, label)}"
        "</span>"
    )


def render_live_query_hint() -> str:
    hint = (
        "Live queries are saved-query outputs used for fresher recent data. On Dune, "
        "they can be queried with the query_<query_id> table name."
    )
    return (
        f'<span class="inline-info-hint" title="{escape(hint)}" aria-label="{escape(hint)}" '
        f'data-tooltip="{escape(hint)}" role="img" tabindex="0">i</span>'
    )


def live_query_table_name(live_query: dict) -> str:
    table_name = live_query.get("table_name")
    if table_name:
        return str(table_name)
    query_id = live_query.get("query_id")
    if query_id is None or query_id == "":
        return ""
    return f"query_{query_id}"


def render_live_query_value(live_query: dict) -> str:
    table_name = live_query_table_name(live_query)
    if not table_name:
        return render_field_value(None)
    return (
        '<span class="copyable-value live-query-value">'
        f'<code class="table-pill table-pill-block">{escape(table_name)}</code>'
        f"{render_copy_button(table_name, 'live query table name')}"
        f"{render_live_query_hint()}"
        "</span>"
    )


def live_query_glance_fields(live_query) -> list[tuple[str, str, str | None]]:
    if not isinstance(live_query, dict) or not live_query:
        return []
    if not live_query_table_name(live_query):
        return []
    return [("Live query", render_live_query_value(live_query), "copyable-table-name live-query-card")]


def render_metadata_list(values) -> str:
    if not values:
        return f'<p class="missing">{NOT_DOCUMENTED}</p>'
    if isinstance(values, str):
        values = [values]

    items = "\n".join(f"<li>{render_inline_markdown(format_metadata_item(value))}</li>" for value in values)
    return f"<ul>{items}</ul>"


def format_metadata_item(value) -> str:
    if isinstance(value, dict):
        if len(value) == 1:
            key, item_value = next(iter(value.items()))
            return f"{key}: {item_value}"
        return ", ".join(f"{key}: {item_value}" for key, item_value in value.items())
    return str(value)


def render_tag_list(values) -> str:
    if not values:
        return f'<p class="missing">{NOT_DOCUMENTED}</p>'
    tags = "\n".join(f'<span class="tag">{escape(str(value))}</span>' for value in values)
    return f'<div class="tag-list">{tags}</div>'


def render_fact_grid(fields: list[tuple[str, object]], class_name: str = "fact-grid") -> str:
    facts = []
    for label, value in fields:
        facts.append(
            "<div class=\"fact\">"
            f"<span>{escape(label)}</span>"
            f"<strong>{render_field_value(value)}</strong>"
            "</div>"
        )
    return f'<div class="{escape(class_name)}">' + "\n".join(facts) + "</div>"


def render_stat_grid(stats: list[tuple[str, object, str]]) -> str:
    rendered_stats = []
    for label, value, helper in stats:
        rendered_stats.append(
            '<div class="stat">'
            f"<span>{escape(label)}</span>"
            f"<strong>{escape(str(value))}</strong>"
            f"<p>{escape(helper)}</p>"
            "</div>"
        )
    return '<div class="stat-grid">' + "\n".join(rendered_stats) + "</div>"


def parse_freshness_timestamp(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith(" UTC"):
            text = f"{text[:-4]}+00:00"
        elif text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_freshness_table_timestamp(value: datetime | None) -> str:
    if value is None:
        return FRESHNESS_NOT_DOCUMENTED
    return value.strftime("%Y-%m-%d %H:%M UTC")


def format_minutes(minutes: float | None) -> str:
    if minutes is None:
        return NOT_DOCUMENTED
    minutes = max(0, int(round(minutes)))
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {remainder}m" if remainder else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def format_relative_age(minutes: float | None) -> str:
    if minutes is None:
        return FRESHNESS_NOT_DOCUMENTED
    minutes = max(0, int(round(minutes)))
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours, remainder = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {remainder}m ago" if remainder else f"{hours}h ago"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h ago" if hours and days < 2 else f"{days}d ago"


def format_compact_relative_age(minutes: float | None) -> str:
    if minutes is None:
        return FRESHNESS_NOT_DOCUMENTED
    minutes = max(0, int(round(minutes)))
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours, remainder = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {remainder}m ago" if remainder else f"{hours}h ago"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h ago" if hours and days < 2 else f"{days}d ago"


def freshness_status_for_entry(
    entry: DatasetEntry,
    freshness_registry: dict,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    data = entry.data
    dataset_name = str(data.get("name") or entry.slug)
    snapshot = freshness_snapshot_for_dataset(data, freshness_registry, dataset_name)
    last_updated = parse_freshness_timestamp(snapshot.get("last_updated"))
    refresh_interval = data.get("refresh_interval_minutes")
    lag_minutes = None
    ratio = None
    next_update = None

    if refresh_interval is None:
        status = "not-documented"
        label = "Not documented"
        description = "Missing refresh interval metadata."
    elif last_updated is None:
        status = "unknown"
        label = "Unknown"
        description = "No latest Dune snapshot has been imported yet."
    else:
        refresh_interval = int(refresh_interval)
        lag_minutes = max(0, (now - last_updated).total_seconds() / 60)
        ratio = lag_minutes / refresh_interval if refresh_interval else None
        next_update = last_updated + timedelta(minutes=refresh_interval)
        if ratio is not None and ratio <= 1:
            status = "fresh"
            label = "Fresh"
            description = "Within the expected refresh interval."
        elif ratio is not None and ratio <= 2:
            status = "delayed"
            label = "Delayed"
            description = "Past the expected refresh interval."
        else:
            status = "stale"
            label = "Stale"
            description = "More than twice the expected refresh interval."

    return {
        "entry": entry,
        "dataset_name": dataset_name,
        "display_name": dataset_title(entry),
        "table_name": data.get("table_name") or dataset_name,
        "description_text": data.get("description"),
        "aliases": data.get("aliases") or [],
        "raw_category": entry.category,
        "category": titleize_category(entry.category),
        "source_query_id": data.get("source_query_id") or snapshot.get("query_id"),
        "source_query_url": data.get("source_query_url"),
        "refresh_interval_minutes": refresh_interval,
        "freshness_column": data.get("freshness_timestamp_column"),
        "last_updated": last_updated,
        "next_update": next_update,
        "lag_minutes": lag_minutes,
        "ratio": ratio,
        "status": status,
        "label": label,
        "description": description,
    }


def freshness_sort_key(row: dict) -> tuple:
    status_rank = {
        "stale": 0,
        "delayed": 1,
        "unknown": 2,
        "not-documented": 3,
        "fresh": 4,
    }
    ratio = row.get("ratio")
    return (
        status_rank.get(row["status"], 2),
        -(ratio if ratio is not None else -1),
        row["display_name"].lower(),
    )


def freshness_group_for_row(row: dict) -> str:
    haystack = " ".join(
        str(value)
        for value in [
            row.get("display_name"),
            row.get("dataset_name"),
            row.get("table_name"),
            row.get("raw_category"),
            row.get("description_text"),
        ]
        if value
    ).lower()

    raw_category = str(row.get("raw_category") or "")
    if "cash" in haystack:
        return "cash"
    if raw_category == "etherfi_protocol":
        return "protocol"
    if raw_category == "lrt_restaking":
        return "lrt-restaking"
    if raw_category in {"activity", "metadata", "prices"}:
        return raw_category
    return "unknown"


def render_freshness_badge(row: dict) -> str:
    status = str(row["status"])
    display_status = "unknown" if status == "not-documented" else status
    label = "Unknown" if status == "not-documented" else str(row["label"])
    return f'<span class="status-badge freshness-badge {escape(display_status)}">{escape(label)}</span>'


def freshness_display_status(row: dict) -> tuple[str, str]:
    status = str(row["status"])
    if status == "not-documented":
        return "unknown", "Unknown"
    return status, str(row["label"])


def freshness_meter_for_row(row: dict) -> dict:
    ratio = row.get("ratio")
    lag_minutes = row.get("lag_minutes")
    refresh_interval = row.get("refresh_interval_minutes")
    relative_age = format_relative_age(lag_minutes)
    refresh_label = format_minutes(refresh_interval)

    if ratio is None or refresh_interval is None or lag_minutes is None:
        return {
            "phase": "unknown",
            "filled": 0,
            "label": f"Freshness unknown, refreshed {relative_age}",
        }

    if ratio <= 1:
        phase = "fresh"
        if ratio <= 0.1:
            filled = 10
        elif ratio <= 0.2:
            filled = 9
        else:
            filled = max(1, min(10, round((1 - ratio) * 10)))
    elif ratio <= 2:
        phase = "delayed"
        filled = max(1, min(10, math.ceil((ratio - 1) * 10)))
    else:
        phase = "stale"
        filled = 10

    phase_label = {
        "fresh": "green",
        "delayed": "yellow",
        "stale": "red",
    }[phase]
    return {
        "phase": phase,
        "filled": filled,
        "label": (
            f"Freshness: {filled}/10 {phase_label} bars, "
            f"refreshed {relative_age}, expected every {refresh_label}"
        ),
    }


def render_freshness_meter(row: dict) -> str:
    meter = freshness_meter_for_row(row)
    phase = str(meter["phase"])
    filled = int(meter["filled"])
    segments = "".join(
        f'<span class="freshness-meter-segment{" filled" if index <= filled else ""}"></span>'
        for index in range(1, 11)
    )
    label = escape(str(meter["label"]))
    return (
        f'<div class="freshness-meter {escape(phase)}" role="img" '
        f'aria-label="{label}" title="{label}">{segments}</div>'
    )


def render_summary_card(label: str, value: object, helper: str = "", class_name: str = "") -> str:
    classes = f"catalog-summary-card {class_name}".strip()
    helper_html = f"<p>{escape(helper)}</p>" if helper else ""
    return (
        f'<article class="{escape(classes)}">'
        f"<span>{escape(label)}</span>"
        f"<strong>{escape(str(value))}</strong>"
        f"{helper_html}"
        "</article>"
    )


def render_meta_chip(label: str, value_html: str, class_name: str = "", title: str = "") -> str:
    classes = f"meta-chip {class_name}".strip()
    title_attr = f' title="{escape(title)}"' if title else ""
    return (
        f'<span class="{escape(classes)}"{title_attr}>'
        f"<span>{escape(label)}</span>"
        f"<strong>{value_html}</strong>"
        "</span>"
    )


def mcp_grouped_tools(tools: dict[str, MCPToolInfo]) -> list[dict]:
    grouped = []
    mapped_tools: set[str] = set()
    for group in MCP_TOOL_GROUPS:
        group_tools = [
            tools[name]
            for name in group["tools"]
            if name in tools
        ]
        mapped_tools.update(tool.name for tool in group_tools)
        if group_tools:
            grouped.append({**group, "tool_infos": group_tools})

    extra_tools = [
        tool
        for name, tool in tools.items()
        if name not in mapped_tools
    ]
    if extra_tools:
        grouped.append(
            {
                "title": "Other available tools",
                "description": "Registered tools that do not yet have a more specific website group.",
                "tools": [tool.name for tool in extra_tools],
                "tool_infos": extra_tools,
            }
        )
    return grouped


def render_mcp_badge(label: str, class_name: str) -> str:
    return f'<span class="mcp-badge {escape(class_name)}">{escape(label)}</span>'


def mcp_tool_badges(tool: MCPToolInfo, group_title: str) -> list[str]:
    if tool.live_capable:
        return [
            render_mcp_badge("Planning", "planning"),
            render_mcp_badge("Live-capable", "live"),
            render_mcp_badge("DUNE_API_KEY", "key"),
        ]
    if tool.name == "plan_etherfi_query":
        return [render_mcp_badge("Planning", "planning")]
    if group_title == "Freshness and status":
        return [
            render_mcp_badge("Metadata", "metadata"),
            render_mcp_badge("Status", "status"),
        ]
    return [render_mcp_badge("Metadata", "metadata")]


def render_mcp_tool_card(tool: MCPToolInfo, group_title: str) -> str:
    badges = "".join(mcp_tool_badges(tool, group_title))
    return (
        f'<article class="mcp-tool-card" data-mcp-tool="{escape(tool.name)}">'
        f"<code>{escape(tool.name)}</code>"
        f"<p>{escape(tool.description)}</p>"
        f'<div class="mcp-badge-row">{badges}</div>'
        "</article>"
    )


def render_mcp_tool_groups(tools: dict[str, MCPToolInfo]) -> str:
    groups = []
    for group in mcp_grouped_tools(tools):
        tool_cards = "".join(
            render_mcp_tool_card(tool, str(group["title"]))
            for tool in group["tool_infos"]
        )
        groups.append(
            '<section class="mcp-tool-group detail-panel">'
            "<div>"
            f"<h3>{escape(str(group['title']))}</h3>"
            f"<p>{escape(str(group['description']))}</p>"
            "</div>"
            f'<div class="mcp-tool-list">{tool_cards}</div>'
            "</section>"
        )
    return "".join(groups)


def render_mcp_capability_card(title: str, description: str) -> str:
    return (
        '<article class="mcp-capability-card">'
        f"<h3>{escape(title)}</h3>"
        f"<p>{escape(description)}</p>"
        "</article>"
    )


def render_mcp_prompt_card(group: str, prompt: str) -> str:
    return (
        '<article class="mcp-prompt-card">'
        f"<span>{escape(group)}</span>"
        f"<p>{escape(prompt)}</p>"
        "</article>"
    )


def render_mcp_code_block(value: str) -> str:
    return f"<pre><code>{escape(value.strip())}</code></pre>"


def render_mcp_page(tools: dict[str, MCPToolInfo] | None = None) -> str:
    tools = tools or extract_mcp_tools()
    live_tool_count = sum(1 for tool in tools.values() if tool.live_capable)
    catalog_install_command = (
        "uvx --from git+https://github.com/henrystats/etherfi-data-catalog.git "
        "etherfi-catalog-mcp"
    )
    codex_config = """
[mcp_servers.dune]
command = "<official-dune-mcp-command>"
args = ["<official-dune-mcp-args>"]
tool_timeout_sec = 300

[mcp_servers.dune.env]
DUNE_API_KEY = "your_dune_api_key_here"

[mcp_servers.etherfi-catalog]
command = "uvx"
args = [
  "--from",
  "git+https://github.com/henrystats/etherfi-data-catalog.git",
  "etherfi-catalog-mcp",
]
startup_timeout_sec = 30
tool_timeout_sec = 60

[mcp_servers.etherfi-catalog.env]
DUNE_API_KEY = "your_dune_api_key_here"
"""
    claude_config = """
{
  "mcpServers": {
    "dune": {
      "command": "<official-dune-mcp-command>",
      "args": ["<official-dune-mcp-args>"],
      "env": {
        "DUNE_API_KEY": "your_dune_api_key_here"
      }
    },
    "etherfi-catalog": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/henrystats/etherfi-data-catalog.git",
        "etherfi-catalog-mcp"
      ],
      "env": {
        "DUNE_API_KEY": "your_dune_api_key_here"
      }
    }
  }
}
"""
    capability_cards = "".join(
        render_mcp_capability_card(title, description)
        for title, description in [
            (
                "Dataset discovery",
                "Find the right ether.fi materialized view and understand what it represents.",
            ),
            (
                "Dashboard discovery",
                "Find existing Dune dashboards and the internal datasets they depend on.",
            ),
            (
                "Freshness checks",
                "Check whether key materialized views are fresh, stale, or undocumented.",
            ),
            (
                "Query planning",
                "Help agents plan safe ether.fi DuneSQL queries with the right tables, filters, and caveats.",
            ),
            (
                "Live answers",
                "Run selected narrow Dune-backed tools when live execution is enabled.",
            ),
        ]
    )
    prompt_cards = "".join(
        render_mcp_prompt_card(group, prompt)
        for group, prompt in [
            ("Dataset discovery", "Which ether.fi dataset should I use to analyze protocol token TVL?"),
            ("Dataset discovery", "What does result_etherfi_cash_events contain?"),
            ("Freshness", "Is the Cash events dataset fresh?"),
            ("Freshness", "Which ether.fi datasets are currently stale?"),
            ("Dashboard discovery", "Is there already a dashboard for ether.fi Cash?"),
            ("Dashboard discovery", "Which dashboards depend on the Cash events dataset?"),
            ("Live answer", "What are the latest balances for Cash address 0xCa59d6a6a7360fBe3ceDF9C82CeBfe7F7AE72e8F?"),
            ("Query planning", "Plan a Dune query for weekly USDC spend volume on ether.fi Cash."),
        ]
    )
    tool_groups = render_mcp_tool_groups(tools)

    return (
        '<section class="page mcp-page" data-mcp-page>'
        '<div class="wrap mcp-layout">'
        '<section class="mcp-hero detail-panel">'
        '<div>'
        '<p class="eyebrow">Semantic agent layer</p>'
        "<h1>ether.fi Catalog MCP</h1>"
        '<p class="page-lead">Install a local stdio MCP that helps AI agents use ether.fi&rsquo;s dataset catalog, dashboard registry, freshness status, and Dune query-planning context.</p>'
        '<div class="mcp-action-row">'
        '<a class="button primary" href="datasets.html">Explore datasets</a>'
        '<a class="button secondary" href="dashboards.html">View dashboards</a>'
        '<a class="button secondary" href="freshness.html">Check freshness</a>'
        "</div>"
        "</div>"
        '<div class="mcp-summary-grid">'
        f'{render_summary_card("Registered tools", len(tools), class_name="accent")}'
        f'{render_summary_card("Tool groups", len(mcp_grouped_tools(tools)), class_name="fresh")}'
        f'{render_summary_card("Live-capable", live_tool_count, class_name="stale")}'
        f'{render_summary_card("Execution layer", "Dune", class_name="unknown")}'
        "</div>"
        "</section>"
        '<section class="mcp-section">'
        '<div class="mcp-section-heading">'
        "<h2>What this MCP does</h2>"
        "<p>It helps agents and teammates choose the right ether.fi context before moving into Dune execution.</p>"
        "</div>"
        f'<div class="mcp-capability-grid">{capability_cards}</div>'
        "</section>"
        '<section class="mcp-section mcp-flow-section detail-panel">'
        '<div class="mcp-section-heading">'
        "<h2>How it fits together</h2>"
        "<p>etherfi-catalog is the semantic layer. Dune is still the query and dashboard execution layer.</p>"
        "</div>"
        '<div class="mcp-flow">'
        '<article><span>1</span><strong>User question</strong><p>A teammate or agent asks what to analyze, build, check, or summarize.</p></article>'
        '<article><span>2</span><strong>etherfi-catalog MCP</strong><p>Chooses datasets, tools, caveats, filters, and safe query shape.</p></article>'
        '<article><span>3</span><strong>Dune / Dune MCP</strong><p>Handles query execution, saved queries, charts, and dashboards.</p></article>'
        '<article><span>4</span><strong>Website catalog</strong><p>Documents the same datasets, dashboards, and freshness status for humans.</p></article>'
        "</div>"
        "</section>"
        '<section class="mcp-section">'
        '<div class="mcp-section-heading">'
        "<h2>Tool groups</h2>"
        "<p>Available tools are read from the current MCP server and grouped for the website.</p>"
        "</div>"
        f'<div class="mcp-tool-groups">{tool_groups}</div>'
        "</section>"
        '<section class="mcp-section">'
        '<div class="mcp-section-heading">'
        "<h2>Example prompts</h2>"
        "<p>Short prompts that show how teammates and agents should start with catalog semantics.</p>"
        "</div>"
        f'<div class="mcp-prompt-grid">{prompt_cards}</div>'
        "</section>"
        '<section class="mcp-section mcp-mode-grid">'
        '<article class="detail-panel">'
        "<h2>Planning mode</h2>"
        "<ul>"
        "<li>No Dune query execution.</li>"
        "<li>Metadata and planning tools work without <code>DUNE_API_KEY</code>.</li>"
        "<li>Returns recommended datasets, caveats, filters, and suggested SQL.</li>"
        "<li>Useful for safe query authoring and review before creating Dune artifacts.</li>"
        "</ul>"
        "</article>"
        '<article class="detail-panel warning">'
        "<h2>Live mode</h2>"
        "<ul>"
        "<li>Runs narrow Dune-backed tools where implemented.</li>"
        "<li>Requires <code>DUNE_API_KEY</code> in the local <code>etherfi-catalog</code> MCP env block.</li>"
        "<li>May consume Dune credits; use summary mode and narrow filters.</li>"
        "</ul>"
        "</article>"
        "</section>"
        '<section class="mcp-section detail-panel">'
        '<div class="mcp-section-heading compact">'
        "<h2>Today vs later</h2>"
        "<p>Local stdio install is the recommended team path. Docker and Cloud Run remain advanced options for private staging, demos, and future remote deployments.</p>"
        "</div>"
        "</section>"
        '<section class="mcp-section detail-panel">'
        '<div class="mcp-section-heading">'
        "<h2>Recommended setup</h2>"
        "<p>Install Dune MCP first for execution workflows, then install ether.fi Catalog MCP as the semantic catalog and planning layer. Each teammate should use their own Dune credentials locally.</p>"
        "</div>"
        '<div class="mcp-setup-grid">'
        '<article><strong>1. Install Dune MCP</strong><p>Follow the current official Dune MCP instructions for your client. Use OAuth when the client can complete browser auth, or put <code>DUNE_API_KEY</code> in the Dune MCP env block for API-key auth.</p></article>'
        f'<article><strong>2. Install ether.fi Catalog MCP</strong><p><code>{escape(catalog_install_command)}</code></p></article>'
        '<article><strong>3. Reload the client</strong><p>After changing MCP config, fully restart or reload Codex, Claude Desktop, or the active MCP client so new server processes receive the environment.</p></article>'
        '<article><strong>Advanced only</strong><p>Docker and Cloud Run are optional/private staging paths, not the default team setup.</p></article>'
        "</div>"
        "</section>"
        '<section class="mcp-section detail-panel">'
        '<div class="mcp-section-heading">'
        "<h2>Codex config</h2>"
        "<p>Codex may load a global config such as <code>/Users/&lt;user&gt;/.codex/config.toml</code>. Put real keys only in private local config, never in this repo.</p>"
        "</div>"
        f"{render_mcp_code_block(codex_config)}"
        "</section>"
        '<section class="mcp-section detail-panel">'
        '<div class="mcp-section-heading">'
        "<h2>Claude Desktop config</h2>"
        "<p>Claude-style clients use the same local stdio shape: one server entry for Dune MCP and one for ether.fi Catalog MCP.</p>"
        "</div>"
        f"{render_mcp_code_block(claude_config)}"
        "</section>"
        '<section class="mcp-section detail-panel">'
        '<div class="mcp-section-heading">'
        "<h2>Test it works</h2>"
        "<p>Start with metadata and planning prompts. These do not require <code>DUNE_API_KEY</code> and should not make live Dune calls.</p>"
        "</div>"
        "<ul>"
        "<li>Search ether.fi datasets for Cash events.</li>"
        "<li>Show details for the protocol token holders dataset.</li>"
        "<li>Is the Cash events dataset fresh?</li>"
        "<li>Plan a Dune query for weekly USDC spend volume on ether.fi Cash with <code>execute_live=false</code>.</li>"
        "</ul>"
        "</section>"
        '<section class="mcp-section detail-panel warning">'
        '<div class="mcp-section-heading">'
        "<h2>Optional live Dune calls</h2>"
        "<p>Only use live catalog tools when the question needs a fresh Dune-backed answer.</p>"
        "</div>"
        "<ul>"
        "<li>Set <code>DUNE_API_KEY</code> in the local <code>etherfi-catalog</code> MCP env block before using <code>execute_live=true</code>.</li>"
        "<li>Live calls may consume Dune credits.</li>"
        "<li>Use summary mode, narrow date ranges, and token, chain, or address filters.</li>"
        "<li>Prefer one narrow live call over repeated broad calls.</li>"
        "</ul>"
        "</section>"
        '<section class="mcp-section detail-panel">'
        '<div class="mcp-section-heading">'
        "<h2>Troubleshooting</h2>"
        "</div>"
        "<ul>"
        "<li>If planning tools work but live tools cannot see <code>DUNE_API_KEY</code>, confirm the key is in the active MCP client config and restart the client.</li>"
        "<li>On Apple Silicon, <code>/usr/local/bin/git ... Bad CPU type in executable</code> usually means an old Intel Git is first on <code>PATH</code>; prefer <code>/opt/homebrew/bin/git</code> or <code>/usr/bin/git</code>.</li>"
        "<li>If Dune MCP auth fails, verify whether your client should use OAuth or API-key auth.</li>"
        "<li>Keep Cloud Run and Docker as advanced/private staging options until auth, rate limits, and credit controls are reviewed.</li>"
        "</ul>"
        "</section>"
        '<section class="mcp-section detail-panel">'
        "<h2>Best practices</h2>"
        '<div class="mcp-best-practices">'
        "<span>Start with dataset discovery before writing SQL.</span>"
        "<span>Check freshness before using a dataset for reporting.</span>"
        "<span>Use Dune for heavy execution and dashboards.</span>"
        "<span>Prefer batched queries over repeated small calls.</span>"
        "<span>For live catalog tools, prefer summary mode and narrow filters.</span>"
        "<span>Preserve caveats in generated query descriptions.</span>"
        "<span>Use team Dune context/API keys for shareable team-owned artifacts when applicable.</span>"
        "</div>"
        "</section>"
        "</div>"
        "</section>"
    )


def render_home_preview_card(title: str, description: str, href: str, label: str) -> str:
    return (
        '<article class="home-preview-card">'
        "<div>"
        f"<h2>{escape(title)}</h2>"
        f"<p>{escape(description)}</p>"
        "</div>"
        f'<a class="dataset-detail-action" href="{escape(href)}">{escape(label)}</a>'
        "</article>"
    )


def render_home_workflow_step(number: int, title: str, description: str) -> str:
    return (
        "<article>"
        f"<span>{number}</span>"
        f"<strong>{escape(title)}</strong>"
        f"<p>{escape(description)}</p>"
        "</article>"
    )


def render_home_page(
    entries: list[DatasetEntry],
    dashboard_entries: list[DashboardEntry],
    freshness_registry: dict,
    *,
    now: datetime | None = None,
) -> str:
    preview_cards = "".join(
        [
            render_home_preview_card(
                "Datasets",
                "Browse ether.fi materialized views, table schemas, refresh cadence, source queries, and related datasets.",
                "datasets.html",
                "Explore datasets",
            ),
            render_home_preview_card(
                "Dashboards",
                "Find Dune dashboards by product area and see which internal catalog datasets they use.",
                "dashboards.html",
                "View dashboards",
            ),
            render_home_preview_card(
                "Freshness",
                "Check which catalog datasets are fresh, delayed, stale, or undocumented.",
                "freshness.html",
                "Check freshness",
            ),
            render_home_preview_card(
                "MCP",
                "Connect AI agents to ether.fi dataset metadata, dashboard discovery, freshness checks, and selected live tools.",
                "mcp.html",
                "Learn about MCP",
            ),
        ]
    )
    workflow = "".join(
        [
            render_home_workflow_step(
                1,
                "Discover the right dataset or dashboard",
                "Start with the catalog pages to find existing tables and analysis.",
            ),
            render_home_workflow_step(
                2,
                "Check freshness and context",
                "Confirm whether a dataset is fresh enough before using it in reporting.",
            ),
            render_home_workflow_step(
                3,
                "Use MCP/Dune to answer questions",
                "Use the MCP for semantics and Dune for execution, charts, and dashboards.",
            ),
        ]
    )

    return (
        '<section class="page home-hub-page" data-home-page>'
        '<div class="wrap home-hub-layout">'
        '<section class="home-hub-hero detail-panel">'
        '<div>'
        '<p class="eyebrow">Repo-backed analytics catalog</p>'
        "<h1>ether.fi Data Catalog</h1>"
        '<p class="page-lead">A repo-backed catalog for ether.fi datasets, dashboards, freshness status, and MCP-powered AI workflows.</p>'
        "</div>"
        "</section>"
        '<section class="home-section">'
        '<div class="mcp-section-heading">'
        "<h2>Explore the data catalog</h2>"
        "</div>"
        f'<div class="home-preview-grid">{preview_cards}</div>'
        "</section>"
        '<section class="home-section detail-panel">'
        '<div class="mcp-section-heading">'
        "<h2>How this fits together</h2>"
        "</div>"
        f'<div class="home-workflow-grid">{workflow}</div>'
        "</section>"
        '<section class="home-start-callout detail-panel">'
        "<p>Start with <strong>Datasets</strong> if you are looking for tables. Start with <strong>Dashboards</strong> if you are looking for existing analysis. Start with <strong>MCP</strong> if you want an agent to choose the right data path.</p>"
        "</section>"
        "</div>"
        "</section>"
    )


def source_query_href(row: dict) -> str:
    query_url = row.get("source_query_url")
    query_id = row.get("source_query_id")
    return str(query_url or (f"https://dune.com/queries/{query_id}" if query_id else ""))


def render_freshness_page(
    entries: list[DatasetEntry],
    freshness_registry: dict,
    *,
    dashboard_count: int = 0,
    mcp_tool_count: int = 0,
    now: datetime | None = None,
    freshness_js_version: str = "local",
) -> str:
    rows = [
        freshness_status_for_entry(entry, freshness_registry, now=now)
        for entry in entries
    ]
    rows = sorted(rows, key=freshness_sort_key)

    counts = {
        status: sum(1 for row in rows if row["status"] == status)
        for status in ["fresh", "delayed", "stale", "unknown", "not-documented"]
    }

    summary_grid = (
        '<div class="catalog-summary-grid">'
        + "\n".join(
            [
                render_summary_card("Total datasets", len(rows), class_name="accent"),
                render_summary_card("Fresh", counts["fresh"], class_name="fresh"),
                render_summary_card("Stale", counts["delayed"] + counts["stale"], class_name="stale"),
                render_summary_card(
                    "Unknown",
                    counts["unknown"] + counts["not-documented"],
                    class_name="unknown",
                ),
            ]
        )
        + "</div>"
    )

    status_filter_buttons = "\n".join(
        f'<button class="filter-chip" type="button" data-status-filter="{escape(value)}">{escape(label)}</button>'
        for value, label in [
            ("all", "All"),
            ("fresh", "Fresh"),
            ("delayed", "Delayed"),
            ("stale", "Stale"),
            ("unknown", "Unknown"),
        ]
    )

    registry_cards = []
    for row in rows:
        dataset_url = dataset_href(row["entry"])
        group = freshness_group_for_row(row)
        display_status, display_status_label = freshness_display_status(row)
        absolute_last_updated = format_freshness_table_timestamp(row["last_updated"])
        relative_last_updated = format_relative_age(row["lag_minutes"])
        refresh_interval = row.get("refresh_interval_minutes")
        refresh_label = format_minutes(refresh_interval) if refresh_interval is not None else FRESHNESS_DASH
        refresh_label_html = (
            escape(refresh_label)
            if refresh_interval is not None
            else FRESHNESS_DASH
        )
        last_refreshed_chip_value = escape(relative_last_updated)
        source_href = source_query_href(row)
        source_action = (
            f'<a class="dune-action" href="{escape(source_href)}" '
            f'aria-label="Open source Dune query for {escape(row["display_name"])}" '
            f'title="Source query on Dune">Dune</a>'
            if source_href
            else '<span class="dune-action disabled" aria-disabled="true" title="No source query">Dune</span>'
        )
        last_refreshed_title = (
            absolute_last_updated if row["last_updated"] is not None else FRESHNESS_NOT_DOCUMENTED
        )
        last_refreshed_attr = (
            row["last_updated"].isoformat() if row["last_updated"] is not None else ""
        )
        refresh_interval_attr = (
            str(int(refresh_interval)) if refresh_interval is not None else ""
        )
        table_name = row.get("table_name") or row["dataset_name"]
        source_query_id = row.get("source_query_id")
        search_text = " ".join(
            str(value)
            for value in [
                row["dataset_name"],
                row["display_name"],
                row["category"],
                display_status_label,
                group,
                source_query_id,
                source_href,
                refresh_label,
                table_name,
                *[
                    alias
                    for alias in (row.get("aliases") or [])
                ],
            ]
            if value
        ).lower()
        registry_cards.append(
            f'<article class="registry-card freshness-dataset-card {escape(row["status"])}" '
            f'data-dataset-card data-freshness-row data-status="{escape(display_status)}" '
            f'data-group="{escape(group)}" data-search="{escape(search_text)}" '
            f'data-last-refreshed="{escape(last_refreshed_attr)}" '
            f'data-refresh-interval-minutes="{escape(refresh_interval_attr)}">'
            '<div class="registry-card-left">'
            f'<a class="freshness-dataset-link" href="{escape(dataset_url)}">{escape(row["display_name"])}</a>'
            '<div class="registry-meta-row">'
            f'{render_meta_chip("Refresh", refresh_label_html, "interval")}'
            f'{render_meta_chip("Last refreshed", last_refreshed_chip_value, "updated", last_refreshed_title)}'
            "</div>"
            "</div>"
            '<div class="registry-card-status">'
            f"{render_freshness_meter(row)}"
            f"{render_freshness_badge(row)}"
            f"{source_action}"
            "</div>"
            "</article>"
        )

    registry_html = "\n".join(registry_cards)
    freshness_js_src = f"assets/freshness.js?v={freshness_js_version}"

    return (
        '<section class="page catalog-page freshness-page" data-freshness-page>'
        '<div class="wrap catalog-layout">'
        f"{summary_grid}"
        '<section class="catalog-toolbar">'
        '<div class="catalog-search">'
        '<label for="dataset-search">Search datasets</label>'
        '<input id="dataset-search" type="search" placeholder="Search by dataset, table name, category, status, or query ID..." data-freshness-search>'
        "</div>"
        '<div class="filter-groups">'
        '<div class="filter-group">'
        '<span class="filter-group-label">Status</span>'
        f'<div class="filter-chip-row" aria-label="Dataset status filters">{status_filter_buttons}</div>'
        "</div>"
        "</div>"
        "</section>"
        '<section class="registry-section">'
        '<div class="registry-section-header">'
        "<div>"
        "<h2>Dataset registry</h2>"
        "<p>One card per generated catalog entry, with freshness, refresh cadence, source query, and dataset detail links.</p>"
        "</div>"
        f'<span id="dataset-count" data-freshness-count>{len(rows)} shown</span>'
        "</div>"
        f'<div class="registry-list">{registry_html}</div>'
        '<div id="dataset-empty-state" class="freshness-empty-state" data-freshness-empty hidden>No datasets match your search.</div>'
        "</section>"
        f'<script src="{escape(freshness_js_src)}" defer></script>'
        "</div>"
        "</section>"
    )


def dataset_title(entry: DatasetEntry) -> str:
    return str(entry.data.get("display_name") or entry.data.get("name") or entry.slug)


def dataset_href(entry: DatasetEntry) -> str:
    return f"datasets/{entry.slug}.html"


def dataset_href_from_nested_page(entry: DatasetEntry) -> str:
    return f"../datasets/{entry.slug}.html"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def dataset_documentation_status(data: dict) -> tuple[str, str]:
    if data.get("query_ready"):
        return "Query ready", "ready"
    return "Needs documentation", "needs-docs"


def dataset_missing_fields(data: dict) -> list[str]:
    required_fields = [
        "grain",
        "important_columns",
        "use_when",
        "do_not_use_when",
        "caveats",
        "example_user_intents",
    ]
    return [field for field in required_fields if not data.get(field)]


def build_dataset_reference_index(entries: list[DatasetEntry]) -> dict[str, DatasetEntry]:
    references: dict[str, DatasetEntry] = {}
    for entry in entries:
        data = entry.data
        values = [
            data.get("name"),
            data.get("table_name"),
            *(data.get("aliases") or []),
        ]
        for value in values:
            if value:
                references[str(value).lower()] = entry
    return references


def build_dashboard_reference_index(entries: list[DashboardEntry]) -> dict[str, DashboardEntry]:
    references: dict[str, DashboardEntry] = {}
    for entry in entries:
        data = entry.data
        values = [
            data.get("name"),
            data.get("title"),
            data.get("url"),
        ]
        for value in values:
            if value:
                references[str(value).lower()] = entry
    return references


def flatten_search_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        values: list[str] = []
        for key, item in value.items():
            values.append(str(key))
            values.extend(flatten_search_values(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(flatten_search_values(item))
        return values
    return [str(value)]


def dataset_search_text(entry: DatasetEntry) -> str:
    data = entry.data
    values = [
        dataset_title(entry),
        entry.category,
        titleize_category(entry.category),
        data.get("name"),
        data.get("table_name"),
        data.get("description"),
        data.get("source_query_id"),
        data.get("source_query_url"),
        data.get("grain"),
        data.get("freshness_timestamp_column"),
        data.get("query_ready"),
        data.get("aliases"),
        data.get("schema"),
        data.get("important_columns"),
        data.get("related_datasets"),
        data.get("related_dashboards"),
        data.get("search_keywords"),
        data.get("query_patterns"),
    ]
    return " ".join(
        token
        for value in values
        for token in flatten_search_values(value)
        if token
    ).lower()


def dataset_source_query_href(data: dict) -> str:
    source_query_url = data.get("source_query_url")
    source_query_id = data.get("source_query_id")
    return str(source_query_url or (f"https://dune.com/queries/{source_query_id}" if source_query_id else ""))


def dataset_refresh_label(data: dict) -> str:
    refresh_interval = data.get("refresh_interval_minutes")
    if refresh_interval is not None:
        return format_minutes(refresh_interval)
    if data.get("refresh cadence"):
        return str(data["refresh cadence"])
    return FRESHNESS_NOT_DOCUMENTED


def dataset_freshness_interval_summary(data: dict, row: dict) -> str:
    display_status, status_label = freshness_display_status(row)
    last_refreshed = format_compact_relative_age(row.get("lag_minutes"))
    refresh_label = dataset_refresh_label(data)
    interval_label = (
        "Interval not documented"
        if refresh_label in {NOT_DOCUMENTED, FRESHNESS_NOT_DOCUMENTED}
        else f"Every {refresh_label}"
    )
    return (
        f'<span class="freshness-status-pill status-{escape(display_status)}">{escape(status_label)}</span>'
        f'<span class="freshness-refresh-text">{escape(last_refreshed)} · {escape(interval_label)}</span>'
    )


def freshness_snapshot_for_dataset(
    data: dict,
    freshness_registry: dict,
    dataset_name: str | None = None,
) -> dict:
    reference_values = [
        dataset_name,
        data.get("name"),
        data.get("table_name"),
        *(data.get("aliases") or []),
    ]
    for value in reference_values:
        if value and value in freshness_registry:
            return freshness_registry[value] or {}

    source_query_id = data.get("source_query_id")
    if source_query_id is not None:
        source_query_id_text = str(source_query_id)
        for snapshot in freshness_registry.values():
            if str((snapshot or {}).get("query_id")) == source_query_id_text:
                return snapshot or {}

    return {}


def dataset_freshness_row(
    entry: DatasetEntry,
    freshness_registry: dict,
    now: datetime | None = None,
) -> dict:
    return freshness_status_for_entry(entry, freshness_registry, now=now)


def related_dashboard_count(entry: DatasetEntry) -> int:
    return len(entry.data.get("related_dashboards") or [])


def related_dataset_count(entry: DatasetEntry) -> int:
    return len(entry.data.get("related_datasets") or [])


def render_compact_dataset_card(
    entry: DatasetEntry,
    freshness_registry: dict,
    *,
    now: datetime | None = None,
    include_search_attrs: bool = True,
    class_name: str = "dataset-browser-card",
) -> str:
    data = entry.data
    row = dataset_freshness_row(entry, freshness_registry, now=now)
    display_status, display_status_label = freshness_display_status(row)
    relative_last_refreshed = format_relative_age(row["lag_minutes"])
    source_href = dataset_source_query_href(data)
    query_id = data.get("source_query_id")
    attrs = ""
    if include_search_attrs:
        attrs = (
            " data-dataset-card"
            f' data-category="{escape(entry.category)}"'
            f' data-status="{escape(display_status)}"'
            f' data-search="{escape(dataset_search_text(entry))}"'
        )
    source_query_attr = f' data-source-query-id="{escape(str(query_id))}"' if query_id else ""
    source_link = (
        f'<a class="dune-action" href="{escape(source_href)}">Dune</a>'
        if source_href
        else '<span class="dune-action disabled" aria-disabled="true">Dune</span>'
    )
    return (
        f'<article class="{escape(class_name)}"{attrs}{source_query_attr}>'
        '<div class="dataset-card-main">'
        f'<a class="dataset-card-title" href="{escape(dataset_href(entry))}">{escape(dataset_title(entry))}</a>'
        f'<p>{render_field_value(data.get("description"))}</p>'
        '<div class="registry-meta-row">'
        f'{render_meta_chip("Refresh", escape(dataset_refresh_label(data)), "interval")}'
        f'{render_meta_chip("Last refreshed", escape(relative_last_refreshed), "updated", format_freshness_table_timestamp(row["last_updated"]))}'
        f'{render_meta_chip("Status", escape(display_status_label), display_status)}'
        "</div>"
        "</div>"
        '<div class="dataset-card-side">'
        f"{source_link}"
        f'<a class="dataset-detail-action" href="{escape(dataset_href(entry))}">Details</a>'
        "</div>"
        "</article>"
    )


def render_featured_dataset_card(
    entry: DatasetEntry,
    freshness_registry: dict,
    *,
    now: datetime | None = None,
) -> str:
    return render_compact_dataset_card(
        entry,
        freshness_registry,
        now=now,
        include_search_attrs=False,
        class_name="dataset-browser-card featured",
    )


def featured_dataset_entries(entries: list[DatasetEntry]) -> list[DatasetEntry]:
    preferred = [
        "ether.fi assets under management",
        "ether.fi protocol token tvl",
        "ether.fi cash events",
    ]
    entries_by_title = {dataset_title(entry).lower(): entry for entry in entries}
    featured = [entries_by_title[name] for name in preferred if name in entries_by_title]
    if len(featured) >= 3:
        return featured[:3]
    for entry in entries:
        if entry not in featured and entry.data.get("query_ready"):
            featured.append(entry)
        if len(featured) == 3:
            break
    return featured[:3]


def category_description(category: str, count: int) -> str:
    label = titleize_category(category)
    return f"{count} generated dataset{'s' if count != 1 else ''} in the {label} catalog group."


def render_dataset_index(
    entries: list[DatasetEntry],
    freshness_registry: dict | None = None,
    *,
    now: datetime | None = None,
    datasets_js_version: str = "local",
) -> str:
    freshness_registry = freshness_registry or {}
    entries = visible_dataset_entries(entries)
    grouped: dict[str, list[DatasetEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.category, []).append(entry)

    sorted_categories = sorted(grouped.items(), key=category_sort_key)
    nav_buttons = [
        '<button class="dataset-nav-button active" type="button" data-dataset-nav="overview" aria-pressed="true">'
        '<span>Overview</span>'
        f'<strong>{len(entries)}</strong>'
        "</button>"
    ]
    for category, category_entries in sorted_categories:
        nav_buttons.append(
            f'<button class="dataset-nav-button" type="button" data-dataset-nav="{escape(category)}" aria-pressed="false">'
            f'<span>{escape(titleize_category(category))}</span>'
            f'<strong>{len(category_entries)}</strong>'
            "</button>"
        )

    featured_cards = "".join(
        render_featured_dataset_card(entry, freshness_registry, now=now)
        for entry in featured_dataset_entries(entries)
    )

    category_sections = []
    for category, category_entries in sorted_categories:
        cards = "".join(
            render_compact_dataset_card(entry, freshness_registry, now=now)
            for entry in category_entries
        )
        category_sections.append(
            f'<section class="dataset-category-view" data-dataset-category-section data-category="{escape(category)}" hidden>'
            '<div class="dataset-view-heading">'
            "<div>"
            f"<h2>{escape(titleize_category(category))}</h2>"
            f"<p>{escape(category_description(category, len(category_entries)))}</p>"
            "</div>"
            f'<span class="dataset-view-count">{len(category_entries)} datasets</span>'
            "</div>"
            f'<div class="dataset-browser-list">{cards}</div>'
            "</section>"
        )

    datasets_js_src = f"assets/datasets.js?v={datasets_js_version}"

    return (
        '<section class="page dataset-browser-page" data-datasets-page>'
        '<div class="wrap dataset-browser-shell">'
        '<aside class="dataset-category-panel">'
        '<div class="dataset-category-panel-header">'
        "<span>Dataset categories</span>"
        "<strong>Catalog</strong>"
        "</div>"
        f'{"".join(nav_buttons)}'
        "</aside>"
        '<div class="dataset-browser-main">'
        '<section class="catalog-toolbar dataset-browser-toolbar">'
        '<div class="catalog-search">'
        '<label for="dataset-search">Search datasets</label>'
        '<input id="dataset-search" type="search" placeholder="Search by dataset, table name, column, category, or query ID..." data-dataset-search>'
        "</div>"
        f'<span id="dataset-count" class="dataset-count">{len(entries)} datasets</span>'
        "</section>"
        '<section class="dataset-overview-view" data-dataset-overview>'
        '<div class="dataset-overview-copy">'
        "<h1>Dataset catalog</h1>"
        "<p>This page documents ether.fi materialized views and supporting datasets. Browse by category, search across the full catalog, and open detail pages for table meaning, freshness, schema, source queries, and related resources.</p>"
        "</div>"
        '<section class="dataset-featured-section">'
        '<div class="dataset-view-heading">'
        "<div>"
        "<h2>Featured datasets</h2>"
        "<p>Common starting points for protocol, TVL, and Cash analysis.</p>"
        "</div>"
        "</div>"
        f'<div class="dataset-browser-list featured-list">{featured_cards}</div>'
        "</section>"
        '<section class="dataset-browse-callout">Browse categories on the left to explore the full catalog.</section>'
        "</section>"
        f'{"".join(category_sections)}'
        '<div id="dataset-empty-state" class="freshness-empty-state dataset-empty-state" hidden>No datasets match your search.</div>'
        f'<script src="{escape(datasets_js_src)}" defer></script>'
        "</div>"
        "</div>"
        "</section>"
    )


def parse_named_metadata_item(value) -> tuple[str | None, str]:
    if isinstance(value, dict):
        if len(value) == 1:
            key, item_value = next(iter(value.items()))
            return str(key), str(item_value)
        return None, ", ".join(f"{key}: {item_value}" for key, item_value in value.items())
    text = str(value)
    if ":" in text:
        key, item_value = text.split(":", 1)
        if key.strip():
            return key.strip(), item_value.strip()
    return None, text


def render_important_columns(values) -> str:
    if not values:
        return f'<p class="missing">{NOT_DOCUMENTED}</p>'
    if isinstance(values, str):
        values = [values]
    items = []
    for value in values:
        column, description = parse_named_metadata_item(value)
        if column:
            items.append(
                '<article class="column-note">'
                f"<code>{escape(column)}</code>"
                f"<p>{render_inline_markdown(description)}</p>"
                "</article>"
            )
        else:
            items.append(f'<article class="column-note"><p>{render_inline_markdown(description)}</p></article>')
    return '<div class="column-note-grid">' + "\n".join(items) + "</div>"


def schema_column_key(value) -> str:
    return str(value or "").strip().strip("`").lower()


def important_column_description_map(values) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    if not values:
        return descriptions
    if isinstance(values, dict):
        iterable = values.items()
        for column, description in iterable:
            if isinstance(description, dict):
                description = description.get("description") or description.get("desc") or description.get("note")
            if column and description:
                descriptions[schema_column_key(column)] = str(description)
        return descriptions
    if isinstance(values, str):
        values = [values]
    for value in values:
        column = None
        description = None
        if isinstance(value, dict):
            column = value.get("name") or value.get("column") or value.get("field")
            description = value.get("description") or value.get("desc") or value.get("note")
            if not column and len(value) == 1:
                column, description = next(iter(value.items()))
        else:
            column, description = parse_named_metadata_item(value)
        if column and description:
            descriptions[schema_column_key(column)] = str(description)
    return descriptions


def normalize_schema_columns(schema) -> list[dict[str, str]]:
    if not schema:
        return []
    items = schema.items() if isinstance(schema, dict) else schema
    columns = []
    for column in items:
        description = ""
        if isinstance(schema, dict):
            name, value = column
            if isinstance(value, dict):
                column_type = value.get("type") or value.get("data_type") or value.get("datatype") or NOT_DOCUMENTED
                description = value.get("description") or value.get("desc") or value.get("note") or ""
            else:
                column_type = value if value is not None else NOT_DOCUMENTED
        elif isinstance(column, dict):
            if len(column) == 1 and not {"name", "column", "field"}.intersection(column):
                name, value = next(iter(column.items()))
                if isinstance(value, dict):
                    column_type = value.get("type") or value.get("data_type") or value.get("datatype") or NOT_DOCUMENTED
                    description = value.get("description") or value.get("desc") or value.get("note") or ""
                else:
                    column_type = value if value is not None else NOT_DOCUMENTED
            else:
                name = column.get("name") or column.get("column") or column.get("field") or NOT_DOCUMENTED
                column_type = column.get("type") or column.get("data_type") or column.get("datatype") or NOT_DOCUMENTED
                description = column.get("description") or column.get("desc") or column.get("note") or ""
        else:
            name, column_type = parse_named_metadata_item(column)
            name = name or column
        columns.append(
            {
                "name": str(name),
                "type": str(column_type),
                "description": str(description or ""),
            }
        )
    return columns


def render_schema_description(value: str) -> str:
    if not value:
        return '<span class="schema-description-empty">&mdash;</span>'
    return render_inline_markdown(value)


def render_schema_table(schema, important_columns=None) -> str:
    columns = normalize_schema_columns(schema)
    if not columns:
        return f'<p class="missing">{NOT_DOCUMENTED}</p>'
    important_descriptions = important_column_description_map(important_columns)
    rows = []
    for column in columns:
        name = column["name"]
        column_type = column["type"]
        description = column["description"] or important_descriptions.get(schema_column_key(name), "")
        rows.append(
            "<tr>"
            f"<td><code>{escape(name)}</code></td>"
            f"<td>{escape(column_type)}</td>"
            f'<td class="schema-description">{render_schema_description(description)}</td>'
            "</tr>"
        )
    return (
        '<div class="schema-table-wrap">'
        '<table class="schema-table">'
        "<thead><tr><th>Column</th><th>Type</th><th>Description</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
    )


def render_limited_metadata_list(values, *, limit: int = 6) -> str:
    if not values:
        return f'<p class="missing">{NOT_DOCUMENTED}</p>'
    if isinstance(values, str):
        values = [values]
    visible = list(values)[:limit]
    items = "\n".join(f"<li>{render_inline_markdown(format_metadata_item(value))}</li>" for value in visible)
    return f"<ul>{items}</ul>"


def compact_about_text(text: str, *, max_chars: int = 260) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    boundary = cleaned.rfind(". ", 0, max_chars)
    if boundary >= 80:
        return cleaned[: boundary + 1]
    return cleaned[:max_chars].rstrip() + "..."


def ensure_sentence_boundary(text: str) -> str:
    stripped = text.strip()
    if not stripped or stripped.endswith((".", "!", "?", "...")):
        return stripped
    return f"{stripped}."


def dataset_fallback_description(entry: DatasetEntry) -> str:
    category = titleize_category(entry.category)
    title = dataset_title(entry)
    return f"This dataset documents {category} data for {title}."


def dataset_summary_text(entry: DatasetEntry) -> str:
    description = str(entry.data.get("description") or "").strip()
    return description or dataset_fallback_description(entry)


def semantic_note_candidates(data: dict) -> list[str]:
    notes = data.get("semantic_notes") or []
    if isinstance(notes, str):
        notes = [notes]
    return [
        " ".join(note.split())
        for note in notes
        if isinstance(note, str) and 20 <= len(" ".join(note.split())) <= 180
    ]


def render_about_table(entry: DatasetEntry) -> str:
    parts = [ensure_sentence_boundary(compact_about_text(dataset_summary_text(entry)))]
    if entry.data.get("description"):
        for note in semantic_note_candidates(entry.data):
            note_text = ensure_sentence_boundary(compact_about_text(note, max_chars=180))
            if note_text and note_text not in parts:
                parts.append(note_text)
            break
    about = " ".join(parts[:2]) or dataset_fallback_description(entry)
    return f'<p class="dataset-about-copy">{render_inline_markdown(about)}</p>'


def render_dataset_glance(fields: list[tuple[str, str, str | None]]) -> str:
    items = []
    for label, value_html, class_name in fields:
        card_class = f' class="dataset-glance-card {escape(class_name)}"' if class_name else ' class="dataset-glance-card"'
        if class_name and "freshness-refresh-item" in class_name:
            items.append(
                f"<article{card_class}>"
                f'<div class="glance-label">{escape(label)}</div>'
                f'<div class="glance-value freshness-refresh-value">{value_html}</div>'
                "</article>"
            )
        else:
            items.append(
                f"<article{card_class}>"
                f"<span>{escape(label)}</span>"
                f"<strong>{value_html}</strong>"
                "</article>"
            )
    return '<div class="dataset-glance-grid">' + "\n".join(items) + "</div>"


def render_related_dataset_links(
    values,
    dataset_reference_index: dict[str, DatasetEntry],
    *,
    include_subtables: bool = False,
) -> str:
    if not values:
        return f'<p class="missing">{NOT_DOCUMENTED}</p>'
    if isinstance(values, str):
        values = [values]
    links = []
    for value in values:
        text = str(value)
        entry = dataset_reference_index.get(text.lower())
        if entry:
            if is_subtable_entry(entry) and not include_subtables:
                continue
            links.append(
                f'<a class="related-resource" href="{escape(dataset_href_from_nested_page(entry))}">'
                f"{escape(dataset_title(entry))}</a>"
            )
        else:
            links.append(f'<span class="related-resource muted">{escape(text)}</span>')
    if not links:
        return f'<p class="missing">{NOT_DOCUMENTED}</p>'
    return '<div class="related-resource-list">' + "\n".join(links) + "</div>"


def parent_dataset_references(entry: DatasetEntry) -> set[str]:
    data = entry.data
    return {
        str(value).lower()
        for value in [
            data.get("name"),
            data.get("table_name"),
            entry.slug,
            *(data.get("aliases") or []),
        ]
        if value
    }


def supporting_subtable_entries(
    entry: DatasetEntry,
    entries: list[DatasetEntry],
) -> list[DatasetEntry]:
    parent_values = parent_dataset_references(entry)
    subtables = [
        candidate
        for candidate in entries
        if is_subtable_entry(candidate)
        and str(candidate.data.get("parent_dataset") or "").lower() in parent_values
    ]
    return sorted(subtables, key=lambda candidate: dataset_title(candidate).lower())


def render_supporting_subtables(
    entry: DatasetEntry,
    entries: list[DatasetEntry],
) -> str:
    subtables = supporting_subtable_entries(entry, entries)
    if not subtables:
        return ""
    links = "\n".join(
        f'<a class="related-resource" href="{escape(dataset_href_from_nested_page(subtable))}">'
        f"{escape(dataset_title(subtable))}</a>"
        for subtable in subtables
    )
    return (
        '<section class="detail-panel dataset-detail-section">'
        "<h2>Supporting sub-tables</h2>"
        '<p class="dataset-about-copy">Supporting layers used for lineage, debugging, and freshness/cost-aware dataset construction. '
        "Use the main dataset for normal analysis.</p>"
        f'<div class="related-resource-list">{links}</div>'
        "</section>"
    )


def render_related_dashboard_links(
    values,
    dashboard_reference_index: dict[str, DashboardEntry],
) -> str:
    if not values:
        return f'<p class="missing">{NOT_DOCUMENTED}</p>'
    if isinstance(values, str):
        values = [values]
    links = []
    for value in values:
        text = str(value)
        dashboard = dashboard_reference_index.get(text.lower())
        if dashboard:
            links.append(
                f'<a class="related-resource" href="../dashboards/{escape(dashboard.slug)}.html">'
                f"{escape(dashboard_title(dashboard))}</a>"
            )
        elif text.startswith(("http://", "https://")):
            links.append(f'<a class="related-resource" href="{escape(text)}">{escape(text)}</a>')
        else:
            links.append(f'<span class="related-resource muted">{escape(text)}</span>')
    return '<div class="related-resource-list">' + "\n".join(links) + "</div>"


def render_dataset_page(
    entry: DatasetEntry,
    *,
    entries: list[DatasetEntry] | None = None,
    dashboard_entries: list[DashboardEntry] | None = None,
    freshness_registry: dict | None = None,
    now: datetime | None = None,
    dataset_detail_js_version: str = "local",
) -> str:
    data = entry.data
    title = dataset_title(entry)
    entries = entries or []
    dashboard_entries = dashboard_entries or []
    freshness_registry = freshness_registry or {}
    row = dataset_freshness_row(entry, freshness_registry, now=now)
    display_status, _ = freshness_display_status(row)
    source_href = dataset_source_query_href(data)
    source_button = (
        f'<a class="dune-action" href="{escape(source_href)}">Dune</a>'
        if source_href
        else '<span class="dune-action disabled" aria-disabled="true">Dune</span>'
    )
    table_name = data.get("table_name") or data.get("name")
    summary_text = dataset_summary_text(entry)
    glance_fields = [
        ("Grain", render_field_value(data.get("grain")), "glance-grain"),
        (
            "Freshness & Refresh Interval",
            dataset_freshness_interval_summary(data, row),
            "glance-compact freshness-refresh-item",
        ),
    ]
    glance_fields.extend(live_query_glance_fields(data.get("live_query")))
    glance_fields.append(
        (
            "Full table name",
            render_copyable_code_value(table_name, "full table name"),
            "full-table-name copyable-table-name",
        )
    )
    at_a_glance = render_dataset_glance(glance_fields)
    dataset_reference_index = build_dataset_reference_index(entries)
    dashboard_reference_index = build_dashboard_reference_index(dashboard_entries)
    related_dataset_html = render_related_dataset_links(data.get("related_datasets"), dataset_reference_index)
    related_dashboard_html = render_related_dashboard_links(data.get("related_dashboards"), dashboard_reference_index)
    supporting_subtables_html = render_supporting_subtables(entry, entries)

    return (
        '<section class="page dataset-page">'
        '<div class="wrap dataset-detail-layout">'
        '<header class="dataset-detail-header">'
        '<div>'
        '<a class="dataset-back-link" href="../datasets.html">Back to datasets</a>'
        f"<h1>{escape(title)}</h1>"
        f"<p>{render_inline_markdown(summary_text)}</p>"
        "</div>"
        f"{source_button}"
        "</header>"
        '<section class="detail-panel dataset-detail-section">'
        "<h2>At a glance</h2>"
        f"{at_a_glance}"
        "</section>"
        '<section class="detail-panel dataset-detail-section">'
        "<h2>About this table</h2>"
        f"{render_about_table(entry)}"
        "</section>"
        '<section class="detail-panel dataset-detail-section">'
        "<h2>Schema</h2>"
        f"{render_schema_table(data.get('schema'), data.get('important_columns'))}"
        "</section>"
        f"{supporting_subtables_html}"
        '<section class="detail-panel dataset-detail-section">'
        "<h2>Related datasets and dashboards</h2>"
        '<div class="related-resource-columns">'
        "<div><h3>Related datasets</h3>"
        f"{related_dataset_html}"
        "</div>"
        "<div><h3>Related dashboards</h3>"
        f"{related_dashboard_html}"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
        f'<script src="../assets/dataset-detail.js?v={escape(dataset_detail_js_version)}" defer></script>'
        "</section>"
    )


def dashboard_title(entry: DashboardEntry) -> str:
    return str(entry.data.get("title") or entry.data.get("name") or entry.slug)


def dashboard_href(entry: DashboardEntry) -> str:
    return f"dashboards/{entry.slug}.html"


def dashboard_is_core(entry: DashboardEntry) -> bool:
    return bool(entry.data.get("show_in_core"))


def dashboard_category_label(entry: DashboardEntry) -> str:
    return titleize_dashboard_category(entry.category)


def dashboard_url(entry: DashboardEntry) -> str:
    return str(entry.data.get("url") or "")


def dashboard_linked_dataset_values(
    dataset_names: list[str],
    dataset_reference_index: dict[str, DatasetEntry],
) -> list[str]:
    values = []
    for dataset_name in dataset_names:
        values.append(str(dataset_name))
        dataset_entry = dataset_reference_index.get(str(dataset_name).lower())
        if dataset_entry:
            values.extend(
                [
                    dataset_title(dataset_entry),
                    dataset_entry.data.get("name"),
                    dataset_entry.data.get("table_name"),
                    dataset_entry.category,
                    titleize_category(dataset_entry.category),
                ]
            )
    return [str(value) for value in values if value]


def resolve_dashboard_dataset_entries(
    dataset_names: list[str],
    dataset_reference_index: dict[str, DatasetEntry],
) -> list[DatasetEntry]:
    resolved = []
    seen_slugs = set()
    for dataset_name in dataset_names:
        dataset_entry = dataset_reference_index.get(str(dataset_name).lower())
        if not dataset_entry or dataset_entry.slug in seen_slugs:
            continue
        seen_slugs.add(dataset_entry.slug)
        resolved.append(dataset_entry)
    return resolved


def dashboard_search_text(
    entry: DashboardEntry,
    dataset_reference_index: dict[str, DatasetEntry],
) -> str:
    data = entry.data
    values = [
        data.get("name"),
        dashboard_title(entry),
        entry.category,
        dashboard_category_label(entry),
        data.get("description"),
        data.get("url"),
        data.get("tags"),
        "core" if dashboard_is_core(entry) else "",
        dashboard_linked_dataset_values(data.get("datasets") or [], dataset_reference_index),
    ]
    return " ".join(
        token
        for value in values
        for token in flatten_search_values(value)
        if token
    ).lower()


def render_dashboard_tag_chips(tags, *, limit: int = 4) -> str:
    if not tags:
        return ""
    chips = [
        f'<span class="dashboard-tag">{escape(str(tag))}</span>'
        for tag in list(tags)[:limit]
    ]
    if len(tags) > limit:
        chips.append(f'<span class="dashboard-tag muted">+{len(tags) - limit}</span>')
    return '<div class="dashboard-tag-row">' + "".join(chips) + "</div>"


def render_dashboard_card(
    entry: DashboardEntry,
    dataset_reference_index: dict[str, DatasetEntry],
    *,
    include_search_attrs: bool = True,
    class_name: str = "dashboard-browser-card",
) -> str:
    data = entry.data
    datasets = data.get("datasets") or []
    internal_datasets = resolve_dashboard_dataset_entries(datasets, dataset_reference_index)
    source_href = dashboard_url(entry)
    source_link = (
        f'<a class="dune-action" href="{escape(source_href)}">Dune</a>'
        if source_href
        else '<span class="dune-action disabled" aria-disabled="true">Dune</span>'
    )
    attrs = ""
    if include_search_attrs:
        attrs = (
            " data-dashboard-card"
            f' data-dashboard-category="{escape(entry.category)}"'
            f' data-search="{escape(dashboard_search_text(entry, dataset_reference_index))}"'
        )
    core_attr = ' data-dashboard-core-card' if not include_search_attrs else ""
    return (
        f'<article class="{escape(class_name)}"{attrs}{core_attr}>'
        '<div class="dashboard-card-main">'
        '<div class="dashboard-card-topline">'
        f'<span class="dashboard-category-chip {escape(entry.category)}">{escape(dashboard_category_label(entry))}</span>'
        f'<span class="dashboard-linked-count">{len(internal_datasets)} linked datasets</span>'
        "</div>"
        f'<a class="dashboard-card-title" href="{escape(dashboard_href(entry))}">{escape(dashboard_title(entry))}</a>'
        f'<p class="dashboard-card-description">{render_field_value(data.get("description"))}</p>'
        f'{render_dashboard_tag_chips(data.get("tags") or [])}'
        "</div>"
        '<div class="dashboard-card-side">'
        f"{source_link}"
        f'<a class="dataset-detail-action" href="{escape(dashboard_href(entry))}">Details</a>'
        "</div>"
        "</article>"
    )


def render_dashboard_dataset_links(
    dataset_names: list[str],
    dataset_reference_index: dict[str, DatasetEntry],
    *,
    nested: bool = False,
) -> str:
    dataset_entries = resolve_dashboard_dataset_entries(dataset_names, dataset_reference_index)
    if not dataset_entries:
        return ""

    links = []
    for dataset_entry in dataset_entries:
        href = dataset_href_from_nested_page(dataset_entry) if nested else dataset_href(dataset_entry)
        links.append(
            f'<a class="related-resource" href="{escape(href)}">'
            f"{escape(dataset_title(dataset_entry))}</a>"
        )
    return '<div class="related-resource-list">' + "\n".join(links) + "</div>"


def render_dashboard_index(
    entries: list[DashboardEntry],
    dataset_reference_index: dict[str, DatasetEntry],
    *,
    dashboards_js_version: str = "local",
) -> str:
    grouped: dict[str, list[DashboardEntry]] = {category: [] for category in DASHBOARD_CATEGORY_ORDER}
    for entry in entries:
        grouped.setdefault(entry.category, []).append(entry)

    core_entries = [entry for entry in entries if dashboard_is_core(entry)]
    linked_dataset_count = len(
        {
            dataset_entry.slug
            for entry in entries
            for dataset_entry in resolve_dashboard_dataset_entries(
                entry.data.get("datasets") or [],
                dataset_reference_index,
            )
        }
    )
    summary_grid = (
        '<div class="catalog-summary-grid dataset-summary-grid">'
        + "\n".join(
            [
                render_summary_card("Total dashboards", len(entries), class_name="accent"),
                render_summary_card("Core dashboards", len(core_entries), class_name="fresh"),
                render_summary_card("Categories", len(DASHBOARD_CATEGORY_ORDER), class_name="unknown"),
                render_summary_card("Linked datasets", linked_dataset_count, class_name="stale"),
            ]
        )
        + "</div>"
    )

    nav_buttons = []
    for group in DASHBOARD_DISPLAY_GROUPS:
        count = len(core_entries) if group == "core" else len(grouped.get(group, []))
        active_class = " active" if group == "core" else ""
        pressed = "true" if group == "core" else "false"
        nav_buttons.append(
            f'<button class="dataset-nav-button{active_class}" type="button" data-dashboard-nav="{escape(group)}" aria-pressed="{pressed}">'
            f'<span>{escape(titleize_dashboard_category(group))}</span>'
            f"<strong>{count}</strong>"
            "</button>"
        )

    def render_dashboard_section(group: str, section_entries: list[DashboardEntry], *, core: bool = False) -> str:
        cards = "".join(
            render_dashboard_card(
                entry,
                dataset_reference_index,
                include_search_attrs=not core,
                class_name="dashboard-browser-card featured" if core else "dashboard-browser-card",
            )
            for entry in section_entries
        )
        empty = (
            '<div class="dashboard-section-empty">No dashboards documented in this group yet.</div>'
            if not section_entries
            else ""
        )
        description = (
            "Core contains the top dashboards teammates should check first."
            if core
            else f"{len(section_entries)} dashboard{'s' if len(section_entries) != 1 else ''} in the {titleize_dashboard_category(group)} product area."
        )
        hidden = "" if core else " hidden"
        core_attr = " data-dashboard-core" if core else ""
        return (
            f'<section class="dashboard-category-view" data-dashboard-section data-dashboard-group="{escape(group)}"{core_attr}{hidden}>'
            '<div class="dataset-view-heading">'
            "<div>"
            f"<h2>{escape(titleize_dashboard_category(group))}</h2>"
            f"<p>{escape(description)}</p>"
            "</div>"
            f'<span class="dataset-view-count">{len(section_entries)} dashboard{"s" if len(section_entries) != 1 else ""}</span>'
            "</div>"
            f'<div class="dashboard-browser-list">{cards}{empty}</div>'
            "</section>"
        )

    sections = [
        render_dashboard_section("core", core_entries, core=True),
        *[
            render_dashboard_section(category, grouped.get(category, []))
            for category in DASHBOARD_CATEGORY_ORDER
        ],
    ]
    dashboards_js_src = f"assets/dashboards.js?v={dashboards_js_version}"

    return (
        '<section class="page dashboard-browser-page" data-dashboards-page>'
        '<div class="wrap dataset-browser-shell">'
        '<aside class="dataset-category-panel">'
        '<div class="dataset-category-panel-header">'
        "<span>Dashboard groups</span>"
        "<strong>Registry</strong>"
        "</div>"
        f'{"".join(nav_buttons)}'
        "</aside>"
        '<div class="dataset-browser-main">'
        '<section class="dashboard-browser-header">'
        "<h1>Dashboards</h1>"
        "<p>Browse ether.fi Dune dashboards by product area and linked datasets.</p>"
        f"{summary_grid}"
        "</section>"
        '<section class="catalog-toolbar dataset-browser-toolbar">'
        '<div class="catalog-search">'
        '<label for="dashboard-search">Search dashboards</label>'
        '<input id="dashboard-search" type="search" placeholder="Search by dashboard, category, tag, URL, or linked dataset..." data-dashboard-search>'
        "</div>"
        f'<span id="dashboard-count" class="dataset-count">{len(core_entries)} dashboard{"s" if len(core_entries) != 1 else ""}</span>'
        "</section>"
        f'{"".join(sections)}'
        '<div id="dashboard-empty-state" class="freshness-empty-state dashboard-empty-state" hidden>No dashboards match your search.</div>'
        f'<script src="{escape(dashboards_js_src)}" defer></script>'
        "</div>"
        "</div>"
        "</section>"
    )


def render_dashboard_page(
    entry: DashboardEntry,
    dataset_reference_index: dict[str, DatasetEntry],
) -> str:
    data = entry.data
    title = dashboard_title(entry)
    url = data.get("url")
    datasets = data.get("datasets") or []
    linked_datasets_html = render_dashboard_dataset_links(
        datasets,
        dataset_reference_index,
        nested=True,
    )
    linked_section = (
        '<section class="detail-panel dataset-detail-section">'
        "<h2>Linked datasets</h2>"
        f"{linked_datasets_html}"
        "</section>"
        if linked_datasets_html
        else ""
    )

    dashboard_link = (
        f'<a class="dune-action" href="{escape(str(url))}">Dune</a>'
        if url
        else f'<span class="missing">{NOT_DOCUMENTED}</span>'
    )

    return (
        '<section class="page dashboard-detail-page">'
        '<div class="wrap dataset-detail-layout">'
        '<header class="dataset-detail-header">'
        '<div>'
        '<a class="dataset-back-link" href="../dashboards.html">Back to dashboards</a>'
        f"<h1>{escape(title)}</h1>"
        f'<p>{render_field_value(data.get("description"))}</p>'
        "</div>"
        f"{dashboard_link}"
        "</header>"
        '<section class="detail-panel dataset-detail-section">'
        "<h2>Tags</h2>"
        f"{render_tag_list(data.get('tags'))}"
        "</section>"
        f"{linked_section}"
        "</div>"
        "</section>"
    )


def write_dashboard_pages(
    *,
    entries: list[DashboardEntry],
    dataset_entries: list[DatasetEntry],
    pages: list[Page],
    template: Template,
    output_dir: Path,
    dashboards_js_version: str = "local",
) -> list[Path]:
    written_paths: list[Path] = []
    dataset_reference_index = build_dataset_reference_index(dataset_entries)

    index_path = output_dir / "dashboards.html"
    index_path.write_text(
        render_generated_page(
            title="Dashboards",
            description="Generated dashboard registry for ether.fi analytics.",
            content=render_dashboard_index(
                entries,
                dataset_reference_index,
                dashboards_js_version=dashboards_js_version,
            ),
            pages=pages,
            template=template,
            active_slug="dashboards",
        ),
        encoding="utf-8",
    )
    written_paths.append(index_path)

    dashboard_dir = output_dir / "dashboards"
    if dashboard_dir.exists():
        shutil.rmtree(dashboard_dir)
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        output_path = dashboard_dir / f"{entry.slug}.html"
        output_path.write_text(
            render_generated_page(
                title=dashboard_title(entry),
                description=str(entry.data.get("description") or ""),
                content=render_dashboard_page(entry, dataset_reference_index),
                pages=pages,
                template=template,
                active_slug="dashboards",
                link_prefix="../",
                asset_prefix="../",
                body_class="dashboard-detail",
            ),
            encoding="utf-8",
        )
        written_paths.append(output_path)

    return written_paths


def write_freshness_page(
    *,
    entries: list[DatasetEntry],
    freshness_registry: dict,
    dashboard_count: int,
    mcp_tool_count: int,
    pages: list[Page],
    template: Template,
    output_dir: Path,
    now: datetime | None = None,
    freshness_js_version: str = "local",
) -> list[Path]:
    index_path = output_dir / "freshness.html"
    index_path.write_text(
        render_generated_page(
            title="Freshness",
            description="Generated freshness status page for ether.fi materialized views.",
            content=render_freshness_page(
                entries,
                freshness_registry,
                dashboard_count=dashboard_count,
                mcp_tool_count=mcp_tool_count,
                now=now,
                freshness_js_version=freshness_js_version,
            ),
            pages=pages,
            template=template,
            active_slug="freshness",
            body_class="freshness-detail",
        ),
        encoding="utf-8",
    )
    return [index_path]


def write_mcp_page(
    *,
    pages: list[Page],
    template: Template,
    output_dir: Path,
) -> list[Path]:
    output_path = output_dir / "mcp.html"
    output_path.write_text(
        render_generated_page(
            title="MCP",
            description="Product documentation for the ether.fi catalog MCP.",
            content=render_mcp_page(),
            pages=pages,
            template=template,
            active_slug="mcp",
            body_class="mcp-detail",
        ),
        encoding="utf-8",
    )
    return [output_path]


def write_home_page(
    *,
    entries: list[DatasetEntry],
    dashboard_entries: list[DashboardEntry],
    freshness_registry: dict,
    pages: list[Page],
    template: Template,
    output_dir: Path,
    now: datetime | None = None,
) -> list[Path]:
    output_path = output_dir / "index.html"
    output_path.write_text(
        render_generated_page(
            title="ether.fi Data Catalog",
            description="Repo-backed catalog for ether.fi datasets, dashboards, freshness status, and MCP workflows.",
            content=render_home_page(
                entries,
                dashboard_entries,
                freshness_registry,
                now=now,
            ),
            pages=pages,
            template=template,
            active_slug="index",
            body_class="home-page",
        ),
        encoding="utf-8",
    )
    return [output_path]


def write_dataset_pages(
    *,
    entries: list[DatasetEntry],
    dashboard_entries: list[DashboardEntry],
    freshness_registry: dict,
    pages: list[Page],
    template: Template,
    output_dir: Path,
    now: datetime | None = None,
    datasets_js_version: str = "local",
    dataset_detail_js_version: str = "local",
) -> list[Path]:
    written_paths: list[Path] = []

    index_path = output_dir / "datasets.html"
    index_path.write_text(
        render_generated_page(
            title="Datasets",
            description="Generated dataset documentation for the ether.fi analytics catalog.",
            content=render_dataset_index(
                entries,
                freshness_registry,
                now=now,
                datasets_js_version=datasets_js_version,
            ),
            pages=pages,
            template=template,
            active_slug="datasets",
        ),
        encoding="utf-8",
    )
    written_paths.append(index_path)

    dataset_dir = output_dir / "datasets"
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        output_path = dataset_dir / f"{entry.slug}.html"
        output_path.write_text(
            render_generated_page(
                title=dataset_title(entry),
                description=str(entry.data.get("description") or ""),
                content=render_dataset_page(
                    entry,
                    entries=entries,
                    dashboard_entries=dashboard_entries,
                    freshness_registry=freshness_registry,
                    now=now,
                    dataset_detail_js_version=dataset_detail_js_version,
                ),
                pages=pages,
                template=template,
                active_slug="datasets",
                link_prefix="../",
                asset_prefix="../",
                body_class="dataset-detail",
            ),
            encoding="utf-8",
        )
        written_paths.append(output_path)

    return written_paths


def build_site(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    datasets_dir: Path | None = DEFAULT_DATASETS_DIR,
    dashboard_registry_path: Path | None = DEFAULT_DASHBOARD_REGISTRY,
    freshness_registry_path: Path | None = DEFAULT_FRESHNESS_REGISTRY,
    now: datetime | None = None,
) -> list[Path]:
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    use_generated_catalog_pages = source_dir.resolve() == DEFAULT_SOURCE_DIR.resolve()
    pages = load_pages(source_dir)
    template = Template((source_dir / "templates" / "base.html.tpl").read_text(encoding="utf-8"))
    dataset_entries = load_dataset_entries(Path(datasets_dir)) if datasets_dir is not None else []
    dashboard_entries = (
        load_dashboard_entries(Path(dashboard_registry_path))
        if dashboard_registry_path is not None
        else []
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    copy_assets(source_dir, output_dir)
    for output_name in unpublished_page_output_names(source_dir) | OBSOLETE_PAGE_OUTPUT_NAMES:
        stale_path = output_dir / output_name
        if stale_path.exists():
            stale_path.unlink()
    freshness_js_version = asset_cache_version(source_dir / "assets" / "freshness.js")
    datasets_js_version = asset_cache_version(source_dir / "assets" / "datasets.js")
    dataset_detail_js_version = asset_cache_version(source_dir / "assets" / "dataset-detail.js")
    dashboards_js_version = asset_cache_version(source_dir / "assets" / "dashboards.js")
    freshness_registry = (
        load_freshness_registry(Path(freshness_registry_path))
        if freshness_registry_path is not None
        else {}
    )

    written_paths: list[Path] = []
    for page in pages:
        if use_generated_catalog_pages and page.slug == "index":
            continue
        if use_generated_catalog_pages and page.slug == "mcp":
            continue
        if page.slug == "datasets" and datasets_dir is not None:
            continue
        if page.slug == "dashboards" and dashboard_registry_path is not None:
            continue
        if page.slug == "freshness" and datasets_dir is not None and freshness_registry_path is not None:
            continue
        output_path = output_dir / page.output_name
        output_path.write_text(render_page(page, pages, template), encoding="utf-8")
        written_paths.append(output_path)

    if use_generated_catalog_pages:
        written_paths.extend(
            write_home_page(
                entries=dataset_entries,
                dashboard_entries=dashboard_entries,
                freshness_registry=freshness_registry,
                pages=pages,
                template=template,
                output_dir=output_dir,
                now=now,
            )
        )

        written_paths.extend(
            write_mcp_page(
                pages=pages,
                template=template,
                output_dir=output_dir,
            )
        )

    if datasets_dir is not None:
        written_paths.extend(
            write_dataset_pages(
                entries=dataset_entries,
                dashboard_entries=dashboard_entries,
                freshness_registry=freshness_registry,
                pages=pages,
                template=template,
                output_dir=output_dir,
                now=now,
                datasets_js_version=datasets_js_version,
                dataset_detail_js_version=dataset_detail_js_version,
            )
        )

    if dashboard_registry_path is not None:
        written_paths.extend(
            write_dashboard_pages(
                entries=dashboard_entries,
                dataset_entries=dataset_entries,
                pages=pages,
                template=template,
                output_dir=output_dir,
                dashboards_js_version=dashboards_js_version,
            )
        )

    if datasets_dir is not None and freshness_registry_path is not None:
        written_paths.extend(
            write_freshness_page(
                entries=dataset_entries,
                freshness_registry=freshness_registry,
                dashboard_count=len(dashboard_entries),
                mcp_tool_count=count_mcp_tools(),
                pages=pages,
                template=template,
                output_dir=output_dir,
                now=now,
                freshness_js_version=freshness_js_version,
            )
        )

    return written_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the presentation website.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE_DIR), help="Website source directory.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="Website output directory.")
    parser.add_argument(
        "--datasets",
        default=str(DEFAULT_DATASETS_DIR),
        help="Dataset metadata directory. Pass an empty string to skip generated dataset pages.",
    )
    parser.add_argument(
        "--dashboards",
        default=str(DEFAULT_DASHBOARD_REGISTRY),
        help="Dashboard metadata directory or legacy registry YAML. Pass an empty string to skip generated dashboard pages.",
    )
    parser.add_argument(
        "--freshness",
        default=str(DEFAULT_FRESHNESS_REGISTRY),
        help="Runtime freshness YAML. Pass an empty string to keep the static freshness page.",
    )
    args = parser.parse_args()

    datasets_dir = Path(args.datasets) if args.datasets else None
    dashboard_registry_path = Path(args.dashboards) if args.dashboards else None
    freshness_registry_path = Path(args.freshness) if args.freshness else None
    written_paths = build_site(
        Path(args.source),
        Path(args.output),
        datasets_dir=datasets_dir,
        dashboard_registry_path=dashboard_registry_path,
        freshness_registry_path=freshness_registry_path,
    )
    print(f"Built {len(written_paths)} pages into {Path(args.output)}")


if __name__ == "__main__":
    main()
