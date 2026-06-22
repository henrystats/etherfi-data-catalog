---
title: Freshness
nav_label: Freshness
description: Freshness and Dune cost awareness direction for the catalog website.
order: 5
format: html
---

<section class="page">
  <div class="wrap page-shell">
    <div class="content-stack">
      <div>
        <p class="eyebrow">Trust and operations</p>
        <h1>Freshness and cost awareness</h1>
        <p class="page-lead">
          The catalog should help users understand whether a dataset is fresh
          enough for the question and whether a query shape is likely to waste
          Dune credits.
        </p>
      </div>

      <section class="detail-panel">
        <h2>Freshness model</h2>
        <p>
          Static dataset metadata stores expected refresh intervals and freshness
          timestamp columns. Runtime snapshots live in `status/dataset_freshness.yaml`
          and can be imported from a Dune tracker CSV export.
        </p>
        <pre><code>.venv/bin/python scripts/update_freshness_from_tracker.py path/to/tracker.csv
scripts/refresh_catalog_status.sh path/to/tracker.csv</code></pre>
      </section>

      <section class="detail-panel warning">
        <h2>Cost guidance for MVP</h2>
        <p>
          Use qualitative labels and query-shape advice before reliable credit
          telemetry exists. Do not invent exact credit estimates.
        </p>
      </section>

      <section class="detail-panel">
        <h2>Good defaults</h2>
        <ul>
          <li>Filter date windows early.</li>
          <li>Batch symbols and days into one Dune query.</li>
          <li>Aggregate on Dune, not in Python.</li>
          <li>Prefer dataset-native USD columns before joining prices.</li>
          <li>Avoid minute prices unless the user needs minute-level precision.</li>
        </ul>
      </section>
    </div>

    <aside class="sidebar">
      <section class="detail-panel">
        <h2>Ticket 6</h2>
        <p>
          The next freshness pass will generate a real status page from catalog
          metadata and the optional local freshness snapshot.
        </p>
      </section>
    </aside>
  </div>
</section>

