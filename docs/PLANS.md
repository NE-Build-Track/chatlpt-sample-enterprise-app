# Plans

Work larger than a small change has an **exec plan** in `docs/exec-plans/active/`. A plan names its
goal, scope, acceptance checks, a progress log and a decision log. It moves to `completed/` when its
acceptance checks pass, in the same commit. Known shortcuts go to
[tech-debt-tracker.md](exec-plans/tech-debt-tracker.md) with an owner and a trigger for paying them.

`scripts/check_docs.py` checks that every plan has those sections and that every link resolves.

## Order of work (D21)

| Plan | Goal | Status |
| --- | --- | --- |
| [plan-01-foundation](exec-plans/completed/plan-01-foundation.md) | Repository map, docs, decisions, scaffold of backend, UI, deploy and checks | completed 2026-10-19 |
| [plan-02-payments-stack](exec-plans/active/plan-02-payments-stack.md) | Compose with Batteries, signer and the shared allocation; first paid reply end to end | active |
| plan-03-accounts | Email/password, Google, GitHub, sessions, admin list | next |
| plan-04-chat-and-billing | Conversations, replies, context window, two books, admin page | next |
| plan-05-engine-streaming (builder-core) | `tasks/m3/mz/stream-support`: contract, transport, REST, tests | parallel with 02–04 |
| plan-06-streaming-adapter | Move the pin, swap `adapters/engine.py`, verify deltas end to end | after 05 |

Small changes do not need a plan; they need a test and a sentence in the commit.
