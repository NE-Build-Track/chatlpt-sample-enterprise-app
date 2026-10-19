# Plan 02: the payment stack and the first paid reply

## Goal

Run Clearinghouse Batteries, the node remote signer and ChatLPT from `deploy/compose.yaml` on this
machine, bootstrap the shared allocation (D3), and produce one real reply from
`blueclaw/chat/qwen3.8-27b` through the embedded engine, with both books filled: retail from tokens,
wholesale from the engine once Batteries reports it.

## Scope

- `deploy/init-secrets.py`, the payer keystore from `~/.livepeer/keys/cloud-spe-gateway`, the Arbitrum RPC
  URL, pinned orchestrator certificates (T3).
- `deploy/first-run.sh` creating the grant and the `lpg_` key; the resulting `LPB_SHARED_*` settings.
- A paid reply through the UI or the API; `GET /v1/models` through the engine for the context window.
- Evidence recorded in `docs/references/evidence/`.

## Out of scope

Streaming (plan-05/06), provider sign-in against real Google/GitHub apps (plan-03).

## Expected spend

Grant creation and allocation are Batteries accounting entries, not on-chain transfers. Each short
reply is about $0.00003 to $0.0003 at the observed per-second rates; `GET /v1/models` is a fraction
of that. Budget for this plan: under $0.05.

## Acceptance

- [ ] `docker compose -f deploy/compose.yaml ps` shows clearinghouse (healthy), signer and chatlpt up.
- [ ] `GET /readyz` reports `chat_available: true` and the derived model id.
- [ ] One reply completes; the message carries token counts, a retail amount and `wholesale: pending`.
- [ ] Within a few minutes `wholesale.status` becomes `delivered` with an amount, and the admin page shows the margin.
- [ ] Evidence page written with job id, orchestrator, tokens, retail, wholesale.

## Progress

- 2026-10-19: plan opened.

## Decision log

- 2026-10-19: the RPC URL and payer keystore are the same operator credentials builder-core's dev-stack uses;
  one signer per payer account at a time (D10), so that stack stays down while this one runs.
