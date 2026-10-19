# Approved orchestrators (D8)

| Orchestrator | Chat app observed | Certificate |
| --- | --- | --- |
| `https://orch-us-central.xodeapp.xyz:18935` | yes (2026-10-14) | pinned (T3) |
| `https://us-central-metrics.speedybird.xyz:28935` | yes (2026-10-14, 2026-10-19) | pinned (T3) |
| `https://orch-eu-central.open-pool.com:443` | discovered, not routed to | pinned (T3) |
| `https://hky.eliteencoder.net:8936` | discovered, not routed to | pinned (T3) |
| `https://ai1.eliteencoder.net:8936` | no chat app; **77 runners, 73 of them fal apps, including `comfystream/fal-flux-schnell` at a fixed ~$0.003 per image** (added 2026-10-19 for model-driven images) | pinned (T3) |

The signer's `Orchestrators` list (`deploy/config/signer.toml`) names them; the engine's discovery
wrapper refuses any runner not on this list. `deploy/config/pin-orchestrator-certs.py` pins their
TLS certificates trust-on-first-use; re-run it when one rotates.
