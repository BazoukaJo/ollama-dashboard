# Local AI (Continue / VS Code)

1. Read `AGENTS.md` and `PROJECT.md` before non-trivial work
2. Read `memory/working.md` at session start
3. Long runs: `docs/agent/LONGEVITY.md` + `FAILURE_RECOVERY.md` + `HARDWARE_LOCAL.md`
4. Web / Unreal playbooks + recipes under `docs/agent/`
5. One queue item per turn; status: memory updated / task / retries / next
6. Recipe -> patch -> verify; bridge honesty (no fake PIE)
7. Fail: gist -> fix -> retry (max 3) -> continue
8. No invented scope; no secrets; human owns architecture, merge, deploy, PIE/visual
