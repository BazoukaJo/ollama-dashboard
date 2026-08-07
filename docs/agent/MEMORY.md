# MEMORY.md — Disk memory & compaction

Small local models fail mid-run when chat is the only memory. **Files outlive chat.**  
Long runs: also read `LONGEVITY.md` + `FAILURE_RECOVERY.md`.

## Budgets (treat as real)

For ~8k-class local chats (see `HARDWARE_LOCAL.md`):

| Trigger | Ratio / cue | Action |
|---------|-------------|--------|
| Soft | ~75% full / long scroll | Summarize into `working.md`; strip tool dumps |
| Hard | ~92% / repeated plans | Archive → reset narrative; keep goal/error/next |
| Milestone | every verify/decision | Write memory **before** next step |
| Observation | — | Cap pasted logs; gist first Error only (`max ~800` chars in chat) |

## Files

| File | Role |
|------|------|
| `memory/working.md` | Live scratchpad + heartbeat |
| `memory/queue.json` | Optional structured queue mirror |
| `memory/archive/` | Hard-compact snapshots |
| `PROJECT.md` | Stable truth + fingerprint |
| `TASKS.md` | Human-readable queue |
| `docs/agent/LONGEVITY.md` | Forever-run turn protocol |

## Compact-every-milestone

Update `working.md` after: decisions, build/test/PIE results, new paths, task done/blocked, human corrections, recovery from failure.

### Status proof (required on long runs)

```text
memory updated: yes
task: <name>
retries: 0
next: <one line>
```

## Archive rotation

1. Copy working body → `memory/archive/YYYYMMDD-HHMM.md`
2. Clear settled narrative; keep Decisions / Next step / domain fields / heartbeat
3. Point to archive path in working.md

## Forever-run

`LONGEVITY.md`: one queue item → act → verify → memory → compact → continue.  
Failures: `FAILURE_RECOVERY.md` (max 3 retries default).

## Recovery after restart

1. `working.md` Next step + heartbeat  
2. `TASKS.md` / `queue.json`  
3. Resume — do not restart the whole feature from zero  
