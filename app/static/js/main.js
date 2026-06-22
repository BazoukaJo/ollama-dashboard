/**
 * Main JavaScript functionality for Ollama Dashboard
 * Poll timers live in modules/polling.js
 */

let refreshCountdown = 10;
let _statsInFlight = false;

/** Refresh all dashboard data (models + stats) without full page reload. */
function refreshDashboardData() {
  [document.getElementById("refreshModelsBtn")].forEach(function (btn) {
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
  if (typeof updateModelData === "function") updateModelData(true);
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
    const response = await fetch(modelActionUrl("start", modelName), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });
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

    const response = await fetch(modelActionUrl("stop", modelName), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ force: !!force }),
    });

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

    const response = await fetch(modelActionUrl("restart", modelName), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });
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

    const response = await fetch(modelActionUrl("delete", modelName), {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
    });
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
      let flagsFromCards = null;
      const normalizeName = (n) => {
        if (!n || typeof n !== "string") return "";
        return n.trim().toLowerCase();
      };
      const stripTag = (n) => n.replace(/:[^\s]+$/, "");
      const baseSegment = (n) => {
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
      }

      const details = info.details || {};
      const summaryHtml = buildModelSummary(info, details, modelName);
      const capabilityPayload = buildCapabilityPayloadForModal(
        flagsFromCards || info,
      );
      const capabilityBadges = renderCapabilityBadges(capabilityPayload);
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
  // Mixture-of-Experts is architectural: only surface it when known true (avoids noisy "unknown").
  if (info?.has_moe === true) {
    badges.push({ label: "MoE", icon: "fa-cubes", val: true });
  }

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

function afterModelCardsRendered() {
  if (
    window.modelCardActions &&
    typeof modelCardActions.enhanceAllModelCards === "function"
  ) {
    modelCardActions.enhanceAllModelCards();
  }
  ensureCapabilityFilterButtons();
}

const CAPABILITY_FILTER_SPECS = {
  reasoning: {
    tooltip: "Show only models with reasoning / thinking support.",
    title: "Filter reasoning models",
    label: "Filter reasoning models",
    icon: "fa-brain",
  },
  vision: {
    tooltip: "Show only models with image / vision support.",
    title: "Filter vision models",
    label: "Filter vision models",
    icon: "fa-image",
  },
  tools: {
    tooltip: "Show only models with tool or function-calling support.",
    title: "Filter tool-enabled models",
    label: "Filter tool-enabled models",
    icon: "fa-tools",
  },
  moe: {
    tooltip: "Show only Mixture of Experts (MoE) models.",
    title: "Filter MoE models",
    label: "Filter MoE models",
    icon: "fa-cubes",
  },
};

