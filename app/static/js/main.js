/**
 * Main JavaScript functionality for Ollama Dashboard
 */

// Model data poll interval (seconds) - read from DOM or default 5
function getPollIntervalSec() {
  const el = document.querySelector(".refresh-indicator");
  const val = el && el.dataset.pollInterval;
  const n = parseInt(val, 10);
  return Number.isFinite(n) && n > 0 ? n : 10;
}

/** System Resources (CPU/RAM/VRAM/GPU/SSD) refresh — faster than model list poll. */
function getStatsPollIntervalSec() {
  const el = document.querySelector(".compact-system-resources");
  const val = el && el.dataset.statsPollInterval;
  const n = parseInt(val, 10);
  return Number.isFinite(n) && n > 0 ? n : 1;
}

let refreshCountdown = 10;

const DOWNLOAD_STATE_KEY = "ollamaDashboardActiveDownloads";
const DOWNLOAD_RESUME_POLL_MS = 2500;
const DOWNLOAD_RESUME_TIMEOUT_MS = 7200000;
const _downloadResumeTimers = new Map();

function getActiveDownloads() {
  try {
    const raw = sessionStorage.getItem(DOWNLOAD_STATE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_) {
    return {};
  }
}

function saveActiveDownloads(map) {
  try {
    sessionStorage.setItem(DOWNLOAD_STATE_KEY, JSON.stringify(map || {}));
  } catch (_) {}
}

function setDownloadState(modelName, state) {
  const name = String(modelName || "").trim();
  if (!name) return;
  const all = getActiveDownloads();
  if (!state) {
    delete all[name];
  } else {
    all[name] = { ...state, updatedAt: Date.now() };
  }
  saveActiveDownloads(all);
}

function clearDownloadState(modelName) {
  setDownloadState(modelName, null);
  const t = _downloadResumeTimers.get(modelName);
  if (t) {
    clearInterval(t);
    _downloadResumeTimers.delete(modelName);
  }
}

function hasAnyActiveDownload() {
  return Object.keys(getActiveDownloads()).length > 0;
}

function augmentAvailableModelsForDownloads(models) {
  const list = Array.isArray(models) ? models.slice() : [];
  const apiNames = new Set(
    list.map((m) => (m && m.name ? String(m.name).trim() : "")).filter(Boolean),
  );
  for (const [name, state] of Object.entries(getActiveDownloads())) {
    if (!name || apiNames.has(name)) continue;
    list.unshift({
      name,
      details: { family: "Unknown", parameter_size: "Unknown" },
      formatted_size: state.percent != null ? "Downloading…" : "Downloading…",
      context_length: "—",
      _downloadPlaceholder: true,
    });
  }
  return list;
}

function applyDownloadStateToCard(modelName, state) {
  const esc = cssEscape(modelName);
  const card =
    document.querySelector(
      `#availableModelsContainer .model-card[data-model-name="${esc}"]`,
    ) || document.querySelector(`.model-card[data-model-name="${esc}"]`);
  if (!card || !state) return;

  card.dataset.downloadActive = "true";
  const button =
    card.querySelector(".btn-dashboard-download") ||
    card.querySelector(".model-actions--available .btn-primary");
  const progressContainer = card.querySelector(".download-progress");
  const progressBar = progressContainer
    ? progressContainer.querySelector(".progress-bar")
    : null;
  const progressText = progressContainer
    ? progressContainer.querySelector("small")
    : null;

  if (progressContainer) {
    progressContainer.classList.remove("d-none");
    progressContainer.style.display = "block";
  }
  if (button) {
    button.disabled = true;
    const msg = state.message || "Downloading...";
    if (state.status === "complete") {
      button.innerHTML = '<i class="fas fa-check me-1"></i>Downloaded';
    } else {
      button.innerHTML = `<i class="fas fa-download me-1"></i>${typeof escapeHtml === "function" ? escapeHtml(msg) : msg}`;
    }
  }
  const percent =
    state.percent != null && !Number.isNaN(Number(state.percent))
      ? Math.max(0, Math.min(100, Number(state.percent)))
      : null;
  if (percent != null) {
    if (progressBar) {
      progressBar.style.width = `${percent}%`;
      progressBar.setAttribute("aria-valuenow", String(percent));
    }
    if (progressText) {
      progressText.textContent = `${percent}%`;
    }
  } else if (progressText && state.status === "downloading") {
    progressText.textContent = "…";
  }
}

function restoreAllDownloadUi() {
  for (const [name, state] of Object.entries(getActiveDownloads())) {
    ensureAvailableCardForDownload(name);
    applyDownloadStateToCard(name, state);
  }
}

function pollForDownloadCompletion(modelName) {
  const name = String(modelName || "").trim();
  if (!name || _downloadResumeTimers.has(name)) return;

  const started = Date.now();
  const timer = setInterval(async function () {
    if (Date.now() - started > DOWNLOAD_RESUME_TIMEOUT_MS) {
      clearDownloadState(name);
      return;
    }
    try {
      const response = await fetch("/api/models/available");
      const ar = await readApiJson(response);
      if (!ar.responseOk) return;
      const models = Array.isArray(ar.data?.models) ? ar.data.models : [];
      const found = models.some(
        (m) => m && String(m.name || "").trim() === name,
      );
      if (found) {
        clearDownloadState(name);
        const card = document.querySelector(
          `#availableModelsContainer .model-card[data-model-name="${cssEscape(name)}"]`,
        );
        if (card) delete card.dataset.downloadActive;
        if (typeof updateModelData === "function") {
          void updateModelData();
        }
      }
    } catch (_) {}
  }, DOWNLOAD_RESUME_POLL_MS);

  _downloadResumeTimers.set(name, timer);
}

function resumeActiveDownloads() {
  const active = getActiveDownloads();
  for (const [name, state] of Object.entries(active)) {
    ensureAvailableCardForDownload(name);
    applyDownloadStateToCard(name, state);
    if (state.status === "downloading") {
      pollForDownloadCompletion(name);
    }
  }
}

function scheduleReloadUnlessDownloading() {
  if (typeof hasAnyActiveDownload === "function" && hasAnyActiveDownload()) {
    const started = Date.now();
    const wait = setInterval(function () {
      if (!hasAnyActiveDownload()) {
        clearInterval(wait);
        location.reload();
        return;
      }
      if (Date.now() - started > DOWNLOAD_RESUME_TIMEOUT_MS) {
        clearInterval(wait);
        location.reload();
      }
    }, 2000);
    return;
  }
  location.reload();
}

window.hasAnyActiveDownload = hasAnyActiveDownload;
window.scheduleReloadUnlessDownloading = scheduleReloadUnlessDownloading;
window.resumeActiveDownloads = resumeActiveDownloads;

function resetRefreshCountdown() {
  refreshCountdown = getPollIntervalSec();
  const el = document.getElementById("nextRefresh");
  if (el) el.textContent = String(refreshCountdown);
}

// Timer and UI update functions
function updateTimes() {
  const refreshIndicator = document.querySelector(".refresh-indicator");
  const tzAbbr = refreshIndicator ? refreshIndicator.dataset.timezone : "";
  refreshCountdown = getPollIntervalSec();

  const tick = () => {
    const now = new Date();
    const timeStr = now.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    const displayText = tzAbbr ? `${timeStr} ${tzAbbr}` : timeStr;
    const lastEl = document.getElementById("lastUpdate");
    if (lastEl) lastEl.textContent = displayText;

    const nextEl = document.getElementById("nextRefresh");
    if (nextEl) {
      refreshCountdown--;
      if (refreshCountdown <= 0) {
        refreshCountdown = getPollIntervalSec();
        // Keep running models list in sync when models change outside this app (CLI, other UIs).
        if (typeof updateModelData === "function") {
          void updateModelData();
        }
      }
      nextEl.textContent = String(refreshCountdown);
    }
  };

  tick();
  setInterval(tick, 1000);
}

function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  const toggleButton = document.getElementById("toggleButton");
  sidebar.classList.toggle("show");
  toggleButton.innerHTML = sidebar.classList.contains("show") ? "✕" : "📋";
}

// Model management functions

/** Refresh all dashboard data (models + stats) without full page reload. */
function refreshDashboardData() {
  [
    document.getElementById("refreshDashboardBtn"),
    document.getElementById("refreshModelsBtn"),
  ].forEach(function (btn) {
    if (btn) {
      const icon = btn.querySelector("i");
      if (icon) {
        icon.classList.add("fa-spin");
        setTimeout(function () {
          icon.classList.remove("fa-spin");
        }, 800);
      }
    }
  });
  if (typeof updateModelData === "function") updateModelData();
  if (typeof updateSystemStats === "function") updateSystemStats();
}

/**
 * Poll for model status change and refresh UI when confirmed.
 * @param {string} modelName - Name of the model to check
 * @param {boolean} shouldBeRunning - True if we expect the model to be running, false if stopped
 */
async function pollForModelStatus(modelName, shouldBeRunning) {
  const maxAttempts = 20;
  const delays = [500, 500, 1000, 1000, 1000, 1500, 1500, 2000, 2000, 2000];

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const delay = delays[Math.min(attempt, delays.length - 1)];
    await new Promise((resolve) => setTimeout(resolve, delay));

    try {
      const response = await fetch("/api/models/running");
      const pr = await readApiJson(response);
      if (pr.responseOk) {
        const data = pr.data;
        const runningModels = Array.isArray(data.models) ? data.models : [];
        const want = String(modelName || "").trim();
        const isRunning = runningModels.some(
          (m) => String(m && m.name != null ? m.name : "").trim() === want,
        );

        if (isRunning === shouldBeRunning) {
          refreshDashboardData();
          return;
        }
      }
    } catch (error) {
      console.log("Error polling model status:", error);
    }
  }

  refreshDashboardData();
}

/**
 * Poll until the model is no longer in the available list, then return.
 * Caller should reload the page. Times out after maxAttempts to avoid waiting forever.
 */
async function pollForModelDeleted(
  modelName,
  maxAttempts = 15,
  delayMs = 1000,
) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    try {
      const response = await fetch("/api/models/available");
      const pr = await readApiJson(response);
      if (pr.responseOk) {
        const data = pr.data;
        const models = Array.isArray(data.models) ? data.models : [];
        const stillPresent = models.some(
          (m) =>
            m.name === modelName ||
            (m.name && m.name.startsWith(modelName + ":")),
        );
        if (!stillPresent) return;
      }
    } catch (error) {
      console.log("Error polling for deleted model:", error);
    }
  }
}

