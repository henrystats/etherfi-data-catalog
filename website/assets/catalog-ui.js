(function (root, factory) {
  const catalogUI = factory(root);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = catalogUI;
  }
  if (root) {
    root.CatalogUI = catalogUI;
  }
  if (typeof document !== "undefined") {
    catalogUI.ready(document);
  }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  const SEARCH_SELECTOR = "[data-catalog-search]";
  const CLEAR_SELECTOR = "[data-search-clear]";
  const INFO_HINT_SELECTOR = "[data-info-hint]";
  const DETAIL_TABS_SELECTOR = "[data-detail-tabs]";
  const DETAIL_TAB_LIST_SELECTOR = "[data-detail-tab-list]";
  const DETAIL_TAB_SELECTOR = "[data-detail-tab]";
  const DETAIL_PANEL_SELECTOR = "[data-detail-tab-panel]";
  const TAB_HASH_ALIASES = Object.freeze({
    "about-table": "about",
    "dataset-caveats": "about",
    "dataset-schema": "schema",
    "supporting-tables": "related-resources",
    "dashboard-metrics": "metrics",
    "dashboard-tags": "tags",
  });

  function isEditableTarget(target) {
    if (!target || typeof target.matches !== "function") {
      return false;
    }
    return target.matches("input, textarea, select, [contenteditable='true']");
  }

  function shortcutAction(event, context) {
    const key = String((event && event.key) || "");
    const modified = Boolean(event && (event.altKey || event.ctrlKey || event.metaKey));
    const state = context || {};

    if (
      key === "/" &&
      !modified &&
      state.hasSearch &&
      !state.editableTarget
    ) {
      return "focus-search";
    }
    if (key !== "Escape") {
      return "none";
    }
    if (state.hintFocused) {
      return "dismiss-hint";
    }
    if (!state.activeSearch) {
      return "none";
    }
    return state.searchHasValue ? "clear-search" : "blur-search";
  }

  function dispatchInput(input) {
    const ownerWindow = input.ownerDocument && input.ownerDocument.defaultView;
    const EventConstructor = (ownerWindow && ownerWindow.Event) || (root && root.Event);
    if (EventConstructor) {
      input.dispatchEvent(new EventConstructor("input", { bubbles: true }));
    }
  }

  function clearSearch(input, keepFocus) {
    if (!input) {
      return;
    }
    input.value = "";
    dispatchInput(input);
    if (keepFocus && typeof input.focus === "function") {
      input.focus();
    }
  }

  function setHintExpanded(hint, expanded) {
    if (!hint) {
      return;
    }
    hint.classList.toggle("is-open", expanded);
    hint.setAttribute("aria-expanded", String(expanded));
  }

  function closeUnfocusedHints(infoHints, target) {
    const focusedHint = target && typeof target.closest === "function"
      ? target.closest(INFO_HINT_SELECTOR)
      : null;
    infoHints.forEach((hint) => {
      if (hint !== focusedHint) {
        setHintExpanded(hint, false);
      }
    });
  }

  function copyWithFallback(text, scope) {
    if (!scope || !scope.body || typeof scope.createElement !== "function") {
      return Promise.resolve(false);
    }
    const textarea = scope.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "-9999px";
    textarea.style.left = "-9999px";
    scope.body.appendChild(textarea);
    textarea.select();

    try {
      return Promise.resolve(Boolean(scope.execCommand && scope.execCommand("copy")));
    } finally {
      scope.body.removeChild(textarea);
    }
  }

  function copyText(text, scope) {
    const browserNavigator = root && root.navigator;
    if (
      browserNavigator &&
      browserNavigator.clipboard &&
      typeof browserNavigator.clipboard.writeText === "function" &&
      root.isSecureContext
    ) {
      return browserNavigator.clipboard.writeText(text)
        .then(() => true)
        .catch(() => copyWithFallback(text, scope));
    }
    return copyWithFallback(text, scope);
  }

  function visibleSearch(scope) {
    return [...scope.querySelectorAll(SEARCH_SELECTOR)].find((input) => {
      if (input.disabled || input.hidden) {
        return false;
      }
      return typeof input.getClientRects !== "function" || input.getClientRects().length > 0;
    }) || null;
  }

  function normalizedHashValue(value) {
    const raw = String(value || "").replace(/^#/, "");
    if (!raw) {
      return "";
    }
    try {
      return decodeURIComponent(raw);
    } catch (error) {
      return raw;
    }
  }

  function tabValueForHash(hash, availableValues) {
    const values = Array.isArray(availableValues) ? availableValues : [];
    const normalized = normalizedHashValue(hash);
    const candidate = TAB_HASH_ALIASES[normalized] || normalized;
    return values.includes(candidate) ? candidate : "";
  }

  function tabIndexForKey(key, currentIndex, total) {
    if (total < 1 || currentIndex < 0) {
      return -1;
    }
    if (key === "ArrowRight") {
      return (currentIndex + 1) % total;
    }
    if (key === "ArrowLeft") {
      return (currentIndex - 1 + total) % total;
    }
    if (key === "Home") {
      return 0;
    }
    if (key === "End") {
      return total - 1;
    }
    return -1;
  }

  function setActiveTab(group, value, options) {
    if (!group || typeof group.querySelectorAll !== "function") {
      return false;
    }
    const tabs = [...group.querySelectorAll(DETAIL_TAB_SELECTOR)];
    const panels = [...group.querySelectorAll(DETAIL_PANEL_SELECTOR)];
    const selectedTab = tabs.find((tab) => tab.dataset.detailTab === value);
    const selectedPanel = panels.find((panel) => panel.dataset.detailTabPanel === value);
    if (!selectedTab || !selectedPanel) {
      return false;
    }

    tabs.forEach((tab) => {
      const selected = tab === selectedTab;
      tab.classList.toggle("is-active", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.setAttribute("tabindex", selected ? "0" : "-1");
    });
    panels.forEach((panel) => {
      const selected = panel === selectedPanel;
      panel.hidden = !selected;
      if (selected && panel.dataset.emptyTabPanel !== "true") {
        panel.setAttribute("tabindex", "0");
      } else {
        panel.removeAttribute("tabindex");
      }
    });
    group.dataset.activeTab = value;

    if (options && options.focus && typeof selectedTab.focus === "function") {
      selectedTab.focus();
    }
    return true;
  }

  function updateTabHash(value, replace) {
    if (!root || !root.location) {
      return;
    }
    const nextHash = `#${encodeURIComponent(value)}`;
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

  function scrollToTabHash(group, hash) {
    if (!group || typeof group.querySelectorAll !== "function") {
      return;
    }
    const targetId = normalizedHashValue(hash);
    if (!targetId) {
      return;
    }
    const target = [...group.querySelectorAll("[id]")].find(
      (candidate) => candidate.id === targetId,
    );
    if (!target || typeof target.scrollIntoView !== "function") {
      return;
    }
    const scroll = () => target.scrollIntoView({ block: "start" });
    if (root && typeof root.requestAnimationFrame === "function") {
      root.requestAnimationFrame(scroll);
    } else {
      scroll();
    }
  }

  function mountDetailTabs(scope) {
    if (!scope || typeof scope.querySelectorAll !== "function") {
      return;
    }

    [...scope.querySelectorAll(DETAIL_TABS_SELECTOR)].forEach((group) => {
      if (group.dataset.detailTabsMounted === "true") {
        return;
      }
      const tabList = group.querySelector(DETAIL_TAB_LIST_SELECTOR);
      const tabs = [...group.querySelectorAll(DETAIL_TAB_SELECTOR)];
      const panels = [...group.querySelectorAll(DETAIL_PANEL_SELECTOR)];
      const tabValues = tabs.map((tab) => tab.dataset.detailTab);
      const panelValues = panels.map((panel) => panel.dataset.detailTabPanel);
      const tabIds = tabs.map((tab) => tab.id);
      const valid = Boolean(
        tabList &&
        tabs.length >= 2 &&
        panels.length === tabs.length &&
        new Set(tabValues).size === tabs.length &&
        new Set(panelValues).size === panels.length &&
        new Set(tabIds).size === tabs.length &&
        tabIds.every(Boolean) &&
        tabValues.every((value) => /^[a-z][a-z0-9-]*$/.test(String(value || ""))) &&
        tabs.every((tab) => {
          const value = tab.dataset.detailTab;
          const panel = panels.find(
            (candidate) => candidate.dataset.detailTabPanel === value,
          );
          return Boolean(
            panel &&
            panel.id === tab.dataset.detailTabControls &&
            panel.dataset.detailTabLabelledby === tab.id
          );
        }),
      );
      if (!valid) {
        return;
      }

      const values = tabValues;
      const hashValue = tabValueForHash(
        root && root.location ? root.location.hash : "",
        values,
      );
      const defaultValue = values.includes(group.dataset.defaultTab)
        ? group.dataset.defaultTab
        : values[0];
      if (!setActiveTab(group, hashValue || defaultValue)) {
        return;
      }

      tabList.setAttribute("role", "tablist");
      tabList.setAttribute(
        "aria-label",
        group.dataset.detailTabsLabel || "Detail sections",
      );
      tabs.forEach((tab) => {
        tab.setAttribute("role", "tab");
        tab.setAttribute("aria-controls", tab.dataset.detailTabControls);
      });
      panels.forEach((panel) => {
        panel.setAttribute("role", "tabpanel");
        panel.setAttribute(
          "aria-labelledby",
          panel.dataset.detailTabLabelledby,
        );
      });
      setActiveTab(group, hashValue || defaultValue);
      tabList.hidden = false;
      group.dataset.detailTabsMounted = "true";
      if (hashValue) {
        scrollToTabHash(group, root && root.location ? root.location.hash : "");
      }

      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => {
          const value = tab.dataset.detailTab;
          if (setActiveTab(group, value)) {
            updateTabHash(value, false);
            scrollToTabHash(group, `#${value}`);
          }
        });
        tab.addEventListener("keydown", (event) => {
          const nextIndex = tabIndexForKey(event.key, index, tabs.length);
          if (nextIndex < 0) {
            return;
          }
          event.preventDefault();
          const nextValue = tabs[nextIndex].dataset.detailTab;
          if (setActiveTab(group, nextValue, { focus: true })) {
            updateTabHash(nextValue, true);
          }
        });
      });

      const syncFromLocation = () => {
        const hash = root && root.location ? root.location.hash : "";
        const value = tabValueForHash(hash, values);
        if (normalizedHashValue(hash) && !value) {
          return;
        }
        const nextValue = value || defaultValue;
        if (group.dataset.activeTab === nextValue) {
          return;
        }
        const ownerDocument = group.ownerDocument || scope;
        const activeElement = ownerDocument && ownerDocument.activeElement;
        const shouldRestoreFocus = Boolean(
          activeElement &&
          typeof group.contains === "function" &&
          group.contains(activeElement),
        );
        setActiveTab(
          group,
          nextValue,
          shouldRestoreFocus ? { focus: true } : undefined,
        );
        if (value) {
          scrollToTabHash(group, hash);
        }
      };
      if (root && typeof root.addEventListener === "function") {
        root.addEventListener("hashchange", syncFromLocation);
        root.addEventListener("popstate", syncFromLocation);
      }
    });
  }

  function mount(scope) {
    if (!scope || !scope.documentElement || scope.documentElement.dataset.catalogUiMounted === "true") {
      return;
    }
    scope.documentElement.dataset.catalogUiMounted = "true";
    mountDetailTabs(scope);

    scope.querySelectorAll(CLEAR_SELECTOR).forEach((button) => {
      button.addEventListener("click", () => {
        const shell = button.closest("[data-search-shell]");
        const input = shell ? shell.querySelector(SEARCH_SELECTOR) : null;
        clearSearch(input, true);
      });
    });

    const infoHints = [...scope.querySelectorAll(INFO_HINT_SELECTOR)];
    scope.addEventListener("focusin", (event) => {
      closeUnfocusedHints(infoHints, event.target);
    });
    scope.addEventListener("click", (event) => {
      const clickedHint = event.target && typeof event.target.closest === "function"
        ? event.target.closest(INFO_HINT_SELECTOR)
        : null;
      if (clickedHint) {
        const willExpand = clickedHint.getAttribute("aria-expanded") !== "true";
        infoHints.forEach((hint) => setHintExpanded(hint, hint === clickedHint && willExpand));
        return;
      }
      infoHints.forEach((hint) => setHintExpanded(hint, false));
    });

    scope.addEventListener("keydown", (event) => {
      const activeElement = scope.activeElement;
      const searchInput = activeElement && activeElement.matches &&
        activeElement.matches(SEARCH_SELECTOR)
        ? activeElement
        : null;
      const action = shortcutAction(event, {
        activeSearch: Boolean(searchInput),
        editableTarget: isEditableTarget(event.target),
        hasSearch: Boolean(visibleSearch(scope)),
        hintFocused: Boolean(
          activeElement &&
          activeElement.matches &&
          activeElement.matches(INFO_HINT_SELECTOR)
        ),
        searchHasValue: Boolean(searchInput && searchInput.value),
      });

      if (action === "focus-search") {
        event.preventDefault();
        const input = visibleSearch(scope);
        if (input) {
          input.focus();
        }
      } else if (action === "clear-search") {
        event.preventDefault();
        clearSearch(searchInput, true);
      } else if (action === "blur-search" || action === "dismiss-hint") {
        event.preventDefault();
        if (action === "dismiss-hint") {
          setHintExpanded(activeElement, false);
        }
        if (activeElement && typeof activeElement.blur === "function") {
          activeElement.blur();
        }
      }
    });
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
    clearSearch,
    closeUnfocusedHints,
    copyText,
    isEditableTarget,
    mount,
    mountDetailTabs,
    normalizedHashValue,
    ready,
    setActiveTab,
    setHintExpanded,
    shortcutAction,
    scrollToTabHash,
    tabIndexForKey,
    tabValueForHash,
    updateTabHash,
  };
});
