# Plan 01: foundation

## Goal

A repository an agent can work in: the map, the decisions, the layers, a runnable backend
skeleton, a buildable UI skeleton, the deploy files, and the checks that enforce the rules.

## Scope

- `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `README.md`, `LICENSE`, `.gitignore`.
- `docs/`: index, product spec, decisions, core beliefs, streaming design, plans, tech debt,
  references, reliability, security, frontend, design, quality score.
- `pyproject.toml` (uv, Python 3.12, `livepeer-builder @ v0.1.0`), `src/chatlpt/` with every layer
  present and `chatlpt serve` answering `/readyz`.
- `web/` with Vite, React, TypeScript, Tailwind and shadcn/ui, building to `web/dist`.
- `deploy/`: `compose.yaml`, `Dockerfile`, signer and clearinghouse config, `init-secrets.py`,
  `.env.example`; `scripts/build-images.sh`.
- `tests/structure/`: layers, third-party confinement, file size, docs links; `scripts/check_docs.py`.

## Out of scope

Working sign-in, a paid reply, billing. Those are plans 02 to 04.

## Acceptance

- [x] `uv run pytest`, `uv run ruff check .`, `uv run mypy`, `uv run python scripts/check_docs.py` pass.
- [x] `uv run chatlpt serve` answers `GET /readyz` with the engine not configured (degraded, honest).
- [x] `cd web && pnpm build` produces `web/dist`, and the server serves it.
- [ ] `scripts/build-images.sh` builds the three images locally without pushing.
- [x] `docker compose -f deploy/compose.yaml config` validates.

## Progress

- 2026-10-19: decisions D1–D22 recorded; map, architecture, product spec, streaming design written.
- 2026-10-19: every layer exists and is wired. Accounts (email/password, provider sign-in), conversations, the
  reply pipeline with both books, the context-window derivation, the admin page and the React UI are
  implemented against the in-memory and SQLite stores; 322 tests pass (unit, store contract, HTTP). The server
  boots degraded without the payment stack and serves the built UI. What plan-01 did **not** do: run a paid
  reply (plan-02), configure a provider (plan-03), or verify the UI against a live engine (plan-04).

## Decision log

- 2026-10-19: layers and third-party confinement copied from builder-core so an agent moving between
  the two repositories meets the same rules.
- 2026-10-19: the reply runs in a detached task writing to a queue; the SSE route reads the queue. A browser
  that leaves mid-reply never cancels paid work (ARCHITECTURE.md#a-reply-end-to-end).
- 2026-10-19: the model-info cache is stamped with the app clock, not the backend's, so the TTL is ours.
- 2026-10-19: `tests/store/test_contract.py` runs against both `MemoryStore` and `SqlStore`, so the fake can
  never drift from the real store.
- 2026-10-19: Google sign-in reads identity from the OIDC userinfo endpoint with the access token rather than
  verifying the `id_token` locally; both are authenticated by Google over TLS, and it avoids a JWKS cache.
