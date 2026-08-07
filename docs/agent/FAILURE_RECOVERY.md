# FAILURE_RECOVERY.md — Stay on the queue

Paired with `LONGEVITY.md`. Local models fail; the run must not.

## Loop

```text
fail → gist FIRST useful error into memory/working.md
     → classify → one fix → re-verify → retries++
     → if retries >= max_retries → blocked + next safe task (or stop)
```

Default `max_retries`: **3** per task (override in `PROJECT.md` if needed).

## Classify

| Class | Examples | First move |
|-------|----------|------------|
| `build` | UBT, tsc, lint | Fix one cause; re-run same command |
| `runtime` | crash, Accessed None | Narrow repro; null/init order |
| `tool` | ollama timeout, MCP down | Retry once; warm model; check localhost |
| `empty_model` | blank/useless reply | Re-prompt shorter; switch fallback model if configured |
| `intent` | missing product decision | Block; one clear question; do not invent |
| `verify` | tests red | First failure only; gist; fix |

## Empty / stuck model (common on local)

1. Shrink context: compact to disk now  
2. Re-state **only**: goal + path + last error + next command  
3. If `PROJECT.md` lists `Fallback Ollama model`, try once  
4. If still empty: `stop_reason: model_unresponsive` in memory; end turn  

Never fabricate tool results or “PIE passed”.

## What not to do

- Abandon the queue because the log is long  
- Paste entire logs into chat — **gist** only  
- Start unrelated refactors while fixing  
- Mark Done without verify  

## After recovery

- Update **Last error → fix**  
- `retries` back to 0 on success  
- Continue same task or next queue item  
