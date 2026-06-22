(function (root, factory) {
  const browser = factory(root);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = browser;
  }
  if (root) {
    root.DashboardBrowser = browser;
  }
  if (typeof document !== "undefined") {
    browser.ready(document);
  }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  const PAGE_SELECTOR = "[data-dashboards-page]";
  const SEARCH_SELECTOR = "#dashboard-search";
  const CARD_SELECTOR = "[data-dashboard-card]";
  const CORE_CARD_SELECTOR = "[data-dashboard-core-card]";
  const NAV_SELECTOR = "[data-dashboard-nav]";
  const SECTION_SELECTOR = "[data-dashboard-section]";
  const COUNT_SELECTOR = "#dashboard-count";
  const EMPTY_SELECTOR = "#dashboard-empty-state";

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

  function cardDataFromElement(element) {
    return {
      category: element.dataset.dashboardCategory || "",
      element,
      search: element.dataset.search || "",
    };
  }

  function filterCards(cards, query) {
    return cards.map((card) => ({
      card,
      visible: matchesSearch(card, query),
    }));
  }

  function setVisible(element, visible) {
    if (!element) {
      return;
    }
    element.hidden = !visible;
    element.style.display = visible ? "" : "none";
  }

  function setActiveNav(buttons, activeGroup) {
    buttons.forEach((button) => {
      const active = button.dataset.dashboardNav === activeGroup;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function countVisibleCards(section) {
    if (!section) {
      return 0;
    }
    return [...section.querySelectorAll(`${CARD_SELECTOR}, ${CORE_CARD_SELECTOR}`)].filter(
      (card) => !card.hidden && card.style.display !== "none",
    ).length;
  }

  function mount(scope) {
    const page = scope.querySelector(PAGE_SELECTOR);
    if (!page || page.dataset.dashboardsMounted === "true") {
      return;
    }
    page.dataset.dashboardsMounted = "true";

    const searchInput = page.querySelector(SEARCH_SELECTOR);
    const cards = [...page.querySelectorAll(CARD_SELECTOR)].map(cardDataFromElement);
    const coreCards = [...page.querySelectorAll(CORE_CARD_SELECTOR)];
    const navButtons = [...page.querySelectorAll(NAV_SELECTOR)];
    const sections = [...page.querySelectorAll(SECTION_SELECTOR)];
    const count = page.querySelector(COUNT_SELECTOR);
    const emptyState = page.querySelector(EMPTY_SELECTOR);
    const state = {
      activeGroup: "core",
      query: "",
    };

    if (!searchInput || !count || !emptyState) {
      console.warn("[ether.fi dashboards] Browser controls missing", {
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
        coreCards.forEach((card) => setVisible(card, false));
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
          const group = section.dataset.dashboardGroup || "";
          setVisible(section, group !== "core" && Boolean(visibleByCategory.get(group)));
        });
      } else {
        cards.forEach((card) => setVisible(card.element, true));
        coreCards.forEach((card) => setVisible(card, true));
        sections.forEach((section) => {
          const visible = section.dataset.dashboardGroup === state.activeGroup;
          setVisible(section, visible);
          if (visible) {
            visibleCount = countVisibleCards(section);
          }
        });
      }

      setActiveNav(navButtons, state.activeGroup);
      if (count) {
        const suffix = visibleCount === 1 ? "dashboard" : "dashboards";
        count.textContent = hasQuery ? `${visibleCount} shown` : `${visibleCount} ${suffix}`;
      }
      if (emptyState) {
        setVisible(emptyState, hasQuery && visibleCount === 0);
      }
    }

    if (root) {
      root.__etherfiDashboardBrowserDebug = () => ({
        inputFound: Boolean(searchInput),
        cardCount: cards.length,
        coreCardCount: coreCards.length,
        selectedGroup: state.activeGroup,
        visibleCount: cards.filter((card) => !card.element.hidden && card.element.style.display !== "none").length,
      });
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilters);
    }

    navButtons.forEach((button) => {
      button.addEventListener("click", () => {
        state.activeGroup = button.dataset.dashboardNav || "core";
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
