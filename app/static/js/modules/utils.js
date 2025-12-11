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

// Expose on window for inline handlers and other scripts.
window.escapeHtml = escapeHtml;
window.cssEscape = cssEscape;