async function startModel(modelName) {
  try {
    const response = await fetch(
      `/api/models/start/${encodeURIComponent(modelName)}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      },
    );
    const r = await readApiJson(response);
    if (!r.responseOk) {
      showNotification(
        r.message || `Failed to start model (HTTP ${r.status})`,
        "error",
      );
      return;
    }
    const result = r.data;
    if (result.success) {
      showNotification(result.message, "success");
      await pollForModelStatus(modelName, true);
    } else {
      showNotification(result.message, "error");
    }
  } catch (error) {
    showNotification("Failed to start model: " + error.message, "error");
  }
}

async function stopModel(modelName, force) {
  const card = document.querySelector(
    `.model-card[data-model-name="${cssEscape(modelName)}"]`,
  );
  const stopButton = card
    ? card.querySelector('button[data-model-action="stop"]')
    : null;
  const originalText = stopButton ? stopButton.innerHTML : null;
  if (stopButton) {
    stopButton.innerHTML = force
      ? '<i class="fas fa-spinner fa-spin me-1"></i>Force stopping...'
      : '<i class="fas fa-spinner fa-spin me-1"></i>Stopping...';
    stopButton.disabled = true;
  }

  try {
    showNotification(
      force
        ? `Force-unloading ${modelName} via Ollama restart...`
        : `Attempting to stop model ${modelName}...`,
      "info",
    );

    const response = await fetch(
      `/api/models/stop/${encodeURIComponent(modelName)}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ force: !!force }),
      },
    );

    const sr = await readApiJson(response);
    if (!sr.responseOk) {
      const canForce = sr.data && sr.data.can_force;
      if (canForce && !force) {
        const retry = window.confirm(
          `Could not stop ${modelName}. Restart Ollama to force-unload all models from memory?`,
        );
        if (retry) {
          if (stopButton && originalText !== null) {
            stopButton.innerHTML = originalText;
            stopButton.disabled = false;
          }
          return stopModel(modelName, true);
        }
      }
      showNotification(
        sr.message || `Failed to stop model (HTTP ${sr.status})`,
        "error",
      );
      if (stopButton && originalText !== null) {
        stopButton.innerHTML = originalText;
        stopButton.disabled = false;
      }
      return;
    }

    const result = sr.data;
    if (result.success) {
      const level = result.restart_required ? "warning" : "success";
      showNotification(
        result.message || `Model ${modelName} stopped successfully`,
        level,
      );
      if (force || result.memory_cleared) {
        if (typeof window.serviceControl?.updateHealthStatus === "function") {
          window.serviceControl.updateHealthStatus();
        }
        setTimeout(() => scheduleReloadUnlessDownloading(), 2000);
      } else {
        await pollForModelStatus(modelName, false);
      }
    } else {
      showNotification(
        result.message || `Failed to stop model ${modelName}`,
        "error",
      );
      if (stopButton && originalText !== null) {
        stopButton.innerHTML = originalText;
        stopButton.disabled = false;
      }
    }
  } catch (error) {
    showNotification(
      "Failed to stop model: " + (error.message || "Network error"),
      "error",
    );
    if (stopButton && originalText !== null) {
      stopButton.innerHTML = originalText;
      stopButton.disabled = false;
    }
  }
}

/** Last successful /api/models/running payload (for callers that need the latest list). */
let _lastRunningModelsSnapshot = null;

