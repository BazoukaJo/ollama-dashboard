# 10 — Networking / replication primer

Parent: [00_INDEX.md](./00_INDEX.md)

## Authority

Replication model and net architecture are **human-approved**. Agent proposes only.

## Loop

```text
check fingerprint (SP vs MP) → match existing replicated props/RPCs
  → compile → human multiplayer PIE → memory
```

## Rules

1. Do not add `replicated` flags casually on SP projects
2. Mirror existing ownership / RPC patterns in-repo
3. Ask before introducing new net driver or listen-server assumptions

## Verify

- Compiles · human MP PIE if relevant · document assumptions in memory
