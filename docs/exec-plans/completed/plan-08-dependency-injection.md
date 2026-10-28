# Plan 08: move onto builder-core's dependency-injection refactor

## Goal

Build the embedded engine the way builder-core now teaches (`BuilderEngine.create` with supply and
decorate, settings as values, the `JourneyApi` facade, the shipped `FakeEngine`), and apply the same
python-dependency-injection rules to ChatLPT's own composition root. builder-core's side is its plan
`docs/exec-plans/active/dependency-injection-refactor.md` (branch `tasks/mz/dependency-injection-refactor`).

## Scope

- Pin `livepeer-builder` to the refactor branch; build the engine with `BuilderEngine.create`.
- Pick the streaming adapter from the `jobs.streaming` capability instead of `hasattr`.
- Discovery decorates the engine's configured default (`parts.discovery_source`) instead of
  re-implementing it, so ChatLPT no longer imports `livepeer_gateway` or builder-core internals, and the
  signer header and discovery URL the default carries are kept.
- `build_engine` and `Application.from_settings` take `EngineSettings` as a value; tests stop setting
  `LPB_*` variables.
- Adapters are typed against `livepeer_builder.JourneyApi`; their tests use `livepeer_builder.testing.FakeEngine`
  instead of hand-written duck-typed fakes.
- ChatLPT imports only builder-core's public API (a structural test).
- `Application.from_settings` closes what it opened when a later step fails; `stop()` runs every
  shutdown step even when one fails.
- `LPB_BATTERIES_OPERATOR_TOKEN` leaves ChatLPT's configuration (the grant desk is optional in the engine).

## Out of scope

UI, services and stores; a DI container (python-dependency-injection guide, Rule 1); builder-core
changes beyond the refactor branch (its `FakeEngine` gaps found here were fixed there, `bdf2630`).

## Acceptance

- [x] `uv run pytest`, ruff, mypy, `scripts/check_docs.py` pass; coverage floors hold.
- [x] No module or test imports `livepeer_gateway` or a non-public `livepeer_builder` module.
- [x] Outside the CLI's own tests (the CLI reads the environment by design), no test sets or deletes an
  `LPB_*` variable; only `config.py` reads the environment (a structural test).
- [x] A failure while building the application closes the store it opened (a failing-first test).
- [x] References (`builder-engine.md`, `payment-stack.md`, SECURITY, ARCHITECTURE, `.env.example`) and D2 updated.

## Progress

- 2026-10-23: plan opened. Re-pinned to `bdf2630`: 2 tests and mypy fail on `from_settings` and
  `jobs.stream`; with `hasattr`, the runtime would silently fall back to the buffered adapter.
- 2026-10-23: built with `create`; the streaming adapter is picked by `jobs.streaming` (`348c54b`).
- 2026-10-23: discovery decorates `parts.discovery_source` (`FilteredDiscovery`); ChatLPT no longer imports
  `livepeer_gateway` (now allowed nowhere) or `livepeer_builder.adapters.sdk`. The default's signer header
  now reaches discovery; the replacement had dropped it (`0d7fb4d`).
- 2026-10-23: settings are values. `build_engine(engine_settings, ...)` and
  `Application.from_settings(settings, engine_settings)`; the CLI builds both from the environment.
  `test_settings.py` (only `config.py` reads the environment) failed first on the `CHATLPT_ADMIN_EMAILS`
  check in `from_settings`, which moved into `Settings.from_env` with a test; the unused
  `Settings.engine_configured` (an `LPB_SIGNER_URL` read) is gone. `livepeer_builder` may be imported
  anywhere in `runtime/`, the composition root.
- 2026-10-23: adapters are typed against `JourneyApi` and the runtime holds `JourneyApi | None` (no more
  `type: ignore` on `start`/`stop`). Their tests use builder-core's `FakeEngine` instead of three
  hand-written duck-typed fakes. The fake lacked what these tests needed (parsed `data`, attempts,
  failure part-way through a stream, repeated `operation_ref`, scripted engine errors, paid failures); those were
  added in builder-core with contract cases (`bdf2630`, `165e601`) and the pin moved to `165e601`.
  `tests/structure/test_engine_api.py` keeps every `livepeer_builder` import public; it failed first on
  six files importing `livepeer_builder.errors` and `.contracts`.
- 2026-10-23: cleanup on failure. `Application.from_settings` puts the store and the engine on an exit
  stack as they open, so a later failure (a missing pricing file) closes and stops them; `stop()` runs
  every step and logs `app.stop_failed` for one that fails; `chatlpt serve` stops the application in a
  `finally`, for a failure before the HTTP lifespan runs. Each behaviour failed its test first; stopping
  twice is tested as harmless.
- 2026-10-23: `LPB_BATTERIES_OPERATOR_TOKEN` is out of `.env.example`, SECURITY and the references (the
  engine's grant desk is off without it; ChatLPT never uses it). `builder-engine.md` describes `create`,
  the decorator, `jobs.streaming`, `JourneyApi` and `FakeEngine`; D2 records the pin. The pin to an
  unmerged branch is T9. Acceptance met; plan complete. Not done here: a reply through the deployed
  stack on this build.
- 2026-10-23 (after completion): builder-core renamed `JourneyApi` to `ActorApi` (its decision 14); the pin
  moved to `d6a7d9c` and the adapters, runtime and references follow. No behaviour changed.
- 2026-10-23 (after completion): builder-core PR #41 merged to `releases/m3` as `b89c1bb`, the same code as
  `a22bc98`. The pin moved there, which pays T9.
- 2026-10-23: re-pinned to `878e4f4`, the merge of builder-core PR #42: `FakeEngine` settles a cancelled
  stream as the engine does, and the README quick-start test is deterministic.
- 2026-10-24: re-pinned to `629f1ab`, the merge of builder-core PRs #43 and #44: a paid reply's
  wholesale cost reads `pending` until it settles (never $0 between syncs), and a cancelled or
  disconnected reply keeps its charge on the job. ChatLPT code is unchanged.
- 2026-10-27: re-pinned to `chore/pin-gateway` `5e6683a`, the head of builder-core PR #61 (D52, D53),
  to run ChatLPT against the engine-owned paid call before that pull request merges. ChatLPT still
  reads wholesale from `JobCost.fees` (everything the allocation paid). `JobCost.billable` is the
  delivered attempts only and is not the network book.

## Decision log

- 2026-10-23: the work is on `tasks/mz/dependency-injection-refactor`, branched from `main`; PR #40's
  pin is not carried (owner's call).
- 2026-10-23: discovery is a decorator over the configured default. The default asks the signer for
  every app, not only ours, and the decorator filters; the payload is small and this keeps the signer
  header and `LPB_DISCOVERY_URL` handling in one place.
