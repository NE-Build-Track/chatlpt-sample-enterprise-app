# ChatLPT

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![uv](https://img.shields.io/badge/packaging-uv-DE5FE9?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/UI-React%2019-61DAFB?logo=react&logoColor=black)](web/)
[![shadcn/ui](https://img.shields.io/badge/components-shadcn%2Fui-000000)](https://ui.shadcn.com/)
[![TypeScript strict](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)](web/tsconfig.json)
[![Docker Compose](https://img.shields.io/badge/deploy-Docker%20Compose-2496ED?logo=docker&logoColor=white)](deploy/compose.yaml)
[![livepeer-builder streaming branch](https://img.shields.io/badge/livepeer--builder-m3%20stream--support%20(embedded)-00EB88)](https://github.com/NE-Build-Track/livepeer-builder-core)
[![Model](https://img.shields.io/badge/model-Qwen3.8--27B%20on%20Livepeer-FF6A00)](docs/references/qwen-runner.md)
[![Status](https://img.shields.io/badge/status-alpha%20%C2%B7%20streaming%20%2B%20images%20live-orange)](docs/PLANS.md)
[![Agent-first](https://img.shields.io/badge/built-agent--first-8A2BE2)](docs/references/harness-engineering.md)

A ChatGPT-style chat application that runs its model on the **Livepeer network** through the
[livepeer-builder](https://github.com/NE-Build-Track/livepeer-builder-core) engine, pays
orchestrators through a **self-hosted remote signer and Clearinghouse Batteries**, and shows two
numbers under every reply: what the network actually charged (**wholesale**) and what the same
tokens would cost at the model vendor's list price (**retail**).

It is a **sample enterprise application**: a reference for embedding the engine in a Python backend,
and a reference for building such an app agent-first, where the repository is the system of record.

> Status: **alpha; paid, streamed replies and model-driven images work end to end**. See [docs/PLANS.md](docs/PLANS.md) for the order of work.

## Contents

- [Motivation](#motivation)
- [What it does](#what-it-does)
- [Assumptions](#assumptions)
- [Architecture](#architecture)
- [Conventions](#conventions)
- [Build](#build)
- [Run locally](#run-locally)
- [Deploy](#deploy)
- [Configuration](#configuration)
- [Streaming](#streaming)
- [Working in this repository](#working-in-this-repository)

## Motivation

Public chat products hide what inference costs. Enterprises that run on open networks want the
opposite: per user, per reply, what the network charged and what the tokens are worth. ChatLPT puts
both next to each answer. It also exercises the builder engine in **embedded mode**, where the
application authenticates its own users, builds an `ActorContext`, and lets the engine own
discovery, payment, failover and cost attribution.

The repository is also a demonstration of the
[harness-engineering](docs/references/harness-engineering.md) approach: a short map
([AGENTS.md](AGENTS.md)), a `docs/` tree as the system of record, invariants enforced by tests,
and plans checked in as artifacts.

## What it does

- Sign up with email and password; sign in with Google or GitHub when configured.
- Chat with `Qwen3.8-27B` (`blueclaw/chat/qwen3.8-27b`), served by vLLM on approved Livepeer
  orchestrators. Markdown replies, code blocks, a collapsible **Thinking** block, a stop button, a
  per-conversation thinking level, and **Continue generating** when a reply hits the output limit.
- **Images, the way ChatGPT does them:** the assistant decides when to draw. It calls a
  `generate_image` tool, the app runs FLUX.1 [schnell] (`comfystream/fal-flux-schnell`) through the
  engine, keeps the file, and the model captions the result. Each image shows its retail price (fal's
  list price per megapixel) and the network cost.
- Under each reply: prompt, completion and reasoning tokens; **retail** cost from Alibaba Cloud's
  Qwen list prices; **wholesale** cost from the engine once Batteries reports it.
- Conversation sidebar, rename and delete, per-conversation and per-month totals.
- A minimal admin page: per-user tokens, retail, wholesale and margin.

The full spec, with phase 2, is [docs/product-specs/chatlpt.md](docs/product-specs/chatlpt.md).

## Assumptions

Each is a numbered decision in [docs/design-docs/decisions.md](docs/design-docs/decisions.md).

| Assumption | Decision |
| --- | --- |
| Streaming is required, and is designed generically for builder-core, not patched into this app | D1, D20 |
| builder-core is pinned to `releases/m3` at `2134e29` (native HTTP, paid failover, the manifest stored before signing) | D2 |
| One shared application payment key; the app tracks tokens per user; both books are kept | D3 |
| Retail prices are Alibaba Cloud's international list prices for Qwen3.8-27B, recorded in-repo with a date | D4 |
| Email/password accounts in SQLite, self-signup open; Google (OIDC) and GitHub (OAuth 2.0) optional | D5, D6 |
| Four approved orchestrators run the chat app today | D8 |
| The payment stack runs beside the app from this repository's compose file, one signer per payer key | D9, D10 |
| SQLite for the app and the embedded engine | D11 |
| The context window is read from the model (`max_model_len`), not configured | D14 |
| No CI, no beads, no attribution trailers; commit as you go, never push without review | D12, D13 |

## Architecture

One process, one container. Details and the layer rules are in [ARCHITECTURE.md](ARCHITECTURE.md).

```text
Browser ──session cookie──▶ chatlpt (FastAPI + static React)
                              ├─ services: auth, conversations, chat, context, billing, admin
                              ├─ store: SQLite  chatlpt.db
                              └─ embedded livepeer-builder (streaming branch, D2)
                                   ├─ store: SQLite  livepeer-builder.db
                                   ├─▶ node remote signer ──webhook──▶ Clearinghouse Batteries
                                   └─▶ orchestrators running blueclaw/chat/qwen3.8-27b (vLLM)
```

A reply: the route authenticates the session, the chat service builds the message list within the
derived context window, the engine adapter runs the paid job with `stream_options.include_usage`,
chunks go to the browser as server-sent events and are saved on completion with token counts, the
retail cost is computed from the price table, and the network cost is read from the engine whenever
the reply is shown (D29); nothing copies it. If the browser leaves mid-reply, the app keeps reading so the paid reply is
not lost.

## Conventions

- **Layers** (`contracts → errors → protocols → config → services | store | adapters → runtime → http`)
  with dependency direction and third-party confinement enforced by `tests/structure/`.
- **Parse at the boundary:** frozen pydantic contracts in Python, zod schemas in TypeScript.
- **Money is `Decimal` with a currency.** Missing cost is `pending`, never zero.
- **Two books, never mixed.** Retail lives in the app's ledger; network cost lives in the engine and is
  read by job id (D29).
- **The browser holds a session cookie and nothing else.**
- **Reserved features answer 501.** Schema changes ship with a migration and regenerated docs.
- **Plans are artifacts** in `docs/exec-plans/` with progress and decision logs.

## Build

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 24 with pnpm (via corepack),
Docker with Compose v2.

```sh
uv sync --all-extras                 # backend
(cd web && pnpm install && pnpm build)   # UI → web/dist
scripts/build-images.sh              # clearinghouse, node signer, chatlpt images (never pushes)
```

Checks:

```sh
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run python scripts/check_docs.py
(cd web && pnpm typecheck && pnpm test)
```

## Run locally

Without the payment stack the app boots in a degraded state: sign-in works, chat is disabled and
`/readyz` says why.

```sh
cp deploy/.env.example deploy/.env    # fill CHATLPT_SESSION_SECRET at least
uv run chatlpt migrate
uv run chatlpt serve                  # http://localhost:3050
```

With the payment stack, see [Deploy](#deploy). Every reply spends real money from the shared
allocation; the amounts are tiny (about $0.00003 for a short reply) but they are real.

## Deploy

The compose file runs four services: `clearinghouse` (Batteries with embedded Kafka), `signer`
(the node remote signer, sharing the clearinghouse network namespace; it only signs), `discovery`
(builder-core's discovery service, listing `deploy/config/orchestrators.txt`) and `chatlpt`. Only the app is
published, on loopback. Put a TLS proxy in front for anything but local use.

```sh
cd deploy
python3 init-secrets.py                      # Batteries creds, engine token, webhook, Kafka users
# add, mode 0600: secrets/rpc-url, secrets/keystore.json, secrets/keystore-password
docker compose up -d clearinghouse signer discovery
./first-run.sh                               # grant + shared allocation key → .env
docker compose up -d chatlpt
```

Prerequisites: a payer keystore whose account has a funded TicketBroker deposit and reserve on
Arbitrum One, and an Arbitrum One RPC URL. Run one signer per payer account at a time. The
runbook, pins and topology are in [docs/references/payment-stack.md](docs/references/payment-stack.md);
backup and health in [docs/RELIABILITY.md](docs/RELIABILITY.md); trust boundaries in
[docs/SECURITY.md](docs/SECURITY.md).

## Configuration

Everything is an environment variable; `deploy/.env.example` lists each with its default.

| Variable | Purpose |
| --- | --- |
| `CHATLPT_DATABASE_URL` | SQLite URL for the app database |
| `CHATLPT_PUBLIC_BASE_URL`, `CHATLPT_HTTP_HOST`, `CHATLPT_HTTP_PORT` | Where the app is reached (OAuth callbacks need the base URL) |
| `CHATLPT_SESSION_SECRET` | Signs session cookies |
| `CHATLPT_ALLOW_SIGNUP`, `CHATLPT_TRUST_FORWARDED_FOR` | Open signup (default on; close it for a public deployment); rate-limit by `X-Forwarded-For` behind a proxy |
| `CHATLPT_GOOGLE_CLIENT_ID/SECRET`, `CHATLPT_GITHUB_CLIENT_ID/SECRET` | Enable each sign-in button |
| `CHATLPT_SYSTEM_PROMPT`, `CHATLPT_TEMPERATURE`, `CHATLPT_MAX_OUTPUT_TOKENS` | Model defaults; the output limit covers answer plus thinking |
| `CHATLPT_DEFAULT_THINKING`, `CHATLPT_THINKING_BUDGET_LOW/MEDIUM/HIGH` | The per-conversation thinking level and its chain-of-thought caps |
| `CHATLPT_TOOLS_ENABLED`, `CHATLPT_IMAGE_APP`, `CHATLPT_IMAGES_DIR`, `CHATLPT_IMAGE_RETENTION_DAYS`, `CHATLPT_IMAGE_PRICING_FILE` | Model-driven images: the tool, the runner app, where files live, how long, and fal's price table |
| `CHATLPT_CONTEXT_WINDOW_OVERRIDE` | Last-resort override of the derived context window |
| `CHATLPT_PRICING_FILE` | The retail price table (`config/pricing/qwen3.8-27b.json`) |
| `LPB_*` | The embedded engine: signer, Batteries, shared key, database. See [payment-stack](docs/references/payment-stack.md) |

## Streaming

Replies stream token by token through the engine's `jobs.stream`, from builder-core `releases/m3`
(the generic design is in
[docs/design-docs/streaming-through-the-engine.md](docs/design-docs/streaming-through-the-engine.md)).
The buffered adapter remains for an engine without `jobs.stream`; it still needs an engine that accepts
`idle_timeout_s` (the pinned commit onward), so it is not a fallback to `v0.1.0`.

## Working in this repository

Start with [AGENTS.md](AGENTS.md). Humans steer; agents execute; the repository is the only context
an agent has. There is no CI yet; run the checks that exist for what you changed and say which ones
you ran. Commit as you go. Never push without a human review. No attribution trailers.

## License

MIT. See [LICENSE](LICENSE).
