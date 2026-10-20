# ChatLPT: a ChatGPT-style chat product on Livepeer

Status: accepted by the owner on 2026-10-19. Decisions are numbered in
[decisions.md](../design-docs/decisions.md).

## Who it is for

An enterprise that wants to give its people a ChatGPT-like assistant while paying the Livepeer
network wholesale for inference, and that needs to know, per user, what the network charged
(wholesale) and what the same usage would have cost at a model vendor's list price (retail).

## Motivation

Public chat products hide two numbers: what the provider paid for the compute and what the tokens
would cost at list price. ChatLPT shows both next to every reply. It is the reference application
for the livepeer-builder engine in embedded mode, and the reference for building such an app with
coding agents.

## Phase 1

### Accounts

- **Email and password** accounts stored in SQLite. Passwords are hashed with argon2id. Self-signup
  is open (D5).
- **Sign in with Google** (OpenID Connect) and **Sign in with GitHub** (OAuth 2.0; the app reads the
  verified primary email from GitHub's API). Each appears only when its client id and secret are
  configured. Accounts link by verified email (D6).
- Sessions are signed, HTTP-only cookies. The browser never holds an engine, payment or admin
  credential.
- Users listed in `CHATLPT_ADMIN_EMAILS` are admins (D7).

### Chat

- Looks and behaves like ChatGPT: a conversation sidebar, a composer, Markdown replies with code
  blocks, a stop button, and a collapsible **Thinking** block when the model returns reasoning (D15).
- One model: `blueclaw/chat/qwen3.8-27b`, served by vLLM on the approved orchestrators (D8).
- Replies stream token by token through the engine (D1).
- A reply cut off at the output limit offers **Continue generating** (D24); the continuation is a new
  segment that renders attached to the reply. Each conversation has a **thinking level**, off to high.
  A reply says when earlier turns were left out to fit the model's context.
- The conversation title is the first user message, trimmed. No extra paid call (D16).
- History sent to the model is truncated to fit the runner's context window, derived from the
  model's own `max_model_len` (D14). The system prompt, temperature and output cap are settings.
- Users can rename and delete conversations. Deleting removes the messages; usage records remain.

- **Images are model-driven** (D25): the assistant is offered a `generate_image` tool and decides when
  to draw; the app runs `comfystream/fal-flux-schnell` through the engine, stores the file on the
  volume for `CHATLPT_IMAGE_RETENTION_DAYS`, and the model captions it. Images render inline with
  prompt, size, retail (fal's list price per megapixel) and network cost. No image button.

### Usage and cost

Every assistant message records, and the UI shows:

| Field | Source | Book |
| --- | --- | --- |
| Prompt, completion and reasoning tokens | the runner's `usage` in the final chunk | both |
| **Retail** cost in USD | tokens × Alibaba Cloud Qwen3.8-27B list prices (D3, D4) | retail |
| **Wholesale** cost in USD | the engine's cost for the job, `pending` until it arrives (D3) | wholesale |

- The price table lives in the repository with its source URL and the date observed
  ([qwen-pricing](../references/qwen-pricing.md)). Input, cached input, output and thinking-mode
  output are priced separately.
- A conversation shows its running totals. A user's page shows their totals for the month.
- Wholesale is never guessed from retail or the other way around.

### Admin

- A minimal admin page: users, their token totals, retail and wholesale totals, and the margin.
- Admins can disable a user. There are no quotas in phase 1.

## Phase 2 (not scheduled)

- GitHub CI and the agent review loop.
- Per-user token or dollar quotas.
- File uploads, image input, image editing.
- More models as orchestrators advertise them.

## Constraints

- One container for the app; the payment stack (Clearinghouse Batteries and the node remote signer)
  runs beside it from the same compose file (D10).
- Python 3.12 with uv, FastAPI; React with shadcn/ui served as static files; SQLite for both the app
  and the embedded engine (D11).
- builder-core pinned to the streaming branch until it merges, then to a release (D2).
