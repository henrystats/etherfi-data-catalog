# ether.fi Data Catalog

A static data catalog and MCP server for ether.fi analytics datasets,
dashboards, freshness, and query-planning workflows. It helps teammates and AI
agents choose the right Dune-backed source, understand its caveats, and plan
safe, reviewable analysis.

## Live website

- Website: [https://henrystats.github.io/etherfi-data-catalog/](https://henrystats.github.io/etherfi-data-catalog/)
- GitHub Pages is built and deployed by
  [`.github/workflows/deploy-website.yml`](.github/workflows/deploy-website.yml)
  on pushes to `main` and manual workflow runs.

## What this repo provides

- Repo-backed metadata for ether.fi analytics datasets.
- A registry of Dune dashboards and their linked datasets.
- Freshness and status views based on imported Dune results.
- A generated static website for browsing the catalog.
- An MCP server for catalog discovery, dashboard lookup, freshness, query
  planning, and selected live Dune-backed workflows.
- An ether.fi workflow skill pack for coordinating the catalog with Dune MCP
  and Dune Skills.

## Who it is for

- ether.fi analysts and dashboard builders.
- GTM, finance, and product teammates working with ether.fi data.
- AI agents that use MCP for dataset discovery and query planning.
- Dune users who need trusted ether.fi semantics before writing or running SQL.

## Repository layout

```text
datasets/              Dataset metadata organized by subject area
dashboards/            Dashboard metadata organized by product
etherfi_catalog/       Python catalog library and MCP server
website/               Static website source and templates
scripts/               Website, freshness, and local utility scripts
skills/etherfi/        Agent workflow instructions and examples
docs/                   Detailed MCP deployment and SQL guidance
status/                 Local runtime freshness snapshot and example
tests/                  Catalog, MCP, workflow, and website tests
```

Top-level metadata is the source of truth for repo development. Installable
package mirrors live under `etherfi_catalog/data/`.

## Quick start

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

Run the MCP server locally over its default stdio transport:

```bash
.venv/bin/python -m etherfi_catalog.server
```

## MCP usage

The recommended public install is:

```bash
uvx --from "git+https://github.com/henrystats/etherfi-data-catalog.git" etherfi-catalog-mcp
```

The MCP server uses stdio by default. Metadata, discovery, freshness,
dashboard, and query-planning tools work without `DUNE_API_KEY`. Selected live
Dune-backed tools require `DUNE_API_KEY` in the MCP server environment when
called with `execute_live=true`; those calls may consume Dune credits.

See [MCP deployment and setup](docs/mcp_deployment.md) for client configuration,
local transport testing, secret handling, and advanced deployment notes.

## Recommended agent stack

- `etherfi-catalog` MCP: ether.fi dataset and tool selection, semantic caveats,
  freshness context, and query planning.
- Dune MCP: query execution, saved queries, results, visualizations, and
  dashboards.
- Dune Skills: Dune CLI, query-writing, optimization, and Dune-side workflow guidance for agents.
- `skills/etherfi/`: workflow instructions for combining the three layers.

Use `etherfi-catalog` to decide which ether.fi source and query shape are correct. Use Dune MCP to run, save, retrieve, visualize, and dashboard the Dune query.
For shareable charts and dashboards, confirm the catalog-vetted plan, then use Dune MCP visualization/dashboard tools.
Use Dune Skills for DuneSQL style, optimization, and Dune CLI guidance when needed.

## Website

Build the static site:

```bash
.venv/bin/python scripts/build_website.py
```

Preview the generated site at `http://localhost:8000`:

```bash
.venv/bin/python -m http.server 8000 --directory output/website
```

The build reads the repo metadata and writes `output/website`. Generated output
is ignored by git. The normal GitHub Pages workflow runs the website tests,
builds the site, uploads the generated directory, and deploys it without Dune
credentials.

## Freshness

Catalog freshness comes from
[Dune query 7625551](https://dune.com/queries/7625551). The importer pulls that
query's latest stored result; it does not execute the Dune SQL.

For a local refresh:

```bash
DUNE_API_KEY=... .venv/bin/python scripts/update_freshness_from_dune.py --query-id 7625551
```

The importer writes `status/dataset_freshness.yaml`. This file is a runtime
snapshot and remains gitignored; it is not source metadata. When it is absent,
the website still builds and reports unknown or undocumented runtime freshness.

The optional
[`refresh-freshness.yml`](.github/workflows/refresh-freshness.yml) workflow is
configured to run hourly or manually. With the repository's `DUNE_API_KEY`
secret, it imports the stored result, rebuilds the site, and deploys the
freshness-aware Pages artifact.

## Metadata conventions

- Dataset YAML files live under `datasets/`.
- Dashboard YAML files live under `dashboards/`.
- Packaged mirrors live under `etherfi_catalog/data/datasets/` and
  `etherfi_catalog/data/dashboards/`.
- Set `show_in_core: true` when a dashboard should also appear in the website's
  Core group; do not create a separate `dashboards/core/` directory.
- Keep runtime freshness snapshots out of version control.

Metadata should document the source table, grain, refresh cadence, accuracy,
completeness, caveats, important columns, and related resources where relevant.

## Testing

Before opening a pull request, run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/build_website.py
git diff --check
```

## Documentation

- [MCP deployment and setup](docs/mcp_deployment.md)
- [ether.fi SQL style and optimization guide](docs/sql_style_guide.md)
- [ether.fi agent workflow skill](skills/etherfi/SKILL.md)

## Project boundaries

`etherfi-catalog` is the ether.fi semantic catalog and planning layer, not a
general-purpose Dune client. Use it for source selection, caveats, freshness,
and safe query planning. Use Dune MCP for execution, saved queries,
visualizations, and dashboard creation.
