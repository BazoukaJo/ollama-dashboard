/** Toast notifications (XSS-safe message rendering). */
(function () {
  function showNotification(message, type) {
    const notification = document.createElement("div");
    const isError = type === "error" || type === "danger";
    const alertClass = isError
      ? "danger"
      : type === "success"
        ? "success"
        : "info";
    notification.className = `alert alert-${alertClass} alert-dismissible fade show position-fixed`;
    notification.style.cssText =
      "top: 20px; right: 20px; z-index: 9999; min-width: 300px; max-width: 500px;";

    const safeMessage =
      typeof escapeHtml === "function"
        ? escapeHtml(String(message || ""))
        : String(message || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");

    const copyButton = isError
      ? `
    <button type="button" class="btn btn-sm btn-outline-light" onclick="copyErrorToClipboard(this)"
            style="padding: 0.25rem 0.5rem; font-size: 0.75rem; flex-shrink: 0;" data-dashboard-tooltip="Copy error to clipboard">
      <i class="fas fa-copy"></i> Copy
    </button>
  `
      : "";

    notification.innerHTML = `
        <div style="display: flex; align-items: start; gap: 10px;">
          <div style="flex: 1; min-width: 0;" data-error-message="${safeMessage}">${safeMessage}</div>
          <div style="display: flex; gap: 5px; align-items: center; flex-shrink: 0;">
            ${copyButton}
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="alert" aria-label="Close"></button>
          </div>
        </div>
    `;
    document.body.appendChild(notification);

    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, 5000);
  }

  function copyErrorToClipboard(button) {
    const errorDiv = button
      .closest(".alert")
      ?.querySelector("[data-error-message]");
    if (!errorDiv) return;

    const errorText = errorDiv.getAttribute("data-error-message") || errorDiv.textContent;
    navigator.clipboard
      .writeText(errorText)
      .then(() => {
        const originalHtml = button.innerHTML;
        button.innerHTML = '<i class="fas fa-check"></i> Copied!';
        setTimeout(() => {
          button.innerHTML = originalHtml;
        }, 2000);
      })
      .catch((err) => {
        console.error("Failed to copy:", err);
        showNotification("Failed to copy to clipboard", "error");
      });
  }

  window.showNotification = showNotification;
  window.copyErrorToClipboard = copyErrorToClipboard;
})();
