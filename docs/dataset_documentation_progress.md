# Dataset Documentation Progress

Last updated: 2026-06-19

This tracker is for completing repo-backed dataset documentation without losing
context between passes. Dataset YAML files should only be updated after Henry
provides the missing documentation details.

## Summary

- Total datasets: 32
- Good enough: 7
- Partial docs: 13
- Missing docs: 12

## Status Rules

- Missing docs: placeholder description and/or missing core fields such as
  grain, schema, or important columns.
- Partial docs: usable base metadata exists, but descriptions, schema coverage,
  related resources, or caveats need improvement.
- Good enough: enough description, schema/important column context, freshness,
  source query, and related-resource context for the website and MCP to be useful.

## First Batch Recommendation

Ask Henry for details for these first:

1. `dune.ether_fi.result_etherfi_cash_events`
2. `dune.ether_fi.result_etherfi_protocol_events`
3. `dune.ether_fi.result_etherfi_protocol_token_tvl`
4. `etherfi_protocol_token_holders`
5. `etherfi_protocol_token_holders_with_defi`

These are high-impact protocol/Cash datasets, linked to dashboards, likely MCP
routing targets, and already have source/freshness metadata.

## Reusable Input Template

```text
Dataset:
Table name:
Plain-English description:
What this table is used for:
Grain:
Refresh cadence:
Freshness timestamp column:
Source Dune query ID / URL:
Important columns and descriptions:
Schema descriptions, if different from important columns:
Related datasets:
Related dashboards:
Known caveats / interpretation notes:
Anything not to mention publicly:
```

## Checklist By Category

### activity

- [ ] `dune.ether_fi.result_addresses_transfers`
  - File: `datasets/activity/addresses_transfers.yaml`
  - Table: `dune.ether_fi.result_addresses_transfers`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, related_dashboards, caveats/interpretation notes
  - Why it matters: daily address-transfer activity; likely useful for activity monitoring and dashboard drilldowns.

- [ ] `dune.ether_fi.result_addresses_transfers_hourly`
  - File: `datasets/activity/addresses_transfers_hourly.yaml`
  - Table: `dune.ether_fi.result_addresses_transfers_hourly`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, related_dashboards, caveats/interpretation notes
  - Why it matters: hourly address-transfer activity; likely used for fresher operational checks.

- [x] `contracts_logs`
  - File: `datasets/activity/contracts_logs.yaml`
  - Table: `dune.ether_fi.result_contracts_logs`
  - Status: Good enough
  - Priority: Medium
  - Missing/weak: none currently blocking
  - Why it matters: contract log activity; useful for raw event inspection and reconciliation.

- [x] `contracts_traces`
  - File: `datasets/activity/contracts_traces.yaml`
  - Table: `dune.ether_fi.result_contracts_traces`
  - Status: Good enough
  - Priority: Medium
  - Missing/weak: none currently blocking
  - Why it matters: contract trace activity; useful for execution-level diagnostics.

- [ ] `dune.ether_fi.result_defi_events`
  - File: `datasets/activity/defi_events.yaml`
  - Table: `dune.ether_fi.result_defi_events`
  - Status: Missing docs
  - Priority: High
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, related_dashboards, caveats/interpretation notes
  - Why it matters: DeFi event activity; likely powers protocol or partner activity analysis.

- [ ] `dune.ether_fi.result_tokens_transfers`
  - File: `datasets/activity/tokens_transfers.yaml`
  - Table: `dune.ether_fi.result_tokens_transfers`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, related_dashboards, caveats/interpretation notes
  - Why it matters: daily token-transfer activity; useful for movement and holder-flow analysis.

- [ ] `dune.ether_fi.result_tokens_transfers_hourly`
  - File: `datasets/activity/tokens_transfers_hourly.yaml`
  - Table: `dune.ether_fi.result_tokens_transfers_hourly`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, related_dashboards, caveats/interpretation notes
  - Why it matters: hourly token-transfer activity; likely useful for operational monitoring.

- [ ] `dune.ether_fi.result_tokens_weth_tfers`
  - File: `datasets/activity/tokens_weth_tfers.yaml`
  - Table: `dune.ether_fi.result_tokens_weth_tfers`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, related_dashboards, caveats/interpretation notes
  - Why it matters: WETH-only transfer activity; useful when separating WETH flows from broader token movement.

### etherfi_protocol

