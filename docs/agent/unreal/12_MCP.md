# 12 — Unreal Editor MCP (UE 5.8+)

Parent: [00_INDEX.md](./00_INDEX.md) · Limits: [BRIDGE_LIMITS.md](./BRIDGE_LIMITS.md)

Pattern distilled from real UE 5.8 projects (e.g. consumer installs). **Generic setup only** — project lore stays in that project's `CLAUDE.md` / `docs/`.

## What it is

UE 5.8 can run **Model Context Protocol** inside the editor (`ModelContextProtocol` plugin).

- Server: often `http://127.0.0.1:8000/mcp` (loopback)
- Transports: HTTP / SSE (not stdio)
- Usually needs **AllToolsets** (or equivalent) enabled or `tools/list` is empty
- Tool calls run **serially on the game thread** — never overlap MCP calls

## Fingerprint fields

In `PROJECT.md`:

| Field | Example |
|-------|---------|
| Live Unreal bridge? | `partial` (MCP read) / `yes` (writes allowed) / `no` |
| MCP URL | `http://127.0.0.1:8000/mcp` |
| Mutation policy | `read_only` / `lift_per_task` / `agent_may_edit` |

## Client config (Cursor example)

`.cursor/mcp.json` (project-owned — **not** overwritten by kit sync):

```json
{
  "mcpServers": {
    "unreal-local": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Also generate via editor when available: `ModelContextProtocol.GenerateClientConfig Cursor`

## Console commands (typical)

| Command | Effect |
|---------|--------|
| `ModelContextProtocol.StartServer [port]` | Start server |
| `ModelContextProtocol.StopServer` | Stop |
| `ModelContextProtocol.RefreshTools` | Re-poll tools after hot-reload |
| `ModelContextProtocol.GenerateClientConfig <Client\|All>` | Write client config |

Flags: `-ModelContextProtocolStartServer`, `-ModelContextProtocolPort=N`

## Tool Search mode

If `bEnableToolSearch` is on, `tools/list` may only show meta-tools (`list_toolsets`, `describe_toolset`, `call_tool`). **Discover** before assuming a full catalog.

## UltimateTrainning Python bridge

Training / harness repo can talk to the same Editor MCP without inventing PIE Done:

| Mode | Env / flag | Behavior |
|------|------------|----------|
| `dry_run` | default | In-memory harness (no Editor) |
| `live_readonly` | `UNREAL_BRIDGE_MODE=live_readonly` | Real MCP inspect; mutate rejected |
| `live_mutate` | `live_mutate` + `BRIDGE_MUTATION=1` + `BRIDGE_LIFT_TASK=<id>` | Content writes only after explicit lift |

```text
# From UltimateTrainning repo root (Editor must be running for live_*):
python -m src.unreal.bridge ping
python -m src.unreal.bridge --mode live_readonly list-toolsets
python -m src.unreal.bridge --mode live_readonly describe Editor
python -m src.unreal.bridge --mode live_readonly call GetSelectedActors
python -m src.unreal.bridge --mode dry_run catalog-smoke

# Optional coverage probe (soft-fails if Editor offline):
python -m src.unreal_feature_test --live-mcp
```

Config: `configs/bridge.yaml`, `configs/unreal_mcp_map.yaml`. Env: `UNREAL_MCP_URL`, `UNREAL_BRIDGE_MODE`, `BRIDGE_MUTATION`, `BRIDGE_LIFT_TASK`.

## Agent rules

1. Default MCP = **inspect / read** unless fingerprint says writes OK
2. No overlapping calls
3. Never claim PIE/visual success from MCP alone
4. If mutation is `lift_per_task`, wait for an explicit human lift naming the task
5. Prefer UT bridge CLI / `live_readonly` for discover/inspect; do not auto-promote bridge to `yes` / `agent_may_edit`
