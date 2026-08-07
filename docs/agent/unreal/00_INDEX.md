# Unreal playbook — index

Use with `AGENTS.md` + filled **Unreal fingerprint** in `PROJECT.md`.  
Read [BRIDGE_LIMITS.md](./BRIDGE_LIMITS.md) before claiming any Editor automation.

## Rule

**Do not invent graph topology cold.**  
Select a recipe under `docs/agent/unreal/recipes/` → patch for this project → compile → **human PIE** (unless `Live Unreal bridge? = yes` in `PROJECT.md`) → update `memory/working.md`.

Recipe JSON is **`status: schematic`** until a bridge or Editor Python apply path exists — plans and handoffs, not fake tool success.

## Routing

| Task | Open |
|------|------|
| Overall loop / limits | This index + [BRIDGE_LIMITS.md](./BRIDGE_LIMITS.md) |
| Fingerprint | `PROJECT.md` |
| Editor / settings / PIE / logs | [01_EDITOR_SETTINGS_INI.md](./01_EDITOR_SETTINGS_INI.md) |
| C++ | [02_CPP.md](./02_CPP.md) |
| Blueprints | [03_BLUEPRINTS.md](./03_BLUEPRINTS.md) |
| Materials | [04_MATERIALS_SHADERS.md](./04_MATERIALS_SHADERS.md) |
| Niagara | [05_NIAGARA.md](./05_NIAGARA.md) |
| Plugins | [06_PLUGINS.md](./06_PLUGINS.md) |
| Cook / package | [07_BUILD_COOK_PACKAGE.md](./07_BUILD_COOK_PACKAGE.md) |
| Enhanced Input | [08_INPUT_ENHANCED.md](./08_INPUT_ENHANCED.md) |
| UI UMG/CommonUI | [09_UI_UMG.md](./09_UI_UMG.md) |
| Networking | [10_NETWORKING.md](./10_NETWORKING.md) |
| Animation | [11_ANIMATION.md](./11_ANIMATION.md) |
| Unreal MCP (5.8+) | [12_MCP.md](./12_MCP.md) |
| Human steps / mutation modes | [13_HUMAN_STEPS_MUTATION.md](./13_HUMAN_STEPS_MUTATION.md) |
| Failures encyclopedia | [99_FAILURES.md](./99_FAILURES.md) |
| Recipes | [recipes/README.md](./recipes/README.md) |

Compat stub: `docs/agent/GAME.md` → this index.

## Feature coverage (host training repo)

In UltimateTrainning (not required inside a consumer game):

```text
python -m src.unreal_feature_test
```

Dry-run harness exercises every `unreal.*` tool from create/edit/export/compile/debug through assets, C++, plugins, and PIE. Live Content mutation stays gated by `PROJECT.md` / human lift.

## Default loop

```text
spec → fingerprint → pattern or recipe → edit → compile → log clean
  → human PIE/visual if required → memory
```

## Authority

| Human owns | Agent owns |
|------------|------------|
| Design, look, fun, audio | Scaffold, wire, compile fixes |
| Architecture / net model | Propose only |
| PIE / viewport truth | Repro + need-PIE status |
| Ship / cert | Cook triage + first-error gist |

## Memory fields

Active map/GameMode · assets · modules dirty · restart? · last compile/cook/PIE · recipe ids · human gates · bridge mode
