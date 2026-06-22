/** Ask? modal — drag header to snap left/right, resize split, or return to center overlay. */
(function () {
  var EDGE_RATIO = 0.14;
  var CENTER_RATIO = 0.22;
  var DISMISS_OUTSIDE_PX = 100;
  var SPLIT_STORAGE_KEY = "askModalDockSplitPct";
  var SPLIT_MIN = 22;
  var SPLIT_MAX = 78;
  var DEFAULT_SPLIT = 50;

  var modalEl = null;
  var dialogEl = null;
  var headerEl = null;
  var snapRoot = null;
  var splitEl = null;
  var bound = false;

  var mode = "center"; // center | float | left | right
  var splitPct = DEFAULT_SPLIT;
  var dragging = false;
  var resizingSplit = false;
  var activeSnap = null;
  var dismissHint = false;
  var dragOffsetX = 0;
  var dragOffsetY = 0;
  var floatPos = null;
  var dragStartX = 0;
  var dragStartY = 0;
  var dragMoved = false;

  function readStoredMode() {
    try {
      return sessionStorage.getItem("askModalDockMode") || "center";
    } catch (_) {
      return "center";
    }
  }

  function storeMode(value) {
    try {
      sessionStorage.setItem("askModalDockMode", value);
    } catch (_) {}
  }

  function readStoredFloatPos() {
    try {
      var raw = sessionStorage.getItem("askModalFloatPos");
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  function storeFloatPos(pos) {
    try {
      if (pos) sessionStorage.setItem("askModalFloatPos", JSON.stringify(pos));
      else sessionStorage.removeItem("askModalFloatPos");
    } catch (_) {}
  }

  function readStoredSplit() {
    try {
      var v = parseFloat(sessionStorage.getItem(SPLIT_STORAGE_KEY));
      if (Number.isFinite(v)) return clamp(v, SPLIT_MIN, SPLIT_MAX);
    } catch (_) {}
    return DEFAULT_SPLIT;
  }

  function storeSplit() {
    try {
      sessionStorage.setItem(SPLIT_STORAGE_KEY, String(splitPct));
    } catch (_) {}
  }

  function applySplitCss() {
    document.documentElement.style.setProperty("--ask-dock-ask-width-vw", String(splitPct));
  }

  function ensureSnapZones() {
    if (snapRoot) return snapRoot;
    snapRoot = document.createElement("div");
    snapRoot.id = "askSnapZones";
    snapRoot.className = "ask-snap-zones";
    snapRoot.setAttribute("aria-hidden", "true");
    snapRoot.innerHTML =
      '<div class="ask-snap-zone ask-snap-zone--left" data-zone="left"></div>' +
      '<div class="ask-snap-zone ask-snap-zone--right" data-zone="right"></div>' +
      '<div class="ask-snap-zone ask-snap-zone--center" data-zone="center"></div>';
    document.body.appendChild(snapRoot);
    return snapRoot;
  }

  function ensureSplitter() {
    if (splitEl) return splitEl;
    splitEl = document.createElement("div");
    splitEl.id = "askDockSplitter";
    splitEl.className = "ask-dock-splitter";
    splitEl.hidden = true;
    splitEl.setAttribute("role", "separator");
    splitEl.setAttribute("aria-orientation", "vertical");
    splitEl.setAttribute("aria-label", "Resize Ask panel");
    splitEl.setAttribute("tabindex", "0");
    splitEl.addEventListener("mousedown", onSplitterDown);
    splitEl.addEventListener("keydown", onSplitterKeyDown);
    document.body.appendChild(splitEl);
    return splitEl;
  }

  function splitterLeftPx() {
    var vw = window.innerWidth || document.documentElement.clientWidth || 0;
    if (mode === "left") return (splitPct / 100) * vw;
    if (mode === "right") return ((100 - splitPct) / 100) * vw;
    return 0;
  }

  function updateSplitterPosition() {
    if (!splitEl) return;
    splitEl.style.left = splitterLeftPx() + "px";
    splitEl.setAttribute("aria-valuenow", String(Math.round(splitPct)));
    splitEl.setAttribute(
      "aria-valuetext",
      "Ask panel " + Math.round(splitPct) + " percent, dashboard " + Math.round(100 - splitPct) + " percent",
    );
  }

  function showSplitter() {
    ensureSplitter();
    applySplitCss();
    updateSplitterPosition();
    splitEl.hidden = false;
    splitEl.classList.add("ask-dock-splitter--visible");
  }

  function hideSplitter() {
    if (!splitEl) return;
    splitEl.classList.remove("ask-dock-splitter--visible", "ask-dock-splitter--active");
    splitEl.hidden = true;
  }

  function splitPctFromClientX(clientX) {
    var vw = window.innerWidth || document.documentElement.clientWidth || 1;
    if (mode === "left") return (clientX / vw) * 100;
    return ((vw - clientX) / vw) * 100;
  }

  function setSplitPct(pct, persist) {
    splitPct = clamp(pct, SPLIT_MIN, SPLIT_MAX);
    applySplitCss();
    updateSplitterPosition();
    if (persist) storeSplit();
  }

  function onSplitterDown(e) {
    if (e.button !== 0 || (mode !== "left" && mode !== "right")) return;
    resizingSplit = true;
    document.body.classList.add("ask-dock-split-active");
    splitEl.classList.add("ask-dock-splitter--active");
    e.preventDefault();
  }

  function onSplitterKeyDown(e) {
    if (mode !== "left" && mode !== "right") return;
    var step = e.shiftKey ? 5 : 2;
    if (e.key === "ArrowLeft") {
      setSplitPct(mode === "left" ? splitPct - step : splitPct + step, true);
      e.preventDefault();
    } else if (e.key === "ArrowRight") {
      setSplitPct(mode === "left" ? splitPct + step : splitPct - step, true);
      e.preventDefault();
    } else if (e.key === "Home") {
      setSplitPct(SPLIT_MIN, true);
      e.preventDefault();
    } else if (e.key === "End") {
      setSplitPct(SPLIT_MAX, true);
      e.preventDefault();
    }
  }

  function onSplitterMove(e) {
    if (!resizingSplit) return;
    setSplitPct(splitPctFromClientX(e.clientX), false);
    e.preventDefault();
  }

  function onSplitterUp() {
    if (!resizingSplit) return;
    resizingSplit = false;
    document.body.classList.remove("ask-dock-split-active");
    if (splitEl) splitEl.classList.remove("ask-dock-splitter--active");
    storeSplit();
  }

  function setActiveSnap(zone) {
    activeSnap = zone;
    if (!snapRoot) return;
    snapRoot.querySelectorAll(".ask-snap-zone").forEach(function (el) {
      el.classList.toggle("ask-snap-zone--active", el.dataset.zone === zone);
    });
    snapRoot.classList.toggle("ask-snap-zones--visible", !!zone || dismissHint);
    snapRoot.classList.toggle("ask-snap-zones--dismiss", dismissHint && !zone);
  }

  function clearSnapUi() {
    dismissHint = false;
    setActiveSnap(null);
    if (snapRoot) snapRoot.classList.remove("ask-snap-zones--visible", "ask-snap-zones--dismiss");
  }

  function dialogRect() {
    return dialogEl ? dialogEl.getBoundingClientRect() : { left: 0, top: 0, width: 0, height: 0 };
  }

  function clamp(n, min, max) {
    return Math.max(min, Math.min(max, n));
  }

  function applyFloatPosition(x, y) {
    if (!dialogEl) return;
    var rect = dialogEl.getBoundingClientRect();
    var w = rect.width || dialogEl.offsetWidth;
    var h = rect.height || dialogEl.offsetHeight;
    var maxX = Math.max(8, window.innerWidth - w - 8);
    var maxY = Math.max(8, window.innerHeight - h - 8);
    floatPos = {
      x: clamp(x, 8, maxX),
      y: clamp(y, 8, maxY),
    };
    dialogEl.style.left = floatPos.x + "px";
    dialogEl.style.top = floatPos.y + "px";
    storeFloatPos(floatPos);
  }

  function clearInlinePosition() {
    if (!dialogEl) return;
    dialogEl.style.left = "";
    dialogEl.style.top = "";
    dialogEl.style.transform = "";
  }

  function setBodyDockClass(side) {
    document.body.classList.remove("ask-dock-left-open", "ask-dock-right-open", "ask-dock-floating");
    if (side === "left") document.body.classList.add("ask-dock-left-open");
    if (side === "right") document.body.classList.add("ask-dock-right-open");
    if (side === "float") document.body.classList.add("ask-dock-floating");
  }

  function updateBackdrop() {
    var backdrop = document.querySelector(".modal-backdrop");
    if (!backdrop) return;
    if (mode === "left" || mode === "right") {
      backdrop.classList.add("ask-backdrop-hidden");
    } else {
      backdrop.classList.remove("ask-backdrop-hidden");
    }
  }

  function syncDockChrome() {
    if (mode === "left" || mode === "right") {
      applySplitCss();
      showSplitter();
    } else {
      hideSplitter();
    }
  }

  function applyModeClasses() {
    if (!modalEl || !dialogEl) return;
    modalEl.classList.remove("ask-mode-center", "ask-mode-float", "ask-mode-left", "ask-mode-right", "ask-modal-dragging");
    dialogEl.classList.remove("ask-dialog-floating");
    modalEl.classList.add(
      mode === "center"
        ? "ask-mode-center"
        : mode === "float"
          ? "ask-mode-float"
          : mode === "left"
            ? "ask-mode-left"
            : "ask-mode-right",
    );
    if (mode === "float") dialogEl.classList.add("ask-dialog-floating");
    setBodyDockClass(mode === "float" ? "float" : mode === "left" || mode === "right" ? mode : null);
    updateBackdrop();
    syncDockChrome();
  }

  function enterCenterMode() {
    mode = "center";
    floatPos = null;
    storeFloatPos(null);
    storeMode("center");
    clearInlinePosition();
    applyModeClasses();
  }

  function enterFloatMode(x, y) {
    mode = "float";
    storeMode("float");
    applyModeClasses();
    applyFloatPosition(
      x != null ? x : floatPos && floatPos.x != null ? floatPos.x : window.innerWidth * 0.25,
      y != null ? y : floatPos && floatPos.y != null ? floatPos.y : window.innerHeight * 0.12,
    );
  }

  function enterDockMode(side) {
    mode = side;
    floatPos = null;
    storeFloatPos(null);
    storeMode(side);
    splitPct = readStoredSplit();
    clearInlinePosition();
    applyModeClasses();
  }

  function detectSnap(clientX, clientY) {
    var w = window.innerWidth;
    var h = window.innerHeight;

    if (
      clientX < -DISMISS_OUTSIDE_PX ||
      clientY < -DISMISS_OUTSIDE_PX ||
      clientX > w + DISMISS_OUTSIDE_PX ||
      clientY > h + DISMISS_OUTSIDE_PX
    ) {
      return { snap: null, dismiss: true };
    }

    if (mode === "left" || mode === "right") {
      var centerStart = w * (0.5 - CENTER_RATIO / 2);
      var centerEnd = w * (0.5 + CENTER_RATIO / 2);
      if (clientX >= centerStart && clientX <= centerEnd && clientY >= 0 && clientY <= h) {
        return { snap: "center", dismiss: false };
      }
      return { snap: null, dismiss: false };
    }

    if (clientX <= w * EDGE_RATIO) return { snap: "left", dismiss: false };
    if (clientX >= w * (1 - EDGE_RATIO)) return { snap: "right", dismiss: false };
    return { snap: null, dismiss: false };
  }

  function onPointerMove(e) {
    if (resizingSplit) {
      onSplitterMove(e);
      return;
    }
    if (!dragging || !dialogEl) return;

    var clientX = e.clientX;
    var clientY = e.clientY;

    if (!dragMoved) {
      if (Math.abs(clientX - dragStartX) < 5 && Math.abs(clientY - dragStartY) < 5) return;
      dragMoved = true;
      if (mode === "center") {
        var rect = dialogRect();
        dragOffsetX = dragStartX - rect.left;
        dragOffsetY = dragStartY - rect.top;
        enterFloatMode(rect.left, rect.top);
      }
    }

    e.preventDefault();
    var target = detectSnap(clientX, clientY);
    dismissHint = target.dismiss;
    setActiveSnap(target.snap);

    if (mode === "left" || mode === "right") return;

    applyFloatPosition(clientX - dragOffsetX, clientY - dragOffsetY);
    if (modalEl) modalEl.classList.add("ask-modal-dragging");
  }

  function hideModal() {
    if (!modalEl || typeof bootstrap === "undefined") return;
    var inst = bootstrap.Modal.getInstance(modalEl);
    if (inst) inst.hide();
    enterCenterMode();
  }

  function onPointerUp(e) {
    if (resizingSplit) {
      onSplitterUp();
      return;
    }
    if (!dragging) return;
    dragging = false;
    if (modalEl) modalEl.classList.remove("ask-modal-dragging");
    document.body.classList.remove("ask-modal-drag-active");

    if (!dragMoved) {
      clearSnapUi();
      return;
    }

    var target = detectSnap(e.clientX, e.clientY);

    if (target.dismiss) {
      clearSnapUi();
      hideModal();
      return;
    }

    if (target.snap === "left") enterDockMode("left");
    else if (target.snap === "right") enterDockMode("right");
    else if (target.snap === "center") enterCenterMode();

    clearSnapUi();
  }

  function onHeaderPointerDown(e) {
    if (!dialogEl || !modalEl || !modalEl.classList.contains("show")) return;
    if (e.button !== 0) return;
    if (e.target.closest(".btn-close")) return;

    dragging = true;
    dragMoved = false;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    document.body.classList.add("ask-modal-drag-active");
    ensureSnapZones();

    var rect = dialogRect();
    dragOffsetX = e.clientX - rect.left;
    dragOffsetY = e.clientY - rect.top;

    e.preventDefault();
  }

  function onWindowResize() {
    if (mode === "left" || mode === "right") updateSplitterPosition();
  }

  function restoreStoredLayout() {
    splitPct = readStoredSplit();
    applySplitCss();
    var stored = readStoredMode();
    if (stored === "left" || stored === "right") enterDockMode(stored);
    else if (stored === "float") {
      floatPos = readStoredFloatPos();
      enterFloatMode(floatPos && floatPos.x, floatPos && floatPos.y);
    } else enterCenterMode();
  }

  function onModalShown() {
    restoreStoredLayout();
    updateBackdrop();
  }

  function onModalHidden() {
    dragging = false;
    resizingSplit = false;
    clearSnapUi();
    hideSplitter();
    document.body.classList.remove(
      "ask-modal-drag-active",
      "ask-dock-split-active",
      "ask-dock-left-open",
      "ask-dock-right-open",
      "ask-dock-floating",
    );
    if (modalEl) modalEl.classList.remove("ask-modal-dragging");
  }

  function bind() {
    if (bound) return;
    modalEl = document.getElementById("askModelModal");
    if (!modalEl) return;
    dialogEl = modalEl.querySelector(".modal-dialog");
    headerEl = modalEl.querySelector(".modal-header");
    if (!dialogEl || !headerEl) return;

    bound = true;
    splitPct = readStoredSplit();
    applySplitCss();
    ensureSnapZones();
    headerEl.classList.add("ask-modal-drag-handle");
    headerEl.setAttribute(
      "title",
      "Drag to move · snap to screen edges · drag the center gutter to resize split view",
    );

    headerEl.addEventListener("mousedown", onHeaderPointerDown);
    window.addEventListener("mousemove", onPointerMove);
    window.addEventListener("mouseup", onPointerUp);
    window.addEventListener("resize", onWindowResize);
    modalEl.addEventListener("shown.bs.modal", onModalShown);
    modalEl.addEventListener("hidden.bs.modal", onModalHidden);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }

  window.askModalDock = {
    bind: bind,
    reset: enterCenterMode,
    getMode: function () {
      return mode;
    },
    getSplitPct: function () {
      return splitPct;
    },
    setSplitPct: function (pct, persist) {
      setSplitPct(pct, persist !== false);
    },
  };
})();
