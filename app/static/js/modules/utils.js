// Utility functions extracted from main.js
export function escapeHtml(str) {
  if (!str && str !== 0) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function cssEscape(str) {
  if (!str && str !== 0) return '';
  if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(String(str));
  return String(str).replace(/(["'\\\[\]\.\/\#\:\s])/g, '\\$1');
}

// expose on window for legacy inline handlers (if any)
window.escapeHtml = escapeHtml;
window.cssEscape = cssEscape;