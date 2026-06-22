/** Rich formatting for Ask? chat bubbles (fenced code, inline code, basic markdown). */
(function () {
  var LANG_ALIASES = {
    py: "python",
    python3: "python",
    js: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    sh: "bash",
    shell: "bash",
    zsh: "bash",
    yml: "yaml",
    "c++": "cpp",
    cc: "cpp",
    hpp: "cpp",
    "c#": "csharp",
    cs: "csharp",
    md: "markdown",
    golang: "go",
    rs: "rust",
    rb: "ruby",
    kt: "kotlin",
    kts: "kotlin",
    ps1: "powershell",
    pwsh: "powershell",
    docker: "dockerfile",
    html: "xml",
    htm: "xml",
    vue: "xml",
    sql: "sql",
    java: "java",
  };

  function escapeHtml(str) {
    if (typeof window.escapeHtml === "function") return window.escapeHtml(str);
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normalizeSource(text) {
    return String(text || "")
      .replace(/\uFF40/g, "`")
      .replace(/\r\n/g, "\n");
  }

  function normalizeHighlightLang(lang) {
    var key = String(lang || "")
      .trim()
      .toLowerCase();
    if (!key) return "";
    return LANG_ALIASES[key] || key;
  }

  function parseFenceHeader(infoLine) {
    var line = String(infoLine || "").trim();
    if (!line) return { lang: "", lead: "" };
    var m = line.match(/^([a-zA-Z#][\w#+\-.]*)(?:\s+(.*))?$/);
    if (!m) return { lang: "", lead: line };
    return { lang: m[1], lead: (m[2] || "").trim() };
  }

  function joinCodeLead(lead, body) {
    if (!lead) return body || "";
    if (!body) return lead;
    return lead + "\n" + body;
  }

  function splitMessageParts(text, streaming) {
    var src = normalizeSource(text);
    var parts = [];
    var i = 0;

    while (i < src.length) {
      var open = src.indexOf("```", i);
      if (open < 0) {
        var tail = src.slice(i);
        if (tail) parts.push({ type: "prose", text: tail });
        break;
      }

      if (open > i) {
        parts.push({ type: "prose", text: src.slice(i, open) });
      }

      var cursor = open + 3;
      var close = src.indexOf("```", cursor);
      var incomplete = false;

      if (close < 0) {
        close = src.length;
        incomplete = !!streaming;
      }

      var firstNl = src.indexOf("\n", cursor);
      var headerEnd;
      var codeStart;

      if (firstNl >= 0 && firstNl < close) {
        headerEnd = firstNl;
        codeStart = firstNl + 1;
      } else {
        headerEnd = close;
        codeStart = close;
      }

      var header = parseFenceHeader(src.slice(cursor, headerEnd));
      var code = src.slice(codeStart, close).replace(/\n$/, "");
      code = joinCodeLead(header.lead, code);

      parts.push({
        type: "code",
        lang: header.lang,
        text: code,
        incomplete: incomplete,
      });

      i = incomplete ? src.length : close + 3;
    }

    return parts;
  }

  function formatInlineProse(text) {
    var safe = escapeHtml(text);
    safe = safe.replace(/`([^`\n]+)`/g, function (_m, code) {
      return '<code class="ask-inline-code">' + code + "</code>";
    });
    safe = safe.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    safe = safe.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, function (_m, label, url) {
      return (
        '<a href="' +
        escapeHtml(url) +
        '" class="ask-prose-link" target="_blank" rel="noopener noreferrer">' +
        label +
        "</a>"
      );
    });
    return safe;
  }

  function proseToHtml(text) {
    var normalized = normalizeSource(text);
    if (!normalized.trim()) return "";
    var chunks = normalized.split(/\n{2,}/);
    return chunks
      .map(function (chunk) {
        var trimmed = chunk.trim();
        if (!trimmed) return "";
        var lines = formatInlineProse(trimmed).split("\n");
        return '<p class="ask-prose">' + lines.join("<br>") + "</p>";
      })
      .join("");
  }

  function codeBlockHtml(lang, code, incomplete) {
    var hlLang = normalizeHighlightLang(lang);
    var label = lang ? escapeHtml(lang) : hlLang ? escapeHtml(hlLang) : "code";
    var cls = "ask-code-block" + (incomplete ? " ask-code-block--streaming" : "");
    var codeClass = hlLang ? "language-" + escapeHtml(hlLang) : "";
    return (
      '<div class="' +
      cls +
      '">' +
      '<div class="ask-code-block-header">' +
      '<span class="ask-code-lang">' +
      label +
      "</span>" +
      '<button type="button" class="ask-code-copy-btn btn btn-sm btn-outline-secondary">Copy</button>' +
      "</div>" +
      '<pre class="ask-code-pre"><code class="' +
      codeClass +
      '">' +
      escapeHtml(code) +
      "</code></pre>" +
      "</div>"
    );
  }

  function formatAskMessageHtml(raw, options) {
    options = options || {};
    var text = normalizeSource(raw);
    if (!text) {
      return options.pending ? "…" : "";
    }

    var parts = splitMessageParts(text, !!options.streaming);
    var hasCode = parts.some(function (p) {
      return p.type === "code";
    });

    if (!hasCode) {
      return proseToHtml(text);
    }

    return parts
      .map(function (part) {
        if (part.type === "code") {
          return codeBlockHtml(part.lang, part.text, !!part.incomplete);
        }
        return proseToHtml(part.text);
      })
      .join("");
  }

  function highlightAskCodeBlocks(root) {
    var hljs = window.hljs;
    if (!hljs || typeof hljs.highlightElement !== "function") return;
    var scope = root || document.getElementById("askThread");
    if (!scope) return;
    scope.querySelectorAll("pre.ask-code-pre code").forEach(function (el) {
      var langClass = Array.prototype.find.call(el.classList, function (c) {
        return c.indexOf("language-") === 0;
      });
      var lang = langClass ? langClass.slice(9) : "";
      try {
        if (lang && hljs.getLanguage && !hljs.getLanguage(lang)) {
          el.classList.remove(langClass);
        }
        hljs.highlightElement(el);
      } catch (_) {
        /* partial stream or unknown grammar */
      }
    });
  }

  function bindAskCodeCopyButtons(root) {
    var container = root || document.getElementById("askThread");
    if (!container || container.dataset.askCopyBound === "1") return;
    container.dataset.askCopyBound = "1";
    container.addEventListener("click", function (e) {
      var btn = e.target.closest(".ask-code-copy-btn");
      if (!btn) return;
      e.preventDefault();
      var block = btn.closest(".ask-code-block");
      var codeEl = block && block.querySelector(".ask-code-pre code");
      if (!codeEl) return;
      var label = btn.textContent;
      navigator.clipboard
        .writeText(codeEl.textContent || "")
        .then(function () {
          btn.textContent = "Copied";
          setTimeout(function () {
            btn.textContent = label || "Copy";
          }, 1400);
        })
        .catch(function () {
          if (window.showNotification) window.showNotification("Could not copy code", "warning");
        });
    });
  }

  window.formatAskMessageHtml = formatAskMessageHtml;
  window.highlightAskCodeBlocks = highlightAskCodeBlocks;
  window.bindAskCodeCopyButtons = bindAskCodeCopyButtons;
  window._askSplitMessageParts = splitMessageParts;
})();