function ensureCapabilityFilterButtons() {
  document.querySelectorAll(".capability-filters").forEach((bar) => {
    Object.entries(CAPABILITY_FILTER_SPECS).forEach(([capability, meta]) => {
      if (bar.querySelector(`.filter-btn[data-capability="${capability}"]`)) {
        return;
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm btn-outline-secondary filter-btn";
      btn.dataset.capability = capability;
      btn.setAttribute("data-dashboard-tooltip", meta.tooltip);
      btn.title = meta.title;
      btn.setAttribute("aria-label", meta.label);
      btn.setAttribute("aria-pressed", "false");
      btn.addEventListener("click", () => toggleCapabilityFilter(capability));
      btn.innerHTML = `<i class="fas ${meta.icon}"></i>`;
      const activePeer = document.querySelector(
        `.filter-btn[data-capability="${capability}"].active`,
      );
      if (activePeer) {
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
      }
      bar.appendChild(btn);
    });
  });
}

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
  return `<span class="model-action-settings-inner"><span class="model-action-settings-label-row"><i class="fas fa-cog" aria-hidden="true"></i><span class="model-action-btn-label">Settings</span></span>${status}</span>`;
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
  const m = model?.has_moe;
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
    <span class="capability-icon ${capState(m)}" data-dashboard-tooltip="${capTitle(m, "Mixture of Experts (MoE)")}">
      <i class="fas fa-cubes"></i>
    </span>
  `;
}

window.getCapabilitiesHTML = getCapabilitiesHTML;

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

const timelineData = {
  cpu: [],
  memory: [],
  vram: [],
  gpu3d: [],
  disk: [],
};

const MAX_TIMELINE_POINTS = 60;

const TIMELINE_COLOR_CPU = "#3b82f6";
const TIMELINE_COLOR_MEMORY = "#22c55e";
const TIMELINE_COLOR_VRAM = "#06b6d4";
const TIMELINE_COLOR_GPU3D = "#f59e0b";
const TIMELINE_COLOR_DISK = "#a855f7";

function drawTimeline(canvas, data, color) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);

  if (data.length < 2) return;

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

  ctx.fillStyle = color.replace("rgb", "rgba").replace(")", ", 0.3)");
  ctx.beginPath();
  ctx.moveTo(0, height);

  const stepX = width / (data.length - 1);
  for (let i = 0; i < data.length; i++) {
    const x = i * stepX;
    const y = height - (data[i] / 100) * height;
    ctx.lineTo(x, y);
  }

  ctx.lineTo(width, height);
  ctx.closePath();
  ctx.fill();

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

  const currentValue = data[data.length - 1];
  const currentX = (data.length - 1) * stepX;
  const currentY = height - (currentValue / 100) * height;

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(currentX, currentY, 3, 0, 2 * Math.PI);
  ctx.fill();
}

async function updateSystemStats() {
  if (_statsInFlight) return;
  _statsInFlight = true;
  try {
    const fetchFn = typeof fetchWithTimeout === "function" ? fetchWithTimeout : fetch;
    const response = await fetchFn("/api/system/stats", {}, 8000);
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

      timelineData.cpu.push(cpu);
      timelineData.memory.push(memPct);
      timelineData.vram.push(vramTotal > 0 ? vramPct : 0);
      timelineData.gpu3d.push(typeof vram.gpu_3d === "number" ? gpu3d : 0);
      timelineData.disk.push(diskActivity);

      if (timelineData.cpu.length > MAX_TIMELINE_POINTS) {
        timelineData.cpu.shift();
        timelineData.memory.shift();
        timelineData.vram.shift();
        timelineData.gpu3d.shift();
        timelineData.disk.shift();
      }

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

      const lastUpdateTimeEl = document.getElementById("lastUpdateTime");
      if (lastUpdateTimeEl)
        lastUpdateTimeEl.textContent = new Date().toLocaleTimeString();
    }
  } catch (error) {
    console.log("Failed to update system stats:", error);
  } finally {
    _statsInFlight = false;
  }
}

let _versionPollCounter = 0;
let _updateModelDataInFlight = false;
const _API_TIMEOUT_MS = 15000;
const VERSION_POLL_EVERY_N = 12;

function _availableSectionExpanded() {
  const body = document.getElementById("availableModelsBody");
  if (!body) return true;
  return body.style.display !== "none";
}

async function updateModelData(forceRefresh) {
  if (_updateModelDataInFlight) return;
  _updateModelDataInFlight = true;
  let runningModels = null;
  let availableModels = null;
  const refreshQ = forceRefresh ? "?refresh=1" : "";
  const fetchAvailable = forceRefresh || _availableSectionExpanded();

  try {
    const fetchFn = typeof fetchWithTimeout === "function" ? fetchWithTimeout : fetch;
    if (fetchAvailable) {
      const listsResp = await fetchFn(
        "/api/models/lists" + refreshQ,
        {},
        _API_TIMEOUT_MS,
      );
      const listsR = await readApiJson(listsResp);
      if (listsR.responseOk) {
        const data = listsR.data || {};
        runningModels = Array.isArray(data.running) ? data.running : [];
        availableModels = Array.isArray(data.available) ? data.available : [];
        _lastRunningModelsSnapshot = runningModels;
        updateRunningModelsDisplay(runningModels);
        updateAvailableModelsDisplay(availableModels);
      }
    } else {
      const runningResponse = await fetchFn(
        "/api/models/running" + refreshQ,
        {},
        _API_TIMEOUT_MS,
      );
      const runR = await readApiJson(runningResponse);
      if (runR.responseOk) {
        const runningData = runR.data;
        runningModels = Array.isArray(runningData.models)
          ? runningData.models
          : [];
        _lastRunningModelsSnapshot = runningModels;
        updateRunningModelsDisplay(runningModels);
      }
    }
  } catch (error) {
    console.log("Failed to update models:", error);
  } finally {
    _updateModelDataInFlight = false;
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

  const countEl = document.getElementById("runningModelsCount");
  if (countEl) {
    countEl.textContent = models.length;
  }

  if (!models || models.length === 0) {
    runningModelsContainer.innerHTML = "";
    return;
  }

  const newNames = new Set(
    models.map((m) => (m.name || "").trim()).filter(Boolean),
  );
  const currentCards = runningModelsContainer.querySelectorAll(
    ".model-card[data-model-name]",
  );
  const currentNames = new Set(
    Array.from(currentCards).map((c) => (c.dataset.modelName || "").trim()),
  );
  const namesChanged =
    newNames.size !== currentNames.size ||
    [...newNames].some((n) => !currentNames.has(n));

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
    const capabilityIcons = getCapabilitiesHTML(model);

    const cardIndex = index + 1;

    const titleBlock =
      window.modelCards &&
      typeof window.modelCards.modelTitleMarkup === "function"
        ? window.modelCards.modelTitleMarkup(name)
        : `<div class="model-title">${safeNameText}</div>`;

    const settingsBtnInner = getSettingsButtonInnerHtml(hasCustom);

    const specsHtml =
      window.modelCards &&
      typeof window.modelCards.buildSpecsRowsRunning === "function"
        ? window.modelCards.buildSpecsRowsRunning(model, cardIndex)
        : "";

  const visionDataAttr =
    model?.has_vision === true
      ? ' data-has-vision="true"'
      : model?.has_vision === false
        ? ' data-has-vision="false"'
        : "";
  const toolsDataAttr =
    model?.has_tools === true
      ? ' data-has-tools="true"'
      : model?.has_tools === false
        ? ' data-has-tools="false"'
        : "";
  const reasoningDataAttr =
    model?.has_reasoning === true
      ? ' data-has-reasoning="true"'
      : model?.has_reasoning === false
        ? ' data-has-reasoning="false"'
        : "";
  const moeDataAttr =
    model?.has_moe === true
      ? ' data-has-moe="true"'
      : model?.has_moe === false
        ? ' data-has-moe="false"'
        : "";

  return `
      <div class="col">
        <div class="model-card h-100 model-card--running" data-model-name="${safeDataName}"${visionDataAttr}${toolsDataAttr}${reasoningDataAttr}${moeDataAttr}>
          <div class="model-header model-card-head">
            <div class="model-icon-wrapper">
              <i class="fas fa-brain model-icon-main"></i>
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
            ${specsHtml}
          </div>
          <div class="model-actions model-actions--running">
            <button type="button" class="btn btn-primary" data-model-action="restart" onclick="restartModel(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Reload this model in memory (applies updated settings from disk).">
              <i class="fas fa-redo"></i> <span class="model-action-btn-label">Restart</span>
            </button>
            <button type="button" class="btn btn-success" onclick="openAskModal(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Send a question to this running model (streams the response)." aria-label="Ask this model a question">
              <i class="fas fa-comment-dots"></i> <span class="model-action-btn-label">Ask?</span>
            </button>
            <button class="btn btn-info" onclick="showModelInfo(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Open a modal with raw Ollama model details (JSON).">
              <i class="fas fa-info-circle"></i> <span class="model-action-btn-label">Info</span>
            </button>
            <button type="button" class="btn btn-secondary model-action-settings-btn" onclick="openModelSettingsModal(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Edit temperature, context, and other options stored for this dashboard." aria-label="${hasCustom ? "Settings (saved custom defaults)" : "Settings (using defaults)"}">
              ${settingsBtnInner}
            </button>
            <button type="button" class="btn btn-warning" data-model-action="stop" onclick="stopModel(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Unload from VRAM (ollama stop). Model files stay installed.">
              <i class="fas fa-stop"></i> <span class="model-action-btn-label">Stop</span>
            </button>
          </div>
        </div>
      </div>
    `;
  };

  if (namesChanged) {
    const cardsHtml = models
      .map((m, idx) => buildRunningModelCardHTML(m, idx))
      .join("");
    runningModelsContainer.innerHTML = cardsHtml;
    afterModelCardsRendered();
    runningModelsContainer.querySelectorAll(".model-card").forEach((card) => {
      setModelCardVisible(card, true);
    });
    return;
  }

  try {
    const syncFn =
      window.modelCards &&
      typeof window.modelCards.syncModelCardFromModel === "function"
        ? window.modelCards.syncModelCardFromModel
        : null;
    currentCards.forEach((card) => {
      const name = (card.dataset.modelName || "").trim();
      if (!name) return;
      const matching = (models || []).find(
        (m) => m.name && m.name.trim() === name,
      );
      if (!matching) return;
      if (syncFn) syncFn(card, matching);
      syncSettingsSavedIndicatorOnCard(card, matching);
    });
  } catch (err) {
    console.log("Failed to update running model cards", err);
  }
  runningModelsContainer.querySelectorAll(".model-card").forEach((card) => {
    setModelCardVisible(card, true);
  });
}

window.updateRunningModelsDisplay = updateRunningModelsDisplay;

function buildAvailableModelCardHTML(model) {
  const name = model?.name || "Unknown";
  const safeDataName =
    typeof escapeHtml === "function" ? escapeHtml(String(name)) : String(name);
  const hasCustom = modelHasCustomSettings(model);
  const details = model?.details || {};
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

  const specsHtml =
    window.modelCards &&
    typeof window.modelCards.buildSpecsRowsAvailable === "function"
      ? window.modelCards.buildSpecsRowsAvailable(model, contextStr)
      : "";
  const visionDataAttr =
    model?.has_vision === true
      ? ' data-has-vision="true"'
      : model?.has_vision === false
        ? ' data-has-vision="false"'
        : "";
  const toolsDataAttr =
    model?.has_tools === true
      ? ' data-has-tools="true"'
      : model?.has_tools === false
        ? ' data-has-tools="false"'
        : "";
  const reasoningDataAttr =
    model?.has_reasoning === true
      ? ' data-has-reasoning="true"'
      : model?.has_reasoning === false
        ? ' data-has-reasoning="false"'
        : "";
  const moeDataAttr =
    model?.has_moe === true
      ? ' data-has-moe="true"'
      : model?.has_moe === false
        ? ' data-has-moe="false"'
        : "";

  return `
      <div class="col">
        <div class="model-card h-100" data-model-name="${safeDataName}"${visionDataAttr}${toolsDataAttr}${reasoningDataAttr}${moeDataAttr}>
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
            ${specsHtml}
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
    applyCapabilityFilters("availableModelsContainer");
    return;
  }

  try {
    const syncFn =
      window.modelCards &&
      typeof window.modelCards.syncModelCardFromModel === "function"
        ? window.modelCards.syncModelCardFromModel
        : null;
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
      if (syncFn) {
        syncFn(card, matching);
      }
      syncSettingsSavedIndicatorOnCard(card, matching);
    });
    applyCapabilityFilters("availableModelsContainer");
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

