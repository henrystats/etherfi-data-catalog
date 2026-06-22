# Example: Bar Chart For A Query

Prompt:

> Create a bar chart for that query.

Flow:

1. Confirm the existing query was already routed through `etherfi-catalog` MCP, or route it through the catalog before changing semantics.
2. Use Dune MCP to run or reuse the query.
3. Use Dune MCP to create the bar chart visualization.
4. Include the date window, token or chain filters, and relevant caveats in the chart title or description.

Avoid local chart files when the user wants a shareable Dune artifact.
