# 08 — Enhanced Input

Parent: [00_INDEX.md](./00_INDEX.md)

## Loop

```text
find existing IMC/IA assets → mirror naming → bind in PlayerController/Pawn
  → compile → human PIE input feel → memory
```

## Rules

1. Prefer Enhanced Input if fingerprint lists it — do not add legacy axis binds cold
2. Reuse existing `InputAction` / `InputMappingContext` assets when possible
3. Ask before changing default mapping contexts globally

## Verify

- Compiles · human PIE confirms bindings · paths in memory
