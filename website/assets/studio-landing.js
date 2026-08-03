(function (root, factory) {
  const landing = factory(root);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = landing;
  }
  if (root) {
    root.EtherfiStudioLanding = landing;
  }
  if (typeof document !== "undefined") {
    landing.ready(document);
  }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";

  const LANDING_SELECTOR = "[data-studio-landing]";
  const DASHBOARD_SELECTOR = "[data-studio-dashboard-select]";

  function destinationForSelection(value) {
    const destination = String(value || "").trim();
    if (!destination || /^(?:javascript|data):/i.test(destination)) {
      return "";
    }
    return destination;
  }

  function navigate(destination) {
    const safeDestination = destinationForSelection(destination);
    if (!safeDestination || !root || !root.location) {
      return false;
    }
    if (typeof root.location.assign === "function") {
      root.location.assign(safeDestination);
    } else {
      root.location.href = safeDestination;
    }
    return true;
  }

  function mount(scope) {
    const page = scope && scope.querySelector
      ? scope.querySelector(LANDING_SELECTOR)
      : null;
    if (!page || page.dataset.studioLandingMounted === "true") {
      return false;
    }
    const selector = page.querySelector(DASHBOARD_SELECTOR);
    if (selector) {
      selector.addEventListener("change", () => navigate(selector.value));
    }
    page.dataset.studioLandingMounted = "true";
    return true;
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
    destinationForSelection,
    mount,
    navigate,
    ready,
  };
});
