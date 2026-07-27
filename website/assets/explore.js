(function (root, factory) {
  "use strict";

  const explore = factory();

  if (typeof module !== "undefined" && module.exports) {
    module.exports = explore;
  }
  if (root && root.document) {
    root.CatalogExplore = explore;
    explore.ready(root.document, root);
  }
})(
  typeof window !== "undefined"
    ? window
    : (typeof globalThis !== "undefined" ? globalThis : this),
  function () {
    "use strict";

    const PAGE_SELECTOR = "[data-explore-page]";
    const INPUT_SELECTOR = "[data-explore-search]";
    const CLEAR_SELECTOR = "[data-explore-clear]";
    const FILTER_SELECTOR = "[data-explore-filter]";
    const CARD_SELECTOR = "[data-explore-card]";
    const COUNT_SELECTOR = "[data-explore-count]";
    const EMPTY_SELECTOR = "[data-explore-empty]";

    function normalize(value) {
      return String(value == null ? "" : value)
        .toLowerCase()
        .replace(/\s+/g, " ")
        .trim();
    }

    function cleanQuery(value) {
      return String(value == null ? "" : value)
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

    function normalizeKind(value) {
      const normalized = normalize(value);
      if (normalized === "dataset" || normalized === "datasets") {
        return "dataset";
      }
      if (normalized === "dashboard" || normalized === "dashboards") {
        return "dashboard";
      }
      return "all";
    }

    function resourceSearchText(resource) {
      const item = resource || {};
      return normalize([
        item.kind,
        item.title,
        item.category,
        item.description,
        item.search,
        item.searchText,
        ...(Array.isArray(item.matchHints) ? item.matchHints : []),
      ].join(" "));
    }

    function matchesResource(resource, state) {
      const item = resource || {};
      const current = state || {};
      const selectedKind = normalizeKind(current.kind);
      const resourceKind = normalizeKind(item.kind);
      if (selectedKind !== "all" && resourceKind !== selectedKind) {
        return false;
      }

      const searchText = resourceSearchText(item);
      return termsFor(current.query).every((term) => searchText.includes(term));
    }

    function filterResources(resources, state) {
      if (!Array.isArray(resources)) {
        return [];
      }
      return resources.filter((resource) => matchesResource(resource, state));
    }

    function kindFromHash(hash) {
      const value = normalize(String(hash || "").replace(/^#/, ""));
      return normalizeKind(value);
    }

    function isCatalogHash(hash) {
      const value = normalize(String(hash || "").replace(/^#/, ""));
      return value === "" || value === "datasets" || value === "dashboards";
    }

    function hashForKind(kind) {
      const normalized = normalizeKind(kind);
      if (normalized === "dataset") {
        return "#datasets";
      }
      if (normalized === "dashboard") {
        return "#dashboards";
      }
      return "";
    }

    function queryFromSearch(search) {
      const rawSearch = String(search || "").replace(/^\?/, "");
      if (!rawSearch) {
        return "";
      }
      const params = new URLSearchParams(rawSearch);
      return cleanQuery(params.get("q") || "");
    }

    function normalizeState(state) {
      const current = state || {};
      return {
        kind: normalizeKind(current.kind),
        query: cleanQuery(current.query),
      };
    }

    function stateFromLocation(locationObject) {
      const location = locationObject || {};
      return normalizeState({
        kind: kindFromHash(location.hash),
        query: queryFromSearch(location.search),
      });
    }

    function urlForState(state, locationObject) {
      const current = normalizeState(state);
      const location = locationObject || {};
      const params = new URLSearchParams(
        String(location.search || "").replace(/^\?/, ""),
      );
      if (current.query) {
        params.set("q", current.query);
      } else {
        params.delete("q");
      }

      const search = params.toString();
      return (
        String(location.pathname || "") +
        (search ? `?${search}` : "") +
        hashForKind(current.kind)
      );
    }

    function resultCountLabel(visible, total, active) {
      const count = Number.isFinite(visible) ? visible : 0;
      const all = Number.isFinite(total) ? total : 0;
      const noun = all === 1 ? "resource" : "resources";
      if (active) {
        return `${count} of ${all} ${noun}`;
      }
      return `${all} ${noun}`;
    }

    function isEditableTarget(target) {
      if (!target) {
        return false;
      }
      const tagName = normalize(target.tagName);
      return (
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select" ||
        Boolean(target.isContentEditable)
      );
    }

    function isSearchShortcut(event) {
      return Boolean(
        event &&
        event.key === "/" &&
        !event.altKey &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.shiftKey &&
        !isEditableTarget(event.target),
      );
    }

    function mount(scope, browserRoot) {
      if (!scope || typeof scope.querySelector !== "function") {
        return null;
      }

      const page = scope.querySelector(PAGE_SELECTOR);
      if (!page || page.getAttribute("data-explore-mounted") === "true") {
        return null;
      }

      const host = browserRoot || scope.defaultView;
      const input = page.querySelector(INPUT_SELECTOR);
      const clearButton = page.querySelector(CLEAR_SELECTOR);
      const count = page.querySelector(COUNT_SELECTOR);
      const empty = page.querySelector(EMPTY_SELECTOR);
      const cards = [...page.querySelectorAll(CARD_SELECTOR)];
      const filters = [...page.querySelectorAll(FILTER_SELECTOR)];
      if (!input || !count || !empty) {
        return null;
      }

      const catalogIndex = (
        host && Array.isArray(host.ETHERFI_CATALOG_INDEX)
          ? host.ETHERFI_CATALOG_INDEX
          : []
      );
      const resources = cards.map((card, index) => {
        const indexedResource = catalogIndex[index];
        return {
          kind: card.getAttribute("data-resource-kind") || "",
          node: card,
          search: indexedResource
            ? resourceSearchText(indexedResource)
            : (card.getAttribute("data-search") || ""),
        };
      });
      let state = stateFromLocation(host && host.location);

      count.setAttribute("aria-live", "polite");
      count.setAttribute("aria-atomic", "true");

      function render() {
        let visible = 0;
        resources.forEach((resource) => {
          const matches = matchesResource(resource, state);
          resource.node.hidden = !matches;
          if (matches) {
            visible += 1;
          }
        });

        const active = Boolean(state.query || state.kind !== "all");
        count.textContent = resultCountLabel(visible, resources.length, active);
        empty.hidden = visible !== 0;
        if (clearButton) {
          clearButton.hidden = !state.query;
        }
        filters.forEach((button) => {
          const selected = normalizeKind(
            button.getAttribute("data-explore-filter"),
          ) === state.kind;
          button.setAttribute("aria-pressed", selected ? "true" : "false");
          if (button.classList && typeof button.classList.toggle === "function") {
            button.classList.toggle("active", selected);
          }
        });
        return visible;
      }

      function syncUrl(method) {
        if (
          !host ||
          !host.history ||
          typeof host.history[method] !== "function"
        ) {
          return false;
        }
        const nextUrl = urlForState(state, host.location);
        const currentUrl = (
          String((host.location && host.location.pathname) || "") +
          String((host.location && host.location.search) || "") +
          String((host.location && host.location.hash) || "")
        );
        if (nextUrl === currentUrl) {
          return false;
        }
        host.history[method]({}, "", nextUrl);
        return true;
      }

      function setState(nextState, historyMethod) {
        const activeElement = scope.activeElement;
        const focusedCard = (
          activeElement &&
          typeof activeElement.closest === "function"
        )
          ? activeElement.closest(CARD_SELECTOR)
          : null;
        state = normalizeState(nextState);
        input.value = state.query;
        const visible = render();
        if (focusedCard && focusedCard.hidden) {
          const activeFilter = filters.find((button) => (
            normalizeKind(button.getAttribute("data-explore-filter")) === state.kind
          ));
          const focusTarget = activeFilter || input;
          if (typeof focusTarget.focus === "function") {
            focusTarget.focus();
          }
        }
        if (historyMethod) {
          syncUrl(historyMethod);
        }
        return visible;
      }

      function applyLocation() {
        if (!isCatalogHash(host && host.location && host.location.hash)) {
          return state;
        }
        return setState(stateFromLocation(host && host.location));
      }

      function applyHashLocation() {
        return applyLocation();
      }

      input.addEventListener("input", () => {
        setState(
          { kind: state.kind, query: input.value },
          "replaceState",
        );
      });
      input.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !state.query) {
          return;
        }
        event.preventDefault();
        setState({ kind: state.kind, query: "" }, "replaceState");
        input.focus();
      });

      if (clearButton) {
        clearButton.addEventListener("click", () => {
          setState({ kind: state.kind, query: "" }, "replaceState");
          input.focus();
        });
      }

      filters.forEach((button) => {
        button.addEventListener("click", () => {
          const nextKind = normalizeKind(
            button.getAttribute("data-explore-filter"),
          );
          if (nextKind === state.kind) {
            return;
          }
          setState({ kind: nextKind, query: state.query }, "pushState");
        });
      });

      scope.addEventListener("keydown", (event) => {
        if (event.defaultPrevented) {
          return;
        }
        if (event.key === "Escape" && state.query) {
          event.preventDefault();
          setState({ kind: state.kind, query: "" }, "replaceState");
          input.focus();
          return;
        }
        if (!isSearchShortcut(event)) {
          return;
        }
        event.preventDefault();
        input.focus();
      });

      if (host && typeof host.addEventListener === "function") {
        host.addEventListener("popstate", applyLocation);
        host.addEventListener("hashchange", applyHashLocation);
      }

      input.value = state.query;
      render();
      page.setAttribute("data-explore-mounted", "true");

      return {
        applyLocation,
        render,
        setState,
        state() {
          return { ...state };
        },
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
      cleanQuery,
      filterResources,
      hashForKind,
      isCatalogHash,
      isSearchShortcut,
      kindFromHash,
      matchesResource,
      mount,
      normalize,
      normalizeKind,
      ready,
      resourceSearchText,
      resultCountLabel,
      stateFromLocation,
      termsFor,
      urlForState,
    };
  },
);
