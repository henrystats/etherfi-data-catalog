# ether.fi analytics catalog

This repository is the starting point for an ether.fi analytics catalog.

The goal is to help AI assistants and team members:

- discover the right materialized views
- understand caveats and completeness
- find existing dashboards
- later support SQL generation

For now, this project is intentionally minimal. It provides the starting catalog structure, a small local Python loader, and a simple local MCP server.

## Recommended team setup

The recommended team setup is a combined stack with clear responsibilities:

- `etherfi-catalog` MCP: ether.fi dataset and tool selection, semantic caveats, freshness/completeness context, and planning-mode SQL review.
- Dune MCP: Dune query lifecycle work, including creating, running, saving, and retrieving query results; it can also help generate charts and dashboards.
- Dune Skills: Dune CLI, query-writing, optimization, and Dune-side workflow guidance for agents.
- `skills/etherfi`: a lightweight ether.fi workflow skill pack that teaches agents how to route between the catalog, Dune MCP, and Dune Skills.

Intended orchestration flow:

1. Ask `etherfi-catalog` which ether.fi dataset, tool, filters, and caveats fit the question.
2. Use Dune MCP to create, run, save, and retrieve the query, and to build charts or dashboards when needed.
3. Use Dune Skills to help the agent write, optimize, and operate Dune-side workflows.

Keep the boundary explicit: `etherfi-catalog` is the semantic catalog and planning layer; Dune MCP is the execution and visualization layer. The catalog should not become a general-purpose Dune client.

### Recommended local install

The recommended team path is a local stdio MCP install. Each teammate installs
Dune MCP separately, installs the ether.fi Catalog MCP from GitHub, and uses
their own local Dune credentials.

Recommended ether.fi Catalog MCP command:

```bash
uvx --from git+https://github.com/henrystats/etherfi-data-catalog etherfi-catalog-mcp
```

Tagged releases can be installed with:

```bash
uvx --from git+https://github.com/henrystats/etherfi-data-catalog@v0.1.0 etherfi-catalog-mcp
```

Fallback with `pipx`:

```bash
pipx run --spec git+https://github.com/henrystats/etherfi-data-catalog etherfi-catalog-mcp
```

Local development from a clone still works:

```bash
.venv/bin/python -m etherfi_catalog.server
```

The server defaults to stdio. Streamable HTTP remains available for local
transport testing or advanced private staging:

```bash
etherfi-catalog-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

Installed runs load bundled catalog metadata from the package. Local repo runs
still prefer the top-level `datasets/`, `dashboards/`, and
`status/dataset_freshness.yaml` files when they exist. Advanced users can point
the runtime at external metadata with:

- `ETHERFI_CATALOG_DATA_DIR`
- `ETHERFI_DATASETS_DIR`
- `ETHERFI_DASHBOARDS_DIR`
- `ETHERFI_STATUS_DIR`
- `ETHERFI_FRESHNESS_PATH`

### MCP client config snippets

Use the current official Dune MCP install command for the `dune` entry. The
placeholder below shows where a local API key belongs when API-key auth is used;
browser-capable clients may use Dune MCP OAuth instead.

Claude Desktop / Claude-style JSON:

```json
{
  "mcpServers": {
    "dune": {
      "command": "<official-dune-mcp-command>",
      "args": ["<official-dune-mcp-args>"],
      "env": {
        "DUNE_API_KEY": "your_dune_api_key_here"
      }
    },
    "etherfi-catalog": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/henrystats/etherfi-data-catalog",
        "etherfi-catalog-mcp"
      ],
      "env": {
        "DUNE_API_KEY": "your_dune_api_key_here"
      }
    }
  }
}
```

Codex TOML:

```toml
[mcp_servers.dune]
command = "<official-dune-mcp-command>"
args = ["<official-dune-mcp-args>"]
tool_timeout_sec = 300

[mcp_servers.dune.env]
DUNE_API_KEY = "your_dune_api_key_here"

