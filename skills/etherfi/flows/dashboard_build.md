# Chart And Dashboard Build

Use this flow when the user asks for a chart, dashboard widget, dashboard, or shareable visualization.

## Route

1. Confirm the underlying query route with `etherfi-catalog` MCP first, unless the user is continuing from an already-vetted query.
2. Use Dune MCP for query execution, visualization creation, and dashboard work.
3. Use Dune Skills for Dune visualization conventions, DuneSQL reshaping, or Dune CLI workflow guidance when needed.
4. Keep chart labels and descriptions aligned with catalog caveats.

## Visualization Hygiene

- Prefer Dune visualizations for shareable team artifacts.
- Avoid local HTML/CSV/chart generation when the user asked for a Dune chart or dashboard.
- Use time-series output for line charts and grouped bars.
- Use compact aggregate output for KPI cards and tables.
- Include units, chain filters, token filters, and date windows in chart titles or descriptions.

## Dashboard Notes

- For team-owned dashboards, create or move artifacts in a team Dune context when available.
- If the user asks for "that query," reuse the saved Dune query instead of rebuilding from scratch.
- If a chart needs a different grain or grouping, go back through the catalog route before changing the query semantics.

## Done When

- The visualization is backed by a catalog-vetted query.
- Dune MCP has created or updated the requested chart/dashboard artifact.
- The title, description, and filters make the caveats visible enough for teammates.
