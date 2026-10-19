# Approved orchestrators (D8)

| Orchestrator | Chat app observed | Certificate |
| --- | --- | --- |
| `https://orch-us-central.xodeapp.xyz:18935` | yes (2026-10-14) | pinned (T3) |
| `https://us-central-metrics.speedybird.xyz:28935` | yes (2026-10-14, 2026-10-19) | pinned (T3) |
| `https://orch-eu-central.open-pool.com:443` | discovered, not routed to | pinned (T3) |
| `https://hky.eliteencoder.net:8936` | discovered, not routed to | pinned (T3) |

The signer's `Orchestrators` list (`deploy/config/signer.toml`) names them; the engine's discovery
wrapper refuses any runner not on this list. `deploy/config/pin-orchestrator-certs.py` pins their
TLS certificates trust-on-first-use; re-run it when one rotates.
