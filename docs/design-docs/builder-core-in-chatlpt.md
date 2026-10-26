# builder-core in ChatLPT

How ChatLPT uses livepeer-builder: the classes on each side of the boundary, and the flows that cross
it. Every box and message is a real class, method, route or setting in this repository or in
builder-core, so each diagram leads to the code. The diagrams describe the code pinned to builder-core
`985f23d`, which has the discovery service (builder-core D43).

This is the consumer's view. The engine's own interfaces and its REST server are drawn in builder-core's
[interfaces-and-http-servers.md](https://github.com/NE-Build-Track/livepeer-builder-core/blob/tasks/mz/interface-walkthrough/docs/design-docs/interfaces-and-http-servers.md).
The list of calls and the behavior to design around is in [builder-engine.md](../references/builder-engine.md).

**Notation.** `<<interface>>` is a `typing.Protocol`, satisfied structurally (`..|>`). `-->` means
"holds", `..>` means "calls", `X?` is optional and `X[]` a sequence. Classes from builder-core are
marked `builder-core`.

## What runs where

ChatLPT embeds the engine in its own process (imported mode). It does not run builder-core's REST
service, and it never reaches the signer, Batteries or an orchestrator itself: the engine does.

```mermaid
flowchart LR
    Browser["Browser (React UI)"]
    subgraph Box["chatlpt container"]
        App["ChatLPT: FastAPI, services, chatlpt.db"]
        Eng["BuilderEngine (embedded): livepeer-builder.db"]
    end
    Disc["discovery (lpb discovery, static list)"]
    Signer["signer (livepeer-node)"]
    CH["clearinghouse (Batteries)"]
    Orch["Orchestrators: chat and image runners"]
    IdP["Google, GitHub"]
    Browser -->|"session cookie, SSE"| App
    App -->|"ActorApi calls, in-process"| Eng
    App --> IdP
    App -->|"fetch generated image bytes"| Orch
    Eng -->|"LPB_DISCOVERY_URL: GET /discovery"| Disc --> Orch
    Eng -->|"sign (shared lpg_ key)"| Signer -->|"webhook"| CH
    Eng -->|"paid HTTP"| Orch
    Eng -->|"GET /v1/usage"| CH
```

## The part of builder-core ChatLPT uses

| builder-core | How ChatLPT uses it | Where |
| --- | --- | --- |
| `EngineSettings` | From `LPB_*`, passed to the composition root as a value | `runtime/engine.py` |
| `BuilderEngine.create(settings, decorate=...)` | Builds the engine once at startup, typed as `ActorApi` afterwards | `runtime/engine.py`, `runtime/app.py` |
| `Decorate` and `EngineParts.discovery_source` | Wraps the engine's `HttpDiscoverySource` in `FilteredDiscovery` | `runtime/engine.py`, `adapters/discovery.py` |
| `ActorContext` | One per signed-in user: `actor_id=<user id>`, `application_id="chatlpt"`, four permissions | `adapters/engine.py` (`actor_for`) |
| `jobs.streaming.stream` and `JobStreamApi` | A chat reply, streamed | `StreamingEngineChat` |
| `jobs.run` | A reply when the transport cannot stream, the model card (`GET /v1/models`) and every image | `BufferedEngineChat`, `EngineImages` |
| `jobs.report_usage` | Token counts after a reply, a courtesy copy | `BufferedEngineChat.report_usage` |
| `costs.for_job`, `costs.summary` | The network cost of a message or image, and a user's totals, read each time they are shown (D29) | `BufferedEngineChat.wholesale`, `network_totals` |
| `health()`, `discovery.candidates` | Readiness: can a reply or an image run now? | `BufferedEngineChat.ready`, `EngineImages.ready` |
| `JobFailed` and the `EngineError`s | Translated into ChatLPT's own errors at the adapter | `adapters/engine.py` (`failure_from`) |

**Not used:** `AdminApi` (provisioning, keys, grants, reconciliation), builder-core's REST service, and
engine API keys. Payment runs in `per_application` mode: one shared allocation key for the whole app,
with each job still recording the user as its actor.

## Key classes

### Composition

`Application` is ChatLPT's composition root. It builds the store, the engine and the adapters, then
every service from them, and owns their lifecycle. There is no DI container.

```mermaid
classDiagram
    direction LR
    class Application {
        +from_settings(settings, engine_settings)$ Application
        +async start() None
        +async stop() None
        +async health() AppHealth
        +store AppStore
        +backend ChatBackend?
        +auth, conversations, chat, context
        +images, network, billing, admin
        -engine ActorApi?
    }
    class build_engine {
        <<function>>
        settings, apps, approved_hosts, clock
        returns BuilderEngine and FilteredDiscovery, or None
    }
    class BuilderEngine {
        builder-core
        +create(settings, supply, decorate)$
    }
    class FilteredDiscovery {
        -inner DiscoverySource
        -apps, hosts
        +async fetch() Runner[]
        +model_from_discovery(app) ModelInfo?
    }
    class StreamingEngineChat
    class BufferedEngineChat
    class EngineImages
    class SqlStore {
        chatlpt.db
    }
    Application ..> build_engine : from_settings
    build_engine ..> BuilderEngine : create(decorate=filter_discovery)
    build_engine ..> FilteredDiscovery : wraps parts.discovery_source
    Application --> SqlStore
    Application --> StreamingEngineChat : if engine.jobs.streaming
    Application --> BufferedEngineChat : otherwise
    Application --> EngineImages : if tools are on
    Application --> FilteredDiscovery : as ModelMetadataSource
```

Without both `LPB_SIGNER_URL` and `LPB_DISCOVERY_URL`, `build_engine` returns `None`: the app still
runs, with chat and images reported unavailable in `/readyz`.

### The engine boundary

Services never see builder-core. They call ChatLPT's own ports (`ChatBackend`, `ImageBackend`,
`ModelMetadataSource`), and only the adapters import `livepeer_builder`.

