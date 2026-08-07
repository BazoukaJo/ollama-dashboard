# HARDWARE_LOCAL.md — Run local agents on 16GB-class GPUs

Target profile (proven in this org):

| Spec | Value |
|------|--------|
| CPU | Modern multi-core (e.g. i9-class) |
| RAM | 64 GB comfortable / 32 GB minimum |
| GPU | **16 GB VRAM** (e.g. RTX 4070 Ti Super class) |

## Model routing (Ollama)

| Role | Prefer | Notes |
|------|--------|-------|
| Agent / chat / edits | `qwen3.5:9b-q8_0` (or similar 9B) | Fits 16GB when desktop load is moderate |
| Tight VRAM / parallel editor | `qwen3.5:4b` | Lower quality; more recipes + memory required |
| Autocomplete (Continue) | small coder 1.5B–3B | Do not use 9B for tab-complete |
| Embeddings (optional) | `nomic-embed-text` | Only if `@codebase` needed |

Put primary + fallback tags in `PROJECT.md`:

```text
Preferred Ollama model: qwen3.5:9b-q8_0
Fallback Ollama model: qwen3.5:4b
```

## Keep the box stable overnight

1. Close games / other GPU hogs before long runs  
2. Warm Ollama once: `ollama run <model> "ping"`  
3. Prefer project on **local SSD**, not OneDrive, for Unreal + heavy writes  
4. One heavy agent loop at a time (training + 9B agent + UE editor may thrash 16GB)  
5. If OS swap thrash: drop to 4B or pause editor PIE  

## Context

Local chats often behave like **~8k** usable context even if the model card claims more.  
Treat soft/hard compact in `MEMORY.md` / `LONGEVITY.md` as mandatory, not optional.

## Training vs daily agent

- **Daily coding:** this MD kit + Ollama in Cursor/VS Code/Claude Code  
- **Training loop:** UltimateTrainning repo separately (do not run both GPU-heavy jobs casually)  
