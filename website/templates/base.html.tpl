<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light dark">
    <meta name="theme-color" content="#f2f0e8" data-theme-color>
    <meta name="description" content="$description">
    <meta name="robots" content="index,follow">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="ether.fi Data Catalog">
    <meta property="og:title" content="$document_title">
    <meta property="og:description" content="$description">
    <meta name="twitter:card" content="summary">
    <title>$document_title</title>
    <script data-theme-init>
      (function () {
        var root = document.documentElement;
        var theme = "light";
        root.setAttribute("data-js", "");

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
    $extra_head
    <script src="${asset_prefix}assets/catalog-ui.js?v=$catalog_ui_js_version" defer></script>
    <script src="${asset_prefix}assets/catalog-index.js?v=$catalog_index_js_version" defer></script>
    <script src="${asset_prefix}assets/global-search.js?v=$global_search_js_version" defer></script>
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
          <nav class="site-nav site-nav-desktop" aria-label="Primary navigation">
            $nav
          </nav>
          <a class="site-search-trigger" href="${asset_prefix}explore.html"$search_current
            aria-label="Search catalog"
            data-catalog-search-open aria-keyshortcuts="Meta+K Control+K"
            title="Search catalog (Command or Control + K)">
            <span>Search catalog</span>
            <span class="site-search-shortcut" aria-hidden="true"><kbd>⌘</kbd><kbd>K</kbd></span>
            <span class="visually-hidden">Keyboard shortcut: Command K or Control K</span>
          </a>
          <button class="theme-toggle" type="button" data-theme-toggle aria-pressed="false" aria-label="Dark theme" title="Switch to dark theme">
            <span class="theme-toggle-track" aria-hidden="true"><span class="theme-toggle-knob"></span></span>
          </button>
          <details class="site-mobile-menu">
            <summary><span>Menu</span></summary>
            <nav class="site-mobile-nav" aria-label="Mobile navigation">
              $nav
            </nav>
          </details>
        </div>
      </div>
    </header>
    <dialog class="catalog-command-dialog" data-catalog-dialog
      data-catalog-site-root="${asset_prefix}"
      aria-labelledby="catalog-command-title">
      <div class="catalog-command-shell">
        <header class="catalog-command-header">
          <div>
            <p class="eyebrow">Catalog search</p>
            <h2 id="catalog-command-title">Search datasets and dashboards</h2>
          </div>
          <button class="catalog-command-close" type="button"
            data-catalog-command-close aria-label="Close catalog search">Close</button>
        </header>
        <label class="visually-hidden" for="catalog-command-input">
          Search the catalog
        </label>
        <input class="catalog-command-input" id="catalog-command-input"
          type="search" data-catalog-command-input
          placeholder="Dataset, schema column, dashboard metric..."
          autocomplete="off" spellcheck="false">
        <div class="catalog-command-status">
          <span data-catalog-command-count role="status"
            aria-live="polite" aria-atomic="true">0 results</span>
          <span aria-hidden="true">Use ↑ and ↓ to move</span>
        </div>
        <div class="catalog-command-results" data-catalog-command-results></div>
        <p class="catalog-command-empty" data-catalog-command-empty hidden>
          No catalog resources match those terms.
        </p>
        <p class="catalog-command-note">
          Results include schema columns and dashboard metrics.
        </p>
      </div>
    </dialog>
    <main id="main-content" tabindex="-1">
      $content
    </main>
    <footer class="site-footer">
      <div class="site-footer-inner">
        <div class="site-footer-brand">
          <strong>ether.fi Data Catalog</strong>
          <span>Repository-backed context for onchain analysis.</span>
        </div>
        <nav class="site-footer-links" aria-label="Footer navigation">
          <a href="${asset_prefix}datasets.html">Datasets</a>
          <a href="${asset_prefix}dashboards.html">Dashboards</a>
          <a href="${asset_prefix}freshness.html">Freshness</a>
          <a href="${asset_prefix}mcp.html">MCP</a>
        </nav>
      </div>
    </footer>
    <script src="${asset_prefix}assets/theme.js?v=$theme_js_version" defer></script>
  </body>
</html>
