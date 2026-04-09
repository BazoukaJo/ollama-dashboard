// Utility functions extracted from main.js (global, non-module).
function escapeHtml(str) {
  if (!str && str !== 0) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function cssEscape(str) {
  if (!str && str !== 0) return '';
  if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(String(str));
  return String(str).replace(/(["'\\\[\]\.\/\#\:\s])/g, '\\$1');
}

/**
 * Read a fetch Response body once and parse JSON when possible.
 * Avoids response.json() throwing on HTML/plain errors and prevents double-read bugs.
 *
 * @returns {{ responseOk: boolean, status: number, data: object, message: string|null }}
 */
async function readApiJson(response) {
  const status = response.status;
  let text = "";
  try {
    text = await response.text();
  } catch (e) {
    return {
      responseOk: false,
      status,
      data: {},
      message: e.message || "Failed to read response",
    };
  }
  const trimmed = (text || "").trim();
  if (!trimmed) {
    return {
      responseOk: response.ok,
      status,
      data: {},
      message: response.ok ? null : `HTTP ${status}`,
    };
  }
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(text);
      const data =
        typeof parsed === "object" && parsed !== null ? parsed : {};
      const message = response.ok
        ? null
        : String(data.message || data.error || `HTTP ${status}`);
      return {
        responseOk: response.ok,
        status,
        data,
        message,
      };
    } catch {
      return {
        responseOk: false,
        status,
        data: {},
        message: trimmed.slice(0, 240) || "Invalid JSON response",
      };
    }
  }
  // HTML/plain error page or misconfigured proxy — not usable JSON.
  return {
    responseOk: false,
    status,
    data: {},
    message: trimmed.slice(0, 240) || (response.ok ? "Non-JSON response" : `HTTP ${status}`),
  };
}

// Expose on window for inline handlers and other scripts.
window.escapeHtml = escapeHtml;
window.cssEscape = cssEscape;
window.readApiJson = readApiJson;