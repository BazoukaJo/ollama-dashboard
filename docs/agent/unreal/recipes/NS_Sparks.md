# Recipe: NS_Sparks

Domain: [05_NIAGARA.md](../05_NIAGARA.md) · Contract: [NS_Sparks.json](./NS_Sparks.json)

## Intent

Small **sparks / fountain** Niagara system from a Fountain-style emitter: spawn, velocity, color scale, sprite renderer. Starting point for hit sparks / welds — not a final art piece.

## Patch points

| Field | Default | Change when |
|-------|---------|-------------|
| `asset_path` | `/Game/FX/NS_Sparks` | Match FX folder in fingerprint |
| `user_params.Color` | warm orange | Art direction |
| Spawn rate / velocity | in stack | Perf budget / look |

## Steps

1. Confirm FX path in `PROJECT.md`
2. Create/update system from JSON (`editable: true`)
3. Compile + preview
4. Check particle budget
5. Human art/perf gate
6. Memory: path + recipe id `NS_Sparks`

## Verify

- [ ] Compiles
- [ ] Preview done (human or bridge)
- [ ] Budget note if dense
- [ ] Still editable

## Bridge hint

`unreal.niagara.import_stack` + compile + preview — see JSON `export_hint`.
