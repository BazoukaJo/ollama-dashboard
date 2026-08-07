# COMMON_GATES.md — Shared hard gates (all pillars)

Synced from local-ai-dropin. Project lore stays in root `AGENTS.md` / `PROJECT.md` / `01-*.mdc`.

## 1. Fingerprint gate (before serious edits)

Refuse non-trivial work if `PROJECT.md`:

- Still titled **Example —** or looks like an unfilled template
- Has `_` / `_(…)_` placeholders in **active** Identity / Stack / Verify sections
- Lists verify commands that do not exist in this repo (`package.json` / scripts / CONTRIBUTING)

**Do instead:** fill fingerprint (or ask human once), then proceed. Prefer real scripts over a stale example table.

## 2. Overlay win order

1. Human intent this turn  
2. Root `PROJECT.md` + root `AGENTS.md` / `CLAUDE.md`  
3. Optional `.cursor/rules/01-*.mdc` (project overlay; **wins** over kit `00-*`)  
4. Synced kit: `docs/agent/**`, `.cursor/rules/00-local-agent.mdc`

Never put project lore into synced `docs/agent/` — it will be overwritten on kit sync.

## 3. Observe before “done”

- No Done without **observed** verify output (or explicit human gate)
- On retry: gist the prior failure → corrected action (don’t silently restart the plan)

## 4. Mutation / Unreal steps

Honor `PROJECT.md` mutation: `read_only` | `lift_per_task` | `agent_may_edit`.  
Under `read_only` or ungated `lift_per_task`: numbered tagged steps only — see `unreal/13_HUMAN_STEPS_MUTATION.md`.  
Never fake PIE / Content writes when bridge is `no`/`partial`.

## 5. Web post-change loop

If `PROJECT.md` defines **Post-change** / restart / Dev URL: after code changes that affect a running app, run those commands (build/package/restart). Agent restarts local servers when documented — tell human to hard-refresh (`Ctrl+F5`) when static assets change. Details: `WEB.md`.

## 6. Local model bar

See `HARDWARE_LOCAL.md`. If below optional `Minimum agent model` in `PROJECT.md`, prefer recipes + ask for a stronger model rather than silent low-quality edits.
