# Security

## Trust boundaries

| Holder | Credential | Never reaches |
| --- | --- | --- |
| Browser | signed session cookie (HTTP-only, SameSite=Lax) | anything else |
| App process | `CHATLPT_SESSION_SECRET`, OAuth client secrets, `LPB_SHARED_PAYMENT_KEY`, `LPB_BATTERIES_TOKEN`, `LPB_BATTERIES_OPERATOR_TOKEN`, `LPB_SECRET_KEY` | logs, responses, client bundles |
| Signer container | payer keystore + password, RPC URL, webhook token, Kafka credentials | the app |
| Batteries container | its credentials file | the app (it sees only the management token) |

## Rules

- Passwords: argon2id, per-user salt, never logged. Password reset is out of scope in phase 1.
- OAuth: state and nonce checked; Google via OIDC `id_token`; GitHub via `/user/emails`, verified
  primary only. Accounts link by verified email (D6).
- Sessions: itsdangerous-signed cookie carrying the user id and an expiry; rotated on login.
- CSRF: same-site cookie plus a custom header on state-changing JSON requests.
- The engine's `DefaultPolicy` still applies in embedded mode: a user reads only their own jobs.
- Structured logs redact values of keys matching `token|secret|password|key`
  (`tests/structure/test_logging.py`).
- Secrets live in `deploy/secrets/` and `deploy/.env`, both git-ignored, mode 0600.
- The app container runs as uid 10001 with a read-only root filesystem; `/data` is the only volume.

## Money

Every chat reply spends from the shared allocation. Admission is the engine's; the app adds no
quota in phase 1 (phase 2). Watch `GET /readyz` and the admin page's allowance.
