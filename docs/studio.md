# Studio architecture and data workflow

Studio is the repository's static analytics workspace. It shares the generated
site shell, theme, build, and GitHub Pages deployment, but its dashboard and
metric registries are independent from the dataset catalog, MCP server,
freshness registry, and legacy dashboard registry.

The checked-in dashboards are development products:

- `/studio/kyberswap/` is a campaign dashboard backed by a validated snapshot
  of reviewed latest stored query results. Its eight counters share Dune query
  8180894; its current-location
  ranking and two Sankeys share Dune query 8199058; its signed post-referral
  activity chart uses Dune query 8202133; and its six Campaign Growth & Activity
  charts use four reviewed read-only sources. Its depositor tables and wallet
  investigation also use reviewed latest-result sources.
- `/studio/` is the generated dashboard selector.

Queries `8180894`, `8191379`, `8191704`,
`8193003`, `8193040`, `8199058`, `8202133`, `8204345`, and `8204373` are the
reviewed read-only sources in the current rollout. The browser never calls Dune
and never receives a Dune API key.

## System map

```text
studio/
  dashboards.yaml                 Dashboard identity, routes, sections, defaults
  metrics.yaml                    Metric presentation and query/column contracts
  query_inventory.json            Generated registry/query inventory
  data/
    kyberswap.json                Deterministic invented sample data
  fixtures/
    query_8199058.json            Offline raw-source fixture for attribution
    query_8180894.json            Offline raw-source fixture for summary counters
    query_8191379.json            Offline raw-source fixture for referral deposits
    query_8191704.json            Offline raw-source fixture for attributed TVL
    query_8193003.json            Offline raw-source fixture for deposit breakdowns
    query_8193040.json            Offline raw-source fixture for activity counts
    query_8202133.json            Offline raw-source fixture for signed activity
    query_8204345.json            Offline raw-source fixture for referral deposits
    query_8204373.json            Offline raw-source fixture for activity events
    scenarios.yaml                Offline ingestion behavior scenarios
    README.md                     Fixture design notes
scripts/
  enrich_kyberswap_attributed_holdings.py
                                  Decimal attribution and reconciliation
  prepare_kyberswap_campaign_summary.py
                                  Counter-result validation and provenance
  enrich_kyberswap_growth.py      Growth validation and deterministic prepared views
  studio.py                       Registry, generated-data, and page validation
  studio_ingestion.py             Fetch, normalize, validate, snapshot, promote
  fetch_studio_data.py            Refresh/validation CLI
  generate_studio_demo_data.py    Deterministic KyberSwap sample-data generator
  generate_studio_inventory.py    JSON and Markdown inventory generator
  build_website.py                Static-site integration
website/data/studio/generated/
  manifest.json                   Empty bootstrap, or legacy flat snapshot
  state.json                      Active snapshot pointer after a refresh
  snapshots/<snapshot-id>/
    manifest.json                 Immutable validated snapshot manifest
    query_<query-id>.json         One normalized result per unique query
    raw_query_8199058.json         Private raw source sidecar (not published)
    raw_query_8180894.json         Private raw source sidecar (not published)
    raw_query_8191379.json         Private raw referral-deposits sidecar
    raw_query_8191704.json         Private raw attributed-TVL sidecar
    raw_query_8193003.json         Private raw deposit-breakdown sidecar
    raw_query_8193040.json         Private raw activity-count sidecar
    raw_query_8202133.json         Private raw signed-activity sidecar
    raw_query_8204345.json         Private raw referral-deposit sidecar
    raw_query_8204373.json         Private raw activity-event sidecar
  attempts/<attempt-id>/
    attempt.json                  Success, unchanged, partial, or failure audit
output/website/data/studio/generated/
  manifest.json                   Flattened active public manifest
  query_<query-id>.json           Flattened active public results
  refresh_status.json             Sanitized state summary when state exists
website/assets/
  studio.css
  studio.js
  studio-landing.js
  vendor/echarts.min.js
docs/
  studio-query-inventory.md       Generated human-readable inventory
.github/workflows/
  studio-fixture-refresh.yml      Manual, offline, non-deploying fixture check
  deploy-website.yml              Push-only production entry point
  studio-live-refresh.yml         Manual + four-hour production entry point
  studio-production-deploy.yml    Shared live ingest/build/Pages deployment
  refresh-freshness.yml           Catalog-freshness validation artifact only
```

The main flow is:

```text
dashboard + metric registries
          |
          +--> inventory generator --> query_inventory.json + Markdown
          |
          +--> refresh CLI --> route fixture/latest-result provider explicitly
                                --> fetch_latest_result once per unique query
                                --> preserve private raw source where configured
                                --> Decimal enrichment and reconciliation
                                --> build validated cross-query derived artifacts
                                --> normalize and validate in staging
                                --> stamp dashboard_refreshed_at at acceptance
                                --> immutable snapshot + atomic state pointer
          |
          +--> website build --> resolve active snapshot
                                 --> flatten public manifest/query/status files
                                 --> generated HTML/CSS/JS site
```

Production has two thin workflow files but three trigger paths and only one
implementation. A push to `main` enters through `deploy-website.yml`; manual
and four-hour scheduled live refreshes enter through `studio-live-refresh.yml`.
All three call the reusable, `workflow_call`-only
`studio-production-deploy.yml`, which owns the secret check, read-only import,
validation, tests, build, Pages artifact, and deployment. The cron
`25 */4 * * *` runs at approximately 00:25, 04:25, 08:25, 12:25, 16:25, and
20:25 UTC; it schedules only this importer, never a Dune query execution.

The production provider flow is deliberately one-way and read-only:

```text
Dune's independent query schedule --> latest stored result
                                          |
GitHub Action --> GET /api/v1/query/{query_id}/results
              --> validate execution metadata, freshness, columns, and rows
              --> write/promote Studio snapshot --> build and deploy website
```

Studio owns only `fetch_latest_result`; Dune owns query execution and its
schedule. In SDK terms the allowed operation is
`dune.get_latest_result(query_id)`. An abstraction named `execute_query` would
be outside the Studio ingestion boundary.

`scripts/studio.py` is the shared contract boundary. Inventory generation uses
configuration-only validation, ingestion validates the query contracts and
candidate snapshot, and the website build validates the active data again
before publishing it.

### Current KyberSwap Depositor Analysis boundary

