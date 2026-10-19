# Plan 07: model-driven images

## Goal

Let the assistant draw the way ChatGPT does: it is offered a `generate_image` tool, decides when to
call it, the app runs `comfystream/fal-flux-schnell` through the engine, keeps the image on the
volume, and the model captions the result. Both books per image (D25).

## Scope

- Discovery covers a set of approved apps; `ai1.eliteencoder.net` joins the approved hosts (D8).
- `ToolSpec`/`ToolCall` on the chat port; tool calls parsed from buffered and streamed replies.
- `ImageBackend` over the engine, `ImageFiles` on disk, fal's per-megapixel price table.
- `tool_call` messages with their images; a second model call for the caption; history folds the
  picture into one assistant turn.
- `GET /api/images/{id}` for the owner; retention; the UI renders images inline with costs.

## Out of scope

Image editing, image input, more than one image model, a manual image button.

## Acceptance

- [x] Unit, store, HTTP tests for the loop, pricing (rounded-up megapixels), retention and the route.
- [x] Live: a request through the deployed app produces a tool call, an image on the volume, a
      caption, and three ledger rows with wholesale arriving.
- [x] Evidence page and screenshot; decisions, references and README updated.

## Progress

- 2026-10-19: feasibility shown live ([evidence](../../references/evidence/2026-10-19-model-driven-images.md));
  Mike approved ai1.eliteencoder.net.
- 2026-10-19: built and deployed: tool calls parsed buffered and streamed, `EngineImages`, files on the volume,
  fal's price table, the two-message picture, the image route, retention; 443 tests at 95.8% coverage with the
  floors held. Live through the app: a vintage-poster cabin, three ledger rows all delivered
  ([evidence addendum](../../references/evidence/2026-10-19-model-driven-images.md)). Plan complete.

## Decision log

- 2026-10-19: a picture is two assistant messages, a `tool_call` message carrying the image and a text
  message carrying the caption, so every paid job keeps one ledger row and the data model stays flat.
- 2026-10-19: tools are offered with at least low thinking; the decision was unreliable with thinking off.
- 2026-10-19: at most two images per turn; image bytes are fetched once and kept for the retention window.
