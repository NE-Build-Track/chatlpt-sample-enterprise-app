.PHONY: install check test web-install web-check web-test web-build build dev images docs smoke

install:
	uv sync --all-extras
	cd web && pnpm install

web-check:
	cd web && pnpm typecheck

web-test:
	cd web && pnpm test

web-build:
	cd web && pnpm build

check: web-check
	uv run ruff check . && uv run ruff format --check .
	uv run mypy
	uv run python scripts/check_docs.py

test: web-test
	uv run pytest

build: web-build
	uv build

docs:
	uv run chatlpt gen-docs

images:
	scripts/build-images.sh

# Boot one instance per worktree (docs/RELIABILITY.md#per-worktree-boot): its own port and database.
WORKTREE := $(notdir $(CURDIR))
PORT ?= $(shell python3 -c 'import zlib; print(3100 + zlib.crc32(b"$(WORKTREE)") % 800)')
dev: web-build
	CHATLPT_HTTP_PORT=$(PORT) CHATLPT_DATABASE_URL=sqlite+aiosqlite:///./.local/$(WORKTREE).db \
	CHATLPT_PUBLIC_BASE_URL=http://localhost:$(PORT) CHATLPT_SESSION_SECRET=$${CHATLPT_SESSION_SECRET:-dev-only-not-secret-$(WORKTREE)} \
	uv run chatlpt serve

smoke:
	uv run chatlpt smoke
