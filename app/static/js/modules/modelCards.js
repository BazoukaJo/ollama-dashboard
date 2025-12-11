// Ensure getCapabilitiesHTML is available globally
if (!window.getCapabilitiesHTML) {
    window.getCapabilitiesHTML = function(model) {
        const hasReasoning = model.has_reasoning || false;
        const hasVision = model.has_vision || false;
        const hasTools = model.has_tools || false;
        return `
            <span class="capability-icon ${hasReasoning ? 'enabled' : 'disabled'}" title="Reasoning: ${hasReasoning ? 'Available' : 'Not available'}">
                <i class="fas fa-brain"></i>
            </span>
            <span class="capability-icon ${hasVision ? 'enabled' : 'disabled'}" title="Image Processing: ${hasVision ? 'Available' : 'Not available'}">
                <i class="fas fa-image"></i>
            </span>
            <span class="capability-icon ${hasTools ? 'enabled' : 'disabled'}" title="Tool Usage: ${hasTools ? 'Available' : 'Not available'}">
                <i class="fas fa-tools"></i>
            </span>
        `;
    };
}
(function(){
    const escapeHtml = window.escapeHtml || (s => s);
    const getCapabilitiesHTML = window.getCapabilitiesHTML;
    function buildDownloadableModelCardHTML(model){
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
                <div class="model-title">${escapeHtml(model.name) || 'Unknown'}</div>
                <div class="model-capabilities">${getCapabilitiesHTML(model)}</div>
                <div class="model-specs">
                  <div class="spec-row compact-hide">
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-cogs"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">Family</div>
                                <div class="spec-value">${model.family || 'Unknown'}</div>
                            </div>
                        </div>
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-weight"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">Parameters</div>
                                <div class="spec-value">${model.parameter_size || 'Unknown'}</div>
                            </div>
                        </div>
                    </div>
                  <div class="spec-row compact-hide">
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-hdd"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">Size</div>
                                <div class="spec-value">${model.size || 'Unknown'}</div>
                            </div>
                        </div>
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-memory"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">System RAM</div>
                                <div class="spec-value" id="downloadable-ram-${escapeHtml(model.name).replace(/[^a-zA-Z0-9]/g, '-')}">Loading...</div>
                            </div>
                        </div>
                    </div>
                    <!-- System VRAM capacity (hidden in compact mode) -->
                    <div class="spec-row compact-hide" title="System-wide capacities (not per model)">
                        <div class="spec-item">
                            <div class="spec-icon">
                                <i class="fas fa-palette"></i>
                            </div>
                            <div class="spec-content">
                                <div class="spec-label">System VRAM</div>
                                <div class="spec-value" id="downloadable-vram-${escapeHtml(model.name).replace(/[^a-zA-Z0-9]/g, '-')}">Loading...</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="download-progress" style="display: none; margin-bottom: 0.5rem;">
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
  window.modelCards.buildDownloadableModelCardHTML = buildDownloadableModelCardHTML;
})();
