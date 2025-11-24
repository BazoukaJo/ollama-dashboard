(function(){
  async function openModelSettingsModal(modelName){
    try {
      const resp = await fetch(`/api/models/settings/${encodeURIComponent(modelName)}`);
      const data = await resp.json();
      const settings = data.settings || {};
      const modalHtml = `
      <div class="modal fade" id="modelSettingsModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered modal-md">
          <div class="modal-content bg-dark text-light">
            <div class="modal-header">
              <h5 class="modal-title">Model Settings: ${modelName}</h5>
              <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <form id="modelSettingsForm">
                <div class="mb-3">
                  <label class="form-label">Temperature</label>
                  <input type="number" step="0.01" min="0" max="1" class="form-control" id="ms-temperature" value="${settings.temperature ?? 0.7}">
                </div>
                <div class="mb-3">
                  <label class="form-label">Top K</label>
                  <input type="number" class="form-control" id="ms-top-k" value="${settings.top_k ?? 40}">
                </div>
                <div class="mb-3">
                  <label class="form-label">Top P</label>
                  <input type="number" step="0.01" min="0" max="1" class="form-control" id="ms-top-p" value="${settings.top_p ?? 0.9}">
                </div>
                <div class="mb-3">
                  <label class="form-label">Context (num_ctx)</label>
                  <input type="number" class="form-control" id="ms-num-ctx" value="${settings.num_ctx ?? 2048}">
                </div>
                <div class="mb-3">
                  <label class="form-label">Seed</label>
                  <input type="number" class="form-control" id="ms-seed" value="${settings.seed ?? 0}">
                </div>
                <hr />
                <button type="button" class="btn btn-sm btn-outline-info mb-2" id="ms-toggle-advanced"><i class="fas fa-sliders-h me-1"></i> Advanced Settings</button>
                <div id="ms-advanced" style="display:none;">
                  <div class="row g-2">
                    ${buildAdvancedField('Num Predict','ms-num-predict', settings.num_predict ?? 256,'number',{min:1})}
                    ${buildAdvancedField('Repeat Last N','ms-repeat-last-n', settings.repeat_last_n ?? 64,'number',{min:0})}
                    ${buildAdvancedField('Repeat Penalty','ms-repeat-penalty', settings.repeat_penalty ?? 1.1,'number',{step:0.01})}
                    ${buildAdvancedField('Presence Penalty','ms-presence-penalty', settings.presence_penalty ?? 0.0,'number',{step:0.01})}
                    ${buildAdvancedField('Frequency Penalty','ms-frequency-penalty', settings.frequency_penalty ?? 0.0,'number',{step:0.01})}
                    ${buildAdvancedField('Min P','ms-min-p', settings.min_p ?? 0.05,'number',{step:0.01})}
                    ${buildAdvancedField('Typical P','ms-typical-p', settings.typical_p ?? 1.0,'number',{step:0.01})}
                    ${buildAdvancedField('Mirostat Mode','ms-mirostat', settings.mirostat ?? 0,'number',{min:0,max:2})}
                    ${buildAdvancedField('Mirostat Tau','ms-mirostat-tau', settings.mirostat_tau ?? 5.0,'number',{step:0.1})}
                    ${buildAdvancedField('Mirostat Eta','ms-mirostat-eta', settings.mirostat_eta ?? 0.1,'number',{step:0.01})}
                    <div class="col-6 d-flex align-items-center mt-3">
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="ms-penalize-newline" ${settings.penalize_newline ? 'checked' : ''}>
                        <label class="form-check-label" for="ms-penalize-newline">Penalize Newline</label>
                      </div>
                    </div>
                    <div class="col-12">
                      <label class="form-label">Stop Sequences (comma separated)</label>
                      <input type="text" class="form-control" id="ms-stop" value="${(settings.stop && Array.isArray(settings.stop) ? settings.stop.join(',') : '')}">
                    </div>
                  </div>
                  <div class="form-text text-muted mt-2">Advanced parameters fine-tune sampling and penalties. Leave defaults if unsure.</div>
                </div>
                <div class="form-text text-muted">Recommended values are shown when not overridden; saving persists this model's defaults.</div>
              </form>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-danger" id="ms-delete">Delete Custom</button>
              <button type="button" class="btn btn-secondary" id="ms-recommend">Reset to Recommended</button>
              <button type="button" class="btn btn-outline-primary" id="ms-apply-recommended">Apply Recommended</button>
              <button type="button" class="btn btn-primary" id="ms-save">Save</button>
            </div>
          </div>
        </div>
      </div>`;
      document.body.insertAdjacentHTML('beforeend', modalHtml);
      const modalEl = document.getElementById('modelSettingsModal');
      const modal = new bootstrap.Modal(modalEl); modal.show();
      document.getElementById('ms-toggle-advanced').onclick = ()=>{
        const adv = document.getElementById('ms-advanced');
        adv.style.display = adv.style.display === 'none' ? 'block' : 'none';
      };
      document.getElementById('ms-save').onclick = async ()=>{
        const payload = collectSettingsPayload();
        await submitModelSettings(modelName, payload);
        modal.hide();
      };
      document.getElementById('ms-delete').onclick = async ()=>{
        if(!confirm('Remove custom settings for this model?')) return;
        await deleteModelSettings(modelName); modal.hide();
      };
      document.getElementById('ms-recommend').onclick = ()=>loadRecommendedIntoForm(modelName);
      document.getElementById('ms-apply-recommended').onclick = async ()=>{
        try {
          const r = await fetch(`/api/models/settings/${encodeURIComponent(modelName)}/reset`,{method:'POST'});
          const jr = await r.json();
          if(jr.success){ window.showNotification(jr.message,'success'); modal.hide(); }
          else { window.showNotification(jr.message || 'Failed to apply recommended','error'); }
        } catch(err){ window.showNotification('Failed: '+err.message,'error'); }
      };
      modalEl.addEventListener('hidden.bs.modal',()=>{ modalEl.remove(); setTimeout(()=>location.reload(),500); });
    } catch(err){ window.showNotification('Failed to open settings: '+err.message,'error'); }
  }

  function buildAdvancedField(label,id,val,type,attrs){
    const attrStr = Object.entries(attrs||{}).map(([k,v])=>`${k}="${v}"`).join(' ');
    return `<div class="col-6"><label class="form-label">${label}</label><input type="${type}" class="form-control" id="${id}" value="${val}" ${attrStr}></div>`;
  }

  function collectSettingsPayload(){
    const g = id=>document.getElementById(id);
    return {
      temperature: parseFloat(g('ms-temperature').value),
      top_k: parseInt(g('ms-top-k').value),
      top_p: parseFloat(g('ms-top-p').value),
      num_ctx: parseInt(g('ms-num-ctx').value),
      seed: parseInt(g('ms-seed').value),
      num_predict: parseInt(g('ms-num-predict').value),
      repeat_last_n: parseInt(g('ms-repeat-last-n').value),
      repeat_penalty: parseFloat(g('ms-repeat-penalty').value),
      presence_penalty: parseFloat(g('ms-presence-penalty').value),
      frequency_penalty: parseFloat(g('ms-frequency-penalty').value),
      min_p: parseFloat(g('ms-min-p').value),
      typical_p: parseFloat(g('ms-typical-p').value),
      mirostat: parseInt(g('ms-mirostat').value),
      mirostat_tau: parseFloat(g('ms-mirostat-tau').value),
      mirostat_eta: parseFloat(g('ms-mirostat-eta').value),
      penalize_newline: g('ms-penalize-newline').checked,
      stop: (function(){ const raw = g('ms-stop').value.trim(); if(!raw) return []; return raw.split(',').map(s=>s.trim()).filter(s=>s).slice(0,10); })()
    };
  }

  async function submitModelSettings(modelName,payload){
    try {
      const r = await fetch(`/api/models/settings/${encodeURIComponent(modelName)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const data = await r.json();
      if(data.success) window.showNotification(data.message,'success');
      else window.showNotification(data.message || 'Failed to save settings','error');
    } catch(err){ window.showNotification('Failed to save settings: '+err.message,'error'); }
  }

  async function deleteModelSettings(modelName){
    try {
      const r = await fetch(`/api/models/settings/${encodeURIComponent(modelName)}`,{method:'DELETE'});
      const data = await r.json();
      if(data.success) window.showNotification(data.message,'success');
      else window.showNotification(data.message || 'Failed to delete settings','error');
    } catch(err){ window.showNotification('Failed to delete settings: '+err.message,'error'); }
  }

  async function loadRecommendedIntoForm(modelName){
    try {
      const r = await fetch(`/api/models/settings/recommended/${encodeURIComponent(modelName)}`);
      const dataRec = await r.json(); const s = dataRec.settings || {}; const set=(id,val)=>{ const el=document.getElementById(id); if(el) el.value=val; };
      set('ms-temperature', s.temperature ?? 0.7); set('ms-top-k', s.top_k ?? 40); set('ms-top-p', s.top_p ?? 0.9); set('ms-num-ctx', s.num_ctx ?? 2048); set('ms-seed', s.seed ?? 0);
      set('ms-num-predict', s.num_predict ?? 256); set('ms-repeat-last-n', s.repeat_last_n ?? 64); set('ms-repeat-penalty', s.repeat_penalty ?? 1.1);
      set('ms-presence-penalty', s.presence_penalty ?? 0.0); set('ms-frequency-penalty', s.frequency_penalty ?? 0.0); set('ms-min-p', s.min_p ?? 0.05); set('ms-typical-p', s.typical_p ?? 1.0);
      set('ms-mirostat', s.mirostat ?? 0); set('ms-mirostat-tau', s.mirostat_tau ?? 5.0); set('ms-mirostat-eta', s.mirostat_eta ?? 0.1);
      const stopEl = document.getElementById('ms-stop'); if(stopEl) stopEl.value = (s.stop && Array.isArray(s.stop)) ? s.stop.join(',') : '';
      const pn = document.getElementById('ms-penalize-newline'); if(pn) pn.checked = !!s.penalize_newline;
    } catch(err){ window.showNotification('Failed to load recommended settings: '+err.message,'error'); }
  }

  window.modelSettings = { openModelSettingsModal, submitModelSettings, deleteModelSettings };
  window.openModelSettingsModal = openModelSettingsModal; // maintain legacy global for inline onclick.
})();