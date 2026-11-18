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

## FLUX.2 [klein] 4B (the `openai.images.v1` runner, D30)

Observed on **2026-11-18** at <https://fal.ai/models/fal-ai/flux-2/klein/4b>: "Price: **$0.005 per
megapixels**". The page states no rounding rule; the app rounds up to the nearest megapixel, as it does
for FLUX.1 [schnell]. The machine-readable copy is
[`config/pricing/flux-2-klein-4b.json`](../../config/pricing/flux-2-klein-4b.json). fal's "base" variant of
the model is a different product at $0.009 per megapixel; the runner on `ai1` names
`black-forest-labs/FLUX.2-klein-4B`, the distilled model.

The app asks this runner for 512×512 whatever the preset ([orchestrators.md](orchestrators.md)), so
every image is one billed megapixel: $0.005 retail.

The network's wholesale price for `text-to-image` on ai1.eliteencoder.net was a fixed
11,125,095,244,150 wei per run, about **$0.02**, on 2026-11-18. An image there costs the operator more
than its retail price.
