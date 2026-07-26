(function () {
  const COPY_SELECTOR = "[data-copy-text]";
  const FEEDBACK_SELECTOR = "[data-copy-feedback]";
  const ANNOUNCER_SELECTOR = "[data-copy-announcer]";
  const RESET_DELAY_MS = 1400;
  const resetTimers = new WeakMap();
  document.documentElement.dataset.datasetDetailMounted = "true";

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
