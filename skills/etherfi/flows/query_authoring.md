# Shareable Query Authoring

Use this flow when the user asks for a Dune query they can save, share, rerun, or hand to teammates.

## Route

1. Ask `etherfi-catalog` MCP for the right ether.fi dataset/tool, caveats, filters, and freshness/completeness notes.
2. If the catalog has a planning mode for the question, use planning mode first and inspect the suggested SQL shape.
3. Follow the repo SQL guide at [`docs/sql_style_guide.md`](../../../docs/sql_style_guide.md), then use Dune Skills for DuneSQL style, optimization, and Dune CLI guidance as needed.
4. Use Dune MCP to create or update the query, execute it, and fetch results when requested.
5. Put important catalog caveats in the Dune query description or SQL comments when they affect interpretation.

## Guardrails

- Do not invent dataset semantics. Let `etherfi-catalog` be the source of truth.
- Do not create a generic SQL-writing tool inside this skill.
- Do not run live query logic from the skill pack.
- Filter date windows early, in the first CTE that scans the selected table.
- Prefer aggregate SQL on Dune for totals, counts, rankings, grouped summaries, and time series.
- Prefer one batched query over repeated per-symbol or per-day queries.
- Prefer dataset-native USD columns when they already answer the question.
- For historical price joins, prefer `dune.ether_fi.result_tokens_prices_enriched_daily`.
- Avoid enriched minute prices unless the question requires minute-level precision.

## Common Decisions

- If the user asks for Cash spend volume, start from Cash events, not Cash balances.
- If the user asks for current holdings or balances, start from the relevant balance/snapshot tool or dataset.
- If the user asks for history, prefer a time-series dataset/tool over repeated snapshots.
- If the user asks for a population total, use a population aggregate, not top-N ranking output.
- If token identity is ambiguous, resolve symbol/address/category with the catalog before writing SQL. For core ether.fi datasets, symbol filters such as `eETH` and `liquidUSD` are normal and acceptable.

## Done When

- The selected dataset/tool and caveats are clear.
- The query is saved or ready to save in Dune.
- The query description or comments preserve important interpretation limits.
- The result shape matches the user's requested artifact.
