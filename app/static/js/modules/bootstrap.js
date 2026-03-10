(function () {
  var _modelPollInterval = null;
  var _statsPollInterval = null;
  var _healthPollInterval = null;

  function startModelPolling() {
    if (_modelPollInterval) clearInterval(_modelPollInterval);
    if (typeof updateModelData === "function") {
      updateModelData();
      _modelPollInterval = setInterval(updateModelData, 10000);
    }
  }

  function stopModelPolling() {
    if (_modelPollInterval) {
      clearInterval(_modelPollInterval);
      _modelPollInterval = null;
    }
  }

  function startStatsPolling() {
    if (_statsPollInterval) clearInterval(_statsPollInterval);
    if (typeof updateSystemStats === "function") {
      updateSystemStats();
      _statsPollInterval = setInterval(updateSystemStats, 10000);
    }
  }

  function stopStatsPolling() {
    if (_statsPollInterval) {
      clearInterval(_statsPollInterval);
      _statsPollInterval = null;
    }
  }

  function startHealthPolling() {
    if (_healthPollInterval) clearInterval(_healthPollInterval);
    if (window.serviceControl && window.serviceControl.updateHealthStatus) {
      window.serviceControl.updateHealthStatus();
      _healthPollInterval = setInterval(
        window.serviceControl.updateHealthStatus,
        15000,
      );
    }
  }

  function stopHealthPolling() {
    if (_healthPollInterval) {
      clearInterval(_healthPollInterval);
      _healthPollInterval = null;
    }
  }

  function init() {
    if (typeof updateTimes === "function") updateTimes();
    if (typeof initializeCompactMode === "function") initializeCompactMode();
    if (typeof loadDownloadableModels === "function") loadDownloadableModels();

    startModelPolling();
    startStatsPolling();
    startHealthPolling();
  }

  // Pause all polling when tab is hidden to avoid wasted requests;
  // resume and immediately refresh when tab becomes visible again.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      startModelPolling();
      startStatsPolling();
      startHealthPolling();
    } else {
      stopModelPolling();
      stopStatsPolling();
      stopHealthPolling();
    }
  });

  document.addEventListener("DOMContentLoaded", init);
  window.bootstrapInit = init;
  window.startModelPolling = startModelPolling;
  window.stopModelPolling = stopModelPolling;
})();
