(function () {
  const COPY_SELECTOR = "[data-snippet-copy]";
  const FEEDBACK_SELECTOR = "[data-copy-feedback]";
  const RESET_DELAY_MS = 1400;

  function copyWithFallback(text) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "-9999px";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();

    try {
      return Promise.resolve(Boolean(document.execCommand("copy")));
    } finally {
      document.body.removeChild(textarea);
    }
  }

  function copyText(text) {
    if (
      window.navigator &&
      window.navigator.clipboard &&
      typeof window.navigator.clipboard.writeText === "function"
    ) {
      return window.navigator.clipboard.writeText(text).then(() => true);
    }
    return copyWithFallback(text);
  }

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
  }

  function resetButton(button) {
    window.setTimeout(() => {
      button.classList.remove("copied", "copy-selected", "copy-failed");
      setFeedback(button, "Copy");
    }, RESET_DELAY_MS);
  }

  async function handleCopy(button) {
    const text = button.dataset.copyText || "";
    if (!text) {
      return;
    }

    try {
      const copied = await copyText(text);
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
