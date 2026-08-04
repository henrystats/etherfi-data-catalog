import base64
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
STUDIO_JS_PATH = ROOT / "website" / "assets" / "studio.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")


def run_node_json(source: str):
    script = (
        f"const studio = require({json.dumps(str(STUDIO_JS_PATH))});\n"
        f"{source}"
    )
    result = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_studio_runtime_exposes_browser_independent_commonjs_helpers():
    exported = run_node_json(
        """
const required = [
  "CHART_STYLES",
  "RANGE_OPTIONS",
  "addressCopyLabel",
  "aggregateSankeyRows",
  "allowedChartStyles",
  "buildCsv",
  "chartPeriodLabel",
  "chartPresentation",
  "chartAnimationConfig",
  "classifySourceFreshness",
  "compactNumber",
  "compareValues",
  "counterValueForRows",
  "createZip",
  "csvEscape",
  "dashboardExportFilename",
  "dashboardGeneratedDate",
  "dateStamp",
  "defaultChartStyle",
  "deriveTableView",
  "explorerUrl",
  "filterTableRows",
  "filterRowsByRange",
  "finiteNumber",
  "formatTooltipValue",
  "formatValue",
  "growthAxisIndex",
  "growthChartModel",
  "growthChartView",
  "growthChartViews",
  "growthDynamicStackEnabled",
  "growthProjectedExportRows",
  "growthTooltipFormat",
  "isSourceStale",
  "latestDate",
  "loadStudioSources",
  "metricCsvEntry",
  "metricExportFilename",
  "metricGeneratedDate",
  "metricSourceNotice",
  "methodologyDetails",
  "momentumChartModel",
  "momentumFilterOptions",
  "momentumValueAxisUsesScale",
  "momentumWeekStart",
  "navigateToSelection",
  "normalizeChain",
  "normalizeDemoBundle",
  "normalizeGeneratedQuery",
  "normalizeManifest",
  "normalizeRefreshStatus",
  "panelToggleModel",
  "periodKeyForMetric",
  "rangeCutoff",
  "rawRowsForMetric",
  "relativeAgeLabel",
  "rowsToCsv",
  "selectedMetricCsvEntries",
  "selectPeriodRow",
  "sectionNavId",
  "setActiveSectionNav",
  "shortAddress",
  "sankeyConservation",
  "sankeyNodeId",
  "sortRows",
  "sortTableRows",
  "sparklineGeometry",
  "stackedBarBorderRadius",
  "stackedBarSeriesData",
  "stableBarInteraction",
  "utcTimestampLabel",
  "utcTimestampDetailLabel",
  "validateExpectedColumns",
  "visibilityDisclosureModel",
  "visibilityDisclosureStorageKey",
  "visibilityStorageKey",
];
console.log(JSON.stringify({
  missing: required.filter((name) => !(name in studio)),
  nonFunctions: required
    .filter((name) => !["CHART_STYLES", "RANGE_OPTIONS"].includes(name))
    .filter((name) => typeof studio[name] !== "function"),
  rowsAlias: studio.rowsToCsv === studio.buildCsv,
  sortAlias: studio.sortTableRows === studio.sortRows,
  chartStyles: studio.CHART_STYLES,
  motion: {
    default: studio.chartAnimationConfig(false),
    reduced: studio.chartAnimationConfig(true),
  },
  ranges: studio.RANGE_OPTIONS,
}));
"""
    )

    assert exported == {
        "missing": [],
        "nonFunctions": [],
        "rowsAlias": True,
        "sortAlias": True,
        "chartStyles": ["line", "area", "column", "scatter"],
        "motion": {
            "default": {
                "animation": True,
                "animationDuration": 380,
                "animationDurationUpdate": 260,
            },
            "reduced": {
                "animation": False,
                "animationDuration": 0,
                "animationDurationUpdate": 0,
            },
        },
        "ranges": ["7D", "30D", "90D", "YTD", "1Y", "ALL"],
    }


def test_visibility_storage_key_resets_only_when_dashboard_registry_changes():
    result = run_node_json(
        """
const base = [
  { id: "a", default_visible: true },
  { id: "b", default_visible: false },
];
const sameReordered = [
  { id: "b", default_visible: false },
  { id: "a", default_visible: true },
];
const baseKey = studio.visibilityStorageKey("kyberswap_campaign", base);
console.log(JSON.stringify({
  prefix: baseKey.startsWith(
    "etherfi.studio.visibility.v2.kyberswap_campaign.",
  ),
  orderStable: baseKey === studio.visibilityStorageKey(
    "kyberswap_campaign",
    sameReordered,
  ),
  addedChanges: baseKey !== studio.visibilityStorageKey(
    "kyberswap_campaign",
    [...base, { id: "c", default_visible: true }],
  ),
  defaultChanges: baseKey !== studio.visibilityStorageKey(
    "kyberswap_campaign",
    [
      { id: "a", default_visible: false },
      { id: "b", default_visible: false },
    ],
  ),
  dashboardChanges: baseKey !== studio.visibilityStorageKey("demo", base),
  legacyIgnored: baseKey !== "etherfi.studio.visibility.v1.kyberswap_campaign",
}));
"""
    )

    assert result == {
        "prefix": True,
        "orderStable": True,
        "addedChanges": True,
        "defaultChanges": True,
        "dashboardChanges": True,
        "legacyIgnored": True,
    }


def test_visibility_disclosure_state_is_dashboard_scoped_and_toggles_independently():
    result = run_node_json(
        """
const metrics = [
  { id: "a", section: "counters" },
  { id: "b", section: "growth" },
  { id: "c", section: "growth" },
  { id: "d", section: "flows" },
];
const key = studio.visibilityDisclosureStorageKey("kyberswap_campaign", metrics);
const reorderedWithinSection = [metrics[0], metrics[2], metrics[1], metrics[3]];
const opened = studio.visibilityDisclosureModel(["counters"], "growth");
const closed = studio.visibilityDisclosureModel(opened, "counters");
console.log(JSON.stringify({
  prefix: key.startsWith(
    "etherfi.studio.visibility-sections.v1.kyberswap_campaign.",
  ),
  metricOrderStable: key === studio.visibilityDisclosureStorageKey(
    "kyberswap_campaign",
    reorderedWithinSection,
  ),
  sectionOrderChanges: key !== studio.visibilityDisclosureStorageKey(
    "kyberswap_campaign",
    [metrics[1], metrics[0], metrics[3]],
  ),
  dashboardChanges: key !== studio.visibilityDisclosureStorageKey("demo", metrics),
  opened,
  closed,
  blankIgnored: studio.visibilityDisclosureModel(closed, ""),
}));
"""
    )

    assert result == {
        "prefix": True,
        "metricOrderStable": True,
        "sectionOrderChanges": True,
        "dashboardChanges": True,
        "opened": ["counters", "growth"],
        "closed": ["growth"],
        "blankIgnored": ["growth"],
    }


def test_panel_toggle_model_keeps_left_and_right_state_independent():
    result = run_node_json(
        """
const initial = { leftCollapsed: "true", rightCollapsed: "true" };
const leftOpen = studio.panelToggleModel(initial, "left");
const rightOpen = studio.panelToggleModel(initial, "right");
const bothOpen = studio.panelToggleModel({
  leftCollapsed: String(leftOpen.leftCollapsed),
  rightCollapsed: String(leftOpen.rightCollapsed),
}, "right");
const leftClosed = studio.panelToggleModel({
  leftCollapsed: String(bothOpen.leftCollapsed),
  rightCollapsed: String(bothOpen.rightCollapsed),
}, "left");
console.log(JSON.stringify({ initial, leftOpen, rightOpen, bothOpen, leftClosed }));
"""
    )

    assert result["initial"] == {
        "leftCollapsed": "true",
        "rightCollapsed": "true",
    }
    assert result["leftOpen"] == {
        "leftCollapsed": False,
        "rightCollapsed": True,
        "collapsed": False,
        "ariaExpanded": "true",
        "ariaLabel": "Collapse dashboard navigation panel",
        "icon": "←",
    }
    assert result["rightOpen"] == {
        "leftCollapsed": True,
        "rightCollapsed": False,
        "collapsed": False,
        "ariaExpanded": "true",
        "ariaLabel": "Collapse metrics and downloads panel",
        "icon": "→",
    }
    assert result["bothOpen"]["leftCollapsed"] is False
    assert result["bothOpen"]["rightCollapsed"] is False
    assert result["leftClosed"]["leftCollapsed"] is True
    assert result["leftClosed"]["rightCollapsed"] is False
    assert result["leftClosed"]["ariaLabel"] == (
        "Expand dashboard navigation panel"
    )
    assert result["leftClosed"]["icon"] == "→"


def test_csv_helpers_escape_special_values_and_keep_metric_column_scope():
    result = run_node_json(
        """
const rows = [
  {
    name: 'Alpha, "Beta"',
    note: "line 1\\nline 2",
    amount: 42,
    ignored: "not exported",
  },
  { name: " padded ", note: null, amount: 0, later: "also ignored" },
];
const inferredRows = [{ first: 1 }, { second: 2, first: 3 }];
console.log(JSON.stringify({
  escaped: {
    comma: studio.csvEscape("alpha,beta"),
    quote: studio.csvEscape('He said "yes"'),
    newline: studio.csvEscape("line 1\\nline 2"),
    whitespace: studio.csvEscape(" padded "),
    formula: studio.csvEscape("=SUM(A1:A2)"),
    atFormula: studio.csvEscape("@SUM(A1:A2)"),
    negativeNumber: studio.csvEscape(-42),
    nullValue: studio.csvEscape(null),
    objectValue: studio.csvEscape({ state: "ready" }),
    dateValue: studio.csvEscape(new Date("2026-07-30T12:34:56Z")),
  },
  csv: studio.buildCsv(rows, ["name", "note", "amount"]),
  aliasCsv: studio.rowsToCsv(rows, ["name", "note", "amount"]),
  inferredCsv: studio.buildCsv(inferredRows),
}));
"""
    )

    assert result["escaped"] == {
        "comma": '"alpha,beta"',
        "quote": '"He said ""yes"""',
        "newline": '"line 1\nline 2"',
        "whitespace": '" padded "',
        "formula": "'=SUM(A1:A2)",
        "atFormula": "'@SUM(A1:A2)",
        "negativeNumber": "-42",
        "nullValue": "",
        "objectValue": '"{""state"":""ready""}"',
        "dateValue": "2026-07-30T12:34:56.000Z",
    }
    expected_csv = (
        'name,note,amount\r\n'
        '"Alpha, ""Beta""","line 1\nline 2",42\r\n'
        '" padded ",,0\r\n'
    )
    assert result["csv"] == expected_csv
    assert result["aliasCsv"] == expected_csv
    assert result["inferredCsv"] == "first,second\r\n1,\r\n3,2\r\n"


def test_date_range_helpers_use_inclusive_utc_calendar_days_without_mutation():
    result = run_node_json(
        """
const rows = [
  { id: "future", day: "2026-07-31" },
  { id: "end-late", day: "2026-07-30T23:59:59Z" },
  { id: "start", day: "2026-07-24" },
  { id: "too-old", day: "2026-07-23" },
  { id: "invalid", day: "not-a-date" },
];
const sevenDays = studio.filterRowsByRange(
  rows,
  "day",
  "7D",
  "2026-07-30T18:40:00Z",
);
const allRows = studio.filterRowsByRange(rows, "day", "ALL");
console.log(JSON.stringify({
  latest: studio.latestDate(rows, "day"),
  noLatest: studio.latestDate([{ day: "invalid" }], "day"),
  cutoffs: Object.fromEntries(
    studio.RANGE_OPTIONS.map((range) => {
      const value = studio.rangeCutoff(range, "2026-07-30T18:40:00Z");
      return [range, value ? value.toISOString() : null];
    }),
  ),
  invalidCutoff: studio.rangeCutoff("UNKNOWN", "2026-07-30"),
  sevenDays: sevenDays.map((row) => row.id),
  allRows: allRows.map((row) => row.id),
  cloned: sevenDays !== rows && allRows !== rows,
  original: rows.map((row) => row.id),
  ytd: studio.filterRowsByRange(
    [
      { id: "prior", day: "2025-12-31" },
      { id: "first", day: "2026-01-01" },
      { id: "current", day: "2026-07-30" },
    ],
    "day",
    "YTD",
    "2026-07-30",
  ).map((row) => row.id),
}));
"""
    )

    assert result["latest"] == "2026-07-31T00:00:00.000Z"
    assert result["noLatest"] is None
    assert result["cutoffs"] == {
        "7D": "2026-07-24T00:00:00.000Z",
        "30D": "2026-07-01T00:00:00.000Z",
        "90D": "2026-05-02T00:00:00.000Z",
        "YTD": "2026-01-01T00:00:00.000Z",
        "1Y": "2025-07-31T00:00:00.000Z",
        "ALL": None,
    }
    assert result["invalidCutoff"] is None
    assert result["sevenDays"] == ["end-late", "start"]
    assert result["allRows"] == [
        "future",
        "end-late",
        "start",
        "too-old",
        "invalid",
    ]
    assert result["cloned"] is True
    assert result["original"] == result["allRows"]
    assert result["ytd"] == ["first", "current"]


def test_momentum_cumulative_filters_source_days_before_monday_weekly_grouping():
    result = run_node_json(
        """
const rows = [
  { record_type: "daily_total", granularity: "daily", period: "2026-07-28", amount_usd: "100", num_deposits: 10 },
  { record_type: "daily_total", granularity: "daily", period: "2026-07-31", amount_usd: "5", num_deposits: 2 },
  { record_type: "daily_total", granularity: "daily", period: "2026-08-01", amount_usd: "7", num_deposits: 1 },
  { record_type: "daily_total", granularity: "daily", period: "2026-08-03", amount_usd: "11", num_deposits: 3 },
  { record_type: "daily_total", granularity: "daily", period: "2026-08-04", amount_usd: "13", num_deposits: 4 },
  { record_type: "weekly_total", granularity: "weekly", period: "2026-07-27", amount_usd: "999", num_deposits: 99 },
];
const metric = {
  momentum_chart: {
    kind: "cumulative",
    default_granularity: "daily",
    export_columns: [
      "period",
      "period_deposits_usd",
      "cumulative_deposits_usd",
      "granularity",
    ],
  },
};
const original = JSON.stringify(rows);
const weekly = studio.momentumChartModel(rows, metric, {
  granularity: "weekly",
  activeRange: "7D",
  referenceDate: "2026-08-04",
});
const daily = studio.momentumChartModel(rows, metric, {
  granularity: "daily",
  activeRange: "7D",
  referenceDate: "2026-08-04",
});
console.log(JSON.stringify({
  weekStarts: [
    studio.momentumWeekStart("2026-08-02"),
    studio.momentumWeekStart("2026-08-03"),
    studio.momentumWeekStart("invalid"),
  ],
  labels: {
    weeklyAxis: studio.chartPeriodLabel("2026-08-03", "weekly"),
    weeklyTooltip: studio.chartPeriodLabel("2026-08-03", "weekly", {
      includeYear: true,
      tooltip: true,
    }),
    dailyAxis: studio.chartPeriodLabel("2026-08-03", "daily"),
    crossYearWeeklyAxis: [
      studio.chartPeriodLabel("2025-12-29", "weekly", { includeYear: true }),
      studio.chartPeriodLabel("2026-01-05", "weekly", { includeYear: true }),
    ],
  },
  weekly,
  dailyFirst: daily.exportRows[0],
  unchanged: original === JSON.stringify(rows),
}));
"""
    )

    assert result["weekStarts"] == ["2026-07-27", "2026-08-03", ""]
    assert result["labels"] == {
        "weeklyAxis": "03 Aug",
        "weeklyTooltip": "Week of 03 Aug 2026",
        "dailyAxis": "03 Aug",
        "crossYearWeeklyAxis": ["29 Dec 2025", "05 Jan 2026"],
    }
    assert "Week of" not in result["labels"]["weeklyAxis"]
    assert result["weekly"]["periods"] == ["2026-07-27", "2026-08-03"]
    assert result["weekly"]["series"] == [
        {"name": "Cumulative deposits", "values": [12, 36]}
    ]
    assert result["weekly"]["exportRows"] == [
        {
            "period": "2026-07-27",
            "period_deposits_usd": "12",
            "cumulative_deposits_usd": "12",
            "granularity": "weekly",
        },
        {
            "period": "2026-08-03",
            "period_deposits_usd": "24",
            "cumulative_deposits_usd": "36",
            "granularity": "weekly",
        },
    ]
    assert result["weekly"]["context"] == "Weekly · Measured in USD"
    assert result["dailyFirst"] == {
        "period": "2026-07-31",
        "period_deposits_usd": "5",
        "cumulative_deposits_usd": "5",
        "granularity": "daily",
    }
    assert result["unchanged"] is True


def test_relative_age_uses_fixed_reference_grammar_and_full_utc_detail():
    result = run_node_json(
        """
const reference = "2026-08-03T00:00:00Z";
globalThis.__STUDIO_REFERENCE_TIME__ = reference;
const ages = {
  justNow: studio.relativeAgeLabel("2026-08-02T23:59:40Z", reference),
  oneMinute: studio.relativeAgeLabel("2026-08-02T23:59:00Z", reference),
  minutes: studio.relativeAgeLabel("2026-08-02T23:31:00Z", reference),
  oneHour: studio.relativeAgeLabel("2026-08-02T23:00:00Z", reference),
  hours: studio.relativeAgeLabel("2026-08-02T18:00:00Z", reference),
  oneDay: studio.relativeAgeLabel("2026-08-02T00:00:00Z", reference),
  days: studio.relativeAgeLabel("2026-07-26T00:00:00Z", reference),
  oneMonth: studio.relativeAgeLabel("2026-07-04T00:00:00Z", reference),
  months: studio.relativeAgeLabel("2026-05-05T00:00:00Z", reference),
  oneYear: studio.relativeAgeLabel("2025-08-03T00:00:00Z", reference),
};
console.log(JSON.stringify({
  ages,
  fixedDefault: studio.relativeAgeLabel("2026-08-02T23:31:00Z"),
  detail: studio.utcTimestampDetailLabel("2026-08-02T23:31:47Z"),
}));
"""
    )

    assert result == {
        "ages": {
            "justNow": "Just now",
            "oneMinute": "1 min ago",
            "minutes": "29 mins ago",
            "oneHour": "1 hr ago",
            "hours": "6 hrs ago",
            "oneDay": "1 day ago",
            "days": "8 days ago",
            "oneMonth": "1 month ago",
            "months": "3 months ago",
            "oneYear": "1 year ago",
        },
        "fixedDefault": "29 mins ago",
        "detail": "02 Aug 2026 · 23:31:47 UTC",
    }