```mermaid
classDiagram
    direction LR
    class ChatBackend {
        <<interface>>
        +app str
        +async open_reply(user_id, turns, params, operation_ref, tools) ReplyStream
        +async model_info(user_id) ModelInfo
        +async wholesale(user_id, job_id) WholesaleCost
        +async network_totals(user_id, start, end) NetworkTotals
        +async report_usage(user_id, job_id, usage) None
        +ready() bool and reason
    }
    class ReplyStream {
        <<interface>>
        +job_id UUID?
        +orchestrator_url str?
        +async for ReplyChunk
    }
    class ImageBackend {
        <<interface>>
        +app str
        +async generate(user_id, prompt, image_size, operation_ref) ImageResult
        +ready() bool and reason
    }
    class ModelMetadataSource {
        <<interface>>
        +model_from_discovery(app) ModelInfo?
    }
    class BufferedEngineChat {
        -engine ActorApi
        jobs.run, costs.for_job, costs.summary
    }
    class StreamingEngineChat {
        -streaming StreamingApi
        jobs.streaming.stream
    }
    class BufferedReply
    class StreamingReply {
        -stream JobStreamApi
        SseDecoder, ToolCallAssembler
    }
    class EngineImages {
        -engine ActorApi
        one jobs.run per picture
    }
    class FilteredDiscovery
    class ActorApi {
        <<interface>>
        builder-core
    }
    class JobStreamApi {
        <<interface>>
        builder-core
    }
    class DiscoverySource {
        <<interface>>
        builder-core
    }
    BufferedEngineChat ..|> ChatBackend
    BufferedEngineChat <|-- StreamingEngineChat
    BufferedReply ..|> ReplyStream
    StreamingReply ..|> ReplyStream
    EngineImages ..|> ImageBackend
    FilteredDiscovery ..|> ModelMetadataSource
    FilteredDiscovery ..|> DiscoverySource
    FilteredDiscovery --> DiscoverySource : inner
    BufferedEngineChat --> ActorApi
    EngineImages --> ActorApi
    StreamingEngineChat ..> StreamingReply : returns
    BufferedEngineChat ..> BufferedReply : returns
    StreamingReply --> JobStreamApi
```

`FilteredDiscovery` sits on both sides: to the engine it is a `DiscoverySource`, and to ChatLPT a
`ModelMetadataSource` that remembers each app's smallest advertised context window (D14).

### Services and their ports