[mcp_servers.etherfi-catalog]
command = "uvx"
args = [
  "--from",
  "git+https://github.com/henrystats/etherfi-data-catalog",
  "etherfi-catalog-mcp",
]
startup_timeout_sec = 30
tool_timeout_sec = 60

[mcp_servers.etherfi-catalog.env]
DUNE_API_KEY = "your_dune_api_key_here"
```

Generic stdio MCP shape:

```json
{
  "name": "etherfi-catalog",
  "transport": "stdio",
  "command": "uvx",
  "args": [
    "--from",
    "git+https://github.com/henrystats/etherfi-data-catalog",
    "etherfi-catalog-mcp"
  ],
  "env": {
    "DUNE_API_KEY": "your_dune_api_key_here"
  }
}
```

Metadata, discovery, freshness, dashboard lookup, and query-planning tools work
without `DUNE_API_KEY`. Live ether.fi tools require `DUNE_API_KEY` only when the
caller sets `execute_live=true`, and those live calls may consume Dune credits.
Do not embed a team/shared key in package config; each user should provide their
own key locally.

### Agent workflow quick start

For the practical routing guide and onboarding examples, see [`docs/agent_workflow.md`](docs/agent_workflow.md).
For teammate-friendly ether.fi DuneSQL style, optimization, and price-table defaults, see [`docs/sql_style_guide.md`](docs/sql_style_guide.md).

Quick decision guide:

- Live ether.fi answer: use `etherfi-catalog` only.
- New shareable Dune query: use `etherfi-catalog` or `plan_etherfi_query(...)` first, then Dune MCP.
- Chart or dashboard artifact: confirm the catalog-vetted query plan, then use Dune MCP visualization/dashboard tools.
- Query optimization or DuneSQL hygiene: use Dune Skills.
- Workflow routing: use `skills/etherfi` to teach the agent how to combine the layers.

For team-shared Dune queries and dashboards, prefer a team-owned Dune context or team API key when available.

### Website MVP

This repo also includes a lightweight static website foundation for the Monday
presentation MVP. It intentionally uses only the Python dependencies already in
the project, so previewing the site does not require installing MkDocs, Node, or
another frontend toolchain.

Build the site:

```bash
.venv/bin/python scripts/build_website.py
```

Preview it locally:

```bash
.venv/bin/python -m http.server 8000 --directory output/website
```

Then open `http://localhost:8000`.

Website source files live under `website/`. Generated HTML is written to
`output/website`, which is intentionally ignored by git. Dataset and dashboard
pages will be generated from the catalog metadata in follow-up MVP tickets.

### ether.fi workflow skill

This repo includes `skills/etherfi/` as a compact workflow guide for Codex/Claude-style agents. It does not add a new data layer or replace the MCP server. Use it to teach agents the correct orchestration pattern: start with `etherfi-catalog` for ether.fi semantics and caveats, then use Dune MCP for shareable queries, charts, dashboards, and execution lifecycle, with Dune Skills helping on DuneSQL and Dune CLI workflows.

### Dune MCP setup guidance

Dune MCP supports two common auth paths:

- OAuth: best for browser-capable agents and interactive teammate onboarding. Use this when the agent can complete a browser-based authorization flow.
- API key: best for headless environments, CI-like setups, or agents that cannot complete browser auth. Store the key in the MCP environment rather than hard-coding it in prompts or generated SQL.

For Codex, install and configure Dune MCP separately from this repo's `etherfi-catalog` MCP entry. A teammate's Codex config will usually contain both MCP servers: one for `etherfi-catalog`, and one for Dune MCP. Follow the current Dune MCP installation instructions for the exact command and arguments, then choose either OAuth or API-key auth based on the agent environment.

For long-running Dune result retrieval in Codex, set the Dune MCP server timeout higher than the default:

```toml
[mcp_servers.dune]
# command = "..."
# args = [...]
# env = { DUNE_API_KEY = "..." } # API-key auth only; omit for OAuth setups.
tool_timeout_sec = 300
```

### etherfi-catalog live-tool setup

