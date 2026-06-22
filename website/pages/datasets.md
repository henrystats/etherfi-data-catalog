---
title: Datasets
nav_label: Datasets
description: Dataset documentation foundation for the ether.fi analytics catalog.
order: 3
format: html
---

<section class="page">
  <div class="wrap page-shell">
    <div class="content-stack">
      <div>
        <p class="eyebrow">Catalog source of truth</p>
        <h1>Dataset documentation</h1>
        <p class="page-lead">
          Dataset YAML files are the source of truth for table meaning, grain,
          completeness, caveats, key columns, example prompts, and related dashboards.
        </p>
      </div>

      <section class="detail-panel">
        <h2>High-impact dataset families</h2>
        <div class="tag-list">
          <span class="tag">Protocol holders</span>
          <span class="tag">Protocol TVL</span>
          <span class="tag">Assets under management</span>
          <span class="tag">Cash events</span>
          <span class="tag">Protocol events</span>
          <span class="tag">Enriched prices</span>
        </div>
        <p>
          Ticket 3 will generate one page per dataset from the existing YAML
          metadata. Ticket 4 will polish the pages that matter most for the Monday
          demo and teammate onboarding.
        </p>
      </section>

      <section class="detail-panel callout">
        <h2>Important semantic example</h2>
        <p>
          Top holder prompts must surface both direct holder balances and tracked
          DeFi-aware exposure when relevant. `identified_defi_contract` is a tracked
          DeFi contract name, not a boolean, and DeFi-aware coverage is partial.
        </p>
      </section>

      <section class="detail-panel">
        <h2>What every important dataset page should show</h2>
        <ul>
          <li>Table or materialized view name and source query URL.</li>
          <li>Business meaning, grain, refresh cadence, and freshness timestamp column.</li>
          <li>Important columns with semantic explanations.</li>
          <li>Use-when and do-not-use-when guidance.</li>
          <li>Caveats, completeness notes, example prompts, related dashboards, and related tables.</li>
        </ul>
      </section>
    </div>

    <aside class="sidebar">
      <section class="detail-panel warning">
        <h2>MVP honesty</h2>
        <p>
          Some metadata is intentionally incomplete today. The website should show
          "Not documented yet" rather than inventing semantics.
        </p>
      </section>
      <section class="detail-panel">
        <h2>Next ticket</h2>
        <p>
          Ticket 3 turns this shell into generated dataset pages backed by
          `datasets/*.yaml`.
        </p>
      </section>
    </aside>
  </div>
</section>

