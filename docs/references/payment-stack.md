# Payment stack: Clearinghouse Batteries and the node remote signer

The components of builder-core's `deploy/dev-stack` (its README is the runbook of record for the
components themselves), all built from upstream `livepeer/*`:

| Service | Source | Pin |
| --- | --- | --- |
| `clearinghouse` | `livepeer/clearinghouse-batteries`, `examples/compose/Dockerfile` | `ca09e47c067682fb48c3f15425546fb6aa5b6659` |
| `signer` | `livepeer/node`, `docker/Dockerfile`, binary `livepeer-signer` | `406b248f6cb8728e6e7eba1809901f589060bc6b` (v1.0.2) |
| `discovery` | `livepeer/node`, `docker/Dockerfile`, binary `livepeer-discovery`, static mode, list in `deploy/config/discovery.toml` | `f45d83fd68f73d195dffe8b45f6cac296d023c49` (main, 10 commits after v1.0.6: the node commit builder-core `v0.2.0` pins, D2) |

The signer stays at `406b248` (D9), while builder-core `v0.2.0`'s own dev stack signs with `f45d83f` too
(its D63 (5)). The engine reaches the signer through the same SDK pin at both engine commits.

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
