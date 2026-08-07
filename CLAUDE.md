# CLAUDE.md — Claude Code (cloud or Ollama)

## Read first

- @AGENTS.md
- @PROJECT.md
- @docs/agent/COMMON_GATES.md
- @memory/working.md
- @docs/agent/MEMORY.md

Long runs also:

- @docs/agent/LONGEVITY.md
- @docs/agent/FAILURE_RECOVERY.md
- @docs/agent/HARDWARE_LOCAL.md

Playbooks:

- Web: @docs/agent/WEB.md and @docs/agent/web/recipes/README.md
- Unreal: @docs/agent/unreal/00_INDEX.md , @docs/agent/unreal/BRIDGE_LIMITS.md , @docs/agent/unreal/13_HUMAN_STEPS_MUTATION.md
- Autopilot: @docs/agent/AUTOPILOT.md if `tasks.json` exists

Keep @TASKS.md honest.

## Fingerprint + overlays

If `PROJECT.md` is still **Example —** / unfilled → stop; fill first.  
Root AGENTS/PROJECT/`01-*.mdc` win over synced kit docs.

## Bridge / mutation gate

If bridge is `no`/`partial` or mutation gated: do not claim PIE/visual success or invent write tool results.  
Use numbered tagged human steps when mutation is `read_only` / ungated `lift_per_task`.  
MCP: one call at a time; discover tools via Tool Search when needed.

## Local models / longevity

One task per turn. Status must include **memory updated**, **task**, **retries**, **next**.  
Fail → gist → retry (max 3) → continue. Compact before context fills. Prefer recipes over invention.  
Observe verify output before Done.

## Verify

Use PROJECT.md commands **and** Post-change / restart fields when defined. Honor human gates before Done.
