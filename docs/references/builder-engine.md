# livepeer-builder (embedded)

Pinned to branch **`tasks/m3/mz/stream-support`** of `NE-Build-Track/livepeer-builder-core` at `973ac57`
(2026-10-19; vendored wheel until the branch is pushed, T7). Previously tag `v0.1.0` (commit `153f0de`). Source of truth: that repository's `ARCHITECTURE.md`, `docs/contracts/engine.md`,
`docs/design-docs/extending-the-engine.md`.

## What we call

| Need | Engine API | Notes |
| --- | --- | --- |
| Build and start | `BuilderEngine.from_settings(EngineSettings.from_env(), discovery_source=..., selection=...)`, `await engine.start()` | `LPB_*` variables; see [payment-stack](payment-stack.md) |
| Who is calling | `ActorContext(actor_id, application_id="chatlpt", permissions={discover, jobs.run, jobs.read, costs.read})` | Built by our runtime; no engine key for users |
| Offerings | `engine.discovery` snapshot / offerings | Filtered to the chat app on approved orchestrators |
| A reply | `engine.jobs.stream(actor, JobRequest(app="blueclaw/chat/qwen3.8-27b", path="/v1/chat/completions", payload={..., "stream": true, "stream_options": {"include_usage": true}}, operation_ref=..., max_attempts=..., timeout_s=..., idle_timeout_s=...))` | A `JobStream` of SSE bytes; `jobs.run` remains the fallback for an engine without streaming |
| Model limits | the same, `method="GET"`, `path="/v1/models"` | Billed per second (tiny); cached (D14) |
| Token usage | `engine.jobs.report_usage(actor, job_id, {"prompt_tokens": n, ...})` | Once per job, owner only, succeeded jobs only |
| Wholesale cost | `engine.costs.for_job(actor, job_id)` | `pending` until Batteries reports; then `delivered`, `failed_after_payment`, `uncertain` |
| Allowance | `engine.payments.allowance(actor)` | The shared allocation's granted/spent/available |

## Behavior to design around

- **Results are inline only.** `GET /v1/jobs/{id}/result` is 501 until M4. Persist the reply before anything else.
- **Streaming:** `jobs.stream` opens the paid call and yields bytes; a stream the app stops reading ends `abandoned` and the job `uncertain` (see [streaming design](../design-docs/streaming-through-the-engine.md)). `Runner` now carries `version`, `metadata` and `gpu`.
- **Failover only before payment.** After payment the job is bound to a runner; a timeout leaves it `uncertain`.
- **`per_application` mode** needs `LPB_SHARED_PAYMENT_KEY` and `LPB_SHARED_ALLOCATION_ID`; jobs still carry `actor_id`.
- **`LPB_BATTERIES_OPERATOR_TOKEN` is required** when `LPB_BATTERIES_URL` is set, even if we never create grants from the app.
- **Money is `Decimal`**; a cost status of `none` means "not yet known", never free.
- **One engine process per database.** Fine: one container.
- **Discovery** refreshes every `LPB_DISCOVERY_INTERVAL_S` (15 s) and is stale after three misses.

## Extension points we use

- `DiscoverySource`: a wrapper over `SignerDiscoverySource` keeping only `app == blueclaw/chat/qwen3.8-27b` on hosts in D8.
- `SelectionPolicy`: the default `MostCapacityFirst` for now.
- Everything else: defaults.
