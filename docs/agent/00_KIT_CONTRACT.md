# Kit contract (synced from local-ai-dropin)

This file is **overwritten** when UltimateTrainning syncs the drop-in kit into consumer projects.  
Put **project-specific** rules in root `AGENTS.md` / `CLAUDE.md` / `PROJECT.md` — those are never overwritten by sync.

## Mission

Help a human ship work using a local model with project markdown as durable brain.  
On long runs: be **autonomous within ceilings** — queue + memory + verify — not chat amnesia.

Pillars: **WEB** (`WEB.md` + `web/recipes/`) and/or **GAME** (`unreal/00_INDEX.md` + recipes).

## Long-run mandatory reads

- `LONGEVITY.md` — turn protocol (one task, status proof, compact)
- `MEMORY.md` — budgets + archive
- `FAILURE_RECOVERY.md` — retries / empty model
- `HARDWARE_LOCAL.md` — 16GB-class routing
- `AUTOPILOT.md` — if `tasks.json` exists

## Authority (default)

| Owns | Human | Agent |
|------|-------|-------|
| Product intent / scope | yes | no invent |
| Architecture / schema | approve | propose |
| Merge / deploy / secrets | yes | no |
| Unreal visual / PIE ground truth | yes | draft + ask |
| Draft / search / refactor / tests | review | yes (unless project AGENTS restricts) |
| `memory/working.md` + `TASKS.md` | spot-check | required every milestone |

## Startup

1. Root `AGENTS.md` (project overlays win)
2. `PROJECT.md` (models + mutation + bridge)
3. `memory/working.md` (+ `queue.json` if used)
4. `TASKS.md`
5. This contract + playbook + **LONGEVITY** if session will be long
6. Unreal: `BRIDGE_LIMITS.md` before any Editor claims

## Turn proof (long runs)

Every status must include: `memory updated` · `task` · `retries` · `next`

## Unreal bridge honesty

If bridge `no`/`partial` or mutation forbidden: never fake PIE/writes. See `unreal/BRIDGE_LIMITS.md`.

## Quality / safety

Concrete paths · observe verify output · max 3 retries then block · no secrets · no force-push main  
