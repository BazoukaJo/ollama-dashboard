/** Ask? modal — streaming chat with optional attachments (image, PDF, Word, code). */
(function () {
  var _askModelName = null;
  var _askAbortController = null;
  var _askAttachments = [];
  var _askModelCaps = { has_vision: null };
  var _askControlsBound = false;

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

  function readFileAsText(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        resolve(String(reader.result || ""));
      };
      reader.onerror = function () {
        reject(reader.error || new Error("Could not read file"));
      };
      reader.readAsText(file);
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

  function capsFromModelCard(modelName) {
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
    if (!card || !card.dataset) return null;
    var vision = triStateFlag(card.dataset.hasVision);
    if (vision === null) return null;
    return { has_vision: vision, has_tools: null, has_reasoning: null };
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

    if (caps.has_vision === null) {
      var lower = normalizeModelName(modelName);
      if (/llava|vision|vl\b|bakllava|moondream|minicpm-v|gemma.*vision/i.test(lower)) {
        caps.has_vision = true;
      }
    }
    return caps;
  }

  function updateAskCapabilityHint() {
    var hint = document.getElementById("askModelCapabilitiesHint");
    var imageBtn = document.getElementById("askAttachImageBtn");
    if (!hint) return;

    var parts = [];
    if (_askModelCaps.has_vision === true) {
      parts.push("Vision: attach images for this model.");
    } else if (_askModelCaps.has_vision === false) {
      parts.push("This model is text-only — images are disabled.");
    } else {
      parts.push("Image attachments work best with vision-capable models.");
    }
    parts.push("PDF and Word text is extracted for all models.");
    parts.push("Code snippets are included in the prompt.");
    hint.textContent = parts.join(" ");

    if (imageBtn) {
      var hideImage = _askModelCaps.has_vision === false;
      imageBtn.hidden = hideImage;
      imageBtn.disabled = false;
      imageBtn.classList.remove("disabled");
      imageBtn.style.display = hideImage ? "none" : "";
      imageBtn.setAttribute(
        "title",
        hideImage
          ? "This model does not support images"
          : "Attach image (JPEG, PNG, GIF, WebP)",
      );
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
      if (window.showNotification) {
        showNotification("File exceeds 8 MB limit", "error");
      }
      return;
    }
    try {
      var b64 = await readFileAsBase64(file);
      _askAttachments.push({
        type: type,
        name: file.name,
        content: b64,
      });
      renderAskAttachments();
    } catch (err) {
      if (window.showNotification) {
        showNotification(err.message || "Could not attach file", "error");
      }
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
        if (pdfInput.files && pdfInput.files[0]) {
          addFileAttachment(pdfInput.files[0], "pdf");
        }
        pdfInput.value = "";
      });
    }
    if (docBtn && docInput) {
      docBtn.addEventListener("click", function () {
        docInput.click();
      });
      docInput.addEventListener("change", function () {
        if (docInput.files && docInput.files[0]) {
          addFileAttachment(docInput.files[0], "doc");
        }
        docInput.value = "";
      });
    }
    if (codeBtn) codeBtn.addEventListener("click", addCodeSnippet);
    if (codeConfirm) codeConfirm.addEventListener("click", confirmCodeSnippet);
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

  async function openAskModal(modelName) {
    if (!modelName) {
      if (window.showNotification) showNotification("Could not determine model name", "error");
      return;
    }
    ensureAskControlsBound();
    _askModelName = modelName;
    _askAbortController = null;
    resetAskAttachments();
    _askModelCaps = capsFromModelCard(modelName) || {
      has_vision: null,
      has_tools: null,
      has_reasoning: null,
    };
    updateAskCapabilityHint();

    var nameEl = document.getElementById("askModelModalName");
    if (nameEl) nameEl.textContent = modelName;

    var input = document.getElementById("askModelInput");
    if (input) {
      input.value = "";
      input.onkeydown = function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendAskModelQuestion();
        }
      };
    }

    var responseWrap = document.getElementById("askModelResponseWrap");
    if (responseWrap) responseWrap.style.display = "none";

    var responseEl = document.getElementById("askModelResponse");
    if (responseEl) responseEl.textContent = "";

    var spinner = document.getElementById("askModelSpinner");
    if (spinner) spinner.style.display = "none";

    var sendBtn = document.getElementById("askModelSendBtn");
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

    _askModelCaps = await resolveAskModelCapabilities(modelName);
    updateAskCapabilityHint();
  }

  async function sendAskModelQuestion() {
    var question = (document.getElementById("askModelInput")?.value || "").trim();
    if (!question && !_askAttachments.length) {
      if (window.showNotification) showNotification("Enter a question or attach a file", "warning");
      return;
    }

    var sendBtn = document.getElementById("askModelSendBtn");
    var spinner = document.getElementById("askModelSpinner");
    var responseWrap = document.getElementById("askModelResponseWrap");
    var responseEl = document.getElementById("askModelResponse");

    if (sendBtn) sendBtn.disabled = true;
    if (responseWrap) responseWrap.style.display = "";
    if (responseEl) responseEl.textContent = "";
    if (spinner) spinner.style.display = "";

    if (_askAbortController) _askAbortController.abort();
    _askAbortController = new AbortController();

    var payload = {
      model: _askModelName,
      prompt: question,
      stream: true,
    };
    if (_askAttachments.length) {
      payload.attachments = _askAttachments.map(function (att) {
        var out = { type: att.type, name: att.name };
        if (att.type === "code") {
          out.content = att.content;
          out.language = att.language || "text";
        } else {
          out.content = att.content;
        }
        return out;
      });
    }

    try {
      var resp = await fetch("/api/chat", {
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
        if (responseEl) responseEl.textContent = "Error: " + errMsg;
        if (spinner) spinner.style.display = "none";
        if (sendBtn) sendBtn.disabled = false;
        return;
      }

      if (spinner) spinner.style.display = "";

      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      var gotFirstToken = false;

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
            if (parsed.response != null) {
              if (!gotFirstToken) {
                gotFirstToken = true;
                if (spinner) spinner.style.display = "none";
              }
              if (responseEl) {
                responseEl.textContent += parsed.response;
                responseEl.scrollTop = responseEl.scrollHeight;
              }
            }
          } catch (_) {}
        }
      }
      if (buffer.trim()) {
        try {
          var last = JSON.parse(buffer.trim());
          if (last.response != null && responseEl) {
            responseEl.textContent += last.response;
            responseEl.scrollTop = responseEl.scrollHeight;
          }
        } catch (_) {}
      }
    } catch (err) {
      if (err.name !== "AbortError" && responseEl) {
        responseEl.textContent = "Error: " + err.message;
      }
    } finally {
      if (spinner) spinner.style.display = "none";
      if (sendBtn) sendBtn.disabled = false;
      _askAbortController = null;
    }
  }

  window.openAskModal = openAskModal;
  window.sendAskModelQuestion = sendAskModelQuestion;
})();
