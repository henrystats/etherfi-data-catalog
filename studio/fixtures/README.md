# Studio ingestion fixtures

`scenarios.yaml` layers deterministic response behaviors over the checked-in
raw query fixtures. The fixture client therefore exercises the same counters,
time series, rankings, Sankey rows, wallet tables, addresses, transaction
hashes, nulls, and large datasets that Studio renders, while each unique query
ID is still fetched only once.

`query_8180894.json`, `query_8191379.json`, `query_8191704.json`,
`query_8193003.json`, `query_8193040.json`, `query_8199058.json`, and
`query_8202133.json` are offline raw-source fixtures for the reviewed production
transformations. They exercise campaign-summary validation, Campaign Growth
daily/weekly snapshots, attribution, and signed post-referral activity without
contacting Dune or initiating execution. Query 8199058 uses its exact ten-column
latest-result schema with monetary values already expressed in USD. Query
8202133 retains positive and negative `amount_usd` values while preparing daily
and weekly Label, Project, and Event sums. Prepared rows are derived
deterministically and never trigger or simulate query execution.

The named scenarios cover valid, empty, extra/reordered-column, malformed,
duplicate, null, large-value, multi-chain, invalid-date, rate-limit, timeout,
previously observed Dune execution-failure, partial-result, and row-count
mismatch behavior. These fixtures never initiate execution. Numeric
strings and duplicate rows are preserved; normalization never guesses a
financial conversion or silently drops data.
