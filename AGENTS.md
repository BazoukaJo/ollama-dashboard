# AGENTS.md — Local coding agent contract

Context for humans and agents. No training pipeline required.

## Mission

Help a human ship work using a **local** model with project markdown as durable brain.  
Long runs: autonomous **within ceilings** — see `docs/agent/LONGEVITY.md`.

Pillars:

1. **WEB** — `docs/agent/WEB.md` + `docs/agent/web/recipes/`
2. **GAME** — `docs/agent/unreal/00_INDEX.md` + recipes

Habits: tool-mediated edits · disk memory · recipe-first · fail→retry (max 3) · one task per turn · **observe verify before Done**

Hard gates (all projects): `docs/agent/COMMON_GATES.md`.

## Fingerprint gate

If `PROJECT.md` is still an **Example —** stub, has unfilled `_` placeholders in active sections, or verify commands do not match this repo → **stop serious edits**. Fill fingerprint first (or ask once).

## Overlay win order

Root `PROJECT.md` / `AGENTS.md` / `CLAUDE.md` and optional `.cursor/rules/01-*.mdc` **win** over synced kit files (`docs/agent/**`, `00-local-agent.mdc`). Put lore in root or `01-*`, never in synced playbooks.

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
Proposals (`*-PROPOSAL.md`, unsigned numbers) ≠ law until human settles them.

## Startup

1. `AGENTS.md` (this) + `docs/agent/COMMON_GATES.md`
2. `PROJECT.md` — **fingerprint must be real**
3. `memory/working.md` (+ `queue.json` if used)
4. `TASKS.md`
5. Playbook (WEB and/or unreal + `BRIDGE_LIMITS.md`)
6. Long session → `MEMORY.md` + `LONGEVITY.md` + `FAILURE_RECOVERY.md`

## How to work

1. One queue item only
2. Inspect files — no guessed paths
3. Prefer recipes; identify project single-sources-of-truth (colors/schema/auth) before forking
4. Minimal diffs → **observe** verify output
5. Web: run **Post-change** / restart commands from `PROJECT.md` when defined
6. Checkpoint memory; status: `memory updated` / `task` / `retries` / `next`
7. On failure: gist → classify → fix → retry → continue or block

## Unreal gates

Bridge honesty + mutation policy from `PROJECT.md` / `BRIDGE_LIMITS.md`.  
Mutation modes + step glossary: `docs/agent/unreal/13_HUMAN_STEPS_MUTATION.md`.  
Graphs: recipe → patch → compile → keep editable.  
MCP: serial calls; Tool Search when catalog is meta-only (`unreal/12_MCP.md`).

## Safety

No secrets · no force-push main · no destructive git unless asked · respect do-not-touch · env **names** only