Most `etherfi-catalog` tools support planning mode with `execute_live=false`. Planning mode does not hit Dune and can work even when live execution is not configured.

Live Dune-backed `etherfi-catalog` tools require `DUNE_API_KEY` to be present in the MCP server process environment. If planning mode works but live mode fails, confirm that the key is propagated into the `etherfi-catalog` MCP session. For local shell sessions, the pattern we have used is:

```bash
set -a; source .env; set +a
```

This environment propagation is for `etherfi-catalog` live tools. It is separate from Dune MCP auth, which may use OAuth or its own API-key configuration.

For current MCP deployment notes, local stdio usage, secret hygiene, and the staged remote deployment checklist, see [`docs/mcp_deployment.md`](docs/mcp_deployment.md).

## Troubleshooting

### Dune MCP auth issues

Use OAuth when the agent can open a browser and complete an interactive auth flow. Use API-key auth for headless setups. If Dune MCP is installed but cannot authenticate, first check that the chosen auth path matches the agent environment, then verify that any API key is configured on the Dune MCP server entry rather than on the `etherfi-catalog` server entry.

### Codex `Transport closed` during Dune results

Long-running Dune MCP `getExecutionResults` calls can hit `Transport closed` in Codex when the tool timeout is too low. Set the Dune MCP server config to:

```toml
tool_timeout_sec = 300
```

### etherfi-catalog live mode cannot see `DUNE_API_KEY`

If `etherfi-catalog` planning mode works but `execute_live=true` fails, the MCP process may not have inherited `DUNE_API_KEY`. Start from a shell where `.env` has been exported:

```bash
set -a; source .env; set +a
```

Then restart the MCP session so the server process receives the environment.

### Catalog planning vs Dune execution

Use `etherfi-catalog` to decide which ether.fi dataset or tool is semantically correct, what caveats apply, and what query shape is expected. Use Dune MCP to run, save, retrieve, visualize, and dashboard the Dune query. When the question is "what should I query?", start with the catalog. When the question is "run/save/chart this query", use Dune MCP.

## dataset metadata

Dataset metadata lives in `datasets/` and may be organized in subfolders under that directory.

Dashboard metadata lives in one-file-per-dashboard YAML files under product folders:

```text
dashboards/
  stake/
  cash/
  liquid/
  others/
```

Use `category: stake|cash|liquid|others` to match the folder where possible. Use `show_in_core: true` when a dashboard should also appear in the website's Core display group. Core is website-only; do not create a `dashboards/core/` folder.

Runtime freshness snapshots belong in local `status/dataset_freshness.yaml`, separate from static dataset metadata.
That file can be generated locally from the saved Dune catalog freshness query or from the older Dune tracker CSV export, and `status/dataset_freshness.example.yaml` shows the expected shape.
To fetch the latest stored result from the saved Dune query that returns `query_id` and `last_updated`, run:

```bash
DUNE_API_KEY=... .venv/bin/python scripts/update_freshness_from_dune.py --query-id 7625551
```

This importer calls Dune's latest query result endpoint and does not trigger a fresh execution of the SQL. Schedule or run the query on Dune itself when you need a new snapshot, then use this importer to pull the already-computed result into the website.

The GitHub Pages workflow in `.github/workflows/refresh-freshness.yml` runs the
same importer hourly and on manual dispatch, rebuilds `output/website`, and
deploys the generated static site. Before enabling it for the launched website,
configure GitHub Pages to use GitHub Actions and add a read-only repository
secret named `DUNE_API_KEY`.

To refresh the local runtime file, run `.venv/bin/python scripts/update_freshness_from_tracker.py path/to/tracker.csv`.
Or use `scripts/refresh_catalog_status.sh path/to/tracker.csv`.

These files are the source of truth for semantic context in this repo. They are meant to help AI assistants and team members choose the right table and ask better follow-up questions.

Important fields currently used:

- name
- display_name
- description
- grain
- refresh cadence
- accuracy label
- completeness label
- use_when
- do_not_use_when
- important_columns
- comparison_notes
- clarifying_questions

