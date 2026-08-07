# Local AI (Continue / VS Code)

1. Read `AGENTS.md`, `PROJECT.md`, and `docs/agent/COMMON_GATES.md` before non-trivial work
2. Fingerprint gate: if PROJECT.md is still Example/unfilled → stop and fill first
3. Project `.cursor/rules/01-*` and root AGENTS/CLAUDE win over kit `00-*`
4. Read `memory/working.md` at session start
5. Long runs: `docs/agent/LONGEVITY.md` + `FAILURE_RECOVERY.md` + `HARDWARE_LOCAL.md`
6. Web / Unreal playbooks + recipes under `docs/agent/`; web Post-change/restart when defined
7. One queue item per turn; status: memory updated / task / retries / next
8. Recipe -> patch -> observe verify; bridge honesty (no fake PIE)
9. Fail: gist -> fix -> retry (max 3) -> continue
10. No invented scope; no secrets; human owns architecture, merge, deploy, PIE/visual
