# ether.fi Data Catalog Roadmap

This roadmap tracks the Monday, June 1, 2026 MVP push for a presentation-ready
website over the existing ether.fi analytics catalog and MCP server.

## Tracking Rules

- Keep tickets small and reviewable.
- Move one ticket to `in progress` at a time.
- Prefer a polished website MVP over exhaustive metadata completeness before June 1.
- Preserve the architecture boundary: `etherfi-catalog` owns semantics and planning;
  Dune MCP owns query, chart, dashboard, and execution lifecycle.
- Do not invent dataset semantics. If metadata is incomplete, show it honestly.

## Status Legend

- `[ ]` todo
- `[~]` in progress
- `[x]` done

## Milestone: Monday Pretty Website MVP

### Ticket 1: Create Pretty Static Website Foundation

**Status:** `[x]` done  
**Labels:** `website`, `mvp`, `presentation`  
**Estimate:** 2-3h  
**Goal:** Add a polished docs website shell with navigation, homepage, styling direction, and local preview/build commands.

**Acceptance Criteria:**
- Site can be built and previewed locally.
- Homepage explains ether.fi Data Catalog clearly.
- Navigation includes MCP, datasets, dashboards, freshness, and agent workflow.
- Visual style feels presentation-ready, not default docs boilerplate.
- README includes local website commands.

**Likely Files:**
- `mkdocs.yml` or equivalent site config
- `docs/index.md`
- `docs/mcp.md`
- `docs/datasets.md`
- `docs/dashboards.md`
- `docs/freshness.md`
- `README.md`
- `pyproject.toml`

### Ticket 2: Build Presentation-Ready Homepage

**Status:** `[x]` done  
**Labels:** `website`, `design`, `mvp`  
**Estimate:** 2h  
**Goal:** Make the first screen clearly communicate what the catalog is and why it matters.

**Acceptance Criteria:**
- Homepage has a strong product narrative.
- Shows the four-layer architecture: `etherfi-catalog` MCP, Dune MCP, Dune Skills, and website/docs.
- Shows primary user groups: team members, analysts, and agents.
- Includes a "what this helps answer" section with concrete ether.fi examples.
- Does not overclaim completeness.

**Likely Files:**
- `docs/index.md`
- optional custom theme/CSS file depending on framework

### Ticket 3: Generate Dataset Index And Dataset Pages

**Status:** `[x]` done  
**Labels:** `website`, `catalog`, `mvp`  
**Estimate:** 4h  
**Goal:** Turn existing YAML metadata into readable dataset documentation pages.

**Acceptance Criteria:**
- One generated page exists per dataset.
- Dataset index groups datasets by folder/category.
- Pages show table name, description, grain, source query URL, refresh cadence, important columns, use/do-not-use guidance, caveats, and example prompts when available.
- Missing fields render as "Not documented yet" rather than breaking.
- Generation does not hit Dune.

**Likely Files:**
- `scripts/generate_docs.py`
- `docs/generated/datasets/`
- `docs/datasets.md`
- `tests/test_docs_generation.py`

### Ticket 4: Add High-Impact Dataset Detail Polish

**Status:** `[ ]` todo  
**Labels:** `metadata`, `datasets`, `mvp`  
**Estimate:** 3h  
**Goal:** Make the most demo-relevant dataset pages feel complete enough for Monday.

**Scope:**
- Protocol token holders
- Protocol holders with DeFi
- Assets under management
- Cash events
- Protocol events
- Protocol token TVL
- Enriched daily prices
- Ether.fi addresses / Cash classification if needed

**Acceptance Criteria:**
- Core pages explain business meaning and caveats clearly.
- Direct vs DeFi holder distinction is prominent.
- Cash balances vs Cash events distinction is prominent.
- AUM vs canonical TVL distinction is prominent.
- Existing tests still pass.

**Likely Files:**
- selected YAML files under `datasets/etherfi_protocol/`
- selected YAML files under `datasets/prices/`

### Ticket 5: Generate Dashboard Registry Pages

**Status:** `[x]` done  
**Labels:** `website`, `dashboards`, `mvp`  
**Estimate:** 2h  
**Goal:** Make existing dashboards discoverable through the site.