def test_recent_activity_uses_raw_timestamp_for_sorting_and_csv_export():
    result = run_node_json(
        """
const address = "0x1234567890abcdef1234567890abcdef12345678";
const rows = [
  {
    block_time: "2026-08-01T05:00:00Z",
    address,
    tx_hash: `0x${"1".repeat(64)}`,
  },
  {
    block_time: "2026-08-02T23:31:47Z",
    address,
    tx_hash: `0x${"2".repeat(64)}`,
  },
  {
    block_time: "2026-08-02T09:15:30Z",
    address,
    tx_hash: `0x${"3".repeat(64)}`,
  },
];
const metric = {
  id: "kyber_recent_referral_deposits",
  intelligence_component: "recent_referral_deposits",
  data_source: "kyberswap_referral_deposit_events",
  date_column: "block_time",
  table_columns: ["block_time", "address", "tx_hash"],
  export_columns: ["block_time", "address", "tx_hash"],
  export_slug: "kyberswap-recent-referral-deposits",
};
const orphan = {
  block_time: "2026-08-03T00:00:00Z",
  address: `0x${"f".repeat(40)}`,
  tx_hash: `0x${"4".repeat(64)}`,
};
const primaryRows = [...rows, orphan];
const state = {
  activeRange: "ALL",
  config: { dashboard: { id: "kyberswap_campaign", slug: "kyberswap" } },
  data: {
    meta: { generated_at: "2026-08-03T00:00:00Z" },
    datasets: {
      kyberswap_referral_deposit_events: primaryRows,
      kyberswap_depositor_intelligence: {
        wallets: [{ address, referral_deposits: rows }],
      },
    },
    sourceMeta: {
      kyberswap_referral_deposit_events: {
        generated_at: "2026-08-03T00:00:00Z",
        columns: ["block_time", "address", "tx_hash"],
      },
    },
  },
};
const view = studio.deriveTableView(rows, metric.table_columns, {
  sortColumn: "block_time",
  sortDirection: "descending",
  pageSize: 10,
});
const entry = studio.metricCsvEntry(state, metric);
const renderedRows = studio.rawRowsForMetric(state, metric);
console.log(JSON.stringify({
  sorted: view.rows.map((row) => row.block_time),
  renderedCount: renderedRows.length,
  renderedHasOrphan: renderedRows.some((row) => row.tx_hash === orphan.tx_hash),
  csv: entry.data,
  txCopyLabel: studio.addressCopyLabel(rows[0].tx_hash, "tx_hash"),
  addressCopyLabel: studio.addressCopyLabel(address, "address"),
}));
"""
    )

    assert result["sorted"] == [
        "2026-08-02T23:31:47Z",
        "2026-08-02T09:15:30Z",
        "2026-08-01T05:00:00Z",
    ]
    assert result["renderedCount"] == 4
    assert result["renderedHasOrphan"] is True
    assert result["csv"].startswith("block_time,address,tx_hash\r\n")
    assert "2026-08-02T23:31:47Z" in result["csv"]
    assert "0x" + ("4" * 64) in result["csv"]
    assert "ago" not in result["csv"]
    assert result["txCopyLabel"] == (
        "Copy transaction hash 0x" + ("1" * 64)
    )
    assert result["addressCopyLabel"] == (
        "Copy address 0x1234567890abcdef1234567890abcdef12345678"
    )


def test_depositor_renderers_keep_compact_accessible_controls_and_five_metrics():
    source = STUDIO_JS_PATH.read_text(encoding="utf-8")

    def function_source(name: str) -> str:
        match = re.search(
            rf"  function {re.escape(name)}\(.*?(?=\n  function |\n  return \{{)",
            source,
            re.DOTALL,
        )
        assert match, name
        return match.group(0)

    summary = function_source("appendWalletSummaryCards")
    assert [
        "Total Referral Deposits",
        "Attributed TVL",
        "Depositor Type",
        "Retention Rate",
        "Products Deposited",
    ] == re.findall(r'^\s+\["([^"]+)", wallet\.', summary, re.MULTILINE)
    assert "Exited Balance" not in summary
    assert "Current Locations" not in summary

    investigation = function_source("renderWalletInvestigation")
    assert "studio-wallet-meta" not in investigation
    assert "appendWalletLatestActivity" not in investigation
    assert "Latest Referral Deposit" not in investigation
    assert "Latest ether.fi Activity" not in investigation
    assert (
        'columns: ["strategy_symbol", "current_token", '
        '"current_token_category", "referral_balance", "current_balance", '
        '"attributed_balance", "exited_balance"]'
    ) in investigation
    assert 'labels: { block_time: "Age"' in investigation
    assert 'tx_hash: "Transaction"' in investigation
    assert 'relativeTimeColumns: ["block_time"]' in investigation
    assert "allocation_rule" not in investigation

    copy_icon = function_source("appendCopyIcon")
    identifier_cell = function_source("appendIdentifierCell")
    copy_feedback = function_source("showCopyFeedback")
    table_renderer = function_source("renderTable")
    assert 'createElementNS("http://www.w3.org/2000/svg", "svg")' in copy_icon
    assert '["3", "3"]' in copy_icon
    assert '["7", "7"]' in copy_icon
    assert 'svg.setAttribute("aria-hidden", "true")' in copy_icon
    assert '"visually-hidden studio-copy-status"' in copy_icon
    assert 'compactCopy ? undefined : "Copy"' in identifier_cell
    assert "appendCopyIcon(scope, button)" in identifier_cell
    assert 'button.setAttribute("aria-label", copyLabel)' in identifier_cell
    assert 'button.title = copyLabel' in identifier_cell
    assert 'button.querySelector("[data-copy-status]")' in copy_feedback
    assert 'status.textContent = copied ? "Copied." : "Copy failed."' in copy_feedback
    assert "{ compactCopy: isRecentActivityTable(metric) }" in table_renderer
    assert "appendRelativeAgeCell(body.ownerDocument, cell, value)" in table_renderer
    assert "studio-table-compact-text" in table_renderer
    assert "text.setAttribute(\"aria-label\", String(value))" in table_renderer

    assert "const RELATIVE_AGE_REFRESH_MS = 60 * 1000;" in source
    assert 'querySelectorAll("[data-relative-timestamp]")' in source
    assert "root.setInterval" in function_source("startRelativeAgeRefresh")


def test_momentum_product_model_orders_dynamic_products_filters_and_exports_csv():
    result = run_node_json(
        """
const rows = [
  { record_type: "daily_product", granularity: "daily", period: "2026-08-03", strategy_symbol: "ultraETH", amount_usd: "50", num_deposits: 1 },
  { record_type: "daily_product", granularity: "daily", period: "2026-07-31", strategy_symbol: "liquidETH", amount_usd: "20", num_deposits: 2 },
  { record_type: "daily_product", granularity: "daily", period: "2026-08-03", strategy_symbol: "liquidBTC", amount_usd: "40", num_deposits: 4 },
  { record_type: "daily_product", granularity: "daily", period: "2026-07-31", strategy_symbol: "eETH", amount_usd: "10", num_deposits: 1 },
  { record_type: "daily_product", granularity: "daily", period: "2026-08-03", strategy_symbol: "liquidUSD", amount_usd: "30", num_deposits: 3 },
];
const metric = {
  id: "product",
  name: "Referral Deposits by Product",
  data_source: "momentum",
  export_slug: "kyberswap-referral-deposits-by-product",
  momentum_chart: {
    kind: "product",
    default_granularity: "daily",
    filter_column: "strategy_symbol",
    filter_order: ["eETH", "liquidETH", "liquidUSD", "liquidBTC"],
    all_label: "All products",
    export_columns: [
      "period",
      "strategy_symbol",
      "amount_usd",
      "granularity",
      "selected_product",
    ],
  },
};
const allWeekly = studio.momentumChartModel(rows, metric, {
  granularity: "weekly",
  filter: "all",
  activeRange: "ALL",
  style: "column",
});
const allWeeklyArea = studio.momentumChartModel(rows, metric, {
  granularity: "weekly",
  filter: "all",
  activeRange: "ALL",
  style: "area",
});
const selected = studio.momentumChartModel(rows, metric, {
  granularity: "daily",
  filter: "liquidETH",
  activeRange: "ALL",
});
const state = {
  activeRange: "ALL",
  referenceDate: "2026-08-03",
  config: { dashboard: { id: "kyberswap_campaign", slug: "kyberswap" } },
  data: {
    meta: { generated_at: "2026-08-04T01:00:00Z" },
    datasets: { momentum: rows },
    sourceMeta: {
      momentum: { execution_finished_at: "2026-08-03T23:00:00Z" },
    },
  },
  momentumSelections: new Map([
    ["product", { granularity: "daily", filter: "liquidETH" }],
  ]),
};
console.log(JSON.stringify({
  options: studio.momentumFilterOptions(rows, metric),
  allWeekly,
  styleIndependent: JSON.stringify(allWeekly) === JSON.stringify(allWeeklyArea),
  selected,
  csv: studio.metricCsvEntry(state, metric),
}));
"""
    )

    assert result["options"] == [
        "eETH",
        "liquidETH",
        "liquidUSD",
        "liquidBTC",
        "ultraETH",
    ]
    assert result["allWeekly"]["series"] == [
        {"name": "eETH", "values": [10, 0]},
        {"name": "liquidETH", "values": [20, 0]},
        {"name": "liquidUSD", "values": [0, 30]},
        {"name": "liquidBTC", "values": [0, 40]},
        {"name": "ultraETH", "values": [0, 50]},
    ]
    assert result["allWeekly"]["shouldStack"] is True
    assert result["allWeekly"]["context"] == (
        "Weekly · All products · Measured in USD"
    )
    assert result["styleIndependent"] is True
    assert result["selected"]["series"] == [
        {"name": "liquidETH", "values": [20]}
    ]
    assert result["selected"]["shouldStack"] is False
    assert result["selected"]["context"] == (
        "Daily · liquidETH · Measured in USD"
    )
    assert result["selected"]["exportRows"] == [
        {
            "period": "2026-07-31",
            "strategy_symbol": "liquidETH",
            "amount_usd": "20",
            "granularity": "daily",
            "selected_product": "liquidETH",
        }
    ]
    assert result["csv"] == {
        "name": (
            "kyberswap-referral-deposits-by-product-all-2026-08-03.csv"
        ),
        "data": (
            "period,strategy_symbol,amount_usd,granularity,selected_product\r\n"
            "2026-07-31,liquidETH,20,daily,liquidETH\r\n"
        ),
    }


def test_momentum_depositor_model_uses_exact_new_old_classifications():
    result = run_node_json(
        """
const rows = [
  { record_type: "daily_depositor", granularity: "daily", period: "2026-08-01", new_or_old: "Old Depositor", amount_usd: "25", num_deposits: 2 },
  { record_type: "daily_depositor", granularity: "daily", period: "2026-08-01", new_or_old: "New Depositor", amount_usd: "75", num_deposits: 5 },
  { record_type: "daily_depositor", granularity: "daily", period: "2026-08-03", new_or_old: "Old Depositor", amount_usd: "30", num_deposits: 3 },
  { record_type: "daily_depositor", granularity: "daily", period: "2026-08-03", new_or_old: "New Depositor", amount_usd: "70", num_deposits: 4 },
];
const metric = {
  momentum_chart: {
    kind: "depositor",
    default_granularity: "daily",
    filter_column: "new_or_old",
    filter_order: ["New Depositor", "Old Depositor"],
    all_label: "All depositors",
    export_columns: [
      "period",
      "new_or_old",
      "amount_usd",
      "granularity",
      "selected_classification",
    ],
  },
};
const all = studio.momentumChartModel(rows, metric, {
  granularity: "daily",
  filter: "all",
  activeRange: "ALL",
});
const oldOnly = studio.momentumChartModel(rows, metric, {
  granularity: "weekly",
  filter: "Old Depositor",
  activeRange: "ALL",
});
console.log(JSON.stringify({
  options: studio.momentumFilterOptions(rows, metric),
  all,
  oldOnly,
}));
"""
    )

    assert result["options"] == ["New Depositor", "Old Depositor"]
    assert result["all"]["series"] == [
        {"name": "New Depositor", "values": [75, 70]},
        {"name": "Old Depositor", "values": [25, 30]},
    ]
    assert result["all"]["shouldStack"] is True
    assert result["all"]["context"] == (
        "Daily · All depositors · Measured in USD"
    )
    assert result["oldOnly"]["series"] == [
        {"name": "Old Depositor", "values": [25, 30]}
    ]
    assert result["oldOnly"]["shouldStack"] is False
    assert result["oldOnly"]["exportRows"] == [
        {
            "period": "2026-07-27",
            "new_or_old": "Old Depositor",
            "amount_usd": "25",
            "granularity": "weekly",
            "selected_classification": "Old Depositor",
        },
        {
            "period": "2026-08-03",
            "new_or_old": "Old Depositor",
            "amount_usd": "30",
            "granularity": "weekly",
            "selected_classification": "Old Depositor",
        },
    ]
    assert "Existing Depositor" not in json.dumps(result)


def test_momentum_activity_uses_integer_counts_for_scatter_column_and_csv():
    result = run_node_json(
        """
const rows = [
  { record_type: "daily_total", granularity: "daily", period: "2026-08-01", amount_usd: "100.25", num_deposits: 2 },
  { record_type: "daily_total", granularity: "daily", period: "2026-08-02", amount_usd: "200.50", num_deposits: 3 },
  { record_type: "daily_total", granularity: "daily", period: "2026-08-03", amount_usd: "300.75", num_deposits: 4 },
];
const metric = {
  id: "activity",
  name: "Referral Deposit Activity",
  data_source: "momentum",
  export_slug: "kyberswap-referral-deposit-activity",
  momentum_chart: {
    kind: "activity",
    default_granularity: "daily",
    export_columns: ["period", "num_deposits", "granularity"],
  },
};
const scatter = studio.momentumChartModel(rows, metric, {
  granularity: "weekly",
  activeRange: "ALL",
  style: "scatter",
});
const column = studio.momentumChartModel(rows, metric, {
  granularity: "weekly",
  activeRange: "ALL",
  style: "column",
});
const state = {
  activeRange: "ALL",
  referenceDate: "2026-08-03",
  config: { dashboard: { id: "kyberswap_campaign" } },
  data: {
    meta: { generated_at: "2026-08-03T13:00:00Z" },
    datasets: { momentum: rows },
    sourceMeta: { momentum: { data_updated_at: "2026-08-03T12:00:00Z" } },
  },
  momentumSelections: new Map([
    ["activity", { granularity: "weekly", filter: "all" }],
  ]),
};
console.log(JSON.stringify({
  scatter,
  styleIndependent: JSON.stringify(scatter) === JSON.stringify(column),
  integers: scatter.series[0].values.every(Number.isInteger),
  csv: studio.metricCsvEntry(state, metric),
}));
"""
    )

    assert result["scatter"]["series"] == [
        {"name": "Referral deposits", "values": [5, 4]}
    ]
    assert result["scatter"]["exportRows"] == [
        {"period": "2026-07-27", "num_deposits": 5, "granularity": "weekly"},
        {"period": "2026-08-03", "num_deposits": 4, "granularity": "weekly"},
    ]
    assert result["scatter"]["context"] == "Weekly · Number of deposits"
    assert result["styleIndependent"] is True
    assert result["integers"] is True
    assert result["csv"] == {
        "name": "kyberswap-referral-deposit-activity-all-2026-08-03.csv",
        "data": (
            "period,num_deposits,granularity\r\n"
            "2026-07-27,5,weekly\r\n"
            "2026-08-03,4,weekly\r\n"
        ),
    }


def test_momentum_exports_preserve_exact_decimal_values_and_sums():
    result = run_node_json(
        """
const totalRows = [
  { record_type: "daily_total", period: "2026-02-02", amount_usd: "1178.6049907477040005", num_deposits: 1 },
  { record_type: "daily_total", period: "2026-02-03", amount_usd: "0.0000000000000005", num_deposits: 1 },
  { record_type: "daily_total", period: "2026-02-09", amount_usd: "9007199254740992.123456789", num_deposits: 1 },
];
const cumulativeMetric = {
  momentum_chart: {
    kind: "cumulative",
    default_granularity: "daily",
    export_columns: [
      "period",
      "period_deposits_usd",
      "cumulative_deposits_usd",
      "granularity",
    ],
  },
};
const productRows = [
  { record_type: "daily_product", period: "2026-02-02", strategy_symbol: "eETH", amount_usd: "1178.6049907477040005", num_deposits: 1 },
  { record_type: "daily_product", period: "2026-02-03", strategy_symbol: "eETH", amount_usd: "0.0000000000000005", num_deposits: 1 },
];
const productMetric = {
  momentum_chart: {
    kind: "product",
    default_granularity: "daily",
    filter_column: "strategy_symbol",
    filter_order: ["eETH"],
    all_label: "All products",
    export_columns: [
      "period",
      "strategy_symbol",
      "amount_usd",
      "granularity",
      "selected_product",
    ],
  },
};
const cumulative = studio.momentumChartModel(totalRows, cumulativeMetric, {
  granularity: "weekly",
  activeRange: "ALL",
});
const product = studio.momentumChartModel(productRows, productMetric, {
  granularity: "weekly",
  filter: "all",
  activeRange: "ALL",
});
console.log(JSON.stringify({
  cumulativeExports: cumulative.exportRows,
  cumulativeSeriesAreNumbers: cumulative.series[0].values
    .every((value) => typeof value === "number"),
  productExports: product.exportRows,
  productSeriesAreNumbers: product.series[0].values
    .every((value) => typeof value === "number"),
  cumulativeCsv: studio.buildCsv(
    cumulative.exportRows,
    cumulativeMetric.momentum_chart.export_columns,
  ),
}));
"""
    )

    assert result["cumulativeExports"] == [
        {
            "period": "2026-02-02",
            "period_deposits_usd": "1178.604990747704001",
            "cumulative_deposits_usd": "1178.604990747704001",
            "granularity": "weekly",
        },
        {
            "period": "2026-02-09",
            "period_deposits_usd": "9007199254740992.123456789",
            "cumulative_deposits_usd": "9007199254742170.728447536704001",
            "granularity": "weekly",
        },
    ]
    assert result["cumulativeSeriesAreNumbers"] is True
    assert result["productExports"] == [
        {
            "period": "2026-02-02",
            "strategy_symbol": "eETH",
            "amount_usd": "1178.604990747704001",
            "granularity": "weekly",
            "selected_product": "All",
        }
    ]
    assert result["productSeriesAreNumbers"] is True
    assert result["cumulativeCsv"] == (
        "period,period_deposits_usd,cumulative_deposits_usd,granularity\r\n"
        "2026-02-02,1178.604990747704001,1178.604990747704001,weekly\r\n"
        "2026-02-09,9007199254740992.123456789,"
        "9007199254742170.728447536704001,weekly\r\n"
    )


