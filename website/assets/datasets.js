(function (root, factory) {
  const browser = factory(root);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = browser;
  }
  if (root) {
    root.DatasetBrowser = browser;
  }
  if (typeof document !== "undefined") {
    browser.ready(document);
  }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  const PAGE_SELECTOR = "[data-datasets-page]";
  const SEARCH_SELECTOR = "#dataset-search";
  const CARD_SELECTOR = "[data-dataset-card]";
  const NAV_SELECTOR = "[data-dataset-nav]";
  const SECTION_SELECTOR = "[data-dataset-category-section]";
  const OVERVIEW_SELECTOR = "[data-dataset-overview]";
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

  function matchesSearch(card, query) {
    const terms = termsFor(query);
    if (terms.length === 0) {
      return true;
    }
    const searchableText = normalize(card.search);
    return terms.every((term) => searchableText.includes(term));
  }

  function setActiveNav(buttons, activeCategory) {
    buttons.forEach((button) => {
      const active = button.dataset.datasetNav === activeCategory;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function cardDataFromElement(element) {
    return {
      category: element.dataset.category || "",
      element,
      search: element.dataset.search || "",
    };
  }

  function filterCards(cards, stateOrQuery) {
    const state = typeof stateOrQuery === "object" && stateOrQuery !== null
      ? stateOrQuery
      : { activeCategory: "all", query: stateOrQuery };
    const activeCategory = state.activeCategory || "all";
    return cards.map((card) => ({
      card,
      visible: matchesSearch(card, state.query) && (
        activeCategory === "all" ||
        activeCategory === "overview" ||
        card.category === activeCategory
      ),
    }));
  }

  function setVisible(element, visible) {
    if (!element) {
      return;
    }
    element.hidden = !visible;
    element.style.display = visible ? "" : "none";
  }

  function mount(scope) {
    const page = scope.querySelector(PAGE_SELECTOR);
    if (!page || page.dataset.datasetsMounted === "true") {
      return;
    }
    page.dataset.datasetsMounted = "true";

    const searchInput = page.querySelector(SEARCH_SELECTOR);
    const cards = [...page.querySelectorAll(CARD_SELECTOR)].map(cardDataFromElement);
    const navButtons = [...page.querySelectorAll(NAV_SELECTOR)];
    const sections = [...page.querySelectorAll(SECTION_SELECTOR)];
    const overview = page.querySelector(OVERVIEW_SELECTOR);
    const count = page.querySelector(COUNT_SELECTOR);
    const emptyState = page.querySelector(EMPTY_SELECTOR);
    const state = {
      activeCategory: "overview",
      query: "",
    };

    if (!searchInput || cards.length === 0 || !count || !emptyState) {
      console.warn("[ether.fi datasets] Browser controls missing", {
        inputFound: Boolean(searchInput),
        cardCount: cards.length,
        countFound: Boolean(count),
        emptyStateFound: Boolean(emptyState),
      });
    }

    function applyFilters() {
      state.query = searchInput ? searchInput.value : "";
      const hasQuery = termsFor(state.query).length > 0;
      let visibleCount = 0;

      if (hasQuery) {
        setVisible(overview, false);
        const results = filterCards(cards, state.query);
        const visibleByCategory = new Map();

        results.forEach((result) => {
          setVisible(result.card.element, result.visible);
          if (result.visible) {
            visibleCount += 1;
            visibleByCategory.set(result.card.category, true);
          }
        });

        sections.forEach((section) => {
          setVisible(section, Boolean(visibleByCategory.get(section.dataset.category || "")));
        });
      } else {
        setVisible(overview, state.activeCategory === "overview");
        cards.forEach((card) => {
          setVisible(card.element, true);
        });
        sections.forEach((section) => {
          const visible = state.activeCategory !== "overview" && section.dataset.category === state.activeCategory;
          setVisible(section, visible);
          if (visible) {
            visibleCount = section.querySelectorAll(CARD_SELECTOR).length;
          }
        });
        if (state.activeCategory === "overview") {
          visibleCount = cards.length;
        }
      }

      setActiveNav(navButtons, state.activeCategory);
      if (count) {
        count.textContent = hasQuery ? `${visibleCount} shown` : `${visibleCount} datasets`;
      }
      if (emptyState) {
        setVisible(emptyState, hasQuery && visibleCount === 0);
      }
    }

    if (root) {
      root.__etherfiDatasetBrowserDebug = () => ({
        inputFound: Boolean(searchInput),
        cardCount: cards.length,
        selectedCategory: state.activeCategory,
        visibleCount: cards.filter((card) => !card.element.hidden && card.element.style.display !== "none").length,
      });
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilters);
    }

    navButtons.forEach((button) => {
      button.addEventListener("click", () => {
        state.activeCategory = button.dataset.datasetNav || "overview";
        applyFilters();
      });
    });

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
    filterCards,
    matchesSearch,
    mount,
    normalize,
    ready,
    termsFor,
  };
});
