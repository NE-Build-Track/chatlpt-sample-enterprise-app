# Plan 01: foundation

**Goal:** a repository an agent can work in: the map, the decisions, the layers, a runnable backend
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

- [ ] `uv run pytest`, `uv run ruff check .`, `uv run mypy`, `uv run python scripts/check_docs.py` pass.
- [ ] `uv run chatlpt serve` answers `GET /readyz` with the engine not configured (degraded, honest).
- [ ] `cd web && pnpm build` produces `web/dist`, and the server serves it.
- [ ] `scripts/build-images.sh` builds the three images locally without pushing.
- [ ] `docker compose -f deploy/compose.yaml config` validates.

## Progress

- 2026-10-19: decisions D1–D22 recorded; map, architecture, product spec, streaming design written.

## Decision log

- 2026-10-19: layers and third-party confinement copied from builder-core so an agent moving between
  the two repositories meets the same rules.
