# Harness engineering

This repository follows the approach described in OpenAI's "Harness engineering: leveraging Codex in
an agent-first world" (Ryan Lopopolo, 11 February 2026, <https://openai.com/index/harness-engineering/>),
as already practiced in builder-core:

- **Humans steer, agents execute.** The engineer's job is the environment: maps, invariants, feedback loops.
- **AGENTS.md is a table of contents**, not a manual. Deep knowledge lives in `docs/` and is cross-linked.
- **The repository is the system of record.** What is not in it does not exist to an agent.
- **Enforce invariants mechanically**: layering, confinement, naming, size, logging, with remediation in the error text.
- **Plans are artifacts** with progress and decision logs. Tech debt is tracked and paid continuously.
- **Make the app legible to agents**: bootable per worktree, structured logs, health endpoints, drivable UI.

Local adaptations: no CI yet (D13), no beads (D12), Python and React rather than the post's stack.
