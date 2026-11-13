# Approved orchestrators (D8)

| Orchestrator | Chat app observed | Certificate (system trust store, 26 October) |
| --- | --- | --- |
| `https://orch-us-central.xodeapp.xyz:18935` | yes (2026-10-14; before the SDK enforced TLS) | self-signed: left out by discovery |
| `https://us-central-metrics.speedybird.xyz:28935` | yes (2026-10-14, 2026-10-19; before the SDK enforced TLS) | self-signed: left out by discovery |
| `https://orch-eu-central.open-pool.com:443` | discovered, not routed to | self-signed: left out by discovery |
| `https://hky.eliteencoder.net:8936` | **yes: carries chat since the SDK pin `76a1a1c` enforced TLS (22 October)** | trusted |
| `https://ai1.eliteencoder.net:8936` | no chat app; **77 runners, 73 of them fal apps, including `comfystream/fal-flux-schnell` at a fixed ~$0.003 per image** (added 2026-10-19 for model-driven images) | trusted |

livepeer/node's `livepeer-discovery` collects them (`Nodes` in `deploy/config/discovery.toml`,
builder-core D63) and the app's discovery wrapper refuses any runner whose URL's host is not on
`CHATLPT_APPROVED_ORCHESTRATORS`. The signer only signs. The engine calls runners over verified TLS, so
orchestrators whose certificate the system trust store rejects cannot be used, and `livepeer-discovery`
leaves them out; nothing is pinned (T3 closed). It also leaves out a runner with no `observed_at`, and
so does the engine's reader.

**2026-11-13**, `livepeer-discovery --dump` built from node `f45d83f` over this list: only `ai1` answered
(20 runners, no `comfystream/fal-flux-schnell`). `hky` serves `blueclaw/chat/qwen3.8-27b` without
`observed_at`, so its runner is skipped; `speedybird` and `open-pool` failed TLS; `orch-us-central`
timed out. No approved host then offered the chat app to builder-core `v0.2.0`.
