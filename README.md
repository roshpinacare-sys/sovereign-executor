# sovereign-executor — the free execution plane (smart separation)

**Why this repo exists:** private repos hit the org Actions spending wall (measured
2026-10-18: instant runner-startup failure, no logs, no check-runs). Public repos get
**unlimited free Actions minutes**. The owner's law: no payments, sovereign operation,
private content stays private. So the execution moves HERE — a public carrier — while
the private repos keep their content and stay private.

**The separation (owner directive «הפרדות חכמות»):**

| Plane | Where | Cost | What runs there |
|---|---|---|---|
| Content | private repos (unchanged) | — | the fleet's private state, books, keys |
| Execution | THIS repo (public) | free | read-only tasks over the fleet, pseudonymous receipts |
| Self-hosted | owner machines (`sovereign-runner-register.sh` in sovereign-runner-kit) | free | any lane, `runs-on: [self-hosted, sovereign]` — queues until a sovereign runner connects |

**Secret-surface law (hard):** this repo carries ONE secret (`SOVEREIGN_PAT`) and allows
ONLY `schedule` + `workflow_dispatch` triggers. No `pull_request` trigger may ever be
added — a fork PR could otherwise reach the secret. The beat itself re-reads this file;
reviewers enforce.

**What the beat runs (read-only until owner approves write-paths):**
- `private-census` — the full 43-repo census INCLUDING the 28 private repos (the
  visibility the CI default token cannot have), receipts pseudonymous `p-<sha256[:7]>`.
- `yield-snapshot` — the 1000/day bridge instrument: reads the live yield engine's
  receipts and emits the measured cadence + verdict, hourly.

**Adding a task:** edit `state/beat-tasks.json` + implement `task_<id>` in
`scripts/beat.py`. Read-only tasks need no approval; write-path tasks are owner-gated.