async function restartModel(modelName) {
  const card = document.querySelector(
    `.model-card[data-model-name="${cssEscape(modelName)}"]`,
  );
  const restartButton = card
    ? card.querySelector('button[data-model-action="restart"]')
    : null;
  if (restartButton && restartButton.disabled) {
    return;
  }
  const originalText = restartButton ? restartButton.innerHTML : null;
  if (restartButton) {
    restartButton.innerHTML =
      '<i class="fas fa-spinner fa-spin me-1"></i>Restarting...';
    restartButton.disabled = true;
  }

  try {
    showNotification(`Restarting model ${modelName}...`, "info");

    const response = await fetch(
      `/api/models/restart/${encodeURIComponent(modelName)}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      },
    );
    const r = await readApiJson(response);
    if (!r.responseOk) {
      showNotification(
        r.message || `Failed to restart model (HTTP ${r.status})`,
        "error",
      );
    } else if (r.data.success) {
      const result = r.data;
      showNotification(result.message, "success");
      await pollForModelStatus(modelName, true);
    } else {
      showNotification(r.data.message || "Restart failed", "error");
    }
  } catch (error) {
    showNotification("Failed to restart model: " + error.message, "error");
  } finally {
    if (restartButton && originalText !== null) {
      restartButton.innerHTML = originalText;
      restartButton.disabled = false;
    }
  }
}

async function deleteModel(modelName) {
  if (
    !confirm(
      `Are you sure you want to delete the model "${modelName}"? This action cannot be undone.`,
    )
  ) {
    return;
  }

  const card = document.querySelector(
    `.model-card[data-model-name="${cssEscape(modelName)}"]`,
  );
  const deleteButton = card
    ? card.querySelector('button[data-model-action="delete"]')
    : null;
  const originalText = deleteButton ? deleteButton.innerHTML : null;
  if (deleteButton) {
    deleteButton.innerHTML =
      '<i class="fas fa-spinner fa-spin me-1"></i>Deleting...';
    deleteButton.disabled = true;
  }

  try {
    showNotification(`Deleting model ${modelName}...`, "info");

    const response = await fetch(
      `/api/models/delete/${encodeURIComponent(modelName)}`,
      {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
      },
    );
    const dr = await readApiJson(response);
    const result = dr.responseOk
      ? dr.data
      : {
          success: false,
          message: dr.message || `HTTP ${dr.status}`,
        };

    if (!dr.responseOk) {
      showNotification(result.message || `HTTP ${response.status}`, "error");
    } else if (result.success) {
      showNotification(result.message, "success");
      await pollForModelDeleted(modelName);
      scheduleReloadUnlessDownloading();
    } else {
      showNotification(result.message || "Failed to delete model.", "error");
    }
  } catch (error) {
    showNotification(
      "Failed to delete model: " + (error?.message || error),
      "error",
    );
  } finally {
    if (deleteButton && originalText !== null) {
      deleteButton.innerHTML = originalText;
      deleteButton.disabled = false;
    }
  }
}

async function showModelInfo(modelName) {
  try {
    const response = await fetch(
      `/api/models/info/${encodeURIComponent(modelName)}`,
    );
    const ir = await readApiJson(response);
    if (!ir.responseOk) {
      showNotification(
        ir.message || `Failed to get model info (HTTP ${ir.status})`,
        "error",
      );
      return;
    }
    const info = ir.data;

    {
      // Fetch backend cards data to ensure capability flags match the main cards
      let flagsFromCards = null;
      const normalizeName = (n) => {
        if (!n || typeof n !== "string") return "";
        return n.trim().toLowerCase();
      };
      const stripTag = (n) => n.replace(/:[^\s]+$/, "");
      const baseSegment = (n) => {
        // Take last path segment if name contains slashes
        const parts = n.split("/");
        return parts[parts.length - 1];
      };
      const equalsLoose = (a, b) => {
        if (!a || !b) return false;
        if (a === b) return true;
        if (stripTag(a) === stripTag(b)) return true;
        const ab = baseSegment(a),
          bb = baseSegment(b);
        if (ab === bb) return true;
        if (stripTag(ab) === stripTag(bb)) return true;
        return false;
      };
      const targetRaw = modelName || info.model || info.name || "";
      const target = normalizeName(targetRaw);
      try {
        const [availResp, runningResp, dlBestResp] = await Promise.all([
          fetch("/api/models/available"),
          fetch("/api/models/running"),
          fetch("/api/models/downloadable?category=best"),
        ]);
        const availR = await readApiJson(availResp);
        if (availR.responseOk) {
          const availJson = availR.data;
          const list = Array.isArray(availJson.models) ? availJson.models : [];
          const match = list.find((m) => {
            const mn = normalizeName(m?.name || m?.model || "");
            return equalsLoose(mn, target);
          });
          if (match) flagsFromCards = match;
        }
        const runR = await readApiJson(runningResp);
        if (!flagsFromCards && runR.responseOk) {
          const runningJson = runR.data;
          const runningList = Array.isArray(runningJson.models)
            ? runningJson.models
            : [];
          const rmatch =
            runningList.find((m) => {
              const rn = normalizeName(m?.name || m?.model || "");
              return equalsLoose(rn, target);
            }) || null;
          if (rmatch) flagsFromCards = rmatch;
        }
        const dlR = await readApiJson(dlBestResp);
        if (!flagsFromCards && dlR.responseOk) {
          const dlJson = dlR.data;
          const dlList = Array.isArray(dlJson.models) ? dlJson.models : [];
          const dmatch = dlList.find((m) => {
            const dn = normalizeName(m?.name || m?.model || "");
            return equalsLoose(dn, target);
          });
          if (dmatch) flagsFromCards = dmatch;
        }
      } catch (e) {
        // Non-fatal: fallback to info-derived flags below
      }

      const details = info.details || {};
      const summaryHtml = buildModelSummary(info, details, modelName);
      const capabilityPayload = buildCapabilityPayloadForModal(
        flagsFromCards || info,
      );
      const capabilityBadges = renderCapabilityBadges(capabilityPayload);
      // flagsSourceLabel removed after verification
      const modelfileBlock = info.modelfile
        ? `<pre class="model-code-block">${escapeHtml(info.modelfile)}</pre>`
        : '<span class="text-muted">No modelfile provided</span>';
      const parametersBlock = info.parameters
        ? `<pre class="model-code-block">${escapeHtml(info.parameters)}</pre>`
        : '<span class="text-muted">No parameters provided</span>';
      const rawJson = escapeHtml(JSON.stringify(info, null, 2));

      const modalHtml = `
        <div class="modal fade" id="modelInfoModal" tabindex="-1" aria-labelledby="modelInfoTitle">
          <div class="modal-dialog modal-xl modal-dialog-centered">
            <div class="modal-content model-info-card">
              <div class="modal-header model-info-header">
                <div class="model-title-group">
                  <h5 class="modal-title" id="modelInfoTitle">${modelName}</h5>
                  <div class="model-info-subtitle">Detailed model information</div>
                </div>
                <div class="d-flex align-items-center gap-2 flex-wrap">
                  ${capabilityBadges}
                  <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Close</button>
                </div>
              </div>
              <div class="modal-body model-info-body">
                ${summaryHtml}

                <section class="model-info-section">
                  <div class="section-header">
                    <div>
                      <h6 class="section-title">Details</h6>
                      <p class="section-hint">Core metadata reported by Ollama</p>
                    </div>
                  </div>
                  <div class="table-responsive">
                    ${jsonToTable(details)}
                  </div>
                </section>

                <section class="model-info-section">
                  <div class="section-header d-flex flex-wrap justify-content-between align-items-start gap-2">
                    <div>
                      <h6 class="section-title">Parameters</h6>
                      <p class="section-hint">Runtime overrides and defaults</p>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-secondary mc-copy-parameters">Copy</button>
                  </div>
                  <div class="model-code-wrapper">${parametersBlock}</div>
                </section>

                <section class="model-info-section">
                  <div class="section-header d-flex flex-wrap justify-content-between align-items-start gap-2">
                    <div>
                      <h6 class="section-title">Modelfile</h6>
                      <p class="section-hint">Source definition used to build this model</p>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-secondary mc-copy-modelfile">Copy</button>
                  </div>
                  <div class="model-code-wrapper">${modelfileBlock}</div>
                </section>

                <div class="accordion" id="modelRawJson">
                  <div class="accordion-item">
                    <h2 class="accordion-header" id="headingRawJson">
                      <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapseRawJson" aria-expanded="false" aria-controls="collapseRawJson">
                        Raw JSON
                      </button>
                    </h2>
                    <div id="collapseRawJson" class="accordion-collapse collapse" aria-labelledby="headingRawJson" data-bs-parent="#modelRawJson">
                      <div class="accordion-body">
                        <pre class="raw-json-block">${rawJson}</pre>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      `;

      document.body.insertAdjacentHTML("beforeend", modalHtml);
      const modalRoot = document.getElementById("modelInfoModal");
      const btnP = modalRoot.querySelector(".mc-copy-parameters");
      if (btnP) {
        btnP.onclick = function () {
          if (window.modelCardActions && modelCardActions.copyText) {
            modelCardActions.copyText(
              info.parameters || "",
              "Parameters copied",
            );
          }
        };
      }
      const btnM = modalRoot.querySelector(".mc-copy-modelfile");
      if (btnM) {
        btnM.onclick = function () {
          if (window.modelCardActions && modelCardActions.copyText) {
            modelCardActions.copyText(info.modelfile || "", "Modelfile copied");
          }
        };
      }
      const modal = new bootstrap.Modal(modalRoot);
      modal.show();

      modalRoot.addEventListener("hidden.bs.modal", function () {
        this.remove();
      });
    }
  } catch (error) {
    showNotification("Failed to get model info: " + error.message, "error");
  }
}

// ===== Ask? modal =====
let _askModelName = null;
let _askAbortController = null;

function openAskModal(modelName) {
  _askModelName = modelName;
  _askAbortController = null;

  const nameEl = document.getElementById("askModelModalName");
  if (nameEl) nameEl.textContent = modelName;

  const input = document.getElementById("askModelInput");
  if (input) {
    input.value = "";
    input.onkeydown = function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendAskModelQuestion();
      }
    };
  }

  const responseWrap = document.getElementById("askModelResponseWrap");
  if (responseWrap) responseWrap.style.display = "none";

  const responseEl = document.getElementById("askModelResponse");
  if (responseEl) responseEl.textContent = "";

  const spinner = document.getElementById("askModelSpinner");
  if (spinner) spinner.style.display = "none";

  const sendBtn = document.getElementById("askModelSendBtn");
  if (sendBtn) sendBtn.disabled = false;

  const modalEl = document.getElementById("askModelModal");
  if (!modalEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.show();

  // Focus textarea after modal is shown
  modalEl.addEventListener("shown.bs.modal", function onShown() {
    modalEl.removeEventListener("shown.bs.modal", onShown);
    if (input) input.focus();
  });

  // Abort any in-flight request when modal is hidden
  modalEl.addEventListener("hidden.bs.modal", function onHidden() {
    modalEl.removeEventListener("hidden.bs.modal", onHidden);
    if (_askAbortController) {
      _askAbortController.abort();
      _askAbortController = null;
    }
  });
}

async function sendAskModelQuestion() {
  const question = (document.getElementById("askModelInput")?.value || "").trim();
  if (!question) return;

  const sendBtn = document.getElementById("askModelSendBtn");
  const spinner = document.getElementById("askModelSpinner");
  const responseWrap = document.getElementById("askModelResponseWrap");
  const responseEl = document.getElementById("askModelResponse");

  if (sendBtn) sendBtn.disabled = true;
  if (responseWrap) responseWrap.style.display = "";
  if (responseEl) responseEl.textContent = "";
  if (spinner) spinner.style.display = "";

  if (_askAbortController) _askAbortController.abort();
  _askAbortController = new AbortController();

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: _askModelName,
        prompt: question,
        stream: true,
      }),
      signal: _askAbortController.signal,
    });

    if (!resp.ok) {
      let errMsg = `HTTP ${resp.status}`;
      try {
        const errJson = await resp.json();
        errMsg = errJson.error || errMsg;
      } catch (_) {}
      if (responseEl) responseEl.textContent = "Error: " + errMsg;
      if (spinner) spinner.style.display = "none";
      if (sendBtn) sendBtn.disabled = false;
      return;
    }

    if (spinner) spinner.style.display = "";

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let gotFirstToken = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete last line
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const parsed = JSON.parse(trimmed);
          if (parsed.response != null) {
            if (!gotFirstToken) {
              gotFirstToken = true;
              if (spinner) spinner.style.display = "none";
            }
            if (responseEl) {
              responseEl.textContent += parsed.response;
              // auto-scroll
              responseEl.scrollTop = responseEl.scrollHeight;
            }
          }
        } catch (_) {
          // skip non-JSON lines
        }
      }
    }
    // flush remaining buffer
    if (buffer.trim()) {
      try {
        const parsed = JSON.parse(buffer.trim());
        if (parsed.response != null && responseEl) {
          responseEl.textContent += parsed.response;
          responseEl.scrollTop = responseEl.scrollHeight;
        }
      } catch (_) {}
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      if (responseEl) responseEl.textContent = "Error: " + err.message;
    }
  } finally {
    if (spinner) spinner.style.display = "none";
    if (sendBtn) sendBtn.disabled = false;
    _askAbortController = null;
  }
}
// ===== End Ask? modal =====

function buildModelSummary(info, details, modelName) {
  const summaryItems = [];

  const families = details.families || (details.family ? [details.family] : []);
  if (families.length) {
    summaryItems.push({ label: "Family", value: families.join(", ") });
  }

  if (details.parameter_size) {
    summaryItems.push({ label: "Parameters", value: details.parameter_size });
  }

  if (details.quantization_level) {
    summaryItems.push({
      label: "Quantization",
      value: details.quantization_level,
    });
  }

  if (details.license) {
    summaryItems.push({ label: "License", value: String(details.license) });
  }

  if (details.model_type) {
    summaryItems.push({
      label: "Model type",
      value: String(details.model_type),
    });
  }

  if (details.format) {
    summaryItems.push({ label: "Format", value: details.format });
  }

  if (typeof info.size === "number") {
    const sizeLabel = formatBytes(info.size);
    if (sizeLabel) {
      summaryItems.push({ label: "Size", value: sizeLabel });
    }
  }

  const updated = formatDate(
    info.modified_at || info.updated_at || info.created_at,
  );
  if (updated) {
    summaryItems.push({ label: "Updated", value: updated });
  }

  if (!summaryItems.length) {
    return "";
  }

  const summaryHtml = summaryItems
    .map(
      (item) => `
        <div class="summary-item">
          <div class="summary-label">${escapeHtml(item.label)}</div>
          <div class="summary-value">${escapeHtml(String(item.value))}</div>
        </div>
      `,
    )
    .join("");

  return `
    <section class="model-info-section">
      <div class="section-header">
        <div>
          <h6 class="section-title">At a Glance</h6>
          <p class="section-hint">Key properties for ${escapeHtml(info.model || info.name || modelName)}</p>
        </div>
      </div>
      <div class="model-summary-grid">${summaryHtml}</div>
    </section>
  `;
}

function formatBytes(bytes) {
  if (typeof bytes !== "number" || Number.isNaN(bytes)) {
    return null;
  }

  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let value = bytes;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  const precision = value >= 10 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
}

function formatDate(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
}

function renderCapabilityBadges(info) {
  const r = info?.has_reasoning,
    v = info?.has_vision,
    t = info?.has_tools;
  const badges = [
    { label: "Reasoning", icon: "fa-brain", val: r },
    { label: "Vision", icon: "fa-image", val: v },
    { label: "Tools", icon: "fa-tools", val: t },
  ];

  return badges
    .map((badge) => {
      const state = capState(badge.val);
      const title = capTitle(badge.val, badge.label);
      return `<span class="capability-pill ${state}" data-dashboard-tooltip="${title}">
          <i class="fas ${badge.icon}"></i>
          <span>${badge.label}</span>
        </span>`;
    })
    .join("");
}

// Settings logic extracted to modules/settings.js; legacy global kept via window.openModelSettingsModal

// Service control logic extracted to modules/serviceControl.js

// Model settings related helper functions removed (submit/delete) now in settings.js

// Health status & service control update functions extracted to serviceControl.js

// Removed DOMContentLoaded initialization (moved to modules/bootstrap.js)
// (Removed inline settings modal construction block; now provided by modules/settings.js)

// submitModelSettings & deleteModelSettings moved to settings.js

function jsonToTable(json, level = 0) {
  if (json === null || json === undefined) {
    return '<span class="text-muted">null</span>';
  }

  if (typeof json === "boolean") {
    return `<span class="text-primary">${json}</span>`;
  }

  if (typeof json === "number") {
    return `<span class="text-success">${json}</span>`;
  }

  if (typeof json === "string") {
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(json)) {
      return `<span class="text-info">${escapeHtml(
        new Date(json).toLocaleString(),
      )}</span>`;
    }
    const maxLength = 100;
    if (json.length > maxLength) {
      const truncated = json.substring(0, maxLength);
      return `<span class="text-warning" data-dashboard-tooltip="${escapeHtml(json)}">"${escapeHtml(truncated)}..."</span>`;
    }
    return `<span class="text-warning">"${escapeHtml(json)}"</span>`;
  }

  if (Array.isArray(json)) {
    if (json.length === 0) {
      return '<span class="text-muted">[]</span>';
    }

    let html = '<div class="array-container">';
    html += `<div class="array-meta">Array (${json.length})</div>`;
    json.forEach((item, index) => {
      html += `<div class="array-item">
                <span class="array-index">[${index}]</span>
                ${jsonToTable(item, level + 1)}
            </div>`;
    });
    html += "</div>";
    return html;
  }

  if (typeof json === "object") {
    const keys = Object.keys(json);
    if (keys.length === 0) {
      return '<span class="text-muted">{}</span>';
    }

    let html = `<table class="table table-sm json-table level-${level}">`;
    if (level === 0) {
      html += "<thead><tr><th>Property</th><th>Value</th></tr></thead>";
    }
    html += "<tbody>";

    keys.forEach((key) => {
      const value = json[key];
      const formattedKey = key
        .replace(/_/g, " ")
        .replace(/\b\w/g, (l) => l.toUpperCase());

      html += "<tr>";
      html += `<td class="json-key-cell" style="padding-left: ${
        level * 20
      }px"><strong>${escapeHtml(formattedKey)}</strong></td>`;
      html += '<td class="json-value-cell">';

      if (typeof value === "object" && value !== null) {
        html += jsonToTable(value, level + 1);
      } else {
        html += jsonToTable(value, level);
      }

      html += "</td>";
      html += "</tr>";
    });

    html += "</tbody></table>";
    return html;
  }

  return String(json);
}