def test_momentum_value_axes_use_zero_baselines_for_columns_areas_and_counts():
    result = run_node_json(
        """
console.log(JSON.stringify({
  cumulative: {
    line: studio.momentumValueAxisUsesScale("cumulative", "line"),
    area: studio.momentumValueAxisUsesScale("cumulative", "area"),
  },
  product: {
    line: studio.momentumValueAxisUsesScale("product", "line"),
    area: studio.momentumValueAxisUsesScale("product", "area"),
    column: studio.momentumValueAxisUsesScale("product", "column"),
  },
  depositorColumn: studio.momentumValueAxisUsesScale("depositor", "column"),
  activity: {
    scatter: studio.momentumValueAxisUsesScale("activity", "scatter"),
    column: studio.momentumValueAxisUsesScale("activity", "column"),
  },
}));
"""
    )

    assert result == {
        "cumulative": {"line": True, "area": False},
        "product": {"line": True, "area": False, "column": False},
        "depositorColumn": False,
        "activity": {"scatter": False, "column": False},
    }


def test_growth_combo_uses_granularity_columns_dual_axes_and_exact_csv():
    result = run_node_json(
        """
const rows = [
  {
    record_type: "referral_daily",
    period: "2026-08-01",
    daily_deposits_usd: "1178.6049907477040005",
    cum_deposits_usd: "9007199254740992.1234567895",
    last_updated: "2026-08-01T12:00:00Z",
    source_last_updated: "2026-08-01T15:00:00Z",
  },
  {
    record_type: "referral_daily",
    period: "2026-07-31",
    daily_deposits_usd: "0.0000000000000005",
    cum_deposits_usd: "9007199254740992.123456789",
    last_updated: "2026-07-31T12:00:00Z",
    source_last_updated: "2026-07-31T15:00:00Z",
  },
  {
    record_type: "referral_daily",
    period: "2026-08-04",
    daily_deposits_usd: "25.25",
    cum_deposits_usd: "9007199254741017.3734567895",
    last_updated: "2026-08-04T12:00:00Z",
    source_last_updated: "2026-08-04T15:00:00Z",
  },
  {
    record_type: "referral_weekly",
    period: "2026-07-28",
    weekly_deposits_usd: "999999",
    cum_deposits_usd: "999999",
  },
];
const metric = {
  id: "kyber_referral_deposits_growth",
  name: "Referral Deposits",
  data_source: "growth",
  date_column: "period",
  format: "currency_compact",
  export_slug: "kyberswap-referral-deposits-growth",
  growth_chart: {
    kind: "combo",
    default_granularity: "weekly",
    available_granularities: ["weekly"],
    default_view: "all",
    rebuild_weekly_from_daily: true,
    views: [{
      id: "all",
      label: "All referrals",
      record_types: { daily: "referral_daily", weekly: "referral_weekly" },
    }],
    measures: [
      {
        column_by_granularity: {
          daily: "daily_deposits_usd",
          weekly: "weekly_deposits_usd",
        },
        label: "Referral deposits",
        format: "currency_compact",
        series_type: "column",
        axis: "left",
        aggregation: "sum",
      },
      {
        column: "cum_deposits_usd",
        label: "Cumulative deposits",
        format: "currency_compact",
        series_type: "line",
        axis: "right",
        aggregation: "latest",
      },
    ],
    export_columns: [
      "period",
      "period_deposits_usd",
      "cumulative_deposits_usd",
      "granularity",
      "source_last_updated",
    ],
    export_aliases: {
      period_deposits_usd: "primary_value",
      cumulative_deposits_usd: "secondary_value",
    },
    unit_label: "Deposits in USD",
  },
};
const model = studio.growthChartModel(rows, metric, {
  granularity: "weekly",
  view: "all",
  activeRange: "7D",
  referenceDate: "2026-08-04",
});
const state = {
  activeRange: "7D",
  referenceDate: "2026-08-04",
  config: { dashboard: { id: "kyberswap_campaign" } },
  data: {
    meta: { generated_at: "2026-08-04T12:00:00Z" },
    datasets: { growth: rows },
    sourceMeta: { growth: { data_updated_at: "2026-08-04T11:00:00Z" } },
  },
  growthSelections: new Map([[
    metric.id,
    { granularity: "weekly", view: "all" },
  ]]),
};
console.log(JSON.stringify({
  model,
  csv: studio.metricCsvEntry(state, metric),
  axisMappings: ["left", "right", 0, 1, "0", "1", null]
    .map(studio.growthAxisIndex),
  tooltipFormats: ["currency_compact", "currency", "integer"]
    .map(studio.growthTooltipFormat),
  navIds: ["growth", "#studio-section-growth", "studio-section-trends"]
    .map(studio.sectionNavId),
}));
"""
    )

    assert result["model"]["periods"] == ["2026-07-27", "2026-08-03"]
    assert result["model"]["series"] == [
        {
            "axis": 0,
            "color": "",
            "format": "currency_compact",
            "name": "Referral deposits",
            "stack": "",
            "type": "column",
            "values": [1178.604990747704, 25.25],
        },
        {
            "axis": 1,
            "color": "",
            "format": "currency_compact",
            "name": "Cumulative deposits",
            "stack": "",
            "type": "line",
            "values": [9007199254740992, 9007199254741018],
        },
    ]
    assert result["model"]["exportRows"] == [
        {
            "granularity": "weekly",
            "source_granularity": "week",
            "selected_view": "all",
            "dashboard_period": "7D",
            "source_last_updated": "2026-08-01T12:00:00Z",
            "period": "2026-07-27",
            "daily_deposits_usd": "1178.604990747704001",
            "cum_deposits_usd": "9007199254740992.1234567895",
            "dimension": "",
            "primary_value": "1178.604990747704001",
            "secondary_value": "9007199254740992.1234567895",
        },
        {
            "granularity": "weekly",
            "source_granularity": "week",
            "selected_view": "all",
            "dashboard_period": "7D",
            "source_last_updated": "2026-08-04T12:00:00Z",
            "period": "2026-08-03",
            "daily_deposits_usd": "25.25",
            "cum_deposits_usd": "9007199254741017.3734567895",
            "dimension": "",
            "primary_value": "25.25",
            "secondary_value": "9007199254741017.3734567895",
        },
    ]
    assert result["model"]["context"] == "Weekly · Deposits in USD"
    assert result["csv"]["data"] == (
        "period,period_deposits_usd,cumulative_deposits_usd,granularity,"
        "source_last_updated\r\n"
        "2026-07-27,1178.604990747704001,9007199254740992.1234567895,"
        "weekly,2026-08-01T12:00:00Z\r\n"
        "2026-08-03,25.25,9007199254741017.3734567895,"
        "weekly,2026-08-04T12:00:00Z\r\n"
    )
    assert result["axisMappings"] == [0, 1, 0, 1, 0, 1, 0]
    assert result["tooltipFormats"] == [
        "currency_compact",
        "currency_compact",
        "integer",
    ]
    assert result["navIds"] == ["growth", "growth", "trends"]


def test_growth_dynamic_views_order_categories_and_preserve_prepared_weekly_rows():
    result = run_node_json(
        """
const rows = [
  { record_type: "tvl_weekly_all", period: "2026-07-28", observation_day: "2026-08-01", cum_attributed_tvl_usd: "100.0000000000000001" },
  { record_type: "tvl_weekly_all", period: "2026-08-04", observation_day: "2026-08-04", cum_attributed_tvl_usd: "110.0000000000000002" },
  { record_type: "tvl_weekly_type", period: "2026-07-28", observation_day: "2026-08-01", depositor_type: "Old Depositor", daily_attributed_tvl_usd: "25.0000000000000001" },
  { record_type: "tvl_weekly_type", period: "2026-07-28", observation_day: "2026-08-01", depositor_type: "New Depositor", daily_attributed_tvl_usd: "75" },
  { record_type: "tvl_weekly_type", period: "2026-07-28", observation_day: "2026-08-01", depositor_type: "Partner Cohort", daily_attributed_tvl_usd: "5" },
  { record_type: "tvl_weekly_type", period: "2026-08-04", observation_day: "2026-08-04", depositor_type: "New Depositor", daily_attributed_tvl_usd: "80" },
];
const metric = {
  name: "Attributed TVL over time",
  date_column: "period",
  format: "currency_compact",
  growth_chart: {
    kind: "timeseries",
    default_granularity: "weekly",
    range_date_column: "observation_day",
    default_view: "all",
    views: [
      {
        id: "all",
        label: "All TVL",
        record_types: { weekly: "tvl_weekly_all" },
        aggregation: "latest",
      },
      {
        id: "depositor_type",
        label: "Depositor type",
        record_types: { weekly: "tvl_weekly_type" },
        dimension_column: "depositor_type",
        dimension_order: ["New Depositor", "Old Depositor"],
        value_column: "daily_attributed_tvl_usd",
        format: "currency_compact",
        aggregation: "latest",
      },
    ],
    measures: [{
      column: "cum_attributed_tvl_usd",
      label: "Attributed TVL",
      format: "currency_compact",
      series_type: "area",
      stack: true,
    }],
    export_columns: ["period", "depositor_type", "daily_attributed_tvl_usd"],
  },
};
const all = studio.growthChartModel(rows, metric, {
  granularity: "weekly",
  view: "all",
  activeRange: "7D",
  referenceDate: "2026-08-04",
});
const byType = studio.growthChartModel(rows, metric, {
  granularity: "weekly",
  view: "depositor_type",
  activeRange: "7D",
  referenceDate: "2026-08-04",
});
console.log(JSON.stringify({
  all,
  byType,
  views: studio.growthChartViews(metric),
  stackModes: {
    area: studio.growthDynamicStackEnabled(byType, metric.growth_chart, "area"),
    column: studio.growthDynamicStackEnabled(byType, metric.growth_chart, "column"),
    line: studio.growthDynamicStackEnabled(byType, metric.growth_chart, "line"),
  },
}));
"""
    )

    assert result["all"]["periods"] == ["2026-07-28", "2026-08-04"]
    assert result["all"]["exportRows"][0]["cum_attributed_tvl_usd"] == (
        "100.0000000000000001"
    )
    assert result["byType"]["categories"] == [
        "New Depositor",
        "Old Depositor",
        "Partner Cohort",
    ]
    assert result["byType"]["series"] == [
        {
            "axis": 0,
            "color": "",
            "format": "currency_compact",
            "name": "New Depositor",
            "type": "dynamic",
            "values": [75, 80],
        },
        {
            "axis": 0,
            "color": "",
            "format": "currency_compact",
            "name": "Old Depositor",
            "type": "dynamic",
            "values": [25, 0],
        },
        {
            "axis": 0,
            "color": "",
            "format": "currency_compact",
            "name": "Partner Cohort",
            "type": "dynamic",
            "values": [5, 0],
        },
    ]
    assert result["byType"]["context"] == (
        "Weekly · Depositor type · Measured in USD"
    )
    assert result["byType"]["stackRequested"] is True
    assert result["stackModes"] == {"area": True, "column": True, "line": False}
    assert [view["id"] for view in result["views"]] == ["all", "depositor_type"]


def test_growth_ranking_and_activity_models_honor_dashboard_range_and_views():
    result = run_node_json(
        """
const rankingRows = [
  { record_type: "product_daily", period: "2026-07-28", product_symbol: "eETH", daily_deposits: "1000" },
  { record_type: "product_daily", period: "2026-07-31", product_symbol: "eETH", daily_deposits: "20.0000000000000001" },
  { record_type: "product_daily", period: "2026-08-03", product_symbol: "eETH", daily_deposits: "30.0000000000000002" },
  { record_type: "product_daily", period: "2026-08-03", product_symbol: "liquidETH", daily_deposits: "75" },
  { record_type: "product_weekly", period: "2026-08-03", product_symbol: "liquidETH", daily_deposits: "9999" },
  { record_type: "depositor_daily", period: "2026-07-31", depositor_type: "Existing Depositor", daily_deposits: "15" },
  { record_type: "depositor_daily", period: "2026-08-03", depositor_type: "New Depositor", daily_deposits: "60" },
];
const rankingMetric = {
  name: "Total Referral Deposits Breakdown",
  date_column: "period",
  value_column: "daily_deposits",
  format: "currency_compact",
  growth_chart: {
    kind: "ranking",
    default_view: "product",
    views: [
      {
        id: "product",
        label: "Product",
        record_types: { total: "product_daily" },
        dimension_column: "product_symbol",
        value_column: "daily_deposits",
      },
      {
        id: "depositor_type",
        label: "Depositor Type",
        record_types: { total: "depositor_daily" },
        dimension_column: "depositor_type",
        dimension_order: ["New Depositor", "Existing Depositor", "Past Depositor"],
        value_column: "daily_deposits",
      },
    ],
    export_columns: [
      "product_symbol",
      "daily_deposits",
      "dashboard_period",
    ],
  },
};
const activityRows = [
  { record_type: "weekly_product_deposits", period: "2026-07-28", category: "liquidETH", metric_value: "4" },
  { record_type: "weekly_product_deposits", period: "2026-07-28", category: "eETH", metric_value: "8" },
  { record_type: "weekly_product_depositors", period: "2026-07-28", category: "eETH", metric_value: "3" },
];
const activityMetric = {
  name: "Deposit and Depositor Count by Product",
  date_column: "period",
  format: "integer",
  growth_chart: {
    kind: "timeseries",
    default_granularity: "weekly",
    default_view: "deposits",
    views: [
      {
        id: "deposits",
        label: "Deposits",
        record_types: { weekly: "weekly_product_deposits" },
        dimension_column: "category",
        dimension_order: ["eETH", "liquidETH", "liquidUSD", "liquidBTC"],
        value_column: "metric_value",
        format: "integer",
      },
      {
        id: "depositors",
        label: "Depositors",
        record_types: { weekly: "weekly_product_depositors" },
        dimension_column: "category",
        value_column: "metric_value",
        format: "integer",
      },
    ],
    measures: [{
      column: "metric_value",
      label: "Count",
      format: "integer",
      series_type: "column",
      stack: true,
    }],
    export_columns: ["period", "category", "metric_value", "selected_view"],
  },
};
console.log(JSON.stringify({
  ranking: studio.growthChartModel(rankingRows, rankingMetric, {
    view: "product",
    activeRange: "7D",
    referenceDate: "2026-08-04",
  }),
  rankingByType: studio.growthChartModel(rankingRows, rankingMetric, {
    view: "depositor_type",
    activeRange: "7D",
    referenceDate: "2026-08-04",
  }),
  deposits: studio.growthChartModel(activityRows, activityMetric, {
    granularity: "weekly",
    view: "deposits",
    activeRange: "ALL",
  }),
  depositors: studio.growthChartModel(activityRows, activityMetric, {
    granularity: "weekly",
    view: "depositors",
    activeRange: "ALL",
  }),
  activityStackModes: {
    column: studio.growthDynamicStackEnabled(
      studio.growthChartModel(activityRows, activityMetric, {
        granularity: "weekly",
        view: "deposits",
        activeRange: "ALL",
      }),
      activityMetric.growth_chart,
      "column",
    ),
    line: studio.growthDynamicStackEnabled(
      studio.growthChartModel(activityRows, activityMetric, {
        granularity: "weekly",
        view: "deposits",
        activeRange: "ALL",
      }),
      activityMetric.growth_chart,
      "line",
    ),
  },
}));
"""
    )

    assert result["ranking"]["categories"] == ["liquidETH", "eETH"]
    assert result["ranking"]["ranking"] == [
        {
            "name": "liquidETH",
            "exact": "75",
            "numeric": 75,
            "present": True,
            "sourceLastUpdated": "",
        },
        {
            "name": "eETH",
            "exact": "50.0000000000000003",
            "numeric": 50,
            "present": True,
            "sourceLastUpdated": "",
        },
    ]
    assert result["ranking"]["context"] == (
        "7D dashboard period · Product · Measured in USD"
    )
    assert result["rankingByType"]["categories"] == [
        "New Depositor",
        "Existing Depositor",
    ]
    assert [row["exact"] for row in result["rankingByType"]["ranking"]] == [
        "60",
        "15",
    ]
    assert result["deposits"]["categories"] == ["eETH", "liquidETH"]
    assert result["deposits"]["series"] == [
        {
            "axis": 0,
            "color": "",
            "format": "integer",
            "name": "eETH",
            "type": "dynamic",
            "values": [8],
        },
        {
            "axis": 0,
            "color": "",
            "format": "integer",
            "name": "liquidETH",
            "type": "dynamic",
            "values": [4],
        },
    ]
    assert result["depositors"]["categories"] == ["eETH"]
    assert result["depositors"]["exportRows"][0]["metric_value"] == "3"
    assert result["activityStackModes"] == {"column": True, "line": False}


