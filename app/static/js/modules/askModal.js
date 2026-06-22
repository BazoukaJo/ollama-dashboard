/** Ask? modal — multi-turn chat with optional attachments (image, PDF, Word, code). */
(function () {
  var _askModelName = null;
  var _askAbortController = null;
  var _askAttachments = [];
  var _askModelCaps = { has_vision: null, has_tools: null, has_reasoning: null };
  var _askCapsLoading = false;
  var _askControlsBound = false;
  var _askThread = [];
  var _askIsSending = false;

  var CODE_LANGS = [
    "text",
    "python",
    "javascript",
    "typescript",
    "java",
    "c",
    "cpp",
    "csharp",
    "go",
    "rust",
    "sql",
    "bash",
    "html",
    "css",
    "json",
    "yaml",
    "markdown",
  ];

  function renderAskMessageContent(text, options) {
    options = options || {};
    if (typeof window.formatAskMessageHtml === "function") {
      return window.formatAskMessageHtml(text, options);
    }
    var esc =
      typeof escapeHtml === "function"
        ? escapeHtml
        : function (s) {
            return String(s || "");
          };
    return esc(String(text || ""));
  }

  function readFileAsBase64(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        var result = reader.result || "";
        var comma = String(result).indexOf(",");
        resolve(comma >= 0 ? String(result).slice(comma + 1) : String(result));
      };
      reader.onerror = function () {
        reject(reader.error || new Error("Could not read file"));
      };
      reader.readAsDataURL(file);
    });
  }

  function normalizeModelName(name) {
    return String(name || "")
      .trim()
      .toLowerCase();
  }

  function triStateFlag(val) {
    if (val === true || val === "true") return true;
    if (val === false || val === "false") return false;
    return null;
  }

  function equalsLooseModelName(a, b) {
    var left = normalizeModelName(a);
    var right = normalizeModelName(b);
    if (!left || !right) return false;
    if (left === right) return true;
    var stripTag = function (n) {
      return n.replace(/:[^\s]+$/, "");
    };
    if (stripTag(left) === stripTag(right)) return true;
    var base = function (n) {
      var parts = n.split("/");
      return parts[parts.length - 1];
    };
    var ab = base(left);
    var bb = base(right);
    if (ab === bb) return true;
    return stripTag(ab) === stripTag(bb);
  }

  function findModelInList(models, modelName) {
    if (!Array.isArray(models)) return null;
    return (
      models.find(function (m) {
        return equalsLooseModelName(m && m.name, modelName);
      }) || null
    );
  }

  function findModelCardElement(modelName) {
    var esc =
      typeof cssEscape === "function" ? cssEscape(String(modelName || "")) : String(modelName || "");
    var card = document.querySelector('.model-card[data-model-name="' + esc + '"]');
    if (!card) {
      document.querySelectorAll(".model-card[data-model-name]").forEach(function (el) {
        if (!card && equalsLooseModelName(el.dataset.modelName, modelName)) {
          card = el;
        }
      });
    }
    return card || null;
  }

  function capsFromModelCard(modelName) {
    var card = findModelCardElement(modelName);
    if (!card || !card.dataset) return null;
    var caps = {
      has_vision: triStateFlag(card.dataset.hasVision),
      has_tools: triStateFlag(card.dataset.hasTools),
      has_reasoning: triStateFlag(card.dataset.hasReasoning),
    };
    if (caps.has_tools === null) {
      var toolsIcon = card.querySelector(".capability-icon .fa-tools");
      if (toolsIcon) {
        var toolsWrap = toolsIcon.closest(".capability-icon");
        if (toolsWrap) {
          if (toolsWrap.classList.contains("enabled")) caps.has_tools = true;
          else if (toolsWrap.classList.contains("disabled")) caps.has_tools = false;
        }
      }
    }
    if (caps.has_vision === null && caps.has_tools === null && caps.has_reasoning === null) {
      return null;
    }
    return caps;
  }

  function applyModelCapsFromRecord(caps, record) {
    if (!record || typeof record !== "object") return;
    if (typeof record.has_vision === "boolean") caps.has_vision = record.has_vision;
    if (typeof record.has_tools === "boolean") caps.has_tools = record.has_tools;
    if (typeof record.has_reasoning === "boolean") caps.has_reasoning = record.has_reasoning;
  }

  async function resolveAskModelCapabilities(modelName) {
    var caps = { has_vision: null, has_tools: null, has_reasoning: null };
    var fromCard = capsFromModelCard(modelName);
    if (fromCard) applyModelCapsFromRecord(caps, fromCard);

    try {
      var responses = await Promise.all([
        fetch("/api/models/available"),
        fetch("/api/models/running"),
      ]);
      var availJr = await readApiJson(responses[0]);
      var runJr = await readApiJson(responses[1]);
      if (availJr.responseOk && availJr.data && Array.isArray(availJr.data.models)) {
        applyModelCapsFromRecord(caps, findModelInList(availJr.data.models, modelName));
      }
      if (runJr.responseOk && runJr.data && Array.isArray(runJr.data.models)) {
        applyModelCapsFromRecord(caps, findModelInList(runJr.data.models, modelName));
      }
    } catch (_) {}

    if (caps.has_tools === null || caps.has_vision === null) {
      try {
        var infoResp = await fetch("/api/models/info/" + encodeURIComponent(modelName));
        var infoJr = await readApiJson(infoResp);
        if (infoJr.responseOk && infoJr.data && typeof infoJr.data === "object") {
          var info = infoJr.data;
          if (caps.has_tools === null && Array.isArray(info.capabilities)) {
            var capSet = info.capabilities.map(function (c) {
              return String(c || "").toLowerCase();
            });
            if (capSet.indexOf("tools") >= 0 || capSet.indexOf("tool") >= 0) {
              caps.has_tools = true;
            } else if (capSet.length) {
              caps.has_tools = false;
            }
          }
          if (caps.has_vision === null && Array.isArray(info.capabilities)) {
            var visionSet = info.capabilities.map(function (c) {
              return String(c || "").toLowerCase();
            });
            if (
              visionSet.indexOf("vision") >= 0 ||
              visionSet.indexOf("image") >= 0 ||
              visionSet.indexOf("multimodal") >= 0
            ) {
              caps.has_vision = true;
            }
          }
        }
      } catch (_) {}
    }

    if (caps.has_vision === null) {
      var lower = normalizeModelName(modelName);
      if (/llava|vision|vl\b|bakllava|moondream|minicpm-v|gemma.*vision/i.test(lower)) {
        caps.has_vision = true;
      }
    }
    return caps;
  }

  function threadMessagesForApi() {
    return _askThread
      .filter(function (msg) {
        return (
          msg &&
          !msg.pending &&
          (msg.role === "user" || msg.role === "assistant") &&
          msg.content != null
        );
      })
      .map(function (msg) {
        return { role: msg.role, content: msg.content };
      });
  }

  function threadMessagesForHistory() {
    return _askThread
      .filter(function (msg) {
        return (
          msg &&
          (msg.role === "user" || msg.role === "assistant") &&
          (msg.content != null || msg.thinking)
        );
      })
      .map(function (msg) {
        var out = { role: msg.role, content: String(msg.content || "") };
        if (msg.thinking) out.thinking = String(msg.thinking);
        return out;
      });
  }

  function lastAssistantContent() {
    for (var i = _askThread.length - 1; i >= 0; i--) {
      if (_askThread[i].role === "assistant") {
        return String(_askThread[i].content || "").trim();
      }
    }
    return "";
  }

  function lastUserContent() {
    for (var i = _askThread.length - 1; i >= 0; i--) {
      if (_askThread[i].role === "user") {
        return String(_askThread[i].content || "").trim();
      }
    }
    return "";
  }

  function scrollAskThreadToBottom() {
    var thread = document.getElementById("askThread");
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  function renderAskThread() {
    var thread = document.getElementById("askThread");
    if (!thread) return;

    if (!_askThread.length) {
      thread.querySelectorAll(".ask-msg").forEach(function (el) {
        el.remove();
      });
      updateAskActionButtons();
      return;
    }

    thread.querySelectorAll(".ask-msg").forEach(function (el) {
      el.remove();
    });

    _askThread.forEach(function (msg, idx) {
      var isUser = msg.role === "user";
      var bubble = document.createElement("div");
      bubble.className =
        "ask-msg ask-msg--" + (isUser ? "user" : "assistant") + (msg.pending ? " ask-msg--pending" : "");
      bubble.dataset.index = String(idx);
      var bodyHtml = "";
      if (!isUser && msg.toolSteps && msg.toolSteps.length) {
        bodyHtml += '<div class="ask-msg-tools">';
        msg.toolSteps.forEach(function (step) {
          if (!step || !step.name) return;
          var label = step.phase === "result" ? "Tool result" : "Tool call";
          var detail = step.detail != null ? String(step.detail) : "";
          bodyHtml +=
            '<div class="ask-msg-tool-step ask-msg-tool-step--' +
            (step.phase === "result" ? "result" : "call") +
            '">' +
            '<div class="ask-msg-tool-step-label small text-muted">' +
            escapeHtml(label + ": " + step.name) +
            "</div>";
          if (detail) {
            bodyHtml +=
              '<div class="ask-msg-tool-step-body">' + escapeHtml(detail) + "</div>";
          }
          bodyHtml += "</div>";
        });
        bodyHtml += "</div>";
      }
      if (!isUser && msg.thinking) {
        bodyHtml +=
          '<div class="ask-msg-thinking">' +
          '<div class="ask-msg-thinking-label small text-muted mb-1">Reasoning</div>' +
          '<div class="ask-msg-thinking-body">' +
          escapeHtml(msg.thinking) +
          "</div></div>";
      }
      bodyHtml +=
        '<div class="ask-msg-body ask-msg-body--rich">' +
        (isUser
          ? renderAskMessageContent(msg.content || "")
          : renderAskMessageContent(msg.content || "", {
              streaming: !!msg.pending,
              pending: msg.pending && !msg.thinking && !msg.content,
            })) +
        "</div>";
      bubble.innerHTML =
        '<div class="ask-msg-label small text-muted mb-1">' +
        (isUser ? "You" : "Assistant") +
        "</div>" +
        bodyHtml;
      thread.appendChild(bubble);
    });
    if (typeof window.bindAskCodeCopyButtons === "function") {
      window.bindAskCodeCopyButtons(thread);
    }
    if (typeof window.highlightAskCodeBlocks === "function") {
      window.highlightAskCodeBlocks(thread);
    }
    scrollAskThreadToBottom();
    updateAskActionButtons();
  }

  function clearAskThread() {
    _askThread = [];
    renderAskThread();
  }

  function loadAskConversation(modelName, messages) {
    if (!modelName) return;
    _askModelName = modelName;
    var nameEl = document.getElementById("askModelModalName");
    if (nameEl) nameEl.textContent = modelName;
    _askThread = (messages || [])
      .filter(function (m) {
        return m && (m.role === "user" || m.role === "assistant") && m.content != null;
      })
      .map(function (m) {
        var entry = { role: m.role, content: String(m.content || "") };
        if (m.thinking) entry.thinking = String(m.thinking);
        return entry;
      });
    resetAskAttachments();
    renderAskThread();
    activateAskTab();
    var input = document.getElementById("askModelInput");
    if (input) {
      input.value = "";
      input.focus();
    }
    resolveAskModelCapabilities(modelName).then(function (caps) {
      _askModelCaps = caps;
      updateAskCapabilityHint();
    });
  }

  function updateAskActionButtons() {
    var hasReply = !!lastAssistantContent();
    var hasChat = _askThread.length > 0;
    var copyBtn = document.getElementById("askModelCopyBtn");
    var saveBtn = document.getElementById("askModelSaveBtn");
    if (copyBtn) copyBtn.disabled = !hasReply || _askIsSending;
    if (saveBtn) saveBtn.disabled = !hasChat || _askIsSending;
  }

  function setAskTyping(visible) {
    var row = document.getElementById("askTypingRow");
    if (row) row.style.display = visible ? "" : "none";
  }

  function updateAskCapabilityHint() {
    var hint = document.getElementById("askModelCapabilitiesHint");
    var imageBtn = document.getElementById("askAttachImageBtn");
    if (!hint) return;

    var parts = [];
    if (_askThread.length) {
      parts.push("Follow-up messages include earlier turns in this chat.");
    }
    if (_askModelCaps.has_tools === true) {
      parts.push("Agent mode: web search, fetch URL, and dashboard tools are available.");
    } else if (_askModelCaps.has_tools === false) {
      parts.push("This model does not support tools — web search is unavailable.");
    } else if (_askCapsLoading) {
      parts.push("Detecting model capabilities…");
    }
    if (_askModelCaps.has_vision === true) {
      parts.push("Vision: attach images for this model.");
    } else if (_askModelCaps.has_vision === false) {
      parts.push("This model is text-only — images are disabled.");
    }
    hint.textContent = parts.join(" ");

    if (imageBtn) {
      var hideImage = _askModelCaps.has_vision === false;
      imageBtn.hidden = hideImage;
      imageBtn.disabled = false;
      imageBtn.classList.remove("disabled");
      imageBtn.style.display = hideImage ? "none" : "";
      var imageInput = document.getElementById("askImageInput");
      if (imageInput) imageInput.disabled = hideImage;
    }
  }

  function renderAskAttachments() {
    var list = document.getElementById("askAttachmentsList");
    if (!list) return;
    if (!_askAttachments.length) {
      list.innerHTML = "";
      list.style.display = "none";
      return;
    }
    list.style.display = "";
    list.innerHTML = _askAttachments
      .map(function (att, idx) {
        var icon =
          att.type === "image"
            ? "fa-image"
            : att.type === "pdf"
              ? "fa-file-pdf"
              : att.type === "code"
                ? "fa-code"
                : "fa-file-word";
        return (
          '<span class="ask-attachment-chip badge bg-secondary me-1 mb-1">' +
          '<i class="fas ' +
          icon +
          ' me-1" aria-hidden="true"></i>' +
          escapeHtml(att.name || att.type) +
          '<button type="button" class="btn-close btn-close-white btn-sm ms-1 ask-attachment-remove" data-idx="' +
          idx +
          '" aria-label="Remove attachment"></button></span>'
        );
      })
      .join("");

    list.querySelectorAll(".ask-attachment-remove").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var i = parseInt(btn.getAttribute("data-idx"), 10);
        if (!isNaN(i)) {
          _askAttachments.splice(i, 1);
          renderAskAttachments();
        }
      });
    });
  }

  function resetAskAttachments() {
    _askAttachments = [];
    renderAskAttachments();
    var codeWrap = document.getElementById("askCodeSnippetWrap");
    if (codeWrap) codeWrap.style.display = "none";
    var codeInput = document.getElementById("askCodeInput");
    if (codeInput) codeInput.value = "";
  }

  async function addFileAttachment(file, type) {
    if (!file) return;
    var maxBytes = 8 * 1024 * 1024;
    if (file.size > maxBytes) {
      if (window.showNotification) showNotification("File exceeds 8 MB limit", "error");
      return;
    }
    try {
      var b64 = await readFileAsBase64(file);
      _askAttachments.push({ type: type, name: file.name, content: b64 });
      renderAskAttachments();
    } catch (err) {
      if (window.showNotification) showNotification(err.message || "Could not attach file", "error");
    }
  }

  function addCodeSnippet() {
    var wrap = document.getElementById("askCodeSnippetWrap");
    var input = document.getElementById("askCodeInput");
    var langSel = document.getElementById("askCodeLanguage");
    if (!wrap || !input) return;
    wrap.style.display = "";
    input.focus();
    if (langSel && !langSel.options.length) {
      CODE_LANGS.forEach(function (lang) {
        var opt = document.createElement("option");
        opt.value = lang;
        opt.textContent = lang;
        langSel.appendChild(opt);
      });
    }
  }

  function confirmCodeSnippet() {
    var input = document.getElementById("askCodeInput");
    var langSel = document.getElementById("askCodeLanguage");
    var wrap = document.getElementById("askCodeSnippetWrap");
    var text = (input && input.value ? input.value : "").trim();
    if (!text) {
      if (window.showNotification) showNotification("Paste code first", "warning");
      return;
    }
    var lang = langSel && langSel.value ? langSel.value : "text";
    _askAttachments.push({
      type: "code",
      name: "snippet." + lang,
      content: text,
      language: lang,
    });
    if (input) input.value = "";
    if (wrap) wrap.style.display = "none";
    renderAskAttachments();
  }

  function bindAskAttachmentControls() {
    var imageInput = document.getElementById("askImageInput");
    var pdfInput = document.getElementById("askPdfInput");
    var docInput = document.getElementById("askDocInput");
    var imageBtn = document.getElementById("askAttachImageBtn");
    var pdfBtn = document.getElementById("askAttachPdfBtn");
    var docBtn = document.getElementById("askAttachDocBtn");
    var codeBtn = document.getElementById("askAttachCodeBtn");
    var codeConfirm = document.getElementById("askCodeConfirmBtn");
    var newChatBtn = document.getElementById("askNewChatBtn");
    var copyBtn = document.getElementById("askModelCopyBtn");

    if (imageBtn && imageInput) {
      imageBtn.addEventListener("click", function () {
        imageInput.click();
      });
      imageInput.addEventListener("change", function () {
        Array.from(imageInput.files || []).forEach(function (f) {
          addFileAttachment(f, "image");
        });
        imageInput.value = "";
      });
    }
    if (pdfBtn && pdfInput) {
      pdfBtn.addEventListener("click", function () {
        pdfInput.click();
      });
      pdfInput.addEventListener("change", function () {
        if (pdfInput.files && pdfInput.files[0]) addFileAttachment(pdfInput.files[0], "pdf");
        pdfInput.value = "";
      });
    }
    if (docBtn && docInput) {
      docBtn.addEventListener("click", function () {
        docInput.click();
      });
      docInput.addEventListener("change", function () {
        if (docInput.files && docInput.files[0]) addFileAttachment(docInput.files[0], "doc");
        docInput.value = "";
      });
    }
    if (codeBtn) codeBtn.addEventListener("click", addCodeSnippet);
    if (codeConfirm) codeConfirm.addEventListener("click", confirmCodeSnippet);
    if (newChatBtn) {
      newChatBtn.addEventListener("click", function () {
        clearAskThread();
        resetAskAttachments();
        updateAskCapabilityHint();
        var input = document.getElementById("askModelInput");
        if (input) input.focus();
      });
    }
    if (copyBtn) copyBtn.addEventListener("click", copyAskModelResponse);
  }

  function getAttachmentMetadata() {
    return _askAttachments.map(function (att) {
      return { type: att.type, name: att.name || att.type };
    });
  }

  function getAskExchangeState() {
    var messages = threadMessagesForHistory();
    return {
      model: _askModelName,
      messages: messages,
      prompt: lastUserContent(),
      response: lastAssistantContent(),
      attachments: getAttachmentMetadata(),
    };
  }

  function activateAskTab() {
    var askTabBtn = document.getElementById("askTabBtn");
    if (askTabBtn && typeof bootstrap !== "undefined") {
      bootstrap.Tab.getOrCreateInstance(askTabBtn).show();
    }
  }

  async function copyAskModelResponse() {
    var text = lastAssistantContent();
    if (!text) {
      if (window.showNotification) showNotification("Nothing to copy yet", "warning");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      if (window.showNotification) showNotification("Response copied to clipboard", "success");
    } catch (err) {
      if (window.showNotification) showNotification("Could not copy to clipboard", "error");
    }
  }

  function ensureAskControlsBound() {
    if (_askControlsBound) return;
    _askControlsBound = true;
    bindAskAttachmentControls();
    var modalEl = document.getElementById("askModelModal");
    if (modalEl) {
      modalEl.addEventListener("hidden.bs.modal", function () {
        if (_askAbortController) {
          _askAbortController.abort();
          _askAbortController = null;
        }
        resetAskAttachments();
      });
    }
  }

  async function openAskModal(modelName, options) {
    options = options || {};
    if (!modelName) {
      if (window.showNotification) showNotification("Could not determine model name", "error");
      return;
    }
    ensureAskControlsBound();
    activateAskTab();
    _askModelName = modelName;
    _askAbortController = null;
    if (!options.keepThread) {
      clearAskThread();
      resetAskAttachments();
    }
    _askModelCaps = capsFromModelCard(modelName) || {
      has_vision: null,
      has_tools: null,
      has_reasoning: null,
    };
    _askCapsLoading = true;
    updateAskCapabilityHint();

    var nameEl = document.getElementById("askModelModalName");
    if (nameEl) nameEl.textContent = modelName;

    var input = document.getElementById("askModelInput");
    if (input) {
      if (!options.keepThread) input.value = "";
      input.onkeydown = function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendAskModelQuestion();
        }
      };
    }

    updateAskActionButtons();
    setAskTyping(false);

    var sendBtn = document.getElementById("askModelSendBtn");
    if (sendBtn) sendBtn.disabled = true;

    _askModelCaps = await resolveAskModelCapabilities(modelName);
    _askCapsLoading = false;
    updateAskCapabilityHint();

    if (sendBtn) sendBtn.disabled = false;

    var modalEl = document.getElementById("askModelModal");
    if (!modalEl || typeof bootstrap === "undefined") {
      if (window.showNotification) showNotification("Ask dialog unavailable (UI not loaded)", "error");
      return;
    }
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    modalEl.addEventListener(
      "shown.bs.modal",
      function onShown() {
        modalEl.removeEventListener("shown.bs.modal", onShown);
        if (input) input.focus();
      },
      { once: true },
    );
  }

  function parseStreamToken(parsed) {
    if (parsed.response != null) return String(parsed.response);
    var msg = parsed.message;
    if (msg && msg.content != null) return String(msg.content);
    return null;
  }

  function parseStreamThinking(parsed) {
    var msg = parsed.message;
    if (!msg || typeof msg !== "object") return null;
    var keys = ["thinking", "reasoning", "reasoning_content"];
    for (var i = 0; i < keys.length; i++) {
      var piece = msg[keys[i]];
      if (piece != null && String(piece)) return String(piece);
    }
    return null;
  }

  function formatToolStepDetail(name, payload) {
    if (payload == null) return "";
    if (typeof payload === "string") {
      try {
        payload = JSON.parse(payload);
      } catch (_) {
        return payload.length > 180 ? payload.slice(0, 180) + "…" : payload;
      }
    }
    if (typeof payload !== "object" || !payload) return "";
    if (name === "web_search" && Array.isArray(payload.results)) {
      return payload.results
        .slice(0, 3)
        .map(function (r) {
          return r && r.title ? String(r.title) : "";
        })
        .filter(Boolean)
        .join(" · ");
    }
    if (name === "fetch_url" && payload.url) {
      var text = String(payload.text || "");
      var preview = text.length > 120 ? text.slice(0, 120) + "…" : text;
      return String(payload.url) + (preview ? " — " + preview : "");
    }
    if (payload.query) return String(payload.query);
    if (payload.url) return String(payload.url);
    if (payload.error) return String(payload.error);
    return "";
  }

  function updatePendingAssistant(content, thinking, toolSteps) {
    for (var i = _askThread.length - 1; i >= 0; i--) {
      if (_askThread[i].role === "assistant") {
        if (content != null) _askThread[i].content = content;
        if (thinking != null) _askThread[i].thinking = thinking;
        if (toolSteps != null) _askThread[i].toolSteps = toolSteps.slice();
        _askThread[i].pending = false;
        break;
      }
    }
    renderAskThread();
  }

  function appendAssistantError(message) {
    _askThread.push({ role: "assistant", content: "Error: " + message, pending: false });
    renderAskThread();
  }

  function failPendingAssistant(message) {
    for (var i = _askThread.length - 1; i >= 0; i--) {
      if (_askThread[i].role === "assistant") {
        _askThread[i] = { role: "assistant", content: "Error: " + message, pending: false };
        renderAskThread();
        return;
      }
    }
    appendAssistantError(message);
  }

  async function consumeAgentStream(reader) {
    var decoder = new TextDecoder();
    var buffer = "";
    var assistantText = "";
    var thinkingText = "";
    var toolSteps = [];
    var gotFirstToken = false;

    function noteStreamActivity() {
      if (!gotFirstToken) {
        gotFirstToken = true;
        setAskTyping(false);
      }
    }

    function handleAgentEvent(evt) {
      if (!evt || !evt.type) return;
      if (evt.type === "thinking" && evt.text != null) {
        noteStreamActivity();
        thinkingText += evt.text;
        updatePendingAssistant(assistantText, thinkingText, toolSteps);
      } else if (evt.type === "content" && evt.text != null) {
        noteStreamActivity();
        assistantText += evt.text;
        updatePendingAssistant(assistantText, thinkingText, toolSteps);
      } else if (evt.type === "tool_call") {
        noteStreamActivity();
        toolSteps.push({
          phase: "call",
          name: String(evt.name || "tool"),
          detail: evt.arguments ? JSON.stringify(evt.arguments) : "",
        });
        updatePendingAssistant(assistantText, thinkingText, toolSteps);
      } else if (evt.type === "tool_result") {
        noteStreamActivity();
        toolSteps.push({
          phase: "result",
          name: String(evt.name || "tool"),
          detail: formatToolStepDetail(String(evt.name || ""), evt.content),
        });
        updatePendingAssistant(assistantText, thinkingText, toolSteps);
      } else if (evt.type === "error") {
        updatePendingAssistant("Error: " + (evt.message || "Request failed"), thinkingText, toolSteps);
      }
    }

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      var lines = buffer.split("\n");
      buffer = lines.pop();
      for (var i = 0; i < lines.length; i++) {
        var trimmed = lines[i].trim();
        if (!trimmed) continue;
        try {
          handleAgentEvent(JSON.parse(trimmed));
        } catch (_) {}
      }
    }
    if (buffer.trim()) {
      try {
        handleAgentEvent(JSON.parse(buffer.trim()));
      } catch (_) {}
    }
    if (!assistantText.trim() && !thinkingText.trim() && !toolSteps.length) {
      updatePendingAssistant("(No response text returned.)", "", toolSteps);
    }
  }

  async function consumeChatStream(reader) {
    var decoder = new TextDecoder();
    var buffer = "";
    var assistantText = "";
    var thinkingText = "";
    var gotFirstToken = false;

    function noteStreamActivity() {
      if (!gotFirstToken) {
        gotFirstToken = true;
        setAskTyping(false);
      }
    }

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      var lines = buffer.split("\n");
      buffer = lines.pop();
      for (var i = 0; i < lines.length; i++) {
        var trimmed = lines[i].trim();
        if (!trimmed) continue;
        try {
          var parsed = JSON.parse(trimmed);
          var think = parseStreamThinking(parsed);
          if (think != null) {
            noteStreamActivity();
            thinkingText += think;
            updatePendingAssistant(assistantText, thinkingText);
          }
          var token = parseStreamToken(parsed);
          if (token != null) {
            noteStreamActivity();
            assistantText += token;
            updatePendingAssistant(assistantText, thinkingText);
          }
        } catch (_) {}
      }
    }
    if (buffer.trim()) {
      try {
        var last = JSON.parse(buffer.trim());
        var tailThink = parseStreamThinking(last);
        if (tailThink != null) {
          thinkingText += tailThink;
          updatePendingAssistant(assistantText, thinkingText);
        }
        var tail = parseStreamToken(last);
        if (tail != null) {
          assistantText += tail;
          updatePendingAssistant(assistantText, thinkingText);
        }
      } catch (_) {}
    }
    if (!assistantText.trim() && !thinkingText.trim()) {
      updatePendingAssistant("(No response text returned.)", "");
    }
  }

  async function sendAskModelQuestion() {
    var input = document.getElementById("askModelInput");
    var question = (input && input.value ? input.value : "").trim();
    if (!question && !_askAttachments.length) {
      if (window.showNotification) showNotification("Enter a message or attach a file", "warning");
      return;
    }
    if (_askIsSending) return;
    if (_askCapsLoading) {
      if (window.showNotification) showNotification("Still detecting model capabilities…", "warning");
      return;
    }

    var sendBtn = document.getElementById("askModelSendBtn");
    _askModelCaps = await resolveAskModelCapabilities(_askModelName);
    updateAskCapabilityHint();
    var useAgent = _askModelCaps.has_tools === true;
    if (!useAgent && /search the web|look up online|current news|latest price|fetch url|browse the web/i.test(question)) {
      if (window.showNotification) {
        showNotification(
          "This model does not support tools, so web search is unavailable. Try a tool-capable model (e.g. qwen3, llama3.2).",
          "warning",
        );
      }
    }
    var attachmentsPayload = _askAttachments.length
      ? _askAttachments.map(function (att) {
          var out = { type: att.type, name: att.name };
          if (att.type === "code") {
            out.content = att.content;
            out.language = att.language || "text";
          } else {
            out.content = att.content;
          }
          return out;
        })
      : null;

    _askThread.push({ role: "user", content: question || "(attachment only)" });
    var apiMessages = threadMessagesForApi();
    _askThread.push({ role: "assistant", content: "", pending: true });
    renderAskThread();
    if (input) input.value = "";
    resetAskAttachments();

    _askIsSending = true;
    if (sendBtn) sendBtn.disabled = true;
    setAskTyping(true);
    updateAskActionButtons();

    if (_askAbortController) _askAbortController.abort();
    _askAbortController = new AbortController();

    var payload = {
      model: _askModelName,
      messages: apiMessages,
      stream: !useAgent,
    };
    if (attachmentsPayload) payload.attachments = attachmentsPayload;

    var endpoint = useAgent ? "/api/chat/agent" : "/api/chat";

    try {
      var resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: _askAbortController.signal,
      });

      if (!resp.ok) {
        var errMsg = "HTTP " + resp.status;
        try {
          var errJson = await resp.json();
          errMsg = errJson.error || errMsg;
        } catch (_) {}
        failPendingAssistant(errMsg);
        return;
      }

      if (useAgent) {
        await consumeAgentStream(resp.body.getReader());
      } else {
        await consumeChatStream(resp.body.getReader());
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        failPendingAssistant(err.message);
      } else {
        _askThread.pop();
        if (_askThread.length && _askThread[_askThread.length - 1].role === "user") {
          _askThread.pop();
        }
        renderAskThread();
      }
    } finally {
      _askIsSending = false;
      setAskTyping(false);
      if (sendBtn) sendBtn.disabled = false;
      _askAbortController = null;
      updateAskCapabilityHint();
      updateAskActionButtons();
      if (input) input.focus();
    }
  }

  window.openAskModal = openAskModal;
  window.sendAskModelQuestion = sendAskModelQuestion;
  window.askModalGetState = getAskExchangeState;
  window.askModalLoadConversation = loadAskConversation;
})();
