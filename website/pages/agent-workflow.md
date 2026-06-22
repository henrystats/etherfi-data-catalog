---
title: Agent Workflow
nav_label: Agent Workflow
description: How agents should route ether.fi analytics work across catalog MCP, Dune MCP, and Dune Skills.
order: 6
format: html
published: false
---

<section class="page">
  <div class="wrap page-shell">
    <div class="content-stack">
      <div>
        <p class="eyebrow">Routing guide</p>
        <h1>Agent workflow</h1>
        <p class="page-lead">
          The safest agent behavior is simple: resolve ether.fi semantics first,
          then create or run Dune artifacts only when the route is clear.
        </p>
      </div>

      <section class="detail-panel">
        <h2>Default flow</h2>
        <div class="route">
          <div class="route-step">
            <span>1</span>
            <div>
              <strong>Ask the catalog</strong>
              <p>Pick the dataset, tool, caveats, filters, grain, and expected output shape.</p>
            </div>
          </div>
          <div class="route-step">
            <span>2</span>
            <div>
              <strong>Use Dune MCP when needed</strong>
              <p>Create, run, save, visualize, or dashboard the query after catalog planning.</p>
            </div>
          </div>
          <div class="route-step">
            <span>3</span>
            <div>
              <strong>Preserve caveats</strong>
              <p>Carry direct-vs-DeFi, freshness, price, and completeness notes into the artifact.</p>
            </div>
          </div>
        </div>
      </section>

      <section class="detail-panel callout">
        <h2>When to stop at the catalog</h2>
        <p>
          If the user wants a narrow live answer and a dedicated catalog tool
          exists, return the compact answer with caveats and freshness. Do not
          create a shareable Dune query unless the user asks for one.
        </p>
      </section>
    </div>

    <aside class="sidebar">
      <section class="detail-panel">
        <h2>Common disambiguations</h2>
        <ul>
          <li>Direct holders vs holders with DeFi exposure.</li>
          <li>Cash balances vs Cash events.</li>
          <li>Snapshot answer vs time series.</li>
          <li>Full-population total vs top-N ranking.</li>
        </ul>
      </section>
    </aside>
  </div>
</section>
