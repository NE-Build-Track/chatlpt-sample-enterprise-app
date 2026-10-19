# Plan 06: stream replies through the engine

## Goal

Replace the buffered reply with the engine's `jobs.stream` so the browser sees tokens as the runner
produces them, with no change outside the engine adapter and the dependency pin (D1, D20).

## Scope

- Pin `livepeer-builder` to the streaming branch (`tasks/m3/mz/stream-support`); until the branch is
  pushed, a wheel built from it is vendored under `vendor/` (T7).
- `adapters/engine.py`: `StreamingEngineChat` over `jobs.stream`, an incremental SSE decoder, deltas
  as reply chunks, usage from the final event, `abandoned`/`timeout` mapped to uncertain.
- The runtime picks the streaming adapter when the engine offers `jobs.stream`, else the buffered one.
- Partial text stays on the message when a stream fails after it started.
- Evidence: event timestamps from a live reply showing incremental arrival.

## Out of scope

Changes to the UI, the services or the stores: they were streaming-shaped from day one.

## Acceptance

- [x] `uv run pytest`, ruff, mypy, `scripts/check_docs.py` pass; coverage floors hold.
- [x] A live reply through the deployed stack shows `content` events arriving over time, not one at the end.
- [x] Tokens, retail and wholesale on a streamed reply match a buffered one in shape; wholesale arrives and settles.
- [x] Evidence page written; D2 and the references updated.

## Progress

- 2026-10-19: plan opened after the builder-core branch was shown live (its evidence: `2026-10-19-streaming-live`).
- 2026-10-19: `StreamingEngineChat` and the SSE decoder in; the runtime picks it by capability; 386 tests. Deployed and
  shown live: first token at 1.4 s, 74 deltas, done at 2.6 s
  ([evidence](../../references/evidence/2026-10-19-streamed-replies.md)). Plan complete. Later that day the
  branch was pushed and the pin became the git reference (T7 paid).

## Decision log

- 2026-10-19: both adapters stay in `adapters/engine.py`; the runtime chooses by capability
  (`hasattr(engine.jobs, "stream")`), so the app runs against either engine release.
- 2026-10-19: a vendored wheel stood in for the git pin until the branch was pushed later that day; the pin
  is now the git reference and `vendor/` is gone (T7 paid).
