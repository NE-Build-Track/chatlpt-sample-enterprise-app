# Runtime evidence: model-driven image generation, 19 October 2026

The check behind D25: can the Qwen runner decide to draw through tool calling, can the engine run the
FLUX app, and can the model caption the result? Run from a script against the ChatLPT payment stack
with the engine from branch `tasks/m3/mz/stream-support` at `973ac57`.

## Where the apps are

| App | Orchestrators advertising it (approved list) |
| --- | --- |
| `blueclaw/chat/qwen3.8-27b` | xode us-central, speedybird, hky.eliteencoder |
| `comfystream/fal-flux-schnell` | **none of the original four.** Of every orchestrator on the Railway signer's list, only `https://ai1.eliteencoder.net:8936` advertises it (77 runners, 73 fal apps). Mike approved adding it (D8). |

## The loop

| Step | Result |
| --- | --- |
| 1. Chat with `tools=[generate_image]`, `tool_choice: auto`, "Draw me a watercolor lighthouse at sunset." | `finish_reason: tool_calls`; a parsed call with a 60-word prompt the model wrote and `image_size: portrait_4_3`; 2.3 s, 392/123 tokens. In an earlier run with thinking **off** the model answered in prose and made no call; with thinking **on** it called every time. The decision is sampled, so the app should offer tools with at least low thinking. |
| 2. Control: "What is a lighthouse for? One sentence." | A plain answer, no tool call, 1.2 s. |
| 3. `comfystream/fal-flux-schnell` with the model's prompt | 4.7 s on ai1.eliteencoder.net; one 768×1024 JPEG, seed 435584106, safety flag false, inference 1.04 s; the `fal.media` URL served 678 KB. |
| 4. Tool result back (`role: tool` with size and seed) | A two-paragraph caption, `finish_reason: stop`, 569/67 tokens, 1.5 s. |
| 5. Costs | three chat jobs at $0.000111 each; the image job **$0.003007** (fixed); all observed and matched. |

![The generated image, reduced](2026-10-19-tool-image.jpg)

## What this fixes in the design

- Tool calling works on this runner without any change to the chat template or the engine; the
  engine already carries `tools` in the payload untouched.
- Model-driven images are three paid jobs per picture: the decision, the image, the caption. Each
  keeps its own ledger row.
- Retail for an image comes from fal's list price per megapixel ([fal-pricing](../fal-pricing.md));
  it is nearly equal to the network price for this app.