```mermaid
classDiagram
    direction LR
    class ChatService {
        +start_reply(user, conversation_id, request) ReplyQueue
        +start_continue(user, conversation_id, message_id) ReplyQueue
        +async drain() None
    }
    class ContextService {
        +async window(user_id, app) int
        +fit(system_prompt, history, window, reserve)$ turns, dropped
    }
    class ImageService {
        +async generate(user, conversation, message_id, prompt, image_size) GeneratedImage
        +async expire_old() int
    }
    class NetworkCostService {
        +async with_costs(user_id, messages) Message[]
        +async user_totals(user_id, start, end) UsageTotals
        +async totals_by_user(users, start, end) UsageTotals[]
    }
    class BillingService {
        +retail(usage, thinking) Money
    }
    class ConversationService
    class AuthService
    class AdminService
    class ChatBackend {
        <<interface>>
    }
    class ImageBackend {
        <<interface>>
    }
    class ModelMetadataSource {
        <<interface>>
    }
    class AppStore {
        <<interface>>
        UserStore, ConversationStore, UsageLedger
        ModelInfoCache, ImageRepo
    }
    class ImageFiles {
        <<interface>>
    }
    class PriceSource {
        <<interface>>
    }
    ChatService --> ChatBackend
    ChatService --> ContextService
    ChatService --> ImageService
    ChatService --> BillingService
    ChatService --> ConversationService
    ChatService --> AppStore : messages, ledger
    ContextService --> ChatBackend : model_info
    ContextService --> ModelMetadataSource
    ContextService --> AppStore : model info cache
    ImageService --> ImageBackend
    ImageService --> ImageFiles
    ImageService --> AppStore : images, ledger
    NetworkCostService --> ChatBackend : wholesale, network_totals
    NetworkCostService --> AppStore : ledger
    AdminService --> NetworkCostService
    BillingService --> PriceSource
```

### The HTTP layer

```mermaid
classDiagram
    direction LR
    class create_app {
        <<function>>
        app Application, manage_lifecycle
        routes, error handler, lifespan, static UI
    }
    class Sessions {
        signed cookie chatlpt_session
        +issue(response, user_id) None
        +read(request) UUID?
    }
    class current_user_dependency {
        <<function>>
        cookie to User, else NotAuthenticated
    }
    class csrf_guard {
        <<function>>
        x-chatlpt header on writes
    }
    class auth_router {
        /api/auth: signup, login, logout, me, oauth, claim
    }
    class chat_router {
        /api: model, conversations, messages SSE, continue, images, usage/me
    }
    class admin_router {
        /api/admin: users, disabled
    }
    class Application
    create_app ..> Sessions
    create_app ..> current_user_dependency
    create_app ..> auth_router
    create_app ..> chat_router
    create_app ..> admin_router
    chat_router ..> csrf_guard
    chat_router ..> Application : services
    current_user_dependency ..> Application : auth.current
```

Routes call services, never the engine. The engine appears in HTTP only through `/readyz`
(`Application.health`) and the `/api/model` availability check.

## Flows

### Startup and shutdown

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant CLI as chatlpt serve
    participant App as Application
    participant Store as SqlStore
    participant BE as build_engine
    participant Eng as BuilderEngine
    participant FD as FilteredDiscovery
    participant U as uvicorn and lifespan
    Op->>CLI: chatlpt serve
    CLI->>App: from_settings(Settings, EngineSettings.from_env())
    App->>Store: connect(chatlpt.db, migrate)
    App->>BE: build_engine(settings, apps, approved_hosts, clock)
    alt LPB_SIGNER_URL or LPB_DISCOVERY_URL missing
        BE-->>App: None (chat and images unavailable)
    else both set
        BE->>Eng: create(settings, decorate=filter_discovery)
        Note over Eng,FD: decorate replaces parts.discovery_source with FilteredDiscovery(HttpDiscoverySource)
        Eng-->>BE: engine
        BE-->>App: engine, FilteredDiscovery
        App->>App: StreamingEngineChat if engine.jobs.streaming, else BufferedEngineChat
        App->>App: EngineImages if tools are on
    end
    App->>App: build every service
    CLI->>U: serve(create_app(app))
    U->>App: start()
    App->>Eng: start() (recover jobs, first discovery, background loops)
    App->>App: task image-retention
    Op->>U: SIGTERM
    U->>App: stop()
    App->>App: chat.drain() (replies in flight finish and are saved)
    App->>Eng: stop()
    App->>Store: close()