document.addEventListener("DOMContentLoaded", function () {
  if (typeof startStatsPollTimer === "function") startStatsPollTimer();
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

  ensureCapabilityFilterButtons();

  ["availableModelsContainer", "downloadableModelsContainer"].forEach((id) =>
    applyCapabilityFilters(id),
  );
});

function modelCardColumn(card) {
  if (!card) return null;
  const parent = card.parentElement;
  if (parent && parent.classList.contains("col")) return parent;
  return card.closest(".col");
}

function setModelCardVisible(card, visible) {
  const column = modelCardColumn(card);
  if (column) column.style.display = visible ? "" : "none";
}

function isDownloadActiveCard(card) {
  if (!card) return false;
  if (card.dataset.downloadActive === "true") return true;
  const name = (card.dataset.modelName || "").trim();
  if (!name || typeof getActiveDownloads !== "function") return false;
  return Object.prototype.hasOwnProperty.call(getActiveDownloads(), name);
}

function capabilityFlagsFromCard(card) {
  const caps = card.querySelectorAll(".capability-icon");
  let hasReasoning = false;
  let hasVision = false;
  let hasTools = false;
  let reasoningKnown = false;
  let visionKnown = false;
  let toolsKnown = false;
  let hasMoe = false;
  let moeKnown = false;

  if (caps.length >= 3) {
    const [reasoningEl, visionEl, toolsEl] = caps;
    hasReasoning = reasoningEl.classList.contains("enabled");
    hasVision = visionEl.classList.contains("enabled");
    hasTools = toolsEl.classList.contains("enabled");
    reasoningKnown =
      reasoningEl.classList.contains("enabled") ||
      reasoningEl.classList.contains("disabled");
    visionKnown =
      visionEl.classList.contains("enabled") ||
      visionEl.classList.contains("disabled");
    toolsKnown =
      toolsEl.classList.contains("enabled") ||
      toolsEl.classList.contains("disabled");
  } else {
    const reasoning = card.dataset.hasReasoning;
    const vision = card.dataset.hasVision;
    const tools = card.dataset.hasTools;
    hasReasoning = reasoning === "true";
    hasVision = vision === "true";
    hasTools = tools === "true";
    reasoningKnown = reasoning === "true" || reasoning === "false";
    visionKnown = vision === "true" || vision === "false";
    toolsKnown = tools === "true" || tools === "false";
  }

  if (caps.length >= 4) {
    const moeEl = caps[3];
    hasMoe = moeEl.classList.contains("enabled");
    moeKnown =
      moeEl.classList.contains("enabled") ||
      moeEl.classList.contains("disabled");
  } else {
    caps.forEach((el) => {
      if (el.querySelector(".fa-cubes")) {
        hasMoe = el.classList.contains("enabled");
        moeKnown =
          el.classList.contains("enabled") ||
          el.classList.contains("disabled");
      }
    });
  }
  if (!moeKnown && card.dataset.hasMoe !== undefined) {
    hasMoe = card.dataset.hasMoe === "true";
    moeKnown = card.dataset.hasMoe === "true" || card.dataset.hasMoe === "false";
  }

  return {
    hasReasoning,
    hasVision,
    hasTools,
    hasMoe,
    reasoningKnown,
    visionKnown,
    toolsKnown,
    moeKnown,
  };
}

