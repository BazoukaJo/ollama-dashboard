/**
 * Main JavaScript functionality for Ollama Dashboard
 */

// Model data poll interval (seconds) - read from DOM or default 5
function getPollIntervalSec() {
  const el = document.querySelector(".refresh-indicator");
  const val = el && el.dataset.pollInterval;
  const n = parseInt(val, 10);
  return Number.isFinite(n) && n > 0 ? n : 5;
}

let refreshCountdown = 5;

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
      if (refreshCountdown <= 0) refreshCountdown = getPollIntervalSec();
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
  const btn = document.getElementById("refreshDashboardBtn");
  if (btn) {
    const icon = btn.querySelector("i");
    if (icon) {
      icon.classList.add("fa-spin");
      setTimeout(() => icon.classList.remove("fa-spin"), 800);
    }
  }
  if (typeof updateModelData === "function") updateModelData();
  if (typeof updateSystemStats === "function") updateSystemStats();
}

/**
 * Poll for model status change and refresh UI when confirmed.
 * @param {string} modelName - Name of the model to check
 * @param {boolean} shouldBeRunning - True if we expect the model to be running, false if stopped
 */
async function pollForModelStatus(modelName, shouldBeRunning) {
  const maxAttempts = 10; // Maximum 5 seconds (10 * 500ms)
  let attempts = 0;

  while (attempts < maxAttempts) {
    attempts++;

    try {
      const response = await fetch("/api/models/running");
      if (response.ok) {
        const data = await response.json();
        const runningModels = Array.isArray(data.models) ? data.models : [];
        const isRunning = runningModels.some((m) => m.name === modelName);

        // Check if the expected state matches
        if (isRunning === shouldBeRunning) {
          refreshDashboardData();
          return;
        }
      }
    } catch (error) {
      console.log("Error polling model status:", error);
    }

    // Wait 500ms before next check
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  // If we've exhausted attempts, refresh anyway
  console.log(`Status polling timeout for ${modelName}, refreshing anyway`);
  refreshDashboardData();
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
    const result = await response.json();
    if (result.success) {
      showNotification(result.message, "success");
      refreshDashboardData();
      await pollForModelStatus(modelName, true);
    } else {
      showNotification(result.message, "error");
    }
  } catch (error) {
    showNotification("Failed to start model: " + error.message, "error");
  }
}

