/**
 * Main JavaScript functionality for Ollama Dashboard
 */

// Timer and UI update functions
function updateTimes() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString(undefined, {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });

    const refreshIndicator = document.querySelector('.refresh-indicator');
    const tzAbbr = refreshIndicator ? refreshIndicator.dataset.timezone : '';
    const displayText = tzAbbr ? `${timeStr} ${tzAbbr}` : timeStr;

    document.getElementById('lastUpdate').textContent = displayText;

    let seconds = 30;
    const countdown = setInterval(() => {
        seconds--;
        document.getElementById('nextRefresh').textContent = seconds;
        if (seconds <= 0) clearInterval(countdown);
    }, 1000);
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggleButton = document.getElementById('toggleButton');
    sidebar.classList.toggle('show');
    toggleButton.innerHTML = sidebar.classList.contains('show') ? '✕' : '📋';
}

// Model management functions
async function startModel(modelName) {
    try {
        const response = await fetch(`/api/models/start/${encodeURIComponent(modelName)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        const result = await response.json();
        if (result.success) {
            showNotification(result.message, 'success');
            setTimeout(() => location.reload(), 2000);
        } else {
            showNotification(result.message, 'error');
        }
    } catch (error) {
        showNotification('Failed to start model: ' + error.message, 'error');
    }
}

async function stopModel(modelName) {
    const stopButton = event.target.closest('button');
    const originalText = stopButton.innerHTML;
    stopButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Stopping...';
    stopButton.disabled = true;

    try {
        showNotification(`Attempting to stop model ${modelName}...`, 'info');

        const response = await fetch(`/api/models/stop/${encodeURIComponent(modelName)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        const result = await response.json();

        if (result.success) {
            let notificationType = 'success';
            let message = result.message;

            if (result.force_killed) {
                notificationType = 'warning';
                message += ' ⚠️ Force kill was required - some data may have been lost.';
            }

            showNotification(message, notificationType);
            setTimeout(() => location.reload(), 3000);
        } else {
            showNotification(result.message, 'error');
        }
    } catch (error) {
        showNotification('Failed to stop model: ' + error.message, 'error');
    } finally {
        stopButton.innerHTML = originalText;
        stopButton.disabled = false;
    }
}

async function deleteModel(modelName) {
    if (!confirm(`Are you sure you want to delete the model "${modelName}"? This action cannot be undone.`)) {
        return;
    }

    const deleteButton = event.target.closest('button');
    const originalText = deleteButton.innerHTML;
    deleteButton.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Deleting...';
    deleteButton.disabled = true;

    try {
        showNotification(`Deleting model ${modelName}...`, 'info');

        const response = await fetch(`/api/models/delete/${encodeURIComponent(modelName)}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        const result = await response.json();

        if (result.success) {
            showNotification(result.message, 'success');
            setTimeout(() => location.reload(), 2000);
        } else {
            showNotification(result.message, 'error');
        }
    } catch (error) {
        showNotification('Failed to delete model: ' + error.message, 'error');
    } finally {
        deleteButton.innerHTML = originalText;
        deleteButton.disabled = false;
    }
}

async function showModelInfo(modelName) {
    try {
        const response = await fetch(`/api/models/info/${encodeURIComponent(modelName)}`);
        const info = await response.json();

        if (response.ok) {
            const modalHtml = `
                <div class="modal fade" id="modelInfoModal" tabindex="-1">
                    <div class="modal-dialog modal-xl">
                        <div class="modal-content" style="background: linear-gradient(135deg, #1a1a1a 0%, #1e1e1e 100%); color: #cccccc; border: 1px solid #3e3e42;">
                            <div class="modal-header" style="border-bottom: 1px solid #3e3e42;">
                                <h5 class="modal-title">Model Information: ${modelName}</h5>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body model-info-body">
                                <div class="table-scroll-wrapper">
                                    <div class="table-responsive">
                                        ${jsonToTable(info)}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            const modal = new bootstrap.Modal(document.getElementById('modelInfoModal'));
            modal.show();

            document.getElementById('modelInfoModal').addEventListener('hidden.bs.modal', function() {
                this.remove();
            });
        } else {
            showNotification('Failed to get model info: ' + info.error, 'error');
        }
    } catch (error) {
        showNotification('Failed to get model info: ' + error.message, 'error');
    }
}

function jsonToTable(json, level = 0) {
    if (json === null || json === undefined) {
        return '<span class="text-muted">null</span>';
    }

    if (typeof json === 'boolean') {
        return `<span class="text-primary">${json}</span>`;
    }

    if (typeof json === 'number') {
        return `<span class="text-success">${json}</span>`;
    }

    if (typeof json === 'string') {
        if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(json)) {
            return `<span class="text-info">${new Date(json).toLocaleString()}</span>`;
        }
        const maxLength = 100;
        if (json.length > maxLength) {
            const truncated = json.substring(0, maxLength);
            const escapedJson = json.replace(/"/g, '"').replace(/</g, '<').replace(/>/g, '>');
            return `<span class="text-warning" title="${escapedJson}">"${truncated}..."</span>`;
        }
        return `<span class="text-warning">"${json}"</span>`;
    }

    if (Array.isArray(json)) {
        if (json.length === 0) {
            return '<span class="text-muted">[]</span>';
        }

        let html = '<div class="array-container">';
        json.forEach((item, index) => {
            html += `<div class="array-item">
                <span class="array-index">[${index}]</span>
                ${jsonToTable(item, level + 1)}
            </div>`;
        });
        html += '</div>';
        return html;
    }

    if (typeof json === 'object') {
        const keys = Object.keys(json);
        if (keys.length === 0) {
            return '<span class="text-muted">{}</span>';
        }

        let html = '<table class="table table-dark table-sm json-table">';
        if (level === 0) {
            html += '<thead><tr><th>Property</th><th>Value</th></tr></thead>';
        }
        html += '<tbody>';

        keys.forEach(key => {
            const value = json[key];
            const formattedKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

            html += '<tr>';
            html += `<td class="json-key-cell" style="padding-left: ${level * 20}px"><strong>${formattedKey}</strong></td>`;
            html += '<td class="json-value-cell">';

            if (typeof value === 'object' && value !== null) {
                html += jsonToTable(value, level + 1);
            } else {
                html += jsonToTable(value, level);
            }

            html += '</td>';
            html += '</tr>';
        });

        html += '</tbody></table>';
        return html;
    }

    return String(json);
}

function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(notification);

    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// System stats update function
async function updateSystemStats() {
    try {
        const response = await fetch('/api/system/stats');
        const stats = await response.json();

        if (response.ok) {
            // Update percentages
            const cpuPercentEl = document.getElementById('cpuPercent');
            const memoryPercentEl = document.getElementById('memoryPercent');
            const vramPercentEl = document.getElementById('vramPercent');
            const diskPercentEl = document.getElementById('diskPercent');

            if (cpuPercentEl) cpuPercentEl.textContent = `${stats.cpu_percent.toFixed(1)}%`;
            if (memoryPercentEl) memoryPercentEl.textContent = `${stats.memory.percent.toFixed(1)}%`;
            if (vramPercentEl) vramPercentEl.textContent = stats.vram && stats.vram.total > 0 ? `${stats.vram.percent.toFixed(1)}%` : '--%';
            if (diskPercentEl) diskPercentEl.textContent = `${stats.disk.percent.toFixed(1)}%`;

            // Update progress bars
            const cpuBarEl = document.getElementById('cpuBar');
            const memoryBarEl = document.getElementById('memoryBar');
            const vramBarEl = document.getElementById('vramBar');
            const diskBarEl = document.getElementById('diskBar');

            if (cpuBarEl) cpuBarEl.style.width = `${stats.cpu_percent}%`;
            if (memoryBarEl) memoryBarEl.style.width = `${stats.memory.percent}%`;
            if (vramBarEl) vramBarEl.style.width = stats.vram && stats.vram.total > 0 ? `${stats.vram.percent}%` : '0%';
            if (diskBarEl) diskBarEl.style.width = `${stats.disk.percent}%`;

            // Update last update time
            const lastUpdateTimeEl = document.getElementById('lastUpdateTime');
            if (lastUpdateTimeEl) lastUpdateTimeEl.textContent = new Date().toLocaleTimeString();
        }
    } catch (error) {
        console.log('Failed to update system stats:', error);
    }
}

// Model data update function
async function updateModelData() {
    try {
        // Update running models
        const runningResponse = await fetch('/api/models/running');
        if (runningResponse.ok) {
            const runningModels = await runningResponse.json();
            updateRunningModelsDisplay(runningModels);
        }

        // Update available models (less frequently)
        const availableResponse = await fetch('/api/models/available');
        if (availableResponse.ok) {
            const availableModels = await availableResponse.json();
            updateAvailableModelsDisplay(availableModels.models || []);
        }

        // Update Ollama version
        const versionResponse = await fetch('/api/version');
        if (versionResponse.ok) {
            const versionData = await versionResponse.json();
            updateVersionDisplay(versionData.version || 'Unknown');
        }
    } catch (error) {
        console.log('Failed to update model data:', error);
    }
}

function updateRunningModelsDisplay(models) {
    const runningModelsContainer = document.getElementById('runningModelsContainer');
    if (!runningModelsContainer) return;

    // Only update if there are changes to avoid unnecessary DOM manipulation
    const currentCount = runningModelsContainer.querySelectorAll('.model-card').length;
    if (currentCount !== models.length) {
        // Models count changed, trigger a page reload to get fresh data
        location.reload();
        return;
    }

    // Update individual model cards with new data
    models.forEach((model, index) => {
        const modelCard = runningModelsContainer.querySelectorAll('.model-card')[index];
        if (modelCard) {
            // Update expiration time if it exists
            const expiresEl = modelCard.querySelector('.model-expires');
            if (expiresEl && model.expires_at) {
                expiresEl.textContent = model.expires_at.relative || model.expires_at.local || '';
            }

            // Update size if it changed
            const sizeEl = modelCard.querySelector('.model-size');
            if (sizeEl && model.formatted_size) {
                sizeEl.textContent = model.formatted_size;
            }
        }
    });
}

function updateAvailableModelsDisplay(models) {
    const availableModelsContainer = document.getElementById('availableModelsContainer');
    if (!availableModelsContainer) return;

    // Update the count display
    const countEl = document.getElementById('availableModelsCount');
    if (countEl) {
        countEl.textContent = models.length;
    }
}

function updateVersionDisplay(version) {
    const versionEl = document.getElementById('ollamaVersion');
    if (versionEl) {
        versionEl.textContent = version;
    }
}

// Service management functions
async function startOllamaService() {
    const startBtn = document.getElementById('startServiceBtn');
    const originalText = startBtn.innerHTML;
    startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    startBtn.disabled = true;

    try {
        const response = await fetch('/api/service/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        const result = await response.json();

        if (result.success) {
            showNotification(result.message, 'success');
            setTimeout(() => location.reload(), 3000);
        } else {
            showNotification(result.message, 'error');
            startBtn.disabled = false;
        }
    } catch (error) {
        showNotification('Failed to start service: ' + error.message, 'error');
        startBtn.disabled = false;
    } finally {
        startBtn.innerHTML = originalText;
    }
}

async function stopOllamaService() {
    const stopBtn = document.getElementById('stopServiceBtn');
    const originalText = stopBtn.innerHTML;
    stopBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    stopBtn.disabled = true;

    try {
        const response = await fetch('/api/service/stop', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        const result = await response.json();

        if (result.success) {
            showNotification(result.message, 'success');
            setTimeout(() => location.reload(), 3000);
        } else {
            showNotification(result.message, 'error');
            stopBtn.disabled = false;
        }
    } catch (error) {
        showNotification('Failed to stop service: ' + error.message, 'error');
        stopBtn.disabled = false;
    } finally {
        stopBtn.innerHTML = originalText;
    }
}

async function restartOllamaService() {
    const restartBtn = document.getElementById('restartServiceBtn');
    const originalText = restartBtn.innerHTML;
    restartBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    restartBtn.disabled = true;

    try {
        const response = await fetch('/api/service/restart', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });
        const result = await response.json();

        if (result.success) {
            showNotification(result.message, 'success');
            setTimeout(() => location.reload(), 5000);
        } else {
            showNotification(result.message, 'error');
            restartBtn.disabled = false;
        }
    } catch (error) {
        showNotification('Failed to restart service: ' + error.message, 'error');
        restartBtn.disabled = false;
    } finally {
        restartBtn.innerHTML = originalText;
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    updateTimes();
    updateSystemStats();
    updateModelData();

    // Update system stats every 2 seconds
    setInterval(updateSystemStats, 2000);

    // Update model data every 10 seconds
    setInterval(updateModelData, 10000);
});
