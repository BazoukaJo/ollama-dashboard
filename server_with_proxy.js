// Optional companion proxy: makes the dashboard's saved per-model settings apply to
// EXTERNAL clients (VS Code's Ollama extension, `ollama run`, curl, LangChain, etc.)
// that talk to Ollama directly, not just to requests the dashboard itself sends.
//
// How it works: this server sits in front of the real Ollama API. Point external
// clients at this proxy's URL instead of Ollama's. For every /api/chat or
// /api/generate request it looks up the target model in the SAME model_settings.json
// file the dashboard reads/writes (see app/services/model_settings_helpers.py),
// merges the saved "settings" into the request's "options", and forwards the
// rewritten request upstream to Ollama. Also accepts /v1/chat/completions and /v1/completions
// (GitHub Copilot): merges saved settings into request options before forwarding.
// For Copilot with the /ollama URL prefix and CORS, prefer the Flask dashboard proxy
// at :5000/ollama (app/routes/proxy.py).
//
// This is an alternative to the dashboard's "Bake into Model" feature
// (POST /api/models/settings/<model>/bake): baking creates a derived model with
// PARAMETER directives in its Modelfile (works with zero extra running services, but
// can't express every option and requires clients to reference the derived model
// name). This proxy applies the *exact* saved settings to the *original* model name,
// for every request, but requires clients to point at this proxy's host:port instead
// of Ollama's.
//
// Run with: node server_with_proxy.js
// Configure with env vars (mirroring the Flask app's config):
//   OLLAMA_HOST           Ollama host (default: localhost). May itself be "host:port"
//                         (the form Ollama's OWN OLLAMA_HOST takes) — an embedded
//                         port wins over OLLAMA_PORT below; see resolveOllamaHostPort().
//   OLLAMA_PORT           Ollama port (default: 11434)
//   MODEL_SETTINGS_FILE   Path to model_settings.json (default: ./model_settings.json,
//                         same default the Flask app uses — point both at the same file)
//   PROXY_PORT            Port this proxy listens on (default: 11435)
//
// Port takeover: rather than pointing every client at this proxy individually, you
// can make EVERYTHING that assumes Ollama's default address (VS Code extensions,
// `ollama run`, curl, LangChain, ...) flow through it with zero per-client config:
//   1. Relocate the real Ollama off its default port — set OLLAMA_HOST=host:port
//      (e.g. 127.0.0.1:11436) in the environment that *launches Ollama*, and restart it.
//   2. Run this proxy with PROXY_PORT=11434 (Ollama's now-vacated default) and
//      OLLAMA_HOST/OLLAMA_PORT pointed at the relocated address from step 1.
// See docs/GUIDE.md > "Per-Model Settings: scope and limitations" for the full walkthrough.

const express = require('express');
const { createProxyMiddleware, fixRequestBody } = require('http-proxy-middleware');
const fs = require('fs');
const path = require('path');

const app = express();

// Mirrors _get_ollama_host_port() / _normalize_ollama_host_port_for_display() in the
// Python app (app/services/ollama_core.py, app/routes/main.py): splits an embedded
// port out of OLLAMA_HOST — taking precedence over OLLAMA_PORT — so naive
// `${OLLAMA_HOST}:${OLLAMA_PORT}` concatenation can't double-port it into
// "http://127.0.0.1:11436:11434". This is exactly the value Ollama's own OLLAMA_HOST
// expects when relocating it for the port-takeover pattern described above, so a
// single env var configures both the real Ollama and this proxy consistently.
function resolveOllamaHostPort(rawHost, rawPort) {
    let host = (rawHost || 'localhost').trim() || 'localhost';
    let port = parseInt(rawPort, 10);
    if (!Number.isFinite(port)) port = 11434;
    const embedded = /^([^:]+):(\d+)$/.exec(host);
    if (embedded) {
        host = embedded[1];
        port = parseInt(embedded[2], 10);
    }
    return { host, port };
}

const PROXY_PORT = parseInt(process.env.PROXY_PORT || '11435', 10);
const { host: OLLAMA_HOST, port: OLLAMA_PORT } = resolveOllamaHostPort(process.env.OLLAMA_HOST, process.env.OLLAMA_PORT || '11434');
const OLLAMA_URL = `http://${OLLAMA_HOST}:${OLLAMA_PORT}`;
const SETTINGS_FILE_PATH = path.resolve(process.env.MODEL_SETTINGS_FILE || path.join(__dirname, 'model_settings.json'));
const OLLAMA_DEFAULT_PORT = 11434;
const IS_PORT_TAKEOVER = PROXY_PORT === OLLAMA_DEFAULT_PORT;

