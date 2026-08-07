# 07 — Build / cook / package

Parent: [00_INDEX.md](./00_INDEX.md)

## When to use

UBT compile, cook, BuildCookRun / package, shipping configs, cook error triage.

## Loop

```text
use exact PROJECT.md cmdlines → on fail capture FIRST meaningful error
  → one fix → re-run → memory (do not paste entire log into chat)
```

## Rules

1. Never invent cook flags — copy from fingerprint
2. Save error **gist** to `memory/working.md`, not megabyte logs in chat
3. Fix one root cause per iteration
4. Packaging/shipping sign-off is a **human gate**
5. Missing package / redirector issues: ask before mass-fix Content

## Verify ladder

1. Command exits successfully (or known acceptable warnings listed)
2. Output path noted (packaged dir)
3. Human ship/playtest gate if claiming release readiness
4. `TASKS.md` updated

## Common failures → first move

| Symptom | First check |
|---------|-------------|
| Missing package / can’t find asset | References; redirectors; cook maps list |
| Shader cook fail | Material domain; platform; first shader error line |
| UBT fail | Module deps; include; generated headers |
| Long opaque log | Search first `Error:` / `Fatal:` → gist only |

## Memory checkpoint

- Command used
- First error → fix
- Output path
- Human package sign-off status
