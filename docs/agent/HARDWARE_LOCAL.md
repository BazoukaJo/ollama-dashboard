# HARDWARE_LOCAL.md — Run local agents on 16GB-class GPUs

Target profile (proven in this org):

| Spec | Value |
|------|--------|
| CPU | Modern multi-core (e.g. i9-class) |
| RAM | 64 GB comfortable / 32 GB minimum |
| GPU | **16 GB VRAM** (e.g. RTX 4070 Ti Super class) |

## Model routing (Ollama / Opilot)

| Role | Prefer | Notes |
|------|--------|-------|
| Agent / chat / edits | `qwen3.5:9b-q8_0` (or similar 9B) | Fits 16GB when desktop load is moderate |
| Unreal Editor open | `lfm2.5` / 4B-class | Share VRAM with UE |
| Tight VRAM / parallel editor | `qwen3.5:4b` | Lower quality; more recipes + memory required |
| Autocomplete / inline | small coder / `lfm2.5` | Do **not** use 9B for tab-complete |
| Long agent tool loops | Gemma 12B agentic (optional) | Manual pick; one heavy model at a time |
| Embeddings (optional) | `nomic-embed-text` | Only if `@codebase` needed |
| Avoid on 16GB daily | `llama4` (~67GB), large MoE with UE open | Offload thrash |

Put tags in `PROJECT.md`:

```text
Preferred Ollama model: qwen3.5:9b-q8_0
Fallback Ollama model: qwen3.5:4b
Minimum agent model: qwen3.5:9b   # optional bar — below this, prefer recipes + ask
```

## Host alignment

- Editor `opilot.host` / `ollama.endpoint` / Claude `ANTHROPIC_BASE_URL` must hit the **same** daemon you intend (`http://127.0.0.1:11434` unless you use a deliberate proxy).
- After load/restart: brief settle + refresh model list before declaring “no models”.
- Switch models: stop the old one (`ollama stop` / Opilot Stop) before starting another heavy model.

## Keep the box stable overnight

1. Close games / other GPU hogs before long runs  
2. Warm Ollama once: `ollama run <model> "ping"`  
3. Prefer project on **local SSD**, not OneDrive, for Unreal + heavy writes  
4. One heavy agent loop at a time (training + 9B agent + UE editor may thrash 16GB)  
5. If OS swap thrash: drop to light model or pause editor PIE  

## Context

Local chats often behave like **~8k** usable context even if the model card claims more.  
Treat soft/hard compact in `MEMORY.md` / `LONGEVITY.md` as mandatory, not optional.  
Realistic `num_ctx` on 16GB: ~32k–65k (not 256k) alongside other apps.

## Training vs daily agent

- **Daily coding:** this MD kit + Ollama in Cursor/VS Code/Claude Code  
- **Training loop:** UltimateTrainning repo separately (do not run both GPU-heavy jobs casually)  
