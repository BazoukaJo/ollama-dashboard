# 99 — Common Unreal failures

Parent: [00_INDEX.md](./00_INDEX.md)

On failure: gist **first** meaningful error into `memory/working.md` → one fix → retry.

| Symptom | Likely cause | First move |
|---------|--------------|------------|
| LNK2019 unresolved external | Missing module dep | `Build.cs` / `.uproject` modules |
| UHT / GENERATED_BODY errors | Macro order / missing include | Fix header macros; rebuild |
| Live Coding failed to apply | Incompatible change | Full UBT + editor restart |
| Accessed None | Null ref / init order | Soft refs; BeginPlay order; defaults |
| BP pin type mismatch | Wrong types after C++ change | Recompile C++; fix pins |
| Material compile error | Bad wire / domain | Compare to recipe; fix domain/blend |
| Niagara module error | Stack order / missing dep | Simplify emitter; check modules |
| Cook missing package | Bad ref / redirector | Fix reference; ask before mass redirector fix |
| Shader cook Fatal | Material/platform | First shader Error line only |
| Plugin failed to load | Version / dep | Engine version; `.uplugin` deps |
| Editor crash on hot reload | Static UObject* | Soft pointers; reduce statics |
| Map won't PIE | Bad GameMode/default pawn | Fingerprint anchors; log gist |

## After each fix

1. Re-run the same verify command
2. Update **Last error → fix** in memory
3. Continue queue — do not abandon
