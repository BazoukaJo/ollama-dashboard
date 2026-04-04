/**
 * Dashboard tooltips: migrate title → data-dashboard-tooltip, then show text in a
 * single layer under document.body (position:fixed) so popups are not clipped or
 * buried by stacking contexts inside cards, grids, or overflow:hidden ancestors.
 */
(function () {
  var host = null;
  var activeEl = null;
  var tooltipId = "dashboard-tooltip-floating";
  /** Delay before showing on hover (ms). Avoids flicker when moving the pointer across the UI. */
  var HOVER_SHOW_DELAY_MS = 550;
  var showTimer = null;
  var pendingEl = null;

  function clearHoverShowTimer() {
    if (showTimer) {
      clearTimeout(showTimer);
      showTimer = null;
    }
    pendingEl = null;
  }

  function shouldSkip(el) {
    if (!el || el.nodeType !== 1) return true;
    if (el.hasAttribute("data-tooltip-native")) return true;
    if (el.closest("[data-no-dashboard-tooltip]")) return true;
    return false;
  }

  function ensureHost() {
    if (host && host.parentNode) return host;
    host = document.createElement("div");
    host.id = tooltipId;
    host.className = "dashboard-tooltip-host";
    host.setAttribute("role", "tooltip");
    host.hidden = true;
    host.setAttribute("aria-hidden", "true");
    document.body.appendChild(host);
    return host;
  }

  function positionNear(trigger, el) {
    el.classList.remove("dashboard-tooltip-host--above");
    var r = trigger.getBoundingClientRect();
    var margin = 6;
    var pad = 8;
    el.style.display = "block";
    el.style.left = "0";
    el.style.top = "0";
    var er = el.getBoundingClientRect();
    var left = r.left + r.width / 2 - er.width / 2;
    var top = r.bottom + margin;
    if (top + er.height > window.innerHeight - pad && r.top > er.height + margin + pad) {
      top = r.top - er.height - margin;
      el.classList.add("dashboard-tooltip-host--above");
    }
    left = Math.max(pad, Math.min(left, window.innerWidth - er.width - pad));
    top = Math.max(pad, Math.min(top, window.innerHeight - er.height - pad));
    el.style.left = left + "px";
    el.style.top = top + "px";
  }

  function showFor(el) {
    var text = el.getAttribute("data-dashboard-tooltip");
    if (!text || !String(text).trim()) return;
    el.removeAttribute("title");
    var h = ensureHost();
    h.textContent = text;
    h.hidden = false;
    h.setAttribute("aria-hidden", "false");
    h.classList.remove("dashboard-tooltip-host--visible");
    activeEl = el;
    el.setAttribute("aria-describedby", tooltipId);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (activeEl !== el || !host) return;
        positionNear(el, host);
        host.classList.add("dashboard-tooltip-host--visible");
      });
    });
  }

  function hide() {
    clearHoverShowTimer();
    if (host) {
      host.classList.remove("dashboard-tooltip-host--visible");
      host.hidden = true;
      host.setAttribute("aria-hidden", "true");
      host.style.display = "";
      host.style.left = "";
      host.style.top = "";
    }
    if (activeEl) {
      activeEl.removeAttribute("aria-describedby");
      activeEl = null;
    }
  }

  function repositionIfNeeded() {
    if (activeEl && host && !host.hidden) positionNear(activeEl, host);
  }

  function initFloatingLayer() {
    document.addEventListener(
      "mouseover",
      function (e) {
        var t = e.target.closest && e.target.closest("[data-dashboard-tooltip]");
        if (!t || shouldSkip(t)) return;
        if (t === activeEl) return;
        if (activeEl && activeEl !== t) hide();
        if (t === pendingEl) return;
        clearHoverShowTimer();
        pendingEl = t;
        showTimer = setTimeout(function () {
          showTimer = null;
          var el = pendingEl;
          pendingEl = null;
          if (!el || !document.body.contains(el)) return;
          showFor(el);
        }, HOVER_SHOW_DELAY_MS);
      },
      true
    );

    document.addEventListener(
      "mouseout",
      function (e) {
        var rel = e.relatedTarget;
        if (pendingEl) {
          if (!rel || !pendingEl.contains(rel)) {
            clearHoverShowTimer();
          }
        }
        if (!activeEl) return;
        if (rel && activeEl.contains(rel)) return;
        if (rel && host && host.contains(rel)) return;
        hide();
      },
      true
    );

    document.addEventListener(
      "focusin",
      function (e) {
        var t = e.target.closest && e.target.closest("[data-dashboard-tooltip]");
        if (!t || shouldSkip(t)) return;
        showFor(t);
      },
      true
    );

    document.addEventListener(
      "focusout",
      function () {
        if (!activeEl) return;
        setTimeout(function () {
          if (!activeEl) return;
          var ae = document.activeElement;
          if (ae && (activeEl === ae || activeEl.contains(ae))) return;
          hide();
        }, 0);
      },
      true
    );

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && activeEl) hide();
    });

    window.addEventListener("resize", repositionIfNeeded);
    document.addEventListener("scroll", repositionIfNeeded, true);
  }

  function stripNativeTooltipConflicts(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[data-dashboard-tooltip]").forEach(function (el) {
      if (shouldSkip(el)) return;
      if (el.hasAttribute("title")) el.removeAttribute("title");
    });
  }

  function migrateTitles(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[title]").forEach(function (el) {
      if (shouldSkip(el)) return;
      var t = el.getAttribute("title");
      if (!t || !String(t).trim()) return;
      if (el.hasAttribute("data-dashboard-tooltip")) {
        el.removeAttribute("title");
        return;
      }
      if (el.dataset.dashboardTooltipMigrated === "1") return;
      el.setAttribute("data-dashboard-tooltip", t);
      el.removeAttribute("title");
      el.dataset.dashboardTooltipMigrated = "1";
      if (
        !el.hasAttribute("aria-label") &&
        !el.hasAttribute("aria-labelledby") &&
        el.tagName !== "BUTTON" &&
        el.tagName !== "A"
      ) {
        el.setAttribute("aria-label", t);
      }
    });
  }

  function syncDashboardTooltips(root) {
    migrateTitles(root || document.body);
    stripNativeTooltipConflicts(root || document.body);
  }

  function init() {
    syncDashboardTooltips(document.body);
    initFloatingLayer();
    var scheduled = false;
    var obs = new MutationObserver(function () {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        scheduled = false;
        syncDashboardTooltips(document.body);
      });
    });
    obs.observe(document.body, { childList: true, subtree: true });

    var attrObs = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        if (m.attributeName !== "title") return;
        var el = m.target;
        if (!el || el.nodeType !== 1) return;
        if (shouldSkip(el)) return;
        if (!el.hasAttribute("title")) return;
        var tv = el.getAttribute("title");
        if (!tv || !String(tv).trim()) return;
        if (el.hasAttribute("data-dashboard-tooltip")) {
          el.removeAttribute("title");
          return;
        }
        el.setAttribute("data-dashboard-tooltip", tv);
        el.removeAttribute("title");
        el.dataset.dashboardTooltipMigrated = "1";
      });
    });
    attrObs.observe(document.body, {
      attributes: true,
      attributeFilter: ["title"],
      subtree: true,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.migrateDashboardTooltips = function (root) {
    syncDashboardTooltips(root || document.body);
  };
})();
