# 04 — Materials / shaders

Parent: [00_INDEX.md](./00_INDEX.md) · Recipes: [recipes/M_Master_Lit.md](./recipes/M_Master_Lit.md)

## When to use

Material graphs, Material Instances (MIC), parameters, domain/blend mode, shader compile issues.

## Loop

```text
select parent/recipe → patch params/nodes → keep editable
  → compile → human look + cost check → memory
```

## Rules

1. **Recipe first** for lit master materials — start from `M_Master_Lit` (or project parent listed in fingerprint)
2. Prefer MIC parameter changes over forking a new master when possible
3. Expose only needed parameters; match Content folder conventions from `PROJECT.md`
4. Keep graphs **editable** — never claim success with an uneditable bake if further art edits are expected
5. Respect perf budgets in fingerprint (instruction count / samples)

## Verify ladder

1. Material compiles
2. Parameters listed (name/type/default) in memory
3. Human validates look (+ rough cost if budget-sensitive)
4. Asset path(s) recorded (master + MIC if any)

## Common failures → first move

| Symptom | First check |
|---------|-------------|
| Missing connections | Recipe wires vs actual graph |
| Domain/blend mismatch | Opaque vs translucent use case |
| Texture sample errors | Samplers / SRGB / compression |
| Too expensive | Reduce samples; share parent; simplify |

## Memory checkpoint

- Master + MIC paths
- Params changed
- Recipe id
- Human look sign-off status
