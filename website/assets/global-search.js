(function (root, factory) {
  "use strict";

  const globalSearch = factory();

  if (typeof module !== "undefined" && module.exports) {
    module.exports = globalSearch;
  }
  if (root && root.document) {
    root.GlobalCatalogSearch = globalSearch;
    globalSearch.ready(root.document, root);
  }
})(
  typeof window !== "undefined"
    ? window
    : (typeof globalThis !== "undefined" ? globalThis : this),
  function () {
    "use strict";

    const RESULT_LIMIT = 10;
    const OPEN_SELECTOR = "[data-catalog-search-open]";
    const DIALOG_SELECTOR = "[data-catalog-dialog]";
    const INPUT_SELECTOR = "[data-catalog-command-input]";
    const RESULTS_SELECTOR = "[data-catalog-command-results]";
    const EMPTY_SELECTOR = "[data-catalog-command-empty]";
    const COUNT_SELECTOR = "[data-catalog-command-count]";
    const CLOSE_SELECTOR = "[data-catalog-command-close]";
    const RESULT_SELECTOR = "[data-catalog-command-result]";

    function normalize(value) {
      return String(value == null ? "" : value)
        .toLowerCase()
        .replace(/\s+/g, " ")
        .trim();
    }

    function termsFor(query) {
      const normalized = normalize(query);
      if (!normalized) {
        return [];
      }
      return normalized.split(" ").filter((term, index, terms) => (
        term && terms.indexOf(term) === index
      ));
    }

    function normalizedHints(resource) {
      if (!resource || !Array.isArray(resource.matchHints)) {
        return [];
      }
      return resource.matchHints
        .map((hint) => String(hint == null ? "" : hint).trim())
        .filter(Boolean);
    }

    function searchableFields(resource) {
      const item = resource || {};
      const title = normalize(item.title);
      const category = normalize(item.category);
      const other = normalize([
        item.kind,
        item.description,
        item.searchText,
        ...normalizedHints(item),
      ].join(" "));

      return {
        all: normalize([title, category, other].join(" ")),
        category,
        other,
        title,
      };
    }

    function queryParts(query) {
      return {
        normalized: normalize(query),
        terms: termsFor(query),
      };
    }

    function matchesResource(resource, query) {
      const parts = queryParts(query);
      if (parts.terms.length === 0) {
        return true;
      }
      const fields = searchableFields(resource);
      return parts.terms.every((term) => fields.all.includes(term));
    }

    function relevanceTier(resource, query) {
      const parts = queryParts(query);
      if (parts.terms.length === 0) {
        return 0;
      }

      const fields = searchableFields(resource);
      if (!parts.terms.every((term) => fields.all.includes(term))) {
        return -1;
      }
      if (fields.title === parts.normalized) {
        return 5;
      }
      if (fields.title.startsWith(parts.normalized)) {
        return 4;
      }
      if (
        fields.title.includes(parts.normalized) ||
        parts.terms.every((term) => fields.title.includes(term))
      ) {
        return 3;
      }
      if (
        fields.category.includes(parts.normalized) ||
        parts.terms.every((term) => fields.category.includes(term))
      ) {
        return 2;
      }
      return 1;
    }

    function scoreResource(resource, query) {
      const parts = queryParts(query);
      const tier = relevanceTier(resource, query);
      if (tier < 0) {
        return -1;
      }
      if (parts.terms.length === 0) {
        return 0;
      }

      const fields = searchableFields(resource);
      const titleTerms = parts.terms.filter(
        (term) => fields.title.includes(term),
      ).length;
      const titleWordPrefixes = parts.terms.filter((term) => (
        fields.title.split(" ").some((word) => word.startsWith(term))
      )).length;
      const categoryTerms = parts.terms.filter(
        (term) => fields.category.includes(term),
      ).length;
      const otherPhrase = fields.other.includes(parts.normalized) ? 1 : 0;

      return (
        (tier * 1000000) +
        (titleTerms * 10000) +
        (titleWordPrefixes * 1000) +
        (categoryTerms * 100) +
        (otherPhrase * 10)
      );
    }

    function rankResources(resources, query) {
      if (!Array.isArray(resources)) {
        return [];
      }

      const parts = queryParts(query);
      const candidates = resources
        .map((resource, index) => ({
          index,
          resource,
          score: scoreResource(resource, parts.normalized),
        }))
        .filter((candidate) => (
          candidate.resource &&
          typeof candidate.resource === "object" &&
          candidate.score >= 0
        ));

      if (parts.terms.length === 0) {
        return candidates.map((candidate) => candidate.resource);
      }

      candidates.sort((left, right) => (
        (right.score - left.score) ||
        (left.index - right.index)
      ));
      return candidates.map((candidate) => candidate.resource);
    }

    function searchResources(resources, query) {
      return rankResources(resources, query).slice(0, RESULT_LIMIT);
    }

    function hintScore(hint, normalizedQuery, terms) {
      const normalizedHint = normalize(hint);
      const matchingTerms = terms.filter(
        (term) => normalizedHint.includes(term),
      ).length;
      if (matchingTerms === 0) {
        return -1;
      }
      if (normalizedHint === normalizedQuery) {
        return 50000 + matchingTerms;
      }
      if (normalizedHint.startsWith(normalizedQuery)) {
        return 40000 + matchingTerms;
      }
      if (normalizedHint.includes(normalizedQuery)) {
        return 30000 + matchingTerms;
      }
      if (matchingTerms === terms.length) {
        return 20000 + matchingTerms;
      }
      return 10000 + matchingTerms;
    }

    function bestMatchingHint(resource, query) {
      const hints = normalizedHints(resource);
      if (hints.length === 0) {
        return "";
      }

      const parts = queryParts(query);
      if (parts.terms.length === 0) {
        return "";
      }

      let bestHint = "";
      let bestScore = -1;
      hints.forEach((hint) => {
        const score = hintScore(hint, parts.normalized, parts.terms);
        if (score > bestScore) {
          bestHint = hint;
          bestScore = score;
        }
      });
      return bestHint;
    }

    function kindLabel(kind) {
      const value = String(kind || "");
      if (!value) {
        return "";
      }
      return `${value.charAt(0).toUpperCase()}${value.slice(1)}`;
    }

    function prefixResourceHref(href, siteRoot) {
      const value = String(href || "");
      const prefix = String(siteRoot || "");
      if (
        !value ||
        !prefix ||
        value.startsWith("/") ||
        value.startsWith("#") ||
        /^[a-z][a-z\d+.-]*:/i.test(value) ||
        value.startsWith("//")
      ) {
        return value;
      }
      return `${prefix}${value.replace(/^\.\//, "")}`;
    }

    function clearElement(element) {
      while (element && element.firstChild) {
        element.removeChild(element.firstChild);
      }
    }

    function appendTextElement(ownerDocument, parent, tagName, className, text) {
      const element = ownerDocument.createElement(tagName);
      element.className = className;
      element.textContent = String(text == null ? "" : text);
      parent.appendChild(element);
      return element;
    }

    function createResult(ownerDocument, resource, query, siteRoot) {
      const item = resource || {};
      const link = ownerDocument.createElement("a");
      link.className = "catalog-command-result";
      link.setAttribute("data-catalog-command-result", "");
      link.setAttribute("data-resource-kind", String(item.kind || ""));
      link.setAttribute(
        "href",
        prefixResourceHref(item.href, siteRoot),
      );

      const meta = ownerDocument.createElement("span");
      meta.className = "catalog-command-result__meta";
      appendTextElement(
        ownerDocument,
        meta,
        "span",
        "catalog-command-result__kind",
        kindLabel(item.kind),
      );
      appendTextElement(
        ownerDocument,
        meta,
        "span",
        "catalog-command-result__category",
        item.category,
      );
      link.appendChild(meta);

      appendTextElement(
        ownerDocument,
        link,
        "span",
        "catalog-command-result__title",
        item.title,
      );
      appendTextElement(
        ownerDocument,
        link,
        "span",
        "catalog-command-result__description",
        item.description,
      );

      const matchingHint = bestMatchingHint(item, query);
      if (matchingHint) {
        appendTextElement(
          ownerDocument,
          link,
          "span",
          "catalog-command-result__hint",
          `Matches “${matchingHint}”`,
        );
      }

      return link;
    }

    function renderResults(resultsElement, resources, query, siteRoot) {
      if (!resultsElement) {
        return [];
      }
      const ownerDocument = resultsElement.ownerDocument;
      if (!ownerDocument || typeof ownerDocument.createElement !== "function") {
        return [];
      }

      clearElement(resultsElement);
      const rendered = [];
      const items = Array.isArray(resources) ? resources : [];
      items.forEach((resource) => {
        const result = createResult(ownerDocument, resource, query, siteRoot);
        resultsElement.appendChild(result);
        rendered.push(result);
      });
      return rendered;
    }

    function resultCountLabel(total, shown) {
      const resultWord = total === 1 ? "result" : "results";
      if (total > shown) {
        return `${total} ${resultWord}, showing ${shown}`;
      }
      return `${total} ${resultWord}`;
    }

    function isOpenShortcut(event) {
      if (
        !event ||
        normalize(event.key) !== "k" ||
        event.altKey ||
        event.shiftKey
      ) {
        return false;
      }
      return Boolean(event.metaKey || event.ctrlKey);
    }

    function mount(scope, browserRoot) {
      if (!scope || typeof scope.querySelector !== "function") {
        return null;
      }
      if (
        scope.body &&
        scope.body.classList &&
        scope.body.classList.contains("studio-page")
      ) {
        return null;
      }

      const host = browserRoot || scope.defaultView;
      const index = host && host.ETHERFI_CATALOG_INDEX;
      const dialog = scope.querySelector(DIALOG_SELECTOR);
      if (!Array.isArray(index) || !dialog) {
        return null;
      }
      if (dialog.getAttribute("data-catalog-command-mounted") === "true") {
        return null;
      }

      const input = dialog.querySelector(INPUT_SELECTOR);
      const results = dialog.querySelector(RESULTS_SELECTOR);
      const empty = dialog.querySelector(EMPTY_SELECTOR);
      const count = dialog.querySelector(COUNT_SELECTOR);
      const closeButton = dialog.querySelector(CLOSE_SELECTOR);
      if (!input || !results || !empty || !count) {
        return null;
      }

      const siteRoot = dialog.getAttribute("data-catalog-site-root") || "";
      const triggers = [...scope.querySelectorAll(OPEN_SELECTOR)];
      let restoreTarget = null;
      let dialogIsOpen = false;

      count.setAttribute("aria-live", "polite");
      count.setAttribute("aria-atomic", "true");

      function currentResultLinks() {
        return [...results.querySelectorAll(RESULT_SELECTOR)];
      }

      function applySearch() {
        const ranked = rankResources(index, input.value);
        const visible = ranked.slice(0, RESULT_LIMIT);
        renderResults(results, visible, input.value, siteRoot);
        empty.hidden = ranked.length !== 0;
        count.textContent = resultCountLabel(ranked.length, visible.length);
        return visible;
      }

      function restoreFocus() {
        const target = restoreTarget;
        restoreTarget = null;
        if (
          target &&
          target.isConnected !== false &&
          typeof target.focus === "function"
        ) {
          target.focus();
        }
      }

      function openDialog(source) {
        if (typeof dialog.showModal !== "function") {
          return false;
        }
        if (dialogIsOpen || dialog.open) {
          input.focus();
          return true;
        }

        restoreTarget = source || scope.activeElement || null;
        applySearch();
        try {
          dialog.showModal();
        } catch (error) {
          restoreTarget = null;
          return false;
        }
        dialogIsOpen = true;
        input.focus();
        return true;
      }

      function closeDialog() {
        if (typeof dialog.close !== "function") {
          return false;
        }
        dialog.close();
        dialogIsOpen = false;
        restoreFocus();
        return true;
      }

      function focusFromInput(event) {
        if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
          return;
        }
        const links = currentResultLinks();
        if (links.length === 0) {
          return;
        }
        event.preventDefault();
        const target = event.key === "ArrowDown"
          ? links[0]
          : links[links.length - 1];
        target.focus();
      }

      function focusFromResult(event) {
        if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
          return;
        }
        const links = currentResultLinks();
        const eventResult = event.target && typeof event.target.closest === "function"
          ? event.target.closest(RESULT_SELECTOR)
          : null;
        const current = eventResult || scope.activeElement;
        const currentIndex = links.indexOf(current);
        if (currentIndex < 0) {
          return;
        }

        event.preventDefault();
        const nextIndex = event.key === "ArrowDown"
          ? currentIndex + 1
          : currentIndex - 1;
        if (nextIndex < 0 || nextIndex >= links.length) {
          input.focus();
          return;
        }
        links[nextIndex].focus();
      }

      input.addEventListener("input", applySearch);
      input.addEventListener("keydown", focusFromInput);
      results.addEventListener("keydown", focusFromResult);

      triggers.forEach((trigger) => {
        trigger.addEventListener("click", (event) => {
          if (
            event.defaultPrevented ||
            (typeof event.button === "number" && event.button !== 0) ||
            event.altKey ||
            event.ctrlKey ||
            event.metaKey ||
            event.shiftKey ||
            typeof dialog.showModal !== "function"
          ) {
            return;
          }
          if (openDialog(trigger)) {
            event.preventDefault();
          }
        });
      });

      if (closeButton) {
        closeButton.addEventListener("click", () => {
          closeDialog();
        });
      }

      dialog.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
          return;
        }
        event.preventDefault();
        closeDialog();
      });
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        closeDialog();
      });
      dialog.addEventListener("close", () => {
        dialogIsOpen = false;
        restoreFocus();
      });

      scope.addEventListener("keydown", (event) => {
        if (!isOpenShortcut(event)) {
          return;
        }
        if (openDialog(null)) {
          event.preventDefault();
        }
      });

      applySearch();
      dialog.setAttribute("data-catalog-command-mounted", "true");

      return {
        applySearch,
        close: closeDialog,
        open: openDialog,
      };
    }

    function ready(scope, browserRoot) {
      if (!scope) {
        return null;
      }
      if (scope.readyState === "loading") {
        scope.addEventListener(
          "DOMContentLoaded",
          () => mount(scope, browserRoot),
          { once: true },
        );
        return null;
      }
      return mount(scope, browserRoot);
    }

    return {
      RESULT_LIMIT,
      bestMatchingHint,
      createResult,
      isOpenShortcut,
      matchesResource,
      mount,
      normalize,
      prefixResourceHref,
      rankResources,
      ready,
      relevanceTier,
      renderResults,
      resultCountLabel,
      scoreResource,
      searchResources,
      termsFor,
    };
  },
);
