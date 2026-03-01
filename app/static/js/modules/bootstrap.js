(function () {
  // Track the model polling interval so we can pause/resume it
  var _modelPollInterval = null;

  function startModelPolling() {
    if (_modelPollInterval) clearInterval(_modelPollInterval);
    if (typeof updateModelData === "function") {
      // Refresh immediately when polling resumes (catches changes made while tab was hidden)
      updateModelData();
      _modelPollInterval = setInterval(updateModelData, 5000);
    }
  }

  function stopModelPolling() {
    if (_modelPollInterval) {
      clearInterval(_modelPollInterval);
      _modelPollInterval = null;
    }
  }

  function init() {
    if (typeof updateTimes === "function") updateTimes();
    if (typeof updateSystemStats === "function") updateSystemStats();
    if (typeof initializeCompactMode === "function") initializeCompactMode();
    if (window.serviceControl && window.serviceControl.init)
      window.serviceControl.init();
    if (typeof loadDownloadableModels === "function") loadDownloadableModels();
    // Intervals
    if (typeof updateSystemStats === "function")
      setInterval(updateSystemStats, 1000);
    // Start model polling (also handles the first updateModelData call)
    startModelPolling();
    // Health interval handled inside serviceControl.init()
  }

  // Page Visibility API: when the tab becomes visible again, immediately refresh
  // model status and restart the 5-second interval.  This prevents stale state
  // when Ollama models are loaded/unloaded by external apps while the tab is hidden
  // (browsers throttle setInterval to ~1 minute for inactive tabs).
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      startModelPolling();
    } else {
      stopModelPolling();
    }
  });

  document.addEventListener("DOMContentLoaded", init);
  window.bootstrapInit = init;
  // Expose for use by serviceControl and other modules that manage polling lifecycle
  window.startModelPolling = startModelPolling;
  window.stopModelPolling = stopModelPolling;
})();