```

`stop()` runs every step even when one fails, so a stuck engine never keeps the database open.

### Discovery and the context window

```mermaid
sequenceDiagram
    autonumber
    participant DS as DiscoveryService (engine)
    participant FD as FilteredDiscovery
    participant H as HttpDiscoverySource (engine)
    participant Svc as discovery service
    participant Ctx as ContextService
    participant Cache as AppStore (model info)
    participant B as ChatBackend
    loop every LPB_DISCOVERY_INTERVAL_S
        DS->>FD: fetch()
        FD->>H: fetch()
        H->>Svc: GET /discovery
        Svc-->>H: runners of every orchestrator
        H-->>FD: Runner[]
        FD->>FD: keep our apps on approved hosts
        FD->>FD: parse runner.metadata, keep the smallest max_context per app
        FD-->>DS: Runner[] (errors propagate: the engine keeps its last snapshot)
    end
    Note over Ctx: on every reply
    Ctx->>FD: model_from_discovery(app)
    alt the runner advertised its window (free)
        FD-->>Ctx: ModelInfo
        Ctx->>Cache: put_model_info if it changed
    else nothing advertised
        Ctx->>Cache: get_model_info(app), fresh within the TTL
        opt missing or stale
            Ctx->>B: model_info(user_id) (a paid GET /v1/models job)
        end
    end
```

### A chat reply, streamed

The route returns at once with an SSE response. The reply runs in its own task, which writes to a
queue the route drains. A browser that leaves therefore never cancels a paid reply: the task reads the
engine's stream to the end and saves the message.

```mermaid
sequenceDiagram
    autonumber
    actor Br as Browser
    participant R as chat_router send
    participant Chat as ChatService
    participant Ctx as ContextService
    participant Store as AppStore
    participant SEC as StreamingEngineChat
    participant Eng as engine.jobs.streaming
    participant JS as JobStream (engine)
    participant SR as StreamingReply
    participant Bill as BillingService
    Br->>R: POST /api/conversations/{id}/messages (cookie, x-chatlpt)
    R->>R: csrf_guard, current_user, conversations.get (404 before the stream)
    R->>Chat: start_reply(user, conversation_id, NewMessage)
    Chat-->>R: queue (a task now runs the reply)
    R-->>Br: 200 text/event-stream, drains the queue
    Chat->>Chat: backend.ready() (ChatUnavailable becomes an error event)
    Chat->>Store: add_message(user message)
    Chat->>Ctx: window(user_id, app), then fit(system prompt, history)
    Chat->>Store: add_message(assistant placeholder, state streaming)
    Chat-->>Br: event start
    Chat->>SEC: open_reply(user_id, turns, params, operation_ref=placeholder id, tools)
    SEC->>Eng: stream(actor_for(user_id), JobRequest(stream, include_usage, idle_timeout_s))
    Note over Eng: admission, attempt, payment, failover before payment
    Eng-->>SEC: JobStream
    SEC-->>Chat: StreamingReply(JobStream, orchestrator_url)
    loop runner SSE bytes
        JS-->>SR: bytes
        SR->>SR: SseDecoder.feed, ToolCallAssembler.feed
        SR-->>Chat: ReplyChunk reasoning or content
        Chat-->>Br: event reasoning or content
    end
    SR-->>Chat: ReplyChunk tool_call (if any), usage, done
    Note over JS: read to the end: the engine records the job succeeded
    Chat->>Bill: retail(usage, thinking)
    Chat->>Store: update_message(complete, job_id, usage, retail)
    Chat->>Store: record(UsageRecord) (the retail book)
    Chat->>SEC: report_usage(user_id, job_id, usage)
    SEC->>Eng: jobs.report_usage(actor, job_id, quantities) (failure only logged)
    Chat-->>Br: event done (wholesale pending)
