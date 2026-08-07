# Unreal recipes

**Policy:** select → patch → compile → human PIE (if bridge=no) → keep **editable**.

All bundled JSON: `schema_version: 1`, `status: schematic`, `apply_mode: human`  
(`export_hint` = future bridge ops only — see `../BRIDGE_LIMITS.md`)

| Id | Domain | Doc | JSON |
|----|--------|-----|------|
| `M_Master_Lit` | Material | [M_Master_Lit.md](./M_Master_Lit.md) | [M_Master_Lit.json](./M_Master_Lit.json) |
| `BP_InteractDoor` | Blueprint | [BP_InteractDoor.md](./BP_InteractDoor.md) | [BP_InteractDoor.json](./BP_InteractDoor.json) |
| `NS_Sparks` | Niagara | [NS_Sparks.md](./NS_Sparks.md) | [NS_Sparks.json](./NS_Sparks.json) |

## How to use

1. Read `.md` wrapper
2. Adapt `asset_path` to fingerprint Content roots
3. Apply as **plan / human editor work** (or bridge when `apply_mode` / PROJECT says so)
4. Compile + human gate
5. Record recipe id + path in memory
