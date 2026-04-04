(function () {
  var _pollActive = false;
  var _healthTimer = null;
  var HEALTH_INTERVAL = 15000;

  // Stats: main.js updates every 1s. Only health is polled here (15s).

  function startPolling() {
    if (_pollActive) return;
    _pollActive = true;
    if (_healthTimer) clearInterval(_healthTimer);
    if (window.serviceControl && window.serviceControl.updateHealthStatus) {
      window.serviceControl.updateHealthStatus();
      _healthTimer = setInterval(
        window.serviceControl.updateHealthStatus,
        HEALTH_INTERVAL,
      );
    }
  }

  function stopPolling() {
    _pollActive = false;
    if (_healthTimer) { clearInterval(_healthTimer); _healthTimer = null; }
  }

  function init() {
    if (typeof updateTimes === "function") updateTimes();
    if (typeof initializeCompactMode === "function") initializeCompactMode();
    if (typeof loadDownloadableModels === "function") loadDownloadableModels();
    if (typeof updateModelData === "function") updateModelData();
    startPolling();
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      if (typeof updateModelData === "function") updateModelData();
      startPolling();
    } else {
      stopPolling();
    }
  });

  document.addEventListener("DOMContentLoaded", init);
  window.bootstrapInit = init;
  window.startModelPolling = startPolling;
  window.stopModelPolling = stopPolling;
})();