// Moved escapeHtml and cssEscape to modules/utils.js; legacy globals preserved there.

function showNotification(message, type) {
  const notification = document.createElement("div");
  const isError = type === "error" || type === "danger";
  const alertClass = isError
    ? "danger"
    : type === "success"
      ? "success"
      : "info";
  notification.className = `alert alert-${alertClass} alert-dismissible fade show position-fixed`;
  notification.style.cssText =
    "top: 20px; right: 20px; z-index: 9999; min-width: 300px; max-width: 500px;";

  // Add copy button for error messages
  const copyButton = isError
    ? `
    <button type="button" class="btn btn-sm btn-outline-light" onclick="copyErrorToClipboard(this)"
            style="padding: 0.25rem 0.5rem; font-size: 0.75rem; flex-shrink: 0;" data-dashboard-tooltip="Copy error to clipboard">
      <i class="fas fa-copy"></i> Copy
    </button>
  `
    : "";

  notification.innerHTML = `
        <div style="display: flex; align-items: start; gap: 10px;">
          <div style="flex: 1; min-width: 0;" data-error-message="${message.replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}">${message}</div>
          <div style="display: flex; gap: 5px; align-items: center; flex-shrink: 0;">
            ${copyButton}
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="alert" aria-label="Close"></button>
          </div>
        </div>
    `;
  document.body.appendChild(notification);

  setTimeout(() => {
    if (notification.parentNode) {
      notification.remove();
    }
  }, 5000);
}

function afterModelCardsRendered() {
  if (
    window.modelCardActions &&
    typeof modelCardActions.enhanceAllModelCards === "function"
  ) {
    modelCardActions.enhanceAllModelCards();
  }
}

function copyErrorToClipboard(button) {
  const errorDiv = button
    .closest(".alert")
    .querySelector("[data-error-message]");
  const errorMessage = errorDiv.getAttribute("data-error-message");

  navigator.clipboard
    .writeText(errorMessage)
    .then(() => {
      const originalContent = button.innerHTML;
      button.innerHTML = '<i class="fas fa-check"></i> Copied!';
      button.disabled = true;

      setTimeout(() => {
        button.innerHTML = originalContent;
        button.disabled = false;
      }, 2000);
    })
    .catch((err) => {
      console.error("Failed to copy error:", err);
      button.innerHTML = '<i class="fas fa-times"></i> Failed';
      setTimeout(() => {
        button.innerHTML = '<i class="fas fa-copy"></i> Copy';
      }, 2000);
    });
}

// Capability state: green=enabled, grey=disabled (known not functional), yellow=unknown
function capState(val) {
  if (val === true) return "enabled";
  if (val === false) return "disabled";
  return "unknown";
}
function capTitle(val, label) {
  if (val === true) return `${label}: Available`;
  if (val === false) return `${label}: Not available`;
  return `${label}: Unknown`;
}

// Capability rendering using backend-provided flags
/** Backend + API may expose has_custom_settings as boolean; normalize for UI. */
function modelHasCustomSettings(model) {
  if (!model || typeof model !== "object") return false;
  const v = model.has_custom_settings;
  if (v === false || v === "false" || v === 0 || v === "0") return false;
  return v === true || v === "true" || v === 1 || v === "1" || v === "yes";
}

function getSettingsButtonInnerHtml(hasCustom) {
  if (
    window.modelCards &&
    typeof window.modelCards.modelActionSettingsButtonInner === "function"
  ) {
    return window.modelCards.modelActionSettingsButtonInner(hasCustom);
  }
  const status = hasCustom
    ? '<span class="badge rounded-pill model-settings-status-badge model-settings-status-badge--saved" data-dashboard-tooltip="Custom per-model options saved for this dashboard (temperature, context, etc.)." aria-label="Saved custom defaults"><i class="fas fa-floppy-disk model-settings-status-ic" aria-hidden="true"></i><span>Saved</span></span>'
    : '<span class="badge rounded-pill model-settings-status-badge model-settings-status-badge--default" data-dashboard-tooltip="Using recommended or built-in defaults — nothing custom saved yet for this model." aria-label="Using default settings"><i class="fas fa-floppy-disk model-settings-status-ic" aria-hidden="true"></i><span>Default</span></span>';
  return `<span class="model-action-settings-inner"><i class="fas fa-cog" aria-hidden="true"></i><span class="model-action-btn-label">Settings</span>${status}</span>`;
}

/** Keep Settings action in sync when cards are updated in place (e.g. available list poll). */
function syncSettingsSavedIndicatorOnCard(card, model) {
  if (!card || !model) return;
  const btn = card.querySelector(".model-action-settings-btn");
  if (!btn) return;
  const hasCustom = modelHasCustomSettings(model);
  btn.innerHTML = getSettingsButtonInnerHtml(hasCustom);
  btn.setAttribute(
    "aria-label",
    hasCustom
      ? "Settings (saved custom defaults)"
      : "Settings (using defaults)",
  );
}

function getCapabilitiesHTML(model) {
  const r = model?.has_reasoning;
  const v = model?.has_vision;
  const t = model?.has_tools;
  return `
    <span class="capability-icon ${capState(r)}" data-dashboard-tooltip="${capTitle(r, "Reasoning")}">
      <i class="fas fa-brain"></i>
    </span>
    <span class="capability-icon ${capState(v)}" data-dashboard-tooltip="${capTitle(v, "Image Processing")}">
      <i class="fas fa-image"></i>
    </span>
    <span class="capability-icon ${capState(t)}" data-dashboard-tooltip="${capTitle(t, "Tool Usage")}">
      <i class="fas fa-tools"></i>
    </span>
  `;
}

/**
 * Build { has_reasoning, has_vision, has_tools } for the info modal using the same
 * rules as cards: prefer backend-normalized flags, else Ollama capabilities[] (see capabilities.py).
 */
function flagsFromOllamaCapabilitiesArray(capsList) {
  if (!Array.isArray(capsList) || capsList.length === 0) return null;
  const capsLower = capsList.map((c) => String(c).toLowerCase().trim());
  const visionAliases = ["vision", "image", "multimodal"];
  const toolsAliases = [
    "tools",
    "tool",
    "function",
    "function-calling",
    "tool-use",
  ];
  const reasoningAliases = ["reasoning", "thinking", "think"];
  const has = (aliases) => aliases.some((a) => capsLower.includes(a));
  return {
    has_vision: has(visionAliases),
    has_tools: has(toolsAliases),
    has_reasoning: has(reasoningAliases),
  };
}

function buildCapabilityPayloadForModal(src) {
  if (!src || typeof src !== "object") {
    return {
      has_reasoning: undefined,
      has_vision: undefined,
      has_tools: undefined,
    };
  }
  const explicit =
    "has_reasoning" in src || "has_vision" in src || "has_tools" in src;
  if (explicit) {
    return {
      has_reasoning: src.has_reasoning,
      has_vision: src.has_vision,
      has_tools: src.has_tools,
    };
  }
  const capsList =
    src.capabilities || (src.details && src.details.capabilities) || null;
  const fromArr = flagsFromOllamaCapabilitiesArray(capsList);
  if (fromArr) return fromArr;
  return {
    has_reasoning: undefined,
    has_vision: undefined,
    has_tools: undefined,
  };
}

// Historical data storage for timelines
const timelineData = {
  cpu: [],
  memory: [],
  vram: [],
  gpu3d: [],
  disk: [],
};

const MAX_TIMELINE_POINTS = 60; // 60 seconds of data

// System Resources sparklines — same palette as Claude-Hybrid header-ui timelines
const TIMELINE_COLOR_CPU = "#3b82f6";
const TIMELINE_COLOR_MEMORY = "#22c55e";
const TIMELINE_COLOR_VRAM = "#06b6d4";
const TIMELINE_COLOR_GPU3D = "#f59e0b";
const TIMELINE_COLOR_DISK = "#a855f7";