**Acceptance Criteria:**
- Dashboard index exists.
- `etherfi_overview` has a readable page.
- Page shows URL, description, tags, and linked datasets.
- Linked datasets point to generated dataset pages where possible.
- Page clearly says this registry will grow over time.

**Likely Files:**
- `scripts/generate_docs.py`
- `docs/dashboards.md`
- `docs/generated/dashboards/`

### Ticket 6: Freshness And Catalog Health Page

**Status:** `[x]` done  
**Labels:** `website`, `freshness`, `mvp`  
**Estimate:** 2-3h  
**Goal:** Show the team that freshness/status is part of the product direction.

**Acceptance Criteria:**
- Freshness page lists datasets with expected refresh intervals.
- If `status/dataset_freshness.yaml` exists, observed latest update/status is shown.
- If no runtime snapshot exists, page explains how to generate one.
- Stale warnings are visible but not alarmist.
- Cost awareness is qualitative and conservative; no invented credit estimates.

**Likely Files:**
- `scripts/generate_docs.py`
- `docs/freshness.md`
- `docs/generated/freshness.md`

### Ticket 7: MCP Setup And Agent Workflow Pages

**Status:** `[ ]` todo  
**Labels:** `docs`, `mcp`, `mvp`  
**Estimate:** 2h  
**Goal:** Make the site useful for teammates who want to connect Codex/Claude/ChatGPT-style agents.

**Acceptance Criteria:**
- MCP page explains what `etherfi-catalog` does.
- Shows planning mode vs live mode.
- Lists available tools by category.
- Explains when to use Dune MCP instead.
- Includes 6-10 realistic example prompts.

**Likely Files:**
- `docs/mcp.md`
- `docs/agent_workflow.md`
- maybe generated tool section from `src/server.py`

### Ticket 8: Website Visual Polish Pass

**Status:** `[x]` done  
**Labels:** `design`, `presentation`, `mvp`  
**Estimate:** 3h  
**Goal:** Make the site look intentionally designed for Monday.

**Acceptance Criteria:**
- Homepage looks polished on desktop.
- Dataset pages are scannable.
- Important caveats appear in visually distinct callouts.
- Navigation is clean.
- No obvious broken links.
- No default-theme rough edges distract in a presentation.

**Likely Files:**
- site theme config
- custom CSS
- `docs/index.md`
- generated templates/script output

### Ticket 9: Deployment Path

**Status:** `[ ]` todo  
**Labels:** `deployment`, `docs`, `mvp`  
**Estimate:** 1-2h  
**Goal:** Make the website easy to share.

**Acceptance Criteria:**
- Build command is documented.
- GitHub Pages or static hosting path is documented.
- Optional GitHub Actions workflow is added if low-friction.
- No secrets are required to build the site.

**Likely Files:**
- `.github/workflows/docs.yml`
- `README.md`
- site config

### Ticket 10: Post-MVP Metadata Completeness Dashboard

**Status:** `[ ]` todo  
**Labels:** `metadata`, `quality`, `post-mvp`  
**Estimate:** 3-4h  
**Goal:** Add a generated audit page showing metadata completeness across datasets.

**Acceptance Criteria:**
- Page lists missing schema/caveats/examples/query-ready fields.
- Helps analysts prioritize documentation work.
- Does not block the Monday presentation.

**Likely Files:**
- `scripts/generate_docs.py`
- `docs/generated/metadata_audit.md`
- `tests/test_docs_generation.py`

## Recommended Implementation Order

1. Ticket 1: Create Pretty Static Website Foundation
2. Ticket 2: Build Presentation-Ready Homepage
3. Ticket 3: Generate Dataset Index And Dataset Pages
4. Ticket 8: Website Visual Polish Pass
5. Ticket 5: Generate Dashboard Registry Pages
6. Ticket 6: Freshness And Catalog Health Page
7. Ticket 7: MCP Setup And Agent Workflow Pages
8. Ticket 9: Deployment Path
9. Ticket 10: Post-MVP Metadata Completeness Dashboard
