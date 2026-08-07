# Recipe: M_Master_Lit

Domain: [04_MATERIALS_SHADERS.md](../04_MATERIALS_SHADERS.md) · Contract: [M_Master_Lit.json](./M_Master_Lit.json)

## Intent

Editable **opaque surface** master material: BaseColor × Tint, Normal, Roughness parameters. Prefer this (or project parent) over inventing a lit graph cold.

## Patch points

| Field | Default | Change when |
|-------|---------|-------------|
| `asset_path` | `/Game/Mats/M_Master_Lit` | Match fingerprint Content roots |
| `parameters` | BaseColor, Normal, Roughness, Tint | Add only if art needs more |
| `blend_mode` / `domain` | Opaque / Surface | Translucent/UI need different recipe |

## Steps

1. Confirm Material folder in `PROJECT.md`
2. Create/update master from JSON contract (keep `editable: true`)
3. Create MIC for instances; expose same params
4. Compile material
5. Human look + rough cost check
6. Memory: paths + recipe id `M_Master_Lit`

## Verify

- [ ] Compiles
- [ ] Params listed in memory
- [ ] Still editable (not baked opaque)
- [ ] Human look gate (MD-only) or bridge preview

## Bridge hint

`unreal.material.import_graph` + compile — see JSON `export_hint`.
