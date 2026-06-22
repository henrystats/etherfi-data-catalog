# AGENTS.md

## Project purpose
This repository contains an ether.fi analytics catalog and MCP server.

The goal is to help AI assistants and team members:
- discover the right materialized views and queries
- understand dataset caveats and completeness
- find existing dashboards
- generate correct SQL using trusted metadata

## Working rules
- Keep changes small and easy to review.
- Do not invent dataset semantics.
- Prefer simple, readable code with minimal dependencies.
- Treat metadata files in this repo as the source of truth.
- Add tests for any parsing or comparison logic.
- Update README when adding new tools or setup steps.

## Dataset documentation rules
Each important dataset should eventually include:
- table or matview name
- short description
- grain
- refresh cadence
- accuracy
- completeness
- important caveats
- key columns that need semantic explanation
- related dashboards
- related source query IDs or logic links

## Example semantic behavior
If a user asks for top ether.fi protocol token holders:
- surface both `protocol_token_holders` and `protocol_token_holders_with_defi` when relevant
- explain that `protocol_token_holders` is the clean direct-holders view
- explain that `protocol_token_holders_with_defi` includes tracked defi exposure but is incomplete
- ask whether indirect defi exposure should be included
- explain that `identified_defi_contract` is a tracked DeFi contract name, where non-null rows are attributed to known tracked DeFi contracts

## MCP Tool Authoring Standard

When adding or modifying an MCP tool in this repo, follow this pattern unless there is a strong reason not to.

### 1) Start with the question class

Before writing code, define the exact user question type:

- single-entity lookup
- ranking / top-N
- population aggregate / total
- time-series summary
- row inspection
- diagnostic / coverage debugging
- discovery / disambiguation

Do not overload one tool to handle multiple unrelated question classes unless the shape is still clean and safe.

### 2) Prefer the narrowest correct dataset

Choose the best dataset based on existing metadata and semantics.

Prefer:
- the most semantically correct table
- the narrowest table that answers the question
- a dataset already documented as query-ready when possible

Document:
- chosen dataset
- why it was chosen
- what common wrong alternatives exist

### 3) Aggregate on Dune, not in Python

If the user asks for:
- totals
- counts
- rankings
- grouped summaries
- top-N
- distinct counts
- per-token or per-chain summaries

then the aggregation should happen in SQL on Dune.

Do not:
- pull large raw row sets into Python just to aggregate there
- compose multiple live tool calls when one aggregate query can answer the question

### 4) Tool design requirements

Each tool should have:

- clear name
- minimal but sufficient parameters
- conservative validation
- planning mode (`execute_live=False`)
- live mode (`execute_live=True`)
- narrow SQL
- structured summary output
- explicit caveats
- README examples
- focused regression tests

### 5) Parameter design rules

Expose parameters only when they materially change the query semantics.

Examples:
- token_symbol
- token_address
- blockchain
- strategy_symbol
- strategy_address
- event_type
- include_defi
- exclude_identified_defi
- as_of_date
- recent_days
- limit

Rules:
- reject ambiguous parameter combinations when possible
- prefer explicit validation over silent precedence
- keep identifiers conservative and safe
- cap expensive parameters like `limit`

### 6) Planning mode contract

Planning mode must not hit Dune.

It should return:
- chosen dataset(s)
- why they were chosen
- ranking / aggregate scope
- key caveats
- suggested SQL
- expected output fields
- explanation of important semantics

Planning mode should be good enough for a reviewer to confirm the query shape before live execution.

### 7) Live mode contract

Live mode should:
- run one narrow Dune query whenever practical
- use aggregate SQL for aggregate questions
- return compact rows, not oversized payloads
- include a structured summary
- include freshness/status when available
- clearly explain partial / missing coverage when relevant

### 8) Output shape guidelines

Most tools should return:
- tool metadata / chosen dataset
- filters applied
- row_count
- rows (compact)
- summary
- caveats / warnings
- freshness_status when available

### 9) Honest-boundary rules

The tool must not claim to answer a question it cannot actually answer.

Examples:
- top-10 overall cohort is not the same as top-10 by filtered token
- partial result is not population total
- evidence-based profile is not canonical identity
- exchange-rate coverage is not USD price coverage

If the tool cannot answer exactly, say what it *can* answer and what tool/filter is missing.

### 10) When to add a new tool vs extend an existing one

Extend an existing tool when:
- the new filter/refinement preserves the same core question class

Add a new tool when:
- the question class changes

Examples:
- extending `get_top_cash_users(...)` with `token_symbol` is good
- using `get_top_cash_users(...)` to answer full-population token totals is not
- that should be a separate aggregate tool

### 11) Test requirements

For every new or changed tool, add:
- validation tests
- planning-mode tests
- live-mode mocked tests
- at least one natural prompt-equivalent regression
- one edge-case or ambiguity test

### 12) README requirements

Add 2–5 short realistic example prompts that show:
- the intended use
- important filters
- likely teammate phrasing

### 13) Preferred implementation style

Keep changes:
- small
- reviewable
- metadata-aware
- summary-first
- deterministic

Avoid:
- broad refactors
- generic arbitrary SQL execution
- large multi-tool orchestration when one query will do