async function stopModel(modelName) {
  const card = document.querySelector(
    `.model-card[data-model-name="${cssEscape(modelName)}"]`,
  );
  const stopButton = card
    ? card.querySelector('button[title="Stop model"]')
    : null;
  const originalText = stopButton ? stopButton.innerHTML : null;
  if (stopButton) {
    stopButton.innerHTML =
      '<i class="fas fa-spinner fa-spin me-1"></i>Stopping...';
    stopButton.disabled = true;
  }

  try {
    showNotification(`Attempting to stop model ${modelName}...`, "info");

    const response = await fetch(
      `/api/models/stop/${encodeURIComponent(modelName)}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      },
    );

    // Check if response is OK before parsing JSON
    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      let errorMessage = `Failed to stop model: HTTP ${response.status}`;
      try {
        const errorJson = JSON.parse(errorText);
        if (errorJson.message) {
          errorMessage = errorJson.message;
        }
      } catch {
        if (errorText) {
          errorMessage = errorText;
        }
      }
      showNotification(errorMessage, "error");
      if (stopButton && originalText !== null) {
        stopButton.innerHTML = originalText;
        stopButton.disabled = false;
      }
      return;
    }

    const result = await response.json();

    if (result.success) {
      showNotification(
        result.message || `Model ${modelName} stopped successfully`,
        "success",
      );
      refreshDashboardData();
      await pollForModelStatus(modelName, false);
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

async function restartModel(modelName) {
  const card = document.querySelector(
    `.model-card[data-model-name="${cssEscape(modelName)}"]`,
  );
  const restartButton = card
    ? card.querySelector('button[title="Restart model"]')
    : null;
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
    const result = await response.json();

    if (result.success) {
      showNotification(result.message, "success");
      refreshDashboardData();
      await pollForModelStatus(modelName, true);
    } else {
      showNotification(result.message, "error");
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
    ? card.querySelector('button[title="Delete model"]')
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
    let result;
    try {
      result = await response.json();
    } catch (jsonErr) {
      // Non-JSON response (likely error)
      result = { success: false, message: await response.text() };
    }

    if (result.success) {
      showNotification(result.message, "success");
      setTimeout(() => location.reload(), 2000);
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
    const info = await response.json();

    if (response.ok) {
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
        const [availResp, runningResp] = await Promise.all([
          fetch("/api/models/available"),
          fetch("/api/models/running"),
        ]);
        if (availResp.ok) {
          const availJson = await availResp.json();
          const list = Array.isArray(availJson.models) ? availJson.models : [];
          const match = list.find((m) => {
            const mn = normalizeName(m?.name || m?.model || "");
            return equalsLoose(mn, target);
          });
          if (match) flagsFromCards = getCapabilityFlags(match);
        }
        if (!flagsFromCards && runningResp.ok) {
          const runningJson = await runningResp.json();
          const runningList = Array.isArray(runningJson.models) ? runningJson.models : [];
          const rmatch = runningList.find((m) => {
            const rn = normalizeName(m?.name || m?.model || "");
            return equalsLoose(rn, target);
          }) || null;
          if (rmatch) flagsFromCards = getCapabilityFlags(rmatch);
        }
      } catch (e) {
        // Non-fatal: fallback to info-derived flags below
      }

      const details = info.details || {};
      const summaryHtml = buildModelSummary(info, details, modelName);
      const capabilityBadges = flagsFromCards
        ? renderCapabilityBadges(flagsFromCards)
        : renderCapabilityBadges(info);
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
                  <div class="section-header">
                    <div>
                      <h6 class="section-title">Parameters</h6>
                      <p class="section-hint">Runtime overrides and defaults</p>
                    </div>
                  </div>
                  <div class="model-code-wrapper">${parametersBlock}</div>
                </section>

                <section class="model-info-section">
                  <div class="section-header">
                    <div>
                      <h6 class="section-title">Modelfile</h6>
                      <p class="section-hint">Source definition used to build this model</p>
                    </div>
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
      const modal = new bootstrap.Modal(
        document.getElementById("modelInfoModal"),
      );
      modal.show();

      document
        .getElementById("modelInfoModal")
        .addEventListener("hidden.bs.modal", function () {
          this.remove();
        });
    } else {
      showNotification("Failed to get model info: " + info.error, "error");
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
  const r = info?.has_reasoning, v = info?.has_vision, t = info?.has_tools;
  const badges = [
    { label: "Reasoning", icon: "fa-brain", val: r },
    { label: "Vision", icon: "fa-eye", val: v },
    { label: "Tools", icon: "fa-wrench", val: t },
  ];

  return badges
    .map(
      (badge) => {
        const state = capState(badge.val);
        const title = capTitle(badge.val, badge.label);
        return `<span class="capability-pill ${state}" title="${title}">
          <i class="fas ${badge.icon}"></i>
          <span>${badge.label}</span>
        </span>`;
      },
    )
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
      return `<span class="text-info">${escapeHtml(new Date(
        json,
      ).toLocaleString())}</span>`;
    }
    const maxLength = 100;
    if (json.length > maxLength) {
      const truncated = json.substring(0, maxLength);
      return `<span class="text-warning" title="${escapeHtml(json)}">"${escapeHtml(truncated)}..."</span>`;
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
  const isError = type === "error" || type === "danger" || type !== "success";
  notification.className = `alert alert-${
    type === "success" ? "success" : "danger"
  } alert-dismissible fade show position-fixed`;
  notification.style.cssText =
    "top: 20px; right: 20px; z-index: 9999; min-width: 300px; max-width: 500px;";

  // Add copy button for error messages
  const copyButton = isError
    ? `
    <button type="button" class="btn btn-sm btn-outline-light" onclick="copyErrorToClipboard(this)"
            style="padding: 0.25rem 0.5rem; font-size: 0.75rem; flex-shrink: 0;" title="Copy error to clipboard">
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
function getCapabilitiesHTML(model) {
  const r = model?.has_reasoning;
  const v = model?.has_vision;
  const t = model?.has_tools;
  return `
    <span class="capability-icon ${capState(r)}" title="${capTitle(r, "Reasoning")}">
      <i class="fas fa-brain"></i>
    </span>
    <span class="capability-icon ${capState(v)}" title="${capTitle(v, "Image Processing")}">
      <i class="fas fa-image"></i>
    </span>
    <span class="capability-icon ${capState(t)}" title="${capTitle(t, "Tool Usage")}">
      <i class="fas fa-tools"></i>
    </span>
  `;
}

function getCapabilityFlags(source) {
  if (!source || typeof source !== "object") {
    return { hasReasoning: false, hasVision: false, hasTools: false };
  }

  const capsObj = source.capabilities || source.details?.capabilities || {};
  const truthy = (v) => {
    if (v === undefined || v === null) return false;
    if (typeof v === "boolean") return v;
    if (typeof v === "number") return v !== 0;
    if (typeof v === "string")
      return /^(true|yes|enabled|on|available)$/i.test(v.trim());
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    return false;
  };
  const fromStrings = (obj, keys) => keys.some((k) => truthy(obj?.[k]));

  return {
    hasReasoning:
      truthy(source.has_reasoning) ||
      truthy(capsObj.reasoning) ||
      fromStrings(source, ["reasoning", "hasReasoning"]) ||
      fromStrings(capsObj, ["has_reasoning", "hasReasoning"]),
    hasVision:
      truthy(source.has_vision) ||
      truthy(capsObj.vision) ||
      fromStrings(source, ["vision", "hasVision", "image"]) ||
      fromStrings(capsObj, ["has_vision", "hasVision", "vision"]),
    hasTools:
      truthy(source.has_tools) ||
      truthy(capsObj.tools) ||
      fromStrings(source, ["tools", "hasTools"]) ||
      fromStrings(capsObj, ["has_tools", "hasTools", "tools"]),
  };
}

// Historical data storage for timelines
const timelineData = {
  cpu: [],
  memory: [],
  vram: [],
  disk: [],
};

const MAX_TIMELINE_POINTS = 60; // 60 seconds of data

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
    const stats = await response.json();

    if (response.ok) {
      // Update percentages
      const cpuPercentEl = document.getElementById("cpuPercent");
      const memoryPercentEl = document.getElementById("memoryPercent");
      const vramPercentEl = document.getElementById("vramPercent");
      const diskPercentEl = document.getElementById("diskPercent");

      if (cpuPercentEl)
        cpuPercentEl.textContent = `${stats.cpu_percent.toFixed(1)}%`;
      if (memoryPercentEl)
        memoryPercentEl.textContent = `${stats.memory.percent.toFixed(1)}%`;
      if (vramPercentEl)
        vramPercentEl.textContent =
          stats.vram && stats.vram.total > 0
            ? `${stats.vram.percent.toFixed(1)}%`
            : "--%";
      if (diskPercentEl)
        diskPercentEl.textContent = `${stats.disk.percent.toFixed(1)}%`;

      // Store historical data
      timelineData.cpu.push(stats.cpu_percent);
      timelineData.memory.push(stats.memory.percent);
      timelineData.vram.push(
        stats.vram && stats.vram.total > 0 ? stats.vram.percent : 0,
      );
      timelineData.disk.push(stats.disk.percent);

      // Limit data points
      if (timelineData.cpu.length > MAX_TIMELINE_POINTS) {
        timelineData.cpu.shift();
        timelineData.memory.shift();
        timelineData.vram.shift();
        timelineData.disk.shift();
      }

      // Update timelines
      const cpuCanvas = document.getElementById("cpuTimeline");
      const memoryCanvas = document.getElementById("memoryTimeline");
      const vramCanvas = document.getElementById("vramTimeline");
      const diskCanvas = document.getElementById("diskTimeline");

      if (cpuCanvas) drawTimeline(cpuCanvas, timelineData.cpu, "#0d6efd");
      if (memoryCanvas)
        drawTimeline(memoryCanvas, timelineData.memory, "#198754");
      if (vramCanvas) drawTimeline(vramCanvas, timelineData.vram, "#0dcaf0");
      if (diskCanvas) drawTimeline(diskCanvas, timelineData.disk, "#ffc107");

      // Update last update time
      const lastUpdateTimeEl = document.getElementById("lastUpdateTime");
      if (lastUpdateTimeEl)
        lastUpdateTimeEl.textContent = new Date().toLocaleTimeString();
    }
  } catch (error) {
    console.log("Failed to update system stats:", error);
  }
}

// Model data update function
async function updateModelData() {
  // Update running models
  try {
    const runningResponse = await fetch("/api/models/running");
    if (runningResponse.ok) {
      const runningData = await runningResponse.json();
      const runningModels = Array.isArray(runningData.models) ? runningData.models : [];
      updateRunningModelsDisplay(runningModels);
    }
  } catch (error) {
    console.log("Failed to update running models:", error);
  }

  // Update available models (less frequently)
  try {
    const availableResponse = await fetch("/api/models/available");
    if (availableResponse.ok) {
      const availableModels = await availableResponse.json();
      updateAvailableModelsDisplay(availableModels.models || []);
    }
  } catch (error) {
    console.log("Failed to update available models:", error);
  }

  // Update Ollama version
  try {
    const versionResponse = await fetch("/api/version");
    if (versionResponse.ok) {
      const versionData = await versionResponse.json();
      updateVersionDisplay(versionData.version || "Unknown");
    }
  } catch (error) {
    console.log("Failed to update Ollama version:", error);
  }

  // Update model memory usage
  try {
    const memoryResponse = await fetch("/api/models/memory/usage");
    if (memoryResponse.ok) {
      const memoryData = await memoryResponse.json();
      updateModelMemoryDisplay(memoryData);
    }
  } catch (error) {
    console.log("Failed to update model memory usage:", error);
  }

  resetRefreshCountdown();
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

  // Get current model names from DOM
  const currentCards = runningModelsContainer.querySelectorAll(".model-card");
  const currentModelNames = Array.from(currentCards)
    .map((card) =>
      card.dataset && card.dataset.modelName
        ? card.dataset.modelName.trim()
        : "",
    )
    .filter((name) => name)
    .sort();

  // Get new model names from API response
  const newModelNames = models
    .map((m) => m.name)
    .filter((name) => name)
    .sort();

  // Compare model names to detect any changes (not just count)
  const namesChanged =
    currentModelNames.length !== newModelNames.length ||
    currentModelNames.some((name, idx) => name !== newModelNames[idx]);

  if (namesChanged) {
    // Models changed (loaded, unloaded, or replaced), trigger a page reload to get fresh data
    location.reload();
    return;
  }

  // Update individual model cards with new data
  models.forEach((model) => {
    // Find model card by model data attribute for robust and reliable lookup
    let modelCard = runningModelsContainer.querySelector(
      `.model-card[data-model-name="${cssEscape(model.name)}"]`,
    );
    // Fallback: compare dataset values for safety
    if (!modelCard) {
      const cards = runningModelsContainer.querySelectorAll(".model-card");
      for (let i = 0; i < cards.length; i++) {
        const dataName =
          cards[i].dataset && cards[i].dataset.modelName
            ? cards[i].dataset.modelName.trim()
            : "";
        if (dataName === model.name) {
          modelCard = cards[i];
          break;
        }
      }
    }
    if (modelCard) {
      // Update expiration time if it exists
      const expiresEl = modelCard.querySelector(".model-expires");
      if (expiresEl && model.expires_at) {
        expiresEl.textContent =
          model.expires_at.relative || model.expires_at.local || "";
      }

      // Update size if it changed
      const sizeEl = modelCard.querySelector(".model-size");
      if (sizeEl && model.formatted_size) {
        sizeEl.textContent = model.formatted_size;
      }

      // Update capability icons (reasoning, vision, tools): enabled=green, disabled=grey, unknown=yellow
      try {
        const caps = modelCard.querySelectorAll(".capability-icon");
        if (caps && caps.length >= 3) {
          const [reasoningEl, visionEl, toolsEl] = caps;
          for (const [el, val, label] of [
            [reasoningEl, model.has_reasoning, "Reasoning"],
            [visionEl, model.has_vision, "Image Processing"],
            [toolsEl, model.has_tools, "Tool Usage"],
          ]) {
            const state = val === true ? "enabled" : val === false ? "disabled" : "unknown";
            const title = val === true ? `${label}: Available` : val === false ? `${label}: Not available` : `${label}: Unknown`;
            el.classList.remove("enabled", "disabled", "unknown");
            el.classList.add(state);
            el.setAttribute("title", title);
          }
        }
      } catch (err) {
        console.log(
          "Failed to update capability icons for running model",
          model.name,
          err,
        );
      }

      // Update Live Metrics: GPU Allocation and Context
      try {
        const gpuEl = modelCard.querySelector(`[id^="model-gpu-"]`);
        const contextEl = modelCard.querySelector(`[id^="model-context-"]`);

        if (gpuEl && model.size_vram !== undefined && model.size > 0) {
          const vramPercent = ((model.size_vram / model.size) * 100).toFixed(1);
          const vramFormatted = model.formatted_size_vram || "0 B";
          gpuEl.textContent = `${vramPercent}% (${vramFormatted})`;
        }

        if (contextEl) {
          const ctx = model.context_length ?? (model.details || {}).context_length;
          contextEl.textContent = ctx != null && ctx !== "" ? String(ctx) : "Unknown";
        }
      } catch (err) {
        console.log("Failed to update live metrics for", model.name, err);
      }
    }
  });
  // Re-apply filters after update
  applyCapabilityFilters("runningModelsContainer");
}

function updateAvailableModelsDisplay(models) {
  const availableModelsContainer = document.getElementById(
    "availableModelsContainer",
  );
  if (!availableModelsContainer) return;

  // Update the count display
  const countEl = document.getElementById("availableModelsCount");
  if (countEl) {
    countEl.textContent = models.length;
  }

  // Update capability icons for available models in the DOM
  try {
    const availableCards = document.querySelectorAll(
      "#availableModelsContainer .model-card",
    );
    availableCards.forEach((card) => {
      const titleEl = card.querySelector(".model-title");
      // Prefer dataset attribute if present
      const name =
        card.dataset && card.dataset.modelName
          ? card.dataset.modelName.trim()
          : titleEl
            ? titleEl.textContent.trim()
            : null;
      if (!name) return;
      const matching = models.find((m) => m.name && m.name.trim() === name);
      if (!matching) return;
      const caps = card.querySelectorAll(".capability-icon");
      if (caps && caps.length >= 3) {
        const [reasoningEl, visionEl, toolsEl] = caps;
        for (const [el, val, label] of [
          [reasoningEl, matching.has_reasoning, "Reasoning"],
          [visionEl, matching.has_vision, "Image Processing"],
          [toolsEl, matching.has_tools, "Tool Usage"],
        ]) {
          const state = val === true ? "enabled" : val === false ? "disabled" : "unknown";
          const title = val === true ? `${label}: Available` : val === false ? `${label}: Not available` : `${label}: Unknown`;
          el.classList.remove("enabled", "disabled", "unknown");
          el.classList.add(state);
          el.setAttribute("title", title);
        }
      }
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

function updateModelMemoryDisplay(memoryData) {
  // Logic removed as redundant system info was removed from model cards.
  // System-wide stats are already handled by updateSystemStats().
}

// Service management functions moved to serviceControl.js

// Compact mode functionality
function initializeCompactMode() {
  const compactToggle = document.getElementById("compactToggle");
  const body = document.body;

  // Check if compact mode was previously enabled
  const isCompact = localStorage.getItem("compactMode") === "true";

  if (isCompact) {
    body.classList.add("compact-mode");
    compactToggle.classList.add("active");
    compactToggle.innerHTML = '<i class="fas fa-expand"></i>';
  }

  // Toggle compact mode on button click
  compactToggle.addEventListener("click", function () {
    const isCurrentlyCompact = body.classList.contains("compact-mode");

    if (isCurrentlyCompact) {
      body.classList.remove("compact-mode");
      compactToggle.classList.remove("active");
      compactToggle.innerHTML = '<i class="fas fa-compress"></i>';
      localStorage.setItem("compactMode", "false");
    } else {
      body.classList.add("compact-mode");
      compactToggle.classList.add("active");
      compactToggle.innerHTML = '<i class="fas fa-expand"></i>';
      localStorage.setItem("compactMode", "true");
    }
  });
}

// updateHealthStatus & updateServiceControlButtons moved to serviceControl.js

// Downloadable models functionality - Global scope for onclick handlers
let extendedModelsLoaded = false;

async function loadExtendedModels() {
  const container = document.getElementById("extendedModelsContainer");
  if (!container) return;

  try {
    const response = await fetch("/api/models/downloadable?category=all");
    if (response.ok) {
      const data = await response.json();
      renderExtendedModels(data.models, container);
      extendedModelsLoaded = true;
    } else {
      container.innerHTML =
        '<div class="col-12 text-center text-danger">Failed to load extended models</div>';
    }
  } catch (error) {
    console.error("Error loading extended models:", error);
    container.innerHTML =
      '<div class="col-12 text-center text-danger">Error loading models</div>';
  }
}

function renderExtendedModels(models, container) {
  if (!models || models.length === 0) {
    container.innerHTML =
      '<div class="col-12 text-center text-muted">No models available</div>';
    return;
  }
  container.innerHTML = models
    .map((m) =>
      window.modelCards && window.modelCards.buildDownloadableModelCardHTML
        ? window.modelCards.buildDownloadableModelCardHTML(m)
        : `<!-- modelCards module missing -->`,
    )
    .join("");

  // Apply current filters to the newly rendered models
  applyCapabilityFilters("extendedModelsContainer");
}

async function toggleExtendedModels() {
  const container = document.getElementById("extendedModelsContainer");
  const button = document.getElementById("viewMoreModelsBtn");

  if (container.style.display === "none" || container.style.display === "") {
    // Load extended models if not already loaded
    if (!extendedModelsLoaded) {
      button.innerHTML =
        '<i class="fas fa-spinner fa-spin me-2"></i>Loading...';
      button.disabled = true;
      await loadExtendedModels();
      button.disabled = false;
    }
    // Show extended models
    container.style.display = "flex";
    button.innerHTML = '<i class="fas fa-minus-circle me-2"></i>Show Less';
  } else {
    // Hide extended models
    container.style.display = "none";
    button.innerHTML =
      '<i class="fas fa-plus-circle me-2"></i>View More Models';
  }
}

// Initialize when page loads
// Initialization handled by modules/bootstrap.js

// Downloadable models functionality
async function loadDownloadableModels() {
  const container = document.getElementById("downloadableModelsContainer");
  if (!container) return;

  try {
    const response = await fetch("/api/models/downloadable?category=best");
    if (response.ok) {
      const data = await response.json();
      renderDownloadableModels(data.models);
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
  container.innerHTML = models
    .map((m) =>
      window.modelCards && window.modelCards.buildDownloadableModelCardHTML
        ? window.modelCards.buildDownloadableModelCardHTML(m)
        : `<!-- modelCards module missing -->`,
    )
    .join("");

  // Apply current filters to the newly rendered models
  applyCapabilityFilters("downloadableModelsContainer");
}

async function pullModel(modelName) {
  const card = document.querySelector(
    `.model-card[data-model-name="${cssEscape(modelName)}"]`,
  );
  const button = card
    ? card.querySelector('button[title="Download model"]')
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

  if (button) {
    button.innerHTML =
      '<i class="fas fa-spinner fa-spin me-1"></i>Downloading...';
    button.disabled = true;
  }

  if (progressContainer) {
    progressContainer.style.display = "block";
  }

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
      throw new Error(`Failed to start download (${pullResp.status})`);
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
            if (button) {
              button.innerHTML = `<i class="fas fa-download me-1"></i>${msg}`;
            }

            // Update progress bar if total and completed are available
            if (payload.total && payload.completed !== undefined) {
              const percent = Math.round(
                (payload.completed / payload.total) * 100,
              );
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
            // Set progress to 100% on completion
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
      const fallbackResult = await fallback.json();
      pullSucceeded = !!fallbackResult.success;
      pullMessage = fallbackResult.message || pullMessage;
    }

    if (!pullSucceeded) {
      throw new Error(pullMessage || "Pull failed");
    }

    showNotification(pullMessage, "success");

    // Download complete - update UI and refresh models list
    if (button)
      button.innerHTML = '<i class="fas fa-check me-1"></i>Downloaded';
    setTimeout(() => {
      updateModelData();
      location.reload();
    }, 1500);
  } catch (err) {
    showNotification(`Download failed: ${err.message}`, "error");
    if (button && originalText !== null) {
      button.innerHTML = originalText;
      button.disabled = false;
    }
    if (progressContainer) {
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
  // Toggle globally for ALL containers
  const filterBtns = document.querySelectorAll(
    `.filter-btn[data-capability="${capability}"]`,
  );

  filterBtns.forEach((btn) => {
    btn.classList.toggle("active");
  });

  // Apply filters to ALL containers
  applyCapabilityFilters("runningModelsContainer");
  applyCapabilityFilters("availableModelsContainer");
  applyCapabilityFilters("downloadableModelsContainer");
  applyCapabilityFilters("extendedModelsContainer");
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

  const reasoningActive =
    firstReasoningBtn?.classList.contains("active") ?? true;
  const visionActive = firstVisionBtn?.classList.contains("active") ?? true;
  const toolsActive = firstToolsBtn?.classList.contains("active") ?? true;

  // If all filters are active, show all models
  if (reasoningActive && visionActive && toolsActive) {
    const cards = container.querySelectorAll(".model-card");
    cards.forEach((card) => {
      const column = card.closest(".col-md-6, .col-lg-4, .col-12");
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

      let shouldShow = true;
      if (hasReasoning && !reasoningActive) shouldShow = false;
      if (hasVision && !visionActive) shouldShow = false;
      if (hasTools && !toolsActive) shouldShow = false;

      const column = card.closest(".col-md-6, .col-lg-4, .col-12");
      if (column) {
        column.style.display = shouldShow ? "" : "none";
      }
    }
  });
}

// Global exposure
window.toggleCapabilityFilter = toggleCapabilityFilter;
