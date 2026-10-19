# FLUX.1 [schnell] list price (retail book for images)

Observed on **2026-10-19** at <https://fal.ai/models/fal-ai/flux/schnell>: "Your request will cost
**$0.003 per megapixel**. Images are billed by rounding up to the nearest megapixel." The
machine-readable copy the app loads is [`config/pricing/fal-flux-schnell.json`](../../config/pricing/fal-flux-schnell.json).

| Size preset | Pixels | Billed megapixels | Retail |
| --- | --- | --- | --- |
| `square` (512×512) | 0.26 MP | 1 | $0.003 |
| `landscape_4_3` (1024×768), `portrait_4_3` | 0.79 MP | 1 | $0.003 |
| `square_hd` (1024×1024) | 1.05 MP | 2 | $0.006 |
| `landscape_16_9` (1024×576) | 0.59 MP | 1 | $0.003 |

The network's wholesale price for `comfystream/fal-flux-schnell` on ai1.eliteencoder.net is a fixed
1,250,342,569,331 wei per run, about **$0.0030** on 2026-10-19. For a default-size image the two books
are therefore nearly equal; the margin story is in chat, not images.
