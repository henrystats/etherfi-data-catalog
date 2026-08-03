(function () {
  "use strict";

  var STORAGE_KEY = "etherfi-data-catalog-theme";
  var root = document.documentElement;
  var toggle = document.querySelector("[data-theme-toggle]");
  var studioThemeSlot = document.querySelector("[data-studio-theme-slot]");
  var themeColor = document.querySelector("[data-theme-color]");

  if (toggle && studioThemeSlot) {
    studioThemeSlot.appendChild(toggle);
  }

  function isTheme(value) {
    return value === "light" || value === "dark";
  }

  function readStoredTheme() {
    try {
      var value = window.localStorage.getItem(STORAGE_KEY);
      return isTheme(value) ? value : null;
    } catch (error) {
      return null;
    }
  }

  function storeTheme(theme) {
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch (error) {
      // The theme still changes for this page when storage is unavailable.
    }
  }

  function systemTheme() {
    try {
      return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    } catch (error) {
      return "light";
    }
  }

  function applyTheme(theme, persist) {
    var nextTheme = isTheme(theme) ? theme : "light";
    var isDark = nextTheme === "dark";
    var controlTitle = isDark ? "Switch to light theme" : "Switch to dark theme";

    root.setAttribute("data-theme-ready", "");
    root.setAttribute("data-theme", nextTheme);

    if (toggle) {
      toggle.setAttribute("aria-pressed", isDark ? "true" : "false");
      toggle.setAttribute("aria-label", "Dark theme");
      toggle.setAttribute("title", controlTitle);
    }

    if (themeColor) {
      themeColor.setAttribute("content", isDark ? "#0b110d" : "#f2f0e8");
    }

    if (persist) {
      storeTheme(nextTheme);
    }
  }

  applyTheme(root.getAttribute("data-theme") || readStoredTheme() || systemTheme(), false);

  if (toggle) {
    toggle.addEventListener("click", function () {
      var nextTheme = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(nextTheme, true);
    });
  }

  try {
    var mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    var followSystemTheme = function (event) {
      if (!readStoredTheme()) {
        applyTheme(event.matches ? "dark" : "light", false);
      }
    };

    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener("change", followSystemTheme);
    } else if (mediaQuery.addListener) {
      mediaQuery.addListener(followSystemTheme);
    }
  } catch (error) {
    // Older or restricted browsers keep the already-applied theme.
  }

  if (window.addEventListener) {
    window.addEventListener("storage", function (event) {
      if (event.key === STORAGE_KEY) {
        applyTheme(isTheme(event.newValue) ? event.newValue : systemTheme(), false);
      }
    });
  }
}());
