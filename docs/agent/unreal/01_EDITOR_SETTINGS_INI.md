# 01 — Editor / settings / PIE / logs

Parent: [00_INDEX.md](./00_INDEX.md)

## When to use

Project Settings, Editor Preferences, `Default*.ini` / `Config`, PIE start-stop handoff, Output Log triage.

## Loop

```text
read fingerprint → change one setting or reproduce in PIE
  → capture FIRST Error/Fatal gist → memory → human confirms viewport if visual
```

## Rules

1. Prefer documenting intended ini/setting keys in memory before large edits
2. One config concern per change set
3. **MD-only:** do not claim PIE success — write repro steps and ask human
4. **Bridge=yes only** (see `PROJECT.md`): may drive PIE/log tools if listed
5. Never commit machine-local `Saved/` or `Intermediate/` junk

## PIE handoff template (paste into memory)

```markdown
### PIE ask
- Map:
- What to try:
- Expected:
- Build/compile status before PIE:
```

## Log gist template

```markdown
### Log gist
- Source: Output Log / cook / UBT
- First Error/Fatal line:
- Likely module/asset:
- Fix attempted:
```

## Verify ladder

1. Setting/ini change noted
2. Compile clean if C++ involved
3. Human PIE if behavior/visual
4. Memory updated

## Common failures

| Symptom | First check |
|---------|-------------|
| Setting reverts | Wrong config hierarchy / Saved overrides |
| PIE crash on start | Last C++ change; missing default pawn/map |
| Spam warnings | Filter to first Error; ignore noise until Error clear |
