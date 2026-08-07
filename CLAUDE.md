# CLAUDE.md — Claude Code (cloud or Ollama)

## Read first

- @AGENTS.md
- @PROJECT.md
- @memory/working.md
- @docs/agent/MEMORY.md

Long runs also:

- @docs/agent/LONGEVITY.md
- @docs/agent/FAILURE_RECOVERY.md
- @docs/agent/HARDWARE_LOCAL.md

Playbooks:

- Web: @docs/agent/WEB.md and @docs/agent/web/recipes/README.md
- Unreal: @docs/agent/unreal/00_INDEX.md and @docs/agent/unreal/BRIDGE_LIMITS.md
- Autopilot: @docs/agent/AUTOPILOT.md if `tasks.json` exists

Keep @TASKS.md honest.

## Bridge gate

If bridge is `no`/`partial` or mutation gated: do not claim PIE/visual success or invent write tool results.

## Local models / longevity

One task per turn. Status must include **memory updated**, **task**, **retries**, **next**.  
Fail → gist → retry (max 3) → continue. Compact before context fills. Prefer recipes over invention.

## Verify

Use PROJECT.md commands and human gates before Done.
