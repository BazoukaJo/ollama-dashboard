/**
 * Light / dark theme — localStorage key "theme" (matches BlueprintAssist layout.tsx).
 */
(function () {
  var KEY = "theme";

  function applyTheme(theme) {
    var t = theme === "light" ? "light" : "dark";
    var root = document.documentElement;
    root.classList.remove("light", "dark");
    root.classList.add(t);
    root.setAttribute("data-bs-theme", t);
    try {
      localStorage.setItem(KEY, t);
    } catch (e) {
      /* ignore */
    }
    syncToggleButton();
  }

  function syncToggleButton() {
    var btn = document.getElementById("themeToggleBtn");
    if (!btn) return;
    var dark = document.documentElement.classList.contains("dark");
    var text = dark ? "Switch to light mode" : "Switch to dark mode";
    btn.removeAttribute("title");
    btn.setAttribute("data-dashboard-tooltip", text);
    btn.setAttribute("aria-label", text);
    btn.dataset.dashboardTooltipMigrated = "1";
  }

  function initToggle() {
    var btn = document.getElementById("themeToggleBtn");
    if (!btn) return;
    syncToggleButton();
    btn.addEventListener("click", function () {
      var root = document.documentElement;
      var next = root.classList.contains("dark") ? "light" : "dark";
      applyTheme(next);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initToggle);
  } else {
    initToggle();
  }

  window.applyDashboardTheme = applyTheme;
})();
