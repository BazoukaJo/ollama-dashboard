(function(){
  function init(){
    if(typeof updateTimes==='function') updateTimes();
    if(typeof updateSystemStats==='function') updateSystemStats();
    if(typeof updateModelData==='function') updateModelData();
    if(typeof initializeCompactMode==='function') initializeCompactMode();
    if(window.serviceControl && window.serviceControl.init) window.serviceControl.init();
    if(typeof loadDownloadableModels==='function') loadDownloadableModels();
    // Intervals
    if(typeof updateSystemStats==='function') setInterval(updateSystemStats,1000);
    if(typeof updateModelData==='function') setInterval(updateModelData,3000);
    // Health interval handled inside serviceControl.init()
  }
  document.addEventListener('DOMContentLoaded', init);
  window.bootstrapInit = init;
})();