(function () {
  const COPY_SELECTOR = "[data-snippet-copy]";
  const FEEDBACK_SELECTOR = "[data-copy-feedback]";
  const ANNOUNCER_SELECTOR = "[data-copy-announcer]";
  const RESET_DELAY_MS = 1400;
  const resetTimers = new WeakMap();
  document.documentElement.dataset.mcpMounted = "true";

  function selectSnippetText(button) {
    const snippet = button.closest(".code-snippet");
    const code = snippet ? snippet.querySelector("code") : null;
    if (!code || !window.getSelection || !document.createRange) {
      return false;
    }

    const range = document.createRange();
    range.selectNodeContents(code);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  }

  function setFeedback(button, label) {
    const feedback = button.querySelector(FEEDBACK_SELECTOR);
    if (feedback) {
      feedback.textContent = label;
    }
    const announcer = button.parentElement
      ? button.parentElement.querySelector(ANNOUNCER_SELECTOR)
      : null;
    if (announcer) {
      announcer.textContent = label === "Copy" ? "" : label;
    }
  }

  function resetButton(button) {
    const existingTimer = resetTimers.get(button);
    if (existingTimer) {
      window.clearTimeout(existingTimer);
    }
    const timer = window.setTimeout(() => {
      button.classList.remove("copied", "copy-selected", "copy-failed");
      setFeedback(button, "Copy");
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
      const selected = copied ? false : selectSnippetText(button);
      button.classList.toggle("copied", copied);
      button.classList.toggle("copy-selected", selected);
      button.classList.toggle("copy-failed", !copied && !selected);
      setFeedback(button, copied ? "Copied" : selected ? "Selected" : "Copy failed");
      resetButton(button);
    } catch (error) {
      const selected = selectSnippetText(button);
      button.classList.toggle("copy-selected", selected);
      button.classList.toggle("copy-failed", !selected);
      setFeedback(button, selected ? "Selected" : "Copy failed");
      resetButton(button);
      console.warn("[ether.fi mcp] Copy failed", error);
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
