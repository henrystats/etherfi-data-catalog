# Example: Latest Cash Address Balances

Prompt:

> What are the latest balances for ether.fi cash address 0x...?

Flow:

1. Use `etherfi-catalog` MCP first.
2. Choose the Cash-safe profile or balance lookup path if available.
3. If needed, use planning mode to confirm caveats and output fields.
4. Use live mode only when the user wants current data and `DUNE_API_KEY` is available to the catalog MCP session.
5. Return balances, recent activity if relevant, freshness/status, and caveats.

Do not create a Dune query unless the user asks for a shareable query or dashboard.
