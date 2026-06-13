(function () {
  let _restartInFlight = false;
  let _updateInFlight = false;
  let _installInFlight = false;

  async function fetchServiceRunning() {
    try {
      const resp = await fetch("/api/service/status");
      const jr = await readApiJson(resp);
      if (jr.responseOk && jr.data && typeof jr.data.running === "boolean") {
        return jr.data.running;
      }
    } catch (_) {}
    return null;
  }

  async function isServiceReady() {
    const running = await fetchServiceRunning();
    if (running === false) return false;
    try {
      const h = await fetch("/api/health");
      const hj = await readApiJson(h);
      if (!hj.responseOk || !hj.data) return running === true;
      const health = hj.data;
      if (health.ollama_running === false || health.status === "stopped") {
        return false;
      }
      if (health.status === "healthy") return true;
      if (
        running === true &&
        health.background_thread_alive &&
        (health.status === "degraded" || health.status === "unhealthy")
      ) {
        return true;
      }
      return health.status === "healthy";
    } catch (_) {
      return running === true;
    }
  }

  function pollForServiceState(expectedRunning, maxWaitMs, intervalMs, onDone) {
    const startTime = Date.now();
    const poll = async function () {
      if (Date.now() - startTime > maxWaitMs) {
        if (typeof onDone === "function") onDone(false);
        return;
      }
      try {
        const running = await fetchServiceRunning();
        if (running === expectedRunning) {
          if (expectedRunning) {
            if (await isServiceReady()) {
              if (typeof onDone === "function") onDone(true);
              return;
            }
          } else {
            updateHealthStatus();
            if (typeof onDone === "function") onDone(true);
            return;
          }
        }
      } catch (_) {}
      setTimeout(poll, intervalMs);
    };
    setTimeout(poll, intervalMs);
  }

  function reloadPage() {
    if (typeof window.scheduleReloadUnlessDownloading === "function") {
      window.scheduleReloadUnlessDownloading();
    } else {
      location.reload();
    }
  }

  function pollForHealthyAndReload(maxWaitMs, intervalMs) {
    pollForServiceState(true, maxWaitMs, intervalMs, function () {
      reloadPage();
    });
  }

  function updateServiceControlButtons(isRunning) {
    const startBtn = document.getElementById("startServiceBtn");
    const stopBtn = document.getElementById("stopServiceBtn");
    const restartBtn = document.getElementById("restartServiceBtn");
    if (startBtn) {
      startBtn.disabled = !!isRunning;
      startBtn.classList.remove("btn-success", "btn-outline-success");
      startBtn.classList.add(isRunning ? "btn-outline-success" : "btn-success");
    }
    if (stopBtn) {
      stopBtn.disabled = !isRunning;
      stopBtn.classList.remove("btn-danger", "btn-secondary");
      stopBtn.classList.add(isRunning ? "btn-danger" : "btn-secondary");
    }
    if (restartBtn) {
      restartBtn.disabled = !isRunning;
      restartBtn.classList.remove("btn-warning", "btn-outline-warning");
      restartBtn.classList.add(
        isRunning ? "btn-warning" : "btn-outline-warning",
      );
    }
  }

  function setBackendStatusBadge(badge, ok, text, tooltip) {
    if (!badge) return;
    badge.classList.remove("bg-success", "bg-warning", "bg-secondary", "bg-danger");
    if (ok === true) badge.classList.add("bg-success");
    else if (ok === false) badge.classList.add("bg-warning");
    else badge.classList.add("bg-secondary");
    const span = badge.querySelector(".ollama-backend-status-text");
    if (span) span.textContent = text;
    const tip = tooltip || text;
    if (tip) {
      badge.setAttribute("data-dashboard-tooltip", tip);
      badge.setAttribute("title", tip);
    }
  }

  async function updateHealthStatus() {
    try {
      const [healthResp, serviceRunning] = await Promise.all([
        fetch("/api/health"),
        fetchServiceRunning(),
      ]);
      const hr = await readApiJson(healthResp);
      const health =
        hr.responseOk && hr.data
          ? hr.data
          : { status: "unhealthy", error: hr.message || "Invalid response" };
      const healthBadge = document.getElementById("healthStatus");
      const healthText = document.getElementById("healthText");
      const backendBadge = document.getElementById("ollamaBackendStatusBadge");
      if (!healthBadge || !healthText) return;

      const ollamaRunning =
        serviceRunning !== null
          ? serviceRunning
          : health.ollama_running !== false && health.status !== "stopped";

      healthBadge.style.padding = "";
      healthBadge.style.fontSize = "";

      if (ollamaRunning && health.status === "healthy") {
        healthBadge.className =
          "badge bg-success health-status-badge dashboard-header-health";
        const uptimeMin = Math.floor((health.uptime_seconds || 0) / 60);
        const uptimeHr = Math.floor(uptimeMin / 60);
        const uptimeDisplay =
          uptimeHr > 0 ? `${uptimeHr}h ${uptimeMin % 60}m` : `${uptimeMin}m`;
        healthText.textContent = "Healthy";
        healthBadge.setAttribute(
          "data-dashboard-tooltip",
          `Ollama API healthy • Uptime: ${uptimeDisplay}`,
        );
        setBackendStatusBadge(backendBadge, true, "ready");
        updateServiceControlButtons(true);
      } else if (!ollamaRunning || health.status === "stopped") {
        healthBadge.className =
          "badge bg-warning health-status-badge dashboard-header-health";
        healthText.textContent = "Stopped";
        setBackendStatusBadge(backendBadge, false, "stopped");
        updateServiceControlButtons(false);
      } else if (health.status === "degraded") {
        healthBadge.className =
          "badge bg-warning health-status-badge dashboard-header-health";
        healthText.textContent = "Degraded";
        setBackendStatusBadge(backendBadge, false, "degraded");
        updateServiceControlButtons(ollamaRunning);
      } else {
        healthBadge.className =
          "badge bg-danger health-status-badge dashboard-header-health";
        healthText.textContent = "Unreachable";
        setBackendStatusBadge(backendBadge, false, "offline");
        updateServiceControlButtons(ollamaRunning);
      }
    } catch (err) {
      const healthBadge = document.getElementById("healthStatus");
      const healthText = document.getElementById("healthText");
      const backendBadge = document.getElementById("ollamaBackendStatusBadge");
      if (healthBadge && healthText) {
        healthBadge.className =
          "badge bg-danger health-status-badge dashboard-header-health";
        healthBadge.style.padding = "";
        healthBadge.style.fontSize = "";
        healthText.textContent = "Health check failed";
        setBackendStatusBadge(backendBadge, false, "offline");
        updateServiceControlButtons(false);
      }
    }
  }

  function setServiceButtonLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
      if (!btn.dataset.serviceOrigHtml) {
        btn.dataset.serviceOrigHtml = btn.innerHTML;
      }
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
      btn.disabled = true;
    } else if (btn.dataset.serviceOrigHtml) {
      btn.innerHTML = btn.dataset.serviceOrigHtml;
      delete btn.dataset.serviceOrigHtml;
    }
  }

  async function startOllamaService() {
    const btn = document.getElementById("startServiceBtn");
    setServiceButtonLoading(btn, true);
    try {
      const resp = await fetch("/api/service/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const sr = await readApiJson(resp);
      if (!sr.responseOk) {
        window.showNotification(
          sr.message || "Failed to start service: HTTP " + resp.status,
          "error",
        );
        setServiceButtonLoading(btn, false);
        if (btn) btn.disabled = false;
        return;
      }
      const data = sr.data;
      if (data.success) {
        window.showNotification(data.message, "success");
        updateHealthStatus();
        pollForServiceState(true, 90000, 1500, function () {
          reloadPage();
        });
      } else {
        window.showNotification(
          data.message || "Failed to start service",
          "error",
        );
        setServiceButtonLoading(btn, false);
        if (btn) btn.disabled = false;
      }
    } catch (e) {
      window.showNotification(
        "Failed to start service: " + (e.message || "Network error"),
        "error",
      );
      setServiceButtonLoading(btn, false);
      if (btn) btn.disabled = false;
    }
  }

  async function stopOllamaService() {
    const btn = document.getElementById("stopServiceBtn");
    setServiceButtonLoading(btn, true);
    try {
      const resp = await fetch("/api/service/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const sr = await readApiJson(resp);
      if (!sr.responseOk) {
        window.showNotification(
          sr.message || "Failed to stop service: HTTP " + resp.status,
          "error",
        );
        setServiceButtonLoading(btn, false);
        if (btn) btn.disabled = false;
        return;
      }
      const data = sr.data;
      if (data.success) {
        window.showNotification(data.message, "success");
        updateHealthStatus();
        pollForServiceState(false, 30000, 500, function () {
          reloadPage();
        });
      } else {
        window.showNotification(
          data.message || "Failed to stop service",
          "error",
        );
        setServiceButtonLoading(btn, false);
        if (btn) btn.disabled = false;
      }
    } catch (e) {
      window.showNotification(
        "Failed to stop service: " + (e.message || "Network error"),
        "error",
      );
      setServiceButtonLoading(btn, false);
      if (btn) btn.disabled = false;
    }
  }

  async function restartOllamaService() {
    if (_restartInFlight) return;
    _restartInFlight = true;
    const btn = document.getElementById("restartServiceBtn");
    setServiceButtonLoading(btn, true);
    try {
      const resp = await fetch("/api/service/restart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const rr = await readApiJson(resp);
      if (!rr.responseOk) {
        window.showNotification(
          rr.message || "Failed to restart service",
          "error",
        );
        setServiceButtonLoading(btn, false);
        if (btn) btn.disabled = false;
        return;
      }
      const data = rr.data;
      if (data.success) {
        window.showNotification(data.message, "success");
        updateHealthStatus();
        pollForServiceState(true, 90000, 1500, function () {
          reloadPage();
        });
      } else {
        window.showNotification(data.message, "error");
        setServiceButtonLoading(btn, false);
        if (btn) btn.disabled = false;
      }
    } catch (e) {
      window.showNotification(
        "Failed to restart service: " + e.message,
        "error",
      );
      setServiceButtonLoading(btn, false);
      if (btn) btn.disabled = false;
    } finally {
      _restartInFlight = false;
    }
  }

  function showRestartConfirm() {
    const confirmBtn = document.getElementById("confirmRestartBtn");
    const modalEl = document.getElementById("restartConfirmModal");
    if (!confirmBtn || !modalEl) {
      restartOllamaService();
      return;
    }
    const handler = async function () {
      confirmBtn.disabled = true;
      await restartOllamaService();
      const m = bootstrap.Modal.getInstance(modalEl);
      if (m) m.hide();
      confirmBtn.disabled = false;
    };
    confirmBtn.onclick = handler;
    modalEl.addEventListener(
      "hidden.bs.modal",
      function () {
        confirmBtn.onclick = null;
      },
      { once: true },
    );
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }

  const UPDATE_FETCH_MS = 2700000;

  async function updateOllamaService() {
    if (_updateInFlight) return;
    _updateInFlight = true;
    const btn = document.getElementById("updateOllamaBtn");
    const original = btn ? btn.innerHTML : null;
    if (btn) {
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
      btn.disabled = true;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(function () {
      ctrl.abort();
    }, UPDATE_FETCH_MS);
    try {
      const resp = await fetch("/api/service/update-ollama", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      const ur = await readApiJson(resp);
      const data = ur.data || {};
      if (ur.responseOk && data.success) {
        window.showNotification(data.message || "Ollama updated.", "success");
        updateHealthStatus();
        pollForServiceState(true, 180000, 2000, function () {
          reloadPage();
        });
      } else {
        window.showNotification(
          data.message ||
            ur.message ||
            "Update failed: " + (resp.statusText || "error"),
          "error",
        );
        if (btn && original !== null) btn.innerHTML = original;
        if (btn) btn.disabled = false;
      }
    } catch (e) {
      clearTimeout(timer);
      if (e && e.name === "AbortError") {
        window.showNotification(
          "Update request timed out locally. Update may still be running in the background; checking health…",
          "error",
        );
        pollForServiceState(true, 300000, 3000, function () {
          reloadPage();
        });
      } else {
        window.showNotification(
          "Failed to update Ollama: " + (e.message || "Network error"),
          "error",
        );
        if (btn && original !== null) btn.innerHTML = original;
        if (btn) btn.disabled = false;
      }
    } finally {
      _updateInFlight = false;
    }
  }

  function showUpdateOllamaConfirm() {
    const confirmBtn = document.getElementById("confirmUpdateOllamaBtn");
    const modalEl = document.getElementById("updateOllamaModal");
    if (!confirmBtn || !modalEl) {
      updateOllamaService();
      return;
    }
    const handler = async function () {
      confirmBtn.disabled = true;
      await updateOllamaService();
      const m = bootstrap.Modal.getInstance(modalEl);
      if (m) m.hide();
      confirmBtn.disabled = false;
    };
    confirmBtn.onclick = handler;
    modalEl.addEventListener(
      "hidden.bs.modal",
      function () {
        confirmBtn.onclick = null;
      },
      { once: true },
    );
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }

  const INSTALL_FETCH_MS = 2700000;

  async function installOllamaService() {
    if (_installInFlight) return;
    _installInFlight = true;
    const btn = document.getElementById("installOllamaBtn");
    const original = btn ? btn.innerHTML : null;
    if (btn) {
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
      btn.disabled = true;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(function () {
      ctrl.abort();
    }, INSTALL_FETCH_MS);
    try {
      const resp = await fetch("/api/service/install-ollama", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      const ir = await readApiJson(resp);
      const data = ir.responseOk ? ir.data : {};
      if (data.success) {
        window.showNotification(data.message || "Ollama installed.", "success");
        pollForHealthyAndReload(120000, 2000);
      } else {
        window.showNotification(
          data.message ||
            ir.message ||
            "Install failed: " + (resp.statusText || "error"),
          "error",
        );
        if (btn) btn.disabled = false;
      }
    } catch (e) {
      clearTimeout(timer);
      if (e && e.name === "AbortError") {
        window.showNotification(
          "Install request timed out locally. Install may still be running in the background; checking health…",
          "error",
        );
        pollForHealthyAndReload(300000, 3000);
      } else {
        window.showNotification(
          "Failed to install Ollama: " + (e.message || "Network error"),
          "error",
        );
      }
      if (btn) btn.disabled = false;
    } finally {
      if (btn && original !== null) btn.innerHTML = original;
      _installInFlight = false;
    }
  }

  function showInstallOllamaConfirm() {
    const confirmBtn = document.getElementById("confirmInstallOllamaBtn");
    const modalEl = document.getElementById("installOllamaModal");
    if (!confirmBtn || !modalEl) {
      installOllamaService();
      return;
    }
    const handler = async function () {
      confirmBtn.disabled = true;
      await installOllamaService();
      const m = bootstrap.Modal.getInstance(modalEl);
      if (m) m.hide();
      confirmBtn.disabled = false;
    };
    confirmBtn.onclick = handler;
    modalEl.addEventListener(
      "hidden.bs.modal",
      function () {
        confirmBtn.onclick = null;
      },
      { once: true },
    );
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }

  function init() {
    updateHealthStatus();
  }

  window.serviceControl = {
    updateHealthStatus,
    updateServiceControlButtons,
    startOllamaService,
    stopOllamaService,
    restartOllamaService,
    showRestartConfirm,
    updateOllamaService,
    showUpdateOllamaConfirm,
    installOllamaService,
    showInstallOllamaConfirm,
    init,
  };
  window.startOllamaService = startOllamaService;
  window.stopOllamaService = stopOllamaService;
  window.restartOllamaService = restartOllamaService;
  window.showRestartConfirm = showRestartConfirm;
  window.updateOllamaService = updateOllamaService;
  window.showUpdateOllamaConfirm = showUpdateOllamaConfirm;
  window.installOllamaService = installOllamaService;
  window.showInstallOllamaConfirm = showInstallOllamaConfirm;
})();
