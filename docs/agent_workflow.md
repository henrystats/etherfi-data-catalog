# Agent Workflow

Use this guide when deciding how an agent should combine `etherfi-catalog` MCP, Dune MCP, Dune Skills, and `skills/etherfi`.

## Which Tool Should The Agent Use?

| User intent | Intended routing |
| --- | --- |
| Live ether.fi answer | `etherfi-catalog` only |
| New shareable Dune query | `etherfi-catalog` plan first, then Dune MCP |
| Chart or dashboard artifact | `etherfi-catalog` plan first, then Dune MCP visualization/dashboard tools |
| Query optimization or DuneSQL hygiene | Dune Skills, usually after `etherfi-catalog` has selected the right ether.fi semantics |
| Workflow routing for ether.fi prompts | `skills/etherfi` teaches the agent how to combine the layers |

## Layer Responsibilities

- `etherfi-catalog` MCP is the semantic/planning layer for ether.fi datasets, tools, caveats, freshness/completeness, safe filters, and dedicated live tools.
- Dune MCP handles Dune query creation, updates, execution, results, visualizations, and dashboards.
- Dune Skills help with DuneSQL, Dune CLI workflows, and optimization.
- `skills/etherfi` is workflow glue. It teaches the agent to start with catalog semantics and then use Dune MCP only when a shareable Dune artifact is needed.

## Core User Journeys

### A. Live Answer Only

Prompt:

> What are the latest balances for this Cash address?

Expected flow:

1. Use `etherfi-catalog` only.
2. Pick the dedicated Cash-safe/balance live tool if available.
3. Return compact balances, caveats, and freshness/status.
4. Do not create a Dune query unless the user asks for one.

### B. Shareable Query

Prompt:

> Can you create a Dune query for weekly USDC Cash spend volume?

Expected flow:

1. Use `etherfi-catalog`, usually `plan_etherfi_query(...)`, to choose Cash events, event filters, caveats, grain, metrics, and starter SQL shape.
2. Use Dune Skills for DuneSQL hygiene if the query needs refinement.
3. Use Dune MCP to create, save, run, and fetch the query.

### C. Shareable Chart Or Dashboard

Prompt:

> Create a chart and dashboard widget for that query.

Expected flow:

1. Confirm the query was already planned against ether.fi catalog semantics.
2. Use Dune MCP visualization/dashboard tools to create the chart or widget.
3. Keep important caveats, date ranges, token filters, and units visible in chart or dashboard descriptions.

## Example Prompts And Routing

| Prompt | Intended routing |
| --- | --- |
| "What are the latest balances for ether.fi cash address 0x...?" | `etherfi-catalog` only |
| "Show me the weekly volume for USDC spends on etherfi-cash." | `etherfi-catalog` first; add Dune MCP if the user wants it run/saved/shared |
| "Can you create a Dune query I can share with colleagues?" | `etherfi-catalog` + Dune MCP + Dune Skills |
| "Create a bar chart for that query." | Dune MCP, after confirming the query was catalog-vetted |
| "Should I use protocol_token_holders or protocol_token_holders_with_defi?" | `etherfi-catalog` only |
| "Show monthly TVL for eETH and liquidETH over the last year." | `etherfi-catalog` first; add Dune MCP for a shareable query/chart |

## Shareability And Ownership

If the goal is a query, chart, or dashboard that teammates will reuse, prefer a team-owned Dune context or team API key when available. A personal Dune context can be fine for exploration, but shared artifacts should live where the team can maintain permissions, ownership, and continuity.

## Practical Rules

- Start ether.fi-specific prompts with `etherfi-catalog`; do not invent dataset semantics.
- Use `plan_etherfi_query(...)` for new shareable-query or chart-ready planning prompts.
- Use dedicated catalog live tools for narrow live answers.
- Use Dune MCP for Dune artifact lifecycle work.
- Use Dune Skills for DuneSQL quality and Dune CLI workflows.
- Do not build local charts when the user asked for a shareable Dune artifact.

## Regression Coverage

The intended routing in this guide is covered by `tests/test_orchestration_regressions.py` with fixtures in `tests/fixtures/orchestration_prompt_regressions.yaml`. Update those prompt regressions when changing the workflow contract.
