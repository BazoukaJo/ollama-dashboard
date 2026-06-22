/**
 * Dashboard poll timers — model list and system stats refresh intervals.
 */
(function () {
  "use strict";

  function getPollIntervalSec() {
    const el = document.querySelector(
      ".dashboard-header-meta-group[data-model-poll-interval]",
    );
    const val = el && el.dataset.modelPollInterval;
    const n = parseInt(val, 10);
    return Number.isFinite(n) && n > 0 ? n : 10;
  }

  function getStatsPollIntervalSec() {
    const el = document.querySelector(".compact-system-resources");
    const val = el && el.dataset.statsPollInterval;
    const n = parseInt(val, 10);
    return Number.isFinite(n) && n > 0 ? n : 1;
  }

  let _modelPollTimer = null;
  let _statsPollTimer = null;

  function stopModelPollTimer() {
    if (_modelPollTimer) {
      clearInterval(_modelPollTimer);
      _modelPollTimer = null;
    }
  }

  function stopStatsPollTimer() {
    if (_statsPollTimer) {
      clearInterval(_statsPollTimer);
      _statsPollTimer = null;
    }
  }

  function startModelPollTimer() {
    stopModelPollTimer();
    updateTimes();
  }

  function startStatsPollTimer() {
    stopStatsPollTimer();
    const statsMs =
      typeof getStatsPollIntervalSec === "function"
        ? getStatsPollIntervalSec() * 1000
        : 1000;
    if (typeof updateSystemStats === "function") updateSystemStats();
    _statsPollTimer = setInterval(function () {
      if (document.visibilityState !== "visible") return;
      if (typeof updateSystemStats === "function") updateSystemStats();
    }, statsMs);
  }

  function updateTimes() {
    const intervalSec = getPollIntervalSec();
    stopModelPollTimer();
    _modelPollTimer = setInterval(function () {
      if (document.visibilityState !== "visible") return;
      if (typeof updateModelData === "function") {
        void updateModelData(false);
      }
    }, intervalSec * 1000);
  }

  window.getPollIntervalSec = getPollIntervalSec;
  window.getStatsPollIntervalSec = getStatsPollIntervalSec;
  window.stopModelPollTimer = stopModelPollTimer;
  window.stopStatsPollTimer = stopStatsPollTimer;
  window.startModelPollTimer = startModelPollTimer;
  window.startStatsPollTimer = startStatsPollTimer;
  window.updateTimes = updateTimes;
})();
