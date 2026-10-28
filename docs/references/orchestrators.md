# Approved orchestrators (D8)

| Orchestrator | Chat app observed | Certificate (system trust store, 26 October) |
| --- | --- | --- |
| `https://orch-us-central.xodeapp.xyz:18935` | yes (2026-10-14; before the SDK enforced TLS) | self-signed: left out by discovery |
| `https://us-central-metrics.speedybird.xyz:28935` | yes (2026-10-14, 2026-10-19; before the SDK enforced TLS) | self-signed: left out by discovery |
| `https://orch-eu-central.open-pool.com:443` | discovered, not routed to | self-signed: left out by discovery |
| `https://hky.eliteencoder.net:8936` | **yes: carries chat since the SDK pin `76a1a1c` enforced TLS (22 October)** | trusted |
| `https://ai1.eliteencoder.net:8936` | no chat app; **77 runners, 73 of them fal apps, including `comfystream/fal-flux-schnell` at a fixed ~$0.003 per image** (added 2026-10-19 for model-driven images) | trusted |

builder-core's discovery service lists them (`deploy/config/orchestrators.txt`, the static directory)
and the app's discovery wrapper refuses any runner not on `CHATLPT_APPROVED_ORCHESTRATORS`. The signer
only signs (builder-core D43). The engine calls runners over verified TLS, so orchestrators whose
certificate the system trust store rejects cannot be used, and the discovery service leaves them out;
nothing is pinned (T3 closed).
