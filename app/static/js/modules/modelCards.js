// Ensure getCapabilitiesHTML is available globally (uses capState from main.js when loaded)
if (!window.getCapabilitiesHTML) {
  window.getCapabilitiesHTML = function (model) {
    const capState = (v) =>
      v === true ? "enabled" : v === false ? "disabled" : "unknown";
    const capTitle = (v, l) =>
      v === true
        ? `${l}: Available`
        : v === false
          ? `${l}: Not available`
          : `${l}: Unknown`;
    const r = model?.has_reasoning,
      v = model?.has_vision,
      t = model?.has_tools;
    const moe =
      model?.has_moe === true
        ? `
            <span class="capability-icon enabled" data-dashboard-tooltip="Mixture of Experts (MoE)">
                <i class="fas fa-cubes"></i>
            </span>`
        : "";
    return `
            <span class="capability-icon ${capState(r)}" data-dashboard-tooltip="${capTitle(r, "Reasoning")}">
                <i class="fas fa-brain"></i>
            </span>
            <span class="capability-icon ${capState(v)}" data-dashboard-tooltip="${capTitle(v, "Image Processing")}">
                <i class="fas fa-image"></i>
            </span>
            <span class="capability-icon ${capState(t)}" data-dashboard-tooltip="${capTitle(t, "Tool Usage")}">
                <i class="fas fa-tools"></i>
            </span>${moe}
        `;
  };
}
(function () {
  const escapeHtml = window.escapeHtml || ((s) => s);
  const getCapabilitiesHTML = window.getCapabilitiesHTML;

  function familyFromModel(model) {
    if (model.family != null && model.family !== "")
      return String(model.family);
    const details = model.details || {};
    if (details.family != null && details.family !== "")
      return String(details.family);
    const name = model.name;
    if (!name || typeof name !== "string") return "Unknown";
    const colon = name.indexOf(":");
    return colon > 0 ? name.slice(0, colon).trim() : name.trim() || "Unknown";
  }

  function contextFromModel(model) {
    const val =
      model.context_length ?? (model.details && model.details.context_length);
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

  /** Card title: optional registry path prefix + primary name + tag on one line. */
  function modelTitleMarkup(rawName) {
    const esc = window.escapeHtml || escapeHtml;
    const { full, tag, pathPrefix, shortStem } = parseModelTitleParts(rawName);
    const titleAttr = full ? ` title="${esc(full)}"` : "";
    const scopePart = pathPrefix
      ? `<span class="model-title-scope-row"><span class="model-title-scope">${esc(pathPrefix)}</span></span>`
      : "";
    const nameCore =
      tag != null
        ? `<span class="model-title-name-core"><span class="model-title-base">${esc(shortStem)}</span><span class="model-title-colon" aria-hidden="true">:</span><span class="model-title-tag">${esc(tag)}</span></span>`
        : `<span class="model-title-name-core model-title-name-core--full"><span class="model-title-full">${esc(shortStem)}</span></span>`;
    const inner = `<span class="model-title-stack"><span class="model-title-name-line">${scopePart}${nameCore}</span></span>`;
    return `<div class="model-title"><span class="model-title-display"${titleAttr} aria-label="${esc(full)}">${inner}</span></div>`;
  }

  function esc(value) {
    return escapeHtml(value == null || value === "" ? String(value ?? "") : String(value));
  }

  function specItemPad() {
    return (
      '<div class="spec-item spec-item--pad" aria-hidden="true">' +
      '<div class="spec-icon"><i class="fas fa-minus" aria-hidden="true"></i></div>' +
      '<div class="spec-content"><div class="spec-label">&nbsp;</div><div class="spec-value">&nbsp;</div></div>' +
      "</div>"
    );
  }

  function specItem(options) {
    const label = options.label || "";
    const icon = options.icon || "fa-circle";
    const tooltip = options.tooltip || "";
    const valueHtml = options.valueHtml != null ? options.valueHtml : esc(options.value ?? "—");
    const valueClass = options.valueClass || "";
    const tip = tooltip ? ` data-dashboard-tooltip="${esc(tooltip)}"` : "";
    const valCls = valueClass ? ` ${valueClass}` : "";
    return (
      `<div class="spec-item">` +
      `<div class="spec-icon"><i class="fas ${icon}" aria-hidden="true"></i></div>` +
      `<div class="spec-content">` +
      `<div class="spec-label"${tip}>${esc(label)}</div>` +
      `<div class="spec-value${valCls}">${valueHtml}</div>` +
      `</div></div>`
    );
  }

  function specRow(leftHtml, rightHtml) {
    return `<div class="spec-row">${leftHtml}${rightHtml != null ? rightHtml : specItemPad()}</div>`;
  }

  function parameterSizeFromModel(model) {
    const details = (model && model.details) || {};
    const raw =
      details.parameter_size ??
      model?.parameter_size;
    if (raw == null || raw === "") return "Unknown";
    return String(raw);
  }

  function quantizationFromModel(model) {
    const details = (model && model.details) || {};
    const raw =
      details.quantization_level ??
      details.quantization ??
      model?.quantization_level ??
      model?.quantization;
    if (raw != null && String(raw).trim() !== "") return String(raw);
    const fmt = details.format;
    if (fmt != null && String(fmt).trim() !== "" && String(fmt).toLowerCase() !== "gguf") {
      return String(fmt);
    }
    const name = model?.name != null ? String(model.name) : "";
    const colon = name.lastIndexOf(":");
    if (colon > 0 && colon < name.length - 1) {
      const tag = name.slice(colon + 1).trim();
      if (/^(q\d+[_\-\w]*|f\d+[\w_\-]*|mxfp\d+|bf16|fp16|fp32)$/i.test(tag)) {
        return tag.toUpperCase().replace(/-/g, "_");
      }
    }
    return "—";
  }

  function formattedSizeFromModel(model) {
    if (model?.formatted_size != null && model.formatted_size !== "") {
      return String(model.formatted_size);
    }
    if (typeof model?.size === "number" && !Number.isNaN(model.size)) {
      if (typeof window.formatBytes === "function") {
        return window.formatBytes(model.size);
      }
      return String(model.size);
    }
    if (model?.size != null && model.size !== "") return String(model.size);
    return "Unknown";
  }

  function buildSpecsRowsCore(model, sizeTooltip) {
    const family = familyFromModel(model);
    const parameterSize = parameterSizeFromModel(model);
    const quantization = quantizationFromModel(model);
    const size = formattedSizeFromModel(model);
    return (
      specRow(
        specItem({
          label: "Family",
          icon: "fa-cogs",
          tooltip: "Model family from Ollama metadata.",
          value: family,
        }),
        specItem({
          label: "Parameters",
          icon: "fa-weight",
          tooltip: "Parameter class from metadata (e.g. 7B).",
          value: parameterSize,
        }),
      ) +
      specRow(
        specItem({
          label: "Quantization",
          icon: "fa-compress",
          tooltip: "Quantization format from metadata (e.g. Q4_K_M).",
          value: quantization,
        }),
        specItem({
          label: "Size",
          icon: "fa-hdd",
          tooltip: sizeTooltip,
          valueHtml: `<span class="text-nowrap">${esc(size)}</span>`,
        }),
      )
    );
  }

  function buildSpecsRowsAvailable(model) {
    return buildSpecsRowsCore(
      model,
      "Disk space used by this model’s files.",
    );
  }

  function buildRunningContextDualInner(maxHtml, loadedHtml, cardIndex) {
    return (
      `<span class="ctx-max text-nowrap" id="model-context-max-${cardIndex}" data-dashboard-tooltip="Maximum context from model metadata (Ollama show / details).">${maxHtml}</span>` +
      `<span class="ctx-sep text-muted" aria-hidden="true">·</span>` +
      `<span class="ctx-loaded text-nowrap" id="model-context-loaded-${cardIndex}" data-dashboard-tooltip="Context window allocated for this running process (Ollama /api/ps).">${loadedHtml}</span>`
    );
  }

  function buildSpecsRowsRunning(model, cardIndex) {
    const size = typeof model?.size === "number" ? model.size : 0;
    const sizeVram = typeof model?.size_vram === "number" ? model.size_vram : 0;
    const gpuPercent =
      size > 0 && sizeVram > 0 ? ((sizeVram / size) * 100).toFixed(1) : "0.0";
    const formattedSizeVram =
      model?.formatted_size_vram != null && model.formatted_size_vram !== ""
        ? String(model.formatted_size_vram)
        : "0 B";
    const details = model?.details || {};
    const contextMax =
      (details.context_length != null && details.context_length !== ""
        ? details.context_length
        : null) ??
      model?.context_length ??
      "Unknown";
    const contextLoaded =
      model?.loaded_context_length != null && model.loaded_context_length !== ""
        ? model.loaded_context_length
        : (model?.context_length ?? "Unknown");

    return (
      buildSpecsRowsCore(
        model,
        "On-disk size of this model’s files.",
      ) +
      specRow(
        specItem({
          label: "GPU Allocation",
          icon: "fa-microchip",
          tooltip:
            "While loaded: fraction of weights in GPU memory vs model size (from Ollama).",
          valueHtml: `<span class="text-nowrap model-size" id="model-gpu-${cardIndex}">${esc(gpuPercent)}% (${esc(formattedSizeVram)})</span>`,
        }),
        specItem({
          label: "Context",
          icon: "fa-align-left",
          tooltip: "Maximum context from metadata · allocated for this running process.",
          valueClass: "spec-context-dual",
          valueHtml: buildRunningContextDualInner(
            esc(contextMax),
            esc(contextLoaded),
            cardIndex,
          ),
        }),
      )
    );
  }

  function buildSpecsRowsDownloadable(model) {
    return buildSpecsRowsCore(
      model,
      "Approximate download size from the library listing.",
    );
  }

  function syncModelCardCapabilitiesFromModel(card, model) {
    if (!card || !model) return;
    const wrap = card.querySelector(".model-capabilities");
    const htmlFn = window.getCapabilitiesHTML;
    if (wrap && typeof htmlFn === "function") {
      wrap.innerHTML = htmlFn(model);
    }
  }

  function runningCardIndexFor(card) {
    const container = card.closest("#runningModelsContainer");
    if (!container) return 1;
    const cards = [...container.querySelectorAll(".model-card--running")];
    const idx = cards.indexOf(card);
    return idx >= 0 ? idx + 1 : 1;
  }

  function syncModelCardSpecsFromModel(card, model) {
    if (!card || !model) return;
    const specs = card.querySelector(".model-specs");
    if (!specs) return;
    if (card.classList.contains("model-card--running")) {
      specs.innerHTML = buildSpecsRowsRunning(model, runningCardIndexFor(card));
      return;
    }
    if (card.classList.contains("model-card--downloadable")) {
      specs.innerHTML = buildSpecsRowsDownloadable(model);
      return;
    }
    specs.innerHTML = buildSpecsRowsAvailable(model);
  }

  function syncModelCardFromModel(card, model) {
    syncModelCardCapabilitiesFromModel(card, model);
    syncModelCardSpecsFromModel(card, model);
  }

  /** Settings row: status pill always visible — saved (yellow) vs default/recommended (grey). */
  function modelActionSettingsButtonInner(hasCustomSettings) {
    const status = hasCustomSettings
      ? `<span class="badge rounded-pill model-settings-status-badge model-settings-status-badge--saved" data-dashboard-tooltip="Custom per-model options saved for this dashboard (temperature, context, etc.)." aria-label="Saved custom defaults"><i class="fas fa-floppy-disk model-settings-status-ic" aria-hidden="true"></i><span>Saved</span></span>`
      : `<span class="badge rounded-pill model-settings-status-badge model-settings-status-badge--default" data-dashboard-tooltip="Using recommended or built-in defaults — nothing custom saved yet for this model." aria-label="Using default settings"><i class="fas fa-floppy-disk model-settings-status-ic" aria-hidden="true"></i><span>Default</span></span>`;
    return `<span class="model-action-settings-inner"><span class="model-action-settings-label-row"><i class="fas fa-cog" aria-hidden="true"></i><span class="model-action-btn-label">Settings</span></span>${status}</span>`;
  }

  function buildDownloadableModelCardHTML(model) {
    return `
        <div class="col">
          <div class="model-card h-100 model-card--downloadable" data-model-name="${escapeHtml(model.name)}">
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
                  ${buildSpecsRowsDownloadable(model)}
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

  const MARQUEE_PX_PER_SEC = 26;
  const marqueeObservers = new WeakMap();

  function setupTitleMarquee(display) {
    if (!display) return;
    const stack = display.querySelector(".model-title-stack");
    if (!stack) return;

    display.classList.remove("is-marquee");
    display.style.removeProperty("--marquee-shift");
    display.style.removeProperty("--marquee-duration");
    stack.style.transform = "";

    const overflow = stack.scrollWidth - display.clientWidth;
    if (overflow <= 4) return;

    const duration = Math.max(12, Math.min(40, overflow / MARQUEE_PX_PER_SEC + 8));
    display.style.setProperty("--marquee-shift", `${-overflow}px`);
    display.style.setProperty("--marquee-duration", `${duration}s`);
    display.classList.add("is-marquee");
  }

  function observeTitleMarquee(display) {
    if (!display) return;
    setupTitleMarquee(display);
    if (marqueeObservers.has(display)) return;
    const ro = new ResizeObserver(() => setupTitleMarquee(display));
    ro.observe(display);
    const stack = display.querySelector(".model-title-stack");
    if (stack) ro.observe(stack);
    marqueeObservers.set(display, ro);
  }

  function setupAllTitleMarquees(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(".model-card .model-title-display").forEach(observeTitleMarquee);
  }

  window.modelCards = window.modelCards || {};
  window.modelCards.buildDownloadableModelCardHTML =
    buildDownloadableModelCardHTML;
  window.modelCards.buildSpecsRowsAvailable = buildSpecsRowsAvailable;
  window.modelCards.buildSpecsRowsRunning = buildSpecsRowsRunning;
  window.modelCards.buildSpecsRowsDownloadable = buildSpecsRowsDownloadable;
  window.modelCards.syncModelCardFromModel = syncModelCardFromModel;
  window.modelCards.syncModelCardCapabilitiesFromModel =
    syncModelCardCapabilitiesFromModel;
  window.modelCards.syncModelCardSpecsFromModel = syncModelCardSpecsFromModel;
  window.modelCards.modelTitleMarkup = modelTitleMarkup;
  window.modelCards.modelActionSettingsButtonInner =
    modelActionSettingsButtonInner;
  window.modelCards.parseModelTitleParts = parseModelTitleParts;
  window.modelCards.setupTitleMarquee = setupTitleMarquee;
  window.modelCards.setupAllTitleMarquees = setupAllTitleMarquees;
})();