```

Continuing a reply that hit the output limit (`/continue`, D24) is the same pipeline with the partial
answer as the final turn and `continue_final_message` set; it adds a new assistant message.

### When a reply fails

`failure_from` turns the engine's `JobFailed` into ChatLPT's errors, at the adapter. The engine's job
id stays on the message, so a paid failure still shows its network cost.

| Engine | ChatLPT | The message | The browser |
| --- | --- | --- | --- |
| `JobFailed` with `no_offering`, `no_capacity`, `not_provisioned`, `refused`, `unreachable`, `payment` | `ChatUnavailable` | `failed`, `unavailable` | `error` event with `retry_after_s` |
| `NoCapacity`, `NotProvisioned`, `ProviderUnavailable` | `ChatUnavailable` | `failed`, `unavailable` | `error` event with `retry_after_s` |
| `JobFailed` with `timeout` or `abandoned`, or job state `uncertain` | `ReplyFailed(uncertain=True)` | `uncertain`, partial text kept, `job_id` | `error` event |
| any other `JobFailed` | `ReplyFailed(payment_sent=...)` | `failed`, partial text kept, `job_id` | `error` event |
| `OperationExists`, `OperationConflict` | `Conflict` | left `streaming` (see question 6) | `error` event |
| any other `EngineError` | `ReplyFailed(payment_sent=False)` | `failed` | `error` event |

Once the SSE response has started, every error reaches the browser as an `error` event, not as an HTTP
status. Errors before it (`401`, `404`, a missing `x-chatlpt` header) are ordinary statuses from the
`AppError` handler.

### A reply that draws an image

When the model answers with a `generate_image` tool call, the reply becomes a `tool_call` message, the
image runs as a separate buffered job, and a second model call captions it (D25).

```mermaid
sequenceDiagram
    autonumber
    actor Br as Browser
    participant Chat as ChatService
    participant Img as ImageService
    participant EI as EngineImages
    participant Eng as engine.jobs
    participant Files as LocalImageFiles
    participant Store as AppStore
    Note over Chat: the reply stream ended with a generate_image tool call
    Chat->>Store: update_message(kind tool_call)
    Chat-->>Br: event tool_call
    loop at most two calls
        Chat->>Img: generate(user, conversation, message_id, prompt, image_size)
        Img->>EI: generate(user_id, prompt, size, operation_ref=image id)
        EI->>Eng: run(actor, JobRequest(image app, path /, timeout_s 120))
        Eng-->>EI: JobResult (the runner's temporary image URL)
        EI-->>Img: EngineImageResult(url, size, seed, job_id)
        Img->>Files: fetch(url), save(image_id, bytes)
        Img->>Store: add_image, record(UsageRecord kind image)
        Img-->>Chat: GeneratedImage (wholesale pending)
        Chat-->>Br: event image
    end
    Chat->>Store: update_message(complete, images)
    Chat-->>Br: event done
    Chat->>Chat: produce again with the tool results, no tools (the caption)
```

### Showing what a reply cost

ChatLPT keeps two books (D29). The retail book (what the user is charged) lives in ChatLPT's ledger.
The network book (what Livepeer charged) stays in the engine and is read each time it is shown. They
join on the job id.

```mermaid
sequenceDiagram
    autonumber
    actor Br as Browser
    participant R as chat_router
    participant Net as NetworkCostService
    participant B as BufferedEngineChat
    participant Eng as engine.costs
    participant Ledger as AppStore (ledger)
    Br->>R: GET /api/conversations/{id}
    R->>Net: with_costs(user_id, messages)
    loop each message or image with a job_id
        Net->>B: wholesale(user_id, job_id)
        B->>Eng: for_job(actor, job_id)
        Eng-->>B: JobCost (pending, none, observed, corrected)
        B-->>Net: WholesaleCost (delivered, failed_after_payment, uncertain, pending, none)
    end
    R->>Ledger: conversation_totals(conversation_id) (retail)
    R-->>Br: messages with retail and network cost, totals
    Br->>R: GET /api/usage/me
    R->>Net: user_totals(user_id, month)
    Net->>Ledger: totals(user_id, start, end)
    Net->>B: network_totals(user_id, start, end)
    B->>Eng: summary(actor, start, end)
    R-->>Br: UsageTotals (retail, delivered, failed, pending)
```

A cost the engine cannot answer is shown as `unknown`, never as $0.

## Questions for the review

Points worth deciding, noticed while drawing these:

1. **Readiness reads `discovery.candidates`.** `BufferedEngineChat.ready` and `EngineImages.ready`
   call it, and it checks no permission (builder-core review question 1). If builder-core moves it,
   ChatLPT needs another way to ask "can this app run now?".
2. **The same error translation appears three times.** `BufferedEngineChat._run`,
   `StreamingEngineChat.open_reply` and `EngineImages.generate` repeat the same `except` clauses.
3. **A reply is read to the runner's end.** `StreamingReply` never calls `JobStream.complete()`, so a
   runner that sends `data: [DONE]` and then holds the connection keeps the job open until
   `idle_timeout_s`.
4. **The model card is a paid job.** `GET /v1/models` runs through `jobs.run` whenever discovery
   metadata is missing and the cached window is stale (D14).
5. **Per-user cost relies on `actor_id` alone.** In `per_application` mode every user shares one
   allocation, so the engine's per-user totals depend on the job's actor, not on separate allocations.
6. **A reply can stay `streaming`.** `ChatService._produce` updates the placeholder only on
   `ReplyFailed` and `ChatUnavailable`. A `Conflict`, an unexpected error, or a restart mid-reply leaves
   the message `streaming`, and nothing resolves it on start, unlike the engine's
   `recover_interrupted`. The engine's job record is still correct.
