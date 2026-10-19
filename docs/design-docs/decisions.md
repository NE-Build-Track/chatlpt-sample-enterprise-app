# Decisions

Accepted by the owner (Mike Zupper) on 2026-10-19 unless noted. Changing one is an escalation.

| # | Decision | Why |
| --- | --- | --- |
| D1 | **Streaming is a requirement**, and the design must be generic to builder-core, not specific to ChatLPT. | Other apps on the engine need incremental text and media. |
| D2 | Pin `livepeer-builder` to the **`v0.1.0`** tag (the M2 close-out). Move the pin to the streaming branch once it exists. The branch is `tasks/m3/mz/stream-support` off `releases/m3`. | v0.1.0 is the reviewed baseline; the streaming work decides the next pin. |
| D3 | **One shared application payment key** (`per_application` mode). The app tracks per-user input and output tokens (retail) and the engine's per-job network cost (wholesale). Both are kept. | Enterprise pays the network once; the app owns customer accounting. |
| D4 | **Retail prices come from Alibaba Cloud's list prices for Qwen3.8-27B**, international (Singapore) region, in USD, with input, cached input, output and thinking-mode output priced separately. The table is a dated file in the repository with its source URL. | A "hypothetical" cost like ChatGPT's needs a public, defensible rate. |
| D5 | **Email and password accounts** in SQLite, **self-signup open**. No magic links. | Simplest credible enterprise login for a sample. |
| D6 | **Google (OIDC) and GitHub (OAuth 2.0) sign-in** when configured; accounts link by verified email. | Common enterprise identity providers; one library handles both. |
| D7 | Admins are the emails in `CHATLPT_ADMIN_EMAILS`. | No bootstrap ceremony; auditable in config. |
| D8 | Orchestrators: `https://orch-us-central.xodeapp.xyz:18935`, `https://us-central-metrics.speedybird.xyz:28935`, `https://orch-eu-central.open-pool.com:443`, `https://hky.eliteencoder.net:8936`. The engine's discovery is filtered to the chat app on these hosts. | These run `blueclaw/chat/qwen3.8-27b` today (evidence in builder-core, 14 and 19 October). |
| D9 | **Rebuild** the Clearinghouse Batteries and node signer images from the pinned commits (`ca09e47`, `406b248`) in `scripts/build-images.sh`. Never push from the script. | Reproducible stack; same pins as builder-core's dev-stack. |
| D10 | **Run the full payment stack in dev** from this repository's compose file, reading the payer keystore from `~/.livepeer/keys/cloud-spe-gateway`. Do not point at another running signer. One signer per payer account at a time. | Two signers on one keystore is asking for trouble. |
| D11 | **SQLite** for both the app database and the embedded engine's database, on one volume. | One container, no database service, enough for a sample. |
| D12 | Harness-engineering approach: AGENTS.md as a map, `docs/` as the system of record, structural tests, exec plans. **No beads.** **No attribution trailers** in commits or PRs. Commit as you go; never push without review. | Owner preference; matches builder-core. |
| D13 | **No GitHub CI in v1.** Checks run locally and are listed in AGENTS.md. | Scope; v2. |
| D14 | **The context window is derived**, not configured. Order: the runner's discovery `metadata` (`max_context`, `model_id`; free, observed 2026-10-19 as 131072 for Qwen3.8-27B), then the cached value, then `GET /v1/models` (`max_model_len`, a paid call), then a stale cache, then `CHATLPT_CONTEXT_WINDOW_OVERRIDE`, then 8192. History is truncated to fit it minus the output reserve. | The model on the network knows its own limits; the metadata costs nothing. |
| D15 | Show the model's **reasoning** in a collapsible block when present; reasoning tokens are billed as output in retail. | Matches ChatGPT; matches how Alibaba bills. |
| D16 | Conversation titles come from the first user message. No extra paid call. | Every call spends money. |
| D17 | A minimal **admin page** shows per-user retail vs wholesale totals and the margin. | The margin is the point of the demo. |
| D18 | The public base URL and port are settings (`CHATLPT_PUBLIC_BASE_URL`, default `http://localhost:3050`). | OAuth callbacks need it; no preference yet. |
| D19 | Token counts come from the runner's `usage` with `stream_options.include_usage`; the app also reports them to the engine with `report_usage`, so both books share the job id. | One source of truth for tokens. |
| D20 | The ChatLPT engine adapter is **streaming-shaped from day one**. The v0.1.0 implementation yields the whole reply as one chunk; the streaming implementation yields deltas. Only `adapters/engine.py` changes. | Nothing in the app is written twice. |
| D21 | Order of work: scaffold ChatLPT end to end against v0.1.0 first (proves payments, auth, billing), write the builder-core streaming exec plan in parallel, then build the branch, then swap the adapter. | Validate the most things with the least new code. |
| D22 | MIT license; the repository lives under the NE-Build-Track organization. | Matches builder-core. |