- [ ] `dune.ether_fi.result_etherfi_addresses`
  - File: `datasets/etherfi_protocol/etherfi_addresses.yaml`
  - Table: `dune.ether_fi.result_etherfi_addresses`
  - Status: Partial docs
  - Priority: Medium
  - Missing/weak: refresh_interval_minutes, freshness_timestamp_column, source_query_id/source_query_url, schema descriptions 6/15
  - Why it matters: canonical address classification; supports AUM, dashboard context, and address interpretation.

- [x] `dune.ether_fi.result_etherfi_assets_under_management`
  - File: `datasets/etherfi_protocol/etherfi_assets_under_management.yaml`
  - Table: `dune.ether_fi.result_etherfi_assets_under_management`
  - Status: Good enough
  - Priority: Low
  - Missing/weak: none currently blocking
  - Why it matters: high-impact balance/AUM dataset and featured website entry.

- [ ] `dune.ether_fi.result_etherfi_cash_borrow_index`
  - File: `datasets/etherfi_protocol/etherfi_cash_borrow_index.yaml`
  - Table: `dune.ether_fi.result_etherfi_cash_borrow_index`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: weak description, related_datasets
  - Why it matters: Cash borrow-index context; likely important for Cash lending/repay analysis.

- [ ] `dune.ether_fi.result_etherfi_cash_events`
  - File: `datasets/etherfi_protocol/etherfi_cash_events.yaml`
  - Table: `dune.ether_fi.result_etherfi_cash_events`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: weak description, related_datasets
  - Why it matters: core Cash activity table and dashboard/MCP routing target.

- [ ] `dune.ether_fi.result_etherfi_competitive_assets_holders_with_defi`
  - File: `datasets/etherfi_protocol/etherfi_competitive_assets_holders_with_defi.yaml`
  - Table: `dune.ether_fi.result_etherfi_competitive_assets_holders_with_defi`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: related_datasets
  - Why it matters: broader competitive asset holder analysis with DeFi exposure caveats.

- [ ] `dune.ether_fi.result_etherfi_protocol_events`
  - File: `datasets/etherfi_protocol/etherfi_protocol_events.yaml`
  - Table: `dune.ether_fi.result_etherfi_protocol_events`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: schema descriptions 8/23, related_datasets
  - Why it matters: core protocol event analytics and likely dashboard/MCP routing target.

- [ ] `etherfi_protocol_token_holders`
  - File: `datasets/etherfi_protocol/etherfi_protocol_token_holders.yaml`
  - Table: `dune.ether_fi.result_etherfi_protocol_token_holders`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: related_datasets
  - Why it matters: clean direct-holder view; important for holder rankings and MCP disambiguation.

- [ ] `etherfi_protocol_token_holders_with_defi`
  - File: `datasets/etherfi_protocol/etherfi_protocol_token_holders_with_defi.yaml`
  - Table: `dune.ether_fi.result_etherfi_protocol_token_holders_with_defi`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: schema descriptions 6/15, related_datasets
  - Why it matters: DeFi-aware holder exposure; needs clear caveats because coverage is partial.

- [ ] `dune.ether_fi.result_etherfi_protocol_token_tvl`
  - File: `datasets/etherfi_protocol/etherfi_protocol_token_tvl.yaml`
  - Table: `dune.ether_fi.result_etherfi_protocol_token_tvl`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: schema descriptions 7/18, related_datasets
  - Why it matters: featured protocol TVL dataset and primary overview-dashboard source.

### lrt_restaking

- [ ] `dune.ether_fi.result_lrts_restaking_dex_pools`
  - File: `datasets/lrt_restaking/lrts_restaking_dex_pools.yaml`
  - Table: `dune.ether_fi.result_lrts_restaking_dex_pools`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, caveats/interpretation notes
  - Why it matters: LRT/restaking pool coverage; likely supports overview dashboard sections.

- [ ] `dune.ether_fi.result_lrts_restaking_dex_pools_balances`
  - File: `datasets/lrt_restaking/lrts_restaking_dex_pools_balances.yaml`
  - Table: `dune.ether_fi.result_lrts_restaking_dex_pools_balances`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, caveats/interpretation notes
  - Why it matters: balance side of LRT/restaking pool analysis.

- [ ] `dune.ether_fi.result_lrts_restaking_dex_pools_transfers`
  - File: `datasets/lrt_restaking/lrts_restaking_dex_pools_transfers.yaml`
  - Table: `dune.ether_fi.result_lrts_restaking_dex_pools_transfers`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, related_dashboards, caveats/interpretation notes
  - Why it matters: transfer side of LRT/restaking pool analysis.

