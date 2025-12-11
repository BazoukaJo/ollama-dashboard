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
      const health = await response.json();
      const healthBadge = document.getElementById('healthStatus');
      const healthText = document.getElementById('healthText');
      if(!healthBadge || !healthText) return;
      const applyCommon = ()=>{ healthBadge.style.padding='0.5rem 1rem'; healthBadge.style.fontSize='0.85rem'; };
      if (health.status === 'healthy') {
        healthBadge.className='badge bg-success'; applyCommon();
        const uptimeMin = Math.floor(health.uptime_seconds/60);
        const uptimeHr = Math.floor(uptimeMin/60);
        const uptimeDisplay = uptimeHr>0?`${uptimeHr}h ${uptimeMin%60}m`:`${uptimeMin}m`;
        healthText.innerHTML = `Healthy • Uptime: ${uptimeDisplay} • ${health.models.running_count} running / ${health.models.available_count} available`;
        updateServiceControlButtons(true);
      } else if (health.status === 'degraded') {
        healthBadge.className='badge bg-warning'; applyCommon();
        healthText.innerHTML = 'Degraded • Ollama service not running';
        updateServiceControlButtons(false);
      } else {
        healthBadge.className='badge bg-danger'; applyCommon();
        healthText.innerHTML = 'Unhealthy • ' + (health.error || 'Unknown error');
        updateServiceControlButtons(false);
      }
    } catch(err){
      const healthBadge = document.getElementById('healthStatus');
      const healthText = document.getElementById('healthText');
      if(healthBadge && healthText){
        healthBadge.className='badge bg-danger';
        healthBadge.style.padding='0.5rem 1rem';
        healthBadge.style.fontSize='0.85rem';
        healthText.innerHTML='Health check failed';
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
      if(!resp.ok){
        const errorText = await resp.text().catch(()=>'Unknown error');
        window.showNotification('Failed to start service: '+errorText,'error');
        if(btn) btn.disabled=false;
        return;
      }
      const data = await resp.json();
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
      if(!resp.ok){
        const errorText = await resp.text().catch(()=>'Unknown error');
        window.showNotification('Failed to stop service: '+errorText,'error');
        if(btn) btn.disabled=false;
        return;
      }
      const data = await resp.json();
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
      const data = await resp.json();
      if(data.success){
        window.showNotification(data.message,'success');
        // Poll health until healthy or timeout then reload
        const startTime = Date.now();
        const poll = async () => {
          if(Date.now() - startTime > 30000){ location.reload(); return; }
          try {
            const h = await fetch('/api/health');
            if(h.ok){
              const hj = await h.json();
              if(hj.status === 'healthy'){ location.reload(); return; }
            }
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

  function init(){ updateHealthStatus(); setInterval(updateHealthStatus,15000); }

  window.serviceControl = { updateHealthStatus, updateServiceControlButtons, startOllamaService, stopOllamaService, restartOllamaService, showRestartConfirm, init };
  // Expose legacy globals for existing inline onclick handlers
  window.startOllamaService = startOllamaService;
  window.stopOllamaService = stopOllamaService;
  window.restartOllamaService = restartOllamaService;
  window.showRestartConfirm = showRestartConfirm;
})();