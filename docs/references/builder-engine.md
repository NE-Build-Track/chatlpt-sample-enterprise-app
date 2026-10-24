# livepeer-builder (embedded)

Pinned to branch **`releases/m3`** of `NE-Build-Track/livepeer-builder-core` at commit `629f1ab`
(2026-10-24: the merge of PR #44, after PR #43: a paid job's cost never reads `none`, and payment
evidence is stored when the signer signs, builder-core D42; migration `0005`, applied on start).
Before that `878e4f4` (2026-10-23: the merge of PR #42, after PR #41, the dependency-injection
refactor, plan 08; `JourneyApi` renamed `ActorApi` in builder-core decision 14).
Before that `releases/m3` at `ad6bba9` (2026-10-21: the merge of PR #28, streaming, and PR #31,
gateway `3238731` and D41), and before that the
streaming branch `tasks/m3/mz/stream-support` at `93756ba` (2026-10-21: the PR #28 review fixes, D40), `a89216d` (2026-10-20: the stream
lifecycle fixes, D34–D39), `973ac57`
(2026-10-19), and tag `v0.1.0` (commit `153f0de`). Source of truth: that repository's `ARCHITECTURE.md`, `docs/contracts/engine.md`,
`docs/design-docs/extending-the-engine.md`.

## What we call

| Need | Engine API | Notes |
| --- | --- | --- |
| Build and start | `BuilderEngine.create(engine_settings, decorate=...)`, `await engine.start()` | `engine_settings` is an `EngineSettings` value; the CLI reads it from `LPB_*` ([payment-stack](payment-stack.md)). We type the engine as `ActorApi` |
| Who is calling | `ActorContext(actor_id, application_id="chatlpt", permissions={discover, jobs.run, jobs.read, costs.read})` | Built by our runtime; no engine key for users |
| Offerings | `engine.discovery` snapshot / offerings | Filtered to the chat app on approved orchestrators |
| A reply | `engine.jobs.streaming.stream(actor, JobRequest(app="blueclaw/chat/qwen3.8-27b", path="/v1/chat/completions", payload={..., "stream": true, "stream_options": {"include_usage": true}}, operation_ref=..., max_attempts=..., timeout_s=..., idle_timeout_s=...))` | A `JobStream` of SSE bytes. `jobs.streaming` is `None` when the transport cannot stream; then `jobs.run` |
| Model limits | the same, `method="GET"`, `path="/v1/models"` | Billed per second (tiny); cached (D14) |
| Token usage | `engine.jobs.report_usage(actor, job_id, {"prompt_tokens": n, ...})` | Once per job, owner only, succeeded jobs only |
| Network cost of a job | `engine.costs.for_job(actor, job_id)`, each time it is shown (D29) | `pending` while the job runs and until Batteries reports, never `none` for a paid job; then `delivered`, `failed_after_payment`, `uncertain`; `none` = the job ended and nothing was paid ($0) |
| A user's network totals | `engine.costs.summary(actor, start, end)` | By class; `jobs_pending` beside the totals. Running and just-finished jobs count as `pending` straight away; a finished job's cost settles within one engine cost-sync cycle (30 s) |
| Allowance | `engine.payments.allowance(actor)` | The shared allocation's granted/spent/available |

## Behavior to design around

- **Results are inline only.** `GET /v1/jobs/{id}/result` is 501 until M4. Persist the reply before anything else.
- **Streaming:** `jobs.streaming.stream` opens the paid call and yields bytes; a stream the app stops reading ends `abandoned` and the job `uncertain` (see [streaming design](../design-docs/streaming-through-the-engine.md)). `Runner` now carries `version`, `metadata` and `gpu`.
- **Stream lifecycle (builder-core D34–D40, from `93756ba`):** the engine records a stream's end in its own task, so a cancelled reply still finishes its job and frees its slot. Deadlines: `timeout_s` from the job's start, `first_byte_timeout_s` (60 s default) to the first chunk, `idle_timeout_s` between chunks (we set it; the engine default is 60 s). `JobStream` supports `async with` and `complete()` (succeeded with the bytes the caller read); a cancelled reader, or `disconnected()`, gets `LPB_STREAM_SETTLE_S` (1 s) for the runner to finish, while closing or dropping the iterator abandons at once (D40). `timeout_s` stops once the runner has finished, and `engine.stop()` waits for final writes. We read every stream to the end in a task the browser connection does not touch, so none of this changes our replies.
- **Gateway `3238731` (builder-core D41, from `ad6bba9`):** `payment_sent` and the manifests come only from the SDK's `on_payment_session`, which runs after the signer returns a valid payment and before the paid request goes out. A failure while signing records the attempt as not paid (`failed`); any charge the signer made then shows in reconciliation as unattributed. The SDK now verifies runner TLS certificates with the process trust store: a runner with a self-signed certificate is `unreachable`, unpaid, and the engine fails over. A missing payload is sent as `{}`.
- **Failover only before payment.** After payment the job is bound to a runner; a timeout leaves it `uncertain`.
- **`per_application` mode** needs `LPB_SHARED_PAYMENT_KEY` and `LPB_SHARED_ALLOCATION_ID`; jobs still carry `actor_id`.
- **No operator token.** `LPB_BATTERIES_OPERATOR_TOKEN` only turns on the engine's grant desk
  (`engine.payments.grants`); ChatLPT never lists or creates grants, so it leaves it unset.
- **Money is `Decimal`.** A cost status of `none` means no attempt was paid: a settled $0 (D29).
- **One engine process per database.** Fine: one container.
- **Discovery** refreshes every `LPB_DISCOVERY_INTERVAL_S` (15 s) and is stale after three misses.

## Extension points we use

- **Decorate** `parts.discovery_source` (`FilteredDiscovery`, `adapters/discovery.py`): the engine's configured
  source, signer header included, filtered to our apps on D8 hosts; it reads each `Runner.metadata` for the
  context window (D14).
- `SelectionPolicy`: the default `MostCapacityFirst` for now.
- Everything else: defaults.
- **Tests** use `livepeer_builder.testing.FakeEngine` (the journey, scripted with `Reply`, `Fails`, `Raises`),
  which builder-core keeps in step with the real engine by a contract test. We import only builder-core's
  public API (`tests/structure/test_engine_api.py`).