- [ ] `dune.ether_fi.result_lrts_restaking_protocol_tvl`
  - File: `datasets/lrt_restaking/lrts_restaking_protocol_tvl.yaml`
  - Table: `dune.ether_fi.result_lrts_restaking_protocol_tvl`
  - Status: Missing docs
  - Priority: High
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, caveats/interpretation notes
  - Why it matters: LRT/restaking TVL is high-impact and likely dashboard-facing.

- [ ] `dune.ether_fi.result_lrts_restaking_trades`
  - File: `datasets/lrt_restaking/lrts_restaking_trades.yaml`
  - Table: `dune.ether_fi.result_lrts_restaking_trades`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, caveats/interpretation notes
  - Why it matters: LRT/restaking trade activity and DEX context.

### metadata

- [x] `contracts_addresses_list`
  - File: `datasets/metadata/contracts_addresses_list.yaml`
  - Table: `dune.ether_fi.result_contracts_addresses_list`
  - Status: Good enough
  - Priority: Medium
  - Missing/weak: none currently blocking
  - Why it matters: input registry for reusable contract logs/traces extraction and related downstream rate/oracle logic.

- [ ] `dune.ether_fi.result_addresses_traits`
  - File: `datasets/metadata/addresses_traits.yaml`
  - Table: `dune.ether_fi.result_addresses_traits`
  - Status: Missing docs
  - Priority: Medium
  - Missing/weak: weak description, grain, schema, important_columns, related_datasets, caveats/interpretation notes
  - Why it matters: address traits likely support classification and joins across activity/protocol tables.

- [ ] `dune.ether_fi.result_tokens_traits`
  - File: `datasets/metadata/tokens_traits.yaml`
  - Table: `dune.ether_fi.result_tokens_traits`
  - Status: Partial docs
  - Priority: Medium
  - Missing/weak: weak description, related_dashboards, caveats/interpretation notes
  - Why it matters: token metadata powers price lookup, token resolution, and symbol/address disambiguation.

### prices

- [ ] `dune.ether_fi.result_tokens_exchange_rates_daily`
  - File: `datasets/prices/tokens_exchange_rates_daily.yaml`
  - Table: `dune.ether_fi.result_tokens_exchange_rates_daily`
  - Status: Partial docs
  - Priority: Medium
  - Missing/weak: related_dashboards
  - Why it matters: daily exchange-rate coverage; supports enriched pricing and valuation.

- [ ] `dune.ether_fi.result_tokens_prices_enriched_daily`
  - File: `datasets/prices/tokens_prices_enriched_daily.yaml`
  - Table: `dune.ether_fi.result_tokens_prices_enriched_daily`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: related_dashboards
  - Why it matters: daily enriched price table, likely a primary pricing source for reporting.

- [ ] `dune.ether_fi.result_tokens_prices_enriched_minute`
  - File: `datasets/prices/tokens_prices_enriched_minute.yaml`
  - Table: `dune.ether_fi.result_tokens_prices_enriched_minute`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: related_dashboards
  - Why it matters: minute-level enriched prices and likely live/recent analysis source.

- [ ] `dune.ether_fi.result_tokens_prices_tokens_list`
  - File: `datasets/prices/tokens_prices_tokens_list.yaml`
  - Table: `dune.ether_fi.result_tokens_prices_tokens_list`
  - Status: Partial docs
  - Priority: High
  - Missing/weak: source_query_id/source_query_url
  - Why it matters: token universe/coverage diagnostics for price lookup and missing-price questions.

- [x] `dune.ether_fi.result_tokens_prices_usd`
  - File: `datasets/prices/tokens_prices_usd.yaml`
  - Table: `dune.ether_fi.result_tokens_prices_usd`
  - Status: Good enough
  - Priority: Low
  - Missing/weak: none currently blocking
  - Why it matters: minute-level direct USD price source.

- [x] `dune.ether_fi.result_tokens_prices_usd_daily`
  - File: `datasets/prices/tokens_prices_usd_daily.yaml`
  - Table: `dune.ether_fi.result_tokens_prices_usd_daily`
  - Status: Good enough
  - Priority: Low
  - Missing/weak: none currently blocking
  - Why it matters: daily direct USD price source.

- [x] `dune.ether_fi.result_tokens_rates_oracle_pegs`
  - File: `datasets/prices/tokens_rates_oracle_pegs.yaml`
  - Table: `dune.ether_fi.result_tokens_rates_oracle_pegs`
  - Status: Good enough
  - Priority: Low
  - Missing/weak: none currently blocking
  - Why it matters: exchange-rate source for enriched pricing and valuation.

## Next Notes

- Do not infer or invent missing descriptions.
- Update dataset YAML files only after Henry provides details.
- After each YAML update, rebuild the website and run focused validation tests.
