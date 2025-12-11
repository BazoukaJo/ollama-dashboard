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
                    </div>
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