Not every dataset will need every field at the beginning.

### Live query and monitoring metadata

Some event datasets may also define grouped `live_query`, `backups`, and `monitoring` metadata. This is a lightweight foundation for a future database-monitor / data-accuracy page; it does not create runtime monitoring jobs by itself.

- `live_query` describes the query/table planners should prefer for current, recent, or latest questions. For now, it may intentionally point to the same query/table as the scheduled materialized-view baseline through `defaults_to_mat_view: true`.
- `backups` reserves weekly and monthly reconciliation references. Empty values are acceptable until backup queries or tables exist.
- `monitoring` records dimensions and metrics a future monitor can use for live-query vs backup comparisons, raw-source event-count sanity checks, and USD/volume checks.

Historical and range-style planning should still prefer the baseline materialized view because settled historical analysis usually gets little practical benefit from a fresher live-query layer. When a live query currently defaults to the mat view, planners should mention the mat view refresh cadence honestly.

For local development, install the project with `pip install -e .[dev]`.

To run the local MCP server over stdio after installing the package, use `etherfi-catalog-mcp`.

Dashboard search is now also available through the MCP server.
Dashboard search can now also surface linked dataset freshness warnings through the MCP server.
Dashboard detail lookup is now also available through the MCP server.
Dashboard status lookup is now also available through the MCP server.
Catalog health summary is now also available through the MCP server.
New-query planning is now also available through `plan_etherfi_query(question, execute_live=false)`.
Assets under management balance lookup planning is now also available through the MCP server.
Dataset search can now also surface freshness and status hints through the MCP server.
Dataset status lookup is now also available through the MCP server.
Stale dataset listing is now also available through the MCP server.
Stale warnings now also include a suggested next action.
Use planning mode by calling `get_assets_under_management_balances(address)` and live mode by setting `DUNE_API_KEY` and calling `get_assets_under_management_balances(address, execute_live=true)`.
Top ether.fi Cash user ranking is available through `get_top_cash_users(as_of_date=None, limit=10, min_total_usd=None, token_symbol=None, token_address=None, blockchain=None, execute_live=false)`.
Example Cash ranking prompts:

- "Who are the top ether.fi Cash holders by liquidUSD?"
- "Show the top Cash users by liquidETH."
- "Who holds the most liquidUSD on Optimism?"

Cash population totals are available through `get_cash_token_totals(as_of_date=None, token_symbol=None, token_address=None, blockchain=None, execute_live=false)`.
Example Cash total prompts:

- "What is the total balance of liquidUSD held by ether.fi Cash users?"
- "How many Cash users hold liquidUSD?"
- "What is the total liquidUSD held by Cash users on Optimism?"

Cash holdings time series are available through `get_cash_holdings_timeseries(start_date=None, end_date=None, period=None, granularity="day", token_symbol=None, token_symbols=None, token_address=None, blockchain=None, group_by=None, category_preset=None, categories=None, execute_live=false)`.
Use this tool for range-based chart questions instead of making repeated point-in-time calls. Supported granularities are `day` and `month`; monthly rows use the latest available daily Cash balance row in each calendar month. When multiple symbols are requested, pass `token_symbols=[...]` so the tool issues one Dune query with `token_symbol IN (...)`.
Supported grouping options:

- `group_by="token_symbol"`: returns chart-friendly rows by token symbol.
- `group_by="category"` with `category_preset="cash_balance_buckets"`: maps exact token symbols into `liquidUSD`, `liquidETH`, `liquidBTC`, and `stables` buckets. The stable bucket is explicit: `USDC` and `USDC.e`. Use `categories=[...]` only to select from those explicit bucket labels.

Example Cash time-series prompts:

