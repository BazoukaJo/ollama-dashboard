# Bridge limits — read before claiming Editor automation

## Default

Most installs have **`Live Unreal bridge? = no`** in `PROJECT.md`.

| Bridge value | Meaning |
|--------------|---------|
| `no` | MD + source + CLI only |
| `partial` | MCP/tools for **read/inspect** (see [12_MCP.md](./12_MCP.md)); writes still gated |
| `yes` | Documented automation may run; still honor art/ship human gates |

Also set **Mutation policy**: `read_only` | `lift_per_task` | `agent_may_edit` — see [13_HUMAN_STEPS_MUTATION.md](./13_HUMAN_STEPS_MUTATION.md).

## Hard STOP (bridge = no)

Do **not**:

- Claim you ran PIE / saw the viewport
- Claim Material/Niagara “looks correct”
- Invent successful `unreal.material.import_graph` / `unreal.pie.start` calls
- Mark visual tasks Done without human confirmation

Do:

- Produce editable plans, C++/config diffs, recipe patches
- Write PIE/log handoff templates (`01_EDITOR_SETTINGS_INI.md`)
- Set task status to need human PIE / art gate

## Bridge = yes

Only if `PROJECT.md` documents how (Python Remote Execution, MCP, custom tools).

Then:

1. Use only tools listed there
2. Still keep human gates for art / ship / architecture
3. Record tool observations in `memory/working.md`

## Upgrade path

Training repo / future plugins may add live `unreal.*` tools. Until fingerprint says yes, treat recipe `export_hint` as **future bridge ops**, not current capabilities.
