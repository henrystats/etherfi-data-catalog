# Live Question Vs Shareable Query

Use this flow to decide whether to answer directly through `etherfi-catalog` or create a Dune artifact.

## Live Answer Only

Use `etherfi-catalog` directly when the user asks for a narrow ether.fi answer and a dedicated catalog live tool exists.

Examples:

- "What are the latest balances for this Cash address?"
- "Who are the top Cash users right now?"
- "What is the latest TVL of eETH?"

Route:

1. Use the relevant catalog tool in planning mode if the query shape or caveats need review.
2. Use live mode only when live execution is needed and configured.
3. Return compact rows, caveats, freshness/status, and a clear summary.
4. Do not create a Dune query unless the user asks for a shareable artifact.

## Shareable Query

Use Dune MCP after catalog routing when the user asks to create, save, share, rerun, or hand off a Dune query.

Examples:

- "Can you create a Dune query for weekly USDC Cash spend volume?"
- "Make a query I can share with colleagues."
- "Save this as a Dune query."

Route:

1. Ask the catalog for the correct dataset/tool and caveats.
2. Draft or adapt DuneSQL using Dune Skills as needed.
3. Use Dune MCP to create, save, run, and fetch results.

## Chart Or Dashboard

Use Dune MCP when the user asks for a chart, dashboard, widget, or shareable visualization.

Examples:

- "Create a bar chart for that query."
- "Add this to a dashboard."
- "Make a shareable dashboard widget."

Route:

1. Ensure the query has already been catalog-vetted.
2. Use Dune MCP for visualization and dashboard lifecycle.
3. Preserve caveats and filters in artifact titles or descriptions.

## Ambiguity Checks

Ask or surface a choice when it changes the answer:

- direct holders or holders with DeFi exposure
- Cash balances or Cash events
- point-in-time snapshot or history
- token symbol, address, or category bucket
- top-N ranking or full-population aggregate
