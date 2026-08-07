# WEB.md — Web development playbook

Use with `AGENTS.md` + `PROJECT.md` + [COMMON_GATES.md](./COMMON_GATES.md). Prefer [web/recipes/](./web/recipes/) over inventing process.

## Default loop

```text
spec → read existing code → select web recipe if fits → smallest change
  → lint/typecheck/test (PROJECT.md) → post-change/restart if defined
  → update memory
```

## Stacks

| Area | Typical tools |
|------|----------------|
| Frontend | JS/TS, HTML, CSS, React/Vue/etc. |
| Backend | Node, PHP, .NET/C#, Python |
| Data | JSON, XML, SQL |
| Quality | linter, unit/e2e, browser DevTools |

Match versions and package manager from `PROJECT.md`.

## Verify ladder (every web task)

Prefer a **command table** in `PROJECT.md` (task → cmdline). Minimum:

1. Lint / typecheck from `PROJECT.md`
2. Relevant unit/e2e if present (prefer **path-scoped** test when fixing one file)
3. Optional one-shot check script (`check.bat` / `npm run check`) if listed
4. Manual browser check only if UI — note result in memory
5. Checkpoint `memory/working.md` (paths + recipe id)

Done = those commands **observed** green (or explicit human gate).

## Post-change loop (running apps)

When `PROJECT.md` defines **Post-change** / restart / Dev URL:

1. After code that affects the running app → run the listed post-change commands (build/package/restart)
2. **Agent restarts** the local server when the project documents that — do not only tell the human to restart
3. Tell human to **hard-refresh** (`Ctrl+F5`) when static/CSS changed
4. Keep retrying start/verify until the app is up or retries exhausted (then block with gist)

Optional `PROJECT.md` fields: `Post-change:`, `Dev URL:`, `Restart required when:`.

## Invariants / single source of truth

Identify project SoT modules (theme/colors, schema, auth) from code or `PROJECT.md` — do not fork duplicates.  
In fidelity-sensitive domains (parsers, UI contracts): same input → stable counts/ids; treat drift as P0.

## Recipe catalog

See [web/recipes/README.md](./web/recipes/README.md):

- `next_zod_api` — typed API + Zod
- `auth_middleware` — reuse project auth
- `db_migration` — human-approved schema

## Inline loops (when no recipe fits)

### API change

Find existing handler pattern → mirror errors/auth → dual-side types → test → memory

### UI change

Locate component → reuse primitives → a11y basics if project cares → verify → memory

### Bug fix

Reproduce → smallest fail unit → fix root cause → re-run check → memory cause→fix

### Refactor

Invariant first → one layer → full verify

## Failure table

| Symptom | First move |
|---------|------------|
| Type errors | Fix types before feature creep |
| 401/CORS surprise | Match existing auth/CORS middleware |
| Migration fail | Stop; ask human; do not force prod |
| Test red | Read first failure only; gist to memory |
| Dev server dead after edit | Restart per PROJECT.md; hard-refresh |

## Cross-cutting

- Secrets: env **names** only; never paste values
- Prod flag checklists (when documented): do not regress `X=false` style gates
- Deps: ask before heavy new frameworks
- Migrations: human-approved architecture
- Done = verify + post-change commands pass

## When stuck

Re-read `PROJECT.md` → search similar feature → one intent question → `TASKS.md` Blocked
