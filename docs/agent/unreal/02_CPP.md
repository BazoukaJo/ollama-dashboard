# 02 — C++ / modules

Parent: [00_INDEX.md](./00_INDEX.md) · Fingerprint: `PROJECT.md`

## When to use

Gameplay code, `UObject`/`AActor` types, modules, `Build.cs`, UHT/`UPROPERTY`/`UFUNCTION`, Live Coding or UBT compile fixes.

## Loop

```text
match module + include style → small header/source diff
  → compile (PROJECT.md cmdline) → fix errors → PIE gate if visible → memory
```

## Rules

1. Match existing module / `Build.cs` / include style in-repo — do not invent a parallel module without approval
2. Prefer minimal diffs; keep UHT macros correct (`UCLASS`, `GENERATED_BODY`, categories)
3. Prefer `TSoftObjectPtr` / async load patterns already used in the project for content refs
4. Hot-reload safety: avoid fragile static state; tell human if editor restart is required
5. Never edit Engine source unless `PROJECT.md` explicitly allows it

## Verify ladder

1. Compile clean (Live Coding or full build per fingerprint)
2. Note module(s) touched in `memory/working.md`
3. If gameplay-visible → human PIE before “done”
4. If replicated → note net relevance / ownership assumptions (ask if unclear)

## Common failures → first move

| Symptom | First check |
|---------|-------------|
| LNK2019 / missing symbols | Module deps in `Build.cs` / `.uproject` |
| UHT errors | Macro placement, missing `GENERATED_BODY`, bad specifiers |
| Live Coding won’t apply | Full rebuild; restart editor |
| Access None at runtime | Init order; soft refs; null checks |

## Memory checkpoint

- Classes / modules touched
- Compile result
- Restart required?
- Next PIE ask (if any)