[Dune query 8199058](https://dune.com/queries/8199058) is mapped to exactly
one enriched result that is reused by the capital-position views and Depositor
Intelligence:

| Studio metric | View or stages | Value |
|---|---|---|
| Attributed TVL by Current Location | `current_token` or `current_token_category` ranking | `attributed_balance` |
| Attributed Funds by Current Location Sankey | `strategy_symbol` → `current_token` | `attributed_balance` |
| Depositor Journey Sankey | `depositor_type` → `strategy_symbol` → `current_token_category` | `attributed_balance` |
| Top Referred Depositors | address summary | deduplicated `referral_balance` |
| Referral Deposit Concentration | cumulative address tiers | referral deposits or active attributed TVL |
| Top Depositors | address summary | deposits, active TVL, exits, retention, products, and locations |
| Wallet Investigation | indexed wallet positions | enriched position records |

Ingestion starts one logical fetch for query 8199058 per refresh and reuses the
single enriched result for all three metrics. Read-only pagination may use
multiple GET pages inside that logical fetch. The ranking defaults to Protocol
(`current_token`) and can switch locally to Category
(`current_token_category`) without another Dune request. The first Sankey
includes a synthetic `Exited` token
when the referral-attributed amount no longer has a supported current balance.
The second includes `Exited` as a destination category and uses
`Uncategorized` for a non-empty source position whose category is missing.

The first Sankey applies a presentation-only destination rollup configured in
the metric registry: it retains the five largest active `current_token`
destinations, groups the remaining active destinations into `Others`, and
always preserves `Exited` as a separate destination. Links are re-aggregated by
source and visible destination without changing the conserved total. The
underlying enriched rows and CSV export keep every individual destination.
The current-location ranking similarly keeps the six largest active categories,
groups the remaining active value into `Others`, and preserves `Exited`
separately. This grouping is presentation-only and the underlying export rows
remain ungrouped.

Two additional latest-result sources complete the same atomic candidate:

| Query | Grain | Validation and use |
|---|---|---|
| [8204345](https://dune.com/queries/8204345) | one KyberSwap referral deposit event | Validates EVM address and transaction identifiers, known chains, timestamps, product, and finite non-negative USD; powers recent deposits and per-wallet deposit history. |
| [8204373](https://dune.com/queries/8204373) | one later ether.fi activity event by a referred wallet | Validates identifiers, known chains, timestamps, event/project/label, and finite signed USD; powers recent activity and per-wallet activity history. Negative values remain negative. |

After all three normalized query artifacts are available, Python builds
`kyberswap_depositor_intelligence.json` once. It counts `referral_balance` once
per lowercase address and `strategy_symbol`, sums active `attributed_balance`
without synthetic `Exited` rows, keeps exit value separately, and joins latest
deposit/activity fields. Each wallet contains its pre-indexed position, deposit,
and activity rows; `wallet_index` maps a lowercase address to its deterministic
offset in the wallet list. Concentration tiers and all wallet-facing components
reuse this one address summary rather than independently recomputing totals.

The derived artifact records the three source query IDs and execution metadata,
is checksummed in the snapshot manifest, and is validated before the atomic
state pointer moves. A missing, malformed, stale-policy failure, or
non-reconciling required source leaves the previous complete snapshot active.
The public browser only reads the promoted artifact and never joins live Dune
responses or initiates an execution.

### Current KyberSwap query 8202133 boundary

[Dune query 8202133](https://dune.com/queries/8202133) powers the
**Post-Referral Activity** signed stacked bar chart. Its source columns are
`day`, `week`, `project`, `event`, `label`, and signed `amount_usd`. Python
prepares deterministic daily and weekly sums for Label, Project, and Event;
Weekly and Project are the browser defaults. Positive values remain positive,
negative withdrawals remain negative, and the browser switches among prepared
views without refetching Dune. The raw result is preserved once in
`raw_query_8202133.json`, and promotion requires the prepared grouping totals to
reconcile with the source totals.

Within the active dashboard period and selected grouping, the browser ranks
categories by the sum of absolute activity magnitude, displays the largest six,
and aggregates every remaining category into one signed `Others` series per
period. Only ranking uses magnitude: displayed and exported monetary values
retain their original signs, visible totals reconcile exactly, and the chart
recomputes locally when the period or grouping changes.

### Current KyberSwap query 8180894 boundary

[Dune query 8180894](https://dune.com/queries/8180894) is the single source for
all eight campaign-summary counters. One read-only latest-result fetch is
preserved in `raw_query_8180894.json`, validated once, transformed once, and
reused by these field mappings:

| Counter | Source field |
|---|---|
| Total Referral Deposits | `total_deposits_usd` |
| Attributed TVL | `outstanding_balance_usd` |
| Referred Deposits by New Depositors | `deposits_by_new_depositors` |
| % Deposits by New Depositors | `depositors_new_users_rate` |
| Total Depositors | `num_depositors` |
| New Depositors | `new_depositors` |
| Retention Rate | `retention_rate` |
| Revenue Generated | `revenue_generated` |

Dashboard periods select rows through the registry's explicit `key_` mapping:
`7D` → `7d_data`, `30D` → `30d_data`, `90D` → `90d_data`, `YTD` →
`ytd_data`, `1Y` → `1y_data`, and `ALL` → `all_time_data`. Period switching
reuses the loaded result and never refetches Dune. During the current
development phase, an absent period row or numeric value renders as a
formatted zero and records a concise developer warning; it does not mutate the
stored raw result. Duplicate, contradictory, or otherwise structurally invalid
rows fail validation and leave the previous valid snapshot active.

The eight cards share one methodology action and one selected-period CSV. The
export aliases `key_` to `period` and the misleading source name
`depositors_new_users_rate` to `deposits_by_new_depositors_rate`; the raw source
column remains unchanged.

### Current KyberSwap Campaign Growth & Activity boundary

Four latest stored results power six charts:

| Query | Prepared charts | Python behavior |
|---|---|---|
| [8191379](https://dune.com/queries/8191379) | Referral Deposits | Daily values remain daily. Weekly columns and the cumulative line use the latest available day in each week; repeated `weekly_deposits_usd` values are never summed. |
| [8191704](https://dune.com/queries/8191704) | Attributed TVL Over Time | All validates one repeated cumulative TVL per day. Depositor Type keeps dynamic type series. Weekly TVL selects the latest observation rather than summing balances. |
| [8193003](https://dune.com/queries/8193003) | Referral Deposits Breakdown; Total Referral Deposits Breakdown | Daily flows aggregate by product and depositor type. Weekly flows are summed. The total ranking aggregates filtered daily rows inside the active dashboard period. |
| [8193040](https://dune.com/queries/8193040) | Deposit & Depositor Count by Product; Deposit & Depositor Count by Depositor Type | Source-provided `day` and `week` grains remain separate and are selected by `timestamp_type`; weekly rows are not reconstructed from daily rows. |

`scripts/enrich_kyberswap_growth.py` validates each source independently and
emits deterministic record types for the browser's daily/weekly, grouping, and
metric controls. Each query is fetched and transformed once per ingestion run,
even when two charts reuse it. The exact raw source is preserved in one private
`raw_query_<query-id>.json` sidecar and is never published with the website.

The dashboard period filters prepared dates before display. Chart controls
select already-prepared record types and never call Dune. Each chart has its own
Methodology action and selected-view CSV; the combo chart always keeps columns
and its cumulative line together.

The generic `growth_chart` contract keeps range and export behavior explicit.
`range_date_column: observation_day` makes the two latest-observation weekly
charts compare the active range against the underlying observation rather than
the Monday bucket label. `rebuild_weekly_from_daily: true` makes the deposit
breakdown filter daily source rows before forming weekly groups, so a boundary
week contains only in-range activity. A measure's `stack: true` stacks column
and area presentations but never a line alternative. `export_columns` declares
stable user-facing CSV headers; the validated `export_aliases` mapping resolves
those headers from the rendered model (`period`, `granularity`, selected view,
dimension, and primary/secondary values), while `export_constants` supplies a
fixed category type where a chart owns one category family. These operations
reuse the loaded prepared rows and cannot initiate a query execution.

All KyberSwap registry mappings now use reviewed `latest_result` sources. Demo
fixtures remain available for offline validation, but production live mode does
not substitute fixture rows or send placeholder query IDs to Dune.

## Dashboard registry contract

Each `studio/dashboards.yaml` entry defines:

- identity and route: `id`, `slug`, `name`, `short_name`, `display_order`;
- presentation: `eyebrow`, `description`, `audience`, and ordered `sections`;
- state: `status`, `freshness_status`, and `freshness_note`;
- data: `data_mode`, `data_file`, and `default_date_range`;
- optional lineage: `dune_url`;
- optional freshness thresholds: `freshness_policy`.

`data_mode` is `demo` or `generated`; omission normalizes to `demo`. Demo mode
loads a checked-in file from `studio/data/`. Generated mode requires a complete
validated query snapshot. It never silently falls back to demo values.

Every section needs a unique `id`, a display `label`, and a `description`.
Dashboard IDs, slugs, section IDs, and per-dashboard metric ordering are
validated before pages are written.

## Metric and query contract

Each `studio/metrics.yaml` entry belongs to one dashboard and one declared
section. Its main fields are:

- identity and ordering: `id`, `dashboard_id`, `section`, `name`,
  `description`, `display_order`, `size`;
- presentation: `visualization_type`, `default_visualization`,
  `allowed_visualizations`, `format`/`value_format`, `default_visible`;
- query lineage: `query_id`, `query_url`, `data_file`, `data_source`, and
  optional `source_label` and `provider_mode`;
- column contract: `columns`, `optional_columns`, `dimension_columns`, and
  `value_columns`;
- optional enrichment lineage: `transformation` (ID/version, methodology ID,
  script/test/fixture paths, raw sidecar name, and source-column contract) and
  structured `methodology` content;
- visualization mappings such as `date_column`, `series`, `category_column`,
  `value_column`, `source_column`, `target_column`, `stage_columns`, optional
  `exit_value_column`, counter `period_key_column`/`period_key_map`, Sankey
  destination aggregation, and table column metadata;
- identity mappings: `chain_column`, `address_columns`, and
  `transaction_columns`;
- supporting data: `comparison_column`, `sparkline_data_source`,
  `sparkline_date_column`, and `sparkline_column`;
- behavior: `is_exportable`, `allow_empty`, optional `freshness_policy`, and
  optional shared-section methodology/export actions.

`value_format` is a clearer alias for the existing `format` field. If both are
set, they must match. Line metrics may allow `line`, `area`, `column`, and/or
`scatter` views; changing the view is presentation-only and does not refetch or
mutate rows. A generic `growth_chart` mapping declares prepared record types,
daily/weekly defaults, range-date behavior, grouping views, measures, axes,
weekly reconstruction rules, and validated selected-view export aliases.

`provider_mode` is `fixture` or `latest_result`. It is part of the reviewed
query contract, not a runtime guess. All queries in the current registry —
8180894, 8191379, 8191704, 8193003, 8193040, 8199058, 8202133, 8204345, and
8204373 — are `latest_result`.
Metrics that share a query must agree on provider and transformation metadata.

`columns` is the required, metric-scoped projection and is also the CSV export
projection. `optional_columns` may be present in a result but are not required.
`dimension_columns` and `value_columns` identify semantic roles and must refer
to declared required or optional columns without overlapping each other.
Comparison and visualization dependencies are promoted to the query's required
column union. `allow_empty` defaults to false for exportable metrics and true
for non-exportable metrics when it is omitted.

The freshness policy supports positive hour thresholds:

```yaml
freshness_policy:
  expected_refresh_hours: 24
  warning_after_hours: 36
  stale_after_hours: 72
```

Thresholds must be nondecreasing. A metric policy overrides dashboard fields;
when several metrics share a query, ingestion uses the strictest effective
thresholds.

`query_url` normalizes to `https://dune.com/queries/<query_id>` and `data_file`
normalizes to `query_<query_id>.json`. Explicit values must agree with the ID.
Unsafe names, conflicting source mappings, undeclared visualization columns,
duplicate IDs/orders, and inconsistent shared-query contracts fail validation.

### One fetch, many metrics

`query_id` identifies lineage, `data_file` identifies the normalized result,
and `columns` selects what one metric owns. Multiple metrics can reuse a result:

```yaml
- id: kyber_total_referral_deposits
  query_id: 8180894
  data_file: query_8180894.json
  data_source: kyberswap_campaign_summary
  value_column: total_deposits_usd

- id: kyber_attributed_tvl
  query_id: 8180894
  data_file: query_8180894.json
  data_source: kyberswap_campaign_summary
  value_column: outstanding_balance_usd
```

Ingestion deduplicates the registry into one request per query ID. The browser
also caches file loads by path. A counter may consume a second query through a
sparkline mapping; the inventory records that dependency as a separate
`sparkline` source role while the counter CSV remains limited to its primary
`columns`.

For reviewed production queries, deduplication also happens before
transformation: each raw stored result is preserved and transformed once. The
current-location ranking and both Sankeys consume one 8199058 artifact, the
post-referral chart consumes one 8202133 artifact, all eight counters consume
one 8180894 artifact, and the six growth charts consume one artifact for each
of 8191379, 8191704, 8193003, and 8193040. Metric projections, period changes,
grouping controls, and chart styles do not cause additional Dune requests or
transforms.

## Query-to-metric inventory

Run:

```bash
.venv/bin/python scripts/generate_studio_inventory.py
.venv/bin/python scripts/generate_studio_inventory.py --check
```

The first command deterministically writes:

```text
studio/query_inventory.json
docs/studio-query-inventory.md
```

The JSON schema records a registry checksum, dashboard/metric/unique-query
counts, display and section ordering, presentation defaults, source labels,
required/optional/dimension/value columns, freshness policy, and every primary
or supporting source mapping. Its deduplicated query plan contains the union of
required and optional columns, consuming dashboards/metrics/data sources, and
source roles.

The Markdown inventory renders one row per source dependency, then a unique
query fetch plan. Regenerate these files instead of editing them by hand.

Inventory generation deliberately calls registry validation with generated
data checks disabled. This breaks an otherwise circular onboarding dependency:
a reviewer can add a new query mapping, regenerate and review the inventory,
and only then produce the first matching snapshot. Ingestion and website builds
still require full generated-data validation where generated data is consumed.

## Refresh CLI

The supported entry point is `scripts/fetch_studio_data.py`. With no mode flag,
it attempts live mode, but live mode is blocked by two explicit environment
gates. Fixture mode is the safe default for development and CI.

### Offline fixture refresh

```bash
.venv/bin/python scripts/fetch_studio_data.py \
  --fixture-mode \
  --fixture-scenario success \
  --fixture-now 2026-07-31T12:00:00Z \
  --output-dir /tmp/studio-fixture-generated \
  --keep-previous 1 \
  --verbose

.venv/bin/python scripts/fetch_studio_data.py \
  --validate-only \
  --output-dir /tmp/studio-fixture-generated
.venv/bin/python scripts/build_website.py \
  --studio-generated-data /tmp/studio-fixture-generated
```

`--validate-only` always validates the registry. When `state.json` points to an
active snapshot, it validates that complete snapshot too; with only the empty
bootstrap manifest it reports `active_snapshot: false` without manufacturing
data.

Fixture mode uses the checked-in raw query fixtures and
`studio/fixtures/scenarios.yaml`. It does not need network access or
`DUNE_API_KEY`. Named scenarios cover:

```text
success, previous_valid_snapshot, empty_result, missing_required_column,
additional_unexpected_column, reordered_columns, malformed_row,
duplicate_rows, null_values, large_numeric_string, multiple_chains,
invalid_date, rate_limited_once, timeout_once, query_execution_failed,
partial_refresh, row_count_mismatch
```

The `query_execution_failed` fixture represents Studio observing that the most
recent Dune-side run had already failed. It does not model Studio submitting,
owning, polling, retrying, or otherwise initiating that execution. Execution
metadata in any fixture is provider history, not an action taken by Studio.

Use an isolated `--output-dir` under `/tmp` when testing destructive or failure
scenarios manually. Fixture values remain invented and must not be presented as
live analytics.

An unfiltered refresh includes only queries required by dashboards whose
`data_mode` is `generated`. Explicit fixture filters may refine or extend a
same-mode current snapshot; live mode rejects fixture-backed generated
mappings.

### Live latest-result refresh

For the current KyberSwap registry, queries 8180894, 8191379, 8191704, 8193003,
8193040, 8199058, 8202133, 8204345, and 8204373 are all `latest_result` sources
and are each imported once from Dune. Keep the checked-in snapshot unchanged:
seed an isolated temporary root from it, load a local gitignored `.env` without
printing its contents, and enable the two live gates:

```bash
STUDIO_LIVE_ROOT="$(mktemp -d)"
STUDIO_LIVE_GENERATED="$STUDIO_LIVE_ROOT/studio-live-generated"
mkdir -p "$STUDIO_LIVE_GENERATED"
cp -R website/data/studio/generated/. "$STUDIO_LIVE_GENERATED/"
set -a
source .env
set +a
STUDIO_ENABLE_LIVE_DUNE=1 \
  .venv/bin/python scripts/fetch_studio_data.py \
  --output-dir "$STUDIO_LIVE_GENERATED" \
  --keep-previous 1 \
  --verbose
.venv/bin/python scripts/fetch_studio_data.py \
  --validate-only \
  --output-dir "$STUDIO_LIVE_GENERATED"
.venv/bin/python scripts/build_website.py \
  --studio-generated-data "$STUDIO_LIVE_GENERATED"
```

The first command is the exact live ingestion CLI used by production, with the
runner's temporary path substituted for `STUDIO_LIVE_GENERATED`. The validation
and build commands consume that same promoted root explicitly. The resulting
manifest records each query's actual `source_mode`. Plain live mode rejects any
future fixture-backed generated mapping rather than querying an unapproved ID.
`--fixture-mode` remains fully offline. The separate `--mixed-source-mode`
option is an explicit development tool for a deliberately mixed registry; the
current KyberSwap workflow does not use it.

### Filtered and partial refreshes

Repeat `--query-id <id>` or `--dashboard <dashboard-id>` to narrow a refresh.
A filtered refresh requires an existing complete current snapshot, because
unselected queries are copied from it before the new complete candidate is
validated. Unknown or empty selections fail.

The default is fail-closed: any selected-query failure preserves the current
snapshot and returns a nonzero status. `--allow-partial` is an explicit recovery
mode that may reuse the previous validated result for a failed query. The state
and attempt records identify that the previous data is in use; a partial result
is never described as a fresh full success.

`--keep-previous [COUNT]` controls retained older snapshots and defaults to one.
`--force` promotes a snapshot even when normalized content is unchanged.
`--timeout`, `--max-attempts`, and `--backoff` control provider
requests and retry behavior.

### Explicit production read-only import

Production read-only mode requires both gates in the server-side process. The
shared workflow supplies the secret only to the read-only import steps and uses
the seeded runner-temporary output root:

```bash
STUDIO_ENABLE_LIVE_DUNE=1 \
python scripts/fetch_studio_data.py \
  --output-dir "$RUNNER_TEMP/studio-live-generated" \
  --keep-previous 1 \
  --force \
  --verbose
python scripts/fetch_studio_data.py \
  --validate-only \
  --output-dir "$RUNNER_TEMP/studio-live-generated"
python scripts/build_website.py \
  --studio-generated-data "$RUNNER_TEMP/studio-live-generated"
```

Do not put the key in registries, generated JSON, logs, browser assets, Pages
artifacts, shell history, or committed workflow files. The adapter sends it only
as the `X-Dune-API-Key` request header. Provision the production key with read
access only; Studio needs no permission to create, edit, execute, cancel, or
refresh queries. Configure it at **GitHub repository → Settings → Secrets and
variables → Actions → New repository secret**, with the name `DUNE_API_KEY`.
An absent secret fails the production job before ingestion, artifact upload, or
deployment; it never silently substitutes fixture data.

The production client implements one logical `fetch_latest_result(query_id)`
operation per unique query ID per GitHub Action run. That operation reads only:

```text
GET /api/v1/query/{query_id}/results
```

If the official Python SDK is used instead, the equivalent allowed call is:

```python
dune.get_latest_result(query_id)
```

Each unique query starts one logical latest-result import per run. That import
may require multiple GET requests through `next_uri` or `next_offset`, or a
bounded retry after a transient GET failure; none of those requests starts a
new execution.
Pagination URLs must stay on the configured API origin and result path. Every
page must retain the same Dune execution ID, the first page must declare the
complete row count, and any repeated count must remain consistent. The one
normalized result is cached for the run and reused by every primary or
supporting Studio metric mapped to that query ID.

Studio must never call `run_query`, `run_query_dataframe`, an execute-query or
execute-SQL/pipeline operation, a materialized-view refresh, or
`POST /query/{query_id}/execute`. It must not pass `max_age_hours` or enable any
SDK option that automatically reruns stale queries. A failed or stale stored
result never changes this rule.

For each successful stored result, Studio records the latest Dune execution ID
and execution completion timestamp and compares that provider timestamp with
the configured freshness policy. A stale result is marked `stale`; it is not
rerun. Failed, pending, missing, mixed, truncated, or looping responses fail
closed. If no successful stored result is available, the previous validated
Studio snapshot remains active and the attempt records the failure, including
the provider execution ID/completion time when Dune returned them. The
built-in HTTP transport also refuses redirects so the API-key header cannot be
forwarded to another origin.

The Dune execution completion time, `execution_*`, and `data_updated_at`
metadata describe provider history. The time the local CLI checked Dune is not
the time the underlying query ran or its data changed.

## Query 8199058 raw preservation and Decimal enrichment

Query 8199058 has a two-part contract. The read-only provider result must
contain exactly these source columns:

```text
day, address, strategy_symbol, base_asset, depositor_type, current_token,
current_token_category, referral_balance, current_balance, previous_balance
```

All three monetary values are already USD. There is no price column and no
currency conversion step. The stored execution completion timestamp supplies
`source_last_updated`. The raw provider rows, their column order, and source
execution metadata are preserved in `raw_query_8199058.json` before enrichment.
That sidecar is stored only inside the private immutable snapshot. It is
validated and carried across previous-snapshot fallback, but the website
publisher does not copy it into `output/website`.

The Python transformation
`scripts/enrich_kyberswap_attributed_holdings.py` uses exact `Decimal`
arithmetic. It never executes SQL and has no Dune client. Source rows have the
grain `(day, address, strategy_symbol, current_token)` and must describe one
latest snapshot day. Attribution groups use
`(day, address, strategy_symbol)`; repeated referral caps, prior balances,
base assets, and depositor types must agree within the group.
The source's `New Depositor`, `Existing Depositor`, and `Past Depositor`
classifications are retained verbatim for the journey Sankey. Any additional
non-empty classification is retained with a data-quality warning; it does not
change balance allocation.

For each group, the methodology calculates:

```text
total_current_balance = sum(max(current_balance, 0)) for non-Empty tokens
campaign_supported_balance = max(total_current_balance - previous_balance, 0)
final_attributable_balance = min(referral_balance, campaign_supported_balance)
exited_balance = referral_balance - final_attributable_balance
```

Active destinations are then allocated deterministically under methodology
`kyberswap_attributed_holdings_v1`:

1. **Rule A — no current attributable balance:** allocate zero when the final
   attributable balance is zero.
2. **Rule B — current positions fit:** when total current balance does not
   exceed the attributable amount, attribute each current balance in full.
3. **Rule C — largest balance first:** when no destination alone reaches the
   attributable cap, allocate in descending current-balance order.
4. **Rule D — preserve smaller destinations:** when exactly one destination
   reaches the cap, allocate the smaller destinations first, then give the
   oversized destination the remainder.
5. **Rule E — multiple destinations reach the cap:** give the cap to the
   highest-ranked destination.

Balance-order ties use `current_token` ascending, so output does not depend on
provider row order. Existing pre-referral holdings are excluded once per
wallet/product group through `previous_balance`, and active attribution cannot
exceed either the referral cap or a destination's current balance. A synthetic
`Exited` row carries any remaining referral balance. A source `Empty` token
must have a null category; it represents no current destination and may not
carry a materially positive current balance. Non-empty destinations with a
missing category become `Uncategorized` and emit a warning. Negative current
balances are invalid.

The transformation keeps the source USD balances directly—without redundant
converted-value aliases—and records `methodology_id`, source query ID, source execution ID,
`source_last_updated`, transformation generation time, transformation-script
checksum, summary totals, and warnings. Snapshot promotion requires exact
zero-tolerance reconciliation:

```text
per group: active attributed balance + exited balance = referral_balance
per group: sum(destination allocations) = final_attributable_balance
global: active attributed balance + exited balance = referral balance
Sankey 1 total = Sankey 2 stage-one total = Sankey 2 stage-two total
```

Any invalid group or failed reconciliation is a transformation failure. It
cannot trigger a Dune execution; the previous validated Studio snapshot stays
active.

## Query 8180894 raw preservation and counter validation

Query 8180894 follows the same read-only preservation boundary. Its latest
stored result is written unchanged to `raw_query_8180894.json` before
`scripts/prepare_kyberswap_campaign_summary.py` validates and annotates the
published rows. The source contract is:

```text
rank_, key_, total_deposits_usd, outstanding_balance_usd, num_depositors,
new_depositors, deposits_by_new_depositors, retention_rate,
depositors_new_users_rate, revenue_generated
```

The transformation accepts multiple period rows but requires a non-empty,
well-formed, unique `key_` per row. It rejects duplicate keys, missing
structural fields, invalid numeric shapes, negative deposit amounts or user
counts, rates outside `[0, 1]`, outstanding balance above deposits, and
new-depositor deposits above total deposits. It appends source execution,
source completion, and transformation timestamps without rewriting source
field names or values in the private raw sidecar.

Missing period rows and missing individual counter values are a temporary
browser presentation fallback only: the affected counter displays zero and a
developer warning identifies the period, field, and metric. A serious source
validation failure cannot trigger a Dune execution and cannot replace the
active validated snapshot.

## Normalization and validation

Each unique result passes the same normalization pipeline before it reaches a
snapshot:

1. Verify query identity, terminal status, declared columns, complete row
   count, and required columns.
2. Reject a partial payload and reject an empty result when the shared contract
   does not allow empty output.
3. Order columns deterministically: required columns first, returned optional
   columns next, then unexpected provider columns sorted by name.
4. Preserve provider row order, duplicate rows, nulls, non-value booleans, and
   numeric strings. The live JSON decoder preserves decimal lexemes and integer
   literals outside JavaScript's safe range as strings; custom-client unsafe
   integers are serialized the same way. Configured value columns must have a
   finite numeric shape, but the pipeline does not infer financial conversions
   or coerce precise financial values into lossy browser numbers.
5. Require every row to contain every emitted column and require each value to
   be a finite JSON scalar.
6. Validate configured ISO date/timestamp, EVM address, and EVM transaction
   fields, plus provider timestamp chronology and future-clock bounds.
7. Record duplicate and unexpected-column counts instead of silently dropping
   data.
8. Hash canonical `{columns, rows}` content and the exact result-file bytes.

Only rate limiting, timeouts, and network errors are retryable. Authentication,
latest-result request failures, unavailable or previously failed queries,
malformed responses, missing columns, partial/empty contract violations,
invalid rows/values/dates, and write/manifest failures fail immediately. Retry
delay uses `Retry-After` when available, otherwise bounded exponential backoff.
Delta-seconds and HTTP-date forms are accepted; invalid or unbounded values
cannot bypass the configured maximum delay.

## Immutable snapshots and atomic promotion

After a refresh, the source tree is:

```text
<generated-root>/
  state.json
  snapshots/
    <current-id>/
      manifest.json
      query_<id>.json
    <previous-id>/
      manifest.json
      query_<id>.json
  attempts/
    <attempt-id>/attempt.json
```

For a local production-equivalent run, `<generated-root>` is the isolated
`STUDIO_LIVE_GENERATED` path shown above. In Actions it is
`$RUNNER_TEMP/studio-live-generated`. The shared workflow seeds that directory
from the checked-in `website/data/studio/generated/` previous-good snapshot,
then writes only to the temporary copy. It never commits or uploads the private
snapshot tree as the Pages artifact.

Promotion is transactional:

1. Acquire an output-root-specific cross-process lock, fetch the latest stored
   result once for every selected unique query, and merge validated reused
   queries.
2. Normalize the complete candidate in a temporary directory under
   `snapshots/`.
3. Validate manifest/query agreement, registry contracts, content checksums,
   file checksums, source checksum, and manifest checksum.
4. Stamp `dashboard_refreshed_at`, recompute the manifest checksum, and
   revalidate the accepted candidate.
5. Rename the validated directory to its immutable snapshot ID.
6. Atomically replace `state.json` so readers switch to the new snapshot in one
   operation.
7. Retain the configured number of older snapshots while protecting the exact
   `previous_snapshot_id`; retention cleanup is best-effort after promotion.

Fetch or validation failure writes an attempt and failure state while preserving
the active snapshot. A reader never observes a half-written promoted directory.
Snapshot IDs contain mode, UTC refresh time, and a checksum prefix. In
production, any import, transformation, validation, test, or build failure
stops before Pages artifact upload and deployment. The already-deployed site is
therefore the true previous-good production fallback; the runner must not
publish its older checked-in seed over a newer live deployment.

When normalized content and latest-result metadata match the active snapshot,
the CLI records an `unchanged` attempt and updates `last_checked_at` and
`last_successful_fetch_at` without rewriting immutable files unless `--force`
is used. A new provider execution ID or completion timestamp is promoted even
when its rows are identical, so the public snapshot always identifies the
latest scheduled Dune run. In that metadata-only case, `data_changed_at` stays
stable and the content-based `changed_query_ids` remains empty.

## Persisted contracts

`state.json` schema version 2 is the mutable pointer and latest health summary.
It records:

```text
current_snapshot_id, previous_snapshot_id, current_manifest_checksum,
updated_at, last_checked_at, last_successful_fetch_at,
latest_attempt_id, latest_attempt_status, using_previous, latest_failure
```

Failed and unchanged updates preserve applicable existing success timestamps.
`using_previous` plus `latest_failure.failed_query_ids`, categories, and summary
make fallback explicit. A promoted partial snapshot preserves the prior
complete `last_successful_fetch_at`; only failed/reused query sources are marked
as previous in the browser, while the dashboard reports a mixed partial state.

Each `attempts/<id>/attempt.json` uses ingestion schema version 2 and records the
mode, checked time, status, selected IDs, candidate/active snapshot where
applicable, changed/reused IDs, failures, and source checksum. Attempts are
diagnostic records and are not browser data.

Each immutable `manifest.json` contains:

```text
schema_version, ingestion_schema_version, ingestion_tool_version,
snapshot_id, previous_snapshot_id, generated_at, dashboard_refreshed_at,
display_updated_at,
data_updated_at, last_checked_at, last_successful_fetch_at,
source, mode, validation_status,
dashboard_count, metric_count, unique_query_count,
changed_query_ids, reused_query_ids, source_data_checksum, contract_checksum,
queries, manifest_checksum
```

Each query entry mirrors the self-describing query file except for `rows`, and
adds publication metadata such as `data_file`, `file_checksum`, file size,
metric/dashboard consumers, required/optional/dimension/value columns, fetch
attempt count, freshness policy, `provider_mode`, source-column requirements,
and the reviewed transformation contract. A transformed entry also records the
private raw sidecar's name, sizes, and checksums; methodology/script/test
provenance; transformation summaries; and data-quality warnings.

A `query_<id>.json` file contains:

```text
schema_version, ingestion_schema_version, query_id, query_url,
generated_at, fetched_at, execution_id,
execution_started_at, execution_finished_at,
data_updated_at, data_changed_at,
status, freshness_status, row_count, columns, rows,
optional_columns, dimension_columns, value_columns, allow_empty,
freshness_policy, checksum, duplicate_row_count, unexpected_columns,
validation_status, mode, optional source_label
```

Transformed query files additionally contain:

```text
source_mode, source_query_id, source_execution_id, source_last_updated,
raw_data_file, raw_row_count, raw_columns, raw_checksum, raw_file_checksum,
raw_file_size_bytes, methodology_id, methodology_version,
script_path, script_checksum, tests_path,
transformation_summary, data_quality_warnings
```

These provenance fields are non-secret and are checked against the manifest.
The raw sidecar they describe is intentionally absent from the public build.

## Timestamp and freshness semantics

These timestamps answer different questions:

- `execution_started_at` / `execution_finished_at`: when the provider's stored
  query execution ran. `execution_finished_at` is the authoritative timestamp
  for applying the query freshness policy.
- `data_updated_at`: the provider data timestamp; for live Dune latest-result
  imports this mirrors `execution_finished_at`, but it does not override it for
  freshness classification.
- `source_last_updated`: the stored execution completion time for every current
  KyberSwap source. Query 8191379 additionally preserves its row-level
  `last_updated` column and uses that source timestamp in the chart CSV. It
  documents source lineage and does not replace `execution_finished_at` for
  freshness classification.
- enriched-row `generated_at`: a deterministic provenance timestamp anchored
  to the stored source execution completion so replaying identical raw input
  stays byte-stable; it is not the local transformation clock.
- `data_changed_at`: when the normalized content last changed; it stays stable
  across identical content.
- `fetched_at`: when the provider response was fetched.
- `generated_at`: when this local validated snapshot/result was written.
- `dashboard_refreshed_at`: when all required sources and enrichments passed
  validation and the complete snapshot was accepted at the atomic promotion
  boundary. The writer emits a timezone-aware UTC `Z` value. Fixture mode uses
  its deterministic fixture clock. A failed, partial, filtered, or unchanged
  non-forced attempt preserves the prior successful value because it did not
  fetch every required production source in one complete acceptance cycle.
- `last_checked_at`: the most recent refresh attempt, including unchanged or
  failed checks.
- `last_successful_fetch_at`: the most recent complete successful fetch,
  including a content-unchanged check that avoided promotion.
- website build time: when static files were rendered; it is not data time.

The snapshot `display_updated_at` (also recorded as snapshot
`data_updated_at`) is the minimum query-level `data_updated_at` across required
queries. It represents the oldest contributing data, not the newest request or
build. Query freshness is `current`, `delayed`, or `stale` according to its
effective warning/stale thresholds. Dashboard status uses the worst required
source state.

The top-right **Dashboard Last Updated** label uses
`dashboard_refreshed_at`. It answers when Studio successfully refreshed and
accepted the deployed snapshot. Query execution, source-last-updated,
source-data-through, snapshot-generated, and methodology-version fields answer
source provenance questions and remain separate. Legacy manifests without the
field fall back to `last_successful_fetch_at`, then `generated_at`; they never
fall back to the oldest source timestamp.

Do not replace these semantics with `Date.now()` in the browser. Page-open and
site-build times must not make old data look fresh.

## Static build and browser boundary

The website build resolves `state.json` to the active snapshot when it exists;
otherwise it accepts the flat bootstrap `manifest.json`. It validates the
active manifest and query files, deletes stale Studio output, and flattens the
public `manifest.json` plus referenced `query_<id>.json` files into
`output/website/data/studio/generated/`. When source state exists, the build
also writes `refresh_status.json`: a validated allowlist of snapshot IDs,
checksum/timestamps, latest status, `using_previous`, and a restrained failure
summary. The raw `state.json`, snapshot history, attempts, and API key are not
published.

Production passes the validated runner-temporary root through
`--studio-generated-data`; it never relies on the build command's checked-in
default. The public manifest and source descriptors therefore carry the live
snapshot ID and generation time, Dune execution IDs and completion times,
source `last_updated` values where supplied by a transformation, and
methodology IDs and versions. Dashboard `Last Updated` uses the accepted
snapshot's `dashboard_refreshed_at`, while source age and methodology continue
to use their query-specific data/completion timestamps. If a validated
partial/fallback snapshot is ever built explicitly, `refresh_status.json` and
the per-source metadata expose `using_previous` and the failed/reused sources;
fallback is never silently labeled as a fresh full success.

Each dashboard page embeds presentation configuration. `studio.js` loads only
local static JSON, including the optional sanitized refresh status, normalizes
demo and generated sources into a shared adapter, and caches shared paths.
Only demo-mode dashboard bundles are copied; a generated dashboard has no demo
bundle URL and consumes its query files exclusively. There is no arbitrary SQL
execution and no browser-side Dune request.

Bad data remains isolated where possible. Supported UI states include loading,
no data, delayed data, stale data, query failure, missing column, unavailable
file, malformed file, and previous validated data in use. A broken auxiliary
sparkline can report “Trend unavailable” while its valid primary counter still
renders. A malformed manifest is dashboard-wide because query/file resolution
cannot be trusted.

The query-8180894 campaign-summary cards have no inline CSV or Methodology
actions; their export selection and methodology metadata remain available in
the right-side metrics panel. Each Capital Position & Activity chart retains a
Methodology action. The accessible drawer uses one aligned content layout for
definitions, business/allocation rules, limitations, methodology ID/version,
source execution and `source_last_updated`, data-quality warnings, and links to
the Dune query, Python transformation, and focused tests. Closing the drawer
restores focus to the trigger. The methodology text and provenance come from
the reviewed registry/snapshot contract; the browser does not recalculate
attribution or infer methodology from chart labels.

Sankey node identity includes its stage as well as its visible label. This
allows the same label to appear in two stages without collapsing into a
self-link. Both query-8199058 diagrams use the same attributed USD rows.
Sankeys and all other Studio charts use the shared compact visible-tooltip
formatter while CSV exports retain the unformatted source values.

CSV exports contain original loaded rows projected to that metric's configured
`columns`; chart style, date range, table search/sort/pagination, and display
formatting do not rewrite export values. Table sorting compares precise numeric
strings as exact decimals. Standard high-precision formatting does not coerce
them through JavaScript `Number`; the compact campaign counters explicitly
round only their visual USD/percentage presentation while their loaded rows and
exports remain exact. ZIP export groups those metric CSVs.
Names use source metadata rather than the browser clock:

```text
<dashboard-slug>-<metric-id>-<YYYY-MM-DD>.csv
<dashboard-slug>-studio-<YYYY-MM-DD>.zip
```

A metric may declare a stable `export_slug`. The two KyberSwap Sankeys use
`kyberswap-attributed-funds-by-location-<YYYY-MM-DD>.csv` and
`kyberswap-depositor-journey-<YYYY-MM-DD>.csv`; their raw exported rows retain
the source and methodology provenance columns required by the metric contract.
The shared counter export selects only the active period row and uses
`kyberswap-campaign-summary-<period>-<YYYY-MM-DD>.csv`. It aliases `key_` to
`period` and `depositors_new_users_rate` to the semantically correct
`deposits_by_new_depositors_rate`, without changing the stored raw result.

All vertical bars, horizontal rankings, and column views use a same-geometry
emphasis state. Hover preserves the assigned fill and exact bar dimensions,
avoids fading sibling bars, and leaves the tooltip enabled in both themes.

## GitHub Actions safety

`.github/workflows/studio-fixture-refresh.yml` is an active but manual-only
offline validation workflow. It runs immediately when dispatched and has no
confirmation checkbox. It:

- has read-only repository permission and no Dune secret;
- checks the inventory;
- builds a deterministic fixture snapshot at a fixed time;
- validates the active snapshot, runs the complete tests, and builds the site;
- uploads short-lived diagnostics;
- does not deploy Pages or commit generated data.

Production is active through three narrowly scoped workflows:

- `.github/workflows/deploy-website.yml` is a push-to-`main` wrapper. It has no
  build steps of its own and calls the shared production workflow.
- `.github/workflows/studio-live-refresh.yml` preserves `workflow_dispatch` and
  also runs on `25 */4 * * *`. Manual and scheduled invocations call the same
  shared production workflow with the same ingestion command.
- `.github/workflows/studio-production-deploy.yml` is `workflow_call`-only. It
  requires the `DUNE_API_KEY` secret, performs the complete read-only import,
  validates and tests it, builds the complete website from the promoted
  runner-temporary snapshot, uploads one Pages artifact, and deploys only after
  the build job succeeds.

The shared workflow first checks that `DUNE_API_KEY` is present, then copies the
checked-in previous-good root to `$RUNNER_TEMP/studio-live-generated`. It loads
the unique production query IDs from the validated Studio registry rather than
hardcoding them in YAML. Its live import omits `--allow-partial`,
`--mixed-source-mode`, and all execution or stale-auto-refresh options. It uses
`--force` so every fully validated production deployment receives a newly
accepted immutable snapshot and `dashboard_refreshed_at`, even when Dune's
latest stored execution IDs are unchanged. A
source, transformation, reconciliation, validation, test, or build failure
prevents artifact upload and deployment. A missing secret fails before
ingestion and provides repository Actions-secret setup guidance. No generated
data is written back to git.

All production entries share the fixed `studio-production-pages` concurrency
group with `cancel-in-progress: true`. Only one production deployment can
proceed at a time, and a newer run supersedes an older in-progress run. The
fixture workflow uses a separate group and has no Pages permissions, so it
cannot interfere with production.

`.github/workflows/refresh-freshness.yml` remains scheduled hourly and can also
be dispatched manually, but it now validates only the latest already-stored
catalog-freshness result and uploads a short-lived diagnostic artifact. It has
read-only repository permission and no Pages build, artifact, environment, or
deployment. It therefore cannot overwrite a live Studio site. The shared
production build imports catalog freshness when it builds the complete website.

Configure the repository Actions secret before triggering either production
entry point:

```text
GitHub repository -> Settings -> Secrets and variables -> Actions
Secret name: DUNE_API_KEY
Access: Dune query-result read access only
```

The four-hour Studio schedule imports only latest stored results. Dune's own
independent query schedules remain the sole mechanism that executes or
refreshes the reviewed queries. Push, manual, and scheduled Studio triggers all
use the same read-only production path.

## Onboarding changes safely

### Add a query

1. Confirm the query's output grain and exact required/optional columns. Do not
   invent semantics from a visualization.
2. Add or update a metric mapping with the positive `query_id`. Let
   `query_url`/`data_file` normalize, or use their exact derived values.
3. Reuse an existing ID only when URL, file, data source, and shared column
   semantics are genuinely compatible.
4. Regenerate and review both inventory files. This works before a generated
   result exists because inventory validation is configuration-only.
5. Run a fixture scenario or an approved production stored-result import into
   an isolated output directory, then validate it.

### Add a metric

1. Choose the existing dashboard and section, then add a unique metric ID and
   per-dashboard `display_order`.
2. Declare the narrow primary `columns`, optional/dimension/value roles,
   visualization mappings, format, visibility/export/empty behavior, source
   label, and freshness policy.
3. Map any sparkline dependency explicitly to an existing `data_source` and its
   date/value columns.
4. Regenerate the inventory and run focused registry, inventory, ingestion,
   build, and browser tests.
5. Verify both rendered values and raw CSV/ZIP output.

### Add a dashboard

1. Add a unique dashboard ID/slug/order with sections and either `demo` or
   `generated` data mode.
2. Add its metrics following the metric workflow above.
3. For demo mode, create a deterministic clearly labeled bundle in
   `studio/data/`. For generated mode, produce a complete validated snapshot;
   do not hand-edit promoted query JSON.
4. Regenerate/check the inventory and run the full site build. The landing card
   and route are generated automatically.
5. Check desktop/mobile UI states, empty/failure behavior, explorer links, and
   exports. Normal onboarding should not require dashboard-specific HTML or JS.

## Debugging

- Inventory mismatch: run the generator, inspect registry changes and checksum,
  then rerun `--check`.
- No active snapshot: `--validate-only` reports `active_snapshot: false`; run a
  successful fixture refresh when snapshot validation or generated mode is
  required.
- Refresh failed: inspect `attempts/<latest_attempt_id>/attempt.json` and
  `state.json`; the prior snapshot should still be active.
- Unexpected partial status: inspect `using_previous`, reused query IDs, and
  `latest_failure`; partial reuse only happens with `--allow-partial`.
- Missing column: compare the inventory's query union, provider column list,
  and the affected metric mapping. Do not silently weaken a required contract.
- Stale/delayed result: compare `last_checked_at` with query
  `execution_finished_at` and the effective freshness policy.
- Build-time malformed data: run the CLI's `--validate-only`; the build repeats
  validation deliberately.
- Port already in use: choose another local preview port in both command and
  URL.

## Local build and preview

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/generate_studio_inventory.py --check
.venv/bin/python scripts/build_website.py
.venv/bin/python -m http.server 8000 --directory output/website
```

Open:

- `http://localhost:8000/studio/`
- `http://localhost:8000/studio/kyberswap/`

The build replaces Studio's generated output, so retired routes and query files
cannot linger. Regenerate the invented KyberSwap sample bundle with:

```bash
.venv/bin/python scripts/generate_studio_demo_data.py
.venv/bin/python scripts/generate_studio_demo_data.py \
  --refreshed-at 2026-07-30T12:00:00Z
```

Rebuild after regeneration and keep sample-data labeling visible.

## ECharts and performance baseline

Studio vendors Apache ECharts 6.1.0 and its Apache 2.0 license under
`website/assets/vendor/`. One local static library supplies responsive line,
area, column, horizontal/vertical bar, and Sankey charts without a CDN or a
Node bundling step.

The tradeoff is bundle size. A local audit measured approximately 1.12 MB raw
(369 KB gzip) for `echarts.min.js`, 148 KB raw (31 KB gzip) for `studio.js`,
and 174 KB raw (30 KB gzip) for the public generated query payloads. The
complete generated website was about 3.7 MB. In that same environment, full
site builds took about 0.23–0.26 seconds and the then-current 719-test suite took
44.25 seconds. These are one-machine diagnostic baselines, not CI budgets or
performance guarantees; test counts and timings change as coverage grows.

A future tree-shaken ECharts build could reduce transfer size but would add a
JavaScript dependency/build pipeline. Any such change should compare cached and
uncached payloads, mobile rendering, and the no-CDN reliability of the current
approach.

## Tests

Focused Studio and workflow coverage:

```bash
.venv/bin/python -m pytest \
  tests/test_kyberswap_campaign_summary.py \
  tests/test_kyberswap_attributed_holdings.py \
  tests/test_studio_build.py \
  tests/test_studio_data_contract.py \
  tests/test_studio_ingestion.py \
  tests/test_studio_inventory.py \
  tests/test_studio_js.py \
  tests/test_website_deploy_workflow.py -q
```

Complete verification:

```bash
.venv/bin/python scripts/generate_studio_inventory.py --check
.venv/bin/python -m pytest -q
.venv/bin/python scripts/build_website.py
git diff --check
```

The tests cover registry validation, config-only inventory generation,
shared-query deduplication, fixture/live mocked clients, retry classes,
normalization edge cases, immutable promotion and rollback, unchanged/partial
states, timestamp/freshness semantics, build publication, UI fallback states,
chart controls, identifiers, tables, and raw metric-scoped exports. The focused
KyberSwap suite covers campaign-summary period/financial validation, source
preservation, source schema/grain, exact Decimal allocation rules A–E, stable
ties, exits, warnings, provenance, group reconciliation, and both Sankey
reconciliations without contacting Dune.
