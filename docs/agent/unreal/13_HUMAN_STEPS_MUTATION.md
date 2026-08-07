# 13 — Human step glossary + mutation modes

Parent: [00_INDEX.md](./00_INDEX.md)

Useful when the human is learning the editor, or the project forbids silent Content edits (large World Partition / shipping risk).

## Mutation modes (set in PROJECT.md)

| Mode | Agent may | Agent must |
|------|-----------|------------|
| `read_only` | Read code/docs; MCP inspect | Output **numbered manual steps** only |
| `lift_per_task` | Edit only after human lifts a **named** task | Minimal diffs; verify; re-lock when done |
| `agent_may_edit` | Normal kit edit loop | Still respect human gates (PIE/art/ship) |

## Step glossary (tag every human instruction)

| Tag | Meaning |
|-----|---------|
| `[UI]` | Click-path: `Menu > Submenu > Item` |
| `[CONSOLE]` | Editor console (backtick) |
| `[CMD]` | OS terminal |
| `[BP]` | Blueprint graph — node names in backticks |
| `[ASSET]` | Content asset with full `/Game/...` path |
| `[CPP]` | C++ file + class |
| `[PY]` | Editor Python |
| `[VERIFY]` | How to confirm before next step |

## Proposal vs settled docs

| Pattern | Meaning |
|---------|---------|
| `docs/*-PROPOSAL.md` | Not settled — do not treat numbers as law |
| `docs/00-*.md` pitch / SoT | Intent source of truth when project says so |
| `docs/*-rating.md` / policy | Binding content/audience rules if present |

**One decision at a time:** do not invent floor counts, economies, or cast lists and present them as approved.

## OneDrive / sync folders

Prefer a **non-synced** disk path for Unreal project roots (`Saved/`, `Intermediate/`, DDC lock badly with cloud sync). Note the preferred path in `PROJECT.md` if different from the opened folder.