function filterButtonsForContainer(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return null;
  const shell = container.closest(".models-section-shell");
  const bar =
    shell?.querySelector(".capability-filters") ||
    document.querySelector("#availableModelsFilters, #bestModelsFilters");
  if (!bar) return null;
  return {
    reasoning: bar.querySelector('.filter-btn[data-capability="reasoning"]'),
    vision: bar.querySelector('.filter-btn[data-capability="vision"]'),
    tools: bar.querySelector('.filter-btn[data-capability="tools"]'),
    moe: bar.querySelector('.filter-btn[data-capability="moe"]'),
  };
}

function toggleCapabilityFilter(capability) {
  const filterBtns = document.querySelectorAll(
    `.filter-btn[data-capability="${capability}"]`,
  );
  filterBtns.forEach((btn) => {
    btn.classList.toggle("active");
    btn.setAttribute("aria-pressed", btn.classList.contains("active") ? "true" : "false");
  });

  ["availableModelsContainer", "downloadableModelsContainer"].forEach((id) =>
    applyCapabilityFilters(id),
  );
  const runC = document.getElementById("runningModelsContainer");
  if (runC) {
    runC.querySelectorAll(".model-card").forEach((card) => {
      setModelCardVisible(card, true);
    });
  }
}

function syncModelSectionCount(containerId, countElementId) {
  const container = document.getElementById(containerId);
  const countEl = document.getElementById(countElementId);
  if (!container || !countEl) return;
  const cards = container.querySelectorAll(".model-card[data-model-name]");
  const total = cards.length;
  let visible = 0;
  cards.forEach((card) => {
    const column = modelCardColumn(card);
    if (!column || column.style.display !== "none") visible += 1;
  });
  countEl.textContent = visible === total ? String(total) : `${visible}/${total}`;
}

