/** Ask? modal — saved Q&A history tab. */
(function () {
  var _historyItems = [];
  var _expandedId = null;
  var _historyBound = false;

  function esc(str) {
    return typeof escapeHtml === "function" ? escapeHtml(String(str || "")) : String(str || "");
  }

  function formatRelativeTime(iso) {
    if (!iso) return "";
    try {
      var then = new Date(iso).getTime();
      var now = Date.now();
      var diffSec = Math.max(0, Math.floor((now - then) / 1000));
      if (diffSec < 60) return "just now";
      var diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return diffMin + (diffMin === 1 ? " minute ago" : " minutes ago");
      var diffHr = Math.floor(diffMin / 60);
      if (diffHr < 24) return diffHr + (diffHr === 1 ? " hour ago" : " hours ago");
      var diffDay = Math.floor(diffHr / 24);
      if (diffDay < 7) return diffDay + (diffDay === 1 ? " day ago" : " days ago");
      return new Date(iso).toLocaleString();
    } catch (_) {
      return String(iso);
    }
  }

  function truncate(text, max) {
    var s = String(text || "").trim();
    if (s.length <= max) return s;
    return s.slice(0, max).trim() + "…";
  }

  function buildMarkdown(entry) {
    var model = entry.model || "unknown";
    var prompt = entry.prompt || "";
    var response = entry.response || "";
    var ts = entry.timestamp || "";
    var lines = ["# Ask: " + model];
    if (ts) lines.push("", "_Saved: " + ts + "_");
    if (Array.isArray(entry.attachments) && entry.attachments.length) {
      lines.push(
        "",
        "**Attachments:** " +
          entry.attachments.map(function (a) {
            return (a.type || "file") + ": " + (a.name || "");
          }).join(", "),
      );
    }
    lines.push("", "**Question:**", prompt, "", "**Answer:**", response);
    return lines.join("\n");
  }

  function downloadText(filename, text) {
    var blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function safeFilename(model) {
    return String(model || "ask")
      .replace(/[^\w.\-]+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "ask";
  }

  function updateHistoryCount(count) {
    var badge = document.getElementById("askHistoryCount");
    if (badge) badge.textContent = String(count);
  }

  function getFilteredItems() {
    var filterEl = document.getElementById("askHistoryModelFilter");
    var modelFilter = filterEl && filterEl.value ? filterEl.value : "";
    if (!modelFilter) return _historyItems.slice();
    return _historyItems.filter(function (item) {
      return item.model === modelFilter;
    });
  }

  function populateModelFilter(items) {
    var filterEl = document.getElementById("askHistoryModelFilter");
    if (!filterEl) return;
    var current = filterEl.value;
    var models = [];
    items.forEach(function (item) {
      if (item.model && models.indexOf(item.model) === -1) models.push(item.model);
    });
    models.sort();
    filterEl.innerHTML =
      '<option value="">All models</option>' +
      models
        .map(function (m) {
          return '<option value="' + esc(m) + '">' + esc(m) + "</option>";
        })
        .join("");
    if (current && models.indexOf(current) !== -1) {
      filterEl.value = current;
    }
  }

  function findItem(id) {
    return _historyItems.find(function (item) {
      return item.id === id;
    });
  }

  function renderHistoryList() {
    var listEl = document.getElementById("askHistoryList");
    var emptyEl = document.getElementById("askHistoryEmpty");
    if (!listEl || !emptyEl) return;

    var items = getFilteredItems();
    var filterEl = document.getElementById("askHistoryModelFilter");
    var hasFilter = filterEl && filterEl.value;
    if (!items.length) {
      listEl.innerHTML = "";
      emptyEl.style.display = "";
      emptyEl.textContent = hasFilter
        ? "No saved answers for this model."
        : "No saved answers yet. Ask a question, then click Save.";
      return;
    }

    emptyEl.style.display = "none";
    listEl.innerHTML = items
      .map(function (item) {
        var id = item.id || "";
        var expanded = _expandedId === id;
        var preview = truncate(item.prompt || item.response || "(empty)", 120);
        return (
          '<article class="ask-history-item' +
          (expanded ? " ask-history-item--expanded" : "") +
          '" data-id="' +
          esc(id) +
          '">' +
          '<button type="button" class="ask-history-item-toggle btn btn-link text-start w-100 p-0 text-decoration-none text-light">' +
          '<div class="d-flex flex-wrap align-items-center gap-2 mb-1">' +
          '<span class="badge bg-success ask-history-model">' +
          esc(item.model || "unknown") +
          "</span>" +
          '<span class="small text-muted ask-history-time">' +
          esc(formatRelativeTime(item.timestamp)) +
          "</span>" +
          "</div>" +
          '<div class="ask-history-preview small">' +
          esc(preview) +
          "</div>" +
          "</button>" +
          (expanded
            ? '<div class="ask-history-detail mt-2">' +
              '<div class="ask-history-block mb-2">' +
              '<div class="small text-muted mb-1">Question</div>' +
              '<div class="ask-history-text">' +
              esc(item.prompt || "") +
              "</div>" +
              "</div>" +
              '<div class="ask-history-block mb-2">' +
              '<div class="small text-muted mb-1">Answer</div>' +
              '<div class="ask-history-text">' +
              esc(item.response || "") +
              "</div>" +
              "</div>" +
              '<div class="d-flex flex-wrap gap-1 ask-history-actions">' +
              '<button type="button" class="btn btn-sm btn-outline-secondary ask-history-copy" data-id="' +
              esc(id) +
              '"><i class="fas fa-copy me-1"></i>Copy</button>' +
              '<button type="button" class="btn btn-sm btn-outline-secondary ask-history-download" data-id="' +
              esc(id) +
              '"><i class="fas fa-download me-1"></i>Download</button>' +
              '<button type="button" class="btn btn-sm btn-outline-info ask-history-ask-again" data-id="' +
              esc(id) +
              '"><i class="fas fa-redo me-1"></i>Ask again</button>' +
              '<button type="button" class="btn btn-sm btn-outline-danger ask-history-delete ms-auto" data-id="' +
              esc(id) +
              '"><i class="fas fa-trash-alt me-1"></i>Delete</button>' +
              "</div>" +
              "</div>"
            : "") +
          "</article>"
        );
      })
      .join("");

    listEl.querySelectorAll(".ask-history-item-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var article = btn.closest(".ask-history-item");
        var id = article && article.getAttribute("data-id");
        if (!id) return;
        _expandedId = _expandedId === id ? null : id;
        renderHistoryList();
      });
    });

    listEl.querySelectorAll(".ask-history-copy").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        copyHistoryItem(btn.getAttribute("data-id"));
      });
    });
    listEl.querySelectorAll(".ask-history-download").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        downloadHistoryItem(btn.getAttribute("data-id"));
      });
    });
    listEl.querySelectorAll(".ask-history-ask-again").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        askAgainFromHistory(btn.getAttribute("data-id"));
      });
    });
    listEl.querySelectorAll(".ask-history-delete").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        deleteHistoryItem(btn.getAttribute("data-id"));
      });
    });
  }

  async function loadHistory() {
    try {
      var resp = await fetch("/api/chat/history");
      var jr = await readApiJson(resp);
      if (!jr.responseOk) {
        if (window.showNotification) showNotification(jr.message || "Could not load history", "error");
        return;
      }
      _historyItems = Array.isArray(jr.data.history) ? jr.data.history : [];
      updateHistoryCount(_historyItems.length);
      populateModelFilter(_historyItems);
      renderHistoryList();
    } catch (err) {
      if (window.showNotification) showNotification("Could not load history: " + err.message, "error");
    }
  }

  async function saveCurrentExchange() {
    if (!window.askModalGetState) return;
    var state = window.askModalGetState();
    if (!state || !state.model) {
      if (window.showNotification) showNotification("No model selected", "warning");
      return;
    }
    if (!state.prompt && !state.response) {
      if (window.showNotification) showNotification("Nothing to save yet", "warning");
      return;
    }

    var saveBtn = document.getElementById("askModelSaveBtn");
    if (saveBtn) saveBtn.disabled = true;

    try {
      var resp = await fetch("/api/chat/history", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: state.model,
          prompt: state.prompt,
          response: state.response,
          attachments: state.attachments || [],
        }),
      });
      var jr = await readApiJson(resp);
      if (!jr.responseOk) {
        if (window.showNotification) showNotification(jr.message || "Save failed", "error");
        return;
      }
      if (window.showNotification) showNotification("Saved to history", "success");
      await loadHistory();
    } catch (err) {
      if (window.showNotification) showNotification("Save failed: " + err.message, "error");
    } finally {
      if (saveBtn && state && state.response) saveBtn.disabled = false;
    }
  }

  async function deleteHistoryItem(id) {
    if (!id) return;
    if (!window.confirm("Delete this saved answer?")) return;
    try {
      var resp = await fetch("/api/chat/history/" + encodeURIComponent(id), { method: "DELETE" });
      var jr = await readApiJson(resp);
      if (!jr.responseOk) {
        if (window.showNotification) showNotification(jr.message || "Delete failed", "error");
        return;
      }
      if (_expandedId === id) _expandedId = null;
      await loadHistory();
      if (window.showNotification) showNotification("Deleted from history", "success");
    } catch (err) {
      if (window.showNotification) showNotification("Delete failed: " + err.message, "error");
    }
  }

  async function clearAllHistory() {
    if (!_historyItems.length) return;
    if (!window.confirm("Clear all saved answers? This cannot be undone.")) return;
    try {
      var resp = await fetch("/api/chat/history", { method: "DELETE" });
      var jr = await readApiJson(resp);
      if (!jr.responseOk) {
        if (window.showNotification) showNotification(jr.message || "Clear failed", "error");
        return;
      }
      _expandedId = null;
      await loadHistory();
      if (window.showNotification) showNotification("History cleared", "success");
    } catch (err) {
      if (window.showNotification) showNotification("Clear failed: " + err.message, "error");
    }
  }

  async function copyHistoryItem(id) {
    var item = findItem(id);
    if (!item) return;
    var text = item.response || buildMarkdown(item);
    try {
      await navigator.clipboard.writeText(text);
      if (window.showNotification) showNotification("Copied to clipboard", "success");
    } catch (err) {
      if (window.showNotification) showNotification("Could not copy", "error");
    }
  }

  function downloadHistoryItem(id) {
    var item = findItem(id);
    if (!item) return;
    var date = item.timestamp ? new Date(item.timestamp).toISOString().slice(0, 10) : "export";
    var filename = "ask-" + safeFilename(item.model) + "-" + date + ".md";
    downloadText(filename, buildMarkdown(item));
    if (window.showNotification) showNotification("Download started", "success");
  }

  function askAgainFromHistory(id) {
    var item = findItem(id);
    if (!item || !item.model) return;
    if (typeof window.openAskModal === "function") {
      window.openAskModal(item.model);
    }
    var input = document.getElementById("askModelInput");
    if (input) input.value = item.prompt || "";
    var askTabBtn = document.getElementById("askTabBtn");
    if (askTabBtn && typeof bootstrap !== "undefined") {
      bootstrap.Tab.getOrCreateInstance(askTabBtn).show();
    }
    if (input) input.focus();
  }

  function bindHistoryControls() {
    if (_historyBound) return;
    _historyBound = true;

    var modalEl = document.getElementById("askModelModal");
    if (modalEl) {
      modalEl.addEventListener("shown.bs.tab", function (e) {
        if (e.target && e.target.id === "askHistoryTabBtn") {
          loadHistory();
        }
      });
    }

    var filterEl = document.getElementById("askHistoryModelFilter");
    if (filterEl) {
      filterEl.addEventListener("change", renderHistoryList);
    }

    var clearBtn = document.getElementById("askHistoryClearAllBtn");
    if (clearBtn) clearBtn.addEventListener("click", clearAllHistory);

    var saveBtn = document.getElementById("askModelSaveBtn");
    if (saveBtn) saveBtn.addEventListener("click", saveCurrentExchange);
  }

  function initAskHistory() {
    bindHistoryControls();
    loadHistory();
  }

  window.askHistory = {
    loadHistory: loadHistory,
    saveCurrentExchange: saveCurrentExchange,
    init: initAskHistory,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAskHistory);
  } else {
    initAskHistory();
  }
})();