- "Show me the average USD holdings of ether.fi Cash users over the last 30 days."
- "Aggregate ether.fi Cash balances by day for the last month."
- "Chart daily average Cash holdings for liquidUSD over the last 90 days."
- "Show the daily total and average USD balances for Cash users on Optimism."
- "Show me monthly ether.fi Cash holdings over the last 2 years."
- "Show monthly ether.fi Cash holdings for liquidUSD, liquidETH, and liquidBTC over the last 2 years."
- "Group monthly Cash balances into liquidUSD, liquidETH, liquidBTC, and stables."
- "Show monthly Cash holdings by category for liquidUSD, liquidETH, liquidBTC, and stables."
- "Return month-end Cash balance rows for a MoM bar racing chart."
- "Return month-end Cash balance rows for these symbols in one query."
- "Aggregate Cash balances for multiple symbols over time."
- "Show monthly Cash holdings by category over time."

Product deployment-footprint planning uses `dune.ether_fi.result_etherfi_assets_under_management` with `parent_symbol` for the product and `token_project` for the deployed protocol. For lending protocols currently identified as Aave and Morpho, planner SQL treats borrow-side rows as negative exposure by checking `secondary_trait = 'borrow'`.
Example product deployment prompts:

- "How much of liquidUSD is held in Aave?"
- "How much liquidETH is deployed in Morpho?"
- "Show liquidUSD deployment by token_project."
- "Where is liquidETH deployed by protocol and chain?"

Protocol token TVL time series are available through `get_protocol_token_tvl_timeseries(strategy_symbol=None, strategy_symbols=None, strategy_address=None, start_date=None, end_date=None, period=None, granularity="day", execute_live=false)`.
Use this tool for historical TVL charts, month-over-month comparisons, and chart-ready history instead of making repeated point-in-time `get_protocol_token_tvl(...)` calls or improvising local CSV/chart workflows.
Supported granularities:

- `day`: one row per day per strategy with `day`, `strategy_symbol`, and `tvl_usd`
- `month`: one row per calendar month per strategy using the latest available daily snapshot in that month, with `month`, `strategy_symbol`, `month_end_day`, and `tvl_usd`

Example protocol-TVL time-series prompts:

- "Show me the TVL in USD for eETH, liquidETH, liquidUSD, eBTC, and liquidBTC over the last 1 year."
- "Chart ether.fi protocol token TVL by day for the last year."
- "Give me the monthly TVL history for eETH and liquidETH."
- "Return month-end TVL rows for liquidUSD over the last year."
- "Prepare month-over-month TVL data for a bar racing chart."
- "Show daily TVL history for liquidETH and eETH over the last 90 days."
- "Compare liquidUSD vs eBTC TVL over time."

Cash-safe profile lookup is available through `get_cash_safe_profile(address, as_of_date=None, recent_days=30, validate_cash_identity=false, execute_live=false)`.
Token price lookup is available through `get_token_price(token_address, blockchain=None, as_of_timestamp=None, granularity="minute", execute_live=false)`.
Batch token price lookup is available through `get_token_prices_batch(token_addresses, blockchain=None, as_of_timestamp=None, granularity="daily", execute_live=false)`.
Price token discovery is available through `find_price_tokens(token_symbol=None, token_project=None, blockchain=None, limit=20, execute_live=false)`.
Symbol-based token price lookup is available through `get_token_price_by_symbol(token_symbol, blockchain=None, token_project=None, as_of_timestamp=None, granularity="minute", execute_live=false)`.
Token price coverage diagnostics are available through `diagnose_token_price_coverage(token_address, blockchain=None, execute_live=false)`.

For Codex, point the MCP config at the `uvx` command shown above. For local
development from a clone, `.venv/bin/python -m etherfi_catalog.server` also
works. If discovery is working, the server should appear as `etherfi-catalog`
with these tools:

- `search_datasets`
- `search_dashboards`
- `get_dashboard_details`
- `get_dashboard_status`
- `get_catalog_health_summary`
- `plan_etherfi_query`
- `get_assets_under_management_balances`
- `get_cash_holdings_timeseries`
- `get_cash_safe_profile`
- `get_cash_token_totals`
- `get_top_cash_users`
- `get_protocol_token_tvl_timeseries`
- `diagnose_token_price_coverage`
- `find_price_tokens`
- `get_token_price`
- `get_token_prices_batch`
- `get_token_price_by_symbol`
- `get_dataset_details`
- `get_dataset_status`
- `list_stale_datasets`
- `compare_datasets`

