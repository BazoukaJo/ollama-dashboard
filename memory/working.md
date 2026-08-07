# Working memory

Agents: update every milestone. Long runs: follow `docs/agent/LONGEVITY.md`.

## Session / heartbeat

- Goal:
- Status: `idle` / `in_progress` / `blocked` / `done`
- Pillar: `web` / `game` / `hybrid`
- Bridge mode: `no` / `partial` / `yes`
- Mutation policy: `read_only` / `lift_per_task` / `agent_may_edit`
- Started:
- Last compact at:
- Context pressure: `low` / `soft` / `hard`
- Active task:
- Retries: 0
- Last verify:
- Stop reason: _(empty if running)_
- Model primary / fallback:

## Decisions (settled — do not re-ask)

-

## Paths & artifacts

| Path | Why it matters |
|------|----------------|
| | |

## Unreal (game/hybrid)

| Field | Value |
|-------|-------|
| Active map / GameMode | |
| Assets touched (`/Game/...`) | |
| Modules dirty (need compile?) | |
| Editor restart required? | `yes` / `no` |
| Last compile / cook / PIE | |
| Recipe id(s) used | |
| Open human gates | |

## Web (web/hybrid)

| Field | Value |
|-------|-------|
| Routes / packages touched | |
| Recipe id(s) used | |
| Last lint/test result | |

## Last error → fix

- Class: `build` / `runtime` / `tool` / `empty_model` / `intent` / `verify`
- Gist:
- Fix:

## Next step

1.

## Archive pointers

- Latest archive:

## Queue

- Active task (see `TASKS.md` / `memory/queue.json`):
