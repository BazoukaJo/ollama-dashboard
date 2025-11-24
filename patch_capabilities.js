// Add this after line 300 (after historical data storage comment)

// Capability detection helpers
function hasVisionCapability(model) {
  // Check if model name indicates vision support
  const visionModelNames = ['llava', 'bakllava', 'llava-llama3', 'llava-phi3', 'moondream'];
  const modelNameLower = (model.name || '').toLowerCase();

  // Check by name
  if (visionModelNames.some(name => modelNameLower.includes(name))) {
    return true;
  }

  // Check by families array for 'clip' or projector indicators
  if (model.details && model.details.families) {
    const families = Array.isArray(model.details.families)
      ? model.details.families
      : [model.details.families];
    return families.some(family =>
      family && (family.toLowerCase().includes('clip') || family.toLowerCase().includes('projector'))
    );
  }

  // Check by has_vision flag
  if (model.has_vision === true) {
    return true;
  }

  return false;
}

function getCapabilitiesHTML(model) {
  const hasVision = hasVisionCapability(model);

  return `
    <span class="capability-icon disabled" title="Reasoning: Not available">
      <i class="fas fa-brain"></i>
    </span>
    <span class="capability-icon ${hasVision ? 'enabled' : 'disabled'}" title="Image Processing: ${hasVision ? 'Available' : 'Not available'}">
      <i class="fas fa-image"></i>
    </span>
    <span class="capability-icon disabled" title="Tool Usage: Not available">
      <i class="fas fa-tools"></i>
    </span>
  `;
}

// USAGE: Replace the hardcoded capability spans with: ${getCapabilitiesHTML(model)}
// in both renderDownloadableModels and loadExtendedModels functions
