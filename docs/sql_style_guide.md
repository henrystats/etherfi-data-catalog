# ether.fi SQL Style And Optimization Guide

## Purpose

Use this guide when writing or reviewing ether.fi DuneSQL for shareable queries, charts, dashboards, and catalog-backed analysis. It is intentionally practical: choose the correct ether.fi dataset first, keep the query shape reviewable, and avoid wasting Dune credits on avoidable scans.

This guide does not replace dataset metadata. The catalog metadata remains the source of truth for table meaning, caveats, completeness, and dashboard links.

## Core Principles

- Start with the narrowest correct dataset. Prefer a query-ready ether.fi result table or purpose-built catalog tool over rebuilding semantics from lower-level events.
- Filter early. If the question has a date period, filter on the table's date or timestamp column as close to the base scan as possible.
- Batch related work into one query. Prefer `IN (...)`, grouped output, and range queries over repeated per-symbol, per-address, or per-day calls.
- Aggregate on Dune, not in Python. Totals, counts, rankings, grouped summaries, time series, and distinct counts belong in SQL.
- Preserve semantics in the artifact. Query descriptions or comments should carry important caveats, especially direct-vs-DeFi holder scope and price enrichment behavior.
- Prefer reviewable query shapes over cleverness. A teammate should be able to see the selected dataset, filters, grain, and metric definitions quickly.

## SQL Style Conventions

- Use lowercase SQL keywords and readable CTE names.
- Keep CTEs purposeful: `filtered_events`, `daily_totals`, `month_end_days`, `ranked_holders`.
- Put narrow filters in the first CTE that touches the large table.
- Select only the columns needed for the next step.
- Use explicit date windows, even for starter queries, so the default plan does not scan all history.
- Use `group by 1, 2` only when the selected columns are obvious and stable; otherwise spell out the grouping columns.
- Order final outputs by the reporting grain first, then the business dimension, or by the ranking metric for top-N tables.
- Use comments sparingly for semantic caveats, not for line-by-line narration.

## Query Optimization Rules

1. Filter on the date window early.

   Good query shapes put `block_date`, `day`, or `minute` filters in the base CTE:

   ```sql
   with filtered_events as (
     select
       block_date,
       token_symbol,
       token_amount_usd
     from dune.ether_fi.result_etherfi_cash_events
     where block_date >= date_add('day', -90, current_date)
       and event_type = 'spend'
   )
   select ...
   ```

2. Use the narrowest correct dataset.

   Cash event volume should start from `dune.ether_fi.result_etherfi_cash_events`, not Cash balance snapshots. Protocol token TVL history should start from `dune.ether_fi.result_etherfi_protocol_token_tvl`, not holder tables.

3. Avoid repeated point calls.

   Do not loop through one day or one symbol at a time when one range query can return the chart-ready result. Use `token_symbol in (...)` for multi-token slices and group by the relevant dimension.

4. Aggregate on Dune.

   DuneSQL should compute `sum(...)`, `count(...)`, `count(distinct ...)`, `rank()`, time buckets, and grouped summaries. Python should not pull large raw row sets just to aggregate them locally.

5. Avoid unnecessary joins.

   Use dataset-native USD columns when available, such as `token_amount_usd`, `token_balance_usd`, or `token_supply_usd`. Join prices only when the selected dataset does not already contain the USD value needed for the question.

6. Avoid minute price joins unless needed.

   Minute-level price joins are expensive and can introduce gaps. If the analysis is daily, weekly, monthly, or dashboard-historical, use daily prices or dataset-native USD values.

7. Treat large executions carefully.

   Dune credits are shared team resources. For broad history, multi-chain joins, or large table scans, review the query shape first, add date filters, and consider testing a smaller window before running the full query.

## Price-Table Guidance

Default hierarchy:

1. Prefer dataset-native USD fields when the chosen ether.fi dataset already has them.
2. For historical aggregated work that needs a price join, default to `dune.ether_fi.result_tokens_prices_enriched_daily`.
3. Use `dune.ether_fi.result_tokens_prices_enriched_minute` only when the question truly requires minute-level or intraday precision.
4. Use direct USD price tables as debugging/reference inputs, not the default historical price source.

`dune.ether_fi.result_tokens_prices_enriched_daily` is the safer default for historical work because it is more complete than the enriched minute table. It supports daily, weekly, monthly, and most dashboard-style analysis well.

`dune.ether_fi.result_tokens_prices_enriched_minute` has gaps and should not be joined to daily-aggregated data unless the user explicitly needs minute precision.

Direct USD tables are useful when debugging enriched prices, checking whether a token is missing from enriched daily, or inspecting raw/non-enriched price behavior. Do not present them as the normal dashboarding default when enriched daily is suitable.

## Token Symbol Guidance

Do not force a blanket "use token_address instead of token_symbol" rule.

For core ether.fi datasets such as `protocol_events`, `protocol_token_tvl`, and `assets_under_management`, token symbols are effectively unique for normal teammate workflows. Filtering by `token_symbol` or `strategy_symbol` for core assets such as `eETH`, `liquidETH`, `liquidUSD`, `eBTC`, and `liquidBTC` is acceptable and expected.

