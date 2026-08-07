# Recipe: BP_InteractDoor

Domain: [03_BLUEPRINTS.md](../03_BLUEPRINTS.md) · Contract: [BP_InteractDoor.json](./BP_InteractDoor.json)

## Intent

Simple **interactable door** Actor BP: replicated `bIsOpen`, `OpenAngle`, BeginPlay + Interact + timeline rotation. Use as a template for similar interactables.

## Patch points

| Field | Default | Change when |
|-------|---------|-------------|
| `asset_path` | `/Game/Interactables/BP_Door` | Match Content layout |
| `parent_class` | `AActor` | Project door base class if one exists |
| `OpenAngle` | 90 | Design |
| `bIsOpen` replicated | true | Set false if single-player only |

## Steps

1. Search Content for an existing door/interact BP — extend it if better
2. Otherwise create from JSON contract (`editable: true`)
3. Wire mesh/collision in editor as project requires
4. Compile BP
5. Human PIE (open/close, replication if MP)
6. Memory: path + recipe id `BP_InteractDoor`

## Verify

- [ ] Compiles
- [ ] Interact path clear in EventGraph
- [ ] Human PIE gate
- [ ] Still editable

## Bridge hint

`unreal.blueprint.import_graph` + compile + PIE debug — see JSON `export_hint`.
