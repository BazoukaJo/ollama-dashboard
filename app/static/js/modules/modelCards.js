// Ensure getCapabilitiesHTML is available globally (uses capState from main.js when loaded)
if (!window.getCapabilitiesHTML) {
  window.getCapabilitiesHTML = function (model) {
    const capState = (v) => (v === true ? "enabled" : v === false ? "disabled" : "unknown");
    const capTitle = (v, l) => (v === true ? `${l}: Available` : v === false ? `${l}: Not available` : `${l}: Unknown`);
    const r = model?.has_reasoning, v = model?.has_vision, t = model?.has_tools;
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
  };
}
(function () {
  const escapeHtml = window.escapeHtml || ((s) => s);
  const getCapabilitiesHTML = window.getCapabilitiesHTML;
  function buildDownloadableModelCardHTML(model) {
    return `
        <div class="col-md-6 col-lg-4">
          <div class="model-card h-100" data-model-name="${escapeHtml(model.name)}">
                <div class="model-header">
                    <div class="model-icon-wrapper">
                        <i class="fas fa-cloud model-icon-main"></i>
                    </div>
                    <div class="model-meta">
                        <span class="status-indicator downloadable">
                            <i class="fas fa-circle"></i>Downloadable
                        </span>
                    </div>
                </div>
                <div class="model-title">${escapeHtml(model.name) || "Unknown"}</div>
                <div class="model-capabilities">${getCapabilitiesHTML(model)}</div>
                <div class="model-specs">
                  <div class="spec-row compact-hide">
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-cogs"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">Family</div>
                                <div class="spec-value">${model.family || "Unknown"}</div>
                            </div>
                        </div>
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-weight"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">Parameters</div>
                                <div class="spec-value">${model.parameter_size || "Unknown"}</div>
                            </div>
                        </div>
                    </div>
                    <div class="spec-row spec-row-size-context compact-hide">
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-hdd"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">Size</div>
                                <div class="spec-value">${model.size || "Unknown"}</div>
                            </div>
                        </div>
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-align-left"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">Context</div>
                                <div class="spec-value">${model.context_length ?? "Unknown"}</div>
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
                <div class="model-actions">
                    <button class="btn btn-primary w-100" onclick="pullModel(this.closest('.model-card').dataset.modelName)" title="Download model">
                        <i class="fas fa-download"></i> <span class="d-none d-sm-inline">Download</span>
                    </button>
                </div>
            </div>
        </div>`;
  }
  window.modelCards = window.modelCards || {};
  window.modelCards.buildDownloadableModelCardHTML =
    buildDownloadableModelCardHTML;
})();
