# syntax=docker/dockerfile:1
# ChatLPT image: the React bundle (Node) and the FastAPI app with the embedded engine (Python, uv).
# Runs as uid 10001 with a read-only root filesystem; SQLite lives on /data. Context: repository root.

FROM node:24-bookworm-slim AS web
WORKDIR /build/web
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable && corepack prepare pnpm@10.33.2 --activate
COPY web/package.json web/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM python:3.12-slim-bookworm AS python
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS app
RUN groupadd --gid 10001 chatlpt && useradd --uid 10001 --gid chatlpt --no-create-home chatlpt \
    && mkdir -p /data && chown 10001:10001 /data
WORKDIR /app
COPY --from=python /app/.venv /app/.venv
COPY --from=python /app/src /app/src
COPY --from=web /build/web/dist /app/web/dist
COPY config /app/config
ENV PATH=/app/.venv/bin:$PATH \
    CHATLPT_HTTP_HOST=0.0.0.0 CHATLPT_HTTP_PORT=3050 \
    CHATLPT_STATIC_DIR=/app/web/dist \
    CHATLPT_DATABASE_URL=sqlite+aiosqlite:////data/chatlpt.db \
    CHATLPT_PRICING_FILE=/app/config/pricing/qwen3.8-27b.json \
    CHATLPT_IMAGE_PRICING_FILE=/app/config/pricing/fal-flux-schnell.json \
    CHATLPT_IMAGES_DIR=/data/images \
    LPB_DATABASE_URL=sqlite+aiosqlite:////data/livepeer-builder.db
VOLUME ["/data"]
USER 10001:10001
EXPOSE 3050
STOPSIGNAL SIGTERM
CMD ["chatlpt", "serve"]
