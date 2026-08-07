# 06 — Plugins / modules

Parent: [00_INDEX.md](./00_INDEX.md)

## When to use

`.uplugin`, plugin modules, enable/disable, editor tools exposed by plugins, hot-reload after plugin changes.

## Loop

```text
check fingerprint plugins → stub or edit with correct deps
  → note restart needs → human editor stability check → memory
```

## Rules

1. Prefer plugins already listed in `PROJECT.md` fingerprint
2. Ask before enabling heavy/new plugins that change architecture
3. `.uplugin` / module dependencies must be explicit; balanced Startup/Shutdown
4. Hot-reload safety: soft content refs; no dangling statics
5. Never mark “stable” without human opening the editor after enable/disable

## Verify ladder

1. Manifest / module names valid
2. Project still opens (human)
3. Restart flag recorded if required
4. Memory updated with plugin name + why

## Common failures → first move

| Symptom | First check |
|---------|-------------|
| Plugin failed to load | Engine version mismatch; missing dep module |
| Editor crash on reload | Static state; raw UObject* across reload |
| Missing third-party lib | `Build.cs` / runtime paths |

## Memory checkpoint

- Plugin name + path
- Enabled/disabled
- Restart required?
- Human open-test status
