(function () {
  var _pollActive = false;
  var _pollTimer = null;
  var _healthTimer = null;
  var _fetching = false;
  var POLL_INTERVAL = 10000;
  var HEALTH_INTERVAL = 15000;

  async function pollCycle() {
    if (_fetching) return;
    _fetching = true;
    try {
      var p1 = typeof updateModelData === "function" ? updateModelData() : Promise.resolve();
      var p2 = typeof updateSystemStats === "function" ? updateSystemStats() : Promise.resolve();
      await Promise.all([p1, p2]);
    } catch (e) {
      console.log("Poll cycle error:", e);
    } finally {
      _fetching = false;
    }
  }

  function startPolling() {
    if (_pollActive) return;
    _pollActive = true;
    pollCycle();
    if (_pollTimer) clearInterval(_pollTimer);
    _pollTimer = setInterval(pollCycle, POLL_INTERVAL);

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
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    if (_healthTimer) { clearInterval(_healthTimer); _healthTimer = null; }
  }

  function init() {
    if (typeof updateTimes === "function") updateTimes();
    if (typeof initializeCompactMode === "function") initializeCompactMode();
    if (typeof loadDownloadableModels === "function") loadDownloadableModels();
    startPolling();
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
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
