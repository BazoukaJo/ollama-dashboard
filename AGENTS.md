# AGENTS.md — Local coding agent contract

Context for humans and agents. No training pipeline required.

## Mission

Help a human ship work using a **local** model with project markdown as durable brain.  
Long runs: autonomous **within ceilings** — see `docs/agent/LONGEVITY.md`.

Pillars:

1. **WEB** — `docs/agent/WEB.md` + `docs/agent/web/recipes/`
2. **GAME** — `docs/agent/unreal/00_INDEX.md` + recipes

Habits: tool-mediated edits · disk memory · recipe-first · fail→retry (max 3) · one task per turn

## Model size guidance

See `docs/agent/HARDWARE_LOCAL.md`.

| Hardware | Prefer |
|----------|--------|
| Tight VRAM/RAM | 4B; lean on recipes + memory |
| ~16GB VRAM / 64GB RAM | 9B Q8 agent; small model for autocomplete |
| Fallback | Set in `PROJECT.md`; use on empty/timeout |

## Authority

| Owns | Human | Agent |
|------|-------|-------|
| Product intent / scope | yes | no invent |
| Architecture / schema / net model | approve | propose |
| Merge / deploy / secrets | yes | no |
| Unreal visual / PIE ground truth | yes | draft + ask |
| Draft / search / refactor / tests | review | yes |
| Memory + TASKS | spot-check | required every milestone |

Never re-ask facts in `PROJECT.md` or `memory/working.md`.

## Startup

1. `AGENTS.md` (this)
2. `PROJECT.md`
3. `memory/working.md` (+ `queue.json` if used)
4. `TASKS.md`
5. Playbook (WEB and/or unreal + BRIDGE_LIMITS)
6. Long session → `MEMORY.md` + `LONGEVITY.md` + `FAILURE_RECOVERY.md`

## How to work

1. One queue item only
2. Inspect files — no guessed paths
3. Prefer recipes
4. Minimal diffs → verify
5. Checkpoint memory; status: `memory updated` / `task` / `retries` / `next`
6. On failure: gist → classify → fix → retry → continue or block

## Unreal gates

Bridge honesty + mutation policy from `PROJECT.md` / `BRIDGE_LIMITS.md`.  
Graphs: recipe → patch → compile → keep editable.

## Safety

No secrets · no force-push main · no destructive git unless asked · respect do-not-touch
