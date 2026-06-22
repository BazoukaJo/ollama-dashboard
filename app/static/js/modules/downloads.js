/** Model download state, resume, and pull streaming UI. */
(function () {
  const DOWNLOAD_STATE_KEY = "ollamaDashboardActiveDownloads";
  const DOWNLOAD_RESUME_POLL_MS = 2500;
  const DOWNLOAD_RESUME_TIMEOUT_MS = 7200000;
  const _downloadResumeTimers = new Map();

  function escText(value) {
    return typeof escapeHtml === "function"
      ? escapeHtml(String(value || ""))
      : String(value || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
  }

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
        button.innerHTML = `<i class="fas fa-download me-1"></i>${escText(msg)}`;
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
            void updateModelData(true);
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
    if (hasAnyActiveDownload()) {
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
      if (typeof afterModelCardsRendered === "function") {
        afterModelCardsRendered();
      }
      if (typeof applyCapabilityFilters === "function") {
        applyCapabilityFilters("availableModelsContainer");
      }
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

    if (window.showNotification) {
      window.showNotification(
        `Starting download for ${modelName}. This may take a while...`,
        "info",
      );
    }

    try {
      const pullResp = await fetch(
        modelActionUrl("pull", modelName, { stream: "true" }),
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
                button.innerHTML = `<i class="fas fa-download me-1"></i>${escText(msg)}`;
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
        const fallback = await fetch(modelActionUrl("pull", modelName), {
          method: "POST",
        });
        const fr = await readApiJson(fallback);
        const fallbackResult = fr.responseOk ? fr.data : {};
        pullSucceeded = !!fallbackResult.success;
        pullMessage = fallbackResult.message || fr.message || pullMessage;
      }

      if (!pullSucceeded) {
        throw new Error(pullMessage || "Pull failed");
      }

      if (window.showNotification) {
        window.showNotification(pullMessage, "success");
      }

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
      if (window.showNotification) {
        window.showNotification(`Download failed: ${err.message}`, "error");
      }
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

  window.getActiveDownloads = getActiveDownloads;
  window.hasAnyActiveDownload = hasAnyActiveDownload;
  window.augmentAvailableModelsForDownloads = augmentAvailableModelsForDownloads;
  window.applyDownloadStateToCard = applyDownloadStateToCard;
  window.restoreAllDownloadUi = restoreAllDownloadUi;
  window.resumeActiveDownloads = resumeActiveDownloads;
  window.scheduleReloadUnlessDownloading = scheduleReloadUnlessDownloading;
  window.ensureAvailableCardForDownload = ensureAvailableCardForDownload;
  window.pullModel = pullModel;
})();
