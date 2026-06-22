---
name: etherfi
description: Use this skill for ether.fi analytics workflow routing that combines etherfi-catalog MCP, Dune MCP, and Dune Skills. It teaches when to ask the catalog for dataset/tool semantics and caveats, when to use Dune MCP for shareable queries, charts, and dashboards, and when to rely on Dune Skills for DuneSQL or CLI workflow guidance.
---

# ether.fi Analytics Workflow Routing

This skill is workflow glue. It does not replace `etherfi-catalog` MCP, add a data layer, or execute live queries itself.

## Core Rule

For ether.fi-specific analytics prompts, consult `etherfi-catalog` MCP first.

Use the catalog to determine:

- the correct ether.fi dataset or dedicated tool
- semantic caveats and completeness limits
- freshness/status warnings
- safe filters and important disambiguations

Only use Dune MCP after the semantic route is clear, and only when the user wants a new shareable query, chart, dashboard, saved artifact, or Dune-side execution lifecycle.

## Responsibility Split

Use `etherfi-catalog` MCP for:

- choosing the right ether.fi dataset/tool
- surfacing caveats, completeness, freshness, and status
- answering narrow ether.fi live questions when a dedicated live tool exists
- planning SQL shape for review without hitting Dune

Use Dune MCP for:

- creating or updating Dune queries
- executing Dune queries
- fetching execution results
- saving or sharing queries
- generating visualizations
- building dashboards

Use Dune Skills for:

- DuneSQL writing and optimization guidance
- Dune CLI workflows
- Dune-side operational patterns

When authoring ether.fi SQL, also follow the repo guide at
[`docs/sql_style_guide.md`](../../docs/sql_style_guide.md). In short: filter date windows early,
batch related symbols/days into one Dune query, aggregate on Dune instead of in Python, prefer
dataset-native USD columns, use enriched daily prices for historical work, and avoid minute prices
unless minute precision is actually required.

## Choose The Flow

- For live answer only: read [flows/live_question_vs_shareable_query.md](flows/live_question_vs_shareable_query.md).
- For shareable query creation: read [flows/query_authoring.md](flows/query_authoring.md).
- For chart or dashboard requests: read [flows/dashboard_build.md](flows/dashboard_build.md).
- For concrete prompt patterns: read the short examples in [examples/](examples/).

## Common Disambiguations

Surface or resolve these before executing or saving a query:

- Direct holders vs holders with DeFi exposure.
- Cash balances vs Cash events.
- Snapshot answer vs time series.
- Token symbol vs token address vs category bucket.
- Full-population total vs top-N ranking.

Do not stretch a ranking tool into a population-total answer. If the catalog has a purpose-built aggregate or time-series tool, prefer that over repeated point calls.

## Query Hygiene

- Preserve important ether.fi caveats in Dune query descriptions or SQL comments when useful for reviewers.
- Apply date or timestamp filters in the first CTE that scans the base dataset.
- Prefer one batched Dune query over repeated per-day, per-symbol, or per-address calls.
- Aggregate totals, counts, rankings, grouped summaries, and time series in SQL on Dune, not locally.
- Prefer dataset-native USD fields when available; otherwise use `dune.ether_fi.result_tokens_prices_enriched_daily` for historical price joins.
- Avoid `dune.ether_fi.result_tokens_prices_enriched_minute` unless the question truly requires minute-level precision.
- Keep catalog-derived semantics visible when moving from planning to a shareable Dune artifact.
- Avoid ad hoc local chart building when the user asked for a shareable Dune chart or dashboard.
- For team-owned/shareable Dune artifacts, prefer a team Dune context instead of a purely personal workspace when available.