// Timeline drawing function
function drawTimeline(canvas, data, color) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  // Clear canvas
  ctx.clearRect(0, 0, width, height);

  if (data.length < 2) return;

  // Draw background grid
  ctx.strokeStyle = "rgba(255, 255, 255, 0.1)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, height * 0.25);
  ctx.lineTo(width, height * 0.25);
  ctx.moveTo(0, height * 0.5);
  ctx.lineTo(width, height * 0.5);
  ctx.moveTo(0, height * 0.75);
  ctx.lineTo(width, height * 0.75);
  ctx.stroke();

  // Fill area under the line
  ctx.fillStyle = color.replace("rgb", "rgba").replace(")", ", 0.3)");
  ctx.beginPath();
  ctx.moveTo(0, height); // Start from bottom-left

  const stepX = width / (data.length - 1);
  for (let i = 0; i < data.length; i++) {
    const x = i * stepX;
    const y = height - (data[i] / 100) * height;
    ctx.lineTo(x, y);
  }

  ctx.lineTo(width, height); // Close path to bottom-right
  ctx.closePath();
  ctx.fill();

  // Draw timeline line
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();

  for (let i = 0; i < data.length; i++) {
    const x = i * stepX;
    const y = height - (data[i] / 100) * height;

    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  }
  ctx.stroke();

  // Draw current value point
  const currentValue = data[data.length - 1];
  const currentX = (data.length - 1) * stepX;
  const currentY = height - (currentValue / 100) * height;

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(currentX, currentY, 3, 0, 2 * Math.PI);
  ctx.fill();
}

// System stats update function
async function updateSystemStats() {
  try {
    const response = await fetch("/api/system/stats");
    const sr = await readApiJson(response);
    if (!sr.responseOk || !sr.data) {
      return;
    }
    const stats = sr.data;
    const cpu =
      typeof stats.cpu_percent === "number" &&
      Number.isFinite(stats.cpu_percent)
        ? stats.cpu_percent
        : 0;
    const mem =
      stats.memory && typeof stats.memory === "object" ? stats.memory : {};
    const memPct =
      typeof mem.percent === "number" && Number.isFinite(mem.percent)
        ? mem.percent
        : 0;
    const vram = stats.vram && typeof stats.vram === "object" ? stats.vram : {};
    const vramTotal =
      typeof vram.total === "number" && Number.isFinite(vram.total)
        ? vram.total
        : 0;
    const vramPct =
      typeof vram.percent === "number" && Number.isFinite(vram.percent)
        ? vram.percent
        : 0;
    const gpu3d =
      typeof vram.gpu_3d === "number" && Number.isFinite(vram.gpu_3d)
        ? vram.gpu_3d
        : 0;
    const disk =
      stats.disk && typeof stats.disk === "object" ? stats.disk : {};
    const diskActivity =
      typeof disk.activity_percent === "number" &&
      Number.isFinite(disk.activity_percent)
        ? disk.activity_percent
        : 0;

    {
      // Update percentages
      const cpuPercentEl = document.getElementById("cpuPercent");
      const memoryPercentEl = document.getElementById("memoryPercent");
      const vramPercentEl = document.getElementById("vramPercent");
      const gpu3dPercentEl = document.getElementById("gpu3dPercent");
      const diskActivityPercentEl = document.getElementById(
        "diskActivityPercent",
      );

      if (cpuPercentEl) cpuPercentEl.textContent = `${cpu.toFixed(1)}%`;
      if (memoryPercentEl)
        memoryPercentEl.textContent = `${memPct.toFixed(1)}%`;
      if (vramPercentEl)
        vramPercentEl.textContent =
          vramTotal > 0 ? `${vramPct.toFixed(1)}%` : "--%";
      if (gpu3dPercentEl)
        gpu3dPercentEl.textContent =
          typeof vram.gpu_3d === "number" ? `${gpu3d.toFixed(1)}%` : "--%";
      if (diskActivityPercentEl)
        diskActivityPercentEl.textContent = `${diskActivity.toFixed(1)}%`;

      // Store historical data
      timelineData.cpu.push(cpu);
      timelineData.memory.push(memPct);
      timelineData.vram.push(vramTotal > 0 ? vramPct : 0);
      timelineData.gpu3d.push(typeof vram.gpu_3d === "number" ? gpu3d : 0);
      timelineData.disk.push(diskActivity);

      // Limit data points
      if (timelineData.cpu.length > MAX_TIMELINE_POINTS) {
        timelineData.cpu.shift();
        timelineData.memory.shift();
        timelineData.vram.shift();
        timelineData.gpu3d.shift();
        timelineData.disk.shift();
      }

      // Update timelines
      const cpuCanvas = document.getElementById("cpuTimeline");
      const memoryCanvas = document.getElementById("memoryTimeline");
      const vramCanvas = document.getElementById("vramTimeline");
      const gpu3dCanvas = document.getElementById("gpu3dTimeline");
      const diskCanvas = document.getElementById("diskTimeline");

      if (cpuCanvas)
        drawTimeline(cpuCanvas, timelineData.cpu, TIMELINE_COLOR_CPU);
      if (memoryCanvas)
        drawTimeline(memoryCanvas, timelineData.memory, TIMELINE_COLOR_MEMORY);
      if (vramCanvas)
        drawTimeline(vramCanvas, timelineData.vram, TIMELINE_COLOR_VRAM);
      if (gpu3dCanvas)
        drawTimeline(gpu3dCanvas, timelineData.gpu3d, TIMELINE_COLOR_GPU3D);
      if (diskCanvas)
        drawTimeline(diskCanvas, timelineData.disk, TIMELINE_COLOR_DISK);

      // Update last update time
      const lastUpdateTimeEl = document.getElementById("lastUpdateTime");
      if (lastUpdateTimeEl)
        lastUpdateTimeEl.textContent = new Date().toLocaleTimeString();
    }
  } catch (error) {
    console.log("Failed to update system stats:", error);
  }
}

let _versionPollCounter = 0;
// Version fetch every N model polls (default poll interval 10s from data-poll-interval → ~120s).
const VERSION_POLL_EVERY_N = 12;

// Model data update function
async function updateModelData() {
  let runningModels = null;
  let availableModels = null;

  try {
    const [runningResponse, availableResponse] = await Promise.all([
      fetch("/api/models/running"),
      fetch("/api/models/available"),
    ]);

    const runR = await readApiJson(runningResponse);
    if (runR.responseOk) {
      const runningData = runR.data;
      runningModels = Array.isArray(runningData.models)
        ? runningData.models
        : [];
      _lastRunningModelsSnapshot = runningModels;
      updateRunningModelsDisplay(runningModels);
    }

    const availR = await readApiJson(availableResponse);
    if (availR.responseOk) {
      const availableData = availR.data;
      availableModels = Array.isArray(availableData.models)
        ? availableData.models
        : [];
      updateAvailableModelsDisplay(availableModels);
    }
  } catch (error) {
    console.log("Failed to update models:", error);
  }

  restoreAllDownloadUi();

  _versionPollCounter++;
  if (_versionPollCounter >= VERSION_POLL_EVERY_N) {
    _versionPollCounter = 0;
    try {
      const versionResponse = await fetch("/api/version");
      const vr = await readApiJson(versionResponse);
      if (vr.responseOk && vr.data) {
        updateVersionDisplay(vr.data.version || "Unknown");
      }
    } catch (error) {
      console.log("Failed to update Ollama version:", error);
    }
  }

  resetRefreshCountdown();
}

function _escModelCard(s) {
  return typeof escapeHtml === "function" ? escapeHtml(String(s)) : String(s);
}

function prefixContextTokensUsedHtml(model, innerHtml) {
  const used =
    model?.context_tokens_used_display != null &&
    model.context_tokens_used_display !== ""
      ? String(model.context_tokens_used_display)
      : "";
  if (!used) return innerHtml;
  return `<span class="ctx-used text-nowrap" data-dashboard-tooltip="Tokens from the last non-streaming dashboard generate/chat for this model (Ollama prompt_eval_count + eval_count).">${_escModelCard(used)}</span><span class="ctx-sep text-muted" aria-hidden="true">·</span>${innerHtml}`;
}

function prefixRequestContextHtml(model, innerHtml) {
  const req =
    model?.request_context_length != null && model.request_context_length !== ""
      ? String(model.request_context_length)
      : "";
  if (!req) return innerHtml;
  return `<span class="ctx-request text-nowrap" data-dashboard-tooltip="Context (num_ctx) the dashboard sends with API requests for this model.">${_escModelCard(req)}</span><span class="ctx-sep text-muted" aria-hidden="true">·</span>${innerHtml}`;
}

function buildAvailableContextInnerHtml(model, contextStr) {
  const maxPart = _escModelCard(contextStr);
  const req =
    model?.request_context_length != null && model.request_context_length !== ""
      ? String(model.request_context_length)
      : "";
  const maxSpan = `<span class="ctx-max text-nowrap" data-dashboard-tooltip="Maximum context from Ollama metadata for this tag.">${maxPart}</span>`;
  const core = req
    ? `<span class="ctx-request text-nowrap" data-dashboard-tooltip="Context (num_ctx) the dashboard sends with generate/chat for this model.">${_escModelCard(req)}</span><span class="ctx-sep text-muted" aria-hidden="true">·</span>${maxSpan}`
    : maxSpan;
  return prefixContextTokensUsedHtml(model, core);
}

function quantizationFromModel(model) {
  const details = (model && model.details) || {};
  const raw =
    details.quantization_level ??
    details.quantization ??
    model?.quantization_level ??
    model?.quantization;
  if (raw == null || raw === "") return "Unknown";
  return String(raw);
}

