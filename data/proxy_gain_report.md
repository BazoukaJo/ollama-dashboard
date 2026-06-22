# Dashboard vs Default Ollama — Gain Report

**Machine:** 64 GB DDR5 · **Date:** 2026-06-22  
**Source:** `data/benchmark_tune_history.json` (7-model fleet, 2 rounds, compare mode)  
**Baseline:** Raw `http://127.0.0.1:11434` with `num_predict: 256`, `temperature: 0.2` only  
**Dashboard:** Saved settings from `model_settings.json` (benchmark compare caps dashboard `num_predict` at 1024 for speed)

---

## Executive summary

| Metric | Round 1 | Round 2 (final) |
|--------|---------|-----------------|
| **Fleet avg score** | 78.3 / 100 | **84.1 / 100** |
| **Avg proxy lift** | -2.2 pts | **+4.9 pts** |

**Bottom line:** After tuning, the fleet averages **84.1/100** with **+4.9 pts** lift vs raw Ollama. **`lfm2.5:latest`** still needs the proxy (+26 pts). **`gemma4`**, **`qwen3.6:27B`**, **`Qwen3-Coder-Next`**, and **`llama4`** tie or beat baseline on this text-only suite. **`qwen3-vl:8b`** underperformed on text prompts (vision model); settings were reset to the vision profile (`num_predict: 2048`, `top_k: 30`).

---

## 7-model fleet — round 2 scores

| Model | Dashboard | Raw Ollama | Lift | Passed (D / B) | Verdict |
|-------|------------|------------|------|----------------|---------|
| `gemma4:latest` | 96.2 | 96.2 | 0 | 10 / 10 | Raw OK; keep as routing hub |
| `qwen3.6:27B` | 96.2 | 96.2 | 0 | 10 / 10 | Raw OK for this suite |
| `Qwen3-Coder-Next:latest` | 96.2 | 96.2 | 0 | 10 / 10 | Raw OK for this suite |
| `llama4:latest` | 92.7 | 92.7 | 0 | 9 / 9 | On-demand frontier |
| `lfm2.5:latest` | 89.2 | 62.9 | **+26.3** | 9 / 6 | **Proxy required** |
| `llama3.1:8b-instruct-q4_K_M` | 75.9 | 84.9 | -9.0 | 7 / 8 | Reset to profile `num_predict: 2048` |
| `qwen3-vl:8b` | 42.3 | 25.2 | +17.1 | 5 / 3 | Vision model; text suite not representative |

**Fleet average lift (round 2):** **+4.9 pts**

---

## Params applied this run

| Model | Change |
|-------|--------|
| `gemma4:latest` | `copilot_think: off` (routing unchanged) |
| `lfm2.5:latest` | `copilot_think: off` |
| `llama4:latest` | `num_predict: 8192`, `copilot_think: off` |
| `qwen3-vl:8b` | Vision profile: `num_predict: 2048`, `top_k: 30`, `copilot_think: off` |
| `llama3.1:8b-instruct-q4_K_M` | `num_predict: 2048` (profile default; was 4096) |

**Benchmark tooling:** compare runs disable residency pins; dashboard `num_predict` capped at 1024 during benchmark only (production settings unchanged).

---

## Recommendations

1. **Always proxy** `lfm2.5:latest` and use proxy for IDE/agent features on all models (`num_ctx`, trim, routing, keep-alive).
2. **Default model:** `gemma4:latest` → routes to `qwen3.6:27B` / `Qwen3-Coder-Next:latest`.
3. **Do not use `qwen3-vl:8b` scores** to judge vision quality — this suite is text-only.
4. **Re-benchmark** after `qwen3-vl` / `llama3.1` profile reset if you want updated lift numbers.

---

## Artifacts

- `data/benchmark_tune_history.json` — full round 2 report (task `40d3865309ce`)
- `data/benchmark_run_latest.log` — console log
- `scripts/benchmark_tune_loop.py` — tune loop (2 rounds, auto-apply between rounds)
