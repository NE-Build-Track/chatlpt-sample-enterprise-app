# Core beliefs

Operating principles for humans and agents in this repository. Where a belief can be checked
mechanically, the enforcing test is named. They follow the harness-engineering approach: humans
steer, agents execute, and the repository is the only context an agent has.

## Product

1. **Two books.** Wholesale is what the network charged, from the engine. Retail is what the tokens
   are worth at list price, from the app. Both are shown; neither is derived from the other.
2. **Missing evidence is never zero.** A wholesale cost that has not arrived is `pending`. A reply
   whose payment went out but whose outcome is unknown is `uncertain`.
3. **The browser holds a session, nothing else.** No engine key, payment key or admin key reaches a
   client bundle, template, response or log.
4. **It should feel like ChatGPT.** Familiar layout and behavior lower the bar for users; the
   differences are the two cost numbers and the Livepeer attribution.
5. **One model, derived limits.** What the model can do (context window) is read from the runner,
   not hard-coded.

## Engineering

6. **Enforce invariants, not implementations.** Layering, third-party confinement, structured
   logging, file size and the money types are tests (`tests/structure/`) with remediation in their
   failure messages.
7. **Parse at the boundary.** Wire formats become frozen contract models in adapters; the UI parses
   responses with zod. No guessed shapes inside services or components.
8. **Boring, inspectable dependencies.** SQLAlchemy Core, argparse, server-sent events over
   WebSockets. Prefer code an agent can read end to end.
9. **The repository is the system of record.** Decisions, plans, evidence and prices live in
   `docs/`. If it isn't in the repository, an agent can't know it.
10. **Plans are artifacts.** Work larger than a small change has an exec plan with a progress log
    and a decision log, updated in the same commit as the code.
11. **Legible to agents.** The app boots per worktree, logs structured JSON, and exposes health, so
    an agent can run it, drive it, and read what happened.
12. **Generic over local.** A capability the engine lacks (streaming) is designed for builder-core,
    not patched into this app.
