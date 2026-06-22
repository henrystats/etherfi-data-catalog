(function (root, factory) {
  const filters = factory(root);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = filters;
  }
  if (root) {
    root.FreshnessFilters = filters;
  }
  if (typeof document !== "undefined") {
    filters.ready(document);
  }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  const SEARCH_SELECTOR = "#dataset-search";
  const ROW_SELECTOR = "[data-dataset-card]";
  const STATUS_FILTER_SELECTOR = "[data-status-filter]";
  const COUNT_SELECTOR = "#dataset-count";
  const EMPTY_SELECTOR = "#dataset-empty-state";

  function normalize(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function termsFor(query) {
    const normalized = normalize(query);
    return normalized === "" ? [] : normalized.split(" ");
  }

  function matchesStatus(row, status) {
    return status === "all" || row.status === status;
  }

  function matchesSearch(row, query) {
    const terms = termsFor(query);
    if (terms.length === 0) {
      return true;
    }
    const searchableText = normalize(row.search);
    return terms.every((term) => searchableText.includes(term));
  }

  function matchesRow(row, state) {
    const status = state.status || "all";
    const query = state.query || "";
    return matchesStatus(row, status) && matchesSearch(row, query);
  }

  function filterRows(rows, state) {
    return rows.map((row) => ({
      row,
      visible: matchesRow(row, state),
    }));
  }

  function rowDataFromElement(row) {
    return {
      element: row,
      search: row.dataset.search || "",
      status: row.dataset.status || "",
    };
  }

  function setActive(buttons, activeValue, attribute) {
    buttons.forEach((button) => {
      const isActive = button.dataset[attribute] === activeValue;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
  }

  function mount(scope) {
    const page = scope.querySelector("[data-freshness-page]");
    if (!page) {
      return;
    }

    if (page.dataset.freshnessMounted === "true") {
      return;
    }
    page.dataset.freshnessMounted = "true";

    const searchInput = page.querySelector(SEARCH_SELECTOR);
    const statusButtons = [...page.querySelectorAll(STATUS_FILTER_SELECTOR)];
    const rows = [...page.querySelectorAll(ROW_SELECTOR)].map(rowDataFromElement);
    const count = page.querySelector(COUNT_SELECTOR);
    const emptyState = page.querySelector(EMPTY_SELECTOR);
    const state = {
      status: "all",
      query: "",
    };

    if (!searchInput || rows.length === 0 || !count || !emptyState) {
      console.warn("[ether.fi freshness] Search controls missing", {
        inputFound: Boolean(searchInput),
        cardCount: rows.length,
        countFound: Boolean(count),
        emptyStateFound: Boolean(emptyState),
      });
    }

    function applyFilters() {
      state.query = searchInput ? searchInput.value : "";
      const results = filterRows(rows, state);
      const visibleCount = results.filter((result) => result.visible).length;

      results.forEach((result) => {
        result.row.element.hidden = !result.visible;
        result.row.element.style.display = result.visible ? "" : "none";
      });

      if (count) {
        count.textContent = `${visibleCount} shown`;
      }
      if (emptyState) {
        emptyState.hidden = visibleCount !== 0;
      }
    }

    function visibleCount() {
      return rows.filter((row) => !row.element.hidden && row.element.style.display !== "none").length;
    }

    if (root) {
      root.__etherfiFreshnessSearchDebug = () => ({
        inputFound: Boolean(searchInput),
        cardCount: rows.length,
        visibleCount: visibleCount(),
        selectedStatus: state.status,
      });
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilters);
    }

    statusButtons.forEach((button) => {
      button.addEventListener("click", () => {
        state.status = button.dataset.statusFilter || "all";
        setActive(statusButtons, state.status, "statusFilter");
        applyFilters();
      });
    });

    setActive(statusButtons, state.status, "statusFilter");
    applyFilters();
  }

  function ready(scope) {
    if (!scope || scope.readyState === "loading") {
      scope.addEventListener("DOMContentLoaded", () => mount(scope), { once: true });
      return;
    }
    mount(scope);
  }

  return {
    filterRows,
    matchesRow,
    mount,
    normalize,
    ready,
    termsFor,
  };
});
