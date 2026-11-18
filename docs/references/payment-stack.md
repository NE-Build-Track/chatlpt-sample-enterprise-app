# Payment stack: Clearinghouse Batteries and the node remote signer

The components of builder-core's `deploy/dev-stack` (its README is the runbook of record for the
components themselves), all built from upstream `livepeer/*`:

| Service | Source | Pin |
| --- | --- | --- |
| `clearinghouse` | `livepeer/clearinghouse-batteries`, `examples/compose/Dockerfile` | `03bc9fb5e15b073e68986ec0261e68d7ecd9598b` (v0.0.3; was `ca09e47`) |
| `signer` | `livepeer/node`, `docker/Dockerfile`, binary `livepeer-signer` | `eee09c41f46d64a34bfd9ed3c9cb649536490f13` (v1.0.7; was `406b248`, v1.0.2) |
| `discovery` | `livepeer/node`, `docker/Dockerfile`, binary `livepeer-discovery`, static mode, list in `deploy/config/discovery.toml` | `eee09c41f46d64a34bfd9ed3c9cb649536490f13` (v1.0.7, the same image as the signer; was `f45d83f`) |

Since 18 November 2026 the signer and discovery run one node image, v1.0.7, and Batteries is v0.0.3: the
versions builder-core's dev stack is being moved to (D9: same pins as builder-core's dev stack). Both
need the `unsafe@` prefix on a bind that is not loopback (`deploy/config/signer.toml`,
`clearinghouse.toml`). The v1.0.7 signer keeps its chain view fresh in the background: about 28 RPC
requests every 5 seconds with no jobs running (measured on builder-core's dev stack), about 480,000 a
day, and no setting changes it. Stop the stack when it is not in use, or size the RPC plan for it.

`livepeer-discovery` skips a runner with no `observed_at` and an orchestrator whose TLS certificate the
system trust store rejects. On 2026-11-13 that left only `ai1.eliteencoder.net` of the five D8 hosts:
`hky.eliteencoder.net`, the one host advertising `blueclaw/chat/qwen3.8-27b`, serves its runner without
`observed_at` (node older than `v1.0.4`). Check before a paid run: `docker compose exec chatlpt python -c
"import urllib.request; print(urllib.request.urlopen('http://discovery:8939/discovery').read().decode())"`.

## Topology

The signer shares the clearinghouse container's network namespace: the webhook (`:8080`) and
embedded Kafka (`:9092`) stay on loopback; the management API (`:8081`) and the signer (`:8937`) are
reachable by the app on the compose network. Nothing is published to the host except the app.

## Secrets (git-ignored `deploy/secrets/`)

`keystore.json` and `keystore-password` (payer account, from `~/.livepeer/keys/cloud-spe-gateway`),
`rpc-url` (Arbitrum One), plus what `deploy/init-secrets.py` generates: `clearinghouse.toml`
(credentials), `engine-token`, `grant-desk-token`, `webhook-url`, `webhook-headers`,
`kafka-username`, `kafka-password`.

## Shared allocation bootstrap (D3)

`deploy/first-run.sh`, once, after `clearinghouse` is healthy:

1. `clearinghouse grant create --name ChatLPT --sponsor ChatLPT --amount-usd <N> --status active`
2. `clearinghouse api-key create --grant-id <id> --name chatlpt --amount-usd <N>`
3. Write the returned `api_key` to `LPB_SHARED_PAYMENT_KEY` and `allocation_id` to
   `LPB_SHARED_ALLOCATION_ID` in `deploy/.env`.

The app reads `LPB_ALLOCATION_MODE=per_application`, `LPB_SIGNER_URL=http://clearinghouse:8937`,
`LPB_BATTERIES_URL=http://clearinghouse:8081`, `LPB_BATTERIES_TOKEN`, `LPB_SECRET_KEY`,
`LPB_DATABASE_URL=sqlite+aiosqlite:////data/livepeer-builder.db`. It does not need
`LPB_BATTERIES_OPERATOR_TOKEN` (the engine's grant desk, which the app never uses).

## Prerequisites

A payer account with a funded TicketBroker deposit and reserve on Arbitrum One, and an RPC URL.
Run **one** signer per payer account at a time (D10).
