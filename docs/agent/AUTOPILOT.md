# AUTOPILOT.md — Optional machine queue alongside TASKS.md

Some projects use a JSON queue (`tasks.json`) driven by a shell wrapper for overnight loops.  
This kit’s human-facing queue remains **`TASKS.md`**. Use both without drift.

## Rules

| File | Owner | Role |
|------|-------|------|
| `TASKS.md` | Human + agent | Readable queue / session handoff |
| `memory/queue.json` | Agent | Optional structured mirror |
| `tasks.json` (project) | Autopilot wrapper | If present, **one pending task per execution block** |

## When `tasks.json` exists

1. Read it at turn start  
2. Work **exactly one** pending item  
3. On complete: mark completed + update `global_context.current_summary_of_work` if that schema exists  
4. Mirror status into `TASKS.md` + `memory/working.md`  
5. Exit cleanly — do not chain the next autopilot task in the same turn  

## When only TASKS.md exists

Follow `LONGEVITY.md` turn protocol; optionally maintain `memory/queue.json`.

## Refill policy

Do **not** invent features to keep autopilot busy.  
Ask human for the next batch, or deepen an existing approved task (docs polish, verify, failure mining).
