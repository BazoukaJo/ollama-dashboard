# 05 — Niagara

Parent: [00_INDEX.md](./00_INDEX.md) · Recipes: [recipes/NS_Sparks.md](./recipes/NS_Sparks.md)

## When to use

Niagara systems/emitters/modules, user parameters, FX preview, particle budgets.

## Loop

```text
select recipe/template → patch emitters/params → compile
  → preview → human art/perf gate → memory
```

## Rules

1. **Recipe first** for common FX (sparks, bursts) — see `NS_Sparks`
2. Prefer project template emitters over inventing stacks cold
3. Keep stacks **editable**; document user params
4. Respect Niagara particle / GPU budgets in `PROJECT.md`
5. Do not mark “done” on look without human (MD-only mode)

## Verify ladder

1. System compiles
2. Preview attempted (human or bridge)
3. Budget note if dense FX
4. Asset path + recipe id in memory

## Common failures → first move

| Symptom | First check |
|---------|-------------|
| Module compile errors | Emitter module order / dependencies |
| Invisible particles | Renderer; material; spawn rate; bounds |
| Perf spike | Spawn rate; overdraw; reduce count |

## Memory checkpoint

- `/Game/...` path
- Emitters touched
- User params
- Preview / human sign-off
