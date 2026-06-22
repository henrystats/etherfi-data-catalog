# Example: Weekly USDC Cash Spend Volume

Prompt:

> Show me the weekly volume for USDC spends on etherfi-cash.

Flow:

1. Use `etherfi-catalog` MCP to confirm this is a Cash events question, not a Cash balances question.
2. Ask the catalog for event-type semantics, token filters, date fields, and caveats.
3. Use Dune Skills to shape DuneSQL for weekly aggregation.
4. Use Dune MCP only if the user wants the query run, saved, shared, charted, or dashboarded.

Query hygiene:

- Aggregate weekly volume in DuneSQL.
- Filter USDC explicitly; use token address if the symbol is ambiguous.
- Include event/cash-flow caveats in the query description when saving.
