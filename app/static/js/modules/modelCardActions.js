/**
 * Model card "More" menu: clipboard helpers, library link, quick chat, copy settings.
 */
(function () {
  const RECENT_KEY = "ollamaDashRecentErrors";

  function safeDomId(modelName) {
    return String(modelName || "m")
      .replace(/[^a-zA-Z0-9_-]/g, "_")
      .slice(0, 96);
  }

  function getOllamaApiBase() {
    const b = document.body;
    const u = b && b.dataset ? b.dataset.ollamaApiBase : "";
    return (u && String(u).trim()) || "http://127.0.0.1:11434";
  }

  function encModel(modelName) {
    return encodeURIComponent(String(modelName || ""));
  }

  async function copyText(text, okMsg) {
    const t = String(text ?? "");
    try {
      await navigator.clipboard.writeText(t);
      if (typeof showNotification === "function") {
        showNotification(okMsg || "Copied to clipboard", "success");
      }
    } catch (err) {
      if (typeof showNotification === "function") {
        showNotification("Could not copy to clipboard", "error");
      }
    }
  }

  function librarySlug(modelName) {
    const n = String(modelName || "").trim();
    if (!n) return null;
    const base = n.split(":")[0].split("/").pop();
    return base || null;
  }

  function libraryUrl(modelName) {
    const s = librarySlug(modelName);
    return s ? "https://ollama.com/library/" + encodeURIComponent(s) : null;
  }

  function openLibrary(modelName) {
    const u = libraryUrl(modelName);
    if (u) window.open(u, "_blank", "noopener,noreferrer");
    else if (typeof showNotification === "function") {
      showNotification("Could not derive library URL for this name", "error");
    }
  }

  function copyModelName(modelName) {
    copyText(String(modelName || ""), "Model name copied");
  }

  function copyOllamaRun(modelName) {
    const n = String(modelName || "");
    const line =
      "ollama run " + (n.includes(" ") || n.includes('"') ? JSON.stringify(n) : n);
    copyText(line, "CLI command copied");
  }

  function copyOllamaEmbed(modelName) {
    const n = String(modelName || "");
    const line =
      "ollama embed " + (n.includes(" ") || n.includes('"') ? JSON.stringify(n) : n) + ' "your text"';
    copyText(line, "Embed CLI copied");
  }

  function copyCurlGenerate(modelName) {
    const base = getOllamaApiBase().replace(/\/$/, "");
    const body = { model: String(modelName || ""), prompt: "Hello", stream: false };
    const line =
      "curl -s " +
      JSON.stringify(base + "/api/generate") +
      " -H " +
      JSON.stringify("Content-Type: application/json") +
      " -d " +
      JSON.stringify(JSON.stringify(body));
    copyText(line, "curl /api/generate copied");
  }

  function copyCurlChatRoute(modelName) {
    const origin =
      typeof window !== "undefined" && window.location && window.location.origin
        ? window.location.origin
        : "";
    const body = { model: String(modelName || ""), prompt: "Hello" };
    const line =
      "curl -s " +
      JSON.stringify(origin + "/api/chat") +
      " -H " +
      JSON.stringify("Content-Type: application/json") +
      " -d " +
      JSON.stringify(JSON.stringify(body));
    copyText(line, "curl dashboard /api/chat copied");
  }

  function moreMenuHtml(modelName) {
    const e = encModel(modelName);
    const sid = safeDomId(modelName);
    return (
      '<div class="btn-group dropstart model-more-wrap" role="group">' +
      '<button type="button" class="btn btn-outline-secondary btn-sm dropdown-toggle border-secondary" ' +
      'data-bs-toggle="dropdown" data-bs-display="static" aria-expanded="false" data-dashboard-tooltip="Copy model name, CLI snippets, or curl examples for this card." ' +
      'id="mc-more-' +
      sid +
      '">' +
      '<i class="fas fa-ellipsis-h" aria-hidden="true"></i></button>' +
      '<ul class="dropdown-menu dropdown-menu-end dropdown-menu-dark text-small" style="min-width:13rem;" ' +
      'aria-labelledby="mc-more-' +
      sid +
      '">' +
      '<li><button type="button" class="dropdown-item" data-mc-act="copy-name" data-mc-model="' +
      e +
      '">Copy model name</button></li>' +
      '<li><button type="button" class="dropdown-item" data-mc-act="copy-run" data-mc-model="' +
      e +
      '">Copy <code class="text-info">ollama run</code></button></li>' +
      '<li><button type="button" class="dropdown-item" data-mc-act="copy-embed" data-mc-model="' +
      e +
      '">Copy <code class="text-info">ollama embed</code></button></li>' +
      '<li><hr class="dropdown-divider"></li>' +
      '<li><button type="button" class="dropdown-item" data-mc-act="copy-curl-gen" data-mc-model="' +
      e +
      '">Copy curl → Ollama <code class="text-info">/api/generate</code></button></li>' +
      '<li><button type="button" class="dropdown-item" data-mc-act="copy-curl-dash" data-mc-model="' +
      e +
      '">Copy curl → dashboard <code class="text-info">/api/chat</code></button></li>' +
      '<li><hr class="dropdown-divider"></li>' +
      '<li><button type="button" class="dropdown-item" data-mc-act="open-lib" data-mc-model="' +
      e +
      '">Open ollama.com library</button></li>' +
      '<li><button type="button" class="dropdown-item" data-mc-act="quick-chat" data-mc-model="' +
      e +
      '">Quick try (chat)…</button></li>' +
      '<li><button type="button" class="dropdown-item" data-mc-act="copy-settings" data-mc-model="' +
      e +
      '">Copy settings from another model…</button></li>' +
      "</ul></div>"
    );
  }

  function appendMoreMenuToCard(card) {
    if (!card || card.querySelector(".model-more-wrap")) return;
    const actions = card.querySelector(".model-actions");
    const name = card.dataset.modelName;
    if (!actions || !name) return;
    actions.insertAdjacentHTML("beforeend", moreMenuHtml(name));
  }

  function enhanceAllModelCards() {
    document.querySelectorAll(".model-card[data-model-name]").forEach(appendMoreMenuToCard);
  }

  function decodeModel(el) {
    const e = el && el.getAttribute && el.getAttribute("data-mc-model");
    if (e == null || e === "") return "";
    try {
      return decodeURIComponent(e);
    } catch (err) {
      return "";
    }
  }

  async function showQuickChatModal(modelName) {
    const mid = "quickChatModal";
    const old = document.getElementById(mid);
    if (old) old.remove();
    const safe = typeof escapeHtml === "function" ? escapeHtml(modelName) : modelName;
    document.body.insertAdjacentHTML(
      "beforeend",
      '<div class="modal fade" id="' +
        mid +
        '" tabindex="-1">' +
        '<div class="modal-dialog modal-dialog-centered">' +
        '<div class="modal-content bg-dark text-light">' +
        '<div class="modal-header"><h5 class="modal-title">Quick try — ' +
        safe +
        '</h5>' +
        '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>' +
        '<div class="modal-body">' +
        '<p class="text-muted small">Uses dashboard <code class="text-info">/api/chat</code> (model must be installed).</p>' +
        '<textarea class="form-control bg-dark text-light border-secondary" id="qc-prompt" rows="4" ' +
        'placeholder="Your message…">Hello! Reply in one short sentence.</textarea>' +
        '<div id="qc-out" class="mt-3 small text-wrap" style="white-space:pre-wrap;max-height:240px;overflow:auto;"></div>' +
        "</div>" +
        '<div class="modal-footer">' +
        '<button type="button" class="btn btn-primary" id="qc-send"><i class="fas fa-paper-plane me-1"></i>Send</button>' +
        "</div></div></div></div>",
    );
    const el = document.getElementById(mid);
    const modal = new bootstrap.Modal(el);
    modal.show();
    document.getElementById("qc-send").onclick = async function () {
      const ta = document.getElementById("qc-prompt");
      const out = document.getElementById("qc-out");
      const prompt = (ta && ta.value) || "";
      if (!prompt.trim()) {
        if (typeof showNotification === "function") {
          showNotification("Enter a prompt", "error");
        }
        return;
      }
      out.textContent = "…";
      try {
        const r = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model: modelName, prompt: prompt.trim(), stream: false }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          out.textContent = data.error || data.message || "Request failed";
          recordRecentModelError(String(out.textContent));
          return;
        }
        const text =
          data.response != null
            ? String(data.response)
            : JSON.stringify(data, null, 2);
        out.textContent = text;
        if (typeof updateModelData === "function") {
          void updateModelData();
        }
      } catch (err) {
        out.textContent = err.message || String(err);
        recordRecentModelError(String(out.textContent));
      }
    };
    el.addEventListener("hidden.bs.modal", function () {
      el.remove();
    });
  }

  async function showCopySettingsModal(targetModel) {
    const mid = "copySettingsModal";
    const old = document.getElementById(mid);
    if (old) old.remove();
    let options = '<option value="">— pick source model —</option>';
    try {
      const r = await fetch("/api/models/available");
      const j = await r.json();
      const list = Array.isArray(j.models) ? j.models : [];
      list.forEach(function (m) {
        const n = m && m.name;
        if (!n || n === targetModel) return;
        const lab = typeof escapeHtml === "function" ? escapeHtml(n) : n;
        const v = String(n)
          .replace(/&/g, "&amp;")
          .replace(/"/g, "&quot;")
          .replace(/</g, "&lt;");
        options += '<option value="' + v + '">' + lab + "</option>";
      });
    } catch (err) {
      options = '<option value="">(failed to load models)</option>';
    }
    const tgt =
      typeof escapeHtml === "function" ? escapeHtml(targetModel) : targetModel;
    document.body.insertAdjacentHTML(
      "beforeend",
      '<div class="modal fade" id="' +
        mid +
        '" tabindex="-1">' +
        '<div class="modal-dialog modal-dialog-centered">' +
        '<div class="modal-content bg-dark text-light">' +
        '<div class="modal-header"><h5 class="modal-title">Copy settings → ' +
        tgt +
        '</h5>' +
        '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>' +
        '<div class="modal-body">' +
        '<label class="form-label">Copy from</label>' +
        '<select class="form-select bg-dark text-light border-secondary" id="cs-from">' +
        options +
        "</select>" +
        '<p class="text-muted small mt-2 mb-0">Overwrites custom settings for the target with the source model’s effective settings.</p>' +
        "</div>" +
        '<div class="modal-footer">' +
        '<button type="button" class="btn btn-primary" id="cs-apply">Copy</button>' +
        "</div></div></div></div>",
    );
    const el = document.getElementById(mid);
    const modal = new bootstrap.Modal(el);
    modal.show();
    document.getElementById("cs-apply").onclick = async function () {
      const sel = document.getElementById("cs-from");
      const raw = sel && sel.value ? sel.value : "";
      if (!raw) {
        if (typeof showNotification === "function") {
          showNotification("Choose a source model", "error");
        }
        return;
      }
      try {
        const r = await fetch("/api/models/settings/copy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ from: raw, to: targetModel }),
        });
        const data = await r.json();
        if (data.success) {
          if (typeof showNotification === "function") {
            showNotification(data.message, "success");
          }
          modal.hide();
          setTimeout(function () {
            location.reload();
          }, 600);
        } else {
          if (typeof showNotification === "function") {
            showNotification(data.message || "Copy failed", "error");
          }
        }
      } catch (err) {
        if (typeof showNotification === "function") {
          showNotification(err.message || "Copy failed", "error");
        }
      }
    };
    el.addEventListener("hidden.bs.modal", function () {
      el.remove();
    });
  }

  function recordRecentModelError(message) {
    try {
      const prev = JSON.parse(sessionStorage.getItem(RECENT_KEY) || "[]");
      prev.unshift({
        t: Date.now(),
        msg: String(message || "").slice(0, 800),
      });
      sessionStorage.setItem(RECENT_KEY, JSON.stringify(prev.slice(0, 6)));
      renderRecentErrorsBar();
    } catch (e) {
      /* ignore */
    }
  }

  function renderRecentErrorsBar() {
    const host = document.getElementById("recentErrorsHost");
    if (!host) return;
    let items;
    try {
      items = JSON.parse(sessionStorage.getItem(RECENT_KEY) || "[]");
    } catch (e) {
      items = [];
    }
    if (!items.length) {
      host.classList.add("d-none");
      host.innerHTML = "";
      return;
    }
    host.classList.remove("d-none");
    const lines = items
      .map(function (x) {
        const time = new Date(x.t).toLocaleTimeString();
        const msg =
          typeof escapeHtml === "function" ? escapeHtml(x.msg) : String(x.msg);
        return (
          '<div class="d-flex align-items-start gap-2 border-bottom border-secondary py-1">' +
          '<small class="text-muted text-nowrap">' +
          time +
          "</small>" +
          '<span class="flex-grow-1 small text-warning text-break">' +
          msg +
          "</span>" +
          '<button type="button" class="btn btn-sm btn-outline-secondary flex-shrink-0" ' +
          'onclick="modelCardActions.copyText(' +
          JSON.stringify(String(x.msg)) +
          ', \'Copied\')">Copy</button></div>'
        );
      })
      .join("");
    host.innerHTML =
      '<div class="card bg-dark border-secondary mb-2">' +
      '<div class="card-header py-1 d-flex justify-content-between align-items-center">' +
      '<span class="small text-muted"><i class="fas fa-exclamation-triangle me-1"></i>Recent issues (this tab)</span>' +
      '<button type="button" class="btn btn-sm btn-outline-secondary" onclick="modelCardActions.clearRecentErrors()">Clear</button>' +
      "</div>" +
      '<div class="card-body py-1">' +
      lines +
      "</div></div>";
  }

  function clearRecentErrors() {
    try {
      sessionStorage.removeItem(RECENT_KEY);
    } catch (e) {
      /* ignore */
    }
    renderRecentErrorsBar();
  }

  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest("[data-mc-act]");
    if (!btn) return;
    const act = btn.getAttribute("data-mc-act");
    const model = decodeModel(btn);
    if (!model) return;
    ev.preventDefault();
    if (act === "copy-name") copyModelName(model);
    else if (act === "copy-run") copyOllamaRun(model);
    else if (act === "copy-embed") copyOllamaEmbed(model);
    else if (act === "copy-curl-gen") copyCurlGenerate(model);
    else if (act === "copy-curl-dash") copyCurlChatRoute(model);
    else if (act === "open-lib") openLibrary(model);
    else if (act === "quick-chat") showQuickChatModal(model);
    else if (act === "copy-settings") showCopySettingsModal(model);
  });

  window.modelCardActions = {
    safeDomId,
    getOllamaApiBase,
    copyText,
    libraryUrl,
    openLibrary,
    copyModelName,
    copyOllamaRun,
    copyOllamaEmbed,
    copyCurlGenerate,
    copyCurlChatRoute,
    moreMenuHtml,
    appendMoreMenuToCard,
    enhanceAllModelCards,
    recordRecentModelError,
    renderRecentErrorsBar,
    clearRecentErrors,
    showQuickChatModal,
    showCopySettingsModal,
  };
})();