def test_growth_ranking_wildcard_uses_only_configured_latest_snapshot_period():
    result = run_node_json(
        """
const rows = [
  {
    day: "2026-08-01",
    record_type: "raw_attribution",
    current_token: "weETH",
    current_token_category: "ether.fi",
    attributed_balance: "9999",
    source_last_updated: "2026-08-01T12:00:00Z",
  },
  {
    day: "2026-08-02",
    record_type: "raw_attribution",
    current_token: "weETH",
    current_token_category: "ether.fi",
    attributed_balance: "125.25",
    source_last_updated: "2026-08-02T12:00:00Z",
  },
  {
    day: "2026-08-02",
    record_type: "synthetic_exit",
    current_token: "Exited",
    current_token_category: "Exited",
    attributed_balance: "50",
    source_last_updated: "2026-08-02T12:00:00Z",
  },
  {
    day: "2026-08-02",
    current_token: "weETH",
    current_token_category: "ether.fi",
    attributed_balance: "74.75",
    source_last_updated: "2026-08-02T12:00:00Z",
  },
];
const metric = {
  name: "Attributed TVL by Current Location",
  format: "currency_compact",
  growth_chart: {
    kind: "ranking",
    period_column: "day",
    latest_period_only: true,
    default_view: "protocol",
    views: [
      {
        id: "protocol",
        label: "Protocol",
        record_types: { total: "*" },
        dimension_column: "current_token",
        value_column: "attributed_balance",
      },
      {
        id: "category",
        label: "Category",
        record_types: { total: ["*"] },
        dimension_column: "current_token_category",
        value_column: "attributed_balance",
      },
    ],
    export_columns: [
      "grouping_type",
      "destination",
      "attributed_tvl_usd",
      "source_day",
    ],
    export_aliases: {
      grouping_type: "selected_view",
      destination: "dimension",
      attributed_tvl_usd: "primary_value",
      source_day: "period",
    },
  },
};
const protocol = studio.growthChartModel(rows, metric, {
  view: "protocol",
  activeRange: "7D",
  referenceDate: "2026-07-29T00:00:00Z",
});
const category = studio.growthChartModel(rows, metric, {
  view: "category",
  activeRange: "ALL",
});
console.log(JSON.stringify({
  protocol,
  category,
  projected: studio.growthProjectedExportRows(
    protocol,
    metric.growth_chart,
  ),
}));
"""
    )

    assert result["protocol"]["categories"] == ["weETH", "Exited"]
    assert result["protocol"]["context"] == "Latest source day · Protocol · Measured in USD"
    assert [row["exact"] for row in result["protocol"]["ranking"]] == [
        "200",
        "50",
    ]
    assert {row["day"] for row in result["protocol"]["rows"]} == {"2026-08-02"}
    assert result["category"]["categories"] == ["ether.fi", "Exited"]
    assert result["projected"] == [
        {
            "grouping_type": "protocol",
            "destination": "weETH",
            "attributed_tvl_usd": "200",
            "source_day": "2026-08-02",
        },
        {
            "grouping_type": "protocol",
            "destination": "Exited",
            "attributed_tvl_usd": "50",
            "source_day": "2026-08-02",
        },
    ]


def test_growth_activity_preserves_signed_values_in_stacks_and_projected_csv():
    result = run_node_json(
        """
const rows = [
  { record_type: "weekly_project", granularity: "weekly", period: "2026-07-27", category: "Aave", amount_usd: "631200.125" },
  { record_type: "weekly_project", granularity: "weekly", period: "2026-07-27", category: "KyberSwap", amount_usd: "-3200.125" },
  { record_type: "weekly_project", granularity: "weekly", period: "2026-08-03", category: "Aave", amount_usd: "-25" },
  { record_type: "daily_project", granularity: "daily", period: "2026-08-03", category: "Aave", amount_usd: "999" },
];
const metric = {
  name: "Post-Referral Activity",
  date_column: "period",
  format: "currency_compact",
  tooltip_signed: true,
  growth_chart: {
    kind: "timeseries",
    default_granularity: "weekly",
    default_view: "project",
    views: [{
      id: "project",
      label: "Project",
      record_types: { daily: "daily_project", weekly: "weekly_project" },
      dimension_column: "category",
      value_column: "amount_usd",
    }],
    measures: [{
      column: "amount_usd",
      label: "Signed activity",
      format: "currency_compact",
      series_type: "column",
      stack: true,
    }],
    export_columns: ["period", "granularity", "category", "amount_usd"],
    export_aliases: { category: "dimension", amount_usd: "primary_value" },
  },
};
const model = studio.growthChartModel(rows, metric, {
  granularity: "weekly",
  view: "project",
  activeRange: "ALL",
});
console.log(JSON.stringify({
  model,
  projected: studio.growthProjectedExportRows(model, metric.growth_chart),
  stackEnabled: studio.growthDynamicStackEnabled(
    model,
    metric.growth_chart,
    "column",
  ),
}));
"""
    )

    assert result["model"]["periods"] == ["2026-07-27", "2026-08-03"]
    assert result["model"]["series"] == [
        {
            "axis": 0,
            "color": "",
            "format": "currency_compact",
            "name": "Aave",
            "type": "dynamic",
            "values": [631200.125, -25],
        },
        {
            "axis": 0,
            "color": "",
            "format": "currency_compact",
            "name": "KyberSwap",
            "type": "dynamic",
            "values": [-3200.125, 0],
        },
    ]
    assert result["model"]["stackRequested"] is True
    assert result["stackEnabled"] is True
    assert result["projected"] == [
        {
            "period": "2026-07-27",
            "granularity": "weekly",
            "category": "Aave",
            "amount_usd": "631200.125",
        },
        {
            "period": "2026-07-27",
            "granularity": "weekly",
            "category": "KyberSwap",
            "amount_usd": "-3200.125",
        },
        {
            "period": "2026-08-03",
            "granularity": "weekly",
            "category": "Aave",
            "amount_usd": "-25",
        },
    ]


def test_growth_semantic_csv_projection_covers_tvl_breakdown_ranking_and_counts():
    result = run_node_json(
        """
function csv(rows, metric, selection) {
  const model = studio.growthChartModel(rows, metric, selection);
  const config = metric.growth_chart;
  return studio.buildCsv(
    studio.growthProjectedExportRows(model, config),
    config.export_columns,
  );
}
const currencyMeasure = {
  column: "cum_attributed_tvl_usd",
  label: "Attributed TVL",
  format: "currency_compact",
  series_type: "area",
  stack: true,
};
const tvl = {
  name: "Attributed TVL Over Time",
  date_column: "period",
  format: "currency_compact",
  growth_chart: {
    kind: "timeseries",
    default_granularity: "weekly",
    default_view: "all",
    range_date_column: "observation_day",
    views: [
      {
        id: "all",
        label: "All",
        record_types: { weekly: "weekly_all" },
        value_column: "cum_attributed_tvl_usd",
      },
      {
        id: "depositor_type",
        label: "Depositor Type",
        record_types: { weekly: "weekly_depositor_type" },
        dimension_column: "depositor_type",
        value_column: "daily_attributed_tvl_usd",
      },
    ],
    measures: [currencyMeasure],
    export_columns: [
      "period", "grouping_mode", "depositor_type", "attributed_tvl_usd", "granularity",
    ],
    export_aliases: {
      grouping_mode: "selected_view",
      depositor_type: "dimension",
      attributed_tvl_usd: "primary_value",
    },
  },
};
const breakdown = {
  name: "Referral Deposits Breakdown",
  date_column: "period",
  format: "currency_compact",
  growth_chart: {
    kind: "timeseries",
    default_granularity: "weekly",
    default_view: "product",
    rebuild_weekly_from_daily: true,
    views: [{
      id: "product",
      label: "Product",
      record_types: { daily: "daily_product", weekly: "weekly_product" },
      dimension_column: "product_symbol",
      value_column: "daily_deposits",
    }],
    measures: [{
      column: "daily_deposits",
      label: "Referral deposits",
      format: "currency_compact",
      series_type: "column",
      stack: true,
    }],
    export_columns: ["period", "category_type", "category", "deposits_usd", "granularity"],
    export_aliases: {
      category_type: "selected_view",
      category: "dimension",
      deposits_usd: "primary_value",
    },
  },
};
const ranking = {
  name: "Total Referral Deposits Breakdown",
  date_column: "period",
  value_column: "daily_deposits",
  format: "currency_compact",
  growth_chart: {
    kind: "ranking",
    default_view: "product",
    views: [{
      id: "product",
      label: "Product",
      record_types: { total: "daily_product" },
      dimension_column: "product_symbol",
      value_column: "daily_deposits",
    }],
    measures: [{
      column: "daily_deposits",
      label: "Total referral deposits",
      format: "currency_compact",
      series_type: "bar",
    }],
    export_columns: ["category_type", "category", "total_deposits_usd", "dashboard_period"],
    export_aliases: {
      category_type: "selected_view",
      category: "dimension",
      total_deposits_usd: "primary_value",
    },
  },
};
function activity(categoryType, recordType) {
  return {
    name: `Counts by ${categoryType}`,
    date_column: "period",
    format: "integer",
    growth_chart: {
      kind: "timeseries",
      default_granularity: "weekly",
      default_view: "deposits",
      views: [{
        id: "deposits",
        label: "Deposits",
        record_types: { weekly: recordType },
        dimension_column: "category",
        value_column: "metric_value",
      }],
      measures: [{
        column: "metric_value",
        label: "Count",
        format: "integer",
        series_type: "column",
        stack: true,
      }],
      export_columns: [
        "timestamp_type", "timestamp", "category_type", "category", "metric_type", "metric_value",
      ],
      export_aliases: {
        timestamp_type: "source_granularity",
        timestamp: "period",
        category: "dimension",
        metric_type: "selected_view",
        metric_value: "primary_value",
      },
      export_constants: { category_type: categoryType },
    },
  };
}
const breakdownRows = [
  { record_type: "daily_product", period: "2026-08-01", product_symbol: "eETH", daily_deposits: "0.0000000000000001" },
  { record_type: "daily_product", period: "2026-08-02", product_symbol: "eETH", daily_deposits: "10.1234567890123456" },
  { record_type: "weekly_product", period: "2026-07-27", product_symbol: "eETH", daily_deposits: "999" },
];
console.log(JSON.stringify({
  tvl: csv(
    [{
      record_type: "weekly_all",
      period: "2026-07-27",
      observation_day: "2026-08-01",
      cum_attributed_tvl_usd: "123.4567890123456789",
    }],
    tvl,
    { granularity: "weekly", view: "all", activeRange: "7D", referenceDate: "2026-08-02" },
  ),
  breakdown: csv(
    breakdownRows,
    breakdown,
    { granularity: "weekly", view: "product", activeRange: "7D", referenceDate: "2026-08-02" },
  ),
  ranking: csv(
    breakdownRows,
    ranking,
    { view: "product", activeRange: "7D", referenceDate: "2026-08-02" },
  ),
  productCounts: csv(
    [{ record_type: "weekly_product_deposits", period: "2026-07-27", category: "eETH", metric_value: "7" }],
    activity("product", "weekly_product_deposits"),
    { granularity: "weekly", view: "deposits", activeRange: "ALL" },
  ),
  depositorCounts: csv(
    [{ record_type: "weekly_depositor_type_deposits", period: "2026-07-27", category: "New Depositor", metric_value: "3" }],
    activity("depositor_type", "weekly_depositor_type_deposits"),
    { granularity: "weekly", view: "deposits", activeRange: "ALL" },
  ),
}));
"""
    )

    assert result["tvl"] == (
        "period,grouping_mode,depositor_type,attributed_tvl_usd,granularity\r\n"
        "2026-07-27,all,,123.4567890123456789,weekly\r\n"
    )
    assert result["breakdown"] == (
        "period,category_type,category,deposits_usd,granularity\r\n"
        "2026-07-27,product,eETH,10.1234567890123457,weekly\r\n"
    )
    assert result["ranking"] == (
        "category_type,category,total_deposits_usd,dashboard_period\r\n"
        "product,eETH,10.1234567890123457,7D\r\n"
    )
    assert result["productCounts"] == (
        "timestamp_type,timestamp,category_type,category,metric_type,metric_value\r\n"
        "week,2026-07-27,product,eETH,deposits,7\r\n"
    )
    assert result["depositorCounts"] == (
        "timestamp_type,timestamp,category_type,category,metric_type,metric_value\r\n"
        "week,2026-07-27,depositor_type,New Depositor,deposits,3\r\n"
    )


def test_period_counters_select_rows_fall_back_to_zero_and_export_selected_aliases():
    result = run_node_json(
        """
const rows = [
  {
    key_: "all_time_data",
    total_deposits_usd: 481905421,
    depositors_new_users_rate: 0.8252461649,
    revenue_generated: 0,
  },
  {
    key_: "90d_data",
    total_deposits_usd: 125000000,
    depositors_new_users_rate: 0.75,
    revenue_generated: 0,
  },
  {
    key_: "30d_data",
    total_deposits_usd: 42000000,
    depositors_new_users_rate: 0.5,
    revenue_generated: null,
  },
];
const original = JSON.stringify(rows);
const metric = {
  id: "kyber_campaign_summary",
  name: "Total Referral Deposits",
  data_source: "campaign_summary",
  columns: [
    "key_",
    "total_deposits_usd",
    "depositors_new_users_rate",
    "revenue_generated",
  ],
  value_column: "total_deposits_usd",
  period_key_column: "key_",
  period_key_map: {
    ALL: "all_time_data",
    "90D": "90d_data",
    "30D": "30d_data",
  },
  export_columns: [
    "key_",
    "total_deposits_usd",
    "depositors_new_users_rate",
    "revenue_generated",
    "source_last_updated",
  ],
  export_column_aliases: {
    key_: "period",
    depositors_new_users_rate: "deposits_by_new_depositors_rate",
  },
  export_slug: "kyberswap-campaign-summary",
};
const state = {
  activeRange: "90D",
  config: { dashboard: { id: "kyberswap_campaign", slug: "kyberswap" } },
  data: {
    meta: { generated_at: "2026-08-01T01:10:00Z" },
    datasets: { campaign_summary: rows },
    sourceMeta: {
      campaign_summary: {
        columns: metric.columns,
        source_last_updated: "2026-08-01T01:04:20Z",
      },
    },
  },
  counterWarnings: new Set(),
};
const entry = studio.metricCsvEntry(state, metric);
const missingColumn = studio.counterValueForRows(
  rows,
  { ...metric, value_column: "missing_metric" },
  "90D",
);
const missingKey = studio.counterValueForRows(rows, metric, "7D");
const warnings = [];
const originalWarn = console.warn;
console.warn = (message) => warnings.push(message);
const warningState = {
  ...state,
  data: {
    ...state.data,
    datasets: { campaign_summary: [{ key_: "90d_data" }] },
    sourceMeta: { campaign_summary: { columns: ["key_"] } },
  },
  counterWarnings: new Set(),
};
studio.metricCsvEntry(warningState, {
  id: "warn_counter",
  data_source: "campaign_summary",
  columns: ["key_"],
  value_column: "revenue_generated",
  period_key_column: "key_",
  period_key_map: { "90D": "90d_data" },
  export_columns: ["key_", "revenue_generated"],
  export_column_aliases: { key_: "period" },
  export_slug: "warning",
});
console.warn = originalWarn;
console.log(JSON.stringify({
  keys: {
    all: studio.periodKeyForMetric(metric, "ALL"),
    ninety: studio.periodKeyForMetric(metric, "90D"),
    unsupported: studio.periodKeyForMetric(metric, "7D"),
  },
  selected: studio.selectPeriodRow(rows, metric, "90D"),
  value: studio.counterValueForRows(rows, metric, "90D"),
  missingColumn: {
    value: missingColumn.value,
    column: missingColumn.valueColumn,
    key: missingColumn.periodKey,
    missing: missingColumn.missing,
  },
  missingKey: {
    value: missingKey.value,
    column: missingKey.valueColumn,
    key: missingKey.periodKey,
    missing: missingKey.missing,
  },
  entry,
  warnings,
  unchanged: JSON.stringify(rows) === original,
}));
"""
    )

    assert result["keys"] == {
        "all": "all_time_data",
        "ninety": "90d_data",
        "unsupported": "",
    }
    assert result["selected"]["key_"] == "90d_data"
    assert result["value"]["value"] == 125000000
    assert result["value"]["missing"] == ""
    assert result["missingColumn"] == {
        "value": 0,
        "column": "missing_metric",
        "key": "90d_data",
        "missing": "column",
    }
    assert result["missingKey"] == {
        "value": 0,
        "column": "total_deposits_usd",
        "key": "",
        "missing": "key",
    }
    assert result["entry"] == {
        "name": "kyberswap-campaign-summary-90d-2026-08-01.csv",
        "data": (
            "period,total_deposits_usd,deposits_by_new_depositors_rate,"
            "revenue_generated,source_last_updated\r\n"
            "90D,125000000,0.75,0,2026-08-01T01:04:20Z\r\n"
        ),
    }
    assert len(result["warnings"]) == 1
    assert "metric=warn_counter" in result["warnings"][0]
    assert "key=90d_data" in result["warnings"][0]
    assert "column=revenue_generated" in result["warnings"][0]
    assert result["unchanged"] is True


def test_compact_campaign_counters_round_only_the_visual_display():
    result = run_node_json(
        """
const metric = { compact_counter: true };
console.log(JSON.stringify({
  totalDeposits: studio.formatValue(
    "481905421.49167466",
    "currency_compact",
    metric,
  ),
  attributedTvl: studio.formatValue(
    "374476858.39556485",
    "currency_compact",
    metric,
  ),
  newDepositorDeposits: studio.formatValue(
    "397690600.9317606",
    "currency_compact",
    metric,
  ),
  newDepositorRate: studio.formatValue(
    "0.8252461649025691",
    "percent",
    metric,
  ),
  totalDepositors: studio.formatValue(550, "integer", metric),
  newDepositors: studio.formatValue(408, "integer", metric),
  retentionRate: studio.formatValue(
    "0.7770754212235694",
    "percent",
    metric,
  ),
  revenue: studio.formatValue(0, "currency_compact", metric),
}));
"""
    )

    assert result == {
        "totalDeposits": "$481.9m",
        "attributedTvl": "$374.5m",
        "newDepositorDeposits": "$397.7m",
        "newDepositorRate": "82.5%",
        "totalDepositors": "550",
        "newDepositors": "408",
        "retentionRate": "77.7%",
        "revenue": "$0",
    }


def test_table_sorting_is_stable_typed_and_keeps_missing_values_last():
    result = run_node_json(
        """
const rows = [
  { id: "ten", value: "10", day: "2026-07-10" },
  { id: "two-a", value: 2, day: "2026-07-02" },
  { id: "missing", value: null, day: null },
  { id: "two-b", value: "2", day: "2026-07-02" },
];
console.log(JSON.stringify({
  ascending: studio.sortRows(rows, "value", "ascending").map((row) => row.id),
  descending: studio.sortTableRows(rows, "value", "descending").map((row) => row.id),
  dates: studio.sortRows(rows, "day").map((row) => row.id),
  original: rows.map((row) => row.id),
  cloned: studio.sortRows(rows, "value") !== rows,
  comparisons: {
    numeric: studio.compareValues("2", 10),
    equalText: studio.compareValues("Alpha", "alpha"),
    dates: studio.compareValues("2026-07-01", "2026-07-02"),
    booleans: studio.compareValues(false, true),
  },
}));
"""
    )

    assert result["ascending"] == ["two-a", "two-b", "ten", "missing"]
    assert result["descending"] == ["ten", "two-a", "two-b", "missing"]
    assert result["dates"] == ["two-a", "two-b", "ten", "missing"]
    assert result["original"] == ["ten", "two-a", "missing", "two-b"]
    assert result["cloned"] is True
    assert result["comparisons"]["numeric"] < 0
    assert result["comparisons"]["equalText"] == 0
    assert result["comparisons"]["dates"] < 0
    assert result["comparisons"]["booleans"] < 0


