# Manual probes (not pytest)

Scripts here require a **running dashboard** and/or **live Ollama**. They are not collected by pytest (`python_files = test_*.py` only).

| Script | Purpose |
|--------|---------|
| `live_api_stats.py` | Print `/api/system/stats` from localhost:5000 |
| `live_chat_models.py` | Print `/api/models/available` from localhost:5000 |
| `downloadable_models_probe.py` | Print downloadable model lists via `OllamaService` |

Run from the repo root, for example:

```bash
python tests/manual/live_api_stats.py
python tests/manual/downloadable_models_probe.py
```
