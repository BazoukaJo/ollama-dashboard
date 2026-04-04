// Ensure getCapabilitiesHTML is available globally (uses capState from main.js when loaded)
if (!window.getCapabilitiesHTML) {
  window.getCapabilitiesHTML = function (model) {
    const capState = (v) => (v === true ? "enabled" : v === false ? "disabled" : "unknown");
    const capTitle = (v, l) => (v === true ? `${l}: Available` : v === false ? `${l}: Not available` : `${l}: Unknown`);
    const r = model?.has_reasoning, v = model?.has_vision, t = model?.has_tools;
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
  };
}
(function () {
  const escapeHtml = window.escapeHtml || ((s) => s);
  const getCapabilitiesHTML = window.getCapabilitiesHTML;

  function familyFromModel(model) {
    if (model.family != null && model.family !== "") return String(model.family);
    const details = model.details || {};
    if (details.family != null && details.family !== "") return String(details.family);
    const name = model.name;
    if (!name || typeof name !== "string") return "Unknown";
    const colon = name.indexOf(":");
    return colon > 0 ? name.slice(0, colon).trim() : name.trim() || "Unknown";
  }

  function contextFromModel(model) {
    const val = model.context_length ?? (model.details && model.details.context_length);
    if (val != null && val !== "") return String(val);
    return "—";
  }

  /**
   * Parse Ollama-style model id: optional registry path, repo stem, tag after last ":".
   * Mirrors Jinja model_title_block (index.html).
   */
  function parseModelTitleParts(rawName) {
    const full = rawName != null ? String(rawName) : "";
    let tag = null;
    let stem = full;
    const cidx = full.lastIndexOf(":");
    if (cidx > 0 && cidx < full.length - 1) {
      tag = full.slice(cidx + 1);
      stem = full.slice(0, cidx);
    }
    let pathPrefix = null;
    let shortStem = stem;
    const sidx = stem.lastIndexOf("/");
    if (sidx >= 0 && sidx < stem.length - 1) {
      pathPrefix = stem.slice(0, sidx + 1);
      shortStem = stem.slice(sidx + 1);
    }
    return { full, tag, pathPrefix, shortStem };
  }

  /** Card title: optional scope line (registry path) + primary name + tag chip. */
  function modelTitleMarkup(rawName) {
    const esc = window.escapeHtml || escapeHtml;
    const { full, tag, pathPrefix, shortStem } = parseModelTitleParts(rawName);
    const titleAttr = full ? ` title="${esc(full)}"` : "";
    const scopeRow = pathPrefix
      ? `<span class="model-title-scope-row"><span class="model-title-scope">${esc(pathPrefix)}</span></span>`
      : "";
    const nameLine =
      tag != null
        ? `<span class="model-title-name-core"><span class="model-title-base">${esc(shortStem)}</span><span class="model-title-colon" aria-hidden="true">:</span><span class="model-title-tag">${esc(tag)}</span></span>`
        : `<span class="model-title-name-core model-title-name-core--full"><span class="model-title-full">${esc(shortStem)}</span></span>`;
    const inner = `<span class="model-title-stack">${scopeRow}<span class="model-title-name-line">${nameLine}</span></span>`;
    return `<div class="model-title"><span class="model-title-display"${titleAttr} aria-label="${esc(full)}">${inner}</span></div>`;
  }

  /** Settings row: status pill always visible — saved (yellow) vs default/recommended (grey). */
  function modelActionSettingsButtonInner(hasCustomSettings) {
    const status = hasCustomSettings
      ? `<span class="badge rounded-pill model-settings-status-badge model-settings-status-badge--saved" data-dashboard-tooltip="Custom per-model options saved for this dashboard (temperature, context, etc.)." aria-label="Saved custom defaults"><i class="fas fa-floppy-disk model-settings-status-ic" aria-hidden="true"></i><span>Saved</span></span>`
      : `<span class="badge rounded-pill model-settings-status-badge model-settings-status-badge--default" data-dashboard-tooltip="Using recommended or built-in defaults — nothing custom saved yet for this model." aria-label="Using default settings"><i class="fas fa-floppy-disk model-settings-status-ic" aria-hidden="true"></i><span>Default</span></span>`;
    return `<span class="model-action-settings-inner"><i class="fas fa-cog" aria-hidden="true"></i><span class="model-action-btn-label">Settings</span>${status}</span>`;
  }

  function buildDownloadableModelCardHTML(model) {
    const family = familyFromModel(model);
    const contextVal = contextFromModel(model);
    return `
        <div class="col">
          <div class="model-card h-100" data-model-name="${escapeHtml(model.name)}">
                <div class="model-header model-card-head">
                    <div class="model-icon-wrapper">
                        <i class="fas fa-cloud model-icon-main"></i>
                    </div>
                    <div class="model-card-head-body">
                        <div class="model-card-head-name-row">
                            ${modelTitleMarkup(model.name || "Unknown")}
                            <div class="model-card-head-trail" aria-label="Model capabilities">
                                <div class="model-card-head-aside" aria-label="Model capabilities">
                                    <div class="model-capabilities" aria-label="Model capabilities">${getCapabilitiesHTML(model)}</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="model-specs">
                  <div class="spec-row compact-hide">
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-cogs"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label" data-dashboard-tooltip="Model family from Ollama metadata.">Family</div>
                                <div class="spec-value">${escapeHtml(family)}</div>
                            </div>
                        </div>
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-weight"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label" data-dashboard-tooltip="Parameter class from metadata (e.g. 7B).">Parameters</div>
                                <div class="spec-value">${model.parameter_size != null && model.parameter_size !== "" ? escapeHtml(String(model.parameter_size)) : "Unknown"}</div>
                            </div>
                        </div>
                    </div>
                    <div class="spec-row compact-hide">
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-hdd"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label" data-dashboard-tooltip="Approximate download size from the library listing.">Size</div>
                                <div class="spec-value">${model.size != null && model.size !== "" ? escapeHtml(String(model.size)) : "Unknown"}</div>
                            </div>
                        </div>
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-align-left"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label" data-dashboard-tooltip="Default or reported max context (tokens) for this tag.">Context</div>
                                <div class="spec-value">${escapeHtml(contextVal)}</div>
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
                <div class="model-actions model-actions--download">
                    <button type="button" class="btn btn-primary btn-dashboard-download" onclick="pullModel(this.closest('.model-card').dataset.modelName)" data-dashboard-tooltip="Pull from Ollama (ollama pull). Progress shows below until complete.">
                        <i class="fas fa-download"></i> <span class="model-action-btn-label">Download</span>
                    </button>
                </div>
            </div>
        </div>`;
  }
  window.modelCards = window.modelCards || {};
  window.modelCards.buildDownloadableModelCardHTML =
    buildDownloadableModelCardHTML;
  window.modelCards.modelTitleMarkup = modelTitleMarkup;
  window.modelCards.modelActionSettingsButtonInner = modelActionSettingsButtonInner;
  window.modelCards.parseModelTitleParts = parseModelTitleParts;
})();