function mergeOptionsForExternalProxy(incomingOptions, dashboardSettings) {
    const incoming = { ...(incomingOptions || {}) };
    const dashboard = { ...(dashboardSettings || {}) };
    // Saved dashboard values (including num_ctx) win over the client request.
    return { ...incoming, ...dashboard };
}

function loadModelSettings() {
    try {
        if (!fs.existsSync(SETTINGS_FILE_PATH)) return {};
        const raw = JSON.parse(fs.readFileSync(SETTINGS_FILE_PATH, 'utf8'));
        return (raw && typeof raw === 'object') ? raw : {};
    } catch (error) {
        console.error('Failed to read model settings file:', error.message);
        return {};
    }
}

// Mirrors normalize_model_settings_key()/lookup_settings_entry() in
// app/services/model_settings_helpers.py: keys are matched by stripped equality so
// minor whitespace differences between persisted keys and request model names don't matter.
function findSettingsForModel(modelSettings, modelName) {
    if (!modelName) return null;
    const want = String(modelName).trim();
    if (!want) return null;
    if (Object.prototype.hasOwnProperty.call(modelSettings, want)) {
        const entry = modelSettings[want];
        return (entry && typeof entry === 'object') ? entry.settings : null;
    }
    for (const key of Object.keys(modelSettings)) {
        if (String(key).trim() === want) {
            const entry = modelSettings[key];
            return (entry && typeof entry === 'object') ? entry.settings : null;
        }
    }
    return null;
}

// Merge saved per-model settings into inference request bodies before they reach Ollama.
function applySavedSettings(body) {
    const modelName = body && body.model;
    if (!modelName) return body;
    const savedSettings = findSettingsForModel(loadModelSettings(), modelName);
    if (savedSettings && typeof savedSettings === 'object') {
        return {
            ...body,
            options: mergeOptionsForExternalProxy(body.options, savedSettings),
        };
    }
    return body;
}

app.use(['/api/chat', '/api/generate', '/v1/chat/completions', '/v1/completions'], express.json(), (req, res, next) => {
    req.body = applySavedSettings(req.body || {});
    next();
});

// Mounted at root with pathFilter so the upstream request keeps the full path prefix.
const ollamaProxy = createProxyMiddleware({
    target: OLLAMA_URL,
    changeOrigin: true,
    pathFilter: (pathname) => pathname.startsWith('/api') || pathname.startsWith('/v1'),
    on: {
        // Re-serializes req.body (rewritten above by express.json() + our middleware)
        // back onto the proxied request — required because body-parser consumes the
        // original request stream. No-ops for routes where req.body was never parsed.
        proxyReq: fixRequestBody,
    },
});

app.use(ollamaProxy);

app.listen(PROXY_PORT, () => {
    console.log('====================================================');
    console.log(`Ollama settings-injecting proxy listening on: http://localhost:${PROXY_PORT}`);
    console.log(`Forwarding to Ollama at: ${OLLAMA_URL}`);
    console.log(`Reading saved settings from: ${SETTINGS_FILE_PATH}`);
    console.log('');
    if (IS_PORT_TAKEOVER) {
        console.log(`Port-takeover mode: this proxy has taken over Ollama's default port`);
        console.log(`(${OLLAMA_DEFAULT_PORT}). Existing clients need NO changes — anything that`);
        console.log("already assumes Ollama lives at its default address (VS Code extensions,");
        console.log('`ollama run`, curl, LangChain, ...) transparently flows through here now.');
        console.log('');
        console.log(`Make sure the REAL Ollama is actually running at ${OLLAMA_URL} (relocated`);
        console.log('via OLLAMA_HOST=host:port in the environment that launches it) — otherwise');
        console.log('this proxy and the real Ollama will fight over the same port.');
    } else {
        console.log('Point external clients (VS Code, ollama run, curl, etc.) at this URL');
        console.log("instead of Ollama's URL to apply your saved per-model settings.");
        console.log('');
        console.log('(Prefer zero client-side config? See "port takeover" in the file header');
        console.log('comment / README — run this with PROXY_PORT=11434 instead.)');
    }
    console.log('====================================================');
    console.log('NOTE: For GitHub Copilot, prefer the Flask dashboard proxy at');
    console.log(':5000/ollama (CORS + /ollama prefix). This Node proxy merges saved');
    console.log('settings on /api/chat, /api/generate, and /v1/chat/completions.');
    console.log('====================================================');
});
