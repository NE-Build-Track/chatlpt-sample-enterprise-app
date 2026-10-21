# Streaming through the engine

Status: **implemented** in builder-core and merged to `releases/m3` at `ad6bba9`, which ChatLPT pins (D2)
(2026-10-19 on branch `tasks/m3/mz/stream-support`, with the lifecycle fixes D34–D39 on 2026-10-20 and the PR #28 review fixes and D40 on 2026-10-21;
merged 2026-10-21 with PR #31). The exec plan is `docs/exec-plans/active/streaming-jobs.md` on that branch. This document is the design as ChatLPT needs it. ChatLPT is the first
consumer, but nothing here is specific to chat.

## Problem

`JobService.run` returns one buffered body. The engine contract (M2) says incremental text and live
media are out of scope. Any app that shows tokens as they are generated, plays audio as it is
synthesized, or reads ndjson progress cannot use the engine today, and would have to bypass it,
losing failover, attribution and cost classification.

## Goal

Stream the runner's response bytes to the caller as they arrive, in both integration modes, while
keeping every rule the job contract fixes: failover only before payment, the attempt row written
before the call, accurate `payment_sent` and `manifest_ids`, cost classification, idempotency.

## Non-goals

- Interpreting the stream. The engine moves bytes with a content type; the app parses SSE, ndjson
  or audio.
- Persistent sessions (M4). A stream is still one single-shot paid call.
- Resuming a stream after a disconnect.

## Design

### Contract

```python
class JobStream(Protocol):
    job: Job  # state "running" until the stream ends
    status_code: int
    content_type: str

    def __aiter__(self) -> AsyncIterator[bytes]: ...
    async def aclose(self) -> None: ...  # caller gave up; see "disconnect"


class JobService:
    async def run(self, actor, request) -> JobResult: ...  # unchanged
    async def stream(self, actor, request) -> JobStream: ...  # new
```

`JobRequest` gains `idle_timeout_s: float | None` (gap between chunks). `timeout_s` stays the total
budget. `mode` stays `immediate`; streaming is a delivery choice, not an execution mode.

### Transport

```python
class RunnerTransport(Protocol):
    async def call(self, runner, request, credential) -> RunnerReply: ...  # unchanged
    async def open(self, runner, request, credential) -> RunnerStream: ...  # new


class RunnerStream(Protocol):
    status_code: int
    content_type: str
    manifest_ids: tuple[str, ...]  # signed sessions so far
    payment_sent: bool

    def __aiter__(self) -> AsyncIterator[bytes]: ...
    async def aclose(self) -> None: ...
```

`SdkRunnerTransport.open` wraps `call_runner(..., stream=True)`. The SDK pays the 402 challenge
before any byte flows and keeps funding the session while the stream is open, so `payment_sent`
is known when `open` returns, and `manifest_ids` grows as the SDK signs more sessions.

### Rules kept

- **Failover only before payment.** `open` raising `refused`, `unreachable` or `payment_refused`
  with `payment_sent=False` fails over to the next runner. Once `open` returns, the job is bound.
- **Attempt written before the call**, updated when the stream ends.
- **Result not retained.** Size and sha256 accumulate per chunk; `ResultRef(storage="inline")` is
  written at the end, as today.
- **Idempotency** by `operation_ref` is unchanged.
- **Cost sync** already resolves many signings under one manifest (14 October evidence), so a long
  stream that pays in rounds classifies like any job.

### New rules

| Event | Attempt outcome | Job state |
| --- | --- | --- |
| Runner closes the stream normally | `succeeded` | `succeeded` |
| Runner errors mid-stream (connection reset, 5xx trailer) | `http` or `unreachable`, `payment_sent=True` | `uncertain` |
| No chunk within `idle_timeout_s` | `timeout`, `payment_sent=True` | `uncertain` |
| Total `timeout_s` exceeded | `timeout`, `payment_sent=True` | `uncertain` |
| Caller calls `aclose()` before the end | new outcome `abandoned`, `payment_sent=True` | `uncertain` |
| Engine dies mid-stream | `recover_interrupted()` as today | `uncertain` |

`abandoned` is new and honest: the work was paid for and probably ran; the caller stopped reading.
An app that wants the full paid result even when its own client leaves (ChatLPT does) keeps reading
and does not call `aclose()`.

### REST mode

`POST /v1/jobs` with `Accept: text/event-stream` or `"stream": true` in the body answers with the
runner's status, its content type, `livepeer-job-id` in the headers, and the body streamed
unbuffered. Errors before the first byte use the existing failure mapping. Errors after the first
byte end the response; the job record carries the outcome.

### Discovery metadata (small, related)

`Runner` gains `version`, `gpu` and `metadata` (the up-to-1 KB string the node echoes from the
runner's registration). Apps use it to derive model limits without a paid call when the runner
publishes them; on 19 October the chat runner published `{"model_id": "Qwen3.8-27B", "max_context": 131072}`.
The engine never interprets it. Until this lands, ChatLPT reads the raw entries itself
(`adapters/discovery.py`).

## Consequences for builder-core

- Contract docs: `docs/contracts/engine.md` gains a streaming section and the `abandoned` outcome.
- Schema: `attempts.outcome` enum gains `abandoned`; `jobs` gains nothing. One migration.
- `tests/structure` unchanged. `tests/unit/test_jobs.py` gains the table above with a
  `ScriptedTransport` that yields chunks and fails at chosen points.
- `docs/design-docs/m2-decisions.md` is not altered; a new decision is recorded in the M3 log.
- The SDK pin may need `on_payment_session` to fire for stream signings; verify on the branch.

## Consequences for ChatLPT

`adapters/engine.py` swaps `jobs.run` for `jobs.stream` and parses SSE deltas. Nothing else moves.

## Open questions for review

1. Does `LiveRunnerCallStream` expose the sessions it signs after the first, so `manifest_ids`
   stays complete? If not, the SDK needs a callback like `on_payment_session` for ongoing funding.
2. Should `abandoned` be a `Failure.kind` as well, so REST clients see it on `GET /v1/jobs/{id}`?
3. Idle timeout default: none (match today's behavior) or 60 s?
