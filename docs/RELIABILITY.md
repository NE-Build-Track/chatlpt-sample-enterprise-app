# Reliability

## Configuration

All settings come from the environment. `deploy/.env.example` lists every variable with its default.

| Prefix | Read by | Documented in |
| --- | --- | --- |
| `CHATLPT_*` | `src/chatlpt/config.py` | this file and `.env.example` |
| `LPB_*` | the embedded engine | builder-core `docs/RELIABILITY.md`; summary in [payment-stack](references/payment-stack.md) |

Key `CHATLPT_*` settings: `DATABASE_URL` (SQLite), `PUBLIC_BASE_URL`, `HTTP_HOST`, `HTTP_PORT`
(3050), `SESSION_SECRET`, `ALLOW_SIGNUP`, `TRUST_FORWARDED_FOR`, `GOOGLE_CLIENT_ID/SECRET`,
`GITHUB_CLIENT_ID/SECRET`,
`SYSTEM_PROMPT`, `TEMPERATURE`, `MAX_OUTPUT_TOKENS`, `CONTEXT_WINDOW_OVERRIDE`, `PRICING_FILE`,
`LOG_JSON`, `STATIC_DIR`.

## Admins

Signing up never makes an admin (D26). Grant and revoke with the CLI, against the same database:

```sh
docker compose -f deploy/compose.yaml exec chatlpt chatlpt make-admin you@example.com
docker compose -f deploy/compose.yaml exec chatlpt chatlpt revoke-admin you@example.com
```

`make-admin` refuses an account whose email nobody has proven (a password-only signup); have the
owner sign in with Google or GitHub first, or pass `--allow-unverified` if you know who it is.

Signup is open by default (`CHATLPT_ALLOW_SIGNUP=true`). **Close it for a public deployment**, unless
you want strangers spending the shared allocation.

## Sign in with Google and GitHub

Each button appears when its client id and secret are set. The callback URL is built from
`CHATLPT_PUBLIC_BASE_URL`, and each provider accepts only the exact URL registered with it. On start,
the app logs the URLs to register (`auth.oauth_redirects`), for example:

```text
https://chat.example.com/api/auth/oauth/google/callback
https://chat.example.com/api/auth/oauth/github/callback
```

- **Google:** Google Cloud console → APIs & Services → Credentials → OAuth client ID (Web
  application). Add the callback under "Authorized redirect URIs". Scopes: `openid email profile`.
- **GitHub:** Settings → Developer settings → OAuth Apps → New OAuth App. Set "Authorization
  callback URL" to the GitHub callback.

With a provider configured, the app refuses to start unless `CHATLPT_PUBLIC_BASE_URL` is `https` (or
`http` on localhost). Behind TLS also set `CHATLPT_SECURE_COOKIES=true`. A failed sign-in returns to
the login page with a reason (`?error=cancelled`, `expired`, `mismatch`, `provider_error`,
`unverified_email`, `disabled`, `signup_closed`); the log line `auth.oauth_failed` has the detail.

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
