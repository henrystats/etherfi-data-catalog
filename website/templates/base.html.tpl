<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#f4f6f1">
    <meta name="description" content="$description">
    <title>$title | ether.fi Data Catalog</title>
    <link rel="stylesheet" href="${asset_prefix}assets/styles.css">
  </head>
  <body class="$body_class">
    <a class="skip-link" href="#main-content">Skip to content</a>
    <header class="site-header">
      <div class="site-header-inner">
        <a class="brand" href="${asset_prefix}index.html" aria-label="ether.fi Data Catalog home">
          <span class="brand-mark">ether.fi</span>
          <span>
            <strong>Data Catalog</strong>
            <small>semantic registry + MCP</small>
          </span>
        </a>
        <nav class="site-nav" aria-label="Primary navigation">
          $nav
        </nav>
      </div>
    </header>
    <main id="main-content">
      $content
    </main>
    <footer class="site-footer">
      <div class="site-footer-inner">
        <div>
          <strong>ether.fi Data Catalog</strong>
          <span>Trusted context for onchain analysis.</span>
        </div>
        <div class="site-footer-links">
          <a href="${asset_prefix}datasets.html">Datasets</a>
          <a href="${asset_prefix}dashboards.html">Dashboards</a>
          <a href="${asset_prefix}freshness.html">Freshness</a>
          <a href="${asset_prefix}mcp.html">MCP</a>
        </div>
      </div>
    </footer>
  </body>
</html>
