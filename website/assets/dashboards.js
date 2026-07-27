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
  const GROUP_FRAGMENT_PREFIX = "dashboard-group-";

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

  function groupFragment(group) {
    const value = String(group || "core").replace(/_/g, "-");
    return `${GROUP_FRAGMENT_PREFIX}${value}`;
  }

  function groupForHash(hash, availableGroups) {
    const fragment = normalizedFragment(hash);
    const groups = Array.isArray(availableGroups) ? availableGroups : [];
    return groups.find((group) => groupFragment(group) === fragment) || "";
  }

  function groupTargetForHash(hash, availableGroups) {
    const fragment = normalizedFragment(hash);
    const group = groupForHash(hash, availableGroups);
    if (fragment && !group) {
      return null;
    }
    return group || "core";
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

  function activeNavForState(state) {
    if (termsFor(state && state.query).length > 0) {
      return "";
    }
    return (state && state.activeGroup) || "core";
  }

  function selectGroup(state, searchInput, group) {
    state.activeGroup = group || "core";
    state.query = "";
    if (searchInput) {
      searchInput.value = "";
    }
    return state;
  }

  function shouldRestoreGroupFocus(activeElement, navButtons) {
    if (!activeElement) {
      return false;
    }
    const buttons = Array.isArray(navButtons) ? navButtons : [];
    if (buttons.includes(activeElement)) {
      return true;
    }
    return Boolean(
      typeof activeElement.closest === "function" &&
      activeElement.closest(SECTION_SELECTOR),
    );
  }

  function updateGroupHash(group, replace) {
    if (!root || !root.location) {
      return;
    }
    const nextHash = `#${encodeURIComponent(groupFragment(group))}`;
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

    const searchInput = page.querySelector(SEARCH_SELECTOR);
    const cards = [...page.querySelectorAll(CARD_SELECTOR)].map(cardDataFromElement);
    const coreCards = [...page.querySelectorAll(CORE_CARD_SELECTOR)];
    const navButtons = [...page.querySelectorAll(NAV_SELECTOR)];
    const sections = [...page.querySelectorAll(SECTION_SELECTOR)];
    const count = page.querySelector(COUNT_SELECTOR);
    const emptyState = page.querySelector(EMPTY_SELECTOR);
    const availableGroups = navButtons.map(
      (button) => button.dataset.dashboardNav,
    );
    const initialGroup = groupForHash(
      root && root.location ? root.location.hash : "",
      availableGroups,
    );
    const state = {
      activeGroup: initialGroup || "core",
      query: "",
    };

    if (!searchInput || !count || !emptyState) {
      console.warn("[ether.fi dashboards] Browser controls missing", {
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
          setVisible(section.querySelector(".dataset-view-count"), false);
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
          setVisible(section.querySelector(".dataset-view-count"), true);
        });
      }

      setActiveNav(navButtons, activeNavForState(state));
      if (count) {
        const suffix = visibleCount === 1 ? "dashboard" : "dashboards";
        if (hasQuery) {
          count.textContent = `${visibleCount} dashboard ${visibleCount === 1 ? "result" : "results"} across all categories`;
        } else if (state.activeGroup === "core") {
          count.textContent = `${visibleCount} core dashboards shown`;
        } else {
          count.textContent = `${visibleCount} ${suffix} shown in the selected category`;
        }
      }
      if (emptyState) {
        setVisible(emptyState, hasQuery && visibleCount === 0);
      }
    }

    function scrollToGroup(group) {
      const fragment = groupFragment(group);
      const target = page.querySelector(`#${fragment}`);
      if (!target || typeof target.scrollIntoView !== "function") {
        return;
      }
      const activeButton = navButtons.find(
        (button) => button.dataset.dashboardNav === group,
      );
      const scroll = () => {
        if (activeButton && typeof activeButton.scrollIntoView === "function") {
          activeButton.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
        target.scrollIntoView({ block: "start" });
      };
      if (root && typeof root.requestAnimationFrame === "function") {
        root.requestAnimationFrame(() => root.requestAnimationFrame(scroll));
      } else {
        scroll();
      }
    }

    function syncFromLocation() {
      const hash = root && root.location ? root.location.hash : "";
      const nextGroup = groupTargetForHash(hash, availableGroups);
      if (!nextGroup) {
        return;
      }
      const searchValue = searchInput ? searchInput.value : "";
      if (
        state.activeGroup === nextGroup &&
        !state.query &&
        !searchValue
      ) {
        return;
      }
      const activeElement = scope.activeElement;
      const restoreFocus = shouldRestoreGroupFocus(
        activeElement,
        navButtons,
      );
      selectGroup(state, searchInput, nextGroup);
      applyFilters();
      if (restoreFocus) {
        const activeButton = navButtons.find(
          (button) => button.dataset.dashboardNav === nextGroup,
        );
        if (activeButton && typeof activeButton.focus === "function") {
          activeButton.focus();
        }
      }
      if (normalizedFragment(hash)) {
        scrollToGroup(nextGroup);
      }
    }

    if (root) {
      root.__etherfiDashboardBrowserDebug = () => ({
        inputFound: Boolean(searchInput),
        cardCount: cards.length,
        coreCardCount: coreCards.length,
        activeNav: activeNavForState(state),
        query: state.query,
        selectedGroup: state.activeGroup,
        visibleCount: cards.filter((card) => !card.element.hidden && card.element.style.display !== "none").length,
      });
    }

    if (searchInput) {
      searchInput.addEventListener("input", applyFilters);
    }

    navButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const group = button.dataset.dashboardNav;
        selectGroup(state, searchInput, group);
        applyFilters();
        updateGroupHash(group, false);
        scrollToGroup(group);
      });
    });

    applyFilters();
    page.dataset.dashboardsMounted = "true";
    if (initialGroup) {
      scrollToGroup(initialGroup);
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
    filterCards,
    groupForHash,
    groupFragment,
    groupTargetForHash,
    matchesSearch,
    mount,
    normalize,
    ready,
    selectGroup,
    shouldRestoreGroupFocus,
    termsFor,
  };
});
