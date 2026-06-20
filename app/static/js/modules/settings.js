(function(){
  function escapeHtml(str) {
    if (!str && str !== 0) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  async function openModelSettingsModal(modelName){
    try {
      const resp = await fetch('/api/models/settings?model=' + encodeURIComponent(modelName));
      const gr = await readApiJson(resp);
      if (!gr.responseOk) {
        throw new Error(gr.message || `HTTP ${gr.status}`);
      }
      const data = gr.data;
      const settings = data.settings || {};
      const client = data.client || data.copilot || {};
      const modalHtml = `
      <div class="modal fade" id="modelSettingsModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered modal-md">
          <div class="modal-content bg-dark text-light">
            <div class="modal-header">
              <h5 class="modal-title">Model Settings: ${escapeHtml(modelName)}</h5>
              <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <form id="modelSettingsForm">
                <div class="mb-3">
                  <label class="form-label">Temperature</label>
                  <input type="number" step="0.01" min="0" max="1" class="form-control" id="ms-temperature" value="${settings.temperature ?? 0.75}">
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
                  <input type="number" class="form-control" id="ms-num-ctx" value="${settings.num_ctx ?? 4096}">
                </div>
                <div class="mb-3">
                  <label class="form-label">External client system prompt</label>
                  <select class="form-select" id="ms-client-preset">
                    <option value="none" ${(client.system_prompt_preset||'none')==='none'?'selected':''}>None</option>
                    <option value="coding_assistant" ${client.system_prompt_preset==='coding_assistant'?'selected':''}>Coding assistant</option>
                    <option value="explain_only" ${client.system_prompt_preset==='explain_only'?'selected':''}>Explain only</option>
                    <option value="test_writer" ${client.system_prompt_preset==='test_writer'?'selected':''}>Test writer</option>
                    <option value="reviewer" ${client.system_prompt_preset==='reviewer'?'selected':''}>Code reviewer</option>
                  </select>
                  <div class="form-text text-muted">Injected for apps using the <code>/ollama</code> API proxy (OpenAI / Ollama-compatible clients).</div>
                </div>
                <div class="mb-3">
                  <label class="form-label">Custom system prompt (optional)</label>
                  <textarea class="form-control" id="ms-client-custom" rows="2">${escapeHtml(client.system_prompt_custom||'')}</textarea>
                </div>
                <div class="form-check mb-3">
                  <input class="form-check-input" type="checkbox" id="ms-client-trim" ${client.context_trim_enabled !== false ? 'checked' : ''}>
                  <label class="form-check-label" for="ms-client-trim">Auto-trim long prompts to fit context (proxy)</label>
                </div>
                <div class="mb-3">
                  <label class="form-label">Reasoning for external clients (Copilot)</label>
                  <select class="form-select" id="ms-client-think">
                    <option value="off" ${(client.copilot_think||'off')==='off'?'selected':''}>Off — fast, direct answers (recommended)</option>
                    <option value="auto" ${client.copilot_think==='auto'?'selected':''}>Auto — follow the client's reasoning request</option>
                    <option value="on" ${client.copilot_think==='on'?'selected':''}>On — always think (reasoning shown in the reply)</option>
                  </select>
                  <div class="form-text text-muted">For thinking models (gemma4, qwen3) via the <code>/ollama</code> proxy. <strong>On</strong> streams the model's reasoning into the visible answer since Copilot only renders content; tool/agent turns always run without thinking.</div>
                </div>
                <div class="mb-3">
                  <label class="form-label">Seed</label>
                  <input type="number" class="form-control" id="ms-seed" value="${settings.seed ?? 0}">
                </div>
                <hr />
                <button type="button" class="btn btn-sm btn-outline-info mb-2" id="ms-toggle-advanced"><i class="fas fa-sliders-h me-1"></i> Advanced Settings</button>
                <div id="ms-advanced" style="display:none;">
                  <div class="row g-2">
                    ${buildAdvancedField('Num Predict','ms-num-predict', settings.num_predict ?? 512,'number',{min:1})}
                    ${buildAdvancedField('Repeat Last N','ms-repeat-last-n', settings.repeat_last_n ?? 64,'number',{min:0})}
                    ${buildAdvancedField('Repeat Penalty','ms-repeat-penalty', settings.repeat_penalty ?? 1.05,'number',{step:0.01})}
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
                <div class="mt-2 p-2 rounded small" style="border:1px solid #495057;background:rgba(255,255,255,0.04)">
                  <div class="fw-semibold text-secondary mb-2" style="font-size:0.78em;letter-spacing:.03em;text-transform:uppercase">Where these settings apply</div>
                  <div class="d-flex align-items-start gap-2 mb-1">
                    <span class="badge bg-success flex-shrink-0" style="min-width:5em;text-align:center">Dashboard</span>
                    <span class="text-muted">Chat, warm-load, and restart from this UI — applied automatically on every request.</span>
                  </div>
                  <div class="d-flex align-items-start gap-2 mb-1">
                    <span class="badge bg-info text-dark flex-shrink-0" style="min-width:5em;text-align:center">Proxy</span>
                    <span class="text-muted">External apps at <code>:5000/ollama</code> — VS Code, Claude Code, Continue, OpenAI SDKs. Saved settings merge on each request.</span>
                  </div>
                  <div class="d-flex align-items-start gap-2">
                    <span class="badge bg-warning text-dark flex-shrink-0" style="min-width:5em;text-align:center">Baked</span>
                    <span class="text-muted">Any client, no proxy needed — click <strong>Bake into Model</strong> to create <code>${modelName}-dashboard</code> with these values in its Modelfile. Works without the dashboard running.</span>
                  </div>
                </div>
              </form>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-danger" id="ms-delete">Delete Custom</button>
              <button type="button" class="btn btn-secondary" id="ms-recommend">Reset to Recommended</button>
              <button type="button" class="btn btn-outline-primary" id="ms-apply-recommended">Apply Recommended</button>
              <button type="button" class="btn btn-outline-warning" id="ms-bake" data-dashboard-tooltip="Create a derived Ollama model (e.g. mymodel-dashboard) with these settings baked in as Modelfile PARAMETER directives, so external clients get them too.">Bake into Model</button>
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
      document.getElementById('ms-bake').onclick = async ()=>{
        if(!confirm(`This will save your current settings, then ask Ollama to create a derived model from "${modelName}" with these values baked in. Continue?`)) return;
        try {
          await submitModelSettings(modelName, collectSettingsPayload());
          const r = await fetch('/api/models/settings/' + encodeURIComponent(modelName) + '/bake', {method:'POST'});
          const jr = await readApiJson(r);
          if(!jr.responseOk || !jr.data.success){ window.showNotification(jr.data?.message || jr.message || 'Failed to bake settings into model','error'); return; }
          window.showNotification(jr.data.message,'success');
        } catch(err){ window.showNotification('Failed: '+err.message,'error'); }
      };
      document.getElementById('ms-apply-recommended').onclick = async ()=>{
        try {
          const r = await fetch('/api/models/settings/reset?model=' + encodeURIComponent(modelName),{method:'POST'});
          const jr = await readApiJson(r);
          if(!jr.responseOk){ window.showNotification(jr.message || 'Failed to apply recommended','error'); return; }
          if(jr.data.success){ window.showNotification(jr.data.message,'success'); modal.hide(); }
          else { window.showNotification(jr.data.message || 'Failed to apply recommended','error'); }
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
    const safeFloat = (el, defaultVal) => {
      const el2 = typeof el === 'string' ? g(el) : el;
      if (!el2 || !el2.value) return defaultVal;
      const v = parseFloat(el2.value);
      return Number.isFinite(v) ? v : defaultVal;
    };
    const safeInt = (el, defaultVal) => {
      const el2 = typeof el === 'string' ? g(el) : el;
      if (!el2 || !el2.value) return defaultVal;
      const v = parseInt(el2.value, 10);
      return Number.isFinite(v) ? v : defaultVal;
    };
    const stopEl = g('ms-stop');
    const stopRaw = stopEl && stopEl.value ? stopEl.value.trim() : '';
    const stopArr = !stopRaw ? [] : stopRaw.split(',').map(s=>s.trim()).filter(s=>s).slice(0,10);
    const penalizeEl = g('ms-penalize-newline');
    const presetEl = g('ms-client-preset');
    const customEl = g('ms-client-custom');
    const trimEl = g('ms-client-trim');
    const thinkEl = g('ms-client-think');
    return {
      temperature: safeFloat('ms-temperature', 0.75),
      top_k: safeInt('ms-top-k', 40),
      top_p: safeFloat('ms-top-p', 0.9),
      num_ctx: safeInt('ms-num-ctx', 4096),
      seed: safeInt('ms-seed', 0),
      num_predict: safeInt('ms-num-predict', 512),
      repeat_last_n: safeInt('ms-repeat-last-n', 64),
      repeat_penalty: safeFloat('ms-repeat-penalty', 1.05),
      presence_penalty: safeFloat('ms-presence-penalty', 0),
      frequency_penalty: safeFloat('ms-frequency-penalty', 0),
      min_p: safeFloat('ms-min-p', 0.05),
      typical_p: safeFloat('ms-typical-p', 1),
      mirostat: safeInt('ms-mirostat', 0),
      mirostat_tau: safeFloat('ms-mirostat-tau', 5),
      mirostat_eta: safeFloat('ms-mirostat-eta', 0.1),
      penalize_newline: penalizeEl ? !!penalizeEl.checked : false,
      stop: stopArr,
      client: {
        system_prompt_preset: presetEl ? presetEl.value : 'none',
        system_prompt_custom: customEl ? customEl.value.trim() : '',
        context_trim_enabled: trimEl ? !!trimEl.checked : true,
        copilot_think: thinkEl ? thinkEl.value : 'off',
      },
    };
  }

  async function submitModelSettings(modelName,payload){
    try {
      const r = await fetch('/api/models/settings?model=' + encodeURIComponent(modelName),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const sr = await readApiJson(r);
      if(!sr.responseOk){ window.showNotification(sr.message || 'Failed to save settings','error'); return; }
      const data = sr.data;
      if(data.success) {
        window.showNotification(data.message,'success');
        if (typeof updateModelData === 'function') void updateModelData();
      }
      else window.showNotification(data.message || 'Failed to save settings','error');
    } catch(err){ window.showNotification('Failed to save settings: '+err.message,'error'); }
  }

  async function deleteModelSettings(modelName){
    try {
      const r = await fetch('/api/models/settings?model=' + encodeURIComponent(modelName),{method:'DELETE'});
      const dr = await readApiJson(r);
      if(!dr.responseOk){ window.showNotification(dr.message || 'Failed to delete settings','error'); return; }
      const data = dr.data;
      if(data.success) {
        window.showNotification(data.message,'success');
        if (typeof updateModelData === 'function') void updateModelData();
      }
      else window.showNotification(data.message || 'Failed to delete settings','error');
    } catch(err){ window.showNotification('Failed to delete settings: '+err.message,'error'); }
  }

  async function loadRecommendedIntoForm(modelName){
    try {
      const r = await fetch('/api/models/settings/recommended?model=' + encodeURIComponent(modelName));
      const rr = await readApiJson(r);
      if(!rr.responseOk){ window.showNotification(rr.message || 'Failed to load recommended','error'); return; }
      const dataRec = rr.data; const s = dataRec.settings || {}; const set=(id,val)=>{ const el=document.getElementById(id); if(el) el.value=val; };
      set('ms-temperature', s.temperature ?? 0.75); set('ms-top-k', s.top_k ?? 40); set('ms-top-p', s.top_p ?? 0.9); set('ms-num-ctx', s.num_ctx ?? 4096); set('ms-seed', s.seed ?? 0);
      set('ms-num-predict', s.num_predict ?? 512); set('ms-repeat-last-n', s.repeat_last_n ?? 64); set('ms-repeat-penalty', s.repeat_penalty ?? 1.05);
      set('ms-presence-penalty', s.presence_penalty ?? 0.0); set('ms-frequency-penalty', s.frequency_penalty ?? 0.0); set('ms-min-p', s.min_p ?? 0.05); set('ms-typical-p', s.typical_p ?? 1.0);
      set('ms-mirostat', s.mirostat ?? 0); set('ms-mirostat-tau', s.mirostat_tau ?? 5.0); set('ms-mirostat-eta', s.mirostat_eta ?? 0.1);
      const stopEl = document.getElementById('ms-stop'); if(stopEl) stopEl.value = (s.stop && Array.isArray(s.stop)) ? s.stop.join(',') : '';
      const pn = document.getElementById('ms-penalize-newline'); if(pn) pn.checked = !!s.penalize_newline;
    } catch(err){ window.showNotification('Failed to load recommended settings: '+err.message,'error'); }
  }

  window.modelSettings = { openModelSettingsModal, submitModelSettings, deleteModelSettings };
  window.openModelSettingsModal = openModelSettingsModal; // maintain legacy global for inline onclick.
})();