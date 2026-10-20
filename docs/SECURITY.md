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
- OAuth (D6, D27): authorization code with PKCE (S256) and a signed `state` cookie (10 minutes).
  The identity comes from Google's userinfo endpoint (`email_verified` required) and GitHub's
  `/user/emails` (the verified primary), each called with the access token from the provider's token
  endpoint. No `id_token` is used, so there is no nonce. Every failure returns to `/login?error=…`.
- Accounts (D26): a provider sign-in links only into a **verified** account. An unverified password
  account with the same email is kept only with its password, otherwise claimed (retired). Admin
  rights come only from `chatlpt make-admin`, never from configuration or signup.
- Attempt limits (D26): login, signup and the claim prompt allow 5 a minute per email and 20 per
  client address, in memory. Behind a reverse proxy set `CHATLPT_TRUST_FORWARDED_FOR=true`, or every
  person shares the proxy's address.
- Redirects after sign-in go only to paths on this site (`next` is checked server and client side).
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