function updateRunningModelsDisplay(models) {
  const runningModelsContainer = document.getElementById(
    "runningModelsContainer",
  );
  if (!runningModelsContainer) return;

  // Update the count display
  const countEl = document.getElementById("runningModelsCount");
  if (countEl) {
    countEl.textContent = models.length;
  }

  // Rebuild the running models list from the latest API payload
  if (!models || models.length === 0) {
    runningModelsContainer.innerHTML = "";
    return;
  }

  const buildRunningModelCardHTML = (model, index) => {
    const name = model?.name || "Unknown";
    const safeNameText =
      typeof escapeHtml === "function"
        ? escapeHtml(String(name))
        : String(name);
    const safeDataName =
      typeof escapeHtml === "function"
        ? escapeHtml(String(name))
        : String(name);

    const hasCustom = modelHasCustomSettings(model);
    const details = model?.details || {};
    const family = details?.family || "Unknown";
    const parameterSize =
      details && details.parameter_size != null && details.parameter_size !== ""
        ? details.parameter_size
        : model?.parameter_size != null && model.parameter_size !== ""
          ? model.parameter_size
          : "Unknown";
    const quantization = quantizationFromModel(model);
    const formattedSize =
      model?.formatted_size != null && model.formatted_size !== ""
        ? model.formatted_size
        : model?.size != null
          ? String(model.size)
          : "Unknown";

    const size = typeof model?.size === "number" ? model.size : 0;
    const sizeVram = typeof model?.size_vram === "number" ? model.size_vram : 0;
    const formattedSizeVram =
      model?.formatted_size_vram != null && model.formatted_size_vram !== ""
        ? model.formatted_size_vram
        : "0 B";

    const contextMax =
      (details &&
      details.context_length != null &&
      details.context_length !== ""
        ? details.context_length
        : null) ??
      model?.context_length ??
      "Unknown";
    const contextLoaded =
      model?.loaded_context_length != null && model.loaded_context_length !== ""
        ? model.loaded_context_length
        : (model?.context_length ?? "Unknown");

    const maxCtxHtml = _escModelCard(contextMax);
    const loadedCtxHtml = _escModelCard(contextLoaded);

    const expires = model?.expires_at || {};
    const expiresLabel = expires.relative || expires.local || "";

    const gpuPercent =
      size > 0 && sizeVram > 0 ? ((sizeVram / size) * 100).toFixed(1) : "0.0";

    const capabilityIcons = getCapabilitiesHTML(model);

    const cardIndex = index + 1;

    const titleBlock =
      window.modelCards &&
      typeof window.modelCards.modelTitleMarkup === "function"
        ? window.modelCards.modelTitleMarkup(name)
        : `<div class="model-title">${safeNameText}</div>`;

    const settingsBtnInner = getSettingsButtonInnerHtml(hasCustom);

    return `
      <div class="col">
        <div class="model-card h-100" data-model-name="${safeDataName}">
          <div class="model-header model-card-head">
            <div class="model-icon-wrapper">
              <i class="fas fa-brain model-icon-main"></i>
            </div>
            <div class="model-card-head-body">
              <div class="model-card-head-name-row">
                ${titleBlock}
                <div class="model-card-head-trail" aria-label="Model status and capabilities">
                  <div class="model-meta">
                    <span class="status-indicator running" data-dashboard-tooltip="Model weights are resident in memory; this card reflects the running process.">
                      <i class="fas fa-circle"></i>Loaded
                    </span>
                  </div>
                  <div class="model-card-head-aside" aria-label="Model capabilities">
                    <div class="model-capabilities" aria-label="Model capabilities">
                      ${capabilityIcons}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="model-specs">
            <div class="spec-row">
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-cogs"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="Model family name from Ollama metadata (e.g. llama, mistral).">Family</div>
                  <div class="spec-value">${
                    typeof escapeHtml === "function"
                      ? escapeHtml(String(family))
                      : String(family)
                  }</div>
                </div>
              </div>
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-weight"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="Approximate parameter size or class (e.g. 7B) from metadata.">Parameters</div>
                  <div class="spec-value">${
                    typeof escapeHtml === "function"
                      ? escapeHtml(String(parameterSize))
                      : String(parameterSize)
                  }</div>
                  <div class="text-muted small">Quant: ${_escModelCard(quantization)}</div>
                </div>
              </div>
            </div>
            <div class="spec-row">
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-hdd"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="On-disk size of this model’s files.">Size</div>
                  <div class="spec-value text-nowrap model-size">${
                    typeof escapeHtml === "function"
                      ? escapeHtml(String(formattedSize))
                      : String(formattedSize)
                  }</div>
                </div>
              </div>
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-microchip"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label text-nowrap" data-dashboard-tooltip="While loaded: fraction of weights in GPU memory vs model size (from Ollama).">GPU Allocation</div>
                  <div class="spec-value text-nowrap" id="model-gpu-${cardIndex}">
                    ${gpuPercent}% (${formattedSizeVram})
                  </div>
                </div>
              </div>
            </div>
            <div class="spec-row">
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-layer-group"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="Maximum context from model metadata (Ollama show / details).">Max context</div>
                  <div class="spec-value text-nowrap" id="model-context-max-${cardIndex}">${maxCtxHtml}</div>
                </div>
              </div>
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-expand-arrows-alt"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="Context window allocated for this running process (Ollama /api/ps).">Allocated</div>
                  <div class="spec-value text-nowrap" id="model-context-loaded-${cardIndex}">${loadedCtxHtml}</div>
                </div>
              </div>
            </div>
          </div>
          <div class="model-actions model-actions--running">
            <button type="button" class="btn btn-primary" data-model-action="restart" onclick="restartModel(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Reload this model in memory (applies updated settings from disk).">
              <i class="fas fa-redo"></i> <span class="model-action-btn-label">Restart</span>
            </button>
            <button type="button" class="btn btn-warning" data-model-action="stop" onclick="stopModel(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Unload from VRAM (ollama stop). Model files stay installed.">
              <i class="fas fa-stop"></i> <span class="model-action-btn-label">Stop</span>
            </button>
            <button class="btn btn-info" onclick="showModelInfo(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Open a modal with raw Ollama model details (JSON).">
              <i class="fas fa-info-circle"></i> <span class="model-action-btn-label">Info</span>
            </button>
            <button type="button" class="btn btn-secondary model-action-settings-btn" onclick="openModelSettingsModal(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Edit temperature, context, and other options stored for this dashboard." aria-label="${hasCustom ? "Settings (saved custom defaults)" : "Settings (using defaults)"}">
              ${settingsBtnInner}
            </button>
          </div>
          ${
            expiresLabel
              ? `<div class="model-expires text-muted small mt-1">${expiresLabel}</div>`
              : ""
          }
        </div>
      </div>
    `;
  };

  const cardsHtml = models
    .map((m, idx) => buildRunningModelCardHTML(m, idx))
    .join("");
  runningModelsContainer.innerHTML = cardsHtml;
  afterModelCardsRendered();
  // Running models must stay visible: capability filters only apply to catalog lists.
  runningModelsContainer.querySelectorAll(".model-card").forEach((card) => {
    const column = card.closest(".model-cards-row .col, .col-12");
    if (column) column.style.display = "";
  });
}

window.updateRunningModelsDisplay = updateRunningModelsDisplay;

function buildAvailableModelCardHTML(model) {
  const name = model?.name || "Unknown";
  const safeDataName =
    typeof escapeHtml === "function" ? escapeHtml(String(name)) : String(name);
  const hasCustom = modelHasCustomSettings(model);
  const details = model?.details || {};
  const family =
    details.family != null && details.family !== ""
      ? String(details.family)
      : "Unknown";
  const parameterSize =
    details.parameter_size != null && details.parameter_size !== ""
      ? String(details.parameter_size)
      : model?.parameter_size != null && model.parameter_size !== ""
        ? String(model.parameter_size)
        : "Unknown";
  const quantization = quantizationFromModel(model);
  const formattedSize =
    model?.formatted_size != null && model.formatted_size !== ""
      ? String(model.formatted_size)
      : typeof model?.size === "number" && !Number.isNaN(model.size)
        ? formatBytes(model.size)
        : "Unknown";
  const ctxMax =
    model?.context_length ??
    (details.context_length != null ? details.context_length : null) ??
    "Unknown";
  const contextStr =
    ctxMax != null && ctxMax !== "" ? String(ctxMax) : "Unknown";

  const capabilityIcons = getCapabilitiesHTML(model);

  const titleBlock =
    window.modelCards &&
    typeof window.modelCards.modelTitleMarkup === "function"
      ? window.modelCards.modelTitleMarkup(name)
      : `<div class="model-title">${safeDataName}</div>`;

  const settingsBtnInner = getSettingsButtonInnerHtml(hasCustom);

  const contextInnerHtml = buildAvailableContextInnerHtml(model, contextStr);

  return `
      <div class="col">
        <div class="model-card h-100" data-model-name="${safeDataName}">
          <div class="model-header model-card-head">
            <div class="model-icon-wrapper">
              <i class="fas fa-box model-icon-main"></i>
            </div>
            <div class="model-card-head-body">
              <div class="model-card-head-name-row">
                ${titleBlock}
                <div class="model-card-head-trail" aria-label="Model capabilities">
                  <div class="model-card-head-aside" aria-label="Model capabilities">
                    <div class="model-capabilities" aria-label="Model capabilities">
                      ${capabilityIcons}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="model-specs">
            <div class="spec-row">
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-cogs"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="Model family from Ollama metadata.">Family</div>
                  <div class="spec-value">${_escModelCard(family)}</div>
                </div>
              </div>
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-weight"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="Parameter class from metadata (e.g. 7B).">Parameters</div>
                  <div class="spec-value">${_escModelCard(parameterSize)}</div>
                  <div class="text-muted small">Quant: ${_escModelCard(quantization)}</div>
                </div>
              </div>
            </div>
            <div class="spec-row">
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-hdd"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="Disk space used by this model’s files.">Size</div>
                  <div class="spec-value text-nowrap">${_escModelCard(formattedSize)}</div>
                </div>
              </div>
              <div class="spec-item">
                <div class="spec-icon">
                  <i class="fas fa-align-left"></i>
                </div>
                <div class="spec-content">
                  <div class="spec-label" data-dashboard-tooltip="Last tokens (dashboard generate/chat) · request num_ctx · max context from Ollama for this tag.">Context</div>
                  <div class="spec-value spec-context-dual">${contextInnerHtml}</div>
                </div>
              </div>
            </div>
          </div>
          <div class="download-progress d-none">
            <div class="progress" style="height: 20px;">
              <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" style="width: 0%;"></div>
            </div>
            <small class="text-muted d-block text-center mt-1">0%</small>
          </div>
          <div class="model-actions model-actions--available">
            <button type="button" class="btn btn-primary btn-dashboard-download" onclick="startModel(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Load into memory so you can use it via API, CLI, or apps (ollama run)." aria-label="Start model">
              <i class="fas fa-play"></i> <span class="model-action-btn-label">Start</span>
            </button>
            <button type="button" class="btn btn-success" onclick="openAskModal(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Send a question to this model (streams the response)." aria-label="Ask this model a question">
              <i class="fas fa-comment-dots"></i> <span class="model-action-btn-label">Ask?</span>
            </button>
            <button class="btn btn-info" onclick="showModelInfo(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Modal with full Ollama model JSON." aria-label="View model information">
              <i class="fas fa-info-circle"></i> <span class="model-action-btn-label">Info</span>
            </button>
            <button type="button" class="btn btn-secondary model-action-settings-btn" onclick="openModelSettingsModal(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Per-model defaults for this dashboard (applied on next load/start)." aria-label="${hasCustom ? "Settings (saved custom defaults)" : "Settings (using defaults)"}">
              ${settingsBtnInner}
            </button>
            <button type="button" class="btn btn-danger" data-model-action="delete" onclick="deleteModel(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Remove from disk (ollama rm). This cannot be undone." aria-label="Delete model">
              <i class="fas fa-trash"></i> <span class="model-action-btn-label">Delete</span>
            </button>
          </div>
        </div>
      </div>
    `;
}

