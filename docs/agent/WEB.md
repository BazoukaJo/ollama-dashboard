# WEB.md — Web development playbook

Use with `AGENTS.md` + `PROJECT.md`. Prefer [web/recipes/](./web/recipes/) over inventing process.

## Default loop

```text
spec → read existing code → select web recipe if fits → smallest change
  → lint/typecheck/test (PROJECT.md) → update memory
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

1. Lint / typecheck from `PROJECT.md`
2. Relevant unit/e2e if present
3. Manual browser check only if UI — note result in memory
4. Checkpoint `memory/working.md` (paths + recipe id)

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

## Cross-cutting

- Secrets: env **names** only
- Deps: ask before heavy new frameworks
- Migrations: human-approved architecture
- Done = verify commands pass

## When stuck

Re-read `PROJECT.md` → search similar feature → one intent question → `TASKS.md` Blocked
