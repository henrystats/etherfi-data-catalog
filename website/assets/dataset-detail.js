(function () {
  const COPY_SELECTOR = "[data-copy-text]";
  const FEEDBACK_SELECTOR = "[data-copy-feedback]";
  const ANNOUNCER_SELECTOR = "[data-copy-announcer]";
  const SCHEMA_FILTER_SELECTOR = "[data-schema-filter]";
  const SCHEMA_TABLE_SELECTOR = "[data-schema-table]";
  const SCHEMA_INPUT_SELECTOR = "[data-schema-filter-input]";
  const SCHEMA_CLEAR_SELECTOR = "[data-schema-filter-clear]";
  const SCHEMA_COUNT_SELECTOR = "[data-schema-filter-count]";
  const SCHEMA_EMPTY_SELECTOR = "[data-schema-filter-empty]";
  const SCHEMA_ROW_SELECTOR = "[data-schema-row]";
  const RESET_DELAY_MS = 1400;

  function normalizeSchemaSearch(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function schemaSearchTerms(query) {
    const normalized = normalizeSchemaSearch(query);
    return normalized === "" ? [] : normalized.split(" ");
  }

  function schemaRowMatches(searchText, query) {
    const searchableText = normalizeSchemaSearch(searchText);
    return schemaSearchTerms(query).every((term) => searchableText.includes(term));
  }

  function filterSchemaRows(rows, query) {
    return rows.map((row) => ({
      row,
      visible: schemaRowMatches(row.search, query),
    }));
  }

  function formatSchemaCount(visibleCount, totalCount, hasQuery) {
    const columnLabel = totalCount === 1 ? "column" : "columns";
    return hasQuery
      ? `${visibleCount} of ${totalCount} ${columnLabel}`
      : `${totalCount} ${columnLabel}`;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      filterSchemaRows,
      formatSchemaCount,
      normalizeSchemaSearch,
      schemaRowMatches,
      schemaSearchTerms,
    };
  }

  if (typeof document === "undefined") {
    return;
  }

  const resetTimers = new WeakMap();
  document.documentElement.dataset.datasetDetailMounted = "true";

  function mountSchemaFilter(filter) {
    if (filter.dataset.schemaFilterMounted === "true") {
      return;
    }

    const table = filter.closest(SCHEMA_TABLE_SELECTOR);
    const input = filter.querySelector(SCHEMA_INPUT_SELECTOR);
    const clearButton = filter.querySelector(SCHEMA_CLEAR_SELECTOR);
    const count = table ? table.querySelector(SCHEMA_COUNT_SELECTOR) : null;
    const emptyState = table ? table.querySelector(SCHEMA_EMPTY_SELECTOR) : null;
    const rows = table
      ? [...table.querySelectorAll(SCHEMA_ROW_SELECTOR)].map((element) => ({
          element,
          search: element.dataset.schemaSearch || "",
        }))
      : [];

    if (!table || !input || !clearButton || !count || !emptyState || rows.length === 0) {
      return;
    }

    function applyFilter() {
      const hasQuery = schemaSearchTerms(input.value).length > 0;
      const results = filterSchemaRows(rows, input.value);
      let visibleCount = 0;

      results.forEach((result) => {
        result.row.element.hidden = !result.visible;
        if (result.visible) {
          visibleCount += 1;
        }
      });

      count.textContent = formatSchemaCount(visibleCount, rows.length, hasQuery);
      emptyState.hidden = visibleCount !== 0;
      clearButton.hidden = !hasQuery;
    }

    function clearFilter() {
      input.value = "";
      applyFilter();
      input.focus();
    }

    input.addEventListener("input", applyFilter);
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") {
        return;
      }
      if (schemaSearchTerms(input.value).length > 0) {
        event.preventDefault();
        clearFilter();
      } else {
        input.blur();
      }
    });
    clearButton.addEventListener("click", clearFilter);

    filter.hidden = false;
    filter.dataset.schemaFilterMounted = "true";
    applyFilter();
  }

  document.querySelectorAll(SCHEMA_FILTER_SELECTOR).forEach(mountSchemaFilter);

  function setFeedback(button, label) {
    const feedback = button.querySelector(FEEDBACK_SELECTOR);
    if (!feedback) {
      return;
    }
    feedback.textContent = label;
    const announcer = button.parentElement
      ? button.parentElement.querySelector(ANNOUNCER_SELECTOR)
      : null;
    if (announcer) {
      announcer.textContent = label === "Copy" ? "" : label;
    }
  }

  function resetFeedback(button) {
    const existingTimer = resetTimers.get(button);
    if (existingTimer) {
      window.clearTimeout(existingTimer);
    }
    const timer = window.setTimeout(() => {
      setFeedback(button, "Copy");
      button.classList.remove("copied", "copy-failed");
      resetTimers.delete(button);
    }, RESET_DELAY_MS);
    resetTimers.set(button, timer);
  }

  async function handleCopy(button) {
    const text = button.dataset.copyText || "";
    if (!text) {
      return;
    }

    try {
      const copied = window.CatalogUI && typeof window.CatalogUI.copyText === "function"
        ? await window.CatalogUI.copyText(text, document)
        : false;
      button.classList.toggle("copied", copied);
      button.classList.toggle("copy-failed", !copied);
      setFeedback(button, copied ? "Copied" : "Copy failed");
      resetFeedback(button);
    } catch (error) {
      button.classList.add("copy-failed");
      setFeedback(button, "Copy failed");
      resetFeedback(button);
      console.warn("[ether.fi datasets] Copy failed", error);
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest(COPY_SELECTOR);
    if (!button) {
      return;
    }
    event.preventDefault();
    handleCopy(button);
  });
})();