function updateAvailableModelsDisplay(models) {
  const availableModelsContainer = document.getElementById(
    "availableModelsContainer",
  );
  if (!availableModelsContainer) return;

  const displayModels = augmentAvailableModelsForDownloads(models);

  const countEl = document.getElementById("availableModelsCount");
  if (countEl) {
    countEl.textContent = String(displayModels.length);
  }

  const newNames = new Set(
    displayModels.map((m) => (m.name || "").trim()).filter(Boolean),
  );
  const currentCards = availableModelsContainer.querySelectorAll(
    ".model-card[data-model-name]",
  );
  const currentNames = new Set(
    Array.from(currentCards).map((c) => (c.dataset.modelName || "").trim()),
  );

  const namesChanged =
    newNames.size !== currentNames.size ||
    [...newNames].some((n) => !currentNames.has(n));

  if (namesChanged) {
    if (displayModels.length === 0) {
      availableModelsContainer.innerHTML = "";
    } else {
      availableModelsContainer.innerHTML = displayModels
        .map((m) => buildAvailableModelCardHTML(m))
        .join("");
    }
    applyCapabilityFilters("availableModelsContainer");
    afterModelCardsRendered();
    restoreAllDownloadUi();
    return;
  }

  try {
    currentCards.forEach((card) => {
      const name = (
        card.dataset && card.dataset.modelName
          ? card.dataset.modelName.trim()
          : ""
      ).trim();
      if (!name) return;
      const matching = (models || []).find(
        (m) => m.name && m.name.trim() === name,
      );
      if (!matching) return;
      const caps = card.querySelectorAll(".capability-icon");
      if (caps && caps.length >= 3) {
        const [reasoningEl, visionEl, toolsEl] = caps;
        for (const [el, val, label] of [
          [reasoningEl, matching.has_reasoning, "Reasoning"],
          [visionEl, matching.has_vision, "Image Processing"],
          [toolsEl, matching.has_tools, "Tool Usage"],
        ]) {
          const state =
            val === true ? "enabled" : val === false ? "disabled" : "unknown";
          const title =
            val === true
              ? `${label}: Available`
              : val === false
                ? `${label}: Not available`
                : `${label}: Unknown`;
          el.classList.remove("enabled", "disabled", "unknown");
          el.classList.add(state);
          el.removeAttribute("title");
          el.setAttribute("data-dashboard-tooltip", title);
          el.dataset.dashboardTooltipMigrated = "1";
        }
      }
      syncSettingsSavedIndicatorOnCard(card, matching);
    });
    applyCapabilityFilters("availableModelsContainer");
    afterModelCardsRendered();
    restoreAllDownloadUi();
  } catch (err) {
    console.log("Failed to update capability icons for available models", err);
  }
}

function updateVersionDisplay(version) {
  const versionEl = document.getElementById("ollamaVersion");
  if (versionEl) {
    versionEl.textContent = version;
  }
}

// updateModelMemoryDisplay removed (was already a no-op; call eliminated from polling)

// Service management functions moved to serviceControl.js

// updateHealthStatus & updateServiceControlButtons moved to serviceControl.js

// System stats: dedicated fast poll (data-stats-poll-interval on .compact-system-resources).
document.addEventListener("DOMContentLoaded", function () {
  const statsMs =
    typeof getStatsPollIntervalSec === "function"
      ? getStatsPollIntervalSec() * 1000
      : 1000;
  if (typeof updateSystemStats === "function") updateSystemStats();
  setInterval(function () {
    if (document.visibilityState !== "visible") return;
    if (typeof updateSystemStats === "function") updateSystemStats();
  }, statsMs);
});

const AVAILABLE_SECTION_COLLAPSED_KEY = "availableModelsSectionCollapsed";

function syncAvailableSectionToggle(collapsed) {
  const button = document.getElementById("availableSectionToggleBtn");
  if (!button) return;

  const label = collapsed
    ? "Expand available models section"
    : "Collapse available models section";
  button.setAttribute("aria-label", label);
  button.setAttribute("title", label);
  button.setAttribute("aria-expanded", collapsed ? "false" : "true");
  button.innerHTML = collapsed
    ? '<i class="fas fa-chevron-down" aria-hidden="true"></i>'
    : '<i class="fas fa-chevron-up" aria-hidden="true"></i>';
}

function toggleAvailableSection(forceCollapsed) {
  const body = document.getElementById("availableModelsBody");
  const section = document.getElementById("availableModelsSection");
  if (!body) return;

  const currentlyCollapsed = body.style.display === "none";
  const nextCollapsed =
    typeof forceCollapsed === "boolean" ? forceCollapsed : !currentlyCollapsed;

  body.style.display = nextCollapsed ? "none" : "";
  if (section) {
    section.classList.toggle("is-collapsed", nextCollapsed);
  }
  syncAvailableSectionToggle(nextCollapsed);
  localStorage.setItem(
    AVAILABLE_SECTION_COLLAPSED_KEY,
    nextCollapsed ? "true" : "false",
  );
}

window.toggleAvailableSection = toggleAvailableSection;

const INITIAL_DOWNLOADABLE_VISIBLE = 24;
const DOWNLOADABLE_LOAD_MORE_BATCH = 24;
const DOWNLOADABLE_SECTION_COLLAPSED_KEY = "downloadableModelsSectionCollapsed";
let cachedDownloadableModels = [];
let downloadableVisibleCount = 0;

function syncDownloadableSectionToggle(collapsed) {
  const button = document.getElementById("downloadableSectionToggleBtn");
  if (!button) return;

  const label = collapsed
    ? "Expand downloadable models section"
    : "Collapse downloadable models section";
  button.setAttribute("aria-label", label);
  button.setAttribute("title", label);
  button.setAttribute("aria-expanded", collapsed ? "false" : "true");
  button.innerHTML = collapsed
    ? '<i class="fas fa-chevron-down" aria-hidden="true"></i>'
    : '<i class="fas fa-chevron-up" aria-hidden="true"></i>';
}

function toggleDownloadableSection(forceCollapsed) {
  const body = document.getElementById("downloadableModelsBody");
  const section = document.getElementById("downloadableModelsSection");
  if (!body) return;

  const currentlyCollapsed = body.style.display === "none";
  const nextCollapsed =
    typeof forceCollapsed === "boolean" ? forceCollapsed : !currentlyCollapsed;

  body.style.display = nextCollapsed ? "none" : "";
  if (section) {
    section.classList.toggle("is-collapsed", nextCollapsed);
  }
  syncDownloadableSectionToggle(nextCollapsed);
  localStorage.setItem(
    DOWNLOADABLE_SECTION_COLLAPSED_KEY,
    nextCollapsed ? "true" : "false",
  );
}

window.toggleDownloadableSection = toggleDownloadableSection;

function buildDownloadableModelsHtml(models) {
  if (!models || models.length === 0) return "";
  return models
    .map((m) =>
      window.modelCards && window.modelCards.buildDownloadableModelCardHTML
        ? window.modelCards.buildDownloadableModelCardHTML(m)
        : "",
    )
    .join("");
}

function updateLoadMoreDownloadableButton() {
  const button = document.getElementById("loadMoreDownloadableBtn");
  if (!button) return;
  const remaining = cachedDownloadableModels.length - downloadableVisibleCount;
  if (remaining <= 0) {
    button.style.display = "none";
    return;
  }
  button.style.display = "";
  const nextCount = Math.min(remaining, DOWNLOADABLE_LOAD_MORE_BATCH);
  button.innerHTML = `<i class="fas fa-plus-circle me-2" aria-hidden="true"></i>Load more (${nextCount})`;
  button.setAttribute(
    "aria-label",
    `Load ${nextCount} more downloadable models`,
  );
}

function loadMoreDownloadableModels() {
  const container = document.getElementById("downloadableModelsContainer");
  if (!container || downloadableVisibleCount >= cachedDownloadableModels.length) {
    updateLoadMoreDownloadableButton();
    return;
  }
  const next = cachedDownloadableModels.slice(
    downloadableVisibleCount,
    downloadableVisibleCount + DOWNLOADABLE_LOAD_MORE_BATCH,
  );
  const html = buildDownloadableModelsHtml(next);
  if (html) {
    container.insertAdjacentHTML("beforeend", html);
    downloadableVisibleCount += next.length;
    applyCapabilityFilters("downloadableModelsContainer");
    afterModelCardsRendered();
  }
  updateLoadMoreDownloadableButton();
}

window.loadMoreDownloadableModels = loadMoreDownloadableModels;

async function loadDownloadableModels() {
  const container = document.getElementById("downloadableModelsContainer");
  if (!container) return;

  try {
    const response = await fetch("/api/models/downloadable?category=best");
    const dr = await readApiJson(response);
    if (dr.responseOk) {
      const data = dr.data;
      const list = Array.isArray(data.models) ? data.models : [];
      cachedDownloadableModels = list;
      const initial = list.slice(0, INITIAL_DOWNLOADABLE_VISIBLE);
      downloadableVisibleCount = initial.length;
      renderDownloadableModels(initial);
      updateLoadMoreDownloadableButton();
    } else {
      container.innerHTML =
        '<div class="col-12 text-center text-danger">Failed to load models</div>';
    }
  } catch (error) {
    console.error("Error loading downloadable models:", error);
    container.innerHTML =
      '<div class="col-12 text-center text-danger">Error loading models</div>';
  }
}

function renderDownloadableModels(models) {
  const container = document.getElementById("downloadableModelsContainer");
  if (!container) return;

  if (!models || models.length === 0) {
    container.innerHTML =
      '<div class="col-12 text-center text-muted">No models available</div>';
    return;
  }
  container.innerHTML = buildDownloadableModelsHtml(models);
  applyCapabilityFilters("downloadableModelsContainer");
  afterModelCardsRendered();
}

