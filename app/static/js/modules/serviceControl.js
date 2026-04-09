(function(){
  function updateServiceControlButtons(isRunning){
    const startBtn = document.getElementById('startServiceBtn');
    const stopBtn = document.getElementById('stopServiceBtn');
    const restartBtn = document.getElementById('restartServiceBtn');
    // Play/start button should be disabled when running
    if (startBtn){
      startBtn.disabled = !!isRunning;
      startBtn.classList.remove('btn-success','btn-outline-success');
      startBtn.classList.add(isRunning ? 'btn-outline-success' : 'btn-success');
    }
    // Stop/restart buttons enabled only when running
    if (stopBtn){
      stopBtn.disabled = !isRunning;
      stopBtn.classList.remove('btn-danger','btn-secondary');
      stopBtn.classList.add(isRunning ? 'btn-danger' : 'btn-secondary');
    }
    if (restartBtn){
      restartBtn.disabled = !isRunning;
      restartBtn.classList.remove('btn-warning','btn-outline-warning');
      restartBtn.classList.add(isRunning ? 'btn-warning' : 'btn-outline-warning');
    }
  }

  async function updateHealthStatus(){
    try {
      const response = await fetch('/api/health');
      const hr = await readApiJson(response);
      const health = hr.responseOk && hr.data ? hr.data : { status: 'unhealthy', error: hr.message || 'Invalid response' };
      const healthBadge = document.getElementById('healthStatus');
      const healthText = document.getElementById('healthText');
      if(!healthBadge || !healthText) return;
      const clearInlineSizing = () => {
        healthBadge.style.padding = '';
        healthBadge.style.fontSize = '';
      };
      if (health.status === 'healthy') {
        healthBadge.className = 'badge bg-success health-status-badge dashboard-header-health';
        clearInlineSizing();
        const uptimeMin = Math.floor((health.uptime_seconds || 0) / 60);
        const uptimeHr = Math.floor(uptimeMin / 60);
        const uptimeDisplay =
          uptimeHr > 0 ? `${uptimeHr}h ${uptimeMin % 60}m` : `${uptimeMin}m`;
        healthText.textContent = `Healthy • Uptime: ${uptimeDisplay}`;
        updateServiceControlButtons(true);
      } else if (health.status === 'degraded') {
        healthBadge.className = 'badge bg-warning health-status-badge dashboard-header-health';
        clearInlineSizing();
        healthText.textContent = 'Degraded • Ollama service not running';
        updateServiceControlButtons(false);
      } else {
        healthBadge.className = 'badge bg-danger health-status-badge dashboard-header-health';
        clearInlineSizing();
        healthText.textContent = 'Unhealthy • ' + (health.error || 'Unknown error');
        updateServiceControlButtons(false);
      }
    } catch(err){
      const healthBadge = document.getElementById('healthStatus');
      const healthText = document.getElementById('healthText');
      if (healthBadge && healthText) {
        healthBadge.className =
          'badge bg-danger health-status-badge dashboard-header-health';
        healthBadge.style.padding = '';
        healthBadge.style.fontSize = '';
        healthText.textContent = 'Health check failed';
        updateServiceControlButtons(false);
      }
    }
  }

  async function startOllamaService(){
    const btn = document.getElementById('startServiceBtn');
    const original = btn?btn.innerHTML:null;
    if(btn){ btn.innerHTML='<i class="fas fa-spinner fa-spin"></i>'; btn.disabled=true; }
    try {
      const resp = await fetch('/api/service/start',{method:'POST',headers:{'Content-Type':'application/json'}});
      const sr = await readApiJson(resp);
      if(!sr.responseOk){
        window.showNotification(sr.message || ('Failed to start service: HTTP '+resp.status),'error');
        if(btn) btn.disabled=false;
        return;
      }
      const data = sr.data;
      if(data.success){ 
        window.showNotification(data.message,'success'); 
        // Update health status and reload after delay
        setTimeout(()=>{ updateHealthStatus(); setTimeout(()=>location.reload(),2000); },2000);
      }
      else { 
        window.showNotification(data.message || 'Failed to start service','error'); 
        if(btn) btn.disabled=false; 
      }
    } catch(e){ 
      window.showNotification('Failed to start service: '+(e.message || 'Network error'),'error'); 
      if(btn) btn.disabled=false; 
    }
    finally { if(btn && original!==null) btn.innerHTML=original; }
  }

  async function stopOllamaService(){
    const btn = document.getElementById('stopServiceBtn');
    const original = btn?btn.innerHTML:null;
    if(btn){ btn.innerHTML='<i class="fas fa-spinner fa-spin"></i>'; btn.disabled=true; }
    try {
      const resp = await fetch('/api/service/stop',{method:'POST',headers:{'Content-Type':'application/json'}});
      const sr = await readApiJson(resp);
      if(!sr.responseOk){
        window.showNotification(sr.message || ('Failed to stop service: HTTP '+resp.status),'error');
        if(btn) btn.disabled=false;
        return;
      }
      const data = sr.data;
      if(data.success){ 
        window.showNotification(data.message,'success'); 
        setTimeout(()=>{ updateHealthStatus(); setTimeout(()=>location.reload(),2000); },2000);
      }
      else { 
        window.showNotification(data.message || 'Failed to stop service','error'); 
        if(btn) btn.disabled=false; 
      }
    } catch(e){ 
      window.showNotification('Failed to stop service: '+(e.message || 'Network error'),'error'); 
      if(btn) btn.disabled=false; 
    }
    finally { if(btn && original!==null) btn.innerHTML=original; }
  }

  async function restartOllamaService(){
    const btn = document.getElementById('restartServiceBtn');
    const original = btn?btn.innerHTML:null;
    if(btn){ btn.innerHTML='<i class="fas fa-spinner fa-spin"></i>'; btn.disabled=true; }
    try {
      // Only restart Ollama service, not the whole app
      let resp = await fetch('/api/service/restart',{method:'POST',headers:{'Content-Type':'application/json'}});
      const rr = await readApiJson(resp);
      if(!rr.responseOk){
        window.showNotification(rr.message || 'Failed to restart service','error');
        if(btn) btn.disabled=false;
        return;
      }
      const data = rr.data;
      if(data.success){
        window.showNotification(data.message,'success');
        // Poll health until healthy or timeout then reload
        const startTime = Date.now();
        const poll = async () => {
          if(Date.now() - startTime > 30000){ location.reload(); return; }
          try {
            const h = await fetch('/api/health');
            const hj = await readApiJson(h);
            if(hj.responseOk && hj.data && hj.data.status === 'healthy'){ location.reload(); return; }
          } catch(_){}
          setTimeout(poll, 1000);
        };
        setTimeout(poll, 1500); // small delay before polling starts
      }
      else { window.showNotification(data.message,'error'); if(btn) btn.disabled=false; }
    } catch(e){ window.showNotification('Failed to restart service: '+e.message,'error'); if(btn) btn.disabled=false; }
    finally { if(btn && original!==null) btn.innerHTML=original; }
  }

  function showRestartConfirm(){
    const confirmBtn = document.getElementById('confirmRestartBtn');
    if(!confirmBtn){ restartOllamaService(); return; }
    const handler = async () => {
      confirmBtn.disabled = true;
      await restartOllamaService();
      const modalEl = document.getElementById('restartConfirmModal');
      const m = bootstrap.Modal.getInstance(modalEl);
      if(m) m.hide();
      confirmBtn.disabled = false;
      confirmBtn.removeEventListener('click', handler);
    };
    confirmBtn.addEventListener('click', handler);
    const modal = new bootstrap.Modal(document.getElementById('restartConfirmModal'));
    modal.show();
  }

  const UPDATE_FETCH_MS = 900000; // 15 minutes (winget/install script can be slow)

  async function updateOllamaService(){
    const btn = document.getElementById('updateOllamaBtn');
    const original = btn ? btn.innerHTML : null;
    if(btn){ btn.innerHTML='<i class="fas fa-spinner fa-spin"></i>'; btn.disabled=true; }
    const ctrl = new AbortController();
    const timer = setTimeout(function(){ ctrl.abort(); }, UPDATE_FETCH_MS);
    try {
      const resp = await fetch('/api/service/update-ollama', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      const ur = await readApiJson(resp);
      const data = ur.responseOk ? ur.data : {};
      if(data.success){
        window.showNotification(data.message || 'Ollama updated.', 'success');
        const startTime = Date.now();
        const poll = async function(){
          if(Date.now() - startTime > 120000){ location.reload(); return; }
          try {
            const h = await fetch('/api/health');
            const hj = await readApiJson(h);
            if(hj.responseOk && hj.data && hj.data.status === 'healthy'){ location.reload(); return; }
          } catch(_){}
          setTimeout(poll, 2000);
        };
        setTimeout(poll, 2000);
      } else {
        window.showNotification(data.message || ur.message || ('Update failed: ' + (resp.statusText || 'error')), 'error');
        if(btn) btn.disabled = false;
      }
    } catch(e){
      clearTimeout(timer);
      const msg = e && e.name === 'AbortError' ? 'Update timed out (waited 15 minutes).' : ('Failed to update Ollama: ' + (e.message || 'Network error'));
      window.showNotification(msg, 'error');
      if(btn) btn.disabled = false;
    } finally {
      if(btn && original !== null) btn.innerHTML = original;
    }
  }

  function showUpdateOllamaConfirm(){
    const confirmBtn = document.getElementById('confirmUpdateOllamaBtn');
    const modalEl = document.getElementById('updateOllamaModal');
    if(!confirmBtn || !modalEl){ updateOllamaService(); return; }
    const handler = async function(){
      confirmBtn.disabled = true;
      await updateOllamaService();
      const m = bootstrap.Modal.getInstance(modalEl);
      if(m) m.hide();
      confirmBtn.disabled = false;
      confirmBtn.removeEventListener('click', handler);
    };
    confirmBtn.addEventListener('click', handler);
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }

  const INSTALL_FETCH_MS = 900000;

  async function installOllamaService(){
    const btn = document.getElementById('installOllamaBtn');
    const original = btn ? btn.innerHTML : null;
    if(btn){ btn.innerHTML='<i class="fas fa-spinner fa-spin"></i>'; btn.disabled=true; }
    const ctrl = new AbortController();
    const timer = setTimeout(function(){ ctrl.abort(); }, INSTALL_FETCH_MS);
    try {
      const resp = await fetch('/api/service/install-ollama', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      const ir = await readApiJson(resp);
      const data = ir.responseOk ? ir.data : {};
      if(data.success){
        window.showNotification(data.message || 'Ollama installed.', 'success');
        const startTime = Date.now();
        const poll = async function(){
          if(Date.now() - startTime > 120000){ location.reload(); return; }
          try {
            const h = await fetch('/api/health');
            const hj = await readApiJson(h);
            if(hj.responseOk && hj.data && hj.data.status === 'healthy'){ location.reload(); return; }
          } catch(_){}
          setTimeout(poll, 2000);
        };
        setTimeout(poll, 2000);
      } else {
        window.showNotification(data.message || ir.message || ('Install failed: ' + (resp.statusText || 'error')), 'error');
        if(btn) btn.disabled = false;
      }
    } catch(e){
      clearTimeout(timer);
      const msg = e && e.name === 'AbortError' ? 'Install timed out (waited 15 minutes).' : ('Failed to install Ollama: ' + (e.message || 'Network error'));
      window.showNotification(msg, 'error');
      if(btn) btn.disabled = false;
    } finally {
      if(btn && original !== null) btn.innerHTML = original;
    }
  }

  function showInstallOllamaConfirm(){
    const confirmBtn = document.getElementById('confirmInstallOllamaBtn');
    const modalEl = document.getElementById('installOllamaModal');
    if(!confirmBtn || !modalEl){ installOllamaService(); return; }
    const handler = async function(){
      confirmBtn.disabled = true;
      await installOllamaService();
      const m = bootstrap.Modal.getInstance(modalEl);
      if(m) m.hide();
      confirmBtn.disabled = false;
      confirmBtn.removeEventListener('click', handler);
    };
    confirmBtn.addEventListener('click', handler);
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
  }

  function init(){ updateHealthStatus(); }

  window.serviceControl = { updateHealthStatus, updateServiceControlButtons, startOllamaService, stopOllamaService, restartOllamaService, showRestartConfirm, updateOllamaService, showUpdateOllamaConfirm, installOllamaService, showInstallOllamaConfirm, init };
  // Expose legacy globals for existing inline onclick handlers
  window.startOllamaService = startOllamaService;
  window.stopOllamaService = stopOllamaService;
  window.restartOllamaService = restartOllamaService;
  window.showRestartConfirm = showRestartConfirm;
  window.updateOllamaService = updateOllamaService;
  window.showUpdateOllamaConfirm = showUpdateOllamaConfirm;
  window.installOllamaService = installOllamaService;
  window.showInstallOllamaConfirm = showInstallOllamaConfirm;
})();