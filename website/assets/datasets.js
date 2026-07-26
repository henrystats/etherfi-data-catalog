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
  const CATEGORY_FRAGMENT_PREFIX = "dataset-view-";

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

  function normalizedFragment(hash) {
    const raw = String(hash || "").replace(/^#/, "");
    if (!raw) {
      return "";
    }
    try {
      return decodeURIComponent(raw);
    } catch (error) {
      return raw;
    }
  }

  function categoryFragment(category) {
    const value = String(category || "overview").replace(/_/g, "-");
    return `${CATEGORY_FRAGMENT_PREFIX}${value}`;
  }

  function categoryForHash(hash, availableCategories) {
    const fragment = normalizedFragment(hash);
    const categories = Array.isArray(availableCategories) ? availableCategories : [];
    return categories.find((category) => categoryFragment(category) === fragment) || "";
  }

  function categoryTargetForHash(hash, availableCategories) {
    const fragment = normalizedFragment(hash);
    const category = categoryForHash(hash, availableCategories);
    if (fragment && !category) {
      return null;
    }
    return category || "overview";
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

  function activeNavForState(state) {
    if (termsFor(state && state.query).length > 0) {
      return "";
    }
    return (state && state.activeCategory) || "overview";
  }

  function selectCategory(state, searchInput, category) {
    state.activeCategory = category || "overview";
    state.query = "";
    if (searchInput) {
      searchInput.value = "";
    }
    return state;
  }

  function shouldRestoreCategoryFocus(activeElement, navButtons) {
    if (!activeElement) {
      return false;
    }
    const buttons = Array.isArray(navButtons) ? navButtons : [];
    if (buttons.includes(activeElement)) {
      return true;
    }
    return Boolean(
      typeof activeElement.closest === "function" &&
      activeElement.closest(`${OVERVIEW_SELECTOR}, ${SECTION_SELECTOR}`),
    );
  }

  function updateCategoryHash(category, replace) {
    if (!root || !root.location) {
      return;
    }
    const nextHash = `#${encodeURIComponent(categoryFragment(category))}`;
    if (root.location.hash === nextHash) {
      return;
    }
    const method = replace ? "replaceState" : "pushState";
    if (root.history && typeof root.history[method] === "function") {
      root.history[method](null, "", nextHash);
      return;
    }
    root.location.hash = nextHash;
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

    const searchInput = page.querySelector(SEARCH_SELECTOR);
    const cards = [...page.querySelectorAll(CARD_SELECTOR)].map(cardDataFromElement);
    const navButtons = [...page.querySelectorAll(NAV_SELECTOR)];
    const sections = [...page.querySelectorAll(SECTION_SELECTOR)];
    const overview = page.querySelector(OVERVIEW_SELECTOR);
    const featuredCount = overview
      ? overview.querySelectorAll(".dataset-browser-card").length
      : 0;
    const count = page.querySelector(COUNT_SELECTOR);
    const emptyState = page.querySelector(EMPTY_SELECTOR);
    const availableCategories = navButtons.map(
      (button) => button.dataset.datasetNav,
    );
    const initialCategory = categoryForHash(
      root && root.location ? root.location.hash : "",
      availableCategories,
    );
    const state = {
      activeCategory: initialCategory || "overview",
      query: "",
    };

    if (!searchInput || cards.length === 0 || !count || !emptyState) {
      console.warn("[ether.fi datasets] Browser controls missing", {
        inputFound: Boolean(searchInput),
        cardCount: cards.length,
        countFound: Boolean(count),
        emptyStateFound: Boolean(emptyState),
      });
      return;
    }
    sections.forEach((section) => {
      section.removeAttribute("data-default-hidden");
    });

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
          setVisible(section.querySelector(".dataset-view-count"), false);
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
          setVisible(section.querySelector(".dataset-view-count"), true);
        });
        if (state.activeCategory === "overview") {
          visibleCount = featuredCount;
        }
      }

      setActiveNav(navButtons, activeNavForState(state));
      if (count) {
        if (hasQuery) {
          count.textContent = `${visibleCount} dataset ${visibleCount === 1 ? "result" : "results"} across all categories`;
        } else if (state.activeCategory === "overview") {
          count.textContent = `${featuredCount} featured datasets shown`;
        } else {
          count.textContent = `${visibleCount} ${visibleCount === 1 ? "dataset" : "datasets"} shown in the selected category`;
        }
      }
      if (emptyState) {
        setVisible(emptyState, hasQuery && visibleCount === 0);
      }
    }

    function scrollToCategory(category) {
      const fragment = categoryFragment(category);
      const target = page.querySelector(`#${fragment}`);
      if (!target || typeof target.scrollIntoView !== "function") {
        return;
      }
      const activeButton = navButtons.find(
        (button) => button.dataset.datasetNav === category,
      );
      const scroll = () => {
        target.scrollIntoView({ block: "start" });
        if (activeButton && typeof activeButton.scrollIntoView === "function") {
          activeButton.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
      };
      if (root && typeof root.requestAnimationFrame === "function") {
        root.requestAnimationFrame(() => root.requestAnimationFrame(scroll));
      } else {
        scroll();
      }
    }

    function syncFromLocation() {
      const hash = root && root.location ? root.location.hash : "";
      const nextCategory = categoryTargetForHash(hash, availableCategories);
      if (!nextCategory) {
        return;
      }
      const searchValue = searchInput ? searchInput.value : "";
      if (
        state.activeCategory === nextCategory &&
        !state.query &&
        !searchValue
      ) {
        return;
      }
      const activeElement = scope.activeElement;
      const restoreFocus = shouldRestoreCategoryFocus(
        activeElement,
        navButtons,
      );
      selectCategory(state, searchInput, nextCategory);
      applyFilters();
      if (restoreFocus) {
        const activeButton = navButtons.find(
          (button) => button.dataset.datasetNav === nextCategory,
        );
        if (activeButton && typeof activeButton.focus === "function") {
          activeButton.focus();
        }
      }
      if (normalizedFragment(hash)) {
        scrollToCategory(nextCategory);
      }
    }

    if (root) {
      root.__etherfiDatasetBrowserDebug = () => ({
        inputFound: Boolean(searchInput),
        cardCount: cards.length,
        activeNav: activeNavForState(state),
        query: state.query,
        selectedCategory: state.activeCategory,
        visibleCount: cards.filter((card) => !card.element.hidden && card.element.style.display !== "none").length,
      });
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilters);
    }

    navButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const category = button.dataset.datasetNav;
        selectCategory(state, searchInput, category);
        applyFilters();
        updateCategoryHash(category, false);
        scrollToCategory(category);
      });
    });

    applyFilters();
    page.dataset.datasetsMounted = "true";
    if (initialCategory) {
      scrollToCategory(initialCategory);
    }
    if (root && typeof root.addEventListener === "function") {
      root.addEventListener("hashchange", syncFromLocation);
      root.addEventListener("popstate", syncFromLocation);
    }
  }

  function ready(scope) {
    if (!scope) {
      return;
    }
    if (scope.readyState === "loading") {
      scope.addEventListener("DOMContentLoaded", () => mount(scope), { once: true });
      return;
    }
    mount(scope);
  }

  return {
    activeNavForState,
    categoryForHash,
    categoryFragment,
    categoryTargetForHash,
    filterCards,
    matchesSearch,
    mount,
    normalize,
    ready,
    selectCategory,
    shouldRestoreCategoryFocus,
    termsFor,
  };
});
