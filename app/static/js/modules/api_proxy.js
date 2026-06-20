/** External API proxy — setup wizard, live status (OpenAI / Claude / Ollama-compatible clients). */
(function () {
  var _statusTimer = null;
  var _statusInFlight = false;
  var STATUS_INTERVAL = 8000;
  var FETCH_TIMEOUT_MS = 12000;

  function proxyBaseUrl() {
    return window.location.origin + "/ollama";
  }

  function proxyDisplayUrl(url) {
    return String(url || "").replace(/^https?:\/\//i, "");
  }

  function endpointCopyText(el) {
    return String(
      el.getAttribute("data-copy-value") || el.getAttribute("title") || el.textContent || ""
    ).trim();
  }

  async function copyHeaderEndpoint(el) {
    var text = endpointCopyText(el);
    if (!text) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      if (window.showNotification) window.showNotification("Address copied", "success");
    } catch (err) {
      if (window.showNotification) window.showNotification("Could not copy address", "error");
    }
  }

  function initHeaderEndpointCopy() {
    var root = document.querySelector(".dashboard-header-meta-group");
    if (!root || root.dataset.endpointCopyBound === "1") return;
    root.dataset.endpointCopyBound = "1";

    root.addEventListener("click", function (e) {
      var el = e.target.closest(".dashboard-header-endpoint-copy");
      if (!el || !root.contains(el)) return;
      e.preventDefault();
      copyHeaderEndpoint(el);
    });

    root.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var el = e.target.closest(".dashboard-header-endpoint-copy");
      if (!el || !root.contains(el)) return;
      e.preventDefault();
      copyHeaderEndpoint(el);
    });
  }

  function setBadge(el, ok, text, tooltip) {
    if (!el) return;
    el.classList.remove("bg-success", "bg-warning", "bg-secondary", "bg-danger");
    el.classList.add(ok ? "bg-success" : "bg-warning");
    var span = el.querySelector(".api-proxy-status-text");
    if (span) span.textContent = text;
    var tip = tooltip || text;
    if (tip) {
      el.setAttribute("data-dashboard-tooltip", tip);
      el.setAttribute("title", tip);
    }
  }

  function syncHeaderProxyDisplay() {
    document.querySelectorAll(".dashboard-header-proxy-url").forEach(function (el) {
      var full = el.getAttribute("data-copy-value") || el.getAttribute("title") || "";
      var display = proxyDisplayUrl(full || el.textContent);
      if (display) el.textContent = display;
    });
  }

  async function refreshProxyStatus() {
    if (_statusInFlight || document.hidden) return;
    _statusInFlight = true;
    var badge = document.getElementById("apiProxyStatusBadge");
    try {
      var resp = await fetchWithTimeout("/api/proxy/status", {}, FETCH_TIMEOUT_MS);
      var jr = await readApiJson(resp);
      if (!jr.responseOk || !jr.data) {
        setBadge(badge, false, "idle");
        return;
      }
      var d = jr.data;
      var label = "ready";
      var detail = label;
      if (d.model_loaded) {
        var parts = ["active"];
        if (d.last_model) parts.push(String(d.last_model).split(":")[0]);
        if (d.allocated_ctx) parts.push(d.allocated_ctx + " ctx");
        if (d.ctx_mismatch) parts.push("ctx mismatch");
        detail = parts.join(" · ");
        label = "active";
      }
      setBadge(badge, d.model_loaded || d.proxy_active !== false, label, detail);
      var url = d.proxy_base_url || d.proxy_endpoint || proxyBaseUrl();
      document.querySelectorAll(".dashboard-header-proxy-url").forEach(function (el) {
        el.setAttribute("title", url);
        el.setAttribute("data-copy-value", url);
      });
      syncHeaderProxyDisplay();
    } catch (e) {
      setBadge(badge, false, "—");
    } finally {
      _statusInFlight = false;
    }
  }

  function startStatusPolling() {
    if (_statusTimer) clearInterval(_statusTimer);
    refreshProxyStatus();
    _statusTimer = setInterval(refreshProxyStatus, STATUS_INTERVAL);
  }

  function stopStatusPolling() {
    if (_statusTimer) {
      clearInterval(_statusTimer);
      _statusTimer = null;
    }
  }

  function mcpBaseUrl() {
    return window.location.origin + "/mcp";
  }

  function copyTextToClipboard(text, successMsg) {
    if (!text) return;
    var done = function () {
      if (window.showNotification) window.showNotification(successMsg || "Copied", "success");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {});
      return;
    }
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      done();
    } catch (_) {}
    document.body.removeChild(ta);
  }

  function renderMcpWizardSection(data, base) {
    var mcpUrl = data.mcp_base_url || mcpBaseUrl();
    var html =
      '<div id="apiMcpWizardSection" class="mt-3 p-2 rounded border border-info api-mcp-wizard-section">' +
      '<div class="small fw-semibold mb-1"><i class="fas fa-toolbox me-1"></i>MCP tools server (dashboard tools for Cursor / VS Code)</div>' +
      '<code class="small user-select-all" id="apiMcpUrlCopy">' +
      escapeHtml(mcpUrl) +
      "</code>" +
      ' <button type="button" class="btn btn-sm btn-outline-info ms-1" id="apiMcpCopyBtn">Copy</button>' +
      '<div class="text-muted small mt-2 mb-2">Same port as the dashboard. Pair with the Ollama proxy above: proxy for <strong>models</strong>, MCP for <strong>dashboard tools</strong>.</div>';

    var tools = data.mcp_tools || [];
    if (tools.length) {
      html += '<div class="small fw-semibold mb-1">Available tools</div><ul class="list-unstyled small mb-2 api-mcp-tool-list">';
      tools.forEach(function (tool) {
        var badge = tool.write
          ? '<span class="badge bg-warning text-dark ms-1">write</span>'
          : '<span class="badge bg-secondary ms-1">read</span>';
        html +=
          "<li class=\"mb-1\"><code>" +
          escapeHtml(tool.name || "") +
          "</code>" +
          badge +
          "<div class=\"text-muted\">" +
          escapeHtml(tool.description || "") +
          "</div></li>";
      });
      html += "</ul>";
    }

    if (data.mcp_write_tools_enabled) {
      html +=
        '<div class="text-warning small mb-2">Write tools (start/stop model) are enabled via <code>MCP_ALLOW_WRITE=true</code>.</div>';
    }

    var mcpExamples = data.mcp_client_examples || [];
    if (mcpExamples.length) {
      html += '<div class="small fw-semibold mb-2">MCP client setup</div>';
      mcpExamples.forEach(function (ex, idx) {
        html +=
          '<div class="mb-2 p-2 rounded api-mcp-example-block" style="background:rgba(255,255,255,0.04)">' +
          '<div class="small fw-semibold">' +
          escapeHtml(ex.name || "") +
          "</div>" +
          '<div class="text-muted small">' +
          escapeHtml(ex.hint || ex.field || "") +
          "</div>" +
          '<pre class="small user-select-all mb-1 api-mcp-example-code" id="apiMcpExample' +
          idx +
          '">' +
          escapeHtml(ex.value || mcpUrl) +
          "</pre>" +
          '<button type="button" class="btn btn-sm btn-outline-secondary api-mcp-example-copy" data-example-idx="' +
          idx +
          '">Copy</button></div>';
      });
    }
    html += "</div>";
    return html;
  }

  async function runWizardChecks(container, scrollToMcp) {
    if (!container) return;
    container.innerHTML =
      '<div class="text-muted small"><i class="fas fa-spinner fa-spin me-1"></i> Running checks…</div>';
    try {
      var resp = await fetchWithTimeout("/api/proxy/wizard-checks", {}, FETCH_TIMEOUT_MS);
      var jr = await readApiJson(resp);
      if (!jr.responseOk) {
        container.innerHTML =
          '<div class="text-danger small">' + escapeHtml(jr.message || "Check failed") + "</div>";
        return;
      }
      var data = jr.data;
      var html = "";
      (data.checks || []).forEach(function (c) {
        var icon = c.passed ? "fa-check-circle text-success" : "fa-times-circle text-warning";
        html +=
          '<div class="d-flex gap-2 align-items-start mb-2 small">' +
          '<i class="fas ' + icon + ' mt-1"></i>' +
          '<div><strong>' + escapeHtml(c.name) + "</strong><br>" +
          escapeHtml(c.detail || "") +
          (c.fix ? '<br><span class="text-muted">' + escapeHtml(c.fix) + "</span>" : "") +
          "</div></div>";
      });

      var base = data.proxy_base_url || data.proxy_endpoint || proxyBaseUrl();
      html +=
        '<div class="mt-3 p-2 rounded border border-secondary">' +
        '<div class="small fw-semibold mb-1">Proxy base URL (use instead of raw Ollama <code>:11434</code>)</div>' +
        '<code class="small user-select-all" id="apiProxyUrlCopy">' +
        escapeHtml(base) +
        "</code>" +
        ' <button type="button" class="btn btn-sm btn-outline-info ms-1" id="apiProxyCopyBtn">Copy</button>' +
        '<div class="text-muted small mt-2 mb-0">Clients append their own paths (<code>/v1/chat/completions</code>, <code>/api/chat</code>, etc.).</div></div>';

      if (data.client_examples && data.client_examples.length) {
        html += '<div class="mt-3"><div class="small fw-semibold mb-2">Example setups</div>';
        data.client_examples.forEach(function (ex) {
          html +=
            '<div class="mb-2 p-2 rounded" style="background:rgba(255,255,255,0.04)">' +
            '<div class="small fw-semibold">' + escapeHtml(ex.name) + "</div>" +
            '<div class="text-muted small">' + escapeHtml(ex.hint || ex.field || "") + "</div>" +
            '<code class="small user-select-all">' + escapeHtml(ex.value || base) + "</code></div>";
        });
        html += "</div>";
      }

      html += renderMcpWizardSection(data, base);

      container.innerHTML = html;
      var copyBtn = document.getElementById("apiProxyCopyBtn");
      if (copyBtn) {
        copyBtn.onclick = function () {
          var text = document.getElementById("apiProxyUrlCopy");
          if (text && navigator.clipboard) {
            navigator.clipboard.writeText(text.textContent || base);
            if (window.showNotification) window.showNotification("Copied proxy URL", "success");
          }
        };
      }
      var mcpCopyBtn = document.getElementById("apiMcpCopyBtn");
      if (mcpCopyBtn) {
        mcpCopyBtn.onclick = function () {
          var mcpEl = document.getElementById("apiMcpUrlCopy");
          copyTextToClipboard((mcpEl && mcpEl.textContent) || data.mcp_base_url || mcpBaseUrl(), "Copied MCP URL");
        };
      }
      container.querySelectorAll(".api-mcp-example-copy").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var idx = btn.getAttribute("data-example-idx");
          var pre = document.getElementById("apiMcpExample" + idx);
          copyTextToClipboard(pre ? pre.textContent : "", "Copied MCP config");
        });
      });
      if (scrollToMcp) {
        var mcpSection = document.getElementById("apiMcpWizardSection");
        if (mcpSection) mcpSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      container.innerHTML = '<div class="text-danger small">' + escapeHtml(err.message) + "</div>";
    }
  }

  function openProxyWizard(scrollToMcp) {
    var existing = document.getElementById("apiProxyWizardModal");
    if (existing) existing.remove();
    var html =
      '<div class="modal fade" id="apiProxyWizardModal" tabindex="-1">' +
      '<div class="modal-dialog modal-dialog-centered modal-lg modal-dialog-scrollable">' +
      '<div class="modal-content bg-dark text-light">' +
      '<div class="modal-header"><h5 class="modal-title"><i class="fas fa-plug me-2"></i>Connect external apps</h5>' +
      '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>' +
      '<div class="modal-body"><p class="text-muted small">Any app that accepts an <strong>Ollama server address</strong> or an <strong>OpenAI-compatible API base URL</strong> can use the dashboard proxy instead of <code>localhost:11434</code>. Saved per-model settings (temperature, <code>num_ctx</code>, prompts) are applied automatically.</p>' +
      '<p class="text-muted small mb-2">Works with VS Code chat extensions, Claude Code with Ollama, Continue, Cursor BYOK, LangChain, OpenAI SDKs pointed at a local base URL, and other compatible tools. Use the <strong>MCP tools server</strong> below so agents can call dashboard tools from Cursor or VS Code.</p>' +
      '<div id="apiProxyWizardChecks"></div></div>' +
      '<div class="modal-footer"><button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>' +
      '<button type="button" class="btn btn-primary" id="apiProxyWizardRerun">Re-run checks</button></div>' +
      "</div></div></div>";
    document.body.insertAdjacentHTML("beforeend", html);
    var modalEl = document.getElementById("apiProxyWizardModal");
    var modal = new bootstrap.Modal(modalEl);
    modal.show();
    var checksEl = document.getElementById("apiProxyWizardChecks");
    runWizardChecks(checksEl, !!scrollToMcp);
    document.getElementById("apiProxyWizardRerun").onclick = function () {
      runWizardChecks(checksEl, false);
    };
    modalEl.addEventListener("hidden.bs.modal", function () {
      modalEl.remove();
    });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") startStatusPolling();
    else stopStatusPolling();
  });

  function init() {
    initHeaderEndpointCopy();
    syncHeaderProxyDisplay();
    startStatusPolling();
  }

  window.apiProxyUI = {
    init: init,
    openWizard: openProxyWizard,
    refreshStatus: refreshProxyStatus,
  };
  // Legacy alias
  window.copilotUI = window.apiProxyUI;
})();
