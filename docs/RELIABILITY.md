# Reliability

## Configuration

All settings come from the environment. `deploy/.env.example` lists every variable with its default.

| Prefix | Read by | Documented in |
| --- | --- | --- |
| `CHATLPT_*` | `src/chatlpt/config.py` | this file and `.env.example` |
| `LPB_*` | the embedded engine | builder-core `docs/RELIABILITY.md`; summary in [payment-stack](references/payment-stack.md) |

Key `CHATLPT_*` settings: `DATABASE_URL` (SQLite), `PUBLIC_BASE_URL`, `HTTP_HOST`, `HTTP_PORT`
(3050), `SESSION_SECRET`, `ADMIN_EMAILS`, `GOOGLE_CLIENT_ID/SECRET`, `GITHUB_CLIENT_ID/SECRET`,
`SYSTEM_PROMPT`, `TEMPERATURE`, `MAX_OUTPUT_TOKENS`, `CONTEXT_WINDOW_OVERRIDE`, `PRICING_FILE`,
`LOG_JSON`, `STATIC_DIR`.

## Health

- `GET /healthz`: the process is up.
- `GET /readyz`: the app database migrated, the engine started, discovery not stale, at least one
  ready chat runner. Reports each check; degraded states are named, never hidden.

## Data

Two SQLite files on the `/data` volume: `chatlpt.db` and `livepeer-builder.db`, both in WAL mode.
Back up by copying both while stopped, or with `sqlite3 .backup`. Alembic migrations run at startup
(`CHATLPT_AUTO_MIGRATE`, default on) or explicitly with `chatlpt migrate`.

## Failure modes a user can see

| What happened | What the UI says |
| --- | --- |
| No ready runner | "The model is not available right now." Retry later. |
| Payment refused everywhere (allowance exhausted) | "The service's network allowance is exhausted." Admin funds the allocation. |
| Timeout after payment | The reply is marked uncertain; wholesale cost may still arrive. |
| Engine not configured (dev without the stack) | `/readyz` degraded; chat disabled with a banner. |

## Per-worktree boot

`make dev` picks a free port and a database path under the worktree, so agents can run one instance
per change and drive it (DevTools or Playwright) without colliding.
