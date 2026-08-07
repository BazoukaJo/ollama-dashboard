# 03 — Blueprints

Parent: [00_INDEX.md](./00_INDEX.md) · Recipes: [recipes/BP_InteractDoor.md](./recipes/BP_InteractDoor.md)

## When to use

Blueprint assets, EventGraph / functions / macros, variables, interfaces, BP compile errors.

## Loop

```text
prefer existing BP or recipe → patch vars/graph → compile BP
  → human PIE → keep editable → memory (asset path)
```

## Rules

1. **Recipe first** when creating common interactables / doors / pickups — see `recipes/`
2. Prefer extending an existing BP over parallel duplicates
3. Clear names; use functions/macros when the project already does
4. Keep graphs **editable** (export/import JSON if using bridge) — no opaque bake when further edits are expected
5. Replication flags only when fingerprint / human says multiplayer

## Verify ladder

1. BP compiles (0 errors)
2. Asset path recorded (`/Game/...`)
3. Human PIE for designer-visible behavior
4. `memory/working.md` updated

## Common failures → first move

| Symptom | First check |
|---------|-------------|
| Pin type mismatch | Cast / promote / wrong variable type |
| Accessed None | Default refs; BeginPlay order; soft refs |
| “Won’t compile” after parent C++ change | Recompile C++ module first, then BP |
| Duplicate logic | Search Content for existing BP before adding |

## Memory checkpoint

- Asset path + parent class
- Vars / events added
- Compile + PIE status
- Recipe id used (if any)