def test_format_address_sankey_navigation_and_sparkline_helpers():
    result = run_node_json(
        """
const address = "0x1234567890abcdef1234567890abcdef12345678";
const sankeyMetric = {
  source_column: "from",
  target_column: "to",
  value_column: "amount",
};
const sankey = studio.aggregateSankeyRows([
  { from: "Entry", to: "Vault", amount: 2 },
  { from: "Entry", to: "Vault", amount: "3" },
  { from: "Entry", to: "Wallet", amount: 1 },
  { from: "Entry", to: "Ignored", amount: 0 },
  { from: "", to: "Ignored", amount: 9 },
  { from: "Entry", to: "Ignored", amount: "not-a-number" },
], sankeyMetric);
const geometry = studio.sparklineGeometry([0, 5, 10], 100, 50, 5);
const flatGeometry = studio.sparklineGeometry([4, 4], 100, 50, 5);
let assigned = null;
globalThis.location = {
  assign(value) { assigned = value; },
};
const navigated = studio.navigateToSelection({ value: "../demo/" });
const emptyNavigation = studio.navigateToSelection({ value: "" });
console.log(JSON.stringify({
  formatted: {
    missing: studio.formatValue(null, "currency"),
    currency: studio.formatValue(1234.5, "currency"),
    compact: studio.formatValue(1284730551.42, "currency_compact"),
    integerCompact: studio.formatValue(98731, "integer_compact"),
    percent: studio.formatValue(0.125, "percent"),
    points: studio.formatValue(0.021, "percentage_points"),
    integer: studio.formatValue(98731, "integer"),
    token: studio.formatValue(
      384290.7348,
      "token",
      { token_decimals: 4, token_symbol: "TEST" },
    ),
    yes: studio.formatValue(true, "boolean"),
    no: studio.formatValue(false, "boolean"),
  },
  addresses: {
    short: studio.shortAddress(address),
    alreadyShort: studio.shortAddress("0x1234"),
    empty: studio.shortAddress(null),
    copyLabel: studio.addressCopyLabel(address, "wallet_address"),
  },
  sankey,
  geometry,
  flatGeometry,
  tooShortGeometry: studio.sparklineGeometry([1], 100, 50, 5),
  navigation: { navigated, emptyNavigation, assigned },
}));
"""
    )

    assert result["formatted"] == {
        "missing": "—",
        "currency": "$1,234.50",
        "compact": "$1.28b",
        "integerCompact": "98.73k",
        "percent": "12.5%",
        "points": "2.1 pp",
        "integer": "98,731",
        "token": "384,290.7348 TEST",
        "yes": "Yes",
        "no": "No",
    }
    assert result["addresses"] == {
        "short": "0x123…45678",
        "alreadyShort": "0x1234",
        "empty": "",
        "copyLabel": (
            "Copy wallet address "
            "0x1234567890abcdef1234567890abcdef12345678"
        ),
    }
    assert result["sankey"] == [
        {
            "source": "stage-0:Entry",
            "target": "stage-1:Vault",
            "sourceLabel": "Entry",
            "targetLabel": "Vault",
            "sourceStage": 0,
            "targetStage": 1,
            "value": 5,
        },
        {
            "source": "stage-0:Entry",
            "target": "stage-1:Wallet",
            "sourceLabel": "Entry",
            "targetLabel": "Wallet",
            "sourceStage": 0,
            "targetStage": 1,
            "value": 1,
        },
    ]
    assert result["geometry"]["points"] == [[5, 45], [50, 25], [95, 5]]
    assert result["geometry"]["line"] == "M5.00,45.00 L50.00,25.00 L95.00,5.00"
    assert result["geometry"]["area"] == (
        "M5.00,45.00 L50.00,25.00 L95.00,5.00 "
        "L95.00,45 L5.00,45 Z"
    )
    assert result["flatGeometry"]["points"] == [[5, 25], [95, 25]]
    assert result["tooShortGeometry"] is None
    assert result["navigation"] == {
        "navigated": True,
        "emptyNavigation": False,
        "assigned": "../demo/",
    }


def test_three_stage_sankey_uses_qualified_nodes_exit_values_and_conserves():
    result = run_node_json(
        """
const metric = {
  stage_columns: ["depositor", "product", "destination"],
  value_column: "active_usd",
  exit_value_column: "exited_usd",
};
const links = studio.aggregateSankeyRows([
  {
    depositor: "New Depositor",
    product: "liquidETH",
    destination: "liquidETH",
    destination_status: "active",
    active_usd: 10,
    exited_usd: 0,
  },
  {
    depositor: "New Depositor",
    product: "liquidETH",
    destination: "liquidETH",
    destination_status: "active",
    active_usd: "2",
    exited_usd: 0,
  },
  {
    depositor: "New Depositor",
    product: "liquidETH",
    destination: "Restaking",
    destination_status: "active",
    active_usd: 5,
    exited_usd: 0,
  },
  {
    depositor: "Existing Depositor",
    product: "eETH",
    destination: "Exited",
    destination_status: "exited",
    active_usd: 999,
    exited_usd: 4,
  },
  {
    depositor: "New Depositor",
    product: "liquidETH",
    destination: "Ignored zero",
    destination_status: "active",
    active_usd: 0,
    exited_usd: 0,
  },
  {
    depositor: "New Depositor",
    product: "",
    destination: "Ignored incomplete",
    destination_status: "active",
    active_usd: 500,
    exited_usd: 0,
  },
], metric);
const conservation = studio.sankeyConservation(links);
const broken = studio.sankeyConservation([
  { source: "stage-0:a", target: "stage-1:b", value: 5 },
  { source: "stage-1:b", target: "stage-2:c", value: 4 },
]);
console.log(JSON.stringify({
  links,
  conservation,
  broken,
  equalVisibleLabelsHaveDifferentIds:
    studio.sankeyNodeId(1, "liquidETH") !== studio.sankeyNodeId(2, "liquidETH"),
}));
"""
    )

    assert result["links"] == [
        {
            "source": "stage-0:New Depositor",
            "target": "stage-1:liquidETH",
            "sourceLabel": "New Depositor",
            "targetLabel": "liquidETH",
            "sourceStage": 0,
            "targetStage": 1,
            "value": 17,
        },
        {
            "source": "stage-1:liquidETH",
            "target": "stage-2:liquidETH",
            "sourceLabel": "liquidETH",
            "targetLabel": "liquidETH",
            "sourceStage": 1,
            "targetStage": 2,
            "value": 12,
        },
        {
            "source": "stage-1:liquidETH",
            "target": "stage-2:Restaking",
            "sourceLabel": "liquidETH",
            "targetLabel": "Restaking",
            "sourceStage": 1,
            "targetStage": 2,
            "value": 5,
        },
        {
            "source": "stage-0:Existing Depositor",
            "target": "stage-1:eETH",
            "sourceLabel": "Existing Depositor",
            "targetLabel": "eETH",
            "sourceStage": 0,
            "targetStage": 1,
            "value": 4,
        },
        {
            "source": "stage-1:eETH",
            "target": "stage-2:Exited",
            "sourceLabel": "eETH",
            "targetLabel": "Exited",
            "sourceStage": 1,
            "targetStage": 2,
            "value": 4,
        },
    ]
    assert result["conservation"]["valid"] is True
    assert result["conservation"]["deltas"] == []
    assert result["broken"]["valid"] is False
    assert result["broken"]["deltas"] == [
        {
            "node": "stage-1:b",
            "incoming": 5,
            "outgoing": 4,
            "delta": 1,
        }
    ]
    assert result["equalVisibleLabelsHaveDifferentIds"] is True


def test_sankey_groups_ranked_destinations_without_mutating_or_losing_flow():
    result = run_node_json(
        """
const rows = [
  { depositor: "New", strategy: "S1", destination: "A", status: "active", active_usd: 100, exited_usd: 0 },
  { depositor: "Existing", strategy: "S2", destination: "B", status: "active", active_usd: 90, exited_usd: 0 },
  { depositor: "Existing", strategy: "S2", destination: "C", status: "active", active_usd: 80, exited_usd: 0 },
  { depositor: "Existing", strategy: "S2", destination: "D", status: "active", active_usd: 70, exited_usd: 0 },
  { depositor: "Existing", strategy: "S2", destination: "E", status: "active", active_usd: 60, exited_usd: 0 },
  { depositor: "New", strategy: "S1", destination: "F", status: "active", active_usd: 20, exited_usd: 0 },
  { depositor: "Existing", strategy: "S2", destination: "F", status: "active", active_usd: 30, exited_usd: 0 },
  { depositor: "New", strategy: "S1", destination: "G", status: "active", active_usd: 10, exited_usd: 0 },
  { depositor: "Existing", strategy: "S2", destination: "H", status: "active", active_usd: 40, exited_usd: 0 },
  { depositor: "New", strategy: "S1", destination: "Exited", destination_status: "exited", active_usd: 999, exited_usd: 5 },
  { depositor: "Existing", strategy: "S2", destination: "Exited", destination_status: "exited", active_usd: 999, exited_usd: 15 },
  { depositor: "New", strategy: "S1", destination: "Zero", status: "active", active_usd: 0, exited_usd: 0 },
];
const original = JSON.stringify(rows);
const metric = {
  stage_columns: ["depositor", "strategy", "destination"],
  value_column: "active_usd",
  exit_value_column: "exited_usd",
  destination_top_n: 5,
  destination_others_label: "Others",
  preserve_destinations: ["Exited"],
};
const links = studio.aggregateSankeyRows(rows, metric);
const destinationLinks = links.filter((link) => link.targetStage === 2);
console.log(JSON.stringify({
  destinationLabels: [...new Set(destinationLinks.map((link) => link.targetLabel))].sort(),
  others: destinationLinks
    .filter((link) => link.targetLabel === "Others")
    .map((link) => ({
      source: link.sourceLabel,
      value: link.value,
      members: link.groupedMembers,
    }))
    .sort((left, right) => left.source.localeCompare(right.source)),
  exited: destinationLinks
    .filter((link) => link.targetLabel === "Exited")
    .reduce((sum, link) => sum + link.value, 0),
  totalDestinationFlow: destinationLinks.reduce((sum, link) => sum + link.value, 0),
  hasZero: destinationLinks.some((link) => link.targetLabel === "Zero"),
  conservation: studio.sankeyConservation(links),
  unchanged: JSON.stringify(rows) === original,
}));
"""
    )

    assert result["destinationLabels"] == [
        "A",
        "B",
        "C",
        "D",
        "E",
        "Exited",
        "Others",
    ]
    assert result["others"] == [
        {"source": "S1", "value": 30, "members": ["F", "G"]},
        {"source": "S2", "value": 70, "members": ["F", "H"]},
    ]
    assert result["exited"] == 20
    assert result["totalDestinationFlow"] == 520
    assert result["hasZero"] is False
    assert result["conservation"]["valid"] is True
    assert result["conservation"]["deltas"] == []
    assert result["unchanged"] is True


def test_methodology_details_exposes_provenance_rules_validation_and_links():
    result = run_node_json(
        """
const metric = {
  id: "kyber_flow",
  name: "KyberSwap Depositor Journey",
  query_id: 8178495,
  query_url: "https://dune.com/queries/8178495",
  transformation: {
    methodology_id: "kyberswap_attributed_holdings_v1",
    version: "1.0.0",
    script_path: "scripts/enrich_kyberswap_attributed_holdings.py",
    tests_path: "tests/test_kyberswap_attributed_holdings.py",
  },
  methodology: {
    title: "KyberSwap Campaign Summary",
    description: "Deterministic referral attribution.",
    metric_definitions: ["Total Referral Deposits — selected-period referral volume."],
    selected_period_logic: ["The active range maps to one query key."],
    definitions: ["Deposited product is the source strategy."],
    business_rules: ["Attribution cannot exceed the referral cap."],
    allocation_rules: ["Ties sort by token name."],
    notes: ["Attribution is not exact asset provenance."],
  },
};
const source = {
  execution_id: "exec-read-only-8178495",
  source_last_updated: "2026-08-01T09:30:00Z",
  generated_at: "2026-08-01T09:35:00Z",
  freshness_status: "current",
  methodology_version: "1.0.0",
  transformation_warnings: ["One destination was Uncategorized."],
  transformation_summary: {
    source_rows: 12,
    total_referral_value_usd: "125.50",
    total_attributed_value_usd: "100.25",
    total_exited_value_usd: "25.25",
    reconciliation_delta_usd: "0",
    invalid_group_count: 0,
  },
};
console.log(JSON.stringify(studio.methodologyDetails(metric, source, {
  dashboard: { repository_file_url_base: "https://example.test/repo/blob/main/" },
})));
"""
    )

    assert result["title"] == "KyberSwap Campaign Summary"
    assert result["methodologyId"] == "kyberswap_attributed_holdings_v1"
    assert result["methodologyVersion"] == "1.0.0"
    assert result["queryId"] == "8178495"
    assert result["executionId"] == "exec-read-only-8178495"
    assert result["sourceLastUpdated"] == "2026-08-01T09:30:00Z"
    assert result["freshnessStatus"] == "current"
    assert result["assumptions"] == ["Deposited product is the source strategy."]
    assert result["metricDefinitions"] == [
        "Total Referral Deposits — selected-period referral volume."
    ]
    assert result["selectedPeriodLogic"] == [
        "The active range maps to one query key."
    ]
    assert result["businessRules"] == [
        "Attribution cannot exceed the referral cap."
    ]
    assert result["allocationRules"] == ["Ties sort by token name."]
    assert result["validation"] == [
        "Referral value $125.50 reconciles to active attribution $100.25 "
        "plus exited value $25.25.",
        "USD reconciliation delta: $0.00.",
        "Invalid attribution groups: 0.",
        "Validated source rows: 12.",
    ]
    assert result["limitations"] == [
        "Attribution is not exact asset provenance.",
        "One destination was Uncategorized.",
    ]
    assert result["scriptUrl"] == (
        "https://example.test/repo/blob/main/"
        "scripts/enrich_kyberswap_attributed_holdings.py"
    )
    assert result["testsUrl"] == (
        "https://example.test/repo/blob/main/"
        "tests/test_kyberswap_attributed_holdings.py"
    )


def test_high_precision_numeric_strings_are_never_silently_rounded():
    result = run_node_json(
        """
const large = "12345678901234567890.123456789";
const scientific = "1.234567890123456789e+20";
const tiny = "0.000000000000000123456789";
console.log(JSON.stringify({
  finite: {
    regular: studio.finiteNumber("42.5"),
    safeInteger: studio.finiteNumber("9007199254740991"),
    unsafeInteger: studio.finiteNumber("9007199254740992"),
    large: studio.finiteNumber(large),
    scientific: studio.finiteNumber(scientific),
    tiny: studio.finiteNumber(tiny),
  },
  formatted: {
    token: studio.formatValue(
      large,
      "token",
      { token_decimals: 12, token_symbol: "ETHFI" },
    ),
    scientificToken: studio.formatValue(
      scientific,
      "token",
      { token_decimals: 12, token_symbol: "ETHFI" },
    ),
    tinyToken: studio.formatValue(
      tiny,
      "token",
      { token_decimals: 12, token_symbol: "ETHFI" },
    ),
    currency: studio.formatValue(large, "currency", { currency: "USD" }),
    percent: studio.formatValue(
      "0.1234567890123456789",
      "percent",
    ),
    compactDisplayCurrency: studio.formatCompactDisplayValue(
      "239331611.95958275",
      "currency_compact",
    ),
    compactDisplayPercent: studio.formatCompactDisplayValue(
      "0.9042916768708528875490224171722781741699438423854172926238258126089383665839",
      "percent",
    ),
  },
}));
"""
    )

    assert result == {
        "finite": {
            "regular": 42.5,
            "safeInteger": 9007199254740991,
            "unsafeInteger": None,
            "large": None,
            "scientific": None,
            "tiny": None,
        },
        "formatted": {
            "token": "12,345,678,901,234,567,890.123456789 ETHFI",
            "scientificToken": "123,456,789,012,345,678,900 ETHFI",
            "tinyToken": "0.000000000000000123456789 ETHFI",
            "currency": "$12,345,678,901,234,567,890.123456789",
            "percent": "12.34567890123456789%",
            "compactDisplayCurrency": "$239.3m",
            "compactDisplayPercent": "90.43%",
        },
    }


def test_table_sort_compares_precise_numeric_strings_without_number_coercion():
    result = run_node_json(
        """
const rows = [
  { label: "smaller", value: "9007199254740992" },
  { label: "larger", value: "9007199254740993" },
  { label: "fraction", value: "0.10000000000000000001" },
];
console.log(JSON.stringify({
  integerComparison: studio.compareValues(
    "9007199254740992",
    "9007199254740993",
  ),
  fractionComparison: studio.compareValues(
    "0.10000000000000000002",
    "0.10000000000000000001",
  ),
  negativeComparison: studio.compareValues(
    "-12345678901234567890.2",
    "-12345678901234567890.1",
  ),
  descending: studio.sortTableRows(rows, "value", "descending")
    .map((row) => row.label),
}));
"""
    )

    assert result == {
        "integerComparison": -1,
        "fractionComparison": 1,
        "negativeComparison": -1,
        "descending": ["larger", "smaller", "fraction"],
    }