Example query-planning prompts:

- "I need a live answer only: what are the latest balances for this ether.fi Cash address?"
- "Can you create a Dune query to show weekly USDC Cash spend volume?"
- "Plan a chart-ready query for monthly TVL for eETH and liquidETH over the last year."
- "Create a dashboard-ready query plan for Cash events by week."
- "Should I use protocol_token_holders or protocol_token_holders_with_defi for a top holders query?"

Use `plan_etherfi_query(...)` before creating new shareable Dune artifacts. It returns the recommended ether.fi dataset(s), caveats, filters, grain, metrics, starter SQL skeleton, visualization suggestion, short query/dashboard description suggestions, and next step. It does not create, execute, save, chart, or dashboard anything; use Dune MCP for those steps.

Example planning outputs to expect:

- "Create a Dune query for weekly USDC Cash spend volume." -> Cash events, `event_type='spend'`, `token_symbol='USDC'`, weekly grain, bar chart, concise Cash-event query description.
- "Show monthly TVL for eETH and liquidETH over the last year." -> protocol TVL time series, monthly grain, line chart with grouped-bar alternative, month-end snapshot description.
- "Create a query for the top 100 ether.fi protocol token holders today." -> holder datasets plus direct-vs-`with_defi` ambiguity, `identified_defi_contract` caveat, table or horizontal-bar recommendation.
- "Build a shareable dashboard view for monthly Cash balances by category." -> Cash AUM balances, `cash_balance_buckets` category preset, grouped/stacked bar guidance, dashboard description.
- "How much of liquidUSD is held in Aave?" -> AUM deployment footprint, `parent_symbol='liquidUSD'`, `token_project='Aave'`, net lending treatment using `secondary_trait`.

Example price workflow prompts:

- "What's the latest weETH price on BNB?"
- "Find likely liquidUSD tokens and get the latest daily price."
- "Price this basket of token addresses using daily enriched prices."
- "Why is this token missing from minute prices?"
- "Does this token have direct USD price coverage or only exchange-rate coverage?"

Example Cash workflow prompts:

- "Show me recent ether.fi Cash spend activity."
- "What are the latest balances for this ether.fi Cash address?"
- "What is the total balance of liquidUSD held by ether.fi Cash users?"
- "How many Cash users hold liquidUSD?"
- "Show me the average USD holdings of ether.fi Cash users over the last 30 days."
- "Aggregate ether.fi Cash balances by day for the last month."
- "Chart daily average Cash holdings for liquidUSD over the last 90 days."
- "Show the daily total and average USD balances for Cash users on Optimism."
- "Who are the top ether.fi Cash users right now?"
- "Summarize this Cash safe."
- "Is this address actually a Cash safe?"
- "What does user_safe mean in ether.fi Cash events?"

Example holder workflow prompts:

- "Who are the top eETH holders today?"
- "Show the top eETH holders including DeFi exposure."
- "Exclude identified DeFi contracts."
- "What does identified_defi_contract mean?"

Example protocol-event workflow prompts:

- "Show recent eETH protocol deposits."
- "Summarize withdrawal requests for liquidETH."
- "Show recent protocol activity for this strategy."
- "Should I filter protocol events by project or strategy_symbol?"

Example protocol-TVL workflow prompts:

- "What is the latest TVL of eETH?"
- "Compare eETH and liquidETH."
- "What backs liquidUSD?"
- "How much ETH backs liquidETH?"
- "Should I filter protocol TVL by project or strategy_symbol?"

Example protocol-TVL time-series workflow prompts:

- "Show me the TVL in USD for eETH, liquidETH, liquidUSD, eBTC, and liquidBTC over the last 1 year."
- "Chart ether.fi protocol token TVL by day for the last year."
- "Show daily TVL history for liquidETH and eETH over the last 90 days."
- "Compare liquidUSD vs eBTC TVL over time."
