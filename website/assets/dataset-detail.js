(function () {
  const COPY_SELECTOR = "[data-copy-text]";
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
      const copied = document.execCommand("copy");
      return Promise.resolve(Boolean(copied));
    } finally {
      document.body.removeChild(textarea);
    }
  }

  function copyText(text) {
    if (
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === "function" &&
      window.isSecureContext
    ) {
      return navigator.clipboard.writeText(text).then(() => true);
    }
    return copyWithFallback(text);
  }

  function setFeedback(button, label) {
    const feedback = button.querySelector(FEEDBACK_SELECTOR);
    if (!feedback) {
      return;
    }
    feedback.textContent = label;
  }

  function resetFeedback(button) {
    window.setTimeout(() => {
      setFeedback(button, "Copy");
      button.classList.remove("copied", "copy-failed");
    }, RESET_DELAY_MS);
  }

  async function handleCopy(button) {
    const text = button.dataset.copyText || "";
    if (!text) {
      return;
    }

    try {
      const copied = await copyText(text);
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