function openFindModelModal() {
  const input = document.getElementById("findModelInput");
  if (input) input.value = "";
  const modal = new bootstrap.Modal(document.getElementById("findModelModal"));
  modal.show();
}

function confirmFindModel() {
  const input = document.getElementById("findModelInput");
  const name = (input ? input.value : "").trim();
  if (!name) {
    showNotification("Please enter a model name.", "error");
    return;
  }
  const modalEl = document.getElementById("findModelModal");
  const modal = bootstrap.Modal.getInstance(modalEl);
  if (modal) modal.hide();
  pullModel(name);
}

document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("findModelInput");
  const modalEl = document.getElementById("findModelModal");
  if (input) {
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") confirmFindModel();
    });
  }
  if (modalEl) {
    modalEl.addEventListener("shown.bs.modal", function () {
      if (input) input.focus();
    });
  }

  const savedAvailableCollapsed =
    localStorage.getItem(AVAILABLE_SECTION_COLLAPSED_KEY) === "true";
  toggleAvailableSection(savedAvailableCollapsed);

  const savedDownloadableCollapsed =
    localStorage.getItem(DOWNLOADABLE_SECTION_COLLAPSED_KEY) === "true";
  toggleDownloadableSection(savedDownloadableCollapsed);
});

function ensureAvailableCardForDownload(modelName) {
  const esc = cssEscape(modelName);
  const availableContainer = document.getElementById("availableModelsContainer");
  let card = availableContainer
    ? availableContainer.querySelector(
        `.model-card[data-model-name="${esc}"]`,
      )
    : null;
  if (card) return card;

  if (!availableContainer || typeof buildAvailableModelCardHTML !== "function") {
    return document.querySelector(`.model-card[data-model-name="${esc}"]`);
  }

  const placeholder = {
    name: modelName,
    details: { family: "Unknown", parameter_size: "Unknown" },
    formatted_size: "Downloading…",
    context_length: "—",
  };
  const cardHtml = buildAvailableModelCardHTML(placeholder);
  const wrapper = document.createElement("div");
  wrapper.innerHTML = cardHtml.trim();
  const col = wrapper.firstElementChild;
  if (col) {
    availableContainer.insertBefore(col, availableContainer.firstChild);
    card = availableContainer.querySelector(
      `.model-card[data-model-name="${esc}"]`,
    );
    const countEl = document.getElementById("availableModelsCount");
    if (countEl) {
      const n = availableContainer.querySelectorAll(
        ".model-card[data-model-name]",
      ).length;
      countEl.textContent = String(n);
    }
    afterModelCardsRendered();
  }
  return card;
}

async function pullModel(modelName) {
  let card = ensureAvailableCardForDownload(modelName);
  if (!card) {
    card = document.querySelector(
      `.model-card[data-model-name="${cssEscape(modelName)}"]`,
    );
  }
  const button = card
    ? card.querySelector(".btn-dashboard-download") ||
      card.querySelector(".model-actions--available .btn-primary")
    : null;
  const progressContainer = card
    ? card.querySelector(".download-progress")
    : null;
  const progressBar = progressContainer
    ? progressContainer.querySelector(".progress-bar")
    : null;
  const progressText = progressContainer
    ? progressContainer.querySelector("small")
    : null;
  const originalText = button ? button.innerHTML : null;

  setDownloadState(modelName, {
    status: "downloading",
    percent: 0,
    message: "Starting download...",
  });

  if (button) {
    button.innerHTML =
      '<i class="fas fa-spinner fa-spin me-1"></i>Downloading...';
    button.disabled = true;
  }

  if (progressContainer) {
    progressContainer.classList.remove("d-none");
    progressContainer.style.display = "block";
  }
  if (card) card.dataset.downloadActive = "true";

  showNotification(
    `Starting download for ${modelName}. This may take a while...`,
    "info",
  );

  try {
    // Step 1: Pull model with streaming status updates
    const pullResp = await fetch(
      `/api/models/pull/${encodeURIComponent(modelName)}?stream=true`,
      { method: "POST" },
    );
    if (!pullResp.ok) {
      const pr = await readApiJson(pullResp);
      throw new Error(
        pr.message || `Failed to start download (${pullResp.status})`,
      );
    }

    let pullSucceeded = false;
    let pullMessage = "Download finished";

    if (pullResp.body) {
      const reader = pullResp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const handleEvents = (eventStrings) => {
        for (const event of eventStrings) {
          const dataLine = event.trim().replace(/^data:\s*/, "");
          if (!dataLine) continue;

          let payload;
          try {
            payload = JSON.parse(dataLine);
          } catch (e) {
            console.warn("Failed to parse pull event", e, dataLine);
            continue;
          }

          if (payload.event === "status") {
            const msg = payload.message || "Downloading...";
            let percent = null;
            if (payload.total && payload.completed !== undefined) {
              percent = Math.round((payload.completed / payload.total) * 100);
            }
            setDownloadState(modelName, {
              status: "downloading",
              percent,
              message: msg,
            });
            if (button) {
              button.innerHTML = `<i class="fas fa-download me-1"></i>${msg}`;
            }

            if (percent != null) {
              if (progressBar) {
                progressBar.style.width = `${percent}%`;
                progressBar.setAttribute("aria-valuenow", percent);
              }
              if (progressText) {
                progressText.textContent = `${percent}%`;
              }
            }
          } else if (payload.event === "error") {
            throw new Error(payload.message || "Pull failed");
          } else if (payload.event === "done") {
            pullSucceeded = payload.success !== false;
            pullMessage = payload.message || pullMessage;
            setDownloadState(modelName, {
              status: "complete",
              percent: 100,
              message: pullMessage,
            });
            if (progressBar) {
              progressBar.style.width = "100%";
              progressBar.setAttribute("aria-valuenow", 100);
            }
            if (progressText) {
              progressText.textContent = "100%";
            }
          }
        }
      };

      // Process Server-Sent Events from the streaming pull endpoint
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop();
        handleEvents(events);
      }

      if (buffer.trim()) {
        handleEvents([buffer]);
      }
    } else {
      // Fallback for environments without streaming support
      const fallback = await fetch(
        `/api/models/pull/${encodeURIComponent(modelName)}`,
        { method: "POST" },
      );
      const fr = await readApiJson(fallback);
      const fallbackResult = fr.responseOk ? fr.data : {};
      pullSucceeded = !!fallbackResult.success;
      pullMessage = fallbackResult.message || fr.message || pullMessage;
    }

    if (!pullSucceeded) {
      throw new Error(pullMessage || "Pull failed");
    }

    showNotification(pullMessage, "success");

    if (button) {
      button.innerHTML = '<i class="fas fa-check me-1"></i>Downloaded';
    }
    clearDownloadState(modelName);
    if (card) delete card.dataset.downloadActive;
    setTimeout(() => {
      if (typeof updateModelData === "function") {
        void updateModelData();
      }
    }, 800);
  } catch (err) {
    clearDownloadState(modelName);
    if (card) delete card.dataset.downloadActive;
    showNotification(`Download failed: ${err.message}`, "error");
    if (button && originalText !== null) {
      button.innerHTML = originalText;
      button.disabled = false;
    }
    if (progressContainer) {
      progressContainer.classList.add("d-none");
      progressContainer.style.display = "none";
    }
    if (progressBar) {
      progressBar.style.width = "0%";
    }
    if (progressText) {
      progressText.textContent = "0%";
    }
  }
}

// Capability filtering logic
function toggleCapabilityFilter(capability) {
  const filterBtns = document.querySelectorAll(
    `.filter-btn[data-capability="${capability}"]`,
  );
  filterBtns.forEach((btn) => {
    btn.classList.toggle("active");
  });

  ["availableModelsContainer", "downloadableModelsContainer"].forEach((id) =>
    applyCapabilityFilters(id),
  );
  const runC = document.getElementById("runningModelsContainer");
  if (runC) {
    runC.querySelectorAll(".model-card").forEach((card) => {
      const column = card.closest(".model-cards-row .col, .col-12");
      if (column) column.style.display = "";
    });
  }
}

function applyCapabilityFilters(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  // Use the state of any visible filter button (only one section shows filters)
  const firstReasoningBtn = document.querySelector(
    `.filter-btn[data-capability="reasoning"]`,
  );
  const firstVisionBtn = document.querySelector(
    `.filter-btn[data-capability="vision"]`,
  );
  const firstToolsBtn = document.querySelector(
    `.filter-btn[data-capability="tools"]`,
  );

  const reasoningRequired =
    firstReasoningBtn?.classList.contains("active") ?? false;
  const visionRequired = firstVisionBtn?.classList.contains("active") ?? false;
  const toolsRequired = firstToolsBtn?.classList.contains("active") ?? false;

  // If no capabilities are required OR all are required, show all models
  // This preserves the previous behavior where the default "all active"
  // state does not hide any models.
  if (
    (!reasoningRequired && !visionRequired && !toolsRequired) ||
    (reasoningRequired && visionRequired && toolsRequired)
  ) {
    const cards = container.querySelectorAll(".model-card");
    cards.forEach((card) => {
      const column = card.closest(".model-cards-row .col, .col-12");
      if (column) column.style.display = "";
    });
    return;
  }

  // Otherwise, filter by selected capabilities
  const cards = container.querySelectorAll(".model-card");
  cards.forEach((card) => {
    const caps = card.querySelectorAll(".capability-icon");
    if (caps.length >= 3) {
      const hasReasoning = caps[0].classList.contains("enabled");
      const hasVision = caps[1].classList.contains("enabled");
      const hasTools = caps[2].classList.contains("enabled");

      // Show models that have at least one of the selected capabilities.
      // This is easier to understand than strict "must have all" logic.
      let matches = false;
      if (reasoningRequired && hasReasoning) matches = true;
      if (visionRequired && hasVision) matches = true;
      if (toolsRequired && hasTools) matches = true;

      const column = card.closest(".model-cards-row .col, .col-12");
      if (column) {
        column.style.display = matches ? "" : "none";
      }
    }
  });
}

// Global exposure
window.toggleCapabilityFilter = toggleCapabilityFilter;
