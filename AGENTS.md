# AGENTS.md

This file is a **map**, not a manual. Read the linked documents when a task touches them.

## What this repository is

**ChatLPT** is a sample enterprise application: a ChatGPT-style chat product built on the
[livepeer-builder](https://github.com/NE-Build-Track/livepeer-builder-core) engine in **embedded
mode**. One Python process runs the FastAPI backend, the embedded engine, and serves the React UI.
It pays Livepeer orchestrators for `blueclaw/chat/qwen3.8-27b` through a self-hosted remote signer
and Clearinghouse Batteries, and it keeps two books: **wholesale** network cost from the engine and
**retail** cost from the tokens each user consumed, priced from Alibaba Cloud's Qwen list prices.

It also exists to show how an enterprise app is built with agents: the repository is the system of
record, invariants are tests, and plans are artifacts (the harness-engineering approach in
[docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md)).

## Start here

| You need | Read |
| --- | --- |
| Why the project exists, assumptions, how to build and run | [README.md](README.md) |
| The layers, and what may import what | [ARCHITECTURE.md](ARCHITECTURE.md) |
| What we are building, and what is out of scope | [docs/product-specs/chatlpt.md](docs/product-specs/chatlpt.md) |
| Why something was decided | [docs/design-docs/decisions.md](docs/design-docs/decisions.md) |
| The rules every change follows | [docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md) |
| Streaming through the engine (generic design for builder-core) | [docs/design-docs/streaming-through-the-engine.md](docs/design-docs/streaming-through-the-engine.md) |
| What to work on, and its acceptance | [docs/exec-plans/active/](docs/exec-plans/active/) and [docs/PLANS.md](docs/PLANS.md) |
| Known gaps and shortcuts | [docs/exec-plans/tech-debt-tracker.md](docs/exec-plans/tech-debt-tracker.md) |
| The engine, the runner, the orchestrators, the prices | [docs/references/index.md](docs/references/index.md) |
| Operating, configuring, backing up | [docs/RELIABILITY.md](docs/RELIABILITY.md) |
| Secrets, credentials, trust boundaries | [docs/SECURITY.md](docs/SECURITY.md) |
| The UI: stack, look and feel, conventions | [docs/FRONTEND.md](docs/FRONTEND.md) and [docs/DESIGN.md](docs/DESIGN.md) |
| How healthy each area is | [docs/QUALITY_SCORE.md](docs/QUALITY_SCORE.md) |
| Generated schema and API documents | [docs/generated/](docs/generated/) (generated; do not edit) |

## Commands

```sh
uv sync --all-extras                      # install (Python 3.12, uv)
uv run pytest                             # unit, store (SQLite) and structural tests
uv run pytest --cov --cov-report=json && uv run python scripts/check_coverage.py
uv run ruff check . && uv run ruff format --check .
uv run mypy                               # strict
uv run python scripts/check_docs.py       # links, anchors, indexes, exec-plan shape
uv run chatlpt gen-docs                   # regenerate docs/generated after schema/API changes
(cd web && pnpm install && pnpm typecheck && pnpm test && pnpm build)
uv run chatlpt serve                      # http://localhost:3050 (serves web/dist when built)
scripts/build-images.sh                   # clearinghouse, node signer, chatlpt images
docker compose -f deploy/compose.yaml up -d
```

There is no CI yet (v2). Run the checks that exist for what you changed, and say which ones you ran.

## Source map

```text
src/chatlpt/
  contracts/   types layer: frozen pydantic models that cross a boundary (imports nothing internal)
  errors.py    application errors, one HTTP status each
  protocols/   ports: ChatBackend, UserStore, ConversationStore, UsageLedger, OAuthProvider, PriceSource, Clock
  config.py    Settings from CHATLPT_* variables; the engine reads its own LPB_* variables
  services/    business rules: auth, conversations, chat, context window, billing, admin
  store/       SQLAlchemy Core + Alembic migrations for chatlpt.db
  adapters/    engine (livepeer_builder), oauth (authlib), passwords (argon2), pricing (table file)
  runtime/     wiring: the embedded BuilderEngine and the application services; structured logging
  http/        FastAPI routes, server-sent events, static UI mount
  testing/     fakes shipped for tests
  cli.py       `chatlpt` operator commands
web/           React + Vite + TypeScript + Tailwind + shadcn/ui
deploy/        compose.yaml, Dockerfile, signer and clearinghouse config, secrets bootstrap
scripts/       build-images.sh, check_docs.py, check_coverage.py
tests/unit  tests/store  tests/structure  tests/http
```

## Working agreements

- **Enforce invariants, not style.** If a rule matters, encode it in `tests/structure/` with a
  failure message that says how to fix it. Do not add prose-only rules.
- **Parse at the boundary.** Contracts are frozen pydantic models; adapters convert wire formats.
  The UI parses API responses with zod.
- **Money is `Decimal`**, with a currency. Never float. A cost that has not arrived is `pending`.
- **Two books, never mixed.** Wholesale (engine network cost) and retail (token price) are separate
  columns with separate sources. Neither is derived from the other.
- **The browser never sees an engine, payment or admin credential.** It holds a session cookie.
- **Reserved features fail loudly** with HTTP 501, never silently.
- **Schema change ⇒ migration + `chatlpt gen-docs`.** `tests/store/test_durability.py` catches drift.
- **Plans are artifacts.** Update the exec plan's progress and decision log in the same change.
- **Git:** commit as you go; never push without a human review. No attribution trailers.

## Escalate to a human when

- a change would alter an accepted decision in `docs/design-docs/decisions.md`;
- builder-core, the SDK, the node or Batteries needs a change (see the streaming design);
- money could move outside an active plan: grants, funding, allocation keys.
