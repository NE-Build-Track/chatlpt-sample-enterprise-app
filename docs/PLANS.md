# Plans

Work larger than a small change has an **exec plan** in `docs/exec-plans/active/`. A plan names its
goal, scope, acceptance checks, a progress log and a decision log. It moves to `completed/` when its
acceptance checks pass, in the same commit. Known shortcuts go to
[tech-debt-tracker.md](exec-plans/tech-debt-tracker.md) with an owner and a trigger for paying them.

`scripts/check_docs.py` checks that every plan has those sections and that every link resolves.

## Order of work (D21)

| Plan | Goal | Status |
| --- | --- | --- |
| [plan-01-foundation](exec-plans/completed/plan-01-foundation.md) | Repository map, docs, decisions, scaffold of backend, UI, deploy and checks | completed 2026-10-19 |
| [plan-02-payments-stack](exec-plans/completed/plan-02-payments-stack.md) | Compose with Batteries, signer and the shared allocation; first paid reply end to end | completed 2026-10-19 |
| plan-03-accounts | Email/password, Google, GitHub, sessions, admins | delivered 2026-10-20 with D26–D28 (verified email wins, claims, `chatlpt make-admin`, OAuth hardening, attempt limits); remaining: a live Google and GitHub sign-in test |
| plan-04-chat-and-billing | Conversations, replies, context window, two books, admin page | delivered with plans 01–02 and D23–D24 (continue generating, thinking levels, dropped-turn notes, 2026-10-19); a browser test suite is the remaining item |
| plan-05-engine-streaming (builder-core) | `tasks/m3/mz/stream-support`: contract, transport, REST, tests | implemented and shown live 2026-10-19 (`973ac57`); review fixes D34–D39 shown live 2026-10-20 (`a89216d`); PR #28 review fixes and D40 2026-10-21 (`93756ba`); merged to `releases/m3` 2026-10-21 with PR #31 (`ad6bba9`, pinned here) |
| [plan-06-streaming-adapter](exec-plans/completed/plan-06-streaming-adapter.md) | Move the pin, swap `adapters/engine.py`, verify deltas end to end | completed 2026-10-19 |
| [plan-07-model-driven-images](exec-plans/completed/plan-07-model-driven-images.md) | The assistant draws through a tool call; images stored, priced and captioned | completed 2026-10-19 |
| [plan-08-dependency-injection](exec-plans/completed/plan-08-dependency-injection.md) | Move onto builder-core's DI refactor: `create` with decorate, settings as values, `ActorApi`, `FakeEngine` | completed 2026-10-23; shown live on the deployed stack (23 replies and checks); pinned to `releases/m3` `629f1ab` (PRs #41 to #44 merged) |

Small changes do not need a plan; they need a test and a sentence in the commit.

## Backlog: to be specified

Not scheduled. Each item needs a spec (and an exec plan) before work starts.

| Item | What we know (2026-10-20) |
| --- | --- |
| Voice input for the prompt | A microphone button in the composer: record up to ~60 s, transcribe, put the text in the composer to edit (never auto-send). Transcription on Livepeer: `blueclaw/audio/whisper-large-v3` (open-pool eu-central) and `comfystream/fal-whisper-transcribe` (ai1), both on D8 hosts. Capture: reuse meeting-manager-app's worklet and `wav.ts` (16 kHz mono WAV); its VAD, chunker and upload queue are for hour-long meetings and are not needed (Silero VAD maybe later for hands-free stop). **Blocker:** builder-core `JobRequest.payload` and the SDK's `call_runner` send JSON only, and Whisper wants multipart; builder-core needs generic non-JSON request bodies first (check whether the pinned SDK already supports multipart). Billing: a `transcription` ledger kind, retail at a dated Whisper list price, network cost read from the engine (D29). Needs HTTPS outside localhost. Avoid the browser Web Speech API (sends audio to Google or Apple, no Firefox). Later: Kokoro TTS (`blueclaw/speech/kokoro`) to read replies aloud. |
