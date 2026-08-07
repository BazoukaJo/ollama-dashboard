# Kit contract (synced from local-ai-dropin)

This file is **overwritten** when UltimateTrainning syncs the drop-in kit into consumer projects.  
Put **project-specific** rules in root `AGENTS.md` / `CLAUDE.md` / `PROJECT.md` / `.cursor/rules/01-*.mdc` — those are never overwritten by sync.

Also read: **[COMMON_GATES.md](./COMMON_GATES.md)** (fingerprint, overlays, observe-before-done, mutation, web post-change).

## Sync boundary

| Synced (kit owns) | Never overwritten (project owns) |
|-------------------|----------------------------------|
| `docs/agent/**` | `PROJECT.md`, `AGENTS.md`, `CLAUDE.md`, `TASKS.md` |
| `.cursor/rules/00-local-agent.mdc` | `.cursor/rules/01-*.mdc` |
| `.continue/rules/00-*`, `.github/copilot-instructions.md` | `memory/working.md`, design `docs/0*.md`, MCP configs |

**Overlays win:** root AGENTS/PROJECT/`01-*.mdc` beat this contract when they conflict.

## Mission

Help a human ship work using a local model with project markdown as durable brain.  
On long runs: be **autonomous within ceilings** — queue + memory + verify — not chat amnesia.

Pillars: **WEB** (`WEB.md` + `web/recipes/`) and/or **GAME** (`unreal/00_INDEX.md` + recipes).

## Long-run mandatory reads

- `COMMON_GATES.md` — hard gates every turn
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
2. `PROJECT.md` — **must not be an Example stub**; fingerprint complete
3. `COMMON_GATES.md`
4. `memory/working.md` (+ `queue.json` if used)
5. `TASKS.md`
6. This contract + playbook + **LONGEVITY** if session will be long
7. Unreal: `BRIDGE_LIMITS.md` + `13_HUMAN_STEPS_MUTATION.md` before Editor claims

## Turn proof (long runs)

Every status must include: `memory updated` · `task` · `retries` · `next`  
Done requires **observed** verify (or explicit human gate).

## Unreal bridge honesty

If bridge `no`/`partial` or mutation forbidden: never fake PIE/writes. See `unreal/BRIDGE_LIMITS.md`.  
Mutation modes: `unreal/13_HUMAN_STEPS_MUTATION.md`. MCP serial + Tool Search: `unreal/12_MCP.md`.

## Quality / safety

Concrete paths · observe verify output · max 3 retries then block · no secrets · no force-push main  
Web post-change/restart when `PROJECT.md` defines them (`WEB.md`).
