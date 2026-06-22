(function () {
  var _pollActive = false;
  var _healthTimer = null;
  var HEALTH_INTERVAL = 15000;

  function startPolling() {
    if (_pollActive) return;
    _pollActive = true;
    if (typeof startModelPollTimer === "function") startModelPollTimer();
    if (typeof startStatsPollTimer === "function") startStatsPollTimer();
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
    if (_healthTimer) {
      clearInterval(_healthTimer);
      _healthTimer = null;
    }
    if (typeof stopModelPollTimer === "function") stopModelPollTimer();
    if (typeof stopStatsPollTimer === "function") stopStatsPollTimer();
  }

  function init() {
    startPolling();
    if (typeof loadDownloadableModels === "function") loadDownloadableModels();
    if (typeof updateModelData === "function") updateModelData(false);
    if (typeof resumeActiveDownloads === "function") resumeActiveDownloads();
    if (window.apiProxyUI && typeof window.apiProxyUI.init === "function") {
      window.apiProxyUI.init();
    }
    if (window.modelCardActions) {
      setTimeout(function () {
        if (typeof modelCardActions.enhanceAllModelCards === "function") {
          modelCardActions.enhanceAllModelCards();
        }
      }, 0);
    }
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      if (typeof updateModelData === "function") updateModelData(true);
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
