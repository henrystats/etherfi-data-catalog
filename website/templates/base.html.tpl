<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light dark">
    <meta name="theme-color" content="#f4f6f1" data-theme-color>
    <meta name="description" content="$description">
    <title>$document_title</title>
    <script data-theme-init>
      (function () {
        var root = document.documentElement;
        var theme = "light";
        root.setAttribute("data-theme-ready", "");

        try {
          var savedTheme = window.localStorage.getItem("etherfi-data-catalog-theme");
          if (savedTheme === "light" || savedTheme === "dark") {
            theme = savedTheme;
          } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
            theme = "dark";
          }
        } catch (error) {
          try {
            if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
              theme = "dark";
            }
          } catch (mediaError) {
            theme = "light";
          }
        }

        root.setAttribute("data-theme", theme);
      }());
    </script>
    <link rel="stylesheet" href="${asset_prefix}assets/styles.css?v=$styles_version">
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
        <div class="site-header-actions">
          <nav class="site-nav" aria-label="Primary navigation">
            $nav
          </nav>
          <button class="theme-toggle" type="button" data-theme-toggle aria-pressed="false" aria-label="Dark theme" title="Switch to dark theme">
            <span class="theme-toggle-track" aria-hidden="true"><span class="theme-toggle-knob"></span></span>
          </button>
        </div>
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
    <script src="${asset_prefix}assets/theme.js?v=$theme_js_version" defer></script>
  </body>
</html>