function applyCapabilityFilters(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const buttons = filterButtonsForContainer(containerId);
  const reasoningRequired =
    buttons?.reasoning?.classList.contains("active") ?? false;
  const visionRequired =
    buttons?.vision?.classList.contains("active") ?? false;
  const toolsRequired =
    buttons?.tools?.classList.contains("active") ?? false;
  const moeRequired =
    buttons?.moe?.classList.contains("active") ?? false;

  const cards = container.querySelectorAll(".model-card");

  if (!reasoningRequired && !visionRequired && !toolsRequired && !moeRequired) {
    cards.forEach((card) => setModelCardVisible(card, true));
    if (containerId === "availableModelsContainer") {
      syncModelSectionCount("availableModelsContainer", "availableModelsCount");
    }
    return;
  }

  cards.forEach((card) => {
    if (isDownloadActiveCard(card)) {
      setModelCardVisible(card, true);
      return;
    }
    const flags = capabilityFlagsFromCard(card);
    let matches = true;
    if (reasoningRequired) {
      if (flags.reasoningKnown && !flags.hasReasoning) matches = false;
    }
    if (visionRequired) {
      if (flags.visionKnown && !flags.hasVision) matches = false;
    }
    if (toolsRequired) {
      if (flags.toolsKnown && !flags.hasTools) matches = false;
    }
    if (moeRequired) {
      if (flags.moeKnown && !flags.hasMoe) matches = false;
    }
    setModelCardVisible(card, matches);
  });

  if (containerId === "availableModelsContainer") {
    syncModelSectionCount("availableModelsContainer", "availableModelsCount");
  }
}

window.toggleCapabilityFilter = toggleCapabilityFilter;
window.applyCapabilityFilters = applyCapabilityFilters;