Use `token_address` when working outside the core ether.fi datasets, when a symbol is ambiguous, or when joining to generic token/price tables where duplicate symbols are common.

## Common Query Patterns

### Weekly Cash Event Volume

```sql
with filtered_events as (
  select
    block_date,
    token_symbol,
    token_amount_usd
  from dune.ether_fi.result_etherfi_cash_events
  where block_date >= date_add('week', -12, current_date)
    and event_type = 'spend'
    and token_symbol in ('USDC', 'liquidUSD')
)
select
  date_trunc('week', block_date) as week,
  token_symbol,
  sum(token_amount_usd) as volume_usd,
  count(*) as event_count
from filtered_events
group by 1, 2
order by 1, 2;
```

### Monthly TVL Timeseries

Use month-end daily snapshots instead of summing daily TVL across the month.

```sql
with daily_tvl as (
  select
    day,
    date_trunc('month', day) as month,
    strategy_symbol,
    sum(token_supply_usd) as tvl_usd
  from dune.ether_fi.result_etherfi_protocol_token_tvl
  where day >= date_add('month', -12, current_date)
    and strategy_symbol in ('eETH', 'liquidETH', 'liquidUSD')
  group by 1, 2, 3
),
month_end_days as (
  select
    month,
    strategy_symbol,
    max(day) as month_end_day
  from daily_tvl
  group by 1, 2
)
select
  daily_tvl.month,
  daily_tvl.strategy_symbol,
  daily_tvl.day as month_end_day,
  daily_tvl.tvl_usd
from daily_tvl
join month_end_days
  on daily_tvl.month = month_end_days.month
  and daily_tvl.strategy_symbol = month_end_days.strategy_symbol
  and daily_tvl.day = month_end_days.month_end_day
order by 1, 2;
```

### Holder Ranking Query Shape

Resolve direct holders vs tracked DeFi-aware exposure before sharing the query. Use `protocol_token_holders` for clean direct holders. Use `protocol_token_holders_with_defi` only when the user wants tracked DeFi exposure and accepts incomplete DeFi coverage.

```sql
with latest_day as (
  select max(day) as day
  from dune.ether_fi.result_etherfi_protocol_token_holders
  where token_symbol = 'eETH'
),
filtered_holders as (
  select
    holders.address,
    holders.blockchain,
    holders.token_symbol,
    holders.token_balance
  from dune.ether_fi.result_etherfi_protocol_token_holders as holders
  join latest_day
    on holders.day = latest_day.day
  where holders.token_symbol = 'eETH'
)
select
  address,
  blockchain,
  token_symbol,
  sum(token_balance) as holder_balance
from filtered_holders
group by 1, 2, 3
order by holder_balance desc
limit 100;
```

### Historical Balances With Enriched Daily Prices

Only join prices when the selected balance dataset does not already include a suitable USD column. For historical daily/weekly/monthly work, use enriched daily prices by default.

```sql
with balances as (
  select
    day,
    address,
    blockchain,
    token_symbol,
    token_address,
    token_balance
  from dune.ether_fi.result_etherfi_assets_under_management
  where day >= date_add('month', -6, current_date)
    and token_symbol in ('eETH', 'liquidUSD')
),
daily_prices as (
  select
    day,
    blockchain,
    token_address,
    coalesce(token_usd, token_usd_rate) as price_usd
  from dune.ether_fi.result_tokens_prices_enriched_daily
  where day >= date_add('month', -6, current_date)
)
select
  balances.day,
  balances.token_symbol,
  count(distinct balances.address) as holder_count,
  sum(balances.token_balance * daily_prices.price_usd) as balance_usd
from balances
join daily_prices
  on balances.day = daily_prices.day
  and balances.blockchain = daily_prices.blockchain
  and balances.token_address = daily_prices.token_address
group by 1, 2
order by 1, 2;
```

## Anti-Patterns To Avoid

- Looping day by day instead of doing one range query grouped by day, week, or month.
- Looping symbol by symbol when a single `token_symbol in (...)` query works.
- Pulling raw rows into Python to compute totals, counts, rankings, or time series.
- Using Cash balance/snapshot tables for event-volume questions.
- Using ranking outputs or top-N tools to answer full-population totals.
- Joining minute prices to daily, weekly, or monthly aggregated data.
- Joining a price table when the selected dataset already has the required USD column.
- Treating direct USD tables as the default historical dashboard price source.
- Hiding important caveats, such as incomplete tracked DeFi exposure, in an unpublished prompt instead of the query description or SQL comments.

## Good Default Approach

For a new shareable ether.fi query:

1. Ask the catalog which dataset, filters, grain, metrics, and caveats fit the question.
2. Start the SQL with a base filtered CTE that applies date and semantic filters early.
3. Use one batched query for the whole requested slice.
4. Aggregate in DuneSQL.
5. Prefer dataset-native USD fields; otherwise use enriched daily prices for historical work.
6. Add only necessary joins.
7. Save the query with a description that states the selected dataset and any interpretation caveats.