def test_chart_styles_compact_numbers_and_ethereum_explorer_helpers():
    result = run_node_json(
        """
const address = "0x1234567890abcdef1234567890abcdef12345678";
const transaction = `0x${"ab".repeat(32)}`;
console.log(JSON.stringify({
  chartStyles: {
    configured: studio.allowedChartStyles({
      allowed_visualizations: ["area", "line", "invalid", "area"],
    }),
    fallback: studio.allowedChartStyles({ allowed_visualizations: ["invalid"] }),
    selected: studio.defaultChartStyle({
      default_visualization: "column",
      allowed_visualizations: ["line", "column"],
    }),
    safeDefault: studio.defaultChartStyle({
      default_visualization: "area",
      allowed_visualizations: ["line", "column"],
    }),
    presentations: studio.CHART_STYLES.map(studio.chartPresentation),
  },
  compact: [
    0,
    999,
    1000,
    1250,
    12300,
    123400,
    999999,
    1234567,
    1284730551.42,
    -1500000,
  ].map(studio.compactNumber),
  formatted: {
    currency: studio.formatValue(1284730551.42, "currency_compact"),
    negativeCurrency: studio.formatValue(-1500000, "currency_compact"),
    integer: studio.formatValue(98731, "integer_compact"),
    exampleMillions: studio.formatValue(2700000, "currency_compact"),
    exampleThousands: studio.formatValue(154200, "currency_compact"),
    exampleBillions: studio.formatValue(1250000000, "currency_compact"),
    exampleInteger: studio.formatValue(2400000, "integer_compact"),
  },
  chains: {
    ethereum: studio.normalizeChain("Ethereum Mainnet"),
    eth: studio.normalizeChain("ETH"),
    unknown: studio.normalizeChain("Base"),
  },
  explorers: {
    address: studio.explorerUrl(address, "address", "ethereum"),
    transaction: studio.explorerUrl(transaction, "transaction", "ETH"),
    unknownChain: studio.explorerUrl(address, "address", "base"),
    invalidIdentifier: studio.explorerUrl("not-an-address", "address", "ethereum"),
  },
}));
"""
    )

    assert result["chartStyles"] == {
        "configured": ["area", "line"],
        "fallback": ["line"],
        "selected": "column",
        "safeDefault": "line",
        "presentations": [
            {
                "style": "line",
                "seriesType": "line",
                "boundaryGap": False,
                "hasArea": False,
                "isScatter": False,
            },
            {
                "style": "area",
                "seriesType": "line",
                "boundaryGap": False,
                "hasArea": True,
                "isScatter": False,
            },
            {
                "style": "column",
                "seriesType": "bar",
                "boundaryGap": True,
                "hasArea": False,
                "isScatter": False,
            },
            {
                "style": "scatter",
                "seriesType": "scatter",
                "boundaryGap": False,
                "hasArea": False,
                "isScatter": True,
            },
        ],
    }
    assert result["compact"] == [
        "0",
        "999",
        "1k",
        "1.25k",
        "12.3k",
        "123.4k",
        "1m",
        "1.23m",
        "1.28b",
        "−1.5m",
    ]
    assert result["formatted"] == {
        "currency": "$1.28b",
        "negativeCurrency": "−$1.5m",
        "integer": "98.73k",
        "exampleMillions": "$2.7m",
        "exampleThousands": "$154.2k",
        "exampleBillions": "$1.25b",
        "exampleInteger": "2.4m",
    }
    assert result["chains"] == {
        "ethereum": "ethereum",
        "eth": "ethereum",
        "unknown": "base",
    }
    assert result["explorers"] == {
        "address": f"https://etherscan.io/address/{'0x1234567890abcdef1234567890abcdef12345678'}",
        "transaction": f"https://etherscan.io/tx/0x{'ab' * 32}",
        "unknownChain": f"https://basescan.org/address/{'0x1234567890abcdef1234567890abcdef12345678'}",
        "invalidIdentifier": "",
    }


def test_shared_tooltip_formatter_compacts_chart_values_and_preserves_signs():
    result = run_node_json(
        """
console.log(JSON.stringify({
  currency: [
    studio.formatTooltipValue(380000000, "currency"),
    studio.formatTooltipValue(12450000, "currency_compact"),
    studio.formatTooltipValue(245900, "currency"),
  ],
  preciseString: studio.formatTooltipValue(
    "12450000.000000000001",
    "currency",
  ),
  integer: studio.formatTooltipValue(1204500, "integer"),
  signed: [
    studio.formatTooltipValue(631200, "currency", { tooltip_signed: true }),
    studio.formatTooltipValue(-3200, "currency", { tooltip_signed: true }),
    studio.formatTooltipValue(0, "currency", { tooltip_signed: true }),
  ],
  percent: studio.formatTooltipValue(0.825, "percent"),
}));
"""
    )

    assert result == {
        "currency": ["$380m", "$12.45m", "$245.9k"],
        "preciseString": "$12.45m",
        "integer": "1.2m",
        "signed": ["+$631.2k", "−$3.2k", "$0"],
        "percent": "82.5%",
    }


