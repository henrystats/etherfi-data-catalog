# Example: Shareable Dune Query

Prompt:

> Can you create a Dune query I can share with colleagues?

Flow:

1. Identify the ether.fi question being turned into a query.
2. Use `etherfi-catalog` MCP to select the dataset/tool, caveats, filters, and expected output shape.
3. Use Dune Skills for DuneSQL quality and optimization.
4. Use Dune MCP to create, save, execute, and fetch results.
5. Prefer a team Dune context for team-owned/shareable artifacts when available.

Preserve catalog caveats in the query description or SQL comments if they affect interpretation.
