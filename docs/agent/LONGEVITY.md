# LONGEVITY.md — Autonomous long-run protocol

For **small/local models** on limited VRAM (target gear: ~16GB VRAM, 64GB RAM).  
Chat is disposable. **Disk + queue** keep the run alive for hours.

Read with: `MEMORY.md` · `FAILURE_RECOVERY.md` · `HARDWARE_LOCAL.md` · root `TASKS.md`

## Goal

Stay useful overnight without the human re-explaining settled facts.

```text
boot → load disk → ONE queue item → act → verify → write memory
  → compact if needed → next item → … until stop / empty queue / hard block
```

## Turn protocol (every agent turn on a long run)

1. **Read** `memory/working.md` + `TASKS.md` (and `memory/queue.json` if present)
2. **Pick exactly one** pending/in-progress item — no multi-feature leaps
3. **Act** (smallest reversible step)
4. **Verify** using `PROJECT.md` commands (or handoff if mutation-gated)
5. **Write** working memory **before** claiming progress
6. **Status line must include:**
   - `memory updated: yes|no`
   - `task: <id or title>`
   - `retries: N`
   - `next: <one line>`
7. **Stop the turn** cleanly so the human/wrapper can clear context if needed

## Compact triggers (numeric guidance)

Aligned with training budgets (~8k context class local chats):

| Signal | Action |
|--------|--------|
| Soft (~75% context / long scroll) | Summarize into `working.md`; drop tool dumps |
| Hard (~92% / repeated plans) | Archive → `memory/archive/YYYYMMDD-HHMM.md` → reset narrative fields |
| After every milestone | Memory write (non-negotiable) |
| Empty/useless model reply | See `FAILURE_RECOVERY.md` — do not invent success |

Keep recent: goal, paths, last error, next step. Drop: verbose logs, duplicated reasoning.

## Queue rules

- Source of truth for humans: `TASKS.md`
- Optional machine queue: `memory/queue.json` (same items, status field)
- **Never invent product scope** to refill the queue — only deepen existing tasks or ask human
- On item done: mark done in both places; append one line to Decisions if settled
- On block: status `blocked` + what is needed; pick another item if safe, else stop

## Autonomy ceilings (honesty)

| Allowed without human | Requires human |
|----------------------|----------------|
| Search, draft, lint/typecheck, C++ compile loops | PIE/visual ground truth |
| Recipe plans, memory/queue hygiene | Architecture / schema / mutation lifts |
| First-error cook triage | Ship/cert, secrets, force-push |
| Compaction + archive | New feature invention |

If `PROJECT.md` mutation policy is `read_only` / `lift_per_task`, autonomy = **planning + numbered steps**, not silent Content edits.

## Heartbeat fields (working.md)

Keep these fresh on long runs:

- `turn` / `started`
- `active_task`
- `retries`
- `last_verify`
- `stop_reason` (empty if running)
- `bridge_mode` / `mutation_policy`

## Boot after crash / new chat

1. `memory/working.md` → Next step  
2. `TASKS.md` / `queue.json` → active item  
3. Do **not** restart the whole feature from zero  
4. If memory missing: rebuild from `PROJECT.md` + ask once

## Measurable SLOs (proven by `python -m src.kit_longevity_test`)

| SLO | Target |
|-----|--------|
| Context compact reduction when over budget | ≥40% tokens |
| First-error gist vs full log | ≤10% tokens |
| Disk settled-facts vs re-paste chat | ≥50% token save |
| Forever stub steps under budget | ≥8 steps, fill <95% |
| Retries before block | 3 |

Re-run after kit changes; report → `reports/kit_efficiency.json`.
