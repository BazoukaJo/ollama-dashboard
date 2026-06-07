const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = 3000; // Your dashboard UI port
const OLLAMA_URL = 'http://127.0.0.1:11434';
const SETTINGS_FILE_PATH = path.join(__dirname, 'saved_parameters.json');

// Ensure database file exists on startup
if (!fs.existsSync(SETTINGS_FILE_PATH)) {
    fs.writeFileSync(SETTINGS_FILE_PATH, JSON.stringify({}, null, 2));
}

// 1. DASHBOARD UI INTERNAL SAVE ROUTE
// Update this path if your frontend calls a different endpoint to save settings
app.use(express.json());
app.post('/dashboard/api/save-settings', (req, res) => {
    try {
        const { model, parameters } = req.body;
        if (!model || !parameters) {
            return res.status(400).json({ error: 'Missing model or parameters configuration' });
        }

        const currentSettings = JSON.parse(fs.readFileSync(SETTINGS_FILE_PATH, 'utf8'));
        currentSettings[model] = parameters;

        fs.writeFileSync(SETTINGS_FILE_PATH, JSON.stringify(currentSettings, null, 2));
        return res.json({ success: true, message: `Parameters updated for ${model}` });
    } catch (error) {
        return res.status(500).json({ error: error.message });
    }
});

// 2. INCOMING REQUEST INTERCEPTOR & INTERMEDIARY
// Captures external payloads from VS Code to overwrite runtime configurations
app.use(['/api/chat', '/api/generate'], (req, res, next) => {
    const { model, options = {} } = req.body || {};

    if (model) {
        try {
            const savedData = JSON.parse(fs.readFileSync(SETTINGS_FILE_PATH, 'utf8'));
            const dashboardModelOptions = savedData[model];

            if (dashboardModelOptions) {
                // Merges settings. Dashboard parameters take complete precedence.
                req.body.options = {
                    ...options,
                    ...dashboardModelOptions
                };

                // Re-serialize the modified body string for the proxy target pipeline
                req.rawBody = JSON.stringify(req.body);
            }
        } catch (error) {
            console.error("Proxy parameter parsing interceptor error:", error);
        }
    }
    next();
});

// 3. UPSTREAM REVERSE PROXY TO OLLAMA CORE ENGINE
const ollamaProxy = createProxyMiddleware({
    target: OLLAMA_URL,
    changeOrigin: true,
    on: {
        proxyReq: (proxyReq, req, res) => {
            // Re-inject the updated options parameter configuration stream back into the pipeline
            if (req.rawBody && (req.method === 'POST' || req.method === 'PUT')) {
                proxyReq.setHeader('Content-Type', 'application/json');
                proxyReq.setHeader('Content-Length', Buffer.byteLength(req.rawBody));
                proxyReq.write(req.rawBody);
            }
        }
    }
});

// Forward all general API calls directly to Ollama
app.use('/api', ollamaProxy);

// 4. SERVE YOUR STATIC DASHBOARD WEB INTERFACE ASSETS
app.use(express.static(path.join(__dirname, 'public')));

app.listen(PORT, () => {
    console.log(`====================================================`);
    console.log(`🚀 Dashboard UI serving on: http://localhost:${PORT}`);
    console.log(`🔌 Route VS Code requests to: http://localhost:${PORT}`);
    console.log(`====================================================`);
});
