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

- [ ] `uv run pytest`, ruff, mypy, `scripts/check_docs.py` pass; coverage floors hold.
- [ ] No module or test imports `livepeer_gateway` or a non-public `livepeer_builder` module.
- [ ] No test sets or deletes an `LPB_*` environment variable.
- [ ] A failure while building the application closes the store it opened (a failing-first test).
- [ ] References (`builder-engine.md`, `payment-stack.md`, SECURITY, ARCHITECTURE, `.env.example`) and D2 updated.

## Progress

- 2026-10-23: plan opened. Re-pinned to `bdf2630`: 2 tests and mypy fail on `from_settings` and
  `jobs.stream`; with `hasattr`, the runtime would silently fall back to the buffered adapter.
- 2026-10-23: built with `create`; the streaming adapter is picked by `jobs.streaming` (`348c54b`).
- 2026-10-23: discovery decorates `parts.discovery_source` (`FilteredDiscovery`); ChatLPT no longer imports
  `livepeer_gateway` (now allowed nowhere) or `livepeer_builder.adapters.sdk`. The default's signer header
  and discovery URL now reach discovery, which the replacement had dropped.

## Decision log

- 2026-10-23: the work is on `tasks/mz/dependency-injection-refactor`, branched from `main`; PR #40's
  pin is not carried (owner's call).
- 2026-10-23: discovery is a decorator over the configured default. The default asks the signer for
  every app, not only ours, and the decorator filters; the payload is small and this keeps the signer
  header and `LPB_DISCOVERY_URL` handling in one place.