def test_stacked_bar_geometry_rounds_only_independent_outer_signed_ends():
    result = run_node_json(
        """
const values = [
  [10, -5, 10, 0],
  [20, -2, 0, -3],
  [0, -7, 5, 0],
];
const vertical = values.map((_, seriesIndex) => (
  studio.stackedBarSeriesData(values, seriesIndex, `color-${seriesIndex}`, {
    orientation: "vertical",
    radius: 4,
  })
));
const horizontal = values.map((_, seriesIndex) => (
  studio.stackedBarSeriesData(values, seriesIndex, `color-${seriesIndex}`, {
    orientation: "horizontal",
    radius: 4,
  })
));
const radii = (matrix) => matrix.map((series) => series.map((datum) => (
  datum.itemStyle.borderRadius
)));
console.log(JSON.stringify({
  vertical: radii(vertical),
  horizontal: radii(horizontal),
  hoverStable: vertical.every((series) => series.every((datum) => (
    JSON.stringify(datum.itemStyle.borderRadius)
      === JSON.stringify(datum.emphasis.itemStyle.borderRadius)
    && JSON.stringify(datum.itemStyle.borderRadius)
      === JSON.stringify(datum.blur.itemStyle.borderRadius)
    && JSON.stringify(datum.itemStyle.borderRadius)
      === JSON.stringify(datum.select.itemStyle.borderRadius)
  ))),
  colorsStable: vertical.every((series, seriesIndex) => series.every((datum) => (
    datum.itemStyle.color === `color-${seriesIndex}`
    && datum.emphasis.itemStyle.color === `color-${seriesIndex}`
  ))),
}));
"""
    )

    assert result == {
        "vertical": [
            [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            [[4, 4, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 4, 4]],
            [[0, 0, 0, 0], [0, 0, 4, 4], [4, 4, 0, 0], [0, 0, 0, 0]],
        ],
        "horizontal": [
            [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
            [[0, 4, 4, 0], [0, 0, 0, 0], [0, 0, 0, 0], [4, 0, 0, 4]],
            [[0, 0, 0, 0], [4, 0, 0, 4], [0, 4, 4, 0], [0, 0, 0, 0]],
        ],
        "hoverStable": True,
        "colorsStable": True,
    }


def test_bar_hover_interaction_preserves_geometry_color_and_neighbor_opacity():
    result = run_node_json(
        """
const radius = [4, 4, 0, 0];
const interaction = studio.stableBarInteraction("#19794b", radius);
console.log(JSON.stringify({
  interaction,
  clonedRadius: interaction.itemStyle.borderRadius !== radius,
  originalRadius: radius,
  geometryKeys: Object.keys(interaction.emphasis.itemStyle)
    .filter((key) => /width|height|size/i.test(key)),
}));
"""
    )

    interaction = result["interaction"]
    assert interaction["axisPointer"] == {"type": "none"}
    assert interaction["itemStyle"] == {
        "color": "#19794b",
        "borderRadius": [4, 4, 0, 0],
    }
    assert interaction["emphasis"]["focus"] == "none"
    assert interaction["emphasis"]["scale"] is False
    assert interaction["emphasis"]["itemStyle"]["color"] == "#19794b"
    assert interaction["emphasis"]["itemStyle"]["borderRadius"] == [4, 4, 0, 0]
    assert interaction["blur"]["itemStyle"]["color"] == "#19794b"
    assert interaction["blur"]["itemStyle"]["opacity"] == 1
    assert result["geometryKeys"] == []
    assert result["clonedRadius"] is True
    assert result["originalRadius"] == [4, 4, 0, 0]


def test_table_view_search_composes_with_sort_pagination_and_formatted_values():
    result = run_node_json(
        """
const rows = [
  {
    id: "old",
    day: "2026-07-20",
    wallet: "0x1111111111111111111111111111111111111111",
    balance: 900,
    active: false,
  },
  {
    id: "small",
    day: "2026-07-29",
    wallet: "0x2222222222222222222222222222222222222222",
    balance: 1234,
    active: true,
  },
  {
    id: "large",
    day: "2026-07-30",
    wallet: "0x3333333333333333333333333333333333333333",
    balance: 98731,
    active: true,
  },
  {
    id: "other",
    day: "2026-07-30",
    wallet: "0x4444444444444444444444444444444444444444",
    balance: 1500,
    active: false,
  },
];
const columns = ["id", "day", "wallet", "balance", "active"];
const columnFormats = {
  balance: "integer_compact",
  active: "boolean",
};
const ranged = studio.filterRowsByRange(rows, "day", "7D", "2026-07-30");
const view = studio.deriveTableView(ranged, columns, {
  query: "yes",
  columnFormats,
  metric: {},
  sortColumn: "balance",
  sortDirection: "descending",
  page: 0,
  pageSize: 1,
});
console.log(JSON.stringify({
  rawAddressSearch: studio.filterTableRows(
    rows,
    columns,
    "3333333333",
    columnFormats,
    {},
  ).map((row) => row.id),
  formattedNumberSearch: studio.filterTableRows(
    rows,
    columns,
    "1.23k",
    columnFormats,
    {},
  ).map((row) => row.id),
  formattedBooleanSearch: studio.filterTableRows(
    rows,
    columns,
    "no",
    columnFormats,
    {},
  ).map((row) => row.id),
  view: {
    ids: view.rows.map((row) => row.id),
    sortedIds: view.sortedRows.map((row) => row.id),
    totalRows: view.totalRows,
    filteredRows: view.filteredRows,
    page: view.page,
    pageCount: view.pageCount,
    start: view.start,
    end: view.end,
  },
  clampedPage: studio.deriveTableView(rows, columns, {
    page: 99,
    pageSize: 3,
  }).page,
  empty: studio.deriveTableView(rows, columns, {
    query: "does-not-exist",
    page: 8,
    pageSize: 2,
  }),
  original: rows.map((row) => row.id),
}));
"""
    )

    assert result["rawAddressSearch"] == ["large"]
    assert result["formattedNumberSearch"] == ["small"]
    assert result["formattedBooleanSearch"] == ["old", "other"]
    assert result["view"] == {
        "ids": ["large"],
        "sortedIds": ["large", "small"],
        "totalRows": 3,
        "filteredRows": 2,
        "page": 0,
        "pageCount": 2,
        "start": 0,
        "end": 1,
    }
    assert result["clampedPage"] == 1
    assert result["empty"]["rows"] == []
    assert result["empty"]["sortedRows"] == []
    assert result["empty"]["totalRows"] == 4
    assert result["empty"]["filteredRows"] == 0
    assert result["empty"]["page"] == 0
    assert result["empty"]["pageCount"] == 0
    assert result["original"] == ["old", "small", "large", "other"]


def test_demo_and_generated_normalizers_report_precise_source_states():
    result = run_node_json(
        """
const descriptor = {
  kind: "demo_bundle",
  dataset: "series",
  queryId: 1234567,
  queryUrl: "https://dune.com/queries/1234567",
  dataFile: "demo.json",
  expectedColumns: ["day", "value"],
};
const demoPayload = {
  meta: {
    dashboard_id: "demo",
    last_refreshed: "2026-07-30T12:00:00Z",
    freshness_status: "current",
  },
  datasets: {
    series: [{ day: "2026-07-30", value: 42, ignored: "kept raw" }],
    empty: [],
    failed: { error: "Controlled query failure.", hint: "Try again later." },
    missing: [{ day: "2026-07-30" }],
  },
};
const generatedPayload = {
  schema_version: 1,
  query_id: 1234567,
  query_url: "https://dune.com/queries/1234567",
  generated_at: "2026-07-30T12:10:00Z",
  execution_id: "exec-1234567",
  execution_finished_at: "2026-07-30T12:00:00Z",
  status: "success",
  freshness_status: "current",
  row_count: 1,
  columns: ["day", "value", "ignored"],
  rows: [{ day: "2026-07-30", value: 42, ignored: "kept raw" }],
};
const generatedDescriptor = {
  ...descriptor,
  kind: "generated_query",
  dataFile: "query_1234567.json",
  expectedColumns: ["day", "value"],
  staleAfterHours: 4,
};
const manifestEntry = {
  query_id: 1234567,
  query_url: generatedPayload.query_url,
  generated_at: generatedPayload.generated_at,
  execution_id: generatedPayload.execution_id,
  execution_finished_at: generatedPayload.execution_finished_at,
  status: generatedPayload.status,
  freshness_status: generatedPayload.freshness_status,
  row_count: generatedPayload.row_count,
  columns: generatedPayload.columns,
  data_file: "query_1234567.json",
};
const readyDemo = studio.normalizeDemoBundle(
  demoPayload,
  descriptor,
  "series",
  "2026-07-30T13:00:00Z",
);
const emptyDemo = studio.normalizeDemoBundle(
  demoPayload,
  { ...descriptor, dataset: "empty" },
  "empty",
);
const failedDemo = studio.normalizeDemoBundle(
  demoPayload,
  { ...descriptor, dataset: "failed" },
  "failed",
);
const missingDemo = studio.normalizeDemoBundle(
  demoPayload,
  { ...descriptor, dataset: "missing" },
  "missing",
);
const readyGenerated = studio.normalizeGeneratedQuery(
  generatedPayload,
  generatedDescriptor,
  "2026-07-30T13:00:00Z",
  manifestEntry,
);
const staleGenerated = studio.normalizeGeneratedQuery(
  generatedPayload,
  generatedDescriptor,
  "2026-07-31T13:00:00Z",
  manifestEntry,
);
const missingGenerated = studio.normalizeGeneratedQuery(
  {
    ...generatedPayload,
    columns: ["day"],
    rows: [{ day: "2026-07-30" }],
  },
  generatedDescriptor,
  "2026-07-30T13:00:00Z",
);
const failedGenerated = studio.normalizeGeneratedQuery(
  {
    ...generatedPayload,
    status: "failed",
    freshness_status: "current",
    row_count: 0,
    columns: [],
    rows: undefined,
    error: "Dune execution failed.",
  },
  generatedDescriptor,
  "2026-07-30T13:00:00Z",
);
const mismatchGenerated = studio.normalizeGeneratedQuery(
  generatedPayload,
  generatedDescriptor,
  "2026-07-30T13:00:00Z",
  { ...manifestEntry, row_count: 2 },
);
const missingExecutionGenerated = studio.normalizeGeneratedQuery(
  { ...generatedPayload, execution_id: undefined },
  generatedDescriptor,
  "2026-07-30T13:00:00Z",
  manifestEntry,
);
const executionMismatchGenerated = studio.normalizeGeneratedQuery(
  generatedPayload,
  generatedDescriptor,
  "2026-07-30T13:00:00Z",
  { ...manifestEntry, execution_id: "different-execution" },
);
const validation = studio.validateExpectedColumns(
  [{ day: "2026-07-30" }],
  ["day", "value"],
  ["day"],
);
console.log(JSON.stringify({
  demo: {
    ready: {
      status: readyDemo.meta.status,
      rows: readyDemo.data,
      columns: readyDemo.meta.columns,
      generatedAt: readyDemo.meta.generated_at,
    },
    empty: {
      status: emptyDemo.meta.status,
      rows: emptyDemo.data,
    },
    failed: {
      status: failedDemo.meta.status,
      code: failedDemo.data.code,
      error: failedDemo.data.error,
    },
    missing: {
      status: missingDemo.meta.status,
      code: missingDemo.data.code,
      missingText: missingDemo.data.hint,
    },
  },
  generated: {
    ready: {
      status: readyGenerated.meta.status,
      stale: readyGenerated.meta.stale,
      rows: readyGenerated.data,
    },
    stale: {
      status: staleGenerated.meta.status,
      freshnessStatus: staleGenerated.meta.freshness_status,
      stale: staleGenerated.meta.stale,
    },
    missing: {
      status: missingGenerated.meta.status,
      code: missingGenerated.data.code,
    },
    failed: {
      status: failedGenerated.meta.status,
      code: failedGenerated.data.code,
      error: failedGenerated.data.error,
    },
    mismatch: {
      status: mismatchGenerated.meta.status,
      code: mismatchGenerated.data.code,
    },
    missingExecution: {
      status: missingExecutionGenerated.meta.status,
      code: missingExecutionGenerated.data.code,
    },
    executionMismatch: {
      status: executionMismatchGenerated.meta.status,
      code: executionMismatchGenerated.data.code,
    },
  },
  validation,
  staleness: {
    within: studio.isSourceStale(
      { execution_finished_at: "2026-07-30T12:00:00Z" },
      4,
      "2026-07-30T15:59:59Z",
    ),
    overdue: studio.isSourceStale(
      { execution_finished_at: "2026-07-30T12:00:00Z" },
      4,
      "2026-07-30T16:00:01Z",
    ),
    disabled: studio.isSourceStale(
      { execution_finished_at: "2020-01-01T00:00:00Z" },
      null,
      "2026-07-30T16:00:01Z",
    ),
  },
  timestamps: {
    stamp: studio.dateStamp("2026-07-30T23:59:59-04:00"),
    label: studio.utcTimestampLabel("2026-07-30T18:40:00Z"),
  },
}));
"""
    )

    assert result["demo"]["ready"] == {
        "status": "success",
        "rows": [{"day": "2026-07-30", "value": 42, "ignored": "kept raw"}],
        "columns": ["day", "value", "ignored"],
        "generatedAt": "2026-07-30T12:00:00Z",
    }
    assert result["demo"]["empty"] == {"status": "empty", "rows": []}
    assert result["demo"]["failed"] == {
        "status": "failed",
        "code": "failed",
        "error": "Controlled query failure.",
    }
    assert result["demo"]["missing"]["status"] == "missing_columns"
    assert result["demo"]["missing"]["code"] == "missing_columns"
    assert "value" in result["demo"]["missing"]["missingText"]
    assert result["generated"]["ready"] == {
        "status": "success",
        "stale": False,
        "rows": [{"day": "2026-07-30", "value": 42, "ignored": "kept raw"}],
    }
    assert result["generated"]["stale"] == {
        "status": "success",
        "freshnessStatus": "stale",
        "stale": True,
    }
    assert result["generated"]["missing"] == {
        "status": "missing_columns",
        "code": "missing_columns",
    }
    assert result["generated"]["failed"] == {
        "status": "failed",
        "code": "failed",
        "error": "Dune execution failed.",
    }
    assert result["generated"]["mismatch"] == {
        "status": "malformed",
        "code": "malformed",
    }
    assert result["generated"]["missingExecution"] == {
        "status": "malformed",
        "code": "malformed",
    }
    assert result["generated"]["executionMismatch"] == {
        "status": "malformed",
        "code": "malformed",
    }
    assert result["validation"] == {
        "valid": False,
        "expectedColumns": ["day", "value"],
        "missingColumns": ["value"],
        "rowErrors": [
            {
                "rowIndex": 0,
                "missingColumns": ["value"],
                "invalidRow": False,
            }
        ],
    }
    assert result["staleness"] == {
        "within": False,
        "overdue": True,
        "disabled": False,
    }
    assert result["timestamps"] == {
        "stamp": "2026-07-31",
        "label": "30 Jul 2026 · 18:40 UTC",
    }


def test_rich_manifest_refresh_status_and_freshness_policy_are_validated():
    result = run_node_json(
        """
const query = {
  query_id: 42,
  query_url: "https://dune.com/queries/42",
  generated_at: "2026-07-31T08:00:00Z",
  execution_id: "exec-42",
  execution_finished_at: "2026-07-31T07:55:00Z",
  data_updated_at: "2026-07-31T07:50:00Z",
  status: "success",
  freshness_status: "delayed",
  row_count: 1,
  columns: ["day", "value"],
  data_file: "query_42.json",
};
const manifest = studio.normalizeManifest({
  schema_version: 1,
  snapshot_id: "live-20260731-active",
  generated_at: "2026-07-31T08:00:00Z",
  dashboard_refreshed_at: "2026-07-31T08:05:00Z",
  display_updated_at: "2026-07-31T07:50:00Z",
  data_updated_at: "2026-07-31T07:50:00Z",
  mode: "live",
  validation_status: "valid",
  queries: [query],
});
const refresh = studio.normalizeRefreshStatus({
  schema_version: 2,
  current_snapshot_id: "live-20260731-active",
  previous_snapshot_id: "live-20260730-previous",
  latest_attempt_status: "failed",
  using_previous: true,
  last_checked_at: "2026-07-31T09:00:00Z",
  latest_failure: {
    failed_query_ids: [42],
    categories: ["timeout"],
    summary: "One query timed out.",
  },
});
function errorMessage(payload) {
  try {
    studio.normalizeManifest(payload);
    return "";
  } catch (error) {
    return error.message;
  }
}
const base = {
  schema_version: 1,
  snapshot_id: "live-20260731-active",
  generated_at: "2026-07-31T08:00:00Z",
  dashboard_refreshed_at: "2026-07-31T08:05:00Z",
  display_updated_at: "2026-07-31T07:50:00Z",
  data_updated_at: "2026-07-31T07:50:00Z",
  mode: "live",
  validation_status: "valid",
  queries: [query],
};
const policy = {
  expected_refresh_hours: 2,
  warning_after_hours: 4,
  stale_after_hours: 8,
};
console.log(JSON.stringify({
  manifest: {
    snapshotId: manifest.snapshot_id,
    dashboardRefreshedAt: manifest.dashboard_refreshed_at,
    displayUpdatedAt: manifest.display_updated_at,
    freshness: manifest.queries[0].freshness_status,
  },
  refresh: {
    status: refresh.latest_attempt_status,
    usingPrevious: refresh.using_previous,
    summary: refresh.latest_failure.summary,
  },
  freshness: {
    current: studio.classifySourceFreshness(
      { data_updated_at: "2026-07-31T00:00:00Z" },
      policy,
      "2026-07-31T03:59:59Z",
    ),
    delayed: studio.classifySourceFreshness(
      { data_updated_at: "2026-07-31T00:00:00Z" },
      policy,
      "2026-07-31T04:00:01Z",
    ),
    stale: studio.classifySourceFreshness(
      { data_updated_at: "2026-07-31T00:00:00Z" },
      policy,
      "2026-07-31T08:00:01Z",
    ),
    explicitStale: studio.classifySourceFreshness(
      {
        data_updated_at: "2026-07-31T07:59:00Z",
        freshness_status: "stale",
      },
      policy,
      "2026-07-31T08:00:00Z",
    ),
    executionWins: studio.classifySourceFreshness(
      {
        execution_finished_at: "2026-07-30T00:00:00Z",
        data_updated_at: "2026-07-31T07:59:00Z",
        freshness_status: "current",
      },
      policy,
      "2026-07-31T08:00:00Z",
    ),
  },
  errors: {
    duplicate: errorMessage({ ...base, queries: [query, { ...query }] }),
    incomplete: errorMessage({ ...base, display_updated_at: undefined }),
    invalidDashboardRefresh: errorMessage({
      ...base,
      dashboard_refreshed_at: "not-a-timestamp",
    }),
    missingExecution: errorMessage({
      ...base,
      queries: [{ ...query, execution_id: undefined }],
    }),
    unsafe: errorMessage({
      ...base,
      queries: [{ ...query, data_file: "../query_42.json" }],
    }),
  },
}));
"""
    )

    assert result["manifest"] == {
        "snapshotId": "live-20260731-active",
        "dashboardRefreshedAt": "2026-07-31T08:05:00Z",
        "displayUpdatedAt": "2026-07-31T07:50:00Z",
        "freshness": "delayed",
    }
    assert result["refresh"] == {
        "status": "failed",
        "usingPrevious": True,
        "summary": "One query timed out.",
    }
    assert result["freshness"] == {
        "current": "current",
        "delayed": "delayed",
        "stale": "stale",
        "explicitStale": "stale",
        "executionWins": "stale",
    }
    assert "duplicate" in result["errors"]["duplicate"].lower()
    assert "incomplete" in result["errors"]["incomplete"].lower()
    assert "incomplete" in result["errors"]["invalidDashboardRefresh"].lower()
    assert "malformed" in result["errors"]["missingExecution"].lower()
    assert "unsafe" in result["errors"]["unsafe"].lower()


def test_runtime_header_prefers_dashboard_refresh_timestamp_and_formats_utc():
    result = run_node_json(
        """
const attributes = {};
const time = {
  dateTime: "",
  textContent: "",
  setAttribute(name, value) { attributes[name] = value; },
};
studio.updateDashboardTimestamp({
  data: {
    meta: {
      dashboard_refreshed_at: "2026-08-04T09:25:31Z",
      display_updated_at: "2026-08-01T06:29:57Z",
    },
  },
  page: {
    querySelector(selector) {
      return selector === "[data-studio-last-updated]" ? time : null;
    },
  },
});
console.log(JSON.stringify({
  dateTime: time.dateTime,
  datetime: attributes.datetime,
  text: time.textContent,
}));
"""
    )

    assert result == {
        "dateTime": "2026-08-04T09:25:31Z",
        "datetime": "2026-08-04T09:25:31Z",
        "text": "04 Aug 2026 · 09:25 UTC",
    }


def test_counter_reports_unavailable_or_stale_auxiliary_sparkline_data():
    result = run_node_json(
        """
const metric = {
  id: "total_value",
  data_source: "summary",
  columns: ["value"],
  sparkline_data_source: "trend",
  sparkline_date_column: "day",
  sparkline_column: "value",
};
const state = {
  data: {
    datasets: {
      summary: [{ value: 42 }],
      trend: {
        error: "The source query failed.",
        hint: "Retry later.",
        code: "failed",
      },
    },
    sourceMeta: {
      summary: { status: "success", stale: false, columns: ["value"] },
      trend: { status: "failed", stale: false, columns: ["day", "value"] },
    },
  },
};
const failed = studio.metricSourceNotice(state, metric);
state.data.datasets.trend = [{ day: "2026-07-29", value: 40 }];
state.data.sourceMeta.trend = {
  status: "stale",
  stale: true,
  execution_finished_at: "2026-07-29T18:40:00Z",
  columns: ["day", "value"],
};
const stale = studio.metricSourceNotice(state, metric);
state.data.sourceMeta.trend.stale = false;
state.data.sourceMeta.trend.status = "success";
state.data.sourceMeta.trend.freshness_status = "delayed";
const delayed = studio.metricSourceNotice(state, metric);
state.data.sourceMeta.trend.freshness_status = "current";
state.data.datasets.trend = [];
const empty = studio.metricSourceNotice(state, metric);
state.data.datasets.trend = [{ day: "2026-07-29", value: 40 }];
const ready = studio.metricSourceNotice(state, metric);
console.log(JSON.stringify({ failed, stale, delayed, empty, ready }));
"""
    )

    assert result["failed"] == {
        "kind": "partial",
        "text": "Trend unavailable · query failed",
        "timestamp": "",
    }
    assert result["stale"] == {
        "kind": "stale",
        "text": "Trend data stale · result from 29 Jul 2026",
        "timestamp": "2026-07-29T18:40:00Z",
    }
    assert result["delayed"] == {
        "kind": "delayed",
        "text": "Trend refresh delayed · showing latest valid data",
        "timestamp": "2026-07-29T18:40:00Z",
    }
    assert result["empty"] == {
        "kind": "partial",
        "text": "Trend unavailable · no data",
        "timestamp": "",
    }
    assert result["ready"] is None


def test_data_loader_deduplicates_fetches_and_isolates_source_failures():
    result = run_node_json(
        """
(async () => {
  function queryPayload(queryId, overrides) {
    return {
      schema_version: 1,
      query_id: queryId,
      query_url: `https://dune.com/queries/${queryId}`,
      generated_at: "2026-07-30T13:00:00Z",
      execution_id: `exec-${queryId}`,
      execution_finished_at: "2026-07-30T12:00:00Z",
      status: "success",
      freshness_status: "current",
      row_count: 1,
      columns: ["day", "value", "users"],
      rows: [{ day: "2026-07-30", value: 42, users: 9 }],
      ...overrides,
    };
  }
  function manifestEntry(payload, dataFile) {
    return {
      query_id: payload.query_id,
      query_url: payload.query_url,
      generated_at: payload.generated_at,
      execution_id: payload.execution_id,
      execution_finished_at: payload.execution_finished_at,
      status: payload.status,
      freshness_status: payload.freshness_status,
      row_count: payload.row_count,
      columns: payload.columns,
      data_file: dataFile,
    };
  }
  const shared = queryPayload(1001);
  const empty = queryPayload(1002, {
    execution_finished_at: "2026-07-30T11:00:00Z",
    status: "empty",
    row_count: 0,
    columns: ["day", "value"],
    rows: [],
  });
  const failed = queryPayload(1003, {
    execution_finished_at: "2026-07-30T10:00:00Z",
    status: "failed",
    freshness_status: "current",
    row_count: 0,
    columns: [],
    rows: undefined,
    error: "Execution failed before a result was written.",
  });
  const badColumns = queryPayload(1004, {
    columns: ["day"],
    rows: [{ day: "2026-07-30" }],
  });
  const malformedContract = queryPayload(1005);
  const missingFile = queryPayload(1006);
  const manifest = {
    schema_version: 1,
    snapshot_id: "live-20260730-active",
    generated_at: "2026-07-30T13:30:00Z",
    display_updated_at: "2026-07-30T10:00:00Z",
    data_updated_at: "2026-07-30T10:00:00Z",
    mode: "live",
    validation_status: "valid",
    queries: [
      manifestEntry(shared, "query_1001.json"),
      manifestEntry(empty, "query_1002.json"),
      manifestEntry(failed, "query_1003.json"),
      manifestEntry(badColumns, "query_1004.json"),
      manifestEntry(malformedContract, "query_1005.json"),
      manifestEntry(missingFile, "query_1006.json"),
    ],
  };
  const demo = {
    meta: {
      dashboard_id: "adapter_test",
      last_refreshed: "2026-07-30T09:00:00Z",
      status: "demo",
    },
    datasets: {
      demo_rows: [{ label: "demo", value: 7 }],
    },
  };
  const payloads = {
    "/manifest.json": manifest,
    "/refresh_status.json": {
      schema_version: 2,
      current_snapshot_id: "live-20260730-active",
      latest_attempt_status: "success",
      using_previous: false,
      last_checked_at: "2026-07-30T13:30:00Z",
      latest_failure: null,
    },
    "/query_1001.json": shared,
    "/query_1002.json": empty,
    "/query_1003.json": failed,
    "/query_1004.json": badColumns,
    "/demo.json": demo,
  };
  const calls = {};
  async function fetcher(url) {
    calls[url] = (calls[url] || 0) + 1;
    if (url === "/query_1006.json") {
      return {
        ok: false,
        status: 404,
        async json() { return {}; },
      };
    }
    if (url === "/query_1005.json") {
      return {
        ok: true,
        async json() { throw new SyntaxError("Unexpected token"); },
      };
    }
    return {
      ok: true,
      async json() { return payloads[url]; },
    };
  }
  const generated = (queryId, dataFile, expectedColumns) => ({
    kind: "generated_query",
    url: `/${dataFile}`,
    queryId,
    queryUrl: `https://dune.com/queries/${queryId}`,
    dataFile,
    expectedColumns,
  });
  const config = {
    dataMode: "generated",
    manifestUrl: "/manifest.json",
    dashboard: { id: "adapter_test", slug: "adapter-test" },
    metrics: [],
    dataSources: {
      shared_value: generated(1001, "query_1001.json", ["day", "value"]),
      shared_users: generated(1001, "query_1001.json", ["day", "users"]),
      empty: generated(1002, "query_1002.json", ["day", "value"]),
      failed: generated(1003, "query_1003.json", ["day", "value"]),
      missing_columns: generated(1004, "query_1004.json", ["day", "value"]),
      malformed: generated(1005, "query_1005.json", ["day", "value"]),
      unavailable: generated(1006, "query_1006.json", ["day", "value"]),
      demo_rows: {
        kind: "demo_bundle",
        url: "/demo.json",
        dataset: "demo_rows",
        queryId: 2001,
        queryUrl: "https://dune.com/queries/2001",
        dataFile: "demo.json",
        expectedColumns: ["label", "value"],
      },
    },
  };
  const data = await studio.loadStudioSources(
    config,
    fetcher,
    "2026-07-30T14:00:00Z",
  );
  console.log(JSON.stringify({
    calls,
    meta: data.meta,
    statuses: Object.fromEntries(
      Object.entries(data.sourceMeta).map(([name, metadata]) => [
        name,
        metadata.status,
      ]),
    ),
    rows: {
      sharedValue: data.datasets.shared_value,
      sharedUsers: data.datasets.shared_users,
      empty: data.datasets.empty,
      demo: data.datasets.demo_rows,
    },
    errors: {
      failed: data.datasets.failed.code,
      missingColumns: data.datasets.missing_columns.code,
      malformed: data.datasets.malformed.code,
      unavailable: data.datasets.unavailable.code,
    },
  }));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    )

    assert result["calls"] == {
        "/manifest.json": 1,
        "/refresh_status.json": 1,
        "/query_1001.json": 1,
        "/query_1002.json": 1,
        "/query_1003.json": 1,
        "/query_1004.json": 1,
        "/query_1005.json": 1,
        "/query_1006.json": 1,
        "/demo.json": 1,
    }
    assert result["meta"]["generated_at"] == "2026-07-30T13:30:00Z"
    assert result["meta"]["execution_finished_at"] == "2026-07-30T09:00:00Z"
    assert result["meta"]["freshness_status"] == "current"
    assert result["meta"]["result_status"] == "partial"
    assert result["meta"]["manifest_status"] == "ready"
    assert result["statuses"] == {
        "shared_value": "success",
        "shared_users": "success",
        "empty": "empty",
        "failed": "failed",
        "missing_columns": "missing_columns",
        "malformed": "malformed",
        "unavailable": "unavailable",
        "demo_rows": "success",
    }
    assert result["rows"] == {
        "sharedValue": [{"day": "2026-07-30", "value": 42, "users": 9}],
        "sharedUsers": [{"day": "2026-07-30", "value": 42, "users": 9}],
        "empty": [],
        "demo": [{"label": "demo", "value": 7}],
    }
    assert result["errors"] == {
        "failed": "failed",
        "missingColumns": "missing_columns",
        "malformed": "malformed",
        "unavailable": "unavailable",
    }


def test_loader_uses_manifest_paths_and_keeps_previous_snapshot_metadata_separate():
    result = run_node_json(
        """
(async () => {
  const query = {
    schema_version: 1,
    query_id: 42,
    query_url: "https://dune.com/queries/42",
    generated_at: "2026-07-31T08:00:00Z",
    execution_id: "exec-42",
    execution_finished_at: "2026-07-30T23:55:00Z",
    data_updated_at: "2026-07-29T22:00:00Z",
    status: "success",
    freshness_status: "delayed",
    row_count: 1,
    columns: ["value"],
    rows: [{ value: 42 }],
  };
  const manifest = {
    schema_version: 1,
    snapshot_id: "live-20260730-active",
    generated_at: "2026-07-30T23:59:00Z",
    dashboard_refreshed_at: "2026-07-30T23:59:30Z",
    display_updated_at: "2026-07-29T22:00:00Z",
    data_updated_at: "2026-07-29T22:00:00Z",
    mode: "live",
    validation_status: "valid",
    queries: [{
      ...query,
      rows: undefined,
      data_file: "query_42.json",
      result_file: "query_42.json",
    }],
  };
  const refresh = {
    schema_version: 2,
    current_snapshot_id: "live-20260730-active",
    previous_snapshot_id: "live-20260729-previous",
    latest_attempt_status: "failed",
    using_previous: true,
    last_checked_at: "2026-07-31T09:00:00Z",
    latest_failure: {
      failed_query_ids: [42],
      categories: ["timeout"],
      summary: "The latest query timed out.",
    },
  };
  const config = {
    dataMode: "generated",
    manifestUrl: "/active/manifest.json",
    dashboard: { id: "authority", slug: "authority" },
    metrics: [],
    dataSources: {
      result: {
        kind: "generated_query",
        url: "/wrong/query_42.json",
        queryId: 42,
        queryUrl: query.query_url,
        dataFile: "query_42.json",
        expectedColumns: ["value"],
      },
    },
  };
  async function load(refreshAvailable, manifestPayload = manifest) {
    const calls = {};
    const data = await studio.loadStudioSources(
      config,
      async (url) => {
        calls[url] = (calls[url] || 0) + 1;
        if (url === "/active/manifest.json") {
          return { ok: true, async json() { return manifestPayload; } };
        }
        if (url === "/active/refresh_status.json") {
          return refreshAvailable
            ? { ok: true, async json() { return refresh; } }
            : { ok: false, status: 404, async json() { return {}; } };
        }
        if (url === "/active/query_42.json") {
          return { ok: true, async json() { return query; } };
        }
        return { ok: false, status: 404, async json() { return {}; } };
      },
      "2026-07-31T09:00:00Z",
    );
    return { data, calls };
  }
  const previous = await load(true);
  const noStatus = await load(false);
  const legacyManifest = { ...manifest };
  delete legacyManifest.dashboard_refreshed_at;
  const legacy = await load(false, legacyManifest);
  const metric = {
    id: "result_metric",
    name: "Result metric",
    data_source: "result",
    columns: ["value"],
  };
  const state = {
    config,
    data: previous.data,
  };
  console.log(JSON.stringify({
    calls: previous.calls,
    meta: previous.data.meta,
    source: previous.data.sourceMeta.result,
    rows: previous.data.datasets.result,
    notice: studio.metricSourceNotice(state, metric),
    exportDate: studio.metricGeneratedDate(state, metric),
    noStatus: {
      rows: noStatus.data.datasets.result,
      snapshotState: noStatus.data.sourceMeta.result.snapshot_state,
      refreshStatus: noStatus.data.meta.refresh_status_status,
    },
    legacyDashboardRefreshedAt: legacy.data.meta.dashboard_refreshed_at,
  }));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    )

    assert result["calls"] == {
        "/active/manifest.json": 1,
        "/active/refresh_status.json": 1,
        "/active/query_42.json": 1,
    }
    assert "/wrong/query_42.json" not in result["calls"]
    assert result["rows"] == [{"value": 42}]
    assert result["meta"]["generated_at"] == "2026-07-30T23:59:00Z"
    assert result["meta"]["dashboard_refreshed_at"] == "2026-07-30T23:59:30Z"
    assert result["meta"]["display_updated_at"] == "2026-07-29T22:00:00Z"
    assert result["meta"]["snapshot_state"] == "previous"
    assert result["meta"]["result_status"] == "success"
    assert result["meta"]["freshness_status"] == "delayed"
    assert result["source"]["result_status"] == "success"
    assert result["source"]["freshness_status"] == "delayed"
    assert result["source"]["snapshot_state"] == "previous"
    assert result["notice"] == {
        "kind": "previous",
        "text": "Using previous snapshot · latest refresh failed",
        "timestamp": "2026-07-29T22:00:00Z",
    }
    assert result["exportDate"] == "2026-07-29"
    assert result["noStatus"] == {
        "rows": [{"value": 42}],
        "snapshotState": "current",
        "refreshStatus": "unavailable",
    }
    assert result["legacyDashboardRefreshedAt"] == "2026-07-30T23:59:00Z"


def test_partial_refresh_uses_previous_snapshot_and_source_scoped_timestamps():
    result = run_node_json(
        """
(async () => {
  function query(queryId, dataUpdatedAt, executionFinishedAt) {
    return {
      schema_version: 1,
      query_id: queryId,
      query_url: `https://dune.com/queries/${queryId}`,
      generated_at: "2026-07-31T08:00:00Z",
      execution_id: `exec-${queryId}`,
      execution_finished_at: executionFinishedAt,
      data_updated_at: dataUpdatedAt,
      status: "success",
      freshness_status: "current",
      row_count: 1,
      columns: ["value"],
      rows: [{ value: queryId }],
    };
  }
  const recent = query(
    42,
    "2026-07-30T22:00:00Z",
    "2026-07-31T07:50:00Z",
  );
  const oldest = query(
    43,
    "2026-07-29T21:00:00Z",
    "2026-07-31T07:45:00Z",
  );
  const manifest = {
    schema_version: 1,
    snapshot_id: "live-20260731-active",
    generated_at: "2026-07-31T08:00:00Z",
    dashboard_refreshed_at: "2026-07-31T08:05:00Z",
    display_updated_at: "2026-07-01T00:00:00Z",
    data_updated_at: "2026-07-01T00:00:00Z",
    mode: "live",
    validation_status: "valid",
    queries: [recent, oldest].map((payload) => ({
      ...payload,
      rows: undefined,
      data_file: `query_${payload.query_id}.json`,
    })),
  };
  const refresh = {
    schema_version: 2,
    current_snapshot_id: "live-20260731-active",
    previous_snapshot_id: "live-20260730-previous",
    latest_attempt_status: "partial",
    using_previous: true,
    last_checked_at: "2026-07-31T09:00:00Z",
    latest_failure: {
      failed_query_ids: [43],
      categories: ["timeout"],
      summary: "One query timed out; previous valid data is active.",
    },
  };
  const config = {
    dataMode: "generated",
    manifestUrl: "/active/manifest.json",
    dashboard: { id: "partial", slug: "partial" },
    metrics: [],
    dataSources: Object.fromEntries([recent, oldest].map((payload) => [
      `query_${payload.query_id}`,
      {
        kind: "generated_query",
        queryId: payload.query_id,
        queryUrl: payload.query_url,
        dataFile: `query_${payload.query_id}.json`,
        expectedColumns: ["value"],
      },
    ])),
  };
  const payloads = {
    "/active/manifest.json": manifest,
    "/active/refresh_status.json": refresh,
    "/active/query_42.json": recent,
    "/active/query_43.json": oldest,
  };
  const data = await studio.loadStudioSources(
    config,
    async (url) => ({
      ok: true,
      async json() { return payloads[url]; },
    }),
    "2026-07-31T09:00:00Z",
  );
  const recentMetric = {
    id: "recent_metric",
    name: "Recent metric",
    data_source: "query_42",
    columns: ["value"],
  };
  const oldestMetric = {
    id: "oldest_metric",
    name: "Oldest metric",
    data_source: "query_43",
    columns: ["value"],
  };
  let invalidPartial = "";
  try {
    studio.normalizeRefreshStatus({ ...refresh, latest_failure: null });
  } catch (error) {
    invalidPartial = error.message;
  }
  console.log(JSON.stringify({
    meta: data.meta,
    recent: data.sourceMeta.query_42,
    oldest: data.sourceMeta.query_43,
    recentNotice: studio.metricSourceNotice({ config, data }, recentMetric),
    oldestNotice: studio.metricSourceNotice({ config, data }, oldestMetric),
    invalidPartial,
  }));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    )

    assert result["meta"]["latest_attempt_status"] == "partial"
    assert result["meta"]["using_previous"] is True
    assert result["meta"]["snapshot_state"] == "partial"
    assert result["meta"]["dashboard_refreshed_at"] == "2026-07-31T08:05:00Z"
    assert result["meta"]["display_updated_at"] == "2026-07-29T21:00:00Z"
    assert result["meta"]["data_updated_at"] == "2026-07-29T21:00:00Z"
    assert result["meta"]["latest_failure"]["failed_query_ids"] == [43]
    assert result["recent"]["display_updated_at"] == "2026-07-30T22:00:00Z"
    assert result["recent"]["data_updated_at"] == "2026-07-30T22:00:00Z"
    assert result["recent"]["snapshot_state"] == "current"
    assert result["oldest"]["display_updated_at"] == "2026-07-29T21:00:00Z"
    assert result["oldest"]["snapshot_state"] == "previous"
    assert result["recentNotice"] is None
    assert result["oldestNotice"] == {
        "kind": "previous",
        "text": "Using previous snapshot · latest refresh partially failed",
        "timestamp": "2026-07-29T21:00:00Z",
    }
    assert "malformed" in result["invalidPartial"].lower()


def test_generated_loader_requires_a_valid_manifest_and_accepts_bootstrap_shape():
    result = run_node_json(
        """
(async () => {
  const query = {
    schema_version: 1,
    query_id: 1001,
    query_url: "https://dune.com/queries/1001",
    generated_at: "2026-07-30T13:00:00Z",
    execution_finished_at: "2026-07-30T12:00:00Z",
    status: "success",
    freshness_status: "current",
    row_count: 1,
    columns: ["value"],
    rows: [{ value: 42 }],
  };
  const config = {
    dataMode: "generated",
    manifestUrl: "/manifest.json",
    dashboard: { id: "manifest_test", slug: "manifest-test" },
    metrics: [],
    dataSources: {
      result: {
        kind: "generated_query",
        url: "/query_1001.json",
        queryId: 1001,
        queryUrl: query.query_url,
        dataFile: "query_1001.json",
        expectedColumns: ["value"],
      },
    },
  };
  async function load(manifestResponse) {
    const calls = {};
    const data = await studio.loadStudioSources(
      config,
      async (url) => {
        calls[url] = (calls[url] || 0) + 1;
        if (url === "/manifest.json") {
          return manifestResponse;
        }
        if (url === "/refresh_status.json") {
          return {
            ok: true,
            async json() {
              return {
                schema_version: 2,
                current_snapshot_id: "live-20260730-active",
                latest_attempt_status: "success",
                using_previous: false,
                last_checked_at: "2026-07-30T14:00:00Z",
                latest_failure: null,
              };
            },
          };
        }
        return { ok: true, async json() { return query; } };
      },
      "2026-07-30T14:00:00Z",
    );
    return { data, calls };
  }
  const missing = await load({
    ok: false,
    status: 404,
    async json() { return {}; },
  });
  const malformed = await load({
    ok: true,
    async json() {
      return { schema_version: 1, generated_at: "not-a-date", queries: [] };
    },
  });
  const bootstrap = studio.normalizeManifest({
    schema_version: 1,
    generated_at: null,
    queries: [],
  });
  console.log(JSON.stringify({
    bootstrap,
    missing: {
      code: missing.data.datasets.result.code,
      status: missing.data.sourceMeta.result.status,
      manifestStatus: missing.data.meta.manifest_status,
      queryCalls: missing.calls["/query_1001.json"] || 0,
    },
    malformed: {
      code: malformed.data.datasets.result.code,
      status: malformed.data.sourceMeta.result.status,
      manifestStatus: malformed.data.meta.manifest_status,
      queryCalls: malformed.calls["/query_1001.json"] || 0,
    },
  }));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    )

    assert result["bootstrap"] == {
        "schema_version": 1,
        "generated_at": "",
        "queries": [],
    }
    assert result["missing"] == {
        "code": "unavailable",
        "status": "unavailable",
        "manifestStatus": "unavailable",
        "queryCalls": 0,
    }
    assert result["malformed"] == {
        "code": "malformed",
        "status": "malformed",
        "manifestStatus": "malformed",
        "queryCalls": 0,
    }


def test_loader_keeps_legacy_dashboard_data_url_compatible():
    result = run_node_json(
        """
(async () => {
  let calls = 0;
  let requestOptions = null;
  const payload = {
    meta: {
      dashboard_id: "legacy",
      status: "demo",
      last_refreshed: "2026-07-30T18:40:00Z",
    },
    datasets: {
      shared: [{ total: 9, users: 4 }],
      empty: [],
    },
  };
  const config = {
    dashboard: { id: "legacy", slug: "legacy" },
    dataUrl: "/legacy.json",
    metrics: [
      {
        id: "total",
        data_source: "shared",
        columns: ["total"],
      },
      {
        id: "users",
        data_source: "shared",
        columns: ["users"],
      },
      {
        id: "empty",
        data_source: "empty",
        columns: ["day", "value"],
      },
    ],
  };
  const data = await studio.loadStudioSources(
    config,
    async (_url, options) => ({
      ok: true,
      async json() {
        calls += 1;
        requestOptions = options;
        return payload;
      },
    }),
    "2026-07-30T19:00:00Z",
  );
  console.log(JSON.stringify({
    calls,
    requestOptions,
    meta: data.meta,
    datasets: data.datasets,
    statuses: Object.fromEntries(
      Object.entries(data.sourceMeta).map(([name, metadata]) => [
        name,
        metadata.status,
      ]),
    ),
  }));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    )

    assert result["calls"] == 1
    assert result["requestOptions"] == {
        "credentials": "same-origin",
        "cache": "no-store",
    }
    assert result["meta"]["generated_at"] == "2026-07-30T18:40:00Z"
    assert result["meta"]["freshness_status"] == "current"
    assert result["datasets"] == {
        "shared": [{"total": 9, "users": 4}],
        "empty": [],
    }
    assert result["statuses"] == {
        "shared": "success",
        "empty": "empty",
    }


def test_metric_csv_export_uses_full_raw_rows_and_identifiers():
    result = run_node_json(
        """
const wallet = "0x1234567890abcdef1234567890abcdef12345678";
const rows = [
  { day: "2026-01-01", wallet, amount: 1234567, ignored: "private" },
  {
    day: "2026-07-30",
    wallet: "0x9999999999999999999999999999999999999999",
    amount: 42,
    ignored: "private",
  },
];
const state = {
  activeRange: "7D",
  config: {
    dashboard: { id: "test_dashboard", slug: "test-dashboard" },
  },
  data: {
    meta: { generated_at: "2026-07-30T18:40:00Z" },
    datasets: { events: rows },
    sourceMeta: {
      events: {
        execution_finished_at: "2026-07-29T22:15:00Z",
        generated_at: "2026-07-30T18:40:00Z",
        columns: ["day", "wallet", "amount", "ignored"],
      },
    },
  },
  tables: new Map([
    ["events_table", { query: "99999", page: 1, sortColumn: "amount" }],
  ]),
  chartStyles: new Map([["events_table", "column"]]),
};
const metric = {
  id: "events_table",
  data_source: "events",
  date_column: "day",
  columns: ["day", "wallet", "amount"],
};
const raw = studio.rawRowsForMetric(state, metric);
const entry = studio.metricCsvEntry(state, metric);
console.log(JSON.stringify({
  rawLength: raw.length,
  cloned: raw !== rows,
  name: entry.name,
  csv: entry.data,
}));
"""
    )

    assert result == {
        "rawLength": 2,
        "cloned": True,
        "name": "test-dashboard-events_table-2026-07-29.csv",
        "csv": (
            "day,wallet,amount\r\n"
            "2026-01-01,0x1234567890abcdef1234567890abcdef12345678,1234567\r\n"
            "2026-07-30,0x9999999999999999999999999999999999999999,42\r\n"
        ),
    }


def test_export_names_use_snapshot_dates_and_empty_results_keep_headers():
    result = run_node_json(
        """
const metric = {
  id: "daily_users",
  data_source: "daily",
  columns: ["day", "users"],
  date_column: "day",
};
function makeState(style) {
  return {
    activeRange: "7D",
    config: {
      dashboard: { id: "campaign", slug: "kyberswap-campaign" },
    },
    data: {
      meta: {
        generated_at: "2026-07-30T18:40:00Z",
        last_refreshed: "2026-07-30T18:40:00Z",
      },
      datasets: { daily: [] },
      sourceMeta: {
        daily: {
          execution_finished_at: "2026-07-29T23:55:00Z",
          generated_at: "2026-07-30T00:05:00Z",
          columns: ["day", "users", "ignored"],
        },
      },
    },
    chartStyles: new Map([["daily_users", style]]),
    tables: new Map([
      ["daily_users", { query: "not-found", page: 8, sortColumn: "users" }],
    ]),
  };
}
const lineState = makeState("line");
const columnState = makeState("column");
const lineEntry = studio.metricCsvEntry(lineState, metric);
const columnEntry = studio.metricCsvEntry(columnState, metric);
const slugFilename = studio.metricExportFilename(lineState, {
  ...metric,
  export_slug: "kyberswap-depositor-journey",
});
const invalidState = makeState("line");
invalidState.data.sourceMeta.daily.columns = ["day"];
const invalid = studio.rawRowsForMetric(invalidState, metric);
console.log(JSON.stringify({
  metricDate: studio.metricGeneratedDate(lineState, metric),
  metricFilename: studio.metricExportFilename(lineState, metric),
  slugFilename,
  dashboardDate: studio.dashboardGeneratedDate(lineState, [metric]),
  dashboardFilename: studio.dashboardExportFilename(lineState, [metric]),
  lineEntry,
  columnEntry,
  unchanged: lineEntry.data === columnEntry.data,
  invalid: {
    code: invalid.code,
    error: invalid.error,
  },
}));
"""
    )

    assert result["metricDate"] == "2026-07-29"
    assert (
        result["metricFilename"]
        == "kyberswap-campaign-daily_users-2026-07-29.csv"
    )
    assert result["slugFilename"] == "kyberswap-depositor-journey-2026-07-29.csv"
    assert result["dashboardDate"] == "2026-07-29"
    assert (
        result["dashboardFilename"]
        == "kyberswap-campaign-studio-2026-07-29.zip"
    )
    assert result["lineEntry"] == {
        "name": "kyberswap-campaign-daily_users-2026-07-29.csv",
        "data": "day,users\r\n",
    }
    assert result["columnEntry"] == result["lineEntry"]
    assert result["unchanged"] is True
    assert result["invalid"]["code"] == "missing_columns"
    assert result["invalid"]["error"] == "An expected column is missing."


def test_selected_zip_preflight_reports_every_unavailable_metric():
    result = run_node_json(
        """
const state = {
  config: { dashboard: { id: "exports", slug: "exports" } },
  data: {
    meta: { display_updated_at: "2026-07-30T00:00:00Z" },
    datasets: {
      ready: [{ value: 42 }],
      unavailable: {
        error: "Query unavailable.",
        hint: "Retry later.",
        code: "unavailable",
      },
    },
    sourceMeta: {
      ready: { columns: ["value"] },
      unavailable: { columns: ["value"], status: "unavailable" },
    },
  },
};
const metrics = [
  {
    id: "ready_metric",
    name: "Ready metric",
    data_source: "ready",
    columns: ["value"],
  },
  {
    id: "missing_metric",
    name: "Missing metric",
    data_source: "unavailable",
    columns: ["value"],
  },
];
const selection = studio.selectedMetricCsvEntries(state, metrics);
console.log(JSON.stringify({
  entryNames: selection.entries.map((entry) => entry.name),
  unavailable: selection.unavailable,
}));
"""
    )

    assert result == {
        "entryNames": ["exports-ready_metric-2026-07-30.csv"],
        "unavailable": ["Missing metric"],
    }


def test_javascript_generated_zip_is_readable_with_python_zipfile():
    result = run_node_json(
        """
const entries = [
  {
    name: "summary.csv",
    data: studio.buildCsv(
      [{ metric: "TVL", value: 123.45 }],
      ["metric", "value"],
    ),
  },
  {
    name: "metrics/ümlaut.csv",
    data: "label,value\\r\\nweETH,384290.7348\\r\\n",
  },
  {
    name: "raw.bin",
    data: new Uint8Array([0, 255, 1, 2]),
  },
];
const first = studio.createZip(entries);
const second = studio.createZip(entries);
console.log(JSON.stringify({
  base64: Buffer.from(first).toString("base64"),
  deterministic: Buffer.compare(Buffer.from(first), Buffer.from(second)) === 0,
}));
"""
    )
    archive_bytes = base64.b64decode(result["base64"])

    assert result["deterministic"] is True
    assert archive_bytes.startswith(b"PK\x03\x04")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == [
            "summary.csv",
            "metrics/ümlaut.csv",
            "raw.bin",
        ]
        assert archive.read("summary.csv") == (
            b"metric,value\r\nTVL,123.45\r\n"
        )
        assert archive.read("metrics/ümlaut.csv") == (
            "label,value\r\nweETH,384290.7348\r\n".encode("utf-8")
        )
        assert archive.read("raw.bin") == bytes([0, 255, 1, 2])
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.flag_bits & 0x800
